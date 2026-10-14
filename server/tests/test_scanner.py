"""
The scanner — a port of LE_Model.pine, so every test here is a place the port
could quietly disagree with the script the owner trades off.

The clock tests pin the boundary instants (03:59/04:00, 09:29/09:30, 15:59/16:00,
19:59/20:00, the weekend) because those are where an off-by-one hides: a window
that is right at 11:00 and wrong at 09:30 is wrong on every trading day.
"""

from __future__ import annotations

import json
import time
import urllib.parse
from datetime import date, datetime
from typing import Any

import pytest

from newsterminal import scan, scanscore
from newsterminal.http import FetchResult
from newsterminal.scan import ET, Bar, Clock, Lvl
from newsterminal.sources import earnings as earn_src
from newsterminal.sources import scanner as scan_src


def et(y: int, mo: int, d: int, h: int, mi: int) -> datetime:
    return datetime(y, mo, d, h, mi, tzinfo=ET)


def bar(dt: datetime, o: float, h: float, lo: float, c: float, v: float = 1000.0) -> Bar:
    return Bar(int(dt.timestamp()), o, h, lo, c, v)


def day_bars(d: date, rth: list[tuple[float, float, float, float]],
             pm: list[tuple[float, float, float, float]] | None = None,
             rth_start: tuple[int, int] = (9, 30)) -> list[Bar]:
    """5-minute bars: optional pre-market from 04:00, then RTH from 09:30."""
    out: list[Bar] = []
    for i, (o, h, lo, c) in enumerate(pm or []):
        t = et(d.year, d.month, d.day, 4, 0).timestamp() + i * 300
        out.append(Bar(int(t), o, h, lo, c, 0.0))
    for i, (o, h, lo, c) in enumerate(rth):
        t = et(d.year, d.month, d.day, *rth_start).timestamp() + i * 300
        out.append(Bar(int(t), o, h, lo, c, 1000.0))
    return out


# --- the clock -----------------------------------------------------------------


@pytest.mark.parametrize(
    ("instant", "session", "trading_day", "pm_locked"),
    [
        (et(2026, 10, 13, 3, 59), "closed", date(2026, 10, 13), False),
        (et(2026, 10, 13, 4, 0), "pre", date(2026, 10, 13), False),
        (et(2026, 10, 13, 9, 29), "pre", date(2026, 10, 13), False),
        (et(2026, 10, 13, 9, 30), "rth", date(2026, 10, 13), True),
        (et(2026, 10, 13, 15, 59), "rth", date(2026, 10, 13), True),
        (et(2026, 10, 13, 16, 0), "post", date(2026, 10, 13), True),
        (et(2026, 10, 13, 19, 59), "post", date(2026, 10, 13), True),
        # 20:00 belongs to the NEXT session — the scanner is being read to plan it.
        (et(2026, 10, 13, 20, 0), "closed", date(2026, 10, 14), False),
        (et(2026, 10, 16, 20, 0), "closed", date(2026, 10, 19), False),  # Fri night → Mon
        (et(2026, 10, 17, 12, 0), "closed", date(2026, 10, 19), False),  # Saturday → Mon
    ],
)
def test_clock_boundaries(instant: datetime, session: str, trading_day: date,
                          pm_locked: bool) -> None:
    c = scan.clock_at(instant)
    assert (c.session, c.trading_day, c.pm_locked) == (session, trading_day, pm_locked)


@pytest.mark.parametrize(
    ("instant", "session", "trading_day", "pm_locked"),
    [
        # Thanksgiving is the NEXT trading day from its first minute — 04:00 is
        # not a pre-market on a day the NYSE never opens (review, 2026-10-13).
        (et(2026, 11, 26, 4, 0), "closed", date(2026, 11, 27), False),
        (et(2026, 11, 26, 10, 0), "closed", date(2026, 11, 27), False),
        # The half day after it: the regular session ends at 13:00, the late
        # session at 17:00, and 17:00 already belongs to Monday.
        (et(2026, 11, 27, 12, 59), "rth", date(2026, 11, 27), True),
        (et(2026, 11, 27, 13, 0), "post", date(2026, 11, 27), True),
        (et(2026, 11, 27, 16, 59), "post", date(2026, 11, 27), True),
        (et(2026, 11, 27, 17, 0), "closed", date(2026, 11, 30), False),
        # Christmas Eve's half day, then Christmas, then the weekend.
        (et(2026, 12, 24, 20, 0), "closed", date(2026, 12, 28), False),
    ],
)
def test_holidays_and_half_days_come_from_the_table(
        instant: datetime, session: str, trading_day: date, pm_locked: bool) -> None:
    c = scan.clock_at(instant)
    assert (c.session, c.trading_day, c.pm_locked) == (session, trading_day, pm_locked)


def test_a_half_day_regular_session_stops_at_13_00() -> None:
    """Bars after 13:00 on a half day are the late session, not the RTH high."""
    rth = [(10, 11, 9, 10)] * 6
    spike = bar(et(2026, 11, 27, 13, 30), 10, 50, 10, 20)  # a late-session spike
    bars = [*day_bars(date(2026, 11, 27), rth), spike]
    mon = scan.technicals(bars, [], scan.clock_at(et(2026, 11, 30, 8, 0)))
    assert mon.pdh == 11  # not 50


# --- parsing ---------------------------------------------------------------------


