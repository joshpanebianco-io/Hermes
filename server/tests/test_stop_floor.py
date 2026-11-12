"""
The stop's floor (owner, 2026-11-11): a stop's distance is never counted as less
than the script's own retest buffer, a quarter of the ten-minute ATR at the
signal's bar.

The first case borrows a real entry and stop: GME's (L) short at 15:20 ET on Tue
10 Nov 2026 sold 25.20 with the script's stop idea at 25.22, 1R of two and a half
cents on a $25 stock. THE FLOOR AND THE BARS AFTER IT ARE MADE UP to show the rule.
GME's real ten-minute ATR at that bar was 9.2c, so its real floor (2.31c) sat under
its stop and the record leaves that signal as it was; the real signals the floor
moves are in the note beside scan.risk_of (GOOGL, 6 Nov 11:40: a two-cent stop on a
$287 stock).
"""

from __future__ import annotations

import json
from datetime import date, datetime
from typing import Any

import pytest

from newsterminal import optcalc, scan, scanlog
from newsterminal.scan import ET, Bar
from newsterminal.scanlog import EventLog, compute_outcome


def et(y: int, mo: int, d: int, h: int, mi: int) -> datetime:
    return datetime(y, mo, d, h, mi, tzinfo=ET)


def ts(y: int, mo: int, d: int, h: int, mi: int) -> int:
    return int(et(y, mo, d, h, mi).timestamp())


def bars5(start: datetime, rows: list[tuple[float, float, float]]) -> list[Bar]:
    """(high, low, close) per 5-minute bar from `start`."""
    t0 = int(start.timestamp())
    return [Bar(t0 + i * 300, c, h, lo, c, 1000.0) for i, (h, lo, c) in enumerate(rows)]


def gme(risk_min: float | None = None) -> dict[str, Any]:
    e: dict[str, Any] = {"kind": "L", "side": "short", "price": 25.20, "stop": 25.2247,
                         "t": ts(2026, 11, 10, 15, 20), "day": "2026-11-10"}
    if risk_min is not None:
        e["risk_min"] = risk_min
    return e


#: After the 15:20 bar: a 4c pop over the entry, then down 15c, then the close.
AFTER = [(25.24, 25.18, 25.19), (25.20, 25.05, 25.06), (25.10, 25.02, 25.08),
         (25.12, 25.04, 25.05), (25.09, 25.01, 25.03), (25.06, 24.98, 25.00)]


def test_a_two_cent_stop_is_read_as_the_retest_buffer() -> None:
    after = bars5(et(2026, 11, 10, 15, 30), AFTER)
    now = ts(2026, 11, 10, 16, 30)
    # As the record had it: 1R is 2.47c, the 4c pop is the stop, and the trade is a loss.
    raw = compute_outcome(gme(), after, now)
    assert (raw["r"], raw["stopped"], raw["hit_1r"], raw["floored"]) == (0.0247, True, False, False)
    # With a floor of 8c (a quarter of a 32c ATR, for the test): the pop is noise, the drop is +1R.
    held = compute_outcome(gme(0.08), after, now)
    assert (held["r"], held["stopped"], held["hit_1r"]) == (0.08, False, True)
    assert held["floored"] is True
    assert held["hit_2r"] is True and held["ret_close_r"] == pytest.approx(2.5)
    # A stop already wider than the floor is the script's own, untouched.
    wide = {**gme(0.08), "stop": 25.40}
    assert compute_outcome(wide, after, now)["r"] == 0.2
    assert compute_outcome(wide, after, now)["floored"] is False


@pytest.mark.parametrize(
    ("price", "stop", "floor", "want"),
    [(100.0, 99.98, 0.30, 0.30),     # the floor is the larger
     (100.0, 99.50, 0.30, 0.50),     # the stop is
     (100.0, 100.02, 0.30, 0.30),    # a short's stop is above
     (100.0, 99.98, None, 0.02),     # no floor on the signal: as it was
     (100.0, 99.98, 0.0, 0.02),
     (100.0, 99.98, True, 0.02)],    # a flag is not a distance
)
def test_the_stops_distance_is_never_less_than_its_floor(price: float, stop: float, floor: Any,
                                                         want: float) -> None:
    assert scan.risk_of(price, stop, floor) == pytest.approx(want)


