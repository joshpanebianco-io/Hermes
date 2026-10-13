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

import threading
import time
import traceback
from collections.abc import Callable
from datetime import UTC, datetime
from typing import Any
from zoneinfo import ZoneInfo

from . import config
from . import scan as scan_mod
from .expiry import state as expiry_state
from .http import CACHE, SourceStatus
from .policy import meetings_priced
from .scanlog import EventLog
from .scanscore import build as scanner_build
from .sessions import session_state
from .sources import auctions as auc_src
from .sources import calendar as cal_src
from .sources import constituents as cons_src
from .sources import earnings as earn_src
from .sources import fedcal as fed_src
from .sources import gex as gex_src
from .sources import profiles as prof_src
from .sources import quotes as quotes_src
from .sources import ranges as ranges_src
from .sources import rates as rates_src
from .sources import scanner as scan_src
from .sources import wire as wire_src
from .volterm import state as volterm_state

ET = ZoneInfo("America/New_York")

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


class Collector:
    """Holds the terminal's whole state and refreshes it on schedule."""

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._stop = threading.Event()
        self._thread: threading.Thread | None = None
        self.started_utc = datetime.now(UTC).isoformat()

        # block name → (fn, interval_sec, next_due_monotonic)
        self._jobs: dict[str, tuple[Callable[[], None], float, float]] = {}
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
        }
        self.scan = scan_src.ScanStore()
        # The scanner's event log (scanlog.py): the alerts' feed and the record
        # each signal's outcome is kept in. Loaded from disk so ids keep counting.
        self.events = EventLog()
        self._status: dict[str, SourceStatus] = {}
        self._updated: dict[str, float] = {}
        self._logged_header = False
        self._log_lock = threading.Lock()
        self._scan_thread: threading.Thread | None = None
        self._quotes_thread: threading.Thread | None = None

        now = time.monotonic()
        # The board, on a thread of its own (module docstring): it is the block
        # every other panel is read against, and a board with no prices is not
        # a terminal.
        self._quote_jobs: dict[str, tuple[Callable[[], None], float, float]] = {
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
        }
        # The scanner's own thread runs these (see the module docstring). Each
        # rotates its names inside a tick — sources/scanner.py has the budget.
        self._scan_jobs: dict[str, tuple[Callable[[], None], float, float]] = {
            "scanner": (self._do_scanner, scan_src.TICK_SEC, now + 1.0),
            "scan_news": (self._do_scan_news, 60.0, now + 6.0),
            "scan_sec": (self._do_scan_sec, 60.0, now + 9.0),
        }

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

    def _do_scanner(self) -> None:
        st = self.scan.tick_bars()
        self._commit("scanner", self.scan.compute(), st)
        # The log reads the SCORED payload, so each event carries the score its
        # row had at the moment it fired — what the outcomes are judged against.
        # Its failure is its own: a log that cannot be written must not mark the
        # scanner itself as down.
        try:
            self.events.observe(self.scanner_payload(), dict(self.scan.bars))
        except Exception as e:  # noqa: BLE001 — see module docstring
            st_ev = SourceStatus("Scanner events")
            st_ev.error = f"{e.__class__.__name__}: {e}"
            self._log("scan_events", st_ev)
            traceback.print_exc()

    def scanner_bars(self, sym: str) -> dict[str, Any]:
        """One name's mini-chart series (scan.chart_series) off the bars held."""
        sym = sym.strip().upper()
        if sym not in self.scan.symbols():
            return {"ok": False, "sym": sym, "error": "not on the watchlist"}
        bars = self.scan.bars.get(sym)
        if not bars:
            return {"ok": False, "sym": sym, "error": "no bars yet"}
        clock = self.scan.clock(datetime.now(UTC))
        tech = scan_mod.technicals(bars, self.scan.daily.get(sym) or [], clock,
                                   official=scan_mod.official_close(self.scan.meta.get(sym)))
        out = scan_mod.chart_series(bars, clock, tech)
        out["sym"] = sym
        return out

    def _do_scan_news(self) -> None:
        st = self.scan.tick_news()
        self._commit("scan_news", dict(self.scan.news), st)

    def _do_scan_sec(self) -> None:
        st = self.scan.tick_sec()
        self._commit("scan_sec", dict(self.scan.filings), st)

    def set_watchlist(self, symbols: list[str]) -> tuple[list[str], list[str]]:
        """Save the scanner's list and make the new names the next thing fetched.

        Called from the API thread. Only the job clocks are touched here — the
        fetching itself stays on the collector thread, where every other
        upstream call lives.
        """
        ok, bad = self.scan.set_watchlist(symbols)
        now = time.monotonic()
        for jobs, name in ((self._scan_jobs, "scanner"), (self._scan_jobs, "scan_news"),
                           (self._scan_jobs, "scan_sec"), (self._jobs, "earnings")):
            fn, interval, _due = jobs[name]
            jobs[name] = (fn, interval, now)
        return ok, bad

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

    def _run_one(self, jobs: dict[str, tuple[Callable[[], None], float, float]]) -> bool:
        """Run the FIRST due job in `jobs`, if any. True when one ran.

        One job, then back to the top: the dict is in priority order, so a
        quotes tick that falls due while the wire is fetching runs next, not
        after everything else that was due in the same pass.
        """
        now = time.monotonic()
        for name, (fn, interval, due) in list(jobs.items()):
            if now < due:
                continue
            try:
                fn()
            except Exception as e:  # noqa: BLE001 — see module docstring
                st = SourceStatus(name)
                st.error = f"{e.__class__.__name__}: {e}"
                self._status[name] = st
                self._log(name, st)
                traceback.print_exc()
            jobs[name] = (fn, interval, time.monotonic() + interval)
            return True
        return False

    def _run(self, jobs: dict[str, tuple[Callable[[], None], float, float]] | None = None,
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
        gone = CACHE.prune(7 * 86400.0, keep=("scanner_watchlist.json", "scanner_events.jsonl"))
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

    def stop(self) -> None:
        self._stop.set()
        for th in (self._thread, self._scan_thread, self._quotes_thread):
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
        return {
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
            "volterm": volterm_state(state.get("quotes") or []),
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


    def scanner_payload(self) -> dict[str, Any]:
        """The Scanner tab's whole read — technicals joined with the macro now."""
        with self._lock:
            scan = self._state.get("scanner") or {}
            parts = {k: self._state.get(k) for k in
                     ("quotes", "sectors", "calendar", "scan_earn", "wire", "scan_news",
                      "scan_sec")}
            st = self._status.get("scanner")
        watch = self.scan.watchlist()
        return scanner_build(
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
            clock=self.scan.clock(datetime.now(UTC)),
        )


COLLECTOR = Collector()
