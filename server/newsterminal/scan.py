"""
The scanner's arithmetic — the Pine script's levels, 8 EMA wave and signals, ported.

WHY A PORT AND NOT A NEW MODEL. The owner already trades off this indicator: a
break of the pre-market or previous-day high/low, then the retest of that level
(or of VWAP / the 8 EMA wave when price has run too far from it), on the
10-minute chart. A scanner that ranked stocks by some other idea of "strong"
would be a second opinion nobody asked for. So every number here is the Pine
script's number, computed the Pine script's way, and where this file has to
choose something the script did not (the free feed's limits, the clock outside
trading hours) the choice is named where it is made.

WHAT THE SCRIPT SEES, AND WHAT THIS SEES. The script runs on TradingView's
extended-hours 10-minute bars. This runs on Yahoo's 5-minute extended-hours
bars resampled to 10 minutes on the same :00/:10/:20 grid — the high, low and
close of a 10-minute bucket are exactly its two 5-minute halves', so levels,
the EMA wave and every signal land on the same bars.

WHAT THE FREE FEED CANNOT GIVE, said once here and again in the payload:
Yahoo's PRE-market bars carry no volume (observed 2026-10-13: every 04:00–09:29
bar on AAPL, SPY and SPCX reads 0), while its post-market bars do (TSLA printed
2.57M after Monday's close). So today's volume is the regular session plus the
post-market — the script's `volExt` default, short only the pre-market it cannot
see — relative volume exists from the bell, and VWAP is anchored at 09:30: a
pre-market VWAP would be a division by zero dressed as a level.

THE CLOCK OUTSIDE THE SESSION. The script's "today" is the last day it has bars
for, so at 22:00 it still shows the day that just closed. A scanner opened at
night is being read to plan the NEXT session, so outside 04:00–20:00 (and at
weekends and on holidays) the trading day is the next weekday and the previous
day's levels are the session that just finished. Inside 04:00–20:00 the two
agree exactly.

THE ORDER OF OPERATIONS INSIDE A BAR IS THE SCRIPT'S. On each confirmed 10-minute
regular-session bar: all four levels step (PDH, PMH, PDL, PML), then the (L)
retest is read, then a pending (E) candle's trigger is checked, then — the
`sigBar` block — a pending (E) that lost the wave or the bias is cancelled, a
new (E) candle can be set, and the arming flags are re-read. Reordering any of
those changes which bar fires, so they stay in this order.
"""

from __future__ import annotations

import math
from bisect import bisect_left
from dataclasses import dataclass, field
from datetime import date, datetime
from typing import Any, NamedTuple
from zoneinfo import ZoneInfo

from . import structure
from .holidays import close_minute, early_close, is_trading_day, next_trading_day

ET = ZoneInfo("America/New_York")

# Minutes of the ET day. The script's sessions are "0400-0930" and "0930-1600".
# On the NYSE's half days the regular session ends at 13:00 and the late session
# at 17:00 — `rth_end` / `post_end` read the holiday table, these are the norm.
PM_START = 4 * 60
RTH_START = 9 * 60 + 30
POST_END = 20 * 60
POST_END_HALF = 17 * 60


def rth_end(d: date) -> int:
    """Minute of the ET day the regular session ends on `d` (13:00 on a half day)."""
    return close_minute(d)


def post_end(d: date) -> int:
    """Minute the late session ends on `d` — 17:00 on a half day, else 20:00."""
    return POST_END_HALF if early_close(d) else POST_END

SRC_SEC = 300  # Yahoo's 5-minute bars
BAR_SEC = 600  # the 10-minute chart the script is built for
#: RVOL compares volume so far with the same time of day on this many prior
#: sessions. Ten since 2026-11-10 (it was four, the whole five-day download): one
#: earnings day in the window then moves the figure a tenth, not a quarter, and a
#: name whose normal changed reads as normal again within two weeks. The download
#: is sized for it (sources/scanner.BARS_RANGE); signals logged before that date
#: carry the four-session figure in their `ctx`.
RVOL_SESSIONS = 10

# A BAR IS CONFIRMED BY THE DOWNLOAD, NOT BY THE CLOCK (audit, 2026-10-14). The
# clock passing 09:50 does not put the 09:40 bar's last prints in a copy of the
# bars read at 09:49:30 — and on Oct 13 that copy fired eight signals the final
# bars never had (IBM's (L) at 09:40, score 82, alerted and logged, among them).
# So a ten-minute bar counts as closed only in bars downloaded this long after
# its close: Yahoo's bars carry a bar's last trades a few seconds after it ends.
# The scanner's close read (sources/scanner.py) fetches every name just after
# this mark, so the wait it costs a signal is seconds.
CLOSE_LAG_SEC = 10

ATR_LEN = 14  # ta.atr(14) on the chart, and the hand-kept daily ATR
WAVE_LEN = 8  # EMA 8 / 9 / 10
BUF_MULT = 0.25  # "Retest buffer (× ATR 14)"
NEAR_PCT = 0.90  # "'About to break' alert at progress ≥ %"
RS_BARS = 6  # "Last N bars" — one hour on the 10m

# THE LEAST A STOP IS COUNTED AS: THE SCRIPT'S OWN RETEST BUFFER. The script's "stop
# idea" is the signal bar's low (its high for a short), and a bar that closes on its
# low puts that stop a cent or two away, or on the entry itself: GOOGL's (L) at 11:40
# on 6 Nov 2026 bought 286.98 with the stop idea two cents under it, 1R = $0.02 on a
# $287 stock. Nobody trades that stop, and the record read as if they did (stopped,
# 119R against). So a stop's distance is never counted as less than the buffer the
# script itself calls a retest by (BUF_MULT x the ten-minute ATR at the signal's
# bar): each (L) and (E) carries it as `risk_min`, and the record
# (scanlog.compute_outcome) and the contract's risk (optcalc.trade_plan) both read
# the stop through it. The script's own stop idea is still what is shown.
#
# WHAT IT REACHES, IN ITS OWN UNIT (2026-11-11; the 893 settled signals whose bars
# were still held, 12 sessions, 26 Oct to 10 Nov 2026, each on the script's own
# stop). The audit that prompted the floor measured stops as a share of PRICE (531 of
# 1,580 under 0.25% of price, +1R 42% against 49 to 50% for the rest) and that is a
# different unit: the ten-minute ATR is a median 0.54% of price, so a quarter of it
# is about 0.13%. The floor binds 84 signals, 9% and not a third, every one an (L):
#
#     stop, in 10m ATRs     n    +1R  stopped   +1R by half of the record
#     under 0.25           81    30%    70%     33% of 39, 26% of 42
#     0.25 to 0.50        120    43%    55%     52% of 54, 36% of 66
#     0.50 to 0.75        199    52%    47%     59% of 85, 47% of 114
#     0.75 to 1.00        225    48%    49%     56% of 124, 39% of 101
#     1.00 to 1.50        197    49%    44%     54% of 109, 42% of 88
#     1.50 and over        68    41%    21%     53% of 38, 27% of 30
#
# and three more with the stop on the entry, which had no R at all. Read on the
# floor the 84 reach +1R 44% of the time: 11 that were stopped get there first.
#
# WHY A QUARTER AND NOT MORE. Under it the 5-minute bars cannot say which came
# first: 35 of that band's 57 stops were on a bar that also reached +1R, which the
# record counts as stopped (scanlog); between a quarter and a half it is 7 of 67,
# above a half 1 of 305. So the band's 30% is the bars' resolution as much as the
# trade, and the floor ends about where that does. Above it the record has nothing
# to say for a higher one: read with no floor, a quarter, a half and three quarters,
# the whole record reaches +1R 46.3, 47.6, 47.8 and 48.2% of the time, and the band
# a half would add moves from 43% to 47% (52 to 56 and 36 to 39 by half). The floor
# is in ATRs, so a quiet stock's is small: GME's 2.47c stop on 10 Nov, the one that
# started the look, is 0.27 of its 9.2c ATR and stands as it was (it lost on any
# stop up to a whole ATR). A quarter is a judgement, like the buffer it borrows;
# raising it is the owner's call.


def risk_of(price: float, stop: float, risk_min: Any = None) -> float:
    """A stop's distance from its entry, never counted as less than `risk_min` (the
    note above). Pure."""
    dist = abs(float(price) - float(stop))
    if isinstance(risk_min, (int, float)) and not isinstance(risk_min, bool) and risk_min > 0:
        return max(dist, float(risk_min))
    return dist

# How far past a broken level price may run before the level stops being the
# entry and VWAP / the 8 EMA wave takes over — the owner's "super far above or
# below". In 10-minute ATRs, the unit the retest buffer is already measured in.
EXT_ATR = 2.5

#: A session's daily row is its final bar in a copy downloaded this long after the
#: close (the closing print and the official range take a few minutes to land), and
#: carries the official open in one downloaded this long after 09:30.
DAILY_SETTLE_SEC = 15 * 60.0
DAILY_OPEN_SEC = 60.0

# The script's daily ATR is seeded at the first day it has bars for: four
# thousand 10-minute extended bars (calc_bars_count) is ~41 sessions back. The
# same window here keeps the seed's leftover weight the same, ~5%.
DAILY_ATR_SESSIONS = 42


class Bar(NamedTuple):
    t: int  # epoch seconds of the bar's OPEN
    open: float
    high: float
    low: float
    close: float
    volume: float


class DayBar(NamedTuple):
    day: date
    open: float
    high: float
    low: float
    close: float
    volume: float


# --------------------------------------------------------------------- parsing


def _quote_rows(doc: Any) -> tuple[list[Any], dict[str, Any], dict[str, Any]]:
    try:
        res = (doc or {})["chart"]["result"][0]
    except (KeyError, IndexError, TypeError):
        return [], {}, {}
    if not isinstance(res, dict):
        return [], {}, {}
    try:
        q = ((res.get("indicators") or {}).get("quote") or [{}])[0] or {}
    except (IndexError, TypeError, AttributeError):
        q = {}
    return list(res.get("timestamp") or []), res.get("meta") or {}, q


def parse_chart(doc: Any, step: int = 0) -> tuple[list[Bar], dict[str, Any]]:
    """A Yahoo v8 chart response (5m, extended) → bars on the 5-minute grid. Pure.

    `step` is the grid in seconds — the 5-minute default, or 60 for the chart's
    one-minute download.

    THE LAST BAR IS NOT ON THE GRID. Yahoo stamps the live bar with the time of
    its last trade (05:38:51), so every stamp is floored to five minutes, and a
    bar that floors onto its predecessor's bucket is merged into it. Rows with a
    null price are holes in the tape (no trade) and are dropped, never zeroed.
    """
    ts, meta, q = _quote_rows(doc)
    step = step or SRC_SEC
    opens, highs, lows = q.get("open") or [], q.get("high") or [], q.get("low") or []
    closes, vols = q.get("close") or [], q.get("volume") or []
    bars: list[Bar] = []
    for i, t in enumerate(ts):
        try:
            o, h, lo, c = opens[i], highs[i], lows[i], closes[i]
            v = vols[i] if i < len(vols) else None
        except IndexError:
            continue
        if o is None or h is None or lo is None or c is None:
            continue
        k = int(t) - int(t) % step
        b = Bar(k, float(o), float(h), float(lo), float(c), float(v or 0.0))
        if bars and bars[-1].t == k:
            p = bars[-1]
            bars[-1] = Bar(k, p.open, max(p.high, b.high), min(p.low, b.low), b.close,
                           p.volume + b.volume)
        elif not bars or k > bars[-1].t:
            bars.append(b)
    return within_day(bars, meta, step), meta


