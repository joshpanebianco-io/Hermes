"""
The driver board — the futures Terminal's engine-computed read, per book.

WHY (owner, 2026-10-22: "do everything you recommend"). The stocks desk has
had a tape count since 2026-10-14: eleven independent reads of the tape,
each a vote with its threshold stated, graded, and the ceiling the game
plan's convictions are capped at. The futures desk had nothing of the kind:
its macro breakdown lived only in the Analysis brief, on demand, minutes to
run on a free model, two runs free to disagree. Between briefs the Terminal
showed the 10Y up six basis points and said nothing about what that did to
NQ or to gold. This is the same count re-cast for NQ, ES and GC — every
driver a vote with its threshold and its reason, graded by the stocks desk's
own arithmetic (marketctx.conviction), with one line on how to treat it.

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
leaders, the VIX's day change) is a neutral vote that says "closed" outside
US hours — the futures desk runs through Asia and London, and a count that
quietly dropped a vote would read stronger than it is.

PURE. `build` takes the snapshot's blocks and does no I/O; computed on read
like volterm and expiry.
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

from . import events as events_mod
from . import frame as frame_mod
from . import marketctx, releases, structure, volterm
from .profile import value_position

BOOKS: tuple[str, ...] = ("NQ", "ES", "GC")
#: Which cash index each equity book's leaders are read from.
INDEX_OF = {"NQ": "NDX", "ES": "SPX"}

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
#: Copper's day move past this is named in silver's note (industrial, not monetary).
COPPER_FLAT = 0.5

#: A quote whose feed is one of these printed today; "closed" and "stale" did not.
_LIVE = ("live", "delayed")


def _num(v: Any) -> float | None:
    if isinstance(v, bool) or not isinstance(v, (int, float)):
        return None
    return float(v)


def _q(quotes: list[dict[str, Any]], key: str) -> dict[str, Any] | None:
    return next((q for q in quotes if q.get("key") == key), None)


def _vote(key: str, label: str, layer: str, value: str, vote: str, note: str) -> dict[str, Any]:
    return {"key": key, "label": label, "layer": layer, "value": value, "vote": vote,
            "note": note}


def _side(x: float, long_at: float, short_at: float) -> str:
    """long at or above `long_at`, short at or below `short_at`, else neutral."""
    if long_at > short_at:
        return "long" if x >= long_at else "short" if x <= short_at else "neutral"
    return "long" if x <= long_at else "short" if x >= short_at else "neutral"


def _signed(x: float, dp: int, unit: str = "") -> str:
    return f"{x:+.{dp}f}{unit}"


def _trading(q: dict[str, Any] | None) -> bool:
    return q is not None and str(q.get("feed") or "") in _LIVE


# ---- macro -------------------------------------------------------------------


def _yields(quotes: list[dict[str, Any]], book: str) -> dict[str, Any]:
    q = _q(quotes, "US10Y")
    chg = _num(q.get("chg")) if q else None
    if q is None or chg is None:
        return _vote("yields", "10Y yield", "macro", "—", "neutral", "no 10Y on the board")
    bp = chg * 100.0
    last = _num(q.get("last"))
    value = f"{last:.2f}% {_signed(bp, 1, 'bp')}" if last is not None else _signed(bp, 1, "bp")
    if not _trading(q):
        return _vote("yields", "10Y yield", "macro", value, "neutral",
                     "the cash 10Y last printed at its close — no live read")
    if abs(bp) < YIELD_BP:
        return _vote("yields", "10Y yield", "macro", value, "neutral",
                     f"inside ±{YIELD_BP:.0f}bp on the day — no read")
    rising = bp > 0
    if book == "GC":
        note = ("yields up: the carrying cost of a zero-coupon asset rises — a headwind"
                if rising else "yields down: cheaper to hold gold — a tailwind")
    else:
        note = ("the discount rate is rising — a headwind for a long-duration index"
                if rising else "the discount rate is falling — a tailwind")
    return _vote("yields", "10Y yield", "macro", value, "short" if rising else "long", note)


def _dollar(quotes: list[dict[str, Any]], book: str) -> dict[str, Any]:
    q = _q(quotes, "DXY")
    pct = _num(q.get("pct")) if q else None
    if q is None or pct is None:
        return _vote("dollar", "Dollar", "macro", "—", "neutral", "no DXY on the board")
    value = _signed(pct, 2, "%")
    if abs(pct) < DXY_FLAT:
        return _vote("dollar", "Dollar", "macro", value, "neutral",
                     f"inside ±{DXY_FLAT}% — no read")
    up = pct > 0
    if book == "GC":
        note = ("a firmer dollar is the unit gold is priced in rising — a headwind" if up
                else "a softer dollar — a tailwind for gold")
    else:
        note = ("a firmer dollar tightens conditions — a headwind" if up
                else "a softer dollar eases conditions — a tailwind")
    return _vote("dollar", "Dollar", "macro", value, "short" if up else "long", note)


def _credit(quotes: list[dict[str, Any]]) -> dict[str, Any]:
    q = _q(quotes, "HYG")
    pct = _num(q.get("pct")) if q else None
    if q is None or pct is None:
        return _vote("credit", "Credit (HYG)", "macro", "—", "neutral", "no HYG on the board")
    value = _signed(pct, 2, "%")
    if not _trading(q):
        return _vote("credit", "Credit (HYG)", "macro", value, "neutral",
                     "the cash market is closed — credit votes from 09:30 ET")
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
        return _vote("vix_dir", "VIX today", "macro", "—", "neutral", "no VIX on the board")
    last = _num(q.get("last"))
    value = f"{last:.1f} {_signed(pct, 1, '%')}" if last is not None else _signed(pct, 1, "%")
    if not _trading(q):
        return _vote("vix_dir", "VIX today", "macro", value, "neutral",
                     "the VIX last printed at its close (it trades 03:00–16:15 ET)")
    if abs(pct) < VIX_FLAT:
        return _vote("vix_dir", "VIX today", "macro", value, "neutral",
                     f"inside ±{VIX_FLAT}% — no read")
    up = pct > 0
    if book == "GC":
        return _vote("vix_dir", "VIX today", "macro", value, "neutral",
                     "equity fear is not a gold vote on its own — the dollar and yields decide")
    return _vote("vix_dir", "VIX today", "macro", value, "short" if up else "long",
                 "protection being bought — risk-off" if up else "protection being sold — risk-on")


def _vix_curve(quotes: list[dict[str, Any]], book: str) -> dict[str, Any]:
    vt = volterm.state(quotes)
    ratio, shape = _num(vt.get("ratio")), vt.get("shape")
    if ratio is None:
        return _vote("vix_curve", "VIX curve", "macro", "—", "neutral",
                     "VIX or VIX3M missing from the board")
    value = f"{ratio:.2f} · {shape or 'unknown'}"
    if book == "GC":
        return _vote("vix_curve", "VIX curve", "macro", value, "neutral",
                     "the equity curve is context for gold, not a vote")
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
        return _vote("silver", "Silver", "macro", "—", "neutral", "no silver on the board")
    value = _signed(pct, 2, "%")
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


def _prints(calendar: list[dict[str, Any]], now: datetime, book: str) -> dict[str, Any]:
    """Today's inflation prints vote; the rest are named and read, not counted."""
    rows = [p for p in marketctx.prints(calendar, now) if p.get("released") and p.get("read")]
    if not rows:
        due = [p for p in marketctx.prints(calendar, now) if not p.get("done")]
        nxt = due[0] if due else None
        return _vote("prints", "US prints", "macro", "—", "neutral",
                     f"nothing printed yet — next {nxt['title']} at {nxt['et']} ET" if nxt
                     else "no US print scored 3 or more today")
    infl = [p for p in rows if "inflation" in (p.get("themes") or [])]
    named = " · ".join(f"{p['title']} {p['read']}" for p in rows[-3:])
    if not infl:
        last = rows[-1]
        imp = releases.implication(last.get("read"), last.get("themes")) or {}
        return _vote("prints", "US prints", "macro", named, "neutral",
                     imp.get(book) or "no inflation print today — read, not counted")
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
    a = ((gex or {}).get("assets") or {}).get(book) if isinstance(gex, dict) else None
    if not isinstance(a, dict) or not a.get("ok"):
        return _vote("gamma", "Dealer gamma", "positioning", "—", "neutral",
                     "GEXYGEN is not answering — no gamma read")
    regime = a.get("regime") if a.get("regime") in ("POS", "NEG") else None
    flip = next((_num(lv.get("price")) for lv in a.get("levels") or []
                 if lv.get("key") == "flip"), None)
    spot = last if last is not None else _num(a.get("spot"))
    word = {"POS": "positive γ", "NEG": "negative γ", None: "no regime"}[regime]
    if flip is None or spot is None:
        return _vote("gamma", "Dealer gamma", "positioning", word, "neutral",
                     "no gamma flip to read spot against")
    above = spot >= flip
    dist = spot - flip
    in_sig = f" ({abs(dist) / sigma:.1f}σ)" if sigma else ""
    value = f"{word} · {'above' if above else 'below'} flip {flip:,.0f}"
    how = ("dealers damp moves — fade into the walls, ranges hold" if regime == "POS"
           else "dealers chase moves — breaks run, trade the break not the fade"
           if regime == "NEG" else "regime unknown")
    return _vote("gamma", "Dealer gamma", "positioning", value, "long" if above else "short",
                 f"spot {abs(dist):,.0f} {'above' if above else 'below'} the flip{in_sig}; {how}")