def test_parse_chart_floors_the_live_bar_and_drops_holes() -> None:
    t0 = int(et(2026, 10, 13, 5, 30).timestamp())
    doc = {"chart": {"result": [{
        "meta": {"shortName": "Apple Inc."},
        "timestamp": [t0, t0 + 300, t0 + 600, t0 + 531 + 300],  # last is 05:43:51
        "indicators": {"quote": [{
            "open": [1.0, None, 2.0, 2.5], "high": [1.5, None, 2.2, 3.0],
            "low": [0.9, None, 1.9, 2.4], "close": [1.2, None, 2.1, 2.9],
            "volume": [10, None, 5, 1],
        }]},
    }]}}
    bars, meta = scan.parse_chart(doc)
    assert meta["shortName"] == "Apple Inc."
    # The null row is gone; the 05:43:51 bar merged into the 05:40 bucket.
    assert [b.t for b in bars] == [t0, t0 + 600]
    assert bars[-1] == Bar(t0 + 600, 2.0, 3.0, 1.9, 2.9, 6.0)


def test_resample_builds_ten_minute_bars_on_the_grid() -> None:
    d = date(2026, 10, 13)
    five = day_bars(d, [(10, 11, 9, 10.5), (10.5, 12, 10, 11), (11, 11.5, 10.8, 11.2)])
    ten = scan.resample(five)
    assert len(ten) == 2
    assert ten[0] == Bar(five[0].t, 10, 12, 9, 11, 2000.0)


# --- levels across days ------------------------------------------------------------


def test_previous_day_skips_a_holiday_gap() -> None:
    thu = day_bars(date(2026, 11, 26 - 1), [(100, 110, 95, 105), (105, 108, 101, 107)])
    # Friday 27th missing (pretend holiday); Monday 30th trades.
    mon = day_bars(date(2026, 11, 30), [(106, 109, 104, 108)],
                   pm=[(106, 112, 103, 107), (107, 111, 104, 106)])
    c = scan.clock_at(et(2026, 11, 30, 10, 0))
    t = scan.technicals(thu + mon, [], c)
    assert (t.pdh, t.pdl, t.pdc) == (110, 95, 107)
    assert t.pdh_day == date(2026, 11, 25)
    assert (t.pmh, t.pml) == (112, 103)


def test_pre_market_levels_are_not_live_until_09_30() -> None:
    prev = day_bars(date(2026, 10, 12), [(100, 105, 99, 104)])
    pm = [(104, 106, 103, 105.5), (105.5, 107, 105, 106.8)]
    today = day_bars(date(2026, 10, 13), [], pm=pm)
    t = scan.technicals(prev + today, [], scan.clock_at(et(2026, 10, 13, 9, 29)))
    assert t.pm_done is False
    assert (t.pmh, t.pml) == (107, 103)
    # Price 106.8 is above PDH 105 and the forming PMH is ignored: +1, not +2.
    assert t.lvl_state == 1
    assert t.trend == 0  # trend needs PMH, which is not live yet
    assert t.progress["pmh"] is None and not t.broken["pmh"]

    t2 = scan.technicals(prev + today, [], scan.clock_at(et(2026, 10, 13, 9, 30)))
    assert t2.pm_done is True
    assert t2.lvl_state == 1  # 106.8 is above PDH but not above PMH 107
    assert t2.progress["pmh"] == pytest.approx((106.8 - 103) / (107 - 103))


def test_change_before_the_open_is_yesterdays_move() -> None:
    d2 = day_bars(date(2026, 10, 9), [(90, 91, 89, 90)])
    d1 = day_bars(date(2026, 10, 12), [(90, 100, 90, 99)])
    pm = day_bars(date(2026, 10, 13), [], pm=[(99, 100, 98, 99.99)])
    t = scan.technicals(d2 + d1 + pm, [], scan.clock_at(et(2026, 10, 13, 8, 0)))
    assert t.chg_pct == pytest.approx((99 / 90 - 1) * 100)  # Pine regChg pre-open
    assert t.ext_pct == pytest.approx((99.99 / 99 - 1) * 100)  # pre-market vs pdc


def test_daily_atr_is_the_scripts_update_rule() -> None:
    days = [scan.DayBar(date(2026, 9, i + 1), 0, 10 + i, 0, 5, 0) for i in range(3)]
    # TR: 10 (seed), then max(11,5)-min(0,5)=11, then 12.
    a = 10.0
    a += (11 - a) / 14
    a += (12 - a) / 14
    assert scan.daily_atr(days) == pytest.approx(a)


# --- the Lvl state machine -----------------------------------------------------------


def _b(o: float, h: float, lo: float, c: float, i: int = 0) -> Bar:
    return Bar(1_800_000_000 + i * 600, o, h, lo, c, 0.0)


def test_breakout_is_marked_only_when_it_crosses() -> None:
    lv = Lvl("PDH", True, 100.0)
    brk, rt = lv.step(1, False, _b(99, 101, 98.5, 100.5), 99.0, 0.25, 100.2, 99.8)
    assert (brk, rt, lv.broken) == (True, False, True)


def test_gap_through_breaks_without_a_marker() -> None:
    lv = Lvl("PDH", True, 100.0)
    brk, _ = lv.step(0, True, _b(101, 102, 100.8, 101.5), 99.0, 0.25, 101, 100.5)
    assert brk is False and lv.broken and lv.gapped


