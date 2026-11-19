"""
The pool — hundreds of large caps screened cheaply, so the scanner's forty
names are chosen from what is moving today rather than typed in on a quiet one.

WHY A POOL IN FRONT OF THE LIST, NOT A LONGER LIST. The scanner's arithmetic
(scan.py) needs each name's five-minute extended-hours bars, and the only free
feed for those is one Yahoo chart request per name every ~90 s
(sources/scanner.py). That scales by the name: forty names is ~20 requests a
minute, three hundred would be ~200, against an unpublished limit whose answer
— one HTTP 429 — pauses the whole scanner. So the wide read has to be a
different, batched read that answers one question only, IS THIS NAME IN PLAY
TODAY, and the names that are get promoted into the forty the Pine port runs
on. A promoted name's first chart request returns twelve sessions of bars, so its
levels, wave and score are complete within one fetch: no warm-up.

WHERE THE POOL COMES FROM, PROBED 2026-10-24 (a Saturday, so Friday's figures).
TradingView's screener endpoint — the JSON behind its public stock screener,
no login, one POST with the filter and the columns wanted, ~0.5 s:

    POST https://scanner.tradingview.com/america/scan
    {"filter": [market cap ≥ $5bn, type in (stock, dr), exchange in
                (NASDAQ, NYSE, AMEX)], "columns": [...], "range": [0, 2500]}

  - 1,586 names answered (415 KB): 1,441 stocks and 145 depositary receipts
    (TSM, ASML, NVO, BABA). 215 of the stocks are preferred lines (GOOGN, a
    1/20th preferred carrying Alphabet's whole market cap) — dropped by
    `typespecs`, which reads ["common"] for a common line and [""] for a DR.
    `is_primary` is NOT the filter: BRK.B reads false (BRK.A is primary).
  - Per name: the regular close and % change, the day's volume, the 30-day
    average volume, the 14-day ATR, market cap, TradingView's sector, the
    PRE-MARKET change, volume and last trade, and the last and next report
    dates — the next as an epoch at 12:00 UTC of the date, the last as the
    report's own instant (SPCX 1792526700 = 20 Oct 16:05 ET: after the close),
    which is how the rank tells a report that gaps TODAY from one that gaps
    tomorrow. `update_mode` was "delayed_streaming_900" on every row: fifteen
    minutes behind, like every other free quote this terminal reads.
  - The pre-market columns are the thing no Yahoo read can give for hundreds
    of names (Yahoo's pre-market bars carry no volume; its batched spark
    endpoint carries extended-hours closes but no volume either), and they
    are why this is one request a pass instead of the ~1,500 Yahoo chart
    reads a night the same screen would otherwise cost.
  - CONFIRMED IN A LIVE PRE-MARKET, Thu 2026-11-05 05:42 ET (APP close 271.75
    against a pre-market last of 314.05, +15.57%; QCOM 173.19 against 156.50):
    before 09:30 `close` is the
    previous regular close and `premarket_close` the last pre-market trade, so
    the gap is their difference. Saturday's reply cannot show that (both are
    Friday's); tools/pool_probe.py prints both so Monday can.

THE GATES — WHAT MAY BE PROMOTED AT ALL. The owner's own screen of 14 Oct 2026
for the fixed list was $2bn+ traded a day and a 14-day ATR of 2.5%+, which is
the bar for a name worth watching EVERY day. A pool is looser on purpose: the
rank below rewards today's move, and a name that gaps three ATRs on a report
is in play whatever its usual ATR. So: $500m+ traded on an average day (the
options on a large cap at that turnover are liquid enough for a weekly),
an ATR of 1.5%+ (room for the retest to pay the premium), $10+ a share.
Of Friday's 1,371 common lines and DRs that is 244 names; $1bn and 2.5% would
have been 84, $250m and 1% 497.

OPENED TO $2BN AND TO TODAY'S TURNOVER (owner, 2026-11-10: "the purpose of this
whole scanner is going into the day to be able to identify the most high
probability stocks with high volume and momentum and news moving it"). The
Day 2/3 names are mostly $2bn to $5bn and trade $100m on an average day, and
the morning's gappers often are too, so neither could ever be promoted: the
query now starts at $2bn (the wide tables' own floor), and the turnover gate
is met by an average day OR by today — $50m before the bell, $500m once it is
on — OR by a strong Day 2/3 track (20%+ on 1.5x at $2bn+, momentum.strong),
whose Day 1 volume says more about this week than its thirty-day average does.
The ATR gate is waived for those tracks for the same reason. $10 stands for all.

THE RANK — THE SCANNER'S OWN IN-PLAY ARITHMETIC (scanscore.in_play), applied
to the pool: the gap in the name's own daily ATRs (8 points, from 0.10 ATR to
0.75) and the pre-market volume as a share of an average day (8 points,
log-scaled from 0.25% to 4%), plus 2 for a report in play — this morning's,
last night's, or one due today. After the open the same two parts read the day's move and the
day's volume instead, with the volume scale moved to 5%–40% of an average
day (fifteen minutes into the session a name in play has traded a twentieth
of its day; one in the news nearly half). Nothing under 4 points is promoted:
a 0.4-ATR gap alone is 3.7, 1% of ADV before the bell alone is 5.5, so on a
dead morning the list is just the pinned names, which is the right answer.
Two parts more since 2026-11-10, for the trade the list is for (a break and
retest of PMH/PML or PDH/PDL, best when the name is already outside the day
before): 2 for a name through the previous day's high or low already (before
the bell against the last session's, after it against the prior one's), and
3 for a Day 2 or 2 for a Day 3+ of a strong move, where Day 1's high is the
level. The reason names each: "through PDH", "day 2 of a +24% move".

THE MARKS — WHEN THE LIST IS DECIDED. The pool is read every five minutes from
04:00 to 10:30 ET on a trading day (half-hourly otherwise, so the panel is
never blank), and promotions happen at four marks:
  08:00, 09:00, 09:25  — the pre-market list, replaced whole each time: nothing
                         has a signal yet, and a name that gapped at 07:00 and
                         faded by 09:00 should not hold a slot.
  10:00                — the post-open look, with the opening drive in the
                         figures (the feed is fifteen minutes behind, so the
                         09:25 mark saw 09:10). It only FILLS: the pre-market
                         marks leave POST_OPEN_SLOTS free for it and nothing
                         promoted is dropped once the session is on.
The marks no longer have the last word in the session (2026-11-19): from 09:35 to a quarter
hour before the close the live rotation (rotation.py) swaps a pick for a better setup off
the list, a minute a round. The core, the favourites and a name tracked by hand are never
swapped. The promotions go when the scanner's day rolls (20:00 ET; 17:00 on a half day).
A collector started at noon runs the latest pre-market mark it missed and then the
post-open one, so it still
gets a list. A stale copy of the pool (a failed read served from disk) ranks
the panel but never promotes: FRESH_MIN caps the age a promotion may read.

THE SLOTS. Pinned names are the owner's and always scanned; the pool fills
whatever is left of MAX_SYMBOLS. Thirty-one pinned leaves nine; a pinned list
trimmed to the core leaves twenty. The panel prints the number.

THIS IS A PERSONAL READ OF A PUBLIC PAGE'S DATA, like every Yahoo and Nasdaq
read here: one request a pass, a browser User-Agent, a 403 or 429 answered
with a ten-minute pause, and GEXYGEN plays no part in it.
"""

