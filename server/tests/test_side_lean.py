"""
Which side a name is filed on: long or short.

The owner, 2026-11-15: "what determines if a stock falls in longs or shorts?", "can we
audit to make sure its funcitoning correctly?", "do the rules make sense based on what
it has actually produced?", then of the audit's recommendation "do what you recommend".

A level decides when the name is through one. Until this day a name inside its levels
took the side its relative strength against SPY leaned to; over eleven sessions that
lean pointed against the market nine times in ten and named the level that broke first
half the time, where the nearer level named it four times in five (scan.lean_of has
the figures). These pin the rule that replaced it, on both sides.
"""

from __future__ import annotations

from datetime import date, datetime
from typing import Any

import pytest

from newsterminal import scan, scanscore, today
from newsterminal.scan import ET, Clock
from newsterminal.sources import pool

# PDH 110, PMH 108, PML 96, PDL 94: the triggers are 108 above and 96 below, twelve apart.
LV = dict(pdh=110.0, pdl=94.0, pmh=108.0, pml=96.0)


def side(last: float, own: float | None = 0.0, in_session: bool = True, **lv: Any) -> str | None:
    levels = {**LV, **lv}
    pm = (levels["pmh"], levels["pml"]) if in_session else (None, None)
    state = scan.lvl_state_of(last, levels["pdh"], levels["pdl"], *pm)
    return scan.side_of(state, last, levels["pdh"], levels["pdl"], *pm, own, in_session)


# ---- a level decides --------------------------------------------------------------


@pytest.mark.parametrize(("last", "want"), [
    (111.0, "long"),      # above PDH and PMH
    (109.0, "long"),      # above PMH alone
    (95.0, "short"),      # below PML alone
    (93.0, "short"),      # below PML and PDL
])
def test_through_a_level_is_that_side_whatever_the_day_has_done(last: float, want: str) -> None:
    for own in (-2.0, 0.0, 2.0, None):
        assert side(last, own) == want


# ---- inside them, in the session: the nearer trigger ------------------------------


@pytest.mark.parametrize(("last", "want"), [
    (107.7, "long"),      # 0.3 under PMH, 11.7 over PML
    (105.0, "long"),      # three quarters of the way up
    (99.0, "short"),      # a quarter of the way up
    (96.3, "short"),      # 0.3 over PML
    (108.0, "long"),      # on the trigger is not through it
    (96.0, "short"),
])
def test_inside_the_levels_a_name_leans_to_the_nearer_trigger(last: float, want: str) -> None:
    # Whatever the day has done: down 2 ATR and nearer its high is still a long lean.
    for own in (-2.0, 0.0, 2.0, None):
        assert side(last, own) == want


def test_the_middle_fifth_between_the_triggers_is_no_side() -> None:
    # The gap is 96 to 108; its middle fifth is 100.8 to 103.2.
    for last in (101.0, 102.0, 103.0):
        assert side(last, own=1.5) is None
    assert side(103.3) == "long" and side(100.7) == "short"
    assert scan.LEAN_MID == 0.20


def test_the_trigger_is_the_nearest_high_and_the_nearest_low() -> None:
    # PMH under PDH: the high trigger is PMH. Over PDH: it is PDH.
    assert side(104.0, pmh=105.0) == "long"                # 1 under PMH 105, 8 over PML
    assert side(106.0, pmh=120.0, pdh=110.0) == "long"     # 4 under PDH, 10 over PML
    assert side(104.0, pmh=120.0, pdh=110.0) is None       # 6 under, 8 over: the middle fifth
    assert side(101.0, pml=100.0) == "short"               # 1 over PML 100, 7 under PMH


