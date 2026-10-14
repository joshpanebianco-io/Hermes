"""
The scanner's event log — what alerts are raised from and outcomes are kept in.

The tests that matter most are the restart ones: a collector that comes back up
at 11:00 replays the morning, and the log must neither duplicate what it already
had nor announce what it finds as though it just happened.
"""

from __future__ import annotations

from datetime import date, datetime
from typing import Any

from newsterminal import scan, scanlog
from newsterminal.scan import ET, Bar
from newsterminal.scanlog import EventLog, compute_outcome


def et(y: int, mo: int, d: int, h: int, mi: int) -> datetime:
    return datetime(y, mo, d, h, mi, tzinfo=ET)


def ts(y: int, mo: int, d: int, h: int, mi: int) -> int:
    return int(et(y, mo, d, h, mi).timestamp())


def row(sym: str = "AAPL", signals: list[dict[str, Any]] | None = None,
        progress: dict[str, float | None] | None = None, score: int = 55) -> dict[str, Any]:
    return {
        "sym": sym, "ok": True, "last": 101.0,
        "signals": signals or [],
        "progress": progress or {"pdh": None, "pdl": None, "pmh": None, "pml": None},
        "levels": {"pdh": 102.0, "pdl": 95.0, "pmh": 101.5, "pml": 99.0, "pm_done": True},
        "score": {"total": score},
    }


def l_signal(t: int, price: float = 100.0, stop: float = 99.0) -> dict[str, Any]:
    return {"kind": "L", "side": "long", "level": "PMH", "at_et": "10:00", "price": price,
            "note": "Retest of PMH 100.00 with the 8 EMA wave at the level", "t": t, "stop": stop}


def payload(rows: list[dict[str, Any]], session: str = "rth",
            day: str = "2026-10-13") -> dict[str, Any]:
    return {"session": session, "trading_day": day, "rows": rows}


# --- dedupe, ids and the live flag ---------------------------------------------------


def test_a_signal_is_logged_once_and_live_when_fresh(tmp_path: Any) -> None:
    log = EventLog(str(tmp_path / "ev.jsonl"))
    t = ts(2026, 10, 13, 10, 0)
    p = payload([row(signals=[l_signal(t)])])
    new = log.observe(p, {}, et(2026, 10, 13, 10, 12))
    assert [(e["id"], e["kind"], e["live"]) for e in new] == [(1, "L", True)]
    assert new[0]["note"].startswith("(L) long — retest of PMH")
    assert new[0]["score"] == 55
    assert log.observe(p, {}, et(2026, 10, 13, 10, 13)) == []  # the same replay, again


def test_a_restart_keeps_the_ids_and_backfills_without_announcing(tmp_path: Any) -> None:
    path = str(tmp_path / "ev.jsonl")
    morning = ts(2026, 10, 13, 10, 0)
    later = ts(2026, 10, 13, 10, 40)
    log = EventLog(path)
    log.observe(payload([row(signals=[l_signal(morning)])]), {}, et(2026, 10, 13, 10, 12))
    # The collector restarts at 11:30 and the replay finds both signals.
    again = EventLog(path)
    new = again.observe(payload([row(signals=[l_signal(morning), l_signal(later, 101, 100)])]),
                        {}, et(2026, 10, 13, 11, 30))
    assert [(e["id"], e["live"]) for e in new] == [(2, False)]  # 10:40's bar closed 40m ago
    # Its row's score at 11:30 is not the score it had at 10:50 — none is kept.
    assert new[0]["score"] is None
    assert again.since(0)["latest"] == 2
    # a page starting at the end
    assert again.since(10**15) == {"latest": 2, "events": [], "retracted": []}


def test_near_fires_once_per_level_per_day(tmp_path: Any) -> None:
    log = EventLog(str(tmp_path / "ev.jsonl"))
    near = row(progress={"pdh": 0.93, "pdl": 0.07, "pmh": None, "pml": None})
    a = log.observe(payload([near]), {}, et(2026, 10, 13, 10, 5))
    b = log.observe(payload([near]), {}, et(2026, 10, 13, 10, 25))  # a later bar, same day
    c = log.observe(payload([near], day="2026-10-14"), {}, et(2026, 10, 14, 10, 5))
    assert [(e["kind"], e["level"], e["side"]) for e in a] == [("NEAR", "PDH", "long")]
    assert b == []
    assert len(c) == 1
    # Not before the bell: the pre-market is a plan, not a break.
    assert log.observe(payload([row(sym="MSFT", progress={"pdh": 0.95})], session="pre"),
                       {}, et(2026, 10, 13, 9, 0)) == []


