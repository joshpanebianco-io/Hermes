"""
The driver board — the futures Terminal's engine-computed read, per book.

WHY (owner, 2026-10-22: "do everything you recommend"). The stocks desk has
had a tape count since 2026-10-14: eleven independent reads of the tape,
each a vote with its threshold stated, graded, and the ceiling the game
plan's convictions are capped at. The futures desk had nothing of the kind:
its macro breakdown lived only in the Analysis brief, on demand, minutes to
run on a free model, two runs free to disagree. Between briefs the Terminal
showed the 10Y up six basis points and said nothing about what that did to
NQ or to gold. This is the same read re-cast for NQ, ES and GC — every
driver a vote with its threshold and its reason, weighed by bias.py with the
stocks desk's tape, with one line on how to treat it.

THREE LAYERS, READ TOGETHER. Macro sets the direction (yields, the dollar,
credit, the VIX and its curve, today's inflation prints); positioning says
how far a move runs (dealer gamma and spot against the flip); structure says
whether the tape is accepting the macro lean (prior value, the last session's
range, the daily frame, breadth). A macro lean the structure rejects is a
CONFLICT, and a conflict lowers conviction rather than picking a side — the
brief's own rule, now computed.

CONTEXT ROWS DO NOT VOTE. Positioning (COT), the market-wide put/call and
OpEx week are what a move will find, not which way it goes; they sit under
the votes with their reads and never enter the count.

THE INPUTS KEEP THEIR OWN CLOCKS. A cash-market read (credit, breadth, the
leaders, the VIX's day change) says "closed" outside US hours and carries
`live: false`: the futures desk runs through Asia and London, and a read that
cannot vote is not the same as a flat one. It is on neither side, and the score
is over the whole of the session's weight (bias.py), so a board with little
live reads near zero and `coverage` says how much of the weight could vote.

PURE. `build` takes the snapshot's blocks and does no I/O; computed on read
like volterm and expiry.
"""

from __future__ import annotations

import re
from datetime import UTC, date, datetime
from typing import Any

from . import bias as bias_mod
from . import events as events_mod
from . import frame as frame_mod
from . import holidays, marketctx, releases, report, structure, volterm
from .profile import value_position
from .sources import cot as cot_mod

#: Every book the board scores. Silver and crude since 2026-11-15 (bias.py says what
#: each answers to); until then they had levels, ranges and gamma and no score.
BOOKS: tuple[str, ...] = ("NQ", "ES", "GC", "SIL", "CL")
#: Which cash index each equity book's leaders are read from.
INDEX_OF = {"NQ": "NDX", "ES": "SPX"}
#: The books the CFTC's positioning is read for (sources/cot.py).
COT_BOOKS: tuple[str, ...] = ("NQ", "ES", "GC")

# ---- the thresholds, the stocks desk's where one exists ----------------------
YIELD_BP = marketctx.YIELD_BP  # the 10Y's day change at or beyond this votes
DXY_FLAT = marketctx.DXY_FLAT
HYG_FLAT = marketctx.HYG_FLAT
VIX_FLAT = marketctx.VIX_FLAT
CURVE_CALM = marketctx.CURVE_CALM
CURVE_STRESS = marketctx.CURVE_STRESS
PART_LONG = marketctx.PART_LONG
PART_SHORT = marketctx.PART_SHORT
PART_MIN = marketctx.PART_MIN
#: Silver's day move at or beyond this votes for gold (the metals bid or offered).
SILVER_FLAT = 0.5
#: Copper's day move past this is named in silver's note (industrial, not monetary),
#: and votes on silver's own board (its industrial half) and on crude's (demand).
COPPER_FLAT = 0.5
#: Gold's day move at or beyond this votes for silver: a quarter of a usual gold day.
GOLD_FLAT = 0.4
#: Gasoline and heating oil, averaged: their day move at or beyond this votes for crude.
PRODUCTS_FLAT = 0.75
#: The weekly crude inventories: a change, or a miss against consensus, of this many
#: barrels votes. The weekly figure is routinely a few million either way.
INVENTORY_FLAT = 1_000_000.0
_INVENTORIES = re.compile(r"crude oil inventories", re.I)

#: A quote whose feed is one of these printed today; "closed" and "stale" did not.
_LIVE = ("live", "delayed")


def _num(v: Any) -> float | None:
    if isinstance(v, bool) or not isinstance(v, (int, float)):
        return None
    return float(v)


def _q(quotes: list[dict[str, Any]], key: str) -> dict[str, Any] | None:
    return next((q for q in quotes if q.get("key") == key), None)


def _vote(key: str, label: str, layer: str, value: str, vote: str, note: str,
          live: bool = True) -> dict[str, Any]:
    """One read. `live` false means it cannot vote at this hour: not flat, absent."""
    return {"key": key, "label": label, "layer": layer, "value": value, "vote": vote,
            "note": note, "live": live}


def _side(x: float, long_at: float, short_at: float) -> str:
    """long at or above `long_at`, short at or below `short_at`, else neutral."""
    if long_at > short_at:
        return "long" if x >= long_at else "short" if x <= short_at else "neutral"
    return "long" if x <= long_at else "short" if x >= short_at else "neutral"


def _signed(x: float, dp: int, unit: str = "") -> str:
    return f"{x:+.{dp}f}{unit}"