def test_failure_needs_a_close_beyond_the_buffer() -> None:
    lv = Lvl("PDH", True, 100.0)
    lv.step(1, False, _b(99, 101, 98.5, 100.5), 99.0, 0.25, 100.2, 99.8)
    lv.step(2, False, _b(100.5, 100.6, 99.7, 99.8), 100.5, 0.25, 100.2, 99.8)  # within buffer
    assert lv.broken and not lv.failed
    lv.step(3, False, _b(99.8, 99.9, 99.5, 99.6), 99.8, 0.25, 100.2, 99.8)  # 0.4 below
    assert not lv.broken and lv.failed


def test_retest_fires_once_and_needs_the_wave_at_the_level() -> None:
    lv = Lvl("PDH", True, 100.0)
    lv.step(1, False, _b(99, 101, 98.5, 100.8), 99.0, 0.25, 100.2, 99.8)
    # Wave far above the level: no retest even though the wick tagged it.
    _, rt = lv.step(2, False, _b(100.8, 101, 100.1, 100.9), 100.8, 0.25, 103, 102)
    assert rt is False
    # A bar away from the level re-arms; the next tag with the wave near fires.
    lv.step(3, False, _b(100.9, 102, 100.9, 101.8), 100.9, 0.25, 101, 100.5)
    _, rt = lv.step(4, False, _b(101.8, 101.9, 100.2, 100.6), 101.8, 0.25, 100.4, 100.1)
    assert rt is True
    # Same zone again on the next bar: disarmed until price leaves the zone.
    _, rt = lv.step(5, False, _b(100.6, 100.9, 100.1, 100.5), 100.6, 0.25, 100.4, 100.1)
    assert rt is False


def test_no_retest_on_the_break_bar_itself() -> None:
    lv = Lvl("PML", False, 50.0)
    brk, rt = lv.step(1, False, _b(50.2, 50.3, 49.6, 49.7), 50.2, 0.25, 50.1, 49.9)
    assert brk and not rt


# --- (E) setup → trigger → cancel -----------------------------------------------------


def _replay(rows: list[tuple[float, float, float, float]], w_top: float, w_bot: float,
            levels: dict[str, Lvl] | None = None) -> list[dict[str, Any]]:
    bars = [_b(*r, i=i) for i, r in enumerate(rows)]
    n = len(bars)
    lv = levels or {"PDH": Lvl("PDH", True, 90.0), "PDL": Lvl("PDL", False, 80.0),
                    "PMH": Lvl("PMH", True, 92.0), "PML": Lvl("PML", False, 85.0)}
    rp = scan.replay(bars, list(range(n)), None, lv, [1.0] * n, [w_top] * n, [w_bot] * n,
                     lv["PMH"].price, lv["PML"].price)
    return rp.signals


def test_e_setup_then_trigger() -> None:
    sig = _replay([
        (99, 101, 99, 100.5),    # clear above the wave (101 > low? low 99 < top) …
        (100.5, 102, 100.2, 101.5),  # low 100.2 > wave top 100 → arms
        (101.5, 101.8, 99.9, 100.6),  # first touch of the wave → (E) candle, trigger 101.8
        (100.6, 102.2, 100.4, 102.0),  # breaks 101.8 → (E) long
    ], w_top=100.0, w_bot=99.5)
    kinds = [(s["kind"], s["side"]) for s in sig]
    assert ("E", "long") in kinds
    e = next(s for s in sig if s["kind"] == "E")
    assert e["price"] == pytest.approx(101.8)


def test_e_setup_cancels_when_price_loses_the_wave() -> None:
    sig = _replay([
        (100.5, 102, 100.2, 101.5),  # arms
        (101.5, 101.8, 99.9, 100.6),  # (E) candle
        (100.6, 100.7, 98.0, 99.0),  # close below the wave bottom → cancelled
        (99.0, 103.0, 99.0, 102.5),  # would have triggered
    ], w_top=100.0, w_bot=99.5)
    assert not any(s["kind"] in ("E", "E_SETUP") and s["side"] == "long" for s in sig)


def test_pending_e_is_reported_as_a_setup() -> None:
    sig = _replay([
        (100.5, 102, 100.2, 101.5),
        (101.5, 101.8, 99.9, 100.6),
    ], w_top=100.0, w_bot=99.5)
    pend = [s for s in sig if s["kind"] == "E_SETUP"]
    assert len(pend) == 1 and pend[0]["price"] == pytest.approx(101.8)


# --- RS, progress, setups ---------------------------------------------------------------


def test_rs_is_the_difference_of_atr_scaled_moves() -> None:
    a, b = scan.Tech(mv_day=1.2, mv_roll=0.5), scan.Tech(mv_day=0.2, mv_roll=-0.5)
    assert scan.rs_pair(a, b) == (pytest.approx(1.0), pytest.approx(1.0))
    assert scan.rs_pair(a, None) == (None, None)


def test_pairs_match_pine_paircells() -> None:
    prog, brk = scan._pairs(105, 110, 100, None, None)
    assert prog["pdh"] == pytest.approx(0.5) and prog["pdl"] == pytest.approx(0.5)
    prog, brk = scan._pairs(111, 110, 100, 108, 101)
    assert brk["pdh"] and brk["pmh"] and prog["pdh"] is None and prog["pdl"] is None


def _tech(**kw: Any) -> scan.Tech:
    base: dict[str, Any] = dict(ok=True, last=100.0, atr_b=1.0, pdh=95.0, pdl=90.0, pmh=96.0,
                                pml=91.0, pm_done=True, rth_today=True, vwap=97.0,
                                wave_hi=98.0, wave_lo=97.5, bar_low=99.5, bar_high=100.5)
    base.update(kw)
    t = scan.Tech(**base)
    t.levels = {k: Lvl(k, k in ("PDH", "PMH"), base[k.lower()])
                for k in ("PDH", "PDL", "PMH", "PML")}
    t.progress, t.broken = scan._pairs(t.last, t.pdh, t.pdl, t.pmh, t.pml)
    return t


