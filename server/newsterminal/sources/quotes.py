"""
The board — every price the terminal shows, from one endpoint.

WHY YAHOO, AND WHY THAT IS FINE HERE. GEXYGEN cannot ship Yahoo bars: its
terms forbid redistribution, and GEXYGEN is going commercial. This terminal is
a personal instrument on one desk, which is exactly the use Yahoo's terms
contemplate — so the constraint that shapes the sister project does not apply,
and the whole board opens up: futures, global indices, the vol complex, the
dollar, energy, metals and crypto, all on one clock.

ONE REQUEST PER CHUNK, NOT ONE PER SYMBOL. The `spark` endpoint takes a
comma-separated list and returns each symbol's meta AND its intraday closes, so
forty-odd instruments cost three requests rather than forty — and the closes
come along free, which is where the sparklines come from. Chunked because a
very long symbol list is where this endpoint starts returning partial results.

EVERY ROW KNOWS WHAT IT IS. `group` drives which panel a row lands in and
`fmt` how it prints, so adding an instrument is one line here rather than a
line here and a branch in the UI.
"""

from __future__ import annotations

import hashlib
import time
import urllib.parse
from datetime import UTC, datetime
from typing import Any
from zoneinfo import ZoneInfo

from ..config import BROWSER_UA
from ..http import SourceStatus, fetch, json_body

SPARK = "https://query1.finance.yahoo.com/v7/finance/spark?symbols={syms}&range={rng}&interval={iv}"

# key, yahoo, label, group, fmt
#
# `fmt` is a hint, not a format string: "px" is a price at the instrument's own
# precision, "pct" a percentage already in percent units, "bp" a rate in
# percent that the UI shows in basis points when it moves.
UNIVERSE: list[tuple[str, str, str, str, str]] = [
    # ---- the three books actually traded ------------------------------------
    ("NQ", "NQ=F", "Nasdaq 100 fut", "core", "px"),
    ("QQQ", "QQQ", "QQQ", "core", "px"),
    ("ES", "ES=F", "S&P 500 fut", "core", "px"),
    ("SPY", "SPY", "SPY", "core", "px"),
    ("GC", "GC=F", "Gold fut", "core", "px"),
    ("GLD", "GLD", "GLD", "core", "px"),
    ("YM", "YM=F", "Dow fut", "core", "px"),
    ("RTY", "RTY=F", "Russell 2000 fut", "core", "px"),
    # The Russell's ETF beside its future, as QQQ and SPY sit beside theirs —
    # the stocks desk's header prints SPY, QQQ and IWM (owner, 2026-10-13).
    ("IWM", "IWM", "IWM", "core", "px"),
    # ---- the world's other sessions -----------------------------------------
    ("N225", "^N225", "Nikkei 225", "global", "px"),
    ("HSI", "^HSI", "Hang Seng", "global", "px"),
    ("SHCOMP", "000001.SS", "Shanghai Comp", "global", "px"),
    ("KOSPI", "^KS11", "KOSPI", "global", "px"),
    # "ASX", not "AXJO": the owner trades from Australia, scanned the board
    # for their own index and could not find it behind Yahoo's code.
    ("ASX", "^AXJO", "ASX 200", "global", "px"),
    ("FTSE", "^FTSE", "FTSE 100", "global", "px"),
    ("DAX", "^GDAXI", "DAX", "global", "px"),
    ("CAC", "^FCHI", "CAC 40", "global", "px"),
    ("SX5E", "^STOXX50E", "Euro Stoxx 50", "global", "px"),
    # ---- rates ---------------------------------------------------------------
    # "US3M", not "US2Y" (2026-11-14): ^IRX is the 13-week bill, and under the old
    # key the Macro board printed it at 4.12 beside the Rates card's real two-year at
    # 4.88. Yahoo has no two-year index; the 2Y is the Treasury's, on the Rates card.
    ("US3M", "^IRX", "13-week bill", "rates", "bp"),
    ("US5Y", "^FVX", "5-year", "rates", "bp"),
    ("US10Y", "^TNX", "10-year", "rates", "bp"),
    ("US30Y", "^TYX", "30-year", "rates", "bp"),
    ("ZN", "ZN=F", "10Y note fut", "rates", "px"),
    ("ZB", "ZB=F", "T-bond fut", "rates", "px"),
    # ---- the fear complex ----------------------------------------------------
    # THE CURVE, NOT JUST THE LEVEL. VIX alone says how much movement is
    # priced; the four tenors together say whether that is calm or stressed,
    # because the shape inverts before the level moves much. See volterm.py.
    ("VIX9D", "^VIX9D", "VIX 9-day", "vol", "px"),
    ("VIX", "^VIX", "VIX", "vol", "px"),
    ("VIX3M", "^VIX3M", "VIX 3-month", "vol", "px"),
    ("VIX6M", "^VIX6M", "VIX 6-month", "vol", "px"),
    # Not a tenor: the cost of far out-of-the-money puts against at-the-money —
    # what the market pays for a crash rather than for movement.
    ("SKEW", "^SKEW", "SKEW", "vol", "px"),
    ("VVIX", "^VVIX", "VVIX", "vol", "px"),
    ("MOVE", "^MOVE", "MOVE (bond vol)", "vol", "px"),
    ("VXN", "^VXN", "VXN (Nasdaq vol)", "vol", "px"),
    # ---- dollar and crosses --------------------------------------------------
    ("DXY", "DX-Y.NYB", "Dollar index", "fx", "px"),
    ("EURUSD", "EURUSD=X", "EUR/USD", "fx", "px"),
    ("USDJPY", "JPY=X", "USD/JPY", "fx", "px"),
    ("GBPUSD", "GBPUSD=X", "GBP/USD", "fx", "px"),
    ("USDCNY", "CNY=X", "USD/CNY", "fx", "px"),
    ("AUDUSD", "AUDUSD=X", "AUD/USD", "fx", "px"),
    # ---- energy --------------------------------------------------------------
    ("WTI", "CL=F", "WTI crude", "energy", "px"),
    ("BRENT", "BZ=F", "Brent crude", "energy", "px"),
    ("NATGAS", "NG=F", "Nat gas", "energy", "px"),
    ("RBOB", "RB=F", "RBOB gasoline", "energy", "px"),
    ("HEATOIL", "HO=F", "Heating oil", "energy", "px"),
    # ---- metals and ags ------------------------------------------------------
    ("SILVER", "SI=F", "Silver", "metals", "px"),
    ("COPPER", "HG=F", "Copper", "metals", "px"),
    ("PLAT", "PL=F", "Platinum", "metals", "px"),
    ("WHEAT", "ZW=F", "Wheat", "metals", "px"),
    ("CORN", "ZC=F", "Corn", "metals", "px"),
    # ---- risk appetite -------------------------------------------------------
    ("BTC", "BTC-USD", "Bitcoin", "crypto", "px"),
    ("ETH", "ETH-USD", "Ethereum", "crypto", "px"),
    ("HYG", "HYG", "HY credit ETF", "crypto", "px"),
    ("TLT", "TLT", "20Y+ Treasury ETF", "crypto", "px"),
]

