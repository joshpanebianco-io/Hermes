"""
The live rotation — the Scanner list's pool picks swapped for better setups during the session.

WHY (owner, 2026-11-19, 10:00 ET): "why does it keep low scored stocks on the list when ive
search stocks not on the list and they have higher scores?" — then, to the proposal of a
fifteen-minute rotation: "yes but i think it should update and rotate more frequent and closer
to real time no?". Until then the forty names the engine scores were chosen before the bell
(the pool's marks, sources/pool.py) on how in play each was, and from 10:00 the list held until
the day rolled. That morning CRWV, opened from the search, scored 50 off the list while ASTS
(7), TSLA (11), TTWO (22) and SPY (23) sat on it.

WHAT CAN MOVE AND WHAT CANNOT. SPY, QQQ, IWM and the MAG 7 are on the list always (the owner's
rule, 2026-11-13), today's favourites and a name tracked by hand are the owner's; none of those
is ever rotated out. The rest are the pool's picks: those a better setup may replace.

A ROUND A MINUTE (ROUND_SEC), from 09:35 (one five-minute bar of the session printed) to a
quarter hour before the close, on the scanner's own thread:
  1. The candidates: the wide read's names off the list that are through their levels now,
     on the stream's live price (universe.UniverseStore.rotation_finder: an outside day
     first, then through the previous day's level, then relative volume), among the names
     the pool counts as tradable (pool.qualify: $10+, the turnover, the daily range), plus
     any name the owner has opened in the last hour (OPENED_SEC). CANDIDATES at most.
  2. Each is scored by the same arithmetic as a name on the list, the read a search makes
     (scanner.ScanStore.compute_one, then the payload's scoring). Its five-minute bars are
     read again at most every REREAD_SEC, READS_PER_ROUND reads a round, and the stream's
     live trade is laid over them between reads (ScanStore.live_bars), so the score moves
     with the price while the extra load on Yahoo stays a few reads a minute.
  3. `decide`: a free slot takes a candidate scoring FLOOR or more; a full list swaps one in
     for its weakest pick when the candidate beats that pick by MARGIN or more. Either way
     the candidate has to qualify on CONFIRM rounds in a row, so one tick's spike does not
     move the list, and at most MAX_MOVES move a round.

WHAT HOLDS A PICK. A name rotated in stays MIN_STAY_SEC at least, so the list does not
flicker and a chart opened on it does not vanish. A name stays for its signals, on any chart
(scanlog.EventLog.holding): a live (L) / (E) / (V) in the last TRADE_HOLD_SEC whose stop has not
been hit is a trade the owner may be in, and a live breakout in the last BREAK_HOLD_SEC has its
retest still to come. The first round, at 10:07 on 19 Nov, held every pick that had signalled
in the last half hour, and after the open that was nearly all of them: TTWO at 22 and AVGO at
27 were held for breakouts from 09:40 and 10:00 that had gone nowhere.

WHAT IT DOES NOT CHANGE. The score, the order the list is drawn in, the core, the favourites
and the pre-market marks. A name that joins is read like any other tracked name from then on;
its signals from before it joined are logged as not live, so they never alert (scanlog._event),
and a name that leaves has its signals settled after the bell like any name that left the list
(ScanStore.read_owed). Each move is written to cache/rotation.jsonl (`log_line`), so whether
the names that came in did better than the ones that went out can be tested.

The arithmetic here is pure; the collector (`Collector._do_rotation`) does the reads.
"""

from __future__ import annotations

import json
import os
from collections.abc import Callable, Iterable
from datetime import datetime
from typing import Any

from . import scan