CLK = Clock(et(2026, 10, 13, 11, 0), "rth", date(2026, 10, 13), True)


@pytest.mark.parametrize(
    ("kw", "state", "entry_kind"),
    [
        (dict(last=96.1, bar_low=96.05), "retest", "PMH"),
        (dict(last=97.5, bar_low=97.2, vwap=95.0), "pullback", "PMH"),
        (dict(last=100.0), "extended", "EMA8"),  # 4 ATR over PMH; wave 98 nearer than VWAP 97
        (dict(last=94.7, vwap=94.0, bar_low=94.5), "approaching", "PDH"),
        (dict(last=92.5, vwap=92.0, bar_low=92.4, wave_hi=92.4, wave_lo=92.2), "chop", None),
    ],
)
def test_setup_states(kw: dict[str, Any], state: str, entry_kind: str | None) -> None:
    t = _tech(**kw)
    side = scan.side_of(scan.lvl_state_of(t.last, t.pdh, t.pdl, t.pmh, t.pml), 0.5)
    s = scan.setup_of(t, side, CLK)
    assert s["state"] == state
    assert (s["entry"] or {}).get("kind") == entry_kind


def test_failed_break_is_its_own_state() -> None:
    t = _tech(last=94.0, vwap=93.0, bar_low=93.8)
    t.levels["PDH"].failed = True
    s = scan.setup_of(t, "long", CLK)
    assert (s["state"], s["level"]) == ("failed", "PDH")


def test_before_the_bell_it_is_a_plan() -> None:
    t = _tech(rth_today=False, last=97.0, pm_done=False)
    s = scan.setup_of(t, "long", Clock(et(2026, 10, 13, 8, 0), "pre", date(2026, 10, 13), False))
    assert s["state"] == "forming" and s["level"] == "PMH"


def test_lost_vwap_is_marked() -> None:
    t = _tech(last=96.1, bar_low=96.05, vwap=97.0)
    s = scan.setup_of(t, "long", CLK)
    assert s["lost_vwap"] is True and "below VWAP" in s["note"]


# --- the score --------------------------------------------------------------------------


def _row(**kw: Any) -> dict[str, Any]:
    r: dict[str, Any] = {
        "lvl_state": 2, "rs": {"SPY": 0.6, "QQQ": 0.4}, "rvol": 1.6, "range_used": 0.5,
        "setup": {"side": "long", "state": "retest", "level": "PMH", "lost_vwap": False,
                  "entry": {"kind": "PMH", "price": 1.0, "dist_atr": 0.1}},
    }
    r.update(kw)
    return r


def test_score_parts_sum_to_the_total() -> None:
    reg = {"bias": "long", "confirm": "confirm"}
    sc = scanscore.score_row(_row(), reg, 0.5, None, None)
    by = {p["key"]: p["pts"] for p in sc["parts"]}
    assert by == {"structure": 30, "rs": 15.0, "location": 20, "volume": 7, "market": 15}
    assert sc["total"] == 87 and sc["side"] == "long"


def test_score_clamps_at_zero_and_lists_penalties() -> None:
    row = _row(lvl_state=0, rs={"SPY": -0.3, "QQQ": None}, rvol=None, range_used=1.5,
               setup={"side": "long", "state": "failed", "level": "PDH", "lost_vwap": True,
                      "entry": None})
    ev = {"title": "CPI", "in_min": 10.0, "et": "08:30", "score": 5}
    earn = {"days": 0, "when": "after", "date": "2026-10-13"}
    sc = scanscore.score_row(row, {"bias": None, "confirm": None}, None, earn, ev)
    keys = [p["key"] for p in sc["parts"]]
    assert {"fuel", "event", "earnings", "failed"} <= set(keys)
    assert sc["total"] == 0


def test_score_short_mirrors_long() -> None:
    long_ = scanscore.score_row(_row(), {"bias": "long", "confirm": "confirm"}, 0.5, None, None)
    short = scanscore.score_row(
        _row(lvl_state=-2, rs={"SPY": -0.6, "QQQ": None},
             setup={"side": "short", "state": "retest", "level": "PML", "lost_vwap": False,
                    "entry": {"kind": "PML", "price": 1.0, "dist_atr": -0.1}}),
        {"bias": "short", "confirm": "risk_off"}, -0.5, None, None)
    assert long_["total"] == short["total"]


# --- the regime ---------------------------------------------------------------------------


def _quotes(vix: float, pct: float, vix3m: float = 20.0) -> list[dict[str, Any]]:
    return [{"key": "VIX", "last": vix, "pct": pct, "chg": 0.0},
            {"key": "VIX3M", "last": vix3m, "pct": 0.0}]


@pytest.mark.parametrize(
    ("vix", "vix3m", "band"),
    [(12.0, 15.0, "grind"), (15.4, 18.0, "normal"), (22.0, 25.0, "elevated"),
     (29.0, 31.0, "stressed"), (19.0, 17.0, "stressed")],  # last: backwardation at 19
)
def test_vix_band(vix: float, vix3m: float, band: str) -> None:
    r = scanscore.regime(_quotes(vix, 0.0, vix3m), {}, [], "rth", et(2026, 10, 13, 11, 0))
    assert r["band"] == band


