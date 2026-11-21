"""
The Market Report's Market Context: the day's backdrop, charted, with the model's read.

WHY (owner, 2026-11-21: "in our market reports in both stocks and futures sectionsm, we
should summaries the market pulse, sector rotations and gex context. for the stocks
section report maybe just have the SPY gex levels"). A report said what could move prices
and which way the bias leaned, and left out what kind of day it was being written into:
how hard risk was being sold, which sectors money was in, and whether dealers were set to
chase a move or lean against it.

THREE CHARTS AND WHAT THEY MEAN (the same day, of the first build's three lines of text:
"it needs to have nisce visuals and it is way too bland. use the ai model to summarise and
tlak about it and how it affects the market. i want it to look like aprofessional market
report"; of the full-size picture of the answer: "go ahead"). So the section is a lead
paragraph and three panels: the Market Pulse's scale with a bar a market, the sectors best
to worst with the index against its equal-weight twin, and a map of the gamma levels with
the price on it. Under each, the model says what it means for the book.

WHO WRITES WHAT. Every figure and every chart is the engine's, built here from what the
pages already show (outlook.py's card, the Sector Rotation row, the gamma levels), stored
with the report so it reads as it was written. The model is handed those figures
(`for_model`) and writes the words: a lead and one paragraph a panel. Its figures go
through the report's numeral guard like the rest of its text. The engine's own line a
panel (`rows`) is kept: it is what Hermes reads, and what the page prints under a chart
when the model wrote nothing for it.

CONTEXT, NEVER A VOTE. Nothing here moves the bias or a call. Dealer gamma was taken out
of the reports on 15 Nov 2026 at the owner's word, when it sat among the levels and the
drivers; it is back as a regime, how far moves tend to run, and is still not a side and
still not a level the report trades from. Its map is drawn in ink and the flip's amber,
never in the green and pink of a side.

WHOSE GAMMA. A futures report: each book it is about. The Stocks report: SPY alone (the
owner's call), the S&P future's levels in SPY's prices by the ratio of the two quotes, so
the future's basis rides with them (as marketctx.gamma converts them for the scanner),
with one care that read does not take: the two prices are of the same moment, and SPY's
is the one trading now, before the bell too (`fund_prices`).

Pure.
"""

from __future__ import annotations

from datetime import datetime
from typing import Any

from . import dashboard
from .sources import universe
from .volterm import BOOK_DP, quote_key

#: The funds that are the market and not a sector of it.
NOT_A_SECTOR = frozenset({"SPY", "RSP"})
#: Sectors named at each end of the row's line.
ENDS = 3
#: The fewest sectors with a move before the row is said at all.
SECTORS_MIN = 6
#: Equal weight against cap weight is said from this many points apart.
BREADTH_GAP = 0.5
#: The panels, in the order the page draws them, and the key the model answers each by.
PANELS = ("pulse", "rotation", "gamma")

_REGIME = {
    "NEG": ("negative gamma", "dealers chase moves and breaks run"),
    "POS": ("positive gamma", "dealers lean against moves and ranges tend to hold"),
}
_WALL = {"put": "Put wall", "call": "Call wall", "flip": "Flip"}


def _num(v: Any) -> float | None:
    if isinstance(v, bool) or not isinstance(v, int | float):
        return None
    f = float(v)
    return f if f == f else None


def _round(v: float, dp: int) -> float:
    """`v` to `dp` decimals, rounded as the report's key levels round it
    (report.key_levels), so the line's price is the Last the same sheet prints above it:
    NQ on a half tick, 25,126.5, is 25,126 in both."""
    return float(round(v, dp) if dp else round(v))


def _n(v: float, dp: int = 2) -> str:
    """A price as the line prints it: to the instrument's decimals, and whole when it is
    whole (a wall at 42 is not 42.000)."""
    v = _round(v, dp)
    return f"{v:,.0f}" if v == round(v) else f"{v:,.{dp}f}"


def _pct(v: float) -> str:
    return f"{v:+.2f}%"


def _quote(snap: dict[str, Any], key: str) -> dict[str, Any]:
    return next((q for q in snap.get("quotes") or []
                 if isinstance(q, dict) and q.get("key") == key), {})


