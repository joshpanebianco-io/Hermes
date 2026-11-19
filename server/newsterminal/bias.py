"""
The bias, weighed: a score from -100 to +100 over the whole of the session's weight.

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
    input is missing, nothing has printed) is on neither side and is not counted
    in its family. One that can and sits inside its threshold is a flat read and
    stays: it is evidence of no lean.
  * Reads are grouped into FAMILIES, each scored by its own net (long minus short,
    over its live reads), so one idea has one voice.
  * Each family has a WEIGHT for the session. The numbers are a judgement, in the
    same order the note's prompt gives the layers (report.session_layers), and
    nothing here claims they have been fitted to outcomes.

`score` is the weighted sum of the families OVER THE WHOLE WEIGHT: a family with
nothing live adds nothing and its weight still counts, so it pulls the score toward
zero as a flat one does. +100 means every family is live and every live read in it
is long. `coverage` is how much of the session's weight is live.

THE SCORE WAS OVER THE LIVE WEIGHT UNTIL 2026-11-15 (owner, of the scale the cards
draw: "the whole point of implementing the scale was to demonstrate that"). Divided
by the live weight alone, two reads of eleven that agreed were -100: at a weekend
the stocks tape was SPY and QQQ's after-hours gap, 35% of the weight, and its mark
sat on the bearish end of the scale. The pages had to draw that one hollow and
print "thin" beside it to take it back, and the owner asked why the mark was a
black circle. How much of the evidence there is belongs in the number: the same
night reads -35. A score is now what the old one was, times its coverage, so with
everything live nothing moved. `basis` says which rule a stored read was scored
by ("whole"; absent on one from before), so a page can draw an old one the same way.

THE GRADE AND ITS CEILING. Strong is 50 or more with at least 60% of the weight
live AND at least two families behind it; moderate 30; weak 10; under that there is
no lean. A macro lean the structure rejects is a CONFLICT and takes a notch off, and
event risk takes one off the ceiling. The ceilings are the old ones.

THE LOGIC PASS OF 2026-11-19 (owner: "weight everything as best and accurate as we
can based on logic then gather data to test", then "do what you recommend - eg how
much should what be weighted in ny vs asia vs london"). What changed, each for a
reason that needs no data, and none of it fitted to outcomes:

  * A READ HAS A SIZE. `strength` on a vote (0 to 1, drivestats.py): a move in its
    own usual days, the remainder a co-mover's move leaves once the book's own move
    is taken out, or net breadth. A family is the mean of its live reads' signed
    strengths. A read with no `strength` is a whole vote, as every read was.
  * THE CONFLICT IS WEIGHED. Macro and structure are compared in the POINTS each
    puts on the score, both at least CONFLICT_PTS from flat. It compared the
    families' raw scores, so the VIX curve alone, 7 of Asia's hundred, called a
    conflict with structure's 53 and took NQ from moderate to weak (18 Nov, 23:10 ET).
  * STRONG NEEDS TWO FAMILIES. Gold read -57 strong on the one fact that it was
    under New York's range and value. One family is one fact.
  * TWO READS ARE NOT SIDES. The VIX curve is a regime (how far moves run), as
    gamma is; the heavyweights' prints are already in the index future's price.
  * EACH BOOK AND SESSION WEIGHS ONLY WHAT CAN SPEAK IN IT, at weights set for that
    book (BOARD_WEIGHTS, BOOK_WEIGHTS: the reasons are written beside them).

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
#: Families that must each put at least BACKER_PTS on the score's side for "strong".
STRONG_FAMILIES = 2
BACKER_PTS = 5.0
#: Macro and structure must each put this many points on the score, on opposite sides,
#: before it is a conflict (the lean's own threshold).
CONFLICT_PTS = 10.0
MAX_CONVICTION = {"strong": 5, "moderate": 4, "weak": 3, "none": 2}
_NOTCH = {"strong": "moderate", "moderate": "weak", "weak": "weak", "none": "none"}

# ---- the families -----------------------------------------------------------------
#: key -> (the name on the board, the name on the strip's one line)
FAMILY_NAMES: dict[str, tuple[str, str]] = {
    "structure": ("Intraday structure", "Structure"),
    "daily": ("Daily trend", "Daily trend"),  # no read since 2026-11-15: the way back
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
#
# TREND DOES NOT VOTE EITHER (owner, 2026-11-15: "i think we drop ema's from the bias
# and scoring of stocks"; asked whether the plain daily read should go with the two
# EMAs, they chose every trend read). There were three: the ten-minute 200 EMA in the
# structure family, and the daily family whole (price against the 20, 50 and 200-day,
# and the 200-day EMA by itself). A moving average is price, late: the board already
# reads price where it is, against the prior session's value and range. The day it
# went, the Nasdaq's profile read "accepted higher" and its ten-minute EMA "below
# trend", which cancelled to no structure read at all, and the whole of its short
# lean (-11) was the daily family. The futures board no longer builds the three
# (drivers.py), the daily family has no weight, and its share is given back below as
# gamma's was. The bias is macro, risk appetite, news and data, the volume profile
# and the session's range, and participation in the session.
#
# NOR DO THE VIX CURVE AND THE HEAVYWEIGHTS' PRINTS (2026-11-19, the logic pass). The
# curve's shape is a regime as gamma's is: flat or inverted says moves run, either way,
# and as a level it sits on the short side for days after any selloff (the night it
# went it was NQ's one short vote while the VIX fell 3.5% and NQ rose 1.2%). The
# prints read the reporters' moves times their index weight, which the index future
# has already traded: the book's own move counted again. Both keep their rows, marked
# as never a side.
#
# NOR DOES THE VIX'S DAY (owner, 2026-11-19: "vix and gex are more regime context
# correct?", then "do what you recommend best"). Its level and its curve had already
# gone; its day's move still voted, short when it rose beyond what the index's own move
# explains. The VIX climbs into a scheduled event (CPI, the Fed) and falls after it
# whatever the index does, and the rest of its move is the index's own, mirrored. So the
# VIX is the weather everywhere now, as the owner's own rule has it: it says how far
# moves run and how wide the stops go, never which way. Credit stays as the risk
# family's read (high yield bid or offered beyond the echo), and the row stays,
# marked as never a side.
BOARD_FAMILY: dict[str, str] = {
    "yields": "rates", "dollar": "rates", "silver": "rates",
    "credit": "risk",
    "prints": "catalysts",
    "value": "structure", "session": "structure",
    "sectors": "participation", "leaders": "participation",
    # Silver's and crude's own reads (2026-11-15, drivers.py): the market each follows
    # sits with its macro drivers, as silver has for gold since the board was built.
    "gold": "rates", "copper": "rates", "products": "rates",
    "inventories": "catalysts",
}

# ---- one board a book: which families can ever speak for it ------------------------
#
# EVERY BOOK HAS ITS OWN HUNDRED (2026-11-15). The weights below were written for the
# index books, and gold read them too with two families it has no vote in: the VIX,
# its curve and credit are "not a gold vote", and gold has no sectors or leaders. While
# the score was over the LIVE weight that cost nothing. Over the whole weight (the
# module's note) a family that can NEVER vote for a book is dead weight for ever: in
# the New York session 31 of gold's hundred could not be earned, so its score topped
# out at 69. So each book keeps the families it has a read in, and the session's
# weights are shared out among those in proportion, to the nearest whole number, the
# way gamma's share was when it left the score. No family's standing against another
# changes; an index book's table is the session's, untouched.
#
# SILVER AND CRUDE ARE SCORED SINCE THE SAME DAY (owner: "implement the silver and oil
# bias calculation and weightings and rules too"). What each answers to, as a desk
# would say it, and none of it fitted to outcomes:
#
#   SILVER  a monetary metal with an industrial half. Rates and the dollar as gold
#           reads them, gold itself (silver follows it, and moves further) and copper
#           (the industrial half), all one voice; the inflation prints; its own
#           structure. The equity vol reads are no more a silver vote than a gold one.
#   CRUDE   a dollar-priced barrel that trades on demand and on its own stocks. The
#           dollar and the products (gasoline and heating oil: whether refiners are
#           pulling the barrel through) as one voice; credit and copper as the demand
#           read; the weekly inventories as its catalyst; its own structure. The
#           10-year is not a crude vote (yields rise on growth, which lifts
#           oil, and on the Fed, which sinks it), and neither is the VIX: in a supply
#           shock crude and fear rise together.
BOOK_FAMILIES: dict[str, tuple[str, ...]] = {
    "GC": ("structure", "rates", "catalysts"),
    "SIL": ("structure", "rates", "catalysts"),
    "CL": ("structure", "rates", "risk", "catalysts"),
}

#: A read that sits in another family on one book: copper is silver's own metal and
#: crude's demand.
BOOK_FAMILY_OVERRIDE: dict[str, dict[str, str]] = {
    "CL": {"copper": "risk"},
}

#: What a family is called on a book where its usual name would mislead.
BOOK_FAMILY_NAMES: dict[str, dict[str, tuple[str, str]]] = {
    "SIL": {"rates": ("Rates, dollar & metals", "Rates & metals")},
    "CL": {"rates": ("Dollar & products", "Dollar & products"),
           "risk": ("Demand", "Demand"),
           "catalysts": ("Inventories", "Inventories")},
}


def board_family(book: str) -> dict[str, str]:
    """Which family each read speaks in, on this book. Pure."""
    return {**BOARD_FAMILY, **BOOK_FAMILY_OVERRIDE.get(book, {})}


def share_out(base: dict[str, int], keep: tuple[str, ...]) -> dict[str, int]:
    """`base` with only `keep` weighted, scaled back to a hundred in proportion. Pure.

    Whole numbers by the largest remainder, so the parts always sum to exactly 100; a
    tie goes to the family named first in `keep`."""
    kept = {k: base.get(k, 0) for k in keep}
    total = sum(kept.values())
    if not total:
        return dict.fromkeys(base, 0)
    exact = {k: 100.0 * w / total for k, w in kept.items()}
    out = {k: int(v) for k, v in exact.items()}
    for k in sorted(exact, key=lambda k: -(exact[k] - out[k]))[:100 - sum(out.values())]:
        out[k] += 1
    return {k: out.get(k, 0) for k in base}


def board_weights(book: str, session: str) -> dict[str, int]:
    """A book's family weights for a session: the index table for NQ and ES, the book's
    own for gold, silver and crude (since 2026-11-19; until then theirs were the index
    table shared out in proportion). Pure."""
    return dict(BOOK_WEIGHTS.get(book, BOARD_WEIGHTS)[session])

#: The stocks desk's reads of the tape. The VIX's curve and its day are read and are no
#: side since 2026-11-19 (BOARD_FAMILY says why).
TAPE_FAMILY: dict[str, str] = {
    "spy_levels": "levels", "qqq_levels": "levels",
    "yields": "rates", "dollar": "rates",
    "credit": "risk",
    "sectors": "participation", "equal_weight": "participation",
    "index_volume": "participation", "participation": "participation",
}

# ---- the weights, by book and session: a judgement, stated once with its reasons ----
#
# SET FROM WHAT EACH SESSION CAN SAY, 2026-11-19 (the module's note). Until then the
# index table was gamma's and the daily trend's shares handed back in proportion to
# a 2026-11-05 judgement (Asia structure 53 / rates 20 / catalysts 20 / risk 7, London
# 44 / 31 / 19 / 6, the New York pre-open catalysts 33 / rates 27 / structure 20 /
# risk 20, the session structure 33 / rates 21 / risk 20 / catalysts 13 /
# participation 13), and gold's, silver's and crude's were that table shared out. Two
# things were wrong with it. Weight sat where nothing could ever vote: a US print
# votes until that day's 16:00 close and no later, the VIX does not trade before
# 03:00 ET, credit and breadth are cash-hours reads, so in Asia only structure and
# rates can speak and 27 of the index's hundred could never be earned. And the metals
# and crude carried the index's priorities, where gold is a rates-and-dollar market
# first and crude has a weekly report of its own.
#
# What each family is, after the same day's changes to the reads (drivers.py):
#   structure      the book against the last session's range and the prior day's
#                  value: where the auction is accepting price. The most direct
#                  evidence there is, and the anchor of every session.
#   rates          the 10-year (the note future when the cash yield is shut) and the
#                  dollar, each voting only while it has been driving the book.
#   risk           credit, on the part of its move the book's own move does not
#                  explain: appetite beyond the echo. (The VIX was in it until the
#                  evening of 2026-11-19: BOARD_FAMILY says why it left.)
#   catalysts      the US inflation prints, from the print to that day's close.
#   participation  the sectors and the index's leaders: how broad the move is, the
#                  one thing in the session that price alone does not say.
#
# THE INDEX BOOKS (NQ, ES), heaviest first in each session:
#   Asia      structure 70, rates 30. Thin trade; the index future mostly ranges
#             unless New York's range or value gives. The note future and the dollar
#             trade, thinly: a real say, the smaller one.
#   London    structure 50, rates 35, risk 15. The first real liquidity: Europe
#             trades the US curve and the dollar, so rates count for more. The VIX
#             prints from 03:00 but thinly before New York, and only its surprise
#             counts. Where price sits against Asia's range is still the anchor.
#   NY pre    structure 30, catalysts 30, rates 25, risk 15. The 08:30 window: an
#             inflation print is the largest scheduled mover of the index day, and
#             on the days there is none its 30 is no lean (whole weight). Structure is
#             London's range and the prior value the open will meet.
#   NY        structure 30, rates 20, participation 20, risk 15, catalysts 15. The
#             session's own auction first; breadth up from 13 because it is the read
#             price cannot give; risk down from 20 because it now counts only what the
#             move does not explain; a morning print is partly priced by the afternoon.
#
# WITH THE VIX OUT OF RISK (the evening of 2026-11-19), the family is credit alone, a
# cash-hours read. Before 09:30 nothing in it can speak, so London's 15 and the
# pre-open's 15 are shared out in proportion as gamma's were (London structure 59 /
# rates 41; the pre-open structure 35 / catalysts 35 / rates 30). In the session one
# read of two is left, so risk keeps 10 and the other 5 goes to structure, the anchor:
# structure 35 / rates 20 / participation 20 / catalysts 15 / risk 10.
BOARD_WEIGHTS: dict[str, dict[str, int]] = {
    "asia": {"structure": 70, "rates": 30, "risk": 0, "catalysts": 0, "participation": 0},
    "london": {"structure": 59, "rates": 41, "risk": 0, "catalysts": 0, "participation": 0},
    "ny_pre": {"structure": 35, "catalysts": 35, "rates": 30, "risk": 0, "participation": 0},
    "ny_live": {"structure": 35, "rates": 20, "participation": 20, "risk": 10,
                "catalysts": 15},
}

# GOLD, SILVER AND CRUDE, each on its own table:
#   GOLD      rates holds the 10-year, the dollar and silver's surprise against gold.
#             Gold trades in earnest round the clock (Shanghai, then London, its home
#             market, then COMEX) and is a rates-and-dollar market first: Asia
#             structure 60 / rates 40, London 50 / 50, the New York pre-open rates 35 /
#             catalysts 35 (a print reaches gold through real yields at once) /
#             structure 30, the session rates 45 / structure 35 / catalysts 20.
#   SILVER    rates holds the 10-year, the dollar, gold's and copper's surprises
#             against silver. Gold's priorities with a little more on its own auction,
#             because silver is the more speculative market: Asia 60 / 40, London
#             50 / 50, the pre-open structure 35 / rates 35 / catalysts 30, the session
#             40 / 40 / 20.
#   CRUDE     structure; "Dollar & products" (the dollar, and the products' surprise
#             against crude: refiners pulling the barrel through); "Demand" (credit's
#             and copper's surprises); catalysts are the weekly inventories (Wednesday
#             10:30) and the US growth prints. Asia structure 60 / products 25 / demand
#             15 (copper trades; credit does not), London 50 / 30 / 20, the pre-open
#             structure 40 / products 30 / demand 15 / growth prints 15, the session
#             35 / 25 / 15 with the inventories and prints at 25: Wednesday's report
#             is the largest scheduled event of crude's week.
BOOK_WEIGHTS: dict[str, dict[str, dict[str, int]]] = {
    "GC": {
        "asia": {"structure": 60, "rates": 40, "catalysts": 0, "risk": 0, "participation": 0},
        "london": {"structure": 50, "rates": 50, "catalysts": 0, "risk": 0, "participation": 0},
        "ny_pre": {"rates": 35, "catalysts": 35, "structure": 30, "risk": 0, "participation": 0},
        "ny_live": {"rates": 45, "structure": 35, "catalysts": 20, "risk": 0, "participation": 0},
    },
    "SIL": {
        "asia": {"structure": 60, "rates": 40, "catalysts": 0, "risk": 0, "participation": 0},
        "london": {"structure": 50, "rates": 50, "catalysts": 0, "risk": 0, "participation": 0},
        "ny_pre": {"structure": 35, "rates": 35, "catalysts": 30, "risk": 0, "participation": 0},
        "ny_live": {"structure": 40, "rates": 40, "catalysts": 20, "risk": 0, "participation": 0},
    },
    "CL": {
        "asia": {"structure": 60, "rates": 25, "risk": 15, "catalysts": 0, "participation": 0},
        "london": {"structure": 50, "rates": 30, "risk": 20, "catalysts": 0, "participation": 0},
        "ny_pre": {"structure": 40, "rates": 30, "risk": 15, "catalysts": 15, "participation": 0},
        "ny_live": {"structure": 35, "rates": 25, "catalysts": 25, "risk": 15, "participation": 0},
    },
}

#: THE STOCKS TAPE. Before the open the sector and leader reads are yesterday's, so the
#: tape is SPY's and QQQ's gap, the macro under it and credit: levels 50 / rates 35 /
#: risk 15. In the session the tape itself speaks: levels 40 / participation 30 / rates
#: 20 / risk 10. Risk was 35 before the open with the VIX's curve and day in it, 25 once
#: the curve left (both no side since 2026-11-19: BOARD_FAMILY), and credit alone keeps
#: 15 (HYG trades thinly before the bell) and 10 in the session; what the VIX's day
#: held goes to SPY's and QQQ's own levels, the most direct read the tape has.
TAPE_WEIGHTS: dict[str, dict[str, int]] = {
    "before_open": {"levels": 50, "rates": 35, "risk": 15, "participation": 0},
    "session": {"levels": 40, "participation": 30, "rates": 20, "risk": 10},
}

#: The phrase the page prints: "85% of London's weight".
WEIGHT_LABEL: dict[str, str] = {
    "asia": "Asia's weight", "london": "London's weight",
    "ny_pre": "the New York pre-open's weight", "ny_live": "New York's weight",
    "before_open": "the pre-open's weight", "session": "the session's weight",
}

#: The families on each side of the macro-against-structure conflict.
_MACRO = ("rates", "risk", "catalysts")
_STRUCTURE = ("structure",)


def session_key(session: str, underway: bool) -> str:
    """Which column of the board's weights a note or a clock reads. Pure."""
    if session in ("asia", "london"):
        return session
    return "ny_live" if underway else "ny_pre"