def test_bias_and_confirm() -> None:
    up = {"ok": True, "lvl_state": 2, "chg_pct": 0.6, "ext_pct": None, "trend": 1, "last": 700}
    r = scanscore.regime(_quotes(15, -3.0), {"SPY": up, "QQQ": up}, [], "rth",
                         et(2026, 10, 13, 11, 0))
    assert (r["bias"], r["confirm"]) == ("long", "confirm")
    r = scanscore.regime(_quotes(15, 3.0), {"SPY": up, "QQQ": up}, [], "rth",
                         et(2026, 10, 13, 11, 0))
    assert r["confirm"] == "divergence"
    flat = {"ok": True, "lvl_state": 0, "chg_pct": 0.05, "ext_pct": None, "trend": 0, "last": 1}
    r = scanscore.regime(_quotes(15, 0.5), {"SPY": flat, "QQQ": flat}, [], "rth",
                         et(2026, 10, 13, 11, 0))
    assert (r["bias"], r["confirm"]) == (None, "chop")


def test_next_event_window() -> None:
    now = et(2026, 10, 14, 8, 0)
    cal = [
        {"region": "us", "score": 5, "ts": et(2026, 10, 14, 8, 30).timestamp(), "event": "CPI",
         "et": "08:30"},
        {"region": "us", "score": 2, "ts": et(2026, 10, 14, 8, 15).timestamp(), "event": "x",
         "et": "08:15"},
        {"region": "eu", "score": 5, "ts": et(2026, 10, 14, 8, 10).timestamp(), "event": "y",
         "et": "08:10"},
    ]
    ev = scanscore.next_event(cal, now)
    assert ev is not None and ev["title"] == "CPI" and ev["in_min"] == pytest.approx(30)


# --- joins ---------------------------------------------------------------------------------


def test_wire_match_is_strict() -> None:
    now = et(2026, 10, 13, 11, 0)
    ts = now.timestamp() - 600
    wire = [{"title": "Intel cuts guidance", "ts": ts},
            {"title": "Artificial intelligence spend rises", "ts": ts},
            {"title": "Why $INTC is moving", "ts": ts}]
    got = scanscore.news_for("INTC", [], wire, ["Intel"], now)
    assert [g["title"] for g in got] == ["Intel cuts guidance", "Why $INTC is moving"]


def test_own_feed_must_name_the_company() -> None:
    assert scan_src.mentions("AAPL Stock Ticks Higher", "AAPL", ["Apple"])
    assert scan_src.mentions("Apple Needs Phones", "AAPL", ["Apple"])
    assert not scan_src.mentions("Generac Entered a Deal With Amazon", "NVDA", ["Nvidia"])
    assert scan_src.mend("Broadcom�s warning") == "Broadcom’s warning"


def test_news_kind() -> None:
    assert scanscore.news_kind("BofA upgrades AMD to Buy") == "rating"
    assert scanscore.news_kind("Coinbase Q3 earnings: what to expect") == "earnings"
    assert scanscore.news_kind("SoFi files for $1bn offering") == "filing"
    assert scanscore.news_kind("SpaceX agrees to testify") == "news"


def test_earnings_for_picks_last_night_or_this_week() -> None:
    td = date(2026, 10, 14)
    rows = [{"symbol": "NFLX", "date": "2026-10-13", "when": "after"},
            {"symbol": "JPM", "date": "2026-10-13", "when": "pre"},
            {"symbol": "TSLA", "date": "2026-10-21", "when": "after"}]
    assert scanscore.earnings_for("NFLX", rows, td)["days"] == -1  # type: ignore[index]
    assert scanscore.earnings_for("JPM", rows, td) is None  # yesterday morning is old news
    assert scanscore.earnings_for("TSLA", rows, td) is None  # beyond the week


def test_earnings_keep_watchlist_names_regardless_of_cap() -> None:
    doc = {"data": {"rows": [
        {"symbol": "SOFI", "marketCap": "$20,000,000,000", "time": "time-pre-market"},
        {"symbol": "TINY", "marketCap": "$1,000,000", "time": "time-after-hours"},
        {"symbol": "NVDA", "marketCap": "$4,000,000,000,000", "time": "time-after-hours"},
    ]}}
    plain = earn_src.parse_day(doc, "2026-10-13")
    assert [r["symbol"] for r in plain] == ["NVDA"]
    kept = earn_src.parse_day(doc, "2026-10-13", frozenset({"SOFI"}))
    assert {r["symbol"]: r["watch_only"] for r in kept} == {"NVDA": False, "SOFI": True}


def test_parse_filings_names_8k_items_and_stops_at_the_window() -> None:
    doc = {"filings": {"recent": {
        "form": ["8-K", "4", "424B5", "10-Q"],
        "filingDate": ["2026-10-13", "2026-10-12", "2026-10-11", "2026-09-01"],
        "items": ["2.02,9.01", "", "", ""],
        "primaryDocDescription": ["8-K", "FORM 4", "", "10-Q"],
        "accessionNumber": ["0001-26-1", "0001-26-2", "0001-26-3", "0001-26-4"],
        "primaryDocument": ["a.htm", "b.xml", "c.htm", "d.htm"],
        "acceptanceDateTime": ["2026-10-13T20:05:00.000Z", None, None, None],
    }}}
    got = scan_src.parse_filings(doc, 320193, date(2026, 10, 13))
    assert [g["form"] for g in got] == ["8-K", "424B5"]
    assert got[0]["desc"] == "results of operations"
    assert got[0]["url"].endswith("/320193/0001261/a.htm")


