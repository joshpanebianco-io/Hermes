"""
The bias record, backfilled: the driver board's reads at the record's marks over the
two years Yahoo's hourly bars reach, written in the live record's own lines so the
reader judges both the same way.

    .venv\\Scripts\\python.exe -I tools/bias_backfill.py                  # build it
    .venv\\Scripts\\python.exe -I tools/bias_backfill.py --check 2026-11-18
    .venv\\Scripts\\python.exe -I tools/bias_record.py --file cache/bias_backfill.jsonl

THE ENGINE IS THE LIVE ONE. At every mark of newsterminal/bias_record.py this rebuilds
the snapshot blocks the driver board reads (quotes, the context feed's daily closes, the
prior New York value area, the last completed session box, the sectors) as they stood at
that instant, from bars that had printed by then, and hands them to `drivers.build`. Its
reads, `drivestats.Stats` for the usual day, `bias_record.read_line` and `close_line` are
called as the collector calls them. Nothing in newsterminal/ is changed by this.

WHAT IS NOT REBUILT, so cannot vote here though it can live:
  * the calendar (the inflation prints, the crude inventories, the growth prints): the
    catalysts family never votes and its weight reads as no lean;
  * the index leaders (constituents) and the heavyweights' prints: participation is the
    sectors alone in the session;
  * the wire (event risk never damps), gamma (never a side anyway), COT, put/call.

WHAT HOURLY BARS COST. Futures bars start on the hour, so a book's price at 10:30 is its
10:00 close. EVERY MARK IS READ AT THE HOUR IT FALLS IN (03:30 at 03:00, 08:45 at 08:00,
09:25 at 09:00, 10:30 at 10:00), every input with it: read at 10:30 the sector ETFs and
credit, on :30 bars, carried the index's 10:00-10:30 move, which is inside the outcome
measured from the 10:00 price, and they looked predictive for it. So the 08:45 read is
from before the 08:30 prints, and the cash 10-year (bars from 08:20) cannot vote in it.
`at` on a line is the instant read; `mark` is the record's. An input's price is the last
printed by then: the close of the last bar to have ended, or the open of a bar that started
since (the 10-year's bars start at :20, the VIX's at 03:00, the ETFs' at :30). The boxes
and the prior value area take a bar by where its middle falls: New York is 09:00-16:00, the
pre-market 04:00-09:00. A feed is live when its market printed a bar starting in the 90
minutes before.

CONTRACT ROLLS. Yahoo's continuous futures switch contract with a jump of the carry,
sometimes over a weekend, where no price series alone can tell it from a gap. Each book is
read against its ETF (QQQ, SPY, GLD, SLV, USO) at New York's close; a step in that ratio is
a roll, placed at the hourly bar that jumped when one did. A read whose inputs or outcome
straddle a roll is not written, and a quote whose day change straddles one leaves the
board. Within a trading day a bar whose whole range sits off the last close is a seam too
(the drivers' rolls are caught only that way).

THE CALENDAR. newsterminal/holidays.py runs from 2025. Before it a session is read only
when it and the weekday before it were full sessions on SPY's tape, so no 2024 holiday or
half day is taken for a normal day.

Every Yahoo answer is kept on disk (cache/bfx_*), so a second run makes no request.
"""

from __future__ import annotations

import argparse
import bisect
import json
import os
import re
import sys
import time as clock
import urllib.request
from collections import Counter
from datetime import date, datetime, time, timedelta
from typing import Any, NamedTuple
from zoneinfo import ZoneInfo

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from newsterminal import bias_record, drivers, profile
from newsterminal import drivestats as ds
from newsterminal.config import BROWSER_UA, CACHE_DIR
from newsterminal.holidays import covered, is_trading_day
from newsterminal.sessions import globex_trade_date

ET = ZoneInfo("America/New_York")
LONDON = ZoneInfo("Europe/London")

CHART = "https://query1.finance.yahoo.com/v8/finance/chart/{sym}?range={rng}&interval={iv}"
HOURLY = ("730d", "1h")
DAILY = ("3y", "1d")
OUT_FILE = os.path.join(CACHE_DIR, "bias_backfill.jsonl")
HOUR = 3600

