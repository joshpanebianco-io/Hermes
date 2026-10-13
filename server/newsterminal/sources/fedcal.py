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
"""

from __future__ import annotations

import html
import json
import re
from datetime import UTC, date, datetime
from typing import Any
from zoneinfo import ZoneInfo

from ..config import BROWSER_UA
from ..http import SourceStatus, fetch, json_body

ET = ZoneInfo("America/New_York")
CALENDAR = "https://www.federalreserve.gov/json/calendar.json"

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


def collect() -> tuple[list[dict[str, Any]], list[dict[str, Any]], SourceStatus]:
    """The next three weeks of Fed events, plus the year's decision dates."""
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
    return rows, fomc, st