def _px(v: float, of: float | None = None) -> str:
    """A price as the board says it: whole points from a thousand up (NQ, ES, gold),
    dollars and cents under it (silver, crude), where whole numbers put silver's
    value area at "49 · 49 · 49". A distance is said in its price's terms (`of`): 200
    points off an NQ flip is "200", 0.88 off silver's is "0.88"."""
    return f"{v:,.0f}" if abs(v if of is None else of) >= 1000 else f"{v:,.2f}"


def _trading(q: dict[str, Any] | None) -> bool:
    return q is not None and str(q.get("feed") or "") in _LIVE


def _stopped(q: dict[str, Any]) -> bool:
    """A row that says it has stopped printing. One that says nothing is trusted."""
    return q.get("feed") in ("closed", "stale")


# ---- macro -------------------------------------------------------------------


def _yields(quotes: list[dict[str, Any]], book: str, day: date | None = None) -> dict[str, Any]:
    q = _q(quotes, "US10Y")
    chg = _num(q.get("chg")) if q else None
    if q is None or chg is None:
        return _vote("yields", "10Y yield", "macro", "—", "neutral", "no 10Y on the board",
                     live=False)
    bp = chg * 100.0
    last = _num(q.get("last"))
    value = f"{last:.2f}% {_signed(bp, 1, 'bp')}" if last is not None else _signed(bp, 1, "bp")
    # A bond holiday (Columbus Day, Veterans Day: stocks trade, Treasuries do not). The
    # index still publishes a figure, and it is not a market: it cannot vote.
    shut = holidays.bond_closed(day) if day else None
    if shut:
        return _vote("yields", "10Y yield", "macro", value, "neutral",
                     f"the cash Treasury market is shut today ({shut}) — no live read",
                     live=False)
    if not _trading(q):
        return _vote("yields", "10Y yield", "macro", value, "neutral",
                     "the cash 10Y last printed at its close — no live read", live=False)
    if abs(bp) < YIELD_BP:
        return _vote("yields", "10Y yield", "macro", value, "neutral",
                     f"inside ±{YIELD_BP:.0f}bp on the day — no read")
    rising = bp > 0
    if book == "GC":
        note = ("yields up: the carrying cost of a zero-coupon asset rises — a headwind"
                if rising else "yields down: cheaper to hold gold — a tailwind")
    elif book == "SIL":
        note = ("yields up: a metal that pays nothing costs more to hold — a headwind"
                if rising else "yields down: cheaper to hold silver — a tailwind")
    else:
        note = ("the discount rate is rising — a headwind for a long-duration index"
                if rising else "the discount rate is falling — a tailwind")
    return _vote("yields", "10Y yield", "macro", value, "short" if rising else "long", note)


def _dollar(quotes: list[dict[str, Any]], book: str) -> dict[str, Any]:
    q = _q(quotes, "DXY")
    pct = _num(q.get("pct")) if q else None
    if q is None or pct is None:
        return _vote("dollar", "Dollar", "macro", "—", "neutral", "no DXY on the board",
                     live=False)
    value = _signed(pct, 2, "%")
    if _stopped(q):
        return _vote("dollar", "Dollar", "macro", value, "neutral",
                     "the dollar index has stopped printing — no live read", live=False)
    if abs(pct) < DXY_FLAT:
        return _vote("dollar", "Dollar", "macro", value, "neutral",
                     f"inside ±{DXY_FLAT}% — no read")
    up = pct > 0
    if book == "GC":
        note = ("a firmer dollar is the unit gold is priced in rising — a headwind" if up
                else "a softer dollar — a tailwind for gold")
    elif book == "SIL":
        note = ("a firmer dollar is the unit silver is priced in rising — a headwind" if up
                else "a softer dollar — a tailwind for silver")
    elif book == "CL":
        note = ("a firmer dollar makes the barrel dearer for every buyer paying in another "
                "currency — a headwind" if up
                else "a softer dollar makes the barrel cheaper outside America — a tailwind")
    else:
        note = ("a firmer dollar tightens conditions — a headwind" if up
                else "a softer dollar eases conditions — a tailwind")
    return _vote("dollar", "Dollar", "macro", value, "short" if up else "long", note)


def _credit(quotes: list[dict[str, Any]]) -> dict[str, Any]:
    q = _q(quotes, "HYG")
    pct = _num(q.get("pct")) if q else None
    if q is None or pct is None:
        return _vote("credit", "Credit (HYG)", "macro", "—", "neutral", "no HYG on the board",
                     live=False)
    value = _signed(pct, 2, "%")
    if not _trading(q):
        return _vote("credit", "Credit (HYG)", "macro", value, "neutral",
                     "the cash market is closed — credit votes from 09:30 ET", live=False)
    if abs(pct) < HYG_FLAT:
        return _vote("credit", "Credit (HYG)", "macro", value, "neutral",
                     f"inside ±{HYG_FLAT}% — no read")
    return _vote("credit", "Credit (HYG)", "macro", value, "long" if pct > 0 else "short",
                 "high yield bid — credit is taking risk" if pct > 0
                 else "high yield offered — credit is leaving risk before equities do")