# The eleven S&P sector SPDRs plus the two benchmarks rotation is measured
# against. Kept separate from UNIVERSE because the rotation panel wants them
# as a SET — relative strength is meaningless one row at a time.
SECTORS: list[tuple[str, str, str]] = [
    ("XLK", "XLK", "Technology"),
    ("XLC", "XLC", "Communication"),
    ("XLY", "XLY", "Cons. Discretionary"),
    ("XLP", "XLP", "Cons. Staples"),
    ("XLE", "XLE", "Energy"),
    ("XLF", "XLF", "Financials"),
    ("XLV", "XLV", "Health Care"),
    ("XLI", "XLI", "Industrials"),
    ("XLB", "XLB", "Materials"),
    ("XLRE", "XLRE", "Real Estate"),
    ("XLU", "XLU", "Utilities"),
    ("SPY", "SPY", "S&P 500"),
    ("RSP", "RSP", "S&P 500 equal weight"),
]

# The themes beside the sectors (owner, 2026-11-09): where inside technology, or
# outside the eleven SPDRs altogether, the money is going. Same arithmetic as the
# sectors, read on the same clock, shown behind a toggle on the same panel.
THEMES: list[tuple[str, str, str]] = [
    ("SMH", "SMH", "Semis"),
    ("DRAM", "DRAM", "Memory"),
    ("IGV", "IGV", "Software"),
    ("CIBR", "CIBR", "Cybersecurity"),
    ("SKYY", "SKYY", "Cloud"),
    ("QTUM", "QTUM", "Quantum"),
    ("BOTZ", "BOTZ", "Robotics & AI"),
    ("ARKK", "ARKK", "Innovation"),
    ("WGMI", "WGMI", "Bitcoin Miners"),
    ("XBI", "XBI", "Biotech"),
    ("ITA", "ITA", "Aerospace & Defense"),
    ("NASA", "NASA", "Space"),
    ("KRE", "KRE", "Regional Banks"),
    ("XHB", "XHB", "Homebuilders"),
    ("JETS", "JETS", "Airlines"),
    ("PAVE", "PAVE", "Infrastructure"),
    ("GRID", "GRID", "Smart Grid"),
    ("TAN", "TAN", "Solar"),
    ("URA", "URA", "Uranium"),
    ("XOP", "XOP", "Oil & Gas E&P"),
    ("GDX", "GDX", "Gold Miners"),
    ("COPX", "COPX", "Copper Miners"),
    ("XME", "XME", "Metals & Mining"),
    ("KWEB", "KWEB", "China Internet"),
    ("FXI", "FXI", "China Large Cap"),
]

