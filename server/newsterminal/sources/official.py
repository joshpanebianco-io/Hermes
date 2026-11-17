"""
The agencies' own figures — what the BLS, the Census Bureau, the BEA and the EIA
published, beside what the calendar says they published.

WHY (owner, 2026-11-15: "so we are getting the news and macro and everything form the
most reputable sources as possible and most official"). The economic calendar is an
aggregator's: Nasdaq's, and TradingView's while Nasdaq refuses. A CPI print reached
this desk second-hand, and nothing checked the copy against the release. For the US
releases this desk stops for, the agency publishes the figure itself where a program
can read it without a key:

  BLS      its public data API: the index and employment series the releases are
           built from. Consumer and producer prices (headline and core, monthly and
           over the year), payrolls, the unemployment rate, hourly earnings, job
           openings. A percentage change is worked from the published index, to one
           place, which is how the BLS itself states it.
  Census   the Economic Briefing Room feed: retail sales, durable goods and factory
           orders, housing starts, new home sales, construction spending, business
           and wholesale inventories, the trade balance.
  BEA      its release feed, which carries each headline as a number: GDP, personal
           income, personal spending, the trade balance.
  EIA      the weekly petroleum status table and the weekly gas storage file: crude,
           gasoline and distillate stocks, gas in storage.

WHAT IT DOES TO A ROW. A figure joins the calendar row it is the print of, and the
agency's figure is the row's figure: it fills a row the feed has not filled yet and
it replaces a feed's figure it disagrees with, keeping what the feed said beside it
so the difference is on the page. A row both agree on is marked as confirmed.

A FIGURE HAS TO BE THIS PRINT'S, NOT THE LAST ONE'S. At 08:30:20 the agency's file
may still hold last month. So a monthly BLS figure joins a row only when its
reference month is the one that release reports (the month before, two before for job
openings); a Census, BEA or gas figure only when the agency published it on the row's
own day; the weekly oil table only when its week ended three to eight days before.
Anything else joins nothing, and the row stays the feed's.

WHAT IS NOT HERE, AND WHY. Jobless claims (the Labor Department's site refuses a
program), the PCE price index (the BEA's feed does not carry it and its data API
wants a registered key), the Fed's industrial production, and every survey that is a
private body's own (ISM, the Michigan and Conference Board surveys, ADP): those rows
stay the calendar feed's, unmarked.

THE BLS ALLOWS TWENTY-FIVE REQUESTS A DAY WITHOUT A KEY. All fifteen series ride one
request, kept on disk for six hours; in the forty minutes after one of its releases
is due it is asked every five minutes until the new month is there. A refusal is
never written over the copy held (`_bls_ok`).

Every request carries the plain browser User-Agent: none of these needs a contact,
and the declared one names the owner.
"""

from __future__ import annotations

import csv
import io
import json
import re
import time
from datetime import UTC, date, datetime, timedelta
from decimal import ROUND_HALF_UP, Decimal, InvalidOperation
from email.utils import parsedate_to_datetime
from typing import Any
from zoneinfo import ZoneInfo

from ..config import BROWSER_UA
from ..http import SourceStatus, clean_text, fetch, json_body
from ..releases import implication, read_of

ET = ZoneInfo("America/New_York")

BLS_API = "https://api.bls.gov/publicAPI/v2/timeseries/data/"
CENSUS = "https://www.census.gov/economic-indicators/indicator.xml"
BEA = "https://apps.bea.gov/rss/rss.xml"
EIA_OIL = "https://ir.eia.gov/wpsr/table1.csv"
EIA_GAS = "https://ir.eia.gov/ngs/wngsr.json"

#: How long a copy is served without asking again, and how long while a release
#: mapped to that agency is due and its figure has not arrived.
QUIET_SEC = {"BLS": 6 * 3600.0, "Census": 900.0, "BEA": 900.0, "EIA": 900.0}
HOT_SEC = {"BLS": 300.0, "Census": 90.0, "BEA": 90.0, "EIA": 90.0}
#: A release is "due" from its scheduled minute for this long.
DUE_SEC = 40 * 60.0
STALE_MAX_SEC = 7 * 86400.0

MONTHS = ("January", "February", "March", "April", "May", "June", "July", "August",
          "September", "October", "November", "December")

