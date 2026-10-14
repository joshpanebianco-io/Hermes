"""The scanner's pre-open "in play" part (scanscore.in_play) — the gap in daily
ATRs, the pre-market volume against the average day, and the catalyst — on
the live figures of 06:02 ET, 2026-10-14, the morning it was built for."""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

import pytest

from newsterminal import scan, scanscore


def _row(last: float, pdc: float, atr: float, side: str = "short",
         rs: float = -0.5) -> dict[str, Any]:
    return {
        "ok": True, "last": last, "atr_d": atr, "levels": {"pdc": pdc},
        "lvl_state": 0, "rs": {"SPY": rs, "QQQ": None}, "rvol": None, "range_used": None,
        "setup": {"side": side, "state": "forming", "level": "PML", "lost_vwap": False,
                  "entry": None},
    }


def _news(n: int, age_min: float = 120.0) -> list[dict[str, Any]]:
    return [{"title": f"story {i}", "age_min": age_min, "kind": "news"} for i in range(n)]


def _pm(pct: float) -> dict[str, Any]:
    return {"volume": 1, "pct_adv": pct}


# (name, last, pdc, daily ATR, pre-market % of ADV, headlines) → in play, rounded
LIVE = [
    ("DELL", 556.48, 572.47, 26.6644, 1.07, 2, 11),   # 6.15 + 4.20 + 1
    ("SNDK", 1445.0, 1482.33, 92.6521, 1.95, 2, 11),  # 3.73 + 5.93 + 1
    ("MU", 940.5663, 953.19, 45.1166, 1.25, 8, 9),    # 2.21 + 4.64 + 2
    ("GME", 27.75, 27.22, 0.9851, 0.61, 4, 10),       # 5.39 + 2.57 + 2
    ("NVDA", 229.05, 228.52, 5.4044, 0.48, 2, 3),     # 0 + 1.88 + 1
]


@pytest.mark.parametrize(("sym", "last", "pdc", "atr", "pct", "heads", "want"), LIVE)
def test_the_mornings_worked_examples(sym: str, last: float, pdc: float, atr: float,
                                      pct: float, heads: int, want: int) -> None:
    sc = scanscore.score_row(_row(last, pdc, atr), {"bias": None, "confirm": None}, None,
                             None, None, session="pre", premkt=_pm(pct), news=_news(heads))
    ip = next(p for p in sc["parts"] if p["key"] == "inplay")
    assert (ip["pts"], ip["max"]) == (want, 22), sym


def test_dell_breaks_down_as_the_comment_says() -> None:
    pts, note = scanscore.in_play(_row(556.48, 572.47, 26.6644), _pm(1.07), None, _news(2))
    assert pts == pytest.approx(6.15 + 4.20 + 1, abs=0.01)
    assert note == "gap 0.60 ATR · pre-market 1.07% of ADV · 2 headlines since the close"


def test_a_reporter_gapping_on_volume_takes_the_whole_part() -> None:
    # Reported after yesterday's close, gapped 0.75 ATR, 4% of its day traded.
    pts, note = scanscore.in_play(_row(107.5, 100.0, 10.0), _pm(4.0),
                                  {"days": -1, "when": "after"}, [])
    assert pts == pytest.approx(22.0)
    assert "reported since the close" in note
    # More of each is still 22: every piece is capped.
    pts, _ = scanscore.in_play(_row(130.0, 100.0, 10.0), _pm(25.0),
                               {"days": 0, "when": "pre"}, _news(8))
    assert pts == pytest.approx(22.0)


def test_floors_drift_and_quiet_names_score_nothing() -> None:
    # 0.06 ATR is overnight drift; 0.2% of ADV is a quiet tape; no news.
    pts, note = scanscore.in_play(_row(100.6, 100.0, 10.0), _pm(0.2), None, [])
    assert pts == 0.0
    assert note == "gap 0.06 ATR · pre-market 0.20% of ADV"


def test_the_catalyst_tiers() -> None:
    r, pm = _row(100.0, 100.0, 10.0), _pm(0.0)
    assert scanscore.in_play(r, pm, {"days": 0, "when": "pre"}, [])[0] == 6
    assert scanscore.in_play(r, pm, {"days": 0, "when": "unspecified"}, [])[0] == 3
    # Reporting after today's close is not this morning's reason (and the
    # score's own earnings penalty covers the holding risk).
    assert scanscore.in_play(r, pm, {"days": 0, "when": "after"}, [])[0] == 0
    assert scanscore.in_play(r, pm, {"days": 2, "when": "pre"}, _news(1))[0] == 1
    assert scanscore.in_play(r, pm, None, _news(3))[0] == 2
    # A headline older than the close does not count; a kind is not a catalyst.
    assert scanscore.in_play(r, pm, None, _news(5, age_min=20 * 60))[0] == 0
    rated = [{"title": "X reiterates", "age_min": 60.0, "kind": "rating"}]
    assert scanscore.in_play(r, pm, None, rated)[0] == 1


def test_overnight_there_is_a_gap_but_no_pre_market_volume_yet() -> None:
    pts, note = scanscore.in_play(_row(105.0, 100.0, 10.0), None, None, [])
    assert pts == pytest.approx(8 * (0.5 - 0.1) / 0.65)
    assert "no pre-market volume yet" in note


def test_in_play_is_side_blind() -> None:
    up = scanscore.in_play(_row(107.5, 100.0, 10.0, side="long"), _pm(2.0), None, [])
    down = scanscore.in_play(_row(92.5, 100.0, 10.0, side="short"), _pm(2.0), None, [])
    assert up[0] == down[0]


def test_the_payload_scores_in_play_before_the_bell_from_the_nasdaq_read() -> None:
    """build() joins the pre-market read before it scores, so the part sees it."""
    clk = scan.clock_at(datetime(2026, 10, 14, 6, 2, tzinfo=scan.ET))
    row = dict(_row(556.48, 572.47, 26.6644))
    row.update({"sym": "DELL", "adv20": 1_000_000.0})
    p = scanscore.build({"rows": {"DELL": row}, "fetched": {}}, quotes=[], sectors=[],
                        calendar=[], earnings=[], wire=[], news={}, filings={}, aliases={},
                        status=None, watchlist=["DELL"], clock=clk,
                        now=datetime(2026, 10, 14, 10, 2, tzinfo=UTC),
                        premkt={"DELL": {"volume": 10_700, "high": None, "low": None,
                                         "last": None, "asof": None}})
    out = p["rows"][0]
    assert out["premkt"]["pct_adv"] == 1.07
    ip = next(x for x in out["score"]["parts"] if x["key"] == "inplay")
    assert ip["pts"] == 10  # 6.15 + 4.20, no headlines
