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


def test_the_report_leads_with_whether_the_list_picks_the_trades_that_run() -> None:
    # Owner, 2026-11-14: the list is for stocks more likely to trend. Two days of six
    # signals: on the first the top of the list runs and the bottom is stopped, on the
    # second the other way round. +1R says nothing between them; +2R and R held do.
    def day(d: str, top_runs: bool) -> list[dict[str, Any]]:
        run = dict(hit=True, two=True, close=3.0)
        out = dict(hit=True, two=False, close=-1.0, stopped=False)
        return [ev(d, 90 - i, **(run if (i < 2) == top_runs else out)) for i in range(6)]

    lines = fit.trend_lines(day("2026-11-16", True) + day("2026-11-17", True))
    assert lines[1].split() == ["+2R", "held", "+1R"]
    assert lines[2].split()[:5] == ["every", "signal", "33.3%", "+0.33", "100.0%"]
    assert lines[4].split()[:5] == ["top", "third", "100.0%", "+3.00", "100.0%"]
    assert lines[5].split()[:5] == ["bottom", "third", "0.0%", "-1.00", "100.0%"]
    assert "+2R +100.0 pts, ahead on 2 of 2 days" in lines[6]
    assert "held +4.00 R, ahead on 2 of 2" in lines[6]
    # A gap that holds on one half only is said to: here the second day runs backwards.
    mixed = fit.trend_lines(day("2026-11-16", True) + day("2026-11-17", False))
    assert "+2R  +0.0 pts, ahead on 1 of 2 days" in mixed[6]
    assert "first half" in mixed[7] and "+2R +100.0 pts" in mixed[7]
    assert "second half" in mixed[8] and "+2R -100.0 pts" in mixed[8]
    # It is the report's first table, and a thin day is a line, not a failure.
    text = fit.report(day("2026-11-16", True), 30)
    assert text.index("Trending, what the list is for") < text.index("By score band")
    assert "too few signals a day" in "\n".join(fit.trend_lines([ev("2026-11-16", 50)]))


def test_each_side_is_read_apart_so_the_longs_cannot_pass_for_the_list() -> None:
    # Owner, 2026-11-14: "when i say trending i mean both bullish and bearish trends".
    # Six longs whose top third runs and six shorts whose top third is stopped: together
    # the list looks fine at the top; apart, the shorts' rank is upside down.
    def one(d: str, score: int, side: str, runs: bool) -> dict[str, Any]:
        e = ev(d, score, hit=True, two=runs, close=3.0 if runs else -1.0)
        e["side"] = side
        return e

    evs: list[dict[str, Any]] = []
    for d in ("2026-11-16", "2026-11-17"):
        evs += [one(d, 95 - i, "long", i < 2) for i in range(6)]
        evs += [one(d, 80 - i, "short", i >= 4) for i in range(6)]
    lines = fit.side_lines(evs)
    longs = next(x for x in lines if x.strip().startswith("longs"))
    shorts = next(x for x in lines if x.strip().startswith("shorts"))
    assert "12 signals, 2 days" in longs and "thirds' gap +2R +100.0 pts (2 of 2 days)" in longs
    assert "held +4.00 R (2 of 2)" in longs
    assert "thirds' gap +2R -100.0 pts (0 of 2 days)" in shorts
    assert "held -4.00 R (0 of 2)" in shorts
    # It rides under the Trending table, and a side with nothing says so.
    assert any("By side" in x for x in fit.trend_lines(evs))
    only = fit.side_lines([one("2026-11-16", 50, "long", True)])
    assert "no day with 5 or more" in only[1] and only[2].strip() == "shorts  none"
    five = fit.side_lines([one("2026-11-16", 50 - i, "long", True) for i in range(5)])
    assert "too few a day to split" in five[1]


