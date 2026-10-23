"""
The implied day is three pieces of arithmetic that each fail quietly if turned
round: a sigma from the wrong index prints a plausible number for the wrong
book, "used" past 1.0 reads as room if the ratio is upside down, and rich reads
as cheap if the premium ratio is. Each is pinned to hand-worked figures here,
and the thresholds are asserted to be the stocks desk's own — the whole point
of the rows is that the two desks never disagree about a number.
"""

from __future__ import annotations

import math
from typing import Any

import pytest

from newsterminal import marketctx, optcalc, report, volterm

SQ = math.sqrt(252.0)


def q(key: str, last: float | None, **kw: float | None) -> dict[str, Any]:
    row: dict[str, Any] = {"key": key, "last": last, "prev": None, "high": None, "low": None,
                           "pct": None}
    row.update(kw)
    return row


def ctx(key: str, last: float, closes: list[float] | None = None,
        day_pct: float | None = None) -> dict[str, Any]:
    return {"key": key, "last": last, "closes": closes or [], "day_pct": day_pct}


def by_key(rows: list[dict[str, Any]]) -> dict[str, dict[str, Any]]:
    return {r["key"]: r for r in rows}


def _closes(n: int, step: float = 0.01) -> list[float]:
    """n+1 closes whose log returns alternate ±step — a known realised vol."""
    out = [100.0]
    for i in range(n):
        out.append(out[-1] * math.exp(step if i % 2 == 0 else -step))
    return out


def test_sigma_is_the_books_own_index_in_the_books_own_points() -> None:
    rows = by_key(volterm.implied_day(
        [q("NQ", 30000.0), q("ES", 8000.0), q("GC", 4000.0), q("VXN", 24.0), q("VIX", 16.0)],
        context=[ctx("GVZ", 20.0, day_pct=-1.5)],
    ))
    nq, es, gc = rows["NQ"], rows["ES"], rows["GC"]
    # NQ reads VXN, not VIX — the Nasdaq-100 has an index of its own.
    assert nq["vol_key"] == "VXN"
    assert nq["vol"] == 24.0
    assert nq["sigma_pct"] == pytest.approx(24.0 / SQ, abs=1e-3)
    assert nq["sigma"] == pytest.approx(30000.0 * 24.0 / 100.0 / SQ, abs=0.01)
    assert nq["lo"] == pytest.approx(30000.0 - nq["sigma"], abs=0.01)
    assert nq["hi"] == pytest.approx(30000.0 + nq["sigma"], abs=0.01)
    assert es["vol_key"] == "VIX"
    assert es["sigma"] == pytest.approx(8000.0 * 16.0 / 100.0 / SQ, abs=0.01)
    # GVZ is on the context feed only, with its day change under another name.
    assert gc["vol_key"] == "GVZ"
    assert gc["vol"] == 20.0
    assert gc["vol_pct"] == -1.5
    assert gc["sigma"] == pytest.approx(4000.0 * 20.0 / 100.0 / SQ, abs=0.01)
    # Decimals follow the book: whole points, quarters, tenths.
    assert (nq["dp"], es["dp"], gc["dp"]) == (0, 2, 1)


@pytest.mark.parametrize(
    ("used", "word"),
    [
        (volterm.FUEL_ROOM - 0.1, "room"),
        (volterm.FUEL_ROOM + 0.1, "normal"),
        (volterm.FUEL_STRETCHED - 0.1, "normal"),
        (volterm.FUEL_STRETCHED + 0.1, "stretched"),
    ],
)
def test_used_is_the_globex_range_against_the_sigma(used: float, word: str) -> None:
    # VIX at √252 prices exactly a 1% day, so the range in percent IS the ratio.
    prev = 8000.0
    rows = by_key(volterm.implied_day(
        [q("ES", 8010.0, prev=prev, low=prev, high=prev * (1 + used / 100.0)), q("VIX", SQ)]))
    es = rows["ES"]
    assert es["sigma_pct"] == pytest.approx(1.0, abs=1e-3)
    assert es["used"] == pytest.approx(used, abs=0.01)
    assert es["fuel"] == word


def test_fuel_word_is_marketctxs_rule() -> None:
    """The ETF fuel on the stocks desk and the books here read one function."""
    assert marketctx.fuel_word is volterm.fuel_word
    assert volterm.fuel_word(None) is None
    assert volterm.fuel_word(volterm.FUEL_ROOM) == "normal"
    assert volterm.fuel_word(volterm.FUEL_STRETCHED) == "normal"
    assert volterm.fuel_word(volterm.FUEL_STRETCHED + 1e-9) == "stretched"


