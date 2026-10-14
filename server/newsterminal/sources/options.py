"""
The stocks desk's option chains — Cboe's free delayed quotes, one name at a time.

WHY CBOE, AND WHY DIRECTLY. Cboe publishes every listed name's whole chain —
bid, ask, IV, the greeks, open interest — as a public JSON document, delayed
fifteen minutes and free to read for personal use. HERMESX reads it itself:
GEXYGEN reads the same feed, but this terminal never depends on that project
for anything but its optional gamma levels (owner's standing rule).

THE BUDGET, MEASURED (2026-10-13). Cboe serves the documents gzipped: SPY's
13,474 contracts are 0.77 MB on the wire (6.0 MB once inflated), QQQ 0.74 MB,
IWM 0.32 MB, a single name 0.18-0.30 MB. During the stocks session window
(08:00-16:15 ET on a trading day) the three daily-expiry ETFs refresh every
five minutes and single names every ten; outside it, hourly. With the default
21-name list that is ~144 requests and ~45 MB an hour in session, ~21 requests
an hour otherwise — one request at most every ten seconds, never a burst.
The data is fifteen minutes delayed at source, so faster would buy nothing.

NOTHING RAW IS KEPT. A chain is parsed straight down to what the desk reads
(optcalc.Chain: spot, IV30, and the nearest expiries' contracts within ±15% of
spot) and only that summary is written to disk — so a restart paints from it
at once, and six megabytes of SPY is never rewritten every five minutes.

THE IV LOG. Cboe gives today's IV30 and no history, and an IV rank needs a
year of it. So every chain's IV30 is recorded once per session day
(cache/iv_history.jsonl) from the day this shipped; the rank appears once
twenty days are in, and says how many it has until then.
"""

from __future__ import annotations

import json
import os
import time
from datetime import UTC, date, datetime, timedelta

from .. import optcalc
from ..config import BROWSER_UA, CACHE_DIR
from ..holidays import is_trading_day, prev_trading_day
from ..http import CACHE, SourceStatus, fetch, json_body

CBOE = "https://cdn.cboe.com/api/global/delayed_quotes/options/{sym}.json"
IV_HISTORY_FILE = os.path.join(CACHE_DIR, "iv_history.jsonl")

TICK_SEC = 10.0
#: Refresh cadence in the stocks session window, and outside it.
ETF_SEC = 300.0
SINGLE_SEC = 600.0
IDLE_SEC = 3600.0
SESSION_FROM = 8 * 60
SESSION_TO = 16 * 60 + 15
#: One chain per tick — the budget above is one request per ten seconds at most.
MAX_PER_TICK = 1
#: A name whose copy is older than this many cadences counts as stale.
STALE_CADENCES = 2.0
#: Back-off after a failure: doubling from a minute to half an hour; a 403 / 429
#: pauses every fetch for five minutes.
FAIL_BASE = 60.0
FAIL_CAP = 1800.0
PAUSE_SEC = 300.0
#: Days of IV kept (a year of sessions, with room).
IV_KEEP_DAYS = 400


def cadence(sym: str, now: datetime) -> float:
    """How often `sym` is refreshed at `now` (module docstring)."""
    et = now.astimezone(optcalc.ET)
    m = et.hour * 60 + et.minute
    if is_trading_day(et.date()) and SESSION_FROM <= m < SESSION_TO:
        return ETF_SEC if sym in optcalc.DAILY_EXPIRY else SINGLE_SEC
    return IDLE_SEC


def iv_day(asof: datetime | None, now: datetime) -> date:
    """The session an IV30 reading belongs to: the latest trading day whose
    regular session had begun when it was read. A pre-market or weekend read is
    still the last close's volatility, not a new day's."""
    et = (asof or now).astimezone(optcalc.ET)
    d = et.date()
    if is_trading_day(d) and et.hour * 60 + et.minute >= 9 * 60 + 30:
        return d
    return prev_trading_day(d)


# ------------------------------------------------------------------ IV history


