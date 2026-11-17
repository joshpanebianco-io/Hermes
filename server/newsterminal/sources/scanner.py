"""
The scanner's feeds — bars, headlines and filings for every name on the watchlist.

FREE, AND ENOUGH FOR THE STRATEGY. Yahoo's v8 chart endpoint gives any US stock
5-minute OHLCV bars from 04:00 to 20:00 ET with no key — exactly what the Pine
script reads through `request.security(…, session.extended)` — twelve sessions
of them here (BARS_RANGE: ten prior sessions for RVOL and a spare). The
same endpoint at a daily interval gives a year of sessions for the daily ATR,
the daily frame (frame.py) and the realised earnings moves. Personal use only,
like every other Yahoo read in this terminal.

THE REQUEST BUDGET, SAID OUT LOUD. One chart request per name, rotated: the job
ticks every 15 s and refreshes at most five of the stalest names, aiming at
every name every 90 s and SPY / QQQ / IWM every 30 s while any session is on
(04:00–20:00 ET), every 15 minutes when none is. With the default 21 names that
is ~20 requests a minute in session, a few an hour overnight, and the daily
bars once per name per six hours on top. A 40-name list stretches each name's
refresh to ~3 minutes rather than raising the rate — Yahoo has no published
limit and the polite answer to that is to stay well under the unpublished one.

IN THE REGULAR SESSION, TWO MORE CLOCKS (owner, 2026-10-14: "as close to real
time as possible"). THE LIVE LAYER reads every name's last trade from the
batched spark endpoint — twelve names a request, so the default list is two
requests every five seconds, ~14 KB each — and the read path lays that trade
over the name's bars (scan.with_live), so price and everything read off it is
seconds old rather than a rotation old. THE CLOSE READ fetches every name's
bars ten seconds after each ten-minute bar closes, 09:30 to the bell, five
names a tick with the ticks a second apart, so a signal on that bar lands
within half a minute of it instead of whenever the name's turn came round.

The live layer is the first thing to give way: a failed read steps it back to
15 s, then 30 s, and a 429 on the bars stops it outright with them.

HEADLINES AND FILINGS ROTATE SLOWER. Yahoo's per-ticker RSS, ten minutes a name
(three names a minute); SEC EDGAR's submissions JSON, thirty minutes a name
(two a minute) — EDGAR asks for ten requests a second at most and a real
contact in the User-Agent, and gets two a minute and config.UA.

NOTHING HERE BLOCKS THE BOARD. These jobs run on the scanner's own thread
beside the collector's (see collector.py), so a slow tick here delays the
scanner and nothing else.

A FAILING NAME BACKS OFF, AND A 429 STOPS EVERYTHING (review, 2026-10-13). A
symbol Yahoo does not know used to fail on every 15-second tick for ever — 8
dead requests a minute, holding one of the five slots — and a rate limit was
answered at full rate. Now each failure doubles that name's wait (30 s up to 15
minutes) and an HTTP 429 pauses the whole fetcher for two minutes.
"""

from __future__ import annotations

import contextlib
import json
import os
import re
import threading
import time
import urllib.parse
from collections.abc import Callable, Iterable
from datetime import UTC, date, datetime, timedelta
from email.utils import parsedate_to_datetime
from typing import Any, NamedTuple

from .. import scan
from ..config import BROWSER_UA, CACHE_DIR, UA
from ..frame import frame_of
from ..holidays import is_trading_day
from ..http import CACHE, SourceStatus, clean_text, feed_body, fetch, json_body, rss_items
from ..scanscore import avg_day
from .earnhist import parse_edgar
from .insiders import InsiderBook, form4_refs, line_of
from .quotes import SPARK
from .wire import gnews

CHART = (
    "https://query1.finance.yahoo.com/v8/finance/chart/{sym}"
    "?range={rng}&interval={iv}&includePrePost=true"
)
YAHOO_RSS = "https://feeds.finance.yahoo.com/rss/2.0/headline?s={sym}&region=US&lang=en-US"
SEC_TICKERS = "https://www.sec.gov/files/company_tickers.json"
SEC_SUBMISSIONS = "https://data.sec.gov/submissions/CIK{cik:010d}.json"
SEC_DOC = "https://www.sec.gov/Archives/edgar/data/{cik}/{acc}/{doc}"

# The Pine scanner's ON tickers, in the script's order — then the
# names added for the same playbook (owner, 2026-10-14: "add more stocks …
# that they would recommend trading with this model").
#
# HOW THE ADDITIONS WERE CHOSEN. EllyD and PB trade on camera
# the index ETFs and the megacaps already here, and build the rest of the day
# from what is moving pre-market on news — they publish no fixed list. So the
# additions are the names that suit a level-retest options trade on numbers,
# screened 14 Oct 2026 off Yahoo dailies and Cboe's chains: $2bn+ a day
# traded (clean levels, honest pre-market), a 14-day ATR of 2.5%+ (room for a
# retest to pay the premium), the weekly at-the-money spread near 5% or under
# and tens of thousands of contracts a day near the money. MU, AVGO, ORCL and
# MSTR were on the script's own list, switched off; SMCI too, the thinnest
# of these and kept for that history. GME by name (owner, 2026-10-14: "can we
# also add gamestop") — under the dollar-volume bar at $27 a share (about
# $270m a day), but a 4.6% ATR and 130k+ contracts a day near the money,
# five cents wide. GOOGL for GOOG (same screen): one company, but the class A
# line lists four expiries inside seven days to GOOG's one and trades about
# three times the contracts — the weekly and same-day strikes live there.
# ARM and SHOP by name (owner, 2026-10-26: "can we add ARM, SHOP, SMCI" — SMCI
# was already here), not screened; both already had a sector and a logo.
DEFAULT_WATCHLIST = [
    "SPY", "QQQ", "IWM", "AMD", "SPCX", "COIN", "PLTR", "HOOD", "DELL", "IBM", "AAPL",
    "NVDA", "TSLA", "AMZN", "META", "MSFT", "GOOGL", "NFLX", "ADBE", "PYPL", "INTC",
    "MU", "AVGO", "ORCL", "MSTR", "MRVL", "SNDK", "CRWV", "NBIS", "SMCI", "GME",
    "ARM", "SHOP",
]
# Always fetched: RS is measured against SPY and QQQ, and the tape reads IWM.
BENCHMARKS = ("SPY", "QQQ", "IWM")
#: The Magnificent Seven, tracked always (owner, 2026-11-13: "why is MAG 7 only showing
#: 3... it should be showing the MAG 7"). They were all favourites, so the Stocks tab's
#: MAG7 chip had seven rows; with the favourites cleared it had the ones in play that
#: morning. Unlike the benchmarks they may still be starred as favourites.
MAG7 = ("AAPL", "MSFT", "GOOGL", "AMZN", "NVDA", "META", "TSLA")
#: What is on the list whatever the favourites and the pool say, first.
CORE = (*BENCHMARKS, *MAG7)
MAX_SYMBOLS = 40
_SYM = re.compile(r"^[A-Z0-9][A-Z0-9.\-]{0,9}$")

TICK_SEC = 15.0
ACTIVE_SEC = 90.0
#: The 5-minute download's range. Yahoo counts SESSIONS, not calendar days
#: (checked 2026-11-10: 5d → 5, 15d → 15): today, the ten prior sessions RVOL
#: reads (scan.RVOL_SESSIONS), and one spare for a half day. About 135 KB a
#: name against 50 KB for five days — well inside the budget above.
BARS_RANGE = "12d"
BENCH_SEC = 30.0
CLOSED_SEC = 900.0
MAX_PER_TICK = 5
DAILY_TTL = 6 * 3600.0
DAILY_PER_TICK = 3
#: WHO WROTE IT (owner, 2026-11-15: "i just want to make sure we have quality sources
#: for the stock related news ... the ones that we use to determine if a stock is likely
#: to trend", then "do what you recommend"). The per-ticker RSS names no author: a
#: story Yahoo hosts for a partner arrives with a finance.yahoo.com link, so four in
#: five read "Yahoo Finance" whoever wrote them. Counted that day over the 84 names:
#: 27% of the stories that scored were these, and for 25 of the 46 names with a scoring
#: story the strongest one was. Yahoo's search answer for the same ticker names the
#: outlet on every story (and the tickers it is filed under): of 156 sampled, about
#: 115 were stock-picking and screen sites (Zacks, 24/7 Wall St, TIKR, Motley Fool,
#: Trefis, Simply Wall St, GuruFocus, Insider Monkey), 11 Barron's, 8 MT Newswires,
#: 4 the company's own release. So the rows are read from the search answer, each
#: with its outlet, and catalysts.SECOND_HAND can then do to Yahoo's what it does to
#: every other feed's. The RSS is still read for the sentence it carries under a
#: headline (newsread.py), and is the rows only when the search does not answer.
YAHOO_SEARCH = ("https://query2.finance.yahoo.com/v1/finance/search?q={sym}"
                "&quotesCount=0&newsCount=40&enableFuzzyQuery=false")