# ---------------------------------------------------------------- the BLS series
#
# series → the figures read off it: (key, how). "mm" and "yy" are the percentage
# change on the month and on the year, from the published index; "chg_k" the month's
# change in a level kept in thousands; "pct" a rate as published; "level_k" a level
# kept in thousands. The seasonally adjusted index gives the monthly change and the
# unadjusted one the change over the year, as the releases state them.
BLS_SERIES: dict[str, tuple[tuple[str, str], ...]] = {
    "CUSR0000SA0": (("cpi_mm", "mm"),),
    "CUSR0000SA0L1E": (("cpi_core_mm", "mm"),),
    "CUUR0000SA0": (("cpi_yy", "yy"),),
    "CUUR0000SA0L1E": (("cpi_core_yy", "yy"),),
    "WPSFD4": (("ppi_mm", "mm"),),
    "WPUFD4": (("ppi_yy", "yy"),),
    "WPSFD49104": (("ppi_core_mm", "mm"),),
    "WPUFD49104": (("ppi_core_yy", "yy"),),
    "WPSFD49116": (("ppi_xfet_mm", "mm"),),
    "WPUFD49116": (("ppi_xfet_yy", "yy"),),
    "CES0000000001": (("payrolls", "chg_k"),),
    "CES0500000001": (("payrolls_private", "chg_k"),),
    "LNS14000000": (("unemployment", "pct"),),
    "CES0500000003": (("ahe_mm", "mm"), ("ahe_yy", "yy")),
    "JTS000000000000000JOL": (("jolts", "level_k"),),
}
#: Months between the reference month and the month the release lands in.
BLS_LAG: dict[str, int] = {"jolts": 2}
BLS_PAGE: dict[str, str] = {
    "cpi": "https://www.bls.gov/news.release/cpi.nr0.htm",
    "ppi": "https://www.bls.gov/news.release/ppi.nr0.htm",
    "jolts": "https://www.bls.gov/news.release/jolts.nr0.htm",
}
BLS_JOBS_PAGE = "https://www.bls.gov/news.release/empsit.nr0.htm"

# ---------------------------------------------------------------- row → figure
#
# The calendar's name for a release → the figure that is its print. Whole-name
# matches, on US rows only: "GDP q/q" is the growth rate and "GDP Price Index q/q"
# is not, "Housing Starts" is the level and "Housing Starts m/m" its change.
EVENTS: tuple[tuple[str, re.Pattern[str]], ...] = tuple(
    (key, re.compile(rf"(?:{pat})", re.I)) for key, pat in (
        ("cpi_mm", r"CPI m/m"),
        ("cpi_core_mm", r"Core CPI m/m"),
        ("cpi_yy", r"CPI y/y"),
        ("cpi_core_yy", r"Core CPI y/y"),
        ("ppi_mm", r"PPI m/m"),
        ("ppi_yy", r"PPI y/y"),
        ("ppi_core_mm", r"Core PPI m/m"),
        ("ppi_core_yy", r"Core PPI y/y"),
        ("ppi_xfet_mm", r"PPI ex\. Food/Energy/Transport m/m"),
        ("ppi_xfet_yy", r"PPI ex\. Food/Energy/Transport y/y"),
        ("payrolls", r"Non-?farm Payrolls|Non-?Farm Employment Change"),
        ("payrolls_private", r"Private Non-?farm Payrolls|Non-?farm Payrolls Private"),
        ("unemployment", r"Unemployment Rate"),
        ("ahe_mm", r"Average Hourly Earnings m/m"),
        ("ahe_yy", r"Average Hourly Earnings y/y"),
        ("jolts", r"JOLTS?(?: Job Openings)?"),
        ("retail_mm", r"Retail Sales m/m"),
        ("durable_mm", r"Durable Goods(?: Orders)? m/m"),
        ("factory_mm", r"Factory Orders m/m"),
        ("starts", r"Housing Starts"),
        ("starts_mm", r"Housing Starts m/m"),
        ("home_sales", r"New Home Sales"),
        ("home_sales_mm", r"New Home Sales m/m"),
        ("construction_mm", r"Construction Spending m/m"),
        ("inventories_mm", r"Business Inventories m/m"),
        ("wholesale_mm", r"Wholesale Inventories m/m"),
        ("trade", r"Trade Balance"),
        ("goods_trade", r"Goods Trade Balance"),
        ("gdp", r"GDP(?: Annualized)?(?: q/q)?"),
        ("income_mm", r"Personal Income m/m"),
        ("spending_mm", r"Personal Spending m/m"),
        ("crude", r"Crude Oil Inventories"),
        ("gasoline", r"Gasoline Inventories"),
        ("distillate", r"(?:EIA )?Distillate (?:Fuel )?(?:Inventories|Stocks Change)"),
        ("gas_storage", r"Natural Gas Storage"),
    )
)
#: Which agency a figure is asked of, for the "is one due" question.
AGENCY: dict[str, str] = {
    **{k: "BLS" for keys in BLS_SERIES.values() for k, _ in keys},
    **{k: "Census" for k in ("retail_mm", "durable_mm", "factory_mm", "starts", "starts_mm",
                             "home_sales", "home_sales_mm", "construction_mm",
                             "inventories_mm", "wholesale_mm", "goods_trade")},
    **{k: "BEA" for k in ("gdp", "income_mm", "spending_mm", "trade")},
    **{k: "EIA" for k in ("crude", "gasoline", "distillate", "gas_storage")},
}
#: A possessive for the sentence on the page: "the BLS's", "the Census Bureau's".
AGENCY_NAME: dict[str, str] = {
    "BLS": "the Bureau of Labor Statistics", "Census": "the Census Bureau",
    "BEA": "the Bureau of Economic Analysis", "EIA": "the Energy Information Administration",
}