# ---- the Market Pulse ------------------------------------------------------------------------


def pulse_data(outlook: Any) -> dict[str, Any] | None:
    """The card's scale, pattern and a row a market, as the panel draws them: each
    market's move and how many of its own usual days that is. Pure."""
    o = outlook if isinstance(outlook, dict) else {}
    if not o.get("ok") or not o.get("name"):
        return None
    sent = o.get("sentiment") if isinstance(o.get("sentiment"), dict) else None
    score = _num((sent or {}).get("score"))
    rows = [{"key": r.get("key"), "group": r.get("group"), "name": r.get("name"),
             "pct": round(p, 2), "mult": round(m, 1), "sized": bool(r.get("sized"))}
            for r in o.get("rows") or [] if isinstance(r, dict)
            and (p := _num(r.get("pct"))) is not None and (m := _num(r.get("mult"))) is not None]
    return {"score": int(score) if score is not None and (sent or {}).get("label") else None,
            "label": (sent or {}).get("label") if score is not None else None,
            "name": o["name"], "what": o.get("what") or "", "tell": o.get("tell") or "",
            "rows": rows}


def pulse_line(outlook: Any) -> str | None:
    """"Extreme fear (-78). Forced selling: stocks and metals sold, bonds bid. Unusual:
    gold fell with stocks." The card's scale, pattern and sentence, in that order. Pure."""
    p = pulse_data(outlook)
    if p is None:
        return None
    parts: list[str] = []
    if p["score"] is not None:
        parts.append(f"{p['label']} ({p['score']:+d}).")
    parts.append(f"{p['name']}: {p['what']}." if p["what"] else f"{p['name']}.")
    if p["tell"]:
        parts.append(str(p["tell"]))
    return " ".join(parts)


# ---- the sector rotation ----------------------------------------------------------------------


def rotation_data(sectors: list[dict[str, Any]], *, pre: bool = False) -> dict[str, Any] | None:
    """The sectors best to worst, how many rose, and the index against its equal-weight
    twin with the sentence that says who carried the day. `sectors` is the snapshot's row
    a fund, SPY and RSP among them; `pre` when the moves are the funds' pre-market ones.
    Pure."""
    rows: list[dict[str, Any]] = [
        {"key": str(s.get("key")), "label": str(s.get("label") or s.get("key")),
         "pct": round(d, 2)}
        for s in sectors if isinstance(s, dict) and s.get("key") not in NOT_A_SECTOR
        and (d := _num(s.get("day_pct"))) is not None]
    if len(rows) < SECTORS_MIN:
        return None
    rows.sort(key=lambda r: -r["pct"])
    up = sum(1 for r in rows if r["pct"] > 0)
    out: dict[str, Any] = {"pre": pre, "up": up, "down": sum(1 for r in rows if r["pct"] < 0),
                           "n": len(rows), "sectors": rows, "spy": None, "rsp": None,
                           "breadth": None}
    by = {s.get("key"): _num(s.get("day_pct")) for s in sectors if isinstance(s, dict)}
    spy, rsp = by.get("SPY"), by.get("RSP")
    # Equal weight against cap weight: whether the largest names made the day. Not before
    # the bell, when the equal-weight fund has hardly traded.
    if not pre and spy is not None and rsp is not None:
        out["spy"], out["rsp"] = round(spy, 2), round(rsp, 2)
        if abs(rsp - spy) >= BREADTH_GAP:
            gap = f"{abs(rsp - spy):.1f} points"
            if rsp > spy:
                why = ("the selling was heaviest in the largest names" if spy < 0
                       else "the average stock did better than the index")
                out["breadth"] = f"Equal weight beat the S&P by {gap}: {why}."
            else:
                why = ("the largest names carried it" if spy > 0
                       else "the average stock fell further than the index")
                out["breadth"] = f"The S&P beat equal weight by {gap}: {why}."
    return out


