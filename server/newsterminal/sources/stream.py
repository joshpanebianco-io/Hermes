"""
Yahoo's live quote stream — every trade, pushed, for the names being watched.

WHY A STREAM (owner, 2026-11-09: "how can we get the chart information closer to
real time"). The chart redrew every twenty to thirty seconds, off five-minute
bars that a forty-name rotation reaches every minute and a half to two minutes,
and outside the regular session it had nothing faster: up to two and a half
minutes behind in the pre-market, which is when PMH and PML are being made.

    wss://streamer.finance.yahoo.com/?version=2

is the feed behind Yahoo's own quote pages: no key, one connection, the symbols
named in a `{"subscribe": [...]}` message. PROBED 2026-11-09 22:34 ET, a Sunday
night: US stocks arrived a median two seconds after their trade time, in the
overnight session, and three hundred more names on the same connection cost
nothing and did not drop it. Thin overnight trading says nothing about 300 busy
names at 09:30, which is what `StreamCheck` below is for.

THE FRAME. JSON, `{"type": "pricing", "message": <base64>}`, the message a
protobuf. Five fields are read here and decoded by hand, because a dependency
for five fields is more to carry than twenty lines:

    1 id (string) · 2 price (float) · 3 time (zigzag varint, ms)
    7 market hours (varint) · 9 day volume (zigzag varint)

Field 7 read 4 for US stocks overnight, a value the published enum does not have.
THE SESSION IS READ OFF THE TICK'S OWN CLOCK instead (scan._session_of), so an
undocumented number cannot put a print in the wrong session.

WHAT IT CHANGES AND WHAT IT LEAVES ALONE.
  - The last candle on a chart and each name's last price: the stream's.
  - Volume stays with the bars. A trade here carries no size worth summing and
    Yahoo's day volume counts about 20% more than its bars do (scan.with_live).
  - Signals are still read on ten-minute bars confirmed by a download.
  - Overnight prints are held apart, for the quote alone. They never enter a
    candle or a level: PMH and PML begin at 04:00, as the Pine reads them.

NOTHING DEPENDS ON IT. Unofficial, and able to change without notice like every
other Yahoo read here, so the spark layer and the bar rotation run as they
always did. A dropped connection backs off and comes back; a chart with no
stream polls its bars as before; if the package is missing the source says so
on the rail and the terminal carries on.
"""

from __future__ import annotations

import asyncio
import base64
import contextlib
import json
import os
import statistics
import struct
import threading
import time
from collections import deque
from collections.abc import Iterable
from datetime import UTC, datetime
from typing import Any, NamedTuple

from .. import scan
from ..config import BROWSER_UA, CACHE_DIR
from ..holidays import is_trading_day
from ..http import SourceStatus

try:
    import websockets
except ImportError:  # pragma: no cover — requirements.txt has it
    websockets = None  # type: ignore[assignment]

URL = "wss://streamer.finance.yahoo.com/?version=2"
ORIGIN = "https://finance.yahoo.com"
#: Every name on one connection. The screener's candidates, the list and an open
#: chart come to well under this; it is here so a bug cannot subscribe the market.
MAX_NAMES = 500
#: How long a chart's interest in an off-list name lasts without another poll.
TOUCH_SEC = 20.0
#: Steps back after a dropped connection, seconds.
BACKOFF = (2.0, 5.0, 15.0, 30.0, 60.0)
#: Silent this long with a US session on: the socket is dead, whatever it says.
QUIET_SEC = 90.0
#: Connected this long is a healthy connection, and the back-off starts over.
HEALTHY_SEC = 120.0
#: One-minute candles held per name: a whole extended session.
MINUTES_KEPT = 16 * 60
CHECK_FILE = os.path.join(CACHE_DIR, "stream_check.json")
#: THE STREAM CAN RUN BEHIND THE MARKET WHILE IT LOOKS ALIVE. Measured in the session
#: of Thu 12 Nov 2026 (a heavy day): frames kept arriving, thirteen a second for six
#: names on a fresh connection of its own, and every trade in them was 90 to 440
#: seconds old on arrival (AAPL 91s, SPY 148s, NVDA 377s, 1% away from its real
#: price). The day before, the median was under a second. So a trade's age on arrival
#: is watched: over the last LAG_WINDOW_SEC, with at least LAG_MIN_TICKS heard, a
#: median past LATE_SEC is a late stream, and the rail says so instead of "ok".
LATE_SEC = 20.0
LAG_WINDOW_SEC = 60.0
LAG_MIN_TICKS = 40


