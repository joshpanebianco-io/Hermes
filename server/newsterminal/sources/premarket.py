"""
Today's pre-market for each watchlist name — Nasdaq's free extended-trading page.

WHY NASDAQ. The scanner's PMH / PML come from Yahoo's five-minute bars, and
those bars carry no volume before the open, so "is this name in play before
the bell?" had no answer. Nasdaq's extended-trading JSON — the data behind its
public pre-market quote page, free and keyless — gives the session's
consolidated share volume, high, low and last trade. Personal use, read
politely; GEXYGEN plays no part in it.

THE ENDPOINT, PROBED LIVE (2026-10-13 at 10:05 ET — AAPL, SPY, SPCX):

    GET https://api.nasdaq.com/api/quote/{SYM}/extended-trading
        ?markettype=pre&assetclass={stocks|etf}
    with a browser User-Agent and Accept: application/json; ~7 KB a read.

  - data.infoTable.rows[0], every value a display string:
        consolidated  "$345.27 +4.30 (+1.26%)"   last trade, change on the close
        volume        "690,259"                  shares, thousands commas
        highPrice     "$345.3 (09:30:00 AM)"     price, and the ET time it printed
        lowPrice      "$340.118 (08:15:22 AM)"
  - data.lastUpdateInfo[0]: "Data last updated Oct 13, 2026 09:30 AM ET." —
    which session the numbers belong to and when they were taken. The page
    keeps serving that session after the open and through the night ("This
    page will resume updating on Oct 14, 2026 04:00 AM ET."), so a read is
    today's only when that line says so. No line, no read.
  - data.tradeDetailTable: the last trades one by one — not read.
  - THE ASSET CLASS MUST MATCH. SPY answers only to assetclass=etf; AAPL and
    SPCX only to stocks. The wrong one is HTTP 200 with `data: null` and
    status.bCodeMessage [{code: 1001, "Symbol not exists."}]. Known ETFs go as
    etf; any other name tries stocks and flips once on that answer.
  - Treat it as up to fifteen minutes behind, like every free quote this
    terminal reads: the `asof` it carries says when it was taken.

THE CADENCE (one request per TICK_SEC at most, most overdue name first):
  - 04:00-08:00 ET on a trading day (holidays.py): each name every ten
    minutes — the early tape is thin and moves slowly.
  - 08:00-09:35: every five minutes.
  - 09:30-09:35: every name not yet read since 09:30 is due at once, so each
    keeps the session's final figures.
  - After that, until the scanner's day rolls (20:00; 17:00 on a half day), a
    name whose read is not final gets at most LATE_TRIES more — Nasdaq still
    serves the morning's numbers, so a collector started at noon still knows
    them. Nothing at all otherwise: weekends, holidays, overnight.
  With the default 21 names that is about 900 requests a morning (~6 MB) —
  one every 16 seconds on average, never more than one per ten.
  A failure backs the name off, doubling from a minute to half an hour; a 403
  or 429 pauses every read for ten minutes.

KEPT FOR THE DAY. `view(trading_day)` gives only reads whose session (the
"last updated" line) is the scanner's trading day. The scanner's rows roll to
the next day's levels at 20:00, and the pre-market goes with them — a row
never shows one day's pre-market beside the next day's PDH / PDL. From then
until the first read after 04:00 there is none: null, not yesterday's. Reads
persist in one small cache file, so a restart repaints at once.
"""

from __future__ import annotations

import json
import re
import urllib.parse
from datetime import UTC, date, datetime
from typing import Any

from .. import scan
from ..config import BROWSER_UA
from ..http import CACHE, SourceStatus, fetch, json_body

URL = ("https://api.nasdaq.com/api/quote/{sym}/extended-trading"
       "?markettype=pre&assetclass={cls}")
SUMMARY_KEY = "nasdaq_premarket"

TICK_SEC = 10.0
MAX_PER_TICK = 1
TIMEOUT = 15
#: Per-name refresh: before FAST_FROM, then from it to the end of the window.
EARLY_SEC = 600.0
NAME_SEC = 300.0
WINDOW_FROM = 4 * 60
FAST_FROM = 8 * 60
OPEN = 9 * 60 + 30
WINDOW_TO = 9 * 60 + 35
#: Reads after the window for a name whose figures are not yet final.
LATE_TRIES = 3
FAIL_BASE = 60.0
FAIL_CAP = 1800.0
PAUSE_SEC = 600.0