# ---- structure ---------------------------------------------------------------


def _value(profiles: dict[str, Any] | None, book: str, last: float | None) -> dict[str, Any]:
    a = ((profiles or {}).get("assets") or {}).get(book) if isinstance(profiles, dict) else None
    rows = {r.get("key"): r for r in (a or {}).get("rows") or []} if isinstance(a, dict) else {}
    prev = rows.get("prev_rth")
    if not prev or last is None:
        return _vote("value", "Prior value", "structure", "—", "neutral",
                     "no prior RTH profile yet")
    pos = value_position(last, prev.get("vah"), prev.get("val"))
    vah, val, poc = prev.get("vah"), prev.get("val"), prev.get("poc")
    area = f"VAL {val:,.0f} · POC {poc:,.0f} · VAH {vah:,.0f}" if vah and val and poc else "no area"
    if pos == "above_value":
        return _vote("value", "Value area", "structure", f"above (VAH {vah:,.0f})", "long",
                     f"trading above yesterday's value area — acceptance higher; {area}")
    if pos == "below_value":
        return _vote("value", "Value area", "structure", f"below (VAL {val:,.0f})", "short",
                     f"trading below yesterday's value area — acceptance lower; {area}")
    return _vote("value", "Value area", "structure", "inside", "neutral",
                 f"inside yesterday's value — rotation, the POC is the magnet; {area}")