class Tick(NamedTuple):
    price: float
    at: float  # epoch seconds of the trade
    session: str | None  # "pre" | "rth" | "post", None overnight
    day_volume: int | None
    recv: float  # epoch seconds this process received it


def _varint(b: bytes, i: int) -> tuple[int, int]:
    shift = v = 0
    while True:
        c = b[i]
        i += 1
        v |= (c & 0x7F) << shift
        if not c & 0x80:
            return v, i
        shift += 7
        if shift > 70:
            raise ValueError("varint too long")


def _zigzag(n: int) -> int:
    return (n >> 1) ^ -(n & 1)


#: The fields sent as protobuf `sint64`, which is zigzag; the rest are plain.
_ZIGZAG = frozenset({3, 9, 14, 19, 22, 24, 26, 27, 28, 29})


def decode(b: bytes) -> dict[int, Any]:
    """A protobuf message → {field number: value}. Pure. Raises on bad bytes."""
    out: dict[int, Any] = {}
    i = 0
    while i < len(b):
        key, i = _varint(b, i)
        field, wire = key >> 3, key & 7
        if wire == 0:
            v, i = _varint(b, i)
            out[field] = _zigzag(v) if field in _ZIGZAG else v
        elif wire == 5:
            out[field] = struct.unpack("<f", b[i : i + 4])[0]
            i += 4
        elif wire == 1:
            out[field] = struct.unpack("<d", b[i : i + 8])[0]
            i += 8
        elif wire == 2:
            n, i = _varint(b, i)
            out[field] = b[i : i + n]
            i += n
        else:
            raise ValueError(f"wire type {wire}")
    return out


def session_of_ts(at: float) -> str | None:
    """pre / rth / post for a trade's own time, None overnight or on a closed day. Pure."""
    dt = datetime.fromtimestamp(at, scan.ET)
    if not is_trading_day(dt.date()):
        return None
    return scan._session_of(dt.date(), dt.hour * 60 + dt.minute)


def parse_frame(raw: str | bytes, now: float | None = None) -> tuple[str, Tick] | None:
    """One frame off the socket → (Yahoo's symbol, its tick), or None. Pure but for `now`.

    Never raises: a frame this cannot read is a frame skipped, and Yahoo also
    sends non-pricing frames. A price of zero or a time more than a day out is
    not a trade.
    """
    try:
        text = raw.decode() if isinstance(raw, bytes | bytearray) else raw
        message: Any = text
        if text.startswith("{"):
            doc = json.loads(text)
            message = doc.get("message")
        if not isinstance(message, str):
            return None
        p = decode(base64.b64decode(message))
        sym = p[1].decode()
        price = float(p[2])
        at = int(p[3]) / 1000.0
    except (KeyError, ValueError, IndexError, TypeError, AttributeError, struct.error):
        return None
    t = now if now is not None else time.time()
    if not price > 0 or abs(t - at) > 86400:
        return None
    vol = p.get(9)
    return sym, Tick(price, at, session_of_ts(at), int(vol) if isinstance(vol, int) else None, t)


def _app_sym(yahoo: str) -> str:
    """BRK-B is BRK.B to the scanner (scanner._yahoo's other direction)."""
    return yahoo.replace("-", ".")


def _yahoo_sym(sym: str) -> str:
    return sym.replace(".", "-")


class Candles:
    """One name's one-minute candles, built tick by tick. Not thread-safe by itself."""

    __slots__ = ("rows",)

    def __init__(self) -> None:
        self.rows: deque[list[float]] = deque(maxlen=MINUTES_KEPT)

    def add(self, price: float, at: float) -> None:
        k = int(at) - int(at) % 60
        if self.rows and int(self.rows[-1][0]) == k:
            c = self.rows[-1]
            c[2] = max(c[2], price)
            c[3] = min(c[3], price)
            c[4] = price
        elif not self.rows or k > int(self.rows[-1][0]):
            self.rows.append([float(k), price, price, price, price])
        # A trade older than the newest minute arrives late; it is in the bars.

    def last(self) -> dict[str, float] | None:
        if not self.rows:
            return None
        c = self.rows[-1]
        return {"t": int(c[0]), "o": c[1], "h": c[2], "l": c[3], "c": c[4]}

    def between(self, t0: int, t1: int) -> list[list[float]]:
        return [c for c in self.rows if t0 <= c[0] < t1]