# --- outcomes ------------------------------------------------------------------------------


def bars5(start: datetime, rows: list[tuple[float, float, float]]) -> list[Bar]:
    """(high, low, close) per 5-minute bar from `start`."""
    t0 = int(start.timestamp())
    return [Bar(t0 + i * 300, c, h, lo, c, 1000.0) for i, (h, lo, c) in enumerate(rows)]


def ev(kind: str = "L", side: str = "long", price: float = 100.0, stop: float = 99.0,
       t: int | None = None) -> dict[str, Any]:
    return {"kind": kind, "side": side, "price": price, "stop": stop,
            "t": t if t is not None else ts(2026, 10, 13, 10, 0), "day": "2026-10-13"}


def test_one_r_before_the_stop_then_two_r() -> None:
    bars = bars5(et(2026, 10, 13, 10, 10), [(100.5, 99.6, 100.4), (101.2, 100.2, 101.0),
                                             (102.1, 100.9, 102.0)])
    o = compute_outcome(ev(), bars, ts(2026, 10, 13, 11, 0))
    assert (o["r"], o["hit_1r"], o["hit_2r"], o["stopped"]) == (1.0, True, True, False)
    assert o["mfe_r"] == 2.1 and o["mae_r"] == 0.4
    assert o["final"] is False


def test_the_same_bar_reaching_target_and_stop_counts_as_stopped() -> None:
    """Inside one bar the order is unknown — the record takes the conservative side."""
    bars = bars5(et(2026, 10, 13, 10, 10), [(101.3, 98.8, 100.0)])
    o = compute_outcome(ev(), bars, ts(2026, 10, 13, 11, 0))
    assert (o["hit_1r"], o["stopped"], o["hit_2r"]) == (False, True, False)


def test_the_l_enters_at_its_close_and_the_e_inside_its_bar() -> None:
    """The (L) bar's own range does not count; the (E) trigger bar's does."""
    t = ts(2026, 10, 13, 10, 0)
    signal_bar = bars5(et(2026, 10, 13, 10, 0), [(100.2, 98.5, 100.0), (100.1, 99.5, 100.0)])
    assert compute_outcome(ev("L", t=t), signal_bar, ts(2026, 10, 13, 11, 0))["stopped"] is None
    assert compute_outcome(ev("E", t=t), signal_bar, ts(2026, 10, 13, 11, 0))["stopped"] is True


def test_short_side_and_the_settled_close() -> None:
    bars = bars5(et(2026, 10, 13, 15, 50), [(100.2, 99.4, 99.5), (99.6, 99.2, 99.3)])
    e = ev("L", "short", price=100.0, stop=101.0, t=ts(2026, 10, 13, 15, 40))
    o = compute_outcome(e, bars, ts(2026, 10, 13, 16, 30))
    assert o["final"] is True and o["ret_close_r"] == 0.7
    assert (o["hit_1r"], o["stopped"]) == (False, False)  # settled with neither


def test_outcomes_update_as_bars_arrive(tmp_path: Any) -> None:
    log = EventLog(str(tmp_path / "ev.jsonl"))
    t = ts(2026, 10, 13, 10, 0)
    p = payload([row(signals=[l_signal(t)])])
    log.observe(p, {}, et(2026, 10, 13, 10, 12))
    bars = {"AAPL": bars5(et(2026, 10, 13, 10, 10), [(101.1, 99.9, 101.0)])}
    log.observe(p, bars, et(2026, 10, 13, 10, 20))
    assert log.events[0]["outcome"]["hit_1r"] is True
    # and the file holds it for the next process
    assert EventLog(str(tmp_path / "ev.jsonl")).events[0]["outcome"]["hit_1r"] is True


# --- stats ---------------------------------------------------------------------------------


def test_stats_group_by_kind_side_and_score() -> None:
    def settled(kind: str, side: str, score: int, win: bool, close_r: float) -> dict[str, Any]:
        return {"kind": kind, "side": side, "score": score, "day": "2026-10-12",
                "outcome": {"final": True, "r": 1.0, "hit_1r": win, "ret_close_r": close_r,
                            "mfe_r": 1.5 if win else 0.3, "mae_r": 0.4}}

    evs = [settled("L", "long", 70, True, 1.2), settled("L", "long", 45, False, -1.0),
           settled("E", "short", 30, True, 0.5),
           {"kind": "NEAR", "side": "long", "day": "2026-10-12", "outcome": None}]
    s = scanlog.stats(evs, 20, date(2026, 10, 13))
    g = {x["key"]: x for x in s["groups"]}
    assert s["total"] == 3
    assert (g["all"]["n"], g["all"]["win_1r"]) == (3, 0.667)
    assert (g["L long"]["n"], g["L long"]["avg_close_r"]) == (2, 0.1)
    assert g["E short"]["n"] == 1 and g["E long"]["n"] == 0 and g["E long"]["win_1r"] is None
    assert (g["score ≥ 60"]["n"], g["score 40–59"]["n"], g["score < 40"]["n"]) == (1, 1, 1)


