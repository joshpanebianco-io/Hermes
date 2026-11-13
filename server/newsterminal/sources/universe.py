"""
The wide read — every US stock worth looking at, in one request.

WHY (owner, 2026-11-09, the screenshots: "I always miss the big breakouts"). The
scanner runs forty names deep. The pool in front of it reads the $5bn+ names, ranks
them on the gap and the volume, and stops adding to the list at 10:00. A stock that
first breaks out at 11:40 and was not already on the list was never seen at all.

THE SAME ENDPOINT THE POOL READS, ASKED FOR MORE. TradingView's screener answers
every US stock and DR in one POST, and PROBED 2026-11-09 it carries the columns the
strategy is made of: `premarket_high` / `premarket_low`, `high[1]` / `low[1]` and
`[2]` (the two previous sessions' bars; `[3]` and deeper come back null on every
row), `gap`, the post-market figures, the day's bar, `industry`, the float. So the
wide scan can say which names are through PMH and PDH without a single chart read.

FIFTEEN MINUTES BEHIND, ON EVERY ROW. `update_mode` is `delayed_streaming_900` on
all 6,094. This is the finder: the stream (sources/stream.py) watches the best few
hundred of what it finds, and a name traded from is a tracked name, whose levels
are still the desk's own (a check of Friday 6 Nov: PDH and PDL within 2c of the
desk's on 26 of 30, PMH within 5c on 23 of 30, PML on 7 of 30, pre-market lows
being the noisiest print of the day on every feed).

THE COLUMNS CHANGE MEANING WITH THE CLOCK, and `basis_at` is the one place that
says so. Before the open TradingView's current daily bar is still yesterday's: the
pool's docstring confirmed `close` is the previous close before 09:30, live, on 5
Nov. So the previous day's high is `high` before the open and `high[1]` after it,
and the fifteen-minute delay moves that flip to 09:45.

    basis   from (ET)   PDH / PDL     last price          the base bar is
    pre     04:15       high / low    premarket_close     the previous session
    rth     09:45       high[1]...    close               today
    post    16:15       high[1]...    postmarket_close    today
    last    20:15       high[1]...    close               the session just finished

`last` is every other hour, weekends included: the whole read of the session that
finished, which is what a page opened on a Sunday should show. Half days move the
16:15 and the 20:15 with the holiday table. tests/test_universe.py prints each
boundary minute.

ONE MORE TRAP: A NAME THAT HAS NOT TRADED YET. The pre-market columns keep the last
session's figures until a new pre-market trade replaces them, so at 08:00 a quiet
name still shows yesterday's PMH. `pm_ref` is those columns as they stood before
the session began, and a row that still equals them has no pre-market today. The
post-market columns are guarded the same way.

RELATIVE VOLUME OUTSIDE THE SESSION HAS TO BE WRITTEN DOWN. The screener's relative
volume is a regular-session figure and no feed here gives a name's usual pre-market:
Yahoo's pre-market bars carry no volume. So each evening every name's finished
pre-market and after-hours volume goes on a thirty-session list (`pm_hist`, `ah_hist`),
and five sessions make an average worth dividing by. Until a name has five, the
figure is an estimate from its share of an average day and the row says so.

A PERSONAL READ OF A PUBLIC PAGE'S DATA, like the pool: one request a pass, a browser
User-Agent, a 403 or 429 answered with a ten-minute pause.
"""

from __future__ import annotations

import json
import math
import os
import statistics
import threading
import urllib.parse
from collections.abc import Callable, Iterable
from dataclasses import dataclass, field
from datetime import UTC, date, datetime
from typing import Any

from .. import scan
from ..config import BROWSER_UA, CACHE_DIR
from ..holidays import is_trading_day, prev_trading_day
from ..http import SourceStatus, fetch, json_body
from .holdings import US_LISTED
from .pool import HEADERS, URL, pool_body, session_points
from .quotes import SPARK
from .quotes import THEMES as ETF_THEMES
from .scanner import _SYM, SECTOR

CACHE_KEY = "tv_universe"
STATE_FILE = os.path.join(CACHE_DIR, "scanner_universe.json")
COLUMNS = [
    "name", "description", "type", "typespecs", "update_mode",
    "close", "change", "open", "high", "low", "volume", "gap", "ATR",
    "premarket_high", "premarket_low", "premarket_close", "premarket_change", "premarket_volume",
    "postmarket_close", "postmarket_change", "postmarket_volume",
    "average_volume_30d_calc", "relative_volume_intraday|5", "market_cap_basic",
    "float_shares_outstanding", "sector", "industry", "country", "Perf.W", "Perf.1M",
    "open[1]", "high[1]", "low[1]", "close[1]", "volume[1]",
    "high[2]", "low[2]", "close[2]", "volume[2]",
]
#: The floor of the read. The table's own filter defaults higher.
MIN_CAP = 300_000_000.0
RANGE = 7000
DELAY_MIN = 15
ACTIVE_SEC = 120.0
IDLE_SEC = 1800.0
TICK_SEC = 20.0
TIMEOUT = 30
PAUSE_SEC = 600.0
STALE_MAX_SEC = 6 * 3600.0
#: A table ships at most this many rows; the counts above it are of them all.
MAX_ROWS = 200
#: The names worth the stream, beyond the tracked list.
CANDIDATES = 300
SPARK_TICK_SEC = 5.0
SPARK_CHUNK = 12
SPARK_TTL = 240.0
SPARK_IDLE_TTL = 1800.0
#: A gap of this many percent, either way, is what the Gaps chip counts.
GAP_PCT = 2.0

DEFAULT_CAP = 2e9
DEFAULT_VOL = 5e5
DEFAULT_RVOL = 2.0
DEFAULT_PM_VOL = 1e5
DEFAULT_AH_VOL = 5e4
#: Sessions of extended-hours volume kept for each name, and how many make an average.
VOL_KEEP = 30
VOL_MIN_DAYS = 5
#: What share of an average day counts as a normal extended session: the estimate's divisor.
USUAL_ADV_PCT = {"pre": 5.0, "post": 2.0}

#: Themes with a clean match in TradingView's `industry`, for the table's filter.
THEMES: list[tuple[str, str, frozenset[str]]] = [
    ("SMH", "Semis", frozenset({"Semiconductors", "Electronic Production Equipment"})),
    # Packaged Software alone: all ten of IGV's largest are in it, and TradingView's
    # internet group would bring in Alphabet, Meta and Netflix.
    ("IGV", "Software", frozenset({"Packaged Software"})),
    ("XBI", "Biotech", frozenset({"Biotechnology"})),
    ("ITA", "Aerospace & Defense", frozenset({"Aerospace & Defense"})),
    # Both groups: TradingView files KeyCorp, Regions, Huntington and Citizens as major banks.
    ("KRE", "Regional Banks", frozenset({"Regional Banks", "Major Banks"})),
    ("XHB", "Homebuilders", frozenset({"Homebuilding"})),
    ("JETS", "Airlines", frozenset({"Airlines"})),
    ("GDX", "Gold Miners", frozenset({"Precious Metals"})),
    ("XME", "Metals & Mining", frozenset({"Other Metals/Minerals", "Steel", "Aluminum"})),
]
THEME_OF: dict[str, str] = {i: k for k, _, inds in THEMES for i in inds}
INDUSTRIES: dict[str, frozenset[str]] = {k: inds for k, _, inds in THEMES}
#: Where an industry and its theme part ways, found by reading each fund's top ten against
#: the list (2026-11-09). TradingView files First Solar and Sunrun as chipmakers, and the
#: national banks and a fintech in the same group as KeyCorp and Regions.
NOT_IN_THEME: dict[str, frozenset[str]] = {
    "SMH": frozenset({"FSLR", "RUN"}),
    "KRE": frozenset({"JPM", "BAC", "WFC", "C", "USB", "PNC", "COF", "DAVE"}),
}
#: TradingView's bank groups take in ICICI, CIBC and HSBC; the theme is American banks.
US_ONLY_THEMES: frozenset[str] = frozenset({"KRE"})
#: A US territory's banks count as American.
US_COUNTRIES: frozenset[str] = frozenset({"United States", "Puerto Rico"})

