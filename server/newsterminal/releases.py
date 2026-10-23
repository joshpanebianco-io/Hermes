"""
One release, one row: the prints an agency publishes together, grouped.

SEVEN ROWS FOR ONE NUMBER (owner review, 2026-10-14). The calendar lists
each series of a release on its own line, so the 08:30 US CPI arrived as Core
CPI m/m, Core CPI y/y, Core CPI Index, CPI y/y, CPI m/m, CPI Index n.s.a. and
CPI Index s.a. — seven rows in the Calendar, four in the Market tab's prints,
and in the futures brief seven catalysts, five of which the model wrote the
same note for. They were also seven of the brief's ten "ahead" slots, which is
how Thursday's PPI and claims fell off a Wednesday-night note.

THE FAMILY RULE, AND IT IS EXPLICIT. Two rows are one release when they share
a country, a timestamp and a FAMILY. The family is the event name with the
series qualifiers taken off — core, m/m, y/y, q/q, index, the seasonal tags,
initial / continuing / 4-week average — and a country's adjective ("German",
"French") dropped, so "Core CPI y/y" and "CPI Index, n.s.a." are both `cpi`.
A few releases print several differently-named series and are joined by
ALIASES: the jobs report (payrolls, the unemployment rate, earnings), weekly
claims, the BEA's PCE and personal income / spending, retail sales and its
control group. Anything else keeps its own family — CPI and jobless claims at
the same 08:30 stay two rows, and so do Real Earnings, which the BLS publishes
beside CPI but which nobody trades as CPI.

THE LEAD is the row the group is titled by: the highest impact score, then a
real series before an index level, then the alias family's own headline
(payrolls, initial claims), then — for the inflation families — core before
headline, because core is the figure the Fed and the rate market price, and
for everything else headline before core; then the monthly change before the
annual. So US CPI leads on Core CPI m/m, PPI on Core PPI m/m, retail sales on
the headline m/m, claims on initial claims.

INDEX LEVELS AND UNADJUSTED TWINS FOLD AWAY. "CPI Index, n.s.a. 336.65" is the
same release expressed as a number no one prices, and the n.s.a. % change is
the seasonal twin of the one that is. They are kept on the group (`levels`) so
a panel can say they exist, never shown as figures beside the real ones.

src/lib/releases.ts IS THIS RULE IN THE BROWSER, and the two are kept in step
by hand — the tests on both sides use the same names.
"""

from __future__ import annotations

import re
from collections.abc import Callable, Iterable
from dataclasses import dataclass, field
from typing import Any, Generic, TypeVar

T = TypeVar("T")

_ADJECTIVE = re.compile(
    r"^(?:german|french|spanish|italian|british|japanese|chinese|canadian|australian|"
    r"swiss|u\.?s\.?|u\.?k\.?|euro ?zone|ez)\s+",
    re.I,
)
_QUALIFIER = re.compile(
    r"\b(?:core|headline|m/m|y/y|q/q|mom|yoy|qoq|3m/3m|3m/y|index|change|monthly|"
    r"initial|continuing|4-week avg\.?|4-week average|n\.?\s?s\.?\s?a\.?|nsa|s\.?\s?a\.?)"
    r"(?=\s|$)",
    re.I,
)

#: Releases that print several differently-named series at once.
ALIASES: dict[str, str] = {
    "nonfarm payrolls": "jobs", "private nonfarm payrolls": "jobs",
    "manufacturing payrolls": "jobs", "government payrolls": "jobs",
    "unemployment rate": "jobs", "u6 unemployment rate": "jobs",
    "average hourly earnings": "jobs", "average weekly hours": "jobs",
    "participation rate": "jobs", "employment": "jobs", "full employment": "jobs",
    "claimant count": "jobs", "average earnings": "jobs",
    "jobless claims": "claims",
    "retail control": "retail sales", "retail sales ex gas/autos": "retail sales",
    # One agency, one minute, one release: the euro area's harmonised index and
    # the BLS's PPI ex food, energy and trade print beside their headline.
    "hicp": "cpi", "cpi ex tobacco": "cpi", "ppi ex. food/energy/transport": "ppi",
    "pce price": "pce", "pce prices": "pce", "personal income": "pce",
    "personal spending": "pce",
}

#: Within an alias family, the series the release is known by.
_FAMILY_LEAD: dict[str, re.Pattern[str]] = {
    "jobs": re.compile(r"nonfarm payrolls|employment change", re.I),
    "claims": re.compile(r"\binitial\b", re.I),
}