# THE MULTI-DAY CONTEXT a desk brief quotes and a one-day board cannot: "WTI
# +11% on the week", "10Y from 4.80 to 4.96 in five sessions", "miners lagging
# GLD". Daily bars over a month, fetched on the sectors' clock and kept out of
# UNIVERSE so the board's fifteen-second poll never pays for a month of
# history. IWM, GDX and GVZ live only here: they are ratio legs and an implied
# vol for the brief, not rows anyone wants on the board.
CONTEXT: list[tuple[str, str, str]] = [
    ("NQ", "NQ=F", "Nasdaq 100 fut"),
    ("ES", "ES=F", "S&P 500 fut"),
    ("GC", "GC=F", "Gold fut"),
    ("SILVER", "SI=F", "Silver"),
    ("WTI", "CL=F", "WTI crude"),
    ("US10Y", "^TNX", "10-year"),
    ("DXY", "DX-Y.NYB", "Dollar index"),
    ("USDJPY", "JPY=X", "USD/JPY"),
    ("QQQ", "QQQ", "QQQ"),
    ("IWM", "IWM", "Russell 2000 ETF"),
    ("GLD", "GLD", "GLD"),
    ("GDX", "GDX", "Gold miners ETF"),
    ("GVZ", "^GVZ", "Gold vol (GVZ)"),
    # Silver's and crude's own implied vols, for their implied day (volterm.EM_VOL).
    ("VXSLV", "^VXSLV", "Silver vol (VXSLV)"),
    ("OVX", "^OVX", "Crude vol (OVX)"),
    # The VIX's own month (volterm.vix_month): twenty closes, both desks.
    ("VIX", "^VIX", "VIX"),
    # THE BIAS'S YARDSTICKS (2026-11-19, drivestats.py): each driver's usual day and how
    # it has moved with each book lately, so a read is weighed by its size and a driver
    # votes only while it is driving. Credit, the 10-year note future (the rates read
    # while the cash yield is shut), copper and the two products had no daily history.
    ("HYG", "HYG", "High yield (HYG)"),
    ("ZN", "ZN=F", "10-year note fut"),
    ("COPPER", "HG=F", "Copper"),
    ("RBOB", "RB=F", "Gasoline"),
    ("HEATOIL", "HO=F", "Heating oil"),
]

#: How much daily history the context feed asks for, and how much of it the week and
#: month figures read. The bias's yardsticks read the whole of it (`hist`): sixty
#: sessions is what a correlation needs to mean anything, where twenty is mostly noise.
CONTEXT_RANGE = "3mo"
MONTH_BARS = 22

#: Context rows read for their level alone, kept when Yahoo has too few closes for a change.
LEVEL_ONLY: frozenset[str] = frozenset({"VXSLV", "OVX", "GVZ"})

# Yahoo starts truncating the response somewhere above ~20 symbols; 12 keeps
# every chunk comfortably inside that and still costs only four requests.
CHUNK = 12


def _chunks(items: list[str], n: int) -> list[list[str]]:
    return [items[i : i + n] for i in range(0, len(items), n)]


def spark_key(symbols: list[str], rng: str, iv: str) -> str:
    """The cache key for one spark request. Pure, and STABLE ACROSS PROCESSES.

    It used to be `abs(hash(tuple(symbols)))`, and Python salts str hashes per
    process — so every restart wrote a fresh set of keys, never read the old
    ones (no warm start, no stale fallback after a restart), and left them on
    disk: 957 orphaned spark files, 20MB, by 2026-10-13. A digest of the list
    is the same every run.
    """
    return f"spark_{rng}_{iv}_{hashlib.sha1(','.join(symbols).encode()).hexdigest()[:12]}"


