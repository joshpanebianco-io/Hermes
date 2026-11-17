"""
The economic calendar — what prints, when, and what the street expects.

WHY THE CONSENSUS MATTERS MORE THAN THE PRINT. A number is not bullish or
bearish on its own; it is bullish or bearish against what was already in the
price. So every row here carries actual, consensus and previous together, and
a `surprise` computed from the first two — because the reaction is a function
of the gap, and reading it off three separate columns during the two seconds
after 08:30 is not a thing anyone does well.

RANKED, NOT FILTERED. A calendar that shows everything is a wall of Korean
industrial production; a calendar that shows only the US misses the BoJ
decision that moves the yen that moves the Nasdaq. Every row is kept and
scored, and the UI shows the top of the list by default.
"""

from __future__ import annotations

import math
import re
import time
from collections.abc import Iterable
from datetime import UTC, date, datetime, timedelta
from typing import Any
from zoneinfo import ZoneInfo

from ..config import BROWSER_UA
from ..http import SourceStatus, clean_text, fetch, json_body
from ..releases import implication, read_of
from ..sessions import desk_window

ET = ZoneInfo("America/New_York")
NASDAQ = "https://api.nasdaq.com/api/calendar/economicevents?date={d}"

# The releases that actually reprice the front end of the curve. Tier 1 stops
# the tape; tier 2 is watched; everything else is context.
TIER1 = re.compile(
    r"\bCPI\b|consumer price|\bPCE\b|personal consumption|nonfarm|non-farm|payroll|"
    r"unemployment rate|\bFOMC\b|federal funds|rate decision|interest rate decision|"
    r"\bGDP\b|initial jobless|\bISM\b.*(?:manufacturing|services|non-manufacturing)|"
    r"retail sales|\bPPI\b|producer price", re.I,
)
TIER2 = re.compile(
    r"\bPMI\b|consumer confidence|consumer sentiment|durable goods|housing starts|"
    r"building permits|existing home|new home|factory orders|trade balance|"
    r"industrial production|capacity utilization|\bJOLTS\b|job openings|"
    r"crude oil inventor|natural gas storage|\bADP\b|employment change|"
    r"treasury (?:auction|refunding)|beige book|minutes", re.I,
)

# A FED OFFICIAL SPEAKING IS WATCHED, NOT A PRINT (2026-11-14). "FOMC" in the name is
# tier one, so "FOMC Member Barr Speaks" scored five, beside CPI and the decision
# itself: the Macro calendar read High 44, Med 2, Low 8, eleven of the week's High rows
# were speeches, and the Scanner's "next event worth stopping for" could be a governor
# at a research conference. A member is three, with the PMIs and the claims. The Chair
# is four, the High tier's lower step: a Chair's remarks can move the front end on
# their own, and a decision still outranks them. It also fixed the other half: Nasdaq's
# "Fed Chair Powell Speaks" has no "FOMC" in it and scored two.
FED_SPEAKS = re.compile(
    r"\b(?:FOMC|Fed|Federal Reserve)\b.*\b(?:speaks?|speech|testif\w*|remarks)\b", re.I)
FED_CHAIR = re.compile(r"(?<!vice )(?<!vice-)\bchair(?:man|woman)?\b", re.I)

# Countries whose prints move the books on this desk. Everything else is scored
# down rather than dropped — a Chinese GDP miss is a Nasdaq event even though
# the US calendar does not list it.
#
# AUSTRALIA AND NEW ZEALAND SIT AT 2, not 1. The first cut weighted everything
# by how much it moves US index futures, which is the right scale for a desk
# that only trades New York — and this one also trades Asia and London. An RBA
# decision is the largest scheduled event in an Asia session and was scoring 3,
# below the `core` threshold, so it never appeared in the default calendar for
# the session it defines.
MAJOR = {
    "United States": 3,
    "Euro Zone": 2, "Germany": 2, "United Kingdom": 2,
    "China": 2, "Japan": 2, "Australia": 2, "New Zealand": 2,
    "France": 1, "Italy": 1, "Spain": 1, "Switzerland": 1,
    "Canada": 1, "South Korea": 1, "India": 1, "Hong Kong": 1, "Taiwan": 1,
}


def _num(s: Any) -> float | None:
    """'-0.4%' → -0.4. Blank, '&nbsp;' and '-' all mean 'not published'."""
    if s is None:
        return None
    t = clean_text(str(s)).replace(",", "").strip()
    if not t or t in {"-", "--", "N/A"}:
        return None
    m = re.search(r"-?\d+(?:\.\d+)?", t)
    if not m:
        return None
    try:
        v = float(m.group(0))
    except ValueError:
        return None
    if "K" in t.upper() and "%" not in t:
        v *= 1_000
    elif "M" in t.upper() and "%" not in t:
        v *= 1_000_000
    return v


# German CPI is published state by state before the national print, so a single
# morning yields Baden-Württemberg, Bavaria, Brandenburg, Hesse, North
# Rhine-Westphalia and Saxony — six rows that all match the inflation keywords
# and none of which is the number anyone trades. Same for the regional Fed
# indices, which are surveys rather than releases.
REGIONAL = re.compile(
    r"baden|wuerttemberg|württemberg|bavaria|brandenburg|hesse|saxony|"
    r"north rhine|westphalia|lower saxony|schleswig|thuringia|mecklenburg|"
    r"rhineland|saarland|bremen|hamburg cpi", re.I,
)


