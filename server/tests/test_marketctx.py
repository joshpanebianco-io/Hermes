"""The Market tab's context — every vote's threshold, the grade, breadth, fuel,
the prints' read, the Fed path, gamma in ETF prices, and the empty cases."""

from __future__ import annotations

import json
import math
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import pytest

from newsterminal import marketctx as mc

FIXTURES = Path(__file__).parent / "fixtures"
# Tue 13 Oct 2026, 10:30 ET — in the session.
NOW = datetime(2026, 10, 13, 14, 30, tzinfo=UTC)


def _q(key: str, last: float = 100.0, pct: float | None = 0.0, chg: float | None = 0.0,
       qt: float | None = None) -> dict[str, Any]:
    return {"key": key, "last": last, "pct": pct, "chg": chg, "quote_time": qt}


def _row(sym: str, *, state: int = 0, last: float = 100.0, ext: float | None = None,
         chg: float | None = 0.0, rvol: float | None = 1.0, levels: dict[str, Any] | None = None,
         options: dict[str, Any] | None = None, **extra: Any) -> dict[str, Any]:
    lv = {"pdh": 101.0, "pdl": 99.0, "pmh": 100.5, "pml": 99.5, "pdc": 100.0,
          "day_hi": None, "day_lo": None, "open": None}
    lv.update(levels or {})
    return {"sym": sym, "ok": True, "lvl_state": state, "last": last, "ext_pct": ext,
            "chg_pct": chg, "rvol": rvol, "prev_close": 100.0, "levels": lv,
            "options": options, **extra}


def _scan(session: str = "rth", *rows: dict[str, Any]) -> dict[str, Any]:
    return {"ok": True, "session": session, "trading_day": "2026-10-13", "rows": list(rows)}


def _vote(vs: list[dict[str, Any]], key: str) -> dict[str, Any]:
    return next(v for v in vs if v["key"] == key)


def _one(key: str, *, scan: dict[str, Any] | None = None,
         quotes: list[dict[str, Any]] | None = None, sectors: list[dict[str, Any]] | None = None,
         cons: dict[str, Any] | None = None, now: datetime = NOW) -> dict[str, Any]:
    return _vote(mc.votes(scan or _scan(), quotes or [], sectors or [], cons, now), key)


def _sectors(ups: int, downs: int, flat: int = 0, *, rsp: float = 0.0,
             spy: float = 0.0) -> list[dict[str, Any]]:
    keys = ["XLK", "XLC", "XLY", "XLP", "XLE", "XLF", "XLV", "XLI", "XLB", "XLRE", "XLU"]
    moves = [0.5] * ups + [-0.5] * downs + [0.0] * flat
    return ([{"key": k, "label": k, "day_pct": m} for k, m in zip(keys, moves, strict=False)]
            + [{"key": "SPY", "day_pct": spy}, {"key": "RSP", "day_pct": rsp}])


def _cons(up: int, down: int, book: str = "NQ") -> dict[str, Any]:
    mem = ([{"symbol": f"U{i}", "pct": 1.0, "contribution": 0.01} for i in range(up)]
           + [{"symbol": f"D{i}", "pct": -1.0, "contribution": -0.01} for i in range(down)])
    return {"indices": {book: {"index": "NDX" if book == "NQ" else "SPX", "members": mem}}}


# ------------------------------------------------------------------ the votes


def test_votes_are_eleven_in_order_and_neutral_with_a_reason_when_inputs_are_missing() -> None:
    vs = mc.votes({}, [], [], None, NOW)
    assert [v["key"] for v in vs] == [
        "spy_levels", "qqq_levels", "vix_dir", "vix_curve", "sectors", "equal_weight",
        "credit", "yields", "dollar", "index_volume", "participation"]
    assert all(v["vote"] == "neutral" and v["note"] for v in vs)
    c = mc.conviction(vs)
    assert (c["bias"], c["grade"], c["max_conviction"], c["neutral"]) == (None, "none", 2, 11)


