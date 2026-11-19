"""
The live rotation (rotation.py): when it runs, what may leave the list, and what it takes to
come in. The owner's case of 2026-11-19 is the worked example: CRWV scored 50 off the list
while ASTS (7) sat on it.
"""

from __future__ import annotations

from datetime import datetime
from typing import Any

import pytest

from newsterminal import rotation as rot
from newsterminal.scan import ET
from newsterminal.scanlog import EventLog
from newsterminal.sources import pool as pool_src
from newsterminal.sources import universe as u


def et(y: int, mo: int, d: int, h: int, mi: int) -> datetime:
    return datetime(y, mo, d, h, mi, tzinfo=ET)


@pytest.mark.parametrize(
    ("at", "on"),
    [
        (et(2026, 11, 19, 9, 34), False),   # the first five-minute bar has not printed
        (et(2026, 11, 19, 9, 35), True),
        (et(2026, 11, 19, 12, 0), True),
        (et(2026, 11, 19, 15, 44), True),
        (et(2026, 11, 19, 15, 45), False),  # a quarter hour before the close
        (et(2026, 11, 19, 8, 0), False),    # the pre-market is the marks' work
        (et(2026, 11, 21, 11, 0), False),   # a Saturday
        (et(2026, 11, 27, 12, 44), True),   # the half day after Thanksgiving, closing 13:00
        (et(2026, 11, 27, 12, 45), False),
    ],
)
def test_the_window(at: datetime, on: bool) -> None:
    assert rot.in_window(at) is on


def pick(sym: str, score: float | None, locked: bool = False) -> dict[str, Any]:
    return {"sym": sym, "score": score, "locked": locked}


def test_the_owners_case_takes_the_weakest_pick_on_the_second_round() -> None:
    picks = [pick("ASTS", 7), pick("TTWO", 22), pick("WMT", 44)]
    cands = [{"sym": "CRWV", "score": 50.0}, {"sym": "MRVL", "score": 30.0}]
    # First round: CRWV qualifies but has not held it yet.
    moves, streak = rot.decide(cands, picks, 0, {})
    assert moves == [] and streak == {"CRWV": 1}
    # Second round in a row: it moves, over ASTS. MRVL is under the floor throughout.
    moves, streak = rot.decide(cands, picks, 0, streak)
    assert moves == [{"in": "CRWV", "in_score": 50.0, "out": "ASTS", "out_score": 7}]
    assert streak == {"CRWV": 2}


def test_a_round_that_misses_resets_the_streak() -> None:
    picks = [pick("ASTS", 45)]
    _, streak = rot.decide([{"sym": "CRWV", "score": 56.0}], picks, 0, {})
    assert streak == {"CRWV": 1}
    # Next round CRWV is 52: under 45 + 10, so the streak is gone, not kept at 1.
    _, streak = rot.decide([{"sym": "CRWV", "score": 52.0}], picks, 0, streak)
    assert streak == {}
    moves, _ = rot.decide([{"sym": "CRWV", "score": 56.0}], picks, 0, streak)
    assert moves == []


def test_a_locked_pick_is_never_the_one_out() -> None:
    picks = [pick("ASTS", 7, locked=True), pick("TTWO", 22)]
    moves, _ = rot.decide([{"sym": "CRWV", "score": 50.0}], picks, 0, {"CRWV": 1})
    assert [(m["in"], m["out"]) for m in moves] == [("CRWV", "TTWO")]
    # Every pick locked: nothing can come in.
    moves, streak = rot.decide([{"sym": "CRWV", "score": 90.0}], [pick("ASTS", 7, True)], 0,
                               {"CRWV": 5})
    assert moves == [] and streak == {}


def test_a_free_slot_takes_a_candidate_over_the_floor_and_moves_are_capped() -> None:
    cands = [{"sym": s, "score": sc} for s, sc in (("A", 70.0), ("B", 65.0), ("C", 60.0),
                                                   ("D", 39.0))]
    streak = {"A": 1, "B": 1, "C": 1, "D": 1}
    moves, nxt = rot.decide(cands, [], 4, streak)
    # Best first, MAX_MOVES a round; D is under the floor and drops out of the streaks.
    assert [(m["in"], m["out"]) for m in moves] == [("A", None), ("B", None)]
    assert nxt == {"A": 2, "B": 2, "C": 2}


def test_each_move_takes_the_next_weakest() -> None:
    picks = [pick("P1", 20), pick("P2", 5), pick("P3", None), pick("P4", 60)]
    cands = [{"sym": "X", "score": 58.0}, {"sym": "Y", "score": 41.0}]
    moves, _ = rot.decide(cands, picks, 0, {"X": 1, "Y": 1})
    # A pick with no score counts as 0: P3 goes first, then P2 (5).
    assert [(m["in"], m["out"]) for m in moves] == [("X", "P3"), ("Y", "P2")]