def _spark(symbols: list[str], rng: str, iv: str, ttl: float, *,
           st: SourceStatus | None = None,
           stale_max: float | None = None,
           prepost: bool = False) -> tuple[dict[str, Any], str | None]:
    """One spark request → {yahoo symbol: response}. Never raises.

    `st` absorbs the fetch's provenance, so a collector built on this can say
    when it is showing a cached copy; `stale_max` caps how old that copy may be.
    `prepost` asks for the extended hours' bars as well (`collect_extended`).
    """
    q = urllib.parse.quote(",".join(symbols), safe="")
    url = SPARK.format(syms=q, rng=rng, iv=iv) + ("&includePrePost=true" if prepost else "")
    # The cache key must not be the URL: it carries the whole symbol list and
    # would produce a different 400-character filename every time the universe
    # is edited, quietly orphaning the old cache entries.
    r = fetch(url, key=spark_key(symbols, rng, iv) + ("_pp" if prepost else ""), ttl_sec=ttl,
              ua=BROWSER_UA, timeout=20, stale_max_sec=stale_max, validate=json_body)
    if st is not None:
        st.absorb(r)
    if not r.ok:
        return {}, r.error
    try:
        doc = r.json()
    except (ValueError, TypeError) as e:
        return {}, f"unparseable: {e}"
    out: dict[str, Any] = {}
    for row in (doc.get("spark") or {}).get("result") or []:
        resp = (row.get("response") or [None])[0]
        if resp:
            out[row.get("symbol")] = resp
    return out, None


#: A print this many minutes behind the clock, while its market trades, is
#: called delayed rather than live. Yahoo carries CME futures ten minutes
#: late and Tokyo's and Hong Kong's indices fifteen to twenty.
LIVE_LAG_MIN = 2.0
#: Past this with no print, a market is not "delayed" but not trading — a
#: lunch break, a grain contract between sessions, a feed that stopped. Said
#: as "stale" and drawn like a closed market, never as a late live one.
STALE_LAG_MIN = 30.0
#: A closing print can land a moment after the session's stated end (the VIX
#: settles 15:15:01 CT against a 15:15 end).
CLOSE_SLACK_SEC = 300

_ET = ZoneInfo("America/New_York")


def cme_break(now: float) -> bool:
    """Is Globex in its daily or weekend halt — 17:00–18:00 ET Monday to
    Thursday, Friday 17:00 to Sunday 18:00? Pure. Holidays are not modelled:
    a halted holiday reads "stale" after half an hour, which is still true."""
    et = datetime.fromtimestamp(now, _ET)
    wd, h = et.weekday(), et.hour
    if wd == 5 or (wd == 4 and h >= 17) or (wd == 6 and h < 18):
        return True
    return h == 17


def feed_state(meta: dict[str, Any], now: float) -> tuple[str, float | None]:
    """How current one instrument's price is: "live", "delayed", "stale" or
    "closed", and the minutes its last print trails `now`. Pure.

    WHY THE BOARD NEEDS IT (audit, 2026-10-14). Every module's chip said
    "live" under a minute after the FETCH, and the fetch is not the print: ES
    on Yahoo is ten minutes late around the clock, and after the cash close
    the VIX and the 10-year are hours old while their row looks like any
    other.

    CLOSED IS THE EXCHANGE'S WORD, CHECKED AGAINST THE PRINT. Yahoo's
    `currentTradingPeriod` is the session a cash market is in or waiting for —
    at 01:16 ET the 10-year's was 08:20–15:00 that day, its last print the
    previous 14:59:55 — but for a 24-hour market it is only the calendar day
    (ES: 00:00–23:59 ET; bitcoin: the UTC day), whose edges are not closes. So
    a period counts as over only if the last print came before its end, and
    as not yet begun only if the print came before its start; a print outside
    it means the market traded on. CME's own halts are known (`cme_break`).
    Past that, the gap between the last print and the clock decides.
    """
    t = meta.get("regularMarketTime")
    if not isinstance(t, (int, float)) or t <= 0:
        return "stale", None
    lag = round(max(0.0, (now - float(t)) / 60.0), 1)
    period = (meta.get("currentTradingPeriod") or {}).get("regular") or {}
    start, end = period.get("start"), period.get("end")
    if isinstance(start, (int, float)) and isinstance(end, (int, float)):
        if now >= end and t <= end + CLOSE_SLACK_SEC:
            return "closed", lag
        if now < start and t < start:
            return "closed", lag
    if str(meta.get("symbol") or "").endswith("=F") and cme_break(now):
        return "closed", lag
    if lag < LIVE_LAG_MIN:
        return "live", lag
    return ("delayed" if lag <= STALE_LAG_MIN else "stale"), lag


