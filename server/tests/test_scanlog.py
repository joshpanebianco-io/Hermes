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
    assert again.since(0)["latest"] == 2
    assert again.since(10**15) == {"latest": 2, "events": []}  # a page starting at the end


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