def within_day(bars: list[Bar], meta: dict[str, Any], step: int = SRC_SEC) -> list[Bar]:
    """The bars, with no regular-session bar of the chart's own day reaching past
    that day's official high and low. Pure.

    A STRAY PRINT IS NOT A TRADE (audit, 2026-11-11). On Tue 10 Nov six of forty
    names carried a 13:00 bar whose high was exactly the previous close: MSFT's
    read 545.18 on a day whose high was 544.15, with the stock at 530. Left in, it
    is the day's high (and tomorrow's PDH), and a wick back through a broken level
    is what the retest test looks for. The chart's own `regularMarketDayHigh` and
    `regularMarketDayLow` are the day's official range as of the quote, so a bar of
    that session that ended before the quote cannot have traded outside it; its
    wicks are brought in to the range (never past its own open and close). The
    newest bar is left alone while the session is on: it can hold a trade the
    quote has not caught up with. Pre-market and after-hours bars are not touched;
    the official range is the regular session's.
    """
    hi, lo, at = (meta.get("regularMarketDayHigh"), meta.get("regularMarketDayLow"),
                  meta.get("regularMarketTime"))
    if not (isinstance(hi, (int, float)) and isinstance(lo, (int, float))
            and isinstance(at, (int, float)) and hi >= lo > 0):
        return bars
    quote = datetime.fromtimestamp(int(at), ET)
    day = quote.date()
    start = int(datetime(day.year, day.month, day.day, tzinfo=ET).timestamp())
    first, last = start + RTH_START * 60, start + rth_end(day) * 60
    closed = int(at) >= last
    out: list[Bar] = []
    for b in bars:
        inside = first <= b.t < last and (closed or b.t + step <= int(at) - 60)
        if inside and (b.high > hi or b.low < lo):
            top, bottom = max(b.open, b.close), min(b.open, b.close)
            b = Bar(b.t, b.open, max(min(b.high, hi), top), min(max(b.low, lo), bottom), b.close,
                    b.volume)
        out.append(b)
    return out


def parse_daily(doc: Any) -> list[DayBar]:
    """A Yahoo v8 chart response (1d) → daily bars keyed by their ET date. Pure."""
    ts, _meta, q = _quote_rows(doc)
    out: list[DayBar] = []
    opens, highs, lows = q.get("open") or [], q.get("high") or [], q.get("low") or []
    closes, vols = q.get("close") or [], q.get("volume") or []
    for i, t in enumerate(ts):
        try:
            o, h, lo, c = opens[i], highs[i], lows[i], closes[i]
            v = vols[i] if i < len(vols) else None
        except IndexError:
            continue
        if o is None or h is None or lo is None or c is None:
            continue
        d = datetime.fromtimestamp(int(t), ET).date()
        row = DayBar(d, float(o), float(h), float(lo), float(c), float(v or 0.0))
        if out and out[-1].day == d:
            out[-1] = row
        else:
            out.append(row)
    return out


def with_live(bars: list[Bar], price: float, at: int) -> list[Bar]:
    """The bars with one live trade laid over the newest. Pure.

    A TRADE, NOT A BAR (owner, 2026-10-14: the session "as close to real time as
    possible"). Between two bar downloads the live layer (sources/scanner.py)
    knows where a name last traded and when. Laid over the five-minute bucket
    it falls in, that trade moves the bucket's close and stretches its high or
    low; past the newest bar it opens the next bucket. Every figure read off the
    close — % change, RS, level progress, trend — then reads the live price by
    the same arithmetic as before. Volume stays with the bars: a trade carries
    none here, and Yahoo's day volume counts ~20% more than its bars do
    (measured 2026-10-14), so mixing the two would make the column jump.

    A trade older than the newest bar is already inside it and changes nothing.
    """
    if not bars:
        return bars
    k = at - at % SRC_SEC
    last = bars[-1]
    if k < last.t:
        return bars
    if k == last.t:
        return [*bars[:-1], Bar(k, last.open, max(last.high, price), min(last.low, price), price,
                                last.volume)]
    return [*bars, Bar(k, price, price, price, price, 0.0)]


# ----------------------------------------------------------------------- clock


@dataclass(frozen=True)
class Clock:
    now: datetime  # ET
    session: str  # "pre" | "rth" | "post" | "closed"
    trading_day: date  # the day the levels are FOR
    pm_locked: bool  # PMH/PML final: now ≥ 09:30 of trading_day


def _mod(dt: datetime) -> int:
    return dt.hour * 60 + dt.minute


def clock_at(now: datetime) -> Clock:
    """Which session it is and which day's levels to show. Pure.

    04:00–20:00 on a trading day is that day (04:00–17:00 on a half day, whose
    regular session ends at 13:00). After that, weekends and NYSE holidays
    belong to the next trading day; 00:00–03:59 already belongs to the session
    that opens at 04:00.

    HOLIDAYS COME FROM THE NYSE'S TABLE (holidays.py), not the tape. This used
    to infer one from "no SPY print by 04:30", which read the first half hour of
    every holiday as a pre-market (review, 2026-10-13) — and a published fact
    has no business being guessed at.
    """
    now = now.astimezone(ET)
    m = _mod(now)
    d = now.date()
    if is_trading_day(d) and m < post_end(d):
        td = d
        if m < PM_START:
            session = "closed"
        elif m < RTH_START:
            session = "pre"
        elif m < rth_end(d):
            session = "rth"
        else:
            session = "post"
    else:
        td = next_trading_day(d)
        session = "closed"
    return Clock(now, session, td, td == d and m >= RTH_START and session != "closed")


# -------------------------------------------------------------------- indicators


def resample(bars: list[Bar], step: int = BAR_SEC) -> list[Bar]:
    """5-minute bars → `step`-second bars on the epoch grid (:00/:10/… in ET). Pure."""
    out: list[Bar] = []
    for b in bars:
        k = b.t - b.t % step
        if out and out[-1].t == k:
            p = out[-1]
            out[-1] = Bar(k, p.open, max(p.high, b.high), min(p.low, b.low), b.close,
                          p.volume + b.volume)
        else:
            out.append(Bar(k, b.open, b.high, b.low, b.close, b.volume))
    return out


def ema(xs: list[float], n: int) -> list[float]:
    """Pine's ta.ema: seeded with the first value, alpha = 2 / (n + 1). Pure."""
    alpha = 2.0 / (n + 1)
    out: list[float] = []
    e: float | None = None
    for x in xs:
        e = x if e is None else alpha * x + (1 - alpha) * e
        out.append(e)
    return out


def atr(bars: list[Bar], n: int = ATR_LEN,
        sessions: dict[int, date] | None = None) -> list[float | None]:
    """Pine's ta.atr: RMA of the true range, seeded with the SMA of the first n. Pure.

    `sessions` (`rth_bar_days`) keeps it to the regular session, which is what the
    scanner's ten-minute ATR is since the quant audit (2026-11-13; owner: "fix
    everything"). Run over every bar, the free feed's thin pre-market bars and the
    04:00 bar's overnight gap set the 09:30 buffer: fourteen quiet pre-market bars
    shrank it, so the opening bars read "extended" and a near-miss retest missed, and
    a gap of a few percent in one true range swelled it for the next hour. With
    `sessions` only regular-session bars count, a session's first bar is its own high
    to low (the night's gap is the daily ATR's business), and every other bar carries
    the last session value forward, so the list still lines up with `bars`. The Pine
    script's chart ATR counts the extended bars when its chart shows them; this is the
    one place the port departs from it, on purpose.
    """
    out: list[float | None] = []
    trs: list[float] = []
    a: float | None = None
    prev: Bar | None = None
    prev_day: date | None = None
    for b in bars:
        day = sessions.get(b.t) if sessions is not None else None
        if sessions is not None and day is None:
            out.append(a)
            continue
        if prev is None or (sessions is not None and day != prev_day):
            tr = b.high - b.low
        else:
            pc = prev.close
            tr = max(b.high - b.low, abs(b.high - pc), abs(b.low - pc))
        prev, prev_day = b, day
        trs.append(tr)
        if a is None:
            if len(trs) >= n:
                a = sum(trs[-n:]) / n
        else:
            a = (a * (n - 1) + tr) / n
        out.append(a)
    return out


def rth_bar_days(bars5: list[Bar], days: list[date] | None = None,
                 mods: list[int] | None = None, step: int = BAR_SEC) -> dict[int, date]:
    """Each regular-session `step` bar's start → its trading day, for `atr`. `days` and
    `mods` are the bars' ET dates and minutes when the caller has them. Pure."""
    if days is None or mods is None:
        stamps = [datetime.fromtimestamp(b.t, ET) for b in bars5]
        days, mods = [s.date() for s in stamps], [_mod(s) for s in stamps]
    ends: dict[date, int] = {}
    out: dict[int, date] = {}
    for b, d, m in zip(bars5, days, mods, strict=True):
        end = ends.get(d)
        if end is None:
            end = ends[d] = rth_end(d)
        if RTH_START <= m < end:
            out[b.t - b.t % step] = d
    return out


def daily_atr(days: list[DayBar], n: int = ATR_LEN) -> float | None:
    """The script's hand-kept daily ATR: seeded with the first true range, then
    `atr + (tr − atr) / 14` per completed regular session. Pure."""
    a: float | None = None
    prev: float | None = None
    for d in days:
        tr = d.high - d.low if prev is None else max(d.high, prev) - min(d.low, prev)
        a = tr if a is None else a + (tr - a) / n
        prev = d.close
    return a


def prog(c: float | None, hi: float | None, lo: float | None, toward_hi: bool) -> float | None:
    """Pine prog(): how far price has come from the opposite level toward this one. Pure."""
    if c is None or hi is None or lo is None or hi - lo <= 0:
        return None
    rng = hi - lo
    return (c - lo) / rng if toward_hi else (hi - c) / rng


def lvl_state_of(c: float | None, pdh: float | None, pdl: float | None,
                 pmh: float | None, pml: float | None) -> int:
    """Pine lvlState: +2 above PDH and PMH, +1 above one, −1/−2 below, 0 inside. Pure.

    `pmh`/`pml` must already be None until the pre-market is done (pmhLive)."""
    if c is None:
        return 0
    up = (1 if pdh is not None and c > pdh else 0) + (1 if pmh is not None and c > pmh else 0)
    dn = (1 if pdl is not None and c < pdl else 0) + (1 if pml is not None and c < pml else 0)
    if up > 0 and dn == 0:
        return up
    if dn > 0 and up == 0:
        return -dn
    return 0


def trend_of(c: float | None, pdh: float | None, pdl: float | None,
             pmh: float | None, pml: float | None) -> int:
    """Pine scanner trend: ▲ above PDH and PMH, ▼ below PDL and PML. Pure."""
    if c is None:
        return 0
    if pdh is not None and pmh is not None and c > pdh and c > pmh:
        return 1
    if pdl is not None and pml is not None and c < pdl and c < pml:
        return -1
    return 0


# ---------------------------------------------------------------- level replay


@dataclass
class Lvl:
    """Pine `type Lvl` — one level's breakout / retest state for the day."""

    name: str
    is_high: bool
    price: float | None
    broken: bool = False
    brk_bar: int | None = None
    armed: bool = False
    #: When it first broke today (bar open, epoch) and whether it broke by gap.
    broke_t: int | None = None
    gapped: bool = False
    #: Broke, then closed back through by more than the buffer — and has not
    #: re-broken since. `failed_t` is when, so the latest failure is the one named.
    failed: bool = False
    failed_t: int | None = None

    def step(self, i: int, first: bool, b: Bar, prev_close: float | None, buf: float,
             w_top: float, w_bot: float) -> tuple[bool, bool]:
        """Pine `method step` on one confirmed bar → (breakout, (L) retest)."""
        brk = rt = False
        lv = self.price
        if lv is None:
            return brk, rt
        s = 1.0 if self.is_high else -1.0
        ref = b.open if first or prev_close is None else prev_close
        if not self.broken:
            if s * (b.close - lv) > 0:
                self.broken = True
                self.brk_bar = i
                self.armed = True
                self.failed = False
                brk = s * (ref - lv) <= 0
                self.broke_t = b.t
                self.gapped = not brk
        elif s * (b.close - lv) < -buf:
            self.broken = False
            self.armed = False
            self.failed = True
            self.failed_t = b.t
        else:
            in_zone = s * ((b.low if self.is_high else b.high) - lv) <= buf
            wave_near = w_bot - buf <= lv <= w_top + buf
            if (self.armed and self.brk_bar is not None and i > self.brk_bar and in_zone
                    and wave_near and s * (b.close - lv) > 0):
                rt = True
                self.armed = False
            elif not in_zone:
                self.armed = True
        return brk, rt


def _hm(t: int) -> str:
    return datetime.fromtimestamp(t, ET).strftime("%H:%M")


def fmt_px(p: float | None) -> str:
    if p is None:
        return "—"
    return f"{p:.2f}" if abs(p) >= 1 else f"{p:.4f}"