def score(country: str, event: str) -> int:
    """0–5. How much of the desk's attention this deserves.

    MULTIPLICATIVE IN SPIRIT, NOT ADDITIVE. The first cut added a country
    weight to a tier weight and capped at five, which let German regional CPI
    (2 + 3) tie US CPI (3 + 3, capped) — so a state-level print nobody trades
    sat at the top of the calendar beside payrolls. Tier decides the band and
    country decides where inside it, which cannot produce that inversion.
    """
    if REGIONAL.search(event):
        return 0
    weight = MAJOR.get(country, 0)
    us = country == "United States"
    if us and FED_SPEAKS.search(event):
        return 4 if FED_CHAIR.search(event) else 3
    if TIER1.search(event):
        return 5 if us else (4 if weight >= 2 else 3)
    if TIER2.search(event):
        return 3 if us else (2 if weight >= 2 else 1)
    return min(weight, 2) if weight else 0


# ---------------------------------------------------------------- themes
#
# WHAT A RELEASE IS ABOUT, so the calendar can be filtered down to the things
# that actually reach NQ, ES and GC rather than by country alone. A Chinese PMI
# and a US ISM are the same theme and the same trade; filtering by "United
# States" would keep one and drop the other.
THEMES: list[tuple[str, re.Pattern[str]]] = [
    ("inflation", re.compile(
        r"\bCPI\b|consumer price|\bPPI\b|producer price|\bPCE\b|inflation|"
        r"price index|deflator|wage growth", re.I)),
    ("jobs", re.compile(
        r"payroll|nonfarm|non-farm|unemployment|jobless|\bJOLTS\b|job openings|"
        r"\bADP\b|employment|claimant|labou?r (?:force|market)", re.I)),
    ("rates", re.compile(
        r"\bFOMC\b|rate decision|interest rate|federal funds|monetary policy|"
        r"central bank|\bECB\b|\bBOJ\b|\bBoE\b|minutes|beige book|"
        r"treasury (?:auction|refunding)|bond auction", re.I)),
    ("growth", re.compile(
        r"\bGDP\b|\bISM\b|\bPMI\b|retail sales|industrial production|factory orders|"
        r"durable goods|capacity utilization|business (?:confidence|climate)|"
        r"consumer (?:confidence|sentiment|spending)|housing starts|building permits|"
        r"home sales|construction", re.I)),
    ("energy", re.compile(
        r"crude oil|oil inventor|petroleum|natural gas|gas storage|\bEIA\b|"
        r"rig count|gasoline", re.I)),
    ("dollar", re.compile(
        r"trade balance|current account|capital flows|reserves|"
        r"exchange rate|intervention", re.I)),
]


def themes_of(event: str) -> list[str]:
    """Every theme a release touches. Pure; a release can carry more than one."""
    return [name for name, pat in THEMES if pat.search(event)]


def is_core(country: str, event: str, sc: int) -> bool:
    """Does this reach NQ / ES / GC?

    THE TEST IS NOT "IS IT AMERICAN". A US housing-starts print is a US release
    that moves nothing on this desk; a Chinese GDP miss is a Nasdaq event that a
    country filter would throw away. So it is scored on theme and weight
    together: a rates, inflation or jobs print from anywhere that matters, or
    anything a major economy publishes that already scored highly.

    `sc > 0` GUARDS THE THEME BRANCH, and it has to. `score` returns 0 for the
    German state-level CPI releases — six of them a morning, none of which is
    the number anyone trades — but every one carries the "inflation" theme and
    Germany's weight of 2, so without this they walked straight back into the
    default view through the theme door after being filtered out of the
    ranking. A release the scorer has rejected outright cannot be core.
    """
    if sc <= 0:
        return False
    th = set(themes_of(event))
    if th & {"inflation", "jobs", "rates"} and MAJOR.get(country, 0) >= 2:
        return True
    return sc >= 4


# ---------------------------------------------------------------- region
#
# GROUPED BY THE DESK THAT TRADES IT, not by continent. Australia and New
# Zealand sit under APAC with Japan and China because an RBA decision prints
# inside the Asia session and is read by whoever is trading it — which for this
# owner is sometimes the case. Switzerland and Norway sit under EU for the same
# reason: they print into the London morning.
REGIONS: dict[str, str] = {
    "United States": "us",
    "United Kingdom": "uk",
    "Euro Zone": "eu", "Germany": "eu", "France": "eu", "Italy": "eu",
    "Spain": "eu", "Netherlands": "eu", "Belgium": "eu", "Austria": "eu",
    "Portugal": "eu", "Ireland": "eu", "Greece": "eu", "Finland": "eu",
    "Switzerland": "eu", "Sweden": "eu", "Norway": "eu", "Denmark": "eu",
    "Poland": "eu", "Czech Republic": "eu", "Hungary": "eu", "Turkey": "eu",
    "Japan": "apac", "China": "apac", "Hong Kong": "apac", "South Korea": "apac",
    "Australia": "apac", "New Zealand": "apac", "India": "apac",
    "Singapore": "apac", "Taiwan": "apac", "Indonesia": "apac",
    "Malaysia": "apac", "Thailand": "apac", "Philippines": "apac", "Vietnam": "apac",
}

# The trading session a release prints into — the clock's partition
# (sessions.desk_window): Asia from the reopen, London 07:00-10:00 London, the
# pre-market from there to the cash open, New York. They were four ET
# constants here, with London from 03:00 ET: UK GDP at 07:00 London (02:00 ET)
# printed "in the Asia session" (review, 2026-10-14), and every boundary was
# an hour out in the mismatch weeks. The ranges panel draws the owner's boxes
# instead (sessions.BOXES), which overlap and leave gaps; a print needs one
# answer, so the tag keeps the partition and the 04:00-05:00 hour is London's.
_SESSION_OF_WINDOW: dict[str | None, str] = {
    "asia": "asia",
    "london": "london",
    "premkt": "premkt",
    "ny": "ny",
}