from __future__ import annotations

import json
import math
import os
import re
import threading
from collections.abc import Callable, Iterable
from datetime import UTC, date, datetime
from typing import Any

from .. import scan
from ..config import BROWSER_UA, CACHE_DIR
from ..holidays import prev_trading_day
from ..http import SourceStatus, fetch, json_body
from ..scanscore import GAP_FULL, GAP_MIN, PMVOL_FULL, PMVOL_MIN, W_GAP, W_PMVOL
from .scanner import _SYM, BENCHMARKS, MAX_SYMBOLS

URL = "https://scanner.tradingview.com/america/scan"
CACHE_KEY = "tv_pool"
STATE_FILE = os.path.join(CACHE_DIR, "scanner_pool.json")
#: THE POOL'S OWN RECORD (quant audit, 2026-11-13, phase 3). The rank had no outcome test:
#: the signal log only sees names that reached the list. Each mark writes the top
#: MARKS_LOGGED as they stood and which were promoted; after the close one line gives each
#: logged name's day (open-to-close figures from the screener), so tools/fit_score.py can
#: ask whether the top of the rank moved more than the rest. Beside the state file.
MARKS_NAME = "pool_marks.jsonl"
MARKS_LOGGED = 50
HEADERS = {
    "Content-Type": "application/json",
    "Accept": "application/json",
    "Origin": "https://www.tradingview.com",
    "Referer": "https://www.tradingview.com/",
}
#: The columns asked for, in the order the reply's `d` arrays carry them.
COLUMNS = [
    "name", "description", "type", "typespecs", "close", "change", "volume",
    "average_volume_30d_calc", "ATR", "market_cap_basic", "sector",
    "premarket_change", "premarket_volume", "premarket_close",
    "earnings_release_next_date", "earnings_release_date", "update_mode",
    # The day's range and the previous session's, for the part a name scores when it
    # is through the previous day's high or low (`outside_of`; that alone is not an
    # outside day, which is through the pre-market range as well): before
    # the bell `high`/`low` ARE the previous session's (the wide read says the same).
    "high", "low", "high[1]", "low[1]",
    # Volume against an average day TO THIS TIME OF DAY (TradingView's, the wide scan's
    # Breakouts column): the rank's volume part in the session (`in_play`).
    "relative_volume_intraday|5",
]
MIN_CAP = 2_000_000_000.0
RANGE = 4000

# ---- the gates (module docstring) -------------------------------------------
MIN_DOLLAR_VOL = 500_000_000.0
#: Today's turnover meets the gate too: this much before the bell, MIN_DOLLAR_VOL after.
MIN_PM_DOLLAR_VOL = 50_000_000.0
MIN_ATR_PCT = 1.5
MIN_PRICE = 10.0
#: A move this large (%), on today's turnover, takes a name past the ATR gate (`qualify`).
UNUSUAL_PCT = 3.0

# ---- the rank ---------------------------------------------------------------
#: After the open the volume part is RVOL, the same figure every page shows (quant
#: audit, 2026-11-13; owner: "fix everything"): in the session the day so far against an
#: average day to the same minute (TradingView's time-of-day column), once the session
#: is over the whole day against an average one. It was the day's volume against a whole
#: average day, which read a normal name at 10:00 as 15% and the same name at 15:00 as
#: 85%, so the part grew all afternoon whatever the name did. 0.75x earns the first
#: point and 2x, where the Breakouts filter and the scanner's volume part are full, earns
#: the whole part; 1x (a normal day) earns 2.3 of 8, as the scanner's gives 2 of 8.
RVOL_MIN = 0.75
RVOL_FULL = 2.0
# PAST FULL, THE RANK STILL HAS TO TELL NAMES APART (owner, 2026-11-11: "do what you
# recommend"). Both parts stopped at 8: a 0.75-ATR move and a 3-ATR one scored the
# same, and so did 40% of a day's volume and 400%. On the evening of 10 Nov the top
# ten read 21.0, 21.0, 21.0, 20.6, 20.0, 20.0, 20.0, 20.0, 20.0, 20.0, and the three
# slots a pre-market mark has were going to whichever of them the tie-break put
# first. So each part carries up to EXTRA more points for what lies beyond its full
# mark, on a log scale to the far mark below: a move of 0.75 to 3 ATR, pre-market
# volume of 4% to 40% of a day, RVOL of 2x to 10x (a day's volume of 40% to 400% of an
# average day until 2026-11-13, RVOL_MIN's note). Nothing under the
# full mark changes, so who clears MIN_SCORE is who cleared it before; only the
# order above it does. Read on that evening's ten: 28.1, 26.3, 26.2, 25.8, 25.6,
# 25.5, 22.9, 22.3, 22.3, 21.6. A judgement on the scale, with no outcome test.
EXTRA = 4.0
GAP_FAR = 3.0
PMVOL_FAR = 40.0
RVOL_FAR = 10.0
W_REPORT = 2
#: A fresh major story that is not the report (sources/tvnews, owner 2026-11-09:
#: "news is the engine of moves"). Three, so a 0.4-ATR gap (3.7, one short of the
#: bar) gets promoted with news behind it, and news alone (3.0) does not: a story
#: the tape is ignoring is not in play.
W_NEWS = 3
#: An outside day: through the previous day's high AND the pre-market high (or both
#: lows), the owner's rule (lib/outsideDay.ts; owner, 2026-11-13). Before the bell the
#: pre-market range is still forming and the previous day's level alone decides.
W_OUTSIDE = 2
#: Through the previous day's level alone, after the open: not an outside day, a step
#: towards one (quant audit, 2026-11-13: the pool paid it the outside day's two).
W_THROUGH = 1
#: A strong Day 2, and a Day 3 or later (momentum.strong).
W_DAY2 = 3
W_DAY3 = 2
MIN_SCORE = 4.0
#: The most a name can score: both parts and their extra, a story (worth more than
#: the report it stands in for), a level taken, a Day 2. For a bar drawn to scale.
SCORE_MAX = (W_GAP + EXTRA) + (W_PMVOL + EXTRA) + max(W_REPORT, W_NEWS) + W_OUTSIDE + max(
    W_DAY2, W_DAY3)

# ---- the marks and the clock ------------------------------------------------
# 06:00 AND 07:00 SINCE THE TODAY LIST (2026-11-13; today.py): the Stocks tab ranks the
# pre-market from 04:00, and a name it puts at the top needs its bars and levels read
# before the last hour, not from 08:00.
PRE_MARKS: tuple[tuple[int, str], ...] = (
    (6 * 60, "06:00"), (7 * 60, "07:00"), (8 * 60, "08:00"), (9 * 60, "09:00"),
    (9 * 60 + 25, "09:25"))
