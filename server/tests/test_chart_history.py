"""The chart's levels, drawn as the owner's Pine script draws them (scan.chart_levels,
scan.history_levels, futures.day_levels): ONE named set, the levels of the day the last
bar is in; each earlier day's kept as plain lines over its own day; and none for a
session that has not started.

Owner, 2026-11-14: "i think there is a bug with the pdh/l and pmh/l levels on the stocks
charts ... i dont think the pmh/l levels are showing on the futures charts which should
also be from 4:00am-9:30am est", and of a first fix that drew the next session's levels
beside the last one's, "you now have double ups of the levels"."""

from __future__ import annotations

from datetime import date, datetime
from zoneinfo import ZoneInfo

from newsterminal import futures, scan
from newsterminal.scan import Bar, history_levels

ET = ZoneInfo("America/New_York")


def _bar(d: date, h: int, m: int, hi: float, lo: float) -> Bar:
    t = int(datetime(d.year, d.month, d.day, h, m, tzinfo=ET).timestamp())
    return Bar(t, (hi + lo) / 2, hi, lo, (hi + lo) / 2, 1000.0)


def _ts(d: date, h: int, m: int) -> int:
    return int(datetime(d.year, d.month, d.day, h, m, tzinfo=ET).timestamp())


MON, TUE, WED = date(2026, 10, 12), date(2026, 10, 13), date(2026, 10, 14)
BARS = [
    _bar(MON, 10, 0, 105.0, 100.0), _bar(MON, 15, 55, 104.0, 101.0),   # Monday RTH 100–105
    _bar(TUE, 4, 0, 103.5, 102.0), _bar(TUE, 9, 25, 104.2, 102.5),     # Tuesday pre 102–104.2
    _bar(TUE, 9, 30, 106.0, 103.0), _bar(TUE, 15, 55, 107.0, 104.0),   # Tuesday RTH
    _bar(TUE, 16, 30, 107.5, 106.5),                                    # after hours: not a level
]


def test_an_earlier_day_keeps_its_own_four_levels_over_its_own_bars() -> None:
    got = history_levels(BARS, WED, since=BARS[0].t)
    tue = {x["key"]: x for x in got if x["day"] == "2026-10-13"}
    # Tuesday's PMH / PML from its 04:00–09:30 bars; its PDH / PDL are Monday's RTH.
    assert {k: x["v"] for k, x in tue.items()} == {"PMH": 104.2, "PML": 102.0, "PDH": 105.0,
                                                 "PDL": 100.0}
    # As the Pine draws a day's lines: from its first bar, 04:00, to its last, 20:00.
    for x in tue.values():
        assert (x["from"], x["to"]) == (_ts(TUE, 4, 0), _ts(TUE, 20, 0))
    # Monday has no session before it in the bars: its PDH / PDL are unknown,
    # and it has no pre-market bars, so it draws nothing.
    assert not [x for x in got if x["day"] == "2026-10-12"]
    # Only days before the one asked for, and only what is still on the chart.
    assert not history_levels(BARS, TUE, since=BARS[0].t)
    assert not history_levels(BARS, WED, since=_ts(TUE, 20, 30))


def test_overnight_the_chart_names_the_last_sessions_levels_and_no_others() -> None:
    # Tuesday 21:00. The trading day has rolled to Wednesday, and Wednesday has no bar:
    # the chart shows Tuesday, so its levels are Tuesday's, as it traded against them
    # (TradingView's chart of the same bars says the same). It drew Wednesday's here:
    # "PDH" and "PDL" on Tuesday's own high and low, 107 and 103, and no PMH or PML.
    clk = scan.clock_at(datetime(2026, 10, 13, 21, 0, tzinfo=ET))
    assert clk.trading_day == WED
    tech = scan.technicals(BARS, [], clk)
    assert (tech.pdh, tech.pdl) == (107.0, 103.0)        # the row's plan is still Wednesday's
    out = scan.chart_series(BARS, clk, tech, tf="5m")
    lv = out["levels"]
    assert (lv["pdh"], lv["pdl"], lv["pmh"], lv["pml"]) == (105.0, 100.0, 104.2, 102.0)
    assert lv["day"] == "2026-10-13" and lv["pm_done"] is True
    assert lv["pd_from"] == lv["pm_from"] == _ts(TUE, 4, 0)
    # ONE SET: nothing of Wednesday's, and Monday has none of its own to keep.
    assert out["history"] == []
    # The chart opens on Tuesday's PRE-MARKET, so the candles behind its PMH and PML are
    # on it (it opened at 09:30, and a PMH could sit above every bar shown).
    assert out["bars"][0]["t"] == _ts(TUE, 4, 0)


def test_from_its_first_bar_the_trading_days_levels_are_the_charts() -> None:
    # Wednesday 08:00: Wednesday has pre-market bars, so the named set is Wednesday's,
    # the pre-market range forming, and Tuesday's is kept as plain lines over Tuesday.
    bars = [*BARS, _bar(WED, 4, 0, 108.0, 106.0), _bar(WED, 7, 55, 109.0, 107.0)]
    clk = scan.clock_at(datetime(2026, 10, 14, 8, 0, tzinfo=ET))
    tech = scan.technicals(bars, [], clk)
    out = scan.chart_series(bars, clk, tech, tf="5m")
    lv = out["levels"]
    assert (lv["pdh"], lv["pdl"], lv["pmh"], lv["pml"]) == (107.0, 103.0, 109.0, 106.0)
    assert lv["day"] == "2026-10-14" and lv["pm_done"] is False
    assert lv["pd_from"] == lv["pm_from"] == _ts(WED, 4, 0)
    assert {(h["key"], h["v"]) for h in out["history"]} == {
        ("PDH", 105.0), ("PDL", 100.0), ("PMH", 104.2), ("PML", 102.0)}
    assert {h["day"] for h in out["history"]} == {"2026-10-13"}
    # The daily view's levels are lines across the days, as they were.
    day = scan.chart_series(bars, clk, tech, tf="D")
    assert day["levels"]["pd_from"] is None and day["levels"]["pm_from"] is None