def test_relative_strength_has_no_say_in_the_side() -> None:
    """NVDA, the weekend of 14 Nov 2026: down 2% on the day and 1.1% after hours, and
    filed long because SPY had fallen further in its own ATRs. A row is read with SPY
    far weaker and far stronger than the name: the side is the same."""
    clk = Clock(datetime(2026, 11, 13, 11, 0, tzinfo=ET), "rth", date(2026, 11, 13), True)

    def tech(mv: float, **kw: Any) -> scan.Tech:
        base: dict[str, Any] = dict(ok=True, last=97.0, atr_b=1.0, atr_d=4.0, pm_done=True,
                                    rth_today=True, mv_day=mv, **LV)
        base.update(kw)
        t = scan.Tech(**base)
        t.progress, t.broken = scan._pairs(t.last, t.pdh, t.pdl, t.pmh, t.pml)
        t.lvl_state = scan.lvl_state_of(t.last, t.pdh, t.pdl, t.pmh, t.pml)
        return t

    name = tech(-0.3)                       # one over PML, eleven under PMH
    for spy_move in (-2.0, 2.0):
        row = scan.row_of("NVDA", name, tech(spy_move), None, clk)
        assert row["rs"]["SPY"] == pytest.approx(-0.3 - spy_move)
        assert row["setup"]["side"] == "short"


# ---- before the bell and overnight: the name's own move ---------------------------


@pytest.mark.parametrize(("own", "want"), [
    (0.6, "long"), (0.10, "long"), (0.09, None), (0.0, None), (None, None),
    (-0.09, None), (-0.10, "short"), (-0.6, "short"),
])
def test_before_the_bell_an_inside_name_leans_to_its_own_move(own: float | None,
                                                              want: str | None) -> None:
    # Nearer PDL than PDH, and it makes no difference: the gap decides.
    assert side(97.0, own, in_session=False) == want
    assert side(107.0, own, in_session=False) == want


def test_before_the_bell_a_level_still_decides() -> None:
    assert side(111.0, -0.5, in_session=False) == "long"
    assert side(93.0, 0.5, in_session=False) == "short"


def test_the_lean_and_the_lists_ask_for_the_same_move() -> None:
    assert scan.LEAN_MIN == scanscore.GAP_MIN == pool.GAP_MIN


def test_overnight_the_lean_reads_the_last_session_and_after_hours_together() -> None:
    """META, the weekend of 14 Nov 2026: up 2.9% on Friday, 0.2 ATR lower after hours
    with the whole market, and filed short on the after-hours drift alone. Once the day
    has rolled (20:00) the move is counted from the close before the session; when the
    pre-market opens it is the gap again."""
    def session(d: date, o: float, h: float, lo: float, c: float) -> list[scan.Bar]:
        t0 = int(datetime(d.year, d.month, d.day, 9, 30, tzinfo=ET).timestamp())
        # Open, the range, the close: three bars are a session to the engine.
        return [scan.Bar(t0, o, h, lo, o, 1000.0), scan.Bar(t0 + 300, o, h, lo, c, 1000.0),
                scan.Bar(t0 + 77 * 300, c, c, c, c, 1000.0)]

    def late(d: date, hh: int, px: float) -> list[scan.Bar]:
        t = int(datetime(d.year, d.month, d.day, hh, 0, tzinfo=ET).timestamp())
        return [scan.Bar(t, px, px, px, px, 0.0)]

    thu, fri, mon = date(2026, 11, 12), date(2026, 11, 13), date(2026, 11, 16)
    bars = (session(date(2026, 11, 11), 100.0, 104.0, 96.0, 100.0)
            + session(thu, 100.0, 104.0, 96.0, 100.0)
            + session(fri, 100.0, 104.0, 99.0, 103.0)       # up 3 on the day
            + late(fri, 19, 102.5))                          # half a point lower after hours
    # Four weeks of daily bars for the ATR, the same range every day until Friday's.
    daily = [scan.DayBar(date.fromordinal(n), 100.0, 104.0, 96.0, 100.0, 1e6)
             for n in range(date(2026, 10, 19).toordinal(), fri.toordinal())
             if date.fromordinal(n).weekday() < 5]
    daily.append(scan.DayBar(fri, 100.0, 104.0, 99.0, 103.0, 1e6))
    sat = scan.technicals(bars, daily, scan.clock_at(datetime(2026, 11, 14, 12, 0, tzinfo=ET)))
    assert sat.pdc == 103.0 and sat.atr_d and not sat.rth_today
    assert sat.mv_day == pytest.approx((102.5 - 103.0) / sat.atr_d)          # after hours alone
    assert sat.mv_lean == pytest.approx((102.5 - 100.0) / sat.atr_d)         # from Thursday's close
    row = scan.row_of("META", sat, None, None,
                      scan.clock_at(datetime(2026, 11, 14, 12, 0, tzinfo=ET)))
    assert row["lvl_state"] == 0 and row["setup"]["side"] == "long"
    # Monday's pre-market trades at the same price: the gap, from Friday's close.
    pre = scan.technicals(bars + late(mon, 7, 102.5), daily,
                          scan.clock_at(datetime(2026, 11, 16, 8, 0, tzinfo=ET)))
    assert pre.mv_lean == pre.mv_day == pytest.approx((102.5 - 103.0) / pre.atr_d)