POST_MARK: tuple[int, str] = (10 * 60, "10:00")
POST_OPEN_SLOTS = 4
#: THE PINNED NAMES ARE FAVOURITES SINCE 2026-11-13 (owner: "yes go ahead with everything
#: proposed", the Today list). The engine reads MAX_SYMBOLS names; with 34 pinned the
#: pool had six slots, two of them before the bell, so the market's best could not get
#: on the list. Now at each pre-market mark the FAV_SLOTS favourites most in play (the
#: pool's rank, then the pinned order) are tracked for the day, the benchmarks always,
#: and the rest of the room is the pool's. A favourite not tracked today is still
#: pinned, and comes back the day it is in play.
FAV_SLOTS = 15
TICK_SEC = 20.0
ACTIVE_SEC = 300.0
IDLE_SEC = 1800.0
ACTIVE_UNTIL = 10 * 60 + 30
#: A promotion may read a copy this many minutes old at most (a live read is 0).
FRESH_MIN = 10.0
STALE_MAX_SEC = 2 * 3600.0
PAUSE_SEC = 600.0
TIMEOUT = 25
#: How many ranked names the panel is shown.
TOP_N = 15

# TradingView's sector → the S&P SPDR, where the mapping is unambiguous. Its
# "Finance" holds the REITs (XLRE) beside the banks and "Retail Trade" puts
# Walmart (XLP) beside Amazon (XLY), so those earn no sector rather than a
# wrong one — the same rule as sources/scanner.SECTOR.
TV_SECTOR: dict[str, str] = {
    "Electronic Technology": "XLK", "Technology Services": "XLK",
    "Health Technology": "XLV", "Health Services": "XLV",
    "Energy Minerals": "XLE", "Utilities": "XLU",
    "Consumer Non-Durables": "XLP", "Consumer Durables": "XLY",
    "Non-Energy Minerals": "XLB", "Process Industries": "XLB",
    "Producer Manufacturing": "XLI", "Transportation": "XLI",
    "Communications": "XLC",
}


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


def pool_body(body: bytes) -> str | None:
    """The screener's JSON, or why not."""
    bad = json_body(body)
    if bad:
        return bad
    head = body[:200].decode("utf-8", errors="replace")
    return None if '"data"' in head or '"totalCount"' in head else "not a screener reply"


# ------------------------------------------------------------------- parsing


def _num(v: Any) -> float | None:
    return float(v) if isinstance(v, (int, float)) and math.isfinite(v) else None


def _when(v: Any) -> tuple[str | None, str | None]:
    """A TradingView report instant → (the ET date, "pre" | "after" | "during").

    The next report comes as noon UTC of its date (08:00 ET: "pre", which is
    only a placeholder); the last report as its own instant, so 16:05 ET reads
    "after" — a report that gaps the NEXT session, not this one.
    """
    n = _num(v)
    if n is None or n <= 0:
        return None, None
    et = datetime.fromtimestamp(n, scan.ET)
    m = et.hour * 60 + et.minute
    when = "pre" if m < scan.RTH_START else "after" if m >= 16 * 60 else "during"
    return et.date().isoformat(), when


def parse(doc: Any) -> tuple[list[dict[str, Any]], str | None]:
    """The screener reply → one row per common line or DR. Pure.

    Preferred lines go (module docstring); a row whose `d` is not the column
    count asked for is skipped rather than mis-zipped into the wrong fields.
    """
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
        close = _num(r.get("close"))
        avg = _num(r.get("average_volume_30d_calc"))
        atr = _num(r.get("ATR"))
        earn_next, _ = _when(r.get("earnings_release_next_date"))
        earn_last, last_when = _when(r.get("earnings_release_date"))
        rows.append({
            "symbol": sym,
            "name": str(r.get("description") or "").strip() or None,
            "dr": kind == "dr",
            "close": close,
            "change": _num(r.get("change")),
            "volume": _num(r.get("volume")),
            "avg_vol": avg,
            "atr": atr,
            "cap": _num(r.get("market_cap_basic")),
            "tv_sector": str(r.get("sector") or "").strip() or None,
            "pm_change": _num(r.get("premarket_change")),
            "pm_volume": _num(r.get("premarket_volume")),
            "pm_close": _num(r.get("premarket_close")),
            "earn_next": earn_next,
            "earn_last": earn_last,
            "earn_last_when": last_when,
            "high": _num(r.get("high")), "low": _num(r.get("low")),
            "h1": _num(r.get("high[1]")), "l1": _num(r.get("low[1]")),
            "rv5": _num(r.get("relative_volume_intraday|5")),
            "dollar_vol": (avg * close) if avg is not None and close is not None else None,
            "atr_pct": (atr / close * 100.0) if atr is not None and close else None,
            "delayed": str(r.get("update_mode") or "").startswith("delayed"),
        })
    return rows, None


def today_turnover(r: dict[str, Any], basis: str) -> float | None:
    """What the name has traded in dollars in the session the rank reads: the
    pre-market's shares at its last print before the bell, the day's after. Pure."""
    if basis == "pre":
        v, px = r.get("pm_volume"), r.get("pm_close")
    else:
        v, px = r.get("volume"), r.get("close")
    return v * px if v is not None and px is not None else None


def qualify(rows: Iterable[dict[str, Any]], basis: str = "last",
            strong: Iterable[str] = ()) -> list[dict[str, Any]]:
    """The gates (module docstring). `strong` are the Day 2/3 names, which pass the
    turnover and ATR gates on their Day 1's say-so. Pure."""
    keep = set(strong)
    out = []
    for r in rows:
        dv, ap, px = r.get("dollar_vol"), r.get("atr_pct"), r.get("close")
        if px is None or px < MIN_PRICE:
            continue
        if r.get("symbol") in keep:
            out.append(r)
            continue
        today = today_turnover(r, basis)
        floor = MIN_PM_DOLLAR_VOL if basis == "pre" else MIN_DOLLAR_VOL
        busy_today = today is not None and today >= floor
        # A NAME MOVING UNUSUALLY TODAY PASSES THE ATR GATE (quant audit, 2026-11-13). The
        # gate is for names that never move; a large cap with a 1.2% ATR gapping 6% on its
        # report was kept out by its usual range on the one day it was not usual. Today's
        # turnover alone is not unusual for a megacap (Berkshire trades $500m any day), so
        # the move has to be UNUSUAL_PCT too.
        move = r.get("pm_change") if basis == "pre" else r.get("change")
        unusual = busy_today and move is not None and abs(move) >= UNUSUAL_PCT
        if not unusual and (dv is None or ap is None or ap < MIN_ATR_PCT):
            continue
        if unusual or busy_today or (dv is not None and dv >= MIN_DOLLAR_VOL):
            out.append(r)
    return out


def _append(path: str, obj: dict[str, Any]) -> None:
    """One JSON line onto a log; a log that cannot be written is skipped, never fatal."""
    try:
        os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
        with open(path, "a", encoding="utf-8") as f:
            f.write(json.dumps(obj, separators=(",", ":")) + "\n")
    except OSError:
        pass


def fresh_premarket(rows: Iterable[dict[str, Any]], basis: str,
                    seen: Callable[[str, float | None, float | None], bool | None] | None
                    ) -> list[dict[str, Any]]:
    """The rows with a pre-market that is still the last session's taken out. Pure.

    THE COLUMNS KEEP YESTERDAY'S PRE-MARKET UNTIL A NEW TRADE (quant audit, 2026-11-13;
    universe.py's module docstring). At 08:00 a name that has not traded yet showed
    yesterday's pre-market close and volume, and the pool scored them as this morning's
    gap and volume: a phantom gapper could take a slot. `seen(sym, pm_close, pm_volume)`
    is the wide scan's answer (UniverseStore.pm_traded): False when those figures are the
    ones it held before the session began, so the name has no pre-market today; True or
    None (no reference to compare) keep the row as it is."""
    if basis != "pre" or seen is None:
        return list(rows)
    out = []
    for r in rows:
        if seen(str(r.get("symbol") or ""), r.get("pm_close"), r.get("pm_volume")) is False:
            r = {**r, "pm_close": None, "pm_volume": None, "pm_change": None, "pm_stale": True}
        out.append(r)
    return out