def tape_key(scan_session: str) -> str:
    """Which column of the tape's weights a scanner session reads. Pure."""
    return "before_open" if scan_session in ("pre", "closed") else "session"


def read(votes: list[dict[str, Any]], family_of: dict[str, str], weights: dict[str, int],
         session: str, names: dict[str, tuple[str, str]] | None = None) -> dict[str, Any]:
    """The score, its grade and the reads behind it. Pure.

    A read with no family (event risk) stays in `votes` and out of everything else.
    A read with no `live` flag is taken as able to vote. `names` renames a family for
    this board (crude's "Rates & dollar" holds the dollar and the products).

    A long or short read carries `strength`, 0 to 1, how much of a full vote its size
    earns (drivestats.py); without one it is a full vote. A family's score is the mean
    of its live reads' signed strengths, a flat read counting as zero."""
    tally: dict[str, list[float]] = {}
    tagged: list[dict[str, Any]] = []
    long_n = short_n = flat_n = cannot = 0
    for v in votes:
        fam = family_of.get(str(v.get("key")))
        tagged.append({**v, "family": fam})
        if fam is None:
            continue
        t = tally.setdefault(fam, [0.0, 0, 0])  # signed strength, live reads, every read
        t[2] += 1
        if v.get("live", True) is False:
            cannot += 1
            continue
        t[1] += 1
        s = v.get("strength")
        amount = 1.0 if not isinstance(s, (int, float)) else max(0.0, min(1.0, float(s)))
        if v.get("vote") == "long":
            t[0] += amount
            long_n += 1
        elif v.get("vote") == "short":
            t[0] -= amount
            short_n += 1
        else:
            flat_n += 1

    whole = sum(weights.values())
    live_weight = 0
    net = 0.0
    families: list[dict[str, Any]] = []
    for fam, t in tally.items():
        s = t[0] / t[1] if t[1] else None
        w = weights.get(fam, 0)
        if s is not None and w:
            live_weight += w
            net += w * s
        label, short = (names or {}).get(fam) or FAMILY_NAMES.get(fam, (fam, fam))
        families.append({"key": fam, "label": label, "short": short, "weight": w,
                         "score": round(100 * s) if s is not None else None,
                         # What the family puts on the score, in its points.
                         "points": round(100 * w * s / whole, 1) if s is not None and whole
                         else 0.0,
                         "live": int(t[1]), "total": int(t[2])})
    families.sort(key=lambda f: -f["weight"])

    # Over the WHOLE weight, not the live weight: a family that cannot vote counts
    # as no lean, so a read on a third of the weight is a third of the way out at
    # most (the module's note has the why).
    score = round(100 * net / whole) if whole else 0
    coverage = round(100 * live_weight / whole) if whole else 0
    bias = ("long" if score >= LEAN_AT else "short" if score <= -LEAN_AT else None)
    size = abs(score)
    # STRONG NEEDS TWO FAMILIES (2026-11-19): one family is one fact, however far out.
    sign = 1 if score > 0 else -1
    backers = sum(1 for f in families if f["points"] * sign >= BACKER_PTS)
    if size >= STRONG_AT and coverage >= STRONG_COVERAGE and backers >= STRONG_FAMILIES:
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
        "bias": bias, "score": score, "basis": "whole", "coverage": coverage, "grade": grade,
        "max_conviction": MAX_CONVICTION[grade],
        "agree": agree, "against": against, "neutral": flat_n,
        "live": live, "cannot_vote": cannot, "total": live + cannot,
        "backers": backers if bias else 0,
        "families": families, "session_key": session,
        "weight_label": WEIGHT_LABEL.get(session, "the session's weight"),
        "votes": tagged,
    }