def test_a_thin_day_does_not_count_as_much_as_a_full_one() -> None:
    # 2026-11-18: 49 signals on 16 Nov, one on 17 Nov (the app stopped), and that one
    # weighed as much as the 49 in every equal-day line.
    full = [ev("2026-11-16", 90 - i, stopped=True, close=-1.0) for i in range(10)]
    lone = [ev("2026-11-17", 50, hit=True, two=True, close=3.0)]
    lines = fit.equal_day_lines(full + lone)
    assert "1 day with fewer than 5 signals left out" in lines[0]
    assert lines[2] == "  every signal    0.0%    0.0%  -1.00"
    assert "1 day with fewer than 5 signals left out" in fit.trend_lines(full + lone)[0]
    assert fit.full_days(fit.by_day(full + lone)) == (["2026-11-16"], 1)


def test_the_news_table_reads_what_is_logged_and_unscored() -> None:
    def e(day: str, hit: bool, news: dict[str, Any]) -> dict[str, Any]:
        x = ev(day, 60, hit=hit, two=hit, close=2.0 if hit else -1.0, stopped=not hit)
        x["ctx"] = {"news": {"pts": 0, "tier": None, "with": None, "src": None, "tag": None,
                             "prior": None, "size": None, **news}}
        return x

    evs: list[dict[str, Any]] = []
    for d in ("2026-11-16", "2026-11-17"):
        evs += [e(d, True, {"prior": {"tag": "Earnings", "tier": 1, "age_min": 1500.0}})
                for _ in range(3)]
        evs += [e(d, True, {"pts": 20, "tier": 1, "with": False, "src": "words", "size": "big"})
                for _ in range(3)]
        evs += [e(d, False, {}) for _ in range(4)]
    text = "\n".join(fit.news_lines(evs))
    by = {x.strip().rsplit("  ", 1)[0].split("  ")[0]: x for x in text.splitlines()}
    for label in ("reads against it", "day 2, no news", "day 2, any", "read as big", "any major"):
        assert label in by and "2/2" in by[label], label
    assert "no day with 3 or more on each side" in by["read as ordinary"]


def test_the_tapes_bias_is_read_on_the_trades_by_side_in_counts() -> None:
    def e(day: str, side: str, hit: bool, bias: str | None, vote: str | None,
          grade: str = "moderate") -> dict[str, Any]:
        x = {**ev(day, 60, hit=hit, stopped=not hit, close=1.5 if hit else -1.0), "side": side}
        x["ctx"] = {"tape": {"score": 30, "grade": grade, "bias": bias, "vote": vote}}
        return x

    evs = [e("2026-11-19", "long", True, "long", "long"),
           e("2026-11-19", "long", True, "long", None, grade="weak"),
           e("2026-11-19", "long", False, "short", "long"),
           e("2026-11-20", "long", False, None, None),
           e("2026-11-20", "short", True, "short", "long"),
           {**ev("2026-11-20", 60), "side": "short"}]          # logged before the bias: left out
    text = fit.bias_lines(evs)
    assert text[0].startswith("The tape's bias at the signal (5 signals on 2 days carry it")
    assert "under 10 days" in text[1]
    rows = {ln.strip().split("  ")[0]: ln for ln in text if ln.startswith("    ")}
    longs = text[text.index("  longs (4)") + 1:text.index("  shorts (1)")]
    got = {ln.strip().split("  ")[0]: ln for ln in longs}
    assert "+1R   2 of 2" in got["with the bias"] and "1 day" in got["with the bias"]
    assert "+1R   0 of 1" in got["against the bias"] and "stopped   1" in got["against the bias"]
    assert "+1R   0 of 1" in got["no lean"]
    assert "+1R   1 of 1" in got["with a moderate or strong"]    # the weak one is not in it
    assert "+1R   1 of 2" in got["with the vote count"]
    # The two rows that decide which read the Market points should come from.
    assert "+1R   1 of 1" in got["with the bias, not the vote"]
    assert "+1R   0 of 1" in got["with the vote, not the bias"]
    assert "with the bias" in rows
    assert fit.bias_lines([ev("2026-11-18", 60)]) == [
        "The tape's bias at the signal: no signal carries it yet (logged from 2026-11-19)"]


