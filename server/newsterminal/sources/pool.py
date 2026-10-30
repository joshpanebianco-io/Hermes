"""
The pool — hundreds of large caps screened cheaply, so the scanner's forty
names are chosen from what is moving today rather than typed in on a quiet one.

WHY A POOL IN FRONT OF THE LIST, NOT A LONGER LIST. The scanner's arithmetic
(scan.py) needs each name's five-minute extended-hours bars, and the only free
feed for those is one Yahoo chart request per name every ~90 s
(sources/scanner.py). That scales by the name: forty names is ~20 requests a
minute, three hundred would be ~200, against an unpublished limit whose answer
— one HTTP 429 — pauses the whole scanner. So the wide read has to be a
different, batched read that answers one question only, IS THIS NAME IN PLAY
TODAY, and the names that are get promoted into the forty the Pine port runs
on. A promoted name's first chart request returns five days of bars, so its
levels, wave and score are complete within one fetch: no warm-up.

WHERE THE POOL COMES FROM, PROBED 2026-10-24 (a Saturday, so Friday's figures).
TradingView's screener endpoint — the JSON behind its public stock screener,
no login, one POST with the filter and the columns wanted, ~0.5 s:

    POST https://scanner.tradingview.com/america/scan
    {"filter": [market cap ≥ $5bn, type in (stock, dr), exchange in
                (NASDAQ, NYSE, AMEX)], "columns": [...], "range": [0, 2500]}

  - 1,586 names answered (415 KB): 1,441 stocks and 145 depositary receipts
    (TSM, ASML, NVO, BABA). 215 of the stocks are preferred lines (GOOGN, a
    1/20th preferred carrying Alphabet's whole market cap) — dropped by
    `typespecs`, which reads ["common"] for a common line and [""] for a DR.
    `is_primary` is NOT the filter: BRK.B reads false (BRK.A is primary).
  - Per name: the regular close and % change, the day's volume, the 30-day
    average volume, the 14-day ATR, market cap, TradingView's sector, the
    PRE-MARKET change, volume and last trade, and the last and next report
    dates — the next as an epoch at 12:00 UTC of the date, the last as the
    report's own instant (SPCX 1792526700 = 20 Oct 16:05 ET: after the close),
    which is how the rank tells a report that gaps TODAY from one that gaps
    tomorrow. `update_mode` was "delayed_streaming_900" on every row: fifteen
    minutes behind, like every other free quote this terminal reads.
  - The pre-market columns are the thing no Yahoo read can give for hundreds
    of names (Yahoo's pre-market bars carry no volume; its batched spark
    endpoint carries extended-hours closes but no volume either), and they
    are why this is one request a pass instead of the ~1,500 Yahoo chart
    reads a night the same screen would otherwise cost.
  - ASSUMED UNTIL A WEEKDAY PRE-MARKET CONFIRMS IT: before 09:30 `close` is the
    previous regular close and `premarket_close` the last pre-market trade, so
    the gap is their difference. Saturday's reply cannot show that (both are
    Friday's); tools/pool_probe.py prints both so Monday can.

THE GATES — WHAT MAY BE PROMOTED AT ALL. The owner's own screen of 14 Oct 2026
for the fixed list was $2bn+ traded a day and a 14-day ATR of 2.5%+, which is
the bar for a name worth watching EVERY day. A pool is looser on purpose: the
rank below rewards today's move, and a name that gaps three ATRs on a report
is in play whatever its usual ATR. So: $500m+ traded on an average day (the
options on a large cap at that turnover are liquid enough for a weekly),
an ATR of 1.5%+ (room for the retest to pay the premium), $10+ a share.
Of Friday's 1,371 common lines and DRs that is 244 names; $1bn and 2.5% would
have been 84, $250m and 1% 497.

THE RANK — THE SCANNER'S OWN IN-PLAY ARITHMETIC (scanscore.in_play), applied
to the pool: the gap in the name's own daily ATRs (8 points, from 0.10 ATR to
0.75) and the pre-market volume as a share of an average day (8 points,
log-scaled from 0.25% to 4%), plus 2 for a report in play — this morning's,
last night's, or one due today. After the open the same two parts read the day's move and the
day's volume instead, with the volume scale moved to 5%–40% of an average
day (fifteen minutes into the session a name in play has traded a twentieth
of its day; one in the news nearly half). Nothing under 4 points is promoted:
a 0.4-ATR gap alone is 3.7, 1% of ADV before the bell alone is 5.5, so on a
dead morning the list is just the pinned names, which is the right answer.

THE MARKS — WHEN THE LIST IS DECIDED. The pool is read every five minutes from
04:00 to 10:30 ET on a trading day (half-hourly otherwise, so the panel is
never blank), and promotions happen at four marks:
  08:00, 09:00, 09:25  — the pre-market list, replaced whole each time: nothing
                         has a signal yet, and a name that gapped at 07:00 and
                         faded by 09:00 should not hold a slot.
  10:00                — the post-open look, with the opening drive in the
                         figures (the feed is fifteen minutes behind, so the
                         09:25 mark saw 09:10). It only FILLS: the pre-market
                         marks leave POST_OPEN_SLOTS free for it and nothing
                         promoted is dropped once the session is on.
From 10:00 the list is sticky until the scanner's day rolls (20:00 ET; 17:00 on
a half day), when the promotions go with it. A collector started at noon runs
the latest pre-market mark it missed and then the post-open one, so it still
gets a list. A stale copy of the pool (a failed read served from disk) ranks
the panel but never promotes: FRESH_MIN caps the age a promotion may read.

THE SLOTS. Pinned names are the owner's and always scanned; the pool fills
whatever is left of MAX_SYMBOLS. Thirty-one pinned leaves nine; a pinned list
trimmed to the core leaves twenty. The panel prints the number.

THIS IS A PERSONAL READ OF A PUBLIC PAGE'S DATA, like every Yahoo and Nasdaq
read here: one request a pass, a browser User-Agent, a 403 or 429 answered
with a ten-minute pause, and GEXYGEN plays no part in it.
"""