def _vix_dir(quotes: list[dict[str, Any]], book: str) -> dict[str, Any]:
    q = _q(quotes, "VIX")
    pct = _num(q.get("pct")) if q else None
    if q is None or pct is None:
        return _vote("vix_dir", "VIX today", "macro", "—", "neutral", "no VIX on the board",
                     live=False)
    last = _num(q.get("last"))
    value = f"{last:.1f} {_signed(pct, 1, '%')}" if last is not None else _signed(pct, 1, "%")
    if not _trading(q):
        return _vote("vix_dir", "VIX today", "macro", value, "neutral",
                     "the VIX last printed at its close (it trades 03:00–16:15 ET)", live=False)
    if abs(pct) < VIX_FLAT:
        return _vote("vix_dir", "VIX today", "macro", value, "neutral",
                     f"inside ±{VIX_FLAT}% — no read")
    up = pct > 0
    if book == "GC":
        return _vote("vix_dir", "VIX today", "macro", value, "neutral",
                     "equity fear is not a gold vote on its own — the dollar and yields decide",
                     live=False)
    return _vote("vix_dir", "VIX today", "macro", value, "short" if up else "long",
                 "protection being bought — risk-off" if up else "protection being sold — risk-on")


def _vix_curve(quotes: list[dict[str, Any]], book: str) -> dict[str, Any]:
    vt = volterm.state(quotes)
    ratio, shape = _num(vt.get("ratio")), vt.get("shape")
    if ratio is None:
        return _vote("vix_curve", "VIX curve", "macro", "—", "neutral",
                     "VIX or VIX3M missing from the board", live=False)
    value = f"{ratio:.2f} · {shape or 'unknown'}"
    if book == "GC":
        return _vote("vix_curve", "VIX curve", "macro", value, "neutral",
                     "the equity curve is context for gold, not a vote", live=False)
    if ratio >= CURVE_STRESS:
        return _vote("vix_curve", "VIX curve", "macro", value, "short",
                     "flat to inverted: near-term protection bid now — stress")
    if ratio < CURVE_CALM:
        return _vote("vix_curve", "VIX curve", "macro", value, "long",
                     "steep contango: a calm tape, dips get bought")
    return _vote("vix_curve", "VIX curve", "macro", value, "neutral",
                 f"between {CURVE_CALM:.2f} and {CURVE_STRESS:.2f} — normal contango, no read")


def _silver(quotes: list[dict[str, Any]]) -> dict[str, Any]:
    q = _q(quotes, "SILVER")
    pct = _num(q.get("pct")) if q else None
    if q is None or pct is None:
        return _vote("silver", "Silver", "macro", "—", "neutral", "no silver on the board",
                     live=False)
    value = _signed(pct, 2, "%")
    if _stopped(q):
        return _vote("silver", "Silver", "macro", value, "neutral",
                     "silver has stopped printing — no live read", live=False)
    cu = _q(quotes, "COPPER")
    cpct = _num(cu.get("pct")) if cu else None
    tail = ""
    if cpct is not None and abs(cpct) >= COPPER_FLAT:
        same = (cpct > 0) == (pct > 0)
        tail = (f"; copper {_signed(cpct, 1, '%')} says the metals bid is "
                f"{'industrial as well' if same else 'monetary, not industrial'}")
    if abs(pct) < SILVER_FLAT:
        return _vote("silver", "Silver", "macro", value, "neutral",
                     f"inside ±{SILVER_FLAT}% — no read" + tail)
    return _vote("silver", "Silver", "macro", value, "long" if pct > 0 else "short",
                 ("the metals complex is bid — gold rarely falls alone" if pct > 0
                  else "the metals complex is offered") + tail)


# ---- silver's and crude's own reads (2026-11-15; bias.py says why these) ------------


def _gold(quotes: list[dict[str, Any]]) -> dict[str, Any]:
    """Gold's day move, for silver: the mirror of the silver read on gold's board."""
    q = _q(quotes, "GC")
    pct = _num(q.get("pct")) if q else None
    if q is None or pct is None:
        return _vote("gold", "Gold", "macro", "—", "neutral", "no gold on the board", live=False)
    value = _signed(pct, 2, "%")
    if _stopped(q):
        return _vote("gold", "Gold", "macro", value, "neutral",
                     "gold has stopped printing — no live read", live=False)
    if abs(pct) < GOLD_FLAT:
        return _vote("gold", "Gold", "macro", value, "neutral", f"inside ±{GOLD_FLAT}% — no read")
    return _vote("gold", "Gold", "macro", value, "long" if pct > 0 else "short",
                 "gold is bid — silver follows it, and moves further" if pct > 0
                 else "gold is offered — silver rarely holds when gold falls")


def _copper(quotes: list[dict[str, Any]], book: str) -> dict[str, Any]:
    """Copper's day move: silver's industrial half, and crude's demand read."""
    q = _q(quotes, "COPPER")
    pct = _num(q.get("pct")) if q else None
    if q is None or pct is None:
        return _vote("copper", "Copper", "macro", "—", "neutral", "no copper on the board",
                     live=False)
    value = _signed(pct, 2, "%")
    if _stopped(q):
        return _vote("copper", "Copper", "macro", value, "neutral",
                     "copper has stopped printing — no live read", live=False)
    if abs(pct) < COPPER_FLAT:
        return _vote("copper", "Copper", "macro", value, "neutral",
                     f"inside ±{COPPER_FLAT}% — no read")
    up = pct > 0
    if book == "CL":
        note = ("copper is bid — the growth trade is on, and crude is a demand market" if up
                else "copper is offered — the growth trade is coming off, and demand with it")
    else:
        note = ("copper is bid — the industrial half of silver's demand is with it" if up
                else "copper is offered — the industrial half of silver's demand is leaving")
    return _vote("copper", "Copper", "macro", value, "long" if up else "short", note)


