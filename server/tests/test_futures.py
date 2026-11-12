"""
The Futures section's chart (futures.py): Yahoo's reply read, the views built,
the overnight standing where a stock's pre-market stands.

Worked on Mon 9 Nov 2026: the Globex day opens at 18:00 ET on Sunday 8 Nov.
"""

from __future__ import annotations

from datetime import datetime
from typing import Any

from newsterminal import futures as f
from newsterminal.scan import ET, Bar


def ts(y: int, mo: int, d: int, h: int, mi: int) -> int:
    return int(datetime(y, mo, d, h, mi, tzinfo=ET).timestamp())


def doc(bars: list[tuple[int, float | None]]) -> dict[str, Any]:
    return {"chart": {"result": [{"timestamp": [t for t, _ in bars], "indicators": {"quote": [{
        "open": [c for _, c in bars], "high": [None if c is None else c + 1 for _, c in bars],
        "low": [None if c is None else c - 1 for _, c in bars], "close": [c for _, c in bars],
        "volume": [100 for _ in bars]}]}}]}}


def test_parse_keeps_whole_bars_and_drops_holes() -> None:
    got = f.parse(doc([(1000, 10.0), (1300, None), (1600, 11.0)]))
    assert [b.t for b in got] == [1000, 1600] and got[1].high == 12.0 and got[0].volume == 100.0
    assert f.parse({"chart": {"result": []}}) == [] and f.parse(None) == []


def test_a_bar_is_read_by_its_last_minute() -> None:
    # Five minutes: each bar where it opened. An hour: 09:00 holds the cash open.
    assert f.session_of(ts(2026, 11, 9, 9, 25), 300) == "pre"
    assert f.session_of(ts(2026, 11, 9, 9, 30), 300) == "rth"
    assert f.session_of(ts(2026, 11, 9, 9, 0), 3600) == "rth"
    assert f.session_of(ts(2026, 11, 9, 16, 0), 300) == "post"
    assert f.session_of(ts(2026, 11, 9, 17, 10), 300) is None   # the daily halt
    assert f.session_of(ts(2026, 11, 8, 18, 0), 300) == "pre"   # the reopen


LADDER = {"dp": 0, "rows": [
    {"price": 28285.0, "label": "Put wall 3", "kind": "put"},
    {"price": 28129.0, "label": "Prior RTH high", "kind": "ref"},
    {"price": 28109.0, "label": "ON high", "kind": "range"},
    {"price": 28064.0, "label": "VWAP since 18:00", "kind": "vwap"},
    {"price": 28049.0, "label": "Last", "kind": "last"},
    {"price": 28015.0, "label": "Prior settle", "kind": "ref"},
    {"price": 28018.0, "label": "ON low", "kind": "range"},
    {"price": 27798.0, "label": "Opening range high", "kind": "range"},
    {"price": 27391.0, "label": "Gamma flip", "kind": "flip"},
    {"price": 27316.0, "label": "Prior RTH low", "kind": "ref"},
    {"price": 28485.0, "label": "Expected move high", "kind": "em"},
    {"price": 27613.0, "label": "Expected move low", "kind": "em"},
]}


def test_a_view_carries_the_overnight_as_its_forming_range_and_the_ladder_as_lines() -> None:
    start = ts(2026, 11, 8, 18, 0)
    bars = [Bar(start + i * 300, 100, 101, 99, 100 + i % 3, 50) for i in range(200)]
    pre = f.series(bars, "10m", datetime(2026, 11, 9, 8, 0, tzinfo=ET), LADDER, "NQ")
    assert pre["ok"] and pre["tf"] == "10m" and len(pre["bars"]) == 85  # 18:00 to 08:00, ten-minute
    assert pre["levels"] == {"pdh": 28129.0, "pdl": 27316.0, "pmh": 28109.0, "pml": 28018.0,
                             "pm_done": False}
    assert {x["label"] for x in pre["lines"]} == {
        "Put wall 3", "Prior settle", "Opening range high", "Gamma flip"}
    assert pre["em"] == {"lo": 27613.0, "hi": 28485.0, "label": "EM ±436"}
    assert [s["kind"] for s in pre["sessions"]] == ["pre"]
    # Once the cash session opens, the overnight is final.
    later = f.series(bars, "10m", datetime(2026, 11, 9, 10, 0, tzinfo=ET), LADDER)
    assert later["levels"]["pm_done"]
    # The 20 and the 50 ride with the wave, one figure a bar; an average with fewer
    # bars behind it than its length is blank rather than a shorter average.
    assert len(pre["ema20"]) == len(pre["ema50"]) == len(pre["bars"])
    assert pre["ema20"][-1] is not None and pre["ema50"][-1] is not None
    assert set(pre["ema200"]) == {None}
    short = f.series(bars[:60], "10m", datetime(2026, 11, 9, 8, 0, tzinfo=ET), LADDER)
    assert len(short["bars"]) == 30 and short["ema20"][-1] is not None
    assert set(short["ema50"]) == {None}


def flat(t: int, price: float, vol: float = 100) -> Bar:
    return Bar(t, price, price, price, price, vol)


