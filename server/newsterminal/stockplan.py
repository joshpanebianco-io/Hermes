"""
The Game plan — the stocks desk's own brief, written before the New York open.

WHY A SECOND BRIEF AND NOT A FOURTH BOOK ON THE FIRST (owner instruction,
2026-10-13: "do everything you recommend" — the review's two-desk split). The
session report reads NQ, ES and GC across three sessions; this one reads the
Scanner's top names for one session, New York, and the owner trades them
through OPTIONS. Different instruments, different hours, a different strategy
and a different unit of risk — folding it into report.py would have meant a
fourth "book" whose tables, prompt, schema and sanitiser share nothing with the
other three. So it is its own module with its own storage, and it borrows only
the plumbing: the OpenRouter client, the model chain, the time budget, the JSON
extraction and the numerals guard, imported from report.py rather than copied.

THE STRATEGY IT WRITES FOR. LE_Model.pine's: a name breaks its pre-market or
previous-day high (low) and the trade is the RETEST of that level — or of VWAP /
the 8 EMA wave when price has run too far from the level for it to come back.
Every name in the facts carries the Scanner's own reading of that: the setup
state, the level, the entry reference and its distance in ten-minute ATRs.

THE TABLES ARE THE SERVER'S, THE WORDS ARE THE MODEL'S — the same split as the
futures brief. `build_facts` computes every figure the page prints; the model
supplies a headline, a read of the tape, and a plan per name, and a plan for a
name that is not in the facts is dropped before it is stored. Every numeral the
model writes is checked against what it was shown (report.unverified's rule);
one corrective re-ask, and whatever survives is stored as `unverified` for the
page to banner.

NO KEY, NO PLAN. As with the report, there is no local fallback: a game plan
invented by this app beside a real one would be indistinguishable from it.
"""

from __future__ import annotations

import contextlib
import json
import os
import re
import time
import urllib.error
from collections.abc import Iterable
from datetime import UTC, date, datetime, timedelta
from typing import Any
from zoneinfo import ZoneInfo

from . import frame, marketctx, optcalc
from . import report as rp
from .config import CACHE_DIR
from .holidays import close_time, next_trading_day
from .sources.shortint import SQUEEZE_PCT
from .targets import (  # noqa: F401 — re-exported for the tests
    MIN_REACH_BARS,
    MIN_REACH_DAY,
    entry_of,
    forming_levels,
    min_reach,
    sign_of,
    target_candidates,
)

ET = ZoneInfo("America/New_York")

PLANS_DIR = os.path.join(CACHE_DIR, "plans")
KEEP = 40

TOP_DEFAULT = 6
TOP_MIN = 4
TOP_MAX = 10

# Always in the facts, ranked or not: they are the tape the plan is read
# against, and the two names the owner trades 0DTE.
TAPE = ("SPY", "QQQ")
# Which expiry each name trades is optcalc's rule (`expiry_rule`, each row's
# `options.pick`) — one copy, read here, by the table and by Settings.

# Sources a plan stands on, worded for the Partial-data banner. Options are
# checked separately — see `_partial`.
PLAN_SOURCES: dict[str, str] = {
    "scanner": "Scanner bars",
    "scan_news": "Per-name headlines",
    "quotes": "Yahoo quotes (VIX and the tape)",
    "calendar": "Economic calendar",
    "earnings": "Earnings calendar",
}
OPTION_STATUS_KEYS = ("options", "scan_options", "scan_opts")


# --------------------------------------------------------------------------
# The facts — computed here, printed by the page, shown to the model.
# --------------------------------------------------------------------------


def _r(v: Any, dp: int = 2) -> float | None:
    """A number rounded to what the page prints — and so what the model can copy."""
    if isinstance(v, bool) or not isinstance(v, (int, float)):
        return None
    return round(float(v), dp)


def _parse_day(s: Any) -> date | None:
    if not isinstance(s, str):
        return None
    try:
        return date.fromisoformat(s[:10])
    except ValueError:
        return None


def _options(row: dict[str, Any]) -> dict[str, Any] | None:
    """The row's options context, summarised — or None when there is none yet.

    Read defensively: the options source is newer than this module, and an
    absent block, a None, or `ok: false` all mean "no options context", never
    an error. The contract summarised is the one the expiry rule picks for the
    name (optcalc.expiry_rule): the same-day one on the 0DTE names, the weekly on
    everything else.
    """
    o = row.get("options")
    if not isinstance(o, dict) or not o.get("ok"):
        return None
    em = {e.get("key"): e for e in o.get("em") or [] if isinstance(e, dict)}
    liq_raw = o.get("liquidity")
    liq: dict[str, Any] = liq_raw if isinstance(liq_raw, dict) else {}
    contracts = [c for c in o.get("contracts") or [] if isinstance(c, dict)]
    want = o.get("pick") or optcalc.pick_key(str(row.get("sym")))

    def pick(kind: str) -> dict[str, Any] | None:
        mine = [c for c in contracts if c.get("kind") == kind]
        return next((c for c in mine if c.get("key") == want), mine[0] if mine else None)

    lg, sp = pick("long"), pick("spread")
    front = em.get("front") or {}
    structure = o.get("structure") if isinstance(o.get("structure"), dict) else None
    earn = o.get("earnings_move") if isinstance(o.get("earnings_move"), dict) else None
    implied = earn.get("implied") if earn and isinstance(earn.get("implied"), dict) else None

    def r_of(c: dict[str, Any] | None) -> dict[str, Any] | None:
        """A contract's value at the first target and its R, when priced."""
        if c is None or c.get("r_multiple") is None:
            return None
        return {"target": _r(c.get("target_price")), "target_label": c.get("target_label"),
                "value_at_target": _r(c.get("target_mid")),
                "reward_per_contract": _r(c.get("reward_per_contract"), 0),
                "risk_per_contract": _r(c.get("risk_per_contract"), 0),
                "r": _r(c.get("r_multiple"))}

    return {
        # Long or spread by R at the first target when both are priced, else
        # by premium (optcalc.structure_pick) — the plan says which and why.
        "structure": None if structure is None else {
            "kind": structure.get("kind"), "by": structure.get("by"),
            "long_r": _r(structure.get("long_r")), "spread_r": _r(structure.get("spread_r"))},
        # The chain's own term structure, front to back: at-the-money IV per expiry.
        "term": [{"expiry": t.get("expiry"), "dte": _int(t.get("dte")), "iv": _r(t.get("iv"), 1)}
                 for t in o.get("term") or [] if isinstance(t, dict)][:4],
        # The earnings number: the move priced for the report against the
        # last few realised, when there is a report ahead or a history.
        "earnings_move": None if earn is None else {
            "implied_pct": _r(implied.get("pct"), 1) if implied else None,
            "implied_expiry": implied.get("expiry") if implied else None,
            "event_pct": _r(implied.get("clean_pct"), 1) if implied else None,
            "realised_pct": [_r(m.get("pct"), 1) for m in earn.get("realised") or []
                             if isinstance(m, dict)],
            "avg_abs_pct": _r(earn.get("avg_abs"), 1),
        },
        "iv30": _r(o.get("iv30"), 1),
        "iv_rv": _r(o.get("iv_rv")),
        "premium": o.get("premium") if isinstance(o.get("premium"), str) else None,
        "iv_rank": _r(o.get("iv_rank"), 0),
        "em_front_pct": _r(front.get("pct")),
        # The front straddle's own bounds and days to expiry: on a same-day
        # expiry they are today's expected move in prices, a target candidate.
        "em_front_dte": _int(front.get("dte")),
        "em_front_hi": _r(front.get("hi")),
        "em_front_lo": _r(front.get("lo")),
        "em_weekly_pct": _r((em.get("weekly") or {}).get("pct")),
        "liquidity": liq.get("grade") if isinstance(liq.get("grade"), str) else None,
        "earnings_in": o.get("earnings_in") if isinstance(o.get("earnings_in"), str) else None,
        "long": None if lg is None else {
            "expiry": lg.get("expiry"), "strike": _r(lg.get("strike")), "right": lg.get("right"),
            "mid": _r(lg.get("mid")), "delta": _r(lg.get("delta")),
            "at_target": r_of(lg),
        },
        "spread": None if sp is None else {
            "expiry": sp.get("expiry"), "strike": _r(sp.get("strike")),
            "short_strike": _r(sp.get("short_strike")), "mid": _r(sp.get("mid")),
            "at_target": r_of(sp),
        },
    }


def _int(v: Any) -> int | None:
    if isinstance(v, bool) or not isinstance(v, (int, float)):
        return None
    return round(float(v))


def _flow(row: dict[str, Any]) -> dict[str, Any] | None:
    """Today's options flow on the name, cut to what a plan cites: put/call
    volume, which way it leans, and the busiest strike. None until a chain has
    given one (the flow is the options source's; read here as optional)."""
    o = row.get("options")
    f = o.get("flow") if isinstance(o, dict) and o.get("ok") else None
    if not isinstance(f, dict):
        return None
    top = next((t for t in f.get("top") or [] if isinstance(t, dict)), None)
    return {
        "pc_vol": _r(f.get("pc_vol")),
        "lean": f.get("lean") if f.get("lean") in ("calls", "puts", "balanced") else None,
        "vol_oi": _r(f.get("vol_oi")),
        "top": None if top is None else {
            "strike": _r(top.get("strike")), "right": top.get("right"),
            "expiry": top.get("expiry"), "volume": _int(top.get("volume")),
            "oi": _int(top.get("oi")),
        },
    }


def _premkt(row: dict[str, Any]) -> dict[str, Any] | None:
    """The name's pre-market volume, and that as a share of its 20-day average."""
    pm = row.get("premkt")
    if not isinstance(pm, dict):
        return None
    return {"volume": _int(pm.get("volume")), "pct_adv": _r(pm.get("pct_adv"), 1)}


def _peers(row: dict[str, Any]) -> list[dict[str, Any]]:
    """Big caps in the name's sector reporting this week (the scanner's `peers`)."""
    return [{"sym": str(x.get("sym")), "date": str(x.get("date") or ""),
             "when": str(x.get("when") or "unspecified"), "days": _int(x.get("days"))}
            for x in row.get("peers") or [] if isinstance(x, dict) and x.get("sym")][:4]


