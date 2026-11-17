"""
Fit the scanner's score to its own record — the calibration the signal log
was kept for.

WHAT IT DOES. Reads cache/scanner_events.jsonl (scanlog.py), keeps the
settled (L) and (E) signals, and reports:

  1. the win rate (+1R before the stop) and what the signals made with the
     stop kept, by score band — does a higher score actually do better;
  2. the top third of each day's signals by score against the bottom third,
     on the whole record and on each half of its days: the test the rank has
     to pass, since the rank is what the list is read by. A reading that holds
     on only one half is that fortnight's market, not a weight;
  3. every signal, the top five and the top third of each day with EVERY DAY
     COUNTING THE SAME, because a pooled figure leans on the busiest sessions.
     Read this before the pooled line;
  4. each part INSIDE EACH DAY, the signals earning at least half of it against
     the rest of that day, so a big day cannot pass for a good input;
  5. for every score part the events carry (`parts`, logged from
     2026-10-22), the win rate when the part earned at least half its
     maximum against when it did not — the part's LIFT, which is what a
     weight should be proportional to;
  6. every penalty, on the signals it fired on against the rest. The tape
     penalty was taken out on this reading (2026-11-05);
  7. the same top and bottom thirds for the list as it stood before the bell
     (cache/scanner_preopen.jsonl, one line a day from 2026-11-05);
  8. a one-variable logistic fit of +1R on the total, for the slope;
  9. (from 2026-11-13, the quant audit's phase 3) the news inside each day: signals
     whose catalyst was with the side, against it and none, and by where the direction
     came from (the name's move, the event's words, the tape, a report); signals the
     RVOL gate held out of the top ten against the rest;
 10. the pool's own record (cache/pool_marks.jsonl): at each mark, the top ten of the
     rank against the rest of its top fifty by the day each then had (range and move
     in daily ATRs), and promoted names against the rest.

AND, from 2026-11-14, the entry gate: signals with an entry to take against those
without, then section 4 again on the first group alone (`entry_lines`). A part is worth
its weight for what it tells apart among trades that can be taken, so that table is
the one to move a weight on.

THE TEST IS TRENDING, AND IT IS PRINTED FIRST (owner, 2026-11-14: "the whole purpose of
the scanner is to identify stocks that are more likely to be strong trenders"). A list
that picks trades which reach +1R and then stall is not doing its job, and on that day's
read it was: the top five (L) retests a day held +0.13 R against +0.11 for the average
one. So `trend_lines` leads the report: +2R reached and R held, every day counting the
same, for every signal, the top five and the top and bottom thirds of each day's list,
the gap between the thirds, and that gap on each half of the days. Move a weight on
that table and the valid-entry one, not on the +1R lines under them. The news table
gained the groups the same day's changes need: a story that reads against the side
(paid since then), one the tape overruled, a name with a major story the session
before (`prior`, logged and unscored), and how big the model read the story to be
(`size`, the same).

READ ONLY WHAT IS ON THE CURRENT WEIGHTS. `--since 2026-11-16` reads the signals from
the first session on the weights of 2026-11-14 (the entry gate, the news paid either
way, RS at 10); `--since 2026-11-13` adds the one session on the quant audit's reweight
before them. Every earlier score is on older rules. Run it weekly and keep a change
only if it holds on both halves.

TWO MEASURES, BOTH WITH THE STOP KEPT. "At +1R" is a trade that takes +1R, is
stopped at -1R, or is out at the close. "Held" is a trade held to the close,
stopped at -1R, with the gain capped (scanlog.held_r). The plain close-to-signal
R ignores the stop and one tiny stop can carry a whole group, so it is not used.

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
from collections.abc import Callable
from datetime import date, datetime, timedelta
from typing import Any

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from newsterminal.config import CACHE_DIR
from newsterminal.scanlog import PREOPEN_NAME, TRADES, held_r
from newsterminal.sources.pool import MARKS_NAME

#: Below this many settled signals the report says the sample is too small
#: to move a weight on; below MIN_PART per side of a part's split, that part
#: is not reported.
MIN_TOTAL = 300
MIN_PART = 40
MIN_PENALTY = 15
#: Inside a day, both sides of a split need this many signals to be compared.
MIN_SAME_DAY = 3
BANDS = ((0, 40), (40, 60), (60, 80), (80, 101))


def load(path: str, days: int, today: date, since: date | None = None) -> list[dict[str, Any]]:
    start = (since - timedelta(days=1)) if since else today - timedelta(days=days)
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


def at_1r(e: dict[str, Any]) -> float:
    """A +1R target with the stop kept: +1 if it came first, -1 if the stop did, else
    the close within those."""
    o = e["outcome"]
    if o.get("hit_1r"):
        return 1.0
    if o.get("stopped"):
        return -1.0
    c = o.get("ret_close_r")
    return max(-1.0, min(1.0, float(c))) if isinstance(c, int | float) else 0.0


def held(e: dict[str, Any]) -> float:
    """Held to the close with the stop kept (scanlog.held_r); no close counts as flat."""
    return held_r(e["outcome"]) or 0.0


def win_2r(evs: list[dict[str, Any]]) -> float | None:
    return sum(1 for e in evs if e["outcome"].get("hit_2r")) / len(evs) if evs else None


def mean(xs: list[float]) -> float | None:
    return sum(xs) / len(xs) if xs else None


def thirds(evs: list[dict[str, Any]],
           key: Callable[[dict[str, Any]], float]) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    """Each day's top and bottom third by `key`, pooled. Within a day, because a score
    orders one day's list, and a strong day's scores should not stand in for its wins."""
    top: list[dict[str, Any]] = []
    bottom: list[dict[str, Any]] = []
    for d in sorted({e["day"] for e in evs}):
        day = sorted((e for e in evs if e["day"] == d), key=key, reverse=True)
        n = len(day) // 3
        if n >= 2:
            top += day[:n]
            bottom += day[-n:]
    return top, bottom


def halves(evs: list[dict[str, Any]]) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    """The record split at its middle day."""
    days = sorted({e["day"] for e in evs})
    if not days:
        return [], []
    mid = days[len(days) // 2]
    return [e for e in evs if e["day"] < mid], [e for e in evs if e["day"] >= mid]


def _pct(x: float | None) -> str:
    return "—" if x is None else f"{x * 100:5.1f}%"


def _signed(x: float | None) -> str:
    return "—" if x is None else f"{x:+.2f}"


def gap_line(label: str, top: list[dict[str, Any]], bottom: list[dict[str, Any]]) -> str:
    """One line of top against bottom: the win rates and the gaps in R."""
    if not top or not bottom:
        return f"  {label:<6} too few signals a day to split"
    g1 = (mean([at_1r(e) for e in top]) or 0.0) - (mean([at_1r(e) for e in bottom]) or 0.0)
    gh = (mean([held(e) for e in top]) or 0.0) - (mean([held(e) for e in bottom]) or 0.0)
    return (f"  {label:<6} {len(top):>4} / {len(bottom):<4}  {_pct(win(top))} / {_pct(win(bottom))}"
            f"   gap at +1R {g1:+.2f} R   gap held {gh:+.2f} R")


def rank_score(e: dict[str, Any]) -> float:
    """What the list was ranked on: the uncapped sum where the log has it (2026-11-13),
    else the capped total."""
    raw = (e.get("ctx") or {}).get("raw")
    return float(raw) if isinstance(raw, int | float) else float(e["score"])


def rank_lines(scored: list[dict[str, Any]]) -> list[str]:
    """Does the score separate a day's signals, on the whole and on both halves?"""
    key = rank_score
    early, late = halves(scored)
    return ["Top third of each day's signals by score against the bottom third, pooled, so the busiest days weigh most:",
            "         signals       +1R",
            gap_line("all", *thirds(scored, key)),
            gap_line("early", *thirds(early, key)),
            gap_line("late", *thirds(late, key))]