def rotation_line(sectors: list[dict[str, Any]], *, pre: bool = False) -> str | None:
    """"1 of 11 sectors up. Leading: ... Lagging: ... Equal weight beat the S&P by 1.7
    points: the selling was heaviest in the largest names." Pure."""
    r = rotation_data(sectors, pre=pre)
    if r is None:
        return None
    rows = r["sectors"]

    def named(part: list[dict[str, Any]]) -> str:
        return ", ".join(f"{x['label']} {_pct(x['pct'])}" for x in part)

    text = (f"{'Before the bell, ' if pre else ''}{r['up']} of {r['n']} sectors up."
            f" Leading: {named(rows[:ENDS])}. Lagging: {named(rows[::-1][:ENDS])}.")
    return f"{text} {r['breadth']}" if r["breadth"] else text


# ---- dealer gamma -----------------------------------------------------------------------------


def gamma_data(name: str, last: float | None, asset: Any, *, ratio: float = 1.0,
               band: bool = True, dp: int = 2) -> dict[str, Any] | None:
    """One instrument's gamma map: its price, the regime, the flip, the walls, the level
    next to the price on each side and (a future's own) the expected move.

    `asset` is one book's block of the gamma feed; `ratio` turns its prices into another
    instrument's (SPY's from the S&P future's), `band` False leaves the expected move out
    (it is the future's own), `dp` is the decimals the instrument prints to. Every
    distance is between two prices as printed, so the panel adds up. None when the feed
    has nothing for the book. Pure."""
    a = asset if isinstance(asset, dict) else {}
    if not a.get("ok") or not last:
        return None
    last = _round(last, dp)
    lv: dict[str, float] = {}
    for x in a.get("levels") or []:
        p = _num(x.get("price")) if isinstance(x, dict) else None
        if p is not None:
            lv[str(x.get("key"))] = _round(p * ratio, dp)
    regime = a.get("regime") if a.get("regime") in _REGIME else None
    flip = lv.get("flip")
    if regime is None and flip is None:
        return None
    puts = sorted({p for k, p in lv.items() if k.startswith("put")}, reverse=True)
    calls = sorted({p for k, p in lv.items() if k.startswith("call")})
    named = [*(("put", p) for p in puts), *(("call", p) for p in calls),
             *((("flip", flip),) if flip is not None else ())]

    def near(above: bool) -> dict[str, Any] | None:
        side = [(k, p) for k, p in named if (p > last if above else p < last)]
        if not side:
            return None
        k, p = min(side, key=lambda x: abs(x[1] - last))
        return {"kind": k, "price": p, "away": _round(abs(p - last), dp)}

    lo, hi = _num(a.get("em_lo")), _num(a.get("em_hi"))
    em = ([_round(lo * ratio, dp), _round(hi * ratio, dp)]
          if band and lo is not None and hi is not None and hi > lo else None)
    return {"name": name, "last": last, "dp": dp, "regime": regime, "flip": flip,
            "to_flip": _round(abs(flip - last), dp) if flip is not None else None,
            "below_flip": last < flip if flip is not None else None,
            "puts": puts, "calls": calls, "above": near(True), "below": near(False), "em": em}


def gamma_text(g: dict[str, Any] | None) -> str | None:
    """"NQ 25,291: negative gamma, 1,499 below the flip at 26,790, so dealers chase moves
    and breaks run. Put walls 25,955, 25,749, 24,719. Expected move 24,284 to 26,298."
    Pure."""
    if g is None:
        return None
    dp = int(g["dp"])
    word, effect = _REGIME.get(str(g["regime"]), (None, None))
    bits: list[str] = []
    if word:
        bits.append(word)
    if g["flip"] is not None:
        side = "below" if g["below_flip"] else "above"
        bits.append(f"{_n(g['to_flip'], dp)} {side} the flip at {_n(g['flip'], dp)}")
    text = f"{g['name']} {_n(g['last'], dp)}: {', '.join(bits)}" \
        + (f", so {effect}." if effect else ".")
    for label, key in (("Put", "puts"), ("Call", "calls")):
        w = [_n(p, dp) for p in g[key]]
        if w:
            text += f" {label} wall{'s' if len(w) > 1 else ''} {', '.join(w)}."
    if g["em"]:
        text += f" Expected move {_n(g['em'][0], dp)} to {_n(g['em'][1], dp)}."
    return text


def gamma_line(name: str, last: float | None, asset: Any, *, ratio: float = 1.0,
               band: bool = True, dp: int = 2) -> str | None:
    """The line for one instrument, straight from its feed block. Pure."""
    return gamma_text(gamma_data(name, last, asset, ratio=ratio, band=band, dp=dp))