#: Nasdaq's "Symbol not exists." — the asset class was the wrong one.
NOSYM = "nosym"
#: Funds that answer only to assetclass=etf. Anything else tries stocks first.
ETFS = frozenset({
    "SPY", "QQQ", "IWM", "DIA", "RSP", "MDY", "SMH", "SOXX", "XLK", "XLF", "XLE", "XLV",
    "XLI", "XLY", "XLP", "XLU", "XLB", "XLRE", "XLC", "KRE", "KBE", "XBI", "IBB", "XRT",
    "XHB", "ITB", "GDX", "GDXJ", "GLD", "SLV", "USO", "UNG", "TLT", "IEF", "HYG", "LQD",
    "ARKK", "TQQQ", "SQQQ", "SOXL", "SOXS", "UVXY", "VXX", "EEM", "EFA", "FXI", "KWEB",
    "IBIT", "ETHA", "BITO",
})

_NUM = re.compile(r"-?\d[\d,]*(?:\.\d+)?")
_UPDATED = re.compile(
    r"updated\s+([A-Z][a-z]{2})[a-z]*\.?\s+(\d{1,2}),\s*(\d{4})\s+(\d{1,2}):(\d{2})\s*([AP]M)",
    re.I)
_MONTHS = {m: i for i, m in enumerate(
    ("jan", "feb", "mar", "apr", "may", "jun", "jul", "aug", "sep", "oct", "nov", "dec"), 1)}


# ----------------------------------------------------------------------- parse


def _num(v: Any) -> float | None:
    """The first number in a display string: "$345.27 +4.30" → 345.27, "690,259" → 690259."""
    if isinstance(v, (int, float)) and not isinstance(v, bool):
        return float(v)
    m = _NUM.search(str(v or ""))
    if m is None:
        return None
    try:
        return float(m.group(0).replace(",", ""))
    except ValueError:
        return None


def parse_updated(text: str) -> datetime | None:
    """ "Data last updated Oct 13, 2026 09:30 AM ET." → that instant, in ET. Pure."""
    m = _UPDATED.search(text or "")
    if m is None:
        return None
    mon = _MONTHS.get(m.group(1).lower())
    hour, minute = int(m.group(4)) % 12, int(m.group(5))
    if m.group(6).upper() == "PM":
        hour += 12
    try:
        return datetime(int(m.group(3)), mon or 0, int(m.group(2)), hour, minute,
                        tzinfo=scan.ET)
    except ValueError:
        return None


def parse(doc: Any) -> tuple[dict[str, Any] | None, str | None]:
    """A Nasdaq extended-trading document → (read, problem). Pure.

    A read is {day, asof, volume, high, low, last}, every figure a number or
    None. `problem` is NOSYM for the wrong asset class, else a sentence. A page
    with a session date and no prints at all (just after 04:00) is neither: it
    comes back (None, None).
    """
    if not isinstance(doc, dict):
        return None, "Nasdaq sent something other than a JSON object"
    data = doc.get("data")
    if not isinstance(data, dict):
        msgs = ((doc.get("status") or {}).get("bCodeMessage") or []) \
            if isinstance(doc.get("status"), dict) else []
        codes = [m.get("code") for m in msgs if isinstance(m, dict)]
        if 1001 in codes:
            return None, NOSYM
        said = next((str(m.get("errorMessage")) for m in msgs
                     if isinstance(m, dict) and m.get("errorMessage")), "")
        return None, f"Nasdaq sent no data{f' ({said})' if said else ''}"
    info = data.get("lastUpdateInfo")
    lines = info if isinstance(info, list) else [info]
    asof = None
    for line in lines:
        asof = parse_updated(str(line or ""))
        if asof is not None:
            break
    if asof is None:
        return None, "Nasdaq's page has no 'last updated' line — cannot tell which session"
    rows = (data.get("infoTable") or {}).get("rows") if isinstance(
        data.get("infoTable"), dict) else None
    row = rows[0] if isinstance(rows, list) and rows and isinstance(rows[0], dict) else {}
    vol = _num(row.get("volume"))
    last, high, low = (_num(row.get(k)) for k in ("consolidated", "highPrice", "lowPrice"))
    if vol is None and last is None and high is None and low is None:
        return None, None
    for p in (last, high, low):
        if p is not None and p <= 0:
            return None, f"Nasdaq sent a non-positive price ({p})"
    if high is not None and low is not None and high < low:
        return None, f"Nasdaq's pre-market high {high} is below its low {low}"
    return {
        "day": asof.date().isoformat(), "asof": asof.isoformat(),
        "volume": int(vol) if vol is not None and vol >= 0 else None,
        "high": high, "low": low, "last": last,
    }, None


