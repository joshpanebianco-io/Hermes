"""
The Fed's own calendar — who speaks, and when, before they speak.

THE GAP THIS FILLS. The wire already carries Federal Reserve speeches, but it
carries them as RSS — which means it tells you what was said after it was said.
On this desk's own tape, "Barclays sees two more Fed rate hikes after Warsh
speech" and "Warsh's Jackson Hole comments" were both moving the market, and the
terminal had no way to know either was coming. An unscheduled remark cannot be
prepared for; a scheduled one can, and the Board publishes the schedule.

THE SOURCE IS THE BOARD'S OWN EVENTS FEED. `calendar.json` behind
federalreserve.gov, a US Government work, carrying about 2,600 entries from 2017
out to the end of the current year, each with a type, a date, a time and a title
naming the speaker.

STATISTICAL RELEASES ARE DROPPED. Roughly 40% of the file is `Stat` — H.10
foreign exchange rates, H.15 selected interest rates, the commercial paper
series. They are data publications on a fixed schedule, not events anyone
positions around, and they would bury the fourteen entries a quarter that
actually matter. What is kept is the FOMC, speeches, testimony and the Beige
Book.

DATES COME APART AND ARE PUT BACK TOGETHER. `month` is "2026-09" and `days` is a
string that may be "3" or "3,4" for a two-day meeting — so a single entry can be
several dates, and the first day is the one to schedule against.

THE MEETINGS PAST DECEMBER COME FROM THE BOARD'S MEETING PAGE (2026-11-14). The
events feed stops at the end of the current year, so from the last autumn meeting
until January it held one FOMC, and the Rates card's "path" was a single row while
the fed funds strip priced fourteen months of moves. `fomccalendars.htm` on the
same site lists every meeting of this year and the next, a year to a block, so it
is read beside the feed and adds the meetings the feed does not reach
(`schedule_from_page`, `with_schedule`). The feed's own entries are left exactly
as they were; if the page cannot be read the schedule is the feed's alone, as
before, and the source says so in a note.
"""

from __future__ import annotations

import calendar as _cal
import html
import json
import re
from datetime import UTC, date, datetime, timedelta
from typing import Any
from zoneinfo import ZoneInfo

from ..config import BROWSER_UA
from ..http import SourceStatus, fetch, json_body

ET = ZoneInfo("America/New_York")
CALENDAR = "https://www.federalreserve.gov/json/calendar.json"
SCHEDULE = "https://www.federalreserve.gov/monetarypolicy/fomccalendars.htm"

# The types worth a reader's attention, and what to call each on screen.
KEEP: dict[str, str] = {
    "FOMC": "FOMC",
    "Speeches": "Speech",
    "Testimony": "Testimony",
    "Beige": "Beige Book",
    "Conferences": "Conference",
}

# Whose remarks move the front of the curve. A governor is not a regional
# president, and neither is a research conference panellist.
PRINCIPALS = re.compile(
    r"chair(?:man|woman)?|vice chair|governor|president", re.I,
)

_TAGS = re.compile(r"<[^>]+>")
_TIME = re.compile(r"^(\d{1,2}):(\d{2})\s*([ap])\.?m", re.I)


def _clean(s: Any) -> str:
    """The feed embeds escaped HTML in both title and description."""
    return re.sub(r"\s+", " ", _TAGS.sub(" ", html.unescape(str(s or "")))).strip()


def _to_et(day: date, raw_time: str) -> tuple[datetime | None, str | None]:
    """'2:00 p.m.' on a date → an ET instant. Untimed entries stay None."""
    m = _TIME.match((raw_time or "").strip())
    if not m:
        return None, None
    hour = int(m.group(1)) % 12
    if m.group(3).lower() == "p":
        hour += 12
    when = datetime(day.year, day.month, day.day, hour, int(m.group(2)), tzinfo=ET)
    return when, when.strftime("%H:%M")


