"""
The volatility term structure — what the options market thinks happens next.

WHY IT EARNS A PANEL WHEN THE BOARD ALREADY CARRIES VIX. A single VIX level
says how much movement is priced for the next thirty days and nothing about
whether that is unusual. The CURVE says whether the market is calm or
frightened, because the shape inverts before the level moves much: in normal
conditions each further tenor prices more vol than the one before it
(contango), and when something is actually wrong the near tenor overtakes the
far one (backwardation). That crossover is one of the cleanest regime signals
available and it typically leads the equity move rather than following it.

IT PAIRS WITH THE GAMMA REGIME AND ANSWERS A DIFFERENT QUESTION. Gamma says how
dealers must hedge — dampening moves or amplifying them. Term structure says
what the options market expects over the next month. Positive gamma with a
curve tipping into backwardation is a different session from positive gamma
with a curve in healthy contango, and nothing else on the terminal separates
those two.

COMPUTED ON READ, NOT POLLED. Every input is already on the board, so this is
arithmetic rather than a source — the same standing as `expiry`. There is no
upstream here to be stale against.
"""

from __future__ import annotations

import math
from typing import Any

from .optcalc import premium, realised_vol

# key, label, roughly how far out it prices
TENORS: list[tuple[str, str, str]] = [
    ("VIX9D", "9-day", "this week"),
    ("VIX", "30-day", "the next month"),
    ("VIX3M", "3-month", "the quarter"),
    ("VIX6M", "6-month", "half a year"),
]

# The near/far pair everyone actually quotes. Above 1.00 the near tenor prices
# more vol than the far one, which is backwardation.
HEADLINE_PAIR = ("VIX", "VIX3M")

# A curve is never exactly flat, and calling a 0.4% steepness "backwardation"
# would fire this signal most weeks. 1.00 is the real boundary; the band around
# it is where the shape is not saying anything yet.
FLAT_BAND = 0.02


def _q(quotes: list[dict[str, Any]], key: str) -> dict[str, Any] | None:
    return next((q for q in quotes if q.get("key") == key), None)


def state(quotes: list[dict[str, Any]]) -> dict[str, Any]:
    """The curve, its shape, and what the shape means."""
    points: list[dict[str, Any]] = []
    for key, label, horizon in TENORS:
        q = _q(quotes, key)
        if q is None or q.get("last") is None:
            continue
        points.append(
            {
                "key": key,
                "label": label,
                "horizon": horizon,
                "value": q["last"],
                "pct": round(q["pct"], 2) if q.get("pct") is not None else None,
            }
        )

    near = _q(quotes, HEADLINE_PAIR[0])
    far = _q(quotes, HEADLINE_PAIR[1])
    ratio = None
    if near and far and far.get("last"):
        ratio = near["last"] / far["last"]

    if ratio is None:
        shape, note = "unknown", None
    elif ratio > 1 + FLAT_BAND:
        shape = "backwardation"
        note = (
            "Near-dated vol is bid above the quarter — the market is paying up for "
            "protection now rather than later. This is the stressed shape, and it "
            "usually turns before the index does."
        )
    elif ratio < 1 - FLAT_BAND:
        shape = "contango"
        note = (
            "Each tenor prices more vol than the one before it — the normal, calm "
            "shape. A move toward 1.00 is the thing to watch, not the level."
        )
    else:
        shape = "flat"
        note = (
            "The curve is flat within a couple of percent. Neither calm nor "
            "stressed; the next move in the ratio decides which."
        )

    # Not a tenor of the curve, so it sits beside it rather than in it: SKEW
    # prices the cost of far out-of-the-money puts against at-the-money, which
    # is what the market is paying for a crash rather than for movement.
    skew = _q(quotes, "SKEW")

    return {
        "points": points,
        "ratio": round(ratio, 4) if ratio is not None else None,
        "ratio_label": f"{HEADLINE_PAIR[0]}/{HEADLINE_PAIR[1]}",
        "shape": shape,
        "note": note,
        "skew": skew["last"] if skew else None,
        "skew_pct": round(skew["pct"], 2) if skew and skew.get("pct") is not None else None,
    }