def region_of(country: str) -> str:
    return REGIONS.get(country, "other")


def session_of(when_et: datetime | None) -> str | None:
    """Which trading session this release prints into. None when untimed."""
    if when_et is None:
        return None
    # 16:00–18:00 ET: cash is shut and Globex has not reopened, or is about to halt.
    return _SESSION_OF_WINDOW.get(desk_window(when_et), "closed")


def parse_day(doc: Any, day: date) -> list[dict[str, Any]]:
    """One Nasdaq day payload → calendar rows. Pure."""
    rows = ((doc or {}).get("data") or {}).get("rows") or []
    out: list[dict[str, Any]] = []
    for r in rows:
        event = clean_text(str(r.get("eventName") or ""))
        country = clean_text(str(r.get("country") or ""))
        if not event:
            continue
        # THE FIELD IS CALLED `gmt` AND THE VALUES ARE ET.
        #
        # Nasdaq's own column header for it is just "Time", and every value
        # checks out as US Eastern rather than UTC: Chicago PMI arrives as
        # 09:45 and releases at 09:45 ET; the Dallas Fed index as 10:30, which
        # is its 10:30 ET slot; bill auctions as 11:30, which is theirs. It
        # holds outside the US too — Japan industrial production arrives as
        # 19:50, and 19:50 ET is 08:50 JST the next morning, which is when it
        # prints. Treating the name at face value and converting UTC to ET put
        # the entire calendar four hours early, which read as plausible right
        # up until an ISM appeared at 06:00.
        raw_time = clean_text(str(r.get("gmt") or ""))
        when_et = None
        m = re.match(r"(\d{1,2}):(\d{2})", raw_time)
        if m:
            when_et = datetime(
                day.year, day.month, day.day, int(m.group(1)), int(m.group(2)), tzinfo=ET
            )

        out.append(_row(
            event, country, day, when_et,
            (_num(r.get("actual")), clean_text(str(r.get("actual") or "")) or None),
            (_num(r.get("consensus")), clean_text(str(r.get("consensus") or "")) or None),
            (_num(r.get("previous")), clean_text(str(r.get("previous") or "")) or None),
            # The plain-English gloss Nasdaq ships. Genuinely useful at
            # 08:29 for a release you do not follow closely.
            clean_text(str(r.get("description") or ""))[:260] or None,
        ))
    return out


Fig = tuple[float | None, str | None]


def _row(event: str, country: str, day: date, when_et: datetime | None,
         actual_f: Fig, cons_f: Fig, prev_f: Fig, note: str | None) -> dict[str, Any]:
    """One calendar row, whichever feed it came from: a figure is (the number, the
    text it arrived as). Pure."""
    when_utc = when_et.astimezone(UTC) if when_et else None
    actual, cons, prev = actual_f[0], cons_f[0], prev_f[0]
    sc = score(country, event)
    return {
        "event": event,
        "country": country,
        "region": region_of(country),
        "session": session_of(when_et),
        "themes": themes_of(event),
        "core": is_core(country, event, sc),
        "date": day.isoformat(),
        "et": when_et.strftime("%H:%M") if when_et else None,
        "utc": when_utc.isoformat() if when_utc else None,
        "ts": when_utc.timestamp() if when_utc else None,
        "actual": actual,
        "actual_raw": actual_f[1],
        "consensus": cons,
        "consensus_raw": cons_f[1],
        "previous": prev,
        "previous_raw": prev_f[1],
        # Signed gap to consensus. None when either side is missing —
        # never zero, which would read as "came in exactly on target".
        "surprise": (actual - cons) if (actual is not None and cons is not None) else None,
        "released": actual is not None,
        # hot / cold / inline once it has printed (releases.read_of) —
        # the economy's word, which the futures Calendar shows and
        # the driver board counts; what it means per book is
        # releases.implication, composed where it is read.
        "read": read_of(event, actual - cons, cons)
        if (actual is not None and cons is not None) else None,
        # And what that read means for NQ, ES and GC, in the server's
        # words (releases.implication), so the Calendar's click-through
        # prints the same sentences the driver board counts.
        "meaning": implication(read_of(event, actual - cons, cons), themes_of(event))
        if (actual is not None and cons is not None) else None,
        "score": sc,
        "note": note,
    }


# ----------------------------------------------------------------- the date
#
# NASDAQ'S `?date=D` CAN LIST ANOTHER DAY'S RELEASES (found 2026-10-13: every
# request returned the day BEFORE the one asked for — `?date=2026-10-15` held
# Wednesday's MBA applications, CPI and Beige Book, and the terminal printed
# Wednesday's CPI as Thursday's). Nothing in the payload names its day — the
# `asOf` is the fetch date — so the day is read off the weekly US releases that
# always print on the same weekday, and each payload is filed under the day
# its rows are for. Voted across every payload in a pass, so one holiday week
# moving a release a day cannot flip it; if Nasdaq fixes its end, the vote
# follows on the next pass with no change here.

#: Weekly US releases and the weekday they print on (Mon = 0).
ANCHORS: dict[str, int] = {
    "mba mortgage applications": 2,
    "initial jobless claims": 3,
    "continuing jobless claims": 3,
    "fed's balance sheet": 3,
    "baker hughes oil rig count": 4,
}
#: What Nasdaq was doing when this was written, for a pass with no anchors in
#: it (a holiday-only window) before any pass has voted.
DEFAULT_SHIFT = -1
_last_shift: int | None = None


