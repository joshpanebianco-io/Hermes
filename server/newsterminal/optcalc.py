"""
The options maths behind each scanner row — pure, so every number is testable.

WHY A STOCKS DESK NEEDS THIS AT ALL (owner, 2026-10-13: "do everything you
recommend"). The scanner said which name and where the entry is; the owner
trades OPTIONS on those names, and the trade is not the same trade at every
price of premium. So each row learns four things from the name's own chain:

  - IS PREMIUM CHEAP OR RICH? Cboe's IV30 against the stock's own realised
    volatility over twenty sessions. Rich premium is the case for a spread
    over a long option; cheap premium is the case for the long.
  - HOW FAR DOES THE MARKET THINK IT GOES? The at-the-money straddle's mid on
    the front and the weekly expiry — the options market's expected move, the
    yardstick a target is checked against.
  - CAN IT BE TRADED? The ATM legs' bid-ask as a share of mid, and their open
    interest. A 9% spread is a loss taken at the fill.
  - WHICH WAY IS TODAY'S MONEY LEANING? Put against call volume, and volume
    against open interest, summed over the contracts the chain keeps (the
    first KEEP_EXPIRIES expiries, strikes within STRIKE_BAND of spot) — with
    the three busiest contracts named. Context, never a vote on its own: a
    put-heavy tape on a name with a long setup is a reason to look twice.
  - WHAT WOULD I BUY? For the row's side: the strike nearest 0.60 delta (in
    the money enough to track the stock, cheap enough to size), and the debit
    spread against the 0.30 delta — with what the stock-level stop costs per
    contract once it is translated through delta.

THE CHAIN IS FIFTEEN MINUTES OLD; THE STOCK IS NOT (owner, 2026-10-14). Cboe's
free quotes are delayed at source, while the row's price is live in the regular
session. So a suggested contract also carries an ESTIMATE of where it trades
now: its delayed mid moved by the stock's move since the chain's own spot,
through delta and gamma (mid + Δ·dS + ½Γ·dS², delta + Γ·dS), never below
intrinsic. Only a same-day chain, only 09:30 to the close, and only for a move
inside REMARK_MAX — further out a second-order step is a guess, and an unmoved
IV is part of the guess anyway. Risk per contract is priced off the estimate
when there is one. The quote itself stays beside it, as quoted.

THE EXPIRIES (owner's defaults, the desks contract). SPY, QQQ and IWM trade a
same-day expiry: their FRONT is today's while it is listed and the clock is an
hour or more before the close (15:00 ET; 12:00 on a half day), else the next
one. Single names' front is simply the nearest expiry that has not expired.
The WEEKLY is the nearest expiry with at least two trading days still to run —
far enough out that one bad session does not decide the trade.

DTE AND "TODAY" ARE THE SCANNER'S TRADING DAY. Overnight on a Monday the
levels are already Tuesday's, and so is the 0DTE: a plan written at 21:00 for
tomorrow's open is about tomorrow's expiry. Minutes on the trading day before
it has started count as before the open.

NOTHING HERE IS ADVICE IN DISGUISE. Every choice is a fixed rule written down
below; the page shows the rule's output beside the numbers that drove it.
"""

from __future__ import annotations

import math
import re
from dataclasses import dataclass, field
from datetime import UTC, date, datetime
from typing import Any
from zoneinfo import ZoneInfo

from .holidays import close_minute, is_trading_day

ET = ZoneInfo("America/New_York")