# ---------------------------------------------------------------------------
# THE IMPLIED DAY, PER BOOK.
#
# THE CURVE ABOVE IS THE S&P 500's; THE DESK TRADES THREE BOOKS. A VIX of 18.5
# says the options market prices a ±1.17% day for the index, and an NQ or gold
# trader had to convert that by hand — through the wrong index, since the
# Nasdaq-100 and gold have vol indices of their own. So this turns each book's
# own index (EM_VOL, which the Report's ladder reads too) into the book's own
# points: the one-day, one-standard-deviation move, which price closes inside
# about two days in three. A 68% band, not a ceiling, and labelled 1σ on the
# page for that reason, as the Report labels it.
#
# TWO READS RIDE WITH IT, both the stocks desk's own rules so the two desks can
# never disagree about a number: how much of the implied day today's range has
# already used (marketctx's fuel — FUEL_ROOM / FUEL_STRETCHED live here now,
# because marketctx imports this module), and implied against realised
# (optcalc's PREMIUM_CHEAP / PREMIUM_RICH: cheap, fair, rich). Twenty-odd daily
# closes per book are already on the context feed for the brief, so the
# realised leg costs no request.
#
# THE RANGE IS THE GLOBEX DAY. A future's high and low on the quote feed run
# from the 18:00 ET reopen, which is the day a futures trader means: at the New
# York open the overnight counts, and "Asia and London have already traded a
# full implied day" is exactly the read this exists to give.
#
# GEXYGEN'S OWN BAND COMES ALONG WHEN IT IS UP, beside the 1σ and never instead
# of it: the 0DTE book's expected move is a same-day number and narrower, and
# the panel says which is which. Computed on read, like the curve above.
# ---------------------------------------------------------------------------

BOOKS: tuple[str, ...] = ("NQ", "ES", "GC")
#: The index that prices each book's day. The Report's ladder reads the same map.
EM_VOL: dict[str, str] = {"NQ": "VXN", "ES": "VIX", "GC": "GVZ"}
#: Decimals a book is quoted to: NQ in whole points, ES in quarters, gold in
#: tenths. A ladder printing 29,408.00 carries three characters of noise a row.
BOOK_DP: dict[str, int] = {"NQ": 0, "ES": 2, "GC": 1}
#: Range used ÷ implied day: under ROOM there is room left to travel; past
#: STRETCHED the day has already done what the options priced.
FUEL_ROOM = 0.6
FUEL_STRETCHED = 1.0
SQRT252 = math.sqrt(252.0)


def fuel_word(used: float | None) -> str | None:
    """marketctx's rule, stated once: room / normal / stretched."""
    if used is None:
        return None
    return "room" if used < FUEL_ROOM else "normal" if used <= FUEL_STRETCHED else "stretched"


def _num(v: Any) -> float | None:
    """A finite number, or None — a bool is not a price and neither is NaN."""
    if isinstance(v, bool) or not isinstance(v, int | float) or not math.isfinite(v):
        return None
    return float(v)