def _session(ranges: dict[str, Any] | None, book: str, last: float | None) -> dict[str, Any]:
    a = ((ranges or {}).get("assets") or {}).get(book) if isinstance(ranges, dict) else None
    rows = [r for r in (a or {}).get("sessions") or []
            if isinstance(r, dict) and r.get("ok") and r.get("status") == "complete"]
    if not rows or last is None:
        return _vote("session", "Last session", "structure", "—", "neutral",
                     "no completed session to read against")
    r = max(rows, key=lambda x: _num(x.get("start_ts")) or 0.0)
    hi, lo = _num(r.get("high")), _num(r.get("low"))
    label = str(r.get("label") or "the last session")
    if hi is None or lo is None:
        return _vote("session", "Last session", "structure", "—", "neutral", "no range")
    value = f"{label} {lo:,.0f}–{hi:,.0f}"
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
                     "no ten-minute history yet — the 200 EMA needs two days of bars")
    slope = str(e.get("slope") or "flat") if isinstance(e, dict) else "flat"
    px = f"{line:,.0f}" if line >= 1000 else f"{line:,.2f}"
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
                     "no daily history yet — the 200-day EMA needs a year of sessions")
    pct = (last - line) / line * 100.0
    px = f"{line:,.0f}" if line >= 1000 else f"{line:,.2f}"
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
                     "no daily history yet")
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
                     "the last session's changes — the leaders vote from 09:30 ET")
    if up + down < PART_MIN:
        return _vote("leaders", label, "structure", value, "neutral",
                     f"only {up + down} of the leaders reporting")
    pct = up / (up + down) * 100.0
    v = _side(pct, PART_LONG, PART_SHORT)
    note = {"long": f"{pct:.0f}% of the leaders up — the weight is behind the move",
            "short": f"only {pct:.0f}% of the leaders up — the weight is selling",
            "neutral": f"{pct:.0f}% up — split leadership"}[v]
    return _vote("leaders", label, "structure", value, v, note)


