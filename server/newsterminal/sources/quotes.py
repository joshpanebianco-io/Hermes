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
import urllib.parse
from typing import Any

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
    ("US2Y", "^IRX", "13-week bill", "rates", "bp"),
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
]

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
           stale_max: float | None = None) -> tuple[dict[str, Any], str | None]:
    """One spark request → {yahoo symbol: response}. Never raises.

    `st` absorbs the fetch's provenance, so a collector built on this can say
    when it is showing a cached copy; `stale_max` caps how old that copy may be.
    """
    q = urllib.parse.quote(",".join(symbols), safe="")
    url = SPARK.format(syms=q, rng=rng, iv=iv)
    # The cache key must not be the URL: it carries the whole symbol list and
    # would produce a different 400-character filename every time the universe
    # is edited, quietly orphaning the old cache entries.
    r = fetch(url, key=spark_key(symbols, rng, iv), ttl_sec=ttl, ua=BROWSER_UA, timeout=20,
              stale_max_sec=stale_max, validate=json_body)
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


def _row(key: str, label: str, group: str, fmt: str, resp: dict[str, Any]) -> dict[str, Any] | None:
    """One spark response → one board row. Pure."""
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
    if px is None or len(closes) < 2:
        return None
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


def collect_context() -> tuple[list[dict[str, Any]], SourceStatus]:
    """Daily bars for the brief's multi-day figures. See CONTEXT."""
    st = SourceStatus("Daily context")
    got: dict[str, Any] = {}
    errors: list[str] = []
    for chunk in _chunks([c[1] for c in CONTEXT], CHUNK):
        part, err = _spark(chunk, "1mo", "1d", ttl=300.0, st=st, stale_max=2 * 3600.0)
        got.update(part)
        if err:
            errors.append(err)

    rows: list[dict[str, Any]] = []
    for key, sym, label in CONTEXT:
        resp = got.get(sym)
        row = _daily_row(key, label, resp) if resp else None
        if row is None:
            continue
        row["closes"] = row["closes"][-23:]
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
        part, err = _spark(chunk, "1mo", "1d", ttl=300.0, st=st, stale_max=2 * 3600.0)
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