class StreamCheck:
    """THE LIVE-SESSION CHECK, RUNNING ITSELF.

    Tonight's probe could only see thin overnight trading. What has to be known
    is whether the stream keeps up with a busy session and whether its candles
    agree with Yahoo's own, so the collector keeps the score as it runs: every
    finished five-minute bucket a tracked name has in a download made after it
    closed is compared with the same five minutes built from the stream, and the
    tally is kept per day and session in cache/stream_check.json.
    `python -I tools/stream_check.py` prints it.

    Agreement is within five basis points of price, on the close, the high and
    the low. A bucket the stream has no trades for counts as missing. It costs no
    request: both sides are already in memory.
    """

    TOL_BP = 5.0

    def __init__(self, path: str = CHECK_FILE) -> None:
        self.path = path
        self.days: dict[str, dict[str, dict[str, Any]]] = {}
        self.done: dict[str, int] = {}
        try:
            with open(path, encoding="utf-8") as f:
                d = json.load(f)
            if isinstance(d, dict) and isinstance(d.get("days"), dict):
                self.days = d["days"]
        except (OSError, ValueError):
            pass

    def _slot(self, day: str, session: str) -> dict[str, Any]:
        slot = self.days.setdefault(day, {}).setdefault(session, {
            "compared": 0, "close_ok": 0, "high_ok": 0, "low_ok": 0, "missing": 0,
            "age_p50": None, "age_p95": None, "peak_ticks_min": 0, "peak_names_min": 0,
            "subscribed": 0,
        })
        return slot

    def compare(self, sym: str, candles: Candles, bars: list[scan.Bar], fetched: float) -> int:
        """Score the buckets not yet scored. Returns how many were. Mutates the tally."""
        scored = 0
        last = self.done.get(sym, 0)
        for b in bars[-40:]:
            if b.t <= last or b.t + scan.SRC_SEC + 30 > fetched:
                continue
            session = session_of_ts(b.t)
            if session is None:
                continue
            day = datetime.fromtimestamp(b.t, scan.ET).date().isoformat()
            slot = self._slot(day, session)
            mine = candles.between(b.t, b.t + scan.SRC_SEC)
            last = b.t
            scored += 1
            if not mine:
                slot["missing"] += 1
                continue
            hi, lo, cl = max(c[2] for c in mine), min(c[3] for c in mine), mine[-1][4]
            near = lambda x, y: abs(x - y) / y * 1e4 <= self.TOL_BP if y else False  # noqa: E731
            slot["compared"] += 1
            slot["close_ok"] += int(near(cl, b.close))
            slot["high_ok"] += int(near(hi, b.high))
            slot["low_ok"] += int(near(lo, b.low))
        self.done[sym] = last
        return scored

    def throughput(self, ages: list[float], ticks: int, names: int, subscribed: int,
                   now: float) -> None:
        """One minute's freshness and volume, into the slot it belongs to."""
        session = session_of_ts(now)
        if session is None:
            return
        day = datetime.fromtimestamp(now, scan.ET).date().isoformat()
        slot = self._slot(day, session)
        slot["peak_ticks_min"] = max(slot["peak_ticks_min"], ticks)
        slot["peak_names_min"] = max(slot["peak_names_min"], names)
        slot["subscribed"] = max(slot["subscribed"], subscribed)
        if ages:
            ages = sorted(ages)
            slot["age_p50"] = round(statistics.median(ages), 2)
            slot["age_p95"] = round(ages[min(len(ages) - 1, int(len(ages) * 0.95))], 2)

    def save(self) -> None:
        keep = dict(sorted(self.days.items())[-20:])
        tmp = self.path + ".tmp"
        try:
            os.makedirs(os.path.dirname(self.path), exist_ok=True)
            with open(tmp, "w", encoding="utf-8") as f:
                json.dump({"saved_utc": datetime.now(UTC).isoformat(), "days": keep}, f)
            os.replace(tmp, self.path)
        except OSError:
            pass


def lag_of(recent: Iterable[tuple[float, float]], now: float) -> float | None:
    """How late the stream is running: the median age on arrival of the trades heard
    in the last LAG_WINDOW_SEC, or None when too few were heard to say. `recent` is
    (received, age) pairs. Pure."""
    ages = [age for recv, age in recent if now - recv <= LAG_WINDOW_SEC]
    return statistics.median(ages) if len(ages) >= LAG_MIN_TICKS else None