# --- the chart -------------------------------------------------------------------------------


def test_the_chart_starts_at_the_previous_open_and_carries_today_s_vwap() -> None:
    mon = [Bar(ts(2026, 10, 12, 9, 30) + i * 300, 10, 11, 9, 10, 100.0) for i in range(6)]
    pre = [Bar(ts(2026, 10, 13, 4, 0) + i * 300, 10, 10.5, 9.5, 10, 0.0) for i in range(4)]
    tue = [Bar(ts(2026, 10, 13, 9, 30) + i * 300, 10, 12, 10, 11, 200.0) for i in range(4)]
    clock = scan.clock_at(et(2026, 10, 13, 10, 0))
    tech = scan.technicals(mon + pre + tue, [], clock)
    out = scan.chart_series(mon + pre + tue, clock, tech)
    assert out["ok"] is True
    assert out["bars"][0]["t"] == ts(2026, 10, 12, 9, 30)
    assert len(out["ema8"]) == len(out["bars"]) == len(out["vwap"])
    assert out["vwap"][0] is None and out["vwap"][-1] == 11.0  # (12+10+11)/3, RTH only
    assert [s["kind"] for s in out["sessions"]] == ["rth", "pre", "rth"]
    assert out["levels"]["pdh"] == 11


# --- the second look: retract, correct, settle (audit, 2026-10-14) ----------------------


def bo_signal(t: int, price: float = 101.5) -> dict[str, Any]:
    return {"kind": "BO", "side": "long", "level": "PMH", "at_et": "10:00", "price": price,
            "note": "Breakout above PMH", "t": t, "stop": None}


def test_a_signal_the_final_bars_do_not_have_is_retracted_not_deleted(tmp_path: Any) -> None:
    log = EventLog(str(tmp_path / "ev.jsonl"))
    t = ts(2026, 10, 13, 10, 0)
    bar_close = t + 600
    first = row(signals=[l_signal(t)])
    first["final_to"] = bar_close
    (ev,) = log.observe(payload([first]), {}, et(2026, 10, 13, 10, 10))
    # Re-read: the final bars hold no (L) at 10:00.
    gone = row(signals=[])
    gone["final_to"] = bar_close
    assert log.observe(payload([gone]), {}, et(2026, 10, 13, 10, 11)) == []
    assert log.events[0]["retracted"] is True and log.events[0]["id"] == ev["id"]
    assert log.since(0)["retracted"] == [ev["id"]]
    # Out of the record.
    log.events[0]["outcome"] = {"final": True, "r": 1.0, "hit_1r": True, "ret_close_r": 1.0}
    assert scanlog.stats(log.events, 20, date(2026, 10, 13))["total"] == 0
    # And back if a later download has it again.
    log.observe(payload([first]), {}, et(2026, 10, 13, 10, 12))
    assert "retracted" not in log.events[0] and log.since(0)["retracted"] == []


def test_a_bar_not_final_in_the_newest_copy_is_left_alone(tmp_path: Any) -> None:
    log = EventLog(str(tmp_path / "ev.jsonl"))
    t = ts(2026, 10, 13, 10, 0)
    first = row(signals=[l_signal(t)])
    first["final_to"] = t + 600
    log.observe(payload([first]), {}, et(2026, 10, 13, 10, 10))
    older = row(signals=[])
    older["final_to"] = t  # these bars end before the signal's bar does
    log.observe(payload([older]), {}, et(2026, 10, 13, 10, 11))
    assert "retracted" not in log.events[0]


def test_a_moved_price_is_corrected_and_the_first_figures_kept(tmp_path: Any) -> None:
    """IBM's PMH breakout was logged at 229.00; the final pre-market bars say 228.30."""
    log = EventLog(str(tmp_path / "ev.jsonl"))
    t = ts(2026, 10, 13, 9, 30)
    a = row(signals=[bo_signal(t, 229.0)])
    a["final_to"] = t + 600
    log.observe(payload([a]), {}, et(2026, 10, 13, 9, 40))
    b = row(signals=[bo_signal(t, 228.3)])
    b["final_to"] = t + 600
    assert log.observe(payload([b]), {}, et(2026, 10, 13, 9, 41)) == []  # same event, no alert
    e = log.events[0]
    assert (e["price"], e["revised"]["price"]) == (228.3, 229.0)
    assert len(log.events) == 1