def key_of(event: Any) -> str | None:
    """The figure a US calendar row is the print of, or None. Pure."""
    name = " ".join(str(event or "").split())
    for key, pat in EVENTS:
        if pat.fullmatch(name):
            return key
    return None


# ---------------------------------------------------------------- figures
#
# A figure is {key, by, kind, value, step, text, period, url} and what places it in
# time: `ref` (year, month) for a monthly BLS series, `published` (the ET day the
# agency put it out) for a release feed, `week_end` for the weekly oil table.
# `kind` is "pct" (a percentage, `value` in points) or "abs" (`value` in base units:
# jobs, houses, dollars, barrels, cubic feet). `step` is the smallest difference the
# agency's own rounding can show, in the same units.


def _fig(key: str, by: str, kind: str, value: float, step: float, text: str,
         period: str, url: str, **when: Any) -> dict[str, Any]:
    return {"key": key, "by": by, "kind": kind, "value": value, "step": step, "text": text,
            "period": period, "url": url, **when}


def _dec(v: Any) -> Decimal | None:
    try:
        d = Decimal(str(v).replace(",", "").strip())
    except (InvalidOperation, ValueError):
        return None
    return d if d.is_finite() else None


def _pct_change(cur: Decimal, was: Decimal) -> float | None:
    """The change from `was` to `cur` in per cent, to one place, half up: the
    agencies work it from the published index the same way. Pure."""
    if was == 0:
        return None
    return float(((cur / was - 1) * 100).quantize(Decimal("0.1"), rounding=ROUND_HALF_UP))


def _pct_text(v: float) -> str:
    return f"{v:g}%"