def parse(doc: Any, today: date, horizon_days: int = 21) -> list[dict[str, Any]]:
    """The calendar payload → the events ahead. Pure."""
    events = doc if isinstance(doc, list) else (doc or {}).get("events") or []
    out: list[dict[str, Any]] = []

    for e in events:
        kind = KEEP.get(str(e.get("type") or ""))
        if not kind:
            continue
        month = str(e.get("month") or "")
        if not re.match(r"^\d{4}-\d{2}$", month):
            continue
        # "3,4" is a two-day meeting. The first day is what you schedule
        # against; the span is carried so the panel can say "two-day".
        days = [d for d in re.findall(r"\d+", str(e.get("days") or "")) if d]
        if not days:
            continue
        y, mo = int(month[:4]), int(month[5:7])
        try:
            first = date(y, mo, int(days[0]))
        except ValueError:
            continue
        delta = (first - today).days
        if delta < 0 or delta > horizon_days:
            continue

        title = _clean(e.get("title"))
        when, et = _to_et(first, str(e.get("time") or ""))
        out.append(
            {
                "kind": kind,
                "title": title,
                "note": _clean(e.get("description"))[:200] or None,
                "date": first.isoformat(),
                "days": len(days),
                "et": et,
                "utc": when.astimezone(UTC).isoformat() if when else None,
                "ts": when.timestamp() if when else None,
                "in_days": delta,
                # An FOMC decision stops the tape; so does the Chair. A regional
                # president at a research conference does not, and the panel
                # weights them accordingly.
                "major": kind in {"FOMC", "Beige Book"}
                or bool(PRINCIPALS.search(title)),
            }
        )

    out.sort(key=lambda r: (r["date"], r["et"] or "99:99"))
    return out


def fomc_ahead(doc: Any, today: date, horizon_days: int = 420) -> list[dict[str, Any]]:
    """The decision schedule itself, a year out. Pure.

    The diary above keeps a three-week horizon because a reader plans against
    it; this list exists for arithmetic — `policy.meetings_priced` un-mixes the
    fed funds strip against these dates — and the strip runs fifteen months, so
    the schedule has to reach as far. Meetings only: the press conference is
    the same event twice.
    """
    return [
        {"date": e["date"], "days": e["days"]}
        for e in parse(doc, today, horizon_days=horizon_days)
        if e["kind"] == "FOMC" and "meeting" in e["title"].lower()
    ]


# ---- the meeting page: next year's dates -------------------------------------

# ">2027 FOMC Meetings<" opens a year's block; each meeting in it is a month cell
# ("January", or "Apr/May" for one that crosses a month end) and a date cell
# ("26-27", "17-18*" with projections, "22 (notation vote)" for what is no meeting).
_YEAR_HEAD = re.compile(r">\s*(\d{4}) FOMC Meetings\s*<")
_MEETING = re.compile(
    r"fomc-meeting__month[^>]*>\s*(?:<strong>)?\s*([^<]+?)\s*(?:</strong>)?\s*</div>"
    r".*?fomc-meeting__date[^>]*>\s*([^<]+?)\s*</div>",
    re.S,
)
_DAY_RANGE = re.compile(r"^(\d{1,2})(?:\s*-\s*(\d{1,2}))?\s*\*?$")
_MONTHS = {m: i for i, m in enumerate(
    ("jan", "feb", "mar", "apr", "may", "jun", "jul", "aug", "sep", "oct", "nov", "dec"), 1)}

# A feed meeting and a page meeting this close together are the same meeting.
_SAME_MEETING_DAYS = 3


def _decision(e: dict[str, Any]) -> date:
    """The day a meeting decides: its last. `date` is its first, `days` its length."""
    return date.fromisoformat(str(e["date"])) + timedelta(days=int(e.get("days") or 1) - 1)


