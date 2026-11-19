"""
THE PRE-MARKET RECORD: what the list said at 09:25, and whether its names then held their
break and trended.

The owner, 2026-11-18: "the break and retest is our entry but the purpose of the scoring
is to show potential strong stocks where the break and retest will hold and continue
trending (both bearish or bullish) with momentum" → "yes do what you recommend".

WHAT THE PRE-MARKET SCORE MEASURES TODAY, AND WHY THAT IS NOT ENOUGH. Before the bell the
list ranks how in play a name is (sources/pool.in_play: the gap in daily ATRs and the
pre-market's volume, a report or story, a level through, a Day 2/3). The quant audit of
2026-11-13 found the gap's size and volume predict how BIG a day is, not which way, and a
big day is not a trend: a name can range three ATRs and chop both ways. The record check
of 2026-11-18 found the pre-market record could not answer the question at all: the marks
kept neither the gap's sign nor the story, the outcome had no open, and it was written
only while the app ran between 20:00 and 04:00 ET.

SO, ONE LINE AT 09:25 AND ONE AFTER THE BELL, in cache/premarket_record.jsonl:
  "list"     the pre-market list as it stood (collector._today_log, the phase's end): each
             name's in-play score and rank, its signed gap, and four figures that are
             SHOWN AND LOGGED, NEVER SCORED, until the record says which earn points:
               own      the gap less SPY's, both in their own daily ATRs (the app's RS);
                        the sector fund's pre-market % beside it, for the review
               rvol     the pre-market's volume against the name's own usual pre-market
                        (universe._ext_rvol; `rvol_est` when fewer than five mornings kept)
               catalyst the model's read of the name's story: how big, which way (newsread)
               hold     where the last trade sits in the pre-market range, toward the gap:
                        1 at the pre-market high of a gap up (or low of a gap down)
  "outcome"  each listed name's day, replayed from its bars read after the bell, whenever
             the app next runs (the owner stops it mid-session, 2026-11-18): the first (L)
             retest by the scanner's own replay (scan.technicals, the signal log's
             settle), its result by the signal log's own rule (scanlog.compute_outcome:
             +1R before the stop, +2R, R held at the close with the stop kept), and the
             day as a trend: where it closed in its range on the retest's side.

tools/fit_score.py reads it (`premarket_lines`), by side, with every day counting the same.
Pure, but for nothing: the collector reads the bars and writes the lines.
"""

from __future__ import annotations

import json
import os
from collections.abc import Iterable
from datetime import date, datetime
from typing import Any

from . import scan, scanlog
from .config import CACHE_DIR

RECORD_NAME = "premarket_record.jsonl"
RECORD_FILE = os.path.join(CACHE_DIR, RECORD_NAME)
#: Names a list line keeps: the ranked list, not the tracked names under it.
LIST_MAX = 40
#: A finished day is read this long after its bell (the signal log's settle waits the same).
AFTER_BELL_SEC = 15 * 60
#: How far back a day without its outcome is still worked: the scanner's 5-minute
#: download reaches twelve sessions (sources/scanner.BARS_RANGE).
OUTCOME_DAYS = 8
#: A trend day: the close in this share of the day's range on the retest's side.
TREND_CLOSE = 0.75
#: Where `hold` reads as holding, and as fading.
HOLD_HIGH = 0.75
HOLD_LOW = 0.40


def _num(v: Any) -> float | None:
    return float(v) if isinstance(v, (int, float)) and not isinstance(v, bool) else None


# ---- the four figures ------------------------------------------------------------


def hold_of(last: float | None, pmh: float | None, pml: float | None,
            up: bool | None) -> float | None:
    """Where `last` sits in the pre-market range toward the gap: 1 at the pre-market high
    of a gap up (the low of a gap down), 0 at the other end; None without a range or a
    direction. Pure."""
    if last is None or pmh is None or pml is None or up is None or pmh <= pml:
        return None
    x = (last - pml) / (pmh - pml) if up else (pmh - last) / (pmh - pml)
    return round(max(0.0, min(1.0, x)), 2)


