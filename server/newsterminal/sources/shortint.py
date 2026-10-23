"""
Short interest and float, per scanner name — Yahoo's quote summary.

WHY (owner, 2026-10-22: the assessment found no squeeze flag). A short setup
on a name with a quarter of its float sold short is a different trade from
the same setup on a megacap: the retest can fail on a squeeze that has
nothing to do with the level. FINRA publishes short interest twice a month
and Yahoo carries the latest figure with the float, the days to cover and
the prior month's number, which is all the flag needs. Personal use only,
like every other Yahoo read in this terminal.

THE CRUMB. Yahoo's quote-summary endpoint wants a session cookie and a
"crumb" tied to it: one GET to fc.yahoo.com sets the cookie (its 404 is
normal), one to /v1/test/getcrumb returns the crumb, and both ride on every
summary request. A 401 or 403 means the pair has expired and is fetched
again, once; a 429 pauses the fetcher for five minutes.

THE BUDGET. One name a tick, twelve hours between reads of the same name:
the default list is read in about ten minutes after a start and then a
handful of requests an hour. ~6 KB a read. Nothing here blocks the board —
the job runs on the scanner's thread.
"""

from __future__ import annotations

import http.cookiejar
import json
import time
import urllib.error
import urllib.parse
import urllib.request
from datetime import UTC, datetime
from typing import Any

from ..config import BROWSER_UA
from ..http import CACHE, SourceStatus

COOKIE_URL = "https://fc.yahoo.com"
CRUMB_URL = "https://query2.finance.yahoo.com/v1/test/getcrumb"
SUMMARY = ("https://query2.finance.yahoo.com/v10/finance/quoteSummary/{sym}"
           "?modules=defaultKeyStatistics&crumb={crumb}")

TICK_SEC = 20.0
TTL_SEC = 12 * 3600.0
PAUSE_SEC = 300.0
FAIL_BASE = 120.0
FAIL_CAP = 3600.0
TIMEOUT = 15
#: Share of the float short at or past which a short setup carries the flag.
SQUEEZE_PCT = 15.0


def _raw(v: Any) -> float | None:
    """Yahoo wraps numbers as {"raw": x, "fmt": "…"}; a bare number is kept too."""
    if isinstance(v, dict):
        v = v.get("raw")
    if isinstance(v, bool) or not isinstance(v, (int, float)):
        return None
    return float(v)


def parse(doc: Any) -> dict[str, Any] | None:
    """A quoteSummary document → the short-interest read. Pure; None when empty."""
    try:
        k = doc["quoteSummary"]["result"][0]["defaultKeyStatistics"]
    except (KeyError, IndexError, TypeError):
        return None
    if not isinstance(k, dict):
        return None
    pct = _raw(k.get("shortPercentOfFloat"))
    shares = _raw(k.get("sharesShort"))
    flt = _raw(k.get("floatShares"))
    if pct is None and shares is not None and flt:
        pct = shares / flt
    if pct is None and shares is None:
        return None
    as_of = k.get("dateShortInterest")
    as_of = as_of.get("fmt") if isinstance(as_of, dict) else None
    return {
        "pct_float": round(pct * 100.0, 2) if pct is not None else None,
        "days_to_cover": _raw(k.get("shortRatio")),
        "shares_short": shares,
        "prior_month": _raw(k.get("sharesShortPriorMonth")),
        "float_shares": flt,
        "as_of": as_of,
    }


def squeeze_flag(short: dict[str, Any] | None, side: str | None) -> dict[str, str] | None:
    """The flag a setup carries when the float is heavily shorted. Pure."""
    if not short or side not in ("long", "short"):
        return None
    pct = short.get("pct_float")
    if pct is None or pct < SQUEEZE_PCT:
        return None
    dtc = short.get("days_to_cover")
    tail = f", {dtc:.1f} days to cover" if dtc else ""
    if side == "short":
        return {"kind": "short_interest", "tone": "warn",
                "text": f"Squeeze risk: {pct:.0f}% of the float is short{tail} — a failed "
                        f"retest can run"}
    return {"kind": "short_interest", "tone": "info",
            "text": f"{pct:.0f}% of the float is short{tail} — fuel for a squeeze on a break"}