@dataclass
class Replay:
    levels: dict[str, Lvl]
    signals: list[dict[str, Any]] = field(default_factory=list)


#: The charts the signals are read on (owner, 2026-11-19: "it should print signals ... if
#: it happens on 3m, 5m and 10m"), and each one's bar in seconds. 10m is the Pine script's
#: own; 5m runs on the store's 5-minute bars as they are; 3m on its 1-minute bars.
TF_SEC: dict[str, int] = {"3m": 180, "5m": 300, "10m": 600}


def replay(bars10: list[Bar], rth_ix: list[int], forming: int | None, levels: dict[str, Lvl],
           atr10: list[float | None], w_top: list[float], w_bot: list[float],
           pmh_live: float | None, pml_live: float | None,
           vwap: list[float | None] | None = None, unit: list[float | None] | None = None,
           tf: str = "10m") -> Replay:
    """Today's (L) / (E) / (V) / breakout signals over confirmed regular-session bars.

    `rth_ix` are the CONFIRMED regular-session bars of the trading day, in order,
    as indices into `bars10` (so the EMA wave, the ATR and the previous close are
    the script's own series values at that bar). `forming` is the still-open
    bar, if any: levels never step on it — the script only steps confirmed bars —
    but an (E) trigger can fire on it, because a high only rises inside a bar.

    ANY TIMEFRAME (2026-11-19). `bars10` may be 3-, 5- or 10-minute bars; `atr10` is then
    that chart's ATR, which sets its retest buffer and stop floor, as the Pine script
    does on whatever chart it is put on. `tf` names the chart on every signal.

    THE EMA AND VWAP ENTRIES ARE FOR AN EXTENDED RUN ONLY (owner, 2026-11-19: "break of a
    pmh or pml and then a retest of the level or if price is really extended, then retest
    of the ema or vwap"). A side is EXTENDED from the bar whose close is more than
    EXT_ATR ten-minute ATRs past the nearest broken level on its side (`unit`, the 10-min
    ATR in force at each bar; `atr10` when None) — the line the setup's state already
    draws (`setup_state`). It stays extended until price comes back to that level (a bar
    within the buffer of it: the level is the entry again) or loses its levels. Only
    while it was extended at the bar before can an (E) candle be set or a (V) fire:
      (E)  a pullback into the 8/9/10 EMA wave, then a break of that candle (the Pine's
           own mechanics; it fired on any pullback before this rule);
      (V)  a retest of VWAP (`vwap`, the session's at each bar's close): armed once a
           bar is clear of it, fired on a bar that comes back within the buffer and
           closes on the far side, the bar's low (high) the stop idea, like the (L).
    """
    out = Replay(levels)
    pdh, pdl = levels["PDH"].price, levels["PDL"].price
    e_bar: dict[str, int | None] = {"long": None, "short": None}
    e_trg: dict[str, float] = {"long": 0.0, "short": 0.0}
    e_stp: dict[str, float] = {"long": 0.0, "short": 0.0}
    e_arm: dict[str, bool] = {"long": False, "short": False}
    ext: dict[str, bool] = {"long": False, "short": False}
    ext_lv: dict[str, str] = {"long": "", "short": ""}
    v_arm: dict[str, bool] = {"long": False, "short": False}

    def sig(kind: str, side: str, level: str | None, t: int, price: float, note: str,
            stop: float | None = None, floor: float | None = None) -> None:
        # `t` (the bar's open, epoch) and `stop` (the script's "stop idea") ride
        # along for the event log and the chart; the row's own readers ignore them.
        # `risk_min` is the least a stop's distance is counted as (`risk_of`).
        out.signals.append({"kind": kind, "side": side, "level": level, "at_et": _hm(t),
                            "price": round(price, 4), "note": note, "t": t,
                            "stop": round(stop, 4) if stop is not None else None,
                            "risk_min": round(floor, 4) if floor else None, "tf": tf})

    for n, i in enumerate(rth_ix):
        b = bars10[i]
        first = n == 0
        prev_close = bars10[i - 1].close if i > 0 else None
        buf = (atr10[i] or 0.0) * BUF_MULT
        wt, wb = w_top[i], w_bot[i]
        state = lvl_state_of(b.close, pdh, pdl, pmh_live, pml_live)

        res: dict[str, tuple[bool, bool]] = {}
        for key in ("PDH", "PMH", "PDL", "PML"):
            res[key] = levels[key].step(i, first, b, prev_close, buf, wt, wb)
        for key in ("PDH", "PMH", "PDL", "PML"):
            if res[key][0]:
                hi = levels[key].is_high
                sig("BO", "long" if hi else "short", key, b.t, levels[key].price or b.close,
                    f"{'Breakout above' if hi else 'Breakdown below'} {key} "
                    f"{fmt_px(levels[key].price)}")

        ok_l, ok_s = state > 0, state < 0
        # THE EXTENSION (docstring): read on this bar's close, used from the next bar.
        was = dict(ext)
        u = (unit[i] if unit is not None else atr10[i]) or 0.0
        for side, ok, keys in (("long", ok_l, ("PDH", "PMH")), ("short", ok_s, ("PDL", "PML"))):
            s = 1.0 if side == "long" else -1.0
            held: list[tuple[str, float]] = []
            for k in keys:
                p = levels[k].price
                if levels[k].broken and p is not None and s * (b.close - p) > 0:
                    held.append((k, p))
            if not ok or not held:
                ext[side] = False
                continue
            k, ref = (max if side == "long" else min)(held, key=lambda x: x[1])
            if s * ((b.low if side == "long" else b.high) - ref) <= buf:
                ext[side] = False  # back at the level: the level is the entry again
            elif u > 0 and s * (b.close - ref) > EXT_ATR * u:
                ext[side], ext_lv[side] = True, k

        l_long = ok_l and (res["PDH"][1] or res["PMH"][1])
        l_short = ok_s and (res["PDL"][1] or res["PML"][1])
        if l_long:
            lv = "PDH" if res["PDH"][1] else "PMH"
            sig("L", "long", lv, b.t, b.close,
                f"Retest of {lv} {fmt_px(levels[lv].price)} with the 8 EMA wave at the level"
                f" · stop idea below {fmt_px(b.low)}", stop=b.low, floor=buf)
        if l_short:
            lv = "PDL" if res["PDL"][1] else "PML"
            sig("L", "short", lv, b.t, b.close,
                f"Retest of {lv} {fmt_px(levels[lv].price)} with the 8 EMA wave at the level"
                f" · stop idea above {fmt_px(b.high)}", stop=b.high, floor=buf)

        # ---- (V): the VWAP retest after an extended run (docstring) -------------
        vw = vwap[i] if vwap is not None else None
        if vw is not None:
            for side, ok, fired in (("long", ok_l, l_long), ("short", ok_s, l_short)):
                s = 1.0 if side == "long" else -1.0
                zone = s * ((b.low if side == "long" else b.high) - vw) <= buf
                if s * (b.close - vw) < -buf:
                    v_arm[side] = False  # lost VWAP: armed again only once clear of it
                elif v_arm[side] and was[side] and ok and not fired and zone \
                        and s * (b.close - vw) > 0:
                    v_stop = b.low if side == "long" else b.high
                    word = "below" if side == "long" else "above"
                    sig("V", side, "VWAP", b.t, b.close,
                        f"Retest of VWAP {fmt_px(vw)} after a run of {EXT_ATR:g}+ ATR past "
                        f"{ext_lv[side] or 'the level'} · stop idea {word} {fmt_px(v_stop)}",
                        stop=v_stop, floor=buf)
                    v_arm[side] = False
                elif not zone:
                    v_arm[side] = True

        conf = {"long": False, "short": False}
        for side in ("long", "short"):
            eb = e_bar[side]
            if eb is None or i <= eb:
                continue
            hit = b.high > e_trg[side] if side == "long" else b.low < e_trg[side]
            if hit:
                conf[side] = True
                word = "above" if side == "long" else "below"
                stop = "below" if side == "long" else "above"
                sig("E", side, None, b.t, e_trg[side],
                    f"Broke {word} the (E) candle {fmt_px(e_trg[side])}"
                    f" · stop idea {stop} {fmt_px(e_stp[side])}", stop=e_stp[side], floor=buf)
                e_bar[side] = None

        # ---- the sigBar block ------------------------------------------------
        # A pending (E) also goes once the run is no longer extended: back at the level,
        # the (L) is the entry (the docstring's rule).
        if e_bar["long"] is not None and (state <= 0 or b.close < wb or not ext["long"]):
            e_bar["long"] = None
        if e_bar["short"] is not None and (state >= 0 or b.close > wt or not ext["short"]):
            e_bar["short"] = None
        if (ok_l and was["long"] and ext["long"] and e_arm["long"] and not conf["long"]
                and not l_long and b.low <= wt and b.close >= wb):
            e_bar["long"], e_trg["long"], e_stp["long"] = i, b.high, b.low
        if (ok_s and was["short"] and ext["short"] and e_arm["short"] and not conf["short"]
                and not l_short and b.high >= wb and b.close <= wt):
            e_bar["short"], e_trg["short"], e_stp["short"] = i, b.low, b.high
        e_arm["long"] = b.low > wt
        e_arm["short"] = b.high < wb

    # The forming bar can trigger a pending (E) — the script fires it intrabar.
    if forming is not None:
        b = bars10[forming]
        for side in ("long", "short"):
            eb = e_bar[side]
            if eb is None or forming <= eb:
                continue
            hit = b.high > e_trg[side] if side == "long" else b.low < e_trg[side]
            if hit:
                word = "above" if side == "long" else "below"
                sig("E", side, None, b.t, e_trg[side],
                    f"Broke {word} the (E) candle {fmt_px(e_trg[side])} (bar still open)",
                    stop=e_stp[side], floor=(atr10[forming] or 0.0) * BUF_MULT)
                e_bar[side] = None

    for side in ("long", "short"):
        eb = e_bar[side]
        if eb is not None:
            word = "above" if side == "long" else "below"
            stop = "below" if side == "long" else "above"
            sig("E_SETUP", side, None, bars10[eb].t, e_trg[side],
                f"(E) candle set — {side} triggers {word} {fmt_px(e_trg[side])}"
                f" · stop idea {stop} {fmt_px(e_stp[side])}", stop=e_stp[side])
    return out


# ------------------------------------------------------------------ technicals


@dataclass
class Tech:
    """One ticker's computed state — everything the scanner row needs except the
    parts that depend on other tickers (RS) or on the macro snapshot (score)."""

    ok: bool = False
    error: str | None = None
    name: str | None = None
    last: float | None = None
    prev_close: float | None = None
    chg_pct: float | None = None
    ext_pct: float | None = None
    volume: float | None = None
    rvol: float | None = None
    atr_d: float | None = None
    atr_b: float | None = None
    mv_day: float | None = None
    #: The move the side's lean reads: `mv_day`, or overnight the last session and
    #: after hours together (see where it is set).
    mv_lean: float | None = None
    mv_roll: float | None = None
    pdh: float | None = None
    pdl: float | None = None
    #: The same two from the 5-minute bars alone, for the page to compare (they
    #: miss the opening prints; `technicals` says how often).
    pdh_bars: float | None = None
    pdl_bars: float | None = None
    pdc: float | None = None
    pdh_day: date | None = None
    pmh: float | None = None
    pml: float | None = None
    #: The same two from the 5-minute bars alone, for the page to compare: on a day the
    #: bars start late they stop short of the range (`technicals`, `pm_wide`).
    pmh_bars: float | None = None
    pml_bars: float | None = None
    pm_done: bool = False
    vwap: float | None = None
    wave_hi: float | None = None
    wave_lo: float | None = None
    ema8: float | None = None
    #: The ten-minute 200 EMA — the side filter (structure.py, 2026-10-30).
    ema200: float | None = None
    ema200_slope: str | None = None
    trend200: int = 0
    day_hi: float | None = None
    day_lo: float | None = None
    open: float | None = None
    #: The open is the daily bar's (the official print), not the first 5-minute bar's.
    open_official: bool = False
    rth_today: bool = False
    #: The latest 10-minute bar's low/high (forming or not) — the retest zone test.
    bar_low: float | None = None
    bar_high: float | None = None
    levels: dict[str, Lvl] = field(default_factory=dict)
    signals: list[dict[str, Any]] = field(default_factory=list)
    #: The same signals read on the 3- and 5-minute charts (2026-11-19), each with its
    #: `tf`. Apart from `signals`, which stays the ten-minute chart's: the score, the
    #: record line and the contract helper read that one, as they always have.
    signals_fast: list[dict[str, Any]] = field(default_factory=list)
    #: Where each fast chart's bars are final, like `final_to` for the 10m.
    final_to_tf: dict[str, int | None] = field(default_factory=dict)
    lvl_state: int = 0
    trend: int = 0
    progress: dict[str, float | None] = field(default_factory=dict)
    broken: dict[str, bool] = field(default_factory=dict)
    range_used: float | None = None
    #: Epoch up to which the ten-minute bars are FINAL in this download — the
    #: newest confirmed bar's close. A logged signal on a bar that ends at or
    #: before it can be checked against these bars (scanlog.revalidate).
    final_to: int | None = None