# ---------------------------------------------------------------------- rank


def basis_for(clock: scan.Clock) -> str:
    """Which figures the rank reads: "pre" before the bell, "day" after it,
    "last" when no session is on (the figures are the last session's)."""
    if clock.session == "pre":
        return "pre"
    return "day" if clock.session in ("rth", "post") else "last"


def _clamp(x: float) -> float:
    return max(0.0, min(1.0, x))


def beyond(x: float, full: float, far: float) -> float:
    """The points past a part's full mark: none up to `full`, EXTRA at `far` and
    over, on a log scale between (the note over EXTRA). Pure."""
    if x <= full:
        return 0.0
    return EXTRA * _clamp(math.log(x / full) / math.log(far / full))


def gap_points(gap_atr: float | None) -> float:
    """The move part: none to GAP_MIN ATR, W_GAP at GAP_FULL, up to EXTRA more by
    GAP_FAR. Pure."""
    if gap_atr is None:
        return 0.0
    return W_GAP * _clamp((gap_atr - GAP_MIN) / (GAP_FULL - GAP_MIN)) + beyond(
        gap_atr, GAP_FULL, GAP_FAR)


def volume_points(x: float | None, vmin: float, vfull: float, vfar: float) -> float:
    """The volume part: none to `vmin`, W_PMVOL at `vfull` on a log scale, up to EXTRA
    more by `vfar`. Pure."""
    if x is None or x <= vmin:
        return 0.0
    return W_PMVOL * min(1.0, math.log(x / vmin) / math.log(vfull / vmin)) + beyond(x, vfull, vfar)


def session_points(gap_atr: float | None, adv_pct: float | None) -> float:
    """An extended session's move and volume as the pool reads the pre-market: the move
    in daily ATRs and the session's share of an average day. The Extended hours order
    (universe.extended), so that page and the pool agree on who is in play. Pure."""
    return gap_points(gap_atr) + volume_points(adv_pct, PMVOL_MIN, PMVOL_FULL, PMVOL_FAR)


def outside_of(row: dict[str, Any], basis: str) -> str | None:
    """"PDH" or "PDL" when the name is already through the previous day's high or
    low: before the bell the pre-market last against the last session's range, after
    it the day's last against the prior session's. None inside, or unread. Pure."""
    if basis == "pre":
        last, hi, lo = row.get("pm_close"), row.get("high"), row.get("low")
    else:
        last, hi, lo = row.get("close"), row.get("h1"), row.get("l1")
    if last is None or hi is None or lo is None:
        return None
    return "PDH" if last > hi else "PDL" if last < lo else None


def outside_both(row: dict[str, Any], basis: str, through: str | None) -> bool:
    """Is the name on an outside day by the owner's rule: through the previous day's
    level AND the pre-market range the same way (`pm_high`/`pm_low`, today's pre-market
    from the wide scan or Nasdaq)? Before the bell the previous day's level alone
    decides, as everywhere else (lib/outsideDay.ts). Unknown pre-market range: no. Pure."""
    if through is None:
        return False
    if basis == "pre":
        return True
    last, ph, pl = row.get("close"), row.get("pm_high"), row.get("pm_low")
    if last is None:
        return False
    if through == "PDH":
        return ph is not None and last > ph
    return pl is not None and last < pl


def in_play(row: dict[str, Any], basis: str, trading_day: date,
            news: Callable[[str], str | None] | None = None,
            stage: dict[str, Any] | None = None) -> dict[str, Any]:
    """One pool name's in-play read: the score, its parts and the reason. Pure.
    `stage` is the name's strong Day 2/3 track (momentum.strong), if it has one.

    Worked examples, Friday 23 Oct 2026's reply (tests/fixtures/tv_pool_trim.json),
    each part's points past its full mark after the plus (`beyond`):
      as "day"   KO    −2.76% on a 1.58 ATR: moved 2.63 = 1.67 ATR → 8.0 + 2.3 ;
                       18.9M of a 16.4M average day, the session over: RVOL
                       1.15 → 8 × ln(1.15/0.75)/ln(2/0.75) = 3.5         → 13.8
                 NVDA  −0.59% on a 6.06 ATR: 0.21 ATR → 8 × 0.11/0.65 = 1.3 ;
                       RVOL 0.76 → 0.1                                  → 1.4
                 (20.1 and 10.4 until 2026-11-13, when a whole average day was the
                 yardstick and 40% of one earned the full 8: RVOL_MIN's note.)
      as "pre"   SNDK  pre-market 1271.01 on a 1238.03 close, ATR 96.14:
                       0.34 ATR → 3.0 ; 193k of 8.58M = 2.25% of ADV →
                       8 × ln(2.25/0.25)/ln(16) = 6.3                   → 9.3
                 ORCL  0.15 ATR → 0.6 ; 0.66% of ADV → 2.8             → 3.4,
                       under MIN_SCORE: not promoted.
    """
    atr, close, avg = row.get("atr"), row.get("close"), row.get("avg_vol")
    if basis == "pre":
        last, ref, vol = row.get("pm_close"), close, row.get("pm_volume")
        vmin, vfull, vfar, vword = PMVOL_MIN, PMVOL_FULL, PMVOL_FAR, "pre-market"
    else:
        chg = row.get("change")
        ref = (close / (1.0 + chg / 100.0)
               if close is not None and chg is not None and chg > -100 else None)
        last, vol = close, row.get("volume")
        vmin, vfull, vfar = RVOL_MIN, RVOL_FULL, RVOL_FAR
        vword = "today" if basis == "day" else "last session"

    gap_atr = (abs(last - ref) / atr
               if last is not None and ref is not None and atr is not None and atr > 0 else None)
    gap_pts = gap_points(gap_atr)
    vol_pct = (vol / avg * 100.0) if vol is not None and avg is not None and avg > 0 else None
    # Before the bell the pre-market's share of an average day; after it RVOL (RVOL_MIN's
    # note): the time-of-day figure `rank` puts on the row in the session, else the whole
    # day against an average one, which is what RVOL is once the day is whole.
    rvol: float | None = None
    if basis != "pre":
        rvol = row["rvol"] if "rvol" in row else (
            vol_pct / 100.0 if vol_pct is not None else None)
    vol_pts = volume_points(vol_pct if basis == "pre" else rvol, vmin, vfull, vfar)

    reports = report_read(row, trading_day)
    rep_pts = float(W_REPORT) if reports else 0.0
    # The report earns its own two; a story is only counted when there is no report.
    story = news(str(row.get("symbol") or "")) if news is not None and not reports else None
    news_pts = float(W_NEWS) if story else 0.0
    through = outside_of(row, basis)
    outside = outside_both(row, basis, through)
    out_pts = float(W_OUTSIDE) if outside else float(W_THROUGH) if through else 0.0
    day_n = int(stage["stage"]) if stage and isinstance(stage.get("stage"), int) else 0
    day_pts = float(W_DAY2) if day_n == 2 else float(W_DAY3) if day_n >= 3 else 0.0

    bits = [
        (f"{'gap' if basis == 'pre' else 'moved'} {gap_atr:.2f} ATR"
         if gap_atr is not None else "no gap read"),
        (f"{vword} {vol_pct:.1f}% of ADV" if vol_pct is not None else f"no {vword} volume")
        if basis == "pre" else
        (f"{'' if basis == 'day' else 'last session '}RVOL {rvol:.2f}×" if rvol is not None
         else "no RVOL read"),
    ]
    if reports:
        bits.append(reports)
    if story:
        bits.append(f"{story.lower()} news")
    if through and outside and basis != "pre":
        bits.append(f"outside day (through {through} and the pre-market "
                    f"{'high' if through == 'PDH' else 'low'})")
    elif through:
        bits.append(f"through {through}")
    if row.get("pm_stale"):
        bits.append("no pre-market trade yet")
    if day_pts:
        bits.append(f"day {day_n} of a {float(stage['move']):+.0f}% move")
    return {
        "score": round(gap_pts + vol_pts + rep_pts + news_pts + out_pts + day_pts, 1),
        "reason": " · ".join(bits),
        "gap_atr": round(gap_atr, 2) if gap_atr is not None else None,
        "vol_pct": round(vol_pct, 2) if vol_pct is not None else None,
        "rvol": round(rvol, 2) if rvol is not None else None,
        "reports": reports,
        "through": through,
        "outside": outside,
        "day": day_n or None,
    }