def date_shift(payloads: list[tuple[date, Any]]) -> int | None:
    """Days between the date requested and the day the payload's rows are for
    (−1: `?date=D` lists D−1), voted by ANCHORS; None when the vote is thin or
    split. Pure."""
    votes = {-1: 0, 0: 0, 1: 0}
    for d, doc in payloads:
        rows = ((doc or {}).get("data") or {}).get("rows") or []
        for r in rows:
            if clean_text(str(r.get("country") or "")) != "United States":
                continue
            wd = ANCHORS.get(clean_text(str(r.get("eventName") or "")).lower())
            if wd is None:
                continue
            for sh in votes:
                if (d + timedelta(days=sh)).weekday() == wd:
                    votes[sh] += 1
    best = max(votes, key=lambda k: votes[k])
    rest = max(v for k, v in votes.items() if k != best)
    return best if votes[best] >= 2 and votes[best] > rest else None


def _pct_val(r: dict[str, Any]) -> float | None:
    """The row's figure when it is a percentage — previous first, then the
    consensus, then the actual — else None."""
    for k in ("previous", "consensus", "actual"):
        raw = str(r.get(f"{k}_raw") or "")
        if raw.endswith("%") and r.get(k) is not None:
            return abs(float(r[k]))
    return None


_SPAN_END = re.compile(r"\b(?:m/m|y/y|q/q)$", re.I)


def label_variants(rows: list[dict[str, Any]]) -> None:
    """Name the two halves of a paired release (in place).

    Nasdaq lists CPI twice at 08:30 under one name — the month-on-month and
    the year-on-year figure — and Existing Home Sales twice at 10:00 — the
    level and its change; nothing in the row says which is which, so the board
    showed "Core CPI" twice with different numbers. The figures do say it: of
    two percentages the smaller is the monthly change (0.2% against 2.5%), and
    beside a level the percentage is the change. A pair the figures cannot
    separate is left as it is rather than guessed at.
    """
    groups: dict[tuple[Any, ...], list[dict[str, Any]]] = {}
    for r in rows:
        groups.setdefault((r["country"], r["event"], r["utc"], r["date"]), []).append(r)
    for g in groups.values():
        # A name that already says which it is has nothing to be told: TradingView's
        # rows carry "m/m" and "y/y", and the UK's monthly and quarterly GDP both
        # arrive as "GDP y/y" at 07:00 (they read "GDP y/y m/m" until 2026-11-11).
        if len(g) != 2 or _SPAN_END.search(g[0]["event"]):
            continue
        a, b = (_pct_val(x) for x in g)
        if a is not None and b is not None and a != b:
            small, big = (g[0], g[1]) if a < b else (g[1], g[0])
            small["event"] += " m/m"
            big["event"] += " y/y"
        elif (a is None) != (b is None):
            (g[0] if a is not None else g[1])["event"] += " m/m"

# ------------------------------------------------------- the second source
#
# TRADINGVIEW'S CALENDAR, FOR WHEN NASDAQ REFUSES (owner, 2026-11-11: "do what you
# recommend best"). Nasdaq answered HTTP 403 from 05:49 ET on Tue 10 Nov 2026 and
# was still refusing a day later. The copy held kept the schedule, but it had been
# read before 08:30, so the desk went through a CPI day with no CPI: the prints
# panel said nothing scored had printed and the driver board never counted a hot
# inflation number (0.4% m/m against 0.3%, core 0.3% against 0.2%). A stale
# schedule is a degraded calendar; a release with no actual is a wrong one.
#
# So when Nasdaq is not delivering, the window is read from the calendar
# TradingView's own site draws: one request, exact UTC instants (no date to vote
# on), and actual, forecast and previous as numbers with a unit and a scale.
# NASDAQ STAYS FIRST when it answers, because every name downstream was written
# against its vocabulary and the owner has read its rows for a month. This is the
# stand-in, and the status row says when it is the one in use.
#
# ITS NAMES ARE TRANSLATED, NOT TRUSTED. TradingView calls CPI "Inflation Rate",
# the trade balance "Balance of Trade", crude inventories "EIA Crude Oil Stocks
# Change", and tags a reading "Prel" or "Final". The tiers above, the themes,
# releases.family and the Fed-speaker rule in tools.py all read the NAME, so each
# title is put into the words Nasdaq uses (`tv_event`) before anything scores it.
# The table below is the names that differed when the two feeds were laid side by
# side for the week of 9 Nov 2026, the same releases at the same minutes.
#
# WHAT IT DOES NOT HAVE. No speeches and no holidays: "FOMC Member Daly Speaks"
# is Nasdaq's row. The Board's own calendar (sources/fedcal.py) is already read
# here, so its speeches are added to these rows (`fed_speech_rows`, by the
# collector); the regional presidents are not on the Board's calendar and are
# missing while this is the source in use.
#
# AND IT LISTS FAR MORE THAN ANYONE READS: four rows an auction, twenty for a
# WASDE report, the MBA's rate tables. Those are dropped by name, and its own
# importance flag (-1, 0, 1) drops the bottom tier unless the name is one the
# tiers above know.

TRADINGVIEW = ("https://economic-calendar.tradingview.com/events"
               "?from={lo}&to={hi}&countries={cc}")
