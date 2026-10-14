"""The chart's earlier-day levels (scan.history_levels) — LE_Model.pine's
"keep previous days' levels", so the pre-market highs and lows a session
traded against are on the chart overnight too."""

from __future__ import annotations

from datetime import date, datetime
from zoneinfo import ZoneInfo

from newsterminal.scan import Bar, history_levels

ET = ZoneInfo("America/New_York")


def _bar(d: date, h: int, m: int, hi: float, lo: float) -> Bar:
    t = int(datetime(d.year, d.month, d.day, h, m, tzinfo=ET).timestamp())
    return Bar(t, (hi + lo) / 2, hi, lo, (hi + lo) / 2, 1000.0)


MON, TUE, WED = date(2026, 10, 12), date(2026, 10, 13), date(2026, 10, 14)
BARS = [
    _bar(MON, 10, 0, 105.0, 100.0), _bar(MON, 15, 55, 104.0, 101.0),   # Monday RTH 100–105
    _bar(TUE, 4, 0, 103.5, 102.0), _bar(TUE, 9, 25, 104.2, 102.5),     # Tuesday pre 102–104.2
    _bar(TUE, 9, 30, 106.0, 103.0), _bar(TUE, 15, 55, 107.0, 104.0),   # Tuesday RTH
    _bar(TUE, 16, 30, 107.5, 106.5),                                    # after hours: not a level
]


def test_tuesdays_session_carries_its_own_four_levels_on_wednesday_night() -> None:
    got = history_levels(BARS, WED, since=BARS[0].t)
    tue = {x["key"]: x["v"] for x in got if x["day"] == "2026-10-13"}
    # Tuesday's PMH / PML from its 04:00–09:30 bars; its PDH / PDL are Monday's RTH.
    assert tue == {"PMH": 104.2, "PML": 102.0, "PDH": 105.0, "PDL": 100.0}
    seg = next(x for x in got if x["day"] == "2026-10-13")
    assert (seg["from"], seg["to"]) == (
        int(datetime(2026, 10, 13, 9, 30, tzinfo=ET).timestamp()),
        int(datetime(2026, 10, 13, 16, 0, tzinfo=ET).timestamp()),
    )
    # Monday has no session before it in the bars: its PDH / PDL are unknown,
    # and it has no pre-market bars, so it draws nothing.
    assert not [x for x in got if x["day"] == "2026-10-12"]


def test_the_trading_day_and_days_off_the_chart_are_not_history() -> None:
    # On Tuesday the trading day's levels are the chart's own lines, not history.
    assert not history_levels(BARS, TUE, since=BARS[0].t)
    # A chart that starts after Tuesday's close ships no Tuesday segment.
    after = int(datetime(2026, 10, 13, 16, 30, tzinfo=ET).timestamp())
    assert not history_levels(BARS, WED, since=after)
