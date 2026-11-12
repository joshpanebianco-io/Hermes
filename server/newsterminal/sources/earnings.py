"""
Earnings — the reports that move an index rather than a stock.

WHY A NEWS TERMINAL FOR INDEX FUTURES CARRIES EARNINGS AT ALL. The Nasdaq 100
is a cap-weighted index in which roughly the top seven names are a third of it.
NVDA after the close moves NQ harder than most macro prints move it in a week,
and a session note written without knowing who reports tonight is missing the
single largest scheduled risk in it. That is a different claim from "track every
earnings release": a small-cap beat is noise to this desk.

FILTERED BY MARKET CAP, NOT BY INDEX MEMBERSHIP. Membership lists go stale and
would need maintaining; capitalisation is in the payload, it is the thing that
actually determines index impact, and it needs no second source. Everything
above the threshold is kept and everything below is dropped, so the panel is
five or ten names a day rather than three hundred.

BEFORE OR AFTER THE BELL IS THE FIELD THAT MATTERS. An after-hours report is
tomorrow's gap; a pre-market one is this morning's. Nasdaq gives it and it rides
on every row.
"""

from __future__ import annotations

import json
import math
import re
import time
from datetime import date, datetime, timedelta
from typing import Any
from zoneinfo import ZoneInfo

from ..config import BROWSER_UA
from ..http import SourceStatus, clean_text, fetch, json_body

ET = ZoneInfo("America/New_York")
NASDAQ = "https://api.nasdaq.com/api/calendar/earnings?date={d}"

# Below this a report does not reach an index future on this desk. $50bn keeps
# roughly the S&P 100 plus the large Nasdaq names and drops the rest.
MIN_CAP = 50_000_000_000.0

# The handful whose reports are session-defining for NQ regardless of anything
# else — kept even if the cap field is missing or malformed, which it sometimes
# is for ADRs and recent listings.
BELLWETHERS = {
    "NVDA", "AAPL", "MSFT", "AMZN", "GOOGL", "GOOG", "META", "TSLA", "AVGO",
    "AMD", "MU", "INTC", "QCOM", "TSM", "ORCL", "CRM", "NFLX", "ADBE", "COST",
    "JPM", "GS", "BAC", "WMT", "XOM", "LLY", "UNH", "V", "MA",
}

_CAP = re.compile(r"[^\d.]")


def _cap(v: Any) -> float | None:
    """'$312,022,761,000' → 312022761000.0."""
    if v is None:
        return None
    t = _CAP.sub("", str(v))
    if not t or t == ".":
        return None
    try:
        return float(t)
    except ValueError:
        return None


def _when(v: Any) -> str:
    """Nasdaq's 'time-after-hours' → 'after'. Anything unknown is 'unspecified'."""
    t = str(v or "").lower()
    if "pre-market" in t or "pre_market" in t or "before" in t:
        return "pre"
    if "after-hours" in t or "after_hours" in t or "after" in t:
        return "after"
    return "unspecified"


def parse_day(doc: Any, day: str, keep: frozenset[str] = frozenset()) -> list[dict[str, Any]]:
    """One Nasdaq earnings day → the rows big enough to matter. Pure.

    `keep` is the scanner's watchlist: a name on it is kept whatever its size,
    because a $20bn stock reporting tonight is the single biggest fact about
    trading it tomorrow. Those rows carry `watch_only` so the Earnings panel —
    which is about what moves an INDEX — can leave them out.
    """
    rows = ((doc or {}).get("data") or {}).get("rows") or []
    out: list[dict[str, Any]] = []
    for r in rows:
        sym = clean_text(str(r.get("symbol") or "")).upper()
        if not sym:
            continue
        cap = _cap(r.get("marketCap"))
        big = sym in BELLWETHERS or (cap is not None and cap >= MIN_CAP)
        if not big and sym not in keep:
            continue
        forecast = clean_text(str(r.get("epsForecast") or "")) or None
        actual = clean_text(str(r.get("eps") or "")) or None
        out.append({
            "symbol": sym,
            "name": clean_text(str(r.get("name") or "")),
            "date": day,
            "when": _when(r.get("time")),
            "eps_forecast": forecast,
            "eps_actual": actual,
            # A NUMBER, NOT A STRING. Nasdaq sends "2.5" (or "N/A"); shipping the
            # raw text meant the UI could not compare it to zero to colour a
            # beat, and "N/A" survived as a truthy value.
            #
            # AND WORKED OUT WHEN NASDAQ HAS NOT YET (2026-11-05). The page for
            # a day just gone carries the actual before the surprise: ARM's
            # $0.15 against $0.22 arrived with "N/A" beside it, so a clean miss
            # read as neither beat nor miss. Nasdaq's own figure is this same
            # sum (AMD: $1.84 against $1.68 is its 9.52).
            "surprise_pct": _float(r.get("surprise")) if _float(r.get("surprise")) is not None
            else surprise_of(actual, forecast),
            "market_cap": cap,
            "bellwether": sym in BELLWETHERS,
            "watch_only": not big,
        })
    # Biggest first: on a day with eight reports the order the eye wants is by
    # how much of the index each one is.
    out.sort(key=lambda r: -(r.get("market_cap") or 0))
    return out


