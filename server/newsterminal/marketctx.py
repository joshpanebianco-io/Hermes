"""
The Market tab's context — what adds conviction to a stock or options trade.

Owner instruction, 2026-10-14: "make sure in the market tab we have everything
that is worth having that helps add more context and confidence to stock and
options". Everything here is COMPUTED, from inputs the collector already holds;
the page prints it and the Game plan is shown it, and none of it is the
model's.

THE TAPE COUNT. Eleven independent reads of the tape, each a vote — long,
short or neutral — with its threshold stated as a constant below, so a vote
the reader disagrees with can be traced to the number that cast it. The
grade is arithmetic on the count, and its `max_conviction` is the ceiling the
Game plan's convictions are capped at. A read whose input is missing is a
NEUTRAL vote that says why, never a guess: a count that quietly drops a vote
reads stronger than it is.

THE CASH MARKET DOES NOT VOTE BEFORE IT OPENS. Before 09:30 the sector SPDRs,
RSP and the index constituents still carry yesterday's change (the board
reads Yahoo's regular-session price), so those reads are neutral pre-market
and say so; the index ETFs vote on their pre-market gap instead of their
levels, and index volume starts at the open. A quote whose last trade is not
from the trading day is likewise not a vote before the bell.

OVERNIGHT IS BEFORE THE OPEN TOO (audit, 2026-10-14). From 20:00 the scanner's
trading day is the NEXT session, and the tab is read to plan it — but the
votes went neutral only in "pre", so all evening the session just finished
voted as if live ("Index leaders 23 up · 36 down" casting a short vote at
22:00 that capped the Game plan's conviction, and flipped to neutral at 04:00
on the same numbers). "closed" now reads like "pre": the levels vote on the
after-hours move, and the cash reads wait for the open they are about.

EVERY BLOCK DEGRADES ON ITS OWN. Breadth without the constituents keeps its
sector count; gamma is null whenever the terminal's optional gamma feed is off
or down, and nothing else changes; the fuel row for IWM has no implied move
unless IWM's own chain has given an implied volatility.

PURE. `build` and `conviction_for` take the scanner payload and the pieces of
the snapshot they read, and do no I/O.
"""

from __future__ import annotations

import math
import re
from datetime import UTC, date, datetime, timedelta
from typing import Any
from zoneinfo import ZoneInfo

from . import releases
from .holidays import next_trading_day
from .policy import HOLD_BAND_BP
from .volterm import SQRT252, fuel_word
from .volterm import state as volterm_state

ET = ZoneInfo("America/New_York")

# ---- the votes' thresholds ------------------------------------------------------
GAP_FLAT = 0.15  # % — a pre-market gap smaller than this casts no level vote
VIX_FLAT = 1.5  # % — VIX's day change inside this is no vote (scanscore's VIX_FLAT)
CURVE_CALM = 0.90  # VIX ÷ VIX3M below this: steep contango, a calm tape → long
CURVE_STRESS = 1.00  # at or above: flat-to-inverted, protection bid now → short
SECTOR_SHARE = 0.6  # share of the reporting sectors moving one way for a vote (7 of 11)
SECTOR_MIN = 6  # fewer sectors reporting than this: no vote
RSP_EDGE = 0.25  # pp — RSP minus SPY beyond this: the average stock leads / lags the index
HYG_FLAT = 0.15  # % — high yield's day move inside this is no vote
YIELD_BP = 4.0  # bp — the 10Y's day change at or beyond this votes (rising → short)
DXY_FLAT = 0.25  # % — the dollar's day move at or beyond this votes (rising → short)
RVOL_HEAVY = 1.2  # index RVOL at or above this: the move is on real volume
RVOL_LIGHT = 0.8  # below this: thin
INDEX_FLAT = 0.15  # % — SPY moved less than this: no direction for volume to confirm
PART_LONG = 60.0  # % of the index leaders up, at or above → long
PART_SHORT = 40.0  # at or below → short
PART_MIN = 20  # fewer leaders reporting than this: no vote

# ---- the grade --------------------------------------------------------------------
STRONG_AGREE = 6
STRONG_AGAINST = 1
MODERATE_AGREE = 4
MAX_CONVICTION = {"strong": 5, "moderate": 4, "weak": 3, "none": 2}

# ---- fuel: how much of the implied move the index has used ------------------------
# The thresholds (volterm.FUEL_ROOM / FUEL_STRETCHED) and the word are volterm's,
# which reads the same rule for the futures books: one rule, stated once, and
# imported here because this module already imports volterm for the curve.
FUEL_VOL = {"SPY": "VIX", "QQQ": "VXN"}  # the index vol each ETF's implied move is read from

# ---- prints -----------------------------------------------------------------------
PRINT_SCORE = 3
# THE READ IS RELEASES' NOW (hot / cold / inline, and what each means per
# book): the futures Calendar and the driver board read the same prints, so
# the rule is stated once, there. Re-exported for the tests that pin it.
INLINE_REL = releases.INLINE_REL
read_of = releases.read_of