def bls_figures(doc: Any) -> dict[str, dict[str, Any]]:
    """The BLS API's answer → the figures of each series' latest month. Pure.

    A figure needs the month it is measured from: a monthly change with last month
    missing, or a year's change with the same month a year ago missing (October 2025
    was never collected), is not worked out from something else. It is left out.
    """
    out: dict[str, dict[str, Any]] = {}
    series = ((doc or {}).get("Results") or {}).get("series") or []
    for s in series:
        reads = BLS_SERIES.get(str(s.get("seriesID") or ""))
        if not reads:
            continue
        vals: dict[tuple[int, int], Decimal] = {}
        for r in s.get("data") or []:
            period = str(r.get("period") or "")
            d = _dec(r.get("value"))
            if not re.fullmatch(r"M(0[1-9]|1[0-2])", period) or d is None:
                continue
            try:
                vals[(int(r.get("year")), int(period[1:]))] = d
            except (TypeError, ValueError):
                continue
        if not vals:
            continue
        y, m = max(vals)
        cur = vals[(y, m)]
        month_ago = vals.get((y, m - 1) if m > 1 else (y - 1, 12))
        year_ago = vals.get((y - 1, m))
        period = f"{MONTHS[m - 1]} {y}"
        for key, how in reads:
            url = BLS_PAGE.get(key.split("_")[0], BLS_JOBS_PAGE)
            when: dict[str, Any] = {"ref": [y, m], "lag": BLS_LAG.get(key, 1)}
            if how in ("mm", "yy"):
                was = month_ago if how == "mm" else year_ago
                v = _pct_change(cur, was) if was is not None else None
                if v is not None:
                    out[key] = _fig(key, "BLS", "pct", v, 0.1, _pct_text(v), period, url, **when)
            elif how == "pct":
                out[key] = _fig(key, "BLS", "pct", float(cur), 0.1, _pct_text(float(cur)),
                                period, url, **when)
            elif how == "chg_k" and month_ago is not None:
                chg = float(cur - month_ago)
                out[key] = _fig(key, "BLS", "abs", chg * 1000.0, 1000.0, f"{chg:,.0f}K",
                                period, url, **when)
            elif how == "level_k":
                lvl = float(cur)
                out[key] = _fig(key, "BLS", "abs", lvl * 1000.0, 1000.0,
                                f"{lvl / 1000.0:.3f}M", period, url, **when)
    return out


def _bls_ok(body: bytes) -> str | None:
    """A BLS answer that is JSON and was served: a refusal (the day's allowance
    spent) arrives as a 200 too, and must not replace the copy held."""
    bad = json_body(body)
    if bad:
        return bad
    try:
        doc = json.loads(body)
    except ValueError as e:
        return f"not JSON: {e}"
    if doc.get("status") != "REQUEST_SUCCEEDED":
        return f"BLS: {doc.get('status')} {'; '.join(map(str, doc.get('message') or []))[:160]}"
    return None


def _xml_ok(body: bytes) -> str | None:
    return None if b"<item" in body[:400_000] else "no items in the feed"


def _tag(block: str, name: str) -> str:
    m = re.search(rf"<{name}\b[^>]*>(.*?)</{name}>", block, re.S)
    if not m:
        return ""
    text = re.sub(r"<!\[CDATA\[|\]\]>", "", m.group(1))
    return clean_text(re.sub(r"<[^>]+>", " ", text))


def _published(raw: str) -> str | None:
    """An RSS pubDate → the ET day it names. BEA writes "EDT"/"EST", which the
    standard parser reads as the offset it is."""
    try:
        d = parsedate_to_datetime(raw.strip())
    except (TypeError, ValueError, IndexError):
        return None
    if d.tzinfo is None:
        d = d.replace(tzinfo=ET)
    return d.astimezone(ET).date().isoformat()


_CHANGE = re.compile(
    r"((?:January|February|March|April|May|June|July|August|September|October|November|"
    r"December) \d{4}|\d(?:st|nd|rd|th) Qtr \d{4})(?: \([a-z]\))?:\s*"
    r"([+-]?\d+(?:\.\d+)?)[°*]?\s*%\s*Change", re.I)
_RATE = re.compile(r"annual rate of ([\d,]+)")
_DEFICIT = re.compile(
    r"\b(deficit|surplus)\b[^$]*?\bto \$([\d,]+(?:\.\d+)?) (billion|million)", re.I)

#: The Census Bureau's own id for an indicator → the figures read off its item.
CENSUS_ITEMS: dict[str, tuple[tuple[str, str], ...]] = {
    "retail_sales": (("retail_mm", "change"),),
    "durable_goods": (("durable_mm", "change"),),
    "mfg_orders": (("factory_mm", "change"),),
    "housing_starts": (("starts", "rate"), ("starts_mm", "change")),
    "home_sales": (("home_sales", "rate"), ("home_sales_mm", "change")),
    "construction_value": (("construction_mm", "change"),),
    "business_sales": (("inventories_mm", "change"),),
    "wholesale": (("wholesale_mm", "change"),),
    "adv_intl_trade": (("goods_trade", "balance"),),
}


def _balance(text: str) -> tuple[float, str] | None:
    """ "the deficit … decreased to $105.0 billion" → (-105.0e9, "-$105.0B"). Pure."""
    m = _DEFICIT.search(text)
    d = _dec(m.group(2)) if m else None
    if m is None or d is None:
        return None
    unit = 1e9 if m.group(3).lower() == "billion" else 1e6
    sign = -1.0 if m.group(1).lower() == "deficit" else 1.0
    text = f"{'-' if sign < 0 else ''}${m.group(2)}{'B' if unit == 1e9 else 'M'}"
    return sign * float(d) * unit, text


