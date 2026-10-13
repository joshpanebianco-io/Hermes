"""
The scanner's feeds — bars, headlines and filings for every name on the watchlist.

FREE, AND ENOUGH FOR THE STRATEGY. Yahoo's v8 chart endpoint gives any US stock
five days of 5-minute OHLCV bars from 04:00 to 20:00 ET with no key — exactly
what LE_Model.pine reads through `request.security(…, session.extended)`. The
same endpoint at a daily interval gives three months of sessions for the daily
ATR. Personal use only, like every other Yahoo read in this terminal.

THE REQUEST BUDGET, SAID OUT LOUD. One chart request per name, rotated: the job
ticks every 15 s and refreshes at most five of the stalest names, aiming at
every name every 90 s and SPY / QQQ / IWM every 30 s while any session is on
(04:00–20:00 ET), every 15 minutes when none is. With the default 21 names that
is ~20 requests a minute in session, a few an hour overnight, and the daily
bars once per name per six hours on top. A 40-name list stretches each name's
refresh to ~3 minutes rather than raising the rate — Yahoo has no published
limit and the polite answer to that is to stay well under the unpublished one.

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

import json
import os
import re
import threading
import time
import urllib.parse
from collections.abc import Iterable
from datetime import UTC, date, datetime, timedelta
from email.utils import parsedate_to_datetime
from typing import Any

from .. import scan
from ..config import BROWSER_UA, CACHE_DIR, UA
from ..http import CACHE, SourceStatus, clean_text, feed_body, fetch, json_body, rss_items
from .wire import gnews

CHART = (
    "https://query1.finance.yahoo.com/v8/finance/chart/{sym}"
    "?range={rng}&interval={iv}&includePrePost=true"
)
YAHOO_RSS = "https://feeds.finance.yahoo.com/rss/2.0/headline?s={sym}&region=US&lang=en-US"
SEC_TICKERS = "https://www.sec.gov/files/company_tickers.json"
SEC_SUBMISSIONS = "https://data.sec.gov/submissions/CIK{cik:010d}.json"
SEC_DOC = "https://www.sec.gov/Archives/edgar/data/{cik}/{acc}/{doc}"

# The LE_Model.pine scanner's ON tickers, in the script's order.
DEFAULT_WATCHLIST = [
    "SPY", "QQQ", "IWM", "AMD", "SPCX", "COIN", "PLTR", "HOOD", "DELL", "IBM", "AAPL",
    "NVDA", "TSLA", "AMZN", "META", "MSFT", "GOOG", "NFLX", "ADBE", "PYPL", "INTC",
]
# Always fetched: RS is measured against SPY and QQQ, and the tape reads IWM.
BENCHMARKS = ("SPY", "QQQ", "IWM")
MAX_SYMBOLS = 40
_SYM = re.compile(r"^[A-Z0-9][A-Z0-9.\-]{0,9}$")

TICK_SEC = 15.0
ACTIVE_SEC = 90.0
BENCH_SEC = 30.0
CLOSED_SEC = 900.0
MAX_PER_TICK = 5
DAILY_TTL = 6 * 3600.0
DAILY_PER_TICK = 3
NEWS_SEC = 600.0
NEWS_PER_TICK = 3
SEC_SEC = 1800.0
SEC_PER_TICK = 2
FILING_DAYS = 3
BACKOFF_BASE = 30.0
BACKOFF_MAX = 15 * 60.0
RATE_LIMIT_PAUSE = 120.0


def backoff(failures: int) -> float:
    """Seconds to wait after the n-th failure in a row: 30, 60, 120 … 900. Pure."""
    return min(BACKOFF_MAX, BACKOFF_BASE * 2 ** max(0, failures - 1))

WATCHLIST_FILE = os.path.join(CACHE_DIR, "scanner_watchlist.json")

# Ticker → the S&P sector SPDR it trades with. A static table because the
# iShares holdings file the constituents panel reads is not reliably served
# (it has come back as an HTML page), and a wrong sector is worse than none —
# an unknown name gets null and simply earns no sector tailwind.
SECTOR: dict[str, str] = {
    **dict.fromkeys(
        ["AAPL", "MSFT", "NVDA", "AMD", "INTC", "AVGO", "MU", "ORCL", "CRM", "ADBE", "IBM",
         "DELL", "SMCI", "ARM", "PLTR", "QCOM", "TXN", "CSCO", "NOW", "AMAT", "LRCX", "KLAC",
         "MRVL", "PANW", "CRWD", "SNOW", "ANET", "TSM", "SHOP", "MSTR", "ASML", "HPE", "HPQ",
         "NET", "DDOG", "ZS", "INTU", "ON", "ADI", "NXPI", "WDC", "STX", "APP", "IONQ"], "XLK"),
    **dict.fromkeys(
        ["META", "GOOG", "GOOGL", "NFLX", "DIS", "T", "VZ", "TMUS", "RDDT", "SPOT", "CMCSA",
         "SNAP", "PINS", "WBD", "ROKU", "TTD"], "XLC"),
    **dict.fromkeys(
        ["AMZN", "TSLA", "HD", "NKE", "MCD", "SBUX", "ABNB", "BKNG", "LULU", "RIVN", "GM", "F",
         "LOW", "TJX", "CMG", "DASH", "LCID", "NIO", "CVNA", "DKNG"], "XLY"),
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
    "MSTR": ["MicroStrategy"], "SOFI": ["SoFi"], "TSM": ["TSMC"], "JPM": ["JPMorgan"],
    "GS": ["Goldman Sachs"], "BA": ["Boeing"], "WMT": ["Walmart"], "COST": ["Costco"],
    "DIS": ["Disney"], "XOM": ["Exxon"], "LLY": ["Eli Lilly"], "UNH": ["UnitedHealth"],
}

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
        out.append({
            "title": title,
            "url": r["link"],
            "publisher": pub,
            "utc": when.astimezone(UTC).isoformat() if when else None,
            "ts": when.timestamp() if when else None,
        })
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

    def __init__(self, watchlist_path: str = WATCHLIST_FILE) -> None:
        self._lock = threading.Lock()
        self._path = watchlist_path
        self._watch = load_watchlist(watchlist_path)
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
        self.ciks: dict[str, int] = {}
        self.sec_names: dict[str, str] = {}
        #: Per-symbol failures in a row and when it may be tried again (epoch).
        self.fails: dict[str, tuple[int, float]] = {}
        self.daily_fails: dict[str, tuple[int, float]] = {}
        #: Yahoo said 429 — nothing is fetched before this (epoch).
        self.pause_until = 0.0
        self._warm = False

    # ---- watchlist ----------------------------------------------------------

    def watchlist(self) -> list[str]:
        with self._lock:
            return list(self._watch)

    def set_watchlist(self, symbols: Iterable[Any]) -> tuple[list[str], list[str]]:
        ok, bad = save_watchlist(symbols, self._path)
        with self._lock:
            self._watch = ok
        return ok, bad

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
                key = f"scan{kind}_{sym}"
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

    def _fetch_bars(self, sym: str) -> str | None:
        url = CHART.format(sym=urllib.parse.quote(_yahoo(sym)), rng="5d", iv="5m")
        r = fetch(url, key=f"scan5m_{sym}", ttl_sec=10.0, ua=BROWSER_UA, timeout=15,
                  stale_max_sec=900.0, validate=json_body)
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

    def _fetch_daily(self, sym: str) -> str | None:
        url = CHART.format(sym=urllib.parse.quote(_yahoo(sym)), rng="3mo", iv="1d")
        r = fetch(url, key=f"scan1d_{sym}", ttl_sec=DAILY_TTL, ua=BROWSER_UA, timeout=15,
                  stale_max_sec=3 * 86400.0, validate=json_body)
        if not r.ok:
            self._failed(self.daily_fails, sym, r.status, time.time())
            return r.error or "unavailable"
        self.daily_fails.pop(sym, None)
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
        due = [] if paused else sorted(
            (s for s in syms if lag(s) >= 1.0 and not waiting(s, self.fails)),
            key=lambda s: -lag(s))
        errors: list[str] = []
        for sym in due[:MAX_PER_TICK]:
            err = self._fetch_bars(sym)
            if err:
                self.errors[sym] = err
                errors.append(f"{sym}: {err}")
            else:
                self.errors.pop(sym, None)

        # Daily bars must be FINAL for every finished session: the previous
        # close is read off them (scan.technicals), and a copy fetched at 14:00
        # carries that afternoon's price as the day's close. So they also go
        # stale at the most recent weekday 16:20 ET — after the closing print.
        mark = _last_close_mark(now)
        stale_daily = [] if paused else [
            s for s in syms
            if (t - self.daily_at.get(s, 0.0) >= DAILY_TTL or self.daily_at.get(s, 0.0) < mark)
            and not waiting(s, self.daily_fails)]
        for sym in stale_daily[:DAILY_PER_TICK]:
            err = self._fetch_daily(sym)
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

    def clock(self, now: datetime) -> scan.Clock:
        return scan.clock_at(now.astimezone(scan.ET))

    def compute(self, now: datetime | None = None) -> dict[str, Any]:
        """Every name's technicals as of now — the block the read path scores."""
        now = now or datetime.now(UTC)
        clock = self.clock(now)
        techs: dict[str, scan.Tech] = {}
        for sym in self.symbols():
            bars = self.bars.get(sym)
            if not bars:
                continue
            name = (self.meta.get(sym) or {}).get("shortName") or self.sec_names.get(sym)
            techs[sym] = scan.technicals(bars, self.daily.get(sym) or [], clock, name=name,
                                         official=scan.official_close(self.meta.get(sym)))
        rows: dict[str, dict[str, Any]] = {}
        for sym, tech in techs.items():
            row = scan.row_of(sym, tech, techs.get("SPY"), techs.get("QQQ"), clock)
            row["sector"] = SECTOR.get(sym)
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

    # ---- headlines ----------------------------------------------------------

    def own_names(self, sym: str) -> list[str]:
        """Looser than `aliases`: for filtering the ticker's OWN feed, where the
        filer's first name word is safe to match — for a name the table lacks.
        Never for a table entry: SpaceX's filer is "SPACE EXPLORATION…", which
        would make every headline with "space" in it SpaceX's."""
        if sym in ALIASES:
            return list(ALIASES[sym])
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
        for sym in due[:NEWS_PER_TICK]:
            r = fetch(YAHOO_RSS.format(sym=urllib.parse.quote(_yahoo(sym))),
                      key=f"scannews_{sym}", ttl_sec=NEWS_SEC - 60, ua=BROWSER_UA, timeout=15,
                      stale_max_sec=6 * 3600.0, validate=feed_body)
            items = parse_news(_decode(r.body)) if r.ok else []
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
        st.items = sum(1 for s in names if self.news.get(s))
        # A tick with nothing due, or names that simply have no headlines, is
        # healthy; only a tick whose fetches FAILED is not.
        st.ok = not errors or st.items > 0
        st.source = "live" if st.ok else "unavailable"
        ages = [(t - self.news_at[s]) / 60.0 for s in names if s in self.news_at]
        st.age_min = max(ages) if ages else None
        if errors:
            st.error = errors[0]
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
        due = sorted((s for s in names if t - self.filings_at.get(s, 0.0) >= SEC_SEC),
                     key=lambda s: self.filings_at.get(s, 0.0))
        today = datetime.now(scan.ET).date()
        for sym in due[:SEC_PER_TICK]:
            cik = self.ciks.get(sym) or self.ciks.get(sym.replace(".", "-"))
            self.filings_at[sym] = t
            if cik is None:
                self.filings[sym] = []
                continue
            r = fetch(SEC_SUBMISSIONS.format(cik=cik), key=f"scansec_{cik}",
                      ttl_sec=SEC_SEC - 60, ua=UA, timeout=20, stale_max_sec=86400.0,
                      validate=json_body)
            if not r.ok:
                err = err or f"{sym}: {r.error}"
                continue
            try:
                self.filings[sym] = parse_filings(r.json(), cik, today)
            except ValueError as e:
                err = err or f"{sym}: unparseable: {e}"
        st.items = sum(len(self.filings.get(s) or []) for s in names)
        st.ok = bool(self.ciks)
        st.source = "live" if st.ok else "unavailable"
        ages = [(t - self.filings_at[s]) / 60.0 for s in names if s in self.filings_at]
        st.age_min = max(ages) if ages else None
        st.error = err
        if st.ok:
            st.last_ok_utc = datetime.now(UTC).isoformat()
        return st