INDEX_ETFS = ("SPY", "QQQ", "IWM")
_NOT_SECTORS = frozenset({"SPY", "RSP"})
_BOOKS = (("NQ", "NDX"), ("ES", "SPX"))
_GAMMA = (("QQQ", "NQ"), ("SPY", "ES"))
FED_PATH = 4
PEER_DAYS = 3  # trading days ahead a report counts as "this week's"

MACRO_PCT: list[tuple[str, str]] = [
    ("DXY", "Dollar (DXY)"), ("HYG", "High yield (HYG)"), ("TLT", "Long bonds (TLT)"),
    ("WTI", "WTI crude"), ("GC", "Gold"), ("BTC", "Bitcoin"),
]


# ------------------------------------------------------------------- helpers


def _num(v: Any) -> float | None:
    if isinstance(v, bool) or not isinstance(v, (int, float)) or math.isnan(float(v)):
        return None
    return float(v)


def _r(v: float | None, dp: int) -> float | None:
    return None if v is None else round(v, dp)


def _q(quotes: list[dict[str, Any]], key: str) -> dict[str, Any] | None:
    return next((q for q in quotes if isinstance(q, dict) and q.get("key") == key), None)


def _signed(x: float, dp: int, unit: str = "") -> str:
    """+1.25% / −4bp — a real minus sign, the way the page prints it."""
    return f"{'−' if x < 0 else '+'}{abs(x):.{dp}f}{unit}"


def _vote(key: str, label: str, value: str, vote: str, note: str) -> dict[str, Any]:
    return {"key": key, "label": label, "value": value, "vote": vote, "note": note}


def _side(x: float, long_at: float, short_at: float) -> str:
    """long when x ≥ long_at, short when x ≤ short_at, else neutral."""
    return "long" if x >= long_at else "short" if x <= short_at else "neutral"


def _trading_day(scan: dict[str, Any], now: datetime) -> date:
    """The scanner's trading day — the session the tab is read for — else today."""
    try:
        return date.fromisoformat(str(scan.get("trading_day"))[:10])
    except ValueError:
        return now.astimezone(ET).date()


def _rows(scan: dict[str, Any]) -> dict[str, dict[str, Any]]:
    return {str(r.get("sym")): r for r in scan.get("rows") or []
            if isinstance(r, dict) and r.get("ok")}


def _before_open(session: str) -> bool:
    """The pre-market, and overnight / the weekend — read for the session ahead."""
    return session in ("pre", "closed")


def _fresh(q: dict[str, Any], session: str, now: datetime, td: date | None = None) -> bool:
    """Whether a quote has traded on the trading day `td` (today when not given).
    Only asked before the bell: in the session a regular-market quote is the day's
    by definition. An unstamped quote is trusted."""
    if not _before_open(session):
        return True
    t = _num(q.get("quote_time"))
    if t is None:
        return True
    return datetime.fromtimestamp(t, ET).date() >= (td or now.astimezone(ET).date())


def _on(td: date | None, now: datetime) -> str:
    """"today", or "on Wed" when the trading day is a later one (overnight)."""
    return "today" if td is None or td == now.astimezone(ET).date() else f"on {td:%a}"


def _quote(quotes: list[dict[str, Any]], key: str, field: str, session: str,
           now: datetime, td: date | None = None
           ) -> tuple[dict[str, Any] | None, float | None, str | None]:
    """(quote, the field, why it is missing). The field is None with a reason when the
    quote is absent, has no value, or has not traded today before the bell."""
    q = _q(quotes, key)
    if q is None:
        return None, None, f"no {key} quote on the board"
    v = _num(q.get(field))
    if v is None:
        return q, None, f"{key} has no change yet"
    if not _fresh(q, session, now, td):
        return q, None, f"{key} has not traded {_on(td, now)} yet — it votes once it does"
    return q, v, None


def _sector_moves(sectors: list[dict[str, Any]]) -> list[float]:
    return [v for s in sectors if isinstance(s, dict) and s.get("key") not in _NOT_SECTORS
            and (v := _num(s.get("day_pct"))) is not None]


def _sector_pct(sectors: list[dict[str, Any]], key: str) -> float | None:
    s = next((s for s in sectors if isinstance(s, dict) and s.get("key") == key), None)
    return _num(s.get("day_pct")) if s else None


def _leaders(constituents: dict[str, Any] | None) -> dict[str, float]:
    """Each index leader's day change, once — NDX and SPX share most of their top names."""
    out: dict[str, float] = {}
    for book, _ in _BOOKS:
        ix = ((constituents or {}).get("indices") or {}).get(book) or {}
        for m in ix.get("members") or []:
            if isinstance(m, dict) and (p := _num(m.get("pct"))) is not None:
                out.setdefault(str(m.get("symbol")), p)
    return out


# --------------------------------------------------------------------- votes