# --------------------------------------------------------------------------
# Macro, per name (owner, 2026-10-13: "add a bit more detail in regards to
# macro news relevant to the stock"). Which of today's macro moves a name
# answers to, and which way — computed here, so the plan's "Macro:" line
# narrates a verdict the engine reached rather than one the model guessed.
# --------------------------------------------------------------------------

#: The macro moves a plan can cite: quote key, label, unit. Rates move in
#: basis points (the quote's change × 100); the rest in percent.
MACRO_QUOTES: list[tuple[str, str, str]] = [
    ("US10Y", "10Y yield", "bp"),
    ("DXY", "Dollar", "%"),
    ("WTI", "WTI crude", "%"),
    ("GC", "Gold", "%"),
    ("BTC", "Bitcoin", "%"),
]

#: Below these a move is "flat" — not a headwind or a tailwind worth a line.
FLAT = {"bp": 2.0, "%": 0.3}

#: For each sector SPDR, the drivers it answers to and the sign: +1 means the
#: driver rising HELPS the sector, -1 means it hurts. Deliberately coarse —
#: the textbook transmission, stated, not a fitted beta.
SECTOR_DRIVERS: dict[str, list[tuple[str, int, str]]] = {
    "XLK": [("US10Y", -1, "long-duration growth: higher yields discount its earnings harder"),
            ("DXY", -1, "multinational revenue: a stronger dollar shrinks it in translation")],
    "XLC": [("US10Y", -1, "growth multiple: rate-sensitive")],
    "XLY": [("US10Y", -1, "growth multiple and consumer credit: rate-sensitive"),
            ("WTI", -1, "the consumer's fuel bill")],
    "XLF": [("US10Y", 1, "net interest margins widen with higher yields")],
    "XLE": [("WTI", 1, "earnings move with the crude price")],
    "XLI": [("DXY", -1, "exporters: a stronger dollar prices them out")],
    "XLB": [("DXY", -1, "dollar-priced commodities"), ("GC", 1, "gold and metals producers")],
    "XLP": [("US10Y", -1, "a bond proxy: competes with yield")],
    "XLU": [("US10Y", -1, "a bond proxy: competes with yield")],
    "XLRE": [("US10Y", -1, "financing costs and cap rates")],
    "XLV": [],
}

#: Names whose own drivers outweigh a sector's: crypto-linked equities, and the
#: index ETFs, which have no sector SPDR of their own and would otherwise be
#: left for the model to guess at (a live plan did exactly that, 2026-10-13).
SYMBOL_DRIVERS: dict[str, list[tuple[str, int, str]]] = {
    **{sym: [("BTC", 1, "crypto-linked: trades with bitcoin")]
       for sym in ("COIN", "MSTR", "HOOD", "MARA", "RIOT", "CLSK")},
    "QQQ": [("US10Y", -1, "long-duration growth index: higher yields weigh on it"),
            ("DXY", -1, "multinational revenue: a stronger dollar shrinks it in translation")],
    "SPY": [("US10Y", -1, "equity multiples compete with yield")],
    "IWM": [("US10Y", -1,
             "small caps carry more floating-rate debt: higher yields cost them more")],
}


def macro_moves(quotes: list[dict[str, Any]]) -> dict[str, dict[str, Any]]:
    """Today's macro moves from the board, keyed like MACRO_QUOTES. Pure."""
    by = {q.get("key"): q for q in quotes if isinstance(q, dict)}
    out: dict[str, dict[str, Any]] = {}
    for key, label, unit in MACRO_QUOTES:
        q = by.get(key)
        if not q:
            continue
        raw = q.get("chg") if unit == "bp" else q.get("pct")
        if not isinstance(raw, (int, float)):
            continue
        move = float(raw) * 100.0 if unit == "bp" else float(raw)
        text = f"{move:+.0f}bp" if unit == "bp" else f"{move:+.2f}%"
        out[key] = {"key": key, "label": label, "unit": unit, "move": round(move, 2), "text": text}
    return out


def macro_for(sym: str, sector: str | None,
              moves: dict[str, dict[str, Any]]) -> list[dict[str, Any]]:
    """The drivers a name answers to, each with today's move and its verdict
    FOR THE STOCK (a headwind is bad for its price, whichever side the plan
    takes). Pure."""
    drivers = SYMBOL_DRIVERS.get(sym) or SECTOR_DRIVERS.get(sector or "", [])
    out: list[dict[str, Any]] = []
    for key, sign, why in drivers:
        m = moves.get(key)
        if m is None:
            continue
        flat = abs(m["move"]) < FLAT[m["unit"]]
        effect = "flat" if flat else ("tailwind" if m["move"] * sign > 0 else "headwind")
        out.append({"driver": key, "label": m["label"], "move": m["text"],
                    "effect": effect, "why": why})
    return out


def _age_min(utc: Any, now: datetime) -> float | None:
    try:
        t = datetime.fromisoformat(str(utc).replace("Z", "+00:00"))
    except ValueError:
        return None
    if t.tzinfo is None:
        t = t.replace(tzinfo=UTC)
    return round((now - t).total_seconds() / 60.0, 0)


def macro_headlines(wire: list[dict[str, Any]], now: datetime,
                    hours: float = 12.0, n: int = 6) -> list[dict[str, Any]]:
    """The market's high-impact headlines of the last `hours`, newest first. Pure."""
    out: list[dict[str, Any]] = []
    for w in wire:
        if not isinstance(w, dict) or w.get("impact") != "high":
            continue
        age = _age_min(w.get("utc"), now)
        if age is None or age > hours * 60:
            continue
        out.append({"id": f"m{len(out) + 1}", "title": str(w.get("title") or ""),
                    "publisher": str(w.get("publisher") or ""),
                    "desk": str(w.get("category") or ""), "age_min": age})
        if len(out) >= n:
            break
    return out


def _name(row: dict[str, Any], moves: dict[str, dict[str, Any]] | None = None,
          sectors: dict[str, dict[str, Any]] | None = None,
          session: str = "rth") -> dict[str, Any]:
    """One scanner row → the plan's facts for it. Pure."""
    setup = row.get("setup") or {}
    score = row.get("score") or {}
    lv = row.get("levels") or {}
    entry = setup.get("entry") if isinstance(setup.get("entry"), dict) else None
    earn = row.get("earnings") if isinstance(row.get("earnings"), dict) else None
    sym = str(row.get("sym") or "")
    n: dict[str, Any] = {
        "sym": sym,
        "name": row.get("name"),
        "side": score.get("side") or setup.get("side"),
        "score": int(score.get("total") or 0),
        "state": setup.get("state") or "chop",
        "level": setup.get("level"),
        "entry": None if entry is None else {
            "kind": entry.get("kind"), "price": _r(entry.get("price")),
            "dist_atr": _r(entry.get("dist_atr"), 1),
        },
        "last": _r(row.get("last")),
        "chg_pct": _r(row.get("chg_pct")),
        "ext_pct": _r(row.get("ext_pct")),
        # SPY against itself is 0.00 by construction — a line, not a reading.
        "rs_spy": None if sym == "SPY" else _r((row.get("rs") or {}).get("SPY")),
        "rvol": _r(row.get("rvol"), 1),
        "levels": {k: _r(lv.get(k)) for k in ("pdh", "pdl", "pmh", "pml", "pdc")},
        # The ten-minute 200 EMA as a side — the strategy's filter on its own
        # timeframe (structure.py, 2026-10-30): a long under it or a short over
        # it is fighting the line, and the plan should say so.
        "ema200_10m": _line_side(
            {1: "above", -1: "below"}.get(int(row.get("trend200") or 0), "on"),
            score.get("side") or setup.get("side"),
            value=_r(lv.get("ema200")), slope=row.get("ema200_slope"),
        ) if lv.get("ema200") is not None else None,
        # And the daily 200 EMA, from the frame (frame.read names it; the EMA since 2026-10-30).
        "ema200_daily": _line_side(
            "above" if (row.get("frame_read") or {}).get("above200") else "below",
            score.get("side") or setup.get("side"),
        ) if isinstance((row.get("frame_read") or {}).get("above200"), bool) else None,
        # The scanner's own word on whether PMH / PML have locked; without it,
        # the session says (they lock at 09:30).
        "pm_forming": (not lv["pm_done"]) if isinstance(lv.get("pm_done"), bool)
                      else session in OPEN_SESSIONS,
        "atr_d": _r(row.get("atr_d")),
        "atr_b": _r(row.get("atr_b")),
        "earnings": None if earn is None else {
            "date": earn.get("date"), "when": earn.get("when"), "days": earn.get("days"),
        },
        "options": _options(row),
        "flow": _flow(row),
        "adv20": _int(row.get("adv20")),
        "premkt": _premkt(row),
        "peers": _peers(row),
        "headlines": [
            {"id": f"{sym}-h{i + 1}", "title": str(h.get("title") or ""),
             "publisher": str(h.get("publisher") or ""), "age_min": _r(h.get("age_min"), 0),
             "kind": str(h.get("kind") or "news"), "url": str(h.get("url") or "")}
            for i, h in enumerate([h for h in row.get("news") or [] if isinstance(h, dict)][:5])
        ],
        # False when the name's own news feed had not been read when the plan
        # was built — the model is told to say so, never "nothing".
        "news_loaded": bool(row.get("news_loaded", True)),
        "filings": [
            {"form": str(fl.get("form") or ""), "filed": str(fl.get("filed") or ""),
             "desc": str(fl.get("desc") or "")}
            for fl in [fl for fl in row.get("filings") or [] if isinstance(fl, dict)][:3]
        ],
        "sector": _sector(row, sectors or {}),
        "macro": macro_for(sym, row.get("sector") if isinstance(row.get("sector"), str) else None,
                           moves or {}),
        # The daily frame against the live print (frame.read) and the short
        # interest (sources/shortint) — both the engine's reads, cited as such.
        "daily": _daily(row),
        "short_interest": _short(row),
    }
    # The row's own targets where the scanner computed them (optcalc, from the
    # same entry the contract is priced from); the rule on the facts otherwise.
    got = row.get("targets")
    mine = ([t for t in got if isinstance(t, dict) and isinstance(t.get("price"), (int, float))]
            if isinstance(got, list) else [])
    n["targets"] = mine or target_candidates(n)
    n["invalid_if"] = invalid_if(n)
    n["open_if"] = open_if(n) if session in OPEN_SESSIONS else None
    return n