# ---- the rules (documented constants) -----------------------------------------
#: Same-day expiries on these — their front is today's 0DTE.
DAILY_EXPIRY = frozenset({"SPY", "QQQ", "IWM"})
#: A 0DTE stops being the front this long before the close.
ZERO_DTE_CUTOFF_MIN = 60
#: The weekly needs this many trading days left to run.
WEEKLY_MIN_SESSIONS = 2
#: The long leg's delta, and the spread's short leg.
LONG_DELTA = 0.60
SHORT_DELTA = 0.30
#: Premium verdict: IV30 / RV20 below CHEAP is cheap, above RICH is rich.
PREMIUM_CHEAP = 0.90
PREMIUM_RICH = 1.25
#: Liquidity grade from the ATM legs' spread as a % of mid.
LIQ_GOOD = 3.0
LIQ_OK = 8.0
#: IV rank / percentile need this many logged days before they mean anything.
IV_MIN_DAYS = 20
IV_LOOKBACK = 252
#: Realised volatility window, in sessions.
RV_SESSIONS = 20
#: The Pine's retest buffer, used for the stop when no signal set one.
STOP_BUFFER_ATR = 0.25
#: Strikes kept per expiry, as a band round spot — enough for a 0.25 delta.
STRIKE_BAND = 0.15
#: Expiries kept per name (from the trading day on) — covers the 0DTE, the next
#: one, and a weekly with two sessions to run on a daily-expiry ETF.
KEEP_EXPIRIES = 4
#: Flow lean: put ÷ call volume below CALLS reads as call-led, above PUTS as
#: put-led, between as balanced — the usual equity put/call bands.
FLOW_CALLS = 0.7
FLOW_PUTS = 1.3
#: Fewer contracts than this traded across the kept chain and the lean is not
#: read (null) — a handful of prints is noise, not positioning.
FLOW_MIN_VOL = 100
#: The busiest contracts named under the flow.
FLOW_TOP = 3
#: The live estimate is only made for a stock move inside this fraction of the
#: chain's spot.
REMARK_MAX = 0.05
#: The regular session opens at this minute of the ET day.
RTH_OPEN = 9 * 60 + 30

_OCC = re.compile(r"^([A-Z.]+?)(\d{6})([CP])(\d{8})$")


@dataclass(frozen=True)
class Opt:
    """One contract, the fields the desk reads."""

    symbol: str
    expiry: date
    right: str  # "C" | "P"
    strike: float
    bid: float
    ask: float
    iv: float | None  # fraction, as Cboe sends it
    delta: float | None
    theta: float | None
    oi: float
    volume: float
    gamma: float | None = None

    @property
    def mid(self) -> float | None:
        """Bid-ask mid; a one-sided quote (no bid) is half the ask; no ask is no price."""
        if self.ask <= 0 or self.bid < 0 or self.ask < self.bid:
            return None
        return (self.bid + self.ask) / 2.0

    @property
    def spread_pct(self) -> float | None:
        m = self.mid
        if m is None or m <= 0:
            return None
        return (self.ask - self.bid) / m * 100.0


@dataclass
class Chain:
    """What one Cboe chain is reduced to: spot, IV30, the clock, and the nearest
    expiries' contracts round spot. Never the raw document."""

    sym: str
    spot: float | None
    iv30: float | None
    asof: datetime | None  # UTC
    expiries: list[date]  # every listed expiry from the trading day on
    opts: dict[date, list[Opt]] = field(default_factory=dict)


# ----------------------------------------------------------------------- parse


def parse_occ(sym: str) -> tuple[str, date, str, float] | None:
    """'SPY261013C00778000' → ('SPY', 2026-10-13, 'C', 778.0). Pure."""
    m = _OCC.match(sym or "")
    if not m:
        return None
    root, ymd, right, k = m.groups()
    try:
        exp = date(2000 + int(ymd[:2]), int(ymd[2:4]), int(ymd[4:6]))
    except ValueError:
        return None
    return root, exp, right, int(k) / 1000.0


def _f(v: Any) -> float | None:
    try:
        x = float(v)
    except (TypeError, ValueError):
        return None
    return x if math.isfinite(x) else None


def parse_asof(v: Any) -> datetime | None:
    """Cboe's top-level `timestamp` — "2026-10-13 12:07:43", in UTC."""
    if not isinstance(v, str):
        return None
    try:
        return datetime.strptime(v.strip()[:19], "%Y-%m-%d %H:%M:%S").replace(tzinfo=UTC)
    except ValueError:
        return None