def test_levels_vote_reads_the_state_and_names_the_levels_broken() -> None:
    scan = _scan("rth", _row("SPY", state=2, last=102.0), _row("QQQ", state=-1, last=98.9,
                                                                  levels={"pml": 98.0}))
    spy, qqq = _one("spy_levels", scan=scan), _one("qqq_levels", scan=scan)
    assert (spy["vote"], spy["value"]) == ("long", "▲ above PDH & PMH")
    assert (qqq["vote"], qqq["value"]) == ("short", "▼ below PDL")
    flat = _one("spy_levels", scan=_scan("rth", _row("SPY", state=0)))
    assert (flat["vote"], flat["value"]) == ("neutral", "inside its levels")
    gone = _one("spy_levels", scan=_scan("rth"))
    assert gone["vote"] == "neutral" and "no SPY bars" in gone["note"]


@pytest.mark.parametrize(("gap", "vote"), [
    (0.15, "long"), (0.14, "neutral"), (-0.14, "neutral"), (-0.15, "short"), (None, "neutral")])
def test_levels_vote_pre_market_votes_on_the_gap(gap: float | None, vote: str) -> None:
    v = _one("spy_levels", scan=_scan("pre", _row("SPY", state=2, ext=gap)))
    assert v["vote"] == vote
    if gap is not None:
        assert v["value"].startswith("gap ")


@pytest.mark.parametrize(("pct", "vote"), [
    (-1.5, "long"), (-1.49, "neutral"), (1.49, "neutral"), (1.5, "short")])
def test_vix_direction_threshold(pct: float, vote: str) -> None:
    assert _one("vix_dir", quotes=[_q("VIX", 15.0, pct)])["vote"] == vote


def test_vix_direction_missing_or_not_yet_traded_is_neutral() -> None:
    assert "no VIX quote" in _one("vix_dir")["note"]
    yesterday = datetime(2026, 10, 12, 20, 15, tzinfo=UTC).timestamp()
    stale = _one("vix_dir", scan=_scan("pre"), quotes=[_q("VIX", 15.0, 4.0, qt=yesterday)])
    assert stale["vote"] == "neutral" and "not traded today" in stale["note"]
    today = datetime(2026, 10, 13, 12, 0, tzinfo=UTC).timestamp()
    fresh = _one("vix_dir", scan=_scan("pre"), quotes=[_q("VIX", 15.0, 4.0, qt=today)])
    assert fresh["vote"] == "short"
    # In the session a quote is today's by definition — no stamp check.
    assert _one("vix_dir", quotes=[_q("VIX", 15.0, 4.0, qt=yesterday)])["vote"] == "short"


@pytest.mark.parametrize(("vix", "vix3m", "vote"), [
    (15.0, 17.0, "long"),      # 0.88: steep contango
    (16.0, 17.0, "neutral"),   # 0.94
    (17.0, 17.0, "short"),     # 1.00: flat to inverted
    (19.0, 17.0, "short"),     # backwardation
])
def test_vix_curve_threshold(vix: float, vix3m: float, vote: str) -> None:
    v = _one("vix_curve", quotes=[_q("VIX", vix), _q("VIX3M", vix3m)])
    assert v["vote"] == vote


def test_vix_curve_missing_leg_is_neutral() -> None:
    assert _one("vix_curve", quotes=[_q("VIX", 15.0)])["vote"] == "neutral"


@pytest.mark.parametrize(("ups", "downs", "flat", "vote"), [
    (7, 4, 0, "long"), (4, 7, 0, "short"), (6, 5, 0, "neutral"), (6, 3, 2, "neutral")])
def test_sectors_vote_needs_seven_of_eleven(ups: int, downs: int, flat: int, vote: str) -> None:
    v = _one("sectors", sectors=_sectors(ups, downs, flat, spy=5.0, rsp=5.0))
    assert v["vote"] == vote
    assert v["value"] == f"{ups} up · {downs} down"  # SPY and RSP are not sectors