from __future__ import annotations

import json
import math
import os
import threading
from collections.abc import Iterable
from datetime import UTC, date, datetime
from typing import Any

from .. import scan
from ..config import BROWSER_UA, CACHE_DIR
from ..holidays import prev_trading_day
from ..http import SourceStatus, fetch, json_body
from ..scanscore import GAP_FULL, GAP_MIN, PMVOL_FULL, PMVOL_MIN, W_GAP, W_PMVOL
from .scanner import _SYM, BENCHMARKS, MAX_SYMBOLS

URL = "https://scanner.tradingview.com/america/scan"
CACHE_KEY = "tv_pool"
STATE_FILE = os.path.join(CACHE_DIR, "scanner_pool.json")
HEADERS = {
    "Content-Type": "application/json",
    "Accept": "application/json",
    "Origin": "https://www.tradingview.com",
    "Referer": "https://www.tradingview.com/",
}
#: The columns asked for, in the order the reply's `d` arrays carry them.
COLUMNS = [
    "name", "description", "type", "typespecs", "close", "change", "volume",
    "average_volume_30d_calc", "ATR", "market_cap_basic", "sector",
    "premarket_change", "premarket_volume", "premarket_close",
    "earnings_release_next_date", "earnings_release_date", "update_mode",
]
MIN_CAP = 5_000_000_000.0
RANGE = 2500

# ---- the gates (module docstring) -------------------------------------------
MIN_DOLLAR_VOL = 500_000_000.0
MIN_ATR_PCT = 1.5
MIN_PRICE = 10.0

# ---- the rank ---------------------------------------------------------------
#: After the open the volume part reads the day's volume against an average
#: day; a twentieth of it earns the first point and nearly half the whole part.
RVOL_MIN = 5.0
RVOL_FULL = 40.0
W_REPORT = 2
MIN_SCORE = 4.0

# ---- the marks and the clock ------------------------------------------------
PRE_MARKS: tuple[tuple[int, str], ...] = (
    (8 * 60, "08:00"), (9 * 60, "09:00"), (9 * 60 + 25, "09:25"))
POST_MARK: tuple[int, str] = (10 * 60, "10:00")
POST_OPEN_SLOTS = 4
TICK_SEC = 20.0
ACTIVE_SEC = 300.0
IDLE_SEC = 1800.0
ACTIVE_UNTIL = 10 * 60 + 30
#: A promotion may read a copy this many minutes old at most (a live read is 0).
FRESH_MIN = 10.0
STALE_MAX_SEC = 2 * 3600.0
PAUSE_SEC = 600.0
TIMEOUT = 25
#: How many ranked names the panel is shown.
TOP_N = 15