def _row(key: str, label: str, group: str, fmt: str, resp: dict[str, Any],
         now: float | None = None) -> dict[str, Any] | None:
    """One spark response → one board row. Pure but for the default clock."""
    meta = resp.get("meta") or {}
    px = meta.get("regularMarketPrice")
    if px is None:
        return None
    prev = meta.get("chartPreviousClose") or meta.get("previousClose")
    chg = px - prev if prev else None
    pct = (
        (chg / prev * 100.0)
        if (chg is not None and prev)
        else meta.get("regularMarketChangePercent")
    )

    # The intraday closes, for the sparkline. Nulls are holes in the session
    # (a halt, a thin future overnight) and are dropped rather than zero-filled
    # — a zero would draw a spike to the axis that never traded.
    closes: list[float] = []
    try:
        raw = ((resp.get("indicators") or {}).get("quote") or [{}])[0].get("close") or []
        closes = [float(c) for c in raw if c is not None]
    except (TypeError, ValueError, IndexError, AttributeError):
        closes = []

    hi, lo = meta.get("regularMarketDayHigh"), meta.get("regularMarketDayLow")
    feed, lag = feed_state(meta, time.time() if now is None else now)
    return {
        "key": key,
        "symbol": meta.get("symbol"),
        "label": label,
        "name": meta.get("shortName") or label,
        "group": group,
        "fmt": fmt,
        "last": px,
        "prev": prev,
        "chg": chg,
        "pct": pct,
        "high": hi,
        "low": lo,
        # Where in the day's range this print sits, 0 at the low and 1 at the
        # high. The single most useful number on a board after the change, and
        # it cannot be eyeballed from three separate columns.
        "range_pos": ((px - lo) / (hi - lo)) if (hi and lo and hi > lo) else None,
        "wk52_high": meta.get("fiftyTwoWeekHigh"),
        "wk52_low": meta.get("fiftyTwoWeekLow"),
        "volume": meta.get("regularMarketVolume"),
        "currency": meta.get("currency"),
        "exchange": meta.get("exchangeName"),
        "quote_time": meta.get("regularMarketTime"),
        # Measured when the row is built, so a cached copy served late reads
        # later still — see feed_state.
        "feed": feed,
        "lag_min": lag,
        "spark": closes[-80:],
    }


def collect() -> tuple[list[dict[str, Any]], SourceStatus]:
    """The whole board. One status for the lot; partial results are normal."""
    st = SourceStatus("Yahoo quotes")
    rows: list[dict[str, Any]] = []
    errors: list[str] = []
    by_symbol: dict[str, Any] = {}

    for chunk in _chunks([u[1] for u in UNIVERSE], CHUNK):
        # Ten minutes is the most a price on the board may lag before it is
        # called unavailable rather than served — a quote older than that is
        # not a degraded quote, it is a wrong one.
        got, err = _spark(chunk, "1d", "5m", ttl=15.0, st=st, stale_max=600.0)
        by_symbol.update(got)
        if err:
            errors.append(err)

    for key, sym, label, group, fmt in UNIVERSE:
        resp = by_symbol.get(sym)
        if not resp:
            continue
        row = _row(key, label, group, fmt, resp)
        if row:
            rows.append(row)

    st.items = len(rows)
    if errors:
        st.error = errors[0]
        total = len(_chunks([u[1] for u in UNIVERSE], CHUNK))
        st.notes = [f"{len(errors)} of {total} chunks failed"]
    missing = len(UNIVERSE) - len(rows)
    if missing:
        st.notes.append(f"{missing} instrument(s) did not quote")
    st.settle(len(rows) > 0, "chunk")
    return rows, st