def test_held_locks_the_young_and_the_signalled_and_skips_the_hand_tracked() -> None:
    now = 1_000_000.0
    promoted = [
        {"symbol": "OLD", "mark": "09:25"},
        {"symbol": "NEW", "mark": "live", "since": now - 120},
        {"symbol": "AGED", "mark": "live", "since": now - 900},
        {"symbol": "SIG", "mark": "09:00"},
        {"symbol": "GONE", "mark": "09:25"},          # not on the list: room ran out
        {"symbol": "HAND", "mark": "hand"},
        {"symbol": "UNREAD", "mark": "09:25"},        # no score yet: not a score of 0
    ]
    got = rot.held(promoted, ["OLD", "NEW", "AGED", "SIG", "HAND", "UNREAD"],
                   {"OLD": 12, "NEW": 50, "AGED": 31, "SIG": 9}, {"SIG"}, now)
    assert [(p["sym"], p["score"], p["locked"]) for p in got] == [
        ("OLD", 12.0, False), ("NEW", 50.0, True), ("AGED", 31.0, False), ("SIG", 9.0, True),
        ("UNREAD", None, True)]


def test_no_round_on_a_half_built_list() -> None:
    listed = ["A", "B", "C", "D", "E"]
    assert rot.scores_ready(listed, {"A": 1, "B": 0, "C": 50, "D": 9, "E": 3})
    assert rot.scores_ready(listed, {"A": 1, "B": 0}, slack=3)
    assert not rot.scores_ready(listed, {"A": 1, "B": None}, slack=3)


def test_a_rotated_name_the_pool_would_not_trade_goes_first() -> None:
    now = 1_000_000.0
    promoted = [
        {"symbol": "UGI", "mark": "live", "since": now - 60},     # thin, young, signalled
        {"symbol": "OPENED", "mark": "live", "since": now - 900},  # thin, but the owner's
        {"symbol": "TTWO", "mark": "06:00"},                        # a pre-market pick
        {"symbol": "BMY", "mark": "live", "since": now - 900},     # tradable
    ]
    got = rot.held(promoted, ["UGI", "OPENED", "TTWO", "BMY"],
                   {"UGI": 74, "OPENED": 50, "TTWO": 22, "BMY": 80}, {"UGI"}, now,
                   tradable={"BMY", "TTWO"}, mine={"OPENED"})
    assert [(p["sym"], p["score"], p["locked"]) for p in got] == [
        ("UGI", 0.0, False), ("OPENED", 50.0, False), ("TTWO", 22.0, False),
        ("BMY", 80.0, False)]
    # With no pool read to go by, nothing is judged untradable.
    assert rot.held(promoted[:1], ["UGI"], {"UGI": 74}, set(), now)[0]["score"] == 74.0


def test_reads_go_to_the_unread_then_the_stalest_within_the_budget() -> None:
    now = 10_000.0
    fetched = {"A": now - 30, "B": now - 400, "C": now - 200}
    assert rot.reads_due(["A", "B", "C", "D", "E"], fetched, now) == ["D", "E", "B"]
    assert rot.reads_due(["A"], fetched, now) == []


def test_the_pool_swaps_in_place_and_keeps_its_own_score_scale() -> None:
    p = pool_src.PoolStore(path="nul")
    p.enabled = True
    p.promoted = [{"symbol": "TTWO", "mark": "09:25", "score": 9.0},
                  {"symbol": "ASTS", "mark": "09:25", "score": 8.0},
                  {"symbol": "WMT", "mark": "09:00", "score": 7.5}]
    p.by_sym = {"CRWV": {"symbol": "CRWV", "score": 6.5}}
    moves = [{"in": "CRWV", "in_score": 50.0, "out": "ASTS", "out_score": 7.0},
             {"in": "MRVL", "in_score": 61.0, "out": None, "out_score": None}]
    names = {"CRWV": {"name": "CoreWeave", "sector": "XLK"}}
    assert p.rotate(moves, names, "10:42", 123.0)
    assert [x["symbol"] for x in p.promoted] == ["TTWO", "CRWV", "WMT", "MRVL"]
    crwv = p.promoted[1]
    assert crwv["mark"] == "live" and crwv["since"] == 123.0 and crwv["score"] == 6.5
    assert crwv["setup_score"] == 50.0 and crwv["name"] == "CoreWeave"
    assert crwv["reason"] == "rotated in at 10:42: setup 50 over ASTS 7"
    assert p.promoted[3]["reason"] == "rotated in at 10:42: setup 61 into a free slot"
    # A name already picked is not taken twice, and promotion off moves nothing.
    assert not p.rotate([{"in": "CRWV", "in_score": 50.0, "out": "TTWO", "out_score": 9.0}],
                        names, "10:43", 124.0)
    p.enabled = False
    assert not p.rotate(moves, names, "10:44", 125.0)