def report_read(row: dict[str, Any], trading_day: date) -> str | None:
    """The report in play for `trading_day`, in words, or None. Pure.

    This morning's report (before 09:30) and last night's (after 16:00) both
    gap today; a report after today's close gaps tomorrow and earns nothing
    now; one due today is named as due.
    """
    td = trading_day.isoformat()
    prev = prev_trading_day(trading_day).isoformat()
    last, when = row.get("earn_last"), row.get("earn_last_when")
    if last == td:
        return None if when == "after" else "reported this morning"
    if last == prev:
        return "reported last night" if when == "after" else "reported yesterday"
    if row.get("earn_next") == td:
        return "reports today"
    return None


def rank(rows: Iterable[dict[str, Any]], clock: scan.Clock,
         news: Callable[[str], str | None] | None = None,
         strong: dict[str, dict[str, Any]] | None = None,
         pm_range: Callable[[str, date], tuple[float | None, float | None] | None] | None = None
         ) -> list[dict[str, Any]]:
    """Every qualified name scored and sorted, best first. `pm_range` is today's
    pre-market (high, low) for a name, which an outside day after the open needs
    (outside_both). Pure."""
    basis = basis_for(clock)
    out = []
    for r in rows:
        if clock.session == "rth":
            # In the session RVOL is to the time of day (RVOL_MIN's note). A name the
            # screener has no figure for reads "no RVOL", not a whole-day ratio that
            # would call every name quiet at 10:00.
            r = {**r, "rvol": r.get("rv5")}
        if basis == "day" and pm_range is not None:
            pmr = pm_range(r["symbol"], clock.trading_day)
            if pmr:
                r = {**r, "pm_high": pmr[0], "pm_low": pmr[1]}
        ip = in_play(r, basis, clock.trading_day, news, (strong or {}).get(r["symbol"]))
        out.append({"symbol": r["symbol"], "name": r.get("name"),
                    "sector": TV_SECTOR.get(r.get("tv_sector") or ""),
                    "close": r.get("close"), "cap": r.get("cap"), **ip})
    out.sort(key=lambda x: (-x["score"], -(x["gap_atr"] or 0.0), x["symbol"]))
    return out


# --------------------------------------------------------------------- marks


def _minute(clock: scan.Clock) -> int:
    return clock.now.hour * 60 + clock.now.minute


def _in_day(clock: scan.Clock) -> bool:
    """Inside a trading day's own 04:00–20:00, when the figures are today's."""
    return clock.session != "closed" and clock.trading_day == clock.now.date()


def marks_due(now: datetime, done: Iterable[str]) -> list[str]:
    """Which marks to run at `now`, in order (module docstring). Pure.

    Only the LATEST pre-market mark not yet run: a collector started at 09:40
    runs 09:25, not 08:00 then 09:00 then 09:25. Worked examples, a Tuesday:
      07:59 → [] · 08:00 → ["08:00"] · 09:30 (nothing run) → ["09:25"] ·
      10:05 ("09:25" run) → ["10:00"] · 14:00 (nothing run) → ["09:25", "10:00"]
      · 20:00 → [] (the day has rolled) · Saturday 09:00 → [].
    """
    clock = scan.clock_at(now)
    if not _in_day(clock):
        return []
    m = _minute(clock)
    done_set = set(done)
    out: list[str] = []
    reached = [label for minute, label in PRE_MARKS if m >= minute]
    if reached and reached[-1] not in done_set:
        out.append(reached[-1])
    if m >= POST_MARK[0] and POST_MARK[1] not in done_set:
        out.append(POST_MARK[1])
    return out


def next_mark(now: datetime, done: Iterable[str]) -> str | None:
    """The next mark still to come today, for the panel. Pure."""
    clock = scan.clock_at(now)
    if not _in_day(clock):
        return None
    m = _minute(clock)
    done_set = set(done)
    for minute, label in (*PRE_MARKS, POST_MARK):
        if m < minute and label not in done_set:
            return label
    return None


def choose_favourites(ranked: list[dict[str, Any]], pinned: Iterable[str],
                      n: int | None = None,
                      core: Iterable[str] = BENCHMARKS) -> list[str]:
    """The `n` (FAV_SLOTS) pinned names, benchmarks aside, the engine tracks today: the
    most in play by the pool's rank, then the rest in the pinned order. Pure."""
    n = FAV_SLOTS if n is None else n
    # The core (the benchmarks, and the MAG 7 in the collector) is tracked anyway: a
    # starred MAG 7 name takes no slot.
    skip = set(core)
    order = [s for s in pinned if s not in skip]
    score = {r["symbol"]: float(r.get("score") or 0.0) for r in ranked}
    pos = {s: i for i, s in enumerate(order)}
    return sorted(order, key=lambda s: (-score.get(s, -1.0), pos[s]))[:n]


# ONE TICKER A COMPANY (owner, 2026-11-19: "also in stocks why do i see GOOG and GOOGL? is
# that a gltihc / bug"). It was: the screen reads every US listing at $2bn+, Alphabet's
# class A and class C both passed with the same gap, and the 07:00 mark promoted GOOG while
# GOOGL is on the list for good (the MAG 7). One company, one chart, one story, two slots,
# and two rows of the Scanner, the Dashboard's Top setups and the Charts. A company is its
# name with the class words taken off; the news and the peers already treat share classes
# as one (scanner.SHARE_CLASSES, scanscore._TWINS).
_CLASS_WORDS = re.compile(r"\b(?:class|cl|series)\s+[a-z]\b\.?", re.I)


