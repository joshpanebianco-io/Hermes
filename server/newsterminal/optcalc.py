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

THE EXPIRIES — ONE RULE, STATED ONCE (owner's defaults; audit, 2026-10-14, after
the plan, Settings and the table each kept their own). SPY, QQQ and IWM are the
desk's 0DTE names: their FRONT is today's expiry while it is listed and the
clock is an hour or more before the close (15:00 ET; 12:00 on a half day), else
the next one, and the front is their PICK. Single names list same-day expiries
too now (Wednesdays and Fridays on the big ones), but thinner books and the
pin make the last hours a gamble: a single name's same-day expiry is its front
only until TWO hours before the close (14:00 ET; 11:00 on a half day), and its
pick is always the WEEKLY — the nearest expiry with at least two trading days
still to run, far enough out that one bad session does not decide the trade.
`expiry_rule()` says this in words for the page and the plan's prompt; each
row's `pick` says which contract the rule chose.

RISK IS PRICED FROM THE ENTRY, NOT FROM HERE (audit, 2026-10-14). The setup's
entry is a level — the retest of PDL 543.06 — and its stop the level ∓ the
retest buffer, nineteen cents on MSFT that day; priced from the last print two
dollars away, the card said $119.61 a contract, ten times the trade. So each
contract is re-marked to the ENTRY and to the STOP (delta and gamma off the
chain's own spot, as for the live estimate), and the risk is the difference,
plus half the contract's bid-ask — the cost of getting out at the stop — capped
at what the contract costs at the entry.

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
from collections.abc import Sequence
from dataclasses import dataclass, field
from datetime import UTC, date, datetime, timedelta
from typing import Any, Protocol
from zoneinfo import ZoneInfo

from . import targets
from .holidays import close_minute, is_trading_day

ET = ZoneInfo("America/New_York")

# ---- the rules (documented constants) -----------------------------------------
#: The desk's 0DTE names — daily expiries, and today's is their pick.
DAILY_EXPIRY = frozenset({"SPY", "QQQ", "IWM"})
#: A same-day expiry stops being the front this long before the close: an hour
#: on the 0DTE names, two on a single name (module docstring).
ZERO_DTE_CUTOFF_MIN = 60
SINGLE_ZERO_DTE_CUTOFF_MIN = 120
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


def parse_chain(doc: Any, sym: str, ref_day: date, keep_after: date | None = None) -> Chain:
    """A Cboe delayed-quotes document → a Chain. Pure.

    Expiries before the trading day are dropped (the feed keeps yesterday's
    0DTE listed); so is every strike outside ±STRIKE_BAND of spot, which is
    all a 0.25 delta or an ATM straddle ever needs. `keep_after` keeps one
    more expiry — the first on or after that date, the one that prices a
    report — when it lies beyond the nearest KEEP_EXPIRIES.
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
    kept = list(expiries[:KEEP_EXPIRIES])
    if keep_after is not None:
        extra = next((e for e in expiries if e >= keep_after), None)
        if extra is not None and extra not in kept:
            kept.append(extra)
    keep = {e: sorted(by_exp[e], key=lambda x: (x.right, x.strike)) for e in kept}
    return Chain(sym, spot, iv30, asof, expiries, keep)


def near_expiries(chain: Chain) -> list[date]:
    """The nearest KEEP_EXPIRIES the chain holds — the flow's window, which an
    extra report expiry (parse_chain's `keep_after`) must not widen. Pure."""
    return sorted(chain.opts)[:KEEP_EXPIRIES]


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
            cutoff = close_minute(ref_day) - (ZERO_DTE_CUTOFF_MIN if sym in DAILY_EXPIRY
                                              else SINGLE_ZERO_DTE_CUTOFF_MIN)
            if minute >= cutoff:
                continue
        usable.append(e)
    front = usable[0] if usable else None
    weekly = next((e for e in usable if sessions_left(ref_day, e) >= WEEKLY_MIN_SESSIONS), None)
    return {"front": front, "weekly": weekly}


def pick_key(sym: str) -> str:
    """Which of a name's two contracts the desk would trade: the front on the 0DTE
    names, the weekly on everything else. Pure."""
    return "front" if sym in DAILY_EXPIRY else "weekly"


def _hm_before_close(minutes: int) -> str:
    m = 16 * 60 - minutes
    return f"{m // 60:02d}:{m % 60:02d}"


def expiry_rule() -> dict[str, Any]:
    """The expiry rule in words — the ONE copy the Settings page and the plan's
    prompt print, so neither can drift from the code that applies it. Pure."""
    order = ("SPY", "QQQ", "IWM")
    names: list[str] = sorted(DAILY_EXPIRY, key=lambda s: (s not in order,
                                                          order.index(s) if s in order else 0, s))
    etf = _hm_before_close(ZERO_DTE_CUTOFF_MIN)
    single = _hm_before_close(SINGLE_ZERO_DTE_CUTOFF_MIN)
    return {
        "zero_dte_names": names,
        "etf_cutoff_et": etf,
        "single_cutoff_et": single,
        "weekly_min_sessions": WEEKLY_MIN_SESSIONS,
        "text": (f"{', '.join(names)}: today's expiry (0DTE) is the pick until {etf} ET, then the "
                 f"next one. Single names: a same-day expiry is shown until {single} ET, but the "
                 f"pick is the weekly — the nearest expiry with {WEEKLY_MIN_SESSIONS} or more "
                 f"sessions to run. Half days move both cutoffs three hours earlier."),
    }


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


def term_structure(chain: Chain, spot: float, ref_day: date) -> list[dict[str, Any]]:
    """At-the-money implied volatility per kept expiry, in percent — the
    name's own term structure, front to back. Pure. Event premium shows here
    as a near expiry priced above the ones behind it."""
    out: list[dict[str, Any]] = []
    for e in sorted(chain.opts):
        pair = atm_pair(chain.opts[e], spot)
        if pair is None:
            continue
        ivs = [o.iv for o in pair if o.iv]
        if not ivs:
            continue
        out.append({"expiry": e.isoformat(), "dte": (e - ref_day).days,
                    "iv": round(sum(ivs) / len(ivs) * 100.0, 1)})
    return out


def earnings_move(chain: Chain, spot: float, report: date, when: str | None,
                  ref_day: date) -> dict[str, Any] | None:
    """What the chain prices for a report: the at-the-money straddle of the
    first expiry that covers the reaction day, as a share of spot — and, net
    of the straddle of the last expiry before it, the event alone (the usual
    variance subtraction; "about", since the days between are ignored). Pure.

    A pre-market report reacts on its own day, so that day's expiry covers
    it; an after-hours or untimed report reacts the next session.
    """
    reacts = report if when == "pre" else report + timedelta(days=1)
    exps = sorted(chain.opts)
    covering = next((e for e in exps if e >= reacts), None)
    if covering is None:
        return None
    em = expected_move(chain.opts[covering], spot)
    if em is None:
        return None
    before = [e for e in exps if e < reacts]
    clean = before_pct = None
    before_exp: date | None = None
    if before:
        bm = expected_move(chain.opts[before[-1]], spot)
        if bm is not None:
            before_exp, before_pct = before[-1], bm["pct"]
            clean = round(math.sqrt(max(em["pct"] ** 2 - bm["pct"] ** 2, 0.0)), 2)
    return {
        "report": report.isoformat(), "when": when,
        "expiry": covering.isoformat(), "dte": (covering - ref_day).days,
        "pct": em["pct"], "straddle": em["straddle"],
        "clean_pct": clean,
        "before_expiry": before_exp.isoformat() if before_exp else None,
        "before_pct": before_pct,
    }


class _DayLike(Protocol):
    """A daily bar as the realised moves read it — scan.DayBar fits."""

    @property
    def day(self) -> date: ...
    @property
    def close(self) -> float: ...
    @property
    def volume(self) -> float: ...


def realised_earnings_moves(days: Sequence[_DayLike], reports: list[date],
                            keep: int = 4) -> list[dict[str, Any]]:
    """The close-to-close move across each past report, newest first. Pure.

    THE REACTION DAY IS PICKED BY VOLUME. The report table gives the date and
    not the hour, and a report after the close moves the NEXT session: of the
    report day and the session after it, the one that traded more volume is
    the reaction, and the move is its close against the close before it.
    """
    out: list[dict[str, Any]] = []
    if not days:
        return out
    for rep in sorted(reports, reverse=True):
        i = next((j for j, d in enumerate(days) if d.day >= rep), None)
        if i is None or i == 0:
            continue
        cands = [i] + ([i + 1] if i + 1 < len(days) else [])
        react = max(cands, key=lambda j: days[j].volume)
        prev = days[react - 1].close
        if not prev:
            continue
        out.append({"date": rep.isoformat(), "reaction": days[react].day.isoformat(),
                    "pct": round((days[react].close / prev - 1.0) * 100.0, 2)})
        if len(out) >= keep:
            break
    return out


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


#: Today's chain volume at or past this multiple of its 20-day average, with at
#: least FLOW_MIN_VOL contracts, reads as unusual.
UNUSUAL_X = 2.0


def options_flow(chain: Chain, prev: dict[str, Any] | None = None,
                 vol_hist: list[float] | None = None) -> dict[str, Any] | None:
    """Today's volume against open interest, over every contract the chain keeps. Pure.

    `prev` is the previous session's open interest for the same name — its
    totals and a {contract: oi} map (sources/options.OiLog) — for the change
    in positioning since yesterday; `vol_hist` the chain's end-of-day volumes
    over the sessions before today, for whether today is unusual.

    The window is the compact summary's: the first KEEP_EXPIRIES expiries from
    the trading day on, strikes within ±STRIKE_BAND of spot — so a summary
    loaded after a restart gives the same answer as the chain it came from.
    Cboe's volume is the session's so far (delayed); before the open it can
    be zero, and then there is no lean to read. Null when nothing is kept.
    """
    opts = [o for exp in near_expiries(chain) for o in chain.opts[exp]]
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
    by_prev: dict[str, float] = (prev or {}).get("by") or {}
    pc_oi = _f((prev or {}).get("call_oi")), _f((prev or {}).get("put_oi"))
    hist = [v for v in (vol_hist or []) if v and v > 0]
    avg20 = sum(hist[-20:]) / len(hist[-20:]) if hist else None
    vol_x = round(vol / avg20, 2) if avg20 else None
    return {
        "call_vol": int(call_vol), "put_vol": int(put_vol), "pc_vol": pc,
        "call_oi": int(call_oi), "put_oi": int(put_oi),
        "vol_oi": round(vol / oi, 3) if oi > 0 else None,
        "lean": lean,
        "top": [{"strike": o.strike, "right": o.right, "expiry": o.expiry.isoformat(),
                 "volume": int(o.volume), "oi": int(o.oi),
                 "oi_chg": int(o.oi - by_prev[o.symbol]) if o.symbol in by_prev else None}
                for o in busiest],
        # Since the previous session: the change in open interest on each side
        # (null before a second session is logged), and today's volume against
        # the name's own 20-session average.
        "oi_chg_calls": int(call_oi - pc_oi[0]) if pc_oi[0] is not None else None,
        "oi_chg_puts": int(put_oi - pc_oi[1]) if pc_oi[1] is not None else None,
        "oi_prev_day": (prev or {}).get("day"),
        "vol_avg20": round(avg20) if avg20 else None,
        "vol_x": vol_x,
        "vol_days": len(hist),
        "unusual": bool(vol_x is not None and vol_x >= UNUSUAL_X and vol >= FLOW_MIN_VOL),
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


@dataclass(frozen=True)
class Plan:
    """The stock-level trade a contract is sized against: where it is entered,
    where it is stopped, how that was found, and the spot the chain was quoted
    at (what the contracts are re-marked from)."""

    entry: float
    stop: float
    how: str
    spot: float


def trade_plan(row: dict[str, Any], side: str) -> tuple[float | None, float | None, str]:
    """(entry, stop, how) for the row's side (desks contract): today's latest
    (L)/(E) — its price and its stop — while price is still on its side of the
    stop; else the setup's entry reference and that ∓ the Pine's 0.25 bar-ATR
    buffer; else the last print and one bar-ATR from it. An approximation, said
    out loud on the page."""
    last = _f(row.get("last"))
    atr_b = _f(row.get("atr_b"))
    if last is None:
        return None, None, "no price"
    sign = 1.0 if side == "long" else -1.0
    for s in reversed(row.get("signals") or []):
        if s.get("kind") not in ("L", "E") or s.get("side") != side:
            continue
        stop, price = _f(s.get("stop")), _f(s.get("price"))
        if stop is not None and price is not None and sign * (last - stop) > 0:
            return price, stop, f"the ({s.get('kind')}) signal's stop"
        break
    entry = (row.get("setup") or {}).get("entry")
    if isinstance(entry, dict) and atr_b:
        price = _f(entry.get("price"))
        if price is not None:
            stop = price - sign * STOP_BUFFER_ATR * atr_b
            if sign * (last - stop) > 0:
                return price, stop, f"{entry.get('kind')} ∓ the retest buffer"
    if atr_b:
        return last, last - sign * atr_b, "one ten-minute ATR"
    return None, None, "no ATR yet"


def stock_stop(row: dict[str, Any], side: str) -> tuple[float | None, str]:
    """The stop alone — `trade_plan` without its entry."""
    _entry, stop, how = trade_plan(row, side)
    return stop, how


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


def _at(o: Opt, price: float, spot: float) -> tuple[float, float] | None:
    """A contract's (mid, delta) with the stock at `price`, re-marked from the
    chain's `spot` — None past REMARK_MAX, where a second-order step is a guess."""
    if spot <= 0 or abs(price - spot) > REMARK_MAX * spot:
        return None
    return remark(o, price, price - spot)


def _plan_fields(plan: Plan | None, stock_risk: float | None,
                 entry_mid: float | None) -> dict[str, Any]:
    return {
        "stock_entry": round(plan.entry, 4) if plan else None,
        "stock_stop": round(plan.stop, 4) if plan else None,
        "stock_risk": round(stock_risk, 4) if stock_risk is not None else None,
        "risk_basis": plan.how if plan else None,
        "entry_mid": round(entry_mid, 4) if entry_mid is not None else None,
    }


def _intrinsic(o: Opt, price: float) -> float:
    return max(0.0, price - o.strike) if o.right == "C" else max(0.0, o.strike - price)


def _target_fields(target: tuple[float, str] | None, value_at: Any,
                   floor_at: Any, entry_mid: float | None, rpc: float | None,
                   half: float) -> dict[str, Any]:
    """The contract at the first target: its value there (delta and gamma
    inside REMARK_MAX of the chain's spot, intrinsic value as a floor beyond
    it), the reward per contract after half the bid-ask to get out, and that
    against the risk — the option's own R. Pure."""
    out: dict[str, Any] = {"target_price": None, "target_label": None, "target_mid": None,
                           "target_basis": None, "reward_per_contract": None,
                           "r_multiple": None}
    if target is None or entry_mid is None:
        return out
    price, label = target
    at = value_at(price)
    if at is not None:
        t_mid, basis = at[0], "delta and gamma"
    else:
        t_mid = floor_at(price)
        basis = "intrinsic value — the target is beyond the re-mark range"
    reward = max(t_mid - entry_mid - half, 0.0) * 100.0
    out.update({
        "target_price": round(price, 4), "target_label": label, "target_mid": round(t_mid, 4),
        "target_basis": basis, "reward_per_contract": round(reward, 2),
        "r_multiple": round(reward / rpc, 2) if rpc else None,
    })
    return out


def _label(dte: int, exp: date) -> str:
    return "0DTE" if dte == 0 else f"{exp.strftime('%a %b')} {exp.day} ({dte}DTE)"


def contract_long(o: Opt, key: str, ref_day: date, stock_risk: float | None,
                  move: tuple[float, float] | None = None,
                  plan: Plan | None = None,
                  target: tuple[float, str] | None = None) -> dict[str, Any]:
    """The 0.60Δ long. `move` (live_move) re-marks it to the live stock price;
    `plan` prices its risk from the entry to the stop (module docstring);
    `target` (price, label) prices it at the first target for its R."""
    dte = (o.expiry - ref_day).days
    mid = o.mid or 0.0
    est = remark(o, *move) if move else None
    px, dl = est if est else (mid, o.delta)
    half = (o.ask - o.bid) / 2.0 if o.mid is not None else 0.0
    rpc = entry_mid = None
    if plan is not None:
        a, b = _at(o, plan.entry, plan.spot), _at(o, plan.stop, plan.spot)
        if a and b:
            entry_mid = a[0]
            rpc = min(max(a[0] - b[0], 0.0) + half, a[0]) * 100.0
    if rpc is None and stock_risk is not None and dl is not None:
        # Entry or stop past REMARK_MAX: today's delta, straight-line.
        rpc = min(stock_risk * abs(dl) + half, px) * 100.0
    word = "call" if o.right == "C" else "put"
    theta = f" — theta {o.theta:+.2f}/day" if o.theta is not None else ""
    tf = _target_fields(target if plan is not None else None,
                        lambda price: _at(o, price, plan.spot) if plan else None,
                        lambda price: _intrinsic(o, price),
                        entry_mid if entry_mid is not None else px, rpc, half)
    return {
        "key": key, "kind": "long", "right": o.right, "expiry": o.expiry.isoformat(), "dte": dte,
        "strike": o.strike, "short_strike": None, "symbol": o.symbol, "short_symbol": None,
        "bid": o.bid, "ask": o.ask, "mid": round(mid, 4), "delta": round(o.delta or 0.0, 4),
        "theta": o.theta, "iv": round(o.iv * 100.0, 2) if o.iv is not None else None,
        "short_iv": None,
        "spread_pct": round(o.spread_pct, 2) if o.spread_pct is not None else None,
        "max_value": None,
        **_plan_fields(plan, stock_risk, entry_mid),
        "risk_per_contract": round(rpc, 2) if rpc is not None else None,
        **tf,
        **_est(est, move),
        "note": f"{abs(o.delta or 0):.2f}Δ {word}, {_label(dte, o.expiry)}{theta}",
    }


def contract_spread(lo: Opt, sh: Opt, key: str, ref_day: date, stock_risk: float | None,
                    move: tuple[float, float] | None = None,
                    plan: Plan | None = None,
                    target: tuple[float, str] | None = None) -> dict[str, Any] | None:
    """Buy the 0.60Δ, sell the 0.30Δ, same expiry — a debit vertical. Pure.

    THE SPREAD'S OWN FIGURES, NOT ITS LONG LEG'S (audit, 2026-10-14: the card
    printed the long leg's theta and a 6.7% spread on a spread whose natural
    market was 1.94 / 2.32 — 17.8%). Theta is the net of the legs; the bid-ask
    is the natural one, long bid − short ask to long ask − short bid, as a share
    of the net mid; IV is both legs'. `move` re-marks both legs, `plan` prices
    the risk from the entry to the stop; the debit stays inside [0, width].
    """
    if lo.strike == sh.strike or lo.mid is None or sh.mid is None:
        return None
    debit = lo.mid - sh.mid
    if debit <= 0:
        return None
    width = abs(sh.strike - lo.strike)
    net_delta = (lo.delta or 0.0) - (sh.delta or 0.0)
    nat_bid, nat_ask = max(lo.bid - sh.ask, 0.0), lo.ask - sh.bid
    half = (nat_ask - nat_bid) / 2.0
    dte = (lo.expiry - ref_day).days

    def net_at(price: float, spot: float) -> tuple[float, float] | None:
        a, b = _at(lo, price, spot), _at(sh, price, spot)
        return (min(max(a[0] - b[0], 0.0), width), a[1] - b[1]) if a and b else None

    est = None
    if move:
        ma, mb = remark(lo, *move), remark(sh, *move)
        if ma and mb:
            est = (min(max(ma[0] - mb[0], 0.0), width), ma[1] - mb[1])
    px, dl = est if est else (debit, net_delta)
    rpc = entry_mid = None
    if plan is not None:
        at_entry, at_stop = net_at(plan.entry, plan.spot), net_at(plan.stop, plan.spot)
        if at_entry and at_stop:
            entry_mid = at_entry[0]
            rpc = min(max(at_entry[0] - at_stop[0], 0.0) + half, at_entry[0]) * 100.0
    if rpc is None and stock_risk is not None:
        rpc = min(stock_risk * abs(dl) + half, px) * 100.0
    theta = (lo.theta - sh.theta) if lo.theta is not None and sh.theta is not None else None
    word = "call" if lo.right == "C" else "put"
    tf = _target_fields(target if plan is not None else None,
                        lambda price: net_at(price, plan.spot) if plan else None,
                        lambda price: min(max(_intrinsic(lo, price) - _intrinsic(sh, price), 0.0),
                                          width),
                        entry_mid if entry_mid is not None else px, rpc, half)
    return {
        "key": key, "kind": "spread", "right": lo.right, "expiry": lo.expiry.isoformat(),
        "dte": dte, "strike": lo.strike, "short_strike": sh.strike, "symbol": lo.symbol,
        "short_symbol": sh.symbol, "bid": round(nat_bid, 4),
        "ask": round(nat_ask, 4), "mid": round(debit, 4), "delta": round(net_delta, 4),
        "theta": round(theta, 4) if theta is not None else None,
        "iv": round(lo.iv * 100.0, 2) if lo.iv is not None else None,
        "short_iv": round(sh.iv * 100.0, 2) if sh.iv is not None else None,
        "spread_pct": round((nat_ask - nat_bid) / debit * 100.0, 2),
        "max_value": round(width, 4),
        **_plan_fields(plan, stock_risk, entry_mid),
        "risk_per_contract": round(rpc, 2) if rpc is not None else None,
        **tf,
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
        "zero_dte": False, "pick": None, "earnings_in": None, "contracts": [],
        "structure": None, "targets": [], "term": [], "earnings_move": None, "flow": None,
    }


def structure_pick(contracts: list[dict[str, Any]], pick: str,
                   prem: str | None) -> dict[str, Any]:
    """Long option or debit spread, for the expiry the rule picks: whichever
    has the better R at the first target when both are priced, else the
    premium rule — the spread when premium is rich, the long otherwise. Pure.
    A difference inside 0.05 R is a tie, settled by premium."""
    mine = {c["kind"]: c for c in contracts if c.get("key") == pick}
    lr = (mine.get("long") or {}).get("r_multiple")
    sr = (mine.get("spread") or {}).get("r_multiple")
    if lr is not None and sr is not None and abs(lr - sr) > 0.05:
        return {"kind": "long" if lr > sr else "spread", "by": "r", "long_r": lr, "spread_r": sr}
    return {"kind": "spread" if prem == "rich" else "long", "by": "premium",
            "long_r": lr, "spread_r": sr}


def options_ctx(chain: Chain, row: dict[str, Any], closes: list[float], history: list[float],
                ref_day: date, now: datetime, age_min: float | None,
                reports: list[date] | None = None,
                daily: list[Any] | None = None,
                oi_prev: dict[str, Any] | None = None,
                vol_hist: list[float] | None = None) -> dict[str, Any]:
    """The contract's OptionsCtx for one scanner row. Pure.

    `reports` are the name's past report dates and `daily` its daily bars,
    for the realised earnings moves; `oi_prev` and `vol_hist` the previous
    session's open interest and the chain's volume history (options_flow).
    All optional.
    """
    spot = chain.spot or _f(row.get("last"))
    if spot is None or not chain.opts:
        out = unavailable("no contracts in the chain" if spot else "no spot price", age_min)
        out["asof"] = chain.asof.isoformat() if chain.asof else None
        out["iv30"] = chain.iv30
        out["flow"] = options_flow(chain, oi_prev, vol_hist)
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

    # THE EARNINGS NUMBER: what the chain prices for the report against what
    # the name did on its last few. Only with a report ahead and a date.
    implied_earn = None
    if earnings:
        try:
            rep_day = date.fromisoformat(str(earnings.get("date")))
            implied_earn = earnings_move(chain, spot, rep_day, earnings.get("when"), ref_day)
        except ValueError:
            implied_earn = None
    realised = realised_earnings_moves(daily or [], reports or []) if daily and reports else []
    abs_moves = [abs(m["pct"]) for m in realised]
    earn_block = None
    if implied_earn is not None or realised:
        earn_block = {
            "implied": implied_earn, "realised": realised,
            "avg_abs": round(sum(abs_moves) / len(abs_moves), 2) if abs_moves else None,
            "max_abs": round(max(abs_moves), 2) if abs_moves else None,
        }

    side = (row.get("setup") or {}).get("side") or (row.get("score") or {}).get("side")
    entry: float | None = None
    stop: float | None = None
    how = ""
    if side in ("long", "short"):
        entry, stop, how = trade_plan(row, side)

    # THE FIRST TARGET, by the plan's own rule (targets.py), from the row and
    # the front straddle — measured from the SAME ENTRY the contract is
    # priced from (trade_plan: today's signal where there is one, else the
    # setup's reference), so the target the card prices at is on the right
    # side of the entry it prices from.
    em_front = next((e for e in em if e["key"] == "front"), None)
    tv = targets.view(row, em_front)
    if entry is not None:
        tv["entry"] = {"price": entry}
    tgts = targets.target_candidates(tv)
    target = (float(tgts[0]["price"]), str(tgts[0]["label"])) if tgts else None

    contracts: list[dict[str, Any]] = []
    if side in ("long", "short") and entry is not None:
        right = "C" if side == "long" else "P"
        last = _f(row.get("last"))
        risk = abs(entry - stop) if (stop is not None and entry is not None) else None
        plan = (Plan(entry, stop, how, spot)
                if risk and entry is not None and stop is not None else None)
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
            contracts.append(contract_long(lo, key, ref_day, risk, move, plan, target))
            sh = nearest_delta([o for o in opts if (o.strike > lo.strike if right == "C"
                                                    else o.strike < lo.strike)],
                               right, SHORT_DELTA)
            if sh is not None:
                sp = contract_spread(lo, sh, key, ref_day, risk, move, plan, target)
                if sp is not None:
                    contracts.append(sp)
    pick = pick_key(chain.sym)
    structure = structure_pick(contracts, pick, premium(iv_rv)) if contracts else None
    for c in contracts:
        c["better_r"] = bool(structure and structure["by"] == "r" and c["key"] == pick
                             and c["kind"] == structure["kind"])

    return {
        "ok": True, "error": None,
        "asof": chain.asof.isoformat() if chain.asof else None,
        "age_min": age_min,
        "iv30": chain.iv30, "rv20": rv, "iv_rv": iv_rv, "premium": premium(iv_rv),
        "iv_rank": rank, "iv_pct": pct, "iv_days": len(history),
        "skew": skew, "em": em, "liquidity": liq,
        "zero_dte": ref_day in chain.expiries,
        # The contract the expiry rule picks for this name (expiry_rule).
        "pick": pick,
        "earnings_in": earnings_in, "contracts": contracts,
        # Long or spread, by R at the first target when both are priced
        # (structure_pick); the targets the row's plan may take; the name's
        # own term structure; and the earnings number.
        "structure": structure,
        "targets": tgts,
        "term": term_structure(chain, spot, ref_day),
        "earnings_move": earn_block,
        "flow": options_flow(chain, oi_prev, vol_hist),
    }