def test_a_finished_day_settles_once_against_bars_read_after_its_bell(tmp_path: Any) -> None:
    log = EventLog(str(tmp_path / "ev.jsonl"))
    t1, t2 = ts(2026, 10, 13, 10, 0), ts(2026, 10, 13, 11, 0)
    log.observe(payload([row(signals=[l_signal(t1), l_signal(t2, 102, 101)])]), {},
                et(2026, 10, 13, 11, 10))
    assert log.unchecked("2026-10-13") == {}  # today: the live look, not the settle
    assert log.unchecked("2026-10-14") == {"2026-10-13": {"AAPL"}}
    close = ts(2026, 10, 13, 16, 0)
    # The final bars: 10:00's (L) is gone, 11:00's stands, and 14:00 has one never logged.
    t3 = ts(2026, 10, 13, 14, 0)
    n = log.settle("2026-10-13", {"AAPL": ([l_signal(t2, 102, 101), l_signal(t3, 103, 102)],
                                           close)}, et(2026, 10, 13, 20, 30))
    assert n == 3
    by_t = {e["t"]: e for e in log.events}
    assert by_t[t1]["retracted"] and not by_t[t2].get("retracted")
    assert by_t[t3]["live"] is False and by_t[t3]["score"] is None  # logged now, never alerted
    assert all(e["checked"] for e in log.events)
    assert log.unchecked("2026-10-14") == {}


def test_bars_that_stop_short_of_the_bell_do_not_settle_the_day(tmp_path: Any) -> None:
    log = EventLog(str(tmp_path / "ev.jsonl"))
    t = ts(2026, 10, 13, 10, 0)
    log.observe(payload([row(signals=[l_signal(t)])]), {}, et(2026, 10, 13, 10, 10))
    log.settle("2026-10-13", {"AAPL": ([l_signal(t)], ts(2026, 10, 13, 15, 30))},
               et(2026, 10, 13, 20, 30))
    assert not log.events[0].get("checked")


def test_a_backfill_logged_with_a_late_score_loses_it_on_load(tmp_path: Any) -> None:
    path = tmp_path / "ev.jsonl"
    path.write_text('{"id": 99, "day": "2026-10-13", "sym": "SPY", "kind": "L", "side": "long",'
                    ' "level": "PDL", "t": 1, "live": false, "score": 0}\n'
                    '{"id": 100, "day": "2026-10-13", "sym": "SPY", "kind": "L", "side": "long",'
                    ' "level": "PDL", "t": 2, "live": true, "score": 56}\n', encoding="utf-8")
    assert [e["score"] for e in EventLog(str(path)).events] == [None, 56]


# --- an outcome settles only on bars that reach the bell ---------------------------------


def test_an_outcome_does_not_settle_on_bars_read_before_the_close() -> None:
    e = ev("L", "short", price=100.0, stop=101.0, t=ts(2026, 10, 13, 15, 40))
    bars = bars5(et(2026, 10, 13, 15, 50), [(100.2, 99.4, 99.5), (99.6, 99.2, 99.3)])
    # The copy read at 15:58 holds 15:55's bar only in part — not read, not final.
    early = compute_outcome(e, bars, ts(2026, 10, 13, 16, 5), asof=ts(2026, 10, 13, 15, 58))
    assert early["final"] is False and early["ret_close_r"] is None
    # Read at 16:00:20: the 15:55 bar is whole, and the day settles on it.
    late = compute_outcome(e, bars, ts(2026, 10, 13, 16, 5), asof=ts(2026, 10, 13, 16, 0) + 20)
    assert late["final"] is True and late["ret_close_r"] == 0.7


def test_a_day_whose_last_bars_never_come_settles_an_hour_after_the_bell() -> None:
    e = ev("L", "short", price=100.0, stop=101.0, t=ts(2026, 10, 13, 15, 30))
    bars = bars5(et(2026, 10, 13, 15, 40), [(100.2, 99.4, 99.5)])  # halted after 15:45
    read = ts(2026, 10, 13, 16, 30)
    assert compute_outcome(e, bars, ts(2026, 10, 13, 16, 30), asof=read)["final"] is False
    o = compute_outcome(e, bars, ts(2026, 10, 13, 17, 1), asof=ts(2026, 10, 13, 17, 0))
    assert o["final"] is True and o["ret_close_r"] is None