def test_each_chart_is_read_apart_and_the_record_stays_the_10m_charts() -> None:
    def e(day: str, tf: str | None, hit: bool, alert: bool | None = None) -> dict[str, Any]:
        x = ev(day, 60, hit=hit, stopped=not hit, close=1.5 if hit else -1.0)
        if tf:
            x["tf"] = tf
        if alert is not None:
            x["alert"] = alert
        return x

    evs = [e("2026-11-18", None, True),                       # before the charts: 10m
           e("2026-11-19", "3m", True), e("2026-11-19", "10m", False, alert=False),
           e("2026-11-19", "5m", False)]
    text = fit.tf_lines(evs)
    assert text[0].startswith("By chart, from 2026-11-19 (3 signals on 1 days")
    longs = text[text.index("  longs") + 1:text.index("  shorts")]
    got = {ln.strip().split("  ")[0]: ln for ln in longs}
    assert "+1R   1 of 1" in got["(L) 3m"] and "+1R   0 of 1" in got["(L) 10m"]
    assert "+1R   1 of 2" in got["first to print a setup"]
    assert "+1R   0 of 1" in got["printed it after"]
    assert fit.tf_lines([e("2026-11-18", None, True)]) == [
        "By chart: no 3m or 5m signal settled yet (logged from 2026-11-19)"]
    # Every other table reads the 10m chart alone.
    assert "on the 10m chart over 5 days: 2" in fit.report(evs, 5).splitlines()[0]


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


def test_the_parts_are_read_again_on_the_valid_entries_alone() -> None:
    # 2026-11-14: the entry part is a gate, so a part is judged among the signals that
    # passed it. A graded part above zero (the old weights) passes as the full one does.
    def parts(loc: int, cat: int) -> dict[str, Any]:
        return {"location": {"pts": loc, "max": 25}, "catalyst": {"pts": cat, "max": 20}}

    evs: list[dict[str, Any]] = []
    for day in ("2026-11-16", "2026-11-17"):
        evs += [ev(day, 80, hit=True, close=2.0, parts=parts(25, 20)) for _ in range(3)]
        evs += [ev(day, 60, hit=i < 2, stopped=i == 2, close=-1.0 if i == 2 else 1.0,
                   parts=parts(7, 0)) for i in range(3)]
        # News on the wrong side of VWAP: it drags the catalyst down on the whole record.
        evs += [ev(day, 40, stopped=True, close=-1.0, parts=parts(0, 20)) for _ in range(4)]
    assert fit.at_entry(evs[0]) and fit.at_entry(evs[3]) and not fit.at_entry(evs[6])
    assert fit.at_entry(ev("d", 50))
    lines = fit.entry_lines(evs)
    assert lines[2].split()[:4] == ["valid", "entry", "12", "83.3%"]
    assert lines[3].split()[:4] == ["no", "entry", "8", "0.0%"]
    cat = next(x for x in lines if x.strip().startswith("catalyst"))
    assert cat.split()[1] == "2/2"
    whole = next(x for x in fit.same_day_lines(evs) if x.strip().startswith("catalyst"))
    assert whole.split()[1] == "0/2"
    assert "Only signals at a valid entry" in fit.report(evs, 30)


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


def test_a_mark_run_late_is_left_out_of_the_pool_table() -> None:
    # 2026-11-17: the "10:00" mark ran at 18:30 ET on the whole day's figures.
    rows = [{"sym": "AAA", "promoted": True}]
    outcome = {"AAA": {"close": 110.0, "change": 10.0, "high": 112.0, "low": 99.0, "atr": 4.0}}
    on_time = {"kind": "mark", "day": "2026-11-17", "mark": "09:25", "at_et": "09:25",
               "rows": rows}
    late = {"kind": "mark", "day": "2026-11-17", "mark": "10:00", "at_et": "18:30", "rows": rows}
    assert fit._late(late) and not fit._late(on_time)
    assert not fit._late({"mark": "10:00", "at_et": "10:20"})
    assert not fit._late({"mark": "10:00"})   # an older line without the time it ran
    text = "\n".join(fit.pool_lines([on_time, late,
                                     {"kind": "outcome", "day": "2026-11-17", "rows": outcome}]))
    assert "1 marks over 1 days, 1 run late left out" in text
