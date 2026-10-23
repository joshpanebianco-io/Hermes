"""
Each name's past report dates — Nasdaq's earnings-surprise table.

WHY. The options block warns that a report lands inside the expiry and
stops there; the figure that decides an options trade into a report is the
move the chain prices for it against the moves the name has actually made
on its last few (owner, 2026-10-22: "the earnings number"). The realised
moves are read off the daily bars the scanner already holds; what those
bars cannot say is WHICH days were report days, and Yahoo's summary gives
fiscal quarters, not report dates. Nasdaq's per-company table gives the
date reported for the last four quarters, with the EPS and the surprise.

ONE REQUEST A NAME A DAY, one name a tick, cached on disk, so a restart
costs nothing and the whole list is covered in a few minutes. The same host
and headers as the earnings calendar (sources/earnings.py).
"""

from __future__ import annotations

import re
from datetime import UTC, date, datetime
from typing import Any

from ..config import BROWSER_UA
from ..http import SourceStatus, fetch, json_body

URL = "https://api.nasdaq.com/api/company/{sym}/earnings-surprise"
#: The NEXT report, with its time of day — the calendar feed only reaches a
#: week ahead, and the earnings number wants the report whenever the chain
#: can price it ("expected to report earnings on 11/03/2026 after market close").
NEXT_URL = "https://api.nasdaq.com/api/analyst/{sym}/earnings-date"
TICK_SEC = 15.0
TTL_SEC = 24 * 3600.0
STALE_MAX_SEC = 14 * 86400.0
FAIL_BASE = 300.0
FAIL_CAP = 6 * 3600.0
KEEP = 8


def _date(v: Any) -> str | None:
    """Nasdaq's "8/4/2026" → "2026-08-04"."""
    s = str(v or "").strip()
    for fmt in ("%m/%d/%Y", "%Y-%m-%d"):
        try:
            return datetime.strptime(s, fmt).date().isoformat()
        except ValueError:
            continue
    return None


def _f(v: Any) -> float | None:
    try:
        return float(str(v).replace("$", "").replace(",", ""))
    except (TypeError, ValueError):
        return None


def parse(doc: Any) -> list[dict[str, Any]]:
    """The table → report rows, newest first. Pure."""
    try:
        rows = doc["data"]["earningsSurpriseTable"]["rows"]
    except (KeyError, TypeError):
        return []
    out: list[dict[str, Any]] = []
    for r in rows or []:
        if not isinstance(r, dict):
            continue
        d = _date(r.get("dateReported"))
        if d is None:
            continue
        out.append({
            "date": d,
            "quarter": str(r.get("fiscalQtrEnd") or "") or None,
            "eps": _f(r.get("eps")),
            "consensus": _f(r.get("consensusForecast")),
            "surprise_pct": _f(r.get("percentageSurprise")),
        })
    out.sort(key=lambda x: x["date"], reverse=True)
    return out[:KEEP]


_NEXT_DATE = re.compile(r"\b(\d{1,2})/(\d{1,2})/(\d{4})\b")


def parse_next(doc: Any) -> dict[str, Any] | None:
    """Nasdaq's earnings-date text → {"date", "when"} for the next report. Pure.
    None without a date in the text; "unspecified" without a time of day."""
    try:
        text = str(doc["data"]["reportText"] or "")
    except (KeyError, TypeError):
        return None
    m = _NEXT_DATE.search(text)
    if not m:
        return None
    try:
        d = date(int(m.group(3)), int(m.group(1)), int(m.group(2)))
    except ValueError:
        return None
    low = text.lower()
    when = ("after" if "after market close" in low or "after the close" in low
            else "pre" if "before market open" in low or "before the open" in low
            else "unspecified")
    return {"date": d.isoformat(), "when": when}


class EarnHistStore:
    """Past report dates per name, and the next one, one name a tick."""

    def __init__(self) -> None:
        self.data: dict[str, list[dict[str, Any]]] = {}
        self.next: dict[str, dict[str, Any]] = {}
        self.at: dict[str, float] = {}
        self.fails: dict[str, tuple[int, float]] = {}
        self.errors: dict[str, str] = {}

    def due(self, syms: list[str], t: float) -> list[str]:
        out: list[tuple[float, str]] = []
        for s in syms:
            n, until = self.fails.get(s, (0, 0.0))
            if n and t < until:
                continue
            age = t - self.at.get(s, 0.0)
            if age >= TTL_SEC:
                out.append((-age, s))
        return [s for _, s in sorted(out)]

    def fetch_one(self, sym: str, t: float) -> str | None:
        r = fetch(URL.format(sym=sym.replace(".", "-")), key=f"earnhist_{sym}", ttl_sec=TTL_SEC,
                  ua=BROWSER_UA, timeout=20, headers={"Accept": "application/json"},
                  stale_max_sec=STALE_MAX_SEC, validate=json_body)
        if not r.ok or r.body is None:
            n = self.fails.get(sym, (0, 0.0))[0] + 1
            self.fails[sym] = (n, t + min(FAIL_BASE * 2 ** (n - 1), FAIL_CAP))
            self.errors[sym] = r.error or "unavailable"
            return self.errors[sym]
        try:
            rows = parse(r.json())
        except ValueError as e:
            self.errors[sym] = f"unreadable ({e})"
            return self.errors[sym]
        self.data[sym] = rows
        self.at[sym] = t - (r.age_min or 0.0) * 60.0
        self.fails.pop(sym, None)
        self.errors.pop(sym, None)
        # The next report, from the same host; its failure costs only itself.
        rn = fetch(NEXT_URL.format(sym=sym.replace(".", "-")), key=f"earnnext_{sym}",
                   ttl_sec=TTL_SEC, ua=BROWSER_UA, timeout=20,
                   headers={"Accept": "application/json"}, stale_max_sec=STALE_MAX_SEC,
                   validate=json_body)
        if rn.ok and rn.body is not None:
            try:
                nxt = parse_next(rn.json())
            except ValueError:
                nxt = None
            if nxt is not None:
                self.next[sym] = nxt
            else:
                self.next.pop(sym, None)
        return None

    def tick(self, syms: list[str], now: datetime | None = None) -> SourceStatus:
        now = now or datetime.now(UTC)
        t = now.timestamp()
        st = SourceStatus("Earnings history")
        err: str | None = None
        for sym in self.due(syms, t)[:1]:
            e = self.fetch_one(sym, t)
            if e:
                err = f"{sym}: {e}"
        have = [s for s in syms if s in self.data]
        st.items = len(have)
        st.ok = bool(have)
        st.source = "live" if st.ok else "unavailable"
        st.age_min = (max((t - self.at[s]) / 60.0 for s in have) if have else None)
        if err:
            st.error = err
        if st.ok:
            st.last_ok_utc = datetime.now(UTC).isoformat()
        missing = [s for s in syms if s not in self.data]
        if missing:
            st.notes.append(f"no history yet: {', '.join(missing[:5])}")
        return st

    def view(self) -> dict[str, list[dict[str, Any]]]:
        return dict(self.data)

    def view_next(self) -> dict[str, dict[str, Any]]:
        return dict(self.next)

    def dates(self, sym: str) -> list[date]:
        out: list[date] = []
        for r in self.data.get(sym) or []:
            try:
                out.append(date.fromisoformat(r["date"]))
            except (ValueError, KeyError):
                continue
        return out