# --- the watchlist ------------------------------------------------------------------------


def test_watchlist_validation() -> None:
    ok, bad = scan_src.clean_watchlist(["aapl", "$nvda", "AAPL", "brk.b", "bad sym", "", "X" * 11])
    assert ok == ["AAPL", "NVDA", "BRK.B"]
    assert bad == ["BAD SYM", "X" * 11]
    many, over = scan_src.clean_watchlist([f"A{i}" for i in range(45)])
    assert len(many) == 40 and len(over) == 5


def test_watchlist_persists_and_falls_back(tmp_path: Any) -> None:
    p = str(tmp_path / "w.json")
    assert scan_src.load_watchlist(p) == scan_src.DEFAULT_WATCHLIST
    ok, _ = scan_src.save_watchlist(["tsla", "amd"], p)
    assert ok == ["TSLA", "AMD"] and scan_src.load_watchlist(p) == ["TSLA", "AMD"]
    # An all-invalid save keeps what was there.
    ok, bad = scan_src.save_watchlist(["!!"], p)
    assert ok == ["TSLA", "AMD"] and bad == ["!!"]


# --- volume and VWAP (regular session only: the free feed's extended bars are 0) ---


def test_rvol_by_time_of_day_and_rth_vwap() -> None:
    def day(d: date, vol: float) -> list[Bar]:
        out = []
        for i in range(6):  # 09:30–09:55
            t = et(d.year, d.month, d.day, 9, 30).timestamp() + i * 300
            out.append(Bar(int(t), 10, 11, 9, 10, vol))
        return out

    bars = day(date(2026, 10, 8), 100) + day(date(2026, 10, 9), 300)
    # Today: three completed bars by 09:45 at 400 each, plus pre-market with no volume.
    pm = day_bars(date(2026, 10, 12), [], pm=[(10, 12, 10, 11)])
    today = [Bar(int(et(2026, 10, 12, 9, 30).timestamp()) + i * 300, 10, 12, 10, 11, 400)
             for i in range(3)]
    t = scan.technicals(bars + pm + today, [], scan.clock_at(et(2026, 10, 12, 9, 45)))
    # Prior sessions to 09:45: 3×100 and 3×300 → mean 600; today 1200 → RVOL 2.
    assert t.rvol == pytest.approx(2.0)
    assert t.vwap == pytest.approx((12 + 10 + 11) / 3)
    assert t.volume == 1200


def test_no_rvol_or_vwap_before_the_bell() -> None:
    prev = day_bars(date(2026, 10, 12), [(100, 105, 99, 104)])
    pm = day_bars(date(2026, 10, 13), [], pm=[(104, 106, 103, 105)])
    t = scan.technicals(prev + pm, [], scan.clock_at(et(2026, 10, 13, 8, 0)))
    assert t.rvol is None and t.vwap is None


# --- the previous close is the official print ------------------------------------------


def test_previous_close_prefers_the_official_print() -> None:
    mon = day_bars(date(2026, 10, 12), [(100, 105, 99, 104.0)])  # 5m close misses the auction
    pm = day_bars(date(2026, 10, 13), [], pm=[(104, 105, 103.5, 104.5)])
    clk = scan.clock_at(et(2026, 10, 13, 8, 0))
    # No other source: the bar's close.
    assert scan.technicals(mon + pm, [], clk).pdc == 104.0
    # A finished day's daily bar wins over the bar…
    daily = [scan.DayBar(date(2026, 10, 12), 100, 105, 99, 104.2, 0)]
    assert scan.technicals(mon + pm, daily, clk).pdc == pytest.approx(104.2)
    # …and the chart's own official close for that day wins over both.
    t = scan.technicals(mon + pm, daily, clk, official=(date(2026, 10, 12), 104.3))
    assert t.pdc == pytest.approx(104.3)
    assert t.ext_pct == pytest.approx((104.5 / 104.3 - 1) * 100)
    # PDH/PDL stay on the bars.
    assert (t.pdh, t.pdl) == (105, 99)


def test_todays_daily_bar_is_never_a_close_during_the_session() -> None:
    mon = day_bars(date(2026, 10, 12), [(100, 105, 99, 100.0)])
    tue = day_bars(date(2026, 10, 13), [(100, 102, 99.5, 101.0)])
    daily = [scan.DayBar(date(2026, 10, 12), 100, 105, 99, 100.0, 0),
             scan.DayBar(date(2026, 10, 13), 100, 102, 99.5, 150.0, 0)]  # a mid-day copy
    t = scan.technicals(mon + tue, daily, scan.clock_at(et(2026, 10, 13, 11, 0)))
    assert t.chg_pct == pytest.approx(1.0)
    # After the bell the official print takes over today's close.
    t2 = scan.technicals(mon + tue, daily, scan.clock_at(et(2026, 10, 13, 16, 30)),
                         official=(date(2026, 10, 13), 101.5))
    assert t2.chg_pct == pytest.approx(1.5)


def test_official_close_only_after_the_bell() -> None:
    at = int(et(2026, 10, 12, 16, 0, ).timestamp()) + 1
    assert scan.official_close({"regularMarketTime": at, "regularMarketPrice": 340.97}) == (
        date(2026, 10, 12), 340.97)
    mid = int(et(2026, 10, 13, 11, 0).timestamp())
    assert scan.official_close({"regularMarketTime": mid, "regularMarketPrice": 1.0}) is None


