"""
Each name's past report dates, and the next one.

WHY. The options block warns that a report lands inside the expiry and
stops there; the figure that decides an options trade into a report is the
move the chain prices for it against the moves the name has actually made
on its last few (owner, 2026-10-22: "the earnings number"). The realised
moves are read off the daily bars the scanner already holds; what those
bars cannot say is WHICH days were report days.

PAST REPORTS FROM EDGAR (2026-11-17). Nasdaq's earnings-surprise table was the
source until Nasdaq began answering the collector 403 on 10 Nov. It refuses
Python's TLS client whatever the headers, while curl on the same machine is
still answered, and from then on the status row read "never". The filing is
the record the date comes from anyway: a results release is furnished on an
8-K under item 2.02, and EDGAR stamps the instant it accepted it, so the day
AND the hour (before the open, after the close) come off the filing. The
submissions JSON is the one the scanner already reads every half hour
(sources/scanner.tick_sec), so this asks for nothing of its own.

ITEM 2.02 IS NOT ONLY THE RESULTS. Tesla furnishes its deliveries under it on
the second of each quarter, and a company that pre-announces at a conference
does the same. A 2.02 inside the PREVIEW_DAYS before a later one, or before
the next report known, is that one's preview and is passed over. Amendments
(8-K/A) repeat a release and are skipped.

A foreign filer reports on a 6-K, which carries no items, and a few companies
stop furnishing their results under 2.02 (Oklo's last is March 2025). For a
name with no 2.02, or whose newest is more than STOPPED_DAYS older than
TradingView's last report, TradingView's last stands in, one report deep.

An 8-K furnished the morning after an after-close release (Teradyne) or on
the Monday after a Saturday one (Berkshire) is dated by its filing, before the
open: a day off the release, but the session it names is still the reaction,
which is what optcalc.realised_earnings_moves reads the hour for.

The "recent" list is the last thousand filings. A name that files hundreds
of notes a year (JPM) reaches back about a year, which still holds the four
reports the earnings number reads.

THE NEXT REPORT FROM TRADINGVIEW. One POST to the screener the pool and the
earnings stand-in already read (sources/pool.py, sources/earnings.py), for the
whole list, every NEXT_SEC: the date and, once the company has said, before
the open or after the close. A name added to the list changes the cache key,
so it is asked for at once; a restart reads the copy on disk.
"""

from __future__ import annotations

import json
import zlib
from datetime import UTC, date, datetime
from typing import Any
from zoneinfo import ZoneInfo

from ..config import BROWSER_UA
from ..http import SourceStatus, fetch
from .earnings import TV_HEADERS, TV_SCAN, _tv_when, tv_body

ET = ZoneInfo("America/New_York")
TICK_SEC = 60.0
NEXT_SEC = 3 * 3600.0
FAIL_SEC = 300.0
STALE_MAX_SEC = 2 * 86400.0
PREVIEW_DAYS = 45
STOPPED_DAYS = 7
KEEP = 8
NEXT_COLUMNS = [
    "name", "type", "typespecs",
    "earnings_release_next_date", "earnings_release_next_time",
    "earnings_release_date", "earnings_release_time",
]
EXCHANGES = ["NASDAQ", "NYSE", "AMEX"]


def _day(v: Any) -> date | None:
    try:
        return date.fromisoformat(str(v))
    except (ValueError, TypeError):
        return None


def _instant(accepted: Any, filed: Any) -> dict[str, Any] | None:
    """EDGAR's acceptance stamp (UTC: "2026-10-30T20:30:28.000Z") → the ET day and
    which side of the session it fell; the filing date, with no hour, when the
    stamp is missing."""
    s = str(accepted or "").strip()
    if s:
        try:
            at = datetime.fromisoformat(s.replace("Z", "+00:00")).astimezone(ET)
        except ValueError:
            at = None
        if at is not None:
            m = at.hour * 60 + at.minute
            # EDGAR's day closes at 17:30 ET; what it accepts later is public the
            # next business day, its filing date. PepsiCo, Duke and Xcel file the
            # evening before a release that comes out before the open.
            d = _day(filed)
            if m >= 17 * 60 + 30 and d is not None and d > at.date():
                return {"date": d.isoformat(), "when": "pre"}
            when = "pre" if m < 9 * 60 + 30 else "after" if m >= 16 * 60 else "during"
            return {"date": at.date().isoformat(), "when": when}
    d = _day(filed)
    return {"date": d.isoformat(), "when": "unspecified"} if d else None