#: The board's quotes: key -> (Yahoo symbol, kind, settle ET). A "fut" trades round the
#: clock; its day is the Globex trade date and its previous close is its own hourly
#: series at the settle (the daily series of silver and copper is another contract:
#: 0.5% off every hour). A "cash" market's day is the calendar's, its previous close
#: the daily bar's (or its last hourly bar's where no daily is fetched). The settles are
#: the hour whose close matches Yahoo's daily close best.
QUOTES: dict[str, tuple[str, str, time | None]] = {
    "NQ": ("NQ=F", "fut", time(16, 0)),
    "ES": ("ES=F", "fut", time(16, 0)),
    "GC": ("GC=F", "fut", time(14, 0)),
    "SILVER": ("SI=F", "fut", time(14, 0)),
    "WTI": ("CL=F", "fut", time(15, 0)),
    "US10Y": ("^TNX", "cash", None),
    "ZN": ("ZN=F", "fut", time(15, 0)),
    "DXY": ("DX-Y.NYB", "fut", time(15, 0)),
    "VIX": ("^VIX", "cash", None),
    "VIX3M": ("^VIX3M", "cash", None),
    "HYG": ("HYG", "cash", None),
    "COPPER": ("HG=F", "fut", time(13, 0)),
    "RBOB": ("RB=F", "fut", time(15, 0)),
    "HEATOIL": ("HO=F", "fut", time(15, 0)),
}
#: The context feed's rows the yardsticks read (drivestats.py), from daily bars.
CONTEXT_KEYS: tuple[str, ...] = ("NQ", "ES", "GC", "SILVER", "WTI", "US10Y", "ZN", "DXY",
                                 "VIX", "HYG", "COPPER", "RBOB", "HEATOIL")
CONTEXT_N = 70
SECTORS: tuple[str, ...] = ("XLK", "XLC", "XLY", "XLP", "XLE", "XLF", "XLV", "XLI", "XLB",
                            "XLRE", "XLU", "SPY", "RSP")
#: book -> (its quote, the ETF its rolls are read against, the ratio step that is a roll
#: in percent, the step's sign: +1 where the next contract stands above (contango), 0
#: either way). Silver's ETF wanders against it more than gold's, crude's most.
BOOKS: dict[str, tuple[str, str, float, int]] = {
    "NQ": ("NQ", "QQQ", 0.5, 1), "ES": ("ES", "SPY", 0.5, 1), "GC": ("GC", "GLD", 0.5, 1),
    "SIL": ("SILVER", "SLV", 0.7, 1), "CL": ("WTI", "USO", 0.5, 0),
}
#: Futures whose hourly series is searched for seams inside a trading day. The dollar
#: index is no contract: its jumps at the evening open are its own.
SEAMED: tuple[str, ...] = ("NQ", "ES", "GC", "SILVER", "WTI", "ZN", "COPPER", "RBOB", "HEATOIL")
#: A seam: the last close this many usual hourly moves outside the next bar's range.
SEAM_K = 8.0
SEAM_MIN = 0.15
#: A feed is live with a bar started this recently.
LIVE_SEC = 90 * 60
#: The fewest hourly bars a prior value area is drawn from.
PROFILE_MIN = 3
FIRST_TD = date(2024, 7, 1)

#: (ts, open, high, low, close, volume)
Bar = tuple[int, float, float, float, float, float]


# ---- Yahoo ------------------------------------------------------------------------------


def _cache_path(sym: str, rng: str, iv: str) -> str:
    safe = re.sub(r"[^A-Za-z0-9.-]", "_", sym)
    return os.path.join(CACHE_DIR, f"bfx_{safe}_{rng}_{iv}.json")