def company_key(name: Any) -> str | None:
    """A listing's company, for telling share classes of one apart from two companies:
    "Alphabet Inc. Class C" and "Alphabet Inc. Class A" are both "alphabet inc"; "Liberty
    Media Corporation Series C Liberty Live" keeps its tracker's name. None for no name, which
    is never merged. Pure."""
    if not isinstance(name, str) or not name.strip():
        return None
    n = _CLASS_WORDS.sub(" ", name.lower())
    n = re.sub(r"[^a-z0-9]+", " ", n).strip()
    return n or None


def one_per_company(rows: list[Any], *, name_of: Callable[[Any], Any] = lambda r: r.get("name"),
                    sym_of: Callable[[Any], Any] = lambda r: r.get("symbol"),
                    prefer: Iterable[str] = ()) -> list[Any]:
    """`rows` with one listing a company, in their order. The first of a company stays,
    unless a later share class is one the engine holds for good (`prefer`: the core, the
    favourites), which then takes the first one's place. A row with no name is kept. Pure."""
    keep = set(prefer)
    out: list[Any] = []
    at: dict[str, int] = {}
    for r in rows:
        k = company_key(name_of(r))
        if k is None:
            out.append(r)
        elif k not in at:
            at[k] = len(out)
            out.append(r)
        elif sym_of(r) in keep and sym_of(out[at[k]]) not in keep:
            out[at[k]] = r
    return out


def promote(ranked: list[dict[str, Any]], pinned: Iterable[str], current: list[dict[str, Any]],
            mark: str, cap: int = MAX_SYMBOLS,
            favs: list[str] | None = None,
            core: Iterable[str] = BENCHMARKS) -> list[dict[str, Any]]:
    """The promoted set after `mark` (module docstring). Pure.

    Pre-market marks return the fresh top names, leaving POST_OPEN_SLOTS of
    the room free; the post-open mark keeps `current` and fills the rest. With
    `favs` (the favourites tracked today, `choose_favourites`) the room is what the
    benchmarks and those leave; without, what the whole pinned list leaves.
    """
    pinned_l = list(pinned)
    core_s = set(core)
    excluded = set(pinned_l) | core_s
    # The core (the benchmarks and the MAG 7) is on the list whether `pinned` names it or
    # not (scanner.ScanStore.watchlist, 2026-11-13), so it is counted either way.
    used = len(set(pinned_l) | core_s) if favs is None else len(core_s | set(favs))
    slots = max(0, cap - used)
    # Never a share class of a company already on the list, and one of each company among
    # the rest (`one_per_company`): GOOG is not promoted beside the core's GOOGL.
    key_of = {r["symbol"]: company_key(r.get("name")) for r in ranked}
    held = {k for s in excluded if (k := key_of.get(s))}
    cands = one_per_company([r for r in ranked if r["score"] >= MIN_SCORE
                             and r["symbol"] not in excluded
                             and key_of.get(r["symbol"]) not in held])
    if mark != POST_MARK[1]:
        return cands[: max(0, slots - POST_OPEN_SLOTS)]
    keep = [c for c in current if c["symbol"] not in excluded
            and key_of.get(c["symbol"]) not in held][:slots]
    have = {c["symbol"] for c in keep}
    for r in cands:
        if len(keep) >= slots:
            break
        if r["symbol"] not in have:
            keep.append(r)
            have.add(r["symbol"])
    return keep


def verdict(entry: dict[str, Any] | None, pinned: bool, tracked: bool) -> dict[str, Any]:
    """What the engine does with a name today, for a wide table's row (owner,
    2026-11-10: the Extended hours pass should say which gappers get scored at the
    open and which need Track). `entry` is PoolStore.entry. Pure.

      pinned    on the list for good
      hand      tracked by hand today
      promoted  the pool took it, at `mark`
      tracked   on the list by another route (an ad-hoc read)
      inplay    in the pool over the bar, not taken: Track it
      quiet     in the pool, under the bar
      out       not in the pool (under $2bn, $10, or the turnover gate)
    """
    score = entry.get("score") if entry else None
    mark = entry.get("mark") if entry else None
    if pinned:
        state = "pinned"
    elif mark == "hand":
        state = "hand"
    elif mark:
        state = "promoted"
    elif tracked:
        state = "tracked"
    elif entry is None:
        state = "out"
    else:
        state = "inplay" if isinstance(score, (int, float)) and score >= MIN_SCORE else "quiet"
    return {"state": state, "score": score, "reason": entry.get("reason") if entry else None,
            "mark": mark if mark != "hand" else None, "at": entry.get("at") if entry else None}


def cadence(now: datetime) -> float:
    clock = scan.clock_at(now)
    active = clock.session == "pre" or (clock.session == "rth" and _minute(clock) < ACTIVE_UNTIL)
    return ACTIVE_SEC if active else IDLE_SEC


# --------------------------------------------------------------------- store