def official_close(meta: dict[str, Any] | None) -> tuple[date, float] | None:
    """The chart's own regular-session close, once there is one. Pure.

    After 16:00 Yahoo's `regularMarketPrice` is the official close (auction
    included) and `regularMarketTime` says which day it closed; during the session
    it is just the last trade, which is no close at all.
    """
    if not meta:
        return None
    t, p = meta.get("regularMarketTime"), meta.get("regularMarketPrice")
    if t is None or p is None:
        return None
    dt = datetime.fromtimestamp(int(t), ET)
    return (dt.date(), float(p)) if _mod(dt) >= rth_end(dt.date()) else None


def day_volume(bars_vol: float | None, meta: dict[str, Any] | None,
               trading_day: date) -> float | None:
    """Today's volume as the tape counts it: the chart's own consolidated figure for
    the trading day's regular session, or the bars' sum where that is larger. Pure.

    THE BARS UNDERCOUNT (quant audit, 2026-11-13; owner: "fix everything"). Yahoo's
    5-minute bars miss a fifth to two fifths of a day's shares (META on 12 Nov: 8.09M
    in the bars against 10.25M on the tape), and the share of an average day divided
    them by the daily rows' full count, so every name read light: a normal day showed
    about 75%. `regularMarketVolume` is the tape's count as of the download; it is the
    previous session's until today's first regular trade (`regularMarketTime`), so it
    is used only once that is today's. Each is a floor on the truth, hence the larger.
    RVOL is not this: it divides the bars by the bars (`technicals`), like for like.
    """
    if meta:
        v, t = meta.get("regularMarketVolume"), meta.get("regularMarketTime")
        if isinstance(v, int | float) and v > 0 and isinstance(t, int | float):
            dt = datetime.fromtimestamp(int(t), ET)
            if dt.date() == trading_day and _mod(dt) >= RTH_START:
                return max(float(v), bars_vol or 0.0)
    return bars_vol


def official_range(day: DayBar | None, hi: float, lo: float) -> tuple[float, float]:
    """A session still trading: the 5-minute bars' high and low (`hi`, `lo`), widened
    to the daily row's where that reaches further. The row is a copy from earlier in
    the session, so it can add what the bars missed and cannot stand for the range
    by itself. A FINISHED session's range is its settled daily bar outright (see
    `technicals`). Pure."""
    if day is None:
        return hi, lo
    return max(hi, day.high), min(lo, day.low)


def daily_row(rows: dict[date, DayBar], d: date, daily_asof: float | None, today_cal: date,
              after_min: int | None = None, slack: float = DAILY_SETTLE_SEC) -> DayBar | None:
    """The daily copy's row for session `d`, when the copy can be trusted for it:
    downloaded `slack` seconds past minute `after_min` of that day (its close by
    default, so the row is the finished bar). With no download time known, any day
    before the calendar date `today_cal`. Else None. Pure."""
    row = rows.get(d)
    # A row that is not a bar (a high under its low, a zero) is no evidence of anything.
    if row is None or not row.high >= row.low > 0:
        return None
    if daily_asof is None:
        return row if d < today_cal else None
    minute = rth_end(d) if after_min is None else after_min
    mark = datetime(d.year, d.month, d.day, tzinfo=ET).timestamp() + minute * 60
    return row if daily_asof >= mark + slack else None


def _vwap(bars: list[Bar]) -> float | None:
    pv = sum((b.high + b.low + b.close) / 3.0 * b.volume for b in bars)
    v = sum(b.volume for b in bars)
    return pv / v if v > 0 else None


def vwap_series(bars: list[Bar], idx: list[int]) -> list[float | None]:
    """The session's VWAP as of each bar's close, over the bars at `idx` (today's regular
    session, in order); None at every other bar. Pure."""
    out: list[float | None] = [None] * len(bars)
    pv = v = 0.0
    for k in idx:
        b = bars[k]
        if b.volume > 0:
            pv += (b.high + b.low + b.close) / 3.0 * b.volume
            v += b.volume
        out[k] = pv / v if v > 0 else None
    return out


#: The bars a fast chart's replay reads back: enough for the wave to settle and for the
#: previous session's regular bars to seed its ATR, not the store's twelve days.
FAST_SPAN_SEC = 3 * 86400


def tf_replay(src: list[Bar], tf: str, td: date, td_end: int,
              prices: tuple[float | None, float | None, float | None, float | None],
              final_ts: float, unit10: dict[int, float | None]
              ) -> tuple[list[dict[str, Any]], int | None]:
    """One faster chart's signals for the trading day `td`, and where its bars are final.
    Pure.

    `src` are the bars it is built from (5-minute bars for the 5m, 1-minute for the 3m);
    `prices` the day's PDH, PDL, PMH and PML as the row has them (PMH/PML None until the
    pre-market is done), so every chart breaks and retests the same levels. The wave and
    the ATR are the chart's own; "extended" is measured in the ten-minute ATR of the last
    finished ten-minute bar (`unit10`, by bar start), so it means one thing on every chart."""
    step = TF_SEC[tf]
    if not src:
        return [], None
    cut = src[-1].t - FAST_SPAN_SEC
    bars = resample([b for b in src if b.t >= cut], step)
    if not bars:
        return [], None
    stamps = [datetime.fromtimestamp(b.t, ET) for b in bars]
    rth = [k for k, s in enumerate(stamps) if s.date() == td and RTH_START <= _mod(s) < td_end]
    if not rth:
        return [], None
    closes = [b.close for b in bars]
    e1, e2, e3 = ema(closes, WAVE_LEN), ema(closes, WAVE_LEN + 1), ema(closes, WAVE_LEN + 2)
    w_top = [max(a, b, c) for a, b, c in zip(e1, e2, e3, strict=True)]
    w_bot = [min(a, b, c) for a, b, c in zip(e1, e2, e3, strict=True)]
    a_tf = atr(bars, sessions=rth_bar_days(bars, [s.date() for s in stamps],
                                           [_mod(s) for s in stamps], step=step))
    confirmed = [k for k in rth if bars[k].t + step <= final_ts]
    pending = [k for k in rth if bars[k].t + step > final_ts]
    pdh, pdl, pmh, pml = prices
    levels = {"PDH": Lvl("PDH", True, pdh), "PDL": Lvl("PDL", False, pdl),
              "PMH": Lvl("PMH", True, pmh), "PML": Lvl("PML", False, pml)}
    unit = [unit10.get(b.t - b.t % BAR_SEC - BAR_SEC) for b in bars]
    rp = replay(bars, confirmed, pending[0] if pending else None, levels, a_tf, w_top, w_bot,
                pmh, pml, vwap=vwap_series(bars, rth), unit=unit, tf=tf)
    return rp.signals, (bars[confirmed[-1]].t + step if confirmed else None)