def _products(quotes: list[dict[str, Any]]) -> dict[str, Any]:
    """Gasoline and heating oil, for crude: whether the barrel is being pulled through."""
    legs = [(name, q) for name, key in (("gasoline", "RBOB"), ("heating oil", "HEATOIL"))
            if (q := _q(quotes, key)) is not None and _num(q.get("pct")) is not None]
    if not legs:
        return _vote("products", "Products", "macro", "—", "neutral",
                     "no gasoline or heating oil on the board", live=False)
    value = " · ".join(f"{name} {_signed(float(q['pct']), 2, '%')}" for name, q in legs)
    printing = [float(q["pct"]) for _, q in legs if not _stopped(q)]
    if not printing:
        return _vote("products", "Products", "macro", value, "neutral",
                     "the products have stopped printing — no live read", live=False)
    avg = sum(printing) / len(printing)
    if abs(avg) < PRODUCTS_FLAT:
        return _vote("products", "Products", "macro", value, "neutral",
                     f"{_signed(avg, 2, '%')} between them, inside ±{PRODUCTS_FLAT}% — no read")
    return _vote("products", "Products", "macro", value, "long" if avg > 0 else "short",
                 "the products are bid — refiners are paying up, the barrel is being pulled "
                 "through" if avg > 0
                 else "the products are offered — nothing is pulling the barrel through")


def _barrels(n: float) -> str:
    return f"{n / 1e6:+.1f}M bbl"


def _inventories(calendar: list[dict[str, Any]], now: datetime) -> dict[str, Any]:
    """The weekly crude inventories, on the day they print: a build is short, a draw long.

    Against consensus where the calendar carries one; the week's change itself where it
    does not (the stand-in feed lists the figure and no forecast), which is still the
    fact a desk reacts to. It votes from its print to the end of that New York day."""
    et = report.ET
    today = now.astimezone(et).date()
    rows = [r for r in calendar
            if _INVENTORIES.search(str(r.get("event") or ""))
            and not re.search(r"\bapi\b|cushing", str(r.get("event") or ""), re.I)
            and _num(r.get("ts")) is not None]
    mine = [r for r in rows if datetime.fromtimestamp(float(r["ts"]), et).date() == today]
    if not mine:
        nxt = min((r for r in rows if float(r["ts"]) > now.timestamp()),
                  key=lambda r: float(r["ts"]), default=None)
        when = (f"next {datetime.fromtimestamp(float(nxt['ts']), et):%a %H:%M} ET"
                if nxt else "none on the calendar")
        return _vote("inventories", "Crude inventories", "macro", "—", "neutral",
                     f"no inventories report today — {when}", live=False)
    r = mine[-1]
    actual = _num(r.get("actual"))
    at = datetime.fromtimestamp(float(r["ts"]), et)
    if not r.get("released") or actual is None:
        return _vote("inventories", "Crude inventories", "macro", "—", "neutral",
                     f"due {at:%H:%M} ET today", live=False)
    cons = _num(r.get("consensus"))
    miss = actual - cons if cons is not None else actual
    value = _barrels(actual) + (f" vs {_barrels(cons)} expected" if cons is not None else "")
    basis = "against consensus" if cons is not None else "on the week (no consensus on the feed)"
    if abs(miss) < INVENTORY_FLAT:
        return _vote("inventories", "Crude inventories", "macro", value, "neutral",
                     f"inside ±{INVENTORY_FLAT / 1e6:.0f}M barrels {basis} — no read")
    build = miss > 0
    than = "expected" if cons is not None else "a week ago"
    return _vote("inventories", "Crude inventories", "macro", value, "short" if build else "long",
                 (f"more crude in store than {than} ({_barrels(miss)} {basis}) — supply is "
                  "ahead of demand" if build
                  else f"less crude in store than {than} ({_barrels(miss)} {basis}) — demand is "
                       "ahead of supply"))


def _growth_prints(calendar: list[dict[str, Any]], now: datetime) -> dict[str, Any]:
    """Today's US growth prints, for crude: stronger activity is more barrels burned.

    On the index books a growth print is read and not counted, because strong data
    cuts both ways for an equity. For crude it is demand: hot is long, cold is short."""
    rows = [p for p in marketctx.prints(calendar, now) if p.get("released") and p.get("read")
            and "growth" in (p.get("themes") or [])]
    if not rows:
        return _vote("prints", "US growth prints", "macro", "—", "neutral",
                     "no US growth print has landed today", live=False)
    named = " · ".join(f"{p['title']} {p['read']}" for p in rows[-3:])
    reads = {p["read"] for p in rows}
    if reads == {"hot"}:
        return _vote("prints", "US growth prints", "macro", named, "long",
                     "activity is running ahead of forecast — more demand for the barrel")
    if reads == {"cold"}:
        return _vote("prints", "US growth prints", "macro", named, "short",
                     "activity is running behind forecast — less demand for the barrel")
    return _vote("prints", "US growth prints", "macro", named, "neutral",
                 "growth prints mixed or in line — no read")