def census_figures(xml: str) -> dict[str, dict[str, Any]]:
    """The Economic Briefing Room feed → figures. Pure.

    Each item is one indicator: a sentence with the level, then the period's change
    on a line of its own ("September 2026: +0.8 % Change")."""
    out: dict[str, dict[str, Any]] = {}
    for item in re.findall(r"<item\b[^>]*>(.*?)</item>", xml or "", re.S):
        reads = CENSUS_ITEMS.get(_tag(item, "guid"))
        published = _published(_tag(item, "pubDate"))
        if not reads or not published:
            continue
        text = _tag(item, "description")
        link = _tag(item, "link") or "https://www.census.gov/economic-indicators/"
        change = _CHANGE.search(text)
        period = change.group(1) if change else ""
        for key, how in reads:
            if how == "change" and change:
                v = float(change.group(2))
                out[key] = _fig(key, "Census", "pct", v, 0.1, _pct_text(v), period, link,
                                published=published)
            elif how == "rate":
                m = _RATE.search(text)
                d = _dec(m.group(1)) if m else None
                if d is not None:
                    out[key] = _fig(key, "Census", "abs", float(d), 1000.0,
                                    f"{float(d) / 1e6:.3f}M", period, link, published=published)
            elif how == "balance":
                got = _balance(text)
                if got:
                    out[key] = _fig(key, "Census", "abs", got[0], 1e8, got[1], period, link,
                                    published=published)
    return out


_SIGNED = re.compile(r"([+-])\s*\$?\s*(\d+(?:\.\d+)?)")
_BEA_GDP = re.compile(
    r"^(?:GDP|Gross Domestic Product)\b(?!.*\b(?:County|State|Metropolitan|Industry|"
    r"Puerto Rico|Guam|Samoa|Virgin Islands|Mariana|Local Area)\b)", re.I)


def _bea_number(text: str) -> float | None:
    """BEA's headline cell → its number: "+3.4", "+0.2%", "May 2026 +0.7%", "0.5",
    "-$105.0 billion". The sign is the cell's; a bare figure is positive. Pure."""
    m = _SIGNED.search(text or "")
    if m:
        return float(m.group(2)) * (-1.0 if m.group(1) == "-" else 1.0)
    bare = re.fullmatch(r"\s*(\d+(?:\.\d+)?)\s*%?\s*", text or "")
    return float(bare.group(1)) if bare else None


def bea_figures(xml: str) -> dict[str, dict[str, Any]]:
    """BEA's release feed → figures, the newest release of each kind. Pure."""
    out: dict[str, dict[str, Any]] = {}
    items = re.findall(r'<item\b[^>]*\bname="([^"]*)"[^>]*>(.*?)</item>', xml or "", re.S)
    for name, item in items:
        published = _published(_tag(item, "pubDate"))
        main = re.search(r"<main>(.*?)</main>", item, re.S)
        cur = re.search(r"<current>(.*?)</current>", main.group(1), re.S) if main else None
        if not published or not cur:
            continue
        period = _tag(cur.group(1), "infoDate")
        cell = _tag(cur.group(1), "percentChange")
        link = _tag(item, "link") or "https://www.bea.gov/news/current-releases"
        v = _bea_number(cell)

        def put(key: str, fig: dict[str, Any]) -> None:
            # The feed is newest first; a later item of the same kind is an older release.
            out.setdefault(key, fig)

        if _BEA_GDP.search(name) and v is not None:
            put("gdp", _fig("gdp", "BEA", "pct", v, 0.1, _pct_text(v), period, link,
                            published=published))
        elif name.startswith("Personal Income and Outlays"):
            if v is not None:
                put("income_mm", _fig("income_mm", "BEA", "pct", v, 0.1, _pct_text(v), period,
                                      link, published=published))
            sup = re.search(r'<supplemental\b[^>]*name="Personal Consumption Expenditures"[^>]*>'
                            r"(.*?)</supplemental>", item, re.S)
            sc = re.search(r"<current>(.*?)</current>", sup.group(1), re.S) if sup else None
            sv = _bea_number(_tag(sc.group(1), "percentChange")) if sc else None
            if sv is not None:
                put("spending_mm", _fig("spending_mm", "BEA", "pct", sv, 0.1, _pct_text(sv),
                                        period, link, published=published))
        elif (name.startswith("U.S. International Trade in Goods and Services")
              and v is not None and "billion" in cell.lower()):
            put("trade", _fig("trade", "BEA", "abs", v * 1e9, 1e8,
                              f"{'-' if v < 0 else ''}${abs(v):.1f}B", period, link,
                              published=published))
    return out