def test_sectors_vote_too_few_or_pre_market_is_neutral() -> None:
    assert _one("sectors", sectors=_sectors(5, 0))["vote"] == "neutral"
    pre = _one("sectors", scan=_scan("pre"), sectors=_sectors(11, 0))
    assert pre["vote"] == "neutral" and "from the open" in pre["note"]


@pytest.mark.parametrize(("rsp", "spy", "vote"), [
    (0.5, 0.25, "long"), (0.0, 0.25, "short"), (0.4, 0.25, "neutral")])
def test_equal_weight_threshold(rsp: float, spy: float, vote: str) -> None:
    assert _one("equal_weight", sectors=_sectors(0, 0, rsp=rsp, spy=spy))["vote"] == vote


def test_equal_weight_missing_or_pre_market_is_neutral() -> None:
    assert _one("equal_weight", sectors=[{"key": "SPY", "day_pct": 1.0}])["vote"] == "neutral"
    pre = _one("equal_weight", scan=_scan("pre"), sectors=_sectors(0, 0, rsp=1.0, spy=0.0))
    assert pre["vote"] == "neutral"


@pytest.mark.parametrize(("pct", "vote"), [
    (0.15, "long"), (0.14, "neutral"), (-0.15, "short"), (None, "neutral")])
def test_credit_threshold(pct: float | None, vote: str) -> None:
    assert _one("credit", quotes=[_q("HYG", 77.0, pct)])["vote"] == vote


@pytest.mark.parametrize(("chg", "vote"), [
    (0.04, "short"), (0.039, "neutral"), (-0.039, "neutral"), (-0.04, "long"), (None, "neutral")])
def test_yields_threshold_in_bp(chg: float | None, vote: str) -> None:
    v = _one("yields", quotes=[_q("US10Y", 4.5, 0.0, chg)])
    assert v["vote"] == vote
    if chg == 0.04:
        assert v["value"] == "4.50% +4.0bp"


@pytest.mark.parametrize(("pct", "vote"), [
    (0.25, "short"), (0.24, "neutral"), (-0.25, "long")])
def test_dollar_threshold(pct: float, vote: str) -> None:
    assert _one("dollar", quotes=[_q("DXY", 102.0, pct)])["vote"] == vote


def test_dollar_missing_is_neutral() -> None:
    assert "no DXY" in _one("dollar")["note"]


@pytest.mark.parametrize(("rvol", "chg", "vote", "word"), [
    (1.2, 0.5, "long", "real"), (1.4, -0.3, "short", "real"), (1.4, 0.1, "neutral", "flat"),
    (0.7, 0.8, "neutral", "thin"), (1.0, 0.8, "neutral", "normal")])
def test_index_volume_confirms_the_move(rvol: float, chg: float, vote: str, word: str) -> None:
    scan = _scan("rth", _row("SPY", rvol=rvol, chg=chg), _row("QQQ", rvol=rvol, chg=chg))
    v = _one("index_volume", scan=scan)
    assert v["vote"] == vote and word in v["note"]


def test_index_volume_starts_at_the_open_and_needs_rvol() -> None:
    pre = _one("index_volume", scan=_scan("pre", _row("SPY", rvol=3.0, chg=1.0)))
    assert pre["vote"] == "neutral" and pre["note"] == "starts at the open"
    none = _one("index_volume", scan=_scan("rth", _row("SPY", rvol=None)))
    assert none["vote"] == "neutral" and "no RVOL" in none["note"]


@pytest.mark.parametrize(("up", "down", "vote"), [
    (12, 8, "long"), (11, 9, "neutral"), (8, 12, "short"), (10, 5, "neutral")])
def test_participation_threshold(up: int, down: int, vote: str) -> None:
    assert _one("participation", cons=_cons(up, down))["vote"] == vote