#: TradingView's INDUSTRY → the S&P sector SPDR. Its broader `sector` column will not
#: do: "Finance" holds the banks and the REITs together, "Electronic Technology" puts
#: defence contractors with the chipmakers and "Producer Manufacturing" has Lam
#: Research. Mixed industries (data processing, commercial services, conglomerates,
#: closed-end funds) are left out: a wrong sector is worse than none.
_SECTOR_INDUSTRIES: dict[str, tuple[str, ...]] = {
    "XLK": ("Semiconductors", "Electronic Production Equipment", "Packaged Software",
            "Information Technology Services", "Internet Software/Services",
            "Computer Processing Hardware", "Computer Peripherals", "Computer Communications",
            "Telecommunications Equipment", "Electronic Components",
            "Electronic Equipment/Instruments", "Electronics Distributors"),
    "XLC": ("Major Telecommunications", "Wireless Telecommunications",
            "Specialty Telecommunications", "Cable/Satellite TV", "Broadcasting",
            "Movies/Entertainment", "Media Conglomerates", "Advertising/Marketing Services",
            "Publishing: Books/Magazines", "Publishing: Newspapers"),
    "XLI": ("Aerospace & Defense", "Industrial Machinery", "Trucks/Construction/Farm Machinery",
            "Railroads", "Air Freight/Couriers", "Airlines", "Marine Shipping", "Trucking",
            "Other Transportation", "Engineering & Construction", "Building Products",
            "Electrical Products", "Industrial Conglomerates", "Environmental Services",
            "Personnel Services", "Metal Fabrication", "Tools & Hardware"),
    "XLY": ("Motor Vehicles", "Auto Parts: OEM", "Automotive Aftermarket", "Homebuilding",
            "Home Furnishings", "Home Improvement Chains", "Hotels/Resorts/Cruise lines",
            "Restaurants", "Casinos/Gaming", "Apparel/Footwear", "Apparel/Footwear Retail",
            "Internet Retail", "Specialty Stores", "Department Stores",
            "Electronics/Appliance Stores", "Electronics/Appliances", "Recreational Products"),
    "XLP": ("Food: Major Diversified", "Food: Specialty/Candy", "Food: Meat/Fish/Dairy",
            "Food Retail", "Food Distributors", "Beverages: Alcoholic", "Beverages: Non-Alcoholic",
            "Tobacco", "Household/Personal Care", "Discount Stores", "Drugstore Chains",
            "Agricultural Commodities/Milling", "Consumer Sundries"),
    "XLV": ("Biotechnology", "Pharmaceuticals: Major", "Pharmaceuticals: Other",
            "Pharmaceuticals: Generic", "Medical Specialties", "Medical/Nursing Services",
            "Hospital/Nursing Management", "Managed Health Care", "Medical Distributors",
            "Services to the Health Industry"),
    "XLE": ("Integrated Oil", "Oil & Gas Production", "Oil Refining/Marketing",
            "Oil & Gas Pipelines", "Oilfield Services/Equipment", "Contract Drilling", "Coal"),
    "XLF": ("Major Banks", "Regional Banks", "Savings Banks", "Investment Banks/Brokers",
            "Investment Managers", "Multi-Line Insurance", "Property/Casualty Insurance",
            "Life/Health Insurance", "Specialty Insurance", "Insurance Brokers/Services",
            "Finance/Rental/Leasing", "Financial Publishing/Services"),
    "XLB": ("Chemicals: Agricultural", "Chemicals: Major Diversified", "Chemicals: Specialty",
            "Steel", "Aluminum", "Other Metals/Minerals", "Precious Metals",
            "Construction Materials", "Containers/Packaging", "Forest Products", "Pulp & Paper",
            "Industrial Specialties"),
    "XLRE": ("Real Estate Investment Trusts", "Real Estate Development"),
    "XLU": ("Electric Utilities", "Gas Distributors", "Water Utilities",
            "Alternative Power Generation"),
}
SECTOR_OF_INDUSTRY: dict[str, str] = {i: k for k, inds in _SECTOR_INDUSTRIES.items() for i in inds}
SECTOR_KEYS: frozenset[str] = frozenset(_SECTOR_INDUSTRIES)

#: The sector a theme sits under on the Sectors page; None is the Global menu. Written in
#: the order the owner's reference screenshots run their themes, which is sector by sector
#: and is where Solar and Bitcoin Miners sit: Solar with the oil names, Miners after the
#: technology block, in the Financials slot beside regional banks.
THEME_PARENT: dict[str, str | None] = {
    "SMH": "XLK", "DRAM": "XLK", "IGV": "XLK", "CIBR": "XLK", "SKYY": "XLK", "QTUM": "XLK",
    "BOTZ": "XLK", "ARKK": "XLK", "KRE": "XLF", "WGMI": "XLF", "XOP": "XLE", "URA": "XLE",
    "TAN": "XLE", "XBI": "XLV", "ITA": "XLI", "NASA": "XLI", "PAVE": "XLI", "GRID": "XLI",
    "JETS": "XLI", "XHB": "XLY", "GDX": "XLB", "COPX": "XLB", "XME": "XLB", "KWEB": None,
    "FXI": None,
}
#: A stock's tags read in that same order, as they do in the screenshots' table.
THEME_RANK: dict[str, int] = {k: i for i, k in enumerate(THEME_PARENT)}
#: Regional banks rank with the eleven sectors, as a sector in all but name.
TOP_THEMES: frozenset[str] = frozenset({"KRE"})
#: An industry needs this many stocks at the floor to be a card: fewer is a stock or two.
MIN_INDUSTRY = 5
#: The spans a card reads, and the column each comes from.
SPANS: tuple[tuple[str, str], ...] = (("day", "chg"), ("week", "w1"), ("month", "m1"))


def industry_theme(r: dict[str, Any]) -> str | None:
    """The theme a row's industry puts it in, unless it is one of the exceptions. Pure."""
    key = THEME_OF.get(r["industry"] or "")
    if key is None or r["sym"] in NOT_IN_THEME.get(key, frozenset()):
        return None
    country = r.get("country")
    # No country is not a foreign one: a missing column must not empty the theme.
    return None if key in US_ONLY_THEMES and country and country not in US_COUNTRIES else key


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


def _num(v: Any) -> float | None:
    return float(v) if isinstance(v, int | float) and math.isfinite(v) else None