def _levels_vote(key: str, sym: str, row: dict[str, Any] | None,
                 session: str) -> dict[str, Any]:
    label = f"{sym} vs its levels"
    if row is None:
        return _vote(key, label, "—", "neutral", f"no {sym} bars yet")
    if _before_open(session):
        gap = _num(row.get("ext_pct"))
        if gap is None:
            return _vote(key, label, "—", "neutral",
                         "no extended-hours print yet — before the open it votes on the gap")
        v = _side(gap, GAP_FLAT, -GAP_FLAT)
        why = {"long": "gapping up", "short": "gapping down",
               "neutral": f"a gap inside ±{GAP_FLAT}% is no lean"}[v]
        return _vote(key, label, f"gap {_signed(gap, 2, '%')}", v,
                     f"{why} — the levels set at the open, so pre-market it votes on the gap")
    state = int(_num(row.get("lvl_state")) or 0)
    last = _num(row.get("last"))
    lv = row.get("levels") or {}
    if state > 0:
        hit = [k.upper() for k in ("pdh", "pmh")
               if last is not None and (x := _num(lv.get(k))) is not None and last > x]
        return _vote(key, label, "▲ above " + (" & ".join(hit) or "its highs"), "long",
                     "through its highs — the strategy's long side")
    if state < 0:
        hit = [k.upper() for k in ("pdl", "pml")
               if last is not None and (x := _num(lv.get(k))) is not None and last < x]
        return _vote(key, label, "▼ below " + (" & ".join(hit) or "its lows"), "short",
                     "through its lows — the strategy's short side")
    return _vote(key, label, "inside its levels", "neutral",
                 "between its highs and lows — no break to lean on")


def _vix_dir(quotes: list[dict[str, Any]], session: str, now: datetime,
             td: date | None = None) -> dict[str, Any]:
    key, label = "vix_dir", "VIX direction"
    q, pct, why = _quote(quotes, "VIX", "pct", session, now, td)
    if pct is None or q is None:
        return _vote(key, label, "—", "neutral", why or "no VIX")
    v = _side(-pct, VIX_FLAT, -VIX_FLAT)
    last = _num(q.get("last"))
    value = (f"{last:.2f} " if last is not None else "") + _signed(pct, 1, "%")
    note = {"long": "VIX falling — protection being sold under the tape",
            "short": "VIX rising — protection being bought",
            "neutral": f"VIX inside ±{VIX_FLAT}% — no read"}[v]
    return _vote(key, label, value, v, note)


def _vix_curve(quotes: list[dict[str, Any]], session: str, now: datetime,
               td: date | None = None) -> dict[str, Any]:
    key, label = "vix_curve", "VIX curve"
    vt = volterm_state(quotes)
    ratio = _num(vt.get("ratio"))
    if ratio is None:
        return _vote(key, label, "—", "neutral", "VIX or VIX3M missing from the board")
    q = _q(quotes, "VIX")
    if q is not None and not _fresh(q, session, now, td):
        return _vote(key, label, f"{ratio:.2f}", "neutral",
                     f"VIX has not traded {_on(td, now)} yet — the curve votes once it does")
    v = "long" if ratio < CURVE_CALM else "short" if ratio >= CURVE_STRESS else "neutral"
    note = {"long": f"VIX ÷ VIX3M under {CURVE_CALM:.2f}: steep contango, a calm tape",
            "short": f"VIX ÷ VIX3M at {CURVE_STRESS:.2f} or more: near-dated protection bid",
            "neutral": f"between {CURVE_CALM:.2f} and {CURVE_STRESS:.2f}: neither calm nor "
                       "stressed"}[v]
    return _vote(key, label, f"{ratio:.2f} · {vt.get('shape') or 'unknown'}", v, note)


def _sectors_vote(sectors: list[dict[str, Any]], session: str) -> dict[str, Any]:
    key, label = "sectors", "Sectors moving"
    moves = _sector_moves(sectors)
    up, down, n = sum(m > 0 for m in moves), sum(m < 0 for m in moves), len(moves)
    value = f"{up} up · {down} down" if n else "—"
    if _before_open(session):
        return _vote(key, label, value, "neutral",
                     "the last session's count — the sector SPDRs vote from the open")
    if n < SECTOR_MIN:
        return _vote(key, label, value, "neutral", f"only {n} sectors reporting")
    need = math.ceil(SECTOR_SHARE * n)
    if up >= need:
        return _vote(key, label, value, "long", f"{up} of {n} sectors up — a broad bid")
    if down >= need:
        return _vote(key, label, value, "short", f"{down} of {n} sectors down — broad selling")
    return _vote(key, label, value, "neutral", f"mixed — neither side has {need} of {n}")


def _equal_weight(sectors: list[dict[str, Any]], session: str) -> dict[str, Any]:
    key, label = "equal_weight", "Equal weight vs SPY"
    rsp, spy = _sector_pct(sectors, "RSP"), _sector_pct(sectors, "SPY")
    if rsp is None or spy is None:
        return _vote(key, label, "—", "neutral", "RSP or SPY missing from the sectors")
    spread = rsp - spy
    value = f"RSP {_signed(rsp, 2, '%')} vs SPY {_signed(spy, 2, '%')}"
    if _before_open(session):
        return _vote(key, label, value, "neutral",
                     "the last session's figures — votes from the open")
    v = _side(spread, RSP_EDGE, -RSP_EDGE)
    note = {"long": "the average stock is beating the index — broad participation",
            "short": "the index is leaning on its megacaps — the average stock lags",
            "neutral": f"within ±{RSP_EDGE}pp of the index — no read"}[v]
    return _vote(key, label, value, v, note)