# ---- over one high and under one low: the previous day's level --------------------


def test_through_the_days_level_one_way_and_the_pre_markets_the_other() -> None:
    # Gapped over PDH 100, now under PML 104: up on the day, a pullback toward PDH.
    up = dict(pdh=100.0, pdl=95.0, pmh=106.0, pml=104.0)
    assert scan.lvl_state_of(103.0, **up) == 0
    assert side(103.0, 0.8, **up) == "long"
    # Gapped under PDL 100, now over PMH 96: down on the day.
    down = dict(pdh=105.0, pdl=100.0, pmh=96.0, pml=94.0)
    assert scan.lvl_state_of(97.0, **down) == 0
    assert side(97.0, -0.8, **down) == "short"
    # Under a tenth of an ATR from the close there is nothing to lean on.
    assert side(103.0, 0.05, **up) is None


def test_a_missing_level_falls_back_to_the_names_own_move() -> None:
    assert scan.lean_of(100.0, None, None, None, None, 0.4, True) == "long"
    assert scan.lean_of(100.0, 110.0, None, None, None, -0.4, True) == "short"
    assert scan.lean_of(None, 110.0, 90.0, None, None, 0.4, True) is None


# ---- both sides -------------------------------------------------------------------


def test_the_mirror_of_every_case_is_the_other_side() -> None:
    """Turn the prices over around 102 (every high a low) and the day's move with them:
    the answer must be the other side everywhere, in the session and before it."""
    flip = {"long": "short", "short": "long", None: None}
    m = 102.0
    for tenth in range(900, 1141, 3):
        last = tenth / 10.0
        for own in (-1.0, -0.1, 0.0, 0.1, 1.0, None):
            for in_session in (True, False):
                a = side(last, own, in_session)
                b = side(2 * m - last, None if own is None else -own, in_session,
                         pdh=2 * m - LV["pdl"], pdl=2 * m - LV["pdh"],
                         pmh=2 * m - LV["pml"], pml=2 * m - LV["pmh"])
                assert b == flip[a], (last, own, in_session, a, b)


# ---- the Scanner's list: one rule for a tracked name and an untracked one ---------


def _list_row(lean: str | None, **kw: Any) -> dict[str, Any]:
    base: dict[str, Any] = {"sym": "NVDA", "rank": 3, "last": 161.0, "chg": -2.0, "move": "day",
                            "score": 12.0, "score_max": pool.SCORE_MAX, "why": ["day ▼ 0.33 ATR"],
                            "story": None, "lean": lean}
    base.update(kw)
    return base


def _engine_row(side_: str | None, lvl_state: int = 0, state: str = "forming") -> dict[str, Any]:
    return {"sym": "NVDA", "ok": True, "last": 161.0, "atr_b": 0.5, "lvl_state": lvl_state,
            "levels": {"pdh": 170.0, "pdl": 158.4, "pmh": None, "pml": None, "pdc": 162.85},
            "score": {"total": 40, "side": side_, "parts": []},
            "setup": {"side": side_, "state": state, "level": "PDH", "entry": None,
                      "note": "Plan: break of PDH 170.00, then the retest"},
            "catalyst": None}