#: What the app sends TradingView everywhere (sources/pool.py, sources/tvnews.py).
TV_HEADERS = {
    "Accept": "application/json",
    "Origin": "https://www.tradingview.com",
    "Referer": "https://www.tradingview.com/",
}
#: The code TradingView files each country under: every country REGIONS or MAJOR
#: knows, so the stand-in is asked for the same world Nasdaq lists.
ISO2: dict[str, str] = {
    "United States": "US", "United Kingdom": "GB", "Euro Zone": "EU", "Germany": "DE",
    "France": "FR", "Italy": "IT", "Spain": "ES", "Netherlands": "NL", "Belgium": "BE",
    "Austria": "AT", "Portugal": "PT", "Ireland": "IE", "Greece": "GR", "Finland": "FI",
    "Switzerland": "CH", "Sweden": "SE", "Norway": "NO", "Denmark": "DK", "Poland": "PL",
    "Czech Republic": "CZ", "Hungary": "HU", "Turkey": "TR", "Japan": "JP", "China": "CN",
    "Hong Kong": "HK", "South Korea": "KR", "Australia": "AU", "New Zealand": "NZ",
    "India": "IN", "Singapore": "SG", "Taiwan": "TW", "Indonesia": "ID", "Malaysia": "MY",
    "Thailand": "TH", "Philippines": "PH", "Vietnam": "VN", "Canada": "CA",
}
_COUNTRY_OF = {code: name for name, code in ISO2.items()}
#: A row can arrive under the feed's raw key, "United States-<set>-<name>".
_TV_LANDS = frozenset(ISO2) | {"Euro Area"}

#: "Prel", "Final": which reading it is. Taken off the name (releases.family folds
#: a release by its name, and "cpi final" is not `cpi`) and kept on the note.
_TV_VINTAGE = re.compile(r"\s+(Final|Prel|Flash|Adv|2nd Est|3rd Est)$", re.I)
#: TradingView's title → Nasdaq's words, first match of each, in order.
_TV_RENAME: list[tuple[re.Pattern[str], str]] = [
    (re.compile(r"^Core Inflation Rate\b", re.I), "Core CPI"),
    (re.compile(r"^Harmoni[sz]ed Inflation Rate\b", re.I), "HICP"),
    (re.compile(r"^Inflation Rate\b", re.I), "CPI"),
    (re.compile(r"^Consumer Price Index\b", re.I), "CPI Index"),
    (re.compile(r"^Core Consumer Prices\b", re.I), "Core CPI Index"),
    (re.compile(r"^CPI seasonally adjusted\b", re.I), "CPI Index, s.a"),
    (re.compile(r"^Non ?Farm Payrolls Private\b", re.I), "Private Nonfarm Payrolls"),
    (re.compile(r"^Non Farm Payrolls\b", re.I), "Nonfarm Payrolls"),
    (re.compile(r"^U-6 Unemployment Rate\b", re.I), "U6 Unemployment Rate"),
    (re.compile(r"^GDP Growth Annualized\b", re.I), "GDP Annualized"),
    (re.compile(r"^GDP Growth Rate\b", re.I), "GDP"),
    (re.compile(r"^Balance of Trade\b", re.I), "Trade Balance"),
    (re.compile(r"^EIA Crude Oil Stocks Change\b", re.I), "Crude Oil Inventories"),
    (re.compile(r"^EIA Gasoline Stocks Change\b", re.I), "Gasoline Inventories"),
    (re.compile(r"^EIA Natural Gas Stocks Change\b", re.I), "Natural Gas Storage"),
    (re.compile(r"^API Crude Oil Stock Change\b", re.I), "API Weekly Crude Oil Stock"),
    (re.compile(r"^Retail Sales Control Group\b", re.I), "Retail Control"),
    # Nasdaq's "Thomson Reuters IPSOS PCSI". Spelt out it reads as THE consumer
    # sentiment print to the tiers, and stood as the session's one print that way.
    (re.compile(r"^LSEG/Ipsos Primary Consumer Sentiment Index\b", re.I), "LSEG/Ipsos PCSI"),
    # The BLS's third PPI, under the name releases.ALIASES folds into the PPI row.
    (re.compile(r"^PPI Ex Food,? Energy and Trade(?: Services)?\b", re.I),
     "PPI ex. Food/Energy/Transport"),
    (re.compile(r"\bSpeech$", re.I), "Speaks"),
]
_TV_SPAN: list[tuple[re.Pattern[str], str]] = [
    (re.compile(r"\b(?:MoM|MM)\b"), "m/m"),
    (re.compile(r"\b(?:YoY|YY)\b"), "y/y"),
    (re.compile(r"\bQoQ\b"), "q/q"),
]
#: A bare price index is its LEVEL ("CPI 337.511"): named so releases.is_level
#: folds it away beside the changes anyone prices.
_TV_LEVEL = re.compile(r"(?:Core )?(?:CPI|PPI|PCE|HICP)")
#: The detail rows of a release nobody on this desk reads line by line.
_TV_NOISE = re.compile(
    r"Auction (?:Allotted at High|Bid-to-Cover|Total Accepted)$|"
    r"^MBA .*(?:Contract Rate|Effective Rate|Points)$|"
    r"^(?:WASDE|USDA|NOPA)\b|^CPI-W$|^EIA (?:Ethanol|Crude Oil Exports)\b|^PPI Machinery",
    re.I,
)
#: Bottom-tier by TradingView's flag and still wanted: an auction's own row (its
#: yield), the claims that print beside the initial ones, and the harmonised CPI,
#: which rides under its country's CPI (releases.ALIASES).
_TV_KEEP = re.compile(r"(?:Bill|Note|Bond|TIPS) Auction$|jobless claims|^HICP\b", re.I)
_TV_MONEY = frozenset({"$", "€", "¥", "£"})
_TV_ISO = "%Y-%m-%dT%H:%M:%S.000Z"


