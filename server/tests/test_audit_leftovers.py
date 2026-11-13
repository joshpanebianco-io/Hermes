"""
The quant audit's leftovers, fixed 2026-11-13 (owner: "fix everything").

Each test is one of the items left open after the audit's three phases: a headline's
stated move held against the name's real one, two analyst calls in one headline, one
RVOL on every page, the share of an average day off the tape's own count, the Extended
hours order, and the ten-minute ATR on the regular session alone.
"""

from __future__ import annotations

from datetime import UTC, date, datetime
from typing import Any

import pytest

from newsterminal import catalysts, scan, scanscore
from newsterminal.scan import ET, Bar
from newsterminal.sources import pool, tvnews
from newsterminal.sources import universe as u


def et(y: int, mo: int, d: int, h: int, mi: int) -> datetime:
    return datetime(y, mo, d, h, mi, tzinfo=ET)


def _h(title: str, age_min: float = 300.0) -> dict[str, Any]:
    return {"title": title, "age_min": age_min, "publisher": "Yahoo Finance"}


# ---- a headline's number is the market's verdict only on the day it describes -------

AMD_WRAP = "Stock Market Today, Nov. 12: AMD Jumps 5.9% on Bank of America Price Target"
PLTR = "Palantir stock falls 19% as Wall Street spots a warning"


@pytest.mark.parametrize(
    ("title", "sym", "names", "want"),
    [(AMD_WRAP, "AMD", ["AMD"], 5.9),
     (PLTR, "PLTR", ["Palantir"], -19.0),
     ("NBIS Stock Jumps Over 11% On CoreWeave Boost", "NBIS", ["Nebius"], 11.0),
     ("Micron shares sink 7 percent after guidance", "MU", ["Micron"], -7.0),
     # The revenue's 62%, not the stock's; and no number, no stated move.
     ("Nvidia Revenue Soars 62% on AI Demand", "NVDA", ["Nvidia"], None),
     ("Micron Soars on Upbeat Outlook", "MU", ["Micron"], None),
     # Somebody else's move is not this name's.
     ("Intel Jumps 8% After AMD Misses Estimates", "AMD", ["AMD"], None)],
)
def test_the_move_a_headline_states_for_the_name(title: str, sym: str, names: list[str],
                                                 want: float | None) -> None:
    assert catalysts.stated_move(title, sym, names) == want


@pytest.mark.parametrize(
    ("stated", "day", "want"),
    [(5.9, 0.3, False),     # the evening wrap of yesterday's jump, flat today
     (5.9, 5.4, True),      # today's jump
     (8.0, 2.0, True),      # a jump that faded is still today's story
     (8.0, 1.9, False),
     (-19.0, -2.0, False),  # a fall over weeks
     (5.9, -3.0, False),    # the other way today
     (1.5, -0.4, True),     # too small to tell from noise
     (5.9, None, True)],    # no price: the story stands
)
def test_a_stated_move_must_be_made_today(stated: float, day: float | None, want: bool) -> None:
    assert catalysts.stated_today(stated, day) is want


def test_the_evening_wrap_is_not_the_next_mornings_catalyst() -> None:
    def read(day: float | None, side: str = "short") -> dict[str, Any]:
        return scanscore.catalyst_read(side, None, [_h(AMD_WRAP)], None, sym="AMD",
                                       names=["AMD"], day_move=day)

    # Friday 08:30: AMD +0.3% since Thursday's close. It cost the short ten.
    flat = read(0.3)
    assert flat["pts"] == 0 and flat["earlier"] == 1
    assert "set aside, an earlier move" in flat["note"] and "says +5.9%" in flat["note"]
    # Thursday afternoon, AMD up 5.4%: today's story, against the short.
    assert read(5.4)["pts"] == -10
    # Palantir down 2% today on a "falls 19%" headline: no longer ten against the long.
    pltr = scanscore.catalyst_read("long", None, [_h(PLTR)], None, sym="PLTR",
                                   names=["Palantir"], day_move=-2.0)
    assert pltr["pts"] == 0


def test_the_row_story_passes_over_an_earlier_move() -> None:
    now = et(2026, 11, 13, 8, 30).timestamp()
    stories = [
        {"id": "1", "title": AMD_WRAP, "at": now - 15 * 3600, "syms": ["AMD"],
         "provider": "Yahoo Finance", "url": ""},
        {"id": "2", "title": "AMD Launches New Instinct Accelerator", "at": now - 3600,
         "syms": ["AMD"], "provider": "Reuters", "url": ""},
    ]
    held = tvnews.best(stories, "AMD", now, names=["AMD"])
    assert held is not None and held["id"] == "1"   # unasked, the major move leads
    flat = tvnews.best(stories, "AMD", now, names=["AMD"], move=lambda: 0.3)
    assert flat is not None and flat["id"] == "2"
    up = tvnews.best(stories, "AMD", now, names=["AMD"], move=lambda: 5.6)
    assert up is not None and up["id"] == "1"


