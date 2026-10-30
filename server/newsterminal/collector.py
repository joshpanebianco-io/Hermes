"""
The collector — one background thread, many clocks.

WHY A THREAD AND NOT A REQUEST HANDLER. If the panels fetched on demand, the
first load after a cold start would sit for thirty seconds while forty
upstreams answered one at a time, and every reader who opened a second tab
would pay it again. The collector keeps a warm snapshot and the API hands out
whatever it currently holds; a page load costs one in-memory read.

WHY ONE THREAD AND NOT A POOL. The cadences are seconds to half-hours apart, so
at any given tick there is usually one source due, occasionally two. A pool
would buy nothing and would mean the tick log — the thing this window exists to
show — could interleave two half-written rows.

…EXCEPT THE SCANNER, WHICH GETS ONE OF ITS OWN (review, 2026-10-13). Its three
jobs add ~20 Yahoo requests a minute, two to eight seconds a tick, and on the
one shared thread the board's quotes ran up to 47s late against a 20s cadence.
The scanner's store is written only by its own jobs, so it runs beside the
board rather than in front of it; the tick log takes a lock so the two never
interleave a row.

THE OPTION CHAINS HAVE ONE AS WELL (owner, 2026-10-13: the stocks desk). A
Cboe chain is one request but up to 0.8 MB gzipped and a second of parsing for
SPY; one every ten seconds on the scanner's thread would have stretched its
ticks for nothing the scanner's rank depends on. They rotate on their own.

SO DOES THE SCANNER'S LIVE LAYER (owner, 2026-10-14: the regular session "as
close to real time as possible"). Two batched quote requests every five seconds
cannot wait behind a bars tick that is itself five sequential requests, so they
rotate alone, rebuild the scanner block from the bars held plus each name's
last trade, and log one row a minute rather than twelve.

AND THE QUOTES GET ONE TOO. Pre-empting inside the shared loop (one job, then
back to the top) took the worst lag from 48s to 38s, measured — but a quotes
tick that falls due DURING a job still waits for it to finish, and the wire's
forty feeds are one job. The board is the block every panel is read against, so
it runs alone: its lag is now its own cadence plus its own fetch, and nothing
else. The rest of the shared loop still runs one due job and starts again from
the top, so a short job is never stuck behind a pass of long ones.

EVERY SOURCE IS INDEPENDENT. A source that raises is caught, logged on its own
row, and leaves the previous good data in place with its age climbing. That is
why `age_min` is on every block: a panel showing eleven-minute-old sector data
is fine as long as it says eleven minutes.
"""

from __future__ import annotations

import contextlib
import sys
import threading
import time
import traceback
from collections.abc import Callable
from datetime import UTC, date, datetime
from typing import Any
from zoneinfo import ZoneInfo

from . import config, drivers, marketctx
from . import scan as scan_mod
from .expiry import state as expiry_state
from .http import CACHE, SourceStatus
from .policy import meetings_priced
from .scanlog import EventLog
from .scanscore import build as scanner_build
from .scanscore import earnings_for, next_report
from .sessions import session_state
from .sources import auctions as auc_src
from .sources import calendar as cal_src
from .sources import cboepc as pc_src
from .sources import constituents as cons_src
from .sources import cot as cot_src
from .sources import earnhist as eh_src
from .sources import earnings as earn_src
from .sources import fedcal as fed_src
from .sources import gex as gex_src
from .sources import history as hist_src
from .sources import options as opt_src
from .sources import pool as pool_src
from .sources import premarket as pre_src
from .sources import profiles as prof_src
from .sources import quotes as quotes_src
from .sources import ranges as ranges_src
from .sources import rates as rates_src
from .sources import scanner as scan_src
from .sources import shortint as short_src
from .sources import wire as wire_src
from .volterm import implied_day, vix_month
from .volterm import state as volterm_state

ET = ZoneInfo("America/New_York")

# A LOG LINE MUST NEVER TAKE THE COLLECTOR DOWN (2026-10-14). Started with its
# output redirected to a file, Python on Windows writes in the legacy code
# page, which has no "└─" — the UnicodeEncodeError raised inside `_log`, and
# again inside the handler that logs the failure, killed the collector thread
# outright: quotes, wire and calendar all stopped while the API kept serving
# the last snapshot. Unprintable characters now print as "?".
for _stream in (sys.stdout, sys.stderr):
    with contextlib.suppress(AttributeError, ValueError):
        _stream.reconfigure(errors="replace")  # type: ignore[union-attr]