def test_daily_bars_go_stale_after_each_close() -> None:
    mark = scan_src._last_close_mark(et(2026, 10, 13, 16, 19))
    assert datetime.fromtimestamp(mark, ET) == et(2026, 10, 12, 16, 20)
    mark = scan_src._last_close_mark(et(2026, 10, 18, 9, 0))  # Sunday → Friday
    assert datetime.fromtimestamp(mark, ET) == et(2026, 10, 16, 16, 20)


# --- the payload -------------------------------------------------------------------------


def test_session_comes_from_the_clock_not_the_data() -> None:
    clk = scan.clock_at(et(2026, 10, 13, 7, 0))
    p = scanscore.build({}, quotes=[], sectors=[], calendar=[], earnings=[], wire=[], news={},
                        filings={}, aliases={}, status=None, watchlist=["AAPL"], clock=clk,
                        now=et(2026, 10, 13, 7, 0))
    assert (p["session"], p["trading_day"], p["pm_locked"]) == ("pre", "2026-10-13", False)
    assert p["rows"][0]["ok"] is False


def test_parts_are_whole_points_that_add_up() -> None:
    sc = scanscore.score_row(_row(rs={"SPY": 0.47, "QQQ": None}),
                             {"bias": None, "confirm": None}, None, None, None)
    assert all(isinstance(p["pts"], int) for p in sc["parts"])
    assert sc["total"] == sum(p["pts"] for p in sc["parts"])


def test_rvol_note_before_the_bell() -> None:
    sc = scanscore.score_row(_row(rvol=None), {"bias": None, "confirm": None}, None, None,
                             None, session="pre")
    vol = next(p for p in sc["parts"] if p["key"] == "volume")
    assert "starts at the open" in vol["note"]


# --- the live layer and the close read ---------------------------------------------------


def ets(h: int, mi: int, s: int, d: int = 13, mo: int = 10) -> datetime:
    return datetime(2026, mo, d, h, mi, s, tzinfo=ET)


def test_a_live_trade_moves_the_newest_bar_or_opens_the_next() -> None:
    bars = [bar(et(2026, 10, 13, 10, 0), 100, 101, 99.5, 100.5),
            bar(et(2026, 10, 13, 10, 5), 100.5, 100.8, 100.2, 100.6)]
    inside = scan.with_live(bars, 101.2, int(ets(10, 7, 30).timestamp()))
    assert inside[0] == bars[0]
    assert inside[-1] == Bar(bars[-1].t, 100.5, 101.2, 100.2, 101.2, bars[-1].volume)
    nxt = scan.with_live(bars, 100.0, int(ets(10, 11, 2).timestamp()))
    assert len(nxt) == 3
    t10 = int(et(2026, 10, 13, 10, 10).timestamp())
    assert nxt[-1] == Bar(t10, 100.0, 100.0, 100.0, 100.0, 0.0)
    # A trade older than the newest bar is already inside it.
    assert scan.with_live(bars, 50.0, int(ets(10, 2, 0).timestamp())) == bars


@pytest.mark.parametrize(("now", "mark"), [
    (ets(10, 10, 5), ets(10, 0, 10)),  # the 10:10 close's prints are not all in yet
    (ets(10, 10, 10), ets(10, 10, 10)),
    (ets(10, 14, 0), ets(10, 10, 10)),
    (ets(9, 30, 15), ets(9, 30, 10)),  # the pre-market's last bar: PMH / PML final
    (ets(9, 30, 5), None),  # 09:20 is a pre-market close
    (ets(16, 0, 30), ets(16, 0, 10)),  # the bell
    (ets(16, 10, 30), None),  # post-market
    (ets(10, 15, 0, d=17), None),  # Saturday
    (ets(13, 0, 30, d=27, mo=11), ets(13, 0, 10, d=27, mo=11)),  # a half day's bell
    (ets(13, 10, 30, d=27, mo=11), None),
])
def test_close_mark(now: datetime, mark: datetime | None) -> None:
    got = scan_src.close_mark(now)
    assert got == (mark.timestamp() if mark else None)


@pytest.mark.parametrize(("now", "secs"), [
    (ets(10, 10, 5), 5.0),
    (ets(10, 10, 10), 600.0),
    (ets(10, 14, 0), 370.0),
    (ets(9, 25, 0), 310.0),  # the open's mark
    (ets(16, 0, 30), None),  # nothing until tomorrow
])
def test_next_mark_in(now: datetime, secs: float | None) -> None:
    assert scan_src.next_mark_in(now) == secs


def _spark(rows: list[Any]) -> dict[str, Any]:
    return {"spark": {"result": rows}}


def _resp(sym: str, px: float, at: int) -> dict[str, Any]:
    return {"symbol": sym, "response": [{"meta": {"regularMarketPrice": px,
                                                   "regularMarketTime": at}}]}


def test_parse_live_keeps_only_this_sessions_trades() -> None:
    at = int(ets(10, 3, 0).timestamp())
    doc = _spark([
        _resp("AAPL", 250.5, at),
        _resp("BRK-B", 480.0, at),  # Yahoo's spelling comes back as the watchlist's
        _resp("MSFT", 410.0, int(ets(16, 0, 1).timestamp())),  # the official close
        _resp("NVDA", 180.0, int(ets(15, 59, 0, d=12).timestamp())),  # yesterday
        {"symbol": "AMD", "response": [{"meta": {}}]},
    ])
    names = {"AAPL": "AAPL", "BRK-B": "BRK.B", "MSFT": "MSFT", "NVDA": "NVDA", "AMD": "AMD"}
    got = scan_src.parse_live(doc, names, date(2026, 10, 13))
    assert got == {"AAPL": scan_src.LiveQuote(250.5, at), "BRK.B": scan_src.LiveQuote(480.0, at)}
    assert scan_src.parse_live({"spark": {"result": None}}, names, date(2026, 10, 13)) == {}


