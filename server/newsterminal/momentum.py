"""
Day 1, Day 2, Day 3 — which big movers are still moving.

THE IDEA (owner, 2026-11-09: "I always lose track of my big momentum plays"). A
stock that makes an outsized move on heavy volume, usually on news, tends not to
be finished. The session after is Day 2, and its question is the desk's usual one
aimed at the strongest names of the week: Day 1's high is now the PDH, so does it
break and hold? An inside day is the move resting, and a break of that small range
is the next trigger. Day 3 and on are older and more stretched.

WHAT MAKES A DAY 1. A close-to-close move of 20% or more on 1.5x normal volume at
$2bn+ (the table's defaults, changeable in its filters; the screenshots' own
cut-off is too blurry to read but cannot be above 25%, since XERS at +25.05% and
ADMA at +26.05% made their list for Nov 5). The ledger keeps everything down to
10% and $300m, so the filters can loosen without waiting for history: on Nov 5
those floors found 279 names, 21 of them at the defaults.

WHERE THE HISTORY COMES FROM. The screener carries only two previous sessions'
bars, so the ledger writes itself: once a session, from the first read after its
final figures are in, each open track takes that day's bar and new Day 1s are
added. The very first run seeds yesterday's Day 1s from `[1]` and `[2]`; a Day 3
appears the session after that, and no earlier one can be recovered from this feed.

ITS OWN ROUGH ORDER, NOT THE SCANNER'S SCORE (owner, 2026-11-10: "follow the
screenshots closely"; theirs ranks this table on prev-day levels, volume and news).
The 0-100 rank needs bars and was audited on 5 Nov (see tools/fit_score.py). This one
is a sum of three named parts from what the wide read has (`score_of`), a judgement
with no outcome test behind it, and the row's words still say what the name did.
Pure but for the file.
"""

from __future__ import annotations

import json
import os
import threading
from collections.abc import Callable, Iterable
from datetime import UTC, date, datetime
from typing import Any

from .config import CACHE_DIR
from .holidays import next_trading_day, prev_trading_day

STATE_FILE = os.path.join(CACHE_DIR, "scanner_momentum.json")

#: What the ledger records at all; the table's filter narrows it.
MOVE_FLOOR = 10.0
VOLUME_FLOOR = 1.5
CAP_FLOOR = 300_000_000.0
#: The table's defaults.
DEFAULT_MOVE = 20.0
DEFAULT_CAP = 2e9
#: A track is dropped after this stage: a move a week old is not a Day 3+ any more.
MAX_STAGE = 6


def sessions_after(a: date, b: date) -> int:
    """How many trading days after `a` is `b`. Pure. 0 when they are the same."""
    n = 0
    d = a
    while d < b:
        d = next_trading_day(d)
        n += 1
    return n


def _bar(d: date, o: Any, h: Any, lo: Any, c: Any, v: Any) -> dict[str, Any]:
    return {"day": d.isoformat(), "o": o, "h": h, "l": lo, "c": c, "v": v}


def state_of(side: str, basis: str, hi: float | None, lo: float | None, last: float,
             pdh: float, pdl: float, d1_low: float | None, d1_high: float | None,
             ) -> tuple[str, str]:
    """A track's standing as (words, kind). Pure.

    Kind sorts the table: confirmed, inside, watch, failed. Before the open there
    is no bar yet, only where the pre-market stands against the level. "closed"
    is said only of a finished bar.
    """
    closed = basis in ("post", "last")
    long_ = side == "long"
    level, word_lv = (pdh, "PDH") if long_ else (pdl, "PDL")
    beyond = last > level if long_ else last < level
    if basis == "pre":
        return (f"{'Above' if long_ else 'Below'} {word_lv}", "confirmed") if beyond else (
            f"{'Under' if long_ else 'Over'} {word_lv}", "watch")
    if long_ and d1_low is not None and last < d1_low:
        return ("Lost Day 1's low", "failed")
    if not long_ and d1_high is not None and last > d1_high:
        return ("Lost Day 1's high", "failed")
    if hi is not None and lo is not None and hi <= pdh and lo >= pdl:
        return ("Inside day", "inside")
    broke = (hi is not None and hi > pdh) if long_ else (lo is not None and lo < pdl)
    if beyond:
        verb = f"closed {'above' if long_ else 'below'}" if closed else (
            f"{'above' if long_ else 'below'} it")
        return (f"Broke {word_lv}, {verb}", "confirmed")
    if broke:
        return (f"Broke {word_lv}, faded", "watch")
    return (f"{'Under' if long_ else 'Over'} {word_lv}", "watch")