def test_a_tracked_name_inside_its_levels_takes_the_lists_lean_and_its_plan() -> None:
    got = today.scan_row(_list_row("short"), _engine_row("long"), "overnight", None)
    assert got["score"]["side"] == "short"
    assert got["setup"] == {"side": "short", "state": "forming", "level": "PDL",
                            "entry": {"kind": "PDL", "price": 158.4, "dist_atr": 5.2},
                            "note": "Plan: break of PDL 158.40, then the retest"}
    # And the mirror: a long lean over a short engine side, holding above nothing yet.
    got = today.scan_row(_list_row("long", chg=2.0), _engine_row("short"), "pre", None)
    assert got["score"]["side"] == got["setup"]["side"] == "long"
    assert got["setup"]["note"] == "Plan: break of PDH 170.00, then the retest"


def test_a_tracked_name_through_a_level_keeps_the_engines_side() -> None:
    eng = _engine_row("long", lvl_state=1)
    got = today.scan_row(_list_row("short"), eng, "overnight", None)
    assert got["score"]["side"] == "long" and got["setup"] == eng["setup"]


def test_no_lean_on_the_list_leaves_the_engines_side() -> None:
    eng = _engine_row("long")
    got = today.scan_row(_list_row(None), eng, "overnight", None)
    assert got["score"]["side"] == "long" and got["setup"] == eng["setup"]
    # An engine with no side takes the list's, as it always did.
    got = today.scan_row(_list_row("short"), _engine_row(None), "pre", None)
    assert got["score"]["side"] == "short"


def test_after_the_close_and_in_the_session_the_engine_reads_its_own_day() -> None:
    # Between the close and 20:00 the engine is still reading the session that ended
    # (its setup is a state, not a plan), so its side stands.
    eng = _engine_row("long", state="chop")
    assert today.scan_row(_list_row("short"), eng, "after", None)["score"]["side"] == "long"
    got = today.scan_row(_list_row("short"), _engine_row("long"), "session", None)
    assert got["score"]["side"] == "long"


def test_an_untracked_row_over_one_high_and_under_one_low_has_no_level_state() -> None:
    t = _list_row("long", last=103.0, move="pre",
                  plan=today.plan_of(103.0, 100.0, 95.0, 106.0, 104.0),
                  levels={"pdh": 100.0, "pdl": 95.0, "pmh": 106.0, "pml": 104.0, "pdc": 99.0})
    assert today.scan_row(t, None, "pre", None)["lvl_state"] == 0


def test_the_evening_lean_needs_a_tenth_of_an_atr() -> None:
    def wide(sym: str, **kw: Any) -> dict[str, Any]:
        base: dict[str, Any] = {"sym": sym, "name": sym, "sector": "XLK", "cap": 5e10,
                                "close": 100.0, "chg": 0.1, "c1": 99.9, "high": 101.0,
                                "low": 99.0, "vol": 2e7, "avg": 2e7, "atr": 4.0, "ah_c": None,
                                "ah_chg": None, "ah_vol": None}
        base.update(kw)
        return base

    rows = [
        # 0.09 of an ATR after the close on a fifth of a day: on the list, no side.
        wide("THIN", ah_c=99.64, ah_chg=-0.36, ah_vol=4e6),
        # Half an ATR after the close: a side.
        wide("DOWN", ah_c=98.0, ah_chg=-2.0, ah_vol=4e6),
        wide("UP", ah_c=102.0, ah_chg=2.0, ah_vol=4e6),
    ]
    got = today.rank_evening(
        rows, ah_of=lambda r: {"last": r["ah_c"], "chg": r["ah_chg"], "vol": r["ah_vol"]},
        catalyst=lambda s: {"major": True, "title": "x"}, stage={}, reports={},
        session_day=date(2026, 11, 13), next_day=date(2026, 11, 16), favs=frozenset(),
        tracked=frozenset())
    lean = {r["sym"]: r["lean"] for r in got}
    assert lean == {"THIN": None, "DOWN": "short", "UP": "long"}