def test_every_trade_signal_the_replay_finds_carries_its_floor() -> None:
    # Monday's high is 101; Tuesday breaks it at the open and comes back to it.
    def day(d: date, rows: list[tuple[float, float, float, float]]) -> list[Bar]:
        t0 = int(et(d.year, d.month, d.day, 9, 30).timestamp())
        return [Bar(t0 + i * 300, o, h, lo, c, 1000.0) for i, (o, h, lo, c) in enumerate(rows)]

    mon = day(date(2026, 10, 12), [(100.0, 101.0, 99.0, 100.0)] * 78)
    tue = day(date(2026, 10, 13), [(100.5, 102.0, 100.4, 101.8), (101.8, 102.2, 101.6, 102.0),
                                   (102.0, 102.1, 100.9, 101.2), (101.2, 101.6, 101.05, 101.5),
                                   (101.5, 101.9, 101.4, 101.8), (101.8, 102.3, 101.7, 102.2)])
    clk = scan.clock_at(et(2026, 10, 13, 10, 5))
    t = scan.technicals(mon + tue, [], clk)
    trades = [s for s in t.signals if s["kind"] in ("L", "E")]
    assert trades, "the retest should have fired"
    for s in trades:
        assert s["risk_min"] == pytest.approx(round(scan.BUF_MULT * (t.atr_b or 0.0), 4), rel=0.5)
        assert s["risk_min"] > 0
    # A breakout is not a trade with a stop: it carries none.
    assert all(s.get("risk_min") is None for s in t.signals if s["kind"] == "BO")
    # And the log keeps it on the event.
    evs = scanlog.signal_events("X", t.signals, 60, "2026-10-13", ts(2026, 10, 13, 10, 5))
    assert all((e["risk_min"] is not None) == (e["kind"] in ("L", "E")) for e in evs)


def _history(day_of: date, sessions: int = 2) -> list[Bar]:
    """Flat 5-minute bars with a 40c range for the sessions before `day_of`, so the
    ten-minute ATR at the open of `day_of` is a known 40c."""
    out: list[Bar] = []
    d = day_of.toordinal() - sessions
    for k in range(sessions):
        dd = date.fromordinal(d + k)
        t0 = int(et(dd.year, dd.month, dd.day, 9, 30).timestamp())
        out += [Bar(t0 + i * 300, 25.2, 25.4, 25.0, 25.2, 1000.0) for i in range(78)]
    return out


def _settled(path: Any) -> None:
    raw = compute_outcome(gme(), bars5(et(2026, 11, 10, 15, 30), AFTER), ts(2026, 11, 10, 16, 30))
    rows = [
        {"id": 1, "live": True, "score": 61, "sym": "GME", "level": "PML", **gme(),
         "outcome": raw},
        # A signal on a name whose bars are gone.
        {"id": 2, "live": True, "score": 40, "sym": "GONE", "level": "PDL", **gme(),
         "outcome": raw},
        # One whose stop was already a real distance.
        {"id": 3, "live": True, "score": 50, "sym": "GME", "level": "PDL",
         **{**gme(), "stop": 25.60, "t": ts(2026, 11, 10, 15, 10)},
         "outcome": {**raw, "r": 0.4, "stopped": False}},
    ]
    path.write_text("".join(json.dumps(r) + "\n" for r in rows), encoding="utf-8")


def test_settled_signals_are_worked_again_where_the_bars_allow(tmp_path: Any) -> None:
    path = tmp_path / "ev.jsonl"
    _settled(path)
    before = path.read_text(encoding="utf-8")
    hist = _history(date(2026, 11, 10))
    tue = [Bar(int(et(2026, 11, 10, 9, 30).timestamp()) + i * 300, 25.2, 25.4, 25.0, 25.2, 1000.0)
           for i in range(72)]                                      # 09:30 to 15:25
    held = {"GME": hist + tue[:-2] + bars5(et(2026, 11, 10, 15, 20), [(25.23, 25.19, 25.20)] * 2)
            + bars5(et(2026, 11, 10, 15, 30), AFTER)}
    log = EventLog(str(path))
    got = log.refloor(held.get, et(2026, 11, 10, 20, 30))
    assert got == {"seen": 3, "ruled": 2, "floored": 1, "skipped": 1}
    by = {e["id"]: e for e in log.events}
    # GME's 2.47c stop is read as the buffer: a quarter of the ten-minute ATR at its bar.
    assert by[1]["risk_min"] == pytest.approx(0.1, abs=0.02)
    assert by[1]["outcome"]["floored"] is True and by[1]["outcome"]["stopped"] is False
    assert by[1]["outcome_raw"]["stopped"] is True and by[1]["outcome_raw"]["r"] == 0.0247
    # The one with no bars is exactly as it was.
    assert "risk_min" not in by[2] or by[2]["risk_min"] is None
    assert by[2]["outcome"]["stopped"] is True and "outcome_raw" not in by[2]
    # The wide stop keeps its outcome and is marked as read by the rule.
    assert by[3]["risk_min"] is not None and by[3]["outcome"]["floored"] is False
    assert by[3]["outcome"]["r"] == 0.4 and "outcome_raw" not in by[3]
    # The file as it stood is beside it, and a second run changes nothing.
    assert (tmp_path / "ev.before-floor.jsonl").read_text(encoding="utf-8") == before
    assert log.refloor(held.get, et(2026, 11, 10, 20, 31)) == {
        "seen": 1, "ruled": 0, "floored": 0, "skipped": 1}
    # The record says how much of it is on the rule.
    st = log.stats(20, date(2026, 11, 10))
    assert st["floor"] == {"ruled": 2, "floored": 1, "unruled": 1}


