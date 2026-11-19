"""
The small chart is the slide-out chart's opening view (owner, 2026-11-18: "can we make sure
sparks are accurate representations of the charts"). At 09:20 that morning LOW's spark ran
224.25 to 220.46, Tuesday's regular session, while LOW traded 210.13 before the bell: the
read was Yahoo's one current day without the extended hours. These pin the new cut.
"""

from __future__ import annotations

import threading
from datetime import UTC, date, datetime
from typing import Any

from newsterminal import scan, today
from newsterminal.sources import universe as u

TUE, WED = date(2026, 11, 17), date(2026, 11, 18)


def _t(d: date, hm: str) -> int:
    hh, mm = (int(x) for x in hm.split(":"))
    return int(datetime(d.year, d.month, d.day, hh, mm, tzinfo=scan.ET).timestamp())


def _bars(d: date, start: str, end: str, px: float, step: float = 0.0) -> list[scan.Bar]:
    """Five-minute bars from `start` to `end` (inclusive), closes from `px` by `step`."""
    out, t, stop = [], _t(d, start), _t(d, end)
    while t <= stop:
        out.append(scan.Bar(t, px, px, px, px, 100.0))
        px = round(px + step, 4)
        t += 300
    return out


def _low_tape() -> list[scan.Bar]:
    # Tuesday: a regular session sliding 224.25 → 220.45, the 15:55 close 220.45, after
    # hours to 20:00 near 220; Wednesday's pre-market from 04:00 gapping to ~210.
    rth = _bars(TUE, "09:30", "15:55", 224.25, -0.05)
    post = _bars(TUE, "16:00", "19:55", 220.3)
    pre = _bars(WED, "04:00", "09:15", 212.0, -0.03)
    return [*_bars(TUE, "04:00", "09:25", 224.9), *rth, *post, *pre]


def test_the_spark_is_the_charts_opening_view_with_the_pre_market() -> None:
    bars = _low_tape()
    now = _t(WED, "09:22")
    pts, ref = scan.spark_of(bars, now)
    pre = [b for b in bars if b.t >= _t(WED, "04:00")]
    # Six bars of Tuesday evening, then every pre-market bar to now.
    assert len(pts) == scan.SPARK_LEAD + len(pre)
    assert pts[:scan.SPARK_LEAD] == [220.3] * scan.SPARK_LEAD
    assert pts[scan.SPARK_LEAD] == 212.0 and pts[-1] == pre[-1].close
    # Coloured against Tuesday's close: the last regular bar's without a daily copy.
    rth_last = [b for b in bars if _t(TUE, "09:30") <= b.t < _t(TUE, "16:00")][-1]
    assert ref == rth_last.close
    # A bar at or after now is not drawn, as the chart cuts it.
    assert scan.spark_of(bars, _t(WED, "09:10"))[0][-1] == pre[-3].close


def test_the_official_close_colours_it_once_the_daily_copy_has_settled() -> None:
    bars = _low_tape()
    daily = [scan.DayBar(TUE, 224.5, 226.28, 220.13, 220.46, 5e6)]
    settled = _t(TUE, "16:30")
    assert scan.spark_of(bars, _t(WED, "09:22"), daily, settled)[1] == 220.46
    # A copy read at 14:00 holds an afternoon price, not the close: the bar's is used.
    early = scan.spark_of(bars, _t(WED, "09:22"), daily, _t(TUE, "14:00"))[1]
    assert early is not None and early != 220.46


def test_in_the_session_it_runs_from_the_pre_market_through_the_open() -> None:
    bars = [*_low_tape(), *_bars(WED, "09:20", "11:00", 210.0, 0.05)]
    pts, ref = scan.spark_of(bars, _t(WED, "11:02"))
    first_pre = next(i for i, b in enumerate(bars) if b.t >= _t(WED, "04:00"))
    assert len(pts) == len(bars) - first_pre + scan.SPARK_LEAD
    assert pts[-1] == bars[-1].close and ref is not None


def test_a_day_with_no_pre_market_frames_from_the_day_before_as_the_chart_does() -> None:
    # Wednesday opens at 09:30 with no pre-market trade: the chart's latest pre-market
    # span is Tuesday's, so it frames from there.
    bars = [*_low_tape()[: -len(_bars(WED, "04:00", "09:15", 0.0))],
            *_bars(WED, "09:30", "10:00", 211.0)]
    pts, _ = scan.spark_of(bars, _t(WED, "10:02"))
    assert len(pts) == min(scan.SPARK_MAX, len(bars))
    # No pre-market in either day: the newest eighty bars, the chart's fallback.
    flat = [*_bars(TUE, "09:30", "15:55", 100.0), *_bars(WED, "09:30", "15:55", 101.0)]
    pts, ref = scan.spark_of(flat, _t(WED, "16:30"))
    assert len(pts) == scan.SPARK_FALLBACK and ref == 100.0
    assert scan.spark_of([], 0) == ([], None)