def _prints(calendar: list[dict[str, Any]], now: datetime, book: str) -> dict[str, Any]:
    """Today's inflation prints vote; the rest are named and read, not counted."""
    rows = [p for p in marketctx.prints(calendar, now) if p.get("released") and p.get("read")]
    if not rows:
        due = [p for p in marketctx.prints(calendar, now) if not p.get("done")]
        nxt = due[0] if due else None
        return _vote("prints", "US prints", "macro", "—", "neutral",
                     f"nothing printed yet — next {nxt['title']} at {nxt['et']} ET" if nxt
                     else "no US print scored 3 or more today", live=False)
    infl = [p for p in rows if "inflation" in (p.get("themes") or [])]
    named = " · ".join(f"{p['title']} {p['read']}" for p in rows[-3:])
    if not infl:
        last = rows[-1]
        imp = releases.implication(last.get("read"), last.get("themes")) or {}
        return _vote("prints", "US prints", "macro", named, "neutral",
                     imp.get(book) or "no inflation print today — read, not counted", live=False)
    reads = {p["read"] for p in infl}
    if reads == {"hot"}:
        v = "short"
    elif reads == {"cold"}:
        v = "long"
    else:
        v = "neutral"
    imp = releases.implication("hot" if v == "short" else "cold" if v == "long" else "inline",
                               ["inflation"]) or {}
    note = imp.get(book) or "inflation prints mixed"
    if v == "neutral":
        note = "inflation prints mixed or in line — no read"
    return _vote("prints", "US prints", "macro", named, v, note)


# ---- positioning -------------------------------------------------------------


def _gamma(gex: dict[str, Any] | None, book: str, last: float | None,
           sigma: float | None) -> dict[str, Any]:
    """Dealer gamma: the regime and where spot sits against the flip. NEVER A SIDE
    (bias.BOARD_FAMILY): it voted long above the flip and short below it until
    2026-11-12, which read positive gamma as bullish. It says how far a move runs."""
    def row(value: str, note: str, live: bool = True) -> dict[str, Any]:
        v = _vote("gamma", "Dealer gamma", "positioning", value, "neutral", note, live=live)
        v["aside"] = "never a side: the regime says how far a move runs, not which way"
        return v

    a = ((gex or {}).get("assets") or {}).get(book) if isinstance(gex, dict) else None
    if not isinstance(a, dict) or not a.get("ok"):
        return row("—", "GEXYGEN is not answering — no gamma read", live=False)
    regime = a.get("regime") if a.get("regime") in ("POS", "NEG") else None
    flip = next((_num(lv.get("price")) for lv in a.get("levels") or []
                 if lv.get("key") == "flip"), None)
    spot = last if last is not None else _num(a.get("spot"))
    word = {"POS": "positive γ", "NEG": "negative γ", None: "no regime"}[regime]
    if flip is None or spot is None:
        return row(word, "no gamma flip to read spot against", live=False)
    above = spot >= flip
    dist = spot - flip
    in_sig = f" ({abs(dist) / sigma:.1f}σ)" if sigma else ""
    value = f"{word} · {'above' if above else 'below'} flip {_px(flip)}"
    how = ("dealers damp moves — fade into the walls, ranges hold" if regime == "POS"
           else "dealers chase moves — breaks run, trade the break not the fade"
           if regime == "NEG" else "regime unknown")
    side = "above" if above else "below"
    return row(value, f"spot {_px(abs(dist), flip)} {side} the flip{in_sig}; "
                      f"{how}. Not a direction: positive is not bullish, negative is not bearish")


# ---- structure ---------------------------------------------------------------


def _value(profiles: dict[str, Any] | None, book: str, last: float | None) -> dict[str, Any]:
    a = ((profiles or {}).get("assets") or {}).get(book) if isinstance(profiles, dict) else None
    rows = {r.get("key"): r for r in (a or {}).get("rows") or []} if isinstance(a, dict) else {}
    prev = rows.get("prev_rth")
    if not prev or last is None:
        return _vote("value", "Prior value", "structure", "—", "neutral",
                     "no prior RTH profile yet", live=False)
    pos = value_position(last, prev.get("vah"), prev.get("val"))
    vah, val, poc = prev.get("vah"), prev.get("val"), prev.get("poc")
    area = f"VAL {_px(val)} · POC {_px(poc)} · VAH {_px(vah)}" if vah and val and poc else "no area"
    if pos == "above_value":
        return _vote("value", "Value area", "structure", f"above (VAH {_px(vah)})", "long",
                     f"trading above yesterday's value area — acceptance higher; {area}")
    if pos == "below_value":
        return _vote("value", "Value area", "structure", f"below (VAL {_px(val)})", "short",
                     f"trading below yesterday's value area — acceptance lower; {area}")
    return _vote("value", "Value area", "structure", "inside", "neutral",
                 f"inside yesterday's value — rotation, the POC is the magnet; {area}")


def _session(ranges: dict[str, Any] | None, book: str, last: float | None) -> dict[str, Any]:
    a = ((ranges or {}).get("assets") or {}).get(book) if isinstance(ranges, dict) else None
    rows = [r for r in (a or {}).get("sessions") or []
            if isinstance(r, dict) and r.get("ok") and r.get("status") == "complete"]
    if not rows or last is None:
        return _vote("session", "Last session", "structure", "—", "neutral",
                     "no completed session to read against", live=False)
    r = max(rows, key=lambda x: _num(x.get("start_ts")) or 0.0)
    hi, lo = _num(r.get("high")), _num(r.get("low"))
    label = str(r.get("label") or "the last session")
    if hi is None or lo is None:
        return _vote("session", "Last session", "structure", "—", "neutral", "no range",
                     live=False)
    value = f"{label} {_px(lo)}–{_px(hi)}"
    if last > hi:
        return _vote("session", "Last session", "structure", value, "long",
                     f"{label}'s high is taken out — the handover is higher")
    if last < lo:
        return _vote("session", "Last session", "structure", value, "short",
                     f"{label}'s low is taken out — the handover is lower")
    pos = (last - lo) / (hi - lo) if hi > lo else 0.5
    return _vote("session", "Last session", "structure", value, "neutral",
                 f"inside {label}'s range, {pos * 100:.0f}% of the way up it")