#: Families where core, not headline, is the figure that is priced.
INFLATION = frozenset({"cpi", "ppi", "pce", "hicp"})

_LEVEL_NAME = re.compile(r"\bindex\b", re.I)
_PRICE = re.compile(r"\b(?:CPI|PPI|PCE|HICP|RPI|price)\b", re.I)
_UNADJUSTED = re.compile(r"\bn\.?\s?s\.?\s?a\b|\bnsa\b|,\s*s\.?\s?a\b", re.I)
_MONTHLY = re.compile(r"\b(?:m/m|q/q|mom|qoq)\b", re.I)
_ANNUAL = re.compile(r"\b(?:y/y|yoy)\b", re.I)


def family(event: str) -> str:
    """The release an event name belongs to, folded. Pure.

    "Core CPI m/m" → "cpi"; "German CPI y/y" → "cpi"; "Initial Jobless Claims"
    → "claims"; "Unemployment Rate" → "jobs"; "Cleveland CPI" → "cleveland cpi".
    """
    b = base(event)
    return ALIASES.get(b, b)


def base(event: str) -> str:
    """The name with its qualifiers off, before any alias — "Core CPI y/y" → "cpi". Pure."""
    s = re.sub(r"[,()]", " ", event or "").strip()
    s = _ADJECTIVE.sub("", s)
    s = _QUALIFIER.sub(" ", s)
    return " ".join(s.lower().split())


def is_level(event: str, *figures: str | None) -> bool:
    """A price index's level or an unadjusted twin — a series nobody prices. Pure.

    Only a PRICE index: "Empire State Manufacturing Index 11.2" is the number
    that is traded. And only when its figures are not percentages: "PCE Price
    Index m/m 0.3%" is a change, "Core CPI Index 337.77" is a level.
    """
    name = event or ""
    if _UNADJUSTED.search(name):
        return True
    if not (_LEVEL_NAME.search(name) and _PRICE.search(name)):
        return False
    return not any("%" in f for f in figures if f)


def lead_key(event: str, score: int, fam: str, level: bool) -> tuple[int, ...]:
    """Lower sorts first — see THE LEAD above. Pure."""
    want = _FAMILY_LEAD.get(fam)
    core = bool(re.search(r"\bcore\b", event or "", re.I))
    return (
        -int(score),
        1 if level else 0,
        0 if (want is None or want.search(event or "")) else 1,
        (0 if core else 1) if fam in INFLATION else (1 if core else 0),
        0 if _MONTHLY.search(event or "") else 1 if _ANNUAL.search(event or "") else 2,
    )


@dataclass
class Release(Generic[T]):
    """One release: the row it is titled by, its other series, and the folded ones."""

    family: str
    lead: T
    subs: list[T] = field(default_factory=list)
    levels: list[T] = field(default_factory=list)

    @property
    def rows(self) -> list[T]:
        return [self.lead, *self.subs, *self.levels]


def group(
    rows: Iterable[T],
    *,
    event: Callable[[T], str],
    when: Callable[[T], Any],
    country: Callable[[T], Any],
    score: Callable[[T], int],
    figures: Callable[[T], tuple[str | None, ...]],
) -> list[Release[T]]:
    """Group rows into releases, in the order each release first appears. Pure.

    A row with no time (`when` None) is never grouped: "sometime today" is not
    the same minute as anything.
    """
    buckets: dict[tuple[Any, ...], list[tuple[int, T]]] = {}
    order: list[tuple[Any, ...]] = []
    for i, r in enumerate(rows):
        at = when(r)
        k: tuple[Any, ...] = (country(r), at, family(event(r))) if at is not None else ("solo", i)
        if k not in buckets:
            buckets[k] = []
            order.append(k)
        buckets[k].append((i, r))
    out: list[Release[T]] = []
    for k in order:
        members = buckets[k]
        fam = family(event(members[0][1]))
        ranked = sorted(
            members,
            key=lambda m: (*lead_key(event(m[1]), score(m[1]), fam,
                                     is_level(event(m[1]), *figures(m[1]))), m[0]),
        )
        lead = ranked[0][1]
        # The others in the lead's order, the lead's own name first: under Core
        # PPI m/m, "Core y/y · m/m · y/y" and only then "PPI ex. Food/Energy/
        # Transport m/m · y/y" — interleaved, a bare "y/y" read as the ex-food one.
        rest = [r for _, r in ranked[1:]]
        rest.sort(key=lambda r: base(event(r)) != base(event(lead)))
        subs = [r for r in rest if not is_level(event(r), *figures(r))]
        levels = [r for r in rest if is_level(event(r), *figures(r))]
        out.append(Release(fam, lead, subs, levels))
    return out