#: A story filed under more tickers than this is a list, not a name's story: the rule
#: the wide scan's flow has (tvnews.MAX_RELATED).
SEARCH_MAX_RELATED = 3
#: ONE COMPANY, SEVERAL TICKERS. Yahoo files every Alphabet story under GOOG and its
#: own "GOOGN", never GOOGL: on the first live pass (2026-11-15) not one of GOOGL's 36
#: stories was "its own" by the ticker rule, so the name fell back to the RSS and its
#: stories carried no outlet. A story under a share class of the name is the name's.
SHARE_CLASSES: dict[str, frozenset[str]] = {
    "GOOGL": frozenset({"GOOG", "GOOGN"}), "GOOG": frozenset({"GOOGL", "GOOGN"}),
    "BRK-B": frozenset({"BRK-A"}), "BRK-A": frozenset({"BRK-B"}),
    "FOXA": frozenset({"FOX"}), "FOX": frozenset({"FOXA"}),
    "NWSA": frozenset({"NWS"}), "NWS": frozenset({"NWSA"}),
}
#: Yahoo's spelling of an outlet → the one the terminal prints.
OUTLETS: dict[str, str] = {
    "barrons.com": "Barron's", "barron's": "Barron's",
    "investor's business daily": "IBD", "business wire": "BusinessWire",
    "the wall street journal": "WSJ", "associated press finance": "AP",
    "24/7 wall st.": "24/7 Wall St", "simply wall st.": "Simply Wall St",
    "gurufocus.com": "GuruFocus", "the motley fool": "Motley Fool",
    "investing.com": "Investing.com", "thestreet.com": "TheStreet",
}
NEWS_SEC = 600.0
NEWS_PER_TICK = 3
#: After a restart, names never read get a catch-up of this many a tick, so the
#: whole list has its headlines in about two minutes rather than seven — a
#: game plan generated just after a restart was otherwise written blind.
NEWS_PER_TICK_COLD = 10
SEC_SEC = 1800.0
#: Four a minute since 2026-11-13, when the Today list's names joined the list's own
#: (`sec_extra`): about seventy names, each read every half hour (SEC_SEC). The SEC
#: allows ten requests a second.
SEC_PER_TICK = 4
#: Form 4 documents read a tick (a minute): the SEC asks for under ten requests a second,
#: and a month's backlog for the list is a few hundred.
FORM4_PER_TICK = 8


def _form4_body(body: bytes) -> str | None:
    head = body[:4000].decode("utf-8", errors="replace")
    return None if "<ownershipDocument" in head else "not a Form 4"
FILING_DAYS = 3
BACKOFF_BASE = 30.0
BACKOFF_MAX = 15 * 60.0
RATE_LIMIT_PAUSE = 120.0
#: The live layer's clock in the regular session, its steps back after a
#: failed read (reset by the next good one), and its idle check outside it.
LIVE_SEC = 5.0
LIVE_BACKOFF = (15.0, 30.0)
LIVE_IDLE_SEC = 30.0
#: Names per batched read — the board's chunk (sources/quotes.py), well inside
#: the twenty the endpoint accepts.
LIVE_CHUNK = 12
#: A ten-minute bar's last prints take a moment to reach Yahoo's bars — the
#: same wait scan.technicals makes before it calls a bar confirmed.
CLOSE_LAG = float(scan.CLOSE_LAG_SEC)
#: While a close is being read the bars job comes back this soon.
BURST_TICK_SEC = 1.0
#: Names that left the list during a day and still have signals to settle
#: (`ScanStore.read_owed`): how many are read a tick, and how long one that could
#: not be read waits before it is asked for again.
OWED_PER_TICK = 2
OWED_RETRY_SEC = 6 * 3600.0


class LiveQuote(NamedTuple):
    price: float
    at: int  # epoch of the trade


def backoff(failures: int) -> float:
    """Seconds to wait after the n-th failure in a row: 30, 60, 120 … 900. Pure."""
    return min(BACKOFF_MAX, BACKOFF_BASE * 2 ** max(0, failures - 1))

WATCHLIST_FILE = os.path.join(CACHE_DIR, "scanner_watchlist.json")
#: Names off the list a chart was opened on: how often each may be read, how many are held.
ADHOC_SEC = 60.0
ADHOC_MAX = 40

# Ticker → the S&P sector SPDR it trades with. A static table because the
# iShares holdings file the constituents panel reads is not reliably served
# (it has come back as an HTML page), and a wrong sector is worse than none —
# an unknown name gets null and simply earns no sector tailwind.
SECTOR: dict[str, str] = {
    **dict.fromkeys(
        ["AAPL", "MSFT", "NVDA", "AMD", "INTC", "AVGO", "MU", "ORCL", "CRM", "ADBE", "IBM",
         "DELL", "SMCI", "ARM", "PLTR", "QCOM", "TXN", "CSCO", "NOW", "AMAT", "LRCX", "KLAC",
         "MRVL", "PANW", "CRWD", "SNOW", "ANET", "TSM", "SHOP", "MSTR", "ASML", "HPE", "HPQ",
         "NET", "DDOG", "ZS", "INTU", "ON", "ADI", "NXPI", "WDC", "STX", "APP", "IONQ",
         "SNDK", "CRWV", "NBIS"], "XLK"),
    **dict.fromkeys(
        ["META", "GOOG", "GOOGL", "NFLX", "DIS", "T", "VZ", "TMUS", "RDDT", "SPOT", "CMCSA",
         "SNAP", "PINS", "WBD", "ROKU", "TTD"], "XLC"),
    **dict.fromkeys(
        ["AMZN", "TSLA", "HD", "NKE", "MCD", "SBUX", "ABNB", "BKNG", "LULU", "RIVN", "GM", "F",
         "LOW", "TJX", "CMG", "DASH", "LCID", "NIO", "CVNA", "DKNG", "GME"], "XLY"),
    **dict.fromkeys(
        ["COIN", "HOOD", "PYPL", "SOFI", "JPM", "GS", "BAC", "V", "MA", "XYZ", "SQ", "C", "WFC",
         "MS", "SCHW", "AFRM", "UPST", "AXP", "BLK", "BRK.B", "BRK-B"], "XLF"),
    **dict.fromkeys(["XOM", "CVX", "OXY", "COP", "SLB", "HAL", "DVN", "EOG", "MPC"], "XLE"),
    **dict.fromkeys(
        ["LLY", "UNH", "JNJ", "PFE", "MRK", "ABBV", "NVO", "HIMS", "AMGN", "MRNA", "ISRG",
         "TMO", "CVS"], "XLV"),
    **dict.fromkeys(
        ["SPCX", "BA", "CAT", "GE", "UBER", "RTX", "LMT", "DAL", "UPS", "FDX", "DE", "HON",
         "UAL", "AAL", "NOC", "GD", "RKLB"], "XLI"),
    **dict.fromkeys(["WMT", "COST", "KO", "PEP", "PG", "TGT", "PM", "MO", "KR"], "XLP"),
    **dict.fromkeys(["NEE", "VST", "CEG", "SO", "DUK", "NRG", "OKLO", "SMR"], "XLU"),
    **dict.fromkeys(["FCX", "LIN", "NEM", "MP", "AA", "CLF", "DOW"], "XLB"),
    **dict.fromkeys(["PLD", "AMT", "EQIX", "O", "SPG"], "XLRE"),
    # Big caps that seldom sit on a watchlist but whose reports move their
    # sector — here so a name's sector peers (scanscore.peers_for) can find
    # them on the earnings calendar. Unambiguous GICS sectors only.
    **dict.fromkeys(
        ["ACN", "CDNS", "SNPS", "FTNT", "APH", "GLW", "TEL"], "XLK"),
    **dict.fromkeys(["CHTR", "EA", "TTWO"], "XLC"),
    **dict.fromkeys(
        ["ORLY", "AZO", "MAR", "HLT", "RCL", "CCL", "YUM", "EBAY", "ROST"], "XLY"),
    **dict.fromkeys(
        ["PGR", "TRV", "CB", "AIG", "ALL", "MET", "PNC", "USB", "TFC", "COF", "BK", "BNY",
         "MMC", "MRSH", "AON", "CME", "ICE", "SPGI", "MCO"], "XLF"),
    # TRGP, CQP and EE move gas for a living: TradingView files them with the gas utilities.
    **dict.fromkeys(["PSX", "VLO", "KMI", "WMB", "OKE", "BKR", "TRGP", "CQP", "EE"], "XLE"),
    **dict.fromkeys(
        ["ABT", "DHR", "ELV", "CI", "BMY", "GILD", "VRTX", "REGN", "MDT", "SYK", "BSX", "ZTS",
         "HCA", "MCK"], "XLV"),
    **dict.fromkeys(
        ["UNP", "CSX", "NSC", "MMM", "ETN", "PH", "ITW", "EMR", "WM", "GEV", "PWR", "FAST"],
        "XLI"),
    **dict.fromkeys(["MDLZ", "CL", "KMB", "GIS", "MNST", "KDP", "STZ", "KHC"], "XLP"),
    **dict.fromkeys(["AEP", "D", "EXC", "SRE", "PCG"], "XLU"),
    **dict.fromkeys(["SHW", "APD", "ECL", "NUE"], "XLB"),
    **dict.fromkeys(["WELL", "PSA", "CCI", "DLR"], "XLRE"),
}