class IvHistory:
    """One IV30 per name per session day, on disk as JSON lines."""

    def __init__(self, path: str = IV_HISTORY_FILE) -> None:
        self.path = path
        self.data: dict[str, dict[str, float]] = {}
        self._dirty = False
        self.load()

    def load(self) -> None:
        try:
            with open(self.path, encoding="utf-8") as f:
                for line in f:
                    try:
                        r = json.loads(line)
                        sym, day, iv = str(r["sym"]), str(r["day"]), float(r["iv30"])
                    except (ValueError, KeyError, TypeError):
                        continue
                    self.data.setdefault(sym, {})[day] = iv
        except OSError:
            pass

    def record(self, sym: str, day: date, iv30: float | None) -> None:
        if iv30 is None:
            return
        book = self.data.setdefault(sym, {})
        k = day.isoformat()
        if book.get(k) != iv30:
            book[k] = iv30
            self._dirty = True

    def series(self, sym: str) -> list[float]:
        # A copy first: the API thread reads while the options thread writes.
        book = dict(self.data.get(sym) or {})
        return [book[k] for k in sorted(book)]

    def save(self, today: date | None = None) -> None:
        """Write if anything changed: atomic, and pruned to IV_KEEP_DAYS."""
        if not self._dirty:
            return
        cut = ((today or date.today()) - timedelta(days=IV_KEEP_DAYS)).isoformat()
        tmp = self.path + ".tmp"
        try:
            os.makedirs(os.path.dirname(self.path) or ".", exist_ok=True)
            with open(tmp, "w", encoding="utf-8") as f:
                for sym in sorted(self.data):
                    for day in sorted(self.data[sym]):
                        if day >= cut:
                            f.write(json.dumps({"sym": sym, "day": day,
                                                "iv30": self.data[sym][day]}) + "\n")
            os.replace(tmp, self.path)
            self._dirty = False
        except OSError:
            pass


# ------------------------------------------------------------- chain summaries


def _summary_key(sym: str) -> str:
    return f"cboe_sum_{sym}"


def dump_chain(c: optcalc.Chain) -> bytes:
    """A Chain as compact JSON — the only copy of a chain that reaches disk."""
    return json.dumps({
        "sym": c.sym, "spot": c.spot, "iv30": c.iv30,
        "asof": c.asof.isoformat() if c.asof else None,
        "expiries": [e.isoformat() for e in c.expiries],
        "opts": {e.isoformat(): [[o.symbol, o.right, o.strike, o.bid, o.ask, o.iv, o.delta,
                                  o.theta, o.oi, o.volume, o.gamma] for o in opts]
                 for e, opts in c.opts.items()},
    }, separators=(",", ":")).encode()


def load_chain(blob: bytes) -> optcalc.Chain | None:
    """A summary back to a Chain. Rows written before gamma was kept have ten
    fields, not eleven; they load with no gamma (a delta-only estimate)."""
    try:
        d = json.loads(blob)
        opts: dict[date, list[optcalc.Opt]] = {}
        for k, rows in (d.get("opts") or {}).items():
            e = date.fromisoformat(k)
            opts[e] = [optcalc.Opt(symbol=r[0], expiry=e, right=r[1], strike=r[2], bid=r[3],
                                   ask=r[4], iv=r[5], delta=r[6], theta=r[7], oi=r[8],
                                   volume=r[9], gamma=r[10] if len(r) > 10 else None)
                       for r in rows]
        asof = datetime.fromisoformat(d["asof"]) if d.get("asof") else None
        return optcalc.Chain(sym=str(d["sym"]), spot=d.get("spot"), iv30=d.get("iv30"),
                             asof=asof, expiries=[date.fromisoformat(x) for x in d["expiries"]],
                             opts=opts)
    except (ValueError, KeyError, TypeError, IndexError):
        return None


# ----------------------------------------------------------------------- store