def _line_side(side: str, setup_side: Any, **extra: Any) -> dict[str, Any]:
    """A name against a line: which side it is on, and whether the setup is
    with the line (a long above it, a short below) or against it."""
    out: dict[str, Any] = {"side": side, **extra}
    if setup_side in ("long", "short") and side in ("above", "below"):
        out["with_side"] = "with" if (side == "above") == (setup_side == "long") else "against"
    else:
        out["with_side"] = None
    return out


def _daily(row: dict[str, Any]) -> dict[str, Any] | None:
    """The name's daily frame as the plan cites it: the trend word, the
    averages it is above or below, the distance from the 52-week high."""
    fr = row.get("frame_read")
    if not isinstance(fr, dict) or not fr.get("text"):
        return None
    side = (row.get("score") or {}).get("side") or (row.get("setup") or {}).get("side")
    return {"trend": fr.get("trend"), "text": fr.get("text"),
            "with_side": frame.with_side(fr, side)}


def _short(row: dict[str, Any]) -> dict[str, Any] | None:
    """Short interest, cut to what a plan cites."""
    sh = row.get("short")
    if not isinstance(sh, dict) or sh.get("pct_float") is None:
        return None
    return {"pct_float": _r(sh.get("pct_float"), 1),
            "days_to_cover": _r(sh.get("days_to_cover"), 1),
            "as_of": sh.get("as_of"),
            "squeeze_risk": bool(float(sh["pct_float"]) >= SQUEEZE_PCT)}


def _sector(row: dict[str, Any], sectors: dict[str, dict[str, Any]]) -> dict[str, Any] | None:
    """The name's sector SPDR and how it trades against SPY today. Pure."""
    key = row.get("sector")
    if not isinstance(key, str) or not key:
        return None
    s = sectors.get(key) or {}
    rs = row.get("sector_rs")
    return {"key": key, "label": s.get("label"),
            "rs_day": _r(rs if isinstance(rs, (int, float)) else s.get("rs_day"))}


def pick_names(rows: list[dict[str, Any]], top: int) -> list[dict[str, Any]]:
    """The top `top` rows with a side, by score, then SPY and QQQ if not among them. Pure."""
    live = [r for r in rows if r.get("ok")]
    sided = [r for r in live if (r.get("score") or {}).get("side")]
    ranked = sorted(sided, key=lambda r: -int((r.get("score") or {}).get("total") or 0))[:top]
    have = {r.get("sym") for r in ranked}
    for sym in TAPE:
        row = next((r for r in live if r.get("sym") == sym), None)
        if row is not None and sym not in have:
            ranked.append(row)
    return ranked


# --------------------------------------------------------------------------
# The open — what a plan written before 09:30 may stand on (owner, 2026-10-14:
# "do what you recommend all at once" — the review's pre-open mode).
#
# A plan written at 05:18 ET took the pre-market high as GME's target (27.78,
# with price at 27.75), and put four "No trade — price has not broken the
# pre-market low" cards on the page, when before the open nothing can have
# broken. The prompt already said PMH / PML are provisional; the model wrote
# them anyway. So the server now enforces it: the targets a plan may take are
# computed here from levels that are FINAL, the trigger before the open is an
# if/then the server can write itself, and a target or invalidation that
# breaks the rules is replaced, with the model's words kept beside it.
# --------------------------------------------------------------------------

#: Sessions in which the plan is written for an open that has not happened:
#: the pre-market, and the overnight / weekend "closed" before it.
OPEN_SESSIONS = ("pre", "closed")

# THE TARGET RULE IS targets.py'S NOW (2026-10-22): the options card prices
# each contract at the first target, so the plan and the card share one
# function. MIN_REACH_BARS / MIN_REACH_DAY, min_reach and target_candidates
# are imported above and re-exported here for the tests that pin them.
_LEVEL_WORD = {"PMH": "pre-market high", "PML": "pre-market low",
               "PDH": "previous day's high", "PDL": "previous day's low"}


def _px(v: float) -> str:
    """A price as the facts print it: two places, trailing zeros dropped. Pure."""
    return f"{v:.2f}".rstrip("0").rstrip(".")


_sign = sign_of
_entry = entry_of
_forming = forming_levels


def invalid_if(n: dict[str, Any]) -> str | None:
    """The plan's invalidation in the strategy's own terms — a ten-minute close
    back through the level it is built on. Pure."""
    sign, e = _sign(n), _entry(n)
    kind = str((n.get("entry") or {}).get("kind") or "")
    if not sign or e is None:
        return None
    way = "below" if sign > 0 else "above"
    if kind in _LEVEL_WORD:
        locked = " once it locks" if kind in ("PMH", "PML") and n.get("pm_forming") else ""
        return f"A 10-minute close back {way} {kind} {_px(e)}{locked}."
    return f"A 10-minute close back {way} VWAP and the 8 EMA wave."


def open_if(n: dict[str, Any]) -> str | None:
    """Before the open, the trigger as an if/then the open has to answer. Pure."""
    sign, e = _sign(n), _entry(n)
    kind = str((n.get("entry") or {}).get("kind") or "")
    if not sign or e is None:
        return None
    way = "above" if sign > 0 else "below"
    back = "" if sign > 0 else " from below"
    if kind in ("PMH", "PML"):
        return (f"Once the {_LEVEL_WORD[kind]} locks at 09:30 ({_px(e)} so far): a 10-minute "
                f"close {way} it, then the retest{back} that holds.")
    if kind in ("PDH", "PDL"):
        other = "below" if sign > 0 else "above"
        return (f"If it opens {way} {kind} {_px(e)} and the first 10-minute bar closes {way} it: "
                f"the retest of {kind} {_px(e)}{back} that holds. If it opens {other}, it needs "
                f"a 10-minute close {way} {kind} {_px(e)} first.")
    return (f"If it is still extended at the open: the pullback to VWAP or the 8 EMA wave "
            f"({kind} {_px(e)} now) that holds.")


# THE DAY'S RELEASES, ONE LINE EACH. The calendar lists CPI as up to seven rows
# at 08:30 (core m/m, core y/y, the headline pair, the index levels); a plan's
# clock printed every one, and a free model added a garbage eighth
# ("08:30 CPI, n.s.a”,"). A release is grouped by its minute and its family —
# the keyword it is named for — and the clock and the risks are written here
# from the groups, never by the model.

#: Keyword in a release's title → the family it is printed under.
RELEASE_FAMILIES: tuple[tuple[str, str], ...] = (
    ("CPI", "CPI"), ("PPI", "PPI"), ("PCE", "PCE"), ("Retail Sales", "Retail Sales"),
    ("GDP", "GDP"), ("Nonfarm", "Jobs report"), ("Unemployment Rate", "Jobs report"),
    ("Average Hourly Earnings", "Jobs report"), ("Participation Rate", "Jobs report"),
    ("Jobless Claims", "Jobless Claims"), ("ISM Manufacturing", "ISM Manufacturing"),
    ("ISM Services", "ISM Services"), ("Durable Goods", "Durable Goods"),
    ("Housing Starts", "Housing Starts"), ("Building Permits", "Building Permits"),
    ("Import Prices", "Import Prices"), ("Export Prices", "Export Prices"),
    ("Industrial Production", "Industrial Production"), ("JOLTS", "JOLTS"),
    ("Michigan", "Michigan sentiment"), ("Empire State", "Empire State"),
)

_JUNK = re.compile(r"[\"“”‘’`]+")


def _clean(s: Any) -> str:
    """A calendar title or figure without stray quotes or trailing commas. Pure."""
    return _JUNK.sub("", str(s or "")).strip(" ,;")


def release_family(title: str) -> tuple[str, str]:
    """(family, the part of the title that says which print) for a release. Pure.

    "Core CPI m/m" → ("CPI", "core m/m"); "CPI y/y" → ("CPI", "y/y"); a title
    with no known keyword is its own family, and its part is the whole title.
    """
    t = _clean(title)
    for kw, fam in RELEASE_FAMILIES:
        m = re.search(rf"\b{re.escape(kw)}\b", t, re.I)
        if m is None:
            continue
        if fam != kw:
            return fam, t
        part = re.sub(r"\s+", " ", (t[:m.start()] + t[m.end():])).strip(" ,.-")
        return fam, (part[:1].lower() + part[1:]) if part else "headline"
    return t, t