def _yahoo(sym: str, bars: list[scan.Bar], nulls: int = 0) -> dict[str, Any]:
    closes: list[float | None] = [b.close for b in bars]
    for i in range(nulls):
        closes[-1 - 2 * i] = None
    return {"symbol": sym, "response": [{"timestamp": [b.t for b in bars],
                                         "indicators": {"quote": [{"close": closes}]}}]}


def test_a_spark_read_from_yahoo_is_cut_the_same_way_and_skips_empty_bars() -> None:
    bars = _low_tape()
    now = _t(WED, "09:22")
    pts, ref, last_t = u.spark_read(_yahoo("LOW", bars), now)
    assert (pts, ref) == scan.spark_of(bars, now) and last_t == _t(WED, "09:15")
    thin, _, _ = u.spark_read(_yahoo("LOW", bars, nulls=3), now)
    assert len(thin) == len(pts) - 3
    assert u.spark_read({"symbol": "X", "response": [{}]}, now) == ([], None, None)


def test_a_read_spark_ends_on_the_streams_latest_trade_as_the_chart_does() -> None:
    last = _t(WED, "09:35")
    # In the last bar's five minutes: that bar's close moves.
    assert u.with_trade([1.0, 2.0], last, (2.5, last + 120)) == [1.0, 2.5]
    # Past them: the next bar opens on it.
    assert u.with_trade([1.0, 2.0], last, (2.7, last + 330)) == [1.0, 2.0, 2.7]
    # Older than the last bar, or nothing heard: as read.
    assert u.with_trade([1.0, 2.0], last, (9.0, last - 10)) == [1.0, 2.0]
    assert u.with_trade([1.0, 2.0], last, None) == [1.0, 2.0]
    assert u.with_trade([], None, (9.0, last)) == []


def test_the_store_prefers_the_charts_own_bars_and_lays_both_fields() -> None:
    last = _t(WED, "09:35")
    s = u.UniverseStore.__new__(u.UniverseStore)
    s.sparks = {"LOW": (0.0, [1.0, 2.0], 1.5, last), "TGT": (0.0, [3.0, 4.0], None, last)}
    s.held_spark = lambda sym: ([9.0, 8.0], 8.5) if sym == "LOW" else None
    s.live_trade = lambda sym: (4.2, last + 60) if sym == "TGT" else None
    assert s.spark_pair("LOW") == ([9.0, 8.0], 8.5)
    assert s.spark_pair("TGT") == ([3.0, 4.2], None)
    assert s.spark_pair("NONE") == (None, None)
    row: dict[str, Any] = {"sym": "LOW"}
    s.fill_spark(row)
    assert row["spark"] == [9.0, 8.0] and row["spark_ref"] == 8.5


def test_a_tracked_row_on_the_list_draws_the_lists_spark() -> None:
    t = {"sym": "LOW", "rank": 2, "score": 16.9, "lean": "short", "chg": -2.81,
         "gap_atr": 1.04, "vol_pct": 1.0, "last": 214.26, "tracked": True,
         "levels": {"pdh": 226.28, "pdl": 220.13, "pmh": 229.24, "pml": 212.34},
         "move": "pre", "plan": {}, "why": [], "spark": [212.0, 210.1], "spark_ref": 220.46}
    eng = {"sym": "LOW", "ok": True, "score": {"total": 40, "side": "short", "parts": []},
           "setup": {"state": "forming"}, "lvl_state": -1, "levels": {}, "catalyst": None,
           "spark": [224.25, 220.46]}
    row = today.scan_row(t, eng, "pre", None)
    assert row["spark"] == [212.0, 210.1] and row["spark_ref"] == 220.46
    # The untracked path carries both too.
    wide = today.scan_row(t, None, "pre", {})
    assert wide["spark"] == [212.0, 210.1] and wide["spark_ref"] == 220.46


def test_the_spark_read_asks_for_two_sessions_with_the_extended_hours(monkeypatch: Any) -> None:
    seen: list[str] = []

    class R:
        ok, status, error = False, 500, "x"

    def fake(url: str, **_: Any) -> R:
        seen.append(url)
        return R()

    monkeypatch.setattr(u, "fetch", fake)
    s = u.UniverseStore.__new__(u.UniverseStore)
    s.sparks, s.spark_want, s.held_spark, s.live_trade = {}, ["LOW"], None, None
    s._lock = threading.Lock()
    assert s.tick_sparks(datetime(2026, 11, 18, 14, 20, tzinfo=UTC))
    assert "range=2d" in seen[0] and "interval=5m" in seen[0] and "includePrePost=true" in seen[0]
    # Marked read even though Yahoo failed, with nothing to draw.
    assert s.sparks["LOW"][1] == [] and s.spark_pair("LOW") == ([], None)