def technicals(bars5: list[Bar], daily: list[DayBar], clock: Clock,
               name: str | None = None, official: tuple[date, float] | None = None,
               asof: float | None = None, daily_asof: float | None = None,
               pm_wide: tuple[float | None, float | None] | None = None,
               bars1: list[Bar] | None = None, asof1: float | None = None) -> Tech:
    """Everything the script computes for one symbol, as of `clock.now`. Pure.

    `bars1` are the name's one-minute bars, when held, for the 3m chart's signals, and
    `asof1` when they were downloaded (the same rule as `asof`). Without them there are
    no 3m signals, and `final_to_tf` says so (None), so nothing logged is withdrawn.

    `pm_wide` is the trading day's pre-market (high, low) from a read other than
    these bars, or None: PMH and PML take whichever reaches further (see where
    they are set). A fact about today, like `official`: None when replaying a past
    day.

    Bars that OPEN after `clock.now` are ignored, so the same function replays
    any past instant from a later download — which is how the boundary table in
    tools/scan_probe.py is produced. `official` is `official_close(meta)`;
    pass None when replaying the past, since it is a fact about now.

    `asof` is when `bars5` were downloaded (epoch). A ten-minute bar is
    confirmed — levels step on it, an (L) or a breakout can fire on it — only
    once it closed CLOSE_LAG_SEC before that download; until then it is still
    the forming bar, whatever the clock says. None (a replay from a later
    download) confirms by the clock alone.

    `daily_asof` is when `daily` was downloaded (epoch). A session's daily row is
    read for its high, low and open only from a copy made after the fact: a
    quarter hour past that session's close for the previous day's range, a minute
    past 09:30 for today's open. Unknown (a replay, a test) trusts every day before
    the calendar date, the rule the previous close already goes by.
    """
    tech = Tech(name=name)
    now_ts = int(clock.now.timestamp())
    bars = [b for b in bars5 if b.t < now_ts]
    if not bars:
        tech.error = "no bars"
        return tech

    stamps = [datetime.fromtimestamp(b.t, ET) for b in bars]
    days = [s.date() for s in stamps]
    mods = [_mod(s) for s in stamps]
    td = clock.trading_day

    by_day: dict[date, list[int]] = {}
    for i, d in enumerate(days):
        by_day.setdefault(d, []).append(i)

    def rth_of(d: date) -> list[int]:
        end = rth_end(d)
        return [i for i in by_day.get(d, []) if RTH_START <= mods[i] < end]

    # THE CLOSE IS THE OFFICIAL ONE, NOT THE LAST 5-MINUTE BAR'S. Yahoo's 15:55
    # bar ends before the closing auction, so its close missed the official
    # print by 9–11 cents on AAPL and NVDA on 2026-10-12 — and the script's
    # dCl, read off TradingView's bars, includes the auction. pdc carries every
    # % change and RS Today, so it takes the chart's official close for its day,
    # else the daily bar's close for a day already over (the store refetches the
    # daily bars after every close, so those are final), else the bar.
    # PDH/PDL stay on the 5m bars: they already match the script's to the cent.
    daily_close = {d.day: d.close for d in daily}
    today_cal = clock.now.astimezone(ET).date()

    def close_of(d: date, fallback: float) -> float:
        if official is not None and official[0] == d:
            return official[1]
        if d < today_cal and d in daily_close:
            return daily_close[d]
        return fallback

    # PDH AND PDL ARE THE OFFICIAL DAY'S, NOT THE 5-MINUTE BARS' ALONE (audit,
    # 2026-11-11). Yahoo's 5-minute bars leave out the opening cross and the first
    # prints after the bell, and a session's high or low is often made right there:
    # over 440 name-sessions (forty names, 26 Oct to 9 Nov) the bars' high sat under
    # the daily bar's by more than 5c on 23 and their low over it on 31, never the
    # other way. AVGO's high on 6 Nov was 311.52 and the bars said 306.20, so on
    # Monday the list called it through a PDH it had not reached. Yahoo's daily bar
    # agreed with TradingView's to the cent on all 37 names checked for 9 Nov, and it
    # is the bar a chart draws the level from. So once the daily copy holds that
    # session's FINISHED bar (`daily_row`), the range is that bar's, outright. Not
    # whichever reaches further: the bars also carry strays the day never traded
    # (`within_day`; MSFT's 545.18 on 10 Nov would have been Wednesday's PDH).
    # Until then, the 5-minute bars. `pdh_bars` / `pdl_bars` keep their figures so
    # the page can say when the two disagree.
    daily_bar = {d.day: d for d in daily}

    def day_row(d: date, after_min: int, slack: float) -> DayBar | None:
        return daily_row(daily_bar, d, daily_asof, today_cal, after_min, slack)

    prior = [d for d in sorted(by_day) if d < td and rth_of(d)]
    d1 = prior[-1] if prior else None
    d2 = prior[-2] if len(prior) > 1 else None
    if d1 is not None:
        r1 = rth_of(d1)
        tech.pdh_bars = max(bars[i].high for i in r1)
        tech.pdl_bars = min(bars[i].low for i in r1)
        done = day_row(d1, rth_end(d1), DAILY_SETTLE_SEC)
        tech.pdh, tech.pdl = ((done.high, done.low) if done is not None
                              else (tech.pdh_bars, tech.pdl_bars))
        tech.pdc = close_of(d1, bars[r1[-1]].close)
        tech.pdh_day = d1
    ppdc = close_of(d2, bars[rth_of(d2)[-1]].close) if d2 is not None else None
    tech.prev_close = tech.pdc

    today = by_day.get(td, [])
    pm = [i for i in today if PM_START <= mods[i] < RTH_START]
    if pm:
        tech.pmh = max(bars[i].high for i in pm)
        tech.pml = min(bars[i].low for i in pm)
    tech.pmh_bars, tech.pml_bars = tech.pmh, tech.pml
    # THE PRE-MARKET RANGE IS THE WIDER OF THE BARS' AND A SECOND READ'S (2026-11-11).
    # On Wed 11 Nov Yahoo had no pre-market bar before 05:20 ET for any Nasdaq-listed
    # name (26 of the 34 on the list; the NYSE names and every earlier session began at
    # 04:00), so PMH and PML were the high and low of what was left: NVDA's low read
    # 177.02 against a pre-market low of 172.66, SNDK's 931.00 against 905.37, MU's
    # 768.36 against 758.88. Those are the levels the strategy trades. `pm_wide` is
    # today's pre-market high and low from a read that is not these bars (Nasdaq's, or
    # the wide scan's screener: the caller's `ScanStore.pm_wide`); the level is
    # whichever reaches further, so a short download cannot narrow the range and a
    # late screener (it runs fifteen minutes behind) cannot either. On the five NYSE
    # names whose bars were whole that morning the screener was never the wider one.
    if pm_wide is not None:
        hi, lo = pm_wide
        if hi is not None and hi > 0 and (tech.pmh is None or hi > tech.pmh):
            tech.pmh = hi
        if lo is not None and lo > 0 and (tech.pml is None or lo < tech.pml):
            tech.pml = lo
    tech.pm_done = clock.pm_locked
    td_end = rth_end(td)
    rth = [i for i in today if RTH_START <= mods[i] < td_end]
    tech.rth_today = bool(rth)
    d_cl: float | None = None
    if rth:
        # Today's range and open by the same rule. THE OPEN IS THE DAILY BAR'S ONCE
        # IT IS HELD: the first 5-minute bar's open is the first trade Yahoo's bars
        # caught, which on those 440 name-sessions was more than 0.10% from the
        # official open on 96 of them (MU on 10 Nov: 710.82 against 717.37, a gap
        # read as -3.05% that was -2.15%). The store fetches the daily bars again
        # just after the bell for it (sources/scanner.open_marks).
        today_bar = day_row(td, RTH_START, DAILY_OPEN_SEC)
        tech.day_hi, tech.day_lo = official_range(
            today_bar, max(bars[i].high for i in rth), min(bars[i].low for i in rth))
        tech.open = today_bar.open if today_bar is not None else bars[rth[0]].open
        tech.open_official = today_bar is not None
        d_cl = bars[rth[-1]].close
        # Once the bell has rung, today's close is the official print too.
        if _mod(clock.now.astimezone(ET)) >= td_end:
            d_cl = close_of(td, d_cl)

    last = bars[-1].close
    tech.last = last
    pdc = tech.pdc
    # Pine regChg: the regular session against the previous close — and before
    # the open, still the previous session's own move.
    if rth and pdc:
        tech.chg_pct = (d_cl / pdc - 1.0) * 100.0 if d_cl is not None else None
    elif pdc and ppdc:
        tech.chg_pct = (pdc / ppdc - 1.0) * 100.0
    # Pine extChg: nothing during the regular session; pre-market against the
    # previous close, post-market against today's close.
    last_rth = days[-1] == td and RTH_START <= mods[-1] < td_end
    base = d_cl if rth else pdc
    if not last_rth and base:
        tech.ext_pct = (last / base - 1.0) * 100.0

    # Volume — every bar of the trading day, as volExt counts it; the pre-market
    # adds nothing because the free feed's pre-market bars are all zero.
    # Null rather than 0 before the bell: zero would claim nobody traded, when
    # the truth is the feed cannot say.
    if today:
        vol = sum(bars[i].volume for i in today)
        tech.volume = vol if vol > 0 else None
        tech.vwap = _vwap([bars[i] for i in rth]) if rth else None

    # RVOL by time of day: completed regular-session bars up to now, against the
    # same window on the RVOL_SESSIONS prior sessions in the download (two at
    # least) — the mean of them, as TradingView's is.
    if rth:
        now_mod = _mod(clock.now)
        cum_today = sum(bars[i].volume for i in rth if bars[i].t + SRC_SEC <= now_ts)
        priors: list[float] = []
        for d in sorted(by_day)[::-1]:
            if d >= td:
                continue
            cum = sum(bars[i].volume for i in rth_of(d) if mods[i] + SRC_SEC // 60 <= now_mod)
            if cum > 0:
                priors.append(cum)
            if len(priors) >= RVOL_SESSIONS:
                break
        if len(priors) >= 2 and cum_today > 0:
            tech.rvol = cum_today / (sum(priors) / len(priors))

    # ---- the 10-minute chart -------------------------------------------------
    bars10 = resample(bars)
    closes = [b.close for b in bars10]
    e1, e2, e3 = ema(closes, WAVE_LEN), ema(closes, WAVE_LEN + 1), ema(closes, WAVE_LEN + 2)
    w_top = [max(a, b, c) for a, b, c in zip(e1, e2, e3, strict=True)]
    w_bot = [min(a, b, c) for a, b, c in zip(e1, e2, e3, strict=True)]
    atr10 = atr(bars10, sessions=rth_bar_days(bars, days, mods))
    if bars10:
        tech.ema8, tech.wave_hi, tech.wave_lo = e1[-1], w_top[-1], w_bot[-1]
        e200 = structure.ema_read(closes)
        if e200:
            tech.ema200, tech.ema200_slope = e200["value"], e200["slope"]
        tech.atr_b = atr10[-1]
        tech.bar_low, tech.bar_high = bars10[-1].low, bars10[-1].high
        if len(bars10) > RS_BARS and tech.atr_b:
            tech.mv_roll = (closes[-1] - closes[-1 - RS_BARS]) / tech.atr_b

    # ---- the daily ATR, on completed sessions before the trading day ---------
    dl = [d for d in daily if d.day < td]
    if dl and d1 is not None and dl[-1].day == d1 and tech.pdh is not None \
            and tech.pdl is not None and pdc is not None:
        # The last completed session from the same bars the levels come from, so
        # the ATR's newest range is the PDH−PDL on screen.
        dl[-1] = DayBar(d1, dl[-1].open, tech.pdh, tech.pdl, pdc, dl[-1].volume)
    tech.atr_d = daily_atr(dl[-DAILY_ATR_SESSIONS:]) if dl else None
    if tech.atr_d and pdc is not None:
        tech.mv_day = (last - pdc) / tech.atr_d
    # THE MOVE A LEAN READS (lean_of): the day's, except overnight. From 20:00 to 04:00
    # and on a closed day the trading day has rolled, so `pdc` is the session just ended
    # and `mv_day` is the after-hours drift alone: META, the weekend of 14 Nov 2026, up
    # 2.9% on Friday and 0.2 ATR lower after hours with the whole market, read short.
    # Until the pre-market trades the lean reads the last session and after hours
    # together, from the close before. Over ten nights (884 names inside the session's
    # range at 21:00) nothing said which side the levels had a name on by 10:05 the next
    # morning: after hours alone 50%, the two together 52%, the old RS lean 44%. So this
    # is chosen to read as the row does, not for an edge; the gap takes over at 04:00,
    # as it does on the Scanner's own lists (scratchpad side_overnight.py).
    tech.mv_lean = tech.mv_day
    if tech.atr_d and ppdc and clock.session == "closed" and not rth:
        tech.mv_lean = (last - ppdc) / tech.atr_d

    # ---- levels against price ------------------------------------------------
    pmh_live = tech.pmh if tech.pm_done else None
    pml_live = tech.pml if tech.pm_done else None
    tech.lvl_state = lvl_state_of(last, tech.pdh, tech.pdl, pmh_live, pml_live)
    tech.trend = trend_of(last, tech.pdh, tech.pdl, pmh_live, pml_live)
    tech.trend200 = structure.trend_of_line(last, tech.ema200)
    tech.progress, tech.broken = _pairs(last, tech.pdh, tech.pdl, pmh_live, pml_live)
    if rth and tech.atr_d and tech.day_hi is not None and tech.day_lo is not None:
        tech.range_used = (tech.day_hi - tech.day_lo) / tech.atr_d

    # ---- today's signals -----------------------------------------------------
    levels = {
        "PDH": Lvl("PDH", True, tech.pdh),
        "PDL": Lvl("PDL", False, tech.pdl),
        # The script loads PMH/PML into the levels on the first bar the
        # pre-market is done — the 09:30 bar — before that bar steps.
        "PMH": Lvl("PMH", True, pmh_live),
        "PML": Lvl("PML", False, pml_live),
    }
    rth10 = [
        k for k, b in enumerate(bars10)
        if datetime.fromtimestamp(b.t, ET).date() == td
        and RTH_START <= _mod(datetime.fromtimestamp(b.t, ET)) < td_end
    ]
    # Confirmed: closed by the clock AND in a download read CLOSE_LAG_SEC after
    # its close (see the constant). A bar the clock has closed but the download
    # has not caught up with is still forming — and only the OLDEST such bar
    # forms, so a live trade laid on the next bucket cannot fire an (E) ahead
    # of the bar before it, which would log the same trigger twice.
    final_ts = now_ts if asof is None else min(now_ts, int(asof) - CLOSE_LAG_SEC)
    confirmed = [k for k in rth10 if bars10[k].t + BAR_SEC <= final_ts]
    pending = [k for k in rth10 if bars10[k].t + BAR_SEC > final_ts]
    forming = pending[0] if pending else None
    tech.final_to = bars10[confirmed[-1]].t + BAR_SEC if confirmed else None
    if rth10:
        rp = replay(bars10, confirmed, forming, levels, atr10, w_top, w_bot, pmh_live, pml_live,
                    vwap=vwap_series(bars10, rth10), tf="10m")
        tech.signals = rp.signals
        # THE SAME SIGNALS ON THE 5m AND 3m CHARTS (2026-11-19; TF_SEC). The same levels,
        # each chart's own wave and ATR; 3m only when the one-minute bars are held.
        unit10 = {b.t: a for b, a in zip(bars10, atr10, strict=True)}
        prices = (tech.pdh, tech.pdl, pmh_live, pml_live)
        fast, f5 = tf_replay(bars, "5m", td, td_end, prices, final_ts, unit10)
        tech.final_to_tf = {"5m": f5, "3m": None}
        if bars1:
            final1 = now_ts if asof1 is None else min(now_ts, int(asof1) - CLOSE_LAG_SEC)
            s3, f3 = tf_replay([b for b in bars1 if b.t < now_ts], "3m", td, td_end, prices,
                               final1, unit10)
            fast += s3
            tech.final_to_tf["3m"] = f3
        tech.signals_fast = sorted(fast, key=lambda s: (s["t"], TF_SEC.get(s["tf"], 0)))
    tech.levels = levels
    tech.ok = True
    return tech


def _session_of(day: date, m: int) -> str | None:
    """pre / rth / post for minute `m` of a trading day, None outside them."""
    if PM_START <= m < RTH_START:
        return "pre"
    if RTH_START <= m < rth_end(day):
        return "rth"
    if rth_end(day) <= m < post_end(day):
        return "post"
    return None


#: The chart's timeframes (owner instruction, 2026-10-14: "a toggle for the
#: time frames on the chart — 1m 3m 5m 10m D"), in seconds. 10m is the one the
#: script's signals are read on; the others are views of the same tape.
CHART_TF: dict[str, int] = {"1m": 60, "3m": 180, "5m": 300, "10m": 600, "30m": 1800,
                            "60m": 3600, "D": 86400}
#: The most bars an intraday chart ships — the pane draws at most about a
#: hundred, and the EMA is computed on everything before the cut regardless.
CHART_MAX = 400
#: Sessions on the daily chart.
CHART_DAYS = 90


#: The chart's other averages, beside the wave and the 200 (owner, 2026-11-11: "can we
#: add ema's for 20 and 50"). Drawn only when the reader picks them.
CHART_EMAS: tuple[int, ...] = (20, 50)


def _chart_emas(closes: list[float]) -> dict[int, list[float]]:
    """Each of CHART_EMAS over every close held, or an empty list where there are
    fewer closes than its length: a 50 EMA of thirty bars is not a 50 EMA. Pure."""
    return {n: ema(closes, n) if len(closes) >= n else [] for n in CHART_EMAS}


def _empty_chart(tf: str, error: str) -> dict[str, Any]:
    return {"ok": False, "tf": tf, "error": error, "bars": [], "ema8": [], "ema9": [],
            "ema10": [], "ema20": [], "ema50": [], "vwap": [], "vwap_sd": [], "levels": {},
            "history": [], "sessions": [], "signals": []}


def _at(d: date, minute: int) -> int:
    """Epoch seconds of `minute` past midnight on `d`, New York time."""
    return int(datetime(d.year, d.month, d.day, tzinfo=ET).timestamp()) + minute * 60


#: The bars before the first pre-market bar the slide-out chart opens on (ScanChart:
#: "today's pre-market and six bars of the evening before it").
SPARK_LEAD = 6
#: Its window with no pre-market in the last two days held: the newest eighty bars.
SPARK_FALLBACK = 80
#: The most points a spark carries: 04:00 to 20:00 is 192 five-minute bars, plus the lead.
SPARK_MAX = 200


def _day_of(t: int) -> date:
    return datetime.fromtimestamp(t, ET).date()


def spark_of(bars: list[Bar], now_ts: int, daily: list[DayBar] | None = None,
             daily_asof: float | None = None) -> tuple[list[float], float | None]:
    """(the small chart's closes, the last regular close before them). Pure.

    THE SPARK IS THE CHART'S OPENING VIEW (owner, 2026-11-18: "can we make sure sparks are
    accurate representations of the charts"). It was Yahoo's regular-session closes for
    the one day Yahoo calls current: before 09:30 that is yesterday, so at 09:20 LOW's
    line ran 224 to 220.46 while it traded 210.13, and no pre-market was ever drawn.
    Now it is the five-minute closes the slide-out chart frames when it opens: the bars
    before now (as `chart_series` cuts them), from the newest day with a pre-market bar,
    its first one less SPARK_LEAD, pre-market and after hours included. The chart's own
    fallback with no pre-market (the last eighty bars) is this one's too.

    The reference colours the line: green at or above the close before the day, as the
    % change beside it reads, not against the first point (the evening before's after
    hours, which on a report night is already the move). `daily` gives the official close
    once its copy has settled (`daily_row`, read with `daily_asof`); else the last
    regular-session bar's close."""
    n = bisect_left(bars, now_ts, key=lambda b: b.t)
    if n == 0:
        return [], None
    start: int | None = None
    i, days = n - 1, 0
    while i >= 0 and days < 2:
        d = _day_of(bars[i].t)
        lo = bisect_left(bars, _at(d, 0), hi=i + 1, key=lambda b: b.t)
        if _session_of(d, _mod(datetime.fromtimestamp(bars[lo].t, ET))) == "pre":
            start = lo
            break
        i, days = lo - 1, days + 1
    day = _day_of(bars[start].t) if start is not None else _day_of(bars[n - 1].t)
    first = start if start is not None else bisect_left(bars, _at(day, 0), hi=n,
                                                       key=lambda b: b.t)
    lo = max(0, start - SPARK_LEAD) if start is not None else max(0, n - SPARK_FALLBACK)
    pts = [round(b.close, 4) for b in bars[max(lo, n - SPARK_MAX):n]]
    ref: float | None = None
    if first > 0:
        # The session before, as the bars have it; its official close when the daily
        # copy holds that day finished.
        prev = _day_of(bars[first - 1].t)
        done = daily_row({x.day: x for x in daily or []}, prev, daily_asof, day)
        if done is not None:
            ref = done.close
        else:
            k = bisect_left(bars, _at(prev, rth_end(prev)), hi=first, key=lambda b: b.t) - 1
            if k >= 0 and bars[k].t >= _at(prev, RTH_START):
                ref = bars[k].close
    return pts, (round(ref, 4) if ref is not None else None)


def _levels_out(tech: Tech) -> dict[str, Any]:
    """The trading day's four levels with no start: the daily view's, lines across the
    days. An intraday view's come from `chart_levels`."""
    return {"pdh": _r(tech.pdh), "pdl": _r(tech.pdl), "pmh": _r(tech.pmh),
            "pml": _r(tech.pml), "pm_done": tech.pm_done,
            "pd_from": None, "pm_from": None, "day": None}


def day_sets(bars5: list[Bar], daily: list[DayBar] | None = None,
             daily_asof: float | None = None,
             today_cal: date | None = None) -> dict[date, dict[str, float]]:
    """Every day's four levels off the bars, {day: {"PDH", "PDL", "PMH", "PML"}}: its
    PMH / PML are its own 04:00–09:30 high and low, its PDH / PDL the regular session
    before it in the bars. A day with neither behind it has an empty set. Pure.

    `daily` widens each PDH / PDL to the official day's, by the rule the row's own
    levels go by (`technicals`), so an earlier day's lines sit where that day's
    scanner had them. `today_cal` is the calendar date the copy is read on."""
    rows = {d.day: d for d in daily or []}
    days: dict[date, dict[str, list[float]]] = {}
    for b in bars5:
        dt = datetime.fromtimestamp(b.t, ET)
        kind = _session_of(dt.date(), _mod(dt))
        if kind in ("pre", "rth"):
            slot = days.setdefault(dt.date(), {"pre": [], "rth": []})
            slot[kind].extend((b.high, b.low))
    out: dict[date, dict[str, float]] = {}
    prior: date | None = None   # the latest earlier day with a regular session
    for d in sorted(days):
        found: dict[str, float] = {}
        if prior is not None:
            done = daily_row(rows, prior, daily_asof, today_cal or d)
            rth = days[prior]["rth"]
            found["PDH"], found["PDL"] = ((done.high, done.low) if done is not None
                                          else (max(rth), min(rth)))
        if days[d]["pre"]:
            found["PMH"], found["PML"] = max(days[d]["pre"]), min(days[d]["pre"])
        out[d] = found
        if days[d]["rth"]:
            prior = d
    return out


def history_levels(bars5: list[Bar], before: date, since: int,
                   daily: list[DayBar] | None = None, daily_asof: float | None = None,
                   today_cal: date | None = None) -> list[dict[str, Any]]:
    """Each day's four levels for the days BEFORE `before`, over that day's own bars —
    the Pine script's "keep previous days' levels". Pure.

    WHY (owner, 2026-10-14: "ensure that the chart in the scanner includes the
    pre market highs and lows"): each earlier day in view carries its own PMH / PML
    (its 04:00–09:30 high and low) and PDH / PDL (the session before it).

    AS THE PINE DRAWS THEM (2026-11-14, `chart_levels`): a day's lines start at its
    first bar, 04:00, and run to its last, the end of its after-hours, with no name on
    them; only the last day's are named. They ran 09:30 to 16:00.

    `since` is the first bar the chart ships; days that end before it are not drawn.
    """
    out: list[dict[str, Any]] = []
    for d, found in day_sets(bars5, daily, daily_asof, today_cal or before).items():
        if d >= before:
            continue
        t0, t1 = _at(d, PM_START), _at(d, post_end(d))
        if t1 <= since:
            continue
        out += [{"key": key, "v": _r(found[key]), "from": t0, "to": t1, "day": d.isoformat()}
                for key in ("PDH", "PDL", "PMH", "PML") if key in found]
    return out


def chart_levels(bars5: list[Bar], last_t: int, tech: Tech, trading_day: date, since: int,
                 daily: list[DayBar] | None = None, daily_asof: float | None = None,
                 today_cal: date | None = None) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    """(the chart's own four levels, the earlier days') as the owner's Pine script draws
    them on the same bars. Pure.

    THE NAMED LEVELS ARE THE LAST DAY'S ON THE CHART, AND THERE IS ONE SET (owner,
    2026-11-14: "i think there is a bug with the pdh/l and pmh/l levels on the stocks
    charts", then, of the first fix, "you now have double ups of the levels"). The
    script starts a day's lines at that day's first bar and names the lines of the day
    the last bar is in; a day with no bar yet has none. This chart drew the TRADING
    day's, and the trading day rolls at 20:00: all weekend, and every night, it showed
    Friday's candles under Monday's levels, so "PDH" and "PDL" sat on Friday's own high
    and low and there was no PMH or PML at all, where TradingView had Thursday's range
    and Friday's pre-market. The first fix kept both sets on the chart, each named.

    So: once the trading day has a bar (from 04:00) the levels are the row's own, the
    pre-market range forming until 09:30. Until then they are the last session's: its
    PDH / PDL (the session before it) and its PMH / PML, as it traded against them.
    `pd_from` and `pm_from` are that day's 04:00, where the chart starts each line (it
    runs them on to its right edge); `day` is whose they are. The row beside the chart
    still plans the next session against the trading day's levels (scan.setup_of).

    `last_t` is the open of the last bar shown; `since` the first."""
    last_day = datetime.fromtimestamp(last_t, ET).date()
    if last_day >= trading_day:
        day = trading_day
        levels = _levels_out(tech)
    else:
        day = last_day
        found = day_sets([b for b in bars5 if b.t <= last_t], daily, daily_asof,
                         today_cal or trading_day).get(day, {})
        levels = {"pdh": _r(found.get("PDH")), "pdl": _r(found.get("PDL")),
                  "pmh": _r(found.get("PMH")), "pml": _r(found.get("PML")), "pm_done": True}
    levels.update(pd_from=_at(day, PM_START), pm_from=_at(day, PM_START), day=day.isoformat())
    return levels, history_levels(bars5, day, since, daily, daily_asof, today_cal or trading_day)


def chart_series(bars5: list[Bar], clock: Clock, tech: Tech, tf: str = "10m",
                 bars1: list[Bar] | None = None, daily: list[DayBar] | None = None,
                 daily_asof: float | None = None) -> dict[str, Any]:
    """The Scanner's mini chart for one name: bars from the previous session's
    open, the 8/9/10 EMA wave, today's VWAP, the four levels, the session spans
    and today's signals. Pure — no fetch, the store's bars.

    `tf` picks the timeframe: 5m and 10m are the store's own 5-minute bars (as
    they are, or paired); 1m and 3m need `bars1`, the one-minute download the
    chart asks for only while it is open on one of them; D is `daily` with the
    last few sessions rebuilt from the 5-minute bars (see `_daily_chart`).

    THE EMA IS COMPUTED ON EVERY BAR HELD and then sliced, so the wave at the
    left edge is the same wave the rest of the series runs on, not one
    re-seeded at the first bar shown.

    EACH VIEW SHOWS ITS OWN CHART'S SIGNALS (2026-11-19): the 3m and 5m their own, the
    1m the 3m's, the 10m and longer the ten-minute chart's. On a view shorter than the
    signal's chart the mark goes on the bar holding the signal bar's last minute — the
    close that confirmed it — so a 1m chart shows the (L) where it was confirmed.
    """
    if tf == "D":
        return _daily_chart(daily or [], bars5, clock, tech, daily_asof)
    step = CHART_TF.get(tf)
    if step is None:
        return _empty_chart(tf, f"no {tf} chart")
    base = bars5 if step >= SRC_SEC else bars1
    if not base:
        return _empty_chart(tf, "no bars" if step >= SRC_SEC else "no one-minute bars")
    now_ts = int(clock.now.timestamp())
    bars = resample([b for b in base if b.t < now_ts], step)
    if not bars:
        return _empty_chart(tf, "no bars")
    closes = [b.close for b in bars]
    e8, e9, e10 = ema(closes, WAVE_LEN), ema(closes, WAVE_LEN + 1), ema(closes, WAVE_LEN + 2)
    e200 = ema(closes, structure.EMA_LEN) if len(closes) >= structure.EMA_LEN else []
    extra = _chart_emas(closes)

    # From the previous session's 04:00 (the PDH/PDL day) — or the start of the
    # download if that day is not in it — and never more than CHART_MAX bars. FROM ITS
    # PRE-MARKET, NOT ITS 09:30 (2026-11-14): that day's PMH and PML are drawn on the
    # chart, and the candles that made them were not: a PMH sat above every bar shown
    # (NVDA, Fri 13 Nov: 171.48 over a session whose high was 170.00). The Pine's chart
    # has extended hours on for the same reason.
    start = 0
    if tech.pdh_day is not None:
        t0 = _at(tech.pdh_day, PM_START)
        start = next((i for i, b in enumerate(bars) if b.t >= t0), 0)
    start = max(start, len(bars) - CHART_MAX)

    td = clock.trading_day
    vwap: list[float | None] = []
    # VWAP's volume-weighted standard deviation, for the chart's bands. Taken about
    # the session's first typical price, as futures.anchored does, so the variance is
    # not the difference of two numbers near a price squared.
    vwap_sd: list[float | None] = []
    pv = vol = 0.0
    ref = svd = svd2 = 0.0
    sessions: list[dict[str, Any]] = []
    span_day: date | None = None
    for b in bars[start:]:
        dt = datetime.fromtimestamp(b.t, ET)
        m = _mod(dt)
        # An hour bar holding the open is the session's, so a long bar reads by its last minute.
        kind = _session_of(dt.date(), m + (step // 60 - 1 if step > BAR_SEC else 0))
        if kind is not None:
            # One span per session per day, gaps included: a thin name's
            # one-minute pre-market has minutes with no trade, and each gap
            # would otherwise start a span of its own.
            if sessions and sessions[-1]["kind"] == kind and span_day == dt.date():
                sessions[-1]["to"] = b.t + step
            else:
                sessions.append({"kind": kind, "from": b.t, "to": b.t + step})
                span_day = dt.date()
        if dt.date() == td and kind == "rth":
            # A bar with no volume yet (the live one, before its first print
            # is counted) holds VWAP where it was rather than breaking the line.
            if b.volume > 0:
                tp = (b.high + b.low + b.close) / 3.0
                if vol == 0:
                    ref = tp
                pv += tp * b.volume
                vol += b.volume
                svd += b.volume * (tp - ref)
                svd2 += b.volume * (tp - ref) ** 2
            vwap.append(round(pv / vol, 4) if vol > 0 else None)
            vwap_sd.append(round(math.sqrt(max(0.0, svd2 / vol - (svd / vol) ** 2)), 4)
                           if vol > 0 else None)
        else:
            vwap.append(None)
            vwap_sd.append(None)

    def cut(xs: list[float]) -> list[float | None]:
        # A list too short to hold the average (`_chart_emas`) ships as blanks.
        return [round(x, 4) for x in xs[start:]] if xs else [None] * (len(bars) - start)

    # EACH VIEW ITS OWN CHART'S SIGNALS (2026-11-19): 3m and 5m their own, 1m the 3m's
    # (the shortest read), 10m and longer the ten-minute chart's.
    own = "3m" if step <= 180 else "5m" if step == 300 else "10m"
    shown = tech.signals if own == "10m" else [x for x in tech.signals_fast
                                                if x.get("tf") == own]
    sig_sec = TF_SEC[own]

    def at(t: int) -> int:
        # A shorter view marks the bar holding the signal's last minute; a longer one
        # the bar the signal falls inside.
        return (t + sig_sec - 1) // step * step if step < sig_sec else t - t % step

    levels, history = chart_levels(bars5, bars[-1].t, tech, td, bars[start].t, daily,
                                   daily_asof, clock.now.astimezone(ET).date())

    return {
        "ok": True,
        "tf": tf,
        "bars": [{"t": b.t, "o": round(b.open, 4), "h": round(b.high, 4), "l": round(b.low, 4),
                  "c": round(b.close, 4), "v": b.volume} for b in bars[start:]],
        "ema8": cut(e8), "ema9": cut(e9), "ema10": cut(e10),
        "ema20": cut(extra[20]), "ema50": cut(extra[50]),
        "ema200": cut(e200),
        "vwap": vwap,
        "vwap_sd": vwap_sd,
        "levels": levels,
        "history": history,
        "sessions": sessions,
        "signals": [{"t": at(x["t"]), "kind": x["kind"], "side": x["side"], "price": x["price"],
                     "tf": own} for x in shown if x.get("t") is not None],
    }


def _daily_chart(daily: list[DayBar], bars5: list[Bar], clock: Clock, tech: Tech,
                 daily_asof: float | None = None) -> dict[str, Any]:
    """The daily view: regular-session candles, the wave on daily closes, the
    four levels. No VWAP and no session spans — a daily bar has neither.

    YAHOO'S DAILY ROW WHEN IT WAS FETCHED AFTER THAT DAY'S CLOSE, THE 5-MINUTE
    BARS OTHERWISE. The daily download refreshes every few hours, so a row can
    be a session caught halfway (fetched at 10:00, still that day's bar at
    16:00) — that row, and today's, are rebuilt from the 5-minute bars'
    regular session instead. A finished row is kept as Yahoo has it, because
    its close is the closing auction's print and the last 5-minute bar's is
    not. `daily_asof` is when the daily download was made (epoch); unknown
    means no row is trusted where the 5-minute bars can stand in for it.
    Today's candle appears once the open has traded and grows with the session.
    """
    now_ts = int(clock.now.timestamp())
    rth: dict[date, list[Bar]] = {}
    for b in bars5:
        if b.t >= now_ts:
            continue
        dt = datetime.fromtimestamp(b.t, ET)
        if _session_of(dt.date(), _mod(dt)) == "rth":
            rth.setdefault(dt.date(), []).append(b)
    def settled(d: date) -> bool:
        # Fetched at least fifteen minutes after that day's close.
        if daily_asof is None or d >= clock.trading_day:
            return False
        close = datetime(d.year, d.month, d.day, tzinfo=ET).timestamp() + rth_end(d) * 60
        return daily_asof >= close + 15 * 60

    have = {x.day for x in daily if settled(x.day)}
    rebuilt = {
        d: DayBar(d, xs[0].open, max(x.high for x in xs), min(x.low for x in xs), xs[-1].close,
                  sum(x.volume for x in xs))
        for d, xs in rth.items() if d <= clock.trading_day and d not in have
    }
    days = [x for x in daily if x.day not in rebuilt and x.day < clock.trading_day]
    days = sorted(days + list(rebuilt.values()), key=lambda x: x.day)
    if not days:
        return _empty_chart("D", "no daily bars")
    closes = [x.close for x in days]
    e8, e9, e10 = ema(closes, WAVE_LEN), ema(closes, WAVE_LEN + 1), ema(closes, WAVE_LEN + 2)
    e200 = ema(closes, structure.EMA_LEN) if len(closes) >= structure.EMA_LEN else []
    extra = _chart_emas(closes)
    start = max(0, len(days) - CHART_DAYS)

    def cut(xs: list[float]) -> list[float | None]:
        return [round(x, 4) for x in xs[start:]] if xs else [None] * (len(days) - start)

    def t_of(d: date) -> int:
        return int(datetime(d.year, d.month, d.day, 9, 30, tzinfo=ET).timestamp())

    return {
        "ok": True,
        "tf": "D",
        "bars": [{"t": t_of(x.day), "o": round(x.open, 4), "h": round(x.high, 4),
                  "l": round(x.low, 4), "c": round(x.close, 4), "v": x.volume}
                 for x in days[start:]],
        "ema8": cut(e8), "ema9": cut(e9), "ema10": cut(e10),
        "ema20": cut(extra[20]), "ema50": cut(extra[50]),
        "ema200": cut(e200),
        "vwap": [None] * (len(days) - start),
        "vwap_sd": [None] * (len(days) - start),
        "levels": _levels_out(tech),
        "sessions": [],
        "signals": [],
    }


def _pairs(c: float | None, pdh: float | None, pdl: float | None, pmh: float | None,
           pml: float | None) -> tuple[dict[str, float | None], dict[str, bool]]:
    """Pine pairCells, as numbers: progress inside the range, ● when broken. Pure."""
    progress: dict[str, float | None] = {"pdh": None, "pdl": None, "pmh": None, "pml": None}
    broken = {"pdh": False, "pdl": False, "pmh": False, "pml": False}
    for hk, lk, hi, lo in (("pdh", "pdl", pdh, pdl), ("pmh", "pml", pmh, pml)):
        if c is None or hi is None or lo is None:
            continue
        if c > hi:
            broken[hk] = True
        elif c < lo:
            broken[lk] = True
        else:
            p = prog(c, hi, lo, True)
            p = 0.5 if p is None else p
            progress[hk] = p
            progress[lk] = 1.0 - p
    return progress, broken


# ------------------------------------------------------------------- the setup


# A NAME NO LEVEL HAS DECIDED LEANS TO THE NEARER TRIGGER, NOT TO RELATIVE STRENGTH
# (owner, 2026-11-15, of an audit of the sides: "do what you recommend"). Until then an
# inside name took the side RS against SPY leaned to. Over the eleven sessions in the
# cache (30 Oct to 13 Nov, about a hundred names a session, 2,103 inside reads):
#   - a name inside its levels has barely moved, so SPY's own move decided the lean:
#     with SPY 0.25 ATR or more from its close, 91% of the leans pointed against it;
#   - of the reads where a trigger then went on a five-minute close, the lean had named
#     it 50.5% of the time (45.5% in the first half hour). The nearer trigger named it
#     77%, and 81% leaving out the middle fifth, on all eleven days, longs and shorts
#     alike; where the two disagreed the lean was right one time in five;
#   - 181 leans were filed away from a level the name was 90% of the way to (so the row
#     read "chop"), and that level went first on 135 of them;
#   - before the bell the lean was right 48% of the time about the side the levels had
#     put the name on by 10:05, the name's own gap 60%.
# No way of leaning said where a name closed. The lean's job is which break to watch.
# So: in the session, the nearer of the two triggers (the lowest high above price, the
# highest low under it), and no side in the middle fifth between them; before the bell
# and overnight, where the pre-market pair is not set, the name's own move from the
# previous close, the lean the Scanner's lists already give a name the engine does not
# track. The scratchpad's side_candidates.py prints every figure above.
LEAN_MID = 0.20  # the middle of the gap between the two triggers, as a share of it: no side
LEAN_MIN = 0.10  # daily ATRs of the name's own move; scanscore.GAP_MIN, kept equal by a test


def lean_of(last: float | None, pdh: float | None, pdl: float | None, pmh: float | None,
            pml: float | None, own: float | None, in_session: bool) -> str | None:
    """The side of a name no level has decided, or None. Pure.

    `pmh` / `pml` must already be None until the pre-market is done, as for
    `lvl_state_of`; `own` is the name's move in its daily ATRs (Tech.mv_lean: the day's
    move, and overnight the last session and after hours together); `in_session` is
    whether the regular session has begun today (Tech.rth_today).

    IN THE SESSION, INSIDE ALL ITS LEVELS: the nearer trigger. A name 0.3 under PDH
    and 3.7 over PML leans long; one in the middle fifth of the gap has no side.

    OTHERWISE THE NAME'S OWN MOVE, 0.1 ATR OR MORE: before the bell and overnight;
    with a level missing; and for a name above one high and below one low. That last
    is always the previous day's level one way and the pre-market's the other (above
    PDH and under PML, or under PDL and over PMH), and a name past the previous day's
    level is up or down on the day with it, so the previous day's level decides.
    """
    if last is None:
        return None
    highs = [x for x in (pdh, pmh) if x is not None]
    lows = [x for x in (pdl, pml) if x is not None]
    inside = (bool(highs) and bool(lows) and all(last <= x for x in highs)
              and all(last >= x for x in lows))
    if in_session and inside:
        up, down = min(highs) - last, last - max(lows)
        gap = up + down
        if gap <= 0:
            return None
        pos = down / gap  # 0 on the low trigger, 1 on the high one
        if abs(pos - 0.5) * 2.0 < LEAN_MID:
            return None
        return "long" if pos > 0.5 else "short"
    if own is None or abs(own) < LEAN_MIN:
        return None
    return "long" if own > 0 else "short"


def side_of(lvl_state: int, last: float | None, pdh: float | None, pdl: float | None,
            pmh: float | None, pml: float | None, own: float | None,
            in_session: bool) -> str | None:
    """Long above a level, short below one; otherwise the lean (`lean_of`), which is no
    side at all when the name sits in the middle or has not moved. Pure."""
    if lvl_state > 0:
        return "long"
    if lvl_state < 0:
        return "short"
    return lean_of(last, pdh, pdl, pmh, pml, own, in_session)


def setup_of(t: Tech, side: str | None, clock: Clock) -> dict[str, Any]:
    """Where the trade is: at the level, on the way back to it, or so far past it
    that VWAP / the 8 EMA wave is the entry instead. Pure.

    States (contract): retest · pullback · extended · approaching · chop ·
    failed · forming. `entry.dist_atr` is (last − entry) / 10-minute ATR, signed.
    """
    out: dict[str, Any] = {"side": side, "state": "chop", "level": None, "entry": None,
                           "note": ""}
    last, ab = t.last, t.atr_b
    if last is None:
        out["note"] = "No price"
        return out

    def entry(kind: str, price: float) -> dict[str, Any]:
        d = (last - price) / ab if ab else 0.0
        return {"kind": kind, "price": round(price, 4), "dist_atr": round(d, 2)}

    long_lv = [("PDH", t.pdh), ("PMH", t.pmh)]
    short_lv = [("PDL", t.pdl), ("PML", t.pml)]

    # ---- before the bell: a plan, not a state -------------------------------
    if not t.rth_today:
        out["state"] = "forming"
        if side is None:
            out["note"] = "Inside yesterday's range and flat — no plan yet"
            return out
        cands = long_lv if side == "long" else short_lv
        pm_word = "forming" if not t.pm_done else ""
        if side == "long":
            below = [(k, p) for k, p in cands if p is not None and p < last]
            above = [(k, p) for k, p in cands if p is not None and p >= last]
            if below:
                k, p = max(below, key=lambda x: x[1])
                out["level"], out["entry"] = k, entry(k, p)
                out["note"] = (f"Holding above {k} {fmt_px(p)}"
                               " — plan: the retest of it after the open")
            elif above:
                k, p = min(above, key=lambda x: x[1])
                out["level"], out["entry"] = k, entry(k, p)
                out["note"] = f"Plan: break of {k} {fmt_px(p)}, then the retest"
        else:
            above = [(k, p) for k, p in cands if p is not None and p > last]
            below = [(k, p) for k, p in cands if p is not None and p <= last]
            if above:
                k, p = min(above, key=lambda x: x[1])
                out["level"], out["entry"] = k, entry(k, p)
                out["note"] = (f"Holding below {k} {fmt_px(p)}"
                               " — plan: the retest of it after the open")
            elif below:
                k, p = max(below, key=lambda x: x[1])
                out["level"], out["entry"] = k, entry(k, p)
                out["note"] = f"Plan: break of {k} {fmt_px(p)}, then the retest"
        if pm_word and t.pmh is not None:
            out["note"] += " · PMH/PML still forming"
        return out

    # ---- the regular session -------------------------------------------------
    buf = (ab or 0.0) * BUF_MULT
    if side is not None:
        long_side = side == "long"
        cands = long_lv if long_side else short_lv
        s = 1.0 if long_side else -1.0
        beyond = [(k, p) for k, p in cands if p is not None and s * (last - p) > 0]
        if beyond:
            k, p = (max if long_side else min)(beyond, key=lambda x: x[1])
            lv = t.levels.get(k)
            # Beyond it on the open bar but not on a confirmed close yet: the
            # script has not counted the break, so neither does the note.
            when = " this bar"
            if lv is not None and lv.broke_t is not None and lv.broken:
                when = " at the open" if lv.gapped else f" at {_hm(lv.broke_t)}"
            dist = s * (last - p) / ab if ab else 0.0
            near = t.bar_low if long_side else t.bar_high
            probe = min(last, near) if (long_side and near is not None) else (
                max(last, near) if near is not None else last)
            in_zone = s * (probe - p) <= buf
            out["level"] = k
            if in_zone:
                out["state"] = "retest"
                out["entry"] = entry(k, p)
                out["note"] = f"At {k} {fmt_px(p)} (broke{when}) — the (L) retest is live"
            elif dist <= EXT_ATR:
                out["state"] = "pullback"
                out["entry"] = entry(k, p)
                word = "above" if long_side else "below"
                out["note"] = (f"{dist:.1f} ATR {word} {k} {fmt_px(p)} (broke{when})"
                               f" — the retest of the level is the entry")
            else:
                out["state"] = "extended"
                refs = []
                if t.vwap is not None and s * (last - t.vwap) > 0:
                    refs.append(("VWAP", t.vwap))
                edge = t.wave_hi if long_side else t.wave_lo
                if edge is not None and s * (last - edge) > 0:
                    refs.append(("EMA8", edge))
                word = "above" if long_side else "below"
                head = f"Broke {k} {fmt_px(p)}{when} · {dist:.1f} ATR {word} it"
                if refs:
                    kk, pp = (max if long_side else min)(refs, key=lambda x: x[1])
                    out["entry"] = entry(kk, pp)
                    alts = " or ".join(
                        f"{'VWAP' if a == 'VWAP' else 'the 8 EMA'} {fmt_px(b)}" for a, b in refs)
                    out["note"] = f"{head} — wait for {alts}"
                else:
                    back = "below" if long_side else "above"
                    out["note"] = (f"{head} — but back {back} VWAP and the 8 EMA:"
                                   " the move has stalled")
            return _vwap_check(out, t, side)

        failed = [(k, p) for k, p in cands
                  if p is not None and k in t.levels and t.levels[k].failed]
        if failed:
            k, p = max(failed, key=lambda x: t.levels[x[0]].failed_t or 0)
            out["state"], out["level"], out["entry"] = "failed", k, entry(k, p)
            word = "under" if long_side else "over"
            out["note"] = f"Broke {k} {fmt_px(p)} then closed back {word} it — a failed break"
            return _vwap_check(out, t, side)

    # Inside: approaching a level, or chop.
    near_k, near_p, near_v = None, None, 0.0
    keys = (("pdh", "PDH", t.pdh), ("pmh", "PMH", t.pmh), ("pdl", "PDL", t.pdl),
            ("pml", "PML", t.pml))
    for pk, lk, lp in keys:
        pv = t.progress.get(pk)
        if pv is None or lp is None:
            continue
        if side == "long" and lk in ("PDL", "PML"):
            continue
        if side == "short" and lk in ("PDH", "PMH"):
            continue
        if pv >= NEAR_PCT and pv > near_v:
            near_k, near_p, near_v = lk, lp, pv
    if near_k is not None and near_p is not None:
        out["state"], out["level"], out["entry"] = "approaching", near_k, entry(near_k, near_p)
        out["note"] = (f"{round(near_v * 100)}% of the way to {near_k} {fmt_px(near_p)}"
                       " — watch for the break, then the retest")
        return _vwap_check(out, t, side)
    out["note"] = "Inside the levels — chop, no signals"
    return out


def _vwap_check(out: dict[str, Any], t: Tech, side: str | None) -> dict[str, Any]:
    """Mark price on the wrong side of VWAP for the side — the score reads it."""
    out["lost_vwap"] = False
    if side is None or t.vwap is None or t.last is None:
        return out
    if (side == "long" and t.last < t.vwap) or (side == "short" and t.last > t.vwap):
        out["lost_vwap"] = True
        word = "below" if side == "long" else "above"
        if "VWAP" not in out["note"]:
            out["note"] += f" · {word} VWAP {fmt_px(t.vwap)}"
    return out


def rs_pair(t: Tech, bench: Tech | None) -> tuple[float | None, float | None]:
    """RS "Today" and "Last N bars" against one benchmark: this ticker's move minus
    the benchmark's, each in its own ATRs. Pure."""
    if bench is None:
        return None, None
    day = (t.mv_day - bench.mv_day) if t.mv_day is not None and bench.mv_day is not None else None
    roll = (t.mv_roll - bench.mv_roll) if (t.mv_roll is not None
                                          and bench.mv_roll is not None) else None
    return day, roll


def _r(x: float | None, n: int = 4) -> float | None:
    return round(x, n) if x is not None else None


def row_of(sym: str, t: Tech, spy: Tech | None, qqq: Tech | None,
           clock: Clock) -> dict[str, Any]:
    """The technical half of a scanner row (contract ScanRow), RS and setup included.
    Score, flags, earnings, news and filings are joined on read. Pure."""
    rs_spy, rs1_spy = rs_pair(t, spy)
    rs_qqq, rs1_qqq = rs_pair(t, qqq)
    # The pre-market pair counts once it is set, as it does for the level state.
    side = side_of(t.lvl_state, t.last, t.pdh, t.pdl, t.pmh if t.pm_done else None,
                   t.pml if t.pm_done else None,
                   t.mv_lean if t.mv_lean is not None else t.mv_day, t.rth_today)
    setup = setup_of(t, side, clock) if t.ok else {
        "side": None, "state": "chop", "level": None, "entry": None, "note": t.error or ""}
    return {
        "sym": sym,
        "name": t.name,
        "ok": t.ok,
        "error": t.error,
        "last": _r(t.last),
        "prev_close": _r(t.prev_close),
        "chg_pct": _r(t.chg_pct, 3),
        "ext_pct": _r(t.ext_pct, 3),
        "volume": t.volume,
        "rvol": _r(t.rvol, 2),
        "atr_d": _r(t.atr_d),
        "atr_b": _r(t.atr_b),
        "rs": {"SPY": _r(rs_spy, 3), "QQQ": _r(rs_qqq, 3)},
        "rs_1h": {"SPY": _r(rs1_spy, 3), "QQQ": _r(rs1_qqq, 3)},
        "levels": {
            "pdh": _r(t.pdh), "pdl": _r(t.pdl), "pdc": _r(t.pdc),
            "pmh": _r(t.pmh), "pml": _r(t.pml), "pm_done": t.pm_done,
            "vwap": _r(t.vwap), "wave_hi": _r(t.wave_hi), "wave_lo": _r(t.wave_lo),
            "ema8": _r(t.ema8), "day_hi": _r(t.day_hi), "day_lo": _r(t.day_lo),
            "open": _r(t.open), "ema200": _r(t.ema200),
            # The 5-minute bars' own high and low for that session, for the page to
            # say when the official level sits past them, and whether the open is
            # the official print yet (see `technicals`).
            "pdh_bars": _r(t.pdh_bars), "pdl_bars": _r(t.pdl_bars),
            "open_official": t.open_official,
            # The pre-market range as these bars alone have it: narrower than `pmh` /
            # `pml` on a day the bars start late and a second read fills the range in.
            "pmh_bars": _r(t.pmh_bars), "pml_bars": _r(t.pml_bars),
        },
        "trend200": t.trend200,
        "ema200_slope": t.ema200_slope,
        "progress": {k: _r(v, 3) for k, v in t.progress.items()} if t.progress else
        {"pdh": None, "pdl": None, "pmh": None, "pml": None},
        "broken": t.broken or {"pdh": False, "pdl": False, "pmh": False, "pml": False},
        "lvl_state": t.lvl_state,
        "trend": t.trend,
        "range_used": _r(t.range_used, 3),
        "setup": setup,
        "signals": t.signals,
        # The 3m and 5m charts' signals, each with its `tf` (Tech.signals_fast).
        "signals_fast": t.signals_fast,
        "final_to_tf": t.final_to_tf,
        # Carried for the read path's tape and regime; not part of the contract.
        "pdh_day": t.pdh_day.isoformat() if t.pdh_day else None,
        # Where this row's bars are final (Tech.final_to) — the event log checks
        # what it logged against the signals up to here.
        "final_to": t.final_to,
    }
