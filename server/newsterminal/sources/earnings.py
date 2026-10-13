"""
Earnings — the reports that move an index rather than a stock.

WHY A NEWS TERMINAL FOR INDEX FUTURES CARRIES EARNINGS AT ALL. The Nasdaq 100
is a cap-weighted index in which roughly the top seven names are a third of it.
NVDA after the close moves NQ harder than most macro prints move it in a week,
and a session note written without knowing who reports tonight is missing the
single largest scheduled risk in it. That is a different claim from "track every
earnings release": a small-cap beat is noise to this desk.

FILTERED BY MARKET CAP, NOT BY INDEX MEMBERSHIP. Membership lists go stale and
would need maintaining; capitalisation is in the payload, it is the thing that
actually determines index impact, and it needs no second source. Everything
above the threshold is kept and everything below is dropped, so the panel is
five or ten names a day rather than three hundred.

BEFORE OR AFTER THE BELL IS THE FIELD THAT MATTERS. An after-hours report is
tomorrow's gap; a pre-market one is this morning's. Nasdaq gives it and it rides
on every row.
"""

from __future__ import annotations

import re
from datetime import UTC, datetime, timedelta
from typing import Any
from zoneinfo import ZoneInfo

from ..config import BROWSER_UA
from ..http import SourceStatus, clean_text, fetch

ET = ZoneInfo("America/New_York")
NASDAQ = "https://api.nasdaq.com/api/calendar/earnings?date={d}"

# Below this a report does not reach an index future on this desk. $50bn keeps
# roughly the S&P 100 plus the large Nasdaq names and drops the rest.
MIN_CAP = 50_000_000_000.0

# The handful whose reports are session-defining for NQ regardless of anything
# else — kept even if the cap field is missing or malformed, which it sometimes
# is for ADRs and recent listings.
BELLWETHERS = {
    "NVDA", "AAPL", "MSFT", "AMZN", "GOOGL", "GOOG", "META", "TSLA", "AVGO",
    "AMD", "MU", "INTC", "QCOM", "TSM", "ORCL", "CRM", "NFLX", "ADBE", "COST",
    "JPM", "GS", "BAC", "WMT", "XOM", "LLY", "UNH", "V", "MA",
}

_CAP = re.compile(r"[^\d.]")


def _cap(v: Any) -> float | None:
    """'$312,022,761,000' → 312022761000.0."""
    if v is None:
        return None
    t = _CAP.sub("", str(v))
    if not t or t == ".":
        return None
    try:
        return float(t)
    except ValueError:
        return None


def _when(v: Any) -> str:
    """Nasdaq's 'time-after-hours' → 'after'. Anything unknown is 'unspecified'."""
    t = str(v or "").lower()
    if "pre-market" in t or "pre_market" in t or "before" in t:
        return "pre"
    if "after-hours" in t or "after_hours" in t or "after" in t:
        return "after"
    return "unspecified"


def parse_day(doc: Any, day: str, keep: frozenset[str] = frozenset()) -> list[dict[str, Any]]:
    """One Nasdaq earnings day → the rows big enough to matter. Pure.

    `keep` is the scanner's watchlist: a name on it is kept whatever its size,
    because a $20bn stock reporting tonight is the single biggest fact about
    trading it tomorrow. Those rows carry `watch_only` so the Earnings panel —
    which is about what moves an INDEX — can leave them out.
    """
    rows = ((doc or {}).get("data") or {}).get("rows") or []
    out: list[dict[str, Any]] = []
    for r in rows:
        sym = clean_text(str(r.get("symbol") or "")).upper()
        if not sym:
            continue
        cap = _cap(r.get("marketCap"))
        big = sym in BELLWETHERS or (cap is not None and cap >= MIN_CAP)
        if not big and sym not in keep:
            continue
        out.append({
            "symbol": sym,
            "name": clean_text(str(r.get("name") or "")),
            "date": day,
            "when": _when(r.get("time")),
            "eps_forecast": clean_text(str(r.get("epsForecast") or "")) or None,
            "eps_actual": clean_text(str(r.get("eps") or "")) or None,
            # A NUMBER, NOT A STRING. Nasdaq sends "2.5" (or "N/A"); shipping the
            # raw text meant the UI could not compare it to zero to colour a
            # beat, and "N/A" survived as a truthy value.
            "surprise_pct": _float(r.get("surprise")),
            "market_cap": cap,
            "bellwether": sym in BELLWETHERS,
            "watch_only": not big,
        })
    # Biggest first: on a day with eight reports the order the eye wants is by
    # how much of the index each one is.
    out.sort(key=lambda r: -(r.get("market_cap") or 0))
    return out


def _float(v: object) -> float | None:
    """Nasdaq's numerics arrive as text, with "N/A" for absent."""
    try:
        return float(str(v).replace(",", "").strip())
    except (TypeError, ValueError):
        return None


def collect(
    days_ahead: int = 4, days_back: int = 2, keep: frozenset[str] = frozenset()
) -> tuple[list[dict[str, Any]], SourceStatus]:
    """A few sessions either side of today, big names only — plus `keep`."""
    st = SourceStatus("Earnings")
    today = datetime.now(ET).date()
    rows: list[dict[str, Any]] = []
    failed = 0
    span = range(-days_back, days_ahead + 1)

    for off in span:
        d = (today + timedelta(days=off)).isoformat()
        r = fetch(
            NASDAQ.format(d=d),
            key=f"earn_{d}",
            # Past days are settled; today and ahead refresh so an actual EPS
            # appears once it prints.
            ttl_sec=86400.0 if off < 0 else 1800.0,
            ua=BROWSER_UA,
            timeout=20,
            headers={"Accept": "application/json"},
        )
        if not r.ok:
            failed += 1
            st.error = st.error or r.error
            continue
        try:
            rows.extend(parse_day(r.json(), d, keep))
        except (ValueError, TypeError, AttributeError) as e:
            failed += 1
            st.error = st.error or f"parse: {e}"

    rows.sort(key=lambda r: (r["date"], -(r.get("market_cap") or 0)))
    st.items = len(rows)
    st.ok = len(rows) > 0 or failed == 0
    st.source = "live" if st.ok else "unavailable"
    st.age_min = 0.0 if st.ok else None
    if failed:
        st.notes.append(f"{failed} of {len(list(span))} days unavailable")
    if st.ok:
        st.last_ok_utc = datetime.now(UTC).isoformat()
    return rows, st