def test_vwap_starts_again_at_each_reopen_and_the_first_cut_off_day_is_blank() -> None:
    # Thursday afternoon is the tail of a day whose start is not in the download.
    thu = [flat(ts(2026, 11, 5, 15, 0) + i * 300, 70) for i in range(2)]
    fri = [flat(ts(2026, 11, 5, 18, 0) + i * 300, 50) for i in range(3)]   # Friday's day
    mon = [flat(ts(2026, 11, 8, 18, 0) + i * 300, 10) for i in range(3)]   # Monday's day
    got = f.series(thu + fri + mon, "5m", datetime(2026, 11, 8, 19, 0, tzinfo=ET), None)
    g = got["vwaps"]["globex"]
    assert g["vwap"] == [None, None, 50.0, 50.0, 50.0, 10.0, 10.0, 10.0]
    assert g["sd"][2:] == [0.0] * 6 and g["starts"] == [2, 5]
    assert got["vwap"] == g["vwap"]
    # The chart marks each reopen in the download, not the cut-off start.
    assert got["opens"] == [ts(2026, 11, 5, 18, 0), ts(2026, 11, 8, 18, 0)]
    assert got["levels"]["pdh"] is None and got["lines"] == [] and got["em"] is None


def test_the_bands_are_the_volume_weighted_deviation() -> None:
    sun = ts(2026, 11, 8, 18, 0)
    fri = ts(2026, 11, 6, 16, 55)   # Friday's day, cut off: blank
    src = [flat(fri, 1), flat(sun, 100), flat(sun + 300, 110), flat(sun + 600, 110, 200)]
    got = f.anchored(src, src, 300, "globex")
    assert got["vwap"] == [None, 100.0, 105.0, 107.5]
    # 107.5 from 100×100 and 110×300: variance (100·7.5² + 300·2.5²) / 400.
    assert got["sd"][1:] == [0.0, 5.0, round(((100 * 7.5**2 + 300 * 2.5**2) / 400) ** 0.5, 4)]


def test_the_cash_open_anchor_starts_at_0930_inside_an_hour_bar() -> None:
    # 08:00 to 10:55 on five-minute bars: 200 before the open, 100 from it.
    src = [flat(ts(2026, 11, 9, 8, 0) + i * 300, 200 if i < 18 else 100) for i in range(36)]
    got = f.series(src, "60m", datetime(2026, 11, 9, 11, 0, tzinfo=ET), None)
    rth = got["vwaps"]["rth"]
    assert [b["t"] for b in got["bars"]] == [ts(2026, 11, 9, h, 0) for h in (8, 9, 10)]
    assert rth["vwap"] == [None, 100.0, 100.0] and rth["starts"] == [1]
    # The futures day started at Sunday's 18:00, before this download: blank.
    assert got["vwaps"]["globex"]["vwap"] == [None, None, None] and got["opens"] == []


def test_the_cash_session_vwap_is_held_from_the_close_to_the_next_open() -> None:
    # As the ladder's "VWAP since 09:30" is: built 09:30 to 16:00, then a level.
    t = [ts(2026, 11, 9, 9, 25), ts(2026, 11, 9, 9, 30), ts(2026, 11, 9, 15, 55),
         ts(2026, 11, 9, 16, 0), ts(2026, 11, 9, 18, 0), ts(2026, 11, 10, 9, 30)]
    src = [flat(x, p) for x, p in zip(t, (200, 100, 100, 300, 300, 50), strict=True)]
    got = f.anchored(src, src, 300, "rth")
    assert got["vwap"] == [None, 100.0, 100.0, 100.0, 100.0, 50.0] and got["starts"] == [1, 5]
    # A day the NYSE is shut (Thanksgiving) starts nothing: Wednesday's level carries.
    assert f._period("rth", ts(2026, 11, 26, 10, 0)) is None


def test_an_anchor_inside_the_day_leaves_the_bars_before_it_to_the_day_before() -> None:
    # Mon 9 Nov 2026: London is on GMT and New York on EST, so 07:00 London is 02:00 ET.
    assert f._period("london", ts(2026, 11, 9, 1, 55)) is None
    assert str(f._period("london", ts(2026, 11, 9, 2, 0))) == "2026-11-09"
    assert f._period("rth", ts(2026, 11, 8, 18, 0)) is None          # Sunday night: Friday's
    assert str(f._period("globex", ts(2026, 11, 8, 18, 0))) == "2026-11-09"
    # The week turns at Sunday's reopen, which belongs to Monday.
    assert f._period("week", ts(2026, 11, 6, 15, 0)) == (2026, 45)
    assert f._period("week", ts(2026, 11, 8, 18, 0)) == (2026, 46)


def test_the_daily_view_has_no_vwap() -> None:
    days = [flat(ts(2026, 11, d, 0, 0), 100) for d in (3, 4, 5)]
    got = f.series(days, "D", datetime(2026, 11, 6, 12, 0, tzinfo=ET), None)
    assert got["vwaps"] is None and got["opens"] == [] and got["vwap"] == [None, None, None]


def test_a_view_it_does_not_have_says_so() -> None:
    assert not f.series([], "2h", datetime(2026, 11, 9, 8, 0, tzinfo=ET), None)["ok"]
    assert f.series([], "10m", datetime(2026, 11, 9, 8, 0, tzinfo=ET), None)["error"] == "no bars"


def test_a_vol_index_with_one_close_is_still_a_level() -> None:
    from newsterminal.sources import quotes as level_only
    resp = {"meta": {"regularMarketPrice": 43.67}, "indicators": {"quote": [{"close": [43.67]}]}}
    row = level_only._daily_row("VXSLV", "Silver vol (VXSLV)", resp)
    assert row is not None and row["last"] == 43.67 and row["day_pct"] is None
    assert level_only._daily_row("SILVER", "Silver", resp) is None