def _daily_row(key: str, label: str, resp: dict[str, Any]) -> dict[str, Any] | None:
    """One month of daily bars → day, week and month change. Pure.

    The changes come as percentages AND as plain differences, because a yield
    is discussed in the second: "the 10Y is +3.6% on the week" is true and
    nobody says it.
    """
    meta = resp.get("meta") or {}
    px = meta.get("regularMarketPrice")
    try:
        closes = [
            float(c)
            for c in (((resp.get("indicators") or {}).get("quote") or [{}])[0].get("close") or [])
            if c is not None
        ]
    except (TypeError, ValueError, IndexError, AttributeError):
        closes = []
    if px is None:
        return None
    if len(closes) < 2:
        # A vol index read only for its level (silver's VXSLV, of which Yahoo keeps one
        # close) still answers with that level; anything else needs a series to be a row.
        if key not in LEVEL_ONLY:
            return None
        return {"key": key, "label": label, "last": px, "day_pct": None, "week_pct": None,
                "month_pct": None, "week_chg": None, "month_chg": None, "closes": closes}
    # THE PRIOR CLOSE COMES FROM THE SERIES, NOT FROM meta.
    #
    # Over a 1-month range `chartPreviousClose` is the close before the
    # WINDOW, not before today — so using it here printed the month's move
    # in the day column and had Technology up 8.5% "today". The daily bars
    # are right there: closes[-1] is today's (still forming), closes[-2] is
    # yesterday's settle, which is what a day change is measured against.
    prev = closes[-2]
    first = closes[0]
    wk1 = closes[-6] if len(closes) >= 6 else closes[0]
    return {
        "key": key,
        "label": label,
        "last": px,
        "day_pct": ((px - prev) / prev * 100.0) if prev else None,
        "week_pct": ((px - wk1) / wk1 * 100.0) if wk1 else None,
        "month_pct": ((px - first) / first * 100.0) if first else None,
        "week_chg": px - wk1,
        "month_chg": px - first,
        "closes": closes,
    }


def _tail(resp: dict[str, Any], n: int) -> dict[str, Any]:
    """A spark response cut to its last `n` bars, meta untouched. Pure."""
    try:
        quote = dict(((resp.get("indicators") or {}).get("quote") or [{}])[0])
    except (TypeError, IndexError, AttributeError):
        return resp
    quote["close"] = list(quote.get("close") or [])[-n:]
    return {**resp, "timestamp": list(resp.get("timestamp") or [])[-n:],
            "indicators": {**(resp.get("indicators") or {}), "quote": [quote]}}


def daily_hist(resp: dict[str, Any]) -> dict[str, list[Any]]:
    """Each daily bar's date (the exchange's own) beside its close, bars without a close
    dropped as a pair, so two instruments' days can be lined up across their holidays.
    Pure."""
    off = int(((resp.get("meta") or {}).get("gmtoffset")) or 0)
    try:
        raw = ((resp.get("indicators") or {}).get("quote") or [{}])[0].get("close") or []
    except (TypeError, IndexError, AttributeError):
        raw = []
    days: list[str] = []
    closes: list[float] = []
    for t, c in zip(resp.get("timestamp") or [], raw, strict=False):
        if c is None or t is None:
            continue
        days.append(datetime.fromtimestamp(int(t) + off, UTC).date().isoformat())
        closes.append(float(c))
    return {"days": days, "closes": closes}


def collect_context() -> tuple[list[dict[str, Any]], SourceStatus]:
    """Daily bars for the brief's multi-day figures. See CONTEXT."""
    st = SourceStatus("Daily context")
    got: dict[str, Any] = {}
    errors: list[str] = []
    for chunk in _chunks([c[1] for c in CONTEXT], CHUNK):
        part, err = _spark(chunk, CONTEXT_RANGE, "1d", ttl=300.0, st=st, stale_max=2 * 3600.0)
        got.update(part)
        if err:
            errors.append(err)

    rows: list[dict[str, Any]] = []
    for key, sym, label in CONTEXT:
        resp = got.get(sym)
        # The week and month figures read the last month, as they did when the request
        # was for a month; the yardsticks read the whole three.
        row = _daily_row(key, label, _tail(resp, MONTH_BARS)) if resp else None
        if row is None:
            continue
        row["closes"] = row["closes"][-23:]
        row["hist"] = daily_hist(resp or {})
        rows.append(row)

    st.items = len(rows)
    if errors:
        st.error = errors[0]
    missing = len(CONTEXT) - len(rows)
    if missing:
        st.notes.append(f"{missing} instrument(s) did not quote")
    st.settle(len(rows) > 0, "chunk")
    return rows, st