def parse_chain(doc: Any, sym: str, ref_day: date) -> Chain:
    """A Cboe delayed-quotes document → a Chain. Pure.

    Expiries before the trading day are dropped (the feed keeps yesterday's
    0DTE listed); so is every strike outside ±STRIKE_BAND of spot, which is
    all a 0.25 delta or an ATM straddle ever needs.
    """
    data = (doc or {}).get("data") if isinstance(doc, dict) else None
    if not isinstance(data, dict):
        return Chain(sym, None, None, None, [])
    spot = _f(data.get("current_price"))
    iv30 = _f(data.get("iv30"))
    asof = parse_asof(doc.get("timestamp"))
    by_exp: dict[date, list[Opt]] = {}
    for o in data.get("options") or []:
        if not isinstance(o, dict):
            continue
        p = parse_occ(str(o.get("option") or ""))
        if p is None:
            continue
        _root, exp, right, strike = p
        if exp < ref_day:
            continue
        by_exp.setdefault(exp, [])
        if spot is not None and abs(strike / spot - 1.0) > STRIKE_BAND:
            continue
        iv = _f(o.get("iv"))
        by_exp[exp].append(Opt(
            symbol=str(o.get("option")), expiry=exp, right=right, strike=strike,
            bid=_f(o.get("bid")) or 0.0, ask=_f(o.get("ask")) or 0.0,
            iv=iv if iv and iv > 0 else None, delta=_f(o.get("delta")),
            theta=_f(o.get("theta")), oi=_f(o.get("open_interest")) or 0.0,
            volume=_f(o.get("volume")) or 0.0, gamma=_f(o.get("gamma"))))
    expiries = sorted(by_exp)
    keep = {e: sorted(by_exp[e], key=lambda x: (x.right, x.strike))
            for e in expiries[:KEEP_EXPIRIES]}
    return Chain(sym, spot, iv30, asof, expiries, keep)


# -------------------------------------------------------------------- expiries


def sessions_left(ref: date, exp: date) -> int:
    """Trading days d with ref < d ≤ exp — how many sessions a contract has left
    after the reference day."""
    n = 0
    d = ref
    while d < exp:
        d = date.fromordinal(d.toordinal() + 1)
        if is_trading_day(d):
            n += 1
    return n


def minute_on(ref_day: date, now: datetime) -> int:
    """Minutes into `ref_day` (ET); 0 when `now` is before that day starts —
    overnight, the trading day has not opened, so it is 'before the open'."""
    et = now.astimezone(ET)
    if et.date() < ref_day:
        return 0
    if et.date() > ref_day:
        return 24 * 60
    return et.hour * 60 + et.minute


def pick_expiries(sym: str, expiries: list[date], ref_day: date, minute: int,
                  ) -> dict[str, date | None]:
    """The front and the weekly (module docstring). Pure."""
    usable = []
    for e in expiries:
        if e < ref_day:
            continue
        if e == ref_day:
            if not is_trading_day(ref_day):
                continue
            cutoff = close_minute(ref_day) - (ZERO_DTE_CUTOFF_MIN if sym in DAILY_EXPIRY else 0)
            if minute >= cutoff:
                continue
        usable.append(e)
    front = usable[0] if usable else None
    weekly = next((e for e in usable if sessions_left(ref_day, e) >= WEEKLY_MIN_SESSIONS), None)
    return {"front": front, "weekly": weekly}


# ---------------------------------------------------------------- the readings


def atm_pair(opts: list[Opt], spot: float) -> tuple[Opt, Opt] | None:
    """The call and put at the strike nearest spot that both have a price. Pure."""
    calls = {o.strike: o for o in opts if o.right == "C" and o.mid is not None}
    puts = {o.strike: o for o in opts if o.right == "P" and o.mid is not None}
    both = sorted(set(calls) & set(puts), key=lambda k: (abs(k - spot), k))
    if not both:
        return None
    k = both[0]
    return calls[k], puts[k]


def expected_move(opts: list[Opt], spot: float) -> dict[str, float] | None:
    """The ATM straddle's mid as the options market's expected move. Pure."""
    pair = atm_pair(opts, spot)
    if pair is None:
        return None
    c, p = pair
    straddle = (c.mid or 0.0) + (p.mid or 0.0)
    if straddle <= 0:
        return None
    return {"straddle": round(straddle, 4), "pct": round(straddle / spot * 100.0, 3),
            "lo": round(spot - straddle, 4), "hi": round(spot + straddle, 4)}