def hold_word(hold: float | None, up: bool | None) -> str | None:
    """The hold in words, for the slide-out. Pure."""
    if hold is None or up is None:
        return None
    end = "high" if up else "low"
    if hold >= HOLD_HIGH:
        return f"Holding near its pre-market {end} ({round((1 - hold) * 100)}% off it)"
    if hold >= HOLD_LOW:
        return f"Pulled back from its pre-market {end} ({round((1 - hold) * 100)}% off it)"
    return f"Fading: {round((1 - hold) * 100)}% of the pre-market range given back"


def pre_context(t: dict[str, Any], *, spy_gap: float | None, sector_pct: float | None,
                rvol: float | None, rvol_est: bool, read: dict[str, Any] | None
                ) -> dict[str, Any]:
    """One pre-market list row's four figures (module docstring). `t` is the Today row
    (today.rank_pre / rest_of_list): its signed move `chg`, `gap_atr` (the size), levels
    and story; `spy_gap` SPY's pre-market move in its daily ATRs, signed; `read` the
    model's read of the row's story (newsread.ReadStore.for_story). Pure."""
    chg = _num(t.get("chg"))
    size = _num(t.get("gap_atr"))
    up = None if chg is None or chg == 0 else chg > 0
    gap = (size if up else -size) if size is not None and up is not None else None
    own = round(gap - spy_gap, 2) if gap is not None and spy_gap is not None else None
    lv = t.get("levels") or {}
    hold = hold_of(_num(t.get("last")), _num(lv.get("pmh")), _num(lv.get("pml")), up)
    story = t.get("story") if isinstance(t.get("story"), dict) else {}
    rd = read if isinstance(read, dict) else {}
    return {
        "gap": round(gap, 2) if gap is not None else None,
        "spy": round(spy_gap, 2) if spy_gap is not None else None,
        "own": own,
        "sector_pct": round(sector_pct, 2) if sector_pct is not None else None,
        "rvol": round(rvol, 2) if rvol is not None else None, "rvol_est": bool(rvol_est),
        "catalyst": {"tag": story.get("tag"), "major": bool(story.get("major")),
                     "report": t.get("report"), "size": rd.get("size"),
                     "direction": rd.get("direction"), "line": rd.get("line") or None,
                     "text": rd.get("text")},
        "hold": hold, "hold_word": hold_word(hold, up),
    }


# ---- the 09:25 line ----------------------------------------------------------------


def list_line(day: str, at_et: str, rows: Iterable[dict[str, Any]]) -> dict[str, Any]:
    """The pre-market list as a record line: each ranked name (not the tracked names
    under the ranking) with its score, signed gap and four figures. Pure."""
    out = []
    for t in rows:
        if t.get("listed"):
            continue
        ctx = t.get("pre_ctx") or {}
        out.append({"sym": t.get("sym"), "rank": t.get("rank"), "score": t.get("score"),
                    "lean": t.get("lean"), "chg": t.get("chg"), "gap_atr": t.get("gap_atr"),
                    "vol_pct": t.get("vol_pct"), "stage": t.get("stage"),
                    "tracked": t.get("tracked"),
                    **{k: ctx.get(k) for k in ("gap", "spy", "own", "sector_pct", "rvol",
                                               "rvol_est", "catalyst", "hold")}})
        if len(out) >= LIST_MAX:
            break
    return {"kind": "list", "day": day, "at_et": at_et, "rows": out}


# ---- after the bell ------------------------------------------------------------------