def _pct_vote(quotes: list[dict[str, Any]], session: str, now: datetime, *, key: str,
              label: str, sym: str, flat: float, rising: str,
              notes: tuple[str, str], td: date | None = None) -> dict[str, Any]:
    """A vote on one quote's day change: `rising` is the side a rise votes for."""
    q, pct, why = _quote(quotes, sym, "pct", session, now, td)
    if pct is None or q is None:
        return _vote(key, label, "—", "neutral", why or f"no {sym}")
    last = _num(q.get("last"))
    value = f"{sym} " + (f"{last:.2f} " if last is not None else "") + _signed(pct, 2, "%")
    if abs(pct) < flat:
        return _vote(key, label, value, "neutral", f"inside ±{flat}% — no read")
    up = pct > 0
    falling = "short" if rising == "long" else "long"
    return _vote(key, label, value, rising if up else falling, notes[0] if up else notes[1])


def _yields(quotes: list[dict[str, Any]], session: str, now: datetime,
            td: date | None = None) -> dict[str, Any]:
    key, label = "yields", "10Y yield"
    q, chg, why = _quote(quotes, "US10Y", "chg", session, now, td)
    if chg is None or q is None:
        return _vote(key, label, "—", "neutral", why or "no 10Y")
    bp = chg * 100.0
    last = _num(q.get("last"))
    value = (f"{last:.2f}% " if last is not None else "") + _signed(bp, 1, "bp")
    v = _side(-bp, YIELD_BP, -YIELD_BP)
    note = {"long": "yields falling — multiples get room",
            "short": "yields rising — a headwind for equity multiples, growth first",
            "neutral": f"inside ±{YIELD_BP:.0f}bp — no read"}[v]
    return _vote(key, label, value, v, note)


def _index_volume(rows: dict[str, dict[str, Any]], session: str) -> dict[str, Any]:
    key, label = "index_volume", "Index volume"
    if _before_open(session):
        return _vote(key, label, "—", "neutral", "starts at the open")
    rv = [x for s in ("SPY", "QQQ") if (x := _num((rows.get(s) or {}).get("rvol"))) is not None]
    if not rv:
        return _vote(key, label, "—", "neutral", "no RVOL on SPY or QQQ yet")
    r = sum(rv) / len(rv)
    value = f"RVOL {r:.2f}×"
    move = _num((rows.get("SPY") or {}).get("chg_pct"))
    if r >= RVOL_HEAVY:
        if move is None or abs(move) < INDEX_FLAT:
            return _vote(key, label, value, "neutral",
                         "heavy volume with SPY flat — two-way trade, no side confirmed")
        v = "long" if move > 0 else "short"
        return _vote(key, label, value, v,
                     f"SPY {_signed(move, 2, '%')} on {r:.2f}× normal volume — the move is real")
    if r < RVOL_LIGHT:
        return _vote(key, label, value, "neutral",
                     "thin volume — moves on light volume fade more often")
    return _vote(key, label, value, "neutral", "about normal volume — confirms neither side")


def _participation(constituents: dict[str, Any] | None, session: str) -> dict[str, Any]:
    key, label = "participation", "Index leaders"
    lead = _leaders(constituents)
    up = sum(p > 0 for p in lead.values())
    down = sum(p < 0 for p in lead.values())
    value = f"{up} up · {down} down" if lead else "—"
    if _before_open(session):
        return _vote(key, label, value, "neutral",
                     "the last session's changes — the leaders vote from the open")
    if up + down < PART_MIN:
        return _vote(key, label, value, "neutral",
                     f"only {up + down} of the index leaders reporting")
    pct = up / (up + down) * 100.0
    v = _side(pct, PART_LONG, PART_SHORT)
    note = {"long": f"{pct:.0f}% of the NDX/SPX leaders up — the weight is behind the move",
            "short": f"only {pct:.0f}% of the NDX/SPX leaders up — the weight is selling",
            "neutral": f"{pct:.0f}% up — split leadership"}[v]
    return _vote(key, label, value, v, note)


def votes(scan: dict[str, Any], quotes: list[dict[str, Any]], sectors: list[dict[str, Any]],
          constituents: dict[str, Any] | None, now: datetime | None = None
          ) -> list[dict[str, Any]]:
    """The eleven reads of the tape, in a fixed order. Pure."""
    now = now or datetime.now(UTC)
    session = str(scan.get("session") or "closed")
    td = _trading_day(scan, now)
    rows = _rows(scan)
    return [
        _levels_vote("spy_levels", "SPY", rows.get("SPY"), session),
        _levels_vote("qqq_levels", "QQQ", rows.get("QQQ"), session),
        _vix_dir(quotes, session, now, td),
        _vix_curve(quotes, session, now, td),
        _sectors_vote(sectors, session),
        _equal_weight(sectors, session),
        _pct_vote(quotes, session, now, key="credit", label="Credit (HYG)", sym="HYG",
                  flat=HYG_FLAT, rising="long",
                  notes=("high yield bid — credit is taking risk", "high yield offered — "
                         "credit is leaving risk before equities do"), td=td),
        _yields(quotes, session, now, td),
        _pct_vote(quotes, session, now, key="dollar", label="Dollar", sym="DXY",
                  flat=DXY_FLAT, rising="short",
                  notes=("a firmer dollar tightens conditions — a headwind",
                         "a softer dollar eases conditions — a tailwind"), td=td),
        _index_volume(rows, session),
        _participation(constituents, session),
    ]