def nearest_delta(opts: list[Opt], right: str, target: float) -> Opt | None:
    """The tradable contract (a bid and an ask) whose |delta| is nearest target. Pure."""
    best: Opt | None = None
    for o in opts:
        if o.right != right or o.delta is None or o.bid <= 0 or o.mid is None:
            continue
        if best is None or abs(abs(o.delta) - target) < abs(abs(best.delta or 0) - target):
            best = o
    return best


def skew25(opts: list[Opt]) -> float | None:
    """25-delta put IV minus 25-delta call IV, in vol points. Pure."""
    p = nearest_delta(opts, "P", 0.25)
    c = nearest_delta(opts, "C", 0.25)
    if p is None or c is None or p.iv is None or c.iv is None:
        return None
    return round((p.iv - c.iv) * 100.0, 2)


def liquidity(opts: list[Opt], spot: float) -> dict[str, Any]:
    """The ATM legs' spread as a % of mid, open interest and volume, graded. Pure."""
    pair = atm_pair(opts, spot)
    if pair is None:
        return {"spread_pct": None, "oi": None, "volume": None, "grade": None}
    spreads = [x for x in (pair[0].spread_pct, pair[1].spread_pct) if x is not None]
    sp = sum(spreads) / len(spreads) if spreads else None
    grade = None if sp is None else "good" if sp <= LIQ_GOOD else "ok" if sp <= LIQ_OK else "poor"
    return {"spread_pct": round(sp, 2) if sp is not None else None,
            "oi": pair[0].oi + pair[1].oi, "volume": pair[0].volume + pair[1].volume,
            "grade": grade}


def options_flow(chain: Chain) -> dict[str, Any] | None:
    """Today's volume against open interest, over every contract the chain keeps. Pure.

    The window is the compact summary's: the first KEEP_EXPIRIES expiries from
    the trading day on, strikes within ±STRIKE_BAND of spot — so a summary
    loaded after a restart gives the same answer as the chain it came from.
    Cboe's volume is the session's so far (delayed); before the open it can
    be zero, and then there is no lean to read. Null when nothing is kept.
    """
    opts = [o for exp in chain.opts.values() for o in exp]
    if not opts:
        return None
    call_vol = sum(o.volume for o in opts if o.right == "C")
    put_vol = sum(o.volume for o in opts if o.right == "P")
    call_oi = sum(o.oi for o in opts if o.right == "C")
    put_oi = sum(o.oi for o in opts if o.right == "P")
    vol = call_vol + put_vol
    oi = call_oi + put_oi
    pc = round(put_vol / call_vol, 3) if call_vol > 0 else None
    lean: str | None = None
    if vol >= FLOW_MIN_VOL:
        ratio = pc if pc is not None else math.inf
        lean = "calls" if ratio < FLOW_CALLS else "puts" if ratio > FLOW_PUTS else "balanced"
    busiest = sorted((o for o in opts if o.volume > 0),
                     key=lambda o: (-o.volume, o.expiry, o.right, o.strike))[:FLOW_TOP]
    return {
        "call_vol": int(call_vol), "put_vol": int(put_vol), "pc_vol": pc,
        "call_oi": int(call_oi), "put_oi": int(put_oi),
        "vol_oi": round(vol / oi, 3) if oi > 0 else None,
        "lean": lean,
        "top": [{"strike": o.strike, "right": o.right, "expiry": o.expiry.isoformat(),
                 "volume": int(o.volume), "oi": int(o.oi)} for o in busiest],
    }


def realised_vol(closes: list[float], n: int = RV_SESSIONS) -> float | None:
    """Annualised close-to-close volatility of the last `n` returns, in %. Pure."""
    xs = [c for c in closes if c and c > 0]
    if len(xs) < n + 1:
        return None
    xs = xs[-(n + 1):]
    rets = [math.log(xs[i] / xs[i - 1]) for i in range(1, len(xs))]
    mu = sum(rets) / len(rets)
    var = sum((r - mu) ** 2 for r in rets) / (len(rets) - 1)
    return round(math.sqrt(var) * math.sqrt(252) * 100.0, 3)


def premium(iv_rv: float | None) -> str | None:
    if iv_rv is None:
        return None
    return "cheap" if iv_rv < PREMIUM_CHEAP else "rich" if iv_rv > PREMIUM_RICH else "fair"