class ShortStore:
    """The reads held between ticks; one name a tick; crumb kept in memory."""

    def __init__(self) -> None:
        self.data: dict[str, dict[str, Any]] = {}
        self.at: dict[str, float] = {}
        self.errors: dict[str, str] = {}
        self.fails: dict[str, tuple[int, float]] = {}
        self.pause_until = 0.0
        self._jar = http.cookiejar.CookieJar()
        self._opener = urllib.request.build_opener(urllib.request.HTTPCookieProcessor(self._jar))
        self._crumb: str | None = None
        self._warm = False

    # ---- the crumb ----------------------------------------------------------

    def _get(self, url: str) -> tuple[int, bytes]:
        req = urllib.request.Request(url, headers={"User-Agent": BROWSER_UA, "Accept": "*/*"})
        try:
            with self._opener.open(req, timeout=TIMEOUT) as r:
                return int(getattr(r, "status", 200)), r.read()
        except urllib.error.HTTPError as e:
            return int(e.code), b""

    def crumb(self, refresh: bool = False) -> str | None:
        if self._crumb and not refresh:
            return self._crumb
        self._jar.clear()
        self._get(COOKIE_URL)  # a 404 — the cookie is what it sets
        code, body = self._get(CRUMB_URL)
        text = body.decode("utf-8", errors="replace").strip()
        if code == 200 and text and "<" not in text:
            self._crumb = text
            return text
        self._crumb = None
        return None

    # ---- the rotation -------------------------------------------------------

    def _warm_start(self, syms: list[str]) -> None:
        self._warm = True
        now = time.time()
        for sym in syms:
            key = f"short_{sym}"
            blob, age = CACHE.read(key), CACHE.age_sec(key)
            if blob is None or age is None:
                continue
            try:
                self.data[sym] = json.loads(blob)
                self.at[sym] = now - age
            except ValueError:
                continue

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
        crumb = self.crumb()
        if crumb is None:
            return "no crumb from Yahoo"
        ysym = sym.replace(".", "-")
        url = SUMMARY.format(sym=urllib.parse.quote(ysym), crumb=urllib.parse.quote(crumb))
        code, body = self._get(url)
        if code in (401, 403) and self.crumb(refresh=True):
            url = SUMMARY.format(sym=urllib.parse.quote(ysym),
                                 crumb=urllib.parse.quote(self._crumb or ""))
            code, body = self._get(url)
        if code == 429:
            self.pause_until = t + PAUSE_SEC
        if code != 200 or not body:
            n = self.fails.get(sym, (0, 0.0))[0] + 1
            self.fails[sym] = (n, t + min(FAIL_BASE * 2 ** (n - 1), FAIL_CAP))
            err = f"HTTP {code}" if code else "unreachable"
            self.errors[sym] = err
            return err
        try:
            parsed = parse(json.loads(body))
        except ValueError:
            parsed = None
        if parsed is None:
            self.errors[sym] = "no short-interest figures"
            self.at[sym] = t  # nothing to read: do not retry for a while
            return self.errors[sym]
        self.data[sym] = parsed
        self.at[sym] = t
        self.fails.pop(sym, None)
        self.errors.pop(sym, None)
        CACHE.write(f"short_{sym}", json.dumps(parsed).encode())
        return None

    def tick(self, syms: list[str], now: datetime | None = None) -> SourceStatus:
        now = now or datetime.now(UTC)
        t = now.timestamp()
        if not self._warm:
            self._warm_start(syms)
        st = SourceStatus("Short interest")
        err: str | None = None
        paused = t < self.pause_until
        if not paused:
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
            st.notes.append(f"no read yet: {', '.join(missing[:5])}")
        if paused:
            st.notes.append("Yahoo rate-limited the summary reads — paused")
        return st

    def view(self) -> dict[str, dict[str, Any]]:
        return dict(self.data)