class PoolStore:
    """The pool between ticks: the last read, its rank, and today's promotions.

    Written by the pre-market thread's job; `set_enabled` comes from the API
    thread, so the promotion fields sit behind a lock and `view` copies.
    """

    def __init__(self, path: str = STATE_FILE) -> None:
        self._lock = threading.Lock()
        self._path = path
        self._marks_path = os.path.join(os.path.dirname(path) or ".", MARKS_NAME)
        #: The last session whose outcome line is written (or has nothing to write).
        self._outcome_done: str | None = None
        self.rows: list[dict[str, Any]] = []
        self.ranked: list[dict[str, Any]] = []
        self.screened = 0
        self.basis = "last"
        self.read_at: float | None = None
        self.source = "unavailable"
        self.error: str | None = None
        self.last_attempt = 0.0
        self.pause_until = 0.0
        self.force = False
        # ---- behind the lock
        self.enabled = True
        self.day: str | None = None
        self.promoted: list[dict[str, Any]] = []
        self.marks_done: list[str] = []
        #: The favourites tracked today (FAV_SLOTS), chosen at each pre-market mark and
        #: held from 09:25; None until the day's first mark, when every pin is tracked.
        self.favs: list[str] | None = None
        #: The rank as the last pre-market read left it, for the open (today.rank_open):
        #: after 09:30 the reads are the day's, and the open orders the pre-market's names.
        self.ranked_pre: list[dict[str, Any]] = []
        self.rows_pre: list[dict[str, Any]] = []
        self.pre_day: str | None = None
        #: Names put on the list by hand from the wide scan, for today (`track`).
        #: Apart from `promoted`, which the marks replace whole.
        self.manual: list[dict[str, Any]] = []
        #: On the list always, so never promoted and counted against the room: the
        #: benchmarks, and in the collector the MAG 7 too (scanner.CORE, 2026-11-13).
        self.core: tuple[str, ...] = tuple(BENCHMARKS)
        #: The fresh-major-story read (sources/tvnews.NewsStore.major).
        self.news: Callable[[str], str | None] | None = None
        #: The strong Day 2/3 tracks (momentum.strong), read once a tick.
        self.stage: Callable[[], dict[str, dict[str, Any]]] | None = None
        #: Whether a name's pre-market columns are today's (UniverseStore.pm_traded),
        #: and today's pre-market range (collector._pm_range): `fresh_premarket`, `rank`.
        self.pm_seen: Callable[[str, float | None, float | None], bool | None] | None = None
        self.pm_range: Callable[[str, date], tuple[float | None, float | None] | None] | None = None
        self.by_sym: dict[str, dict[str, Any]] = {}
        self._load()

    # ---- persistence --------------------------------------------------------

    def _load(self) -> None:
        try:
            with open(self._path, encoding="utf-8") as f:
                d = json.load(f)
        except (OSError, ValueError):
            return
        if not isinstance(d, dict):
            return
        self.enabled = bool(d.get("enabled", True))
        self.day = d.get("day") if isinstance(d.get("day"), str) else None
        self.promoted = [p for p in (d.get("promoted") or [])
                         if isinstance(p, dict) and p.get("symbol")]
        self.marks_done = [str(m) for m in (d.get("marks_done") or [])]
        self.manual = [p for p in (d.get("manual") or [])
                       if isinstance(p, dict) and p.get("symbol")]
        favs = d.get("favs")
        self.favs = [str(s) for s in favs] if isinstance(favs, list) else None

    def _save(self) -> None:
        tmp = self._path + ".tmp"
        try:
            os.makedirs(os.path.dirname(self._path), exist_ok=True)
            with open(tmp, "w", encoding="utf-8") as f:
                json.dump({"enabled": self.enabled, "day": self.day, "promoted": self.promoted,
                           "marks_done": self.marks_done, "manual": self.manual,
                           "favs": self.favs, "saved_utc": datetime.now(UTC).isoformat()}, f)
            os.replace(tmp, self._path)
        except OSError:
            pass

    # ---- what the scanner takes ---------------------------------------------

    def for_scan(self) -> tuple[date | None, list[str], dict[str, str], list[str] | None]:
        """(the day the promotions are for, their symbols, their sectors, the favourites
        tracked that day or None while every pin is)."""
        with self._lock:
            day = date.fromisoformat(self.day) if self.day else None
            # By hand first: a name someone asked for keeps its slot over the marks'.
            hand = [p["symbol"] for p in self.manual]
            syms = hand + [p["symbol"] for p in self.promoted
                           if p["symbol"] not in hand] if self.enabled else hand
            sectors = {p["symbol"]: p["sector"] for p in (*self.manual, *self.promoted)
                       if p.get("sector")}
            favs = list(self.favs) if self.enabled and self.favs is not None else None
        return day, syms, sectors, favs

    def track(self, sym: str, name: str | None, sector: str | None, at: str,
              room: int) -> str | None:
        """Put one name on today's list by hand. Returns why not, or None."""
        with self._lock:
            if any(p["symbol"] == sym for p in self.manual):
                return None
            if room <= 0:
                return f"the list is full at {MAX_SYMBOLS} names"
            self.manual.append({"symbol": sym, "name": name, "sector": sector, "score": 0.0,
                                "reason": "tracked by hand from the wide scan", "at": at,
                                "mark": "hand"})
            self._save()
        return None

    def picks(self) -> list[dict[str, Any]]:
        """Today's promotions as they stand (copies), for the live rotation (rotation.py)."""
        with self._lock:
            return [dict(p) for p in self.promoted]

    def rotate(self, moves: list[dict[str, Any]], names: dict[str, dict[str, Any]], at: str,
               now_ts: float) -> bool:
        """The live rotation's moves (rotation.decide) into today's picks: each name in takes
        the place of the one it replaces, or the end of the list for a free slot, with when it
        joined (`since`, which rotation.held reads for the minimum stay). `names` carries each
        name's company name and sector. True when the picks changed.

        In place, not appended: the scanner takes the picks in order up to the room the core
        and the favourites leave (ScanStore.watchlist), so a name added at the end of a list
        longer than the room would be cut. The pool's own in-play read stays the entry's
        `score` (the scale every other reader of it expects); the setup score that won the
        slot is `setup_score`."""
        with self._lock:
            if not self.enabled or not moves:
                return False
            have = {p["symbol"] for p in (*self.promoted, *self.manual)}
            picks = list(self.promoted)
            before = [p["symbol"] for p in picks]
            for m in moves:
                sym = str(m["in"])
                if sym in have:
                    continue
                info = names.get(sym) or {}
                vs = (f" over {m['out']} {round(m['out_score'] or 0)}" if m.get("out")
                      else " into a free slot")
                entry = {"symbol": sym, "name": info.get("name"), "sector": info.get("sector"),
                         "score": float((self.by_sym.get(sym) or {}).get("score") or 0.0),
                         "setup_score": m.get("in_score"),
                         "reason": f"rotated in at {at}: setup {round(m['in_score'] or 0)}{vs}",
                         "at": at, "mark": "live", "since": now_ts}
                at_i = next((i for i, p in enumerate(picks) if p["symbol"] == m.get("out")), None)
                if at_i is None:
                    picks.append(entry)
                else:
                    picks[at_i] = entry
                have.add(sym)
            if [p["symbol"] for p in picks] == before:
                return False
            self.promoted = picks
            self._save()
        return True

    def set_enabled(self, on: bool) -> bool:
        """Switch promotion. Off clears today's list; on re-runs today's latest
        mark on the next read (the marks are forgotten with the list) and makes
        that read the next tick's. True when anything changed."""
        with self._lock:
            if on == self.enabled:
                return False
            self.enabled = on
            self.promoted = []
            self.marks_done = []
            self.favs = None
            self.force = on
            self._save()
        return True

    # ---- the tick -----------------------------------------------------------

    def _roll(self, trading_day: date) -> bool:
        """A new trading day: last day's promotions go. True when any did."""
        with self._lock:
            if self.day == trading_day.isoformat():
                return False
            had = bool(self.promoted or self.manual or self.favs is not None)
            self.day = trading_day.isoformat()
            self.promoted = []
            self.manual = []
            self.marks_done = []
            self.favs = None
            self._save()
        return had

    def _promote(self, pinned: list[str], now: datetime) -> bool:
        changed = False
        et = now.astimezone(scan.ET).strftime("%H:%M")
        labels = [label for _, label in PRE_MARKS]
        with self._lock:
            if not self.enabled:
                return False
            for mark in marks_due(now, self.marks_done):
                if mark in labels:
                    # The favourites most in play this morning (FAV_SLOTS); from the
                    # 09:25 mark they hold for the day, as the promotions do.
                    self.favs = choose_favourites(self.ranked, pinned, core=self.core)
                new = promote(self.ranked, pinned, self.promoted, mark, favs=self.favs,
                              core=self.core)
                was = {p["symbol"]: p for p in self.promoted}
                self.promoted = [was.get(r["symbol"], {**r, "at": et, "mark": mark}) for r in new]
                if mark in labels:
                    # The earlier pre-market marks are done with it: a 09:25
                    # pass is never followed by an 09:00 one.
                    self.marks_done = labels[: labels.index(mark) + 1]
                else:
                    self.marks_done = [*self.marks_done, mark]
                changed = changed or set(was) != {p["symbol"] for p in self.promoted}
                self._save()
                self._log_mark(mark, now)
        return changed

    # ---- the pool's record (MARKS_NAME) --------------------------------------

    def _log_mark(self, mark: str, now: datetime) -> None:
        """One line a mark: the rank's top MARKS_LOGGED as it stood, and which were
        promoted. Behind the lock (called from `_promote`)."""
        prom = {p["symbol"] for p in self.promoted}
        rows = [{"sym": r["symbol"], "score": r.get("score"), "gap_atr": r.get("gap_atr"),
                 "vol_pct": r.get("vol_pct"), "through": r.get("through"),
                 "outside": r.get("outside"), "reports": r.get("reports"), "day": r.get("day"),
                 "close": r.get("close"), "promoted": r["symbol"] in prom}
                for r in self.ranked[:MARKS_LOGGED]]
        _append(self._marks_path, {
            "kind": "mark", "day": self.day, "mark": mark, "basis": self.basis,
            "at_et": now.astimezone(scan.ET).strftime("%H:%M"), "rows": rows})

    def _log_outcome(self, clock: scan.Clock, rows: list[dict[str, Any]]) -> None:
        """After the session, once: each name a mark logged that day, with the day it had
        (the screener's figures once no session is on are the finished session's)."""
        day = prev_trading_day(clock.trading_day).isoformat()
        if self._outcome_done == day:
            return
        logged: set[str] = set()
        try:
            with open(self._marks_path, encoding="utf-8") as f:
                for line in f:
                    try:
                        e = json.loads(line)
                    except ValueError:
                        continue
                    if e.get("day") != day:
                        continue
                    if e.get("kind") == "outcome":
                        self._outcome_done = day
                        return
                    logged |= {str(r.get("sym")) for r in e.get("rows") or [] if r.get("sym")}
        except OSError:
            pass
        self._outcome_done = day
        if not logged:
            return
        by = {r["symbol"]: r for r in rows}
        out = {s: {k: by[s].get(k) for k in ("close", "change", "high", "low", "atr", "volume",
                                             "avg_vol")}
               for s in sorted(logged) if s in by}
        _append(self._marks_path, {"kind": "outcome", "day": day, "rows": out})

    def tick(self, pinned: list[str], now: datetime | None = None
             ) -> tuple[SourceStatus, bool, bool]:
        """One step: read the pool when due, rank it, run any mark that has come.
        Returns (status, whether a read happened, whether the promotions changed)."""
        now = now or datetime.now(UTC)
        t = now.timestamp()
        clock = scan.clock_at(now)
        changed = self._roll(clock.trading_day)
        st = SourceStatus("Pool")
        read = False
        paused = t < self.pause_until
        due = self.force or t - self.last_attempt >= cadence(now)
        if due and not paused:
            self.last_attempt, self.force = t, False
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
                    strong = self.stage() if self.stage else {}
                    rows = fresh_premarket(rows, basis_for(clock), self.pm_seen)
                    self.rows = qualify(rows, basis_for(clock), strong)
                    self.screened = len(rows)
                    self.read_at = t - (r.age_min or 0.0) * 60.0
                    self.source = r.source
                    self.basis = basis_for(clock)
                    self.ranked = rank(self.rows, clock, self.news, strong, self.pm_range)
                    self.by_sym = {x["symbol"]: x for x in self.ranked}
                    if self.basis == "pre":
                        self.ranked_pre, self.rows_pre = self.ranked, self.rows
                        self.pre_day = clock.trading_day.isoformat()
                    self.error = r.error if r.source == "stale" else None
                    fresh = r.source == "live" or (r.age_min or 0.0) <= FRESH_MIN
                    if fresh:
                        changed = self._promote(pinned, now) or changed
                    if self.basis == "last" and fresh:
                        self._log_outcome(clock, rows)
                else:
                    self.error = err or "no names in the reply"
            else:
                self.error = r.error
        st.items = len(self.rows)
        st.settle(bool(self.rows), what="read")
        if self.error and not st.error:
            st.error = self.error
        with self._lock:
            n_prom, on, marks = len(self.promoted), self.enabled, list(self.marks_done)
        st.notes = [f"{self.screened} screened · {len(self.rows)} qualified · "
                    + (f"{n_prom} promoted" if on else "promotion off")
                    + (f" · marks {', '.join(marks)}" if marks else "")]
        nxt = next_mark(now, marks)
        if nxt and on:
            st.notes.append(f"next mark {nxt} ET")
        if paused:
            until = datetime.fromtimestamp(self.pause_until, scan.ET).strftime("%H:%M:%S")
            st.notes.append(f"TradingView refused (403/429) — paused until {until} ET")
        return st, read, changed

    def entry(self, sym: str) -> dict[str, Any] | None:
        """The name's place in the pool today: its rank entry, with the mark and the
        time when promoted or tracked by hand. None when it is not in the pool."""
        ranked = self.by_sym.get(sym)
        with self._lock:
            hand = next((p for p in self.manual if p["symbol"] == sym), None)
            prom = next((p for p in self.promoted if p["symbol"] == sym), None)
        hit = hand or prom
        if ranked is None and hit is None:
            return None
        out = dict(ranked) if ranked is not None else {k: v for k, v in hit.items()
                                                       if k not in ("mark", "at")}
        if hit is not None:
            out["mark"], out["at"] = hit.get("mark"), hit.get("at")
        return out

    # ---- the panel ----------------------------------------------------------

    def view(self, pinned: Iterable[str], now: datetime | None = None) -> dict[str, Any]:
        now = now or datetime.now(UTC)
        pin = set(pinned)
        with self._lock:
            on = self.enabled
            hand = [dict(p) for p in self.manual]
            have = {p["symbol"] for p in hand}
            promoted = hand + [dict(p) for p in self.promoted if p["symbol"] not in have]
            marks = list(self.marks_done)
            favs = list(self.favs) if self.enabled and self.favs is not None else None
        promoted = [p for p in promoted if p["symbol"] not in pin]
        shown = {p["symbol"] for p in promoted}
        top = [r for r in self.ranked
               if r["symbol"] not in pin and r["symbol"] not in self.core][:TOP_N]
        return {
            "ok": bool(self.rows),
            "on": on,
            "read_utc": (datetime.fromtimestamp(self.read_at, UTC).isoformat()
                         if self.read_at else None),
            "age_min": (round((now.timestamp() - self.read_at) / 60.0, 1)
                        if self.read_at else None),
            "source": self.source,
            "error": self.error,
            "screened": self.screened,
            "qualified": len(self.rows),
            "basis": self.basis,
            "gates": {"cap_usd": MIN_CAP, "dollar_vol_usd": MIN_DOLLAR_VOL,
                      "pm_dollar_vol_usd": MIN_PM_DOLLAR_VOL, "atr_pct": MIN_ATR_PCT,
                      "price_usd": MIN_PRICE, "min_score": MIN_SCORE},
            "score_max": SCORE_MAX,
            "top": [{**r, "promoted": r["symbol"] in shown} for r in top],
            "promoted": promoted,
            "day": self.day,
            "marks_done": marks,
            "next_mark": next_mark(now, marks),
            # The core (the benchmarks and the MAG 7) is on the list whether the favourites
            # name it or not (scanner.ScanStore.watchlist, 2026-11-13): counted either way.
            "slots": max(0, MAX_SYMBOLS - (len(set(pin) | set(self.core)) if favs is None
                                           else len(set(self.core) | set(favs)))),
            "post_open_slots": POST_OPEN_SLOTS,
            "favs": favs,
            "fav_slots": FAV_SLOTS,
        }