def iv_rank(history: list[float], current: float | None) -> tuple[float | None, float | None]:
    """IV rank and percentile of `current` over the logged history (≤ a year),
    null until IV_MIN_DAYS have been logged. Pure."""
    hist = [h for h in history if h is not None][-IV_LOOKBACK:]
    if current is None or len(hist) < IV_MIN_DAYS:
        return None, None
    lo, hi = min(hist), max(hist)
    rank = 50.0 if hi <= lo else (current - lo) / (hi - lo) * 100.0
    pct = sum(1 for h in hist if h < current) / len(hist) * 100.0
    return round(max(0.0, min(100.0, rank)), 1), round(pct, 1)


def spans_earnings(expiry: date, earnings: dict[str, Any] | None) -> bool:
    """Does a contract expiring on `expiry` live through the next report?
    A report before the open on its date lands inside that day's expiry; one
    after the close lands after it. Unknown timing is treated as inside."""
    if not earnings:
        return False
    try:
        d = date.fromisoformat(str(earnings.get("date")))
    except ValueError:
        return False
    if earnings.get("when") == "after":
        return expiry > d
    return expiry >= d


# ------------------------------------------------------------------- the trade


def stock_stop(row: dict[str, Any], side: str) -> tuple[float | None, str]:
    """The stop the contract helper translates, and how it was found (desks
    contract): today's latest (L)/(E) stop while price is still on its side;
    else the entry reference ∓ the Pine's 0.25 bar-ATR buffer; else one bar-ATR
    from the last print. An approximation, said out loud on the page."""
    last = _f(row.get("last"))
    atr_b = _f(row.get("atr_b"))
    if last is None:
        return None, "no price"
    sign = 1.0 if side == "long" else -1.0
    for s in reversed(row.get("signals") or []):
        if s.get("kind") not in ("L", "E") or s.get("side") != side:
            continue
        stop = _f(s.get("stop"))
        if stop is not None and sign * (last - stop) > 0:
            return stop, f"the ({s.get('kind')}) signal's stop"
        break
    entry = (row.get("setup") or {}).get("entry")
    if isinstance(entry, dict) and atr_b:
        price = _f(entry.get("price"))
        if price is not None:
            stop = price - sign * STOP_BUFFER_ATR * atr_b
            if sign * (last - stop) > 0:
                return stop, f"{entry.get('kind')} ∓ the retest buffer"
    if atr_b:
        return last - sign * atr_b, "one ten-minute ATR"
    return None, "no ATR yet"


def live_move(chain: Chain, last: float | None, ref_day: date,
              now: datetime) -> tuple[float, float] | None:
    """(the stock's live price, its move since the chain's spot) while the
    chain's contracts may be re-marked — a same-day chain, 09:30 to the close,
    a move inside REMARK_MAX — else None. Pure."""
    if chain.spot is None or chain.spot <= 0 or last is None or chain.asof is None:
        return None
    et = now.astimezone(ET)
    m = et.hour * 60 + et.minute
    if et.date() != ref_day or not RTH_OPEN <= m < close_minute(ref_day):
        return None
    if chain.asof.astimezone(ET).date() != ref_day:
        return None
    d = last - chain.spot
    if abs(d) > REMARK_MAX * chain.spot:
        return None
    return last, d


def remark(o: Opt, spot: float, d_s: float) -> tuple[float, float] | None:
    """A contract's (mid, delta) at the stock's live `spot`, `d_s` away from the
    chain's: mid + Δ·dS + ½Γ·dS², never below intrinsic; delta + Γ·dS, kept
    inside its side's range. None without a mid or a delta to move. Pure."""
    m = o.mid
    if m is None or o.delta is None:
        return None
    g = o.gamma or 0.0
    intrinsic = max(0.0, spot - o.strike) if o.right == "C" else max(0.0, o.strike - spot)
    mid = max(m + o.delta * d_s + 0.5 * g * d_s * d_s, intrinsic)
    delta = o.delta + g * d_s
    delta = min(max(delta, 0.0), 1.0) if o.right == "C" else min(max(delta, -1.0), 0.0)
    return mid, delta