def _trend10m(ranges: dict[str, Any] | None, book: str, last: float | None) -> dict[str, Any]:
    """The ten-minute 200 EMA as a side: the strategy's own filter (2026-10-30)."""
    a = ((ranges or {}).get("assets") or {}).get(book) if isinstance(ranges, dict) else None
    e = (a or {}).get("ema200_10m") if isinstance(a, dict) else None
    line = _num(e.get("value")) if isinstance(e, dict) else None
    if line is None or last is None:
        return _vote("trend10m", "10m trend", "structure", "—", "neutral",
                     "no ten-minute history yet — the 200 EMA needs two days of bars", live=False)
    slope = str(e.get("slope") or "flat") if isinstance(e, dict) else "flat"
    px = _px(line)
    side = structure.side_of(last, line)
    if side == "above":
        return _vote("trend10m", "10m trend", "structure", f"above {px}", "long",
                     f"above the 10-minute 200 EMA ({px}), and it is {slope} — "
                     "longs have the line under them; a short retest into it tends to fail")
    if side == "below":
        return _vote("trend10m", "10m trend", "structure", f"below {px}", "short",
                     f"below the 10-minute 200 EMA ({px}), and it is {slope} — "
                     "shorts have the line over them; a long retest into it tends to fail")
    return _vote("trend10m", "10m trend", "structure", f"on {px}", "neutral",
                 f"sitting on the 10-minute 200 EMA ({px}) — the line itself decides")


def _regime200(frames: dict[str, Any] | None, book: str, last: float | None) -> dict[str, Any]:
    """The daily 200 EMA as a vote (owner, 2026-10-30: the 200s "accounted for"
    in the bias). The daily frame's vote is decided by the 20 and the 50 and
    only names the 200; this one is the 200's own — the regime, above or
    below, with half a percent either side reading as "on it"."""
    fr = ((frames or {}).get("books") or {}).get(book) if isinstance(frames, dict) else None
    line = _num(fr.get("ema200")) if isinstance(fr, dict) and fr.get("ok") else None
    if line is None or last is None:
        return _vote("daily200", "Daily 200", "structure", "—", "neutral",
                     "no daily history yet — the 200-day EMA needs a year of sessions", live=False)
    pct = (last - line) / line * 100.0
    px = _px(line)
    side = structure.side_of(last, line, structure.DAILY_ON_PCT)
    if side == "above":
        return _vote("daily200", "Daily 200", "structure", f"above {px}", "long",
                     f"{pct:.1f}% above the 200-day EMA ({px}) — the daily regime is up; "
                     "dips are bought until it breaks")
    if side == "below":
        return _vote("daily200", "Daily 200", "structure", f"below {px}", "short",
                     f"{abs(pct):.1f}% below the 200-day EMA ({px}) — the daily regime is down; "
                     "rallies are sold until it is reclaimed")
    return _vote("daily200", "Daily 200", "structure", f"on {px}", "neutral",
                 f"within half a percent of the 200-day EMA ({px}) — the regime is being decided")


def _frame(frames: dict[str, Any] | None, book: str, last: float | None) -> dict[str, Any]:
    fr = ((frames or {}).get("books") or {}).get(book) if isinstance(frames, dict) else None
    rd = frame_mod.read(fr if isinstance(fr, dict) and fr.get("ok") else None, last)
    if rd is None:
        return _vote("frame", "Daily frame", "structure", "—", "neutral",
                     "no daily history yet", live=False)
    text = rd.get("text") or "—"
    # The averages clause alone is the figure; the whole read is the note.
    value = text.split(" · ")[0]
    v = "long" if rd["trend"] == "up" else "short" if rd["trend"] == "down" else "neutral"
    word = {"long": "the daily trend is up", "short": "the daily trend is down",
            "neutral": "between the averages — no daily trend to lean on"}[v]
    return _vote("frame", "Daily frame", "structure", value, v, f"{word}; {text}")


def _leaders(constituents: dict[str, Any] | None, book: str, cash_open: bool) -> dict[str, Any]:
    # The constituents block is keyed by the BOOK (NQ, ES), each block naming
    # its index — marketctx.breadth reads it the same way.
    ix = ((constituents or {}).get("indices") or {}).get(book) \
        if isinstance(constituents, dict) else None
    mem = [m for m in (ix or {}).get("members") or [] if isinstance(m, dict)] if ix else []
    pcts = [p for m in mem if (p := _num(m.get("pct"))) is not None]
    up, down = sum(p > 0 for p in pcts), sum(p < 0 for p in pcts)
    label = f"{INDEX_OF.get(book, 'Index')} leaders"
    value = f"{up} up · {down} down" if pcts else "—"
    if not cash_open:
        return _vote("leaders", label, "structure", value, "neutral",
                     "the last session's changes — the leaders vote from 09:30 ET", live=False)
    if up + down < PART_MIN:
        return _vote("leaders", label, "structure", value, "neutral",
                     f"only {up + down} of the leaders reporting", live=False)
    pct = up / (up + down) * 100.0
    v = _side(pct, PART_LONG, PART_SHORT)
    note = {"long": f"{pct:.0f}% of the leaders up — the weight is behind the move",
            "short": f"only {pct:.0f}% of the leaders up — the weight is selling",
            "neutral": f"{pct:.0f}% up — split leadership"}[v]
    return _vote("leaders", label, "structure", value, v, note)