def _float(v: object) -> float | None:
    """Nasdaq's numerics arrive as text, with "N/A" for absent."""
    try:
        return float(str(v).replace(",", "").strip())
    except (TypeError, ValueError):
        return None


def _eps(v: str | None) -> float | None:
    """An EPS as Nasdaq prints it: "$1.84" → 1.84, "($0.17)" → -0.17, "N/A" → None."""
    if not v:
        return None
    t = v.replace("$", "").replace(",", "").strip()
    negative = t.startswith("(") and t.endswith(")")
    got = _float(t.strip("()"))
    if got is None:
        return None
    return -got if negative else got


def surprise_of(actual: str | None, forecast: str | None) -> float | None:
    """The surprise in percent of the estimate, on the size of the estimate so a
    beat is positive for a loss-maker too. None without both figures, or against
    a zero estimate, where a percentage means nothing. Pure."""
    a, f = _eps(actual), _eps(forecast)
    if a is None or f is None or f == 0:
        return None
    return round((a - f) / abs(f) * 100.0, 2)

# ------------------------------------------------------- the second source
#
# TRADINGVIEW'S SCREENER, FOR WHEN NASDAQ REFUSES (owner, 2026-11-11: "do what you
# recommend best"; the economic calendar has the same stand-in, sources/calendar.py).
# Nasdaq answered HTTP 403 from 05:49 ET on Tue 10 Nov 2026. The earnings list went
# on showing the copy read before that, so that evening's reports (PBR, CRWV) stood
# as "due" a day after they were out, and Thursday's list could not be refreshed.
#
# The screener the pool already reads (sources/pool.py) carries each name's last
# and next report: the instant, a flag for before the open or after the close
# (-1 / 1, 0 when the company has not said), the EPS reported, the estimate it
# was set against and the estimate for the next one. Two small requests, one for
# the reports ahead and one for those just gone, each cut to the window by date.
#
# ITS EPS IS NOT ALWAYS NASDAQ'S. The two take their figures from different
# vendors, and a company with a large one-off can read as a beat on one and a
# miss on the other (Occidental's third quarter, 9 Nov 2026: $1.91 against $1.46
# here, $0.64 against $1.43 on Nasdaq). So NASDAQ STAYS FIRST when it answers,
# and the status row says when this is the one in use.

TV_SCAN = "https://scanner.tradingview.com/america/scan"
#: What the app sends TradingView everywhere (sources/pool.py, sources/tvnews.py).
TV_HEADERS = {
    "Content-Type": "application/json",
    "Accept": "application/json",
    "Origin": "https://www.tradingview.com",
    "Referer": "https://www.tradingview.com/",
}
TV_NEXT = "earnings_release_next_date"
TV_LAST = "earnings_release_date"
#: The columns asked for, in the order the reply's `d` arrays carry them.
TV_COLUMNS = [
    "name", "description", "type", "typespecs", "market_cap_basic",
    TV_NEXT, "earnings_release_next_time", "earnings_per_share_forecast_next_fq",
    TV_LAST, "earnings_release_time", "earnings_per_share_fq",
    "earnings_per_share_forecast_fq", "eps_surprise_percent_fq",
]
#: The screener's own floor. The panel keeps $50bn and the watchlist (MIN_CAP,
#: `keep`); this only has to be under every name the watchlist can hold.
TV_MIN_CAP = 2_000_000_000.0
TV_RANGE = 600
#: Nasdaq is not asked again before this (epoch), and why.
NASDAQ_RETRY_SEC = 1800.0
_nasdaq_wait = 0.0
_nasdaq_why = ""
_source = "nasdaq"


def source() -> str:
    """The feed the last `collect` returned rows from ("nasdaq" or "tradingview")."""
    return _source


def tv_query(field: str, lo_ts: int, hi_ts: int) -> dict[str, Any]:
    """The screener request for the names whose `field` (a report instant) falls in
    the window. Pure."""
    return {
        "filter": [
            {"left": "market_cap_basic", "operation": "egreater", "right": TV_MIN_CAP},
            {"left": "type", "operation": "in_range", "right": ["stock", "dr"]},
            {"left": "exchange", "operation": "in_range", "right": ["NASDAQ", "NYSE", "AMEX"]},
            {"left": field, "operation": "in_range", "right": [lo_ts, hi_ts]},
        ],
        "columns": list(TV_COLUMNS),
        "sort": {"sortBy": "market_cap_basic", "sortOrder": "desc"},
        "range": [0, TV_RANGE],
    }


