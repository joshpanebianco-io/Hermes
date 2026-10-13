"""
Treasury supply — the auctions that move the long end, before they happen.

WHY A NEWS TERMINAL CARES. A weak 10-year or 30-year auction reprices the whole
curve at 13:01 ET, and the Nasdaq — the longest-duration equity index on the
board — moves with it. The economic calendar upstream does not carry auctions,
so without this the terminal knew every CPI print for a fortnight ahead and
nothing about the $40bn of duration landing on Wednesday.

THE SOURCE IS TREASURYDIRECT'S OWN FEED — `TA_WS/securities/upcoming`, a US
Government work, no key, about a fortnight of forward visibility.

BILLS ARE DROPPED. Most of the file is weekly bill rollover — 4-week through
52-week paper that clears mechanically and moves nothing. What is kept is
coupon supply: Notes, Bonds and TIPS, the auctions a rates desk actually
watches. FRNs and cash-management bills go with the bills.

REOPENINGS ARE NAMED BY WHAT THEY ARE. The feed calls a 10-year reopening a
"9-Year 11-Month", which is true and useless; `originalSecurityTerm` carries
the name the market uses, and the row keeps a `reopening` flag because a
reopening usually clears more easily than new paper.

ONE CONVENTION: coupon auctions close at 13:00 ET. The feed gives no time, and
that has been the standard competitive close for years; it is a display hint,
not data.
"""

from __future__ import annotations

import json
import re
from datetime import UTC, date, datetime
from typing import Any
from zoneinfo import ZoneInfo

from ..config import BROWSER_UA
from ..http import SourceStatus, fetch, json_body

ET = ZoneInfo("America/New_York")
UPCOMING = "https://www.treasurydirect.gov/TA_WS/securities/upcoming?format=json"

KEEP_TYPES = {"Note", "Bond", "TIPS"}

# The tenors that reprice equities when they tail. The belly matters some;
# the long end is the event.
MAJOR = {"10Y", "20Y", "30Y"}

_TERM = re.compile(r"^(\d+)-Year", re.I)


def _short(term: str) -> str | None:
    """'10-Year' → '10Y'. Anything unparseable stays out of the diary."""
    m = _TERM.match((term or "").strip())
    return f"{m.group(1)}Y" if m else None


def parse(doc: Any, today: date) -> list[dict[str, Any]]:
    """The feed → forward coupon auctions. Pure."""
    rows: list[dict[str, Any]] = []
    for r in doc if isinstance(doc, list) else []:
        if str(r.get("securityType")) not in KEEP_TYPES:
            continue
        reopening = str(r.get("reopening")).strip().lower() == "yes"
        term = str(r.get("originalSecurityTerm") if reopening else r.get("securityTerm") or "")
        short = _short(term)
        if short is None:
            continue
        try:
            when = date.fromisoformat(str(r.get("auctionDate"))[:10])
        except (TypeError, ValueError):
            continue
        delta = (when - today).days
        if delta < 0:
            continue

        # Empty until the announcement, roughly a week out — shown when known,
        # never guessed.
        amount_bn: float | None = None
        raw_amt = str(r.get("offeringAmount") or "").strip()
        if raw_amt.replace(".", "", 1).isdigit():
            amount_bn = round(float(raw_amt) / 1e9, 1)

        close = datetime(when.year, when.month, when.day, 13, 0, tzinfo=ET)
        is_tips = str(r.get("securityType")) == "TIPS"
        rows.append(
            {
                "term": short,
                "label": f"{short} TIPS" if is_tips else short,
                "security": str(r.get("securityType")),
                "date": when.isoformat(),
                "et": "13:00",
                "utc": close.astimezone(UTC).isoformat(),
                "ts": close.timestamp(),
                "in_days": delta,
                "amount_bn": amount_bn,
                "reopening": reopening,
                "major": short in MAJOR and not is_tips,
            }
        )
    rows.sort(key=lambda r: r["date"])
    return rows


def collect() -> tuple[list[dict[str, Any]], SourceStatus]:
    """The forward coupon-auction schedule."""
    st = SourceStatus("Treasury auctions")
    # Six hours. The schedule is set weeks ahead and amended almost never;
    # even the offering amounts only change at the weekly announcement.
    r = fetch(UPCOMING, key="treasury_upcoming", ttl_sec=6 * 3600.0, ua=BROWSER_UA, timeout=40,
              stale_max_sec=7 * 86400.0, validate=json_body)
    st.absorb(r)
    if not r.ok or r.body is None:
        st.error = r.error or "empty response"
        return [], st
    try:
        doc = json.loads(r.body.decode("utf-8-sig", errors="replace"))
    except (ValueError, TypeError) as e:
        st.error = f"parse: {e}"
        return [], st

    rows = parse(doc, datetime.now(ET).date())
    st.items = len(rows)
    st.settle(True, "file")
    if not rows:
        st.notes.append("no coupon auctions in the forward window")
    return rows, st