def collect_sectors() -> tuple[list[dict[str, Any]], SourceStatus]:
    """The eleven SPDRs plus SPY and RSP, on a 1-month clock.

    A MONTH, NOT A DAY. Rotation is a claim about which sector is being bought
    over weeks; one session's change is noise against it, and a leadership
    table built on a single day would reshuffle every morning and mean nothing.
    The daily change comes along for the ride so the panel can show both.
    """
    st = SourceStatus("Sector SPDRs")
    got: dict[str, Any] = {}
    errors: list[str] = []
    for chunk in _chunks([s[1] for s in SECTORS], CHUNK):
        part, err = _spark(chunk, "1mo", "1d", ttl=SECTOR_TTL, st=st, stale_max=2 * 3600.0)
        got.update(part)
        if err:
            errors.append(err)

    rows: list[dict[str, Any]] = []
    for key, sym, label in SECTORS:
        resp = got.get(sym)
        row = _daily_row(key, label, resp) if resp else None
        if row is None:
            continue
        row["spark"] = row.pop("closes")[-30:]
        del row["week_chg"], row["month_chg"]
        rows.append(row)

    # Relative strength against the cap-weighted benchmark, which is the only
    # form of this number that answers "is money rotating INTO this".
    spy = next((r for r in rows if r["key"] == "SPY"), None)
    if spy:
        for r in rows:
            for span in ("day", "week", "month"):
                mine, base = r.get(f"{span}_pct"), spy.get(f"{span}_pct")
                r[f"rs_{span}"] = (mine - base) if (mine is not None and base is not None) else None

    st.items = len(rows)
    if errors:
        st.error = errors[0]
    st.settle(len(rows) > 2, "chunk")
    return rows, st


# ---- the funds outside the session (2026-11-16) ---------------------------------------
#
# WHY (owner: "do they move during extended hours also?. i think we should make the app
# update as to wait theyre actually doing. right now im missing the sectors information
# going into the aopen and to do my analysis before the open"). The cards were read off
# the daily bars, whose price is the regular session's: before the bell every card held
# Friday's move while XLK traded 1.4% lower and SMH 3.4% lower. The funds trade from
# 04:00 to 09:30 and 16:00 to 20:00 ET, and the spark request carries those bars when
# asked (`includePrePost`), many funds to a request.
#
# THE MOVE IS AGAINST THE LAST REGULAR CLOSE: before the bell the last session's close,
# after it today's. Yahoo's `regularMarketPrice` is exactly that outside the session (its
# `chartPreviousClose` is not: it read Thursday's close on a Monday morning).
#
# THIN, AND SAID SO. A sector fund can go twenty minutes without a trade before the bell,
# and Yahoo gives no extended-hours volume for these funds, so each read carries the
# time of its last trade and how many five-minute bars had one.
#
# The engine's own sector reads (the tape count, the driver board, the reports) keep the
# regular session's moves: this is the Sectors page's, joined on (universe.heatmap).

#: The extended hours, in minutes of the New York day.
PRE_START_MIN = 4 * 60
RTH_START_MIN = 9 * 60 + 30
POST_END_MIN = 20 * 60


def _close_min(d: Any) -> int:
    from ..holidays import close_minute

    return close_minute(d)


def ext_read(resp: dict[str, Any] | None) -> dict[str, Any] | None:
    """A fund's last extended-hours trade from a spark response with the extended bars:
    which side of the session it is (`pre` or `post`), its price, the move against the
    last regular close, when, and how many five-minute bars had a trade in that stretch.
    None when the last trade is the regular session's or there is none. Pure."""
    if not isinstance(resp, dict):
        return None
    ref = (resp.get("meta") or {}).get("regularMarketPrice")
    try:
        ts = resp.get("timestamp") or []
        closes = ((resp.get("indicators") or {}).get("quote") or [{}])[0].get("close") or []
    except (AttributeError, IndexError, TypeError):
        return None
    bars = [(int(t), float(c)) for t, c in zip(ts, closes, strict=False)
            if c is not None and t is not None]
    if not bars or not isinstance(ref, int | float) or not ref:
        return None

    def side(t: int) -> tuple[str, str]:
        et = datetime.fromtimestamp(t, _ET)
        m = et.hour * 60 + et.minute
        kind = "pre" if m < RTH_START_MIN else "post" if m >= _close_min(et.date()) else "rth"
        return kind, et.date().isoformat()

    last_t, last_c = bars[-1]
    kind, day = side(last_t)
    if kind == "rth":
        return None
    n = sum(1 for t, _ in bars if side(t) == (kind, day))
    return {"kind": kind, "day": day, "px": last_c, "ref": float(ref),
            "pct": (last_c - ref) / ref * 100.0, "at": last_t, "bars": n}


def extended_now(now: datetime | None = None) -> bool:
    """Whether the funds can be trading outside the session at `now`: a trading day,
    04:00 to the bell or the close to 20:00 ET, with a few minutes either side. Pure."""
    from ..holidays import is_trading_day

    et = (now or datetime.now(_ET)).astimezone(_ET)
    if not is_trading_day(et.date()):
        return False
    m = et.hour * 60 + et.minute
    close = _close_min(et.date())
    return (PRE_START_MIN <= m < RTH_START_MIN + 2) or (close <= m < POST_END_MIN + 5)


