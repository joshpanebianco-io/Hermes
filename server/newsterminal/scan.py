"""
The scanner's arithmetic — LE_Model.pine's levels, 8 EMA wave and signals, ported.

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

from dataclasses import dataclass, field
from datetime import date, datetime
from typing import Any, NamedTuple
from zoneinfo import ZoneInfo

from .holidays import close_minute, early_close, is_trading_day, next_trading_day

ET = ZoneInfo("America/New_York")

# Minutes of the ET day. The script's sessions are "0400-0930" and "0930-1600".
# On the NYSE's half days the regular session ends at 13:00 and the late session
# at 17:00 — `rth_end` / `post_end` read the holiday table, these are the norm.
PM_START = 4 * 60
RTH_START = 9 * 60 + 30
RTH_END = 16 * 60
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

ATR_LEN = 14  # ta.atr(14) on the chart, and the hand-kept daily ATR
WAVE_LEN = 8  # EMA 8 / 9 / 10
BUF_MULT = 0.25  # "Retest buffer (× ATR 14)"
NEAR_PCT = 0.90  # "'About to break' alert at progress ≥ %"
RS_BARS = 6  # "Last N bars" — one hour on the 10m

# How far past a broken level price may run before the level stops being the
# entry and VWAP / the 8 EMA wave takes over — the owner's "super far above or
# below". In 10-minute ATRs, the unit the retest buffer is already measured in.
EXT_ATR = 2.5

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


def parse_chart(doc: Any) -> tuple[list[Bar], dict[str, Any]]:
    """A Yahoo v8 chart response (5m, extended) → bars on the 5-minute grid. Pure.

    THE LAST BAR IS NOT ON THE GRID. Yahoo stamps the live bar with the time of
    its last trade (05:38:51), so every stamp is floored to five minutes, and a
    bar that floors onto its predecessor's bucket is merged into it. Rows with a
    null price are holes in the tape (no trade) and are dropped, never zeroed.
    """
    ts, meta, q = _quote_rows(doc)
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
        k = int(t) - int(t) % SRC_SEC
        b = Bar(k, float(o), float(h), float(lo), float(c), float(v or 0.0))
        if bars and bars[-1].t == k:
            p = bars[-1]
            bars[-1] = Bar(k, p.open, max(p.high, b.high), min(p.low, b.low), b.close,
                           p.volume + b.volume)
        elif not bars or k > bars[-1].t:
            bars.append(b)
    return bars, meta


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


def atr(bars: list[Bar], n: int = ATR_LEN) -> list[float | None]:
    """Pine's ta.atr: RMA of the true range, seeded with the SMA of the first n. Pure."""
    out: list[float | None] = []
    trs: list[float] = []
    a: float | None = None
    for i, b in enumerate(bars):
        if i == 0:
            tr = b.high - b.low
        else:
            pc = bars[i - 1].close
            tr = max(b.high - b.low, abs(b.high - pc), abs(b.low - pc))
        trs.append(tr)
        if a is None:
            if len(trs) >= n:
                a = sum(trs[-n:]) / n
        else:
            a = (a * (n - 1) + tr) / n
        out.append(a)
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