# TradingView's sector → the S&P SPDR, where the mapping is unambiguous. Its
# "Finance" holds the REITs (XLRE) beside the banks and "Retail Trade" puts
# Walmart (XLP) beside Amazon (XLY), so those earn no sector rather than a
# wrong one — the same rule as sources/scanner.SECTOR.
TV_SECTOR: dict[str, str] = {
    "Electronic Technology": "XLK", "Technology Services": "XLK",
    "Health Technology": "XLV", "Health Services": "XLV",
    "Energy Minerals": "XLE", "Utilities": "XLU",
    "Consumer Non-Durables": "XLP", "Consumer Durables": "XLY",
    "Non-Energy Minerals": "XLB", "Process Industries": "XLB",
    "Producer Manufacturing": "XLI", "Transportation": "XLI",
    "Communications": "XLC",
}


def query() -> dict[str, Any]:
    """The screener request. Pure."""
    return {
        "filter": [
            {"left": "market_cap_basic", "operation": "egreater", "right": MIN_CAP},
            {"left": "type", "operation": "in_range", "right": ["stock", "dr"]},
            {"left": "exchange", "operation": "in_range", "right": ["NASDAQ", "NYSE", "AMEX"]},
        ],
        "columns": list(COLUMNS),
        "sort": {"sortBy": "market_cap_basic", "sortOrder": "desc"},
        "range": [0, RANGE],
    }


def pool_body(body: bytes) -> str | None:
    """The screener's JSON, or why not."""
    bad = json_body(body)
    if bad:
        return bad
    head = body[:200].decode("utf-8", errors="replace")
    return None if '"data"' in head or '"totalCount"' in head else "not a screener reply"


# ------------------------------------------------------------------- parsing


def _num(v: Any) -> float | None:
    return float(v) if isinstance(v, (int, float)) and math.isfinite(v) else None


def _when(v: Any) -> tuple[str | None, str | None]:
    """A TradingView report instant → (the ET date, "pre" | "after" | "during").

    The next report comes as noon UTC of its date (08:00 ET: "pre", which is
    only a placeholder); the last report as its own instant, so 16:05 ET reads
    "after" — a report that gaps the NEXT session, not this one.
    """
    n = _num(v)
    if n is None or n <= 0:
        return None, None
    et = datetime.fromtimestamp(n, scan.ET)
    m = et.hour * 60 + et.minute
    when = "pre" if m < scan.RTH_START else "after" if m >= 16 * 60 else "during"
    return et.date().isoformat(), when


def parse(doc: Any) -> tuple[list[dict[str, Any]], str | None]:
    """The screener reply → one row per common line or DR. Pure.

    Preferred lines go (module docstring); a row whose `d` is not the column
    count asked for is skipped rather than mis-zipped into the wrong fields.
    """
    if not isinstance(doc, dict) or not isinstance(doc.get("data"), list):
        return [], "no data array in the reply"
    rows: list[dict[str, Any]] = []
    for item in doc["data"]:
        d = item.get("d") if isinstance(item, dict) else None
        if not isinstance(d, list) or len(d) != len(COLUMNS):
            continue
        r = dict(zip(COLUMNS, d, strict=True))
        sym = str(r.get("name") or "").strip().upper()
        if not _SYM.match(sym):
            continue
        specs: list[Any] = r["typespecs"] if isinstance(r.get("typespecs"), list) else []
        kind = r.get("type")
        if kind not in ("stock", "dr") or (kind == "stock" and "common" not in specs):
            continue
        close = _num(r.get("close"))
        avg = _num(r.get("average_volume_30d_calc"))
        atr = _num(r.get("ATR"))
        earn_next, _ = _when(r.get("earnings_release_next_date"))
        earn_last, last_when = _when(r.get("earnings_release_date"))
        rows.append({
            "symbol": sym,
            "name": str(r.get("description") or "").strip() or None,
            "dr": kind == "dr",
            "close": close,
            "change": _num(r.get("change")),
            "volume": _num(r.get("volume")),
            "avg_vol": avg,
            "atr": atr,
            "cap": _num(r.get("market_cap_basic")),
            "tv_sector": str(r.get("sector") or "").strip() or None,
            "pm_change": _num(r.get("premarket_change")),
            "pm_volume": _num(r.get("premarket_volume")),
            "pm_close": _num(r.get("premarket_close")),
            "earn_next": earn_next,
            "earn_last": earn_last,
            "earn_last_when": last_when,
            "dollar_vol": (avg * close) if avg is not None and close is not None else None,
            "atr_pct": (atr / close * 100.0) if atr is not None and close else None,
            "delayed": str(r.get("update_mode") or "").startswith("delayed"),
        })
    return rows, None