#: The price board's US-listed funds, which trade before the bell and after the close
#: like the sector funds (the audit of 2026-11-16: the SPY, QQQ and IWM tiles read
#: Friday's close at 08:16 ET on a Monday while SPY traded 0.6% lower).
BOARD_EXT: tuple[str, ...] = ("SPY", "QQQ", "IWM", "GLD", "HYG", "TLT")


def regular_now(now: datetime | None = None) -> bool:
    """Whether the regular session is on at `now` (a trading day, the bell to the close,
    a few minutes past it so the closing print lands). Pure."""
    from ..holidays import is_trading_day

    et = (now or datetime.now(_ET)).astimezone(_ET)
    if not is_trading_day(et.date()):
        return False
    m = et.hour * 60 + et.minute
    return RTH_START_MIN <= m < _close_min(et.date()) + 5


#: How long a sector or theme read is kept (2026-11-16, the owner's yes to reading them
#: each minute in the session, where it was five): under the job's minute, so each run
#: asks Yahoo afresh. Outside the session the job runs every five minutes, as before.
SECTOR_TTL = 45.0


def collect_extended() -> tuple[dict[str, dict[str, Any]], SourceStatus]:
    """Every sector and theme fund's last extended-hours trade (`ext_read`), by key, and
    the price board's US-listed funds' (`BOARD_EXT`)."""
    st = SourceStatus("US funds, extended hours")
    pairs = {key: sym for key, sym, _ in [*SECTORS, *THEMES]}
    pairs.update({k: k for k in BOARD_EXT})
    got: dict[str, Any] = {}
    errors: list[str] = []
    for chunk in _chunks(sorted(set(pairs.values())), CHUNK):
        part, err = _spark(chunk, "1d", "5m", ttl=45.0, st=st, stale_max=1800.0, prepost=True)
        got.update(part)
        if err:
            errors.append(err)
    out = {key: x for key, sym in pairs.items() if (x := ext_read(got.get(sym))) is not None}
    st.items = len(out)
    if errors:
        st.error = errors[0]
    # Nothing to read in the session is not a failure: only a request that failed is.
    st.settle(not errors or bool(got), "chunk")
    return out, st


def with_ext(rows: list[dict[str, Any]], ext: dict[str, dict[str, Any]],
             today: str) -> list[dict[str, Any]]:
    """The price board with each US-listed fund's extended trade beside its regular price
    (`ext`: kind, px, pct, at), for the pages' tiles and the Macro board. A pre-market
    read counts only on its own day; an after-hours one is the latest there is, through
    the night. `last` and `pct` stay the regular session's: the engine reads those. Pure."""
    out: list[dict[str, Any]] = []
    for r in rows:
        x = ext.get(str(r.get("key"))) if r.get("key") in BOARD_EXT else None
        ok = x is not None and (x.get("kind") == "post" or x.get("day") == today)
        out.append({**r, "ext": {k: x.get(k) for k in ("kind", "px", "pct", "at", "day")}}
                   if ok and x is not None else r)
    return out


def collect_themes() -> tuple[list[dict[str, Any]], SourceStatus]:
    """The theme ETFs, against SPY — `collect_sectors` for the longer list."""
    st = SourceStatus("Theme ETFs")
    names = [t[1] for t in THEMES]
    got: dict[str, Any] = {}
    errors: list[str] = []
    for chunk in _chunks([*names, "SPY"], CHUNK):
        part, err = _spark(chunk, "1mo", "1d", ttl=SECTOR_TTL, st=st, stale_max=2 * 3600.0)
        got.update(part)
        if err:
            errors.append(err)
    rows: list[dict[str, Any]] = []
    for key, sym, label in [*THEMES, ("SPY", "SPY", "S&P 500")]:
        resp = got.get(sym)
        row = _daily_row(key, label, resp) if resp else None
        if row is None:
            continue
        row["spark"] = row.pop("closes")[-30:]
        del row["week_chg"], row["month_chg"]
        rows.append(row)
    spy = next((r for r in rows if r["key"] == "SPY"), None)
    if spy:
        for r in rows:
            for span in ("day", "week", "month"):
                mine, base = r.get(f"{span}_pct"), spy.get(f"{span}_pct")
                r[f"rs_{span}"] = (mine - base) if (mine is not None and base is not None) else None
    st.items = len(rows)
    if errors:
        st.error = errors[0]
    st.settle(len(rows) > 2, "chunk")
    return rows, st