#: Seconds between rounds while the window is open, and between looks while it is shut.
ROUND_SEC = 60.0
IDLE_SEC = 60.0
#: The window, in minutes of the ET day: one five-minute bar after the bell, to a quarter
#: hour before the close (the close of a half day too: scan.rth_end).
START_MIN = scan.RTH_START + 5
END_BEFORE_CLOSE_MIN = 15
#: A free slot takes a candidate at this score or more (0-100, the list's own scale).
FLOOR = 40
#: A full list swaps a candidate in for its weakest pick at this lead or more.
MARGIN = 10
#: Rounds in a row a candidate must qualify before it moves.
CONFIRM = 2
#: Moves a round at most.
MAX_MOVES = 2
#: Names scored a round at most: the finder's and the ones the owner opened.
CANDIDATES = 8
OPENED_MAX = 3
#: How long a name the owner opened stays a candidate.
OPENED_SEC = 3600.0
#: Five-minute bar reads a round at most, and how old a candidate's may be before a re-read.
READS_PER_ROUND = 3
REREAD_SEC = 180.0
#: A name rotated in stays this long at least.
MIN_STAY_SEC = 600.0
#: A live trade signal this recent, not stopped out, holds a name on the list; so does a live
#: breakout this recent.
TRADE_HOLD_SEC = 1800.0
BREAK_HOLD_SEC = 900.0

LOG_NAME = "rotation.jsonl"


def in_window(now: datetime) -> bool:
    """Is the rotation on at `now`? The regular session, from START_MIN to
    END_BEFORE_CLOSE_MIN before its close. Pure.

    Worked examples, a full day: 09:34 → False · 09:35 → True · 15:44 → True ·
    15:45 → False · a half day (13:00 close) 12:44 → True, 12:45 → False."""
    clock = scan.clock_at(now)
    if clock.session != "rth":
        return False
    m = clock.now.hour * 60 + clock.now.minute
    return START_MIN <= m < scan.rth_end(clock.now.date()) - END_BEFORE_CLOSE_MIN


#: Names on the list that may lack a score before a round is trusted (`scores_ready`).
UNSCORED_SLACK = 3


def scores_ready(listed: Iterable[str], scores: dict[str, Any],
                 slack: int = UNSCORED_SLACK) -> bool:
    """Has the list a score for nearly every name on it? Not in the first minute after a
    restart, when the bars on disk are still being read: at 10:12 on 19 Nov the first round
    after one read TTWO at 0, which it scored 22 a minute later. A pick with no score counts
    as the weakest (`decide`), so a round on a half-built list would swap out names that
    have no score only because they have not been read yet. Pure."""
    missing = [s for s in listed if not isinstance(scores.get(s), int | float)]
    return len(missing) <= slack


def held(promoted: Iterable[dict[str, Any]], listed: Iterable[str], scores: dict[str, Any],
         signalled: Iterable[str], now_ts: float, *,
         tradable: Iterable[str] | None = None, mine: Iterable[str] = (),
         min_stay_sec: float = MIN_STAY_SEC) -> list[dict[str, Any]]:
    """The pool's picks on the list as `decide` reads them: each with its score now and
    whether it is locked (rotated in under `min_stay_sec` ago, held by its signals:
    `signalled`, scanlog.EventLog.holding, or not scored yet). `promoted` is the pool's
    entries (symbol, and `since` when the rotation brought it in); a pick not on the list
    (`listed`) is not counted.

    A name the rotation brought in that the pool does not count as tradable (`tradable`:
    the pool's qualified names) goes first, whatever holds it: scored 0 and unlocked. The
    first half hour of 19 Nov, before the finder was held to the pool's test, brought in
    SNEX, UGI, NTES and HSY, and their tidy levels kept them at the top of the list. A
    name the owner opened (`mine`) is theirs to judge and is spared. Pure."""
    on = set(listed)
    sig = set(signalled)
    ok = set(tradable) if tradable is not None else None
    own = set(mine)
    out: list[dict[str, Any]] = []
    for p in promoted:
        sym = str(p.get("symbol") or "")
        if not sym or sym not in on or p.get("mark") == "hand":
            continue
        if ok is not None and p.get("mark") == "live" and sym not in ok and sym not in own:
            out.append({"sym": sym, "score": 0.0, "locked": False,
                        "why": "not tradable by the pool's test"})
            continue
        since = p.get("since")
        young = isinstance(since, int | float) and now_ts - float(since) < min_stay_sec
        sc = scores.get(sym)
        # No score yet is not a low score: the name may not have been read since a restart.
        unscored = not isinstance(sc, int | float)
        out.append({"sym": sym, "score": None if unscored else float(sc),
                    "locked": young or sym in sig or unscored,
                    "why": "joined under ten minutes ago" if young else
                           "a live trade or a fresh breakout" if sym in sig else
                           "no score yet" if unscored else None})
    return out