def replay(bars10: list[Bar], rth_ix: list[int], forming: int | None, levels: dict[str, Lvl],
           atr10: list[float | None], w_top: list[float], w_bot: list[float],
           pmh_live: float | None, pml_live: float | None) -> Replay:
    """Today's (L) / (E) / breakout signals over confirmed regular-session bars.

    `rth_ix` are the CONFIRMED regular-session bars of the trading day, in order,
    as indices into `bars10` (so the EMA wave, the ATR and the previous close are
    the script's own series values at that bar). `forming` is the still-open
    bar, if any: levels never step on it — the script only steps confirmed bars —
    but an (E) trigger can fire on it, because a high only rises inside a bar.
    """
    out = Replay(levels)
    pdh, pdl = levels["PDH"].price, levels["PDL"].price
    e_bar: dict[str, int | None] = {"long": None, "short": None}
    e_trg: dict[str, float] = {"long": 0.0, "short": 0.0}
    e_stp: dict[str, float] = {"long": 0.0, "short": 0.0}
    e_arm: dict[str, bool] = {"long": False, "short": False}

    def sig(kind: str, side: str, level: str | None, t: int, price: float, note: str,
            stop: float | None = None) -> None:
        # `t` (the bar's open, epoch) and `stop` (the script's "stop idea") ride
        # along for the event log and the chart; the row's own readers ignore them.
        out.signals.append({"kind": kind, "side": side, "level": level, "at_et": _hm(t),
                            "price": round(price, 4), "note": note, "t": t,
                            "stop": round(stop, 4) if stop is not None else None})

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
        l_long = ok_l and (res["PDH"][1] or res["PMH"][1])
        l_short = ok_s and (res["PDL"][1] or res["PML"][1])
        if l_long:
            lv = "PDH" if res["PDH"][1] else "PMH"
            sig("L", "long", lv, b.t, b.close,
                f"Retest of {lv} {fmt_px(levels[lv].price)} with the 8 EMA wave at the level"
                f" · stop idea below {fmt_px(b.low)}", stop=b.low)
        if l_short:
            lv = "PDL" if res["PDL"][1] else "PML"
            sig("L", "short", lv, b.t, b.close,
                f"Retest of {lv} {fmt_px(levels[lv].price)} with the 8 EMA wave at the level"
                f" · stop idea above {fmt_px(b.high)}", stop=b.high)

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
                    f" · stop idea {stop} {fmt_px(e_stp[side])}", stop=e_stp[side])
                e_bar[side] = None

        # ---- the sigBar block ------------------------------------------------
        if e_bar["long"] is not None and (state <= 0 or b.close < wb):
            e_bar["long"] = None
        if e_bar["short"] is not None and (state >= 0 or b.close > wt):
            e_bar["short"] = None
        if (ok_l and e_arm["long"] and not conf["long"] and not l_long
                and b.low <= wt and b.close >= wb):
            e_bar["long"], e_trg["long"], e_stp["long"] = i, b.high, b.low
        if (ok_s and e_arm["short"] and not conf["short"] and not l_short
                and b.high >= wb and b.close <= wt):
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
                    stop=e_stp[side])
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
    mv_roll: float | None = None
    pdh: float | None = None
    pdl: float | None = None
    pdc: float | None = None
    pdh_day: date | None = None
    pmh: float | None = None
    pml: float | None = None
    pm_done: bool = False
    vwap: float | None = None
    wave_hi: float | None = None
    wave_lo: float | None = None
    ema8: float | None = None
    day_hi: float | None = None
    day_lo: float | None = None
    open: float | None = None
    rth_today: bool = False
    #: The latest 10-minute bar's low/high (forming or not) — the retest zone test.
    bar_low: float | None = None
    bar_high: float | None = None
    levels: dict[str, Lvl] = field(default_factory=dict)
    signals: list[dict[str, Any]] = field(default_factory=list)
    lvl_state: int = 0
    trend: int = 0
    progress: dict[str, float | None] = field(default_factory=dict)
    broken: dict[str, bool] = field(default_factory=dict)
    range_used: float | None = None


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


def _vwap(bars: list[Bar]) -> float | None:
    pv = sum((b.high + b.low + b.close) / 3.0 * b.volume for b in bars)
    v = sum(b.volume for b in bars)
    return pv / v if v > 0 else None