def _store(tmp_path: Any, names: list[str]) -> scan_src.ScanStore:
    s = scan_src.ScanStore(str(tmp_path / "watch.json"))
    s._watch = names
    s._warm = True
    return s


def test_live_layer_reads_in_session_and_steps_back_on_failure(
        monkeypatch: Any, tmp_path: Any) -> None:
    now = ets(10, 3, 20)
    at = int(now.timestamp()) - 2

    def ok(url: str, **_kw: Any) -> FetchResult:
        syms = urllib.parse.unquote(url.split("symbols=")[1].split("&")[0]).split(",")
        body = json.dumps(_spark([_resp(s, 100.0, at) for s in syms])).encode()
        return FetchResult(True, body, "live", 0.0, None, 200)

    def refused(url: str, **_kw: Any) -> FetchResult:
        return FetchResult(False, None, "unavailable", None, "HTTP 429", 429)

    s = _store(tmp_path, ["AAPL"])
    monkeypatch.setattr(scan_src, "fetch", ok)
    st, delay = s.tick_live(now)
    assert st is not None and st.ok and delay == scan_src.LIVE_SEC
    assert set(s.live) == {"AAPL", "SPY", "QQQ", "IWM"}
    # Outside the session nothing is read, and nothing is said.
    assert s.tick_live(ets(16, 1, 0)) == (None, scan_src.LIVE_IDLE_SEC)
    # Failures step the clock back to 15 s, then 30 s; a good read resets it.
    monkeypatch.setattr(scan_src, "fetch", refused)
    assert [s.tick_live(now)[1] for _ in range(3)] == [15.0, 30.0, 30.0]
    assert s.pause_until == 0.0  # the live layer's 429 is its own, not the bars'
    monkeypatch.setattr(scan_src, "fetch", ok)
    assert s.tick_live(now)[1] == scan_src.LIVE_SEC
    # A 429 on the bars stops it outright.
    s.pause_until = time.time() + 60.0
    st, _ = s.tick_live(now)
    assert st is not None and not st.ok and "429" in (st.error or "")


def test_the_live_trade_only_lands_on_bars_read_before_it(tmp_path: Any) -> None:
    s = _store(tmp_path, ["AAPL"])
    s.bars["AAPL"] = [bar(et(2026, 10, 13, 10, 0), 100, 101, 99, 100.5)]
    s.fetched["AAPL"] = ets(10, 4, 0).timestamp()
    s.live["AAPL"] = scan_src.LiveQuote(102.0, int(ets(10, 5, 10).timestamp()))
    rth = scan.clock_at(ets(10, 6, 0))
    got = s.live_bars("AAPL", rth)
    assert got is not None and len(got) == 2 and got[-1].close == 102.0
    assert s.compute(ets(10, 6, 0))["rows"]["AAPL"]["last"] == 102.0
    # Bars read after the trade already hold it.
    s.fetched["AAPL"] = ets(10, 5, 30).timestamp()
    assert s.live_bars("AAPL", rth) is s.bars["AAPL"]
    # And outside the regular session the bars stand alone.
    s.fetched["AAPL"] = ets(10, 4, 0).timestamp()
    assert s.live_bars("AAPL", scan.clock_at(ets(16, 30, 0))) is s.bars["AAPL"]


def _chart_doc() -> bytes:
    t = int(et(2026, 10, 13, 10, 0).timestamp())
    q = {"open": [100.0], "high": [101.0], "low": [99.0], "close": [100.5], "volume": [1000]}
    return json.dumps({"chart": {"result": [{"timestamp": [t], "meta": {},
                                             "indicators": {"quote": [q]}}]}}).encode()


def test_the_close_read_fetches_everyone_fresh_and_comes_back_soon(
        monkeypatch: Any, tmp_path: Any) -> None:
    now = ets(10, 10, 12)
    monkeypatch.setattr(scan_src.time, "time", lambda: now.timestamp())
    ttls: dict[str, float] = {}

    def fake(url: str, **kw: Any) -> FetchResult:
        if "interval=5m" in url:
            ttls[url.split("/chart/")[1].split("?")[0]] = kw["ttl_sec"]
        return FetchResult(True, _chart_doc(), "live", 0.0, None, 200)

    monkeypatch.setattr(scan_src, "fetch", fake)
    s = _store(tmp_path, ["A1", "A2", "A3", "A4", "A5"])  # + SPY, QQQ, IWM: eight names
    for sym in s.symbols():
        s.fetched[sym] = now.timestamp() - 20.0  # read 10:09:52 — fresh by the rotation
        s.daily_at[sym] = now.timestamp()
    s.tick_bars(now)
    assert len(ttls) == scan_src.MAX_PER_TICK and set(ttls.values()) == {0.0}
    assert s.burst_left == 3 and s.wake_in(now) == scan_src.BURST_TICK_SEC
    s.tick_bars(now)
    assert len(ttls) == 8 and s.burst_left == 0
    # Done: back to the usual tick, the next close being ten minutes off.
    assert s.wake_in(now) == scan_src.TICK_SEC
    # Five seconds before a mark, the job wakes for it rather than a tick late.
    assert s.wake_in(ets(10, 20, 5)) == 5.0