# ---- the catalysts (events.py) ------------------------------------------------


def _heavyweight_prints(heavy: list[dict[str, Any]], book: str) -> dict[str, Any]:
    """What the names that just reported have added to the index since, in
    percentage points — a macro vote past ±PRINTS_VOTE_PP, since a megacap's print
    is the largest scheduled macro an index future has (2026-10-30). A name that
    has reported and not yet traded in the cash session is named and does not
    vote: the only move on its row is the session before the report (2026-11-05)."""
    label = f"{INDEX_OF.get(book, 'Index')} prints"
    net, who = events_mod.net_print_points(heavy)
    waiting = events_mod.awaiting_open(heavy)
    named = f"{', '.join(waiting[:4])} reported — the cash move comes at the open"
    if not who:
        if waiting:
            return _vote("hw_prints", label, "macro", ", ".join(waiting[:4]), "neutral", named,
                         live=False)
        return _vote("hw_prints", label, "macro", "—", "neutral",
                     "no heavyweight has reported in the last day and a half", live=False)
    value = f"{net:+.2f}pp · {', '.join(who[:4])}"
    tail = f"; {named}" if waiting else ""
    if abs(net) < events_mod.PRINTS_VOTE_PP:
        return _vote("hw_prints", label, "macro", value, "neutral",
                     f"inside ±{events_mod.PRINTS_VOTE_PP:.2f} percentage points of the index "
                     f"— the prints net out{tail}")
    v = "long" if net > 0 else "short"
    return _vote("hw_prints", label, "macro", value, v,
                 f"the names that just reported are {'carrying' if v == 'long' else 'dragging'} "
                 f"the index by {abs(net):.2f} percentage points{tail}")


def _event_risk(events: list[dict[str, Any]]) -> dict[str, Any]:
    """Event risk since the close — a DAMPER, not a direction (events.py): the
    vote is always neutral, and when an event is on the board the count's
    ceiling drops a notch (book_board)."""
    if not events:
        v = _vote("event_risk", "Event risk", "macro", "none", "neutral",
                  "no high-impact geopolitics, policy or energy story since the close")
        v["damper"] = False
        return v
    lead = events[0]
    reach = ", ".join(lead.get("channels") or []) or "the tape"
    n = len(events)
    v = _vote("event_risk", "Event risk", "macro", f"{n} since the close", "neutral",
              f"{lead.get('title')} ({reach}) — risk on the tape caps conviction a notch lower")
    v["damper"] = True
    return v


# ---- context rows ------------------------------------------------------------


def _context(book: str, cot: dict[str, Any] | None, putcall: dict[str, Any] | None,
             expiry: dict[str, Any] | None, fed: dict[str, Any] | None) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    c = ((cot or {}).get("books") or {}).get(book) if isinstance(cot, dict) else None
    if isinstance(c, dict) and c.get("ok"):
        net = c.get("net") or 0
        out.append({"key": "cot", "label": f"COT · {c.get('spec')}",
                    "value": f"net {'long' if net >= 0 else 'short'} {abs(net):,.0f} · "
                             f"{cot_mod.ordinal(c.get('pctile'))} pct",
                    "note": f"{c.get('read')} As of {c.get('as_of')}."})
    elif book in COT_BOOKS:
        # Silver and crude are not among the contracts the CFTC file is read for: no
        # row, where "has not answered" would say a feed was down.
        out.append({"key": "cot", "label": "COT", "value": "—",
                    "note": "the CFTC has not answered"})
    if book in INDEX_OF:
        pc = putcall if isinstance(putcall, dict) else None
        if pc and pc.get("ratios"):
            r, rd = pc["ratios"], pc.get("read") or {}
            eq, tot = r.get("equity"), r.get("total")
            out.append({"key": "putcall", "label": "Cboe put/call",
                        "value": f"equity {eq:.2f} · total {tot:.2f}" if eq is not None
                        and tot is not None else "—",
                        "note": f"Equity {rd.get('equity') or '—'} Total {rd.get('total') or '—'} "
                                f"({pc.get('date')})"})
        else:
            out.append({"key": "putcall", "label": "Cboe put/call", "value": "—",
                        "note": "no daily ratios yet"})
    # The monthly expiry is the equity options'; gold has carried the row since the
    # board was built, silver and crude do not.
    if book not in ("SIL", "CL") and isinstance(expiry, dict) and expiry.get("opex_week"):
        out.append({"key": "opex", "label": "OpEx week", "value": "this week",
                    "note": str(expiry.get("note") or "the near book is at its largest; "
                                "price pins to the walls into Friday")})
    if book == "GC" and isinstance(fed, dict) and fed.get("note"):
        out.append({"key": "fed", "label": "Next FOMC", "value": f"{fed.get('next_bp'):+.0f}bp"
                    if _num(fed.get("next_bp")) is not None else "—",
                    "note": str(fed.get("note"))})
    return out