def tv_body(body: bytes) -> str | None:
    """The screener's JSON, or why not."""
    bad = json_body(body)
    if bad:
        return bad
    head = body[:200]
    return None if b'"data"' in head or b'"totalCount"' in head else "not a screener reply"


def _money(v: Any) -> str | None:
    """An EPS as Nasdaq prints it, so `_eps` and the panel read both feeds alike:
    1.84 → "$1.84", -0.17 → "($0.17)". None for no figure."""
    if isinstance(v, bool) or not isinstance(v, (int, float)) or not math.isfinite(v):
        return None
    return f"${v:.2f}" if v >= 0 else f"(${abs(v):.2f})"


def _tv_when(flag: Any, at: datetime, placeholder: bool) -> str:
    """Before the open or after the close, from TradingView's flag (-1 / 1); with no
    flag, from the instant itself when it is a real one. A report still ahead whose
    company has not said comes as noon UTC, which is no time at all."""
    if flag == -1:
        return "pre"
    if flag == 1:
        return "after"
    if placeholder:
        return "unspecified"
    m = at.hour * 60 + at.minute
    return "pre" if m < 9 * 60 + 30 else "after" if m >= 16 * 60 else "unspecified"


def parse_tradingview(doc: Any, field: str, lo: date, hi: date,
                      keep: frozenset[str] = frozenset()) -> list[dict[str, Any]]:
    """One screener reply → earnings rows for the ET days `lo`..`hi`, in the shape
    `parse_day` makes. `field` says which the reply is: TV_NEXT, the reports ahead
    (an estimate, no result), or TV_LAST, those just gone (both). Pure.

    Preferred lines are passed over (KKR/PD reports nothing of its own); a row whose
    `d` is not the column count asked for is skipped rather than mis-zipped.
    """
    if not isinstance(doc, dict) or not isinstance(doc.get("data"), list):
        return []
    ahead = field == TV_NEXT
    out: list[dict[str, Any]] = []
    for item in doc["data"]:
        d = item.get("d") if isinstance(item, dict) else None
        if not isinstance(d, list) or len(d) != len(TV_COLUMNS):
            continue
        r = dict(zip(TV_COLUMNS, d, strict=True))
        sym = clean_text(str(r.get("name") or "")).upper()
        specs = r["typespecs"] if isinstance(r.get("typespecs"), list) else []
        if not sym or (r.get("type") == "stock" and "common" not in specs):
            continue
        ts = r.get(field)
        if isinstance(ts, bool) or not isinstance(ts, (int, float)) or ts <= 0:
            continue
        at = datetime.fromtimestamp(float(ts), ET)
        if not lo <= at.date() <= hi:
            continue
        cap = r.get("market_cap_basic")
        cap = float(cap) if isinstance(cap, (int, float)) and not isinstance(cap, bool) else None
        big = sym in BELLWETHERS or (cap is not None and cap >= MIN_CAP)
        if not big and sym not in keep:
            continue
        if ahead:
            forecast, actual = _money(r.get("earnings_per_share_forecast_next_fq")), None
            when = _tv_when(r.get("earnings_release_next_time"), at, placeholder=True)
            surprise = None
        else:
            forecast = _money(r.get("earnings_per_share_forecast_fq"))
            actual = _money(r.get("earnings_per_share_fq"))
            when = _tv_when(r.get("earnings_release_time"), at, placeholder=False)
            sp = r.get("eps_surprise_percent_fq")
            surprise = (round(float(sp), 2)
                        if isinstance(sp, (int, float)) and not isinstance(sp, bool)
                        and math.isfinite(sp) else surprise_of(actual, forecast))
        out.append({
            "symbol": sym,
            "name": clean_text(str(r.get("description") or "")),
            "date": at.date().isoformat(),
            "when": when,
            "eps_forecast": forecast,
            "eps_actual": actual,
            "surprise_pct": surprise,
            "market_cap": cap,
            "bellwether": sym in BELLWETHERS,
            "watch_only": not big,
        })
    return out


