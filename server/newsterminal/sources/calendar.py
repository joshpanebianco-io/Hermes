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

import re
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

# The trading session a release prints into — the range panel's windows
# (sessions.desk_window), with its two European windows folded into one
# "london", so "prints in the London session" means one thing across the
# terminal. They were four ET constants here, with London from 03:00 ET: UK
# GDP at 07:00 London (02:00 ET) printed "in the Asia session" (review,
# 2026-10-14), and every boundary was an hour out in the mismatch weeks.
_SESSION_OF_WINDOW: dict[str | None, str] = {
    "asia": "asia",
    "london": "london",
    "euro_mid": "london",
    "preny": "preny",
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
        et_str, when_utc, when_et = None, None, None
        m = re.match(r"(\d{1,2}):(\d{2})", raw_time)
        if m:
            when_et = datetime(
                day.year, day.month, day.day, int(m.group(1)), int(m.group(2)), tzinfo=ET
            )
            when_utc = when_et.astimezone(UTC)
            et_str = when_et.strftime("%H:%M")

        actual = _num(r.get("actual"))
        cons = _num(r.get("consensus"))
        prev = _num(r.get("previous"))
        sc = score(country, event)
        out.append(
            {
                "event": event,
                "country": country,
                "region": region_of(country),
                "session": session_of(when_et),
                "themes": themes_of(event),
                "core": is_core(country, event, sc),
                "date": day.isoformat(),
                "et": et_str,
                "utc": when_utc.isoformat() if when_utc else None,
                "ts": when_utc.timestamp() if when_utc else None,
                "actual": actual,
                "actual_raw": clean_text(str(r.get("actual") or "")) or None,
                "consensus": cons,
                "consensus_raw": clean_text(str(r.get("consensus") or "")) or None,
                "previous": prev,
                "previous_raw": clean_text(str(r.get("previous") or "")) or None,
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
                # The plain-English gloss Nasdaq ships. Genuinely useful at
                # 08:29 for a release you do not follow closely.
                "note": clean_text(str(r.get("description") or ""))[:260] or None,
            }
        )
    return out


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
        if len(g) != 2:
            continue
        a, b = (_pct_val(x) for x in g)
        if a is not None and b is not None and a != b:
            small, big = (g[0], g[1]) if a < b else (g[1], g[0])
            small["event"] += " m/m"
            big["event"] += " y/y"
        elif (a is None) != (b is None):
            (g[0] if a is not None else g[1])["event"] += " m/m"


def collect(days_ahead: int = 3, days_back: int = 1) -> tuple[list[dict[str, Any]], SourceStatus]:
    """Yesterday through the next few sessions, ranked."""
    global _last_shift
    st = SourceStatus("Economic calendar")
    today = datetime.now(ET).date()
    lo, hi = today - timedelta(days=days_back), today + timedelta(days=days_ahead)
    rows: list[dict[str, Any]] = []
    failed = 0
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
            ttl_sec=86400.0 if offset < -1 else 540.0,
            ua=BROWSER_UA,
            timeout=20,
            headers={"Accept": "application/json"},
            # A settled day may serve a week-old copy; the rest may not lag by
            # more than six hours — that is where actuals land.
            stale_max_sec=7 * 86400.0 if offset < -1 else 6 * 3600.0,
            validate=json_body,
        )
        st.absorb(r)
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
    rows = unique

    label_variants(rows)
    rows.sort(key=lambda x: (x.get("ts") or 0))
    st.items = len(rows)
    if failed:
        st.notes.append(f"{failed} of {len(list(span))} days unavailable")
    st.settle(len(rows) > 0, "day")
    return rows, st