def chart_tick(q: dict[str, Any] | None,
               spark: tuple[float, float] | None) -> dict[str, Any] | None:
    """What an open chart is told the last trade is: the NEWER of the stream's quote
    and the spark layer's trade (`spark` is (price, epoch), given in the regular
    session only, the one that layer reads). Pure.

    The stream's used to win whenever it had one. On 2026-11-12 it ran minutes
    behind, and a chart laid a 90-second-old price on its last candle while the
    five-second quote beside it was current; the Setups rows were right all along
    because the scanner already took the newer of the two (ScanStore._latest_trade).
    The stream's minute candle goes when the spark's trade is used: it is the range
    of a minute the stream has not caught up with.
    """
    has = q is not None and "price" in q
    if spark is not None and (not has or float(spark[1]) > float((q or {}).get("at") or 0.0)):
        return {**(q or {}), "price": float(spark[0]), "at": float(spark[1]),
                "session": "rth", "minute": None, "via": "spark"}
    return q


class PriceStream:
    """The connection, what it is subscribed to, and what it has heard.

    `set_targets` and `touch` come from other threads; everything read back goes
    through the one lock, so a reader never sees a candle half made.
    """

    def __init__(self, url: str = URL) -> None:
        self.url = url
        self._lock = threading.Lock()
        self._stop = threading.Event()
        self._thread: threading.Thread | None = None
        self._targets: dict[str, list[str]] = {}
        self._touched: dict[str, float] = {}
        self._last: dict[str, Tick] = {}
        self._overnight: dict[str, Tick] = {}
        self._minutes: dict[str, Candles] = {}
        self.connected = False
        self.connected_at = 0.0
        self.last_frame = 0.0
        self.subscribed = 0
        self.error: str | None = None
        # This minute's traffic, for the check.
        self._ticks_min = 0
        self._names_min: set[str] = set()
        self._ages_min: list[float] = []
        # The last few thousand trades' (received, age on arrival), for `lag_of`.
        self._recent: deque[tuple[float, float]] = deque(maxlen=6000)
        self.check = StreamCheck()

    # ---- what to listen to -----------------------------------------------

    def set_targets(self, name: str, symbols: Iterable[str]) -> None:
        """Replace one named list of names (the tracked list, the candidates)."""
        syms = [s for s in symbols if s]
        with self._lock:
            self._targets[name] = syms

    def touch(self, sym: str) -> None:
        """A chart is open on this name: keep it subscribed a little longer."""
        with self._lock:
            self._touched[sym] = time.monotonic() + TOUCH_SEC

    def wanted(self) -> list[str]:
        """Every name to subscribe to, touched and tracked first, inside MAX_NAMES."""
        now = time.monotonic()
        with self._lock:
            self._touched = {s: t for s, t in self._touched.items() if t > now}
            seen: dict[str, None] = dict.fromkeys(self._touched)
            for key in ("tracked", *sorted(k for k in self._targets if k != "tracked")):
                seen.update(dict.fromkeys(self._targets.get(key) or []))
        return list(seen)[:MAX_NAMES]

    # ---- what it has heard ----------------------------------------------

    def take(self, raw: str | bytes) -> str | None:
        """One frame into the store. Returns the symbol, or None if it was not a trade."""
        got = parse_frame(raw)
        if got is None:
            return None
        sym, tick = _app_sym(got[0]), got[1]
        with self._lock:
            self.last_frame = tick.recv
            self._ticks_min += 1
            self._names_min.add(sym)
            age = max(0.0, tick.recv - tick.at)
            self._ages_min.append(age)
            self._recent.append((tick.recv, age))
            if tick.session is None:
                self._overnight[sym] = tick
                return sym
            prev = self._last.get(sym)
            if prev is None or tick.at >= prev.at:
                self._last[sym] = tick
            self._minutes.setdefault(sym, Candles()).add(tick.price, tick.at)
        return sym

    def last_trade(self, sym: str) -> tuple[float, float] | None:
        """(price, epoch) of the name's latest session trade."""
        with self._lock:
            t = self._last.get(sym)
        return (t.price, t.at) if t else None

    def quote(self, sym: str) -> dict[str, Any] | None:
        """What a chart needs each second: the price, its time, and this minute's candle."""
        with self._lock:
            t = self._last.get(sym)
            n = self._overnight.get(sym)
            c = self._minutes.get(sym)
            minute = c.last() if c else None
        if t is None and n is None:
            return None
        out: dict[str, Any] = {}
        if t is not None:
            out.update(price=t.price, at=t.at, session=t.session, minute=minute)
        if n is not None and (t is None or n.at > t.at):
            out["overnight"] = {"price": n.price, "at": n.at}
        return out

    # ---- the check and the rail ------------------------------------------

    def run_check(self, bars: dict[str, list[scan.Bar]], fetched: dict[str, float]) -> None:
        with self._lock:
            ticks, names, ages = self._ticks_min, len(self._names_min), self._ages_min
            self._ticks_min, self._names_min, self._ages_min = 0, set(), []
            subscribed = self.subscribed
            candles = {s: self._minutes.get(s) for s in bars}
            work = {s: c for s, c in candles.items() if c is not None and len(c.rows) > 0}
            # Copied under the lock: the socket thread keeps appending.
            copies: dict[str, Candles] = {}
            for s, c in work.items():
                dup = Candles()
                dup.rows.extend(list(r) for r in c.rows)
                copies[s] = dup
        now = time.time()
        self.check.throughput(ages, ticks, names, subscribed, now)
        for s, c in copies.items():
            if s in fetched:
                self.check.compare(s, c, bars[s], fetched[s])
        self.check.save()

    def status(self) -> SourceStatus:
        st = SourceStatus("Stream")
        if websockets is None:
            st.error = "the websockets package is not installed"
            st.source = "unavailable"
            return st
        now = time.time()
        with self._lock:
            connected, last, subscribed, err = (self.connected, self.last_frame, self.subscribed,
                                                self.error)
            lag = lag_of(list(self._recent), now)
        st.ok = connected
        st.items = subscribed
        st.source = "live" if connected else "unavailable"
        st.age_min = round((now - last) / 60.0, 2) if last else None
        st.notes = [f"{subscribed} names subscribed"]
        if connected and lag is not None and lag > LATE_SEC:
            # Connected and talking, but behind the market: "stale" on the rail, with
            # how far behind, where it used to read "ok" (the note over LATE_SEC).
            st.source = "stale"
            st.age_min = round(lag / 60.0, 2)
            st.notes.insert(0, f"trades arriving about {lag:.0f}s late: charts and rows "
                               "take the five-second quote where it is newer")
        if not connected and err:
            st.error = err
        if connected:
            st.last_ok_utc = datetime.now(UTC).isoformat()
        return st

    # ---- the connection ---------------------------------------------------

    def start(self) -> None:
        if websockets is None or (self._thread and self._thread.is_alive()):
            return
        self._stop.clear()
        self._thread = threading.Thread(target=self._run, name="stream", daemon=True)
        self._thread.start()

    def stop(self) -> None:
        self._stop.set()
        if self._thread:
            self._thread.join(timeout=3)

    def _run(self) -> None:
        fails = 0
        while not self._stop.is_set():
            started = time.monotonic()
            try:
                asyncio.run(self._session())
            except Exception as e:  # noqa: BLE001 — a stream that fails must not take the thread
                with self._lock:
                    self.error = f"{e.__class__.__name__}: {e}"
            with self._lock:
                self.connected = False
                self.subscribed = 0
            if self._stop.is_set():
                return
            fails = 0 if time.monotonic() - started >= HEALTHY_SEC else fails + 1
            self._stop.wait(BACKOFF[min(fails, len(BACKOFF) - 1)])

    async def _sync(self, ws: Any, have: set[str]) -> set[str]:
        """Bring the subscription into line with what is wanted."""
        want = {_yahoo_sym(s) for s in self.wanted()}
        add, drop = sorted(want - have), sorted(have - want)
        if drop:
            await ws.send(json.dumps({"unsubscribe": drop}))
        if add:
            await ws.send(json.dumps({"subscribe": add}))
        if add or drop:
            with self._lock:
                self.subscribed = len(want)
        return want

    async def _session(self) -> None:
        async with websockets.connect(
            self.url, additional_headers={"Origin": ORIGIN}, user_agent_header=BROWSER_UA,
            open_timeout=15, ping_interval=20, ping_timeout=20, max_size=2**20,
        ) as ws:
            now = time.time()
            with self._lock:
                self.connected, self.connected_at, self.error = True, now, None
                self.last_frame = self.last_frame or now
            have: set[str] = set()
            synced = 0.0
            while not self._stop.is_set():
                t = time.monotonic()
                if t - synced >= 1.0:
                    have = await self._sync(ws, have)
                    synced = t
                with contextlib.suppress(TimeoutError):
                    self.take(await asyncio.wait_for(ws.recv(), timeout=1.0))
                    continue
                # Nothing for a second: fine, unless a US session is on and it
                # has been a long time.
                if session_of_ts(time.time()) is not None and have:
                    with self._lock:
                        heard = max(self.last_frame, self.connected_at)
                    if time.time() - heard > QUIET_SEC:
                        raise TimeoutError(f"no frame for {QUIET_SEC:.0f}s with a session on")