def test_the_engines_move_since_the_close_includes_the_extended_print() -> None:
    row = {"last": 103.0, "levels": {"pdc": 100.0}}
    assert scanscore.day_move_of(row) == pytest.approx(3.0)
    assert scanscore.day_move_of({"last": 103.0, "levels": {}}) is None


def test_the_wide_read_has_a_move_since_the_close_in_each_session() -> None:
    r = {"sym": "X", "chg": 2.0, "pm_chg": 4.0, "ah_chg": 1.0, "pm_h": 1.0, "pm_l": 1.0,
         "pm_vol": 1.0, "ah_c": 1.0, "ah_vol": 1.0}
    s = u.UniverseStore(path="nul")
    s.pm_ref, s.ah_ref = {}, {}
    s.rows, s.by_sym = [r], {"X": r}
    assert s.day_move("X", et(2026, 11, 13, 8, 0)) == 4.0
    s.pm_ref = {"X": [1.0, 1.0, 1.0, 1.0, 1.0]}   # no pre-market trade yet today
    assert s.day_move("X", et(2026, 11, 13, 8, 0)) == 1.0
    assert s.day_move("X", et(2026, 11, 13, 11, 0)) == 2.0
    assert s.day_move("X", et(2026, 11, 13, 17, 0)) == pytest.approx(3.02)
    assert s.day_move("NOPE") is None


# ---- two analyst calls, two ways ----------------------------------------------------

AAPL_BOTH = "China Renaissance Upgraded Apple (AAPL) to Buy. DZ Bank Cut It to Sell"


def test_two_calls_two_ways_are_no_direction() -> None:
    assert catalysts.rated_both(AAPL_BOTH, "AAPL", ["Apple"])
    assert scanscore.headline_direction(AAPL_BOTH, "AAPL", ["Apple"]) is None
    read = scanscore.catalyst_read("long", None, [_h(AAPL_BOTH)], None, sym="AAPL",
                                   names=["Apple"], tape=0.9)
    # Not the tape's direction either, though it is an analyst story and the tape spoke.
    assert read["pts"] == 0 and read["mixed"] == 1
    assert "analysts rating it both ways" in read["note"]
    # One call alone still reads.
    one = "China Renaissance Upgrades Apple (AAPL) to Buy"
    assert not catalysts.rated_both(one, "AAPL", ["Apple"])
    assert scanscore.headline_direction(one, "AAPL", ["Apple"]) == "bull"


def test_another_names_call_is_not_this_ones() -> None:
    t = "Intel Upgraded as AMD Downgraded"
    assert not catalysts.rated_both(t, "INTC", ["Intel"])
    # Read whole, an upgrade and a downgrade were no direction for Intel.
    assert scanscore.headline_direction(t, "INTC", ["Intel"]) == "bull"
    assert scanscore.headline_direction(t, "AMD", ["AMD"]) == "bear"
    # A clause with no subject of its own speaks for the name before it.
    assert catalysts.rated_both("Apple Upgraded to Buy at Citi but Cut to Sell at DZ Bank",
                                "AAPL", ["Apple"])


# ---- one RVOL on every page -----------------------------------------------------------


def _wide(sym: str = "X", **kw: Any) -> dict[str, Any]:
    base: dict[str, Any] = {
        "sym": sym, "name": f"{sym} Inc", "exch": "NASDAQ", "close": 110.0, "chg": 4.0,
        "open": 105.0, "high": 111.0, "low": 104.0, "vol": 3e6, "gap": 2.0, "atr": 2.0,
        "pm_h": 105.0, "pm_l": 103.0, "pm_c": 104.0, "pm_chg": 4.0, "pm_vol": 2e5,
        "ah_c": 110.4, "ah_chg": 0.4, "ah_vol": 1e5, "avg": 1e6, "rv5": 2.5, "cap": 5e9,
        "float": 1e8, "sector": "XLK", "industry": "Semiconductors",
        "o1": 99.0, "h1": 104.0, "l1": 98.0, "c1": 100.0, "v1": 1e6,
        "h2": 101.0, "l2": 97.0, "c2": 99.0, "v2": 1e6,
    }
    base.update(kw)
    return base