# How the wire writes a company, for matching headlines that do not carry the
# cashtag. Proper nouns only — see scanscore.news_for.
ALIASES: dict[str, list[str]] = {
    "AAPL": ["Apple"], "MSFT": ["Microsoft"], "NVDA": ["Nvidia", "NVIDIA"],
    "AMD": ["AMD", "Advanced Micro"], "INTC": ["Intel"], "AMZN": ["Amazon"],
    "TSLA": ["Tesla"], "META": ["Meta", "Facebook"],
    "GOOG": ["Alphabet", "Google"], "GOOGL": ["Alphabet", "Google"], "NFLX": ["Netflix"],
    "ADBE": ["Adobe"], "PYPL": ["PayPal"], "IBM": ["IBM"], "DELL": ["Dell"],
    "PLTR": ["Palantir"], "HOOD": ["Robinhood"], "COIN": ["Coinbase"], "SPCX": ["SpaceX"],
    "AVGO": ["Broadcom"], "MU": ["Micron"], "ORCL": ["Oracle"], "CRM": ["Salesforce"],
    "SMCI": ["Super Micro", "Supermicro"], "ARM": ["Arm Holdings"], "UBER": ["Uber"],
    "MSTR": ["MicroStrategy"], "SOFI": ["SoFi"], "TSM": ["TSMC", "Taiwan Semiconductor"],
    "JPM": ["JPMorgan"],
    "GS": ["Goldman Sachs"], "BA": ["Boeing"], "WMT": ["Walmart"], "COST": ["Costco"],
    # How the headlines write them too (2026-11-13): "Lilly Raises Guidance" and
    # "ExxonMobil Beats" named no company the table knew. Not "Goldman" or "JP Morgan"
    # alone: those are the banks' analysts in every other company's headline.
    "DIS": ["Disney"], "XOM": ["Exxon", "ExxonMobil"], "LLY": ["Eli Lilly", "Lilly"],
    "UNH": ["UnitedHealth"],
    "MRVL": ["Marvell"], "SNDK": ["Sandisk", "SanDisk"], "CRWV": ["CoreWeave"],
    "NBIS": ["Nebius"], "GME": ["GameStop"], "SHOP": ["Shopify"],
}
#: Words a company's OWN feed calls it that are too common to match on the wire:
#: MicroStrategy trades as "Strategy" now, and Arm's headlines say "Arm". Read with
#: the aliases for whose story a headline is (catalysts.about), never for the wire's
#: match, where "Strategy shift at the Fed" would land under MSTR.
OWN_WORDS: dict[str, list[str]] = {"MSTR": ["Strategy"], "ARM": ["Arm"]}

# EDGAR form types worth a line under a stock. Form 4 (insider trades) and 144
# are left out: there are dozens a week on a megacap and they almost never move
# a session.
FORMS = ("8-K", "8-K/A", "10-Q", "10-K", "6-K", "20-F", "S-1", "S-1/A", "S-3", "S-3ASR",
         "F-1", "F-3", "424B1", "424B2", "424B3", "424B4", "424B5", "SC 13D", "SC 13G",
         "SC 13D/A", "SCHEDULE 13D", "SCHEDULE 13G")
ITEMS_8K = {
    "1.01": "material agreement", "1.02": "agreement terminated", "1.03": "bankruptcy",
    "2.01": "acquisition or disposition", "2.02": "results of operations",
    "2.03": "new obligation", "2.05": "restructuring costs", "2.06": "impairment",
    "3.01": "listing notice", "3.02": "unregistered equity sale", "4.01": "auditor change",
    "5.01": "change of control", "5.02": "officer / director change",
    "5.03": "bylaws amended", "5.07": "shareholder vote", "7.01": "Reg FD disclosure",
    "8.01": "other events", "9.01": "exhibits",
}


# ------------------------------------------------------------------ watchlist


def clean_watchlist(raw: Iterable[Any]) -> tuple[list[str], list[str]]:
    """User input → (valid upper-case unique symbols, rejected). Pure.

    A–Z, 0–9, `.` and `-`, ten characters at most, forty symbols at most — the
    rest come back as rejected rather than vanishing, so the editor can say
    which entries it did not take.
    """
    ok: list[str] = []
    bad: list[str] = []
    for item in raw:
        s = str(item or "").strip().upper().lstrip("$")
        if not s:
            continue
        if not _SYM.match(s):
            bad.append(s)
        elif s in ok:
            continue
        elif len(ok) >= MAX_SYMBOLS:
            bad.append(s)
        else:
            ok.append(s)
    return ok, bad


def load_watchlist(path: str = WATCHLIST_FILE) -> list[str]:
    try:
        with open(path, encoding="utf-8") as f:
            doc = json.load(f)
        syms, _ = clean_watchlist(doc.get("symbols") or [])
        return syms or list(DEFAULT_WATCHLIST)
    except (OSError, ValueError, AttributeError):
        return list(DEFAULT_WATCHLIST)


def save_watchlist(
    symbols: Iterable[Any], path: str = WATCHLIST_FILE
) -> tuple[list[str], list[str]]:
    ok, bad = clean_watchlist(symbols)
    if not ok:
        return load_watchlist(path), bad
    tmp = path + ".tmp"
    try:
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump({"symbols": ok, "saved_utc": datetime.now(UTC).isoformat()}, f)
        os.replace(tmp, path)
    except OSError:
        pass
    return ok, bad


# --------------------------------------------------------------------- parsing


def _last_close_mark(now: datetime) -> float:
    """Epoch of the most recent weekday 16:20 ET at or before `now`. Pure."""
    et_now = now.astimezone(scan.ET)
    d = et_now.date()
    while True:
        mark = datetime(d.year, d.month, d.day, 16, 20, tzinfo=scan.ET)
        if d.weekday() < 5 and mark <= et_now:
            return mark.timestamp()
        d -= timedelta(days=1)


#: Minutes of the ET day the daily bars are read again once the bell has rung, so
#: today's row is held: its open is the official print, where the first 5-minute
#: bar's is only the first trade Yahoo's bars caught (scan.technicals). Twice,
#: because a name that opens late has no official open at the first.
OPEN_MARKS: tuple[int, ...] = (scan.RTH_START + 3, scan.RTH_START + 35)


def _last_open_mark(now: datetime) -> float:
    """Epoch of today's newest open mark at or before `now`; 0.0 when there is none
    (not a trading day, or before the first). Pure."""
    et_now = now.astimezone(scan.ET)
    d = et_now.date()
    if not is_trading_day(d):
        return 0.0
    m = et_now.hour * 60 + et_now.minute
    done = [x for x in OPEN_MARKS if x <= m]
    if not done:
        return 0.0
    return datetime(d.year, d.month, d.day, done[-1] // 60, done[-1] % 60,
                    tzinfo=scan.ET).timestamp()


def _in_session_close(close: float) -> bool:
    """Is the ten-minute bar that closed at epoch `close` one the close read
    covers — 09:30 (the pre-market's last, which fixes PMH / PML) to the bell?"""
    dt = datetime.fromtimestamp(close, scan.ET)
    d, m = dt.date(), dt.hour * 60 + dt.minute
    return is_trading_day(d) and scan.RTH_START <= m <= scan.rth_end(d)


def close_mark(now: datetime) -> float | None:
    """When the newest finished ten-minute bar's prints are all in — its close +
    CLOSE_LAG — or None when that bar is outside the session. Pure.

    Any name whose bars were read before this mark is due for the close read.
    """
    t = now.timestamp()
    close = t - t % scan.BAR_SEC
    if t - close < CLOSE_LAG:
        close -= scan.BAR_SEC
    return close + CLOSE_LAG if _in_session_close(close) else None


def next_mark_in(now: datetime) -> float | None:
    """Seconds to the next close mark, or None when that close is outside the session. Pure."""
    t = now.timestamp()
    close = t - t % scan.BAR_SEC
    if t >= close + CLOSE_LAG:
        close += scan.BAR_SEC
    return close + CLOSE_LAG - t if _in_session_close(close) else None


def parse_live(doc: Any, names: dict[str, str], day: date) -> dict[str, LiveQuote]:
    """A spark response → {symbol: its last regular-session trade on `day`}. Pure.

    `names` maps Yahoo's spelling back to the watchlist's (BRK-B → BRK.B). A
    quote stamped outside `day`'s regular session is dropped: before the open
    `regularMarketPrice` is yesterday's close, and after it the official close —
    neither is a live trade.
    """
    out: dict[str, LiveQuote] = {}
    rows = ((doc or {}).get("spark") or {}).get("result") if isinstance(doc, dict) else None
    for row in rows or []:
        try:
            meta = (row.get("response") or [None])[0]["meta"]
            sym = names[row["symbol"]]
            px, at = float(meta["regularMarketPrice"]), int(meta["regularMarketTime"])
        except (KeyError, IndexError, TypeError, ValueError, AttributeError):
            continue
        dt = datetime.fromtimestamp(at, scan.ET)
        m = dt.hour * 60 + dt.minute
        if dt.date() == day and scan.RTH_START <= m < scan.rth_end(day) and px > 0:
            out[sym] = LiveQuote(px, at)
    return out


def _yahoo(sym: str) -> str:
    """BRK.B is BRK-B to Yahoo."""
    return sym.replace(".", "-")


def _decode(body: bytes | None) -> str:
    """Yahoo's RSS is UTF-8 except when a cp1252 apostrophe slips into a summary."""
    if not body:
        return ""
    try:
        return body.decode("utf-8")
    except UnicodeDecodeError:
        return body.decode("cp1252", errors="replace")


def _when(raw: str) -> datetime | None:
    if not raw:
        return None
    try:
        d = parsedate_to_datetime(raw)
        return d if d.tzinfo else d.replace(tzinfo=UTC)
    except (TypeError, ValueError, IndexError):
        return None


# Yahoo's per-ticker feed syndicates other outlets; the link's host says whose
# story it is, which is the attribution a reader actually wants.
PUBLISHERS = {
    "fool.com": "Motley Fool", "finance.yahoo.com": "Yahoo Finance", "investors.com": "IBD",
    "barrons.com": "Barron's", "marketwatch.com": "MarketWatch", "bloomberg.com": "Bloomberg",
    "reuters.com": "Reuters", "cnbc.com": "CNBC", "benzinga.com": "Benzinga",
    "zacks.com": "Zacks", "insidermonkey.com": "Insider Monkey", "simplywall.st": "Simply Wall St",
    "gurufocus.com": "GuruFocus", "investopedia.com": "Investopedia", "thestreet.com": "TheStreet",
    "seekingalpha.com": "Seeking Alpha", "axios.com": "Axios", "wsj.com": "WSJ",
    "businessinsider.com": "Business Insider", "fortune.com": "Fortune", "ft.com": "FT",
    "techcrunch.com": "TechCrunch", "theverge.com": "The Verge", "investing.com": "Investing.com",
    "stocktwits.com": "Stocktwits", "247wallst.com": "24/7 Wall St",
}