def schedule_from_page(page: str, today: date, horizon_days: int = 420) -> list[dict[str, Any]]:
    """The Board's meeting page → the meetings still to decide, shaped as `fomc_ahead`. Pure.

    Kept while the DECISION day is today or later (a two-day meeting is still ahead
    on its second morning) and the meeting opens inside the horizon. A row whose
    date cell is anything but a day or a day range (a notation vote, an unscheduled
    call, a cancelled meeting) is not a scheduled decision and is skipped.
    """
    heads = sorted((m.start(), int(m.group(1))) for m in _YEAR_HEAD.finditer(page))
    out: list[dict[str, Any]] = []
    for i, (pos, year) in enumerate(heads):
        end = heads[i + 1][0] if i + 1 < len(heads) else len(page)
        for month_cell, date_cell in _MEETING.findall(page[pos:end]):
            mon = _MONTHS.get(month_cell.split("/")[0].strip()[:3].lower())
            rng = _DAY_RANGE.match(html.unescape(date_cell).strip())
            if mon is None or rng is None:
                continue
            d1 = int(rng.group(1))
            d2 = int(rng.group(2)) if rng.group(2) else d1
            try:
                first = date(year, mon, d1)
            except ValueError:
                continue
            # "Apr/May 30-1": the second day is in the next month.
            span = d2 - d1 + 1 if d2 >= d1 else _cal.monthrange(year, mon)[1] - d1 + 1 + d2
            if span > 3:
                continue  # No meeting runs longer; a range this wide is a misread.
            last = first + timedelta(days=span - 1)
            if last < today or (first - today).days > horizon_days:
                continue
            out.append({"date": first.isoformat(), "days": span})
    out.sort(key=lambda e: e["date"])
    return out


def with_schedule(feed: list[dict[str, Any]], page: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """The feed's meetings, plus the page's that the feed does not have. Pure.

    THE FEED WINS WHERE BOTH HAVE A MEETING: its entries are what every reader has
    always been given, so they are passed through untouched, and the page only adds
    the ones beyond the feed's reach (next year's, until January).
    """
    have = [_decision(e) for e in feed]
    extra = [e for e in page
             if all(abs((_decision(e) - d).days) > _SAME_MEETING_DAYS for d in have)]
    return sorted([*feed, *extra], key=lambda e: str(e["date"]))


def _schedule_body(body: bytes) -> str | None:
    """The meeting page, not an error page: it has year blocks with date cells."""
    ok = b"FOMC Meetings" in body and b"fomc-meeting__date" in body
    return None if ok else "the meeting page has no schedule in it"


def collect() -> tuple[list[dict[str, Any]], list[dict[str, Any]], SourceStatus]:
    """The next three weeks of Fed events, plus the decision dates the strip reaches."""
    st = SourceStatus("Fed calendar")
    # Half a day. The Board publishes weeks ahead and amends rarely, and the
    # file is ~530 KB — polling it on the wire's cadence would be rude for
    # something that cannot have moved.
    r = fetch(CALENDAR, key="fed_calendar", ttl_sec=12 * 3600.0, ua=BROWSER_UA, timeout=40,
              stale_max_sec=7 * 86400.0, validate=json_body)
    st.absorb(r)
    if not r.ok or r.body is None:
        st.error = r.error or "empty response"
        return [], [], st
    try:
        # utf-8-sig: the file carries a BOM, and `json.loads` refuses it.
        doc = json.loads(r.body.decode("utf-8-sig", errors="replace"))
    except (ValueError, TypeError) as e:
        st.error = f"parse: {e}"
        return [], [], st

    today = datetime.now(ET).date()
    rows = parse(doc, today)
    fomc = fomc_ahead(doc, today)
    st.items = len(rows)
    st.settle(True, "file")
    if not rows:
        st.notes.append("nothing scheduled in the next three weeks")

    # Next year's meetings, which the feed does not carry. NOT ABSORBED into the
    # status: the diary is the feed's, and a meeting page served from its last copy
    # must not date the diary's chip. A month of fallback is fine for a schedule the
    # Board sets a year ahead; without the page the schedule is the feed's alone.
    p = fetch(SCHEDULE, key="fed_fomc_page", ttl_sec=12 * 3600.0, ua=BROWSER_UA, timeout=40,
              stale_max_sec=30 * 86400.0, validate=_schedule_body)
    if p.ok and p.body is not None:
        page = schedule_from_page(p.body.decode("utf-8", errors="replace"), today)
        if page:
            fomc = with_schedule(fomc, page)
        else:
            st.notes.append("meeting page: no dates read, the schedule is the feed's alone")
    else:
        st.notes.append(f"meeting page: {p.error or 'empty response'}")
    return rows, fomc, st
