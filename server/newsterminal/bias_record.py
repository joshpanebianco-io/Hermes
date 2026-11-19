"""
The bias record: every board read logged at set times, and each book's price at New
York's close, so the bias can be tested against what followed.

WHY (owner, 2026-11-19: "weight everything as best and accurate as we can based on
logic then gather data to test"). Until this record nothing logged the bias beside
what the session did next, so nothing could say whether a weight or a rule earned its
place. The logic pass of the same day (bias.py, drivestats.py) set the weights by
reasoning; this is the data that will test them.

WHAT IS WRITTEN (cache/bias_record.jsonl, one JSON object a line):

  {"kind": "read", "td": "2026-11-20", "mark": "08:45", "at": <epoch>, "book": "NQ",
   "weights": "ny_pre", "score": -24, "grade": "weak", "bias": "short", "coverage": 85,
   "conflict": false, "backers": 2, "last": 27410.25, "pct": -0.42, "usual": 1.21,
   "families": {"structure": [30, -100, -30.0], ...},   # weight, score, points
   "votes": {"yields": ["short", 0.6, true], ...}}       # vote, strength, live

  {"kind": "close", "td": "2026-11-20", "at": <epoch>, "last": {"NQ": 27250.5, ...}}

`td` is the New York session the read is FOR: a read at 20:00 ET belongs to the next
trading day, so every read of a day is judged against the same close. The stocks
tape is logged as book "TAPE" and judged on the S&P future, which trades at every mark
(SPY does not, at 20:00 or 03:30). `usual` is the book's usual day in percent
(drivestats.py), the yardstick the outcome is measured in. The backfill
(tools/bias_backfill.py) writes the same lines to its own file; the reader
(tools/bias_record.py) reads either.

PURE but for `read` and `append`.
"""

from __future__ import annotations

import json
import os
from datetime import date, datetime, time
from typing import Any
from zoneinfo import ZoneInfo

from .config import CACHE_DIR
from .holidays import early_close, is_trading_day, next_trading_day

ET = ZoneInfo("America/New_York")

RECORD_NAME = "bias_record.jsonl"
RECORD_FILE = os.path.join(CACHE_DIR, RECORD_NAME)

#: The marks, ET: Asia's evening, London, after the 08:30 prints, the bell's eve, and
#: three in the New York session. A mark is written once, in the MARK_SLACK_MIN after it.
MARKS: tuple[tuple[int, int], ...] = ((20, 0), (3, 30), (8, 45), (9, 25), (10, 30),
                                      (12, 0), (14, 0))
MARK_SLACK_MIN = 15
#: The close is written from the session's close (16:00, 13:00 on a half day) for this long.
CLOSE_SLACK_MIN = 30
#: The board's books, and the tape (judged on SPY).
BOOKS: tuple[str, ...] = ("NQ", "ES", "GC", "SIL", "CL")
TAPE = "TAPE"


def mark_name(hm: tuple[int, int]) -> str:
    return f"{hm[0]:02d}:{hm[1]:02d}"


def session_for(et: datetime) -> date | None:
    """The New York session a read at `et` is for: the same day before 18:00 on a
    trading day, the next trading day from 18:00 (or any time on a day that is not
    one). Pure."""
    d = et.date()
    if et.time() >= time(18, 0) or not is_trading_day(d):
        return next_trading_day(d)
    return d


def close_time(td: date) -> time:
    """When New York closes on `td`. Pure."""
    return early_close(td) or time(16, 0)


def due_mark(now: datetime, done: set[tuple[str, str]]) -> tuple[str, str] | None:
    """(td, mark) when a mark falls due at `now` and has not been written, else None.
    A mark is due in the MARK_SLACK_MIN after it, on an evening before a trading day
    or on a trading day before its close. Pure."""
    et = now.astimezone(ET)
    for hm in MARKS:
        at = et.replace(hour=hm[0], minute=hm[1], second=0, microsecond=0)
        if not 0 <= (et - at).total_seconds() < MARK_SLACK_MIN * 60:
            continue
        # An evening mark needs Globex open: Sunday to Thursday (it shuts Friday 17:00).
        if at.time() >= time(18, 0) and at.weekday() not in (6, 0, 1, 2, 3):
            continue
        td = session_for(at)
        if td is None:
            continue
        # A weekday-morning mark on a holiday belongs to no session that day.
        if at.time() < time(18, 0) and not is_trading_day(at.date()):
            continue
        # Nothing after the close of a half day.
        if at.date() == td and at.time() >= close_time(td):
            continue
        key = (td.isoformat(), mark_name(hm))
        if key not in done:
            return key
    return None