KIND_ORDER = {"confirmed": 0, "inside": 1, "watch": 2, "failed": 3}

#: Points for the story, by its grade (catalysts.py).
NEWS_POINTS = {1: 25.0, 2: 15.0, 3: 8.0}


def score_of(side: str, kind: str, last: float, pdh: float, pdl: float,
             vol_vs_normal: float | None, tier: int | None) -> int:
    """The table's rough 0-100 order, in three parts. Pure.

    Where price stands in yesterday's range from the trade's side: up to 35, and 10
    more for being through its level. The volume against a normal day: up to 30, full
    at twice normal. The news: 25, 15 or 8 by its grade. A failed track is halved.
    """
    span = pdh - pdl
    pos = (last - pdl) / span if span > 0 else 0.5
    pos = max(0.0, min(1.0, pos if side == "long" else 1.0 - pos))
    beyond = last > pdh if side == "long" else last < pdl
    total = pos * 35.0 + (10.0 if beyond else 0.0)
    total += min((vol_vs_normal or 0.0) / 2.0, 1.0) * 30.0
    total += NEWS_POINTS.get(tier or 0, 0.0)
    return round(total * (0.5 if kind == "failed" else 1.0))


class MomentumStore:
    """The ledger of Day 1s and what each has done since."""

    def __init__(self, path: str = STATE_FILE) -> None:
        self.path = path
        self._lock = threading.Lock()
        self.tracks: dict[str, dict[str, Any]] = {}
        self.last_day: str | None = None
        self._load()

    def _load(self) -> None:
        try:
            with open(self.path, encoding="utf-8") as f:
                d = json.load(f)
        except (OSError, ValueError):
            return
        if isinstance(d, dict):
            self.last_day = d.get("last_day")
            self.tracks = {str(t["key"]): t for t in d.get("tracks") or []
                           if isinstance(t, dict) and t.get("key")}

    def _save(self) -> None:
        tmp = self.path + ".tmp"
        try:
            os.makedirs(os.path.dirname(self.path), exist_ok=True)
            with open(tmp, "w", encoding="utf-8") as f:
                json.dump({"saved_utc": datetime.now(UTC).isoformat(), "last_day": self.last_day,
                           "tracks": list(self.tracks.values())}, f)
            os.replace(tmp, self.path)
        except OSError:
            pass

    @staticmethod
    def _qualifies(move: float | None, vx: float | None, cap: float | None) -> bool:
        return (move is not None and vx is not None and cap is not None
                and abs(move) >= MOVE_FLOOR and vx >= VOLUME_FLOOR and cap >= CAP_FLOOR)

    def _start(self, r: dict[str, Any], day: date, move: float, vx: float,
               d1: dict[str, Any], days: list[dict[str, Any]]) -> None:
        key = f"{r['sym']}|{day.isoformat()}"
        self.tracks[key] = {
            "key": key, "sym": r["sym"], "name": r["name"], "cap": r["cap"], "sector": r["sector"],
            "day1": day.isoformat(), "side": "long" if move > 0 else "short",
            "move": round(move, 2), "vx": round(vx, 1), "d1": d1, "days": days,
        }

    def update(self, rows: Iterable[dict[str, Any]], day: date) -> bool:
        """Close the books for the session `day`, whose bar is the rows' base bar.

        Once per session. True when it did anything. `rows` are universe rows
        (sources/universe.parse); it is the caller's part to pass them only when
        the base bar is that finished session.
        """
        iso = day.isoformat()
        if self.last_day == iso or (self.last_day is not None and self.last_day > iso):
            return False

        def today_bar(x: dict[str, Any]) -> dict[str, Any]:
            return _bar(day, x["open"], x["high"], x["low"], x["close"], x["vol"])

        rows = list(rows)
        by = {r["sym"]: r for r in rows}
        with self._lock:
            first = self.last_day is None
            for t in self.tracks.values():
                r = by.get(t["sym"])
                if r is None or r["close"] is None or t["day1"] >= iso:
                    continue
                if not any(b["day"] == iso for b in t["days"]):
                    t["days"].append(today_bar(r))
            prev = prev_trading_day(day)
            for r in rows:
                avg = r["avg"]
                if avg and avg > 0 and r["chg"] is not None and r["vol"] is not None:
                    vx = r["vol"] / avg
                    if self._qualifies(r["chg"], vx, r["cap"]):
                        self._start(r, day, r["chg"], vx, today_bar(r), [])
                if first and avg and avg > 0 and r["c1"] and r["c2"] and r["v1"] is not None:
                    move1 = (r["c1"] / r["c2"] - 1.0) * 100.0
                    vx1 = r["v1"] / avg
                    if self._qualifies(move1, vx1, r["cap"]):
                        self._start(r, prev, move1, vx1,
                                    _bar(prev, r["o1"], r["h1"], r["l1"], r["c1"], r["v1"]),
                                    [today_bar(r)])
            self.tracks = {k: t for k, t in self.tracks.items()
                           if sessions_after(date.fromisoformat(t["day1"]), day) + 1 < MAX_STAGE}
            self.last_day = iso
            self._save()
        return True

    def stage(self, t: dict[str, Any], today: date, session_on: bool) -> int:
        """The track's day number: Day 1's own session is 1. A session in progress counts."""
        d1 = date.fromisoformat(t["day1"])
        return sessions_after(d1, today) + 1 if session_on else (
            sessions_after(d1, date.fromisoformat(self.last_day)) + 1 if self.last_day else 1)

    def stages(self, today: date, session_on: bool, min_stage: int = 1) -> dict[str, int]:
        """{sym: its youngest track's day number}, for the other tables' Day 2/3 chips."""
        out: dict[str, int] = {}
        with self._lock:
            tracks = list(self.tracks.values())
        for t in tracks:
            s = self.stage(t, today, session_on)
            if s >= min_stage and (t["sym"] not in out or s < out[t["sym"]]):
                out[t["sym"]] = s
        return out

    def strong(self, today: date, session_on: bool, min_move: float = DEFAULT_MOVE,
               cap: float = DEFAULT_CAP, min_stage: int = 2) -> dict[str, dict[str, Any]]:
        """{sym: {stage, move, side}} for the tracks past the table's own defaults, on
        Day 2 or later: what the pool's rank reads (sources/pool.in_play), so a name
        coiling after a 20% day is promoted onto the list without being tracked by hand.
        A name with two tracks is its youngest."""
        out: dict[str, dict[str, Any]] = {}
        with self._lock:
            tracks = [t for t in self.tracks.values()
                      if abs(t["move"]) >= min_move and (t.get("cap") or 0) >= cap]
        for t in tracks:
            s = self.stage(t, today, session_on)
            if s >= min_stage and (t["sym"] not in out or s < out[t["sym"]]["stage"]):
                out[t["sym"]] = {"stage": s, "move": t["move"], "side": t["side"]}
        return out

    def names(self, cap: float = DEFAULT_CAP) -> list[str]:
        """The names worth the live stream, biggest Day 1 volume first."""
        with self._lock:
            rows = [t for t in self.tracks.values()
                    if (t.get("cap") or 0) >= cap and abs(t["move"]) >= DEFAULT_MOVE]
        rows.sort(key=lambda t: -t["vx"])
        return list(dict.fromkeys(t["sym"] for t in rows))

    def snapshot(self) -> list[dict[str, Any]]:
        with self._lock:
            return [dict(t) for t in self.tracks.values()]

    def table(self, *, read: Callable[[str], dict[str, Any] | None],
              raw: Callable[[str], dict[str, Any] | None],
              catalyst: Callable[[str], dict[str, Any] | None],
              spark: Callable[[str], list[float] | None], tracked: frozenset[str],
              pinned: frozenset[str], basis: str, today: date, min_move: float, cap: float,
              chip: str, forming: list[dict[str, Any]]) -> dict[str, Any]:
        """The Day 2/3 table: every track past the filters, read against now."""
        session_on = basis != "last"
        rows: list[dict[str, Any]] = []
        seen: set[str] = set()

        def add(sym: str, e: dict[str, Any], r: dict[str, Any], side: str, stage: int, moved: str,
                move: float, vx: float | None, d1c: float | None, d1_low: float | None,
                d1_high: float | None) -> None:
            if stage <= 1:
                words, kind = "Day 1", "confirmed"
            else:
                words, kind = state_of(side, basis, r["high"] if basis != "pre" else None,
                                       r["low"] if basis != "pre" else None, e["last"], e["pdh"],
                                       e["pdl"], d1_low, d1_high)
            level = e["pdh"] if side == "long" else e["pdl"]
            story = catalyst(sym)
            # Volume against normal FOR THIS POINT IN THE DAY. Before the open it is the
            # pre-market's, where 5% of a day is normal. In the session it is the
            # reading's time-of-day figure: a whole day's average made every name read
            # a tenth of normal at 10:00 and full by the close, so the score drifted
            # up all session and the volume part said nothing in the morning (audit,
            # 2026-11-11). Once the day is whole, the day against an average one. All
            # three are the reading's RVOL since 2026-11-13 (universe.rvol_for), the
            # figure every page shows; before the bell the pre-market's own.
            normal = float(e.get("rvol") or 0.0)
            rows.append({
                "sym": sym, "name": r["name"], "cap": r["cap"], "sector": r["sector"],
                "side": side, "stage": stage, "moved": moved, "move": move, "vx": vx,
                "chg": e["chg"], "last": e["last"], "pdh": e["pdh"], "pdl": e["pdl"],
                "level": level,
                "to_level": round((e["last"] / level - 1.0) * 100.0, 1) if level else None,
                "vol": e.get("vol"), "adv_pct": e["adv_pct"], "state": words, "kind": kind,
                "score": score_of(side, kind, e["last"], e["pdh"], e["pdl"], normal,
                                  story.get("tier") if story else None),
                "through": e["pd_state"] != "inside", "live": e["live"],
                "since": round((e["last"] / d1c - 1.0) * 100.0, 2) if d1c else None,
                "catalyst": story, "tracked": sym in tracked, "pinned": sym in pinned,
            })

        for t in self.snapshot():
            if abs(t["move"]) < min_move or (t.get("cap") or 0) < cap:
                continue
            stage = self.stage(t, today, session_on)
            sym = t["sym"]
            e, r = read(sym), raw(sym)
            if e is None or r is None or stage >= MAX_STAGE:
                continue
            # A name with two moves this week shows its most recent.
            if sym in seen:
                prior = next(x for x in rows if x["sym"] == sym)
                if prior["moved"] >= t["day1"]:
                    continue
                rows.remove(prior)
            seen.add(sym)
            d1 = t["d1"]
            add(sym, e, r, t["side"], stage, t["day1"], t["move"], t["vx"], d1.get("c"),
                d1.get("l"), d1.get("h"))
        for f in forming:
            r = f["raw"]
            sym = r["sym"]
            if sym in seen or f["chg"] is None:
                continue
            seen.add(sym)
            add(sym, f, r, "long" if f["chg"] > 0 else "short", 1, today.isoformat(), f["chg"],
                f["rvol"], None, None, None)

        counts = {
            "all": len(rows),
            "long": sum(1 for x in rows if x["side"] == "long"),
            "short": sum(1 for x in rows if x["side"] == "short"),
            "day1": sum(1 for x in rows if x["stage"] == 1),
            "day2": sum(1 for x in rows if x["stage"] == 2),
            "day3": sum(1 for x in rows if x["stage"] >= 3),
            "inside": sum(1 for x in rows if x["kind"] == "inside"),
            "through": sum(1 for x in rows if x["through"]),
        }
        keep = {
            "long": lambda x: x["side"] == "long", "short": lambda x: x["side"] == "short",
            "day1": lambda x: x["stage"] == 1, "day2": lambda x: x["stage"] == 2,
            "day3": lambda x: x["stage"] >= 3, "inside": lambda x: x["kind"] == "inside",
            "through": lambda x: x["through"],
        }.get(chip)
        kept = [x for x in rows if keep(x)] if keep else rows
        kept.sort(key=lambda x: (-x["score"], KIND_ORDER[x["kind"]], x["stage"]))
        for x in kept:
            x["spark"] = spark(x["sym"])
        return {"chips": counts, "rows": kept, "shown": len(kept), "matched": len(rows),
                "last_day": self.last_day}
