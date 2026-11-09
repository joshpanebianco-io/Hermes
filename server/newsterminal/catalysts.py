"""
How much a headline matters — one grade, read by the score, the pool and the tables.

WHY GRADE IT (owner, 2026-11-09: "news is the engine of moves"). The signal log
agrees, as far as it can: on the seven sessions with enough of both, signals with
news behind them reached +2R 47.5% of the time against 35.8% with none, and held
+0.96 R against +0.27 R, on both halves of the record, though no more often
reached +1R (44 signals, in-sample). So news makes a move run; it does not make
a level hold.

BUT THE NEWEST STORY IS THE WRONG TEST. On all five of the biggest breakouts of
Friday 6 Nov that were checked, the newest headline was an analyst's note written
AFTER the move: IRTC's was "Cut to Neutral From Buy by Citigroup", while the
cause, five stories further down, was "iRhythm plunges after Q3 miss". The score
paid a price-target tweak the same twelve points as an earnings beat, and an FDA
approval or a takeover nothing, because neither looks like a rating.

THE TIERS.
  1  Major — it changes what the company is worth today: a report, guidance, an
     FDA or trial readout, a deal, a contract, an offering, a probe, or a story
     that names why the stock moved.
  2  Notable — someone with a following changed their mind: an upgrade, a
     downgrade, an initiation.
  3  Minor — a price-target tweak, a reiteration, a preview, a stock list.
  0  Noise — the law firms' "investors have an opportunity to join" notices.
     Counted for nothing, and shown nowhere.

These are words on a headline, not a judgement of the story; a rough rule that
sorts the common cases. Pure, and `tests/test_catalysts.py` keeps the examples.
"""

from __future__ import annotations

import re
from typing import NamedTuple

MAJOR, NOTABLE, MINOR, NOISE = 1, 2, 3, 0


class Grade(NamedTuple):
    tag: str
    tier: int


_NOISE = re.compile(
    r"class action|shareholder (alert|investigation|rights)|investors? (have|who|are encouraged|"
    r"should|with losses)|law firm|law offices|\bLLP\b|pomerantz|rosen law|levi & korsinsky|"
    r"bragar eagel|faruqi|hagens berman|robbins geller|kessler topaz|lead plaintiff|"
    r"deadline alert|securities (fraud|litigation)|investigation (of|on behalf)",
    re.I,
)
_LIST = re.compile(
    r"stocks? (moving|to watch|to buy|that)|\bmovers\b|top (gainers|losers)|biggest (gainers|"
    r"losers|movers)|stock market today|bulls and bears|market (wrap|update|recap)|"
    r"\bstocks? (rise|fall|close|open|end|slide|climb)\b|why .{0,40} (stock|shares) (is|are)\b",
    re.I,
)
_PREVIEW = re.compile(
    r"what to (expect|look for|watch)|earnings preview|ahead of (its |the |q[1-4] )?(earnings|"
    r"results|report)|expected to report|will report|set to report|scheduled to report|"
    r"to (report|announce) .{0,40}(results|earnings)|to (host|hold) .{0,40}call|"
    r"(results|earnings) (date|release date|conference call)|earnings call is live",
    re.I,
)
_TARGET = re.compile(
    r"price target|\bpt\b|maintains|reiterat|raises? target|cuts? target|lifts? target|"
    r"(lowers?|trims?) target",
    re.I,
)
_RATING = re.compile(
    r"upgrad|downgrad|initiat|resumes? coverage|cut to (neutral|hold|sell|underperform|underweight|"
    r"market perform|sector perform|equal[- ]weight|in[- ]line|peer perform)|"
    r"raised to (buy|outperform|overweight|strong buy)",
    re.I,
)
_GUIDE = re.compile(
    r"(rais|cut|lower|hik|slash|lift|withdraw|reaffirm|boost|trim)\w* .{0,40}"
    r"(guidance|outlook|forecast)|(guidance|outlook|forecast) (cut|raise|hike|lowered|slashed)",
    re.I,
)
_EARN = re.compile(
    r"\bearnings\b|\bresults\b|\bq[1-4]\b|\b(first|second|third|fourth)[- ]quarter\b|\bquarterly\b|"
    r"\beps\b|\bbeats?\b|\bmiss(es|ed)?\b|\bprofit\b|guidance|outlook|\bforecasts?\b",
    re.I,
)
_FDA = re.compile(
    r"\bfda\b|\bphase (1|2|3|i{1,3})\b|\bclinical\b|\btopline\b|\bprimary endpoint\b|"
    r"\bcomplete response\b|\bpdufa\b",
    re.I,
)
_DEAL = re.compile(
    r"\bacqui(re|res|red|ring|sition)\b|\bmerger\b|\bmerge\b|\btakeover\b|\bbuyout\b|"
    r"\btake[- ]private\b|definitive agreement",
    re.I,
)
_CONTRACT = re.compile(r"\bcontract\b|\bawarded\b|\bwins?\b.{0,40}\b(deal|order)\b", re.I)
_OFFERING = re.compile(
    r"\b(public|secondary|stock|share|equity|convertible|notes?|registered direct)\s+offering\b|"
    r"\bprices? .{0,40}offering\b|\bat-the-market\b",
    re.I,
)
_LEGAL = re.compile(
    r"\bprobe\b|\bsubpoena|\bdoj\b|\bsec (charges|sues|probe)\b|\bbankrupt|\bchapter 11\b|"
    r"\brecall\b|\bantitrust\b|\bfraud\b",
    re.I,
)
_MOVE = re.compile(
    r"\b(plunge|plunges|plunged|soar|soars|soared|surge|surges|surged|tumble|tumbles|tumbled|"
    r"sink|sinks|sank|jump|jumps|jumped|slump|slumps|slumped|crash|crashes|rally|rallies|"
    r"skyrocket\w*|nosedive\w*)\b",
    re.I,
)


def grade(title: str) -> Grade:
    """A headline → its tag and tier. Pure. The order of the checks is the rule."""
    t = title or ""
    if _NOISE.search(t):
        return Grade("Notice", NOISE)
    if _PREVIEW.search(t):
        return Grade("Preview", MINOR)
    if _LIST.search(t):
        return Grade("List", MINOR)
    # An analyst first: "Price Target Raised After Q3 Beat" is the note, not the beat.
    if _RATING.search(t):
        return Grade("Analyst", NOTABLE)
    if _TARGET.search(t):
        return Grade("Target", MINOR)
    if _GUIDE.search(t):
        return Grade("Guidance", MAJOR)
    if _FDA.search(t):
        return Grade("FDA", MAJOR)
    if _DEAL.search(t):
        return Grade("Deal", MAJOR)
    if _OFFERING.search(t):
        return Grade("Offering", MAJOR)
    if _LEGAL.search(t):
        return Grade("Legal", MAJOR)
    if _EARN.search(t):
        return Grade("Earnings", MAJOR)
    if _CONTRACT.search(t):
        return Grade("Contract", MAJOR)
    if _MOVE.search(t):
        return Grade("Move", MAJOR)
    return Grade("News", MINOR)


#: A headline's share of the score's twelve points, by tier.
TIER_POINTS = {MAJOR: 12, NOTABLE: 8, MINOR: 3, NOISE: 0}
#: What a headline against the side costs. The -6 was left alone because the
#: record on news against a trade is mixed (worse in the first half of it, better
#: in the second); only a minor note comes down, since it now earns only 3.
TIER_PENALTY = {MAJOR: -6, NOTABLE: -6, MINOR: -3, NOISE: 0}