def test_participation_counts_a_name_once_and_waits_for_the_open() -> None:
    both = {"indices": {**_cons(12, 8, "NQ")["indices"], **_cons(12, 8, "ES")["indices"]}}
    v = _one("participation", cons=both)
    assert v["value"] == "12 up · 8 down"  # the same 20 symbols in both books
    assert _one("participation", scan=_scan("pre"), cons=both)["vote"] == "neutral"


# ------------------------------------------------------------------- the grade


def _votes(long_n: int, short_n: int, total: int = 11) -> list[dict[str, Any]]:
    vs = ["long"] * long_n + ["short"] * short_n
    vs += ["neutral"] * (total - len(vs))
    return [{"key": f"k{i}", "label": "", "value": "", "vote": v, "note": ""}
            for i, v in enumerate(vs)]


@pytest.mark.parametrize(("long_n", "short_n", "bias", "grade", "cap"), [
    (6, 1, "long", "strong", 5),
    (1, 7, "short", "strong", 5),
    (6, 2, "long", "moderate", 4),     # two against: no longer strong
    (4, 2, "long", "moderate", 4),
    (4, 3, "long", "weak", 3),         # 4 is not more than 3 + 1
    (3, 0, "long", "weak", 3),         # a side, but under four
    (2, 2, None, "none", 2),           # a tie
    (0, 0, None, "none", 2),
])
def test_grade_and_max_conviction(long_n: int, short_n: int, bias: str | None, grade: str,
                                  cap: int) -> None:
    c = mc.conviction(_votes(long_n, short_n))
    assert (c["bias"], c["grade"], c["max_conviction"]) == (bias, grade, cap)
    assert c["agree"] + c["against"] + c["neutral"] == c["total"] == 11


# ---------------------------------------------------------------------- breadth


def test_breadth_from_the_constituents_fixture() -> None:
    cons = json.loads((FIXTURES / "constituents_trim.json").read_text(encoding="utf-8"))
    b = mc.breadth(_sectors(3, 7, 1, rsp=-0.38, spy=-0.1), cons)
    assert (b["sectors_up"], b["sectors_down"], b["sectors_total"]) == (3, 7, 11)
    assert b["rsp_vs_spy"] == -0.28
    ndx, spx = b["indices"]
    # NDX: AAPL META MSFT up; MU SPCX AMAT down. |top 3| = .1828 + .0996 + .0890 of .5927.
    assert ndx == {"key": "NDX", "up": 3, "down": 3, "total": 6, "pct_up": 50.0,
                   "top3_share": 0.627, "contrib_pct": -0.082}
    assert spx["key"] == "SPX" and spx["top3_share"] == 0.654 and spx["contrib_pct"] == 0.097
    # The vote counts each leader once: 7 distinct names, under the 20 it needs.
    v = _one("participation", cons=cons)
    assert v["value"] == "3 up · 4 down" and v["vote"] == "neutral"


def test_breadth_without_constituents_keeps_the_sectors() -> None:
    b = mc.breadth(_sectors(7, 4), None)
    assert b["sectors_up"] == 7 and b["indices"] == [] and b["rsp_vs_spy"] == 0.0


# ------------------------------------------------------------------------- fuel


@pytest.mark.parametrize(("hi", "lo", "state"), [
    (100.5, 100.0, "room"),        # 0.5 of the implied move
    (100.8, 100.0, "normal"),
    (101.0, 100.0, "normal"),      # exactly the implied move: still normal
    (101.2, 100.0, "stretched"),
])
def test_fuel_states(hi: float, lo: float, state: str) -> None:
    vix = 1.0 * math.sqrt(252.0)  # a one-day implied move of exactly 1%
    spy = _row("SPY", levels={"day_hi": hi, "day_lo": lo, "open": 100.3})
    f = mc.fuel(_scan("rth", spy), [_q("VIX", vix)])[0]
    assert f["sym"] == "SPY" and f["implied_pct"] == 1.0 and f["state"] == state
    assert f["gap_pct"] == 0.3 and f["gap_vs_implied"] == 0.3