# --------------------------------------------------------------------------
# What a print said, and what it means for each book.
#
# THE READ IS THE ECONOMY'S, NOT THE MARKET'S. "Hot" is a stronger economy —
# a beat on inflation, jobs or growth, and a MISS on unemployment, claims or
# inventories, where the higher number is the weaker one. Deciding what hot
# means for an index is the second step, and it is different per book: a hot
# CPI is a headwind for NQ through the discount rate and for gold through real
# yields; a hot payrolls is good for earnings and bad for cuts, so the 10Y
# decides which the index trades. Both steps live here so the stocks desk's
# Macro tab, the futures Calendar and the driver board say the same thing.
# --------------------------------------------------------------------------

#: A surprise within this share of the consensus reads in line.
INLINE_REL = 0.005
_INVERTED = re.compile(r"unemploy|jobless|claims|inventor", re.I)

BOOKS: tuple[str, ...] = ("NQ", "ES", "GC")


def read_of(title: str, surprise: float | None, consensus: float | None) -> str | None:
    """hot / cold / inline from the sign of the surprise. Pure."""
    if surprise is None or consensus is None:
        return None
    if abs(surprise) <= max(INLINE_REL * abs(consensus), 1e-9):
        return "inline"
    hot = surprise > 0
    if _INVERTED.search(title):
        hot = not hot
    return "hot" if hot else "cold"


def implication(read: str | None, themes: list[str] | None) -> dict[str, str] | None:
    """What a read means for NQ, ES and GC, by the release's theme. Pure.

    Rules of thumb a desk would say out loud, never a vote on their own: the
    driver board (drivers.py) counts only the inflation reads, where the first
    reaction is the least ambiguous. None without a read, and for a rates
    decision, whose "surprise" has no sign worth reading.
    """
    if read is None:
        return None
    th = set(themes or [])
    if "rates" in th and not th & {"inflation", "jobs", "growth"}:
        return None
    if read == "inline":
        line = "In line with consensus: nothing to reprice. Any reaction is positioning unwinding."
        return dict.fromkeys(BOOKS, line)
    hot = read == "hot"
    if "inflation" in th:
        eq = ("Hotter than priced: yields and the dollar bid first, a headwind for the index. "
              "Watch the 10Y and what the next FOMC prices." if hot else
              "Cooler than priced: yields ease and cuts come forward, a tailwind for the index "
              "unless growth is the worry.")
        gc = ("Hawkish for the Fed: real yields up, a headwind for gold." if hot else
              "Dovish: real yields down, supportive for gold.")
        return {"NQ": eq, "ES": eq, "GC": gc}
    if "jobs" in th:
        eq = ("A stronger labour market: good for earnings, bad for cuts. The 10Y decides which "
              "one the index trades." if hot else
              "A weaker labour market: cuts come forward, but a growth scare sells the index "
              "first. Watch whether yields fall faster than stocks.")
        gc = ("Hawkish: the Fed can wait, a headwind for gold." if hot else
              "Dovish: cuts come forward, supportive for gold.")
        return {"NQ": eq, "ES": eq, "GC": gc}
    if "growth" in th:
        eq = ("Stronger than priced: risk-on while yields stay quiet, a headwind if the 10Y "
              "jumps on it." if hot else
              "Weaker than priced: a growth scare. Cyclicals and small caps lead lower; the "
              "index follows if credit confirms.")
        gc = ("A headwind through yields." if hot else "Supportive: cuts come forward.")
        return {"NQ": eq, "ES": eq, "GC": gc}
    if "energy" in th:
        eq = ("A draw: oil bid, an inflation impulse, a touch of headwind through yields."
              if hot else "A build: oil softer, a touch of relief through yields.")
        return {"NQ": eq, "ES": eq, "GC": "Gold trades the dollar and yields, not inventories."}
    line = ("Stronger than priced. Read it through yields: a rise is a headwind for every "
            "book here." if hot else
            "Weaker than priced. Read it through yields: a fall supports the index and gold "
            "unless it is a growth scare.")
    return dict.fromkeys(BOOKS, line)