def fund_prices(q: dict[str, Any], at: float | None) -> tuple[float | None, float | None]:
    """(a fund's price NOW, its price nearest the instant `at`), from its quote row.

    A fund's `last` is the regular session's and stays yesterday's close until the bell;
    what trades before it and after the close rides beside it as `ext` (quotes.with_ext).
    The Stocks report is written at 09:00 ET, so the line speaks of the pre-market price,
    the one the report prints as the fund's Last. And the ratio that turns the future's
    levels into the fund's must pair two prices of the same moment: `at` is when the
    future last printed, and the fund's print nearest it is the one to divide. Friday's
    close set against Monday's 09:00 future would move every level by the weekend's gap.
    Pure."""
    last, t_last = _num(q.get("last")), _num(q.get("quote_time"))
    raw = q.get("ext")
    ext: dict[str, Any] = raw if isinstance(raw, dict) else {}
    px, t_px = _num(ext.get("px")), _num(ext.get("at"))
    if last is None:
        return px, px
    if px is None or t_px is None or t_last is None:
        return last, last
    spot = px if t_px > t_last else last
    if at is None:
        return spot, spot
    return spot, (px if abs(t_px - at) < abs(t_last - at) else last)


def _gamma_live(snap: dict[str, Any]) -> bool:
    """The gamma feed is on and its copy is fresh: a stale wall is worse than none."""
    gex = snap.get("gex")
    st = (snap.get("status") or {}).get("gex")
    if not isinstance(gex, dict) or not gex.get("enabled"):
        return False
    return not (isinstance(st, dict) and (not st.get("ok") or st.get("source") == "stale"))


# ---- the section -------------------------------------------------------------------------------


def build(snap: dict[str, Any], books: list[str], *, etf: bool,
          now: datetime) -> dict[str, Any] | None:
    """The report's section: {as_of, rows, pulse?, rotation?, gamma?}.

    `rows` is the engine's line a panel, [{key, label, text}]; `pulse`, `rotation` and
    `gamma` (a list, one map an instrument) are the figures the panels draw. A panel
    whose source has nothing to say is left out of both, and the whole is None when none
    has. `books` are the report's books; `etf` is the Stocks report, whose gamma is SPY's
    alone. Pure."""
    rows: list[dict[str, str]] = []
    out: dict[str, Any] = {}
    outlook = snap.get("outlook")
    if (pulse := pulse_data(outlook)) and (text := pulse_line(outlook)):
        out["pulse"] = pulse
        rows.append({"key": "pulse", "label": "Market Pulse", "text": text})

    sectors = [s for s in snap.get("sectors") or [] if isinstance(s, dict)]
    raw = snap.get("sector_ext")
    ext: dict[str, dict[str, Any]] = raw if isinstance(raw, dict) else {}
    spy_ext = ext.get("SPY")
    pre = universe.cards_phase(spy_ext, now) == "pre"
    if pre:
        sectors = dashboard.pre_market_rows(sectors, ext, str((spy_ext or {}).get("day")))
    if (rot := rotation_data(sectors, pre=pre)) and (text := rotation_line(sectors, pre=pre)):
        out["rotation"] = rot
        rows.append({"key": "rotation", "label": "Sector Rotation", "text": text})

    maps: list[dict[str, Any]] = []
    if _gamma_live(snap):
        assets = (snap.get("gex") or {}).get("assets") or {}
        if etf:
            fut = _quote(snap, "ES")
            es = _num(fut.get("last"))
            spy, paired = fund_prices(_quote(snap, "SPY"), _num(fut.get("quote_time")))
            if spy and paired and es:
                g = gamma_data("SPY", spy, assets.get("ES"), ratio=paired / es, band=False)
                if g:
                    maps.append(g)
        else:
            for b in books:
                last = _num(_quote(snap, quote_key(b)).get("last"))
                g = gamma_data(b, last, assets.get(b), dp=BOOK_DP.get(b, 2))
                if g:
                    maps.append(g)
    for g in maps:
        rows.append({"key": "gamma", "label": "Dealer Gamma", "text": gamma_text(g) or ""})
    if maps:
        out["gamma"] = maps
    if not rows:
        return None
    label = outlook.get("label") if isinstance(outlook, dict) and outlook.get("ok") else None
    return {"as_of": label, "rows": rows, **out}


