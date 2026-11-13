"""tools/fit_score.py: the audit's tests stay runnable as the record grows."""

from __future__ import annotations

import importlib.util
from pathlib import Path
from typing import Any

_spec = importlib.util.spec_from_file_location(
    "fit_score", Path(__file__).resolve().parent.parent / "tools" / "fit_score.py")
assert _spec is not None and _spec.loader is not None
fit = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(fit)


def ev(day: str, score: int, hit: bool = False, stopped: bool = False, close: float | None = 0.0,
       sym: str = "X", parts: dict[str, Any] | None = None, two: bool = False) -> dict[str, Any]:
    return {"kind": "L", "side": "long", "day": day, "sym": sym, "score": score,
            "parts": parts or {},
            "outcome": {"final": True, "r": 1.0, "hit_1r": hit, "hit_2r": two, "stopped": stopped,
                        "ret_close_r": close}}


def test_the_two_measures_keep_the_stop() -> None:
    assert fit.at_1r(ev("d", 50, hit=True, close=9.0)) == 1.0
    assert fit.at_1r(ev("d", 50, stopped=True, close=9.0)) == -1.0
    assert fit.at_1r(ev("d", 50, close=0.4)) == 0.4
    assert fit.at_1r(ev("d", 50, close=None)) == 0.0
    assert fit.held(ev("d", 50, stopped=True, close=9.0)) == -1.0
    assert fit.held(ev("d", 50, hit=True, close=9.0)) == 5.0
    assert fit.held(ev("d", 50, close=None)) == 0.0


def test_thirds_are_taken_within_each_day_and_a_thin_day_is_left_out() -> None:
    day = [ev("2026-11-02", s) for s in (90, 80, 70, 60, 50, 40)]
    thin = [ev("2026-11-03", s) for s in (99, 1)]
    top, bottom = fit.thirds(day + thin, lambda e: e["score"])
    assert [e["score"] for e in top] == [90, 80]
    assert [e["score"] for e in bottom] == [50, 40]


def test_the_record_splits_at_its_middle_day() -> None:
    evs = [ev(d, 50) for d in ("2026-11-02", "2026-11-03", "2026-11-04", "2026-11-05")]
    early, late = fit.halves(evs)
    assert [e["day"] for e in early] == ["2026-11-02", "2026-11-03"]
    assert [e["day"] for e in late] == ["2026-11-04", "2026-11-05"]
    assert fit.halves([]) == ([], [])


def test_every_day_counts_the_same_however_busy_it_was() -> None:
    busy = [ev("2026-11-02", 90 - i, hit=True, two=True, close=2.0) for i in range(30)]
    quiet = [ev("2026-11-03", 90 - i, stopped=True, close=-1.0) for i in range(6)]
    lines = fit.equal_day_lines(busy + quiet)
    # Pooled this would read 83%; two days, one all winners and one all losers, read 50%.
    assert lines[2] == "  every signal   50.0%   50.0%  +0.50"
    assert lines[3] == "  top 5 a day    50.0%   50.0%  +0.50"
    assert lines[4] == "  top third      50.0%   50.0%  +0.50"


def test_inside_the_day_a_busy_day_cannot_pass_for_a_good_input() -> None:
    hi = {"rs": {"pts": 20, "max": 25}, "fuel": {"pts": -10, "max": 0}}
    lo = {"rs": {"pts": 0, "max": 25}}
    evs = ([ev("2026-11-02", 70, hit=True, two=True, close=2.0, parts=hi) for _ in range(20)]
           + [ev("2026-11-02", 40, stopped=True, close=-1.0, parts=lo) for _ in range(20)])
    for day in ("2026-11-03", "2026-11-04"):
        evs += [ev(day, 70, stopped=True, close=-1.0, parts=hi) for _ in range(3)]
        evs += [ev(day, 40, hit=True, two=True, close=2.0, parts=lo) for _ in range(3)]
    evs += [ev("2026-11-05", 70, parts=hi)]
    lines = fit.same_day_lines(evs)
    rs = next(x for x in lines if x.strip().startswith("rs"))
    # Pooled the strong side wins 20 of 27; inside the day it is ahead on 1 day of 3.
    assert rs.split()[1:4] == ["1/3", "1/3", "1/3"]
    assert not any(x.strip().startswith("fuel") for x in lines)
    only = [ev("2026-11-02", 70, parts=hi)]
    assert "no day with 3 or more on each side" in fit.same_day_lines(only)[2]


def test_the_report_reads_the_rank_the_penalties_and_the_morning_list() -> None:
    clock = {"clock": {"pts": -10, "max": 0}, "structure": {"pts": 30, "max": 30}}
    evs = [ev("2026-11-05", 90 - i, hit=i < 3, sym=f"S{i}", parts=clock if i < 2 else None)
           for i in range(6)]
    morning = [{"day": "2026-11-05", "rows": [{"sym": f"S{i}"} for i in range(6)]}]
    text = fit.report(evs, 30, morning)
    assert "under the 300-signal guard" in text
    assert "all       2 / 2     100.0% /   0.0%   gap at +1R +1.00 R   gap held +0.00 R" in text
    assert "Pre-open rank (1 mornings on file)" in text
    assert "clock       fired on 2, too few to read" in text
    # No morning on file is a line, not a failure.
    assert "no morning on file yet" in fit.report(evs, 30, None)


# ---- the quant audit's phase 3 (2026-11-13) ------------------------------------------


def test_the_news_and_the_gate_are_read_inside_each_day() -> None:
    def with_news(day: str, hit: bool, w: bool | None, src: str | None,
                  gated: bool = False) -> dict[str, Any]:
        e = ev(day, 60, hit=hit)
        e["ctx"] = {"raw": 104, "gated": gated,
                    "news": {"with": w, "src": src, "tier": 1, "set_aside": 0}}
        return e

    evs = [with_news(d, True, True, "move") for d in ("2026-11-16", "2026-11-17") for _ in range(3)]
    evs += [with_news(d, False, None, None) for d in ("2026-11-16", "2026-11-17") for _ in range(3)]
    text = "\n".join(fit.news_lines(evs))
    assert "with the side" in text and "2/2" in text
    # The rank tests read the uncapped sum where the log has it.
    assert fit.rank_score(evs[0]) == 104.0
    assert "no signal carries" in fit.news_lines([ev("d", 50)])[0]


def test_the_pools_record_reads_each_mark_against_its_days_outcome() -> None:
    rows = [{"sym": f"S{i}", "promoted": i < 3} for i in range(12)]
    outcome = {f"S{i}": {"close": 110.0, "change": 10.0 if i < 10 else 1.0, "high": 112.0,
                         "low": 100.0, "atr": 4.0} for i in range(12)}
    text = "\n".join(fit.pool_lines([
        {"kind": "mark", "day": "2026-11-16", "mark": "09:25", "rows": rows},
        {"kind": "outcome", "day": "2026-11-16", "rows": outcome}]))
    assert "top 10" in text and "11-50" in text and "promoted" in text
    assert "no mark" in fit.pool_lines([{"kind": "mark", "day": "d", "rows": rows}])[0]