def parse(doc: Any) -> tuple[list[dict[str, Any]], str | None]:
    """The reply → one row per common line or DR. Pure."""
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
        ex = str(item.get("s") or "").split(":")[0] or None
        industry = str(r.get("industry") or "") or None
        rows.append({
            "sym": sym, "name": str(r.get("description") or "").strip() or None, "exch": ex,
            "close": _num(r["close"]), "chg": _num(r["change"]), "open": _num(r["open"]),
            "high": _num(r["high"]), "low": _num(r["low"]), "vol": _num(r["volume"]),
            "gap": _num(r["gap"]), "atr": _num(r["ATR"]),
            "pm_h": _num(r["premarket_high"]), "pm_l": _num(r["premarket_low"]),
            "pm_c": _num(r["premarket_close"]), "pm_chg": _num(r["premarket_change"]),
            "pm_vol": _num(r["premarket_volume"]),
            "ah_c": _num(r["postmarket_close"]), "ah_chg": _num(r["postmarket_change"]),
            "ah_vol": _num(r["postmarket_volume"]),
            "avg": _num(r["average_volume_30d_calc"]), "rv5": _num(r["relative_volume_intraday|5"]),
            "cap": _num(r["market_cap_basic"]), "float": _num(r["float_shares_outstanding"]),
            # The desk's own table first, where a name's industry misleads: Alphabet
            # and Meta file as internet software and trade with communications.
            "sector": SECTOR.get(sym) or SECTOR_OF_INDUSTRY.get(industry or ""),
            "industry": industry, "country": str(r.get("country") or "") or None,
            "w1": _num(r["Perf.W"]), "m1": _num(r["Perf.1M"]),
            "o1": _num(r["open[1]"]), "h1": _num(r["high[1]"]), "l1": _num(r["low[1]"]),
            "c1": _num(r["close[1]"]), "v1": _num(r["volume[1]"]),
            "h2": _num(r["high[2]"]), "l2": _num(r["low[2]"]), "c2": _num(r["close[2]"]),
            "v2": _num(r["volume[2]"]),
        })
    return rows, None


# ---------------------------------------------------------------- the clock


def _mod(et: datetime) -> int:
    return et.hour * 60 + et.minute


def basis_at(now: datetime) -> str:
    """Which meaning the columns have at `now` (module docstring). Pure."""
    et = now.astimezone(scan.ET)
    d, m = et.date(), _mod(et)
    if not is_trading_day(d) or m < scan.PM_START + DELAY_MIN:
        return "last"
    if m < scan.RTH_START + DELAY_MIN:
        return "pre"
    if m < scan.rth_end(d) + DELAY_MIN:
        return "rth"
    if m < scan.post_end(d) + DELAY_MIN:
        return "post"
    return "last"


def session_day(now: datetime) -> date:
    """The session the read is about: today in a session, else the last finished. Pure."""
    et = now.astimezone(scan.ET)
    d = et.date()
    if basis_at(now) != "last":
        return d
    if is_trading_day(d) and _mod(et) >= scan.rth_end(d) + DELAY_MIN:
        return d
    return prev_trading_day(d)


def cards_day(now: datetime) -> date:
    """The session a card's move is about: the screener's columns and the ETFs' 1D both
    read the last regular session until the open. Pure."""
    et = now.astimezone(scan.ET)
    basis = basis_at(now)
    if basis in ("rth", "post"):
        return et.date()
    return session_day(now) if basis == "last" else prev_trading_day(et.date())


