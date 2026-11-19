"""
Read the live rotation's record against what followed: counts by side, never percentages.

    .venv\\Scripts\\python.exe -I tools/rotation_record.py
    .venv\\Scripts\\python.exe -I tools/rotation_record.py --since 2026-11-20
    .venv\\Scripts\\python.exe -I tools/rotation_record.py --file cache/rotation.jsonl

The rotation (newsterminal/rotation.py) swaps one of the pool's picks for a better setup off
the Scanner list. Whether that was worth doing is one question: from the swap to the close,
did the name that came in go further its own way (up for a long, down for a short, in its
daily ATRs) than the name that went out went its own? Printed, split by the side of the name
that came in:

  * the swaps, how many each day and each hour (the churn the margin and the two-round
    check are there to hold down);
  * came in ran its way, left ran its way, came in ran further, each "N of M";
  * the median run of each, in daily ATRs;
  * the free slots filled, which have no name out to compare with, apart.

A swap is judged only once its day's outcome line is on file (written after 16:30 ET), and
only where both names have a side and a price at the swap (the first morning's lines, 19 Nov
before 10:30 ET, carry neither and are counted apart). Run from server/.
"""

from __future__ import annotations

import argparse
import os
import statistics
import sys
from collections import Counter
from typing import Any

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from newsterminal import rotation
from newsterminal.config import CACHE_DIR

SIDES = ("long", "short")


def tally(judged: list[dict[str, Any]]) -> dict[str, dict[str, Any]]:
    """{side of the name that came in: counts and runs} over the swaps with both runs. Pure."""
    out: dict[str, dict[str, Any]] = {s: {"of": 0, "in_way": 0, "out_way": 0, "further": 0,
                                          "in_runs": [], "out_runs": []} for s in SIDES}
    for j in judged:
        side = j.get("in_side")
        if j["free"] or side not in out or j["in_run"] is None or j["out_run"] is None:
            continue
        t = out[side]
        t["of"] += 1
        t["in_way"] += int(j["in_run"] > 0)
        t["out_way"] += int(j["out_run"] > 0)
        t["further"] += int(j["in_run"] > j["out_run"])
        t["in_runs"].append(j["in_run"])
        t["out_runs"].append(j["out_run"])
    return out


def free_tally(judged: list[dict[str, Any]]) -> dict[str, list[int]]:
    """{side: [ran its way, of]} for the free slots filled. Pure."""
    out = {s: [0, 0] for s in SIDES}
    for j in judged:
        side = j.get("in_side")
        if not j["free"] or side not in out or j["in_run"] is None:
            continue
        out[side][1] += 1
        out[side][0] += int(j["in_run"] > 0)
    return out


def _med(xs: list[float]) -> str:
    return f"{statistics.median(xs):+.2f}" if xs else "—"


def report(lines: list[dict[str, Any]], since: str | None = None) -> str:
    """The printed record. Pure."""
    if since:
        lines = [e for e in lines if str(e.get("day") or "") >= since]
    moves = [e for e in lines if e.get("kind") != "outcome"]
    judged = rotation.judge(lines)
    days = sorted({str(e.get("day")) for e in moves})
    out = [f"Rotation record: {len(moves)} moves over {len(days)} day(s)"
           + (f", {days[0]} to {days[-1]}" if days else "")]
    if not moves:
        return out[0]
    per_day = Counter(str(e.get("day")) for e in moves)
    out.append("By day:  " + "   ".join(f"{d} {per_day[d]}" for d in days))
    per_hour = Counter(str(e.get("at_et") or "")[:2] for e in moves)
    out.append("By hour (ET):  " + "   ".join(f"{h}:00 {per_hour[h]}" for h in sorted(per_hour)))
    waiting = sum(1 for e in moves if e.get("day") not in {j["day"] for j in judged})
    blind = sum(1 for j in judged if j["in_run"] is None or (not j["free"] and j["out_run"] is None))
    if waiting:
        out.append(f"{waiting} move(s) wait for their day's close")
    if blind:
        out.append(f"{blind} move(s) have no side or price on file for a name, not judged")
    out.append("")
    out.append("Swaps, from the swap to the close, each name its own way (daily ATRs):")
    out.append(f"  {'came in':<9}{'swaps':>6}   {'came in ran its way':<21}"
               f"{'left ran its way':<18}{'came in ran further':<21}{'median in':>10}"
               f"{'median out':>11}")
    t = tally(judged)
    for s in SIDES:
        x = t[s]
        if not x["of"]:
            out.append(f"  {s:<9}{0:>6}   —")
            continue
        out.append(f"  {s:<9}{x['of']:>6}   {x['in_way']} of {x['of']:<14}"
                   f"{x['out_way']} of {x['of']:<11}{x['further']} of {x['of']:<14}"
                   f"{_med(x['in_runs']):>10}{_med(x['out_runs']):>11}")
    f = free_tally(judged)
    if any(v[1] for v in f.values()):
        out.append("")
        out.append("Free slots filled, came in ran its way:  "
                   + "   ".join(f"{s} {f[s][0]} of {f[s][1]}" if f[s][1] else f"{s} —"
                              for s in SIDES))
    return "\n".join(out)


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("--file", default=os.path.join(CACHE_DIR, rotation.LOG_NAME))
    ap.add_argument("--since", default=None, help="the first day to read, YYYY-MM-DD")
    a = ap.parse_args()
    print(report(rotation.read_lines(a.file), a.since))


if __name__ == "__main__":
    main()