def implied_day(
    quotes: list[dict[str, Any]],
    context: list[dict[str, Any]] | None = None,
    gex: dict[str, Any] | None = None,
) -> list[dict[str, Any]]:
    """Each book's one-sigma day in its own points, how much of it today's range
    has used, and implied against realised. Pure; a missing input is a null,
    never a zero, and a book with no print has no row."""
    ctx = context or []
    assets = (gex or {}).get("assets") or {}
    rows: list[dict[str, Any]] = []
    for book in BOOKS:
        q = _q(quotes, book)
        last = _num(q.get("last")) if q else None
        if q is None or last is None:
            continue
        prev = _num(q.get("prev"))

        # The book's own index: VIX and VXN ride the board; GVZ is on the daily
        # context feed only, where the brief already reads it.
        vol_key = EM_VOL[book]
        src = _q(quotes, vol_key) or _q(ctx, vol_key) or {}
        iv = _num(src.get("last"))
        iv = iv if iv and iv > 0 else None
        # The index's own day change: a quote row carries `pct`, a context row `day_pct`.
        iv_pct = _num(src.get("pct", src.get("day_pct")))
        sigma_pct = iv / SQRT252 if iv else None
        sigma = last * sigma_pct / 100.0 if sigma_pct else None

        # Today's range against the previous close, as marketctx measures an
        # ETF's — the last print stands in when the feed carries no close.
        hi, lo = _num(q.get("high")), _num(q.get("low"))
        rng = hi - lo if hi is not None and lo is not None and hi >= lo else None
        base = prev or last
        range_pct = rng / base * 100.0 if rng is not None and base else None
        used = range_pct / sigma_pct if range_pct is not None and sigma_pct else None

        closes = [c for c in ((_q(ctx, book) or {}).get("closes") or []) if _num(c) is not None]
        rv = realised_vol([float(c) for c in closes])
        iv_rv = round(iv / rv, 3) if iv and rv else None

        g = assets.get(book) or {}
        g_hi, g_lo = _num(g.get("em_hi")), _num(g.get("em_lo"))
        band = bool(g.get("ok")) and g_hi is not None and g_lo is not None and g_hi > g_lo

        rows.append(
            {
                "key": book,
                "dp": BOOK_DP[book],
                "last": last,
                "prev": prev,
                "vol_key": vol_key,
                "vol": iv,
                "vol_pct": round(iv_pct, 2) if iv_pct is not None else None,
                "sigma_pct": round(sigma_pct, 3) if sigma_pct is not None else None,
                "sigma": round(sigma, 2) if sigma is not None else None,
                "lo": round(last - sigma, 2) if sigma is not None else None,
                "hi": round(last + sigma, 2) if sigma is not None else None,
                "range": round(rng, 2) if rng is not None else None,
                "range_pct": round(range_pct, 3) if range_pct is not None else None,
                "used": round(used, 2) if used is not None else None,
                "fuel": fuel_word(used),
                "rv20": rv,
                "rv_day": round(last * rv / 100.0 / SQRT252, 2) if rv else None,
                "iv_rv": iv_rv,
                "premium": premium(iv_rv),
                "gex_lo": g_lo if band else None,
                "gex_hi": g_hi if band else None,
                "regime": g.get("regime") if g.get("ok") else None,
            }
        )
    return rows


# --------------------------------------------------------------------------
# The VIX against its own month.
#
# A LEVEL IS HALF THE READ (owner, 2026-10-23). An 18 after a week at 13 is
# protection being bid; an 18 after a week at 25 is protection coming off. The
# bands and the 18 sub-line are absolute; this is the relative half: where the
# print sits in the last twenty finished sessions' closes, from the daily
# context block that already carries the VIX. Computed on read for both
# desks, so the header's popover and the scanner's card say the same thing.
# --------------------------------------------------------------------------

MONTH_SESSIONS = 20
MONTH_MIN = 5


def vix_month(context: list[dict[str, Any]], quotes: list[dict[str, Any]]) -> dict[str, Any] | None:
    """The live VIX's percentile of its last twenty finished daily closes, with
    the month's low and high. Pure. None under MONTH_MIN closes or without a
    live print."""
    q = _q(quotes, "VIX")
    last = _num(q.get("last")) if q else None
    ctx = _q(context, "VIX")
    raw = (ctx or {}).get("closes") or []
    closes = [c for c in (_num(x) for x in raw) if c is not None]
    # The newest close is today's, still forming — the live print stands in for it.
    done = closes[:-1][-MONTH_SESSIONS:] if len(closes) > 1 else []
    if last is None or len(done) < MONTH_MIN:
        return None
    return {
        "pctile": round(sum(1 for c in done if c <= last) / len(done) * 100.0),
        "lo": round(min(done), 2),
        "hi": round(max(done), 2),
        "days": len(done),
    }