def tv_event(title: str, unit: str | None = None) -> tuple[str, str | None]:
    """A TradingView title in the words Nasdaq uses, and which reading it is
    ("Prel", "Final") when the title said. Pure.

    "Core Inflation Rate MoM" → "Core CPI m/m"; "Inflation Rate YoY Final" →
    ("CPI y/y", "Final"); "Balance of Trade" → "Trade Balance"; "CPI" with a
    figure that is not a percentage → "CPI Index".
    """
    t = clean_text(str(title or "")).rstrip("* ").strip()
    parts = t.split("-")
    if len(parts) >= 3 and parts[0].strip() in _TV_LANDS:
        t = parts[-1].strip()
    vintage = None
    m = _TV_VINTAGE.search(t)
    if m:
        vintage, t = m.group(1), t[: m.start()]
    for pat, to in _TV_RENAME:
        t = pat.sub(to, t, count=1)
    for pat, to in _TV_SPAN:
        t = pat.sub(to, t)
    t = " ".join(t.split())
    if _TV_LEVEL.fullmatch(t) and unit != "%":
        t += " Index"
    return t, vintage


def _tv_fig(v: Any, unit: str | None, scale: str | None) -> Fig:
    """One TradingView figure as (the number, the text a row carries), in the terms
    `_num` reads Nasdaq's in: thousands and millions multiplied out, a percentage
    ending in "%" (label_variants and releases.is_level look for it). Pure."""
    if isinstance(v, bool) or not isinstance(v, (int, float)) or not math.isfinite(v):
        return None, None
    x = float(v)
    body, sign = f"{abs(x):,.10g}", "-" if x < 0 else ""
    if unit == "%":
        raw = f"{sign}{body}%"
    else:
        raw = f"{sign}{unit if unit in _TV_MONEY else ''}{body}{scale or ''}"
    return x * (1_000.0 if scale == "K" else 1_000_000.0 if scale == "M" else 1.0), raw


def tv_body(body: bytes) -> str | None:
    """TradingView's calendar JSON, or why not."""
    bad = json_body(body)
    if bad:
        return bad
    return None if b'"result"' in body[:400] else "not a calendar reply"


def parse_tradingview(doc: Any, lo: date, hi: date) -> list[dict[str, Any]]:
    """TradingView's calendar payload → the rows for the ET days `lo`..`hi`, in the
    shape `parse_day` makes and the names Nasdaq uses. Pure."""
    events = doc.get("result") if isinstance(doc, dict) else None
    out: list[dict[str, Any]] = []
    for e in events if isinstance(events, list) else []:
        if not isinstance(e, dict):
            continue
        country = _COUNTRY_OF.get(str(e.get("country") or "").upper())
        if country is None:
            continue
        unit = e.get("unit") if isinstance(e.get("unit"), str) else None
        scale = e.get("scale") if isinstance(e.get("scale"), str) else None
        event, vintage = tv_event(str(e.get("title") or ""), unit)
        if not event or _TV_NOISE.search(event):
            continue
        imp = e.get("importance")
        if (not isinstance(imp, (int, float)) or imp < 0) and not (
                TIER1.search(event) or TIER2.search(event) or _TV_KEEP.search(event)):
            continue
        try:
            when = datetime.fromisoformat(str(e.get("date") or "").replace("Z", "+00:00"))
        except ValueError:
            continue
        when_et = (when if when.tzinfo else when.replace(tzinfo=UTC)).astimezone(ET)
        if not lo <= when_et.date() <= hi:
            continue
        note = clean_text(str(e.get("comment") or ""))
        if vintage:
            note = f"{vintage} reading. {note}".strip()
        out.append(_row(
            event, country, when_et.date(), when_et,
            _tv_fig(e.get("actual"), unit, scale),
            _tv_fig(e.get("forecast"), unit, scale),
            _tv_fig(e.get("previous"), unit, scale),
            note[:260] or None,
        ))
    return out


_FED_SUFFIX = frozenset({"jr", "jr.", "sr", "sr.", "ii", "iii"})


def fed_speech_rows(fed: Iterable[dict[str, Any]], lo: date, hi: date,
                    have: Iterable[dict[str, Any]] = ()) -> list[dict[str, Any]]:
    """The Board's scheduled speeches and testimony (sources/fedcal.py rows) as
    calendar rows for `lo`..`hi`, named the way Nasdaq names them. Pure.

    "Speech - Governor Christopher J. Waller" → "FOMC Member Waller Speaks", and
    the Chair is "FOMC Chair …": the tiers read "FOMC", which is what has always
    put a Fed speaker at the top of this calendar. A speaker a row in `have`
    already names at that minute is left out.
    """
    taken = {(str(r.get("utc") or "")[:16], str(r.get("event") or "").lower()) for r in have}
    out: list[dict[str, Any]] = []
    for r in fed:
        ts = r.get("ts")
        if r.get("kind") not in ("Speech", "Testimony") or not isinstance(ts, (int, float)):
            continue
        when_et = datetime.fromtimestamp(float(ts), ET)
        if not lo <= when_et.date() <= hi:
            continue
        title = str(r.get("title") or "")
        who = title.split(" - ", 1)[1] if " - " in title else title
        words = [w.strip(",.") for w in who.split()]
        while words and words[-1].lower() in _FED_SUFFIX:
            words.pop()
        if not words:
            continue
        last = words[-1]
        # "Chairman Kevin Warsh" as well as "Chair Jerome H. Powell": `\bchair\b` alone
        # missed the first, and the Chair was listed as a member (2026-11-14).
        chair = bool(FED_CHAIR.search(who))
        verb = "Testifies" if r.get("kind") == "Testimony" else "Speaks"
        event = f"FOMC {'Chair' if chair else 'Member'} {last} {verb}"
        minute = when_et.astimezone(UTC).isoformat()[:16]
        if any(at == minute and last.lower() in name for at, name in taken):
            continue
        none: Fig = (None, None)
        out.append(_row(event, "United States", when_et.date(), when_et, none, none, none,
                        clean_text(str(r.get("note") or ""))[:260] or None))
    return out