def _store(rows: list[dict[str, Any]]) -> u.UniverseStore:
    s = u.UniverseStore(path="nul")
    s.pm_ref, s.ah_ref = {}, {}
    s.rows, s.by_sym = rows, {r["sym"]: r for r in rows}
    s.read_at = et(2026, 11, 13, 10, 45).timestamp()
    return s


def test_a_tracked_name_shows_the_lists_own_rvol_on_the_wide_pages() -> None:
    s = _store([_wide("MU"), _wide("OFF")])
    ctx = u.Ctx(rvol=lambda sym: 1.37 if sym == "MU" else None)
    got = {r["sym"]: r["rvol"] for r in s.breakouts(ctx, rvol=0.0, now=et(2026, 11, 13, 11, 0))
           ["rows"]}
    # MU is the Stocks list's 1.37; a name off the list keeps the screener's time-of-day 2.5.
    assert got == {"MU": 1.37, "OFF": 2.5}
    assert s.read_one("MU", ctx, et(2026, 11, 13, 11, 0))["rvol"] == 1.37


def test_before_the_bell_breakouts_and_extended_hours_read_the_same_rvol() -> None:
    s = _store([_wide("GAP", pm_chg=6.0, pm_c=106.0, pm_vol=8e5)])
    at = et(2026, 11, 13, 8, 0)
    b = s.breakouts(u.Ctx(), chip="all", now=at)["rows"][0]
    e = s.extended(u.Ctx(), session="pre", now=at)["rows"][0]
    # 80% of an average day pre-market, a fifth of that until five mornings are kept.
    assert b["rvol"] == e["rvol"] == 16.0
    s.pm_hist = {"GAP": [100_000.0] * 5}
    assert s.breakouts(u.Ctx(), chip="all", now=at)["rows"][0]["rvol"] == 8.0
    assert s.extended(u.Ctx(), session="pre", now=at)["rows"][0]["rvol"] == 8.0
    # The Stocks list has no RVOL before the bell, so a tracked name's stands too.
    assert s.read_one("GAP", u.Ctx(rvol=lambda _s: 2.0), at)["rvol"] == 8.0


def test_the_pool_reads_time_of_day_rvol_in_the_session() -> None:
    td = date(2026, 11, 13)
    # 10:00: 20% of an average day already, which for the half hour is 2x normal.
    r = {"symbol": "X", "close": 104.0, "change": 4.0, "atr": 4.0, "avg_vol": 1e6,
         "volume": 2e5, "rv5": 2.0}
    as_of_old = pool.in_play(r, "day", td)        # no time-of-day figure: the whole day
    assert as_of_old["rvol"] == 0.2 and "RVOL 0.20×" in as_of_old["reason"]
    ranked = pool.rank([r], scan.clock_at(et(2026, 11, 13, 10, 0)))[0]
    assert ranked["rvol"] == 2.0 and "RVOL 2.00×" in ranked["reason"]
    assert ranked["score"] - as_of_old["score"] == pytest.approx(pool.W_PMVOL, abs=0.1)


# ---- the share of an average day off the tape's count ---------------------------------


def _meta(vol: float, at: datetime) -> dict[str, Any]:
    return {"regularMarketVolume": vol, "regularMarketTime": int(at.timestamp())}


def test_todays_volume_is_the_tapes_count_once_today_has_traded() -> None:
    td = date(2026, 11, 12)
    # META on 12 Nov: 8.09M in the bars, 10.25M on the tape.
    assert scan.day_volume(8.09e6, _meta(10.25e6, et(2026, 11, 12, 16, 0)), td) == 10.25e6
    # The bars' sum where it is larger (the after-hours bars count in it).
    assert scan.day_volume(11e6, _meta(10.25e6, et(2026, 11, 12, 16, 0)), td) == 11e6
    # Before today's first regular trade the figure is yesterday's: not used.
    assert scan.day_volume(None, _meta(10.25e6, et(2026, 11, 12, 16, 0)),
                           date(2026, 11, 13)) is None
    assert scan.day_volume(None, _meta(9e6, et(2026, 11, 13, 9, 0)), date(2026, 11, 13)) is None
    assert scan.day_volume(5e6, None, td) == 5e6


# ---- the Extended hours order ---------------------------------------------------------