def _est(est: tuple[float, float] | None, move: tuple[float, float] | None) -> dict[str, Any]:
    """The estimate's fields on a contract — all None when there is none."""
    if est is None or move is None:
        return {"est_mid": None, "est_delta": None, "est_spot": None, "quote_spot": None}
    return {"est_mid": round(est[0], 4), "est_delta": round(est[1], 4),
            "est_spot": round(move[0], 4), "quote_spot": round(move[0] - move[1], 4)}


def _label(dte: int, exp: date) -> str:
    return "0DTE" if dte == 0 else f"{exp.strftime('%a %b')} {exp.day} ({dte}DTE)"


def contract_long(o: Opt, key: str, ref_day: date, stock_risk: float | None,
                  move: tuple[float, float] | None = None) -> dict[str, Any]:
    """The 0.60Δ long. `move` (live_move) re-marks it to the live stock price."""
    dte = (o.expiry - ref_day).days
    mid = o.mid or 0.0
    est = remark(o, *move) if move else None
    px, dl = est if est else (mid, o.delta)
    rpc = None
    if stock_risk is not None and dl is not None:
        rpc = min(stock_risk * abs(dl) * 100.0, px * 100.0)
    word = "call" if o.right == "C" else "put"
    theta = f" — theta {o.theta:+.2f}/day" if o.theta is not None else ""
    return {
        "key": key, "kind": "long", "right": o.right, "expiry": o.expiry.isoformat(), "dte": dte,
        "strike": o.strike, "short_strike": None, "symbol": o.symbol, "short_symbol": None,
        "bid": o.bid, "ask": o.ask, "mid": round(mid, 4), "delta": round(o.delta or 0.0, 4),
        "theta": o.theta, "iv": round(o.iv * 100.0, 2) if o.iv is not None else None,
        "spread_pct": round(o.spread_pct, 2) if o.spread_pct is not None else None,
        "max_value": None,
        "stock_risk": round(stock_risk, 4) if stock_risk is not None else None,
        "risk_per_contract": round(rpc, 2) if rpc is not None else None,
        **_est(est, move),
        "note": f"{abs(o.delta or 0):.2f}Δ {word}, {_label(dte, o.expiry)}{theta}",
    }


def contract_spread(lo: Opt, sh: Opt, key: str, ref_day: date, stock_risk: float | None,
                    move: tuple[float, float] | None = None) -> dict[str, Any] | None:
    """Buy the 0.60Δ, sell the 0.30Δ, same expiry — a debit vertical. Pure.
    `move` re-marks both legs; the estimated debit stays inside [0, width]."""
    if lo.strike == sh.strike or lo.mid is None or sh.mid is None:
        return None
    debit = lo.mid - sh.mid
    if debit <= 0:
        return None
    width = abs(sh.strike - lo.strike)
    net_delta = (lo.delta or 0.0) - (sh.delta or 0.0)
    dte = (lo.expiry - ref_day).days
    est = None
    if move:
        a, b = remark(lo, *move), remark(sh, *move)
        if a and b:
            est = (min(max(a[0] - b[0], 0.0), width), a[1] - b[1])
    px, dl = est if est else (debit, net_delta)
    rpc = None
    if stock_risk is not None:
        rpc = min(stock_risk * abs(dl) * 100.0, px * 100.0)
    word = "call" if lo.right == "C" else "put"
    return {
        "key": key, "kind": "spread", "right": lo.right, "expiry": lo.expiry.isoformat(),
        "dte": dte, "strike": lo.strike, "short_strike": sh.strike, "symbol": lo.symbol,
        "short_symbol": sh.symbol, "bid": round(max(lo.bid - sh.ask, 0.0), 4),
        "ask": round(lo.ask - sh.bid, 4), "mid": round(debit, 4), "delta": round(net_delta, 4),
        "theta": lo.theta, "iv": round(lo.iv * 100.0, 2) if lo.iv is not None else None,
        "spread_pct": round(lo.spread_pct, 2) if lo.spread_pct is not None else None,
        "max_value": round(width, 4),
        "stock_risk": round(stock_risk, 4) if stock_risk is not None else None,
        "risk_per_contract": round(rpc, 2) if rpc is not None else None,
        **_est(est, move),
        "note": (f"{lo.strike:g}/{sh.strike:g} {word} debit spread, {_label(dte, lo.expiry)}"
                 f" — {debit:.2f} for up to {width:.2f}"),
    }