def book_board(book: str, *, quotes: list[dict[str, Any]], calendar: list[dict[str, Any]],
               gex: dict[str, Any] | None, profiles: dict[str, Any] | None,
               ranges: dict[str, Any] | None, frames: dict[str, Any] | None,
               sectors: list[dict[str, Any]], constituents: dict[str, Any] | None,
               cot: dict[str, Any] | None, putcall: dict[str, Any] | None,
               expiry: dict[str, Any] | None, fed: dict[str, Any] | None,
               sigma: float | None, scan_session: str, now: datetime, weigh: str,
               heavy: list[dict[str, Any]] | None = None,
               events: list[dict[str, Any]] | None = None) -> dict[str, Any]:
    # Silver and crude ride the board under SILVER and WTI (volterm.quote_key).
    q = _q(quotes, volterm.quote_key(book))
    last = _num(q.get("last")) if q else None
    cash_open = scan_session == "rth"
    day = now.astimezone(report.ET).date()
    # THE MACRO READS ARE THE BOOK'S OWN (bias.py says what each answers to). The
    # index books and gold are as they were; silver reads rates and the dollar as gold
    # does, with gold and copper beside them; crude reads the dollar, the products,
    # credit and copper, its inventories and the day's growth prints, and neither the
    # 10-year nor the VIX.
    votes: list[dict[str, Any]]
    if book == "SIL":
        votes = [_yields(quotes, book, day), _dollar(quotes, book), _gold(quotes),
                 _copper(quotes, book), _prints(calendar, now, book)]
    elif book == "CL":
        votes = [_dollar(quotes, book), _products(quotes), _credit(quotes),
                 _copper(quotes, book), _inventories(calendar, now),
                 _growth_prints(calendar, now)]
    else:
        votes = [_yields(quotes, book, day), _dollar(quotes, book),
                 _silver(quotes) if book == "GC" else _credit(quotes),
                 _vix_dir(quotes, book), _vix_curve(quotes, book), _prints(calendar, now, book)]
    # No trend read (owner, 2026-11-15; bias.BOARD_FAMILY has the why): the daily
    # frame, the 200-day EMA and the ten-minute 200 EMA were three rows here and are
    # none. `_frame`, `_regime200` and `_trend10m` are kept below, unused, as the way
    # back: put them in this list and their families in bias.py.
    votes += [_gamma(gex, book, last, sigma),
              _value(profiles, book, last), _session(ranges, book, last)]
    if book in INDEX_OF:
        sv = marketctx._sectors_vote(sectors, scan_session)
        sv["layer"] = "structure"
        votes.append(sv)
        votes.append(_leaders(constituents, book, cash_open))
        votes.append(_heavyweight_prints(heavy or [], book))
    risk = _event_risk(events or [])
    # What the board prints beside a read that is in no family: each says why it is not a side.
    risk["aside"] = "never a side: on the tape, it lowers the ceiling a notch"
    votes.append(risk)
    a = ((gex or {}).get("assets") or {}).get(book) if isinstance(gex, dict) else None
    regime = a.get("regime") if isinstance(a, dict) and a.get("ok") and a.get("regime") in (
        "POS", "NEG") else None
    return {
        "key": book, "last": last,
        **bias_mod.board_read(book, votes, weigh, regime=regime, ny_open=cash_open,
                              events=len(events or [])),
        "context": _context(book, cot, putcall, expiry, fed),
    }


def weights_for(now: datetime) -> str:
    """Which session's weights the board reads at this instant: the session a note
    pressed now would be written for (report.resolve_session), New York's split at
    its bell. Pure."""
    session = report.resolve_session({"et": now.astimezone(report.ET).isoformat()}, "auto")
    return bias_mod.session_key(session, bool(report.session_progress(session, now)["underway"]))


def build(snap: dict[str, Any], scan_session: str = "closed",
          now: datetime | None = None) -> dict[str, Any]:
    """The driver board for every book from the snapshot's blocks. Pure."""
    now = now or datetime.now(UTC)
    quotes = [x for x in snap.get("quotes") or [] if isinstance(x, dict)]
    books_sigma = {b.get("key"): _num(b.get("sigma"))
                   for b in ((snap.get("volterm") or {}).get("books") or [])
                   if isinstance(b, dict)}
    fed = marketctx.fed(snap.get("policy_meetings") if isinstance(snap.get("policy_meetings"),
                                                                  dict) else None)
    events = events_mod.event_risk(snap, now)
    weigh = weights_for(now)
    boards = {
        book: book_board(
            book, quotes=quotes,
            calendar=[c for c in snap.get("calendar") or [] if isinstance(c, dict)],
            gex=snap.get("gex") if isinstance(snap.get("gex"), dict) else None,
            profiles=snap.get("profiles") if isinstance(snap.get("profiles"), dict) else None,
            ranges=snap.get("ranges") if isinstance(snap.get("ranges"), dict) else None,
            frames=snap.get("history") if isinstance(snap.get("history"), dict) else None,
            sectors=[s for s in snap.get("sectors") or [] if isinstance(s, dict)],
            constituents=snap.get("constituents") if isinstance(snap.get("constituents"), dict)
            else None,
            cot=snap.get("cot") if isinstance(snap.get("cot"), dict) else None,
            putcall=snap.get("putcall") if isinstance(snap.get("putcall"), dict) else None,
            expiry=snap.get("expiry") if isinstance(snap.get("expiry"), dict) else None,
            fed=fed, sigma=books_sigma.get(book), scan_session=scan_session, now=now, weigh=weigh,
            heavy=events_mod.heavyweights(snap, book, now) if book in INDEX_OF else None,
            events=events,
        )
        for book in BOOKS
    }
    return {
        "built_utc": now.astimezone(UTC).isoformat(),
        "session": scan_session,
        "ny_open": scan_session == "rth",
        "weights": weigh,
        "books": boards,
    }
