"""The live rotation's record (rotation.log_line, outcome_line, judge) and its reader,
tools/rotation_record.py: did the name that came in go further its way than the one that left?"""

from __future__ import annotations

import importlib.util
from datetime import datetime
from pathlib import Path
from typing import Any

from newsterminal import rotation as rot
from newsterminal.scan import ET

_spec = importlib.util.spec_from_file_location(
    "rotation_record", Path(__file__).resolve().parent.parent / "tools" / "rotation_record.py")
assert _spec is not None and _spec.loader is not None
rr = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(rr)

DAY = "2026-11-20"
AT = datetime(2026, 11, 20, 10, 8, 56, tzinfo=ET)


def move(i: str, i_side: str, i_last: float, o: str | None, o_side: str | None,
         o_last: float | None, at: datetime = AT) -> dict[str, Any]:
    m = {"in": i, "in_score": 79.0, "out": o, "out_score": 2.0 if o else None}
    sides = {i: {"side": i_side, "last": i_last}}
    if o:
        sides[o] = {"side": o_side, "last": o_last}
    return rot.log_line(DAY, at, m, [{"sym": i, "score": 79.0}], sides)


def test_a_move_carries_each_names_side_and_price() -> None:
    e = move("VVV", "long", 50.0, "ASTS", "short", 20.0)
    assert e["kind"] == "move" and e["at_et"] == "10:08:56"
    assert (e["in_side"], e["in_last"], e["out_side"], e["out_last"]) == ("long", 50.0,
                                                                          "short", 20.0)
    free = move("P", "long", 30.0, None, None, None)
    assert free["out"] is None and free["out_side"] is None


def test_the_days_names_and_its_outcome_line() -> None:
    lines = [move("VVV", "long", 50.0, "ASTS", "short", 20.0),
             move("UGI", "long", 40.0, "WMT", "short", 100.0),
             {**move("X", "long", 1.0, None, None, None), "day": "2026-11-19"}]
    names, done = rot.day_names(lines, DAY)
    assert names == {"VVV", "ASTS", "UGI", "WMT"} and not done
    raw = {"VVV": {"close": 52.0, "high": 53.0, "low": 49.0, "atr": 2.0},
           "ASTS": {"close": 19.0, "atr": 1.0}, "UGI": {"close": None}}
    line = rot.outcome_line(DAY, names, raw.get)
    assert line == {"kind": "outcome", "day": DAY, "rows": {
        "ASTS": {"close": 19.0, "high": None, "low": None, "atr": 1.0},
        "VVV": {"close": 52.0, "high": 53.0, "low": 49.0, "atr": 2.0}}}
    assert rot.day_names([*lines, line], DAY)[1]
    assert rot.outcome_line(DAY, {"UGI"}, raw.get) is None


def test_a_run_is_each_names_own_way_in_daily_atrs() -> None:
    assert rot.run_its_way("long", 50.0, 52.0, 2.0) == 1.0
    assert rot.run_its_way("short", 20.0, 19.0, 1.0) == 1.0     # a short that fell ran its way
    assert rot.run_its_way("short", 20.0, 21.0, 1.0) == -1.0
    assert rot.run_its_way(None, 20.0, 21.0, 1.0) is None
    assert rot.run_its_way("long", None, 21.0, 1.0) is None
    assert rot.run_its_way("long", 20.0, 21.0, 0.0) is None


def test_judge_waits_for_the_close_and_the_reader_counts_by_side() -> None:
    lines = [
        move("VVV", "long", 50.0, "ASTS", "short", 20.0),     # in +1.0, out +1.0: not further
        move("UGI", "long", 40.0, "WMT", "short", 100.0),     # in +0.5, out -1.0: further
        move("NTSK", "short", 30.0, "TTWO", "long", 200.0),   # in +2.0, out -0.5: further
        move("P", "long", 30.0, None, None, None,             # a free slot: in -1.0
             at=datetime(2026, 11, 20, 11, 2, tzinfo=ET)),
        {"day": DAY, "at_et": "10:07:00", "in": "OLD", "in_score": 60.0, "out": "Q",
         "out_score": 5.0, "cands": []},                      # the first morning's shape
        {**move("LATE", "long", 1.0, "Z", "long", 1.0), "day": "2026-11-21"},
    ]
    assert rot.judge(lines) == []                              # no close on file yet
    lines.append({"kind": "outcome", "day": DAY, "rows": {
        "VVV": {"close": 52.0, "atr": 2.0}, "ASTS": {"close": 19.0, "atr": 1.0},
        "UGI": {"close": 41.0, "atr": 2.0}, "WMT": {"close": 102.0, "atr": 2.0},
        "NTSK": {"close": 26.0, "atr": 2.0}, "TTWO": {"close": 199.0, "atr": 2.0},
        "P": {"close": 29.0, "atr": 1.0}, "OLD": {"close": 1.0, "atr": 1.0}}})
    judged = rot.judge(lines)
    assert [(j["in"], j["in_run"], j["out_run"], j["free"]) for j in judged] == [
        ("VVV", 1.0, 1.0, False), ("UGI", 0.5, -1.0, False), ("NTSK", 2.0, -0.5, False),
        ("P", -1.0, None, True), ("OLD", None, None, False)]
    t = rr.tally(judged)
    assert (t["long"]["of"], t["long"]["in_way"], t["long"]["out_way"], t["long"]["further"]) \
        == (2, 2, 1, 1)
    assert (t["short"]["of"], t["short"]["in_way"], t["short"]["out_way"],
            t["short"]["further"]) == (1, 1, 0, 1)
    assert rr.free_tally(judged) == {"long": [0, 1], "short": [0, 0]}
    text = rr.report(lines)
    assert "Rotation record: 6 moves over 2 day(s), 2026-11-20 to 2026-11-21" in text
    assert "1 move(s) wait for their day's close" in text
    assert "1 move(s) have no side or price on file for a name, not judged" in text
    assert "%" not in text
    assert rr.report(lines, since="2026-11-21").startswith("Rotation record: 1 moves")
