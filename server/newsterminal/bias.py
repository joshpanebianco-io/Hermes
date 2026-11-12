"""
The bias, weighed: a score from -100 to +100 across the reads that can vote.

WHY NOT A COUNT (owner, 2026-11-05: "is there a better way to determine bias? ...
it rarely gets anywhere close to 16 of 16"; then "do what you recommend"). The
board counted its reads and printed "3 of 16", and the best on record was 10.
It could never have been 16:

  * Event risk is a damper and never votes.
  * US prints vote only on an inflation day, and the index prints only once a
    heavyweight has reported and traded.
  * Outside New York the cash reads are shut. At 06:15 ET seven of the sixteen
    could not vote at all, and "3 of 16" was really 3 of 8.
  * Reads that are one idea counted as many: the daily frame and the daily 200,
    or the VIX, its curve and credit. Agreement was partly one fact counted three
    times, and the same reads weighed the same at 20:00 as at 10:30.

So the score does three things the count did not:

  * A read that CANNOT vote at this hour (`live` false: the market is shut, the
    input is missing, nothing has printed) leaves the sum. One that can and sits
    inside its threshold is a flat read and stays: it is evidence of no lean.
  * Reads are grouped into FAMILIES, each scored by its own net (long minus short,
    over its live reads), so one idea has one voice.
  * Each family has a WEIGHT for the session. The numbers are a judgement, in the
    same order the note's prompt gives the layers (report.session_layers), and
    nothing here claims they have been fitted to outcomes.

`score` is the weighted sum of the live families. +100 means every live read in
every live family is long, which is reachable on a day when everything agrees, as
16 of 16 never was. `coverage` is how much of the session's weight is live, and it
is printed beside the score so a thin read says it is thin.

THE GRADE AND ITS CEILING. Strong is 50 or more with at least 60% of the weight
live; moderate 30; weak 10; under that there is no lean. A macro lean the structure
rejects is a CONFLICT and takes a notch off, and event risk takes one off the
ceiling, both as they did. The ceilings are the old ones.

PURE. Nothing here imports the rest of the terminal, so the board (drivers.py), the
tape count (marketctx.py) and a note written for another session (report.py) can all
call it.
"""

from __future__ import annotations

from typing import Any

# ---- the grade ------------------------------------------------------------------
STRONG_AT = 50  # |score| at or above: strong
MODERATE_AT = 30  # at or above: moderate
LEAN_AT = 10  # at or above: a lean, weak; under it, no lean
STRONG_COVERAGE = 60  # % of the session's weight that must be live for "strong"
CONFLICT_AT = 25  # both layers at least this far apart before it is a conflict
MAX_CONVICTION = {"strong": 5, "moderate": 4, "weak": 3, "none": 2}
_NOTCH = {"strong": "moderate", "moderate": "weak", "weak": "weak", "none": "none"}

# ---- the families -----------------------------------------------------------------
#: key -> (the name on the board, the name on the strip's one line)
FAMILY_NAMES: dict[str, tuple[str, str]] = {
    "structure": ("Intraday structure", "Structure"),
    "daily": ("Daily trend", "Daily trend"),
    "rates": ("Rates & dollar", "Rates & dollar"),
    "risk": ("Risk appetite", "Risk"),
    "catalysts": ("Catalysts", "Catalysts"),
    "participation": ("Participation", "Participation"),
    "levels": ("Index levels", "Levels"),
}

#: The futures board's reads. Two are in no family, because neither is a side: event
#: risk is a damper, and dealer gamma is a regime.
#
# GAMMA DOES NOT VOTE (owner, 2026-11-12: "gamma levels incorrect bias - positive
# doesnt mean bullish and vice versa"). It was the whole of a "positioning" family,
# long with spot above the flip and short below it, which is the regime by another
# name: positive gamma counted as a long vote and negative as a short one, a fifth of
# the score in the New York session. The regime says how far a move runs (damped
# above the flip, amplified below it), in either direction, and that is where it
# stays: the board's line on how to treat the score (`treatment`), and its own row,
# marked as never a side. The family is gone and its weight is shared out below.
BOARD_FAMILY: dict[str, str] = {
    "yields": "rates", "dollar": "rates", "silver": "rates",
    "vix_dir": "risk", "vix_curve": "risk", "credit": "risk",
    "prints": "catalysts", "hw_prints": "catalysts",
    "value": "structure", "session": "structure", "trend10m": "structure",
    "frame": "daily", "daily200": "daily",
    "sectors": "participation", "leaders": "participation",
}

#: The stocks desk's eleven reads of the tape.
TAPE_FAMILY: dict[str, str] = {
    "spy_levels": "levels", "qqq_levels": "levels",
    "yields": "rates", "dollar": "rates",
    "vix_dir": "risk", "vix_curve": "risk", "credit": "risk",
    "sectors": "participation", "equal_weight": "participation",
    "index_volume": "participation", "participation": "participation",
}