def fetch(sym: str, rng: str, iv: str, refresh: bool = False) -> dict[str, Any]:
    """One chart response, from its disk copy when there is one."""
    path = _cache_path(sym, rng, iv)
    if not refresh and os.path.exists(path):
        with open(path, encoding="utf-8") as f:
            return json.load(f)
    req = urllib.request.Request(CHART.format(sym=sym, rng=rng, iv=iv),
                                 headers={"User-Agent": BROWSER_UA, "Accept": "application/json"})
    with urllib.request.urlopen(req, timeout=60) as r:
        doc = json.loads(r.read())
    os.makedirs(CACHE_DIR, exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(doc, f)
    clock.sleep(0.5)
    return doc


def bars_of(doc: dict[str, Any]) -> list[Bar]:
    res = doc["chart"]["result"][0]
    q = res["indicators"]["quote"][0]
    out: list[Bar] = []
    for t, o, h, lo, c, v in zip(res.get("timestamp") or [], q["open"], q["high"], q["low"],
                                 q["close"], q["volume"], strict=True):
        if None in (o, h, lo, c):
            continue
        out.append((int(t), float(o), float(h), float(lo), float(c), float(v or 0.0)))
    out.sort()
    return out


# ---- one instrument's bars ---------------------------------------------------------------


class Px(NamedTuple):
    price: float
    asof: int  # epoch seconds the price is from
    idx: int  # the hourly bar it came from


class Series:
    """One instrument's hourly bars, with the lookups a mark needs. Pure."""

    def __init__(self, bars: list[Bar]) -> None:
        self.ts = [b[0] for b in bars]
        self.o = [b[1] for b in bars]
        self.h = [b[2] for b in bars]
        self.lo = [b[3] for b in bars]
        self.c = [b[4] for b in bars]
        self.v = [b[5] for b in bars]
        n = len(bars)
        self.end = [min(self.ts[i] + HOUR, self.ts[i + 1]) if i + 1 < n else self.ts[i] + HOUR
                    for i in range(n)]
        self.dates = [datetime.fromtimestamp(t, ET).date() for t in self.ts]

    def at(self, t: float) -> Px | None:
        """The last price printed by `t`: the close of the last bar to have ended, or the
        open of a bar that started after it (a tie goes to the close)."""
        j = bisect.bisect_right(self.ts, t) - 1
        if j < 0:
            return None
        if self.end[j] <= t:
            return Px(self.c[j], self.end[j], j)
        if j > 0 and self.end[j - 1] >= self.ts[j]:
            return Px(self.c[j - 1], self.end[j - 1], j - 1)
        return Px(self.o[j], self.ts[j], j)

    def live(self, t: float) -> bool:
        j = bisect.bisect_right(self.ts, t) - 1
        return j >= 0 and self.ts[j] > t - LIVE_SEC

    def last_before(self, d: date) -> float | None:
        """The close of the last bar dated before `d` (ET)."""
        j = bisect.bisect_left(self.dates, d) - 1
        return self.c[j] if j >= 0 else None

    def between(self, start: float, end: float) -> tuple[int, int]:
        """[lo, hi): the bars whose middle falls in [start, end)."""
        return (bisect.bisect_left(self.ts, start - HOUR / 2),
                bisect.bisect_left(self.ts, end - HOUR / 2))

    def seams(self) -> list[int]:
        """Bars whose whole range sits off the last close by SEAM_K usual hourly moves,
        inside one trade date: a contract switch or a feed glitch, never a move."""
        moves = sorted(abs(c / o - 1.0) for o, c in zip(self.o, self.c, strict=True) if o)
        tol = max(SEAM_MIN / 100.0, SEAM_K * moves[len(moves) // 2]) if moves else 1.0
        out: list[int] = []
        for i in range(1, len(self.ts)):
            p = self.c[i - 1]
            off = self.lo[i] / p - 1.0 if p < self.lo[i] else p / self.h[i] - 1.0 if p > self.h[i] else 0.0
            if off > tol and _trade_date(self.ts[i - 1]) == _trade_date(self.ts[i]):
                out.append(i)
        return out


def _trade_date(ts: int) -> date:
    return globex_trade_date(datetime.fromtimestamp(ts, ET))


class Daily:
    """One instrument's daily closes by date (the first bar of a date: Yahoo appends a
    partial bar for the session under way, stamped with the clock)."""

    def __init__(self, bars: list[Bar]) -> None:
        by: dict[date, float] = {}
        for b in bars:
            by.setdefault(datetime.fromtimestamp(b[0], ET).date(), b[4])
        self.days = sorted(by)
        self.closes = [by[d] for d in self.days]
        self.iso = [d.isoformat() for d in self.days]

    def before(self, d: date) -> tuple[date, float] | None:
        j = bisect.bisect_left(self.days, d) - 1
        return (self.days[j], self.closes[j]) if j >= 0 else None

    def hist(self, d: date, n: int) -> dict[str, list[Any]]:
        j = bisect.bisect_left(self.days, d)
        return {"days": self.iso[max(0, j - n):j], "closes": self.closes[max(0, j - n):j]}


# ---- the rolls ---------------------------------------------------------------------------


def roll_spans(fut: Series, etf: Series, step_pct: float, sign: int) -> list[tuple[int, int]]:
    """(k0, k1]: runs of `fut`'s bars a contract switch lies in, from steps in the ratio of
    the future to its ETF at New York's close. Pure.

    A step is placed at the bar that jumped by at least half of it in its direction where
    one did, else it spans the day."""
    closes: dict[date, int] = {}
    for i, d in enumerate(etf.dates):
        closes[d] = i  # the last bar of each date
    out: list[tuple[int, int]] = []
    prev: tuple[float, int] | None = None
    for d in sorted(closes):
        i = closes[d]
        st = datetime.fromtimestamp(etf.ts[i], ET)
        if st.minute != 30:  # a closing stub (the newest day only): the bar before it
            if i == 0 or etf.dates[i - 1] != d:
                continue
            i -= 1
            st = datetime.fromtimestamp(etf.ts[i], ET)
        t = datetime.combine(d, time(16, 0) if st.hour >= 15 else time(13, 0), ET).timestamp()
        p = fut.at(t)
        if p is None or t - p.asof > 2 * HOUR:
            continue
        r = p.price / etf.c[i]
        if prev is not None:
            step = r / prev[0] - 1.0
            if abs(step) * 100.0 >= step_pct and (sign == 0 or step * sign > 0):
                k0, k1 = prev[1], p.idx
                best, at = 0.0, None
                for s in range(k0 + 1, k1 + 1):
                    q = fut.c[s - 1]
                    jump = (fut.lo[s] / q - 1.0 if q < fut.lo[s]
                            else fut.h[s] / q - 1.0 if q > fut.h[s] else 0.0)
                    if jump * (1 if step > 0 else -1) > best:
                        best, at = abs(jump), s
                out.append((at - 1, at) if at is not None and best >= abs(step) / 2 else (k0, k1))
        prev = (r, p.idx)
    return out


def crosses(spans: list[tuple[int, int]], i0: int, i1: int) -> bool:
    """Whether a switch somewhere in (k0, k1] can lie between bars i0 and i1. Pure."""
    return any(k0 < i1 and k1 > i0 for k0, k1 in spans)


# ---- the snapshot blocks -----------------------------------------------------------------


def _box_window(key: str, d: date) -> tuple[float, float]:
    """One session box on its own date (sessions.py: London keeps London's clock)."""
    if key == "asia":
        s = datetime.combine(d, time(20, 0), ET)
        return s.timestamp(), datetime.combine(d + timedelta(days=1), time(0, 0), ET).timestamp()
    if key == "london":
        return (datetime.combine(d, time(7, 0), LONDON).timestamp(),
                datetime.combine(d, time(10, 0), LONDON).timestamp())
    if key == "premkt":
        return (datetime.combine(d, time(4, 0), ET).timestamp(),
                datetime.combine(d, time(9, 30), ET).timestamp())
    return (datetime.combine(d, time(9, 30), ET).timestamp(),
            datetime.combine(d, time(16, 0), ET).timestamp())


BOXES = (("asia", "Asia"), ("london", "London"), ("premkt", "Pre-market"), ("ny", "New York"))


def boxes(s: Series, now: datetime) -> tuple[list[dict[str, Any]], int | None]:
    """The most recent completed occurrence of each box that is not under way now (the
    collector's ranges mark the one under way live, and the board skips it), and the
    first bar of the one the board reads (the latest to start). Pure."""
    t = now.timestamp()
    rows: list[dict[str, Any]] = []
    first: int | None = None
    for key, label in BOXES:
        base = now.astimezone(LONDON if key == "london" else ET).date()
        for k in range(8):
            a, b = _box_window(key, base - timedelta(days=k))
            if a > t:
                continue
            if t < b:
                break  # under way: no completed row for this box
            lo, hi = s.between(a, b)
            if lo >= hi:
                continue
            rows.append({"key": key, "label": label, "ok": True, "status": "complete",
                         "high": max(s.h[lo:hi]), "low": min(s.lo[lo:hi]),
                         "start_ts": s.ts[lo]})
            if first is None or s.ts[lo] > s.ts[first]:
                first = lo
            break
    return rows, first


def value_area(s: Series, now: datetime, book: str) -> tuple[dict[str, Any] | None, int | None]:
    """The prior New York session's value area (the profile panel's "prev_rth" window,
    profile.windows), from the hourly bars whose middle falls in it, drawn by the
    collector's own profile.build. Each bar is handed over twice at half its volume,
    which leaves the profile as it was and clears the six-bar floor set for 5-minute
    bars. A window with too few bars walks back a trading day, as the collector's does."""
    w = next((x for x in profile.windows(now.astimezone(ET), book) if x["key"] == "prev_rth"),
             None)
    if w is None:
        return None, None
    start, end = w["start"], w["end"]
    for _ in range(5):
        lo, hi = s.between(start.timestamp(), end.timestamp())
        bars = [(s.h[i], s.lo[i], s.v[i] / 2.0) for i in range(lo, hi) if s.v[i] > 0]
        if len(bars) >= PROFILE_MIN:
            prof = profile.build(bars * 2)
            if prof is not None:
                return {"key": "prev_rth", "vah": prof["vah"], "val": prof["val"],
                        "poc": prof["poc"]}, lo
        prev = profile.prev_trading_day(start)
        o, c = profile.rth_open(book), profile.rth_close(prev.date(), book)
        start = datetime.combine(prev.date(), o, ET)
        end = datetime.combine(prev.date(), c, ET)
    return None, None


class Data:
    def __init__(self, refresh: bool = False) -> None:
        self.h: dict[str, Series] = {}
        self.d: dict[str, Daily] = {}
        for key, (sym, _, _) in QUOTES.items():
            self.h[key] = Series(bars_of(fetch(sym, *HOURLY, refresh)))
        for key in CONTEXT_KEYS:
            self.d[key] = Daily(bars_of(fetch(QUOTES[key][0], *DAILY, refresh)))
        for sym in {*SECTORS, *(b[1] for b in BOOKS.values())}:
            self.h[sym] = Series(bars_of(fetch(sym, *HOURLY, refresh)))
        self.seams = {k: [(i - 1, i) for i in self.h[k].seams()] for k in SEAMED}
        self.rolls = {b: roll_spans(self.h[q], self.h[etf], step, sign)
                      for b, (q, etf, step, sign) in BOOKS.items()}
        # A book's quote carries its rolls as well as its seams.
        self.dirty: dict[str, list[tuple[int, int]]] = {k: list(v) for k, v in self.seams.items()}
        for b, (q, *_) in BOOKS.items():
            self.dirty[q] = self.dirty.get(q, []) + self.rolls[b]

    def prev_close(self, key: str, now: datetime) -> tuple[float, int | None] | None:
        """(the previous close, the bar it came from for a future)."""
        _sym, kind, settle = QUOTES[key]
        if kind == "fut" and settle is not None:
            got = self.d[key].before(globex_trade_date(now)) if key in self.d else None
            if got is None:
                return None
            p = self.h[key].at(datetime.combine(got[0], settle, ET).timestamp())
            return (p.price, p.idx) if p else None
        day = now.astimezone(ET).date()
        if key in self.d:
            got = self.d[key].before(day)
            return (got[1], None) if got else None
        c = self.h[key].last_before(day)
        return (c, None) if c is not None else None

    def quote(self, key: str, now: datetime) -> tuple[dict[str, Any] | None, str | None]:
        """One board row at `now`, or why there is none."""
        s = self.h[key]
        p = s.at(now.timestamp())
        prev = self.prev_close(key, now)
        if p is None or prev is None or not prev[0]:
            return None, "missing"
        if prev[1] is not None and crosses(self.dirty.get(key, []), prev[1], p.idx):
            return None, "roll"
        return {"key": key, "last": p.price, "pct": (p.price / prev[0] - 1.0) * 100.0,
                "chg": p.price - prev[0], "feed": "live" if s.live(now.timestamp()) else "closed",
                "_idx": p.idx, "_prev_idx": prev[1]}, None

    def snapshot(self, now: datetime) -> tuple[dict[str, Any], dict[str, Any]]:
        """The blocks drivers.build reads at `now`, and what each book's read leaned on."""
        day = now.astimezone(ET).date()
        quotes, why = [], {}
        for key in QUOTES:
            q, w = self.quote(key, now)
            if q is not None:
                quotes.append(q)
            else:
                why[key] = w
        context = [{"key": k, "hist": self.d[k].hist(day, CONTEXT_N)} for k in CONTEXT_KEYS]
        profiles: dict[str, Any] = {}
        ranges: dict[str, Any] = {}
        first: dict[str, int | None] = {}
        for book, (qk, *_) in BOOKS.items():
            s = self.h[qk]
            va, i_va = value_area(s, now, book)
            rows, i_box = boxes(s, now)
            profiles[book] = {"rows": [va] if va else []}
            ranges[book] = {"sessions": rows}
            first[book] = min((i for i in (i_va, i_box) if i is not None), default=None)
        sectors = []
        for k in SECTORS:
            p, prev = self.h[k].at(now.timestamp()), self.h[k].last_before(day)
            if p is not None and prev:
                sectors.append({"key": k, "day_pct": (p.price / prev - 1.0) * 100.0})
        snap = {"quotes": [{k: v for k, v in q.items() if not k.startswith("_")} for q in quotes],
                "context": context, "profiles": {"assets": profiles},
                "ranges": {"assets": ranges}, "sectors": sectors, "calendar": [],
                "constituents": None}
        return snap, {"quotes": {q["key"]: q for q in quotes}, "why": why, "first": first}


# ---- the marks ---------------------------------------------------------------------------


def scan_session(now: datetime, td: date) -> str:
    et = now.astimezone(ET)
    if et.date() != td:
        return "closed"
    if et.time() < time(9, 30):
        return "pre"
    return "rth" if et.time() < bias_record.close_time(td) else "closed"


def mark_instants(td: date) -> list[tuple[str, datetime]]:
    """The marks that belong to `td`'s session: 20:00 the evening before (Sunday to
    Thursday, Globex open), the rest on the day before its close. Pure."""
    out: list[tuple[str, datetime]] = []
    for hm in bias_record.MARKS:
        if hm >= (18, 0):
            day = td - timedelta(days=1)
            if day.weekday() not in (6, 0, 1, 2, 3):
                continue
        else:
            day = td
        at = datetime.combine(day, time(*hm), ET)
        if day == td and at.time() >= bias_record.close_time(td):
            continue
        if bias_record.session_for(at) != td:
            continue
        out.append((bias_record.mark_name(hm), at))
    return out


def sessions(data: Data) -> list[date]:
    """The sessions to read: SPY traded them, the futures' close is on file, and a 2024
    one (before the holiday table) is a full session after a full session. Pure."""
    spy = data.h["SPY"]
    by: dict[date, list[int]] = {}
    for t, d in zip(spy.ts, spy.dates, strict=True):
        by.setdefault(d, []).append(t)
    full = {d for d, ts in by.items()
            if any(datetime.fromtimestamp(t, ET).time() == time(15, 30) for t in ts)}
    last_fut = min(data.h[q].ts[-1] for q, *_ in BOOKS.values())
    out = []
    for d in sorted(by):
        if d < FIRST_TD:
            continue
        if datetime.combine(d, bias_record.close_time(d), ET).timestamp() > last_fut - HOUR:
            continue
        if covered(d):
            if is_trading_day(d):
                out.append(d)
            continue
        before = d - timedelta(days=3 if d.weekday() == 0 else 1)
        if d in full and before in full:
            out.append(d)
    return out


def run(data: Data, days: list[date], out_path: str | None,
        show: date | None = None) -> Counter[str]:
    tally: Counter[str] = Counter()
    lines: list[dict[str, Any]] = []
    for td in days:
        close_at = datetime.combine(td, bias_record.close_time(td), ET)
        closes = {book: data.h[q].at(close_at.timestamp()) for book, (q, *_) in BOOKS.items()}
        for mark, on in mark_instants(td):
            # Read at the hour the mark falls in, where the futures' price is (docstring).
            at = on.replace(minute=0)
            snap, seen = data.snapshot(at)
            board = drivers.build(snap, scan_session(at, td), at)
            st = ds.Stats(snap["context"], at.astimezone(ET).date())
            if show == td:
                _show(mark, at, snap, seen, board)
            for book, (qk, *_) in BOOKS.items():
                q = seen["quotes"].get(qk)
                end = closes[book]
                if q is None:
                    tally[f"skipped: {book} quote {seen['why'].get(qk)}"] += 1
                    continue
                first = min(i for i in (q["_prev_idx"], seen["first"][book], q["_idx"])
                            if i is not None)
                if end is None or crosses(data.dirty.get(qk, []), first, end.idx):
                    tally[f"skipped: {book} read straddles a roll"] += 1
                    continue
                r = board["books"][book]
                lines.append(bias_record.read_line(td.isoformat(), mark, at, book, r,
                                                   q["last"], q["pct"],
                                                   st.usual(ds.BOOK_KEY[book])[0]))
                tally["reads"] += 1
        lines.append(bias_record.close_line(td.isoformat(), close_at,
                                            {b: p.price if p else None
                                             for b, p in closes.items()}))
        tally["sessions"] += 1
    if out_path:
        if os.path.exists(out_path):
            os.remove(out_path)
        bias_record.append(lines, out_path)
    return tally


def _show(mark: str, at: datetime, snap: dict[str, Any], seen: dict[str, Any],
          board: dict[str, Any]) -> None:
    """One mark's snapshot and the NQ read, for the eye."""
    print(f"\n==== {mark}  {at:%a %Y-%m-%d %H:%M} ET  weights {board['weights']}  "
          f"session {board['session']}")
    for q in snap["quotes"]:
        print(f"   {q['key']:<8} last {q['last']:>11.4f}  pct {q['pct']:+7.3f}  chg {q['chg']:+9.4f}"
              f"  {q['feed']}")
    if seen["why"]:
        print("   off the board:", seen["why"])
    for book in BOOKS:
        va = snap["profiles"]["assets"][book]["rows"]
        rows = snap["ranges"]["assets"][book]["sessions"]
        pick = max(rows, key=lambda r: r["start_ts"]) if rows else None
        print(f"   {book:<4} value " + (f"VAL {va[0]['val']:.2f} POC {va[0]['poc']:.2f} "
                                       f"VAH {va[0]['vah']:.2f}" if va else "—")
              + "   box " + (f"{pick['label']} {pick['low']:.2f}-{pick['high']:.2f} from "
                             f"{datetime.fromtimestamp(pick['start_ts'], ET):%a %H:%M}"
                             if pick else "—"))
    if snap["sectors"]:
        print("   sectors", " ".join(f"{s['key']} {s['day_pct']:+.2f}" for s in snap["sectors"]))
    r = board["books"]["NQ"]
    print(f"   NQ: score {r['score']:+d} {r['grade']} bias {r['bias']} coverage {r['coverage']} "
          f"conflict {r['conflict']}")
    for f in r["families"]:
        print(f"      family {f['key']:<13} weight {f['weight']:>3} score {f['score']} "
              f"points {f['points']}")
    for v in r["votes"]:
        if v.get("family"):
            print(f"      {v['key']:<10} {v['vote']:<7} {v.get('strength', '')!s:<5} "
                  f"live={v.get('live', True)!s:<5} {v['value']} | {v['note'][:110]}")


def main() -> None:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")  # type: ignore[union-attr]
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--check", default=None, help="print one session's marks; write nothing")
    ap.add_argument("--out", default=OUT_FILE)
    ap.add_argument("--refresh", action="store_true", help="fetch from Yahoo again")
    a = ap.parse_args()
    t0 = clock.time()
    data = Data(a.refresh)
    if a.check:
        td = date.fromisoformat(a.check)
        print(run(data, [td], None, show=td))
        return
    days = sessions(data)
    for b in BOOKS:
        print(f"{b}: {len(data.rolls[b])} rolls, {len(data.seams.get(BOOKS[b][0], []))} seams")
    tally = run(data, days, a.out)
    print(f"{tally['sessions']} sessions, {days[0]} to {days[-1]}; {tally['reads']} reads "
          f"written to {a.out} in {clock.time() - t0:.0f}s")
    for k, v in sorted(tally.items()):
        if k.startswith("skipped"):
            print(f"  {k}: {v}")


if __name__ == "__main__":
    main()