# ---- the catalysts (events.py) ------------------------------------------------


def _heavyweight_prints(heavy: list[dict[str, Any]], book: str) -> dict[str, Any]:
    """The index points supplied by the names that just reported — a macro vote
    past ±PRINTS_VOTE_POINTS, since a megacap's print is the largest scheduled
    macro an index future has (2026-10-30)."""
    label = f"{INDEX_OF.get(book, 'Index')} prints"
    net, who = events_mod.net_print_points(heavy)
    if not who:
        return _vote("hw_prints", label, "macro", "—", "neutral",
                     "no heavyweight has reported in the last day and a half")
    value = f"{net:+.2f} pts · {', '.join(who[:4])}"
    if abs(net) < events_mod.PRINTS_VOTE_POINTS:
        return _vote("hw_prints", label, "macro", value, "neutral",
                     f"inside ±{events_mod.PRINTS_VOTE_POINTS:.2f} index points — "
                     "the prints net out")
    v = "long" if net > 0 else "short"
    return _vote("hw_prints", label, "macro", value, v,
                 f"the names that just reported are {'carrying' if v == 'long' else 'dragging'} "
                 f"the index by {abs(net):.2f} points")


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
                             f"{c.get('pctile')}th pct",
                    "note": f"{c.get('read')} As of {c.get('as_of')}."})
    else:
        out.append({"key": "cot", "label": "COT", "value": "—",
                    "note": "the CFTC has not answered"})
    if book != "GC":
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
    if isinstance(expiry, dict) and expiry.get("opex_week"):
        out.append({"key": "opex", "label": "OpEx week", "value": "this week",
                    "note": str(expiry.get("note") or "the near book is at its largest; "
                                "price pins to the walls into Friday")})
    if book == "GC" and isinstance(fed, dict) and fed.get("note"):
        out.append({"key": "fed", "label": "Next FOMC", "value": f"{fed.get('next_bp'):+.0f}bp"
                    if _num(fed.get("next_bp")) is not None else "—",
                    "note": str(fed.get("note"))})
    return out


# ---- the count and the sentence ------------------------------------------------


def _lean(votes: list[dict[str, Any]], layer: str) -> str | None:
    mine = [v for v in votes if v["layer"] == layer]
    long_n = sum(v["vote"] == "long" for v in mine)
    short_n = sum(v["vote"] == "short" for v in mine)
    return "long" if long_n > short_n else "short" if short_n > long_n else None


def treatment(book: str, count: dict[str, Any], macro: str | None, structure: str | None,
              regime: str | None, ny_open: bool) -> str:
    """One line on how to treat the count — the words the strip prints. Pure."""
    bias, grade = count["bias"], count["grade"]
    side = {"long": "long", "short": "short", None: None}[bias]
    agreeing = [v for v in count["votes"] if v["vote"] == bias] if bias else []
    reasons = "; ".join(f"{v['label']} {v['value']}" for v in agreeing[:3])
    gamma = ("positive gamma: fade into the walls, ranges hold" if regime == "POS"
             else "negative gamma: breaks run, trade the break not the fade" if regime == "NEG"
             else "no gamma read")
    where = "" if ny_open else " (gamma is a reference outside New York)"
    conflict = macro and structure and macro != structure
    # The conflict is named before the count: a tie between the layers IS the
    # conflict, and "no lean" would hide what caused it.
    if conflict:
        return (f"Macro leans {macro} on {book} but structure accepts {structure}: a conflict. "
                f"Lower conviction, trade the levels not the lean — {gamma}{where}.")
    if bias is None or grade == "none":
        return (f"No lean on {book}: {count['neutral']} of {count['total']} reads are neutral"
                f". Trade the levels — {gamma}{where}.")
    if grade == "weak":
        return (f"Lean {side} {book}, weak ({count['agree']} of {count['total']}): {reasons}. "
                f"Small size until more reads agree — {gamma}{where}.")
    return (f"Lean {side} {book}, {grade} ({count['agree']} of {count['total']}, "
            f"{count['against']} against): {reasons}. {gamma[0].upper() + gamma[1:]}{where}.")