def parse_edgar(doc: Any) -> list[dict[str, Any]]:
    """EDGAR submissions JSON → each 8-K furnishing item 2.02, newest first, one a
    day: {"date": the ET day it was accepted, "when": "pre" | "during" | "after"}.
    Previews are still in; `reports` passes over them. Pure."""
    try:
        r = doc["filings"]["recent"]
        forms = r["form"]
    except (KeyError, TypeError):
        return []
    n = len(forms)
    items = r.get("items") or [""] * n
    accepted = r.get("acceptanceDateTime") or [None] * n
    filed = r.get("filingDate") or [None] * n
    out: dict[str, dict[str, Any]] = {}
    for i, form in enumerate(forms):
        if form != "8-K" or i >= len(items):
            continue
        if "2.02" not in [x.strip() for x in str(items[i] or "").split(",")]:
            continue
        row = _instant(accepted[i] if i < len(accepted) else None,
                       filed[i] if i < len(filed) else None)
        if row is not None:
            out.setdefault(row["date"], row)
    return sorted(out.values(), key=lambda x: x["date"], reverse=True)


def reports(filed: list[dict[str, Any]], next_date: str | None = None) -> list[dict[str, Any]]:
    """The results releases among a name's 2.02s, newest first, at most KEEP. One
    inside the PREVIEW_DAYS before a later one, or before the next report known,
    is that one's preview (module docstring). Pure."""
    later = _day(next_date)
    out: list[dict[str, Any]] = []
    for r in sorted(filed, key=lambda x: str(x.get("date")), reverse=True):
        d = _day(r.get("date"))
        if d is None:
            continue
        # Strictly after: a next date that has not rolled on yet IS the newest report.
        if later is not None and 0 < (later - d).days <= PREVIEW_DAYS:
            continue
        out.append(r)
        later = d
        if len(out) >= KEEP:
            break
    return out


def next_query(syms: list[str]) -> dict[str, Any]:
    """The screener request for the names' next and last reports. Pure."""
    return {
        "filter": [
            {"left": "name", "operation": "in_range", "right": sorted(syms)},
            {"left": "exchange", "operation": "in_range", "right": list(EXCHANGES)},
        ],
        "columns": list(NEXT_COLUMNS),
        "range": [0, 2 * len(syms) + 10],
    }


def _tv_day(ts: Any, flag: Any, placeholder: bool) -> dict[str, Any] | None:
    if isinstance(ts, bool) or not isinstance(ts, (int, float)) or ts <= 0:
        return None
    at = datetime.fromtimestamp(float(ts), ET)
    return {"date": at.date().isoformat(), "when": _tv_when(flag, at, placeholder)}


def parse_tv(doc: Any) -> dict[str, dict[str, Any]]:
    """The screener reply → {sym: {"next": {"date", "when"} | None, "last": … | None}}.
    Preferred lines are passed over; a row whose `d` is not the column count asked
    for is skipped rather than mis-zipped. Pure."""
    out: dict[str, dict[str, Any]] = {}
    if not isinstance(doc, dict) or not isinstance(doc.get("data"), list):
        return out
    for item in doc["data"]:
        d = item.get("d") if isinstance(item, dict) else None
        if not isinstance(d, list) or len(d) != len(NEXT_COLUMNS):
            continue
        r = dict(zip(NEXT_COLUMNS, d, strict=True))
        sym = str(r.get("name") or "").strip().upper()
        specs = r["typespecs"] if isinstance(r.get("typespecs"), list) else []
        if not sym or (r.get("type") == "stock" and "common" not in specs):
            continue
        out.setdefault(sym, {
            # The next report comes as noon UTC until the company names its hour.
            "next": _tv_day(r.get("earnings_release_next_date"),
                            r.get("earnings_release_next_time"), placeholder=True),
            "last": _tv_day(r.get("earnings_release_date"),
                            r.get("earnings_release_time"), placeholder=False),
        })
    return out