def publisher_of(url: str, default: str) -> str:
    """The outlet behind a syndicated link. Pure."""
    host = (urllib.parse.urlsplit(url).hostname or "").lower().removeprefix("www.")
    for dom, name in PUBLISHERS.items():
        if host == dom or host.endswith("." + dom):
            return name
    return default


def mentions(title: str, sym: str, names: list[str]) -> bool:
    """Does a headline from the ticker's own feed actually concern it? Pure.

    YAHOO'S PER-TICKER FEED IS NOT PER-TICKER. NVDA's carried Motley Fool pieces
    on Eli Lilly and Generac (observed 2026-10-13) — anything that tags the
    symbol anywhere. The title has to name the ticker or the company.
    """
    if re.search(rf"\b{re.escape(sym)}\b", title):
        return True
    return any(re.search(rf"\b{re.escape(n)}\b", title, re.I) for n in names if n)


def mend(title: str) -> str:
    """Yahoo's feed sometimes carries U+FFFD where a curly quote was — it arrives
    already broken, so there is nothing to decode back. Between letters it was an
    apostrophe; between spaces, a dash. Pure."""
    if "�" not in title:
        return title
    title = re.sub(r"(?<=\w)�(?=\w)", "’", title)
    title = title.replace(" � ", " — ")
    return title.replace("�", "")


def parse_news(xml: str, publisher: str = "Yahoo Finance") -> list[dict[str, Any]]:
    """A per-ticker RSS feed → headline rows. Pure.

    Google News titles end " - Publisher", which becomes the attribution.
    """
    out: list[dict[str, Any]] = []
    for r in rss_items(xml, limit=40):
        title = mend(r["title"].strip())
        if not title:
            continue
        pub = publisher
        m = re.search(r"\s+-\s+([A-Z][A-Za-z0-9.&' ]{1,40})$", title)
        if publisher == "Google News" and m:
            pub = m.group(1).strip()
            title = title[: m.start()].strip()
        when = _when(r["date"])
        if publisher != "Google News":
            pub = publisher_of(r["link"], publisher)
        row: dict[str, Any] = {
            "title": title,
            "url": r["link"],
            "publisher": pub,
            "utc": when.astimezone(UTC).isoformat() if when else None,
            "ts": when.timestamp() if when else None,
        }
        # The feed's sentence or two, kept for the model's read of a major story
        # (newsread.py). It never reaches a row: scanscore.news_for copies what it names.
        # A Google News "summary" is markup listing other outlets, as on the wire.
        summary = (r.get("summary") or "").strip()
        if publisher != "Google News" and len(summary) >= 40 and summary != title:
            row["summary"] = summary[:320]
        out.append(row)
    return out


def outlet(name: Any) -> str:
    """An outlet as Yahoo spells it, in the terminal's spelling. Pure."""
    raw = " ".join(str(name or "").split())
    return OUTLETS.get(raw.lower(), raw) or "Yahoo Finance"


def _link_key(url: Any) -> str:
    """A story's address without what a feed appends to it ("?.tsrc=rss")."""
    return str(url or "").split("?", 1)[0].rstrip("/").lower()


def search_ok(body: bytes) -> str | None:
    """A search answer that carries stories. Yahoo now and then answers 200 with an
    empty list for a name it had forty stories for a minute before (AMZN, twice on
    2026-11-15): kept as an answer, that empty list was the name's news for nine
    minutes. Refused here, it is never written over the last good copy and the name
    is asked again."""
    bad = json_body(body)
    if bad:
        return bad
    try:
        doc = json.loads(body)
    except ValueError as e:
        return f"not JSON: {e}"
    return None if isinstance(doc, dict) and doc.get("news") else "no stories in the answer"


def parse_search(doc: Any, sym: str) -> list[dict[str, Any]]:
    """Yahoo's search answer for a ticker → headline rows, each with the outlet that
    wrote it. Pure.

    Left out: a video, a story filed under more than SEARCH_MAX_RELATED tickers (a
    list), and a story Yahoo files under other tickers and not this one, which is
    another company's ("StoneCo Ltd. (STNE) Q3 Earnings Lag Estimates" stood under BZ
    on the RSS, which says nothing of whose a story is).
    """
    own = _yahoo(sym).upper()
    mine = {own} | SHARE_CLASSES.get(own, frozenset())
    out: list[dict[str, Any]] = []
    for n in (doc or {}).get("news") or [] if isinstance(doc, dict) else []:
        if not isinstance(n, dict) or str(n.get("type") or "STORY").upper() != "STORY":
            continue
        title = mend(str(n.get("title") or "").strip())
        link = str(n.get("link") or "")
        if not title or not link:
            continue
        tickers = {str(x).upper() for x in n.get("relatedTickers") or []}
        # Counted as companies, not tickers: a share class of this one is this one.
        if tickers and (not tickers & mine or len(tickers - mine) >= SEARCH_MAX_RELATED):
            continue
        ts = n.get("providerPublishTime")
        when = (datetime.fromtimestamp(float(ts), UTC)
                if isinstance(ts, int | float) and not isinstance(ts, bool) else None)
        out.append({
            "title": title, "url": link, "publisher": outlet(n.get("publisher")),
            "utc": when.isoformat() if when else None,
            "ts": when.timestamp() if when else None,
        })
    return out