def _bell(day: date) -> int:
    m = scan.rth_end(day)
    return int(datetime(day.year, day.month, day.day, m // 60, m % 60, tzinfo=scan.ET).timestamp())


def _open(day: date) -> int:
    return int(datetime(day.year, day.month, day.day, scan.RTH_START // 60,
                        scan.RTH_START % 60, tzinfo=scan.ET).timestamp())


def day_result(sym: str, day: date, signals: list[dict[str, Any]], bars5: list[scan.Bar],
               asof: float, daily: list[scan.DayBar], now_ts: float) -> dict[str, Any]:
    """One listed name's day: the first (L) retest of the scanner's replay and its result
    by the signal log's own rule, and the day as a trend on that side. Pure.

    `signals` are the day's replayed signals (sources/scanner.day_signals), `bars5` the
    name's 5-minute bars read at `asof` (after the bell), `daily` its daily bars."""
    lo_t, hi_t = _open(day), _bell(day)
    rth = [b for b in bars5 if lo_t <= b.t < hi_t]
    atr = scan.daily_atr([d for d in daily if d.day < day])
    out: dict[str, Any] = {"bars": len(rth)}
    if rth:
        o, c = rth[0].open, rth[-1].close
        h, low = max(b.high for b in rth), min(b.low for b in rth)
        out.update({"open": round(o, 4), "high": round(h, 4), "low": round(low, 4),
                    "close": round(c, 4)})
        if atr:
            out["range_atr"] = round((h - low) / atr, 2)
    retests = sorted((s for s in signals if s.get("kind") == "L" and s.get("t") is not None),
                     key=lambda s: int(s["t"]))
    first = retests[0] if retests else None
    if first is None:
        out["retest"] = None
        return out
    ev = scanlog.signal_events(sym, [first], None, day.isoformat(), now_ts)[0]
    oc = scanlog.compute_outcome(ev, bars5, now_ts, asof=asof)
    side = str(first.get("side"))
    out["retest"] = {"side": side, "at_et": ev.get("at_et"), "level": first.get("level"),
                     "price": ev.get("price"), "stop": ev.get("stop"),
                     "hit_1r": oc.get("hit_1r"), "hit_2r": oc.get("hit_2r"),
                     "stopped": oc.get("stopped"), "held_r": scanlog.held_r(oc),
                     "mfe_r": oc.get("mfe_r"), "final": oc.get("final"),
                     "retests": len(retests)}
    if rth and out.get("high") is not None and out["high"] > out["low"]:
        h, low, c = out["high"], out["low"], out["close"]
        pos = (c - low) / (h - low) if side == "long" else (h - c) / (h - low)
        out["close_pos"] = round(pos, 2)
        out["trend_day"] = pos >= TREND_CLOSE
    return out


def outcome_line(day: str, results: dict[str, dict[str, Any]], at: datetime) -> dict[str, Any]:
    return {"kind": "outcome", "day": day, "at_utc": at.isoformat(), "rows": results}


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


def owed(lines: list[dict[str, Any]], today: date, now_ts: float) -> dict[str, list[str]]:
    """{day: names} listed on a finished day (its bell AFTER_BELL_SEC gone, OUTCOME_DAYS
    at most back) with no outcome line yet. The day's last list line is the one that
    counts. Pure."""
    lists: dict[str, list[str]] = {}
    done = {e.get("day") for e in lines if e.get("kind") == "outcome"}
    for e in lines:
        if e.get("kind") == "list" and isinstance(e.get("day"), str):
            lists[e["day"]] = [str(r.get("sym")) for r in e.get("rows") or [] if r.get("sym")]
    out: dict[str, list[str]] = {}
    for d, syms in lists.items():
        try:
            dd = date.fromisoformat(d)
        except ValueError:
            continue
        if d in done or (today - dd).days > OUTCOME_DAYS or not syms:
            continue
        if now_ts >= _bell(dd) + AFTER_BELL_SEC:
            out[d] = syms
    return out


def append(obj: dict[str, Any], path: str = RECORD_FILE) -> None:
    """One line onto the record; a record that cannot be written is skipped."""
    try:
        os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
        with open(path, "a", encoding="utf-8") as f:
            f.write(json.dumps(obj, separators=(",", ":")) + "\n")
    except OSError:
        pass