def close_due(now: datetime, closed: set[str]) -> str | None:
    """The trading day whose close is to be written at `now`, else None. Pure."""
    et = now.astimezone(ET)
    d = et.date()
    if not is_trading_day(d) or d.isoformat() in closed:
        return None
    at = datetime.combine(d, close_time(d), ET)
    return d.isoformat() if 0 <= (et - at).total_seconds() < CLOSE_SLACK_MIN * 60 else None


def read_line(td: str, mark: str, now: datetime, book: str, r: dict[str, Any],
              last: float | None, pct: float | None, usual: float | None) -> dict[str, Any]:
    """One board or tape read as a record line. Pure."""
    return {
        "kind": "read", "td": td, "mark": mark, "at": round(now.timestamp()), "book": book,
        "weights": r.get("session_key"), "score": r.get("score"), "grade": r.get("grade"),
        "bias": r.get("bias"), "coverage": r.get("coverage"), "conflict": r.get("conflict"),
        "backers": r.get("backers"), "last": last, "pct": None if pct is None else round(pct, 3),
        "usual": None if usual is None else round(usual, 3),
        "families": {f["key"]: [f.get("weight"), f.get("score"), f.get("points")]
                     for f in r.get("families") or [] if isinstance(f, dict)},
        "votes": {v["key"]: [v.get("vote"), v.get("strength"), v.get("live", True) is not False]
                  for v in r.get("votes") or [] if isinstance(v, dict) and v.get("family")},
    }


def close_line(td: str, now: datetime, last: dict[str, float | None]) -> dict[str, Any]:
    return {"kind": "close", "td": td, "at": round(now.timestamp()),
            "last": {k: v for k, v in last.items() if v is not None}}


def done_keys(lines: list[dict[str, Any]]) -> tuple[set[tuple[str, str]], set[str]]:
    """(the (td, mark) pairs read, the days closed) on file. Pure."""
    marks = {(str(e.get("td")), str(e.get("mark"))) for e in lines if e.get("kind") == "read"}
    closes = {str(e.get("td")) for e in lines if e.get("kind") == "close"}
    return marks, closes


def outcomes(lines: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Every read with a close on file, with what followed: `move` (percent, mark to
    close), `in_usual` (that in the book's usual days) and `hit` (whether a lean's
    side was the move's; None without a lean or a move). Pure."""
    closes = {str(e["td"]): e.get("last") or {} for e in lines
              if e.get("kind") == "close" and e.get("td")}
    out: list[dict[str, Any]] = []
    for e in lines:
        if e.get("kind") != "read":
            continue
        end = (closes.get(str(e.get("td"))) or {}).get("ES" if e.get("book") == TAPE
                                                         else str(e.get("book")))
        last = e.get("last")
        if not isinstance(end, (int, float)) or not isinstance(last, (int, float)) or not last:
            continue
        move = (end / last - 1.0) * 100.0
        usual = e.get("usual")
        side = e.get("bias")
        hit = None if side not in ("long", "short") or move == 0 else (
            (move > 0) == (side == "long"))
        out.append({**e, "move": move,
                    "in_usual": move / usual if isinstance(usual, (int, float)) and usual else None,
                    "hit": hit})
    return out


# ---- the file --------------------------------------------------------------------------


def read(path: str = RECORD_FILE) -> list[dict[str, Any]]:
    """Every line on file (a bad line skipped)."""
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
        return []
    return out


def append(objs: list[dict[str, Any]], path: str = RECORD_FILE) -> None:
    """Lines onto the record; a record that cannot be written is skipped."""
    if not objs:
        return
    try:
        os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
        with open(path, "a", encoding="utf-8") as f:
            for obj in objs:
                f.write(json.dumps(obj, separators=(",", ":")) + "\n")
    except OSError:
        pass