def qualify(rows: Iterable[dict[str, Any]]) -> list[dict[str, Any]]:
    """The gates (module docstring). Pure."""
    out = []
    for r in rows:
        dv, ap, px = r.get("dollar_vol"), r.get("atr_pct"), r.get("close")
        if dv is None or ap is None or px is None:
            continue
        if dv >= MIN_DOLLAR_VOL and ap >= MIN_ATR_PCT and px >= MIN_PRICE:
            out.append(r)
    return out


# ---------------------------------------------------------------------- rank


def basis_for(clock: scan.Clock) -> str:
    """Which figures the rank reads: "pre" before the bell, "day" after it,
    "last" when no session is on (the figures are the last session's)."""
    if clock.session == "pre":
        return "pre"
    return "day" if clock.session in ("rth", "post") else "last"


def _clamp(x: float) -> float:
    return max(0.0, min(1.0, x))


def in_play(row: dict[str, Any], basis: str, trading_day: date) -> dict[str, Any]:
    """One pool name's in-play read: the score, its parts and the reason. Pure.

    Worked examples, Friday 23 Oct 2026's reply (tests/fixtures/tv_pool_trim.json):
      as "day"   KO    −2.76% on a 1.58 ATR: moved 2.63 = 1.67 ATR → 8.0 ;
                       18.9M of a 16.4M average day = 115% → 8.0      → 16.0
                 NVDA  −0.59% on a 6.06 ATR: 0.21 ATR → 8 × 0.11/0.65 = 1.3 ;
                       76% of ADV → 8.0                                → 9.3
      as "pre"   SNDK  pre-market 1271.01 on a 1238.03 close, ATR 96.14:
                       0.34 ATR → 3.0 ; 193k of 8.58M = 2.25% of ADV →
                       8 × ln(2.25/0.25)/ln(16) = 6.3                   → 9.3
                 ORCL  0.15 ATR → 0.6 ; 0.66% of ADV → 2.8             → 3.4,
                       under MIN_SCORE: not promoted.
    """
    atr, close, avg = row.get("atr"), row.get("close"), row.get("avg_vol")
    if basis == "pre":
        last, ref, vol = row.get("pm_close"), close, row.get("pm_volume")
        vmin, vfull, vword = PMVOL_MIN, PMVOL_FULL, "pre-market"
    else:
        chg = row.get("change")
        ref = (close / (1.0 + chg / 100.0)
               if close is not None and chg is not None and chg > -100 else None)
        last, vol = close, row.get("volume")
        vmin, vfull = RVOL_MIN, RVOL_FULL
        vword = "today" if basis == "day" else "last session"

    gap_atr = (abs(last - ref) / atr
               if last is not None and ref is not None and atr is not None and atr > 0 else None)
    gap_pts = (W_GAP * _clamp((gap_atr - GAP_MIN) / (GAP_FULL - GAP_MIN))
               if gap_atr is not None else 0.0)
    vol_pct = (vol / avg * 100.0) if vol is not None and avg is not None and avg > 0 else None
    vol_pts = 0.0
    if vol_pct is not None and vol_pct > vmin:
        vol_pts = W_PMVOL * min(1.0, math.log(vol_pct / vmin) / math.log(vfull / vmin))

    reports = report_read(row, trading_day)
    rep_pts = float(W_REPORT) if reports else 0.0

    bits = [
        (f"{'gap' if basis == 'pre' else 'moved'} {gap_atr:.2f} ATR"
         if gap_atr is not None else "no gap read"),
        (f"{vword} {vol_pct:.1f}% of ADV" if vol_pct is not None else f"no {vword} volume"),
    ]
    if reports:
        bits.append(reports)
    return {
        "score": round(gap_pts + vol_pts + rep_pts, 1),
        "reason": " · ".join(bits),
        "gap_atr": round(gap_atr, 2) if gap_atr is not None else None,
        "vol_pct": round(vol_pct, 2) if vol_pct is not None else None,
        "reports": reports,
    }


