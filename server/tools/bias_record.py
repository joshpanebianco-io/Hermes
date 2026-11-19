"""
Read the bias record against what followed: counts by side, never percentages.

    .venv\\Scripts\\python.exe -I tools/bias_record.py                 # the live record
    .venv\\Scripts\\python.exe -I tools/bias_record.py --file cache/bias_backfill.jsonl
    .venv\\Scripts\\python.exe -I tools/bias_record.py --book NQ --since 2026-11-20

For every read with its day's close on file (newsterminal/bias_record.py), a lean's side
against the move from the mark to New York's close. Printed, each split long and short:

  * the score's leans, by book and mark, and by grade;
  * the same reads judged on the book's own move so far (its day change at the mark):
    the bias earns its place only where it beats that;
  * the same families weighed equally (every family the session weighs, one share each):
    the weights earn theirs only where they beat that;
  * each family on its own: its side at the mark against the move.

A read with no lean (under 10 either way) is counted apart. Run from server/.
"""

from __future__ import annotations

import argparse
import os
import sys
from collections import defaultdict
from collections.abc import Callable
from typing import Any

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from newsterminal import bias_record

LEAN_AT = 10


def _side(x: float | None, at: float = LEAN_AT) -> str | None:
    if not isinstance(x, (int, float)):
        return None
    return "long" if x >= at else "short" if x <= -at else None


def _tally(rows: list[dict[str, Any]], side_of: Callable[[dict[str, Any]], str | None]
           ) -> dict[str, list[int]]:
    """{side: [right, of]} for the rows whose `side_of` is a side and that moved."""
    out: dict[str, list[int]] = {"long": [0, 0], "short": [0, 0]}
    for r in rows:
        s = side_of(r)
        if s not in out or not r["move"]:
            continue
        out[s][1] += 1
        out[s][0] += int((r["move"] > 0) == (s == "long"))
    return out


def _say(t: dict[str, list[int]]) -> str:
    return "   ".join(f"{s} {t[s][0]} of {t[s][1]}" if t[s][1] else f"{s} —" for s in t)


def _equal(r: dict[str, Any]) -> float | None:
    """The score with every weighed family given one share: the mean of the live
    families' scores over every family the session weighs (a shut one is no lean)."""
    fams = [v for v in (r.get("families") or {}).values()
            if isinstance(v, list) and len(v) >= 2 and (v[0] or 0) > 0]
    if not fams:
        return None
    return sum((v[1] or 0) for v in fams) / len(fams)


def report(lines: list[dict[str, Any]], book: str | None, since: str | None) -> str:
    rows = [r for r in bias_record.outcomes(lines)
            if (book is None or r.get("book") == book) and (since is None or r["td"] >= since)]
    if not rows:
        return "No read with its close on file yet."
    days = sorted({r["td"] for r in rows})
    out = [f"Bias record: {len(rows)} reads on {len(days)} sessions, {days[0]} to {days[-1]}.",
           "Each line: leans whose side was the move's, of leans, split long and short.", ""]
    by_book: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for r in rows:
        by_book[str(r["book"])].append(r)
    for b in sorted(by_book):
        rs = by_book[b]
        out.append(f"== {b} ({len(rs)} reads)")
        out.append(f"  the score           {_say(_tally(rs, lambda r: r.get('bias')))}")
        out.append(f"  its own move so far {_say(_tally(rs, lambda r: _side(r.get('pct'), 0.0001)))}")
        out.append(f"  families equal      {_say(_tally(rs, lambda r: _side(_equal(r))))}")
        flat = sum(1 for r in rs if not r.get("bias"))
        out.append(f"  no lean             {flat}")
        for grade in ("strong", "moderate", "weak"):
            g = [r for r in rs if r.get("grade") == grade]
            if g:
                out.append(f"  grade {grade:<13} {_say(_tally(g, lambda r: r.get('bias')))}")
        marks = sorted({str(r.get("mark")) for r in rs})
        for m in marks:
            mr = [r for r in rs if r.get("mark") == m]
            out.append(f"  at {m} ({mr[0].get('weights')!s:<7}) "
                       f"{_say(_tally(mr, lambda r: r.get('bias')))}")
        fams = sorted({k for r in rs for k in (r.get("families") or {})})
        for f in fams:
            t = _tally(rs, lambda r, f=f: _side(((r.get("families") or {}).get(f) or
                                                 [None, None])[1], 1))
            if t["long"][1] or t["short"][1]:
                out.append(f"  family {f:<14}{_say(t)}")
        big = [r["in_usual"] for r in rs if r.get("bias") and r.get("in_usual") is not None]
        if big:
            with_side = [x if r.get("bias") == "long" else -x
                         for r, x in zip([r for r in rs if r.get("bias")
                                          and r.get("in_usual") is not None], big, strict=True)]
            out.append(f"  how far it went the lean's way, in usual days: "
                       f"{sum(with_side) / len(with_side):+.2f} on average over {len(with_side)}")
        out.append("")
    return "\n".join(out)


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[1] if __doc__ else None)
    ap.add_argument("--file", default=bias_record.RECORD_FILE)
    ap.add_argument("--book", default=None)
    ap.add_argument("--since", default=None)
    a = ap.parse_args()
    print(report(bias_record.read(a.file), a.book, a.since))


if __name__ == "__main__":
    main()