@pytest.mark.parametrize(
    ("mult", "word"),
    [(optcalc.PREMIUM_CHEAP - 0.1, "cheap"), (1.0, "fair"), (optcalc.PREMIUM_RICH + 0.1, "rich")],
)
def test_premium_is_the_stocks_desks_rule(mult: float, word: str) -> None:
    closes = _closes(optcalc.RV_SESSIONS)
    rv = optcalc.realised_vol(closes)
    assert rv is not None
    rows = by_key(volterm.implied_day([q("NQ", 30000.0), q("VXN", rv * mult)],
                                      context=[ctx("NQ", 30000.0, closes=closes)]))
    nq = rows["NQ"]
    assert nq["rv20"] == rv
    assert nq["iv_rv"] == pytest.approx(mult, abs=1e-3)
    assert nq["premium"] == word
    # The realised day is the same arithmetic on the realised leg.
    assert nq["rv_day"] == pytest.approx(30000.0 * rv / 100.0 / SQ, abs=0.01)
    assert volterm.premium is optcalc.premium


def test_realised_needs_twenty_closes() -> None:
    closes = _closes(optcalc.RV_SESSIONS - 1)
    rows = by_key(volterm.implied_day([q("NQ", 30000.0), q("VXN", 24.0)],
                                      context=[ctx("NQ", 30000.0, closes=closes)]))
    assert rows["NQ"]["rv20"] is None
    assert rows["NQ"]["iv_rv"] is None
    assert rows["NQ"]["premium"] is None
    # The sigma does not depend on the realised leg.
    assert rows["NQ"]["sigma"] is not None


def test_gexygen_band_rides_along_only_when_it_is_up() -> None:
    quotes = [q("NQ", 30000.0), q("VXN", 24.0)]
    up = {"assets": {"NQ": {"ok": True, "em_lo": 29600.0, "em_hi": 30400.0, "regime": "NEG"}}}
    down = {"assets": {"NQ": {"ok": False, "em_lo": 29600.0, "em_hi": 30400.0, "regime": "NEG"}}}
    inverted = {"assets": {"NQ": {"ok": True, "em_lo": 30400.0, "em_hi": 29600.0,
                                  "regime": "POS"}}}
    a = by_key(volterm.implied_day(quotes, gex=up))["NQ"]
    assert (a["gex_lo"], a["gex_hi"], a["regime"]) == (29600.0, 30400.0, "NEG")
    b = by_key(volterm.implied_day(quotes, gex=down))["NQ"]
    assert (b["gex_lo"], b["gex_hi"], b["regime"]) == (None, None, None)
    c = by_key(volterm.implied_day(quotes, gex=inverted))["NQ"]
    assert (c["gex_lo"], c["gex_hi"]) == (None, None)
    assert c["regime"] == "POS"
    # The 1σ never defers to GEXYGEN's band.
    assert a["sigma"] == c["sigma"]


def test_missing_inputs_are_nulls_not_zeros() -> None:
    rows = volterm.implied_day([q("NQ", 30000.0, prev=29900.0), q("GC", 4000.0)])
    assert [r["key"] for r in rows] == ["NQ", "GC"]  # no ES print, no ES row
    nq = rows[0]
    assert nq["vol"] is None
    assert nq["sigma"] is None
    assert nq["lo"] is None
    assert nq["range"] is None
    assert nq["used"] is None
    assert nq["fuel"] is None
    assert nq["rv20"] is None
    assert nq["premium"] is None
    # A range with no sigma to measure it against is still a range.
    rows = volterm.implied_day([q("NQ", 30000.0, prev=29900.0, high=30100.0, low=29800.0)])
    assert rows[0]["range"] == 300.0
    assert rows[0]["used"] is None
    # A null last is not a zero price.
    assert volterm.implied_day([q("NQ", None), q("VXN", 24.0)]) == []


def test_books_keep_desk_order_not_quote_order() -> None:
    rows = volterm.implied_day([q("GC", 4000.0), q("ES", 8000.0), q("NQ", 30000.0)])
    assert [r["key"] for r in rows] == ["NQ", "ES", "GC"]


def test_the_report_reads_the_same_maps() -> None:
    assert report.EM_VOL is volterm.EM_VOL
    assert report.BOOK_DP is volterm.BOOK_DP