def _mdy(raw: str) -> date | None:
    try:
        return datetime.strptime(raw.strip(), "%m/%d/%y").date()
    except ValueError:
        return None


EIA_ROWS: dict[str, str] = {
    "Commercial (Excluding SPR)": "crude",
    "Total Motor Gasoline": "gasoline",
    "Distillate Fuel Oil": "distillate",
}
EIA_OIL_PAGE = "https://www.eia.gov/petroleum/supply/weekly/"
EIA_GAS_PAGE = "https://ir.eia.gov/ngs/ngs.html"


def eia_oil_figures(text: str) -> dict[str, dict[str, Any]]:
    """Table 1 of the Weekly Petroleum Status Report → the week's change in stocks,
    in barrels. Pure. The first column after the name is the week, the third the
    difference from the week before, both in millions."""
    rows = list(csv.reader(io.StringIO(text or "")))
    if not rows or len(rows[0]) < 4:
        return {}
    week = _mdy(rows[0][1])
    if week is None:
        return {}
    out: dict[str, dict[str, Any]] = {}
    for r in rows[1:]:
        key = EIA_ROWS.get(r[0].strip()) if r else None
        d = _dec(r[3]) if key and len(r) > 3 else None
        if key is None or d is None or key in out:
            continue
        out[key] = _fig(key, "EIA", "abs", float(d) * 1e6, 1000.0, f"{float(d):.3f}M",
                        f"week ending {week.day} {MONTHS[week.month - 1][:3]}", EIA_OIL_PAGE,
                        week_end=week.isoformat())
    return out


def eia_gas_figures(doc: Any) -> dict[str, dict[str, Any]]:
    """The Weekly Natural Gas Storage Report's file → the week's net change for the
    lower 48, in cubic feet. Pure."""
    if not isinstance(doc, dict):
        return {}
    try:
        released = datetime.strptime(str(doc.get("release_date"))[:11], "%Y-%b-%d").date()
    except ValueError:
        return {}
    for s in doc.get("series") or []:
        if "lower 48" not in str(s.get("name") or "").lower():
            continue
        net = (s.get("calculated") or {}).get("net_change")
        if isinstance(net, bool) or not isinstance(net, int | float):
            continue
        try:
            week = date.fromisoformat(str(doc.get("current_week"))[:10])
            period = f"week ending {week.day} {MONTHS[week.month - 1][:3]}"
        except ValueError:
            period = "the latest week"
        return {"gas_storage": _fig(
            "gas_storage", "EIA", "abs", float(net) * 1e9, 1e9, f"{net:g}B",
            period, EIA_GAS_PAGE, published=released.isoformat())}
    return {}


# ---------------------------------------------------------------- joining a row


def fits(fig: dict[str, Any], day: date) -> bool:
    """Is this figure the print of a release that landed on `day`? Pure. See the
    module note: this month's, not last month's."""
    ref = fig.get("ref")
    if ref:
        months = day.year * 12 + day.month - (int(ref[0]) * 12 + int(ref[1]))
        return months == int(fig.get("lag") or 1)
    if fig.get("published"):
        return fig["published"] == day.isoformat()
    if fig.get("week_end"):
        try:
            gap = (day - date.fromisoformat(fig["week_end"])).days
        except ValueError:
            return False
        return 3 <= gap <= 8
    return False


_RAW = re.compile(r"^\s*([+-])?\s*\$?\s*([\d,]*\.?\d+)\s*([%KMBT]?)", re.I)
_MULT = {"": 1.0, "%": 1.0, "K": 1e3, "M": 1e6, "B": 1e9, "T": 1e12}