def by_day(evs: list[dict[str, Any]]) -> dict[str, list[dict[str, Any]]]:
    days: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for e in evs:
        days[e["day"]].append(e)
    return days


def equal_day_lines(scored: list[dict[str, Any]]) -> list[str]:
    """Every signal, then the top of each day's list, with every day counting the same.

    Two of the first ten sessions held 126 of 325 signals, and a top third that read
    53.8% at +1R pooled read 43.6% once each day counted the same (2026-11-05)."""
    lists = [sorted(r, key=lambda e: e["score"], reverse=True) for r in by_day(scored).values()]

    def line(label: str, pick: Callable[[list[dict[str, Any]]], list[dict[str, Any]]]) -> str:
        picked = [r for r in (pick(x) for x in lists) if r]
        w1 = mean([win(r) or 0.0 for r in picked])
        w2 = mean([win_2r(r) or 0.0 for r in picked])
        h = mean([mean([held(e) for e in r]) or 0.0 for r in picked])
        return f"  {label:<13} {_pct(w1)}  {_pct(w2)}  {_signed(h)}"

    return ["With every day counting the same:",
            "                   +1R     +2R    held",
            line("every signal", lambda r: r),
            line("top 5 a day", lambda r: r[:5]),
            line("top third", lambda r: r[:len(r) // 3])]


def trend_lines(scored: list[dict[str, Any]]) -> list[str]:
    """Does the list pick the trades that RUN? The report's first table (module docstring).

    +2R reached and R held with the stop kept, +1R beside them, every day counting the
    same, in the order the list was ranked on (`rank_score`): every signal, the top
    five, and the top and bottom thirds of each day with six signals or more. Then the
    gap between the thirds with the days the top was ahead, and the same gap on each
    half of the days: a gap that holds on one half only is that fortnight's market."""
    days = by_day(scored)
    order = sorted(days)
    lists = {d: sorted(days[d], key=rank_score, reverse=True) for d in order}

    def stats(evs: list[dict[str, Any]]) -> tuple[float, float, float]:
        return (win_2r(evs) or 0.0, mean([held(e) for e in evs]) or 0.0, win(evs) or 0.0)

    def avg(rows: list[tuple[float, float, float]], i: int) -> float:
        return sum(r[i] for r in rows) / len(rows) if rows else 0.0

    def thirds_of(keys: list[str]) -> tuple[list[tuple[float, float, float]],
                                            list[tuple[float, float, float]]]:
        top: list[tuple[float, float, float]] = []
        bottom: list[tuple[float, float, float]] = []
        for d in keys:
            n = len(lists[d]) // 3
            if n >= 2:
                top.append(stats(lists[d][:n]))
                bottom.append(stats(lists[d][-n:]))
        return top, bottom

    def row(label: str, rows: list[tuple[float, float, float]]) -> str:
        if not rows:
            return f"  {label:<13} too few signals a day"
        return f"  {label:<13} {_pct(avg(rows, 0))}  {_signed(avg(rows, 1))}  {_pct(avg(rows, 2))}"

    def gap(keys: list[str]) -> str:
        top, bottom = thirds_of(keys)
        if not top:
            return "too few signals a day to split"
        g2 = (avg(top, 0) - avg(bottom, 0)) * 100
        gh = avg(top, 1) - avg(bottom, 1)
        a2 = sum(1 for t, b in zip(top, bottom, strict=True) if t[0] > b[0])
        ah = sum(1 for t, b in zip(top, bottom, strict=True) if t[1] > b[1])
        # A plain bar: a Windows console without the code page turns a middle dot to "?".
        return (f"+2R {g2:+5.1f} pts, ahead on {a2} of {len(top)} days | "
                f"held {gh:+.2f} R, ahead on {ah} of {len(top)}")

    top, bottom = thirds_of(order)
    half = len(order) // 2
    return ["Trending, what the list is for: +2R reached and R held, every day counting the same:",
            "                    +2R    held     +1R",
            row("every signal", [stats(lists[d]) for d in order]),
            row("top 5 a day", [stats(lists[d][:5]) for d in order]),
            row("top third", top),
            row("bottom third", bottom),
            f"  top third less bottom third: {gap(order)}",
            f"    first half of the days:  {gap(order[:half])}",
            f"    second half of the days: {gap(order[half:])}",
            *side_lines(scored)]


def side_lines(scored: list[dict[str, Any]]) -> list[str]:
    """The same test on each side's own signals: a trend is a trend both ways.

    Owner, 2026-11-14: "when i say trending i mean both bullish and bearish trends". The
    score is mirrored for a short (below its levels, weak against SPY, a falling tape),
    but a mirrored rule need not work as well both ways, and on that day's read it did
    not: among the longs the top third of each day beat the bottom third at +2R by 20
    points, among the shorts by none, and the shorts were carried by a few sessions
    (held +0.60 R pooled, -0.10 R with every day counting the same). So each side is
    printed apart, ranked among its own signals inside each day: read both before a
    weight is moved, and do not let the longs' gap pass for the list's."""
    lines = ["  By side, each ranked among its own signals inside each day:"]
    for side in ("long", "short"):
        evs = [e for e in scored if e.get("side") == side]
        if not evs:
            lines.append(f"    {side + 's':<7} none")
            continue
        days = by_day(evs)
        order = sorted(days)
        lists = [sorted(days[d], key=rank_score, reverse=True) for d in order]

        def avg(rows: list[list[dict[str, Any]]], f: Callable[[list[dict[str, Any]]], float | None]) -> float:
            vals = [f(r) or 0.0 for r in rows if r]
            return sum(vals) / len(vals) if vals else 0.0

        def held_of(r: list[dict[str, Any]]) -> float | None:
            return mean([held(e) for e in r])

        split = [(x[:len(x) // 3], x[-(len(x) // 3):]) for x in lists if len(x) // 3 >= 2]
        tops, bots = [t for t, _ in split], [b for _, b in split]
        head = (f"    {side + 's':<7} {len(evs):>4} signals, {len(order)} days | every signal +2R "
                f"{_pct(avg(lists, win_2r))} held {_signed(avg(lists, held_of))} | top 5 +2R "
                f"{_pct(avg([x[:5] for x in lists], win_2r))} held "
                f"{_signed(avg([x[:5] for x in lists], held_of))}")
        if not split:
            lines.append(head + " | too few a day to split")
            continue
        g2 = (avg(tops, win_2r) - avg(bots, win_2r)) * 100
        gh = avg(tops, held_of) - avg(bots, held_of)
        a2 = sum(1 for t, b in split if (win_2r(t) or 0.0) > (win_2r(b) or 0.0))
        ah = sum(1 for t, b in split if (held_of(t) or 0.0) > (held_of(b) or 0.0))
        lines.append(head + f" | thirds' gap +2R {g2:+5.1f} pts ({a2} of {len(split)} days), "
                            f"held {gh:+.2f} R ({ah} of {len(split)})")
    return lines


def _earned(e: dict[str, Any], key: str) -> bool:
    """Whether a signal earned at least half of a part."""
    v = e["parts"].get(key) or {}
    return (v.get("max") or 0) > 0 and (v.get("pts") or 0) >= v["max"] / 2


def same_day_lines(with_parts: list[dict[str, Any]]) -> list[str]:
    """Each part inside each day, so a big day cannot pass for a good input. Strong RS
    looked well ahead pooled and reached +2R more often on 3 days of 8 (2026-11-05)."""
    keys = sorted({k for e in with_parts for k, v in e["parts"].items()
                   if isinstance(v, dict) and (v.get("max") or 0) > 0})
    days = by_day(with_parts)
    lines = ["Inside each day, signals earning at least half of a part against the rest of that day:",
             "  part         days ahead: +1R   +2R   held  |  average gap: +1R      +2R      held"]
    for k in keys:
        g1: list[float] = []
        g2: list[float] = []
        gh: list[float] = []
        for rows in days.values():
            on = [e for e in rows if _earned(e, k)]
            off = [e for e in rows if not _earned(e, k)]
            if len(on) < MIN_SAME_DAY or len(off) < MIN_SAME_DAY:
                continue
            g1.append((win(on) or 0.0) - (win(off) or 0.0))
            g2.append((win_2r(on) or 0.0) - (win_2r(off) or 0.0))
            gh.append((mean([held(e) for e in on]) or 0.0) - (mean([held(e) for e in off]) or 0.0))
        n = len(g1)
        if not n:
            lines.append(f"  {k:<11}  no day with {MIN_SAME_DAY} or more on each side")
            continue
        ahead = [f"{sum(1 for x in g if x > 0)}/{n}" for g in (g1, g2, gh)]
        lines.append(f"  {k:<11}              {ahead[0]:<5} {ahead[1]:<5} {ahead[2]:<5} |"
                     f"               {(mean(g1) or 0.0) * 100:+5.1f} pts {(mean(g2) or 0.0) * 100:+5.1f} pts {mean(gh) or 0.0:+.2f} R")
    return lines


def at_entry(e: dict[str, Any]) -> bool:
    """Whether a signal had an entry to take: its `location` part earned anything. The
    part is all or nothing from 2026-11-14 (scanscore.W_ENTRY); before that a graded
    part above zero was the same setups. A signal logged with no such part counts."""
    v = e["parts"].get("location")
    return not isinstance(v, dict) or (v.get("pts") or 0) > 0


def entry_lines(with_parts: list[dict[str, Any]]) -> list[str]:
    """The entry gate, then every part again on the signals that passed it.

    The whole record flatters a part that is high where the entry is bad and hides one
    that only matters once there is a trade to take: read on every signal the catalyst
    showed nothing, and on the valid (L) entries it was ahead on 5 days of 7 (2026-11-14).
    These are the lines to read before a weight is moved."""
    valid = [e for e in with_parts if at_entry(e)]
    rest = [e for e in with_parts if not at_entry(e)]

    def row(label: str, evs: list[dict[str, Any]]) -> str:
        return (f"  {label:<15} {len(evs):>4}  {_pct(win(evs))}  {_pct(win_2r(evs))}  "
                f"{_signed(mean([held(e) for e in evs]))}")

    lines = ["The entry gate (a setup with an entry to take against one without):",
             "                     n     +1R     +2R    held",
             row("valid entry", valid), row("no entry", rest), ""]
    table = same_day_lines(valid)
    table[0] = ("Only signals at a valid entry: inside each day, signals earning at least half "
                "of a part against the rest of that day:")
    return lines + table


def penalty_lines(with_parts: list[dict[str, Any]]) -> list[str]:
    """Each penalty on the signals it fired on against the rest. A penalty has no
    maximum, so the lift table cannot read it."""
    keys = {k for e in with_parts for k, v in e["parts"].items()
            if isinstance(v, dict) and isinstance(v.get("pts"), int | float) and v["pts"] < 0}
    lines = ["Penalties, the signals each fired on against the rest:"]
    for k in sorted(keys):
        on = [e for e in with_parts if ((e["parts"].get(k) or {}).get("pts") or 0) < 0]
        off = [e for e in with_parts if ((e["parts"].get(k) or {}).get("pts") or 0) >= 0]
        if len(on) < MIN_PENALTY:
            lines.append(f"  {k:<11} fired on {len(on)}, too few to read")
            continue
        lines.append(f"  {k:<11} {len(on):>4}  {_pct(win(on))}  at +1R {_signed(mean([at_1r(e) for e in on]))}"
                     f"  |  rest {len(off):>4}  {_pct(win(off))}  at +1R {_signed(mean([at_1r(e) for e in off]))}")
    return lines


def _split_lines(title: str, evs: list[dict[str, Any]],
                 groups: list[tuple[str, Callable[[dict[str, Any]], bool]]]) -> list[str]:
    """Each group inside each day against the rest of that day, as same_day_lines does
    for a part: days ahead and the average gap."""
    days = by_day(evs)
    lines = [title, "  group                n   days ahead: +1R   +2R   held  |  average gap: +1R      held"]
    for label, f in groups:
        g1: list[float] = []
        gh: list[float] = []
        g2: list[float] = []
        n = 0
        for rows in days.values():
            on = [e for e in rows if f(e)]
            off = [e for e in rows if not f(e)]
            n += len(on)
            if len(on) < MIN_SAME_DAY or len(off) < MIN_SAME_DAY:
                continue
            g1.append((win(on) or 0.0) - (win(off) or 0.0))
            g2.append((win_2r(on) or 0.0) - (win_2r(off) or 0.0))
            gh.append((mean([held(e) for e in on]) or 0.0) - (mean([held(e) for e in off]) or 0.0))
        k = len(g1)
        if not k:
            lines.append(f"  {label:<18} {n:>4}   no day with {MIN_SAME_DAY} or more on each side")
            continue
        ahead = [f"{sum(1 for x in g if x > 0)}/{k}" for g in (g1, g2, gh)]
        lines.append(f"  {label:<18} {n:>4}               {ahead[0]:<5} {ahead[1]:<5} {ahead[2]:<5} |"
                     f"               {(mean(g1) or 0.0) * 100:+5.1f} pts {mean(gh) or 0.0:+.2f} R")
    return lines


def news_lines(evs: list[dict[str, Any]]) -> list[str]:
    """The catalyst as the log keeps it from 2026-11-13 (scanlog news_ctx), and the RVOL
    gate."""
    with_news = [e for e in evs if isinstance((e.get("ctx") or {}).get("news"), dict)]
    if not with_news:
        return ["News and the gate: no signal carries the catalyst read yet (logged from 2026-11-13)"]

    def news(e: dict[str, Any]) -> dict[str, Any]:
        return e["ctx"]["news"]

    def paid(e: dict[str, Any]) -> bool:
        return (news(e).get("pts") or 0) > 0

    def prior(e: dict[str, Any]) -> bool:
        return isinstance(news(e).get("prior"), dict)

    return [
        *_split_lines(f"News inside each day ({len(with_news)} signals carry it):", with_news, [
            ("with the side", lambda e: news(e).get("with") is True),
            # Paid its grade since 2026-11-14; it cost points before (scanscore.W_CATALYST).
            ("reads against it", lambda e: news(e).get("with") is False),
            ("tape overruled it", lambda e: news(e).get("src") == "overruled"),
            ("none", lambda e: news(e).get("tier") is None),
            ("any major", lambda e: news(e).get("tier") == 1 and paid(e)),
            ("major with it", lambda e: news(e).get("with") is True and news(e).get("tier") == 1),
            ("by the move", lambda e: news(e).get("src") == "move"),
            ("by the words", lambda e: news(e).get("src") == "words"),
            ("by the tape", lambda e: news(e).get("src") == "tape"),
            ("a report", lambda e: news(e).get("tag") == "Report"),
            # Logged and unscored (2026-11-14): a major story the session before, with and
            # without news today; and how big the model read today's story to be.
            ("day 2, no news", lambda e: prior(e) and not paid(e)),
            ("day 2, any", prior),
            ("read as big", lambda e: news(e).get("size") == "big"),
            ("read as ordinary", lambda e: news(e).get("size") == "ordinary"),
        ]),
        "",
        *_split_lines("The RVOL gate inside each day:", with_news, [
            ("held out of top 10", lambda e: bool(e["ctx"].get("gated"))),
        ]),
    ]


def load_marks(path: str, since: date | None) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    try:
        with open(path, encoding="utf-8") as f:
            for line in f:
                try:
                    e = json.loads(line)
                except ValueError:
                    continue
                if since and str(e.get("day") or "") < since.isoformat():
                    continue
                out.append(e)
    except OSError:
        return []
    return out


def pool_lines(lines: list[dict[str, Any]]) -> list[str]:
    """The pool's rank against the day each name then had (sources/pool MARKS_NAME):
    the day's range and its move from the previous close, both in daily ATRs."""
    outcome = {e["day"]: e.get("rows") or {} for e in lines if e.get("kind") == "outcome"}
    marks = [e for e in lines if e.get("kind") == "mark" and e.get("day") in outcome]
    if not marks:
        return ["Pool marks: no mark with its day's outcome on file yet (logged from 2026-11-13)"]

    def day_of(sym: str, day: str) -> tuple[float, float] | None:
        o = outcome[day].get(sym) or {}
        vals = [float(x) for x in (o.get(k) for k in ("close", "change", "high", "low", "atr"))
                if isinstance(x, int | float)]
        if len(vals) != 5:
            return None
        c, chg, hi, lo, atr = vals
        if not atr:
            return None
        prev = c / (1.0 + chg / 100.0)
        return (hi - lo) / atr, abs(c - prev) / atr

    groups: dict[str, list[tuple[float, float]]] = defaultdict(list)
    for m in marks:
        for i, r in enumerate(m.get("rows") or []):
            d = day_of(str(r.get("sym")), m["day"])
            if d is None:
                continue
            groups["top 10" if i < 10 else "11-50"].append(d)
            groups["promoted" if r.get("promoted") else "not promoted"].append(d)
    out = [f"Pool marks ({len(marks)} marks over {len({m['day'] for m in marks})} days): "
           "the day each name then had, in daily ATRs",
           "  group           n    range   |move|"]
    for g in ("top 10", "11-50", "promoted", "not promoted"):
        xs = groups.get(g) or []
        if xs:
            out.append(f"  {g:<13} {len(xs):>4}   {mean([x[0] for x in xs]) or 0.0:5.2f}   "
                       f"{mean([x[1] for x in xs]) or 0.0:5.2f}")
    return out


def load_preopen(path: str) -> list[dict[str, Any]]:
    """The pre-open lines on file, none if there is no file yet."""
    out: list[dict[str, Any]] = []
    try:
        with open(path, encoding="utf-8") as f:
            for line in f:
                try:
                    if line.strip():
                        out.append(json.loads(line))
                except ValueError:
                    continue
    except OSError:
        return []
    return out


def preopen_lines(days: list[dict[str, Any]], evs: list[dict[str, Any]]) -> list[str]:
    """That day's signals from the top third of the morning's list against the bottom
    third: what the game plan, which picks from that list, would want to know."""
    if not days:
        return ["Pre-open rank: no morning on file yet (one line a day from 2026-11-05)"]
    top: list[dict[str, Any]] = []
    bottom: list[dict[str, Any]] = []
    for line in days:
        rows = line.get("rows") or []
        n = len(rows) // 3
        if n < 1:
            continue
        hi = {r.get("sym") for r in rows[:n]}
        lo = {r.get("sym") for r in rows[-n:]}
        today = [e for e in evs if e.get("day") == line.get("day")]
        top += [e for e in today if e.get("sym") in hi]
        bottom += [e for e in today if e.get("sym") in lo]
    head = f"Pre-open rank ({len(days)} mornings on file), signals from the top third of the list against the bottom:"
    return [head, gap_line("all", top, bottom)]


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


def report(evs: list[dict[str, Any]], days: int, preopen: list[dict[str, Any]] | None = None,
           marks: list[dict[str, Any]] | None = None) -> str:
    lines = [f"Settled (L)/(E) signals over {days} days: {len(evs)}"]
    if len(evs) < MIN_TOTAL:
        lines.append(f"  under the {MIN_TOTAL}-signal guard: read as a hint, change no weight on it")
    lines.append("")
    scored = [e for e in evs if isinstance(e.get("score"), (int, float))]
    lines += trend_lines(scored)
    lines.append("")
    lines.append("By score band          n   win +1R   at +1R   held")
    for lo, hi in BANDS:
        band = [e for e in scored if lo <= e["score"] < hi]
        lines.append(f"  {lo:>3}–{hi - 1:<3}            {len(band):>4}   {_pct(win(band))}   "
                     f"{_signed(mean([at_1r(e) for e in band]))}    {_signed(mean([held(e) for e in band]))}")
    lines.append(f"  unscored (backfilled) {len(evs) - len(scored):>4}")
    fit = logistic_slope(scored)
    if fit:
        a, b = fit
        # A slope, not a verdict: it read as "orders the record" on any b above zero
        # while the top and bottom thirds tied (2026-11-05). The thirds are the test.
        lines.append(f"Logistic P(+1R) = σ({a:+.2f} {b:+.2f}·score/100): the slope; the thirds below are the test")
    lines.append("")
    lines += equal_day_lines(scored)
    lines.append("")
    lines += rank_lines(scored)
    lines.append("")
    lines += preopen_lines(preopen or [], scored)
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
    lines.append("")
    lines += same_day_lines(with_parts)
    lines.append("")
    lines += entry_lines(with_parts)
    lines.append("")
    lines += penalty_lines(with_parts)
    lines.append("")
    lines += news_lines(scored)
    if marks is not None:
        lines.append("")
        lines += pool_lines(marks)
    return "\n".join(lines)


def main() -> int:
    # Windows consoles default to a code page without σ; never let the report
    # die on a glyph (the collector makes the same provision).
    for stream in (sys.stdout, sys.stderr):
        if hasattr(stream, "reconfigure"):
            stream.reconfigure(errors="replace")
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("--days", type=int, default=30)
    ap.add_argument("--since", type=date.fromisoformat, default=None,
                    help="read from this day on (YYYY-MM-DD) — e.g. 2026-11-13, the reweight")
    ap.add_argument("--path", default=os.path.join(CACHE_DIR, "scanner_events.jsonl"))
    args = ap.parse_args()
    try:
        evs = load(args.path, args.days, datetime.now().date(), args.since)
    except OSError as e:
        print(f"no log: {e}")
        return 1
    here = os.path.dirname(args.path)
    days = (datetime.now().date() - args.since).days + 1 if args.since else args.days
    print(report(evs, days, load_preopen(os.path.join(here, PREOPEN_NAME)),
                 load_marks(os.path.join(here, MARKS_NAME), args.since)))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
