"""
Print the session clock at the instants where it has been wrong before.

The owner checks clock logic by reading the actual output side by side
(2026-09-16), not a description of the rule — so this prints `session_state`
at the DST-mismatch week, both passes of the November fall-back hour, the
Sunday Globex reopen, Thanksgiving and the half day after it.

    .venv\\Scripts\\python.exe tools\\clock_probe.py
"""

from __future__ import annotations

import sys
from datetime import datetime
from zoneinfo import ZoneInfo

sys.path.insert(0, __file__.rsplit("tools", 1)[0])

from newsterminal.scan import clock_at
from newsterminal.sessions import session_state

ET = ZoneInfo("America/New_York")

INSTANTS: list[tuple[str, datetime]] = [
    ("Mon 10-19 02:55 (normal)", datetime(2026, 10, 19, 2, 55, tzinfo=ET)),
    ("Mon 10-26 02:55 (UK on GMT, US on EDT)", datetime(2026, 10, 26, 2, 55, tzinfo=ET)),
    ("Mon 10-26 11:45", datetime(2026, 10, 26, 11, 45, tzinfo=ET)),
    ("Sun 11-01 01:30 EDT (1st pass)", datetime(2026, 11, 1, 1, 30, tzinfo=ET)),
    ("Sun 11-01 01:30 EST (2nd pass)", datetime(2026, 11, 1, 1, 30, fold=1, tzinfo=ET)),
    ("Sun 11-01 17:59", datetime(2026, 11, 1, 17, 59, tzinfo=ET)),
    ("Sun 11-01 18:00 (Globex reopen)", datetime(2026, 11, 1, 18, 0, tzinfo=ET)),
    ("Thu 11-26 10:00 (Thanksgiving)", datetime(2026, 11, 26, 10, 0, tzinfo=ET)),
    ("Fri 11-27 12:59 (half day)", datetime(2026, 11, 27, 12, 59, tzinfo=ET)),
    ("Fri 11-27 13:30 (NYSE shut 13:00)", datetime(2026, 11, 27, 13, 30, tzinfo=ET)),
    ("Fri 11-27 17:00", datetime(2026, 11, 27, 17, 0, tzinfo=ET)),
]


def row(st: dict, key: str) -> str:
    r = next(x for x in st["sessions"] if x["key"] == key)
    state = "OPEN" if r["open"] else "shut"
    return f"{state}, {r['next']} {r['next_min']}m"


def marker(st: dict, label: str) -> str:
    m = next((x for x in st["markers"] if x["label"] == label), None)
    return f"in {m['in_min']}m ({m['et']})" if m else "—"


def main() -> None:
    print(f"{'instant (ET)':<40}{'phase':<20}{'London row':<20}{'NY row':<20}"
          f"{'London open marker':<22}{'next marker':<34}{'scanner':<20}")
    for name, t in INSTANTS:
        st = session_state(t.astimezone(ZoneInfo('UTC')))
        nxt = st["markers"][0]
        c = clock_at(t)
        print(f"{name:<40}{st['phase']['label']:<20}{row(st, 'london'):<20}{row(st, 'newyork'):<20}"
              f"{marker(st, 'London open'):<22}"
              f"{nxt['label'] + ' in ' + str(nxt['in_min']) + 'm (' + nxt['et'] + ')':<34}"
              f"{c.session} -> {c.trading_day:%a %m-%d}")


if __name__ == "__main__":
    main()