def test_extended_hours_ranks_the_move_on_its_volume() -> None:
    at = et(2026, 11, 13, 8, 0)
    rows = [
        # 100k shares, +15% on a $5m-share average day: a thin print.
        _wide("THIN", pm_chg=15.0, pm_c=115.0, close=100.0, pm_vol=1.2e5, avg=5e6),
        # 5M shares, +8%: a quarter of an average day already.
        _wide("HEAVY", pm_chg=8.0, pm_c=108.0, close=100.0, pm_vol=5e6, avg=2e7),
        # +6% in a name whose day is 8%: under one ATR.
        _wide("WILD", pm_chg=6.0, pm_c=106.0, close=100.0, pm_vol=2e6, avg=2e7, atr=8.0),
        # +4% in a name whose day is 1%: four ATRs.
        _wide("CALM", pm_chg=4.0, pm_c=104.0, close=100.0, pm_vol=2e6, avg=2e7, atr=1.0),
    ]
    got = _store(rows).extended(u.Ctx(), session="pre", now=at)["rows"]
    assert [r["sym"] for r in got] == ["HEAVY", "CALM", "THIN", "WILD"]
    assert {r["sym"]: r["gap_atr"] for r in got}["CALM"] == 4.0
    # A fresh major story still comes first.
    deal = {"major": True, "tag": "Deal", "tier": 1}
    got = _store(rows).extended(u.Ctx(catalyst=lambda s: deal if s == "WILD" else None),
                                session="pre", now=at)["rows"]
    assert got[0]["sym"] == "WILD"


def test_the_pool_and_extended_hours_score_a_pre_market_alike() -> None:
    # The pool's pre-market part on the same move and volume (pool.session_points).
    row = {"symbol": "X", "close": 100.0, "pm_close": 108.0, "atr": 2.0, "avg_vol": 2e7,
           "pm_volume": 5e6}
    ip = pool.in_play(row, "pre", date(2026, 11, 13))
    assert ip["score"] == round(pool.session_points(4.0, 25.0), 1)


# ---- the ten-minute ATR on the regular session -----------------------------------------


def _bars() -> list[Bar]:
    """Thursday's session at a 1.00 range a bar, then Friday's pre-market at 0.10 after a
    5-point gap, then Friday's first regular bar at a 1.00 range."""
    out: list[Bar] = []
    t = int(et(2026, 11, 12, 9, 30).timestamp())
    for i in range(78):
        out.append(Bar(t + i * 300, 100.0, 100.5, 99.5, 100.0, 1e5))
    t = int(et(2026, 11, 13, 4, 0).timestamp())
    for i in range(66):
        out.append(Bar(t + i * 300, 105.0, 105.05, 104.95, 105.0, 0.0))
    t = int(et(2026, 11, 13, 9, 30).timestamp())
    out.append(Bar(t, 105.0, 105.5, 104.5, 105.0, 2e5))
    out.append(Bar(t + 300, 105.0, 105.5, 104.5, 105.0, 2e5))
    return out


def test_the_ten_minute_atr_leaves_out_the_pre_market_and_the_gap() -> None:
    bars5 = _bars()
    bars10 = scan.resample(bars5)
    old = scan.atr(bars10)[-1]
    new = scan.atr(bars10, sessions=scan.rth_bar_days(bars5))
    # Run over everything, fourteen quiet pre-market bars took the 09:30 ATR down to a
    # third of the session's own, after the 04:00 bar's 5-point gap had swelled it.
    assert old is not None and old < 0.4
    assert new[-1] == pytest.approx(1.0)
    # The pre-market bars carry Thursday's closing value; the list lines up with the bars.
    assert len(new) == len(bars10)
    pre = next(i for i, b in enumerate(bars10) if b.t == int(et(2026, 11, 13, 7, 0).timestamp()))
    assert new[pre] == pytest.approx(1.0)


def test_the_scanners_atr_is_the_regular_sessions() -> None:
    bars5 = _bars()
    clock = scan.clock_at(et(2026, 11, 13, 9, 41))
    tech = scan.technicals(bars5, [], clock)
    assert tech.atr_b == pytest.approx(1.0)


def test_the_stop_floor_is_worked_the_same_way() -> None:
    from newsterminal import scanlog

    bars5 = _bars()
    at = int(et(2026, 11, 13, 9, 30).timestamp())
    assert scanlog.floor_at(bars5, at) == pytest.approx(scan.BUF_MULT * 1.0)


def test_rth_bar_days_marks_only_the_regular_session() -> None:
    bars5 = _bars()
    days = scan.rth_bar_days(bars5)
    assert days[int(et(2026, 11, 12, 15, 50).timestamp())] == date(2026, 11, 12)
    assert int(et(2026, 11, 13, 9, 20).timestamp()) not in days
    assert days[int(et(2026, 11, 13, 9, 30).timestamp())] == date(2026, 11, 13)
    assert all(datetime.fromtimestamp(t, UTC) for t in days)