def book_board(book: str, *, quotes: list[dict[str, Any]], calendar: list[dict[str, Any]],
               gex: dict[str, Any] | None, profiles: dict[str, Any] | None,
               ranges: dict[str, Any] | None, frames: dict[str, Any] | None,
               sectors: list[dict[str, Any]], constituents: dict[str, Any] | None,
               cot: dict[str, Any] | None, putcall: dict[str, Any] | None,
               expiry: dict[str, Any] | None, fed: dict[str, Any] | None,
               sigma: float | None, scan_session: str, now: datetime,
               heavy: list[dict[str, Any]] | None = None,
               events: list[dict[str, Any]] | None = None) -> dict[str, Any]:
    q = _q(quotes, book)
    last = _num(q.get("last")) if q else None
    cash_open = scan_session == "rth"
    votes: list[dict[str, Any]] = [
        _yields(quotes, book), _dollar(quotes, book),
    ]
    if book == "GC":
        votes.append(_silver(quotes))
    else:
        votes.append(_credit(quotes))
    votes += [_vix_dir(quotes, book), _vix_curve(quotes, book), _prints(calendar, now, book),
              _gamma(gex, book, last, sigma),
              _value(profiles, book, last), _session(ranges, book, last),
              _frame(frames, book, last), _regime200(frames, book, last),
              _trend10m(ranges, book, last)]
    if book != "GC":
        sv = marketctx._sectors_vote(sectors, scan_session)
        sv["layer"] = "structure"
        votes.append(sv)
        votes.append(_leaders(constituents, book, cash_open))
        votes.append(_heavyweight_prints(heavy or [], book))
    risk = _event_risk(events or [])
    votes.append(risk)
    count = marketctx.conviction(votes)
    # THE DAMPER (events.py): an event on the tape is not a side, it is a
    # reason to be a notch less sure of any side — the same treatment a
    # macro-against-structure conflict gets, applied to the ceiling.
    if risk.get("damper"):
        count["max_conviction"] = max(1, int(count["max_conviction"]) - 1)
    macro, structure = _lean(votes, "macro"), _lean(votes, "structure")
    a = ((gex or {}).get("assets") or {}).get(book) if isinstance(gex, dict) else None
    regime = a.get("regime") if isinstance(a, dict) and a.get("ok") and a.get("regime") in (
        "POS", "NEG") else None
    ny_open = cash_open
    return {
        "key": book, "last": last,
        **{k: v for k, v in count.items() if k != "votes"},
        "votes": votes,
        "macro_lean": macro, "structure_lean": structure,
        "conflict": bool(macro and structure and macro != structure),
        "regime": regime,
        "event_risk": bool(risk.get("damper")),
        "treatment": treatment(book, count, macro, structure, regime, ny_open)
        + (f" Event risk since the close ({len(events or [])}): conviction capped a notch lower."
           if risk.get("damper") else ""),
        "context": _context(book, cot, putcall, expiry, fed),
    }


def build(snap: dict[str, Any], scan_session: str = "closed",
          now: datetime | None = None) -> dict[str, Any]:
    """The driver board for the three books from the snapshot's blocks. Pure."""
    now = now or datetime.now(UTC)
    quotes = [x for x in snap.get("quotes") or [] if isinstance(x, dict)]
    books_sigma = {b.get("key"): _num(b.get("sigma"))
                   for b in ((snap.get("volterm") or {}).get("books") or [])
                   if isinstance(b, dict)}
    fed = marketctx.fed(snap.get("policy_meetings") if isinstance(snap.get("policy_meetings"),
                                                                  dict) else None)
    events = events_mod.event_risk(snap, now)
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
            fed=fed, sigma=books_sigma.get(book), scan_session=scan_session, now=now,
            heavy=events_mod.heavyweights(snap, book, now) if book != "GC" else None,
            events=events,
        )
        for book in BOOKS
    }
    return {
        "built_utc": now.astimezone(UTC).isoformat(),
        "session": scan_session,
        "ny_open": scan_session == "rth",
        "books": boards,
    }