def _stopped(newest: dict[str, Any], last: dict[str, Any]) -> bool:
    """Whether TradingView's last report is more than STOPPED_DAYS past EDGAR's newest."""
    a, b = _day(newest.get("date")), _day(last.get("date"))
    return a is not None and b is not None and (b - a).days > STOPPED_DAYS


def _names(syms: list[str], cap: int = 5) -> str:
    return ", ".join(syms[:cap]) + ("…" if len(syms) > cap else "")


class EarnHistStore:
    """Past report dates per name and the next one, joined each tick from EDGAR
    (through the scanner's read) and TradingView (module docstring)."""

    def __init__(self) -> None:
        self.data: dict[str, list[dict[str, Any]]] = {}
        self.next: dict[str, dict[str, Any]] = {}
        self.tv: dict[str, dict[str, Any]] = {}
        self.tv_at: float | None = None
        self.tv_error: str | None = None
        self._key = ""
        self._due = 0.0

    def _read_tv(self, syms: list[str], key: str, t: float) -> bool:
        r = fetch(TV_SCAN, key=key, ttl_sec=NEXT_SEC, ua=BROWSER_UA, timeout=20,
                  headers=dict(TV_HEADERS), stale_max_sec=STALE_MAX_SEC, validate=tv_body,
                  data=json.dumps(next_query(syms)).encode())
        if not r.ok or r.body is None:
            self.tv_error = r.error or "unavailable"
            return False
        try:
            self.tv = parse_tv(r.json())
        except (ValueError, TypeError, AttributeError) as e:
            self.tv_error = f"unreadable ({e})"
            return False
        self.tv_at = t - (r.age_min or 0.0) * 60.0
        self.tv_error = r.error if r.source == "stale" else None
        return True

    def tick(self, syms: list[str], filed: dict[str, list[dict[str, Any]]],
             now: datetime | None = None) -> SourceStatus:
        """`syms` the list's companies (the funds left out); `filed` each one's 2.02s
        as the scanner last read them (`parse_edgar`), absent until its first read."""
        t = (now or datetime.now(UTC)).timestamp()
        key = f"earnnext_tv_{zlib.crc32(','.join(sorted(syms)).encode()):08x}"
        if syms and (key != self._key or t >= self._due):
            self._key = key
            self._due = t + (NEXT_SEC if self._read_tv(syms, key, t) else FAIL_SEC)
        data: dict[str, list[dict[str, Any]]] = {}
        nxt: dict[str, dict[str, Any]] = {}
        stand_in: list[str] = []
        for s in syms:
            tv = self.tv.get(s) or {}
            if tv.get("next"):
                nxt[s] = tv["next"]
            rows = reports(filed.get(s) or [], (tv.get("next") or {}).get("date"))
            last = tv.get("last")
            if last and (not rows or _stopped(rows[0], last)):
                rows = [last]
                stand_in.append(s)
            if rows:
                data[s] = rows
        self.data, self.next = data, nxt

        st = SourceStatus("Earnings history")
        have = [s for s in syms if s in data]
        st.items = len(have)
        st.ok = bool(have)
        st.source = "live" if st.ok else "unavailable"
        st.age_min = round((t - self.tv_at) / 60.0, 1) if self.tv_at is not None else None
        if self.tv_error:
            st.error = f"TradingView: {self.tv_error}"
        if st.ok:
            st.last_ok_utc = datetime.now(UTC).isoformat()
        st.notes.append(f"{len(have) - len(stand_in)} of {len(syms)} from EDGAR's 8-Ks"
                        + (f", {len(stand_in)} from TradingView's last report"
                           if stand_in else ""))
        waiting = [s for s in syms if s not in filed]
        if waiting:
            st.notes.append(f"waiting on EDGAR: {_names(waiting)}")
        bare = [s for s in syms if s not in data and s in filed]
        if bare:
            st.notes.append(f"no report found: {_names(bare)}")
        st.notes.append(f"next report for {len(nxt)} of {len(syms)} from TradingView")
        return st

    def view(self) -> dict[str, list[dict[str, Any]]]:
        return dict(self.data)

    def view_next(self) -> dict[str, dict[str, Any]]:
        return dict(self.next)