def _style(raw: Any) -> tuple[float, str, int] | None:
    """A figure as the feed wrote it → (its number, its suffix, its decimals):
    "1.221M" → (1.221, "M", 3), "-105B" → (-105.0, "B", 0), "0.3%" → (0.3, "%", 1)."""
    m = _RAW.match(str(raw or ""))
    if not m:
        return None
    digits = m.group(2).replace(",", "")
    try:
        n = float(digits) * (-1.0 if m.group(1) == "-" else 1.0)
    except ValueError:
        return None
    return n, m.group(3).upper(), len(digits.split(".")[1]) if "." in digits else 0


def _as_the_feed_writes(fig: dict[str, Any], like: Any) -> tuple[float, str] | None:
    """The agency's figure as (number, text) in the units the row's other figures
    are in, or None when the row is in units the figure is not (a percentage row for
    a level): that is a row this figure is not the print of. Pure."""
    st = _style(like)
    if fig["kind"] == "pct":
        if st is not None and st[1] != "%":
            return None
        return fig["value"], fig["text"]
    if st is None:
        own = _style(fig["text"])
        if own is None:
            return None
        return fig["value"] / _MULT[own[1]], fig["text"]
    if st[1] == "%":
        return None
    n = fig["value"] / _MULT[st[1]]
    places = st[2]
    # Never coarser than the row would need to show the agency's own rounding.
    while places < 3 and abs(round(n, places) * _MULT[st[1]] - fig["value"]) > fig["step"] / 2:
        places += 1
    return round(n, places), f"{n:,.{places}f}{st[1]}"


def _agrees(fig: dict[str, Any], raw: Any) -> bool | None:
    """Does the feed's figure say what the agency's does, to the coarser of their
    two roundings? None when the feed's cannot be read. Pure."""
    st = _style(raw)
    if st is None:
        return None
    if (st[1] == "%") != (fig["kind"] == "pct"):
        return None
    feed = st[0] * _MULT[st[1]]
    half = max(fig["step"], 10.0 ** -st[2] * _MULT[st[1]]) / 2
    return abs(feed - fig["value"]) <= half * 1.001 + 1e-9


def apply(rows: list[dict[str, Any]], figures: dict[str, dict[str, Any]],
          now: float | None = None) -> list[dict[str, Any]]:
    """The calendar with each agency figure on the row it is the print of. Pure:
    a row that changes is a new dict, the rest are the ones passed in.

    The agency's figure becomes the row's `actual` where the feed has none or
    disagrees; `official` on the row says whose it is, for which period, whether the
    feed agreed, and what the feed said when it did not.
    """
    if not figures:
        return rows
    now = time.time() if now is None else now
    out: list[dict[str, Any]] = []
    for r in rows:
        key = key_of(r.get("event")) if r.get("country") == "United States" else None
        fig = figures.get(key) if key else None
        ts = r.get("ts")
        if fig is None or (isinstance(ts, int | float) and ts > now + 60):
            out.append(r)
            continue
        try:
            day = date.fromisoformat(str(r.get("date")))
        except ValueError:
            out.append(r)
            continue
        like = r.get("actual_raw") or r.get("consensus_raw") or r.get("previous_raw")
        shown = _as_the_feed_writes(fig, like) if fits(fig, day) else None
        if shown is None:
            out.append(r)
            continue
        feed_raw = r.get("actual_raw")
        agrees = _agrees(fig, feed_raw) if r.get("actual") is not None else None
        row = dict(r)
        row["official"] = {
            "by": fig["by"], "text": shown[1], "period": fig["period"], "url": fig["url"],
            # True: the feed says the same. False: it said `feed`. None: it had not said.
            "agrees": agrees, "feed": feed_raw if agrees is False else None,
        }
        if agrees is not True:
            actual, cons = shown[0], r.get("consensus")
            row["actual"], row["actual_raw"], row["released"] = actual, shown[1], True
            row["surprise"] = actual - cons if cons is not None else None
            read = read_of(str(r.get("event")), actual - cons, cons) if cons is not None else None
            row["read"] = read
            row["meaning"] = implication(read, r.get("themes")) if cons is not None else None
        out.append(row)
    return out


# ---------------------------------------------------------------- collecting

#: What the last pass read, so "is one due" can tell a figure that has arrived.
_held: dict[str, dict[str, Any]] = {}