def decide(cands: list[dict[str, Any]], picks: list[dict[str, Any]], room: int,
           streak: dict[str, int], *, floor: float = FLOOR, margin: float = MARGIN,
           confirm: int = CONFIRM, max_moves: int = MAX_MOVES
           ) -> tuple[list[dict[str, Any]], dict[str, int]]:
    """This round's moves, and the streaks to carry into the next. Pure.

    `cands` are the names off the list scored this round ({sym, score}); `picks` the pool's
    picks on it (`held`); `room` the free slots; `streak` how many rounds in a row each
    candidate has qualified so far. A candidate qualifies at `floor` or more and, when no
    slot is free, `margin` or more over the weakest unlocked pick (a pick with no score
    counts as 0). It moves on its `confirm`-th round in a row, best first, `max_moves` a
    round at most; each move takes a free slot or the weakest pick still standing.

    Worked example: room 0, picks ASTS 7, TTWO 22, WMT 44 (all unlocked), candidates CRWV 50
    and MRVL 30, streak {CRWV: 1}. CRWV qualifies (50 ≥ 40 and ≥ 7 + 10) on its second round
    and takes ASTS's place; MRVL is under the floor. Moves [CRWV for ASTS], streak {CRWV: 2}.
    """
    open_picks = sorted((p for p in picks if not p.get("locked")),
                        key=lambda p: p["score"] if p.get("score") is not None else 0.0)
    moves: list[dict[str, Any]] = []
    nxt: dict[str, int] = {}
    for c in sorted(cands, key=lambda c: -float(c.get("score") or 0.0)):
        sc = c.get("score")
        if not isinstance(sc, int | float) or sc < floor:
            continue
        if room <= 0:
            if not open_picks:
                continue
            weakest = open_picks[0]
            if sc < (weakest.get("score") or 0.0) + margin:
                continue
        n = streak.get(c["sym"], 0) + 1
        nxt[c["sym"]] = n
        if n < confirm or len(moves) >= max_moves:
            continue
        if room > 0:
            room -= 1
            moves.append({"in": c["sym"], "in_score": sc, "out": None, "out_score": None})
        else:
            out = open_picks.pop(0)
            moves.append({"in": c["sym"], "in_score": sc, "out": out["sym"],
                          "out_score": out.get("score")})
    return moves, nxt


def reads_due(cands: list[str], fetched: dict[str, float], now_ts: float, *,
              per_round: int = READS_PER_ROUND, reread_sec: float = REREAD_SEC) -> list[str]:
    """Which candidates' five-minute bars to read this round, in the candidates' order: a
    name with none first, then the stalest past `reread_sec`; `per_round` at most. Pure."""
    never = [s for s in cands if s not in fetched]
    stale = sorted((s for s in cands if s in fetched and now_ts - fetched[s] >= reread_sec),
                   key=lambda s: fetched[s])
    return [*never, *stale][:per_round]


def log_line(day: str, now: datetime, move: dict[str, Any], cands: list[dict[str, Any]],
             at: dict[str, dict[str, Any]] | None = None) -> dict[str, Any]:
    """One move as cache/rotation.jsonl keeps it: when, who came in and who went out with
    both scores, each name's side and last price at the swap (`at`: {sym: {side, last}}),
    and the round's candidates as they scored. The side and the price are what the record
    judges the swap on after the close (`outcome_line`, tools/rotation_record.py). Pure."""
    at = at or {}
    i, o = at.get(move["in"]) or {}, at.get(move["out"] or "") or {}
    return {"kind": "move", "day": day, "at_et": now.astimezone(scan.ET).strftime("%H:%M:%S"),
            "in": move["in"], "in_score": move["in_score"],
            "in_side": i.get("side"), "in_last": i.get("last"),
            "out": move["out"], "out_score": move["out_score"],
            "out_side": o.get("side"), "out_last": o.get("last"),
            "cands": [[c["sym"], c.get("score")] for c in cands]}