def news_anchor(now: datetime) -> float:
    """The moment a row's "last day" of news is counted back from: now while a session is
    on, and the end of the last session when none is. Pure."""
    if basis_at(now) != "last":
        return now.timestamp()
    d = session_day(now)
    end = scan.post_end(d)
    return datetime(d.year, d.month, d.day, end // 60, end % 60, tzinfo=scan.ET).timestamp()


# --------------------------------------------------------------- reading a row


def evaluate(r: dict[str, Any], basis: str, read_at: float, *, pm_ok: bool, ah_ok: bool,
             q: dict[str, Any] | None = None) -> dict[str, Any] | None:
    """One row read against the levels, as of the read, or of the stream's last trade. Pure.

    Worked examples are tests/test_universe.py's. `q` is the stream's quote, used
    only when it is newer than the delayed read and belongs to a session.
    """
    pre = basis == "pre"
    pdh, pdl, pdc = (r["high"], r["low"], r["close"]) if pre else (r["h1"], r["l1"], r["c1"])
    if pdh is None or pdl is None or r["close"] is None:
        return None
    pmh, pml = (r["pm_h"], r["pm_l"]) if pm_ok else (None, None)
    avg = r["avg"]
    chg, gap, vol, rvol, ext = r["chg"], r["gap"], r["vol"], None, None
    if pre:
        last = r["pm_c"] if pm_ok and r["pm_c"] is not None else r["close"]
        chg = r["pm_chg"] if pm_ok else None
        gap = chg
        vol = r["pm_vol"] if pm_ok else None
    elif basis == "post":
        last = r["ah_c"] if ah_ok and r["ah_c"] is not None else r["close"]
        ext = r["ah_chg"] if ah_ok else None
        rvol = (vol / avg) if vol and avg else None
    else:
        last = r["close"]
        rvol = r["rv5"] if basis == "rth" and r["rv5"] is not None else (
            (vol / avg) if vol and avg else None)

    live = False
    if basis != "last" and q and q.get("price") and q.get("session") \
            and float(q["at"]) >= read_at - DELAY_MIN * 60:
        last = float(q["price"])
        live = True
        if basis == "post":
            ext = (last / r["close"] - 1.0) * 100.0 if r["close"] else ext
        elif pdc:
            chg = (last / pdc - 1.0) * 100.0
            if pre:
                # Before the open the gap IS that move: it must follow the live trade
                # too, or the row shows two figures for one thing.
                gap = chg

    pd_state = "above" if last > pdh else "below" if last < pdl else "inside"
    if pmh is None or pml is None:
        pm_state = None
    elif pre:
        pm_state = "forming"
    else:
        pm_state = "above" if last > pmh else "below" if last < pml else "inside"
    both: str | None = None
    if pre:
        # `both` is an OUTSIDE DAY: through the pre-market range and the previous
        # day's the same way (owner, 2026-11-13; the page's chip says "Outside day").
        # The pre-market range cannot be through itself, so before the open it is
        # the previous day's levels alone (and the page says so).
        both = "up" if pd_state == "above" else "down" if pd_state == "below" else None
    elif pm_state == "above" and pd_state == "above":
        both = "up"
    elif pm_state == "below" and pd_state == "below":
        both = "down"
    h1, l1 = r["h1"], r["l1"]
    inside = (r["high"] is not None and r["low"] is not None and h1 is not None and l1 is not None
              and r["high"] <= h1 and r["low"] >= l1)
    return {
        "sym": r["sym"], "name": r["name"], "cap": r["cap"], "sector": r["sector"],
        "theme": industry_theme(r), "industry": r["industry"],
        "last": round(last, 4), "chg": _round(chg), "gap": _round(gap), "ext": _round(ext),
        "rvol": _round(rvol), "vol": vol, "week": _round(r.get("w1")),
        "adv_pct": _round((vol / avg) * 100.0 if vol and avg else None, 0),
        "pmh": pmh, "pml": pml, "pdh": pdh, "pdl": pdl, "pdc": pdc,
        "pm_state": pm_state, "pd_state": pd_state, "both": both, "inside": inside, "live": live,
    }


def _round(v: float | None, n: int = 2) -> float | None:
    return round(v, n) if v is not None else None


@dataclass
class Ctx:
    """What a table joins each row to, from the other stores."""

    quote: Callable[[str], dict[str, Any] | None] = lambda _s: None
    catalyst: Callable[[str], dict[str, Any] | None] = lambda _s: None
    pinned: frozenset[str] = frozenset()
    tracked: frozenset[str] = frozenset()
    stage: dict[str, int] = field(default_factory=dict)
    #: What the engine does with the name today (sources/pool.verdict), for the row.
    verdict: Callable[[str], dict[str, Any] | None] = lambda _s: None
    #: The Stocks list's own RVOL for a name it tracks, None for the rest (`rvol_for`).
    rvol: Callable[[str], float | None] = lambda _s: None


def span_stats(rows: list[dict[str, Any]], column: str, leaders: int = 3) -> dict[str, Any]:
    """How a group's stocks moved over one span: the count each way, the median stock
    (one 40% name cannot carry it the way it carries an average), and who led. Pure."""
    moves = sorted(((r["sym"], r[column]) for r in rows if r.get(column) is not None),
                   key=lambda m: -m[1])
    vals = [m for _, m in moves]
    return {"up": sum(1 for v in vals if v > 0), "down": sum(1 for v in vals if v < 0),
            "median": round(statistics.median(vals), 2) if vals else None,
            "leaders": [{"sym": s, "chg": round(m, 2)} for s, m in moves[:leaders]]}


def last_session_volume(r: dict[str, Any], basis: str) -> float | None:
    """What a group's list filters on: the last whole session's volume, or today's once
    today has passed it. Pure.

    Which stocks are in a sector should not depend on the hour. Before the open the
    table's volume is the pre-market's, which left 3 of Technology's 321 names at 06:19
    ET, and from the open a 15-minute feed has almost none of today.
    """
    if basis == "rth":
        return max(r["vol"] or 0.0, r["v1"] or 0.0)
    return r["vol"]


def _passes(row: dict[str, Any], basis: str, cap: float, vol: float, rvol: float,
            sector: str | None) -> bool:
    if (row["cap"] or 0) < cap:
        return False
    if vol and (row["vol"] or 0) < vol:
        return False
    # No time-of-day volume exists before the open, so the filter stands aside.
    if rvol and basis != "pre" and (row["rvol"] or 0) < rvol:
        return False
    return not (sector and row["sector"] != sector)


_SORTS: dict[str, Callable[[dict[str, Any]], float]] = {
    "rvol": lambda x: -(x["rvol"] or 0.0),
    "chg": lambda x: -abs(x["chg"] or 0.0),
    "gap": lambda x: -abs(x["gap"] or 0.0),
    "vol": lambda x: -(x["vol"] or 0.0),
}


class UniverseStore:
    """The read between ticks. Written on the wide thread; `rows` is replaced, never edited."""

    def __init__(self, path: str = STATE_FILE) -> None:
        self.path = path
        self._lock = threading.Lock()
        self.rows: list[dict[str, Any]] = []
        self.by_sym: dict[str, dict[str, Any]] = {}
        self.read_at: float | None = None
        self.source = "unavailable"
        self.error: str | None = None
        self.last_attempt = 0.0
        self.pause_until = 0.0
        self.pm_ref: dict[str, list[float | None]] = {}
        self.ah_ref: dict[str, list[float | None]] = {}
        #: The session `pm_ref` was taken from, and each name's extended volumes by session.
        self.pm_ref_day: str | None = None
        self.vol_day: str | None = None
        self.pm_hist: dict[str, list[int]] = {}
        self.ah_hist: dict[str, list[int]] = {}
        self.sparks: dict[str, tuple[float, list[float]]] = {}
        self.spark_want: list[str] = []
        #: Each fund-defined theme's stocks (sources/holdings.py), set on the wide thread.
        self.members: dict[str, frozenset[str]] = {}
        self._load()

    # ---- persistence --------------------------------------------------------

    def _load(self) -> None:
        try:
            with open(self.path, encoding="utf-8") as f:
                d = json.load(f)
        except (OSError, ValueError):
            return
        if isinstance(d, dict):
            self.pm_ref = d.get("pm_ref") or {}
            self.ah_ref = d.get("ah_ref") or {}
            self.pm_ref_day = d.get("pm_ref_day")
            self.vol_day = d.get("vol_day")
            self.pm_hist = d.get("pm_hist") or {}
            self.ah_hist = d.get("ah_hist") or {}

    def _save(self) -> None:
        tmp = self.path + ".tmp"
        try:
            os.makedirs(os.path.dirname(self.path), exist_ok=True)
            with open(tmp, "w", encoding="utf-8") as f:
                json.dump({"saved_utc": datetime.now(UTC).isoformat(), "pm_ref": self.pm_ref,
                           "ah_ref": self.ah_ref, "pm_ref_day": self.pm_ref_day,
                           "vol_day": self.vol_day, "pm_hist": self.pm_hist,
                           "ah_hist": self.ah_hist}, f)
            os.replace(tmp, self.path)
        except OSError:
            pass

    # ---- the tick -----------------------------------------------------------

    def _book_volumes(self, rows: list[dict[str, Any]], day: str) -> None:
        """Once a session: each name's finished extended-hours volume onto its list.

        A name that did not trade still shows the last session's figures, which is a
        day of none, unless the reference was itself taken this evening (a restart
        after the first read), when an unchanged row says nothing. A reference with no
        date, from before dates were kept, is treated the same way: one night of a
        quiet name's old figure costs less than a night of zeros for every name.
        """
        if self.vol_day == day:
            return
        ref_is_older = self.pm_ref_day is not None and self.pm_ref_day != day

        def add(book: dict[str, list[int]], sym: str, v: float | None) -> None:
            kept = book.setdefault(sym, [])
            kept.append(int(v or 0))
            del kept[:-VOL_KEEP]

        for r in rows:
            sym = r["sym"]
            pm = self.pm_ref.get(sym) if ref_is_older else None
            same = pm is not None and [r["pm_h"], r["pm_l"], r["pm_vol"]] == pm[:3]
            add(self.pm_hist, sym, 0.0 if same else r["pm_vol"])
            ah = self.ah_ref.get(sym)
            same = ah is not None and [r["ah_c"], r["ah_vol"]] == ah[:2]
            add(self.ah_hist, sym, 0.0 if same else r["ah_vol"])
        self.vol_day = day

    def _ext_rvol(self, sym: str, session: str, vol: float | None,
                  adv_pct: float | None) -> tuple[float | None, bool]:
        """(this session's volume against its own average, whether that is an estimate)."""
        kept = (self.pm_hist if session == "pre" else self.ah_hist).get(sym) or []
        if len(kept) >= VOL_MIN_DAYS:
            mean = sum(kept) / len(kept)
            return (round(vol / mean, 2) if vol and mean > 0 else None), False
        if adv_pct is None:
            return None, True
        return round(adv_pct / USUAL_ADV_PCT[session], 2), True

    def _take(self, rows: list[dict[str, Any]], read_at: float, basis: str) -> None:
        if basis == "last":
            day = session_day(datetime.fromtimestamp(read_at, UTC)).isoformat()
            self._book_volumes(rows, day)
            self.pm_ref = {r["sym"]: [r["pm_h"], r["pm_l"], r["pm_vol"], r["pm_c"], r["pm_chg"]]
                           for r in rows}
            self.pm_ref_day = day
            self._save()
        elif basis in ("pre", "rth"):
            self.ah_ref = {r["sym"]: [r["ah_c"], r["ah_vol"], r["ah_chg"]] for r in rows}
            if basis == "rth" and (self.read_at is None or basis_at(
                    datetime.fromtimestamp(self.read_at, UTC)) != "rth"):
                self._save()
        self.rows, self.by_sym, self.read_at = rows, {r["sym"]: r for r in rows}, read_at

    def tick(self, now: datetime | None = None) -> tuple[SourceStatus, bool]:
        """Read when due. Returns (status, whether a read happened)."""
        now = now or datetime.now(UTC)
        t = now.timestamp()
        basis = basis_at(now)
        st = SourceStatus("Universe")
        wait = IDLE_SEC if basis == "last" else ACTIVE_SEC
        due = not self.rows or t - self.last_attempt >= wait
        read = False
        if due and t >= self.pause_until:
            self.last_attempt = t
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
                    self._take(rows, t - (r.age_min or 0.0) * 60.0, basis)
                    self.source = r.source
                    self.error = r.error if r.source == "stale" else None
                else:
                    self.error = err or "no names in the reply"
            else:
                self.error = r.error
        st.items = len(self.rows)
        st.settle(bool(self.rows), "read")
        if self.error and not st.error:
            st.error = self.error
        if t < self.pause_until:
            st.notes.append("TradingView refused (403/429): paused")
        return st, read

    # ---- freshness ----------------------------------------------------------

    def pm_ok(self, r: dict[str, Any], basis: str) -> bool:
        """Has this name traded in the pre-market the columns claim? (module docstring)"""
        if basis == "last":
            return True
        ref = self.pm_ref.get(r["sym"])
        return ref is None or [r["pm_h"], r["pm_l"], r["pm_vol"]] != ref[:3]

    def pm_traded(self, sym: str, pm_close: float | None, pm_volume: float | None) -> bool | None:
        """For another read of the same screener columns (the pool's): are these a
        pre-market of today? False when they are exactly the figures held before the
        session began (`pm_ref`), True when they differ, None with no reference to
        compare or nothing to compare it with."""
        ref = self.pm_ref.get(sym)
        if ref is None or (pm_close is None and pm_volume is None):
            return None
        return not (pm_volume == ref[2] and pm_close == ref[3])

    def ah_ok(self, r: dict[str, Any], basis: str) -> bool:
        if basis != "post":
            return True
        ref = self.ah_ref.get(r["sym"])
        return ref is None or [r["ah_c"], r["ah_vol"]] != ref[:2]

    def _read(self, r: dict[str, Any], basis: str, q: dict[str, Any] | None,
              own: float | None = None) -> dict[str, Any] | None:
        e = evaluate(r, basis, self.read_at or 0.0, pm_ok=self.pm_ok(r, basis),
                     ah_ok=self.ah_ok(r, basis), q=q)
        if e is not None:
            # The share to the decimal Extended hours rounds it to, so the two agree.
            adv = _round(e["vol"] / r["avg"] * 100.0, 1) if e["vol"] and r["avg"] else None
            e["rvol"] = self.rvol_for(r["sym"], basis, e["rvol"], e["vol"], adv, own)
        return e

    def rvol_for(self, sym: str, basis: str, read: float | None, vol: float | None,
                 adv_pct: float | None, own: float | None = None) -> float | None:
        """ONE RVOL FOR A NAME, WHICHEVER PAGE SHOWS IT (quant audit, 2026-11-13; owner:
        "fix everything"). The pages had six: Setups the engine's time-of-day figure off
        its bars, Breakouts the screener's time-of-day column, the pool a share of a whole
        average day, Day 2/3 a fifth of the pre-market's share of one, Extended hours the
        pre-market's own history; so one stock read 2.4 on one page and 0.6 on another.
        What RVOL is now, everywhere:
          - in the session, volume so far against an average day to the same minute
            (`read`, the screener's; the pool reads the same column);
          - once the session is over, the whole day against an average day (`read`);
          - before the bell, the pre-market against its own usual pre-market (`_ext_rvol`,
            the Extended hours figure: a fifth of a day's share until five mornings are
            kept), since a day's RVOL does not exist yet.
        And a name the Stocks list tracks shows the list's own (`own`, the engine's, off
        live bars where the screener runs fifteen minutes behind), so the same stock reads
        the same on every page. Before the bell the engine has none and the pre-market's
        figure stands."""
        if own is not None and basis != "pre":
            return round(own, 2)
        if basis == "pre":
            return self._ext_rvol(sym, "pre", vol, adv_pct)[0]
        return read

    def premarket_of(self, sym: str, trading_day: date,
                     now: datetime | None = None) -> dict[str, Any] | None:
        """Today's pre-market for one name as the screener has it, in the shape the
        scanner's own pre-market read has (sources/premarket.py), or None.

        THE STAND-IN FOR NASDAQ'S READ (audit, 2026-11-11). The tracked names' pre-
        market volume comes from Nasdaq, one request a name, and is half of the pre-
        open score's in-play part. On 10 Nov Nasdaq refused the collector for thirteen
        hours; the wide read holds the same figure for every name in the one request it
        already makes, fifteen minutes behind. So a name Nasdaq has not answered for
        takes this. None when no session is on, when the session is not `trading_day`'s
        (20:00 to 20:15 ET the scanner's day has rolled and the screener's has not), or
        when the name's columns are still the last session's.
        """
        now = now or datetime.now(UTC)
        basis = basis_at(now)
        r = self.by_sym.get(sym)
        if r is None or basis == "last" or session_day(now) != trading_day:
            return None
        if r["pm_vol"] is None or not self.pm_ok(r, basis):
            return None
        at = self.read_at if self.read_at is not None else now.timestamp()
        return {"volume": r["pm_vol"], "high": r["pm_h"], "low": r["pm_l"], "last": r["pm_c"],
                "asof": datetime.fromtimestamp(at, UTC).isoformat(), "source": "screener"}

    def day_move(self, sym: str, now: datetime | None = None) -> float | None:
        """The name's move since the previous close (%), as the screener has it fifteen
        minutes behind: the pre-market print (or, before one, last evening's after-hours
        print, which is where the name stands), the regular session's change, and after
        the close that change with the after-hours move on top. What a headline's stated
        move is held to (catalysts.STATED_MIN) for a name off the Stocks list."""
        r = self.by_sym.get(sym)
        if r is None:
            return None
        basis = basis_at(now or datetime.now(UTC))
        if basis == "pre":
            return r["pm_chg"] if self.pm_ok(r, basis) else r["ah_chg"]
        if basis == "post" and r["chg"] is not None and r["ah_chg"] is not None \
                and self.ah_ok(r, basis):
            return ((1.0 + r["chg"] / 100.0) * (1.0 + r["ah_chg"] / 100.0) - 1.0) * 100.0
        return r["chg"]

    def read_one(self, sym: str, ctx: Ctx, now: datetime | None = None) -> dict[str, Any] | None:
        """One name's reading, for the Day 2/3 table."""
        r = self.by_sym.get(sym)
        return self._read(r, basis_at(now or datetime.now(UTC)), ctx.quote(sym),
                          ctx.rvol(sym)) if r else None

    # ---- the helpers other stores ask for -----------------------------------

    def exchanges(self) -> dict[str, str]:
        return {r["sym"]: r["exch"] for r in self.rows if r.get("exch")}

    def search(self, q: str, limit: int = 12) -> list[dict[str, Any]]:
        """Symbols and company names for the ticker search. Exact, prefix, then contains."""
        s = q.strip().upper()
        if not s:
            return []

        def rank(r: dict[str, Any]) -> tuple[int, float] | None:
            name = (r["name"] or "").upper()
            if r["sym"] == s:
                p = 0
            elif r["sym"].startswith(s):
                p = 1
            elif name.startswith(s):
                p = 2
            elif s in name:
                p = 3
            else:
                return None
            return (p, -(r["cap"] or 0.0))

        hits = [(k, r) for r in self.rows if (k := rank(r)) is not None]
        hits.sort(key=lambda x: x[0])
        return [{"sym": r["sym"], "name": r["name"], "cap": r["cap"], "sector": r["sector"]}
                for _, r in hits[:limit]]

    def candidates(self, extra: Iterable[str] = (), limit: int = CANDIDATES) -> list[str]:
        """The names worth the stream: `extra` first (the Day 2/3 names), then the
        $2bn+ names through or nearest their levels with the most volume."""
        basis = basis_at(datetime.now(UTC))
        ranked: list[tuple[float, str]] = []
        for r in self.rows:
            if (r["cap"] or 0) < DEFAULT_CAP:
                continue
            e = self._read(r, basis, None)
            if e is None:
                continue
            # Before the open RVOL is the pre-market's own (`rvol_for`).
            rv = e["rvol"] or 0.0
            if e["both"]:
                ranked.append((-10.0 - rv, r["sym"]))
            elif e["pd_state"] != "inside":
                ranked.append((-5.0 - rv, r["sym"]))
            else:
                # Inside: how near the closer level, in the name's own ATRs.
                atr = r["atr"] or 0.0
                if atr > 0 and rv >= 1.0:
                    gap = min(abs(e["last"] - e["pdh"]), abs(e["last"] - e["pdl"])) / atr
                    if gap <= 0.5:
                        ranked.append((-rv, r["sym"]))
        ranked.sort()
        seen: dict[str, None] = dict.fromkeys(extra)
        seen.update(dict.fromkeys(s for _, s in ranked))
        return list(seen)[:limit]

    # ---- sparks -------------------------------------------------------------

    def want_sparks(self, syms: Iterable[str]) -> None:
        with self._lock:
            order = dict.fromkeys(syms)
            order.update(dict.fromkeys(self.spark_want))
            self.spark_want = list(order)[:400]

    def spark(self, sym: str) -> list[float] | None:
        got = self.sparks.get(sym)
        return got[1] if got else None

    def tick_sparks(self, now: datetime | None = None) -> bool:
        """One batched read of the sparks that are due, at most. True when one was made."""
        now = now or datetime.now(UTC)
        t = now.timestamp()
        ttl = SPARK_IDLE_TTL if basis_at(now) == "last" else SPARK_TTL
        with self._lock:
            due = [s for s in self.spark_want if t - self.sparks.get(s, (0.0, []))[0] >= ttl]
            if not due:
                return False
            chunk = due[:SPARK_CHUNK]
        names = {s.replace(".", "-"): s for s in chunk}
        url = SPARK.format(syms=urllib.parse.quote(",".join(names), safe=""), rng="1d", iv="5m")
        r = fetch(url, key=f"univ_spark_{int(t)}", ttl_sec=0.0, ua=BROWSER_UA, timeout=12,
                  stale_ok=False, store=False, validate=json_body)
        # Marked read either way: a name Yahoo does not know must not hold the queue.
        for s in chunk:
            self.sparks.setdefault(s, (t, []))
            self.sparks[s] = (t, self.sparks[s][1])
        if not r.ok:
            return True
        try:
            doc = r.json()
            for row in (doc.get("spark") or {}).get("result") or []:
                sym = names.get(row.get("symbol"))
                resp = (row.get("response") or [None])[0] or {}
                quote = ((resp.get("indicators") or {}).get("quote") or [{}])[0]
                closes = quote.get("close") or []
                pts = [round(float(c), 4) for c in closes if isinstance(c, int | float)]
                if sym and pts:
                    self.sparks[sym] = (t, pts[-80:])
        except (ValueError, TypeError, AttributeError, IndexError):
            pass
        return True

    # ---- the groups ----------------------------------------------------------

    def in_theme(self, r: dict[str, Any], theme: str) -> bool:
        if theme in INDUSTRIES:
            return industry_theme(r) == theme
        return r["sym"] in self.members.get(theme, frozenset())

    def themes_of(self, r: dict[str, Any]) -> list[str]:
        """Every theme this name is in, in the order the themes run."""
        found = {k for k, names in self.members.items() if r["sym"] in names}
        own = industry_theme(r)
        if own:
            found.add(own)
        return sorted(found, key=lambda k: THEME_RANK.get(k, len(THEME_RANK)))

    def theme_list(self) -> list[dict[str, str]]:
        """The themes that can list stocks, for the filters."""
        return [{"key": k, "label": lab} for k, _, lab in ETF_THEMES
                if k in INDUSTRIES or self.members.get(k)]

    def industry_name(self, name: str) -> str | None:
        """An industry as TradingView spells it, however it was typed."""
        want = name.strip().casefold()
        return next((r["industry"] for r in self.rows
                     if r["industry"] and r["industry"].casefold() == want), None)

    def heatmap(self, etfs: list[dict[str, Any]], now: datetime | None = None,
                floor: float = DEFAULT_CAP) -> dict[str, Any]:
        """The Sectors page: every ETF card with what its stocks did, and the industries."""
        now = now or datetime.now(UTC)
        big = [r for r in self.rows if (r["cap"] or 0) >= floor]
        spans = {k: f for k, f in SPANS}

        def read(rows: list[dict[str, Any]]) -> dict[str, Any]:
            return {"names": len(rows), **{k: span_stats(rows, f) for k, f in spans.items()}}

        sectors: dict[str, list[dict[str, Any]]] = {}
        industries: dict[str, list[dict[str, Any]]] = {}
        for r in big:
            if r["sector"]:
                sectors.setdefault(r["sector"], []).append(r)
            if r["industry"]:
                industries.setdefault(r["industry"], []).append(r)
        cards: list[dict[str, Any]] = []
        spy: dict[str, Any] = {}
        for e in etfs:
            key = str(e.get("key"))
            if key == "SPY":
                spy = {"day": e.get("day_pct"), "week": e.get("week_pct"),
                       "month": e.get("month_pct")}
            if key in ("SPY", "RSP"):
                continue
            is_sector = key in SECTOR_KEYS
            rows = sectors.get(key, []) if is_sector else [r for r in big if self.in_theme(r, key)]
            cards.append({
                **{k: e.get(k) for k in ("key", "label", "last", "day_pct", "week_pct",
                                         "month_pct", "rs_day", "rs_week", "rs_month")},
                "kind": "sector" if is_sector else "theme",
                "top": is_sector or key in TOP_THEMES,
                "parent": None if is_sector else THEME_PARENT.get(key),
                "list": ("sector" if is_sector else "industry" if key in INDUSTRIES
                         else "hand" if key in US_LISTED else "fund"),
                **read(rows),
            })
        groups = [{"key": k, "label": k, "sector": SECTOR_OF_INDUSTRY.get(k), **read(v)}
                  for k, v in industries.items() if len(v) >= MIN_INDUSTRY]
        groups.sort(key=lambda g: g["key"])
        return {**self._head(basis_at(now), now), "cards_day": cards_day(now).isoformat(),
                "floor": floor, "names": len(big), "spy": spy, "cards": cards,
                "industries": groups}

    # ---- Breakouts ----------------------------------------------------------

    def _head(self, basis: str, now: datetime) -> dict[str, Any]:
        age = round((now.timestamp() - self.read_at) / 60.0, 1) if self.read_at else None
        return {"ok": bool(self.rows), "basis": basis, "day": session_day(now).isoformat(),
                "read_age_min": age, "delayed_min": DELAY_MIN, "source": self.source,
                "error": self.error}

    def breakouts(self, ctx: Ctx, *, chip: str = "both", cap: float = DEFAULT_CAP,
                  vol: float = DEFAULT_VOL, rvol: float = DEFAULT_RVOL, sector: str | None = None,
                  theme: str | None = None, industry: str | None = None, sort: str = "rank",
                  listing: bool = False, now: datetime | None = None) -> dict[str, Any]:
        """The Breakouts table: every name past the filters, the counts, the top rows.
        `listing` is a group's own list, whose volume filter does not depend on the hour."""
        now = now or datetime.now(UTC)
        basis = basis_at(now)
        base: list[dict[str, Any]] = []
        scanned = 0
        for r in self.rows:
            if (r["cap"] or 0) < cap:
                continue
            scanned += 1
            if (theme and not self.in_theme(r, theme)) or (industry and r["industry"] != industry):
                continue
            e = self._read(r, basis, ctx.quote(r["sym"]), ctx.rvol(r["sym"]))
            if e is None:
                continue
            gate = {**e, "vol": last_session_volume(r, basis)} if listing else e
            if not _passes(gate, basis, cap, vol, rvol, sector):
                continue
            e["catalyst"] = ctx.catalyst(r["sym"])
            base.append(e)
        chips = {
            "all": len(base),
            "both": sum(1 for e in base if e["both"]),
            "news": sum(1 for e in base if e["catalyst"]),
            "gaps": sum(1 for e in base if abs(e["gap"] or 0.0) >= GAP_PCT),
            "through": sum(1 for e in base if e["pd_state"] != "inside"),
            "inside": sum(1 for e in base if e["inside"]),
            "day23": sum(1 for e in base if ctx.stage.get(e["sym"], 0) >= 2),
            "pinned": sum(1 for e in base if e["sym"] in ctx.pinned),
        }
        kept = {
            "both": [e for e in base if e["both"]],
            "news": [e for e in base if e["catalyst"]],
            "gaps": [e for e in base if abs(e["gap"] or 0.0) >= GAP_PCT],
            "through": [e for e in base if e["pd_state"] != "inside"],
            "inside": [e for e in base if e["inside"]],
            "day23": [e for e in base if ctx.stage.get(e["sym"], 0) >= 2],
            "pinned": [e for e in base if e["sym"] in ctx.pinned],
        }.get(chip, base)
        if sort in _SORTS:
            kept = sorted(kept, key=_SORTS[sort])
        else:
            # Through both ranges, then a fresh major story, then volume: news is
            # what makes a move run (catalysts.py), so it comes before size.
            kept = sorted(kept, key=lambda e: (
                0 if e["both"] else 1,
                0 if (e["catalyst"] or {}).get("major") else 1,
                -(e["rvol"] or (e["adv_pct"] or 0.0) / 100.0)))
        rows = kept[:MAX_ROWS]
        self.want_sparks(e["sym"] for e in rows[:120])
        for e in rows:
            e["tracked"] = e["sym"] in ctx.tracked
            e["pinned"] = e["sym"] in ctx.pinned
            e["stage"] = ctx.stage.get(e["sym"])
            e["verdict"] = ctx.verdict(e["sym"])
            e["spark"] = self.spark(e["sym"])
            e["themes"] = self.themes_of(self.by_sym[e["sym"]])
        movers = [e for e in base if e["chg"] is not None]
        top_rvol = max((e for e in base if e["rvol"] is not None), key=lambda e: e["rvol"],
                       default=None)
        top_move = max(movers, key=lambda e: abs(e["chg"]), default=None)
        return {
            **self._head(basis, now),
            "scanned": scanned,
            "shown": len(rows),
            "matched": len(kept),
            "chips": chips,
            "stats": {
                "up": sum(1 for e in base if e["both"] == "up"),
                "down": sum(1 for e in base if e["both"] == "down"),
                "pdh": sum(1 for e in base if e["pd_state"] == "above"),
                "pdl": sum(1 for e in base if e["pd_state"] == "below"),
                "top_rvol": {"sym": top_rvol["sym"], "v": top_rvol["rvol"]} if top_rvol else None,
                "top_move": {"sym": top_move["sym"], "v": top_move["chg"]} if top_move else None,
                "live": sum(1 for e in base if e["live"]),
            },
            "themes": self.theme_list(),
            "rows": rows,
        }

    # ---- Extended hours -----------------------------------------------------

    def _gappers(self, ctx: Ctx, session: str, cap: float, floor: float,
                 basis: str) -> list[dict[str, Any]]:
        """Every name past the filters that moved in this extended session."""
        pre = session == "pre"
        active = basis == session
        out: list[dict[str, Any]] = []
        for r in self.rows:
            if (r["cap"] or 0) < cap:
                continue
            fresh = self.pm_ok(r, basis) if pre else self.ah_ok(r, basis)
            if active and not fresh:
                continue
            chg, v, last = (r["pm_chg"], r["pm_vol"], r["pm_c"]) if pre else (
                r["ah_chg"], r["ah_vol"], r["ah_c"])
            # A gapper moved: the thousand names a few cents off the close are not one.
            if chg is None or last is None or (v or 0) < floor or abs(chg) < GAP_PCT:
                continue
            # The day this session sits against: yesterday's bar before the open
            # (the base bar then), and the session it followed after the close.
            if pre:
                hi, lo = (r["high"], r["low"]) if basis == "pre" else (r["h1"], r["l1"])
            else:
                hi, lo = (r["h1"], r["l1"]) if basis == "rth" else (r["high"], r["low"])
            if hi is None or lo is None:
                continue
            q = ctx.quote(r["sym"]) if active else None
            is_live = False
            if q and q.get("price") and q.get("session") == session:
                last = float(q["price"])
                base = r["close"] if pre or basis != "rth" else r["c1"]
                if base:
                    chg = (last / base - 1.0) * 100.0
                is_live = True
            state = "above" if last > hi else "below" if last < lo else "inside"
            avg = r["avg"]
            adv_pct = _round(v / avg * 100.0 if v and avg else None, 1)
            rvol, est = self._ext_rvol(r["sym"], session, v, adv_pct)
            # The move in the name's own daily ATRs, from the price it moved from.
            atr, ref = r["atr"], last / (1.0 + chg / 100.0) if chg > -100.0 else None
            gap_atr = abs(last - ref) / atr if atr and ref else None
            h1, l1 = r["h1"], r["l1"]
            ok_pm = self.pm_ok(r, basis)
            out.append({"sym": r["sym"], "name": r["name"], "cap": r["cap"],
                        "sector": r["sector"], "float": r["float"], "last": round(last, 4),
                        "chg": round(chg, 2), "vol": v, "adv_pct": adv_pct,
                        "rvol": rvol, "rvol_est": est, "session": session,
                        "gap_atr": _round(gap_atr),
                        "in_play": round(session_points(gap_atr, adv_pct), 1),
                        "hi": hi, "lo": lo, "state": state, "live": is_live,
                        "pmh": r["pm_h"] if ok_pm else None, "pml": r["pm_l"] if ok_pm else None,
                        "inside": (r["high"] is not None and r["low"] is not None
                                   and h1 is not None and l1 is not None
                                   and r["high"] <= h1 and r["low"] >= l1),
                        "catalyst": ctx.catalyst(r["sym"]), "tracked": r["sym"] in ctx.tracked,
                        "pinned": r["sym"] in ctx.pinned, "stage": ctx.stage.get(r["sym"]),
                        "verdict": ctx.verdict(r["sym"])})
        return out

    def extended(self, ctx: Ctx, *, session: str = "pre", cap: float = DEFAULT_CAP,
                 vol: float | None = None, chip: str = "all",
                 now: datetime | None = None) -> dict[str, Any]:
        """The gappers of an extended session: this one if it is on, else the last. "all"
        is both, a name that moved in each shown once, in the more recent of the two."""
        now = now or datetime.now(UTC)
        basis = basis_at(now)

        def floor_of(s: str) -> float:
            return (DEFAULT_PM_VOL if s == "pre" else DEFAULT_AH_VOL) if vol is None else vol

        if session == "all":
            newest = "pre" if basis in ("pre", "rth") else "post"
            older = "post" if newest == "pre" else "pre"
            out = self._gappers(ctx, newest, cap, floor_of(newest), basis)
            seen = {e["sym"] for e in out}
            out += [e for e in self._gappers(ctx, older, cap, floor_of(older), basis)
                    if e["sym"] not in seen]
            floor, active = floor_of("pre"), basis in ("pre", "post")
        else:
            floor, active = floor_of(session), basis == session
            out = self._gappers(ctx, session, cap, floor, basis)
        # A fresh major story first, then THE MOVE ON ITS VOLUME (quant audit, 2026-11-13;
        # owner: "fix everything"): the move in daily ATRs and the session's share of an
        # average day, read the way the pool reads the pre-market (pool.session_points), so
        # this page and the pool agree on who is in play. By the bare percent a 100k-share
        # +15% name sat above a 5M-share +8% one, and a 6% move in a stock that moves 8% on
        # a quiet day above a 4% move in one that moves 1%.
        out.sort(key=lambda e: (0 if (e["catalyst"] or {}).get("major") else 1,
                                -e["in_play"], -abs(e["chg"])))
        ups_all, downs_all = [e for e in out if e["chg"] > 0], [e for e in out if e["chg"] < 0]
        chips = {
            "all": len(out),
            "up": sum(1 for e in out if e["chg"] > 0),
            "down": sum(1 for e in out if e["chg"] < 0),
            "news": sum(1 for e in out if e["catalyst"]),
            "through": sum(1 for e in out if e["state"] != "inside"),
            "inside": sum(1 for e in out if e["inside"]),
            "day23": sum(1 for e in out if (e["stage"] or 0) >= 2),
            "pinned": sum(1 for e in out if e["pinned"]),
        }
        kept = {
            "up": ups_all, "down": downs_all,
            "news": [e for e in out if e["catalyst"]],
            "through": [e for e in out if e["state"] != "inside"],
            "inside": [e for e in out if e["inside"]],
            "day23": [e for e in out if (e["stage"] or 0) >= 2],
            "pinned": [e for e in out if e["pinned"]],
        }.get(chip, out)
        rows = kept[:MAX_ROWS]
        self.want_sparks(e["sym"] for e in rows[:60])
        for e in rows:
            e["spark"] = self.spark(e["sym"])
        by_size = sorted(out, key=lambda e: -abs(e["chg"]))
        ups, downs = [e for e in by_size if e["chg"] > 0], [e for e in by_size if e["chg"] < 0]
        return {
            **self._head(basis, now),
            "session": session,
            "active": active,
            "volume_floor": floor,
            "scanned": sum(1 for r in self.rows if (r["cap"] or 0) >= cap),
            "chips": chips,
            "stats": {"up": ups[0] if ups else None, "down": downs[0] if downs else None,
                      "through": chips["through"], "inside": chips["inside"],
                      "gap_up": len(ups_all),
                      "gap_up_news": sum(1 for e in ups_all if e["catalyst"]),
                      "gap_down": len(downs_all),
                      "gap_down_news": sum(1 for e in downs_all if e["catalyst"])},
            "reference": (self._reference(ctx, "pre" if session == "all" else session, cap, floor)
                          if active and not out
                          else by_size[:4]),
            "reference_is_last": active and not out,
            "shown": len(rows),
            "matched": len(kept),
            "rows": rows,
        }

    def _reference(self, ctx: Ctx, session: str, cap: float, floor: float) -> list[dict[str, Any]]:
        """The previous session's biggest gappers, from the columns as they stood
        before this one began, for the page while nothing has traded yet."""
        pre = session == "pre"
        src = self.pm_ref if pre else self.ah_ref
        out: list[dict[str, Any]] = []
        for r in self.rows:
            ref = src.get(r["sym"])
            if (r["cap"] or 0) < cap or ref is None:
                continue
            last, v, chg = (ref[3], ref[2], ref[4]) if pre else (ref[0], ref[1], ref[2])
            if chg is None or last is None or (v or 0) < floor:
                continue
            out.append({"sym": r["sym"], "name": r["name"], "cap": r["cap"], "sector": r["sector"],
                        "float": r["float"], "last": last, "chg": round(chg, 2), "vol": v,
                        "adv_pct": _round(v / r["avg"] * 100.0 if v and r["avg"] else None, 1),
                        "catalyst": ctx.catalyst(r["sym"])})
        out.sort(key=lambda e: -abs(e["chg"]))
        return out[:4]

    # ---- the Macro tab ------------------------------------------------------

    def breadth(self, now: datetime | None = None,
                floor: float = DEFAULT_CAP) -> dict[str, Any] | None:
        """Advancers and decliners at $2bn+ by the size of the move, and each sector's
        leaders. Off the delayed read: a picture of the whole market, not a trigger."""
        now = now or datetime.now(UTC)
        if not self.rows:
            return None
        basis = basis_at(now)
        edges: list[tuple[str, float, float]] = [
            ("≤-10", -1e9, -10.0), ("-10", -10.0, -5.0), ("-5", -5.0, -2.0), ("-2", -2.0, 0.0),
            ("+2", 0.0, 2.0), ("+5", 2.0, 5.0), ("+10", 5.0, 10.0), ("≥+10", 10.0, 1e9)]
        moves: list[tuple[dict[str, Any], float]] = []
        for r in self.rows:
            if (r["cap"] or 0) < floor:
                continue
            m = r["pm_chg"] if basis == "pre" and self.pm_ok(r, basis) else (
                None if basis == "pre" else r["chg"])
            if m is not None:
                moves.append((r, m))
        buckets = [{"label": lab, "n": sum(1 for _, m in moves if lo <= m < hi and m != 0),
                    "side": "down" if hi <= 0 else "up"} for lab, lo, hi in edges]
        leaders: dict[str, dict[str, list[dict[str, Any]]]] = {}
        for r, m in sorted(moves, key=lambda x: -x[1]):
            if r["sector"] and (r["cap"] or 0) >= 5e9:
                slot = leaders.setdefault(r["sector"], {"up": [], "down": []})
                if len(slot["up"]) < 3 and m > 0:
                    slot["up"].append({"sym": r["sym"], "chg": round(m, 2)})
        for r, m in sorted(moves, key=lambda x: x[1]):
            if r["sector"] and (r["cap"] or 0) >= 5e9:
                slot = leaders.setdefault(r["sector"], {"up": [], "down": []})
                if len(slot["down"]) < 3 and m < 0:
                    slot["down"].append({"sym": r["sym"], "chg": round(m, 2)})
        return {
            **self._head(basis, now),
            "floor": floor,
            "names": len(moves),
            "advancers": sum(1 for _, m in moves if m > 0),
            "decliners": sum(1 for _, m in moves if m < 0),
            "buckets": buckets,
            "leaders": leaders,
        }

    def forming(self, ctx: Ctx, *, min_move: float, cap: float,
                now: datetime | None = None) -> list[dict[str, Any]]:
        """Today's Day 1s while the session is still making them: the ledger only
        writes a Day 1 once the bar is final."""
        now = now or datetime.now(UTC)
        basis = basis_at(now)
        if basis not in ("rth", "post"):
            return []
        out: list[dict[str, Any]] = []
        for r in self.rows:
            if (r["cap"] or 0) < cap or r["chg"] is None or abs(r["chg"]) < min_move:
                continue
            e = self._read(r, basis, ctx.quote(r["sym"]), ctx.rvol(r["sym"]))
            if e is not None and (e["rvol"] or 0.0) >= 1.5:
                out.append({**e, "raw": r})
        return out

    def raw(self, sym: str) -> dict[str, Any] | None:
        return self.by_sym.get(sym)