# ---- a future's levels are its own bars', 04:00 to 09:30 for the pre-market ------------

WED11, THU, FRI, SUN, NEXT_MON = (date(2026, 11, 11), date(2026, 11, 12), date(2026, 11, 13),
                                  date(2026, 11, 15), date(2026, 11, 16))
FUT = [
    _bar(THU, 10, 0, 28650.0, 28050.0), _bar(THU, 15, 55, 28600.0, 28100.0),   # Thursday cash
    _bar(THU, 18, 0, 28700.0, 28400.0),                                        # Friday's day opens
    _bar(FRI, 2, 0, 28800.0, 28300.0),                                         # 02:00: before 04:00
    _bar(FRI, 4, 0, 28580.0, 28300.0), _bar(FRI, 9, 25, 28500.0, 28260.0),     # Friday pre-market
    _bar(FRI, 9, 30, 28399.0, 28000.0), _bar(FRI, 15, 55, 28100.0, 27695.0),   # Friday cash
    _bar(FRI, 16, 30, 27800.0, 27700.0),                                       # after the close
]


def test_over_a_weekend_a_futures_chart_names_fridays_levels_and_only_those() -> None:
    levels, history = futures.day_levels(FUT, datetime(2026, 11, 14, 9, 0, tzinfo=ET))
    # Friday's PDH and PDL are Thursday's cash session. Friday's own range, 28,399 to
    # 27,695, is Monday's PDH and PDL, and Monday has not opened: it is not on the chart.
    assert (levels["pdh"], levels["pdl"]) == (28650.0, 28050.0)
    # ITS PRE-MARKET IS 04:00 TO 09:30, as a stock's: the 02:00 high of 28,800 and the
    # 18:00 reopen's 28,700 are the overnight, which is another range and not this one.
    assert (levels["pmh"], levels["pml"]) == (28580.0, 28260.0)
    assert levels["day"] == "2026-11-13" and levels["pm_done"] is True
    # Drawn from the day's first bar (the 18:00 reopen) and its 04:00, to the right edge.
    assert (levels["pd_from"], levels["pm_from"]) == (_ts(THU, 18, 0), _ts(FRI, 4, 0))
    # Thursday has no day before it here and no pre-market bars: nothing to keep.
    assert history == []


def test_a_futures_day_takes_over_at_its_reopen_and_no_other_days_levels_are_drawn() -> None:
    # Friday 08:00: the pre-market is forming.
    live, _ = futures.day_levels(FUT[:5], datetime(2026, 11, 13, 8, 0, tzinfo=ET))
    assert (live["pmh"], live["pml"], live["pm_done"]) == (28580.0, 28300.0, False)
    assert (live["pdh"], live["pdl"], live["day"]) == (28650.0, 28050.0, "2026-11-13")
    assert futures.day_levels(FUT, datetime(2026, 11, 13, 10, 0, tzinfo=ET))[0]["pm_done"] is True
    # A bar after `now` is not read: at 08:00 Friday's cash session has not happened.
    early, _ = futures.day_levels(FUT, datetime(2026, 11, 13, 8, 0, tzinfo=ET))
    assert (early["pdh"], early["pmh"], early["pml"]) == (28650.0, 28580.0, 28300.0)

    # Sunday 19:00, an hour after the reopen: Monday's day has a bar, so the named set is
    # Monday's (Friday's cash range, no pre-market yet), and Friday's is gone.
    bars = [_bar(WED11, 10, 0, 28500.0, 28200.0), *FUT, _bar(SUN, 18, 0, 27760.0, 27720.0)]
    mon, hist = futures.day_levels(bars, datetime(2026, 11, 15, 19, 0, tzinfo=ET))
    assert (mon["pdh"], mon["pdl"], mon["pmh"]) == (28399.0, 27695.0, None)
    assert mon["day"] == "2026-11-16"
    assert (mon["pd_from"], mon["pm_from"], mon["pm_done"]) == (
        _ts(SUN, 18, 0), _ts(NEXT_MON, 4, 0), False)
    # ONE SET ON A FUTURE'S CHART: no earlier day's lines at all (owner, 2026-11-14:
    # "you now have double ups of the levels"; the chart had none before).
    assert hist == []


def test_the_futures_chart_ships_them_and_the_daily_view_keeps_the_ladders() -> None:
    ladder = {"dp": 0, "rows": [{"price": 1.0, "label": "Prior RTH high", "kind": "ref"},
                                {"price": 0.5, "label": "Prior RTH low", "kind": "ref"},
                                {"price": 9.0, "label": "ON high", "kind": "range"}]}
    out = futures.series(FUT, "5m", datetime(2026, 11, 14, 9, 0, tzinfo=ET), ladder, "NQ")
    # The bars' own, not the ladder's overnight range: PMH is not 9.
    assert (out["levels"]["pdh"], out["levels"]["pmh"]) == (28650.0, 28580.0)
    assert out["history"] == []
    # A daily bar cannot say what a pre-market did: the ladder's prior session, no PMH.
    day = futures.series(FUT, "D", datetime(2026, 11, 14, 9, 0, tzinfo=ET), ladder, "NQ")
    assert (day["levels"]["pdh"], day["levels"]["pdl"], day["levels"]["pmh"]) == (1.0, 0.5, None)
    assert day["history"] == [] and day["levels"]["pd_from"] is None