def day_names(lines: Iterable[dict[str, Any]], day: str) -> tuple[set[str], bool]:
    """(every name a move on `day` brought in or took out, whether `day` has its outcome
    line already), from the record's lines. Pure."""
    names: set[str] = set()
    done = False
    for e in lines:
        if e.get("day") != day:
            continue
        if e.get("kind") == "outcome":
            done = True
        else:
            names |= {s for s in (e.get("in"), e.get("out")) if s}
    return names, done


def outcome_line(day: str, names: Iterable[str],
                 raw_of: Callable[[str], dict[str, Any] | None]) -> dict[str, Any] | None:
    """After the close, once a day: each name the day's moves touched, with the session's
    close, high, low and daily ATR from the wide read (`raw_of(sym)`, its rows), so the
    record can say how far each went its way after the swap. None when no name has a
    close."""
    rows: dict[str, dict[str, Any]] = {}
    for s in sorted(names):
        r = raw_of(s) or {}
        if isinstance(r.get("close"), int | float):
            rows[s] = {k: r.get(k) for k in ("close", "high", "low", "atr")}
    return {"kind": "outcome", "day": day, "rows": rows} if rows else None


def read_lines(path: str) -> list[dict[str, Any]]:
    """The record's lines; an unreadable line is skipped, a missing file is none."""
    out: list[dict[str, Any]] = []
    try:
        with open(path, encoding="utf-8") as f:
            for line in f:
                try:
                    e = json.loads(line)
                except ValueError:
                    continue
                if isinstance(e, dict):
                    out.append(e)
    except OSError:
        pass
    return out


def run_its_way(side: Any, last: Any, close: Any, atr: Any) -> float | None:
    """How far a name went its own way from the swap to the close, in daily ATRs: up for a
    long, down for a short. None when a figure is missing or there is no side. Pure."""
    if side not in ("long", "short"):
        return None
    if not all(isinstance(x, int | float) for x in (last, close, atr)) or not atr:
        return None
    move = (float(close) - float(last)) / float(atr)
    return round(move if side == "long" else -move, 3)


def judge(lines: Iterable[dict[str, Any]]) -> list[dict[str, Any]]:
    """Each move whose day has its outcome on file, judged: `in_run` and `out_run` (each
    name's run its own way to the close, `run_its_way`), the hour it moved, and whether it
    filled a free slot. A move whose day has no outcome yet is left out. Pure."""
    lines = list(lines)
    closes = {e["day"]: e.get("rows") or {} for e in lines if e.get("kind") == "outcome"}
    out: list[dict[str, Any]] = []
    for e in lines:
        if e.get("kind") == "outcome" or e.get("day") not in closes:
            continue
        rows = closes[e["day"]]
        i, o = rows.get(e.get("in")) or {}, rows.get(e.get("out")) or {}
        out.append({"day": e["day"], "hour": str(e.get("at_et") or "")[:2],
                    "in": e.get("in"), "in_side": e.get("in_side"),
                    "in_run": run_its_way(e.get("in_side"), e.get("in_last"),
                                          i.get("close"), i.get("atr")),
                    "out": e.get("out"), "out_side": e.get("out_side"),
                    "out_run": run_its_way(e.get("out_side"), e.get("out_last"),
                                           o.get("close"), o.get("atr")),
                    "free": not e.get("out")})
    return out


def append(path: str, line: dict[str, Any]) -> None:
    """Add a line to the record; a write that fails is skipped, never raised."""
    try:
        os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
        with open(path, "a", encoding="utf-8") as f:
            f.write(json.dumps(line) + "\n")
    except OSError:
        pass