def test_bars_that_stop_short_of_the_bell_change_nothing(tmp_path: Any) -> None:
    path = tmp_path / "ev.jsonl"
    _settled(path)
    hist = _history(date(2026, 11, 10))
    tue = [Bar(int(et(2026, 11, 10, 9, 30).timestamp()) + i * 300, 25.2, 25.4, 25.0, 25.2, 1000.0)
           for i in range(72)]
    # The last download was at 15:45: the day's end is not in it.
    part = {"GME": hist + tue + bars5(et(2026, 11, 10, 15, 30), AFTER[:3])}
    log = EventLog(str(path))
    assert log.refloor(part.get, et(2026, 11, 10, 20, 30))["ruled"] == 0
    assert all("outcome_raw" not in e for e in log.events)
    assert not (tmp_path / "ev.before-floor.jsonl").exists()


def test_a_stop_exactly_on_the_entry_is_the_floors_own_case() -> None:
    # A bar that closes ON its low: the script's stop idea is the entry itself. Three
    # real ones in the record (ARM 29 Oct 12:00, PH 5 Nov 13:50, SHOP 9 Nov 14:00) came
    # back with no R at all, because a distance of nothing was sent back before the
    # floor was looked at.
    after = bars5(et(2026, 11, 10, 15, 30), AFTER)
    now = ts(2026, 11, 10, 16, 30)
    got = compute_outcome({**gme(0.08), "stop": 25.20}, after, now)
    assert (got["r"], got["floored"], got["stopped"], got["hit_1r"]) == (0.08, True, False, True)
    assert got["final"] is True and got["ret_close_r"] == pytest.approx(2.5)
    # With no floor there is nothing to measure in: settled, and no R.
    bare = compute_outcome({**gme(), "stop": 25.20}, after, now)
    assert bare["final"] is True
    assert (bare["r"], bare["hit_1r"], bare["stopped"]) == (None, None, None)
    # And a signal with no stop at all is as it was, floor or not.
    assert compute_outcome({**gme(0.08), "stop": None}, after, now)["r"] is None


def test_a_stop_on_its_entry_settled_unmeasured_is_worked_once_more(tmp_path: Any) -> None:
    blank = {**scanlog.blank_outcome(), "final": True}
    rows = [
        # As the three stood on 11 Nov: the floor on the event, and still no R.
        {"id": 1, "live": True, "score": 61, "sym": "GME", "level": "PML",
         **{**gme(0.1), "stop": 25.20}, "outcome": dict(blank), "outcome_raw": dict(blank)},
        # One from before the floor, never worked.
        {"id": 2, "live": True, "score": 50, "sym": "GME", "level": "PDL",
         **{**gme(), "stop": 25.20, "t": ts(2026, 11, 10, 15, 10)}, "outcome": dict(blank)},
    ]
    path = tmp_path / "ev.jsonl"
    path.write_text("".join(json.dumps(r) + "\n" for r in rows), encoding="utf-8")
    hist = _history(date(2026, 11, 10))
    tue = [Bar(int(et(2026, 11, 10, 9, 30).timestamp()) + i * 300, 25.2, 25.4, 25.0, 25.2, 1000.0)
           for i in range(72)]
    held = {"GME": hist + tue[:-2] + bars5(et(2026, 11, 10, 15, 20), [(25.23, 25.19, 25.20)] * 2)
            + bars5(et(2026, 11, 10, 15, 30), AFTER)}
    log = EventLog(str(path))
    assert log.refloor(held.get, et(2026, 11, 10, 20, 30)) == {
        "seen": 2, "ruled": 2, "floored": 2, "skipped": 0}
    for e in log.events:
        o = e["outcome"]
        assert o["floored"] is True and o["r"] == e["risk_min"] and e["risk_min"] > 0
        assert (o["stopped"], o["hit_1r"]) == (False, True)
        # What it replaced is the first outcome, kept once and never written over.
        assert e["outcome_raw"] == blank
    assert log.refloor(held.get, et(2026, 11, 10, 20, 31)) == {
        "seen": 0, "ruled": 0, "floored": 0, "skipped": 0}