# --------------------------------------------------------------- the pass

#: Which calendar the last pass read ("nasdaq" or "tradingview"), and its window.
_source = "nasdaq"
_window: tuple[date, date] | None = None
#: Nasdaq is not asked again before this (epoch), and why: a host that is refusing
#: is asked twice an hour, not seven times every ten minutes.
NASDAQ_RETRY_SEC = 1800.0
_nasdaq_wait = 0.0
_nasdaq_why = ""


def source() -> str:
    """The feed the last `collect` returned rows from."""
    return _source


def with_fed_speeches(rows: list[dict[str, Any]],
                      fed: Iterable[dict[str, Any]]) -> list[dict[str, Any]]:
    """`rows` with the Board's speeches added, in time order, when the last pass
    read TradingView (which lists none). Otherwise `rows` as they are."""
    if _source != "tradingview" or _window is None:
        return rows
    extra = fed_speech_rows(fed, _window[0], _window[1], rows)
    if not extra:
        return rows
    return sorted([*rows, *extra], key=lambda x: (x.get("ts") or 0))


def _finish(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Exact duplicates out, the paired releases named, in time order."""
    # EXACT duplicates only. Nasdaq lists the same event name twice in a slot
    # when it publishes both a month-on-month and a year-on-year figure, and
    # nothing in the payload distinguishes them — so dropping by (country,
    # event, time) would silently discard a real release. Keyed on the values
    # too, which removes only rows that are genuinely the same row twice.
    seen: set[tuple[Any, ...]] = set()
    unique: list[dict[str, Any]] = []
    for row in rows:
        k = (row["country"], row["event"], row["utc"], row["actual_raw"],
             row["consensus_raw"], row["previous_raw"])
        if k in seen:
            continue
        seen.add(k)
        unique.append(row)
    label_variants(unique)
    unique.sort(key=lambda x: (x.get("ts") or 0))
    return unique


def _from_nasdaq(today: date, lo: date, hi: date, days_ahead: int,
                 days_back: int) -> tuple[list[dict[str, Any]], SourceStatus, bool]:
    """Nasdaq's days for the window → (rows, status, whether it is NOT delivering).

    Not delivering: two or more of the days that can still change (yesterday on)
    failed or came back as the copy on disk. One slow day is a slow day."""
    global _last_shift
    st = SourceStatus("Economic calendar")
    rows: list[dict[str, Any]] = []
    failed = 0
    behind = 0
    # One day wider each side than the window: whichever way the dates run,
    # every day in it is in some payload.
    span = range(-days_back - 1, days_ahead + 2)
    docs: list[tuple[date, Any]] = []

    for offset in span:
        d = today + timedelta(days=offset)
        r = fetch(
            NASDAQ.format(d=d.isoformat()),
            key=f"cal_{d.isoformat()}",
            # Settled days are cached hard; anything that might hold today's
            # releases refreshes, because that is where an `actual` appears
            # the moment it prints — and with the dates off by one, the
            # payload asked for yesterday or tomorrow can be today's.
            # A day more than three ahead is a schedule, not a print: three hours.
            ttl_sec=86400.0 if offset < -1 else 3 * 3600.0 if offset > FULL_DAYS else 540.0,
            ua=BROWSER_UA,
            timeout=20,
            headers={"Accept": "application/json"},
            # A settled day may serve a week-old copy. The rest may serve one two
            # days old. IT WAS SIX HOURS, "where actuals land", and that threw away
            # the schedule with the actuals (audit, 2026-11-11): Nasdaq refused the
            # feed from 05:49 ET on 10 Nov, the copy held was dropped at noon, and
            # the desk read "None scheduled" on a day CPI printed at 08:30. A
            # release's time does not go stale the way its figure does, and the
            # status already says how old the copy is, so the page keeps the
            # schedule and marks it stale rather than showing nothing.
            stale_max_sec=7 * 86400.0 if offset < -1 else 48 * 3600.0,
            validate=json_body,
        )
        st.absorb(r)
        if offset >= -1 and (not r.ok or r.source == "stale"):
            behind += 1
        if not r.ok:
            failed += 1
            st.error = st.error or r.error
            continue
        try:
            docs.append((d, r.json()))
        except ValueError as e:
            failed += 1
            st.error = st.error or f"parse: {e}"

    voted = date_shift(docs)
    if voted is not None:
        _last_shift = voted
    shift = _last_shift if _last_shift is not None else DEFAULT_SHIFT
    for d, doc in docs:
        day = d + timedelta(days=shift)
        if not lo <= day <= hi:
            continue
        try:
            rows.extend(parse_day(doc, day))
        except (ValueError, TypeError, AttributeError) as e:
            failed += 1
            st.error = st.error or f"parse: {e}"

    rows = _finish(rows)
    st.items = len(rows)
    if failed:
        st.notes.append(f"{failed} of {len(list(span))} days unavailable")
    st.settle(len(rows) > 0, "day")
    return rows, st, behind >= 2


def _from_tradingview(lo: date, hi: date, why: str) -> tuple[list[dict[str, Any]], SourceStatus]:
    """The window from TradingView's calendar: one request. `why` is what Nasdaq
    said, for the status row."""
    st = SourceStatus("Economic calendar")
    start = datetime(lo.year, lo.month, lo.day, tzinfo=ET).astimezone(UTC)
    end = datetime(hi.year, hi.month, hi.day, 23, 59, 59, tzinfo=ET).astimezone(UTC)
    r = st.absorb(fetch(
        TRADINGVIEW.format(lo=start.strftime(_TV_ISO), hi=end.strftime(_TV_ISO),
                           cc=",".join(sorted(_COUNTRY_OF))),
        key="cal_tradingview",
        ttl_sec=540.0,
        ua=BROWSER_UA,
        timeout=20,
        headers=dict(TV_HEADERS),
        stale_max_sec=48 * 3600.0,
        validate=tv_body,
    ))
    rows: list[dict[str, Any]] = []
    if r.ok:
        try:
            rows = _finish(parse_tradingview(r.json(), lo, hi))
        except (ValueError, TypeError, AttributeError) as e:
            st.error = f"parse: {e}"
    else:
        st.error = r.error
    st.items = len(rows)
    st.notes.append(f"TradingView's calendar: Nasdaq is not answering ({why})")
    st.settle(len(rows) > 0, "read")
    return rows, st


#: How far ahead the collector reads (2026-11-14). It was three days, so on a Friday
#: evening the Macro calendar ended on Monday and the week being planned for was not
#: on it. A week reaches the same weekday next week from any day.
WEEK_AHEAD = 7
#: And the week after, for its big releases alone (owner, 2026-11-16: "on macro can we
#: add a bit more of the future things that show up in the calendar? and have a see more
#: if we do want to see more"): next week's CPI, payrolls or FOMC is worth seeing now.
DAYS_AHEAD = 14
#: Days ahead that are kept whole. Past these only the rows that matter are kept.
FULL_DAYS = 3
#: Past a week, a release stays only from this impact up: the ones that stop the tape.
FAR_SCORE = 4


def thin_far(rows: list[dict[str, Any]], today: date,
             full_days: int = FULL_DAYS) -> list[dict[str, Any]]:
    """`rows` with the far days cut to what is worth knowing a week out. Pure.

    A day of this feed is seventy-odd releases and most are impact one (Korean
    industrial production, Italian unemployment). Inside `full_days` every row is
    kept, as it always was: that is where a reader may want the whole day. Beyond it
    a row stays only if it reaches the books (`core`, whatever the country) or is a
    US release scoring three or more (housing starts, Michigan sentiment: what the
    stocks desk's own filter keeps). So a week of look-ahead adds the week's events
    and not four more days of the tail to a payload every open tab reads each twenty
    seconds: measured on 13 Nov 2026, the week's 293 rows became 198 where the
    three-day window held 139. A row with no time is kept.

    PAST A WEEK (2026-11-16, `DAYS_AHEAD`), only the releases that stop the tape: a
    score of `FAR_SCORE` or more that reaches the books or is America's.
    """
    edge = today + timedelta(days=full_days)
    week = today + timedelta(days=WEEK_AHEAD)
    out: list[dict[str, Any]] = []
    for r in rows:
        ts = r.get("ts")
        day = datetime.fromtimestamp(float(ts), ET).date() if isinstance(ts, (int, float)) else None
        score = int(r.get("score") or 0)
        ours = bool(r.get("core")) or r.get("region") == "us"
        if day is not None and day > week and not (ours and score >= FAR_SCORE):
            continue
        us3 = r.get("region") == "us" and score >= 3
        if day is not None and day > edge and not r.get("core") and not us3:
            continue
        out.append(r)
    return out


def collect(days_ahead: int = 3, days_back: int = 1,
            today: date | None = None) -> tuple[list[dict[str, Any]], SourceStatus]:
    """Yesterday through the next few sessions, ranked: Nasdaq's calendar, or
    TradingView's while Nasdaq is not delivering (the note above). `today` is for
    the tests; the desk's day is New York's."""
    global _source, _window, _nasdaq_wait, _nasdaq_why
    today = today or datetime.now(ET).date()
    lo, hi = today - timedelta(days=days_back), today + timedelta(days=days_ahead)
    _window = (lo, hi)
    now = time.time()
    held: tuple[list[dict[str, Any]], SourceStatus] | None = None
    if now >= _nasdaq_wait:
        rows, st, down = _from_nasdaq(today, lo, hi, days_ahead, days_back)
        if not down:
            _source = "nasdaq"
            return rows, st
        held = (rows, st)
        _nasdaq_wait = now + NASDAQ_RETRY_SEC
        _nasdaq_why = st.stale_error or st.error or "unreachable"
    tv_rows, tv_st = _from_tradingview(lo, hi, _nasdaq_why or "unreachable")
    if tv_st.ok:
        _source = "tradingview"
        return tv_rows, tv_st
    # Neither is answering: what Nasdaq's copy on disk still holds, marked stale.
    if held is None:
        rows, st, _ = _from_nasdaq(today, lo, hi, days_ahead, days_back)
        held = (rows, st)
    _source = "nasdaq"
    return held