def with_summaries(named: list[dict[str, Any]], rss: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """The rows that name their outlet, each with the sentence the RSS carries under
    the same story (matched by its address, else its headline). Pure."""
    by_link = {_link_key(r.get("url")): r.get("summary") for r in rss if r.get("summary")}
    by_title = {str(r.get("title")): r.get("summary") for r in rss if r.get("summary")}
    out: list[dict[str, Any]] = []
    for r in named:
        summary = by_link.get(_link_key(r.get("url"))) or by_title.get(str(r.get("title")))
        out.append({**r, "summary": summary} if summary else r)
    return out


def parse_filings(doc: Any, cik: int, today: date, days: int = FILING_DAYS) -> list[dict[str, Any]]:
    """EDGAR submissions JSON → the last few days' filings worth a line. Pure."""
    try:
        r = doc["filings"]["recent"]
        forms = r["form"]
    except (KeyError, TypeError):
        return []
    cutoff = today - timedelta(days=days)
    out: list[dict[str, Any]] = []
    for i, form in enumerate(forms):
        try:
            filed = date.fromisoformat(r["filingDate"][i])
        except (ValueError, IndexError, KeyError, TypeError):
            continue
        if filed < cutoff:
            break  # newest first, so nothing after this is recent
        if form not in FORMS:
            continue
        items = (r.get("items") or [""] * len(forms))[i] or ""
        desc = r.get("primaryDocDescription", [""] * len(forms))[i] or ""
        if form.startswith("8-K") and items:
            named = [ITEMS_8K.get(x.strip(), "") for x in items.split(",")]
            named = [n for n in named if n and n != "exhibits"]
            desc = ", ".join(named) or desc
        acc = str(r["accessionNumber"][i])
        doc_name = r.get("primaryDocument", [""] * len(forms))[i] or ""
        accepted = (r.get("acceptanceDateTime") or [None] * len(forms))[i]
        out.append({
            "form": form,
            "filed": accepted or filed.isoformat(),
            "desc": clean_text(desc) or form,
            "url": SEC_DOC.format(cik=cik, acc=acc.replace("-", ""), doc=doc_name),
        })
    return out


# ---------------------------------------------------------------------- store


class ScanStore:
    """The scanner's memory between ticks: bars, daily bars, headlines, filings.

    Written only by the collector thread; the watchlist is the one thing the API
    thread changes, so it alone sits behind a lock.
    """

    def __init__(self, watchlist_path: str = WATCHLIST_FILE,
                 core: Iterable[str] = BENCHMARKS) -> None:
        self._lock = threading.Lock()
        self._path = watchlist_path
        #: On the list first, whatever the favourites and the pool say: the
        #: benchmarks, and in the collector the MAG 7 too (CORE).
        self.core: tuple[str, ...] = tuple(core)
        self._watch = load_watchlist(watchlist_path)
        #: Today's promotions from the pool (sources/pool.py): the day they are
        #: for, the names, and the sector the pool gave each. Behind the lock
        #: with the pinned list; `watchlist()` is the union the jobs fetch.
        self._promoted: list[str] = []
        self._promoted_day: date | None = None
        #: The favourites the pool chose for `_promoted_day` (pool.FAV_SLOTS), or None.
        self._favs: list[str] | None = None
        self.pool_sectors: dict[str, str] = {}
        self.bars: dict[str, list[scan.Bar]] = {}
        self.meta: dict[str, dict[str, Any]] = {}
        self.fetched: dict[str, float] = {}
        self.errors: dict[str, str] = {}
        self.daily: dict[str, list[scan.DayBar]] = {}
        self.daily_at: dict[str, float] = {}
        self.news: dict[str, list[dict[str, Any]]] = {}
        self.news_at: dict[str, float] = {}
        self.filings: dict[str, list[dict[str, Any]]] = {}
        self.filings_at: dict[str, float] = {}
        #: Each name's Form 4s of the last month, and the ones read (sources/insiders.py).
        self.form4_refs: dict[str, list[dict[str, Any]]] = {}
        self.insider_book = InsiderBook()
        #: Each name's results releases, from the same read (sources/earnhist.parse_edgar).
        self.reports: dict[str, list[dict[str, Any]]] = {}
        #: More names for the SEC job to read, set by the collector (`tick_sec`).
        self.sec_extra: Callable[[], Iterable[str]] | None = None
        self.ciks: dict[str, int] = {}
        self.sec_names: dict[str, str] = {}
        #: Per-symbol failures in a row and when it may be tried again (epoch).
        self.fails: dict[str, tuple[int, float]] = {}
        self.daily_fails: dict[str, tuple[int, float]] = {}
        #: Yahoo said 429 — nothing is fetched before this (epoch).
        self.pause_until = 0.0
        #: Each name's last regular-session trade (the live layer), and how many
        #: live reads have failed in a row.
        self.live: dict[str, LiveQuote] = {}
        self.live_fails = 0
        #: Names still owed the current close read — the bars job comes back
        #: BURST_TICK_SEC later while this is non-zero.
        self.burst_left = 0
        self._warm = False
        #: The live stream (sources/stream.py), when the collector has one.
        self.stream: Any = None
        #: Names off the list read on request, and when (`ensure_adhoc`).
        self.adhoc: dict[str, float] = {}
        #: Names off the list read so a finished day could be settled, and when each
        #: was last asked for (`read_owed`).
        self.owed: set[str] = set()
        self.owed_tried: dict[str, float] = {}
        #: Today's pre-market (high, low) for a name from a read that is not these
        #: bars, when the collector has one (`pm_wide`): set by the collector.
        self.pm_hint: Callable[[str, date], tuple[float | None, float | None] | None] | None = None
        #: The widest such range seen for each name today, and the day it is for.
        self.pm_seen: dict[str, tuple[date, float | None, float | None]] = {}

    def pm_wide(self, sym: str, td: date) -> tuple[float | None, float | None] | None:
        """Trading day `td`'s pre-market (high, low) for `sym` from the second read,
        for `scan.technicals` to widen the bars' range with, or None.

        THE WIDEST SEEN THAT DAY IS KEPT. A pre-market range only grows until it
        locks at 09:30, so a later read that reaches less far (the screener's
        columns rolling, a name dropping out of one read) or no read at all must
        not narrow a level the day's signals have already been read against.
        """
        got = self.pm_hint(sym, td) if self.pm_hint is not None else None
        day, hi, lo = self.pm_seen.get(sym, (td, None, None))
        if day != td:
            hi = lo = None
        if got is not None:
            h, low = got
            if h is not None and h > 0 and (hi is None or h > hi):
                hi = h
            if low is not None and low > 0 and (lo is None or low < lo):
                lo = low
        if hi is None and lo is None:
            return None
        self.pm_seen[sym] = (td, hi, lo)
        return hi, lo

    # ---- watchlist ----------------------------------------------------------

    def pinned(self) -> list[str]:
        """The owner's FAVOURITES — what the editor edits and the stars show.

        THE BENCHMARKS ARE NOT FAVOURITES (owner, 2026-11-13: "change pinned name to
        favourites and lets reset it so nothing is favourited"). SPY, QQQ and IWM are
        on the list always (`watchlist` puts them first: the masthead, the regime, the
        Today list and the market overview read their rows), so a list with nothing
        favourited is the three of them, and none of them is anyone's favourite."""
        with self._lock:
            return [s for s in self._watch if s not in BENCHMARKS]

    def watchlist(self, now: datetime | None = None) -> list[str]:
        """What the jobs fetch: the core (the benchmarks and the MAG 7), the
        favourites, then today's promotions from the pool, inside MAX_SYMBOLS.
        Promotions for another day are not today's — the scanner's day rolls at 20:00
        (scan.clock_at) and the list rolls with it, whether or not the pool has ticked
        since."""
        td = scan.clock_at(now or datetime.now(UTC)).trading_day
        with self._lock:
            favs = [s for s in self._watch if s not in self.core]
            if self._promoted_day == td and self._favs is not None:
                # The favourites the pool chose for today (pool.FAV_SLOTS); the other
                # favourites sit the day out (2026-11-13, the Today list).
                keep = set(self._favs)
                favs = [s for s in favs if s in keep]
            pinned = list(self.core) + favs
            if self._promoted_day != td:
                return pinned
            room = max(0, MAX_SYMBOLS - len(pinned))
            return pinned + [s for s in self._promoted if s not in pinned][:room]

    def tracked_favourites(self) -> list[str] | None:
        """The pins tracked today, or None while every pin is."""
        with self._lock:
            return list(self._favs) if self._favs is not None else None

    def set_promoted(self, day: date | None, symbols: Iterable[str],
                     sectors: dict[str, str] | None = None,
                     favs: Iterable[str] | None = None) -> bool:
        """Replace the promotions, and the favourites tracked that day (None: every pin).
        True when they changed."""
        syms = [s for s in symbols if _SYM.match(s)]
        fav_l = [s for s in favs if _SYM.match(s)] if favs is not None else None
        with self._lock:
            before = (self._promoted_day, list(self._promoted), self._favs)
            self._promoted, self._promoted_day, self._favs = syms, day, fav_l
            self.pool_sectors = dict(sectors or {})
        return before != (day, syms, fav_l)

    def set_watchlist(self, symbols: Iterable[Any]) -> tuple[list[str], list[str]]:
        """Replace the favourites; the benchmarks stay at the head of the stored list.

        NOTHING FAVOURITED IS A LIST (2026-11-13). An empty list was refused and kept
        the old one, so the favourites could never be cleared; now it clears them. A
        list in which every entry was invalid is still refused: that is a typo, not a
        wish for no favourites. Answers (the favourites saved, the entries rejected)."""
        ok, bad = clean_watchlist(symbols)
        if not ok and bad:
            return self.pinned(), bad
        favs = [s for s in ok if s not in BENCHMARKS][: MAX_SYMBOLS - len(BENCHMARKS)]
        saved, _ = save_watchlist([*BENCHMARKS, *favs], self._path)
        with self._lock:
            self._watch = saved
        return [s for s in saved if s not in BENCHMARKS], bad

    def symbols(self) -> list[str]:
        w = self.watchlist()
        return w + [b for b in BENCHMARKS if b not in w]

    # ---- bars ---------------------------------------------------------------

    def _warm_start(self) -> None:
        """Load whatever the disk cache holds so a restart paints at once; the
        rotation then refreshes it by staleness like anything else."""
        self._warm = True
        now = time.time()
        for sym in self.symbols():
            for kind in ("5m", "1d"):
                # The daily copy is keyed by its range: "1y" since 2026-10-22,
                # so a three-month copy on disk is never served as a year.
                key = f"scan{kind}_{sym}" if kind == "5m" else f"scan1y_{sym}"
                blob, age = CACHE.read(key), CACHE.age_sec(key)
                if blob is None or age is None:
                    continue
                try:
                    doc = json.loads(blob)
                except ValueError:
                    continue
                if kind == "5m":
                    bars, meta = scan.parse_chart(doc)
                    if bars:
                        self.bars[sym], self.meta[sym], self.fetched[sym] = bars, meta, now - age
                else:
                    days = scan.parse_daily(doc)
                    if days:
                        self.daily[sym], self.daily_at[sym] = days, now - age

    def _failed(self, book: dict[str, tuple[int, float]], sym: str, status: int | None,
                t: float) -> None:
        """Count a failure: back the name off, and pause everything on a 429."""
        n = book.get(sym, (0, 0.0))[0] + 1
        book[sym] = (n, t + backoff(n))
        if status == 429:
            self.pause_until = max(self.pause_until, t + RATE_LIMIT_PAUSE)

    def _fetch_bars(self, sym: str, fresh: bool = False) -> str | None:
        """`fresh` skips the ten-second cache: the close read needs bars read
        after the mark, and a copy cached five seconds before it is not that."""
        url = CHART.format(sym=urllib.parse.quote(_yahoo(sym)), rng=BARS_RANGE, iv="5m")
        r = fetch(url, key=f"scan5m_{sym}", ttl_sec=0.0 if fresh else 10.0, ua=BROWSER_UA,
                  timeout=15, stale_max_sec=900.0, validate=json_body)
        if not r.ok or r.source == "stale":
            self._failed(self.fails, sym, r.status, time.time())
        else:
            self.fails.pop(sym, None)
        if not r.ok:
            if r.status == 404:
                return "Yahoo does not know this symbol (HTTP 404)"
            return r.error or "unavailable"
        try:
            bars, meta = scan.parse_chart(r.json())
        except ValueError as e:
            return f"unparseable: {e}"
        if not bars:
            return "no bars"
        self.bars[sym], self.meta[sym] = bars, meta
        self.fetched[sym] = time.time() - (r.age_min or 0.0) * 60.0
        return None if r.source != "stale" else f"stale: {r.error}"

    def bars_1m(self, sym: str) -> tuple[list[scan.Bar], str | None]:
        """Two sessions of one-minute bars for the chart's 1m and 3m views.

        Fetched ON DEMAND, from the API thread, only while a chart is open on
        one of those views — never in the rotation, which the scan itself runs
        on 5-minute bars. Twenty seconds of cache keeps a chart polling every
        thirty from costing more than one request per poll, and a 429 elsewhere
        pauses this too: the chart serves its last copy instead of hitting
        Yahoo while the rotation is backing off.
        """
        key = f"scan1m_{sym}"
        if self.pause_until > time.time():
            blob = CACHE.read(key)
            if blob is None:
                return [], "Yahoo is rate-limiting — paused"
            body: bytes = blob
        else:
            url = CHART.format(sym=urllib.parse.quote(_yahoo(sym)), rng="2d", iv="1m")
            r = fetch(url, key=key, ttl_sec=20.0, ua=BROWSER_UA, timeout=12,
                      stale_max_sec=600.0, validate=json_body)
            if r.status == 429:
                self.pause_until = max(self.pause_until, time.time() + RATE_LIMIT_PAUSE)
            if not r.ok or r.body is None:
                return [], r.error or "unavailable"
            body = r.body
        try:
            bars, _meta = scan.parse_chart(json.loads(body), step=60)
        except ValueError as e:
            return [], f"unparseable: {e}"
        return bars, None if bars else "no bars"

    def _fetch_daily(self, sym: str, fresh: bool = False) -> str | None:
        # A YEAR, NOT THREE MONTHS (2026-10-22): the daily frame wants the
        # 200-day average and the 52-week extremes, and the earnings number
        # wants the last four reports' reaction days. ~27 KB a name, six-hourly.
        # `fresh` goes upstream whatever the cache holds: a copy made before a
        # mark (the close, the open) is not the one the mark asks for, and the
        # six-hour cache would otherwise hand it straight back.
        url = CHART.format(sym=urllib.parse.quote(_yahoo(sym)), rng="1y", iv="1d")
        r = fetch(url, key=f"scan1y_{sym}", ttl_sec=0.0 if fresh else DAILY_TTL, ua=BROWSER_UA,
                  timeout=15, stale_max_sec=3 * 86400.0, validate=json_body)
        # A stale copy served for a failed read backs the name off too: it is still
        # older than its mark, and would otherwise be asked for again every tick.
        if not r.ok or r.source == "stale":
            self._failed(self.daily_fails, sym, r.status, time.time())
        else:
            self.daily_fails.pop(sym, None)
        if not r.ok:
            return r.error or "unavailable"
        try:
            days = scan.parse_daily(r.json())
        except ValueError as e:
            return f"unparseable: {e}"
        if days:
            self.daily[sym] = days
            self.daily_at[sym] = time.time() - (r.age_min or 0.0) * 60.0
        return None

    def tick_bars(self, now: datetime | None = None) -> SourceStatus:
        """Refresh the stalest few names. One status for the tick."""
        st = SourceStatus("Scanner")
        if not self._warm:
            self._warm_start()
        now = now or datetime.now(UTC)
        clock = self.clock(now)
        active = clock.session != "closed"
        t = time.time()
        syms = self.symbols()

        def target(s: str) -> float:
            if not active:
                return CLOSED_SEC
            return BENCH_SEC if s in BENCHMARKS else ACTIVE_SEC

        def lag(s: str) -> float:
            f = self.fetched.get(s)
            return float("inf") if f is None else (t - f) / target(s)

        def waiting(s: str, book: dict[str, tuple[int, float]]) -> bool:
            return book.get(s, (0, 0.0))[1] > t

        paused = self.pause_until > t
        # The close read: every name read before the newest session bar's mark
        # goes first, ahead of the rotation.
        mark = None if paused else close_mark(now)

        def closing(s: str) -> bool:
            return mark is not None and self.fetched.get(s, 0.0) < mark

        due = [] if paused else sorted(
            (s for s in syms if (lag(s) >= 1.0 or closing(s)) and not waiting(s, self.fails)),
            key=lambda s: (not closing(s), -lag(s)))
        errors: list[str] = []
        for sym in due[:MAX_PER_TICK]:
            err = self._fetch_bars(sym, fresh=closing(sym))
            if err:
                self.errors[sym] = err
                errors.append(f"{sym}: {err}")
            else:
                self.errors.pop(sym, None)
        self.burst_left = sum(1 for s in syms if closing(s) and not waiting(s, self.fails))

        # Daily bars must be FINAL for every finished session: the previous
        # close, high and low are read off them (scan.technicals), and a copy
        # fetched at 14:00 carries that afternoon's price as the day's close. So
        # they also go stale at the most recent weekday 16:20 ET — after the
        # closing print — and just after the open, for today's official open
        # (OPEN_MARKS). A copy older than its mark is read again from Yahoo, not
        # from the six-hour cache: until 2026-11-11 the cache answered, so the
        # final bar could arrive as late as 22:20.
        mark = max(_last_close_mark(now), _last_open_mark(now))

        def before_mark(s: str) -> bool:
            return self.daily_at.get(s, 0.0) < mark

        stale_daily = [] if paused else [
            s for s in syms
            if (t - self.daily_at.get(s, 0.0) >= DAILY_TTL or before_mark(s))
            and not waiting(s, self.daily_fails)]
        for sym in stale_daily[:DAILY_PER_TICK]:
            err = self._fetch_daily(sym, fresh=before_mark(sym))
            if err:
                errors.append(f"{sym} daily: {err}")

        have = [s for s in syms if s in self.bars]
        st.items = len(have)
        st.ok = bool(have)
        st.source = "live" if st.ok else "unavailable"
        ages = [(t - self.fetched[s]) / 60.0 for s in have]
        st.age_min = max(ages) if ages else None
        done = min(len(due), MAX_PER_TICK)
        st.notes = [f"{done} refreshed, {len(due) - done} queued"]
        if self.burst_left:
            st.notes.append(f"close read: {self.burst_left} left")
        missing = len(syms) - len(have)
        if missing:
            st.notes.append(f"{missing} name(s) without bars yet")
        backing = [s for s in syms if waiting(s, self.fails)]
        if backing:
            st.notes.append(f"backing off: {', '.join(backing[:4])}")
        if paused:
            until = datetime.fromtimestamp(self.pause_until, scan.ET).strftime("%H:%M:%S")
            st.notes.append(f"Yahoo rate-limited the scanner (HTTP 429) — paused until {until} ET")
        if errors:
            st.error = errors[0] + (f" (+{len(errors) - 1} more)" if len(errors) > 1 else "")
        if st.ok:
            st.last_ok_utc = datetime.now(UTC).isoformat()
        return st

    def wake_in(self, now: datetime | None = None) -> float:
        """Seconds until the bars job should run again: BURST_TICK_SEC while a
        close read is unfinished, the next close's mark when it comes before the
        usual tick (so the read starts on time, not up to a tick late), else
        TICK_SEC."""
        if self.burst_left:
            return BURST_TICK_SEC
        nxt = next_mark_in(now or datetime.now(UTC))
        return max(BURST_TICK_SEC, min(TICK_SEC, nxt)) if nxt is not None else TICK_SEC

    def tick_live(self, now: datetime | None = None) -> tuple[SourceStatus | None, float]:
        """One batched read of every name's last trade; returns the status and
        the seconds until the next read.

        The status is None outside the regular session — nothing was fetched,
        and a tick-log row every thirty seconds saying so would be noise.
        """
        now = now or datetime.now(UTC)
        clock = self.clock(now)
        if clock.session != "rth":
            return None, LIVE_IDLE_SEC
        st = SourceStatus("Scanner live")
        t = time.time()
        if self.pause_until > t:
            # The bars were refused: the live layer gives way first and whole.
            st.source = "unavailable"
            st.error = "paused with the bars — Yahoo is rate-limiting (HTTP 429)"
            return st, max(LIVE_SEC, self.pause_until - t)
        syms = self.symbols()
        got: dict[str, LiveQuote] = {}
        err: str | None = None
        for i in range(0, len(syms), LIVE_CHUNK):
            chunk = syms[i : i + LIVE_CHUNK]
            names = {_yahoo(s): s for s in chunk}
            url = SPARK.format(syms=urllib.parse.quote(",".join(names), safe=""), rng="1d", iv="1d")
            # Never cached and never a stale copy: a five-second-old price
            # served as live is the one thing this layer exists to avoid.
            r = fetch(url, key=f"scanlive_{i}", ttl_sec=0.0, ua=BROWSER_UA, timeout=8,
                      stale_ok=False, store=False, validate=json_body)
            if not r.ok:
                err = f"HTTP {r.status}" if r.status else (r.error or "unreachable")
                break
            try:
                got.update(parse_live(r.json(), names, clock.trading_day))
            except ValueError as e:
                err = f"unparseable: {e}"
                break
        self.live.update(got)
        if err:
            self.live_fails += 1
            delay = LIVE_BACKOFF[min(self.live_fails, len(LIVE_BACKOFF)) - 1]
            st.error = f"{err} — next read in {delay:.0f}s"
        else:
            self.live_fails = 0
            delay = LIVE_SEC
        st.items = len(got)
        st.ok = bool(got)
        st.source = "live" if st.ok else "unavailable"
        st.age_min = 0.0 if st.ok else None
        st.notes = [f"{len(got)} of {len(syms)} names"]
        if st.ok:
            st.last_ok_utc = datetime.now(UTC).isoformat()
        return st, delay

    def _latest_trade(self, sym: str, session: str) -> LiveQuote | None:
        """The newest trade anyone has told us about. The spark layer's counts only
        in the regular session, the one it reads; the stream's in any."""
        q = self.live.get(sym) if session == "rth" else None
        got = self.stream.last_trade(sym) if self.stream is not None else None
        if got is None:
            return q
        s = LiveQuote(float(got[0]), int(got[1]))
        return s if q is None or s.at >= q.at else q

    def live_bars(self, sym: str, clock: scan.Clock) -> list[scan.Bar] | None:
        """The name's bars, with its live trade laid over them (scan.with_live).
        A trade the bars were read after is already in them, so it changes
        nothing. Any session the stream is hearing, now: the spark layer only
        ever knew the regular one. The clock is allowed five seconds' slack
        against the feed's, or a machine a second behind would refuse every trade."""
        bars = self.bars.get(sym)
        q = self._latest_trade(sym, clock.session)
        if not bars or q is None or clock.session == "closed":
            return bars
        if datetime.fromtimestamp(q.at, scan.ET).date() != clock.trading_day:
            return bars
        if q.at <= self.fetched.get(sym, 0.0) or q.at > clock.now.timestamp() + 5:
            return bars
        return scan.with_live(bars, q.price, q.at)

    def ensure_adhoc(self, sym: str) -> str | None:
        """Bars for a name off the list, on request (a chart opened from the wide
        scan or the search). Called on the API's thread; the bars land in the same
        books as a tracked name's, so every reader of them works unchanged. A
        minute between reads of one name, and the rotation's 429 pause holds here
        too. Returns why not, or None."""
        if not _SYM.match(sym):
            return "not a ticker"
        t = time.time()
        if self.pause_until > t:
            return None if sym in self.bars else "Yahoo is rate-limiting — paused"
        if t - self.adhoc.get(sym, 0.0) < ADHOC_SEC and sym in self.bars:
            return None
        self.adhoc[sym] = t
        err = self._fetch_bars(sym)
        if t - self.daily_at.get(sym, 0.0) >= DAILY_TTL:
            self._fetch_daily(sym)
        self._prune_adhoc()
        return err if sym not in self.bars else None

    def _prune_adhoc(self) -> None:
        keep = set(self.symbols())
        names = sorted((s for s in self.adhoc if s not in keep), key=lambda s: self.adhoc[s])
        for s in names[:-ADHOC_MAX]:
            for book in (self.adhoc, self.bars, self.meta, self.fetched, self.daily, self.daily_at,
                         self.fails, self.daily_fails, self.errors):
                book.pop(s, None)

    def compute_one(self, sym: str, sector: str | None = None,
                    now: datetime | None = None) -> dict[str, Any] | None:
        """One name's technical row, for a name off the list — `compute`'s body for
        a single symbol, read against SPY and QQQ as every row is."""
        now = now or datetime.now(UTC)
        clock = self.clock(now)

        def tech(s: str) -> scan.Tech | None:
            bars = self.live_bars(s, clock)
            if not bars:
                return None
            name = (self.meta.get(s) or {}).get("shortName") or self.sec_names.get(s)
            return scan.technicals(bars, self.daily.get(s) or [], clock, name=name,
                                   official=scan.official_close(self.meta.get(s)),
                                   asof=self.fetched.get(s), daily_asof=self.daily_at.get(s),
                                   pm_wide=self.pm_wide(s, clock.trading_day))

        t = tech(sym)
        if t is None:
            return None
        row = scan.row_of(sym, t, tech("SPY"), tech("QQQ"), clock)
        row["volume"] = scan.day_volume(row.get("volume"), self.meta.get(sym), clock.trading_day)
        row["sector"] = SECTOR.get(sym) or self.pool_sectors.get(sym) or sector
        row["adv"] = avg_day([d.volume for d in (self.daily.get(sym) or [])
                              if d.day < clock.trading_day])
        row["frame"] = frame_of(self.daily.get(sym) or [], clock.trading_day)
        return row

    def clock(self, now: datetime) -> scan.Clock:
        return scan.clock_at(now.astimezone(scan.ET))

    def compute(self, now: datetime | None = None) -> dict[str, Any]:
        """Every name's technicals as of now — the block the read path scores."""
        now = now or datetime.now(UTC)
        clock = self.clock(now)
        techs: dict[str, scan.Tech] = {}
        for sym in self.symbols():
            bars = self.live_bars(sym, clock)
            if not bars:
                continue
            name = (self.meta.get(sym) or {}).get("shortName") or self.sec_names.get(sym)
            # `asof`: a bar is confirmed by THIS download, not by the clock —
            # see scan.CLOSE_LAG_SEC.
            techs[sym] = scan.technicals(bars, self.daily.get(sym) or [], clock, name=name,
                                         official=scan.official_close(self.meta.get(sym)),
                                         asof=self.fetched.get(sym),
                                         daily_asof=self.daily_at.get(sym),
                                         pm_wide=self.pm_wide(sym, clock.trading_day))
        rows: dict[str, dict[str, Any]] = {}
        for sym, tech in techs.items():
            row = scan.row_of(sym, tech, techs.get("SPY"), techs.get("QQQ"), clock)
            # Today's volume as the tape counts it, not the bars' short sum (scan.day_volume).
            row["volume"] = scan.day_volume(row.get("volume"), self.meta.get(sym),
                                            clock.trading_day)
            # The static table first; a promoted name the table does not know
            # takes the pool's sector (sources/pool.TV_SECTOR), else none.
            row["sector"] = SECTOR.get(sym) or self.pool_sectors.get(sym)
            row["adv"] = avg_day([d.volume for d in (self.daily.get(sym) or [])
                                  if d.day < clock.trading_day])
            # The daily frame (frame.py): levels from the finished sessions;
            # the read against the live print is done on the read path.
            row["frame"] = frame_of(self.daily.get(sym) or [], clock.trading_day)
            if self.errors.get(sym) and not tech.ok:
                row["error"] = self.errors[sym]
            rows[sym] = row
        return {
            "session": clock.session,
            "trading_day": clock.trading_day.isoformat(),
            "pm_locked": clock.pm_locked,
            "rows": rows,
            "fetched": dict(self.fetched),
            "errors": dict(self.errors),
        }

    def read_owed(self, owed: dict[str, set[str]], now: float | None = None) -> list[str]:
        """Read, once, the names that have signals from a FINISHED day and are no
        longer being fetched, so `day_signals` can settle that day. Returns the names
        read this tick. `owed` is {day: names} (scanlog.EventLog.unchecked).

        A NAME THAT LEFT THE LIST DURING ITS DAY WAS NEVER SETTLED (audit,
        2026-11-11). The pool swaps its promotions as the morning goes and the owner
        edits the pinned list; from that minute the name's bars stop, `day_signals`
        wants bars read after the bell, and so its signals stayed unchecked and their
        outcomes open for good: logged, shown, and never in the record. 70 events on
        30 name-days in eight sessions stood that way (RCL 27 Oct, RBLX 30 Oct, MAR
        2 Nov, NVDA 10 Nov), 25 of them an (L) or (E) whose result was frozen at the
        minute the name left. A restart loses the bars in memory too, so a name that
        was watched to the bell and is off the list by 20:00 went the same way.

        ONE READ, AFTER THE BELL, AND THE DAILY COPY FIRST. The replay reads its
        levels off the settled daily bar (scan.technicals); settled against bars
        alone, a signal can fail to reappear for a few cents and be withdrawn. So
        the daily copy is read first, and without one read after that bell the bars
        are not read either and nothing changes. The 5-minute range is twelve
        sessions (BARS_RANGE), so a day is in reach for about two weeks; past that
        the name is read once, `day_signals` passes it over, and it is not asked for
        again. The rotation's backoff and its 429 pause hold here too.
        """
        t = time.time() if now is None else now
        if self.pause_until > t:
            return []
        tracked = set(self.symbols())
        # Each name's latest owed bell (a copy read after it is after them all) and
        # its oldest owed day (the first to leave the bars' reach goes first).
        bell_of: dict[str, float] = {}
        first_of: dict[str, str] = {}
        for day in sorted(owed):
            d = date.fromisoformat(day)
            m = scan.rth_end(d)
            bell = datetime(d.year, d.month, d.day, m // 60, m % 60, tzinfo=scan.ET).timestamp()
            for sym in owed[day]:
                if sym in tracked or not _SYM.match(sym):
                    continue
                bell_of[sym] = max(bell_of.get(sym, 0.0), bell)
                first_of.setdefault(sym, day)

        def due(s: str) -> bool:
            if s in self.bars and self.fetched.get(s, 0.0) >= bell_of[s] + CLOSE_LAG:
                return False  # read after that bell already: day_signals has what it needs
            if self.owed_tried.get(s, 0.0) + OWED_RETRY_SEC > t:
                return False
            return self.fails.get(s, (0, 0.0))[1] <= t and self.daily_fails.get(s, (0, 0.0))[1] <= t

        done: list[str] = []
        for sym in sorted((s for s in bell_of if due(s)), key=lambda s: (first_of[s], s)):
            if len(done) >= OWED_PER_TICK or self.pause_until > t:
                break
            self.owed_tried[sym] = t
            # Marked before the read: whatever copy of its bars ends up held, this is
            # a name nobody was watching to the bell (EventLog.settle, `known_only`).
            self.owed.add(sym)
            settled = bell_of[sym] + scan.DAILY_SETTLE_SEC
            if self.daily_at.get(sym, 0.0) < settled:
                self._fetch_daily(sym, fresh=True)
                if self.daily_at.get(sym, 0.0) < settled:
                    continue
            self._fetch_bars(sym, fresh=True)
            if sym in self.bars and self.fetched.get(sym, 0.0) >= bell_of[sym] + CLOSE_LAG:
                done.append(sym)
        return done

    def unwatched(self) -> set[str]:
        """Names whose bars were read off the list, for a settle or a chart: a day
        settled on them checks what was logged and adds nothing (EventLog.settle)."""
        return (self.owed | set(self.adhoc)) - set(self.symbols())

    def day_signals(self, day: date, syms: Iterable[str]
                    ) -> dict[str, tuple[list[dict[str, Any]], int | None]]:
        """Each name's signals for a FINISHED session `day`, replayed from the bars
        held as of that day's bell — what the event log settles the day against
        (scanlog.EventLog.settle). Only names whose bars were read after the bell
        and still reach back to the day: anything else cannot be checked yet.
        `final_to` is where those bars are final (the bell, when they are whole)."""
        m = scan.rth_end(day)
        bell = datetime(day.year, day.month, day.day, m // 60, m % 60, tzinfo=scan.ET)
        first = datetime(day.year, day.month, day.day, scan.PM_START // 60,
                         tzinfo=scan.ET).timestamp()
        clock = scan.clock_at(bell)
        out: dict[str, tuple[list[dict[str, Any]], int | None]] = {}
        for sym in syms:
            bars, at = self.bars.get(sym), self.fetched.get(sym, 0.0)
            if not bars or at < bell.timestamp() + CLOSE_LAG or bars[0].t > first:
                continue
            # The same daily copy the live rows read, by the same rule, so the day is
            # settled against the levels its signals fired on.
            tech = scan.technicals(bars, self.daily.get(sym) or [], clock, asof=at,
                                   daily_asof=self.daily_at.get(sym))
            if tech.ok and tech.rth_today:
                out[sym] = (tech.signals, tech.final_to)
        return out

    # ---- headlines ----------------------------------------------------------

    def own_names(self, sym: str) -> list[str]:
        """Looser than `aliases`: for filtering the ticker's OWN feed, where the
        filer's first name word is safe to match — for a name the table lacks.
        Never for a table entry: SpaceX's filer is "SPACE EXPLORATION…", which
        would make every headline with "space" in it SpaceX's."""
        if sym in ALIASES:
            return [*ALIASES[sym], *OWN_WORDS.get(sym, [])]
        first = (self.sec_names.get(sym) or "").split(" ")[0].strip(",.")
        return [first] if len(first) >= 4 else []

    def aliases(self, sym: str) -> list[str]:
        out = list(ALIASES.get(sym, []))
        n = self.sec_names.get(sym)
        if n and not out:
            short = re.sub(r",?\s+(Inc|Corp|Corporation|Co|Ltd|Plc|Holdings|Group|Company|"
                           r"Technologies|Platforms|Global|Markets)\.?$", "", n, flags=re.I)
            if len(short) >= 5 and short != short.upper():
                out.append(short)
        return out

    def tick_news(self) -> SourceStatus:
        st = SourceStatus("Scanner news")
        t = time.time()
        names = [s for s in self.watchlist() if s not in BENCHMARKS]
        due = sorted((s for s in names if t - self.news_at.get(s, 0.0) >= NEWS_SEC),
                     key=lambda s: self.news_at.get(s, 0.0))
        errors: list[str] = []
        unnamed: list[str] = []
        cold = sum(1 for s in due if s not in self.news_at)
        for sym in due[:max(NEWS_PER_TICK, min(cold, NEWS_PER_TICK_COLD))]:
            r = fetch(YAHOO_RSS.format(sym=urllib.parse.quote(_yahoo(sym))),
                      key=f"scannews_{sym}", ttl_sec=NEWS_SEC - 60, ua=BROWSER_UA, timeout=15,
                      stale_max_sec=6 * 3600.0, validate=feed_body)
            items = parse_news(_decode(r.body)) if r.ok else []
            # The same ticker's stories with the outlet that wrote each (YAHOO_SEARCH):
            # those are the rows, and the RSS is left to supply its sentence.
            j = fetch(YAHOO_SEARCH.format(sym=urllib.parse.quote(_yahoo(sym))),
                      key=f"scansearch_{sym}", ttl_sec=NEWS_SEC - 60, ua=BROWSER_UA, timeout=15,
                      stale_max_sec=6 * 3600.0, validate=search_ok)
            named: list[dict[str, Any]] = []
            if j.ok:
                with contextlib.suppress(ValueError):
                    named = parse_search(j.json(), sym)
            if named:
                items = with_summaries(named, items)
            elif items:
                unnamed.append(sym)
            if not items:
                q = (ALIASES.get(sym) or [sym])[0]
                g = fetch(gnews(f'"{q}" stock', when="3d"), key=f"scangnews_{sym}",
                          ttl_sec=NEWS_SEC - 60, ua=BROWSER_UA, timeout=15,
                          stale_max_sec=6 * 3600.0, validate=feed_body)
                items = parse_news(_decode(g.body), publisher="Google News") if g.ok else []
                if not items and not (r.ok or g.ok):
                    errors.append(f"{sym}: {r.error or g.error or 'unreachable'}")
            # `own`, NOT `names`: reusing the watchlist's name here left the
            # status below counting one ticker's aliases, so every tick read
            # "0 items, not ok" with no error (review, 2026-10-13).
            own = self.own_names(sym)
            items = [it for it in items if mentions(it["title"], sym, own)]
            for it in items:
                it["kind"] = None
            self.news[sym] = items
            self.news_at[sym] = t
            # A name read without its outlets is asked again in two minutes, not ten:
            # after a restart the first ten names go out at once, and Yahoo's search
            # turned two of them away (GOOGL and META, 2026-11-15).
            if sym in unnamed:
                self.news_at[sym] = t - NEWS_SEC + 120.0
        st.items = sum(1 for s in names if self.news.get(s))
        # A tick with nothing due, or names that simply have no headlines, is
        # healthy; only a tick whose fetches FAILED is not.
        st.ok = not errors or st.items > 0
        st.source = "live" if st.ok else "unavailable"
        ages = [(t - self.news_at[s]) / 60.0 for s in names if s in self.news_at]
        st.age_min = max(ages) if ages else None
        if errors:
            st.error = errors[0]
        if unnamed:
            # Said, not silent: these names' stories are the RSS's this pass, with no
            # outlet on the ones Yahoo hosts, so the set-aside list cannot reach them.
            st.notes.append(f"Yahoo's search did not answer for {', '.join(unnamed[:6])}: "
                            "their stories carry no outlet this pass")
        if st.ok:
            st.last_ok_utc = datetime.now(UTC).isoformat()
        return st

    # ---- filings ------------------------------------------------------------

    def _load_ciks(self) -> str | None:
        r = fetch(SEC_TICKERS, key="sec_company_tickers", ttl_sec=86400.0, ua=UA, timeout=30,
                  validate=json_body)
        if not r.ok:
            return r.error or "unavailable"
        try:
            doc = r.json()
            for v in (doc or {}).values():
                tk = str(v.get("ticker") or "").upper()
                if tk:
                    self.ciks[tk] = int(v["cik_str"])
                    self.sec_names[tk] = str(v.get("title") or "")
        except (ValueError, KeyError, TypeError, AttributeError) as e:
            return f"unparseable: {e}"
        return None

    def tick_sec(self) -> SourceStatus:
        st = SourceStatus("Scanner SEC")
        t = time.time()
        err = None if self.ciks else self._load_ciks()
        names = [s for s in self.watchlist() if s not in BENCHMARKS]
        # And the names in play today that the list does not track (the collector's
        # `sec_extra`: the Today list, the pool's top): their insider trades are context
        # on the Today rows whether or not the engine tracks them (2026-11-13, after the
        # favourites were cleared and the Insiders chip fell from 6 to 0).
        if self.sec_extra is not None:
            with contextlib.suppress(Exception):
                names += [s for s in self.sec_extra() if s not in names and s not in BENCHMARKS]
        due = sorted((s for s in names if t - self.filings_at.get(s, 0.0) >= SEC_SEC),
                     key=lambda s: self.filings_at.get(s, 0.0))
        today = datetime.now(scan.ET).date()
        for sym in due[:SEC_PER_TICK]:
            cik = self.ciks.get(sym) or self.ciks.get(sym.replace(".", "-"))
            self.filings_at[sym] = t
            if cik is None:
                self.filings[sym] = []
                self.reports[sym] = []
                continue
            r = fetch(SEC_SUBMISSIONS.format(cik=cik), key=f"scansec_{cik}",
                      ttl_sec=SEC_SEC - 60, ua=UA, timeout=20, stale_max_sec=86400.0,
                      validate=json_body)
            if not r.ok:
                err = err or f"{sym}: {r.error}"
                continue
            try:
                doc = r.json()
                self.filings[sym] = parse_filings(doc, cik, today)
                # The same list's Form 4s, for the insider trades (sources/insiders.py).
                self.form4_refs[sym] = form4_refs(doc, cik, today)
                # And its results releases, for the earnings history (sources/earnhist.py).
                self.reports[sym] = parse_edgar(doc)
            except ValueError as e:
                err = err or f"{sym}: unparseable: {e}"
        # A few of the Form 4s not read yet, newest first: each is read once and kept.
        book = self.insider_book
        pending = [ref for s in names for ref in book.wanted(self.form4_refs.get(s) or [])]
        pending.sort(key=lambda ref: ref["filed"], reverse=True)
        for ref in pending[:FORM4_PER_TICK]:
            got = fetch(ref["xml"], ttl_sec=0.0, ua=UA, timeout=20, stale_ok=False, store=False,
                        validate=_form4_body)
            body = got.body.decode("utf-8", errors="replace") if got.ok and got.body else None
            self.insider_book.take(ref, body)
        if pending:
            self.insider_book.save(today)
        st.items = sum(len(self.filings.get(s) or []) for s in names)
        st.ok = bool(self.ciks)
        st.source = "live" if st.ok else "unavailable"
        ages = [(t - self.filings_at[s]) / 60.0 for s in names if s in self.filings_at]
        st.age_min = max(ages) if ages else None
        st.error = err
        if st.ok:
            st.last_ok_utc = datetime.now(UTC).isoformat()
        left = len(pending) - min(len(pending), FORM4_PER_TICK)
        if left:
            st.notes.append(f"{left} Form 4s still to read")
        return st

    def insiders(self, sym: str, today: date | None = None) -> list[dict[str, Any]]:
        """The name's insider trades worth a line over the last month (sources/insiders.py),
        newest first, each with its line in words: the trades in its own stock, from the
        book, so a restart or a name leaving the list does not hide them."""
        today = today or datetime.now(scan.ET).date()
        return [{**t, "text": line_of(t)} for t in self.insider_book.trades_of(sym, today)]