# --------------------------------------------------------------- the row's ctx


def unavailable(error: str, age_min: float | None = None) -> dict[str, Any]:
    """An OptionsCtx for a name with no usable chain."""
    return {
        "ok": False, "error": error, "asof": None, "age_min": age_min, "iv30": None,
        "rv20": None, "iv_rv": None, "premium": None, "iv_rank": None, "iv_pct": None,
        "iv_days": 0, "skew": None, "em": [],
        "liquidity": {"spread_pct": None, "oi": None, "volume": None, "grade": None},
        "zero_dte": False, "earnings_in": None, "contracts": [], "flow": None,
    }


def options_ctx(chain: Chain, row: dict[str, Any], closes: list[float], history: list[float],
                ref_day: date, now: datetime, age_min: float | None) -> dict[str, Any]:
    """The contract's OptionsCtx for one scanner row. Pure."""
    spot = chain.spot or _f(row.get("last"))
    if spot is None or not chain.opts:
        out = unavailable("no contracts in the chain" if spot else "no spot price", age_min)
        out["asof"] = chain.asof.isoformat() if chain.asof else None
        out["iv30"] = chain.iv30
        out["flow"] = options_flow(chain)
        return out
    minute = minute_on(ref_day, now)
    picks = pick_expiries(chain.sym, chain.expiries, ref_day, minute)
    rv = realised_vol(closes)
    iv_rv = round(chain.iv30 / rv, 3) if chain.iv30 is not None and rv else None
    rank, pct = iv_rank(history, chain.iv30)

    em: list[dict[str, Any]] = []
    seen: set[date] = set()
    for key in ("front", "weekly"):
        e = picks[key]
        if e is None or e in seen or e not in chain.opts:
            continue
        seen.add(e)
        m = expected_move(chain.opts[e], spot)
        if m is not None:
            em.append({"key": key, "expiry": e.isoformat(), "dte": (e - ref_day).days, **m})

    front = picks["front"]
    weekly = picks["weekly"] or front
    liq = liquidity(chain.opts.get(front, []) if front else [], spot)
    skew = skew25(chain.opts.get(weekly, [])) if weekly else None

    earnings = row.get("earnings") if isinstance(row.get("earnings"), dict) else None
    if earnings and (earnings.get("days") is None or earnings.get("days", 0) < 0):
        earnings = None
    earnings_in = None
    for key in ("front", "weekly"):
        e = picks[key]
        if e is not None and spans_earnings(e, earnings):
            earnings_in = e.isoformat()
            break

    side = (row.get("setup") or {}).get("side") or (row.get("score") or {}).get("side")
    contracts: list[dict[str, Any]] = []
    if side in ("long", "short"):
        right = "C" if side == "long" else "P"
        stop, _how = stock_stop(row, side)
        last = _f(row.get("last"))
        risk = abs(last - stop) if (stop is not None and last is not None) else None
        move = live_move(chain, last, ref_day, now)
        done: set[date] = set()
        for key in ("front", "weekly"):
            e = picks[key]
            if e is None or e in done or e not in chain.opts:
                continue
            done.add(e)
            opts = chain.opts[e]
            lo = nearest_delta(opts, right, LONG_DELTA)
            if lo is None:
                continue
            contracts.append(contract_long(lo, key, ref_day, risk, move))
            sh = nearest_delta([o for o in opts if (o.strike > lo.strike if right == "C"
                                                    else o.strike < lo.strike)],
                               right, SHORT_DELTA)
            if sh is not None:
                sp = contract_spread(lo, sh, key, ref_day, risk, move)
                if sp is not None:
                    contracts.append(sp)

    return {
        "ok": True, "error": None,
        "asof": chain.asof.isoformat() if chain.asof else None,
        "age_min": age_min,
        "iv30": chain.iv30, "rv20": rv, "iv_rv": iv_rv, "premium": premium(iv_rv),
        "iv_rank": rank, "iv_pct": pct, "iv_days": len(history),
        "skew": skew, "em": em, "liquidity": liq,
        "zero_dte": ref_day in chain.expiries,
        "earnings_in": earnings_in, "contracts": contracts,
        "flow": options_flow(chain),
    }