def report_read(row: dict[str, Any], trading_day: date) -> str | None:
    """The report in play for `trading_day`, in words, or None. Pure.

    This morning's report (before 09:30) and last night's (after 16:00) both
    gap today; a report after today's close gaps tomorrow and earns nothing
    now; one due today is named as due.
    """
    td = trading_day.isoformat()
    prev = prev_trading_day(trading_day).isoformat()
    last, when = row.get("earn_last"), row.get("earn_last_when")
    if last == td:
        return None if when == "after" else "reported this morning"
    if last == prev:
        return "reported last night" if when == "after" else "reported yesterday"
    if row.get("earn_next") == td:
        return "reports today"
    return None


def rank(rows: Iterable[dict[str, Any]], clock: scan.Clock) -> list[dict[str, Any]]:
    """Every qualified name scored and sorted, best first. Pure."""
    basis = basis_for(clock)
    out = []
    for r in rows:
        ip = in_play(r, basis, clock.trading_day)
        out.append({"symbol": r["symbol"], "name": r.get("name"),
                    "sector": TV_SECTOR.get(r.get("tv_sector") or ""),
                    "close": r.get("close"), "cap": r.get("cap"), **ip})
    out.sort(key=lambda x: (-x["score"], -(x["gap_atr"] or 0.0), x["symbol"]))
    return out


# --------------------------------------------------------------------- marks


def _minute(clock: scan.Clock) -> int:
    return clock.now.hour * 60 + clock.now.minute


def _in_day(clock: scan.Clock) -> bool:
    """Inside a trading day's own 04:00–20:00, when the figures are today's."""
    return clock.session != "closed" and clock.trading_day == clock.now.date()


def marks_due(now: datetime, done: Iterable[str]) -> list[str]:
    """Which marks to run at `now`, in order (module docstring). Pure.

    Only the LATEST pre-market mark not yet run: a collector started at 09:40
    runs 09:25, not 08:00 then 09:00 then 09:25. Worked examples, a Tuesday:
      07:59 → [] · 08:00 → ["08:00"] · 09:30 (nothing run) → ["09:25"] ·
      10:05 ("09:25" run) → ["10:00"] · 14:00 (nothing run) → ["09:25", "10:00"]
      · 20:00 → [] (the day has rolled) · Saturday 09:00 → [].
    """
    clock = scan.clock_at(now)
    if not _in_day(clock):
        return []
    m = _minute(clock)
    done_set = set(done)
    out: list[str] = []
    reached = [label for minute, label in PRE_MARKS if m >= minute]
    if reached and reached[-1] not in done_set:
        out.append(reached[-1])
    if m >= POST_MARK[0] and POST_MARK[1] not in done_set:
        out.append(POST_MARK[1])
    return out


def next_mark(now: datetime, done: Iterable[str]) -> str | None:
    """The next mark still to come today, for the panel. Pure."""
    clock = scan.clock_at(now)
    if not _in_day(clock):
        return None
    m = _minute(clock)
    done_set = set(done)
    for minute, label in (*PRE_MARKS, POST_MARK):
        if m < minute and label not in done_set:
            return label
    return None


def promote(ranked: list[dict[str, Any]], pinned: Iterable[str], current: list[dict[str, Any]],
            mark: str, cap: int = MAX_SYMBOLS) -> list[dict[str, Any]]:
    """The promoted set after `mark` (module docstring). Pure.

    Pre-market marks return the fresh top names, leaving POST_OPEN_SLOTS of
    the room free; the post-open mark keeps `current` and fills the rest.
    """
    pinned_l = list(pinned)
    excluded = set(pinned_l) | set(BENCHMARKS)
    slots = max(0, cap - len(pinned_l))
    cands = [r for r in ranked if r["score"] >= MIN_SCORE and r["symbol"] not in excluded]
    if mark != POST_MARK[1]:
        return cands[: max(0, slots - POST_OPEN_SLOTS)]
    keep = [c for c in current if c["symbol"] not in excluded][:slots]
    have = {c["symbol"] for c in keep}
    for r in cands:
        if len(keep) >= slots:
            break
        if r["symbol"] not in have:
            keep.append(r)
            have.add(r["symbol"])
    return keep