def technicals(bars5: list[Bar], daily: list[DayBar], clock: Clock,
               name: str | None = None, official: tuple[date, float] | None = None) -> Tech:
    """Everything the script computes for one symbol, as of `clock.now`. Pure.

    Bars that OPEN after `clock.now` are ignored, so the same function replays
    any past instant from a later download — which is how the boundary table in
    tools/scan_probe.py is produced. `official` is `official_close(meta)`;
    pass None when replaying the past, since it is a fact about now.
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

    prior = [d for d in sorted(by_day) if d < td and rth_of(d)]
    d1 = prior[-1] if prior else None
    d2 = prior[-2] if len(prior) > 1 else None
    if d1 is not None:
        r1 = rth_of(d1)
        tech.pdh = max(bars[i].high for i in r1)
        tech.pdl = min(bars[i].low for i in r1)
        tech.pdc = close_of(d1, bars[r1[-1]].close)
        tech.pdh_day = d1
    ppdc = close_of(d2, bars[rth_of(d2)[-1]].close) if d2 is not None else None
    tech.prev_close = tech.pdc

    today = by_day.get(td, [])
    pm = [i for i in today if PM_START <= mods[i] < RTH_START]
    if pm:
        tech.pmh = max(bars[i].high for i in pm)
        tech.pml = min(bars[i].low for i in pm)
    tech.pm_done = clock.pm_locked
    td_end = rth_end(td)
    rth = [i for i in today if RTH_START <= mods[i] < td_end]
    tech.rth_today = bool(rth)
    d_cl: float | None = None
    if rth:
        tech.day_hi = max(bars[i].high for i in rth)
        tech.day_lo = min(bars[i].low for i in rth)
        tech.open = bars[rth[0]].open
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
    # same window on the prior sessions in the download (two at least).
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
            if len(priors) >= 4:
                break
        if len(priors) >= 2 and cum_today > 0:
            tech.rvol = cum_today / (sum(priors) / len(priors))

    # ---- the 10-minute chart -------------------------------------------------
    bars10 = resample(bars)
    closes = [b.close for b in bars10]
    e1, e2, e3 = ema(closes, WAVE_LEN), ema(closes, WAVE_LEN + 1), ema(closes, WAVE_LEN + 2)
    w_top = [max(a, b, c) for a, b, c in zip(e1, e2, e3, strict=True)]
    w_bot = [min(a, b, c) for a, b, c in zip(e1, e2, e3, strict=True)]
    atr10 = atr(bars10)
    if bars10:
        tech.ema8, tech.wave_hi, tech.wave_lo = e1[-1], w_top[-1], w_bot[-1]
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

    # ---- levels against price ------------------------------------------------
    pmh_live = tech.pmh if tech.pm_done else None
    pml_live = tech.pml if tech.pm_done else None
    tech.lvl_state = lvl_state_of(last, tech.pdh, tech.pdl, pmh_live, pml_live)
    tech.trend = trend_of(last, tech.pdh, tech.pdl, pmh_live, pml_live)
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
    confirmed = [k for k in rth10 if bars10[k].t + BAR_SEC <= now_ts]
    forming = rth10[-1] if rth10 and rth10[-1] not in confirmed else None
    if rth10:
        rp = replay(bars10, confirmed, forming, levels, atr10, w_top, w_bot, pmh_live, pml_live)
        tech.signals = rp.signals
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


def chart_series(bars5: list[Bar], clock: Clock, tech: Tech) -> dict[str, Any]:
    """The Scanner's mini chart for one name: ten-minute bars from the previous
    session's open, the 8/9/10 EMA wave, today's VWAP, the four levels, the
    session spans and today's signals. Pure — no fetch, the store's bars.

    THE EMA IS COMPUTED ON EVERY BAR THE STORE HOLDS and then sliced, so the
    wave at the left edge of the chart is the same wave the signals were read
    off, not one re-seeded at the first bar shown.
    """
    now_ts = int(clock.now.timestamp())
    bars10 = resample([b for b in bars5 if b.t < now_ts])
    if not bars10:
        return {"ok": False, "error": "no bars", "bars": [], "ema8": [], "ema9": [], "ema10": [],
                "vwap": [], "levels": {}, "sessions": [], "signals": []}
    closes = [b.close for b in bars10]
    e8, e9, e10 = ema(closes, WAVE_LEN), ema(closes, WAVE_LEN + 1), ema(closes, WAVE_LEN + 2)

    # From the previous session's 09:30 (the PDH/PDL day) — or the start of the
    # download if that day is not in it.
    start = 0
    if tech.pdh_day is not None:
        d = tech.pdh_day
        t0 = int(datetime(d.year, d.month, d.day, 9, 30, tzinfo=ET).timestamp())
        start = next((i for i, b in enumerate(bars10) if b.t >= t0), 0)

    td = clock.trading_day
    vwap: list[float | None] = []
    pv = vol = 0.0
    sessions: list[dict[str, Any]] = []
    for b in bars10[start:]:
        dt = datetime.fromtimestamp(b.t, ET)
        m = _mod(dt)
        kind = _session_of(dt.date(), m)
        if kind is not None:
            if sessions and sessions[-1]["kind"] == kind and sessions[-1]["to"] == b.t:
                sessions[-1]["to"] = b.t + BAR_SEC
            else:
                sessions.append({"kind": kind, "from": b.t, "to": b.t + BAR_SEC})
        if dt.date() == td and kind == "rth" and b.volume > 0:
            pv += (b.high + b.low + b.close) / 3.0 * b.volume
            vol += b.volume
            vwap.append(round(pv / vol, 4))
        else:
            vwap.append(None)

    def cut(xs: list[float]) -> list[float | None]:
        return [round(x, 4) for x in xs[start:]]

    return {
        "ok": True,
        "bars": [{"t": b.t, "o": round(b.open, 4), "h": round(b.high, 4), "l": round(b.low, 4),
                  "c": round(b.close, 4), "v": b.volume} for b in bars10[start:]],
        "ema8": cut(e8), "ema9": cut(e9), "ema10": cut(e10),
        "vwap": vwap,
        "levels": {"pdh": _r(tech.pdh), "pdl": _r(tech.pdl), "pmh": _r(tech.pmh),
                   "pml": _r(tech.pml), "pm_done": tech.pm_done},
        "sessions": sessions,
        "signals": [{"t": x["t"], "kind": x["kind"], "side": x["side"], "price": x["price"]}
                    for x in tech.signals if x.get("t") is not None],
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


def side_of(lvl_state: int, rs: float | None) -> str | None:
    """Long above a level, short below one; inside, the side relative strength
    leans to — and no side at all when it barely leans. Pure."""
    if lvl_state > 0:
        return "long"
    if lvl_state < 0:
        return "short"
    if rs is None or abs(rs) < 0.1:
        return None
    return "long" if rs > 0 else "short"


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
            out["note"] = "Inside yesterday's range with no relative-strength lean — no plan yet"
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
    side = side_of(t.lvl_state, rs_spy)
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
            "open": _r(t.open),
        },
        "progress": {k: _r(v, 3) for k, v in t.progress.items()} if t.progress else
        {"pdh": None, "pdl": None, "pmh": None, "pml": None},
        "broken": t.broken or {"pdh": False, "pdl": False, "pmh": False, "pml": False},
        "lvl_state": t.lvl_state,
        "trend": t.trend,
        "range_used": _r(t.range_used, 3),
        "setup": setup,
        "signals": t.signals,
        # Carried for the read path's tape and regime; not part of the contract.
        "pdh_day": t.pdh_day.isoformat() if t.pdh_day else None,
    }
