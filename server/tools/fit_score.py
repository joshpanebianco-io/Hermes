"""
Fit the scanner's score to its own record — the calibration the signal log
was kept for.

WHAT IT DOES. Reads cache/scanner_events.jsonl (scanlog.py), keeps the
settled (L) and (E) signals, and reports:

  1. the win rate (+1R before the stop) and the average close-to-signal R
     by score band — does a higher score actually do better;
  2. for every score part the events carry (`parts`, logged from
     2026-10-22), the win rate when the part earned at least half its
     maximum against when it did not — the part's LIFT, which is what a
     weight should be proportional to;
  3. a one-variable logistic fit of +1R on the total, for the slope.

WHAT IT DOES NOT DO. It never rewrites scanscore.py's weights. The record
is read here and the weights are changed by hand, with this output beside
the change — a fit on a few hundred signals from one fortnight is a hint,
not a measurement, and the tool says so when the sample is under the guard.

Run from server/:  python -I tools/fit_score.py [--days 30] [--path FILE]
"""

from __future__ import annotations

import argparse
import json
import math
import os
import sys
from collections import defaultdict
from datetime import date, datetime, timedelta
from typing import Any

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from newsterminal.config import CACHE_DIR
from newsterminal.scanlog import TRADES

#: Below this many settled signals the report says the sample is too small
#: to move a weight on; below MIN_PART per side of a part's split, that part
#: is not reported.
MIN_TOTAL = 300
MIN_PART = 40
BANDS = ((0, 40), (40, 60), (60, 80), (80, 101))


def load(path: str, days: int, today: date) -> list[dict[str, Any]]:
    start = today - timedelta(days=days)
    out: list[dict[str, Any]] = []
    with open(path, encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                e = json.loads(line)
            except ValueError:
                continue
            if e.get("kind") not in TRADES or e.get("retracted"):
                continue
            o = e.get("outcome") or {}
            if not o.get("final") or o.get("r") is None or o.get("hit_1r") is None:
                continue
            try:
                d = date.fromisoformat(str(e.get("day")))
            except ValueError:
                continue
            if start < d <= today:
                out.append(e)
    return out


def win(evs: list[dict[str, Any]]) -> float | None:
    return sum(1 for e in evs if e["outcome"].get("hit_1r")) / len(evs) if evs else None


def avg_close(evs: list[dict[str, Any]]) -> float | None:
    xs = [e["outcome"].get("ret_close_r") for e in evs]
    xs = [x for x in xs if x is not None]
    return sum(xs) / len(xs) if xs else None


def logistic_slope(evs: list[dict[str, Any]], iters: int = 200, lr: float = 0.01) -> tuple[float, float] | None:
    """P(+1R) = σ(a + b · score/100), by gradient ascent. (a, b) or None."""
    pts = [(e["score"] / 100.0, 1.0 if e["outcome"].get("hit_1r") else 0.0)
           for e in evs if isinstance(e.get("score"), (int, float))]
    if len(pts) < MIN_PART:
        return None
    a = b = 0.0
    for _ in range(iters):
        ga = gb = 0.0
        for x, y in pts:
            p = 1.0 / (1.0 + math.exp(-(a + b * x)))
            ga += y - p
            gb += (y - p) * x
        a += lr * ga / len(pts) * 10
        b += lr * gb / len(pts) * 10
    return a, b


def report(evs: list[dict[str, Any]], days: int) -> str:
    lines = [f"Settled (L)/(E) signals over {days} days: {len(evs)}"]
    if len(evs) < MIN_TOTAL:
        lines.append(f"  under the {MIN_TOTAL}-signal guard: read as a hint, change no weight on it")
    lines.append("")
    lines.append("By score band          n   win +1R   avg close R")
    scored = [e for e in evs if isinstance(e.get("score"), (int, float))]
    for lo, hi in BANDS:
        band = [e for e in scored if lo <= e["score"] < hi]
        w, c = win(band), avg_close(band)
        lines.append(f"  {lo:>3}–{hi - 1:<3}            {len(band):>4}   "
                     f"{'—' if w is None else f'{w * 100:5.1f}%'}   "
                     f"{'—' if c is None else f'{c:+.2f}'}")
    lines.append(f"  unscored (backfilled) {len(evs) - len(scored):>4}")
    fit = logistic_slope(scored)
    if fit:
        a, b = fit
        lines.append(f"Logistic P(+1R) = σ({a:+.2f} {b:+.2f}·score/100): "
                     f"{'the score orders the record' if b > 0 else 'the score does not order the record'}")
    lines.append("")
    with_parts = [e for e in scored if isinstance(e.get("parts"), dict)]
    lines.append(f"Per-part lift ({len(with_parts)} signals carry parts):")
    if not with_parts:
        lines.append("  none yet — parts are logged on every signal from 2026-10-22; run again in a week")
        return "\n".join(lines)
    keys: dict[str, list[tuple[float, float, bool]]] = defaultdict(list)
    for e in with_parts:
        for k, v in e["parts"].items():
            if isinstance(v, dict) and isinstance(v.get("pts"), (int, float)):
                keys[k].append((float(v["pts"]), float(v.get("max") or 0), bool(e["outcome"].get("hit_1r"))))
    lines.append("  part        earned≥½   n     win   |  earned<½   n     win   | lift")
    for k, rows in sorted(keys.items()):
        hi = [(p, m, w) for p, m, w in rows if m > 0 and p >= m / 2]
        lo = [(p, m, w) for p, m, w in rows if m > 0 and p < m / 2]
        if len(hi) < MIN_PART or len(lo) < MIN_PART:
            lines.append(f"  {k:<11} too few on one side ({len(hi)} / {len(lo)})")
            continue
        wh = sum(1 for _, _, w in hi if w) / len(hi)
        wl = sum(1 for _, _, w in lo if w) / len(lo)
        lines.append(f"  {k:<11}            {len(hi):>4}  {wh * 100:5.1f}%  |            "
                     f"{len(lo):>4}  {wl * 100:5.1f}%  | {(wh - wl) * 100:+.1f} pts")
    return "\n".join(lines)


def main() -> int:
    # Windows consoles default to a code page without σ; never let the report
    # die on a glyph (the collector makes the same provision).
    for stream in (sys.stdout, sys.stderr):
        if hasattr(stream, "reconfigure"):
            stream.reconfigure(errors="replace")
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("--days", type=int, default=30)
    ap.add_argument("--path", default=os.path.join(CACHE_DIR, "scanner_events.jsonl"))
    args = ap.parse_args()
    try:
        evs = load(args.path, args.days, datetime.now().date())
    except OSError as e:
        print(f"no log: {e}")
        return 1
    print(report(evs, args.days))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