# Widths chosen so the row stays aligned once the longest source name and a
# four-digit item count are in it. A tick log that reflows is a tick log you
# stop being able to scan.
_HEAD = f"{'TIME':<9}{'SOURCE':<12}{'ITEMS':>6}  {'AGE':>6}  {'SRC':<7}STATUS"

# THE SCANNER'S BLOCKS ARE NOT PART OF /api/terminal. The terminal polls every
# twenty seconds for the whole board; thirty names of bars-derived rows, their
# headlines and filings would roughly double that payload for a tab that is
# usually closed. They live in state like everything else and are served only
# by /api/scanner (see `scanner_payload`).
_SCANNER_KEYS = frozenset({"scanner", "scan_news", "scan_sec", "scan_earn"})

# A job is (fn, interval_sec, next_due_monotonic). A fn may return a number of
# seconds to run again in instead of its interval — the scanner's close read
# and the live layer's back-off pace themselves that way.
Job = tuple[Callable[[], float | None], float, float]


class Collector:
    """Holds the terminal's whole state and refreshes it on schedule."""

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._stop = threading.Event()
        self._thread: threading.Thread | None = None
        self.started_utc = datetime.now(UTC).isoformat()

        # block name → (fn, interval_sec, next_due_monotonic)
        self._jobs: dict[str, Job] = {}
        self._state: dict[str, Any] = {
            "quotes": [], "sectors": [], "context": [], "wire": [], "calendar": [],
            "earnings": [],
            "rates": {}, "ranges": {"assets": {}}, "constituents": {"indices": {}},
            "fed": [],
            "fomc": [],
            "auctions": [],
            "profiles": {"assets": {}},
            "gex": {"assets": {}, "enabled": bool(config.GEXYGEN_API)},
            "scanner": {}, "scan_news": {}, "scan_sec": {}, "scan_earn": [],
            # The driver board's own inputs (2026-10-22): a year of daily bars
            # per book, the CFTC's positioning, Cboe's daily put/call.
            "history": {"books": {}}, "cot": {"books": {}}, "putcall": None,
        }
        self.scan = scan_src.ScanStore()
        # The bars job and the live job both rebuild the scanner block; one at a
        # time, so a build from older bars can never land after a newer one.
        self._scan_build_lock = threading.Lock()
        self._live_logged = 0.0
        # The scanner's event log (scanlog.py): the alerts' feed and the record
        # each signal's outcome is kept in. Loaded from disk so ids keep counting.
        self.events = EventLog()
        self._status: dict[str, SourceStatus] = {}
        self._updated: dict[str, float] = {}
        self._logged_header = False
        self._log_lock = threading.Lock()
        self._scan_thread: threading.Thread | None = None
        self._quotes_thread: threading.Thread | None = None
        self._options_thread: threading.Thread | None = None
        self._premarket_thread: threading.Thread | None = None
        # The stocks desk's option chains (sources/options.py) and their IV log.
        self.options = opt_src.OptionsStore()
        # Each name's pre-market from Nasdaq (sources/premarket.py), kept for the day.
        self.premarket = pre_src.PremarketStore()
        # Cboe's daily put/call log, each name's short interest and its past
        # report dates (sources/cboepc, shortint, earnhist).
        self.putcall = pc_src.PutCallStore()
        self.shorts = short_src.ShortStore()
        self.earnhist = eh_src.EarnHistStore()
        # The pool (sources/pool.py): hundreds of large caps read in one
        # request, the names in play promoted into the scanner's list. Its
        # saved promotions reach the scanner before the warm start, so a
        # restart repaints them beside the pinned names.
        self.pool = pool_src.PoolStore()
        self.scan.set_promoted(*self.pool.for_scan())

        now = time.monotonic()
        # The board, on a thread of its own (module docstring): it is the block
        # every other panel is read against, and a board with no prices is not
        # a terminal.
        self._quote_jobs: dict[str, Job] = {
            "quotes": (self._do_quotes, config.QUOTES_SEC, now),
        }
        self._jobs = {
            "gex": (self._do_gex, config.GEX_SEC, now + 0.4),
            "wire": (self._do_wire, config.WIRE_SEC, now + 0.8),
            "sectors": (self._do_sectors, config.QUOTES_SEC * 15, now + 1.2),
            "calendar": (self._do_calendar, config.CALENDAR_SEC, now + 1.6),
            "rates": (self._do_rates, config.RATES_SEC, now + 2.0),
            # Session ranges move with price but the WINDOWS only close four
            # times a day, so a minute is ample and matches nothing else.
            "ranges": (self._do_ranges, 60.0, now + 2.4),
            # Earnings change when a company reports, which is twice a day at
            # the bells. Half-hourly is generous.
            "earnings": (self._do_earnings, 1800.0, now + 2.8),
            # Weights move once a day and are cached hard; this cadence is
            # really about the 40 quotes behind them.
            "constituents": (self._do_constituents, 90.0, now + 3.2),
            # The Board publishes weeks ahead and amends rarely.
            "fed": (self._do_fed, 3600.0, now + 3.6),
            # Six-hour cadence: the auction schedule is set weeks ahead and
            # amends almost never.
            "auctions": (self._do_auctions, 6 * 3600.0, now + 5.0),
            # Five minutes: the levels move slowly and the fetch is 3 x 55KB.
            "profiles": (self._do_profiles, 300.0, now + 8.0),
            # Daily bars for the session brief. The sectors' clock, because
            # the week and month changes it feeds move no faster than theirs.
            "context": (self._do_context, config.QUOTES_SEC * 15, now + 4.4),
            # A year of daily bars per book, hourly: the frame moves once a day.
            "history": (self._do_history, hist_src.TTL_SEC, now + 6.0),
            # The CFTC publishes once a week; six-hourly catches Friday's.
            "cot": (self._do_cot, cot_src.TTL_SEC, now + 7.0),
            # Cboe's daily file: a minute between ticks while the log backfills,
            # and the same minute catches today's file once it is published.
            "putcall": (self._do_putcall, 60.0, now + 8.5),
        }
        # The scanner's own thread runs these (see the module docstring). Each
        # rotates its names inside a tick — sources/scanner.py has the budget.
        self._scan_jobs: dict[str, Job] = {
            "scanner": (self._do_scanner, scan_src.TICK_SEC, now + 1.0),
            "scan_news": (self._do_scan_news, 60.0, now + 6.0),
            "scan_sec": (self._do_scan_sec, 60.0, now + 9.0),
            # Short interest from Yahoo's summary: one name a tick, twelve
            # hours between reads of the same name.
            "scan_short": (self._do_shorts, short_src.TICK_SEC, now + 12.0),
        }
        # The chains, on their own thread (module docstring); one per tick.
        self._option_jobs: dict[str, Job] = {
            "options": (self._do_options, opt_src.TICK_SEC, now + 3.0),
        }
        # Nasdaq's pre-market, on a thread of its own: its API can hang for the
        # whole timeout, and that must not hold up a chain or a quote.
        self._premarket_jobs: dict[str, Job] = {
            "premarket": (self._do_premarket, pre_src.TICK_SEC, now + 5.0),
            # The same host: each name's past report dates, one a tick, daily.
            "scan_earnhist": (self._do_earnhist, eh_src.TICK_SEC, now + 7.5),
            # The pool: one POST to TradingView's screener every five minutes
            # in the morning, half-hourly otherwise; the tick is short so a
            # mark (08:00, 09:00, 09:25, 10:00 ET) is met within seconds.
            "pool": (self._do_pool, pool_src.TICK_SEC, now + 4.0),
        }
        # The live layer, alone (module docstring); it paces itself.
        self._live_jobs: dict[str, Job] = {
            "scan_live": (self._do_live, scan_src.LIVE_SEC, now + 2.0),
        }
        self._live_thread: threading.Thread | None = None

    # ---------------------------------------------------------------- jobs

    def _commit(self, name: str, data: Any, st: SourceStatus) -> None:
        with self._lock:
            if data is not None:
                self._state[name] = data
            self._status[name] = st
            if st.ok:
                # A block served from a stale fallback is as old as those bytes,
                # not as old as this tick — otherwise every age chip on the board
                # reads "live" through an outage (review, 2026-10-13).
                self._updated[name] = time.time() - (st.stale_age_min or 0.0) * 60.0
        self._log(name, st)

    def _do_quotes(self) -> None:
        rows, st = quotes_src.collect()
        self._commit("quotes", rows if st.ok else None, st)

    def _do_sectors(self) -> None:
        rows, st = quotes_src.collect_sectors()
        self._commit("sectors", rows if st.ok else None, st)

    def _do_context(self) -> None:
        rows, st = quotes_src.collect_context()
        self._commit("context", rows if st.ok else None, st)

    def _do_history(self) -> None:
        data, st = hist_src.collect()
        self._commit("history", data if st.ok else None, st)

    def _do_cot(self) -> None:
        data, st = cot_src.collect()
        self._commit("cot", data if st.ok else None, st)

    def _do_putcall(self) -> None:
        summary, st = self.putcall.tick()
        self._commit("putcall", summary if st.ok else None, st)

    def _do_shorts(self) -> None:
        st = self.shorts.tick(self.scan.watchlist())
        # Like the chains: the reads stay in the store and join the rows on read.
        self._commit("scan_short", None, st)

    def _do_earnhist(self) -> None:
        st = self.earnhist.tick(self.scan.watchlist())
        self._commit("scan_earnhist", None, st)

    def _reports_ahead(self, td: date) -> dict[str, date]:
        """Each watchlist name's next report date, from the earnings rows held —
        what the chain store keeps the covering expiry for."""
        with self._lock:
            rows = list(self._state.get("scan_earn") or [])
        nxt = self.earnhist.view_next()
        out: dict[str, date] = {}
        for sym in self.scan.watchlist():
            e = earnings_for(sym, rows, td) or next_report(nxt.get(sym), td)
            if e and isinstance(e.get("days"), int) and e["days"] >= 0:
                try:
                    out[sym] = date.fromisoformat(str(e.get("date")))
                except ValueError:
                    continue
        return out

    def _do_wire(self) -> None:
        items, feeds = wire_src.collect()
        st = SourceStatus("wire")
        live = [f for f in feeds if f.ok and f.source != "stale"]
        stale = [f for f in feeds if f.ok and f.source == "stale"]
        st.items = len(items)
        st.notes = [f"{len(live)}/{len(feeds)} feeds"]
        dead = [f for f in feeds if not f.ok]
        if dead:
            st.error = f"{len(dead)} feed(s) down: " + ", ".join(f.name for f in dead[:3])
        if stale:
            # Some feeds are showing their last copy. The tape is still live
            # unless they ALL are — but the share is said, and the oldest copy
            # dates the block.
            st.notes.append(f"{len(stale)} feed(s) on a cached copy")
            st.stale = len(stale)
            st.fetches = len(feeds)
            st.stale_age_min = max(f.age_min or 0.0 for f in stale)
        if items and not live and stale:
            st.source = "stale"
            st.ok = True
            st.age_min = st.stale_age_min
            st.error = st.error or "every feed unreachable — showing cached copies"
            st.last_ok_utc = datetime.now(UTC).isoformat()
        else:
            st.ok = bool(items)
            st.source = "live" if st.ok else "unavailable"
            st.age_min = 0.0 if st.ok else None
            if st.ok:
                st.last_ok_utc = datetime.now(UTC).isoformat()
        with self._lock:
            self._state["wire_feeds"] = [f.as_dict() for f in feeds]
        self._commit("wire", items if st.ok else None, st)

    def _do_calendar(self) -> None:
        rows, st = cal_src.collect()
        self._commit("calendar", rows if st.ok else None, st)

    def _do_rates(self) -> None:
        data, st = rates_src.collect()
        self._commit("rates", data if st.ok else None, st)

    def _do_ranges(self) -> None:
        data, st = ranges_src.collect()
        self._commit("ranges", data if st.ok else None, st)

    def _do_earnings(self) -> None:
        rows, st = earn_src.collect(keep=frozenset(self.scan.watchlist()))
        # The panel is about what moves an index; the scanner wants its own
        # names whatever their size. One fetch, two readers.
        if st.ok:
            with self._lock:
                self._state["scan_earn"] = rows
        panel = [r for r in rows if not r.get("watch_only")]
        self._commit("earnings", panel if st.ok else None, st)

    def _do_scanner(self) -> float:
        st = self.scan.tick_bars()
        with self._scan_build_lock:
            self._commit("scanner", self.scan.compute(), st)
        # The log reads the SCORED payload, so each event carries the score its
        # row had at the moment it fired — what the outcomes are judged against.
        # Its failure is its own: a log that cannot be written must not mark the
        # scanner itself as down.
        try:
            payload = self.scanner_payload()
            self.events.observe(payload, dict(self.scan.bars), fetched=dict(self.scan.fetched))
            # A finished day's signals, settled once against bars read after its
            # bell (scanlog's "second look"). Cheap when there is nothing to do:
            # only names with unchecked events and a post-bell download replay.
            for day, syms in self.events.unchecked(str(payload.get("trading_day") or "")).items():
                got = self.scan.day_signals(date.fromisoformat(day), syms)
                if got:
                    self.events.settle(day, got)
        except Exception as e:  # noqa: BLE001 — see module docstring
            st_ev = SourceStatus("Scanner events")
            st_ev.error = f"{e.__class__.__name__}: {e}"
            self._log("scan_events", st_ev)
            traceback.print_exc()
        # Soon while a close read is unfinished, on time for the next one.
        return self.scan.wake_in()

    def _do_live(self) -> float:
        st, delay = self.scan.tick_live()
        if st is None:
            # Outside the session: say so once, so the rail does not keep
            # showing the afternoon's last good read as if it were live.
            with self._lock:
                cur = self._status.get("scan_live")
                if cur is not None and cur.source != "idle":
                    idle = SourceStatus("Scanner live")
                    idle.ok, idle.source = True, "idle"
                    idle.notes = ["regular session only (09:30–16:00 ET)"]
                    self._status["scan_live"] = idle
            return delay
        with self._scan_build_lock:
            data = self.scan.compute()
            with self._lock:
                self._state["scanner"] = data
                self._status["scan_live"] = st
                if st.ok:
                    self._updated["scan_live"] = time.time()
        # Its own row once a minute, or whenever a read fails: twelve rows a
        # minute would bury every other source in the window.
        now = time.monotonic()
        if not st.ok or st.error or now - self._live_logged >= 60.0:
            self._live_logged = now
            self._log("scan_live", st)
        return delay

    def scanner_bars(self, sym: str, tf: str = "10m") -> dict[str, Any]:
        """One name's mini-chart series (scan.chart_series) off the bars held —
        plus, for the 1m and 3m views, a one-minute download made here, on the
        request (ScannerStore.bars_1m)."""
        sym = sym.strip().upper()
        if sym not in self.scan.symbols():
            return {"ok": False, "sym": sym, "tf": tf, "error": "not on the watchlist"}
        clock = self.scan.clock(datetime.now(UTC))
        # The live trade on the last candle too, so the chart's price agrees
        # with the row beside it.
        bars = self.scan.live_bars(sym, clock)
        if not bars:
            return {"ok": False, "sym": sym, "tf": tf, "error": "no bars yet"}
        daily = self.scan.daily.get(sym) or []
        # Confirmed by the download, as on the row (scan.CLOSE_LAG_SEC) — a chart
        # marking a signal the row does not have would be its own phantom.
        tech = scan_mod.technicals(bars, daily, clock,
                                   official=scan_mod.official_close(self.scan.meta.get(sym)),
                                   asof=self.scan.fetched.get(sym))
        bars1: list[scan_mod.Bar] | None = None
        if scan_mod.CHART_TF.get(tf, 600) < 300:
            bars1, err = self.scan.bars_1m(sym)
            if not bars1:
                return {"ok": False, "sym": sym, "tf": tf, "error": err or "no one-minute bars"}
        out = scan_mod.chart_series(bars, clock, tech, tf, bars1=bars1, daily=daily,
                                    daily_asof=self.scan.daily_at.get(sym))
        out["sym"] = sym
        return out

    def _do_options(self) -> None:
        clock = self.scan.clock(datetime.now(UTC))
        st = self.options.tick(self.scan.watchlist(), clock.trading_day,
                               reports=self._reports_ahead(clock.trading_day))
        # Nothing goes into state: the chains stay in the store and are joined
        # into the scanner's rows on read (`scanner_payload`) — only the status
        # row, for the rail.
        self._commit("options", None, st)

    def _do_premarket(self) -> None:
        st = self.premarket.tick(self.scan.watchlist())
        # Like the chains: the reads stay in the store and join the rows on read.
        self._commit("premarket", None, st)

    def _do_scan_news(self) -> None:
        st = self.scan.tick_news()
        self._commit("scan_news", dict(self.scan.news), st)

    def _do_scan_sec(self) -> None:
        st = self.scan.tick_sec()
        self._commit("scan_sec", dict(self.scan.filings), st)

    def set_watchlist(self, symbols: list[str]) -> tuple[list[str], list[str]]:
        """Save the scanner's pinned list and make the new names the next thing
        fetched.

        Called from the API thread. Only the job clocks are touched here — the
        fetching itself stays on the collector thread, where every other
        upstream call lives.
        """
        ok, bad = self.scan.set_watchlist(symbols)
        self._wake_scan_jobs()
        return ok, bad

    def _wake_scan_jobs(self) -> None:
        """Make whatever the list now holds the next thing every scanner job fetches."""
        now = time.monotonic()
        for jobs, name in ((self._scan_jobs, "scanner"), (self._scan_jobs, "scan_news"),
                           (self._scan_jobs, "scan_sec"), (self._jobs, "earnings")):
            fn, interval, _due = jobs[name]
            jobs[name] = (fn, interval, now)

    def _do_pool(self) -> None:
        st, read, changed = self.pool.tick(self.scan.pinned())
        if self._apply_promotions() or changed:
            self._wake_scan_jobs()
        # One row per READ, not per tick: the job ticks every twenty seconds
        # to meet a mark on time and reads every five minutes at most.
        if read:
            self._commit("pool", self.pool.view(self.scan.pinned()), st)

    def _apply_promotions(self) -> bool:
        """The pool's promotions into the scanner's list. True when it changed."""
        day, syms, sectors = self.pool.for_scan()
        return self.scan.set_promoted(day, syms, sectors)

    def set_promotion(self, on: bool) -> None:
        """Switch the pool's promotion (API thread). Off takes today's promoted
        names off the list at once; on makes the pool's next tick a read."""
        if self.pool.set_enabled(on):
            self._apply_promotions()
            self._wake_scan_jobs()
            fn, interval, _due = self._premarket_jobs["pool"]
            self._premarket_jobs["pool"] = (fn, interval, time.monotonic())

    def watchlist_payload(self, rejected: list[str] | None = None) -> dict[str, Any]:
        """The /api/scanner/watchlist read: the pinned list and the pool's view."""
        pinned = self.scan.pinned()
        return {"symbols": pinned, "default": list(scan_src.DEFAULT_WATCHLIST),
                "rejected": list(rejected or []), "pool": self.pool.view(pinned)}

    def _do_constituents(self) -> None:
        data, st = cons_src.collect()
        self._commit("constituents", data if st.ok else None, st)

    def _do_fed(self) -> None:
        rows, fomc, st = fed_src.collect()
        self._commit("fed", rows if st.ok else None, st)
        # The schedule rides the same fetch but is not a source of its own:
        # it has no panel, no age chip, and no failure mode separate from the
        # diary's, so a second status row would be bookkeeping about nothing.
        if st.ok:
            with self._lock:
                self._state["fomc"] = fomc

    def _do_auctions(self) -> None:
        rows, st = auc_src.collect()
        self._commit("auctions", rows if st.ok else None, st)

    def _do_profiles(self) -> None:
        data, st = prof_src.collect()
        # Committed even when degraded, like gex: the panel needs the per-asset
        # error text, and a preserved older profile would be a stale level.
        self._commit("profiles", data, st)

    def _do_gex(self) -> None:
        data, st = gex_src.collect()
        # Committed even when not ok: the panel needs the per-asset error text
        # to say WHICH asset is missing and why, and a preserved older payload
        # would be a stale gamma level, which this must never show.
        self._commit("gex", data, st)

    # ---------------------------------------------------------------- loop

    def _log(self, name: str, st: SourceStatus) -> None:
        if not config.TICK_LOG:
            return
        # One lock round the row and its └─ lines: two threads now write here.
        with self._log_lock:
            if not self._logged_header:
                print(f"\n{_HEAD}", flush=True)
                self._logged_header = True
            t = datetime.now(ET).strftime("%H:%M:%S")
            age = f"{st.age_min:.1f}m" if st.age_min is not None else "—"
            state = "ok" if st.ok else "ERR"
            print(f"{t:<9}{name:<12}{st.items:>6}  {age:>6}  {st.source:<7}{state}", flush=True)
            # Anything degraded gets its own line underneath, so a dead feed
            # cannot hide between healthy rows. Straight out of GEXYGEN's window.
            if st.error:
                print(f"{'':<9}└─ {st.error}", flush=True)
            for n in st.notes:
                if not st.ok or "down" in n or "unavailable" in n or "failed" in n:
                    print(f"{'':<9}└─ {n}", flush=True)

    def _run_one(self, jobs: dict[str, Job]) -> bool:
        """Run the FIRST due job in `jobs`, if any. True when one ran.

        One job, then back to the top: the dict is in priority order, so a
        quotes tick that falls due while the wire is fetching runs next, not
        after everything else that was due in the same pass.
        """
        now = time.monotonic()
        for name, (fn, interval, due) in list(jobs.items()):
            if now < due:
                continue
            wait = interval
            try:
                asked = fn()
                if asked is not None and asked > 0:
                    wait = asked
            except Exception as e:  # noqa: BLE001 — see module docstring
                st = SourceStatus(name)
                st.error = f"{e.__class__.__name__}: {e}"
                self._status[name] = st
                self._log(name, st)
                traceback.print_exc()
            jobs[name] = (fn, interval, time.monotonic() + wait)
            return True
        return False

    def _run(self, jobs: dict[str, Job] | None = None,
             ) -> None:
        jobs = self._jobs if jobs is None else jobs
        while not self._stop.is_set():
            if self._run_one(jobs):
                continue
            # 0.25s rather than a computed sleep-until-next-due: the loop must
            # also notice _stop promptly, and a quarter second of idle polling
            # costs nothing next to forty HTTP requests a minute.
            self._stop.wait(0.25)

    def start(self) -> None:
        if self._thread and self._thread.is_alive():
            return
        # Orphaned cache files go at startup: a removed watchlist name's bars,
        # a past day's calendar, the spark keys the old per-process hash left.
        gone = CACHE.prune(7 * 86400.0, keep=("scanner_watchlist.json", "scanner_pool.json",
                                              "scanner_events.jsonl", "iv_history.jsonl",
                                              "oi_log.jsonl", "cboe_pc.jsonl"))
        if gone and config.TICK_LOG:
            print(f"cache: pruned {gone} file(s) untouched for 7 days", flush=True)
        self._thread = threading.Thread(target=self._run, name="collector", daemon=True)
        self._thread.start()
        self._scan_thread = threading.Thread(
            target=self._run, args=(self._scan_jobs,), name="scanner", daemon=True)
        self._scan_thread.start()
        self._quotes_thread = threading.Thread(
            target=self._run, args=(self._quote_jobs,), name="quotes", daemon=True)
        self._quotes_thread.start()
        self._options_thread = threading.Thread(
            target=self._run, args=(self._option_jobs,), name="options", daemon=True)
        self._options_thread.start()
        self._premarket_thread = threading.Thread(
            target=self._run, args=(self._premarket_jobs,), name="premarket", daemon=True)
        self._premarket_thread.start()
        self._live_thread = threading.Thread(
            target=self._run, args=(self._live_jobs,), name="scan-live", daemon=True)
        self._live_thread.start()

    def stop(self) -> None:
        self._stop.set()
        for th in (self._thread, self._scan_thread, self._quotes_thread, self._options_thread,
                   self._premarket_thread, self._live_thread):
            if th:
                th.join(timeout=3)

    # ---------------------------------------------------------------- read

    def snapshot(self) -> dict[str, Any]:
        """Everything, as one object. Thread-safe."""
        with self._lock:
            state = {k: v for k, v in self._state.items() if k not in _SCANNER_KEYS}
            status = {k: v.as_dict() for k, v in self._status.items()}
            updated = dict(self._updated)

        now = time.time()
        ages = {k: round((now - t) / 60.0, 2) for k, t in updated.items()}
        ready = bool(state.get("quotes"))
        snap = {
            "ok": ready,
            "built_utc": datetime.now(UTC).isoformat(),
            "started_utc": self.started_utc,
            # The session clock takes the Fed calendar so its 14:00 marker can be a
            # real meeting rather than a daily assumption.
            "clock": session_state(fed=state.get("fed") or []),
            # Pure date arithmetic on the ET calendar, so it is computed on read
            # rather than polled — there is no upstream to be stale against.
            "expiry": expiry_state(),
            # Arithmetic on the board, like `expiry` — no upstream to be
            # stale against, so it is computed on read rather than polled.
            "volterm": {
                **volterm_state(state.get("quotes") or []),
                # Each book's one-sigma day in its own points, how much of it
                # today has used, and implied against realised — the same
                # arithmetic on the same board, plus the context closes and
                # GEXYGEN's band, both already in state.
                "books": implied_day(
                    state.get("quotes") or [], state.get("context") or [], state.get("gex") or {}
                ),
                # The VIX against its own month, for the header's popover.
                "vix_month": vix_month(state.get("context") or [], state.get("quotes") or []),
            },
            # The strip and the meeting schedule are both already in state, so
            # what each FOMC has priced into it is arithmetic on read — the
            # same standing as `volterm` and `expiry`.
            "policy_meetings": meetings_priced(
                state.get("rates") or {}, state.get("fomc") or []
            ),
            "status": status,
            "age_min": ages,
            **state,
        }
        # The driver board (drivers.py): arithmetic on the blocks above, so it
        # is computed on read like volterm and expiry. The scanner's session
        # says whether the cash-market reads may vote.
        try:
            snap["drivers"] = drivers.build(snap, self.scan.clock(datetime.now(UTC)).session)
        except (ValueError, TypeError, KeyError, ZeroDivisionError) as e:
            snap["drivers"] = {"books": {}, "error": f"{e.__class__.__name__}: {e}"}
        return snap

    def scanner_payload(self) -> dict[str, Any]:
        """The Scanner tab's whole read — technicals joined with the macro now."""
        with self._lock:
            scan = self._state.get("scanner") or {}
            parts = {k: self._state.get(k) for k in
                     ("quotes", "sectors", "calendar", "scan_earn", "wire", "scan_news",
                      "scan_sec", "context")}
            cons = self._state.get("constituents")
            st = self._status.get("scanner")
        watch = self.scan.watchlist()
        pinned = self.scan.pinned()
        pool_view = self.pool.view(pinned)
        promoted = {p["symbol"]: {k: p.get(k) for k in ("score", "reason", "at", "mark")}
                    for p in pool_view["promoted"]}
        clock = self.scan.clock(datetime.now(UTC))
        td = clock.trading_day
        closes = {s: [d.close for d in (self.scan.daily.get(s) or []) if d.day < td] for s in watch}
        daily = {s: list(self.scan.daily.get(s) or []) for s in watch}
        flow_ctx = {s: {"oi_prev": self.options.oi.prev(s, td),
                        "vol_hist": self.options.oi.volumes(s, td)} for s in watch}
        payload = scanner_build(
            scan,
            quotes=parts["quotes"] or [],
            sectors=parts["sectors"] or [],
            calendar=parts["calendar"] or [],
            earnings=parts["scan_earn"] or [],
            wire=parts["wire"] or [],
            news=parts["scan_news"] or {},
            filings=parts["scan_sec"] or {},
            aliases={s: self.scan.aliases(s) for s in watch},
            status=st.as_dict() if st else None,
            watchlist=watch,
            clock=clock,
            options=self.options.view(),
            closes=closes,
            iv_hist={sym: self.options.history.series(sym) for sym in watch},
            premkt=self.premarket.view(td),
            sector_map=scan_src.SECTOR,
            daily=daily,
            shorts=self.shorts.view(),
            earn_hist=self.earnhist.view(),
            earn_next=self.earnhist.view_next(),
            flow_ctx=flow_ctx,
            context=parts["context"] or [],
            # The tape count is computed inside the build now (the tape penalty
            # reads it), from the constituents; the record line reads the log.
            constituents=cons if isinstance(cons, dict) else None,
            record=self.events.record_table(),
            promoted=promoted,
            pool=pool_view,
            pinned=pinned,
        )
        return payload

    def market_payload(self) -> dict[str, Any]:
        """The Market tab's context (marketctx.build) — computed on read, like the
        Scanner, from the scanner payload and the snapshot keys it reads."""
        scan = self.scanner_payload()
        with self._lock:
            snap: dict[str, Any] = {k: self._state.get(k) for k in (
                "quotes", "sectors", "constituents", "calendar", "rates", "fomc", "gex")}
            snap["status"] = {k: v.as_dict() for k, v in self._status.items()}
        snap["policy_meetings"] = meetings_priced(snap["rates"] or {}, snap["fomc"] or [])
        return marketctx.build(scan, snap)


COLLECTOR = Collector()
