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
import json
import os
import statistics
import sys
import threading
import time
import traceback
import urllib.parse
from collections.abc import Callable
from datetime import UTC, date, datetime, timedelta
from typing import Any
from zoneinfo import ZoneInfo

from . import (
    bias_record,
    config,
    daytype,
    drivers,
    drivestats,
    futfill,
    marketctx,
    newsread,
    premarket_record,
    structure,
)
from . import dashboard as dash_mod
from . import futures as fut_mod
from . import momentum as mom_mod
from . import report as report_mod
from . import rotation as rot_mod
from . import scan as scan_mod
from . import today as today_mod
from . import volterm as volterm_mod
from .config import BROWSER_UA
from .expiry import state as expiry_state
from .holidays import early_close, is_trading_day, prev_trading_day
from .holidays import notices as holiday_notices
from .http import CACHE, SourceStatus, fetch, json_body
from .policy import meetings_priced
from .scanlog import EventLog
from .scanscore import build as scanner_build
from .scanscore import day_move_of, earnings_for, names_of, next_report
from .sessions import globex_trade_date, session_state
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
from .sources import holdings as hold_src
from .sources import official as off_src
from .sources import options as opt_src
from .sources import pool as pool_src
from .sources import premarket as pre_src
from .sources import profiles as prof_src
from .sources import quotes as quotes_src
from .sources import ranges as ranges_src
from .sources import rates as rates_src
from .sources import scanner as scan_src
from .sources import shortint as short_src
from .sources import stream as stream_src
from .sources import tvnews as tvnews_src
from .sources import tvstory as tvstory_src
from .sources import universe as uni_src
from .sources import webull as webull_src
from .sources import wire as wire_src
from .volterm import BOOK_DP, implied_day, vix_month
from .volterm import state as volterm_state

ET = ZoneInfo("America/New_York")

#: The oldest copy of the scanner's bars a spark is drawn from (`_held_spark`): past it
#: the spark read (uni_src.SPARK_TTL, four minutes) is the fresher. The rotation reads a
#: tracked name every ninety seconds in a session and every fifteen minutes when closed.
HELD_SPARK_SEC = 240.0
HELD_SPARK_IDLE_SEC = 1800.0

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