def test_fuel_reads_vxn_for_qqq_the_chain_for_iwm_and_the_gap_pre_market() -> None:
    vxn = 2.0 * math.sqrt(252.0)
    iwm = _row("IWM", options={"ok": True, "iv30": 1.5 * math.sqrt(252.0)},
               levels={"day_hi": 100.75, "day_lo": 100.0})
    by = {f["sym"]: f for f in mc.fuel(_scan("rth", _row("QQQ"), iwm), [_q("VXN", vxn)])}
    assert by["QQQ"]["implied_pct"] == 2.0
    assert by["IWM"]["implied_pct"] == 1.5 and by["IWM"]["used"] == 0.5
    assert by["SPY"] == {"sym": "SPY", "implied_pct": None, "range_pct": None, "used": None,
                         "gap_pct": None, "gap_vs_implied": None, "rvol": None, "state": None}
    no_chain = {f["sym"]: f for f in mc.fuel(_scan("rth", _row("IWM")), [])}["IWM"]
    assert no_chain["implied_pct"] is None and no_chain["state"] is None
    pre = mc.fuel(_scan("pre", _row("SPY", ext=-0.5, levels={"day_hi": 101.0, "day_lo": 99.0})),
                  [_q("VIX", 1.0 * math.sqrt(252.0))])[0]
    assert pre["range_pct"] is None and pre["gap_pct"] == -0.5 and pre["state"] is None
    assert pre["gap_vs_implied"] == -0.5


# ----------------------------------------------------------------------- prints


def _print(event: str, actual: float | None, cons: float | None, *, et: str = "08:30",
           day: int = 13, score: int = 5, region: str = "us") -> dict[str, Any]:
    hh, mm = (int(x) for x in et.split(":"))
    ts = datetime(2026, 10, day, hh + 4, mm, tzinfo=UTC).timestamp()  # EDT = UTC-4
    return {"event": event, "region": region, "score": score, "ts": ts, "date": f"2026-10-{day}",
            "et": et, "actual": actual, "consensus": cons, "previous": None,
            "surprise": None if actual is None or cons is None else actual - cons,
            "released": actual is not None, "themes": ["inflation"]}


def test_prints_read_hot_cold_and_inline_by_theme() -> None:
    rows = [
        _print("Core CPI", 0.4, 0.3),
        _print("Initial Jobless Claims", 250000, 230000),       # more claims: a weaker economy
        _print("Nonfarm Payrolls", 100000, 150000),
        _print("Retail Sales", 0.3, 0.3),
        _print("ISM Services", 50.1, 50.0),                     # within 0.5% of consensus
        _print("PPI", None, 0.2, et="10:00"),
        _print("Speech", 1.0, None, et="11:00"),
    ]
    reads = {p["title"]: p["read"] for p in mc.prints(rows, NOW)}
    assert reads == {"Core CPI": "hot", "Initial Jobless Claims": "cold",
                     "Nonfarm Payrolls": "cold", "Retail Sales": "inline",
                     "ISM Services": "inline", "PPI": None, "Speech": None}


def test_prints_window_is_today_and_tomorrow_before_the_open() -> None:
    rows = [
        _print("Tomorrow early", None, 1.0, day=14, et="08:30"),
        _print("Tomorrow late", None, 1.0, day=14, et="10:00"),
        _print("Today late", None, 1.0, et="14:00"),
        _print("Today early", None, 1.0, et="06:00"),
        _print("Minor", None, 1.0, score=2),
        _print("ECB", None, 1.0, region="eu"),
        _print("Next week", None, 1.0, day=20),
    ]
    got = [(p["et"], p["title"]) for p in mc.prints(rows, NOW)]
    assert got == [("06:00", "Today early"), ("14:00", "Today late"),
                   ("Wed 08:30", "Tomorrow early")]
    # On a Friday, "tomorrow" is Monday.
    fri = datetime(2026, 10, 16, 14, 0, tzinfo=UTC)
    mon = [p["title"] for p in mc.prints([_print("Mon", None, 1.0, day=19)], fri)]
    assert mon == ["Mon"]