def is_final(read: dict[str, Any]) -> bool:
    """Taken at or after 09:30 ET — the session's closing figures."""
    try:
        t = datetime.fromisoformat(str(read.get("asof")))
    except ValueError:
        return False
    return t.hour * 60 + t.minute >= OPEN


# --------------------------------------------------------------------- cadence


def phase(now: datetime) -> str:
    """"window" (04:00-09:35 on a trading day), "late" (after it, until the
    scanner's day rolls), or "idle". Pure."""
    c = scan.clock_at(now)
    et = c.now
    m = et.hour * 60 + et.minute
    if c.trading_day != et.date() or m < WINDOW_FROM:
        return "idle"
    return "window" if m < WINDOW_TO else "late"


def cadence(now: datetime) -> float:
    et = now.astimezone(scan.ET)
    return EARLY_SEC if et.hour * 60 + et.minute < FAST_FROM else NAME_SEC


def _open_ts(day: date) -> float:
    return datetime(day.year, day.month, day.day, OPEN // 60, OPEN % 60,
                    tzinfo=scan.ET).timestamp()


# ----------------------------------------------------------------------- store


class PremarketStore:
    """The day's reads, one per name. Written only by the pre-market thread;
    the read path copies (`view`) and a read is replaced whole, never mutated."""

    def __init__(self, key: str = SUMMARY_KEY) -> None:
        self.key = key
        self.reads: dict[str, dict[str, Any]] = {}
        self.attempt: dict[str, float] = {}
        #: Reads tried since 09:30, per name: (day, count).
        self.after_open: dict[str, tuple[str, int]] = {}
        self.cls: dict[str, str] = {}
        self.flipped: set[str] = set()
        self.fails: dict[str, tuple[int, float]] = {}
        self.errors: dict[str, str] = {}
        #: Names whose last answer was another session's page, and that session.
        self.other_day: dict[str, str] = {}
        self.pause_until = 0.0
        self._warm = False

    def view(self, trading_day: date) -> dict[str, dict[str, Any]]:
        """{sym: {volume, high, low, last, asof}} for reads of `trading_day` only."""
        day = trading_day.isoformat()
        return {s: {k: v for k, v in r.items() if k != "day"}
                for s, r in dict(self.reads).items() if r.get("day") == day}

    def _warm_start(self) -> None:
        self._warm = True
        blob = CACHE.read(self.key)
        if blob is None:
            return
        try:
            d = json.loads(blob)
        except ValueError:
            return
        reads = d.get("reads") if isinstance(d, dict) else None
        for sym, r in (reads or {}).items():
            if isinstance(r, dict) and isinstance(r.get("day"), str) and r.get("asof"):
                self.reads[str(sym)] = r
        for sym, c in ((d.get("cls") if isinstance(d, dict) else None) or {}).items():
            if c in ("stocks", "etf"):
                self.cls[str(sym)] = c

    def _save(self, syms: list[str]) -> None:
        keep = set(syms)
        CACHE.write(self.key, json.dumps({
            "reads": {s: r for s, r in self.reads.items() if s in keep},
            "cls": {s: c for s, c in self.cls.items() if s in keep},
        }, separators=(",", ":")).encode())

    def due(self, syms: list[str], now: datetime) -> list[str]:
        """Names due a read at `now`, most overdue first (module docstring)."""
        ph = phase(now)
        if ph == "idle":
            return []
        t = now.timestamp()
        et = now.astimezone(scan.ET)
        day = et.date().isoformat()
        open_ts = _open_ts(et.date())
        every = cadence(now)
        out: list[tuple[float, str]] = []
        for s in syms:
            n, until = self.fails.get(s, (0, 0.0))
            if n and t < until:
                continue
            last = self.attempt.get(s, 0.0)
            r = self.reads.get(s)
            final = r is not None and r.get("day") == day and is_final(r)
            lag = t - last - every
            if ph == "window":
                if t >= open_ts and last < open_ts and not final:
                    lag = max(lag, t - open_ts)
            else:
                tries = self.after_open.get(s, ("", 0))
                if final or (tries[0] == day and tries[1] >= LATE_TRIES):
                    continue
            if lag >= 0:
                out.append((-lag, s))
        return [s for _, s in sorted(out)]

    def fetch_one(self, sym: str, now: datetime, st: SourceStatus) -> str | None:
        """Read one name and keep it if it is today's. Returns an error, or None."""
        t = now.timestamp()
        et = now.astimezone(scan.ET)
        day = et.date().isoformat()
        cls = self.cls.get(sym) or ("etf" if sym in ETFS else "stocks")
        url = URL.format(sym=urllib.parse.quote(sym.replace("-", ".")), cls=cls)
        r = st.absorb(fetch(url, key=f"nasdaq_pre_{sym}", ttl_sec=0, ua=BROWSER_UA,
                            timeout=TIMEOUT, headers={"Accept": "application/json"},
                            stale_ok=False, store=False, validate=json_body))
        self.attempt[sym] = t
        if t >= _open_ts(et.date()):
            prev = self.after_open.get(sym, ("", 0))
            self.after_open[sym] = (day, (prev[1] if prev[0] == day else 0) + 1)
        err: str | None
        if not r.ok or r.body is None:
            if r.status in (403, 429):
                self.pause_until = t + PAUSE_SEC
            err = f"Nasdaq: {r.error or 'unreachable'}"
            return self._fail(sym, t, err)
        try:
            doc = json.loads(r.body)
        except ValueError as e:
            return self._fail(sym, t, f"Nasdaq sent unreadable JSON ({e})")
        read, err = parse(doc)
        if err == NOSYM:
            if sym in self.flipped:
                self.fails[sym] = (99, t + FAIL_CAP)
                self.errors[sym] = "Nasdaq lists no pre-market for this symbol"
                return self.errors[sym]
            # The other asset class, on the next tick; this answer is not a failure.
            self.flipped.add(sym)
            self.cls[sym] = "etf" if cls == "stocks" else "stocks"
            self.attempt[sym] = 0.0
            if t >= _open_ts(et.date()):
                d, n = self.after_open[sym]
                self.after_open[sym] = (d, max(0, n - 1))
            return None
        if err is not None:
            return self._fail(sym, t, err)
        self.fails.pop(sym, None)
        self.errors.pop(sym, None)
        self.cls[sym] = cls
        if read is None:
            self.other_day.pop(sym, None)
            return None
        if read["day"] != day:
            # Nasdaq still on an earlier session (just after 04:00): not today's.
            self.other_day[sym] = read["day"]
            return None
        self.other_day.pop(sym, None)
        self.reads[sym] = read
        return None

    def _fail(self, sym: str, t: float, err: str) -> str:
        n = self.fails.get(sym, (0, 0.0))[0] + 1
        self.fails[sym] = (n, t + min(FAIL_BASE * 2 ** (n - 1), FAIL_CAP))
        self.errors[sym] = err
        return err

    def tick(self, syms: list[str], now: datetime | None = None) -> SourceStatus:
        """One step: at most MAX_PER_TICK reads, then the status."""
        now = now or datetime.now(UTC)
        if not self._warm:
            self._warm_start()
        st = SourceStatus("Nasdaq pre-market")
        t = now.timestamp()
        ph = phase(now)
        due = self.due(syms, now)
        paused = t < self.pause_until
        errors: list[str] = []
        done = 0
        if not paused:
            for sym in due[:MAX_PER_TICK]:
                before = dict(self.reads)
                err = self.fetch_one(sym, now, st)
                done += 1
                if err:
                    errors.append(f"{sym}: {err}")
                if self.reads != before:
                    self._save(syms)

        td = scan.clock_at(now).trading_day.isoformat()
        have = [s for s in syms if (self.reads.get(s) or {}).get("day") == td]
        st.items = len(have)
        if errors:
            st.error = errors[0]
        failing = ph != "idle" and not have and any(s in self.errors for s in syms)
        st.settle(not failing, what="read")
        if ph == "idle":
            st.notes = ["idle — reads 04:00-09:35 ET on trading days"
                        + (f"; holding {len(have)} for {td}" if have else "")]
        else:
            st.notes = [f"{len(have)} of {len(syms)} read for {td} · {done} fetched, "
                        f"{max(len(due) - done, 0)} due"]
            missing = [s for s in syms if s not in have]
            if missing:
                st.notes.append(f"no read yet: {', '.join(missing[:5])}"
                                + ("…" if len(missing) > 5 else ""))
            behind = sorted({d for s, d in self.other_day.items() if s in syms})
            if behind:
                st.notes.append(f"Nasdaq still serving {', '.join(behind)}'s session for "
                                f"{sum(1 for s in self.other_day if s in syms)} name(s)")
        backing = [s for s in syms if self.fails.get(s, (0, 0.0))[0] and t < self.fails[s][1]]
        if backing:
            st.notes.append(f"backing off: {', '.join(backing[:4])}")
        if paused:
            until = datetime.fromtimestamp(self.pause_until, scan.ET).strftime("%H:%M:%S")
            st.notes.append(f"Nasdaq refused (403/429) — paused until {until} ET")
        return st