def _from_tradingview(today: date, days_ahead: int, days_back: int, keep: frozenset[str],
                      why: str) -> tuple[list[dict[str, Any]], SourceStatus]:
    """The window from the screener: the reports just gone and the ones ahead."""
    st = SourceStatus("Earnings")
    lo, hi = today - timedelta(days=days_back), today + timedelta(days=days_ahead)

    def start(d: date) -> int:
        return int(datetime(d.year, d.month, d.day, tzinfo=ET).timestamp())

    now = int(time.time())
    asks = [
        (TV_LAST, start(lo), now + 3600, "earn_tv_last"),
        (TV_NEXT, start(today), start(hi) + 86400, "earn_tv_next"),
    ]
    rows: dict[str, dict[str, Any]] = {}
    failed = 0
    for field, a, b, key in asks:
        r = st.absorb(fetch(
            TV_SCAN, key=key, ttl_sec=1800.0, ua=BROWSER_UA, timeout=20,
            headers=dict(TV_HEADERS), stale_max_sec=86400.0, validate=tv_body,
            data=json.dumps(tv_query(field, a, b)).encode(),
        ))
        if not r.ok:
            failed += 1
            st.error = st.error or r.error
            continue
        try:
            got = parse_tradingview(r.json(), field, lo, hi, keep)
        except (ValueError, TypeError, AttributeError) as e:
            failed += 1
            st.error = st.error or f"parse: {e}"
            continue
        # The reports gone are read first and win: a name is in both for a moment
        # when its next date has not rolled on yet.
        for row in got:
            rows.setdefault(row["symbol"], row)
    out = sorted(rows.values(), key=lambda r: (r["date"], -(r.get("market_cap") or 0)))
    st.items = len(out)
    st.notes.append(f"TradingView's screener: Nasdaq is not answering ({why})")
    st.settle(failed == 0, "read")
    return out, st


def _from_nasdaq(today: date, days_ahead: int, days_back: int,
                 keep: frozenset[str]) -> tuple[list[dict[str, Any]], SourceStatus, bool]:
    """Nasdaq's days → (rows, status, whether it is NOT delivering): two or more of
    the days that can still change (yesterday on) failed or came back as the copy
    on disk."""
    st = SourceStatus("Earnings")
    rows: list[dict[str, Any]] = []
    failed = 0
    behind = 0
    span = range(-days_back, days_ahead + 1)

    for off in span:
        d = (today + timedelta(days=off)).isoformat()
        r = fetch(
            NASDAQ.format(d=d),
            key=f"earn_{d}",
            # YESTERDAY IS NOT SETTLED (2026-11-05). This said "past days are
            # settled" and held any past day for 24 hours, so the copy read at
            # 22:31 ET on the day, before its actuals existed, went on being
            # served until 22:31 the next night. On Thursday morning ARM and
            # QCOM still showed no result, though Nasdaq had them: the Earnings
            # panel, the notes and Hermes all said they had not reported. Two
            # days back and older really are settled.
            ttl_sec=86400.0 if off < -1 else 1800.0,
            ua=BROWSER_UA,
            timeout=20,
            headers={"Accept": "application/json"},
            stale_max_sec=7 * 86400.0 if off < 0 else 86400.0,
            validate=json_body,
        )
        st.absorb(r)
        if off >= -1 and (not r.ok or r.source == "stale"):
            behind += 1
        if not r.ok:
            failed += 1
            st.error = st.error or r.error
            continue
        try:
            rows.extend(parse_day(r.json(), d, keep))
        except (ValueError, TypeError, AttributeError) as e:
            failed += 1
            st.error = st.error or f"parse: {e}"

    rows.sort(key=lambda r: (r["date"], -(r.get("market_cap") or 0)))
    st.items = len(rows)
    if failed:
        st.notes.append(f"{failed} of {len(list(span))} days unavailable")
    st.settle(len(rows) > 0 or failed == 0, "day")
    return rows, st, behind >= 2


def collect(
    days_ahead: int = 4, days_back: int = 2, keep: frozenset[str] = frozenset(),
    today: date | None = None,
) -> tuple[list[dict[str, Any]], SourceStatus]:
    """A few sessions either side of today, big names only, plus `keep`: Nasdaq's
    list, or the screener's while Nasdaq is not delivering (the note above).
    `today` is for the tests; the desk's day is New York's."""
    global _source, _nasdaq_wait, _nasdaq_why
    today = today or datetime.now(ET).date()
    now = time.time()
    held: tuple[list[dict[str, Any]], SourceStatus] | None = None
    if now >= _nasdaq_wait:
        rows, st, down = _from_nasdaq(today, days_ahead, days_back, keep)
        if not down:
            _source = "nasdaq"
            return rows, st
        held = (rows, st)
        _nasdaq_wait = now + NASDAQ_RETRY_SEC
        _nasdaq_why = st.stale_error or st.error or "unreachable"
    tv_rows, tv_st = _from_tradingview(today, days_ahead, days_back, keep,
                                       _nasdaq_why or "unreachable")
    if tv_st.ok:
        _source = "tradingview"
        return tv_rows, tv_st
    # Neither is answering: what Nasdaq's copy on disk still holds, marked stale.
    if held is None:
        rows, st, _ = _from_nasdaq(today, days_ahead, days_back, keep)
        held = (rows, st)
    _source = "nasdaq"
    return held