# -------------------------------------------------------------------------- fed


def test_fed_path_is_cumulative_and_the_day_change_is_null() -> None:
    pm = {"meetings": [
        {"date": f"2026-1{i}-01", "label": f"M{i}", "move_bp": 5.5, "cum_bp": 5.5 * (i + 1),
         "implied_after": 3.9 + i / 100} for i in range(6)]}
    f = mc.fed(pm)
    assert f is not None
    assert (f["next"], f["next_bp"], f["next_rate"]) == ("2026-10-01", 5.5, 3.9)
    assert [p["bp"] for p in f["path"]] == [5.5, 11.0, 16.5, 22.0]  # four meetings, cumulative
    assert f["change_bp"] is None and "22% of a 25bp hike" in str(f["note"])
    hold = mc.fed({"meetings": [{"date": "2026-10-28", "label": "Oct 28", "move_bp": -1.0}]})
    assert hold is not None and "a hold is priced" in str(hold["note"])
    assert mc.fed(None) is None and mc.fed({"meetings": []}) is None


# ------------------------------------------------------------------------ macro


def test_macro_takes_the_2y_from_the_curve_and_the_10y_from_the_board() -> None:
    rates = {"curve": [{"key": "2Y", "value": 4.8, "chg_bp": 5.0},
                       {"key": "10Y", "value": 5.24, "chg_bp": 2.0}],
             "spreads": [{"key": "2s10s", "value": 44.0}]}
    quotes = [_q("US2Y", 4.06, 0.2, 0.01), _q("US10Y", 5.211, -0.5, -0.029),
              _q("DXY", 102.257, -0.32), _q("BTC", 83210.1, 1.78)]
    by = {m["key"]: m for m in mc.macro(quotes, rates)}
    assert by["US2Y"]["text"] == "4.80% +5bp"  # the Treasury's, not ^IRX's 4.06
    assert by["US10Y"]["text"] == "5.21% −2.9bp" and by["US10Y"]["move"] == -2.9
    assert by["2s10s"]["text"] == "+44bp (−3)" and by["2s10s"]["move"] == -3.0
    assert by["BTC"]["text"] == "83,210.10 +1.78%"
    assert "HYG" not in by  # absent from the board, absent here
    assert mc.macro([], None) == []


# ------------------------------------------------------------------------ gamma


def _gex(regime: str = "NEG", ok: bool = True) -> dict[str, Any]:
    levels = [{"key": "flip", "price": 20100.0}, {"key": "call_1", "price": 20400.0},
              {"key": "call_2", "price": 20500.0}, {"key": "put_1", "price": 19800.0}]
    return {"enabled": True, "assets": {"NQ": {"ok": ok, "regime": regime, "levels": levels}}}


def test_gamma_converts_futures_levels_into_etf_prices() -> None:
    g = mc.gamma(_gex(), [_q("QQQ", 500.0), _q("NQ", 20000.0)], {"ok": True, "source": "live"})
    assert g is not None and len(g) == 1  # ES absent: only QQQ
    q = g[0]
    assert (q["etf"], q["book"], q["regime"], q["ratio"]) == ("QQQ", "NQ", "NEG", 0.025)
    assert (q["flip"], q["call_wall"], q["put_wall"], q["spot"]) == (502.5, 510.0, 495.0, 500.0)
    assert "chase the move" in q["note"] and "below the flip 502.50" in q["note"]


def test_gamma_is_null_when_the_feed_is_off_down_or_stale() -> None:
    quotes = [_q("QQQ", 500.0), _q("NQ", 20000.0)]
    assert mc.gamma(None, quotes) is None
    assert mc.gamma({"enabled": False, "assets": {}}, quotes) is None
    assert mc.gamma(_gex(), quotes, {"ok": False, "error": "refused"}) is None
    assert mc.gamma(_gex(), quotes, {"ok": True, "source": "stale"}) is None
    assert mc.gamma(_gex(ok=False), quotes) is None
    assert mc.gamma(_gex(), [_q("QQQ", 500.0)]) is None  # no futures quote, no ratio