# ---- the weights, by session: a judgement, stated once ------------------------------
#
# Gamma's share (5, 5, 15 and 20 of each hundred) went back to the families that are
# sides, each in proportion to what it already had, to the nearest whole number: no
# family's standing against another changed, and two that were level are still
# level. So a score is what the old one would have been with gamma's vote taken out,
# and nothing else moved. That is why these are not round numbers. Before, in the same
# order: Asia 40 / 20 / 15 / 15 / 5, London 35 / 25 / 15 / 15 / 5, the New York
# pre-open 25 / 20 / 15 / 15 / 10, the session 25 / 15 / 15 / 10 / 10 / 5.
BOARD_WEIGHTS: dict[str, dict[str, int]] = {
    "asia": {"structure": 42, "daily": 21, "rates": 16, "catalysts": 16, "risk": 5,
             "participation": 0},
    "london": {"structure": 37, "rates": 26, "daily": 16, "catalysts": 16, "risk": 5,
               "participation": 0},
    "ny_pre": {"catalysts": 29, "rates": 24, "structure": 18, "risk": 18, "daily": 11,
               "participation": 0},
    "ny_live": {"structure": 31, "rates": 19, "risk": 19, "catalysts": 12, "participation": 12,
                "daily": 7},
}

#: Before the open the sector and leader reads are yesterday's, so the tape is its
#: gap and the macro under it; in the session the tape itself speaks.
TAPE_WEIGHTS: dict[str, dict[str, int]] = {
    "before_open": {"levels": 35, "risk": 35, "rates": 30, "participation": 0},
    "session": {"levels": 35, "participation": 30, "risk": 20, "rates": 15},
}

#: The phrase the page prints: "85% of London's weight".
WEIGHT_LABEL: dict[str, str] = {
    "asia": "Asia's weight", "london": "London's weight",
    "ny_pre": "the New York pre-open's weight", "ny_live": "New York's weight",
    "before_open": "the pre-open's weight", "session": "the session's weight",
}

#: The families on each side of the macro-against-structure conflict.
_MACRO = ("rates", "risk", "catalysts")
_STRUCTURE = ("structure", "daily")


def session_key(session: str, underway: bool) -> str:
    """Which column of the board's weights a note or a clock reads. Pure."""
    if session in ("asia", "london"):
        return session
    return "ny_live" if underway else "ny_pre"


def tape_key(scan_session: str) -> str:
    """Which column of the tape's weights a scanner session reads. Pure."""
    return "before_open" if scan_session in ("pre", "closed") else "session"


def read(votes: list[dict[str, Any]], family_of: dict[str, str], weights: dict[str, int],
         session: str) -> dict[str, Any]:
    """The score, its grade and the reads behind it. Pure.

    A read with no family (event risk) stays in `votes` and out of everything else.
    A read with no `live` flag is taken as able to vote."""
    tally: dict[str, list[int]] = {}
    tagged: list[dict[str, Any]] = []
    long_n = short_n = flat_n = cannot = 0
    for v in votes:
        fam = family_of.get(str(v.get("key")))
        tagged.append({**v, "family": fam})
        if fam is None:
            continue
        t = tally.setdefault(fam, [0, 0, 0, 0])  # long, short, flat, every read
        t[3] += 1
        if v.get("live", True) is False:
            cannot += 1
        elif v.get("vote") == "long":
            t[0] += 1
            long_n += 1
        elif v.get("vote") == "short":
            t[1] += 1
            short_n += 1
        else:
            t[2] += 1
            flat_n += 1

    def family_score(t: list[int]) -> float | None:
        n = t[0] + t[1] + t[2]
        return (t[0] - t[1]) / n if n else None

    live_weight = 0
    net = 0.0
    families: list[dict[str, Any]] = []
    for fam, t in tally.items():
        s = family_score(t)
        w = weights.get(fam, 0)
        if s is not None and w:
            live_weight += w
            net += w * s
        label, short = FAMILY_NAMES.get(fam, (fam, fam))
        families.append({"key": fam, "label": label, "short": short, "weight": w,
                         "score": round(100 * s) if s is not None else None,
                         "live": t[0] + t[1] + t[2], "total": t[3]})
    families.sort(key=lambda f: -f["weight"])

    whole = sum(weights.values())
    score = round(100 * net / live_weight) if live_weight else 0
    coverage = round(100 * live_weight / whole) if whole else 0
    bias = ("long" if score >= LEAN_AT else "short" if score <= -LEAN_AT else None)
    size = abs(score)
    if size >= STRONG_AT and coverage >= STRONG_COVERAGE:
        grade = "strong"
    elif size >= MODERATE_AT:
        grade = "moderate"
    elif size >= LEAN_AT:
        grade = "weak"
    else:
        grade = "none"
    agree = long_n if bias == "long" else short_n if bias == "short" else max(long_n, short_n)
    against = short_n if bias == "long" else long_n if bias == "short" else min(long_n, short_n)
    live = long_n + short_n + flat_n
    return {
        "bias": bias, "score": score, "coverage": coverage, "grade": grade,
        "max_conviction": MAX_CONVICTION[grade],
        "agree": agree, "against": against, "neutral": flat_n,
        "live": live, "cannot_vote": cannot, "total": live + cannot,
        "families": families, "session_key": session,
        "weight_label": WEIGHT_LABEL.get(session, "the session's weight"),
        "votes": tagged,
    }