def market_holidays(today: date | None = None) -> list[dict[str, object]]:
    """Yesterday through three weeks out, on New York's calendar."""
    day = today or datetime.now(ET).date()
    return holiday_notices(day - timedelta(days=1), day + timedelta(days=21))


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
            "themes": [], "breadth_all": None,
            # The agencies' own figures for the US releases (sources/official.py):
            # by key here, and on the calendar rows they are the prints of.
            "official": {},
        }
        # The benchmarks and the MAG 7 are on the list always (scanner.CORE, 2026-11-13).
        self.scan = scan_src.ScanStore(core=scan_src.CORE)
        # The bars job and the live job both rebuild the scanner block; one at a
        # time, so a build from older bars can never land after a newer one.
        self._scan_build_lock = threading.Lock()
        self._live_logged = 0.0
        #: The one-off rework of the signal record on the floored stop has run.
        self._refloored = False
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
        # The wide scan (sources/universe.py), the ticker-tagged news it is read
        # with, the Day 1/2/3 ledger written from it, and the live stream that
        # watches the best of what it finds.
        self.stream = stream_src.PriceStream()
        self.scan.stream = self.stream
        # Webull's trades into the same books, for the same names, while the feed switch
        # says "webull" (webull_src.feed_mode); Yahoo's socket runs beside it either way.
        self.webull = webull_src.WebullFeed(self.stream.put, self._webull_wanted)
        self.stock_news = tvnews_src.NewsStore()
        self.stock_news.names = self._called
        # Only the table's names are held against a headline that does not carry them
        # (catalysts.story): a filer's first word is a guess at what the wire writes.
        self.stock_news.sure = scan_src.ALIASES.__contains__
        # A story that states a move is held to the name's real one (catalysts.STATED_MIN).
        self.stock_news.move = self._day_move
        # What the model made of each name's major story (newsread.py): how big, never
        # score; and since 2026-11-18 which way, for the flag and the tie-break. Asked for
        # by a clock in api.py, with each story's own text (sources/tvstory.py).
        self.newsread = newsread.ReadStore()
        self.story_text = tvstory_src.StoryText()
        self.universe = uni_src.UniverseStore()
        # The scanner's pre-market range is checked against these two reads, which
        # are not Yahoo's bars (`_pm_range`; scan.technicals says why).
        self.scan.pm_hint = self._pm_range
        # A spark off the bars the slide-out chart draws, where the scanner holds them.
        self.universe.held_spark = self._held_spark
        # The rest end on the stream's latest trade, as the chart's last candle does.
        self.universe.live_trade = self.stream.last_trade
        self.holdings = hold_src.HoldingsStore()
        self.momentum = mom_mod.MomentumStore()
        #: The Today list (today.py): when each name first reached the top ten of the
        #: phase now showing (keyed by phase and day), and which phases' lists are logged.
        self._today_seen: dict[str, dict[str, float]] = {}
        self._today_logged: set[str] = set()
        self._today_lock = threading.Lock()
        #: Each futures book's ETF fill as last measured, and when (`_fut_fill`).
        self._fut_fills: dict[str, tuple[float, tuple[float, int, list[scan_mod.Bar]] | None]] = {}
        #: The Today list's names as last drawn, for the SEC job's insider reads (`_sec_extra`).
        self._today_syms: list[str] = []
        #: The Today list as last built: its phase key, when (monotonic), and its rows by
        #: symbol, so the slide-out shows the score the list shows (`_as_listed`).
        self._today_last: tuple[str, float, dict[str, dict[str, Any]]] | None = None
        #: The pre-market record's after-the-bell work (premarket_record.py): when it last
        #: ran, the names worked so far for each owed day, and the tries of each.
        self._pre_outcome_at = 0.0
        self._pre_progress: dict[str, dict[str, dict[str, Any]]] = {}
        self._pre_tries: dict[tuple[str, str], int] = {}
        self.scan.sec_extra = self._sec_extra
        self.pool.core = self.scan.core
        self.pool.news = self.stock_news.major
        self.pool.stage = self._strong
        # Whether the pool's pre-market columns are today's, and today's pre-market range
        # for an outside day after the open (pool.fresh_premarket, pool.outside_both).
        self.pool.pm_seen = self.universe.pm_traded
        self.pool.pm_range = self._pm_range
        # The session-type record (daytype.py): a card per book before the bell,
        # its label after the close. Loaded so a restart keeps the day's marks.
        # The backfill's rows beside it are the record's larger half, and the
        # base-rate tables over both are built once and kept until a label lands.
        self.daytypes = daytype.SessionLog()
        #: The bias record's (td, mark) pairs and closed days on file, read on its first tick.
        self._bias_done: tuple[set[tuple[str, str]], set[str]] | None = None
        self._dt_record = daytype.load_backfill()
        self._dt_tables: dict[str, dict[str, Any]] = {}
        self._dt_meta: dict[str, Any] = {}
        self._dt_key: tuple[int, int] = (-1, -1)
        self._dt_lock = threading.Lock()

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
            # The agencies' own figures. A minute between ticks: each agency is
            # asked only when its copy on disk has aged out (six hours for the BLS,
            # fifteen minutes for the rest), and often only while a release is due.
            "official": (self._do_official, 60.0, now + 9.0),
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
            # The live rotation (rotation.py): a round a minute in the session, the pool's
            # picks swapped for better setups off the list. On this thread because its
            # reads are the bars job's kind and share its 429 pause.
            "rotation": (self._do_rotation, rot_mod.ROUND_SEC, now + 20.0),
        }
        #: Names off the list the owner opened (the slide-out, Hermes's selected name), and
        #: when: candidates for the rotation for rot_mod.OPENED_SEC.
        self._opened: dict[str, float] = {}
        #: How many rounds in a row each candidate has qualified (rotation.decide).
        self._rot_streak: dict[str, int] = {}
        self._rot_logged = 0.0
        #: The session whose rotation outcome line is written (or had nothing to write).
        self._rot_outcome_day: str | None = None
        # The chains, on their own thread (module docstring); one per tick.
        self._option_jobs: dict[str, Job] = {
            "options": (self._do_options, opt_src.TICK_SEC, now + 3.0),
        }
        # Nasdaq's pre-market, on a thread of its own: its API can hang for the
        # whole timeout, and that must not hold up a chain or a quote.
        self._premarket_jobs: dict[str, Job] = {
            "premarket": (self._do_premarket, pre_src.TICK_SEC, now + 5.0),
            # Each name's report dates: the past ones off the scanner's EDGAR read,
            # the next from one TradingView POST every few hours (sources/earnhist.py).
            "scan_earnhist": (self._do_earnhist, eh_src.TICK_SEC, now + 7.5),
            # The pool: one POST to TradingView's screener every five minutes
            # in the morning, half-hourly otherwise; the tick is short so a
            # mark (08:00, 09:00, 09:25, 10:00 ET) is met within seconds.
            "pool": (self._do_pool, pool_src.TICK_SEC, now + 4.0),
            # The session-type record (daytype.py): a card at 09:25 ET, its label
            # after the close. The same short tick, so a mark is met in seconds.
            "daytype": (self._do_daytype, 20.0, now + 8.0),
            # The bias record (bias_record.py): every board read at its marks and each
            # book's price at the close, to test the weights against what followed.
            "bias_record": (self._do_bias_record, 20.0, now + 12.0),
        }
        # The live layer, alone (module docstring); it paces itself.
        self._live_jobs: dict[str, Job] = {
            "scan_live": (self._do_live, scan_src.LIVE_SEC, now + 2.0),
        }
        self._live_thread: threading.Thread | None = None
        # The wide read and everything hung off it, on a thread of their own: a
        # 2 MB reply and the per-name news reads must not hold up a chain or a bar.
        self._wide_jobs: dict[str, Job] = {
            "stream": (self._do_stream, 15.0, now + 1.5),
            "universe": (self._do_universe, uni_src.TICK_SEC, now + 5.0),
            "stock_news": (self._do_stock_news, 20.0, now + 6.5),
            "themes": (self._do_themes, config.QUOTES_SEC * 15, now + 9.0),
            # The funds' extended hours for the Sectors cards (quotes.collect_extended):
            # every minute while they can trade outside the session, else every 15.
            "sector_ext": (self._do_sector_ext, 60.0, now + 10.0),
            "holdings": (self._do_holdings, hold_src.TICK_SEC, now + 2.5),
            "sparks": (self._do_sparks, uni_src.SPARK_TICK_SEC, now + 12.0),
            "stock_news_sym": (self._do_stock_news_sym, tvnews_src.SYM_TICK_SEC, now + 30.0),
        }
        self._wide_thread: threading.Thread | None = None
        self._stream_logged = 0.0
        self._webull_logged = 0.0
        self._stream_checked = 0.0

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

    def _do_sectors(self) -> float | None:
        """The sector funds: each minute in the regular session (owner, 2026-11-16: "do
        what you recommend", to reading them each minute where it was five), at the
        job's own five minutes outside it, where the extended read has them."""
        rows, st = quotes_src.collect_sectors()
        self._commit("sectors", rows if st.ok else None, st)
        return 60.0 if quotes_src.regular_now() else None

    def _do_themes(self) -> float | None:
        """The theme funds, on the sector funds' clock (`_do_sectors`)."""
        rows, st = quotes_src.collect_themes()
        self._commit("themes", rows if st.ok else None, st)
        return 60.0 if quotes_src.regular_now() else None

    def _do_sector_ext(self) -> float:
        """The sector and theme funds' last trades outside the session, for the Sectors
        cards (owner, 2026-11-16: "make the app update as to what they're actually
        doing"). A minute apart while they can trade before the bell or after the close,
        fifteen otherwise: overnight the after-hours read is final."""
        rows, st = quotes_src.collect_extended()
        self._commit("sector_ext", rows if st.ok else None, st)
        return 60.0 if quotes_src.extended_now() else 900.0

    def _do_holdings(self) -> None:
        """One fund's list when one is due; the table of who is in what, every tick."""
        st, read = self.holdings.tick()
        self.universe.members = self.holdings.members()
        if read or "holdings" not in self._status:
            self._commit("holdings", None, st)

    def _do_stream(self) -> None:
        """Tell the stream what to listen to, keep its health on the rail, and
        once a minute score it against the bars (stream.StreamCheck)."""
        self.stream.set_targets("tracked", self.scan.symbols())
        st = self.stream.status()
        with self._lock:
            self._status["stream"] = st
            if st.ok:
                self._updated["stream"] = time.time()
        now = time.monotonic()
        if now - self._stream_checked >= 60.0:
            self._stream_checked = now
            self.stream.run_check(dict(self.scan.bars), dict(self.scan.fetched))
        if not st.ok or now - self._stream_logged >= 300.0:
            self._stream_logged = now
            self._log("stream", st)
        # The feed switch, read again each tick: a change in the app or the file applies
        # within seconds, no restart.
        feed, _why = webull_src.feed_mode()
        if feed == "webull" and not self.webull.running():
            self.webull.start()
        elif feed != "webull" and self.webull.running():
            self.webull.stop()
        if feed == "webull":
            wst = self.webull.status()
            with self._lock:
                self._status["webull"] = wst
                if wst.ok:
                    self._updated["webull"] = time.time()
            if not wst.ok or now - self._webull_logged >= 300.0:
                self._webull_logged = now
                self._log("webull", wst)
        else:
            with self._lock:
                self._status.pop("webull", None)

    def _do_universe(self) -> None:
        st, read = self.universe.tick()
        if not read:
            return
        now = datetime.now(UTC)
        basis = uni_src.basis_at(now)
        et = now.astimezone(ET)
        # Once a session, from the first read whose bar is final: the delayed
        # feed has the close by 16:15, and the auction's print a little after.
        final = basis == "last" or (basis == "post" and
                                    et.hour * 60 + et.minute >= scan_mod.rth_end(et.date()) + 30)
        if final and self.universe.rows:
            self.momentum.update(self.universe.rows, uni_src.session_day(now))
        cands = self.universe.candidates(extra=self.momentum.names())
        self.stream.set_targets("candidates", cands)
        self.stock_news.want(cands[:80])
        breadth = SourceStatus("Breadth (wide)")
        data = self.universe.breadth(now)
        breadth.items = (data or {}).get("names", 0)
        breadth.ok, breadth.source = bool(data), "live" if data else "unavailable"
        with self._lock:
            self._state["breadth_all"] = data
            if data:
                self._updated["breadth_all"] = time.time()
        self._commit("universe", None, st)

    def _do_stock_news(self) -> None:
        on = uni_src.basis_at(datetime.now(UTC)) != "last"
        st, read = self.stock_news.tick_flow(on)
        if read:
            self._commit("stock_news", None, st)

    def _do_stock_news_sym(self) -> None:
        self.stock_news.tick_symbol(self.universe.exchanges())

    def _do_sparks(self) -> None:
        self.universe.tick_sparks()

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
        names = [s for s in self.scan.watchlist() if s not in scan_src.BENCHMARKS]
        st = self.earnhist.tick(names, dict(self.scan.reports))
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
        # Two weeks ahead since 2026-11-16 (a week before that, three days before that,
        # which on a Friday ended on Monday): the days past the third thinned to what
        # reaches the books, the week after to its big releases (calendar.thin_far).
        # And back to the week's Monday (2026-11-19, calendar.DAYS_BACK), the days before
        # yesterday thinned to the prints that stop the tape (calendar.thin_past): the
        # market report's "earlier this week".
        rows, st = cal_src.collect(days_ahead=cal_src.DAYS_AHEAD, days_back=cal_src.DAYS_BACK)
        # TradingView's calendar, read while Nasdaq is refusing, lists no speeches:
        # the Board's own (the "fed" source) join its rows (sources/calendar.py).
        if st.ok:
            with self._lock:
                fed = list(self._state.get("fed") or [])
                figs = dict(self._state.get("official") or {})
            today = datetime.now(ET).date()
            rows = cal_src.thin_past(cal_src.thin_far(cal_src.with_fed_speeches(rows, fed), today),
                                     today)
            # And the agencies' own figures on the rows they are the prints of: a
            # fresh read of the feed would otherwise print the feed's copy again.
            rows = off_src.apply(rows, figs)
            st.items = len(rows)
        self._commit("calendar", rows if st.ok else None, st)

    def _do_official(self) -> None:
        with self._lock:
            held = list(self._state.get("calendar") or [])
        figs, st = off_src.collect(held)
        self._commit("official", figs if st.ok else None, st)
        if not st.ok:
            return
        # On the calendar now, not at its next read ten minutes on. `apply` makes
        # a new row where one changes, so a reader holding the old list is not
        # handed a row that changes under it.
        with self._lock:
            now_held = self._state.get("calendar")
            if isinstance(now_held, list):
                self._state["calendar"] = off_src.apply(now_held, figs)

    def _do_rates(self) -> None:
        data, st = rates_src.collect()
        self._commit("rates", data if st.ok else None, st)

    def _do_ranges(self) -> None:
        data, st = ranges_src.collect()
        self._commit("ranges", data if st.ok else None, st)

    def _do_earnings(self) -> None:
        # Every $2bn+ name the wide scan holds is kept as well as the list (2026-11-13):
        # the Today list's evening reads who reports before the next open, whatever its
        # size. The panel still shows $50bn and up; the rest are `watch_only`.
        wide = frozenset(r["sym"] for r in self.universe.rows
                         if (r.get("cap") or 0) >= pool_src.MIN_CAP)
        rows, st = earn_src.collect(keep=frozenset(self.scan.watchlist()) | wide)
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
            # Once a start: the signals settled before the stop had a floor, worked
            # again from whatever bars are still held (scanlog.EventLog.refloor).
            if not self._refloored:
                self._refloored = True
                done = self.events.refloor(self._held_bars)
                if done["seen"]:
                    st_rf = SourceStatus("Signal record")
                    st_rf.ok, st_rf.source, st_rf.items = True, "live", done["ruled"]
                    st_rf.notes = [f"stop floor: {done['ruled']} of {done['seen']} settled signals "
                                   f"read by it, {done['floored']} moved, {done['skipped']} left "
                                   "as they were (bars gone)"]
                    self._log("scan_events", st_rf)
            # A finished day's signals, settled once against bars read after its
            # bell (scanlog's "second look"). Cheap when there is nothing to do:
            # only names with unchecked events and a post-bell download replay.
            owed = self.events.unchecked(str(payload.get("trading_day") or ""))
            # A name that left the list during its day is read once more, after the
            # bell, so its signals settle like any other's (ScanStore.read_owed).
            read = self.scan.read_owed(owed)
            if read:
                st_ow = SourceStatus("Signal record")
                st_ow.ok, st_ow.source, st_ow.items = True, "live", len(read)
                st_ow.notes = [f"read to settle a finished day: {', '.join(read)} "
                               "(off the list before its bell)"]
                self._log("scan_events", st_ow)
            quiet = self.scan.unwatched()
            for day, syms in owed.items():
                # Every chart's signals (3m, 5m, 10m), each settled on its own bars.
                got = self.scan.day_signals(date.fromisoformat(day), syms, fast=True)
                if got:
                    self.events.settle(day, got, known_only=quiet)
            # The pre-market record's finished days, held to what their names did.
            self._premarket_outcomes()
        except Exception as e:  # noqa: BLE001 — see module docstring
            st_ev = SourceStatus("Scanner events")
            st_ev.error = f"{e.__class__.__name__}: {e}"
            self._log("scan_events", st_ev)
            traceback.print_exc()
        # Soon while a close read is unfinished, on time for the next one.
        return self.scan.wake_in()

    def _held_bars(self, sym: str) -> list[scan_mod.Bar] | None:
        """A name's 5-minute bars as far back as anything here holds them: the
        scanner's own for a name on the list, else the last download left on disk
        from the day it was tracked. No fetch."""
        bars = self.scan.bars.get(sym)
        if bars:
            return bars
        blob = CACHE.read(f"scan5m_{sym}")
        if blob is None:
            return None
        try:
            return scan_mod.parse_chart(json.loads(blob))[0] or None
        except (ValueError, TypeError, KeyError):
            return None

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

    def futures_bars(self, book: str, tf: str = "10m") -> dict[str, Any]:
        """One futures book's chart (futures.series): the contract's own bars from
        Yahoo, cached a few seconds, and the levels from the live ladder."""
        book = book.strip().upper()
        sym = fut_mod.SYMBOL.get(book)
        if sym is None or tf not in fut_mod.SOURCE:
            return {"ok": False, "sym": book, "tf": tf, "error": "not a futures book or view"}
        iv, rng = fut_mod.SOURCE[tf]
        ttl = 20.0 if iv == "1m" else 600.0 if iv == "1d" else 45.0
        r = fetch(fut_mod.CHART.format(sym=urllib.parse.quote(sym), rng=rng, iv=iv),
                  key=f"fut_{book}_{iv}_{rng}", ttl_sec=ttl, ua=BROWSER_UA, timeout=12,
                  stale_max_sec=1800.0, validate=json_body)
        if not r.ok:
            return {"ok": False, "sym": book, "tf": tf, "error": r.error or "no bars"}
        try:
            bars = fut_mod.parse(r.json())
        except (ValueError, TypeError):
            bars = []
        now = datetime.now(UTC)
        # THE LAST TEN MINUTES FROM THE ETF (futfill.py): CME's bars run ten minutes
        # behind; the ETF's minutes since the future's last one, in the future's prices.
        got = self._fut_fill(book) if tf != "D" and bars else None
        extra = futfill.fill(got[1], got[2], got[0], int(now.timestamp())) if got else []
        if extra:
            bars = [*bars, *(b for b in extra if b.t > bars[-1].t)]
        ladder = report_mod.live_ladder(self.snapshot(), book)
        out = fut_mod.series(bars, tf, now, ladder, book)
        if got is not None:
            out["filled"] = {"proxy": futfill.PROXY[book], "bars": len(extra), "from": got[1],
                             "ratio": round(got[0], 6)}
        return out

    def _fut_fill(self, book: str) -> tuple[float, int, list[scan_mod.Bar]] | None:
        """(future ÷ its ETF, the future's last minute, the ETF's one-minute bars) for a
        book, or None when either has no bars or they share no minute (futfill.py). Held
        ten seconds: an open chart asks every second."""
        now = time.monotonic()
        held = self._fut_fills.get(book)
        if held is not None and now - held[0] < 10.0:
            return held[1]
        etf, sym = futfill.PROXY.get(book), fut_mod.SYMBOL.get(book)
        if etf is None or sym is None:
            return None

        def minutes(s: str, key: str) -> list[scan_mod.Bar]:
            r = fetch(fut_mod.CHART.format(sym=urllib.parse.quote(s), rng="1d", iv="1m"), key=key,
                      ttl_sec=15.0, ua=BROWSER_UA, timeout=12, stale_max_sec=300.0,
                      validate=json_body)
            if not r.ok:
                return []
            try:
                return fut_mod.parse(r.json())
            except (ValueError, TypeError):
                return []

        fut1, etf1 = minutes(sym, f"fut_{book}_1m_1d"), minutes(etf, f"etf1m_{etf}")
        r = futfill.ratio(fut1, etf1)
        got = (r[0], fut1[-1].t, etf1) if r is not None and fut1 else None
        self._fut_fills[book] = (now, got)
        return got

    def futures_tick(self, book: str) -> dict[str, Any]:
        """What an open futures chart asks for every second: the ETF's last trade in the
        future's prices (futfill.scaled_tick), between 04:00 and 17:00 ET. Asking keeps
        the ETF subscribed."""
        book = book.strip().upper()
        clock = self.scan.clock(datetime.now(UTC))
        etf = futfill.PROXY.get(book)
        none = {"ok": False, "sym": book, "clock_session": clock.session,
                "connected": self.stream.connected}
        if etf is None:
            return none
        self.stream.touch(etf)
        got = self._fut_fill(book)
        if got is None:
            return none
        spark = self.scan.live.get(etf) if clock.session == "rth" else None
        q = stream_src.chart_tick(self.stream.quote(etf),
                                  (spark.price, float(spark.at)) if spark is not None else None)
        # No stream trade for the ETF, or one older than its newest minute bar: the bar.
        newest = got[2][-1] if got[2] else None
        if newest is not None and (q is None or "price" not in q
                                   or float(q.get("at") or 0.0) < newest.t):
            q = futfill.bar_quote(newest, time.time())
        t = futfill.scaled_tick(q, got[0], book, etf)
        if t is None:
            return none
        t.pop("overnight", None)
        return {**none, **t, "ok": True, "age_sec": round(time.time() - float(t["at"]), 1)}

    def scanner_bars(self, sym: str, tf: str = "10m") -> dict[str, Any]:
        """One name's mini-chart series (scan.chart_series) off the bars held —
        plus, for the 1m and 3m views, a one-minute download made here, on the
        request (ScannerStore.bars_1m)."""
        sym = sym.strip().upper()
        if sym not in self.scan.symbols():
            # A chart opened from the wide scan or the search: read it now.
            err = self.scan.ensure_adhoc(sym)
            if err:
                return {"ok": False, "sym": sym, "tf": tf, "error": err}
        clock = self.scan.clock(datetime.now(UTC))
        # The live trade on the last candle too, so the chart's price agrees
        # with the row beside it.
        bars = self.scan.live_bars(sym, clock)
        if not bars:
            return {"ok": False, "sym": sym, "tf": tf, "error": "no bars yet"}
        daily = self.scan.daily.get(sym) or []
        # Confirmed by the download, as on the row (scan.CLOSE_LAG_SEC) — a chart
        # marking a signal the row does not have would be its own phantom.
        # The one-minute bars the ROW's 3m signals were read on, not the chart's own
        # download below, so the chart marks exactly the signals the row has.
        tech = scan_mod.technicals(bars, daily, clock,
                                   official=scan_mod.official_close(self.scan.meta.get(sym)),
                                   asof=self.scan.fetched.get(sym),
                                   daily_asof=self.scan.daily_at.get(sym),
                                   pm_wide=self.scan.pm_wide(sym, clock.trading_day),
                                   bars1=self.scan.bars1.get(sym),
                                   asof1=self.scan.fetched1.get(sym))
        bars1: list[scan_mod.Bar] | None = None
        if scan_mod.CHART_TF.get(tf, 600) < 300:
            bars1, err = self.scan.bars_1m(sym)
            if not bars1:
                return {"ok": False, "sym": sym, "tf": tf, "error": err or "no one-minute bars"}
        out = scan_mod.chart_series(bars, clock, tech, tf, bars1=bars1, daily=daily,
                                    daily_asof=self.scan.daily_at.get(sym))
        out["sym"] = sym
        return out

    def scanner_tick(self, sym: str) -> dict[str, Any]:
        """What an open chart asks for every second: the last trade and this
        minute's candle, off the stream, or the spark layer's trade when that is
        the newer of the two or the stream has none (stream.chart_tick). Asking
        keeps the name subscribed."""
        sym = sym.strip().upper()
        self.stream.touch(sym)
        now = time.time()
        clock = self.scan.clock(datetime.now(UTC))
        spark = self.scan.live.get(sym) if clock.session == "rth" else None
        q = stream_src.chart_tick(self.stream.quote(sym),
                                  (spark.price, float(spark.at)) if spark is not None else None)
        if q is None:
            return {"ok": False, "sym": sym, "clock_session": clock.session,
                    "connected": self.stream.connected}
        at = q.get("at")
        return {"ok": "price" in q, "sym": sym, "connected": self.stream.connected,
                "clock_session": clock.session, "via": q.get("via", "stream"), **q,
                "age_sec": round(now - float(at), 1) if at else None}

    def scanner_name(self, sym: str) -> dict[str, Any]:
        """One whole row for the slide-out: a tracked name's as the table has it,
        any other's built here on request from a chart read and the same join."""
        sym = sym.strip().upper()
        watch = self.scan.watchlist()
        tracked = sym in watch or sym in self.scan.symbols()
        err: str | None = None
        raw = self.universe.raw(sym)
        if not tracked:
            err = self.scan.ensure_adhoc(sym)
            # Opened by the owner: a candidate for the live rotation for the next hour.
            if err is None:
                self._opened[sym] = time.time()
        names = [sym] if not tracked else None
        sector = raw["sector"] if raw else None
        extra = None
        if not tracked and err is None:
            one = self.scan.compute_one(sym, sector=sector)
            if one is None:
                err = "no bars for this name"
            else:
                extra = {sym: one}
        payload = self._payload(watch=names, extra_rows=extra, news_limit=None)
        row = next((r for r in payload.get("rows") or [] if r.get("sym") == sym), None)
        if row is not None and raw is not None:
            row["float_shares"] = raw.get("float")
            row["market_cap"] = raw.get("cap")
            row["industry"] = raw.get("industry")
            if not row.get("name"):
                row["name"] = raw.get("name")
        if row is not None and row.get("ok"):
            row = self._as_listed(sym, row, raw, datetime.now(UTC))
            self._story_read(row)
        stages = self._ctx().stage
        pinned = self.scan.pinned()
        return {"ok": row is not None and bool(row.get("ok")), "sym": sym, "row": row,
                "error": err or (None if row else "no data for this name"),
                "tracked": tracked, "pinned": sym in pinned,
                "session": payload.get("session"), "trading_day": payload.get("trading_day"),
                "stage": stages.get(sym)}

    #: How old the Today list may be before the slide-out builds it again for a score.
    TODAY_HOLD_SEC = 60.0

    def _as_listed(self, sym: str, row: dict[str, Any], wide: dict[str, Any] | None,
                   now: datetime) -> dict[str, Any]:
        """ONE SCORE: THE SLIDE-OUT'S IS THE LIST'S (owner, 2026-11-18: "i just need it
        intuitive ... before market open see what are gonna be potentially the best stocks
        to trade and then as the session opens ... what is developing and looking like the
        best stocks to trade"). From the bell both are the engine's setup score and this
        changes nothing. Before it the Scanner ranks how in play a name is, and the
        slide-out showed the setup score beside it under the same word: at 02:20 ET that
        morning BILL was 79 in the table and 40 in the slide-out, and 25 of the 40 were
        the Entry part every name with a pre-market plan earns. So a name on the list
        takes its score and side as the list has them (today.scan_row on this row, the
        same call that draws a tracked name's table row); a name off it, its in-play read
        from the pool, as the tracked names under the ranking get theirs."""
        phase = today_mod.phase_at(now)
        if phase.key == "session":
            return row
        key = f"{phase.key}:{phase.day.isoformat()}"
        last = self._today_last
        if last is None or last[0] != key or time.monotonic() - last[1] > self.TODAY_HOLD_SEC:
            try:
                self.today(now)
            except Exception:  # noqa: BLE001 - the slide-out still draws, on the setup score
                traceback.print_exc()
                return row
            last = self._today_last
        t = (last[2] if last and last[0] == key else {}).get(sym)
        if t is None:
            t = today_mod.off_list(sym, self.pool.by_sym.get(sym))
        return today_mod.scan_row(t, row, phase.key, wide)

    def fill_story_text(self, cands: list[dict[str, Any]]) -> None:
        """Each story the model is about to read, with its own text where TradingView
        carries it (newsread.py, sources/tvstory.py): found by the id in its address, else
        by its headline among the stories held. Reads the ones not held yet (a few
        requests, on the model's clock). Never raises: a story without text is read on
        its headline as before."""
        try:
            ids = self.stock_news.ids_by_title(newsread.norm)
            by_url = self.stock_news.ids_by_url()
            want: dict[str, str] = {}
            for c in cands:
                url = str(c.get("url") or "")
                sid = (by_url.get(url) or tvstory_src.id_from_url(url)
                       or ids.get(newsread.norm(str(c.get("headline") or ""))))
                if sid:
                    want[c["key"]] = sid
            self.story_text.read(list(want.values()))
            for c in cands:
                sid = want.get(c["key"])
                c["text"] = (self.story_text.get(sid) or "") if sid else ""
        except Exception:  # noqa: BLE001 - the headline alone is still a read
            traceback.print_exc()

    def _story_read(self, row: dict[str, Any]) -> None:
        """A row with no read of its deciding story takes the read of its own story, the
        one the Scanner shows (a name the engine does not track has no catalyst part)."""
        if row.get("news_read"):
            return
        story = row.get("catalyst")
        if isinstance(story, dict) and story.get("title"):
            row["news_read"] = self.newsread.for_story(str(row.get("sym") or ""),
                                                       str(story["title"]))

    def _catalyst(self, sym: str) -> dict[str, Any] | None:
        return self.stock_news.catalyst(sym, ref=uni_src.news_anchor(datetime.now(UTC)))

    def _day_move(self, sym: str) -> float | None:
        """A name's move since the previous close (%): the Stocks list's own for a name it
        tracks (live bars), else the wide read's. With no session on, the wide pages show
        the last session, so its move is the one a story is held to."""
        now = datetime.now(UTC)
        if uni_src.basis_at(now) != "last":
            with self._lock:
                row = ((self._state.get("scanner") or {}).get("rows") or {}).get(sym)
            if isinstance(row, dict):
                mv = day_move_of(row)
                if mv is not None:
                    return mv
        return self.universe.day_move(sym, now)

    def _strong(self) -> dict[str, dict[str, Any]]:
        """The strong Day 2/3 tracks, for the pool's rank (momentum.strong)."""
        now = datetime.now(UTC)
        return self.momentum.strong(now.astimezone(ET).date(), uni_src.basis_at(now) != "last")

    def _called(self, sym: str) -> list[str]:
        """What a headline calls the company, for the news store's lead test."""
        return names_of(self.scan.aliases(sym), self.scan.own_names(sym))

    def _ctx(self) -> uni_src.Ctx:
        now = datetime.now(UTC)
        basis = uni_src.basis_at(now)
        pinned, tracked = frozenset(self.scan.pinned()), frozenset(self.scan.symbols())
        with self._lock:
            rows = (self._state.get("scanner") or {}).get("rows") or {}
        # The Stocks list's RVOL for the names it tracks, so a stock reads the same on
        # every page (universe.rvol_for).
        own = {str(s): float(r["rvol"]) for s, r in rows.items()
               if isinstance(r, dict) and isinstance(r.get("rvol"), int | float)}
        return uni_src.Ctx(
            quote=self.stream.quote, catalyst=self._catalyst, pinned=pinned, tracked=tracked,
            stage=self.momentum.stages(now.astimezone(ET).date(), basis != "last"),
            verdict=lambda s: pool_src.verdict(self.pool.entry(s), s in pinned, s in tracked),
            rvol=own.get)

    def breakouts(self, **kw: Any) -> dict[str, Any]:
        return self.universe.breakouts(self._ctx(), **kw)

    def extended(self, **kw: Any) -> dict[str, Any]:
        return self.universe.extended(self._ctx(), **kw)

    def heatmap(self) -> dict[str, Any]:
        """The Sectors page: the sector and theme ETFs joined to what their stocks did."""
        with self._lock:
            rows = [*(self._state.get("sectors") or []), *(self._state.get("themes") or [])]
            ext = dict(self._state.get("sector_ext") or {})
        # SPY is on both lists.
        etfs = {str(e["key"]): e for e in rows if isinstance(e, dict) and e.get("key")}
        return self.universe.heatmap(list(etfs.values()), ext=ext)

    def group_rows(self, group: str) -> dict[str, Any] | None:
        """The table of one card: a sector or theme ETF, or an industry by name."""
        key = group.strip().upper()
        table: dict[str, Any] = {"chip": "all", "rvol": 0.0, "listing": True}
        if key in uni_src.SECTOR_KEYS:
            return self.breakouts(sector=key, **table)
        if key in {t["key"] for t in self.universe.theme_list()}:
            return self.breakouts(theme=key, **table)
        name = self.universe.industry_name(group)
        return self.breakouts(industry=name, **table) if name else None

    def _with_insiders(self, r: dict[str, Any]) -> None:
        """INSIDER TRADES, AS CONTEXT LIKE NEWS (owner, 2026-11-13; sources/insiders.py):
        the month's open-market buys and discretionary sales in the row's own stock, and
        the newest as a flag after any report or release flag, so the News column shows it
        when the name has no story. Never part of the score."""
        ins = self.scan.insiders(str(r.get("sym")))
        r["insiders"] = ins[:5]
        if not ins:
            return
        more = f" (+{len(ins) - 1} more this month)" if len(ins) > 1 else ""
        flag = {"kind": "insider", "tone": "good" if ins[0]["side"] == "buy" else "warn",
                "text": f"Insider {'buy' if ins[0]['side'] == 'buy' else 'sale'}: "
                        f"{ins[0]['text']}{more}"}
        flags = list(r.get("flags") or [])
        at = sum(1 for f in flags if f.get("kind") in ("earnings", "event"))
        r["flags"] = [*flags[:at], flag, *flags[at:]]

    def _sec_extra(self) -> list[str]:
        """The names the SEC job reads besides the tracked ones: the Today list as last
        drawn, and the pool's top before any page has drawn it."""
        pool_top = [str(e.get("symbol")) for e in list(self.pool.ranked)[:30] if e.get("symbol")]
        return list(dict.fromkeys([*self._today_syms, *pool_top]))

    def top_stories(self, tracked: frozenset[str] | None = None) -> list[dict[str, Any]]:
        """The stock stories the Dashboard leads with, and the Market overview reads
        (overview.py): the freshest major ones about a name this desk could act on."""
        if tracked is None:
            tracked = frozenset(self.scan.symbols())

        def tradable(sym: str) -> bool:
            # On the list, or at the pool's floor in the wide read: the names this desk
            # could act on. The news flow is every US listing.
            cap = (self.universe.raw(sym) or {}).get("cap")
            return sym in tracked or (isinstance(cap, int | float) and cap >= pool_src.MIN_CAP)

        return self.stock_news.top(keep=tradable)

    def dashboard(self) -> dict[str, Any]:
        """The Dashboard, off what the Scanner and Macro already hold."""
        pinned, tracked = frozenset(self.scan.pinned()), frozenset(self.scan.symbols())
        view = self.pool.view(pinned)

        def price(sym: str) -> float | None:
            q = self.stream.quote(sym)
            p = q.get("price") if q else None
            return float(p) if isinstance(p, int | float) else None

        inplay = dash_mod.in_play(
            # One listing a company, as the Scanner list has it (pool.one_per_company).
            pool_src.one_per_company(list(self.pool.ranked), prefer=set(scan_src.CORE) | pinned),
            view,
            verdict=lambda s: pool_src.verdict(self.pool.entry(s), s in pinned, s in tracked),
            price=price) if view.get("ok") else None
        now = datetime.now(UTC)
        snap = self.snapshot()
        # Before the bell the sector figures are the funds' pre-market (the Sectors
        # cards' rule, universe.cards_phase).
        spy_ext = (snap.get("sector_ext") or {}).get("SPY")
        pre_day = (spy_ext or {}).get("day") if uni_src.cards_phase(spy_ext, now) == "pre" else None
        return dash_mod.build(self.scanner_payload(), snap, self.breakouts(),
                              self.day23(), self.top_stories(tracked),
                              session_day=uni_src.cards_day(now), inplay=inplay, pre_day=pre_day,
                              listed=self._listed_rows(now))

    #: How old a read of the Scanner list the Dashboard takes as it is: the Dashboard's
    #: own poll in the session, so its prices are no staler than they were.
    LISTED_HOLD_SEC = 10.0

    def _listed_rows(self, now: datetime) -> list[dict[str, Any]] | None:
        """The Scanner list's rows in its order, as the Scanner table draws them
        (dashboard.build `listed`): the last read when it is this phase's and under
        LISTED_HOLD_SEC old, else read again. None when it cannot be read: the card then
        falls back to the engine's own order."""
        phase = today_mod.phase_at(now)
        key = f"{phase.key}:{phase.day.isoformat()}"
        last = self._today_last
        if last is None or last[0] != key or time.monotonic() - last[1] > self.LISTED_HOLD_SEC:
            try:
                self.today(now)
            except Exception:  # noqa: BLE001 - the Dashboard still draws, on the engine's rows
                traceback.print_exc()
                return None
            last = self._today_last
        if last is None or last[0] != key:
            return None
        return [r["row"] for r in last[2].values() if isinstance(r.get("row"), dict)]

    # ---- the Today list (today.py) ----------------------------------------------

    def _engine_rows(self) -> dict[str, dict[str, Any]]:
        with self._lock:
            rows = (self._state.get("scanner") or {}).get("rows") or {}
        return {str(s): r for s, r in rows.items() if isinstance(r, dict)}

    def _today_levels(self, sym: str, engine: dict[str, dict[str, Any]], ctx: uni_src.Ctx,
                      now: datetime) -> dict[str, Any]:
        """A name's levels for its plan: the engine's where it is tracked (official
        PDH/PDL, the widened pre-market range), else the wide read's."""
        r = engine.get(sym)
        if r and r.get("ok"):
            lv = r.get("levels") or {}
            return {k: lv.get(k) for k in ("pdh", "pdl", "pmh", "pml", "pdc", "vwap")}
        e = self.universe.read_one(sym, ctx, now) or {}
        return {k: e.get(k) for k in ("pdh", "pdl", "pmh", "pml", "pdc")}

    def _today_pre(self, now: datetime, phase: today_mod.Phase, favs: frozenset[str],
                   tracked: frozenset[str], engine: dict[str, dict[str, Any]],
                   ctx: uni_src.Ctx) -> tuple[list[dict[str, Any]], str | None]:
        """The pre-market list: the pool's in-play rank on live prices. At the open, the
        same as the last pre-market read left it (pool.ranked_pre)."""
        clock = scan_mod.clock_at(now)
        if phase.key == "pre":
            if self.pool.basis != "pre":
                return [], "The pool's first pre-market read lands a few minutes after 04:00."
            rows = today_mod.live_premarket(self.pool.rows, self.stream.quote, now.timestamp())
            rclock = clock
        else:
            if self.pool.pre_day != clock.trading_day.isoformat():
                return [], "No pre-market read was held for this morning."
            rows = self.pool.rows_pre
            d = clock.trading_day
            rclock = scan_mod.clock_at(datetime(d.year, d.month, d.day, 9, 29, tzinfo=ET))
        ranked = pool_src.rank(rows, rclock, self.stock_news.major, self._strong(), self._pm_range)
        by = {str(r.get("symbol")): r for r in rows}
        return today_mod.rank_pre(
            ranked, by, levels=lambda s: self._today_levels(s, engine, ctx, now),
            catalyst=self._catalyst, favs=favs, tracked=tracked), None

    def _today_evening(self, now: datetime, phase: today_mod.Phase, favs: frozenset[str],
                       tracked: frozenset[str]) -> list[dict[str, Any]]:
        """The evening and overnight list from the wide read (today.rank_evening)."""
        basis = uni_src.basis_at(now)
        t = now.timestamp()
        quote = self.stream.quote

        def ah_of(r: dict[str, Any]) -> dict[str, Any] | None:
            # This evening's after-hours figures, or None: before the delayed read has
            # seen the late session the columns are the last one's.
            if basis not in ("post", "last") or not self.universe.ah_fresh(r):
                return None
            q = quote(r["sym"]) if basis == "post" else None
            close = r.get("close")
            if (q and q.get("session") == "post" and close
                    and t - float(q.get("at") or 0.0) <= today_mod.LIVE_SEC):
                p = float(q["price"])
                return {"last": p, "chg": (p / close - 1.0) * 100.0, "vol": r.get("ah_vol")}
            if r.get("ah_c") is None or r.get("ah_chg") is None:
                return None
            return {"last": r["ah_c"], "chg": r["ah_chg"], "vol": r.get("ah_vol")}

        session_day = prev_trading_day(phase.day)
        with self._lock:
            cal = list(self._state.get("scan_earn") or [])
        reports: dict[str, dict[str, Any]] = {}
        for e in cal:
            sym = e.get("symbol")
            if sym and ((e.get("date") == session_day.isoformat() and e.get("when") == "after")
                        or (e.get("date") == phase.day.isoformat() and e.get("when") == "pre")):
                reports[str(sym)] = e
        stage = {s: int(v["stage"]) for s, v in self.momentum.strong(
            now.astimezone(ET).date(), basis != "last", min_stage=1).items()}
        return today_mod.rank_evening(
            list(self.universe.rows), ah_of=ah_of, catalyst=self._catalyst, stage=stage,
            reports=reports, session_day=session_day, next_day=phase.day, favs=favs,
            tracked=tracked)

    def today(self, now: datetime | None = None) -> dict[str, Any]:
        """The Stocks tab's Today list: the phase it is, and the names ranked for it
        (today.py says what each phase ranks by)."""
        now = now or datetime.now(UTC)
        phase = today_mod.phase_at(now)
        pinned = self.scan.pinned()
        favs = frozenset(s for s in pinned if s not in scan_src.BENCHMARKS)
        tracked = frozenset(self.scan.symbols())
        note: str | None = None
        # The engine's rows as the Setups table draws them: every Today row is one
        # (today.scan_row), so the list is drawn in that table.
        payload = {str(r.get("sym")): r for r in self.scanner_payload().get("rows") or []}
        if phase.key == "session":
            rows = today_mod.rank_session(list(payload.values()), favs=favs, tracked=tracked)
        elif phase.key == "pre":
            engine = self._engine_rows()
            rows, note = self._today_pre(now, phase, favs, tracked, engine, self._ctx())
        else:
            rows = self._today_evening(now, phase, favs, tracked)
            if not self.universe.rows:
                note = "The wide read is loading: about half a minute after a restart."
        if phase.key != "session":
            # The rest of the tracked list under the phase's ranking, as Setups showed it.
            rows = rows + today_mod.rest_of_list(rows, payload.values(),
                                                 inplay=dict(self.pool.by_sym), favs=favs)
        # ONE ROW A COMPANY (owner, 2026-11-19: "why do i see GOOG and GOOGL?"): a share
        # class of a company already listed goes, the one held for good (the MAG 7's GOOGL,
        # a favourite) taking the place of the first (pool.one_per_company).
        rows = pool_src.one_per_company(rows, sym_of=lambda r: r["sym"],
                                        prefer=set(scan_src.CORE) | favs)
        key = f"{phase.key}:{phase.day.isoformat()}"
        # One reader at a time past here: the pool's thread (the phase-end log) and a page
        # read the list in the same second after a restart, and the second saw the phase's
        # record made but not yet filled, so it stamped the whole top ten new.
        with self._today_lock:
            fresh = key not in self._today_seen
            if fresh:
                self._today_seen = {key: {}}
            today_mod.mark_new(rows, self._today_seen[key], now.timestamp(), fresh)
        today_mod.numbered(rows)
        if phase.key == "pre":
            self._pre_figures(rows, payload, phase.day)
        self.universe.want_sparks(r["sym"] for r in rows[:40])
        self._today_syms = [r["sym"] for r in rows if not r.get("listed")][:40]
        for r in rows:
            self.universe.fill_spark(r)
            r["row"] = today_mod.scan_row(r, payload.get(r["sym"]), phase.key,
                                          self.universe.raw(r["sym"]))
            # A name the engine does not track is drawn from the wide read, which has no
            # insider trades; the book has them whether it is tracked or not.
            if "insiders" not in r["row"]:
                self._with_insiders(r["row"])
            self._story_read(r["row"])
        self._today_last = (key, time.monotonic(), {r["sym"]: r for r in rows})
        return {"ok": True, "phase": phase.as_dict(now), "phases": [
                    {"key": k, "label": today_mod.LABELS[k]} for k in today_mod.PHASES],
                "rows": rows, "note": note, "favs_tracked": self.scan.tracked_favourites(),
                # The names the live rotation brought in today, each with when and over whom
                # (rotation.py): for Hermes and the page.
                "rotated": [{"sym": p["symbol"], "at": p.get("at"), "why": p.get("reason")}
                            for p in self.pool.picks() if p.get("mark") == "live"],
                "updated_utc": now.isoformat()}

    def _pre_figures(self, rows: list[dict[str, Any]], payload: dict[str, dict[str, Any]],
                     day: date) -> None:
        """Each pre-market row's four figures, shown and logged and never scored
        (premarket_record.pre_context): its gap against SPY's, its pre-market volume
        against its own usual one, the model's read of its story, and where it holds in
        its pre-market range. Never raises: a row without them is drawn as before."""
        try:
            spy = payload.get("SPY") or {}
            s_last, s_pdc = spy.get("last"), (spy.get("levels") or {}).get("pdc")
            s_atr = spy.get("atr_d")
            spy_gap = ((float(s_last) - float(s_pdc)) / float(s_atr)
                       if isinstance(s_last, int | float) and isinstance(s_pdc, int | float)
                       and isinstance(s_atr, int | float) and s_atr else None)
            with self._lock:
                ext = dict(self._state.get("sector_ext") or {})
            for t in rows:
                sym = str(t.get("sym") or "")
                sec = ext.get(str(t.get("sector") or "")) or {}
                pct = (sec.get("pct") if sec.get("kind") == "pre"
                       and sec.get("day") == day.isoformat() else None)
                rvol, est = self.universe.pre_rvol(sym, t.get("vol_pct"))
                story = t.get("story")
                read = (self.newsread.for_story(sym, str(story["title"]))
                        if isinstance(story, dict) and story.get("title") else None)
                t["pre_ctx"] = premarket_record.pre_context(
                    t, spy_gap=spy_gap, sector_pct=pct if isinstance(pct, (int, float)) else None,
                    rvol=rvol, rvol_est=est, read=read)
        except Exception:  # noqa: BLE001 - the list still draws
            traceback.print_exc()

    def _premarket_list(self, got: dict[str, Any], now: datetime) -> None:
        """The pre-market list as it stood near 09:25, one line in the pre-market record
        (premarket_record.list_line). Never fatal."""
        try:
            phase = got.get("phase") or {}
            premarket_record.append(premarket_record.list_line(
                str(phase.get("day") or now.astimezone(ET).date().isoformat()),
                now.astimezone(ET).strftime("%H:%M"), got.get("rows") or []))
        except Exception:  # noqa: BLE001 - a record line must never stop the pool's job
            traceback.print_exc()

    #: How often the pre-market record's after-the-bell work runs, and how many names it
    #: may read bars for each time (a Yahoo download each).
    PRE_OUTCOME_SEC = 120.0
    PRE_OUTCOME_READS = 6
    PRE_OUTCOME_TRIES = 3

    def _premarket_outcomes(self, now: datetime | None = None) -> None:
        """Each finished day's pre-market list, held to what its names did
        (premarket_record.day_result), whenever the app next runs after that day's bell.
        A name's bars are read for it if the ones held were not read after the bell; a
        few names a pass. A day's line is written once every name has a result or has
        been tried PRE_OUTCOME_TRIES times. Never raises."""
        now = now or datetime.now(UTC)
        t = time.monotonic()
        if t - self._pre_outcome_at < self.PRE_OUTCOME_SEC:
            return
        self._pre_outcome_at = t
        try:
            lines = premarket_record.read()
            owed = premarket_record.owed(lines, now.astimezone(ET).date(), now.timestamp())
            reads = 0
            for day, syms in sorted(owed.items()):
                d = date.fromisoformat(day)
                got = self._pre_progress.setdefault(day, {})
                for sym in syms:
                    if sym in got:
                        continue
                    sig = self.scan.day_signals(d, [sym])
                    if sym not in sig:
                        if reads >= self.PRE_OUTCOME_READS:
                            continue  # this pass's reads are spent: the next pass reads it
                        reads += 1
                        self.scan.ensure_adhoc(sym)
                        sig = self.scan.day_signals(d, [sym])
                    if sym in sig:
                        signals, _final = sig[sym]
                        got[sym] = premarket_record.day_result(
                            sym, d, signals, list(self.scan.bars.get(sym) or []),
                            float(self.scan.fetched.get(sym) or now.timestamp()),
                            list(self.scan.daily.get(sym) or []), now.timestamp())
                        continue
                    tries = self._pre_tries.get((day, sym), 0) + 1
                    self._pre_tries[(day, sym)] = tries
                    if tries >= self.PRE_OUTCOME_TRIES:
                        got[sym] = {"error": "no bars for the day after its bell"}
                if all(s in got for s in syms):
                    premarket_record.append(premarket_record.outcome_line(day, got, now))
                    self._pre_progress.pop(day, None)
        except Exception:  # noqa: BLE001 - the record waits for the next pass
            traceback.print_exc()

    def _today_log(self, now: datetime | None = None) -> None:
        """Each phase's list as it stood near its end, one line in cache/today_marks.jsonl,
        so the phases' ranks can be held to what the names then did (as the pool's marks
        are). Never fatal."""
        now = now or datetime.now(UTC)
        phase = today_mod.phase_at(now)
        left = (phase.ends - now).total_seconds() / 60.0
        key = f"{phase.key}:{phase.day.isoformat()}"
        if left > today_mod.LOG_BEFORE_END_MIN or key in self._today_logged:
            return
        self._today_logged.add(key)
        try:
            got = self.today(now)
            today_mod.log_list(os.path.join(config.CACHE_DIR, today_mod.MARKS_NAME), got, now)
            # The pre-market list's own record, with its four figures (premarket_record).
            if phase.key == "pre":
                self._premarket_list(got, now)
        except Exception as e:  # noqa: BLE001 — a log line must never stop the pool's job
            with contextlib.suppress(Exception):
                print(f"today: the {phase.key} list was not logged: {e}", flush=True)

    def day23(self, min_move: float = mom_mod.DEFAULT_MOVE, cap: float = mom_mod.DEFAULT_CAP,
              chip: str = "all") -> dict[str, Any]:
        now = datetime.now(UTC)
        ctx = self._ctx()
        basis = uni_src.basis_at(now)
        out = self.momentum.table(
            read=lambda s: self.universe.read_one(s, ctx, now), raw=self.universe.raw,
            catalyst=ctx.catalyst, spark=self.universe.fill_spark, tracked=ctx.tracked,
            pinned=ctx.pinned, basis=basis, today=now.astimezone(ET).date(), min_move=min_move,
            cap=cap, chip=chip,
            forming=self.universe.forming(ctx, min_move=min_move, cap=cap, now=now))
        self.universe.want_sparks(r["sym"] for r in out["rows"][:80])
        return {**self.universe._head(basis, now), "min_move": min_move, "cap": cap, **out}

    def track(self, sym: str) -> dict[str, Any]:
        """Put a name from the wide scan on today's list."""
        sym = sym.strip().upper()
        raw = self.universe.raw(sym) or {}
        room = scan_src.MAX_SYMBOLS - len(self.scan.watchlist())
        at = datetime.now(UTC).astimezone(ET).strftime("%H:%M")
        err = self.pool.track(sym, raw.get("name"), raw.get("sector"), at, room)
        if err is None and self._apply_promotions():
            self._wake_scan_jobs()
        return {"ok": err is None, "sym": sym, "error": err,
                "tracked": sym in self.scan.symbols(), "room": room}

    def stream_health(self) -> dict[str, Any]:
        st = self.stream.status().as_dict()
        return {"status": st, "connected": self.stream.connected,
                "subscribed": self.stream.subscribed, "check": self.stream.check.days,
                "feed": self.feed()}

    def _webull_wanted(self) -> list[str]:
        """Webull's names, most wanted first: it carries 100 on its one connection
        (webull_src.CONNECTIONS says why one), so the order is what gets real-time trades.
        The charts open now, the tracked names (the engine's rows, the index funds and the
        Magnificent 7), the Scanner list, then the rest of what Yahoo's socket is given."""
        tracked = self.scan.symbols()
        return list(dict.fromkeys([*self.stream.touched(), *tracked, *self._today_syms,
                                   *self.stream.wanted()]))

    def feed(self) -> dict[str, Any]:
        """Which live-price feed is on, why, and each one's health."""
        mode, why = webull_src.feed_mode()
        now = time.time()
        heard, raw = self.webull.pace(now)
        # The first names wanted: Webull's own last trade beside the one the books hold,
        # so a feed that is connected but losing to Yahoo shows itself. Then the first
        # names the snapshots read, the same way.
        running = self.webull.running()
        wanted = self._webull_wanted()
        snap_first = self.webull.snap_names()[:6] if running else []
        sample = []
        for sym in list(dict.fromkeys([*wanted[:8], *self._today_syms[:6], *snap_first])):
            w = self.webull.last_of(sym)
            s = self.webull.snap_of(sym)
            q = self.stream.quote(sym) or {}
            sample.append({"sym": sym, "webull_at": w[0] if w else None,
                           "webull_price": w[1] if w else None,
                           "snap_at": s[0] if s else None, "snap_price": s[1] if s else None,
                           "book_feed": q.get("feed"), "book_at": q.get("at"),
                           "book_price": q.get("price")})
        return {"feed": mode, "why": why, "choices": list(webull_src.FEEDS),
                "webull_keys": webull_src.credentials() is not None,
                "webull": self.webull.status().as_dict() if running else None,
                "yahoo": self.stream.status().as_dict(),
                "webull_pace": {"trades_last_min": heard, "recv_less_trade_sec": raw,
                                "now": now},
                "webull_connections": self.webull.slots(),
                "snapshots": self.webull.snap_status(now) if running else None,
                "coverage": self._feed_coverage(wanted, now),
                "sample": sample}

    def _feed_coverage(self, wanted: list[str], now: float) -> dict[str, Any]:
        """Which feed's trade each wanted name's last price is, and how old those trades are
        (the median, in seconds): the whole list's answer to "is it live", where `sample`
        is a few names'. A name no feed has heard from today counts under "none"."""
        today = datetime.fromtimestamp(now, ET).date()
        ages: dict[str, list[float]] = {}
        none = 0
        for sym in wanted:
            q = self.stream.quote(sym) or {}
            at = q.get("at")
            if not isinstance(at, int | float) or datetime.fromtimestamp(at, ET).date() != today:
                none += 1
                continue
            ages.setdefault(str(q.get("feed") or "?"), []).append(max(0.0, now - float(at)))
        return {"names": len(wanted), "none": none,
                "by_feed": {f: {"names": len(a), "age_p50_sec": round(statistics.median(a), 1)}
                            for f, a in sorted(ages.items())}}

    def set_feed(self, feed: str | None) -> dict[str, Any]:
        """Switch the live-price feed now ("webull" / "yahoo"), or None to go back to what
        .env.local says. Applied here at once, not on the next tick."""
        webull_src.set_feed_mode(feed)
        mode, _ = webull_src.feed_mode()
        if mode == "webull":
            self.webull.start()
        else:
            self.webull.stop()
            with self._lock:
                self._status.pop("webull", None)
        return self.feed()

    def _do_options(self) -> None:
        clock = self.scan.clock(datetime.now(UTC))
        st = self.options.tick(self.scan.watchlist(), clock.trading_day,
                               reports=self._reports_ahead(clock.trading_day))
        # Nothing goes into state: the chains stay in the store and are joined
        # into the scanner's rows on read (`scanner_payload`) — only the status
        # row, for the rail.
        self._commit("options", None, st)

    def _do_premarket(self) -> None:
        watch = self.scan.watchlist()
        st = self.premarket.tick(watch)
        if not st.ok:
            # Nasdaq is not answering. The rows take the screener's figures for a name
            # it has not answered for (`_pm_range`, `scanner_payload`), so the rail
            # reports what the pages have, not the request that failed.
            td = self.scan.clock(datetime.now(UTC)).trading_day
            covered = sum(1 for s in watch if self.universe.premarket_of(s, td) is not None)
            st = pre_src.covered_by_screener(st, covered, len(watch))
        # Like the chains: the reads stay in the store and join the rows on read.
        self._commit("premarket", None, st)

    def _held_spark(self, sym: str) -> tuple[list[float], float | None] | None:
        """One name's spark off the scanner's own five-minute bars, live trade laid on, as
        the slide-out chart draws them (`scanner_bars`), cut to the chart's opening view
        (`scan.spark_of`). None when the scanner does not hold the name, or its copy is
        older than the spark read would be: an ad-hoc chart's bars are read when the chart
        opens and then sit, while the tracked names rotate every ninety seconds."""
        if sym not in self.scan.bars:
            return None
        now = datetime.now(UTC)
        clock = self.scan.clock(now)
        age = time.time() - self.scan.fetched.get(sym, 0.0)
        if age > (HELD_SPARK_IDLE_SEC if clock.session == "closed" else HELD_SPARK_SEC):
            return None
        bars = self.scan.live_bars(sym, clock)
        if not bars:
            return None
        return scan_mod.spark_of(bars, int(now.timestamp()), self.scan.daily.get(sym),
                                 self.scan.daily_at.get(sym))

    def _pm_range(self, sym: str, td: date) -> tuple[float | None, float | None] | None:
        """`td`'s pre-market (high, low) for one name from a read that is not the
        scanner's own bars: Nasdaq's when it has answered for the name, else the wide
        scan's screener (fifteen minutes behind, every name in one request). None when
        neither holds today's. `ScanStore.pm_wide` keeps the widest of what this
        returns, and `scan.technicals` takes whichever of it and the bars reaches
        further."""
        got = self.premarket.view(td).get(sym) or self.universe.premarket_of(sym, td)
        if not got:
            return None

        def num(v: Any) -> float | None:
            return float(v) if isinstance(v, int | float) and not isinstance(v, bool) else None

        return num(got.get("high")), num(got.get("low"))

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
        self._today_log()

    def _rotation_candidates(self, tracked: set[str], on_list: list[dict[str, Any]],
                             t: float) -> list[str]:
        """This round's names to score (rotation.py, step 1): the ones the owner opened in
        the last hour, newest first, then the wide read's through their levels now."""
        for s in [s for s, at in self._opened.items() if t - at > rot_mod.OPENED_SEC]:
            self._opened.pop(s, None)
        opened = [s for s, _ in sorted(self._opened.items(), key=lambda x: -x[1])
                  if s not in tracked][: rot_mod.OPENED_MAX]
        firms = {k for r in on_list if (k := pool_src.company_key(r.get("name")))}
        # Only names the pool counts as tradable ($10+, the turnover, the range); a name the
        # owner opened is theirs to judge and is not held to it.
        found = self.universe.rotation_finder(
            self.stream.quote, skip=tracked | set(opened), skip_companies=firms,
            limit=rot_mod.CANDIDATES - len(opened), only=set(self.pool.by_sym))
        return opened + [str(e["sym"]) for e in found]

    def _rotation_scores(self, cands: list[str], t: float) -> list[dict[str, Any]]:
        """Each candidate scored as a name on the list is (rotation.py, step 2): its bars read
        when due (`rotation.reads_due`), its technical row, then the payload's scoring."""
        for s in rot_mod.reads_due(cands, dict(self.scan.fetched), t):
            self.scan.ensure_adhoc(s)
        extra: dict[str, dict[str, Any]] = {}
        for s in cands:
            if s not in self.scan.bars:
                continue
            raw = self.universe.raw(s)
            one = self.scan.compute_one(s, sector=raw["sector"] if raw else None)
            if one is not None:
                extra[s] = one
        if not extra:
            return []
        got = self._payload(watch=list(extra), extra_rows=extra, news_limit=1)
        out = []
        for r in got.get("rows") or []:
            total = (r.get("score") or {}).get("total")
            if r.get("ok") and isinstance(total, int | float):
                out.append({"sym": str(r["sym"]), "score": float(total),
                            "name": r.get("name"), "sector": r.get("sector"),
                            "side": (r.get("score") or {}).get("side"), "last": r.get("last")})
        return sorted(out, key=lambda c: -c["score"])

    def _rotation_outcome(self, now: datetime) -> None:
        """Once a session, from the first wide read whose bar is final (16:30 ET; the rule
        `_do_universe` writes the momentum ledger on): the close of every name the day's
        rotation moved, so the record can judge each swap (rotation.outcome_line)."""
        basis = uni_src.basis_at(now)
        et = now.astimezone(ET)
        final = basis == "last" or (basis == "post" and
                                    et.hour * 60 + et.minute >= scan_mod.rth_end(et.date()) + 30)
        day = uni_src.session_day(now).isoformat()
        if not final or self._rot_outcome_day == day or not self.universe.rows:
            return
        path = os.path.join(config.CACHE_DIR, rot_mod.LOG_NAME)
        names, done = rot_mod.day_names(rot_mod.read_lines(path), day)
        self._rot_outcome_day = day
        if names and not done:
            line = rot_mod.outcome_line(day, names, self.universe.raw)
            if line is not None:
                rot_mod.append(path, line)

    def _do_rotation(self) -> float:
        """One round of the live rotation (rotation.py): score the best names off the list,
        and swap in any that beat the weakest of the pool's picks by the margin twice in a
        row. Outside its window it clears the streaks and waits."""
        now = datetime.now(UTC)
        if not rot_mod.in_window(now) or not self.pool.enabled:
            self._rot_streak = {}
            self._rotation_outcome(now)
            return rot_mod.IDLE_SEC
        t = now.timestamp()
        started = time.monotonic()
        watch = self.scan.watchlist()
        tracked = set(self.scan.symbols())
        payload = self.scanner_payload()
        day = str(payload.get("trading_day") or "")
        rows = [r for r in payload.get("rows") or [] if isinstance(r, dict)]
        scores = {str(r.get("sym")): (r.get("score") or {}).get("total") for r in rows
                  if r.get("ok")}
        if not rot_mod.scores_ready(watch, scores):
            # A half-built list (just after a restart): no round, and no streak carried.
            self._rot_streak = {}
            return rot_mod.ROUND_SEC
        cands = self._rotation_candidates(tracked, rows, t)
        scored = self._rotation_scores(cands, t)
        # Each name's side and price now, for the record (rotation.log_line).
        at_swap = {str(r.get("sym")): {"side": (r.get("score") or {}).get("side"),
                                       "last": r.get("last")} for r in rows if r.get("ok")}
        at_swap.update({c["sym"]: {"side": c.get("side"), "last": c.get("last")}
                        for c in scored})
        signalled = self.events.holding(day, t, trade_sec=rot_mod.TRADE_HOLD_SEC,
                                        break_sec=rot_mod.BREAK_HOLD_SEC)
        picks = rot_mod.held(self.pool.picks(), watch, scores, signalled, t,
                             tradable=set(self.pool.by_sym) if self.pool.by_sym else None,
                             mine=set(self._opened))
        room = max(0, scan_src.MAX_SYMBOLS - len(watch))
        moves, self._rot_streak = rot_mod.decide(scored, picks, room, self._rot_streak)
        moved = False
        if moves:
            at = now.astimezone(ET).strftime("%H:%M")
            moved = self.pool.rotate(moves, {c["sym"]: c for c in scored}, at, t)
            if moved:
                self._apply_promotions()
                self._wake_scan_jobs()
                path = os.path.join(config.CACHE_DIR, rot_mod.LOG_NAME)
                for m in moves:
                    rot_mod.append(path, rot_mod.log_line(day, now, m, scored, at_swap))
        st = SourceStatus("Rotation")
        st.ok, st.source, st.items = True, "live", len(scored)
        weakest = min((p for p in picks if not p["locked"]),
                      key=lambda p: p["score"] if p["score"] is not None else 0.0, default=None)
        best = scored[0] if scored else None
        note = (f"{len(scored)} of {len(cands)} scored"
                + (f" · best off the list {best['sym']} {best['score']:.0f}" if best else "")
                + (f" · weakest pick {weakest['sym']} {weakest['score'] or 0:.0f}"
                   if weakest else "")
                + (f" · {room} free" if room else "")
                + f" · {time.monotonic() - started:.1f}s")
        st.notes = [note]
        if moved:
            st.notes.append("; ".join(
                f"{m['in']} {m['in_score']:.0f} in" + (f" for {m['out']} {m['out_score'] or 0:.0f}"
                                                       if m["out"] else "") for m in moves))
        with self._lock:
            self._status["rotation"] = st
            self._updated["rotation"] = time.time()
        if moved or time.monotonic() - self._rot_logged >= 600.0:
            self._rot_logged = time.monotonic()
            self._log("rotation", st)
        return rot_mod.ROUND_SEC

    def _apply_promotions(self) -> bool:
        """The pool's promotions, and today's tracked favourites, into the scanner's
        list. True when it changed."""
        day, syms, sectors, favs = self.pool.for_scan()
        return self.scan.set_promoted(day, syms, sectors, favs)

    def set_promotion(self, on: bool) -> None:
        """Switch the pool's promotion (API thread). Off takes today's promoted
        names off the list at once; on makes the pool's next tick a read."""
        if self.pool.set_enabled(on):
            self._apply_promotions()
            self._wake_scan_jobs()
            fn, interval, _due = self._premarket_jobs["pool"]
            self._premarket_jobs["pool"] = (fn, interval, time.monotonic())

    def _unlabelled(self, day: str, book: str) -> dict[str, Any] | None:
        card = self.daytypes.get(day, book)
        return card if card is not None and card.get("type") is None else None

    @staticmethod
    def _daytype_inputs(assets: dict[str, Any], frames: dict[str, Any], book: str
                        ) -> tuple[list[dict[str, Any]], float | None]:
        """One book's session rows and daily ATR, the card's two inputs."""
        sessions = (assets.get(book) or {}).get("sessions") or []
        frame = frames.get(book) or {}
        atr = frame.get("atr14") if isinstance(frame, dict) and frame.get("ok") else None
        return sessions, (float(atr) if isinstance(atr, int | float) else None)

    def _daytype_tables(self) -> dict[str, dict[str, Any]]:
        """The base-rate tables per book (daytype.rate_table) over the record — the
        backfill's rows and the live log's labelled days after them — rebuilt only
        when the log gains a label."""
        live = self.daytypes.rows()
        key = (len(live), sum(1 for r in live if r.get("type")))
        with self._dt_lock:
            if key == self._dt_key:
                return self._dt_tables
            tables: dict[str, dict[str, Any]] = {}
            meta: dict[str, Any] = {}
            for book in daytype.BOOKS:
                back = self._dt_record.get(book) or []
                last = str(back[-1].get("day")) if back else None
                rows = [*back, *self.daytypes.labelled(book, after=last)]
                tables[book] = daytype.rate_table(rows)
                meta[book] = {"n": len(rows), "backfill": len(back),
                              "live": len(rows) - len(back),
                              "from": rows[0].get("day") if rows else None,
                              "to": rows[-1].get("day") if rows else None}
            self._dt_tables, self._dt_meta, self._dt_key = tables, meta, key
            return tables

    def _session_types(self, src: dict[str, Any]) -> dict[str, Any]:
        """The session-type read per book (daytype.py) off blocks already held —
        `src` is the snapshot, or the state's ranges, history, gex, calendar and
        quotes: the card as it stands now (the night so far before the bell, the
        finished night after it), what the record says of a day like it, and the
        day's own label once New York has closed. Computed on read, like volterm;
        the log's card at 09:25 is the one of record."""
        now = datetime.now(UTC)
        day = globex_trade_date(now)
        tables = self._daytype_tables()
        out: dict[str, Any] = {"day": day.isoformat(), "books": {}, "record": self._dt_meta}
        if not is_trading_day(day):
            return out
        assets = (src.get("ranges") or {}).get("assets") or {}
        frames = (src.get("history") or {}).get("books") or {}
        gex = (src.get("gex") or {}).get("assets") or {}
        vt = src.get("volterm") or volterm_state(src.get("quotes") or [])
        vix, ratio = daytype.vix_of(vt)
        prints = daytype.prints_of(src.get("calendar") or [], day)
        prev_key = prev_trading_day(day).isoformat()
        for book in daytype.BOOKS:
            sessions, atr = self._daytype_inputs(assets, frames, book)
            if not sessions or atr is None:
                out["books"][book] = None
                continue
            dp = BOOK_DP.get(book, 0)
            card = daytype.card_from_live(
                book, day, sessions, atr,
                yesterday=structure.yesterday(sessions, atr, None, dp),
                fuel=structure.fuel(sessions, atr, None, dp), vix=vix, vix_ratio=ratio,
                gamma=daytype.gamma_of(gex.get(book)), em=None, prints=prints, now=now,
                half_day=early_close(day) is not None,
                prev_card=self.daytypes.get(prev_key, book))
            done = daytype.label_from_live(card, sessions, atr, now)
            label = ({k: done.get(k) for k in ("type", "dir", "inside", "range_atr", "close_pos")}
                     if done.get("type") else None)
            out["books"][book] = {"card": card, "label": label,
                                  "lean": daytype.lean(card, tables.get(book) or {})}
        return out

    def _do_bias_record(self) -> float | None:
        """The bias record (bias_record.py): at each mark every book's board read and the
        stocks tape's, with the price each is judged from; at the close each book's last.
        What is on file is read once, so a restart neither repeats a mark nor loses one
        still inside its slack. A minute's retry while the board has not been built."""
        now = datetime.now(UTC)
        if self._bias_done is None:
            self._bias_done = bias_record.done_keys(bias_record.read())
        marks, closes = self._bias_done
        key = bias_record.due_mark(now, marks)
        close_td = bias_record.close_due(now, closes)
        if key is None and close_td is None:
            return None
        snap = self.snapshot()
        quotes = {q.get("key"): q for q in snap.get("quotes") or [] if isinstance(q, dict)}

        def last_of(book: str) -> float | None:
            q = quotes.get(volterm_mod.quote_key(book)) or {}
            v = q.get("last")
            return float(v) if isinstance(v, (int, float)) else None

        lines: list[dict[str, Any]] = []
        if key is not None:
            boards = (snap.get("drivers") or {}).get("books") or {}
            if not boards:
                return 60.0
            st = drivestats.Stats([c for c in snap.get("context") or [] if isinstance(c, dict)],
                                  now.astimezone(ET).date())
            for book in bias_record.BOOKS:
                r = boards.get(book)
                if not isinstance(r, dict):
                    continue
                q = quotes.get(volterm_mod.quote_key(book)) or {}
                pct = q.get("pct") if isinstance(q.get("pct"), (int, float)) else None
                lines.append(bias_record.read_line(
                    key[0], key[1], now, book, r, last_of(book), pct,
                    st.usual(drivestats.BOOK_KEY[book])[0]))
            # The stocks tape, judged on the S&P future: it trades at every mark.
            try:
                conv = ((self.scanner_payload().get("regime") or {}).get("conviction")) or None
            except (ValueError, TypeError, KeyError, ZeroDivisionError):
                conv = None
            if isinstance(conv, dict):
                es = quotes.get("ES") or {}
                lines.append(bias_record.read_line(
                    key[0], key[1], now, bias_record.TAPE, conv, last_of("ES"),
                    es.get("pct") if isinstance(es.get("pct"), (int, float)) else None,
                    st.usual("ES")[0]))
            marks.add(key)
        if close_td is not None:
            lines.append(bias_record.close_line(close_td, now,
                                                {b: last_of(b) for b in bias_record.BOOKS}))
            closes.add(close_td)
        bias_record.append(lines)
        return None

    def _do_daytype(self) -> float | None:
        """The session-type record (daytype.py): at CARD_AT one card per book with
        what was known before the bell; from LABEL_AT the label, off the finished
        New York row. The log keeps the day's marks, so a restart neither repeats
        a card nor loses a label, and a card a restart made late says so. The
        previous session's card is labelled too when its window was missed: the
        finished row stays the box's latest, dated, until the next session starts.
        A minute's retry while the ranges or the daily bars are still to arrive."""
        now = datetime.now(UTC)
        et = now.astimezone(ET)
        day = et.date()
        key, prev_key = day.isoformat(), prev_trading_day(day).isoformat()
        to_write = ([b for b in daytype.BOOKS if self.daytypes.get(key, b) is None]
                    if is_trading_day(day) and et.time() >= daytype.CARD_AT else [])
        to_label = [(k, b) for k in (key, prev_key) for b in daytype.BOOKS
                    if (k != key or et.time() >= daytype.LABEL_AT) and self._unlabelled(k, b)]
        if not to_write and not to_label:
            return None
        snap = self.snapshot()
        assets = (snap.get("ranges") or {}).get("assets") or {}
        frames = (snap.get("history") or {}).get("books") or {}
        gex = (snap.get("gex") or {}).get("assets") or {}
        waiting, done = False, 0
        if to_write:
            vix, ratio = daytype.vix_of(snap.get("volterm"))
            prints = daytype.prints_of(snap.get("calendar") or [], day)
        for book in to_write:
            sessions, atr = self._daytype_inputs(assets, frames, book)
            if not sessions or atr is None:
                waiting = True
                continue
            dp = BOOK_DP.get(book, 0)
            em = (report_mod.live_ladder(snap, book) or {}).get("em")
            self.daytypes.put(daytype.card_from_live(
                book, day, sessions, atr,
                yesterday=structure.yesterday(sessions, atr, None, dp),
                fuel=structure.fuel(sessions, atr, em, dp), vix=vix, vix_ratio=ratio,
                gamma=daytype.gamma_of(gex.get(book)), em=em, prints=prints, now=now,
                half_day=early_close(day) is not None,
                prev_card=self.daytypes.get(prev_key, book)))
            done += 1
        for k, book in to_label:
            sessions, atr = self._daytype_inputs(assets, frames, book)
            prior = self.daytypes.get(k, book)
            card = (daytype.label_from_live(prior, sessions, atr, now)
                    if prior and sessions else None)
            if card is None or card.get("type") is None:
                # Today's row is still to finish; yesterday's, if it is gone, is gone.
                waiting = waiting or k == key
                continue
            self.daytypes.put(card)
            done += 1
        if done:
            st = SourceStatus("daytype")
            st.items = done
            self._log("daytype", st.settle(True, "card"))
        return 60.0 if waiting else None

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
                # After a start the calendar is read two seconds before this is:
                # its speeches (see _do_calendar) are added now, not ten minutes on.
                held = self._state.get("calendar")
                if isinstance(held, list):
                    self._state["calendar"] = cal_src.with_fed_speeches(held, rows)

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
                                              "scanner_events.jsonl", "scanner_preopen.jsonl",
                                              "iv_history.jsonl", "scanner_momentum.json",
                                              "scanner_universe.json", "stream_check.json",
                                              "oi_log.jsonl", "cboe_pc.jsonl",
                                              "session_types.jsonl", "bias_record.jsonl"))
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
        self.stream.start()
        self._wide_thread = threading.Thread(
            target=self._run, args=(self._wide_jobs,), name="wide", daemon=True)
        self._wide_thread.start()

    def stop(self) -> None:
        self._stop.set()
        self.stream.stop()
        self.webull.stop()
        for th in (self._thread, self._scan_thread, self._quotes_thread, self._options_thread,
                   self._premarket_thread, self._live_thread, self._wide_thread):
            if th:
                th.join(timeout=3)

    # ---------------------------------------------------------------- read

    def snapshot(self) -> dict[str, Any]:
        """Everything, as one object. Thread-safe."""
        with self._lock:
            state = {k: v for k, v in self._state.items() if k not in _SCANNER_KEYS}
            status = {k: v.as_dict() for k, v in self._status.items()}
            updated = dict(self._updated)

        # OUTSIDE THE SESSION, WHAT THE CASH MARKET IS ACTUALLY DOING (the audit of
        # 2026-11-16, after the Sectors cards). The board's US-listed funds carry their
        # extended-hours trade beside the regular price (quotes.with_ext), and before
        # the bell the index movers carry each name's own pre-market move
        # (constituents.with_pre). New objects, never the stored ones; the regular
        # figures the engine reads are untouched.
        at = datetime.now(UTC)
        ext = state.get("sector_ext") or {}
        if ext and isinstance(state.get("quotes"), list):
            state["quotes"] = quotes_src.with_ext(state["quotes"], ext,
                                                  at.astimezone(ET).date().isoformat())
        if isinstance(state.get("constituents"), dict) and uni_src.basis_at(at) == "pre":
            state["constituents"] = cons_src.with_pre(
                state["constituents"], lambda s: self.universe.pre_move(s, at))

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
            # The days a market the desk trades through is shut or shuts early: US
            # stocks and bonds, London, Tokyo (holidays.py, hand-kept from the
            # published schedules). Yesterday through three weeks out, for the
            # Macro calendar; a table read, so on read as well.
            "holidays": market_holidays(),
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
        # Will New York trend or range (daytype.py): the same arithmetic on the
        # blocks above and the record on disk, so it is computed on read too.
        try:
            snap["daytype"] = self._session_types(snap)
        except (ValueError, TypeError, KeyError, ZeroDivisionError) as e:
            snap["daytype"] = {"books": {}, "error": f"{e.__class__.__name__}: {e}"}
        return snap

    def scanner_payload(self) -> dict[str, Any]:
        """The Scanner tab's whole read — technicals joined with the macro now."""
        return self._payload()

    def story_summaries(self) -> dict[str, str]:
        """{a headline's key (newsread.norm): the feed's sentence or two about it}, from
        the names' own feeds and the wire: what the model is shown beside a major
        story's headline. Most stories have none."""
        with self._lock:
            own = self._state.get("scan_news") or {}
            wire = self._state.get("wire") or []
        out: dict[str, str] = {}
        for rows in [*own.values(), wire]:
            for r in rows if isinstance(rows, list) else []:
                s = r.get("summary") if isinstance(r, dict) else None
                if isinstance(s, str) and len(s) >= 40:
                    out.setdefault(newsread.norm(str(r.get("title") or "")), s)
        return out

    def _payload(self, watch: list[str] | None = None,
                 extra_rows: dict[str, dict[str, Any]] | None = None,
                 news_limit: int | None = 8) -> dict[str, Any]:
        """`watch` narrows the build to those names (the slide-out's one row);
        `extra_rows` carries a row for a name off the list; `news_limit` is how
        many headlines each row ships, None for all of them."""
        with self._lock:
            scan = self._state.get("scanner") or {}
            parts = {k: self._state.get(k) for k in
                     ("quotes", "sectors", "calendar", "scan_earn", "wire", "scan_news",
                      "scan_sec", "context", "ranges", "history", "gex")}
            cons = self._state.get("constituents")
            st = self._status.get("scanner")
            cal_st = self._status.get("calendar")
        if extra_rows:
            scan = {**scan, "rows": {**(scan.get("rows") or {}), **extra_rows}}
        watch = self.scan.watchlist() if watch is None else watch
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
        # Nasdaq's pre-market read, and the wide read's for any name Nasdaq has not
        # answered for today (UniverseStore.premarket_of says why).
        premkt = dict(self.premarket.view(td))
        for s in watch:
            if s not in premkt:
                alt = self.universe.premarket_of(s, td)
                if alt is not None:
                    premkt[s] = alt
        payload = scanner_build(
            scan,
            quotes=parts["quotes"] or [],
            sectors=parts["sectors"] or [],
            calendar=parts["calendar"] or [],
            earnings=parts["scan_earn"] or [],
            wire=parts["wire"] or [],
            # Each name's own feed plus every ticker-tagged story held for it.
            news={s: [*((parts["scan_news"] or {}).get(s) or []),
                      *self.stock_news.headlines(s)] for s in watch},
            filings=parts["scan_sec"] or {},
            aliases={s: self.scan.aliases(s) for s in watch},
            own={s: self.scan.own_names(s) for s in watch},
            # The table's names are held to; a filer's first word is a guess.
            sure=scan_src.ALIASES.__contains__,
            status=st.as_dict() if st else None,
            watchlist=watch,
            clock=clock,
            options=self.options.view(),
            closes=closes,
            iv_hist={sym: self.options.history.series(sym) for sym in watch},
            premkt=premkt,
            sector_map=scan_src.SECTOR,
            daily=daily,
            shorts=self.shorts.view(),
            earn_hist=self.earnhist.view(),
            earn_next=self.earnhist.view_next(),
            flow_ctx=flow_ctx,
            context=parts["context"] or [],
            # The tape count is computed inside the build now (the Market line
            # reads it), from the constituents; the record line reads the log.
            constituents=cons if isinstance(cons, dict) else None,
            record=self.events.record_table(),
            promoted=promoted,
            pool=pool_view,
            pinned=pinned,
            top_story=self._catalyst,
            news_limit=news_limit,
            calendar_ok=bool(cal_st.ok) if cal_st is not None else None,
            news_read=self.newsread.for_item,
            news_dir=self.newsread.direction,
        )
        # Which day of a multi-day move each name is on, for the Day 2/3 preset.
        stages = self._ctx().stage
        self.universe.want_sparks(watch)
        for r in payload.get("rows") or []:
            r["stage"] = stages.get(r.get("sym"))
            self.universe.fill_spark(r)
            self._with_insiders(r)
        # No session type here (owner, 2026-11-11): the Scanner's strip carried NQ's
        # trend-or-range lean for a day, and it is a futures read on a stocks page.
        # The snapshot's `daytype` still feeds the Futures tab and the Dashboard.
        return payload

    def market_payload(self) -> dict[str, Any]:
        """The Market tab's context (marketctx.build) — computed on read, like the
        Scanner, from the scanner payload and the snapshot keys it reads."""
        scan = self.scanner_payload()
        with self._lock:
            snap: dict[str, Any] = {k: self._state.get(k) for k in (
                "quotes", "sectors", "constituents", "calendar", "rates", "fomc", "gex",
                "context")}
            snap["status"] = {k: v.as_dict() for k, v in self._status.items()}
        snap["policy_meetings"] = meetings_priced(snap["rates"] or {}, snap["fomc"] or [])
        return marketctx.build(scan, snap)


COLLECTOR = Collector()