# ---------------------------------------------------------- options and peers


def test_index_options_carry_the_flow_when_the_chain_has_one() -> None:
    flow = {"call_vol": 100, "put_vol": 60, "pc_vol": 0.6, "call_oi": 1000, "put_oi": 900,
            "vol_oi": 0.08, "lean": "calls", "top": []}
    spy = _row("SPY", options={"ok": True, "iv30": 12.04, "iv_rv": 1.234, "premium": "fair",
                               "skew": 1.72, "em": [{"key": "front", "pct": 0.241}],
                               "flow": flow})
    by = {o["sym"]: o for o in mc.index_options(_scan("rth", spy, _row("QQQ")))}
    assert by["SPY"]["iv30"] == 12.0 and by["SPY"]["em_front_pct"] == 0.24
    assert by["SPY"]["flow"] == flow
    assert by["QQQ"]["iv30"] is None and by["QQQ"]["flow"] is None and by["IWM"]["flow"] is None


def test_peers_group_by_sector_with_a_watchlist_names_own_report() -> None:
    nvda = _row("NVDA", sector="XLK",
                peers=[{"sym": "TSM", "date": "2026-10-15", "when": "pre", "days": 2}])
    amd = _row("AMD", sector="XLK", peers=[{"sym": "TSM", "date": "2026-10-15", "when": "pre",
                                            "days": 2}],
               earnings={"date": "2026-10-13", "when": "after", "days": 0})
    jpm = _row("JPM", sector="XLF", earnings={"date": "2026-10-19", "when": "pre", "days": 6})
    out = mc.peers(_scan("rth", nvda, amd, jpm), [{"key": "XLK", "label": "Technology"}])
    assert out == [{"sector": "XLK", "label": "Technology",
                    "reports": [{"sym": "AMD", "date": "2026-10-13", "when": "after", "days": 0},
                                {"sym": "TSM", "date": "2026-10-15", "when": "pre", "days": 2}],
                    "watch": ["NVDA", "AMD"]}]  # JPM's report is four trading days out


# ------------------------------------------------------------------------ build


def test_build_degrades_on_empty_inputs() -> None:
    ctx = mc.build({}, {}, NOW)
    assert ctx["ok"] is False and ctx["session"] == "closed"
    assert ctx["conviction"]["grade"] == "none" and len(ctx["conviction"]["votes"]) == 11
    assert ctx["gamma"] is None and ctx["fed"] is None and ctx["prints"] == []
    assert [f["sym"] for f in ctx["fuel"]] == ["SPY", "QQQ", "IWM"]
    assert ctx["breadth"]["sectors_total"] == 0 and ctx["peers"] == [] and ctx["macro"] == []


def test_build_and_the_scanner_count_are_the_same_function() -> None:
    scan = _scan("rth", _row("SPY", state=2, last=102.0, rvol=1.5, chg=0.6),
                 _row("QQQ", state=1, last=100.7, rvol=1.5, chg=0.6))
    quotes = [_q("VIX", 14.0, -3.0), _q("VIX3M", 17.0), _q("HYG", 77.0, 0.3),
              _q("US10Y", 4.5, 0.0, -0.05), _q("DXY", 102.0, -0.4)]
    sectors = _sectors(8, 3, rsp=0.9, spy=0.5)
    ctx = mc.build(scan, {"quotes": quotes, "sectors": sectors, "constituents": _cons(15, 5)}, NOW)
    c = ctx["conviction"]
    assert (c["bias"], c["agree"], c["against"], c["grade"], c["max_conviction"]) == (
        "long", 11, 0, "strong", 5)
    assert c == mc.conviction_for(scan, quotes, sectors, _cons(15, 5), NOW)