#: With less than this share of the session's weight able to vote, the tape's lean is
#: weak at most (`tape_read`).
THIN_COVERAGE = 50


def tape_read(votes: list[dict[str, Any]], scan_session: str) -> dict[str, Any]:
    """The stocks desk's tape count, weighed. Pure.

    A LEAN ON TWO READS IS NOT A MODERATE TAPE (owner, 2026-11-11: "do what you
    recommend"). Overnight only SPY and QQQ against their levels can vote: at
    20:13 ET on 10 Nov both were a third of a percent up after hours, which is one
    family and 35% of the pre-open's weight, and the card read "Long +100,
    moderate" with plans capped at four. The score is right (every read that can
    vote agrees), and it is a thin read. So with under THIN_COVERAGE of the weight
    live the grade is weak at most, the ceiling follows it, and `thin` tells the
    page to print the count beside the score. Strong already needed 60%; this is
    the same idea one grade down. The futures board (`board_read`) is not changed.
    """
    key = tape_key(scan_session)
    r = read(votes, TAPE_FAMILY, TAPE_WEIGHTS[key], key)
    r["thin"] = r["bias"] is not None and r["coverage"] < THIN_COVERAGE
    if r["thin"] and r["grade"] in ("strong", "moderate"):
        r["grade"] = "weak"
        r["max_conviction"] = MAX_CONVICTION["weak"]
    return r


def _side(x: float) -> str | None:
    return "long" if x > 0 else "short" if x < 0 else None


def board_read(book: str, votes: list[dict[str, Any]], session: str, *,
               regime: str | None, ny_open: bool, events: int = 0) -> dict[str, Any]:
    """One futures book's read for a session: the score, the macro-against-structure
    conflict, the ceiling and the line on how to treat it. Pure."""
    r = read(votes, BOARD_FAMILY, BOARD_WEIGHTS[session], session)
    scores = {f["key"]: f["score"] for f in r["families"] if f["score"] is not None}
    macro = sum(scores.get(k, 0) for k in _MACRO)
    structure = sum(scores.get(k, 0) for k in _STRUCTURE)
    conflict = macro * structure < 0 and min(abs(macro), abs(structure)) >= CONFLICT_AT
    if conflict:
        r["grade"] = _NOTCH[r["grade"]]
    damper = any(v.get("damper") for v in votes)
    cap = MAX_CONVICTION[r["grade"]]
    # THE DAMPER (events.py): an event on the tape is not a side, it is a reason
    # to be a notch less sure of any side.
    r["max_conviction"] = max(1, cap - 1) if damper else cap
    r.update({
        "macro_lean": _side(macro), "structure_lean": _side(structure), "conflict": conflict,
        "regime": regime, "event_risk": damper, "event_count": events if damper else 0,
    })
    r["treatment"] = treatment(book, r, ny_open) + (
        f" Event risk since the close ({events}): conviction capped a notch lower."
        if damper else "")
    return r


def treatment(book: str, r: dict[str, Any], ny_open: bool) -> str:
    """One line on how to treat the score. Pure."""
    bias, grade, regime = r["bias"], r["grade"], r.get("regime")
    weight = {f["key"]: f["weight"] for f in r["families"]}
    # The reads carrying it, heaviest family first.
    agreeing = sorted((v for v in r["votes"] if v.get("family") and v.get("live", True) is not False
                       and v.get("vote") == bias), key=lambda v: -weight.get(v["family"], 0))
    reasons = "; ".join(f"{v['label']} {v['value']}" for v in agreeing[:3])
    gamma = ("positive gamma: fade into the walls, ranges hold" if regime == "POS"
             else "negative gamma: breaks run, trade the break not the fade" if regime == "NEG"
             else "no gamma read")
    where = "" if ny_open else " (gamma is a reference outside New York)"
    stats = f"score {r['score']:+d}, {r['live']} of {r['total']} reads live"
    # The conflict is named before the lean: the layers disagreeing IS the read,
    # and "no lean" would hide what caused it.
    if r.get("conflict"):
        return (f"Macro leans {r['macro_lean']} on {book} but structure accepts "
                f"{r['structure_lean']}: a conflict. Lower conviction, trade the levels not the "
                f"lean — {gamma}{where}.")
    if bias is None or grade == "none":
        return f"No lean on {book}: {stats}. Trade the levels — {gamma}{where}."
    if grade == "weak":
        return (f"Lean {bias} {book}, weak ({stats}): {reasons}. "
                f"Small size until more reads agree — {gamma}{where}.")
    return (f"Lean {bias} {book}, {grade} ({stats}): {reasons}. "
            f"{gamma[0].upper() + gamma[1:]}{where}.")