def due(rows: list[dict[str, Any]], figures: dict[str, dict[str, Any]], now: float) -> set[str]:
    """The agencies with a release scheduled in the last DUE_SEC whose figure is not
    in yet: the ones to ask often. Pure."""
    hot: set[str] = set()
    for r in rows:
        ts = r.get("ts")
        if r.get("country") != "United States" or not isinstance(ts, int | float):
            continue
        if not 0 <= now - ts <= DUE_SEC:
            continue
        key = key_of(r.get("event"))
        if key is None:
            continue
        fig = figures.get(key)
        try:
            day = date.fromisoformat(str(r.get("date")))
        except ValueError:
            continue
        if fig is None or not fits(fig, day):
            hot.add(AGENCY[key])
    return hot


def _get(st: SourceStatus, url: str, key: str, ttl: float, validate: Any,
         data: bytes | None = None) -> Any:
    headers = {"Content-Type": "application/json"} if data is not None else None
    return st.absorb(fetch(url, key=key, ttl_sec=ttl, timeout=25, ua=BROWSER_UA, headers=headers,
                           stale_max_sec=STALE_MAX_SEC, validate=validate, data=data))


def collect(rows: list[dict[str, Any]] | None = None,
            now: float | None = None) -> tuple[dict[str, dict[str, Any]], SourceStatus]:
    """Every figure the agencies have out, by key. `rows` is the calendar held, for
    how often to ask; one agency failing costs that agency's figures."""
    global _held
    now = time.time() if now is None else now
    st = SourceStatus("Official figures")
    hot = due(rows or [], _held, now)

    def ttl(agency: str) -> float:
        return HOT_SEC[agency] if agency in hot else QUIET_SEC[agency]

    figures: dict[str, dict[str, Any]] = {}
    counts: dict[str, int] = {}
    errors: list[str] = []

    def take(agency: str, got: dict[str, dict[str, Any]], err: str | None) -> None:
        counts[agency] = counts.get(agency, 0) + len(got)
        figures.update(got)
        if err:
            errors.append(f"{agency}: {err}")

    year = datetime.fromtimestamp(now, UTC).astimezone(ET).year
    body = json.dumps({"seriesid": list(BLS_SERIES), "startyear": str(year - 1),
                       "endyear": str(year)}).encode()
    r = _get(st, BLS_API, "official_bls", ttl("BLS"), _bls_ok, body)
    try:
        take("BLS", bls_figures(r.json()) if r.ok and r.body else {}, None if r.ok else r.error)
    except ValueError as e:
        take("BLS", {}, f"parse: {e}")

    r = _get(st, CENSUS, "official_census", ttl("Census"), _xml_ok)
    take("Census", census_figures(r.text) if r.ok and r.body else {}, None if r.ok else r.error)

    r = _get(st, BEA, "official_bea", ttl("BEA"), _xml_ok)
    bea = bea_figures(r.text) if r.ok and r.body else {}
    # Both agencies publish the trade balance, in one joint release: the BEA's
    # entry carries the number as a number, so it is the one kept.
    take("BEA", bea, None if r.ok else r.error)

    r = _get(st, EIA_OIL, "official_eia_oil", ttl("EIA"),
             lambda b: None if b"Commercial" in b[:4000] else "not the stocks table")
    take("EIA", eia_oil_figures(r.text) if r.ok and r.body else {}, None if r.ok else r.error)
    r = _get(st, EIA_GAS, "official_eia_gas", ttl("EIA"), json_body)
    try:
        gas = eia_gas_figures(json.loads(r.body.decode("utf-8-sig"))) if r.ok and r.body else {}
        take("EIA", gas, None if r.ok else r.error)
    except ValueError as e:
        take("EIA", {}, f"parse: {e}")

    st.items = len(figures)
    st.notes.append(" · ".join(f"{a} {n}" for a, n in counts.items()))
    if hot:
        st.notes.append(f"a release is due: asking {', '.join(sorted(hot))} often")
    st.notes.extend(errors[:4])
    if not figures and errors:
        st.error = "; ".join(errors[:2])
    st.settle(bool(figures), "agency")
    if figures:
        _held = figures
    return figures, st


def window(today: date) -> tuple[date, date]:
    """The days a figure can belong to a row on the calendar held (for the tests)."""
    return today - timedelta(days=1), today + timedelta(days=7)