def cadence(now: datetime) -> float:
    clock = scan.clock_at(now)
    active = clock.session == "pre" or (clock.session == "rth" and _minute(clock) < ACTIVE_UNTIL)
    return ACTIVE_SEC if active else IDLE_SEC


# --------------------------------------------------------------------- store


class PoolStore:
    """The pool between ticks: the last read, its rank, and today's promotions.

    Written by the pre-market thread's job; `set_enabled` comes from the API
    thread, so the promotion fields sit behind a lock and `view` copies.
    """

    def __init__(self, path: str = STATE_FILE) -> None:
        self._lock = threading.Lock()
        self._path = path
        self.rows: list[dict[str, Any]] = []
        self.ranked: list[dict[str, Any]] = []
        self.screened = 0
        self.basis = "last"
        self.read_at: float | None = None
        self.source = "unavailable"
        self.error: str | None = None
        self.last_attempt = 0.0
        self.pause_until = 0.0
        self.force = False
        # ---- behind the lock
        self.enabled = True
        self.day: str | None = None
        self.promoted: list[dict[str, Any]] = []
        self.marks_done: list[str] = []
        self._load()

    # ---- persistence --------------------------------------------------------

    def _load(self) -> None:
        try:
            with open(self._path, encoding="utf-8") as f:
                d = json.load(f)
        except (OSError, ValueError):
            return
        if not isinstance(d, dict):
            return
        self.enabled = bool(d.get("enabled", True))
        self.day = d.get("day") if isinstance(d.get("day"), str) else None
        self.promoted = [p for p in (d.get("promoted") or [])
                         if isinstance(p, dict) and p.get("symbol")]
        self.marks_done = [str(m) for m in (d.get("marks_done") or [])]

    def _save(self) -> None:
        tmp = self._path + ".tmp"
        try:
            os.makedirs(os.path.dirname(self._path), exist_ok=True)
            with open(tmp, "w", encoding="utf-8") as f:
                json.dump({"enabled": self.enabled, "day": self.day, "promoted": self.promoted,
                           "marks_done": self.marks_done,
                           "saved_utc": datetime.now(UTC).isoformat()}, f)
            os.replace(tmp, self._path)
        except OSError:
            pass

    # ---- what the scanner takes ---------------------------------------------

    def for_scan(self) -> tuple[date | None, list[str], dict[str, str]]:
        """(the day the promotions are for, their symbols, their sectors)."""
        with self._lock:
            day = date.fromisoformat(self.day) if self.day else None
            syms = [p["symbol"] for p in self.promoted] if self.enabled else []
            sectors = {p["symbol"]: p["sector"] for p in self.promoted if p.get("sector")}
        return day, syms, sectors

    def set_enabled(self, on: bool) -> bool:
        """Switch promotion. Off clears today's list; on re-runs today's latest
        mark on the next read (the marks are forgotten with the list) and makes
        that read the next tick's. True when anything changed."""
        with self._lock:
            if on == self.enabled:
                return False
            self.enabled = on
            self.promoted = []
            self.marks_done = []
            self.force = on
            self._save()
        return True

    # ---- the tick -----------------------------------------------------------

    def _roll(self, trading_day: date) -> bool:
        """A new trading day: last day's promotions go. True when any did."""
        with self._lock:
            if self.day == trading_day.isoformat():
                return False
            had = bool(self.promoted)
            self.day = trading_day.isoformat()
            self.promoted = []
            self.marks_done = []
            self._save()
        return had

    def _promote(self, pinned: list[str], now: datetime) -> bool:
        changed = False
        et = now.astimezone(scan.ET).strftime("%H:%M")
        labels = [label for _, label in PRE_MARKS]
        with self._lock:
            if not self.enabled:
                return False
            for mark in marks_due(now, self.marks_done):
                new = promote(self.ranked, pinned, self.promoted, mark)
                was = {p["symbol"]: p for p in self.promoted}
                self.promoted = [was.get(r["symbol"], {**r, "at": et, "mark": mark}) for r in new]
                if mark in labels:
                    # The earlier pre-market marks are done with it: a 09:25
                    # pass is never followed by an 09:00 one.
                    self.marks_done = labels[: labels.index(mark) + 1]
                else:
                    self.marks_done = [*self.marks_done, mark]
                changed = changed or set(was) != {p["symbol"] for p in self.promoted}
                self._save()
        return changed

    def tick(self, pinned: list[str], now: datetime | None = None
             ) -> tuple[SourceStatus, bool, bool]:
        """One step: read the pool when due, rank it, run any mark that has come.
        Returns (status, whether a read happened, whether the promotions changed)."""
        now = now or datetime.now(UTC)
        t = now.timestamp()
        clock = scan.clock_at(now)
        changed = self._roll(clock.trading_day)
        st = SourceStatus("Pool")
        read = False
        paused = t < self.pause_until
        due = self.force or t - self.last_attempt >= cadence(now)
        if due and not paused:
            self.last_attempt, self.force = t, False
            read = True
            r = st.absorb(fetch(URL, key=CACHE_KEY, ttl_sec=0.0, timeout=TIMEOUT, ua=BROWSER_UA,
                                headers=HEADERS, stale_max_sec=STALE_MAX_SEC, validate=pool_body,
                                data=json.dumps(query()).encode()))
            if r.status in (403, 429):
                self.pause_until = t + PAUSE_SEC
            if r.ok:
                try:
                    rows, err = parse(r.json())
                except (ValueError, TypeError) as e:
                    rows, err = [], f"unparseable: {e}"
                if rows:
                    self.rows = qualify(rows)
                    self.screened = len(rows)
                    self.read_at = t - (r.age_min or 0.0) * 60.0
                    self.source = r.source
                    self.basis = basis_for(clock)
                    self.ranked = rank(self.rows, clock)
                    self.error = r.error if r.source == "stale" else None
                    fresh = r.source == "live" or (r.age_min or 0.0) <= FRESH_MIN
                    if fresh:
                        changed = self._promote(pinned, now) or changed
                else:
                    self.error = err or "no names in the reply"
            else:
                self.error = r.error
        st.items = len(self.rows)
        st.settle(bool(self.rows), what="read")
        if self.error and not st.error:
            st.error = self.error
        with self._lock:
            n_prom, on, marks = len(self.promoted), self.enabled, list(self.marks_done)
        st.notes = [f"{self.screened} screened · {len(self.rows)} qualified · "
                    + (f"{n_prom} promoted" if on else "promotion off")
                    + (f" · marks {', '.join(marks)}" if marks else "")]
        nxt = next_mark(now, marks)
        if nxt and on:
            st.notes.append(f"next mark {nxt} ET")
        if paused:
            until = datetime.fromtimestamp(self.pause_until, scan.ET).strftime("%H:%M:%S")
            st.notes.append(f"TradingView refused (403/429) — paused until {until} ET")
        return st, read, changed

    # ---- the panel ----------------------------------------------------------

    def view(self, pinned: Iterable[str], now: datetime | None = None) -> dict[str, Any]:
        now = now or datetime.now(UTC)
        pin = set(pinned)
        with self._lock:
            on = self.enabled
            promoted = [dict(p) for p in self.promoted]
            marks = list(self.marks_done)
        promoted = [p for p in promoted if p["symbol"] not in pin]
        shown = {p["symbol"] for p in promoted}
        top = [r for r in self.ranked
               if r["symbol"] not in pin and r["symbol"] not in BENCHMARKS][:TOP_N]
        return {
            "ok": bool(self.rows),
            "on": on,
            "read_utc": (datetime.fromtimestamp(self.read_at, UTC).isoformat()
                         if self.read_at else None),
            "age_min": (round((now.timestamp() - self.read_at) / 60.0, 1)
                        if self.read_at else None),
            "source": self.source,
            "error": self.error,
            "screened": self.screened,
            "qualified": len(self.rows),
            "basis": self.basis,
            "gates": {"cap_usd": MIN_CAP, "dollar_vol_usd": MIN_DOLLAR_VOL,
                      "atr_pct": MIN_ATR_PCT, "price_usd": MIN_PRICE, "min_score": MIN_SCORE},
            "top": [{**r, "promoted": r["symbol"] in shown} for r in top],
            "promoted": promoted,
            "day": self.day,
            "marks_done": marks,
            "next_mark": next_mark(now, marks),
            "slots": max(0, MAX_SYMBOLS - len(pin)),
            "post_open_slots": POST_OPEN_SLOTS,
        }
