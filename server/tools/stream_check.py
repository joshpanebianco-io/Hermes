"""
How the live stream has done against the bars, session by session.

The collector keeps the score as it runs (sources/stream.StreamCheck): every
finished five-minute bucket a tracked name has in a download made after it closed
is compared with the same five minutes built from the stream. Agreement is within
five basis points of price. A bucket with no stream trades is missing. No request
is made to produce it, and this reads only cache/stream_check.json.

Run from server/:  python -I tools/stream_check.py
"""

from __future__ import annotations

import json
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from newsterminal.sources.stream import CHECK_FILE


def pct(a: int, b: int) -> str:
    return f"{a / b * 100:5.1f}%" if b else "    —"


def main() -> int:
    try:
        with open(CHECK_FILE, encoding="utf-8") as f:
            days = json.load(f).get("days") or {}
    except (OSError, ValueError):
        print("Nothing recorded yet: the check runs during the US sessions, 04:00-20:00 ET.")
        return 0
    if not days:
        print("Nothing recorded yet: the check runs during the US sessions, 04:00-20:00 ET.")
        return 0
    print(f"{'day':<12}{'session':<9}{'buckets':>8}{'close':>8}{'high':>8}{'low':>8}{'missing':>9}"
          f"{'age p50':>9}{'age p95':>9}{'ticks/min':>11}{'names/min':>11}{'subscribed':>12}")
    for day in sorted(days):
        for ses in ("pre", "rth", "post"):
            s = days[day].get(ses)
            if not s:
                continue
            n, miss = s["compared"], s["missing"]
            print(f"{day:<12}{ses:<9}{n:>8}{pct(s['close_ok'], n):>8}{pct(s['high_ok'], n):>8}"
                  f"{pct(s['low_ok'], n):>8}{pct(miss, n + miss):>9}{s['age_p50'] or 0:>8}s"
                  f"{s['age_p95'] or 0:>8}s{s['peak_ticks_min']:>11}{s['peak_names_min']:>11}"
                  f"{s['subscribed']:>12}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