def group_releases(items: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """The day's releases grouped by minute and family, in time order. Pure."""
    groups: dict[tuple[str, str], dict[str, Any]] = {}
    for x in items:
        if not isinstance(x, dict) or not x.get("title"):
            continue
        et = str(x.get("et") or "untimed")
        fam, part = release_family(str(x["title"]))
        g = groups.setdefault((et, fam), {"et": et, "family": fam, "titles": [], "parts": [],
                                          "score": 0, "done": True, "rates": False})
        g["titles"].append(_clean(x["title"]))
        g["parts"].append({"label": part, "actual": x.get("actual"),
                           "consensus": x.get("consensus"), "previous": x.get("previous")})
        g["score"] = max(g["score"], int(x.get("score") or 0))
        g["done"] = g["done"] and bool(x.get("done") or x.get("released"))
        g["rates"] = g["rates"] or "rates" in (x.get("themes") or [])
    return sorted(groups.values(), key=lambda g: (g["et"] == "untimed", g["et"]))


def _figures(p: dict[str, Any]) -> str:
    a, c, prev = (_clean(p.get(k)) for k in ("actual", "consensus", "previous"))
    out = f"{a} vs {c}" if a and c else a or (f"{c} expected" if c else "")
    if prev:
        out = f"{out} (prev {prev})" if out else f"prev {prev}"
    return out


def release_line(g: dict[str, Any]) -> str:
    """One group as one line: "08:30 CPI — core m/m 0.2% expected (prev 0.3%), …". Pure."""
    et = "" if g["et"] == "untimed" else f"{g['et']} "
    if len(g["parts"]) == 1:
        fig = _figures(g["parts"][0])
        return f"{et}{g['titles'][0]}" + (f" — {fig}" if fig else "")
    bits = [f"{p['label']} {f}".strip() if (f := _figures(p)) else p["label"]
            for p in g["parts"]]
    return f"{et}{g['family']} — " + ", ".join(bits)


def _day_prints(prints: list[dict[str, Any]], td: date, today: date) -> list[dict[str, Any]]:
    """The trading day's own prints, their times without the day. Pure.

    The Market tab's prints label today's "08:30" and any other day's "Thu
    08:30"; the plan's clock is the trading day's alone.
    """
    out: list[dict[str, Any]] = []
    for x in prints:
        if not isinstance(x, dict):
            continue
        et = str(x.get("et") or "")
        m = re.fullmatch(r"([A-Z][a-z]{2}) (\d\d:\d\d)", et)
        if m:
            if m.group(1) != f"{td:%a}":
                continue
            et = m.group(2)
        elif td != today:
            continue
        out.append({**x, "et": et or "untimed"})
    return out


def _speaker(title: str) -> str | None:
    m = re.search(r"\b(?:Member|Chair|Vice Chair|President|Governor)\s+([A-Z][a-z]+)", title)
    return m.group(1) if m else None


def clock_lines(facts: dict[str, Any]) -> list[str]:
    """The day's clock — the session's fixed times and the releases still to
    come before the close, one line each, in time order. The server's, not the
    model's. Pure."""
    td = _parse_day(facts.get("trading_day"))
    if td is None:
        return []
    c = _clock(td)
    rows: list[tuple[str, str]] = [
        (c["open"], f"{c['open']} the open"),
        (c["opening_range_end"], f"{c['opening_range_end']} the opening range is set"),
        (c["lunch"][:5], f"{c['lunch']} the lunch lull"),
        (c["last_hour"], f"{c['last_hour']} the last hour"),
        (c["close"], f"{c['close']} the close"),
    ]
    for g in facts.get("events") or []:
        if g["done"] or (g["et"] != "untimed" and g["et"] >= c["close"]):
            continue
        rows.append((g["et"] if g["et"] != "untimed" else "99:99", release_line(g)))
    rows.sort(key=lambda r: r[0])
    return [r[1] for r in rows][:12]


def _risk_groups(facts: dict[str, Any]) -> list[dict[str, Any]]:
    """The day's release groups that are a risk to the plan: high impact (or a
    Fed event), still to come, and before the close. Pure."""
    td = _parse_day(facts.get("trading_day"))
    close = _clock(td)["close"] if td else "16:00"
    return [g for g in facts.get("events") or []
            if not g["done"] and (g["score"] >= 4 or (g["rates"] and g["score"] >= 3))
            and (g["et"] == "untimed" or g["et"] < close)]


def event_risks(facts: dict[str, Any]) -> list[str]:
    """Those groups as risks — from the calendar, not the model (a CPI
    morning's plan once listed none). Pure."""
    out: list[str] = []
    for g in _risk_groups(facts):
        # Named, not re-printed: the figures are on the clock just above.
        name = g["family"] if len(g["parts"]) > 1 else g["titles"][0]
        et = "" if g["et"] == "untimed" else f"{g['et']} "
        when = ("before the open: it sets the gap, and levels formed ahead of it are provisional"
                if g["et"] < "09:30" else "in the session: let it print before taking a level")
        out.append(f"{et}{name} — {when}.")
    return out


def _covered(text: str, facts: dict[str, Any]) -> bool:
    """Whether a model risk restates a release `event_risks` already lists. Pure."""
    for g in _risk_groups(facts):
        keys = {g["family"]} | {s for t in g["titles"] if (s := _speaker(t))}
        if any(re.search(rf"\b{re.escape(k)}\b", text, re.I) for k in keys):
            return True
    return False


def _calendar(rows: list[dict[str, Any]], days: set[date]) -> list[dict[str, Any]]:
    """US releases scored 3+ on the days the plan covers, in time order."""
    out: list[dict[str, Any]] = []
    # The calendar feed carries the odd duplicate row (same release, same
    # minute); a plan's clock listing a print twice reads as two prints.
    seen: set[tuple[str, str, str]] = set()
    for r in rows:
        d = _parse_day(r.get("date"))
        if d is None or d not in days or r.get("region") != "us" or int(r.get("score") or 0) < 3:
            continue
        et = r.get("et") if isinstance(r.get("et"), str) else None
        k = (d.isoformat(), et or "", str(r.get("event") or ""))
        if k in seen:
            continue
        seen.add(k)
        out.append({
            "et": f"{d:%a} {et}" if et else f"{d:%a} (untimed)",
            "title": str(r.get("event") or ""),
            "score": int(r.get("score") or 0),
            "released": bool(r.get("released")),
            "_k": (d.isoformat(), et or "99:99"),
        })
    out.sort(key=lambda x: x["_k"])
    for x in out:
        del x["_k"]
    return out


def _partial(snap: dict[str, Any], rows: list[dict[str, Any]]) -> list[str]:
    """What the plan is missing, worded for the banner — report._partial's rules."""
    status = snap.get("status") or {}
    out: list[str] = []
    for key, name in PLAN_SOURCES.items():
        st = status.get(key)
        if st is None:
            out.append(f"{name}: not collected yet.")
        elif not st.get("ok"):
            err = str(st.get("error") or "").strip()
            out.append(f"{name} unavailable" + (f" ({err[:90]})" if err else "") + ".")
        elif st.get("source") == "stale" or st.get("stale_age_min") is not None:
            age = st.get("stale_age_min")
            when = f" from {float(age):.0f} min ago" if isinstance(age, (int, float)) else ""
            out.append(f"{name}: upstream unreachable — figures are a cached copy{when}.")
    unread = [str(r.get("sym")) for r in rows
              if r.get("ok") and r.get("news_loaded") is False]
    if unread:
        out.append(f"Headlines still loading for {len(unread)} name(s) after a restart "
                   f"({', '.join(unread[:6])}{'…' if len(unread) > 6 else ''}) — their "
                   "News lines say so rather than reading as quiet.")
    has_opts = any(isinstance(r.get("options"), dict) and r["options"].get("ok") for r in rows)
    opt_st = next((status[k] for k in OPTION_STATUS_KEYS if k in status), None)
    if not has_opts:
        out.append("Options chains: not available yet — the plans carry no options context.")
    elif opt_st is not None and not opt_st.get("ok"):
        out.append("Options chains unavailable — options context may be out of date.")
    return out


def _clock(td: date) -> dict[str, str]:
    """The session's fixed times, so a plan's clock is printed in the data it cites."""
    close = close_time(td)
    last = (datetime.combine(td, close) - timedelta(hours=1)).time()
    return {
        "open": "09:30",
        "opening_range_end": "10:00",
        "lunch": "11:30-13:30",
        "last_hour": f"{last:%H:%M}",
        "close": f"{close:%H:%M}",
    }


def build_facts(
    scan: dict[str, Any], snap: dict[str, Any], top: int = TOP_DEFAULT
) -> dict[str, Any]:
    """The plan's tables, from the live scanner payload and the terminal snapshot."""
    top = max(TOP_MIN, min(TOP_MAX, int(top)))
    rows = [r for r in scan.get("rows") or [] if isinstance(r, dict)]
    regime = scan.get("regime") or {}
    vix = regime.get("vix") or {}
    tape = regime.get("tape") or {}
    td = _parse_day(scan.get("trading_day")) or datetime.now(ET).date()
    today = datetime.now(ET).date()
    moves = macro_moves(snap.get("quotes") or [])
    sectors: dict[str, dict[str, Any]] = {
        str(r["key"]): r for r in snap.get("sectors") or []
        if isinstance(r, dict) and isinstance(r.get("key"), str)
    }
    built = scan.get("built_utc")
    try:
        as_of = datetime.fromisoformat(str(built)).astimezone(ET)
    except ValueError:
        as_of = datetime.now(ET)
    # The Market tab's context, the same function the tab prints: the tape
    # count is what the plan's convictions are capped by (sanitize_plan).
    ctx = marketctx.build(scan, snap)
    return {
        "as_of": as_of.strftime("%a %d %b %Y, %H:%M ET"),
        "session": scan.get("session") or "closed",
        "trading_day": td.isoformat(),
        "regime": {
            "vix": _r(vix.get("last")),
            "vix_pct": _r(vix.get("pct")),
            "band": regime.get("band"),
            # The sub-line inside the band (scanscore.vix_sub): words, never score.
            "sub": regime.get("sub"),
            "shape": vix.get("shape"),
            "bias": regime.get("bias"),
            "confirm": regime.get("confirm"),
            "spy_em_pct": _r(regime.get("spy_em_pct")),
            "tape": [
                {"sym": k, "chg_pct": _r(t.get("chg_pct")), "ext_pct": _r(t.get("ext_pct")),
                 "trend": int(t.get("trend") or 0)}
                for k in ("SPY", "QQQ", "IWM") if isinstance(t := tape.get(k), dict)
            ],
        },
        "names": [_name(r, moves, sectors, str(scan.get("session") or "closed"))
                  for r in pick_names(rows, top)],
        # The day's macro, once for the whole plan: the moves the names' drivers
        # are read from, and the market's high-impact headlines.
        "macro": {
            "moves": list(moves.values()),
            "headlines": macro_headlines(snap.get("wire") or [], datetime.now(UTC)),
        },
        "calendar": _calendar(snap.get("calendar") or [], {today, td, next_trading_day(td)}),
        "conviction": ctx["conviction"],
        "breadth": ctx["breadth"],
        "fuel": ctx["fuel"],
        "prints": ctx["prints"],
        # The trading day's releases grouped by minute and family — what the
        # plan's clock and its release risks are written from (server-side).
        "events": group_releases(_day_prints(ctx["prints"] or [], td, today)),
        "fed": ctx["fed"],
        "gamma": ctx["gamma"],
        "partial": _partial(snap, rows),
    }


# --------------------------------------------------------------------------
# What the model is told.
# --------------------------------------------------------------------------

STRATEGY = (
    "LE model, New York only. A name breaks its pre-market high/low (PMH/PML, locked at 09:30) or"
    " previous-day high/low (PDH/PDL); the trade is the RETEST of the broken level on a 10-minute"
    " chart — or of VWAP / the 8 EMA wave when price has run far from the level (entry.dist_atr "
    "is the distance in 10-minute ATRs). (L) = a retest with the 8 EMA wave at the level; (E) = "
    "the first candle touching the 8 EMA wave, triggered when price breaks that candle. The "
    "Pine's stop idea is below the signal bar (long) / above it (short). Options, the expiry: "
    + optcalc.expiry_rule()["text"] + " The contract in each name's `options` is that pick. "
    "A long call/put near 0.60 delta when premium "
    "is cheap or fair; a debit spread (buy ~0.60 delta, sell ~0.30 delta) when premium is rich "
    "(iv_rv above 1.25) — unless each contract's R at the first target (`at_target.r`: reward "
    "over risk per contract, both from the entry to the stop and to the target) says otherwise: "
    "`options.structure` is the engine's pick, by R when both are priced, and the plan uses it. "
    "An expected move (em_*_pct) smaller than the distance to the target "
    "argues for the spread or for no trade. An earnings date inside the expiry (earnings_in) "
    "means IV will collapse after the report — say so, and quote `earnings_move`: the move the "
    "chain prices for the report against the name's last realised ones."
)


def system_prompt(session: str) -> str:
    open_mode = (
        " Nothing has broken yet — the open has not happened — so every plan is an IF/THEN for "
        "the open: its `trigger` starts with \"If\" or \"Once\" and says what the open must show "
        "(each name's `open_if` is the strategy's own wording; use it or say the same thing "
        "better). A name is never \"no trade because it has not broken\": that is every name "
        "before 09:30."
    )
    when = {
        "pre": "It is the pre-market: PMH/PML are still forming and lock at 09:30 (a name's "
               "`pm_forming` is true), so they are provisional — never a target, and a trigger "
               "only as \"once it locks\"." + open_mode,
        "rth": "The session is underway. Write from the current prices and states, not for the "
               "open — a break that has already happened is a retest to wait for, not a trigger.",
        "post": "The session has closed. Write the plan for the next session (trading_day).",
        "closed": "The market is closed. Write the plan for the next session (trading_day)."
                  + open_mode,
    }.get(session, "Write the plan for the next New York session.")
    return f"""\
You are the head of a New York equities desk writing the morning game plan for one trader who \
trades US stocks and ETFs through OPTIONS with a single strategy. {when}

The strategy, which every plan must use:
{STRATEGY}

The data you are given is a scanner's output: for each name its setup state, the level it is \
about, the entry reference, relative strength against SPY in ATRs, relative volume, the four \
levels, its earnings date, its options context (implied vs realised volatility, the premium \
verdict, the expected move from the at-the-money straddle, liquidity, a suggested long contract \
and debit spread), today's options flow (`flow`: put/call volume, which way it leans, the \
busiest strike), its pre-market volume against its 20-day average (`premkt`), big caps in its \
sector reporting this week (`peers`), its sector SPDR against SPY (`sector`), its daily frame \
(`daily`: the trend on the daily chart, whether the setup is with it or against it, the \
distance from the 52-week high), its side of the 200-day EMA and of the ten-minute 200 EMA \
(`ema200_daily`, `ema200_10m`: above or below, and whether the setup is with the line or \
against it — a long above or a short below is with it), its short interest \
(`short_interest`: the share of the float \
sold short and whether that is squeeze risk for a short), the macro drivers \
it answers to with today's move and whether that is a headwind or a tailwind FOR THE STOCK \
(`macro` — computed for you; for a short, a headwind helps), up to five of its own headlines \
tagged rating / earnings / filing / news, and its recent SEC filings. `macro` at the top level is \
the day's macro moves and the market's high-impact headlines. The regime block is the weather: \
VIX and its band, the curve shape, the tape's bias and whether VIX confirms it, SPY's implied \
one-day move. `tape_count` is the engine's count of eleven independent reads of the tape (each \
long, short or neutral) with its grade. `breadth` is sectors up and down, equal weight against \
SPY and the index leaders; `fuel` is how much of its implied one-day move SPY, QQQ and IWM have \
already used (room / normal / stretched); `prints` are the session's US releases against \
consensus, read hot (stronger economy) / cold / in line — `done` means its time has passed (a \
speech never has an actual); `fed` is what the next meetings price; `gamma` is \
dealer gamma in QQQ and SPY prices — POS means dealers damp moves and the walls tend to hold, NEG \
means they chase moves and breaks run (absent when the feed is down).

Rules:
- `headline` is ONE line in your own words: the day's stance and the one or two best names. \
It is never a news headline.
- Write plans ONLY for names in the data, and only where the setup is real. A name without a \
clean setup goes in `avoid` with the reason, or is left out — NEVER a plan that says "no trade" \
or fills its fields with dashes; the server moves those off the page. An empty `plans` list is a \
valid answer on a day the tape says stand aside — chop, backwardation, a high-impact print about \
to land — and `market` must then say so plainly.
- Every number you write must be copied exactly from the data: levels, prices, percentages, \
strikes, times. No arithmetic, no rounding, no new levels. If a number you want is not printed, \
say it in words.
- `trigger` is what must happen first (the break, the retest of the named level, the reclaim of \
VWAP); `invalidation` is the price or condition that cancels the plan (each name's `invalid_if` \
is the strategy's own); `target` is taken from the name's `targets`, copied as printed — the \
levels that are final and sit at least a stop and a half past the entry and past the last price, \
nearest first. When `targets` is empty, say there is no final level beyond the entry and trail \
the 8 EMA wave. The server replaces a target that is still forming, on the wrong side of the \
entry or nearer than that, and an invalidation on the wrong side.
- `options` says how to express it: long option or debit spread, and which expiry (the expiry \
rule in the strategy — the contract given is its pick), from the premium verdict and the expected \
move; flag poor liquidity and earnings inside the expiry. If there is no options context for the \
name, say that.
- `why` is four to six short lines, each starting with its layer. EVERY plan carries \
"Structure:", "RS:", "Macro:" and "News:", and adds "Tape:", "Options:" or "Catalyst:" where \
they matter.
- "Options:" gives the premium verdict and how that shapes the contract — and the engine's \
structure pick with each contract's R at the first target where `at_target` is printed ("the \
long makes 1.4 R to PDH 240.62, the spread 0.8, so the long") — and, when the name \
has a `flow` — reads the flow in the same line: its put/call volume or its busiest strike, as \
printed, and whether it backs the side (e.g. "Options: premium rich, so a debit spread; calls \
lead at put/call 0.37, which backs the long"). Leave the flow out when the name has none. A \
name with `earnings_move` says the move priced for the report against its realised ones.
- "Structure:" also says the daily frame (`daily.text`) and whether the setup is with the \
daily trend or against it; a setup against it is a reason for lower conviction, said so. The \
same for the two 200 EMAs (`ema200_daily`, `ema200_10m`): a setup against either line names \
which, and that too is a reason for lower conviction; with both lines, say so in a word. A \
short on a name whose `short_interest.squeeze_risk` is true names the squeeze risk.
- "Macro:" ties the name to today's macro: its sector against SPY (as printed — an index ETF \
has no `sector`, so leave the sector out rather than calling it null) and the drivers \
in its `macro` list — name the driver, its move as printed, and the verdict (headwind / \
tailwind / flat). If a high-impact market headline in the top-level `macro.headlines` bears on \
the name or its sector, say which. If every driver is flat, say the macro is quiet for it.
- SPY has no relative strength against itself: its plan carries no "RS:" line.
- "News:" cites the name's own most relevant item — an analyst rating, an earnings item, a \
filing or a headline — with its publisher (or form), and what it means for the setup. Only an \
item that names the stock, its company or its sector peers: a market headline (in \
`macro.headlines`) belongs on the Macro line, and only when it bears on the name. If it \
has nothing in the last three days, write "News: nothing stock-specific in three days" — but \
ONLY when its `news_loaded` is true; when it is false, write "News: headlines not loaded yet". \
Never invent a headline, a rating or a filing.
- `conviction` is 1-5 and must reflect the weather as well as the setup. RANK the names: \
the strongest relative strength with the cleanest structure gets the highest conviction, and \
no more than two names may share the top score. Plans that read alike are a sign you have not \
ranked. THE TAPE COUNT CAPS IT: no plan above `tape_count.max_conviction`, and no plan against \
`tape_count.bias` above 3. The server enforces both, so rank within that ceiling.
- `market` is two or three sentences on the tape and the weather from the regime block — never \
empty, even on a quiet day — and says how many of the tape's reads agree, as counted.
- Write plain trader's English. NEVER print a field name or a JSON key — not rs_spy, dist_atr, \
iv_rv, ext_pct, em_front_pct, pc_vol, pct_adv, adv20, news_loaded, max_conviction or any other. \
Say "relative strength against SPY", "N ten-minute ATRs from the entry", "implied volatility N \
times realised", "the pre-market gap", "put/call volume N", "pre-market volume N% of a normal \
day" — with the number as printed in place of N.
- `risks` is one to three concrete ways today's plan fails — a level giving way, the tape \
turning, a name's own weak point. The server lists the day's clock and its releases itself, so \
leave the calendar out of `risks`.
- Be concrete. No disclaimers, no position sizes, no mention of being an AI."""


def _obj(props: dict[str, Any]) -> dict[str, Any]:
    return {"type": "object", "additionalProperties": False, "required": list(props),
            "properties": props}


_S: dict[str, Any] = {"type": "string"}


def schema(syms: list[str]) -> dict[str, Any]:
    """The strict schema — the syms are an enum, so a plan cannot name a ghost."""
    sym = {"type": "string", "enum": syms or ["SPY"]}
    plan = _obj({
        "sym": sym, "side": {"type": "string", "enum": ["long", "short"]},
        "conviction": {"type": "integer", "enum": [1, 2, 3, 4, 5]},
        "plan": _S, "trigger": _S, "invalidation": _S, "target": _S, "options": _S,
        "why": {"type": "array", "minItems": 3, "maxItems": 6, "items": _S},
    })
    return _obj({
        "headline": _S,
        "market": _S,
        "plans": {"type": "array", "minItems": 0, "maxItems": max(1, len(syms)), "items": plan},
        "avoid": {"type": "array", "minItems": 0, "maxItems": max(1, len(syms)),
                  "items": _obj({"sym": sym, "why": _S})},
        "risks": {"type": "array", "minItems": 0, "maxItems": 4, "items": _S},
    })


SKELETON = """{
  "headline": "one line",
  "market": "the tape and the weather in two or three sentences",
  "plans": [ { "sym": "a name from the data", "side": "long" | "short",
               "conviction": integer 1-5,
               "plan": "...", "trigger": "...", "invalidation": "...", "target": "...",
               "options": "...",
               "why": [ "Structure: ...", "RS: ...", "Macro: ...", "News: ...",
                        "Tape: ...", "Options: ... (premium, contract, flow)" ] } ],
  "avoid": [ { "sym": "a name from the data", "why": "..." } ],
  "risks": [ "..." ]
}"""


def build_digest(facts: dict[str, Any]) -> dict[str, Any]:
    """Exactly what the model is shown: the facts, the session clock and the rules' figures."""
    td = _parse_day(facts.get("trading_day")) or datetime.now(ET).date()
    return {
        "as_of_et": facts["as_of"],
        "session": facts["session"],
        "trading_day": facts["trading_day"],
        "clock": _clock(td),
        "strategy": STRATEGY,
        "regime": facts["regime"],
        "calendar": facts["calendar"],
        "macro": facts.get("macro") or {"moves": [], "headlines": []},
        **_market_digest(facts),
        "names": facts["names"],
        "partial": facts["partial"],
    }


def tape_line(c: dict[str, Any] | None) -> str:
    """The tape count in one sentence, for the user message. Pure."""
    if not isinstance(c, dict):
        return "Tape count: not available."
    total, mx = c.get("total"), c.get("max_conviction")
    if c.get("bias") is None:
        return (f"Tape count: no lean across {total} reads — every plan's conviction is capped "
                f"at {mx}.")
    return (f"Tape count: {c.get('agree')} of {total} reads lean {c.get('bias')}, "
            f"{c.get('against')} against ({c.get('grade')}) — conviction is capped at {mx}, "
            f"and at {AGAINST_MAX} for a plan against the {c.get('bias')} tape.")


def _market_digest(facts: dict[str, Any]) -> dict[str, Any]:
    """The market blocks as the model sees them — the figures, without the page's
    prose and the fields a plan never cites, to keep the digest lean. Pure."""
    c = facts.get("conviction")
    out: dict[str, Any] = {}
    if isinstance(c, dict):
        out["tape_count"] = {
            **{k: c.get(k) for k in ("bias", "agree", "against", "neutral", "total", "grade",
                                     "max_conviction")},
            "reads": [f"{v.get('label')}: {v.get('value')} ({v.get('vote')})"
                      for v in c.get("votes") or [] if isinstance(v, dict)],
        }
    if "breadth" in facts:
        out["breadth"] = facts["breadth"]
    if "fuel" in facts:
        out["fuel"] = [{k: f.get(k) for k in ("sym", "implied_pct", "range_pct", "used",
                                               "gap_pct", "state")}
                       for f in facts["fuel"] or [] if isinstance(f, dict)]
    if "prints" in facts:
        out["prints"] = [{k: x.get(k) for k in ("et", "title", "released", "done", "actual",
                                                 "consensus", "previous", "read")}
                         for x in facts["prints"] or [] if isinstance(x, dict)]
    if "fed" in facts:
        fd = facts["fed"]
        out["fed"] = None if not isinstance(fd, dict) else {
            k: fd.get(k) for k in ("next", "next_bp", "next_rate", "path")}
    if "gamma" in facts:
        g = facts["gamma"]
        out["gamma"] = None if not isinstance(g, list) else [
            {k: x.get(k) for k in ("etf", "regime", "flip", "call_wall", "put_wall", "spot")}
            for x in g if isinstance(x, dict)]
    return out


# --------------------------------------------------------------------------
# What comes back.
# --------------------------------------------------------------------------


def _conviction(v: Any) -> int | None:
    if isinstance(v, bool):
        return None
    if isinstance(v, str):
        try:
            v = float(v.strip())
        except ValueError:
            return None
    if not isinstance(v, (int, float)):
        return None
    return max(1, min(5, round(v)))


def _ends(text: str, keep: int = 1500) -> str:
    """Both ends of a failed answer — the head shows the shape it started in,
    the tail whether it was cut off. Pure."""
    if len(text) <= 2 * keep:
        return text
    return f"{text[:keep]}\n…[{len(text) - 2 * keep} chars]…\n{text[-keep:]}"


def _unwrap(obj: dict[str, Any]) -> dict[str, Any]:
    """The plan, out of the one-key wrapper a free model sometimes puts round it.

    OBSERVED, NOT GUESSED (2026-10-13): a live run failed twice with "needs a
    headline" while the next answer from the same model, same prompt, came back
    in the right shape — free models drift between calls. `{"game_plan": {…}}`
    and `{"plan": {…}}` are the drift seen in the futures report's extractor
    too, so a dict with no headline of its own whose single value is a dict that
    has one is read as that inner dict. Pure.
    """
    if "headline" in obj or "plans" in obj:
        return obj
    inner = [v for v in obj.values() if isinstance(v, dict)]
    if len(obj) == 1 and len(inner) == 1 and ("headline" in inner[0] or "plans" in inner[0]):
        return inner[0]
    return obj


_DOUBLE_LAYER = re.compile(r"^\s*([A-Za-z][A-Za-z ]{0,20}):\s*\1:\s*", re.I)


# JSON's own punctuation left inside the last string of a list — "…backs the
# long]," on every plan's final line in a live run (2026-10-13).
_TRAILING_SYNTAX = re.compile(r"[\s\]\},]+$")


def _why(lines: list[str]) -> list[str]:
    """The why lines with a doubled layer word collapsed — the prompt quotes the
    "News: nothing stock-specific…" form, and the model sometimes prefixes it
    again — and any JSON punctuation the model typed into the string. Pure."""
    return [_TRAILING_SYNTAX.sub("", _DOUBLE_LAYER.sub(lambda m: f"{m.group(1)}: ", w))
            for w in lines]


#: The highest conviction a plan AGAINST the tape's bias may carry.
AGAINST_MAX = 3


def cap_conviction(p: dict[str, Any], tape: dict[str, Any] | None) -> dict[str, Any]:
    """The tape count's ceiling on one plan's conviction. Pure; returns `p`, updated.

    Two caps, both the server's and never the model's: no plan above the tape's
    `max_conviction` (strong 5 · moderate 4 · weak 3 · no lean 2), and no plan
    against the tape's bias above 3. `conviction_model` keeps the model's
    number; `capped` says which cap bit, or is None.
    """
    model = int(p["conviction"])
    p["conviction_model"] = model
    p["capped"] = None
    if not isinstance(tape, dict):
        return p
    out, why = model, []
    mx, bias, grade = tape.get("max_conviction"), tape.get("bias"), tape.get("grade")
    if isinstance(mx, int) and out > mx:
        out = mx
        why.append(f"no tape lean — at most {mx}" if bias is None
                   else f"tape {grade} — at most {mx}")
    if bias in ("long", "short") and p.get("side") != bias and out > AGAINST_MAX:
        out = AGAINST_MAX
        why.append(f"against the {bias} tape — at most {AGAINST_MAX}")
    if out < model:
        p["conviction"] = out
        p["capped"] = "; ".join(why)
    return p


# A plan that is no plan: "No trade – price has not broken the pre-market low"
# with a dash in every field (four of seven cards at 05:18 ET, 2026-10-14).
_NO_TRADE = re.compile(r"^\s*(?:no\s+(?:trade|setup|valid\s+setup|plan)|stand\s+aside|pass)\b",
                       re.I)
_BLANK = {"", "-", "–", "—", "n/a", "na", "none", "nil"}
_NO_TRADE_LEAD = re.compile(r"^\s*no\s+(?:trade|setup|valid\s+setup|plan)\s*[-–—:,.]*\s*", re.I)
_CONDITIONAL = re.compile(r"^\s*(?:if|once|after|when|should|provided|on\s+a|at\s+the\s+open)\b",
                          re.I)
_NUM_TOKEN = re.compile(r"(?<![\d.,:])(?:\d{1,3}(?:,\d{3})+(?:\.\d+)?|\d+(?:\.\d+)?)(?![\d:])")
_FORMING_WORD = re.compile(r"\b(?:PMH|PML|pre-?market\s+(?:high|low))\b", re.I)


def _is_filler(p: dict[str, Any]) -> bool:
    """A card that plans nothing — "no trade", or every field a dash. Pure.

    Fields that are simply absent are a malformed answer, not a no-trade one,
    and are left to the page as before."""
    fields = [str(p.get(k) or "").strip().lower() for k in ("trigger", "invalidation", "target")]
    return (bool(_NO_TRADE.match(p.get("plan") or ""))
            or (any(fields) and all(f in _BLANK for f in fields)))


def _prices(text: str, n: dict[str, Any]) -> list[float]:
    """The numbers in a sentence that read as prices of this name — within half
    a price of its last — leaving percentages, times and counts alone. Pure."""
    ref = n.get("last") if isinstance(n.get("last"), (int, float)) else _entry(n)
    if not isinstance(ref, (int, float)) or ref <= 0:
        return []
    out: list[float] = []
    for m in _NUM_TOKEN.finditer(text or ""):
        if re.match(r"\s*(?:%|bp\b|x\b|×|ATR|-minute|-min\b|ten-minute)", text[m.end():], re.I):
            continue
        v = float(m.group(0).replace(",", ""))
        if 0.5 * ref <= v <= 1.5 * ref:
            out.append(v)
    return out


def _target_fault(text: str, n: dict[str, Any]) -> str | None:
    """Why a written target cannot stand, or None. Pure.

    Forming: it names the pre-market high or low before they lock. Too near or
    the wrong side: none of its prices sits a stop and a half past the entry
    and past the last price (`target_candidates`' own test)."""
    sign, e = _sign(n), _entry(n)
    if not sign or e is None:
        return None
    forming = _forming(n)
    prices = _prices(text, n)
    if any(abs(p - f) < 0.005 for p in prices for f in forming):
        return "the pre-market high/low was still forming"
    if not prices:
        return ("the pre-market high/low was still forming"
                if forming and _FORMING_WORD.search(text or "") else None)
    reach = min_reach(n) or 0.0
    last = n.get("last")
    ref = e if not isinstance(last, (int, float)) else (max(e, last) if sign > 0 else min(e, last))
    if any(sign * (p - e) >= reach - 1e-9 and sign * (p - ref) > 0 for p in prices):
        return None
    return ("it was nearer the entry than a stop and a half, the wrong side of it, or already "
            "traded through")


def _invalid_fault(text: str, n: dict[str, Any]) -> str | None:
    """Why a written invalidation cannot stand, or None: it rests on a forming
    level, or sits on the profit side of the entry. Pure."""
    sign, e = _sign(n), _entry(n)
    if not sign or e is None:
        return None
    prices = _prices(text, n)
    if any(abs(p - f) < 0.005 for p in prices for f in _forming(n)):
        return "it rested on the pre-market high/low before they lock"
    reach = min_reach(n) or 0.0
    if any(sign * (p - e) > 0.5 * reach for p in prices):
        return "it sat on the profit side of the entry"
    return None


def _target_text(n: dict[str, Any], open_mode: bool) -> str:
    """The target the server writes when the model's cannot stand. Pure."""
    c = n.get("targets") or []
    if c:
        said = [f"{x['label']} {_px(x['price'])}" if x["label"] in _LEVEL_WORD
                else f"{_px(x['price'])} ({x['label']})" for x in c[:2]]
        return "; then ".join(said)
    if open_mode:
        word = "high" if _sign(n) > 0 else "low"
        return (f"No final level beyond the entry before the open — the locked pre-market {word} "
                "if it clears a stop and a half, otherwise trail the 8 EMA wave.")
    return "No level beyond the entry — trail the 8 EMA wave."


def enforce(p: dict[str, Any], n: dict[str, Any] | None, open_mode: bool) -> dict[str, Any]:
    """The server's rules on one plan's trigger, target and invalidation. Pure;
    returns `p`, updated, with `fixes` naming each replacement and the model's
    words it replaced."""
    fixes: list[dict[str, str]] = []
    if n is not None:
        if open_mode and n.get("open_if"):
            if not _CONDITIONAL.match(p["trigger"] or ""):
                fixes.append({"field": "trigger", "was": p["trigger"],
                              "why": "before the open the trigger is what the open has to show"})
            # A conditional one is replaced too, unrecorded: the first replay
            # copied the if/then and turned its last "PDL 76.12" into "PDH
            # 76.12" (CRWV, 2026-10-14) — same figure, so the numeral guard
            # passed it. Before the open the trigger is the rule's, word for word.
            p["trigger"] = n["open_if"]
        why = _target_fault(p["target"], n)
        if why:
            fixes.append({"field": "target", "was": p["target"], "why": why})
            p["target"] = _target_text(n, open_mode)
        why = _invalid_fault(p["invalidation"], n)
        # Its own words back are not a fix: "…above PML 552.66 once it locks."
        # names a forming level, and is exactly what invalid_if writes.
        if why and n.get("invalid_if") and (p["invalidation"] or "").strip() != n["invalid_if"]:
            fixes.append({"field": "invalidation", "was": p["invalidation"], "why": why})
            p["invalidation"] = n["invalid_if"]
    if p["sym"] == "SPY":
        p["why"] = [w for w in p["why"] if not re.match(r"\s*RS\s*:", w, re.I)]
    p["fixes"] = fixes
    return p


def sanitize_plan(obj: Any, facts: dict[str, Any]) -> dict[str, Any] | None:
    """The model's plan, checked against the names it is allowed to point at. Pure.

    A plan or an avoid for a name that is not in the facts is dropped; a name
    planned twice keeps its first plan; a name both planned and avoided keeps
    the plan. Conviction is clamped to 1-5, then capped by the tape count
    (`cap_conviction`). No headline, no plan — that is the one field without
    which the page has nothing to lead with.

    Then the server's own rules (owner, 2026-10-14): a card that plans nothing
    goes to `watch`, one line; before the open the trigger is an if/then;
    a target or invalidation that breaks the strategy is replaced (`enforce`);
    the clock (`timing`) and the day's release risks (`events`) are written
    from the calendar, and a model risk that restates one of them is dropped.
    """
    if not isinstance(obj, dict):
        return None
    obj = _unwrap(obj)
    # A free model sometimes names the lead "title"; the words are the same job.
    headline = rp._text(obj.get("headline")) or rp._text(obj.get("title"))
    if not headline:
        return None
    names = {n["sym"]: n for n in facts.get("names") or []}
    allowed = set(names)
    open_mode = facts.get("session") in OPEN_SESSIONS
    plans: list[dict[str, Any]] = []
    watch: list[dict[str, str]] = []
    seen: set[str] = set()
    for p in rp._dicts(obj.get("plans")):
        sym = p.get("sym")
        if not isinstance(sym, str) or sym not in allowed or sym in seen:
            continue
        side = p.get("side") if p.get("side") in ("long", "short") else names[sym].get("side")
        conv = _conviction(p.get("conviction"))
        text = rp._text(p.get("plan"))
        if side not in ("long", "short") or conv is None or not text:
            continue
        seen.add(sym)
        item = {
            "sym": sym, "side": side, "conviction": conv, "plan": text,
            "trigger": rp._text(p.get("trigger")),
            "invalidation": rp._text(p.get("invalidation")),
            "target": rp._text(p.get("target")),
            "options": rp._text(p.get("options")),
            "why": _why(rp._texts(p.get("why"), 6)),
        }
        if _is_filler(item):
            # Before the open the line is what would make it a trade; in the
            # session, the model's own reason.
            reason = _NO_TRADE_LEAD.sub("", text).strip() or text
            line = names[sym].get("open_if") if open_mode else None
            watch.append({"sym": sym, "why": line or reason[:1].upper() + reason[1:]})
            continue
        plans.append(enforce(item, names.get(sym), open_mode))
    tape = facts.get("conviction")
    for p in plans:
        cap_conviction(p, tape if isinstance(tape, dict) else None)
    avoid: list[dict[str, str]] = []
    for a in rp._dicts(obj.get("avoid")):
        sym, why = a.get("sym"), rp._text(a.get("why"))
        if isinstance(sym, str) and sym in allowed and sym not in seen and why:
            seen.add(sym)
            avoid.append({"sym": sym, "why": why})
    watch = [w for w in watch if w["sym"] not in {a["sym"] for a in avoid}]
    return {
        "headline": headline,
        "market": rp._text(obj.get("market")),
        "plans": plans,
        "avoid": avoid,
        "watch": watch,
        "timing": clock_lines(facts),
        "events": event_risks(facts),
        "risks": [r for r in rp._texts(obj.get("risks"), 6) if not _covered(r, facts)][:4],
    }


def plan_prose(b: dict[str, Any]) -> list[str]:
    """Every string the model wrote in a sanitised plan — what the guard reads. Pure.

    Not what the server wrote: the clock, the release risks, and any field
    `enforce` replaced (its `fixes` name them).
    """
    out = [b.get("headline") or "", b.get("market") or ""]
    for p in b.get("plans") or []:
        fixed = {f.get("field") for f in p.get("fixes") or []}
        out += [p.get(k) or "" for k in ("plan", "trigger", "invalidation", "target", "options")
                if k not in fixed]
        out += list(p.get("why", []))
    out += [a.get("why") or "" for a in b.get("avoid") or []]
    out += [w.get("why") or "" for w in b.get("watch") or []]
    out += list(b.get("risks", []))
    return [x for x in out if x]


def unverified(b: dict[str, Any], seen: str) -> list[str]:
    """Numerals in the plan that the text the model was shown does not contain."""
    known = rp.known_numerals(seen)
    bad: list[str] = []
    for s in plan_prose(b):
        for k in rp.numerals_in(s):
            if k not in known and k not in bad:
                bad.append(k)
    return bad


def _reask(payload: dict[str, Any], key: str, content: str, bad: list[str],
           facts: dict[str, Any]) -> tuple[dict[str, Any] | None, dict[str, Any] | None, str]:
    """One corrective re-ask on the same model and mode → (plan, doc, outcome)."""
    retry = dict(payload)
    retry["messages"] = [*payload["messages"], {"role": "assistant", "content": content},
                         {"role": "user", "content": rp.guard_retry(bad)}]
    try:
        doc = rp._post(retry, key)
        msg = doc["choices"][0]["message"]
        text = msg.get("content") or msg.get("reasoning") or ""
    except (urllib.error.URLError, OSError, ValueError, KeyError, IndexError, TypeError) as e:
        return None, None, f"re-ask failed: {e}"
    obj = rp.extract_json(text if isinstance(text, str) else str(text))
    fixed = sanitize_plan(obj, facts) if obj is not None else None
    if fixed is None:
        return None, None, "re-ask did not return a plan"
    return fixed, doc, "re-asked"


# --------------------------------------------------------------------------
# Generation — the report's chain, budget and guard, with this module's shape.
# --------------------------------------------------------------------------


def configured() -> dict[str, Any]:
    """The same key and model as the session report — one OpenRouter setup for both desks."""
    return rp.configured()


def generate(scan: dict[str, Any], snap: dict[str, Any], top: int = TOP_DEFAULT,
             model: str | None = None, now: datetime | None = None) -> dict[str, Any]:
    """Build the facts, ask the model, store and return the plan. `now` is the
    moment the plan is dated from — the job runner's (api.py), so its id is
    the job's."""
    key = rp._key()
    now = now or datetime.now(UTC)
    et = now.astimezone(ET)
    model = model or rp.DEFAULT_MODEL
    base: dict[str, Any] = {
        "ok": False,
        "id": rp.note_id(now),
        "created_utc": now.isoformat(),
        "et_label": et.strftime("%a %d %b, %H:%M ET"),
        "model": model,
        "error": None,
        "raw": None,
        "usage": None,
        "digest": None,
        "unverified": [],
        "attempts": [],
        "facts": None,
        "plan": None,
    }
    if not key:
        base["error"] = (
            "No OPENROUTER_API_KEY. Add one to .env.local and restart the collector — the "
            "game plan is written by a model and there is deliberately no local fallback."
        )
        return base

    facts = build_facts(scan, snap, top)
    base["facts"] = facts
    if not facts["names"]:
        base["error"] = ("The scanner has no names with data yet — it fetches the watchlist a "
                         "third at a time; try again in a couple of minutes.")
        return base
    digest = build_digest(facts)
    base["digest"] = digest
    syms = [n["sym"] for n in facts["names"]]

    messages = [
        {"role": "system", "content": system_prompt(facts["session"])},
        {
            "role": "user",
            "content": (
                f"Scanner snapshot at {facts['as_of']} (session: {facts['session']}).\n\n"
                f"```json\n{json.dumps(digest, indent=1, default=str)}\n```\n\n"
                f"{tape_line(facts.get('conviction'))}\n\n"
                f"Write the New York game plan for {facts['trading_day']}. "
                f"Names in scope: {', '.join(syms)}."
            ),
        },
    ]
    sch = schema(syms)

    attempts: list[dict[str, Any]] = []
    pairs = [(m, "schema") for m in rp.model_chain(model)]
    pairs += [(m, "json") for m in rp.model_chain(model)]
    pairs = [p for p in pairs for _ in range(rp.TRIES_PER_PAIR)]
    started = time.monotonic()
    slow: set[str] = set()  # abandoned at the wall clock — passed over after (report.py)
    for candidate, mode in pairs:
        if len(attempts) >= rp.MAX_ATTEMPTS:
            break
        if candidate in slow:
            continue
        elapsed = time.monotonic() - started
        if elapsed + rp._ATTEMPT_RESERVE > rp.BUDGET_SEC:
            attempts.append({"model": candidate, "mode": mode,
                             "error": f"not attempted — {elapsed:.0f}s of the "
                                      f"{rp.BUDGET_SEC:.0f}s budget spent"})
            break
        user = messages[-1] if mode == "schema" else {
            "role": "user",
            "content": messages[-1]["content"]
            + "\n\nReturn ONLY a JSON object, no prose around it, exactly this shape:\n"
            + SKELETON,
        }
        payload: dict[str, Any] = {
            "model": candidate,
            "messages": [messages[0], user],
            "temperature": 0.3,
            # The report's reasoning: thinking is counted in max_tokens. 16,000
            # was enough until the digest grew by the tape count, flow,
            # pre-market and peers (2026-10-13): one run thought for 10.6k
            # tokens and fit, the next ran past 16k twice and answered with no
            # JSON at all (finish_reason=length). The free model allows ~236k.
            "max_tokens": 32000,
            # Capped in tokens, not an effort hint: see report.REASONING. One
            # plan with the hint alone took 158s (2026-10-21) — over the 120s
            # after which no second attempt can start.
            "reasoning": rp.REASONING,
            "response_format": (
                {"type": "json_schema",
                 "json_schema": {"name": "game_plan", "strict": True, "schema": sch}}
                if mode == "schema" else {"type": "json_object"}
            ),
        }
        try:
            doc = rp._post(payload, key)
        except urllib.error.HTTPError as e:
            detail = ""
            with contextlib.suppress(OSError):
                detail = e.read().decode("utf-8", errors="replace")[:400]
            err = f"HTTP {e.code}: {detail or e.reason}"
            attempts.append({"model": candidate, "mode": mode, "error": err})
            if e.code in rp.RETRYABLE or (e.code == 400 and mode == "schema"):
                continue
            base["error"] = f"OpenRouter {err}"
            base["attempts"] = attempts
            return base
        except rp.AttemptTimeout as e:
            # Answering, too slowly to wait for — the next model's turn.
            attempts.append({"model": candidate, "mode": mode, "error": str(e)})
            slow.add(candidate)
            continue
        except (urllib.error.URLError, OSError, ValueError) as e:
            attempts.append({"model": candidate, "mode": mode, "error": f"unreachable: {e}"})
            continue
        if doc.get("error"):
            msg = str(doc["error"].get("message", doc["error"]))
            attempts.append({"model": candidate, "mode": mode, "error": msg})
            if rp.TRANSIENT_TEXT.search(msg):
                continue
            base["error"] = f"OpenRouter: {msg}"
            base["attempts"] = attempts
            return base
        try:
            choice = doc["choices"][0]
            m = choice["message"]
            finish = choice.get("finish_reason")
        except (KeyError, IndexError, TypeError):
            attempts.append({"model": candidate, "mode": mode,
                             "error": "unexpected response shape"})
            continue
        content = m.get("content") or m.get("reasoning") or ""
        if not isinstance(content, str):
            content = str(content)
        if not content.strip():
            attempts.append({"model": candidate, "mode": mode,
                             "error": f"empty answer (finish_reason={finish})"})
            continue
        obj = rp.extract_json(content)
        if obj is None:
            attempts.append({"model": candidate, "mode": mode,
                             "error": f"no JSON object in the answer (finish_reason={finish}, "
                                      f"{len(content)} chars)"})
            base["raw"] = _ends(content)
            continue
        plan = sanitize_plan(obj, facts)
        if plan is None:
            # Usually the whole answer did not parse and the extractor fell
            # through to an inner object — the finish reason and both ends of
            # the answer say whether it was cut off or malformed.
            attempts.append({"model": candidate, "mode": mode,
                             "error": f"JSON did not match the plan shape (needs a headline; "
                                      f"finish_reason={finish}, {len(content)} chars)"})
            base["raw"] = _ends(content)
            continue

        seen = user["content"]
        bad = unverified(plan, seen)
        if bad:
            note = f"unverified numerals: {', '.join(bad[:8])}"
            if (time.monotonic() - started) + rp._ATTEMPT_RESERVE <= rp.BUDGET_SEC:
                fixed, doc2, outcome = _reask(payload, key, content, bad, facts)
                if fixed is not None and doc2 is not None:
                    bad2 = unverified(fixed, seen)
                    outcome = ("ok after re-ask" if not bad2
                               else f"re-ask still unverified: {', '.join(bad2[:8])}")
                    if len(bad2) < len(bad):
                        plan, bad, doc = fixed, bad2, doc2
                note += f" · {outcome}"
            attempts.append({"model": candidate, "mode": mode, "note": note})

        base.update({
            "ok": True, "plan": plan, "unverified": bad, "mode": mode, "model": candidate,
            "usage": doc.get("usage"), "attempts": attempts,
        })
        _store(base)
        return base

    base["attempts"] = attempts
    first = attempts[0].get("error") if attempts else "no models attempted"
    tried = ", ".join(f"{a['model']} ({a.get('mode', '?')})" for a in attempts)
    base["error"] = (f"Every model refused in {time.monotonic() - started:.0f}s. "
                     f"Tried: {tried}. First reason — {first}")
    return base


# --------------------------------------------------------------------------
# Storage — kept, like the reports, so a plan can be judged against the day.
# --------------------------------------------------------------------------


def _store(plan: dict[str, Any]) -> None:
    os.makedirs(PLANS_DIR, exist_ok=True)
    path = os.path.join(PLANS_DIR, f"{plan['id']}.json")
    tmp = path + ".tmp"
    try:
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump(plan, f)
        os.replace(tmp, path)
    except OSError:
        return
    with contextlib.suppress(OSError):
        names = sorted(n for n in os.listdir(PLANS_DIR) if n.endswith(".json"))
        for name in names[:-KEEP]:
            os.remove(os.path.join(PLANS_DIR, name))


def history(limit: int = 20) -> list[dict[str, Any]]:
    """Stored plans, newest first — the stub the list needs, without the digest."""
    if not os.path.isdir(PLANS_DIR):
        return []
    try:
        names = sorted((n for n in os.listdir(PLANS_DIR) if n.endswith(".json")), reverse=True)
    except OSError:
        return []
    out: list[dict[str, Any]] = []
    for name in names[:limit]:
        try:
            with open(os.path.join(PLANS_DIR, name), encoding="utf-8") as fh:
                d = json.load(fh)
        except (OSError, ValueError):
            continue
        body = d.get("plan") or {}
        out.append({
            "id": d.get("id"),
            "et_label": d.get("et_label"),
            "headline": body.get("headline"),
            "model": d.get("model"),
            "n": len(body.get("plans") or []),
        })
    return out


def load(plan_id: str) -> dict[str, Any] | None:
    """One stored plan. `basename` because the id arrives from the page and lands in a path."""
    path = os.path.join(PLANS_DIR, f"{os.path.basename(plan_id)}.json")
    try:
        with open(path, encoding="utf-8") as fh:
            result: dict[str, Any] = json.load(fh)
            return result
    except (OSError, ValueError):
        return None


def latest() -> dict[str, Any] | None:
    h = history(1)
    return load(h[0]["id"]) if h and h[0].get("id") else None


def remove(plan_id: str) -> bool:
    """Delete one stored plan; True if a file went. Not recoverable, as with reports."""
    path = os.path.join(PLANS_DIR, f"{os.path.basename(plan_id)}.json")
    try:
        os.remove(path)
    except OSError:
        return False
    return True


def remove_many(ids: Iterable[str]) -> list[str]:
    """Delete several stored plans; the ids that actually went, in the order asked.

    Each goes through `remove`, so each is basenamed: an id that is not a
    stored plan — a traversal, a typo, one that already went — simply does
    not appear in the answer.
    """
    return [i for i in ids if remove(i)]


def remove_all() -> list[str]:
    """Delete every stored plan — the directory's worth, not the list's.

    `history` shows the newest twenty while KEEP holds forty, so "all" has to
    be read off the disk or it would leave the older half behind and call the
    list empty. The ids that went, newest first.
    """
    try:
        names = sorted((n for n in os.listdir(PLANS_DIR) if n.endswith(".json")), reverse=True)
    except OSError:
        return []
    return [n[:-5] for n in names if remove(n[:-5])]