def test_an_open_trade_or_a_fresh_breakout_holds_a_name(tmp_path: Any) -> None:
    log = EventLog(path=str(tmp_path / "events.json"))
    t0 = 1_800_000_000
    base = {"day": "2026-11-19", "kind": "L", "tf": "5m", "side": "long", "live": True}
    log.events = [
        # A retest 15 minutes ago, its stop not hit (None: not measured yet, False: held).
        {**base, "sym": "OPEN", "t": t0 - 900, "outcome": {"stopped": False}},
        {**base, "sym": "JUST", "t": t0 - 300, "outcome": {"stopped": None}},
        # Stopped out: the trade is over.
        {**base, "sym": "STOPPED", "t": t0 - 900, "outcome": {"stopped": True}},
        # Older than TRADE_HOLD_SEC.
        {**base, "sym": "OLD", "t": t0 - 4000, "outcome": {"stopped": False}},
        # A breakout ten minutes ago holds; one from 09:40 that went nowhere does not (TTWO).
        {**base, "sym": "BROKE", "kind": "BO", "t": t0 - 600, "outcome": None},
        {**base, "sym": "TTWO", "kind": "BO", "t": t0 - 1700, "outcome": None},
        # Replayed when the name joined, withdrawn, a near-miss, or yesterday's: never.
        {**base, "sym": "REPLAY", "t": t0 - 600, "live": False},
        {**base, "sym": "GONE", "t": t0 - 600, "retracted": True},
        {**base, "sym": "NEARONLY", "t": t0 - 600, "kind": "NEAR"},
        {**base, "sym": "YDAY", "t": t0 - 600, "day": "2026-11-18"},
    ]
    got = log.holding("2026-11-19", t0, trade_sec=rot.TRADE_HOLD_SEC,
                      break_sec=rot.BREAK_HOLD_SEC)
    assert got == {"OPEN", "JUST", "BROKE"}


def urow(sym: str, **kw: Any) -> dict[str, Any]:
    base: dict[str, Any] = {
        "sym": sym, "name": f"{sym} Inc", "exch": "NASDAQ", "close": 100.0, "chg": 1.0,
        "open": 99.0, "high": 101.0, "low": 98.0, "vol": 3e6, "gap": 0.5, "atr": 2.0,
        "pm_h": 99.5, "pm_l": 98.5, "pm_c": 99.2, "pm_chg": 0.4, "pm_vol": 2e5,
        "ah_c": 100.4, "ah_chg": 0.4, "ah_vol": 1e5, "avg": 1e6, "rv5": 2.5, "cap": 5e9,
        "float": 1e8, "sector": "XLK", "industry": "Semiconductors",
        "o1": 95.0, "h1": 97.0, "l1": 94.0, "c1": 96.0, "v1": 1e6,
        "h2": 96.0, "l2": 93.0, "c2": 95.0, "v2": 1e6,
    }
    base.update(kw)
    return base


def test_the_finder_ranks_outside_days_then_the_previous_days_level_then_volume() -> None:
    s = u.UniverseStore(path="nul")
    s.pm_ref, s.ah_ref = {}, {}
    rows = [
        # Above PDH 97 and PMH 99.5: an outside day.
        urow("BOTH", close=102.0, rv5=1.5),
        urow("BOTH2", close=103.0, rv5=3.0),
        # Above PDH 97, inside the pre-market range: the previous day's level alone.
        urow("PD", close=98.0, pm_h=99.5, pm_l=97.5, rv5=6.0),
        # Inside PDH/PDL, above PMH: the pre-market range alone.
        urow("PM", close=96.5, pm_h=96.0, pm_l=95.0, h1=97.0, rv5=4.0),
        # Inside both: not a candidate.
        urow("IN", close=96.5, pm_h=99.5, pm_l=95.0, rv5=9.0),
        urow("QUIET", close=102.0, rv5=0.8),                # under 1x RVOL
        urow("THIN", close=102.0, vol=1e5),                 # under the volume floor
        urow("SMALL", close=102.0, cap=1e9),                # under $2bn
        urow("LISTED", close=102.0),                        # already on the list
        urow("GOOG", name="Alphabet Inc. Class C", close=102.0),  # GOOGL's twin
    ]
    s.rows, s.by_sym, s.read_at = rows, {r["sym"]: r for r in rows}, 1_794_000_000.0
    got = s.rotation_finder(lambda _s: None, skip={"LISTED"}, limit=10,
                            skip_companies={pool_src.company_key("Alphabet Inc. Class A")},
                            now=et(2026, 11, 19, 11, 0))
    assert [e["sym"] for e in got] == ["BOTH2", "BOTH", "PD", "PM"]
    assert [e["sym"] for e in s.rotation_finder(lambda _s: None, skip={"LISTED", "GOOG"},
                                                limit=2, now=et(2026, 11, 19, 11, 0))
            ] == ["BOTH2", "BOTH"]
    # Only the names the pool counts as tradable, when the collector says which.
    assert [e["sym"] for e in s.rotation_finder(lambda _s: None, skip=(), limit=10,
                                                only={"PD", "PM", "IN"},
                                                now=et(2026, 11, 19, 11, 0))] == ["PD", "PM"]
    # Outside the session there is nothing to find.
    assert s.rotation_finder(lambda _s: None, skip=(), limit=5, now=et(2026, 11, 19, 18, 0)) == []