def panels(ctx: dict[str, Any] | None) -> list[str]:
    """The panels a stored section has, in the page's order: the keys the model may
    answer by. Pure."""
    if not isinstance(ctx, dict):
        return []
    have = {r.get("key") for r in ctx.get("rows") or [] if isinstance(r, dict)}
    return [k for k in PANELS if k in have]


def for_model(ctx: dict[str, Any] | None) -> dict[str, Any] | None:
    """The section as the model reads it: what it is, the engine's line a panel, and the
    figures the page charts, in the figures the page prints (so a number the model copies
    is one the numeral guard finds). Pure."""
    if not ctx:
        return None
    out: dict[str, Any] = {
        "what_this_is": "The day's backdrop, which the page charts under the call: the "
                        "Market Pulse, the sector rotation and dealer gamma. Context for "
                        "the day: none of it is in the bias and none is a side. You write "
                        "what each means in `context`.",
        "as_of": ctx.get("as_of"),
        "panels": panels(ctx),
        "lines": [f"{r['label']}: {r['text']}" for r in ctx.get("rows") or []],
    }
    p = ctx.get("pulse")
    if isinstance(p, dict):
        out["market_pulse"] = {
            "scale": "risk appetite today from -100 (extreme fear) to +100 (extreme greed)",
            "score": p.get("score"), "reading": p.get("label"), "pattern": p.get("name"),
            "markets": [{"market": r["name"] if r.get("group") == "Stocks" else r.get("group"),
                         "move_pct": round(float(r["pct"]), 1),
                         "times_its_usual_day": abs(float(r["mult"]))}
                        for r in p.get("rows") or []],
        }
    r = ctx.get("rotation")
    if isinstance(r, dict):
        out["sector_rotation"] = {
            "basis": "the funds' pre-market moves" if r.get("pre") else "the session's moves",
            "sectors_up": r.get("up"), "sectors_down": r.get("down"), "of": r.get("n"),
            "best_to_worst": [{"sector": s["label"], "move_pct": s["pct"]}
                              for s in r.get("sectors") or []],
            **({"sp500_pct": r["spy"], "equal_weight_sp500_pct": r["rsp"]}
               if r.get("spy") is not None and r.get("rsp") is not None else {}),
        }
    maps = [g for g in ctx.get("gamma") or [] if isinstance(g, dict)]
    if maps:
        out["dealer_gamma"] = [_gamma_words(g) for g in maps]
    return out


def _gamma_words(g: dict[str, Any]) -> dict[str, Any]:
    """One gamma map for the model, every price AS THE MAP PRINTS IT ("26,790", not
    26790.0): the first futures report copied the bare floats and wrote "1664 below the
    26790 flip" under a chart that said 1,664 and 26,790. Pure."""
    dp = int(g.get("dp") or 0)

    def p(v: Any) -> str | None:
        f = _num(v)
        return _n(f, dp) if f is not None else None

    def near(n: Any) -> dict[str, Any] | None:
        if not isinstance(n, dict):
            return None
        return {"level": _WALL.get(str(n.get("kind")), "Level"), "price": p(n.get("price")),
                "away": p(n.get("away"))}

    regime = _REGIME.get(str(g.get("regime")))
    em = g.get("em")
    return {
        "instrument": g["name"], "price": p(g.get("last")),
        "regime": regime[0] if regime else None,
        "what_the_regime_does": regime[1] if regime else None,
        "flip": p(g.get("flip")), "distance_to_flip": p(g.get("to_flip")),
        "price_is": None if g.get("below_flip") is None
        else "below the flip" if g["below_flip"] else "above the flip",
        "put_walls": [p(x) for x in g.get("puts") or []],
        "call_walls": [p(x) for x in g.get("calls") or []],
        "nearest_level_above": near(g.get("above")),
        "nearest_level_below": near(g.get("below")),
        **({"expected_move": {"low": p(em[0]), "high": p(em[1])}} if em else {}),
    }