#: With this share of the session's weight or less able to vote, the tape's lean is
#: weak at most (`tape_read`). "Or less" since the evening of 2026-11-19, when SPY's and
#: QQQ's levels became half the pre-open's weight: under it they were 40, and two reads
#: of one family must still be a thin lean.
THIN_COVERAGE = 50


def tape_read(votes: list[dict[str, Any]], scan_session: str) -> dict[str, Any]:
    """The stocks desk's tape count, weighed. Pure.

    A LEAN ON TWO READS IS NOT A MODERATE TAPE (owner, 2026-11-11: "do what you
    recommend"). Overnight only SPY and QQQ against their levels can vote: at
    20:13 ET on 10 Nov both were a third of a percent up after hours, which is one
    family and 35% of the pre-open's weight, and the card read "Long +100,
    moderate" with plans capped at four. So with THIN_COVERAGE of the weight or less
    live the grade is weak at most and the ceiling follows it. Strong already
    needed 60%; this is the same idea one grade down. The futures board
    (`board_read`) is not changed.

    The score is over the whole weight since 2026-11-15, so that night reads +35,
    not +100, and the pages draw it as any other read: `thin` no longer changes a
    drawing. It still caps the grade, because +35 on one family would otherwise be
    moderate and put the plans' ceiling back at four.
    """
    key = tape_key(scan_session)
    r = read(votes, TAPE_FAMILY, TAPE_WEIGHTS[key], key)
    r["thin"] = r["bias"] is not None and r["coverage"] <= THIN_COVERAGE
    if r["thin"] and r["grade"] in ("strong", "moderate"):
        r["grade"] = "weak"
        r["max_conviction"] = MAX_CONVICTION["weak"]
    return r


def _side(x: float) -> str | None:
    return "long" if x > 0 else "short" if x < 0 else None


def board_read(book: str, votes: list[dict[str, Any]], session: str, *,
               regime: str | None, ny_open: bool, events: int = 0) -> dict[str, Any]:
    """One futures book's read for a session: the score, the macro-against-structure
    conflict, the ceiling and the line on how to treat it. Pure.

    The book decides which family each read speaks in and what the families weigh
    (`board_family`, `board_weights`): an index book's are the session's own."""
    r = read(votes, board_family(book), board_weights(book, session), session,
             names=BOOK_FAMILY_NAMES.get(book))
    # WEIGHED, SINCE 2026-11-19: what each side puts on the score in points, not the
    # families' raw scores, which let a family worth 7 of the hundred call a conflict
    # with one worth 53.
    points = {f["key"]: f["points"] for f in r["families"]}
    macro = sum(points.get(k, 0.0) for k in _MACRO)
    structure = sum(points.get(k, 0.0) for k in _STRUCTURE)
    conflict = macro * structure < 0 and min(abs(macro), abs(structure)) >= CONFLICT_PTS
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