def conviction(vs: list[dict[str, Any]]) -> dict[str, Any]:
    """The count and its grade. Pure.

    strong: agree ≥ 6 and against ≤ 1 · moderate: agree ≥ 4 and agree > against + 1 ·
    weak: any other count with a side · none: a tie, or no votes at all.
    """
    long_n = sum(v.get("vote") == "long" for v in vs)
    short_n = sum(v.get("vote") == "short" for v in vs)
    bias = "long" if long_n > short_n else "short" if short_n > long_n else None
    agree = max(long_n, short_n)
    against = min(long_n, short_n)
    if bias is None:
        grade = "none"
    elif agree >= STRONG_AGREE and against <= STRONG_AGAINST:
        grade = "strong"
    elif agree >= MODERATE_AGREE and agree > against + 1:
        grade = "moderate"
    else:
        grade = "weak"
    return {"bias": bias, "agree": agree, "against": against,
            "neutral": len(vs) - long_n - short_n, "total": len(vs), "grade": grade,
            "max_conviction": MAX_CONVICTION[grade], "votes": vs}


def conviction_for(scan: dict[str, Any], quotes: list[dict[str, Any]],
                   sectors: list[dict[str, Any]], constituents: dict[str, Any] | None,
                   now: datetime | None = None) -> dict[str, Any]:
    """The Scanner's `regime.conviction` — the same count the Market tab prints. Pure."""
    return conviction(votes(scan, quotes, sectors, constituents, now))


# -------------------------------------------------------------------- breadth


def breadth(sectors: list[dict[str, Any]],
            constituents: dict[str, Any] | None) -> dict[str, Any]:
    """Sectors up and down, equal weight against the index, and each index's leaders. Pure."""
    moves = _sector_moves(sectors)
    rsp, spy = _sector_pct(sectors, "RSP"), _sector_pct(sectors, "SPY")
    indices: list[dict[str, Any]] = []
    for book, label in _BOOKS:
        ix = ((constituents or {}).get("indices") or {}).get(book)
        if not isinstance(ix, dict):
            continue
        mem = [m for m in ix.get("members") or [] if isinstance(m, dict)]
        pcts = [p for m in mem if (p := _num(m.get("pct"))) is not None]
        con = [c for m in mem if (c := _num(m.get("contribution"))) is not None]
        up, down = sum(p > 0 for p in pcts), sum(p < 0 for p in pcts)
        mag = sorted((abs(c) for c in con), reverse=True)
        tot = sum(mag)
        key = ix.get("index") if ix.get("index") in ("NDX", "SPX") else label
        indices.append({
            "key": key, "up": up, "down": down, "total": len(pcts),
            "pct_up": round(up / (up + down) * 100.0, 1) if up + down else None,
            "top3_share": round(sum(mag[:3]) / tot, 3) if tot > 0 else None,
            "contrib_pct": round(sum(con), 3) if con else None,
        })
    return {
        "sectors_up": sum(m > 0 for m in moves),
        "sectors_down": sum(m < 0 for m in moves),
        "sectors_total": len(moves),
        "rsp_vs_spy": round(rsp - spy, 3) if rsp is not None and spy is not None else None,
        "indices": indices,
    }


# ----------------------------------------------------------------------- fuel