def test_a_signal_settled_with_nothing_read_after_it_is_read_from_the_bars(tmp_path: Any) -> None:
    # GEV's (L) at 10:00 on Wed 28 Oct 2026 was settled "neither" with no best and
    # no worst: its bars were not to hand an hour after the bell. The bars held now
    # say what it did.
    blind = {**scanlog.blank_outcome(), "r": 0.4, "hit_1r": False, "hit_2r": False,
             "stopped": False, "final": True, "floored": False}
    rows = [
        # A short at 25.20 on the 15:10 bar with a real stop, 40c away.
        {"id": 1, "live": True, "score": 55, "sym": "GME", "level": "PDL",
         **{**gme(0.1), "stop": 25.60, "t": ts(2026, 11, 10, 15, 10)}, "outcome": dict(blind)},
        # An (L) on the day's last bar has nothing after it: that is not a miss.
        {"id": 2, "live": False, "score": None, "sym": "GME", "level": "PML",
         **{**gme(0.1), "stop": 25.60, "t": ts(2026, 11, 10, 15, 50)}, "outcome": dict(blind)},
    ]
    path = tmp_path / "ev.jsonl"
    path.write_text("".join(json.dumps(r) + "\n" for r in rows), encoding="utf-8")
    hist = _history(date(2026, 11, 10))
    tue = [Bar(int(et(2026, 11, 10, 9, 30).timestamp()) + i * 300, 25.2, 25.4, 25.0, 25.2, 1000.0)
           for i in range(72)]
    held = {"GME": hist + tue[:-2] + bars5(et(2026, 11, 10, 15, 20), [(25.23, 25.19, 25.20)] * 2)
            + bars5(et(2026, 11, 10, 15, 30), AFTER)}
    log = EventLog(str(path))
    assert log.refloor(held.get, et(2026, 11, 10, 20, 30)) == {
        "seen": 1, "ruled": 1, "floored": 0, "skipped": 0}
    by = {e["id"]: e for e in log.events}
    o = by[1]["outcome"]
    # 22c its way at best, 4c against: neither, but now with what it did.
    assert (o["r"], o["hit_1r"], o["stopped"], o["floored"]) == (0.4, False, False, False)
    assert o["mfe_r"] == pytest.approx(0.55) and o["mae_r"] == pytest.approx(0.1)
    assert o["ret_close_r"] == pytest.approx(0.5)
    assert by[1]["outcome_raw"] == blind
    assert by[2]["outcome"] == blind and "outcome_raw" not in by[2]
    # Read once: the next start finds nothing to do.
    assert log.refloor(held.get, et(2026, 11, 10, 20, 31)) == {
        "seen": 0, "ruled": 0, "floored": 0, "skipped": 0}


def test_an_open_signal_from_before_the_floor_takes_it_from_the_replay() -> None:
    e = {"id": 1, "kind": "L", "side": "long", "level": "PMH", "sym": "X", "day": "2026-11-11",
         "t": 1000, "price": 100.0, "stop": 99.98, "outcome": scanlog.blank_outcome()}
    cur = {**e, "risk_min": 0.3}
    found = {scanlog.dedupe_key(e): cur}
    assert scanlog.revalidate(e, found, 1000 + 600, 2000.0) is True
    assert e["risk_min"] == 0.3
    # A settled one is not touched here: `refloor` keeps what it replaces.
    done = {**e, "risk_min": None, "outcome": {**scanlog.blank_outcome(), "final": True}}
    assert scanlog.revalidate(done, found, 1000 + 600, 2000.0) is False


def test_the_contracts_risk_reads_the_same_stop() -> None:
    row = {"last": 100.5, "atr_b": 1.2,
           "signals": [{"kind": "L", "side": "long", "price": 100.0, "stop": 99.98,
                        "risk_min": 0.3}]}
    entry, stop, how = optcalc.trade_plan(row, "long")
    assert (entry, stop) == (100.0, pytest.approx(99.7))
    assert how == "the (L) signal's stop, held to the retest buffer"
    # A stop that was already wider is the signal's own.
    row["signals"][0]["stop"] = 99.4
    assert optcalc.trade_plan(row, "long")[1:] == (99.4, "the (L) signal's stop")