class OptionsStore:
    """The chains held between ticks. Written only by the options thread; the
    read path takes a shallow copy (`view`), and a chain is replaced whole,
    never mutated, so a reader never sees half of one."""

    def __init__(self, history_path: str = IV_HISTORY_FILE) -> None:
        self.chains: dict[str, optcalc.Chain] = {}
        self.fetched: dict[str, float] = {}
        self.errors: dict[str, str] = {}
        self.fails: dict[str, tuple[int, float]] = {}
        self.pause_until = 0.0
        self.history = IvHistory(history_path)
        self.body_bytes: dict[str, int] = {}
        self._warm = False

    def view(self) -> dict[str, tuple[optcalc.Chain, float]]:
        fetched = dict(self.fetched)
        return {s: (c, fetched.get(s, 0.0)) for s, c in dict(self.chains).items()}

    def _warm_start(self, syms: list[str]) -> None:
        self._warm = True
        now = time.time()
        for sym in syms:
            key = _summary_key(sym)
            blob, age = CACHE.read(key), CACHE.age_sec(key)
            if blob is None or age is None:
                continue
            c = load_chain(blob)
            if c is not None:
                self.chains[sym], self.fetched[sym] = c, now - age

    def due(self, syms: list[str], now: datetime) -> list[str]:
        """Names due for a refresh, most overdue first, skipping any in back-off."""
        t = now.timestamp()
        out: list[tuple[float, str]] = []
        for s in syms:
            n, until = self.fails.get(s, (0, 0.0))
            if n and t < until:
                continue
            lag = t - self.fetched.get(s, 0.0) - cadence(s, now)
            if lag >= 0:
                out.append((-lag, s))
        return [s for _, s in sorted(out)]

    def fetch_one(self, sym: str, ref_day: date, now: datetime) -> str | None:
        """Fetch, parse and keep one chain. Returns an error, or None."""
        r = fetch(CBOE.format(sym=sym), key=f"cboe_{sym}", ttl_sec=0, ua=BROWSER_UA, timeout=40,
                  headers={"Accept": "application/json", "Accept-Encoding": "gzip"},
                  stale_ok=False, store=False, validate=json_body)
        t = now.timestamp()
        if not r.ok or r.body is None:
            n = self.fails.get(sym, (0, 0.0))[0] + 1
            self.fails[sym] = (n, t + min(FAIL_BASE * 2 ** (n - 1), FAIL_CAP))
            if r.status in (403, 429):
                self.pause_until = t + PAUSE_SEC
            err = ("Cboe lists no options for this symbol" if r.status == 404
                   else f"Cboe: {r.error or 'unreachable'}")
            self.errors[sym] = err
            return err
        try:
            doc = json.loads(r.body)
        except ValueError as e:
            self.errors[sym] = f"Cboe sent an unreadable chain ({e})"
            return self.errors[sym]
        c = optcalc.parse_chain(doc, sym, ref_day)
        if c.spot is None or not c.expiries:
            self.errors[sym] = "Cboe's chain has no price or no expiries"
            return self.errors[sym]
        self.chains[sym] = c
        self.fetched[sym] = t
        self.fails.pop(sym, None)
        self.errors.pop(sym, None)
        self.body_bytes[sym] = len(r.body)
        self.history.record(sym, iv_day(c.asof, now), c.iv30)
        CACHE.write(_summary_key(sym), dump_chain(c))
        return None

    def tick(self, syms: list[str], ref_day: date, now: datetime | None = None) -> SourceStatus:
        """One rotation step: at most MAX_PER_TICK chains, then the status."""
        now = now or datetime.now(UTC)
        if not self._warm:
            self._warm_start(syms)
        st = SourceStatus("Cboe options")
        t = now.timestamp()
        due = self.due(syms, now)
        paused = t < self.pause_until
        errors: list[str] = []
        done = 0
        if not paused:
            for sym in due[:MAX_PER_TICK]:
                err = self.fetch_one(sym, ref_day, now)
                done += 1
                if err:
                    errors.append(f"{sym}: {err}")
        self.history.save(now.astimezone(optcalc.ET).date())

        have = [s for s in syms if s in self.chains]
        st.items = len(have)
        # Stale = held longer than STALE_CADENCES of its own cadence.
        stale_ages = [(t - self.fetched[s]) / 60.0 for s in have
                      if t - self.fetched[s] > STALE_CADENCES * cadence(s, now)]
        st.fetches = len(have)
        st.stale = len(stale_ages)
        st.stale_age_min = max(stale_ages) if stale_ages else None
        if errors:
            st.error = errors[0]
        st.settle(bool(have), what="chain")
        st.notes = [f"{done} refreshed, {max(len(due) - done, 0)} due"]
        missing = [s for s in syms if s not in self.chains]
        if missing:
            st.notes.append(f"no chain yet: {', '.join(missing[:5])}")
        backing = [s for s in syms if self.fails.get(s, (0, 0.0))[0] and t < self.fails[s][1]]
        if backing:
            st.notes.append(f"backing off: {', '.join(backing[:4])}")
        if paused:
            until = datetime.fromtimestamp(self.pause_until, optcalc.ET).strftime("%H:%M:%S")
            st.notes.append(f"Cboe refused (403/429) — paused until {until} ET")
        return st