def fuel(scan: dict[str, Any], quotes: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """How much of its implied one-day move each index ETF has used. Pure.

    The implied move is the index vol over √252 — VIX for SPY, VXN for QQQ.
    There is no small-cap vol index on the board, so IWM's comes from its own
    chain's 30-day implied volatility when the scanner has one, and is null
    otherwise. `gap_vs_implied` is signed: the gap in implied-move units.
    """
    session = str(scan.get("session") or "closed")
    rows = _rows(scan)
    out: list[dict[str, Any]] = []
    for sym in INDEX_ETFS:
        row = rows.get(sym)
        iv: float | None = None
        if sym in FUEL_VOL:
            q = _q(quotes, FUEL_VOL[sym])
            iv = _num(q.get("last")) if q else None
        elif row is not None and isinstance(row.get("options"), dict) and row["options"].get("ok"):
            iv = _num(row["options"].get("iv30"))
        implied = iv / SQRT252 if iv else None
        rng = gap = None
        if row is not None:
            lv = row.get("levels") or {}
            prev = _num(row.get("prev_close")) or _num(lv.get("pdc"))
            if prev:
                if _before_open(session):
                    gap = _num(row.get("ext_pct"))
                else:
                    hi, lo = _num(lv.get("day_hi")), _num(lv.get("day_lo"))
                    op = _num(lv.get("open"))
                    if hi is not None and lo is not None and hi >= lo:
                        rng = (hi - lo) / prev * 100.0
                    if op is not None:
                        gap = (op - prev) / prev * 100.0
        used = rng / implied if rng is not None and implied else None
        state = fuel_word(used)
        out.append({
            "sym": sym, "implied_pct": _r(implied, 3), "range_pct": _r(rng, 3),
            "used": _r(used, 2), "gap_pct": _r(gap, 3),
            "gap_vs_implied": _r(gap / implied, 2) if gap is not None and implied else None,
            "rvol": _r(_num(row.get("rvol")), 2) if row is not None else None, "state": state,
        })
    return out


# --------------------------------------------------------------------- prints


def _fmt(v: Any, raw: Any) -> str | None:
    if isinstance(raw, str) and raw.strip():
        return raw.strip()
    x = _num(v)
    return None if x is None else f"{x:g}"


#: Series no one trades off: the CPI's index levels and its unadjusted twins,
#: which Nasdaq lists beside the headline figures at the same minute.
PRINT_NOISE = re.compile(r"\bn\.\s?s\.\s?a\b|,\s*s\.\s?a\b|\b(?:cpi|ppi|pce) index\b", re.I)


def prints(calendar: list[dict[str, Any]], now: datetime,
           trading_day: date | None = None) -> list[dict[str, Any]]:
    """The trading day's US prints scored 3+, in time order — and, while that day
    is today, the next session's before its open. Pure.

    KEYED ON THE SESSION, NOT THE CALENDAR (audit, 2026-10-14). At 22:00 the
    tab is read for tomorrow, and keyed on the calendar date it showed today's
    finished releases and only tomorrow's pre-09:30 ones — Wednesday's 11:00
    Cleveland CPI, 13:30 Fed speaker and 14:00 Beige Book were nowhere. Now the
    day is the scanner's trading day.

    `done` is whether its time has passed: a speech is never `released` (it
    has no actual), so a 13:00 Barkin read as the next print all afternoon.
    """
    today = now.astimezone(ET).date()
    day = trading_day or today
    now_ts = now.timestamp()
    after = next_trading_day(day) if day == today else None
    out: list[tuple[tuple[str, str], dict[str, Any]]] = []
    seen: set[tuple[Any, ...]] = set()
    for r in calendar:
        if (not isinstance(r, dict) or r.get("region") != "us"
                or int(_num(r.get("score")) or 0) < PRINT_SCORE):
            continue
        ts = _num(r.get("ts"))
        if ts is not None:
            at = datetime.fromtimestamp(ts, ET)
            d, et = at.date(), f"{at:%H:%M}"
        else:
            try:
                d = date.fromisoformat(str(r.get("date"))[:10])
            except ValueError:
                continue
            et = str(r.get("et") or "")
        if d != day and not (d == after and et and et < "09:30"):
            continue
        title = str(r.get("event") or "")
        if PRINT_NOISE.search(title):
            continue
        k = (d, et, title, r.get("actual"), r.get("consensus"), r.get("previous"))
        if k in seen:
            continue
        seen.add(k)
        actual, cons = _num(r.get("actual")), _num(r.get("consensus"))
        surprise = _num(r.get("surprise"))
        if surprise is None and actual is not None and cons is not None:
            surprise = actual - cons
        released = bool(r.get("released"))
        label = (et or "untimed") if d == today else f"{d:%a} {et}".strip()
        out.append(((d.isoformat(), et or "99:99"), {
            "et": label, "title": title, "score": int(_num(r.get("score")) or 0),
            "released": released,
            "done": released or (ts is not None and ts <= now_ts),
            "actual": _fmt(r.get("actual"), r.get("actual_raw")),
            "consensus": _fmt(r.get("consensus"), r.get("consensus_raw")),
            "previous": _fmt(r.get("previous"), r.get("previous_raw")),
            "surprise": _r(surprise, 4),
            "read": read_of(title, surprise, cons) if released else None,
            "themes": [str(t) for t in r.get("themes") or []],
        }))
    out.sort(key=lambda x: x[0])
    return [p for _, p in out]


# ------------------------------------------------------------------------ fed


def fed(pm: dict[str, Any] | None) -> dict[str, Any] | None:
    """What the next meetings price, from the policy block. Pure.

    `bp` on the path is CUMULATIVE — what is priced by that meeting from today's
    effective rate — because that is how a path is read. `change_bp` is null:
    the day's change in the next meeting's pricing needs yesterday's strip, and
    the terminal does not keep one.
    """
    meetings = [m for m in (pm or {}).get("meetings") or [] if isinstance(m, dict)]
    if not meetings:
        return None
    first = meetings[0]
    bp = _num(first.get("move_bp"))
    label = str(first.get("label") or first.get("date") or "next meeting")
    if bp is None:
        note = f"{label}: no pricing read."
    elif abs(bp) < HOLD_BAND_BP:
        note = f"{label}: a hold is priced ({_signed(bp, 1, 'bp')})."
    else:
        note = (f"{label}: {_signed(bp, 1, 'bp')} priced — about {abs(bp) / 25 * 100:.0f}% "
                f"of a 25bp {'hike' if bp > 0 else 'cut'}.")
    note += " The day's change needs yesterday's strip, which is not kept."
    return {
        "next": first.get("date"), "next_bp": _r(bp, 1),
        "next_rate": _r(_num(first.get("implied_after")), 3),
        "path": [{"date": m.get("date"), "bp": _r(_num(m.get("cum_bp")), 1),
                  "rate": _r(_num(m.get("implied_after")), 3)} for m in meetings[:FED_PATH]],
        "change_bp": None,
        "note": note,
    }


# ---------------------------------------------------------------------- macro


def macro(quotes: list[dict[str, Any]], rates: dict[str, Any] | None) -> list[dict[str, Any]]:
    """The cross-asset moves an equity trade answers to. Pure.

    THE 2Y IS THE TREASURY'S, NOT THE BOARD'S. The board's "US2Y" is Yahoo's
    ^IRX, a 13-week bill — not a two-year note — so the 2Y here is the Treasury
    par curve's, as of its last close. The 10Y is the board's live ^TNX; 2s10s
    and its change come from the curve so both legs are the same print.
    """
    out: list[dict[str, Any]] = []
    curve = {c.get("key"): c for c in (rates or {}).get("curve") or [] if isinstance(c, dict)}
    two, ten = curve.get("2Y") or {}, curve.get("10Y") or {}
    v2, c2 = _num(two.get("value")), _num(two.get("chg_bp"))
    if v2 is not None:
        out.append({"key": "US2Y", "label": "2Y (Treasury close)",
                    "text": f"{v2:.2f}%" + (f" {_signed(c2, 0, 'bp')}" if c2 is not None else ""),
                    "move": c2})
    q10 = _q(quotes, "US10Y")
    if q10 is not None and (l10 := _num(q10.get("last"))) is not None:
        ch = _num(q10.get("chg"))
        bp = ch * 100.0 if ch is not None else None
        out.append({"key": "US10Y", "label": "10Y",
                    "text": f"{l10:.2f}%" + (f" {_signed(bp, 1, 'bp')}" if bp is not None else ""),
                    "move": _r(bp, 1)})
    spread = next((s for s in (rates or {}).get("spreads") or []
                   if isinstance(s, dict) and s.get("key") == "2s10s"), None)
    sv = _num(spread.get("value")) if spread else None
    if sv is not None:
        c10 = _num(ten.get("chg_bp"))
        d = c10 - c2 if c10 is not None and c2 is not None else None
        out.append({"key": "2s10s", "label": "2s10s",
                    "text": _signed(sv, 0, "bp") + (f" ({_signed(d, 0)})" if d is not None else ""),
                    "move": d})
    for key, label in MACRO_PCT:
        q = _q(quotes, key)
        last, pct = (_num(q.get("last")), _num(q.get("pct"))) if q else (None, None)
        if last is None:
            continue
        chg = f" {_signed(pct, 2, '%')}" if pct is not None else ""
        out.append({"key": key, "label": label, "text": f"{last:,.2f}{chg}",
                    "move": _r(pct, 2)})
    return out


# ---------------------------------------------------------------------- gamma


def gamma(gex: dict[str, Any] | None, quotes: list[dict[str, Any]],
          status: dict[str, Any] | None = None) -> list[dict[str, Any]] | None:
    """Dealer gamma on NQ and ES, translated into QQQ and SPY prices. Pure.

    The conversion is the live ratio of the two quotes — QQQ's last over NQ's —
    so it carries the futures' basis with it. Null when the gamma feed is off,
    failing, or serving a cached copy: a stale gamma level is worse than none.
    """
    if not isinstance(gex, dict) or not gex.get("enabled"):
        return None
    if status is not None and (not status.get("ok") or status.get("source") == "stale"):
        return None
    assets = gex.get("assets") or {}
    out: list[dict[str, Any]] = []
    for etf, book in _GAMMA:
        a = assets.get(book)
        if not isinstance(a, dict) or not a.get("ok"):
            continue
        eq, fq = _q(quotes, etf), _q(quotes, book)
        el = _num(eq.get("last")) if eq else None
        fl = _num(fq.get("last")) if fq else None
        if not el or not fl:
            continue
        ratio = el / fl
        lv = {str(x.get("key")): _num(x.get("price")) for x in a.get("levels") or []
              if isinstance(x, dict)}

        def conv(p: float | None, k: float = ratio) -> float | None:
            return round(p * k, 2) if p is not None else None

        flip = conv(lv.get("flip"))
        regime = a.get("regime") if a.get("regime") in ("POS", "NEG") else None
        note = {"POS": "Dealers long gamma — they sell rallies and buy dips, so ranges tend "
                       "to hold and the walls get faded.",
                "NEG": "Dealers short gamma — they chase the move, so ranges extend and "
                       "breaks run.",
                None: "No gamma regime read."}[regime]
        if flip is not None:
            note += f" {etf} {el:.2f} is {'above' if el >= flip else 'below'} the flip {flip:.2f}."
        out.append({"etf": etf, "book": book, "regime": regime, "flip": flip,
                    "call_wall": conv(lv.get("call_1")), "put_wall": conv(lv.get("put_1")),
                    "spot": round(el, 2), "ratio": round(ratio, 6), "note": note})
    return out or None


# ------------------------------------------------------------ options & peers


def index_options(scan: dict[str, Any]) -> list[dict[str, Any]]:
    """SPY, QQQ and IWM's options read — volatility, its premium, skew, the front
    expected move and today's flow (when the chain has given one). Pure."""
    rows = _rows(scan)
    out: list[dict[str, Any]] = []
    for sym in INDEX_ETFS:
        o = (rows.get(sym) or {}).get("options")
        o = o if isinstance(o, dict) and o.get("ok") else {}
        em = next((e for e in o.get("em") or [] if isinstance(e, dict)
                   and e.get("key") == "front"), {})
        flow = o.get("flow")
        out.append({
            "sym": sym, "iv30": _r(_num(o.get("iv30")), 1), "iv_rv": _r(_num(o.get("iv_rv")), 2),
            "premium": o.get("premium") if isinstance(o.get("premium"), str) else None,
            "skew": _r(_num(o.get("skew")), 2), "em_front_pct": _r(_num(em.get("pct")), 2),
            "flow": flow if isinstance(flow, dict) else None,
        })
    return out


def _tdays(a: date, b: date) -> int:
    """Weekdays from a to b (0 for the same day, negative when b is earlier)."""
    if b < a:
        return -_tdays(b, a)
    n, d = 0, a
    while d < b:
        d += timedelta(days=1)
        n += d.weekday() < 5
    return n


def peers(scan: dict[str, Any], sectors: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Per sector: the big caps reporting today through three trading days out (the
    rows' `peers`, plus a watchlist name's own report), and the watchlist names in
    that sector. Sectors with nothing reporting are left out. Pure."""
    labels = {s.get("key"): s.get("label") for s in sectors if isinstance(s, dict)}
    try:
        td = date.fromisoformat(str(scan.get("trading_day"))[:10])
    except ValueError:
        td = datetime.now(ET).date()
    groups: dict[str, dict[str, Any]] = {}
    for r in scan.get("rows") or []:
        if not isinstance(r, dict) or not isinstance(r.get("sector"), str):
            continue
        g = groups.setdefault(r["sector"], {"reports": {}, "watch": []})
        sym = str(r.get("sym") or "")
        g["watch"].append(sym)
        for p in r.get("peers") or []:
            if isinstance(p, dict) and isinstance(p.get("sym"), str):
                g["reports"].setdefault(p["sym"], {
                    "sym": p["sym"], "date": str(p.get("date") or ""),
                    "when": str(p.get("when") or "unspecified"), "days": int(p.get("days") or 0)})
        e = r.get("earnings")
        if isinstance(e, dict):
            try:
                d = date.fromisoformat(str(e.get("date"))[:10])
            except ValueError:
                continue
            n = _tdays(td, d)
            if 0 <= n <= PEER_DAYS:
                g["reports"].setdefault(sym, {"sym": sym, "date": d.isoformat(),
                                              "when": str(e.get("when") or "unspecified"),
                                              "days": n})
    out = [{"sector": k, "label": labels.get(k),
            "reports": sorted(g["reports"].values(), key=lambda x: (x["days"], x["sym"])),
            "watch": g["watch"]} for k, g in groups.items() if g["reports"]]
    out.sort(key=lambda x: (x["reports"][0]["days"], x["sector"]))
    return out


# ---------------------------------------------------------------------- build


def build(scan: dict[str, Any], snap: dict[str, Any],
          now: datetime | None = None) -> dict[str, Any]:
    """The MarketCtx payload. `snap` carries the snapshot keys this reads — quotes,
    sectors, constituents, calendar, rates, policy_meetings, gex, status — and
    any of them may be missing. Pure."""
    now = now or datetime.now(UTC)
    quotes = [q for q in snap.get("quotes") or [] if isinstance(q, dict)]
    sectors = [s for s in snap.get("sectors") or [] if isinstance(s, dict)]
    cons = snap.get("constituents") if isinstance(snap.get("constituents"), dict) else None
    status = snap.get("status") or {}
    gex_st = status.get("gex") if isinstance(status, dict) else None
    session = str(scan.get("session") or "closed")
    return {
        "ok": bool(quotes) or bool(scan.get("ok")),
        "built_utc": now.astimezone(UTC).isoformat(),
        "session": session if session in ("pre", "rth", "post", "closed") else "closed",
        "conviction": conviction_for(scan, quotes, sectors, cons, now),
        "breadth": breadth(sectors, cons),
        "fuel": fuel(scan, quotes),
        "prints": prints([c for c in snap.get("calendar") or [] if isinstance(c, dict)], now,
                         _trading_day(scan, now)),
        "fed": fed(snap.get("policy_meetings") if isinstance(snap.get("policy_meetings"), dict)
                   else None),
        "macro": macro(quotes, snap.get("rates") if isinstance(snap.get("rates"), dict) else None),
        "gamma": gamma(snap.get("gex") if isinstance(snap.get("gex"), dict) else None, quotes,
                       gex_st if isinstance(gex_st, dict) else None),
        "index_options": index_options(scan),
        "peers": peers(scan, sectors),
    }
