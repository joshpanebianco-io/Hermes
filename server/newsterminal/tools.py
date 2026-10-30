"""
Hermes's tools — what the assistant may ask the collector for, one call at a time.

WHY TOOLS AND NOT A BIGGER PROMPT (owner, 2026-10-30: "how can we make our
hermes ai more intelligent?" and "is there a method to also be more efficient
and save tokens?"). The Hermes tab used to be handed everything on both
desks up front — about forty-seven thousand tokens, every question, most of
it irrelevant to the question — and the model skimmed it. Now the tab is
handed a slim picture of the desk (ask.slim_context, a few thousand tokens)
and this list of things it may ask for. A question about Amazon's setup
fetches Amazon's row and its headlines, two thousand tokens that matter,
and the model reasons over those. Sharper answers, a fraction of the
tokens, and the numeral check still runs on what came back.

EVERY TOOL IS A READ OF WHAT THE COLLECTOR ALREADY HOLDS. Nothing here fetches
from the internet or spends a model call; a tool is the same function a
panel reads, cut to what a question needs and capped in size. `run` is pure
given the data it is handed — the route in api.py supplies the snapshot,
the scanner payload and the note loaders.

AN ANSWER IS WRITTEN FOR A MODEL TO READ, NOT FOR A PANEL TO RENDER
(owner, 2026-10-30: "is there ways to handle it so the model uses less when
it doesn't need to?"). The first cut handed back the panels' own JSON — a
scanner row was 9,800 characters, of which the options chain was 5,300 the
question never asked about; a day's calendar was 13,500 with every release
spelled as a dict; a digest was cut mid-JSON at the cap. A headline is now a
line, a calendar release is a line, a bar is a line, and only the figures a
question can turn on keep their keys. Same facts, a third of the tokens,
and nothing truncated mid-word. The numeral check reads the same text, so
a figure quoted from a line verifies exactly as one quoted from a dict.

THE WHOLE TERMINAL, NOT A SAMPLE OF IT (owner, 2026-10-31: "fix hermes not
calling the scanner tool. make sure hermes ai has the context of the ENTIRE
app"). Asked which names were closest to a break and which had the cleanest
options read, Hermes called the stocks digest, whose forty-three-thousand-
character list of names went whole at the cap, and answered that the options
read was not in its reach. And the futures digest at its cap kept the driver
board and dropped rates, the Fed, the vol curve, cross-asset and rotation, so
whole panels could not be reached at all. Now `scanner` is the Scanner table
in one line a name — a question across names starts there — and `panel`
answers every other panel on every tab by name (PANELS is the map). A cap
shrinks a dominating list before it drops sections, and a digest names the
panel for each section it dropped.

TOOLS BELONG TO A DESK. A question about a stock has no use for the levels
ladder's schema and a question about NQ none for the scanner row's; the
schemas ride along on every round, so `spec_for` hands the route only the
desk's set (the web's router picks the desk from the question).
"""

from __future__ import annotations

import json
import re
from collections.abc import Callable, Mapping
from datetime import datetime, timedelta
from typing import Any
from zoneinfo import ZoneInfo

from . import ask, events, marketctx, optcalc, report, sessions, stockplan

ET = ZoneInfo("America/New_York")

#: A tool's answer is cut to this many characters of JSON, lists first.
MAX_CHARS = 12_000
#: Bars a chart tool hands back — the last few hours on 10-minute bars.
MAX_BARS = 36
#: Wire items a search hands back.
MAX_WIRE = 12
#: Characters of a wire summary.
WIRE_SUMMARY = 140
#: Scanner names a stocks digest carries, best score first.
DIGEST_NAMES = 12
#: The Scanner table is every watchlist name, one line each — forty lines at
#: about three hundred characters, so it gets a cap of its own.
SCANNER_CHARS = 16_000
#: Signals the signal log panel hands back, newest last.
MAX_SIGNALS = 30
#: Stored notes the past-notes panel lists, per kind.
MAX_PAST_NOTES = 10
#: A calendar day with more releases than this loses its impact-1 rows.
CALENDAR_ALL = 30
#: The futures books, for a digest or a note asked without one.
BOOKS = ("NQ", "ES", "GC")
#: Which desk each tool serves; "both" rides with either.
DESKS: dict[str, str] = {
    "scanner": "stocks", "scanner_row": "stocks", "bars": "stocks",
    "levels": "futures", "heavyweights": "futures", "event_risk": "futures",
    "wire": "both", "earnings": "both", "calendar": "both", "sessions": "both",
    "digest": "both", "note": "both", "panel": "both",
}

_STR: dict[str, Any] = {"type": "string"}


def _params(props: dict[str, Any], required: list[str] | None = None) -> dict[str, Any]:
    return {"type": "object", "properties": props, "required": required or [],
            "additionalProperties": False}


def _tool(name: str, description: str, params: dict[str, Any]) -> dict[str, Any]:
    return {"name": name, "description": description, "parameters": params}


_BOOK = {"type": "string", "enum": list(BOOKS)}

#: Every panel the other tools do not already answer, by the name `panel`
#: takes: WHERE the reader sees it, then WHAT it holds. With the tools above
#: it, this is the whole terminal — keep it in step with the tabs (lib/tabs.ts)
#: and the product map in the prompt (lib/ask/prompt.ts PRODUCT).
PANELS: dict[str, str] = {
    "driver_board": "Structure, futures · per book, every vote with its threshold and reason, "
                    "the count, the grade, conflicts, event risk and the ceiling on conviction",
    "the_book": "Structure · NQ/QQQ, ES/SPY, GC/GLD, YM and RTY: last, change and where "
                "price sits in the day's range",
    "session_ranges": "Structure, futures · the four session boxes per book (high, low, "
                      "change, range, levels taken out), the overnight, and fuel",
    "volume_profile": "Structure, futures · POC, VAH and VAL for the prior RTH, the overnight "
                      "and the developing session, the read, and yesterday's shape",
    "gamma": "Structure · dealer gamma per futures book (walls, flip, regime) and in ETF "
             "prices for QQQ, SPY and IWM",
    "volatility": "Structure · VIX, VVIX, VXN, GVZ and MOVE with their day ranges, the VIX "
                  "term structure and SKEW, and Cboe put/call",
    "expiry": "Structure · OpEx week, month end and the next expiries",
    "cot": "Structure, futures · CFTC Commitments of Traders per book: the net, its change "
           "and its percentile of the year",
    "tape_count": "Structure, stocks · the eleven tape reads with thresholds, the count, the "
                  "grade and the conviction cap",
    "breadth": "Structure, stocks · sectors up and down, equal weight against SPY, how many "
               "NDX and SPX names are up",
    "fuel": "Structure, stocks · how much of the implied day SPY, QQQ and IWM have used, the "
            "gap, relative volume",
    "index_options": "Structure, stocks · the SPY, QQQ and IWM chains: IV30, IV/RV, skew, the "
                     "front expected move, flow",
    "prints": "Macro · today's US releases against consensus, and their read",
    "rates": "Macro · the Treasury curve with daily changes, real yields, spreads, the "
             "effective funds rate and the FOMC path priced per meeting",
    "fed_diary": "Macro · FOMC meetings, Fed speakers, the Beige Book and Treasury coupon "
                 "auctions ahead",
    "cross_asset": "Macro · the dollar, yields, credit, oil, gold and the other cross-asset "
                   "rows, risk appetite and multi-day moves",
    "sector_rotation": "Macro · the eleven sector ETFs: day, week and month change and excess "
                       "return against SPY, and equal weight against cap weight",
    "index_movers": "Macro · the top NDX and SPX names by contribution, and what the shown "
                    "names add up to",
    "sector_peers": "Macro, stocks · the watchlist's sector peers reporting this week",
    "catalysts": "Analysis, futures · the brief's catalyst list: data, the Fed, auctions and "
                 "bellwether earnings, twelve hours back to three days out",
    "pool": "Scanner · the pinned list, the pool behind it, today's promotions and why, the "
            "names in play that missed, and the options expiry rule",
    "signal_log": "Scanner · the latest signals the engine saw, each with its outcome in R so "
                  "far (sym narrows it to one name)",
    "record": "Scanner · the signal record over twenty sessions by kind, side and score band: "
              "count, +1R rate, average R at the close",
    "past_notes": "Analysis · the stored briefs and game plans, newest first, with the ids "
                  "note takes",
    "sources": "The status rail · every data source's health: down, stale or on a cached "
               "copy, with the error and the age",
}

#: A digest section the cap dropped, and the panel (or tool) that answers it.
DIGEST_PANEL: dict[str, str] = {
    "engine_driver_board": "driver_board", "the_book": "the_book",
    "session_ranges": "session_ranges", "overnight_sessions": "session_ranges",
    "volume_profile": "volume_profile", "gamma_levels": "gamma", "gamma": "gamma",
    "volatility": "volatility", "vol_term_structure": "volatility", "expiry": "expiry",
    "rates": "rates", "fed": "rates", "fed_ahead": "fed_diary",
    "treasury_supply_ahead": "fed_diary", "dollar_and_commodities": "cross_asset",
    "risk_appetite": "cross_asset", "multi_day": "cross_asset", "macro": "cross_asset",
    "sector_rotation_1d_vs_spy": "sector_rotation", "tape_count": "tape_count",
    "breadth": "breadth", "fuel": "fuel", "prints": "prints", "names": "scanner (the tool)",
    "calendar": "calendar (the tool)", "next_session_events": "sessions (the tool)",
}

#: The list the model is shown, in OpenAI's function-calling shape.
SPEC: list[dict[str, Any]] = [
    _tool("scanner_row",
          "One watchlist name's scanner row: last, levels (PDH, PDL, PMH, PML, VWAP), what "
          "has broken, the setup and entry, the score and its parts, options context (IV "
          "against RV, the expected move, the suggested contract), earnings date, recent "
          "headlines and filings. Use for any question about a stock or index ETF the "
          "scanner tracks.",
          _params({"sym": {**_STR, "description": "Ticker, e.g. AMZN or SPY"}}, ["sym"])),
    _tool("scanner",
          "The whole Scanner table, one line per watchlist name: score and side, the setup and "
          "its entry with the distance in ten-minute ATRs, which levels have broken and how far "
          "price has travelled toward the ones that have not, the day's move, relative volume, "
          "relative strength against SPY, the 200 EMA side, the options read (implied against "
          "realised, liquidity and spread, the front expected move) and earnings. Call it FIRST "
          "for any question across names — which is closest to a break, the best or cleanest "
          "setup or options read, the strongest or weakest, a ranking or a comparison — then "
          "scanner_row for the one to three names worth reading in full.",
          _params({
              "sort": {"type": "string",
                       "enum": ["score", "break", "entry", "rs", "rvol", "move"],
                       "description": "score (default); break: nearest an unbroken level "
                                      "first; entry: nearest its entry first; rs: strongest "
                                      "against SPY first, weakest first with side short; rvol; "
                                      "move: the biggest day's move first"},
              "side": {"type": "string", "enum": ["long", "short"]},
              "limit": {"type": "integer", "minimum": 1, "maximum": 40},
          })),
    _tool("bars",
          "A name's recent bars, one line each (time open high low close volume, in ET), "
          "with the EMA wave, VWAP and levels. 10m is the strategy's timeframe; D for the "
          "daily frame.",
          _params({"sym": _STR,
                   "tf": {"type": "string", "enum": ["1m", "3m", "5m", "10m", "D"]}}, ["sym"])),
    _tool("wire",
          "Search the news wire. Returns the newest matching headlines with their desk and "
          "impact tier. Use it for 'why is X moving', 'what happened with Y', or anything "
          "about events.",
          _params({
              "query": {**_STR, "description": "Words to match in the title or summary; "
                                               "empty for the newest items"},
              "hours": {"type": "integer", "minimum": 1, "maximum": 168,
                        "description": "How far back; default 24"},
              "desk": {"type": "string",
                       "enum": ["markets", "corp", "macro", "policy", "geo", "energy"]},
          })),
    _tool("levels",
          "The live levels ladder for a futures book (NQ, ES or GC): prior settle, prior RTH "
          "high/low/POC, the overnight high and low, today's opens, VWAP since 18:00 and since "
          "09:30, the opening range, the expected move and the gamma walls, each with its "
          "distance from last.",
          _params({"book": _BOOK}, ["book"])),
    _tool("heavyweights",
          "What is moving an equity index name by name: the biggest weights and movers with "
          "their index-point contribution, the print if they just reported, and the headline "
          "that explains it.",
          _params({"book": {"type": "string", "enum": ["NQ", "ES"]}}, ["book"])),
    _tool("event_risk",
          "High-impact geopolitics, policy and energy stories since the last cash close, one "
          "per story, with the channels each reaches (oil, rates, semis, tariffs, war, dollar, "
          "fiscal).",
          _params({})),
    _tool("earnings",
          "Earnings: the latest prints (actual against estimate, surprise) and what reports "
          "next.",
          _params({})),
    _tool("calendar",
          "The economic calendar for one ET day, one release per line: time, name, country, "
          "actual, consensus, previous, impact and the session it lands in.",
          _params({"day": {**_STR, "description": "today, tomorrow, yesterday or YYYY-MM-DD; "
                                                  "default today"}})),
    _tool("sessions",
          "The session clock: the phase now, the four session boxes with countdowns, the next "
          "marker, and what is open.",
          _params({})),
    _tool("digest",
          "The digest for a desk — what the Analysis brief (futures) or the Game plan (stocks) "
          "is written from. Large; use only when a question spans a whole desk. On the "
          "futures desk name a book to get just its sections.",
          _params({"desk": {"type": "string", "enum": ["futures", "stocks"]},
                   "book": _BOOK}, ["desk"])),
    _tool("note",
          "A stored note: the latest Analysis brief or Game plan, or one by id, with when it "
          "was written and how old it is. A brief's reads are per book; name one to get "
          "just its read.",
          _params({"kind": {"type": "string", "enum": ["brief", "plan"]},
                   "id": {**_STR, "description": "A note id like 20261029-093225; omit for "
                                                 "the latest"},
                   "book": _BOOK}, ["kind"])),
    _tool("panel",
          "Any other panel on any tab, as the page shows it — with the tools above, the whole "
          "terminal. Call it with no name for the list. Names: "
          + "; ".join(f"{k} ({v})" for k, v in PANELS.items()) + ".",
          _params({"name": {"type": "string", "enum": list(PANELS)},
                   "book": {**_BOOK, "description": "NQ, ES or GC, for a per-book panel"},
                   "sym": {**_STR, "description": "A ticker, for signal_log"}})),
]


def spec_for(desk: str | None) -> list[dict[str, Any]]:
    """The tools for one desk ("futures" or "stocks"), or all of them."""
    if desk not in ("futures", "stocks"):
        return list(SPEC)
    return [t for t in SPEC if DESKS.get(t["name"], "both") in (desk, "both")]


def _size(v: Any) -> int:
    return len(json.dumps(v, default=str))


def _cap(v: Any, limit: int = MAX_CHARS) -> Any:
    """Cut an answer to `limit` characters of JSON: lists from the end first,
    then whole sections from the end, NAMED in `dropped` so the model knows
    what it did not get and can ask for it another way. Never a cut mid-JSON —
    the first cut did that to a digest and handed the model half a brace.

    A LIST SHRINKS BEFORE A SECTION GOES (2026-10-31). A list was capped to
    the whole budget on its own, so a list that fit alone still sank the
    answer, and the section it sat in went whole: the stocks digest's names
    were dropped every time, and the question that needed them was answered
    without them. Now no one list may hold more than half the budget while
    other sections are waiting; it is cut from the end first."""
    if _size(v) <= limit:
        return v
    if isinstance(v, list):
        while len(v) > 1 and _size(v) > limit:
            v = v[: max(1, len(v) * 2 // 3)]
        return v
    if isinstance(v, dict):
        out = dict(v)
        for k, item in out.items():
            if isinstance(item, list) and _size(out) > limit:
                out[k] = _cap(item, limit)
        while _size(out) > limit:
            lists = [(k, _size(x)) for k, x in out.items()
                     if isinstance(x, list) and len(x) > 1 and _size(x) > limit // 2]
            if not lists:
                break
            k = max(lists, key=lambda t: t[1])[0]
            out[k] = out[k][: max(1, len(out[k]) * 2 // 3)]
        dropped: list[str] = []
        while len(out) > 1 and _size({**out, "dropped": dropped}) > limit:
            k = next(reversed(out))
            dropped.insert(0, k)
            out.pop(k)
        if dropped:
            out["dropped"] = dropped
        if _size(out) > limit:
            return {"truncated": True, "text": json.dumps(out, default=str)[:limit]}
        return out
    return {"truncated": True, "text": json.dumps(v, default=str)[:limit]}


def _name_dropped(out: dict[str, Any]) -> dict[str, Any]:
    """Point a capped digest's dropped sections at the panels that hold them."""
    gone = out.get("dropped")
    if isinstance(gone, list) and gone:
        out["ask_panel_for"] = sorted({DIGEST_PANEL[k] for k in gone if k in DIGEST_PANEL})
    return out


def _d(v: Any) -> dict[str, Any]:
    return v if isinstance(v, dict) else {}


def _day_of(arg: Any, now: datetime) -> str:
    today = now.astimezone(ET).date()
    word = str(arg or "today").strip().lower()
    if word in ("", "today"):
        return today.isoformat()
    if word == "tomorrow":
        return (today + timedelta(days=1)).isoformat()
    if word == "yesterday":
        return (today - timedelta(days=1)).isoformat()
    try:
        return datetime.strptime(word, "%Y-%m-%d").date().isoformat()
    except ValueError:
        return today.isoformat()


def _stamp(ts: Any, now: datetime) -> str | None:
    if not isinstance(ts, int | float):
        return None
    at = datetime.fromtimestamp(ts, ET)
    today = at.date() == now.astimezone(ET).date()
    return at.strftime("%H:%M ET") if today else at.strftime("%a %d %H:%M ET")


def _hours(v: Any) -> int:
    if isinstance(v, bool) or not isinstance(v, int):
        return 24
    return max(1, min(168, v))


def _book_arg(a: dict[str, Any], default: str | None = None) -> str | None:
    b = str(a.get("book") or "").upper().strip()
    return b if b in BOOKS else default


def _num(v: Any) -> str:
    """A figure as the line prints it: the row's own precision, no float noise."""
    if isinstance(v, bool) or v is None:
        return "—"
    if isinstance(v, int):
        return str(v)
    if isinstance(v, float):
        s = f"{v:.4f}".rstrip("0").rstrip(".")
        return s if s not in ("", "-0") else "0"
    return str(v)


# --------------------------------------------------------------------------
# The compact answers

def _row_brief(row: dict[str, Any], now: datetime) -> dict[str, Any]:
    """A scanner row cut to what a question can turn on. The options chain's
    contract list, the term structure and the flow's top strikes — the detail
    pane's — are left out; the figures a setup is judged by stay."""
    score, setup, levels = _d(row.get("score")), _d(row.get("setup")), _d(row.get("levels"))
    earn, opt, frame = _d(row.get("earnings")), _d(row.get("options")), _d(row.get("frame_read"))
    broken, rs = _d(row.get("broken")), _d(row.get("rs"))
    liq, flow = _d(opt.get("liquidity")), _d(opt.get("flow"))
    return {
        "sym": row.get("sym"), "name": row.get("name"), "sector": row.get("sector"),
        "last": row.get("last"), "prev_close": row.get("prev"),
        "chg_pct": row.get("chg_pct"), "ext_pct": row.get("ext_pct"), "rvol": row.get("rvol"),
        "trend": row.get("trend"), "rs_vs_spy_atr": rs.get("SPY"),
        "ema200_10m": {"side": {1: "above", -1: "below"}.get(int(row.get("trend200") or 0), "on"),
                       "value": levels.get("ema200"), "slope": row.get("ema200_slope")}
        if levels.get("ema200") is not None else None,
        "score": {
            "total": score.get("total"), "side": score.get("side"),
            "parts": [f"{p.get('label')} {_num(p.get('pts'))}/{_num(p.get('max'))} — "
                      f"{p.get('note')}"
                      for p in score.get("parts") or [] if isinstance(p, dict)],
        },
        "setup": {k: setup.get(k) for k in ("side", "state", "level", "entry", "note")},
        "levels": {k: levels.get(k) for k in ("pdh", "pdl", "pmh", "pml", "vwap", "ema200")},
        "broken": [k.upper() for k, v in broken.items() if v],
        "daily_frame": frame.get("text"),
        "short_interest": row.get("short"),
        "earnings": (f"{earn.get('date')} {earn.get('when') or ''}".strip()
                     if earn.get("date") else None),
        "options": ({
            "asof": opt.get("asof"), "age_min": opt.get("age_min"),
            "iv30": opt.get("iv30"), "rv20": opt.get("rv20"), "iv_rv": opt.get("iv_rv"),
            "premium": opt.get("premium"), "iv_rank": opt.get("iv_rank"),
            "skew": opt.get("skew"), "expected_move": opt.get("em"),
            "liquidity": {"grade": liq.get("grade"), "spread_pct": liq.get("spread_pct")},
            "zero_dte": opt.get("zero_dte"), "earnings_in": opt.get("earnings_in"),
            "earnings_move": opt.get("earnings_move"),
            "pick": opt.get("pick"), "structure": opt.get("structure"),
            "targets": opt.get("targets"),
            "flow": {"pc_vol": flow.get("pc_vol"), "lean": flow.get("lean")},
        } if opt.get("ok") else {"error": opt.get("error") or "no options data"}),
        "news": [f"{n.get('title')} — {n.get('publisher')}, {_when(n.get('utc'), now)}"
                 for n in row.get("news") or [] if isinstance(n, dict)],
        "filings": row.get("filings") or [],
        "flags": [f["text"] for f in row.get("flags") or []
                  if isinstance(f, dict) and f.get("text")],
        "peers": row.get("peers"),
        # What the table's break bars, the pre-market and the detail pane show
        # (2026-10-31): the row had them and the tool left them out.
        "toward_unbroken": _toward(row) or None,
        "range_used": row.get("range_used"),
        "atr": {"daily": row.get("atr_d"), "ten_min": row.get("atr_b")},
        "rs_last_hour_vs_spy_atr": _d(row.get("rs_1h")).get("SPY"),
        "sector_vs_spy": row.get("sector_rs"),
        "premarket": row.get("premkt"),
        "signals": [f"{s.get('at_et')} {s.get('note')}" for s in (row.get("signals") or [])[-3:]
                    if isinstance(s, dict)],
        "record": row.get("record"),
        "promoted": row.get("promoted"),
    }


_LEVELS = ("pdh", "pdl", "pmh", "pml")


def _toward(row: dict[str, Any], at_least: float = 0.0) -> list[str]:
    """How far price has travelled toward each level not yet broken, nearest
    first, as the table's bars print it, with the level's price beside it —
    without it the model once named the last price as the level (2026-10-31):
    "PML 32.05 (98.2%)"."""
    prog, broken, lv = _d(row.get("progress")), _d(row.get("broken")), _d(row.get("levels"))
    got = [(float(p), k) for k in _LEVELS
           if isinstance(p := prog.get(k), int | float) and not broken.get(k)
           and p >= at_least]
    got.sort(reverse=True)

    def label(k: str, p: float) -> str:
        at = f" {_num(lv[k])}" if lv.get(k) is not None else ""
        return f"{k.upper()}{at} ({round(p * 100, 1)}%)"

    return [label(k, p) for p, k in got]


def _nearest_break(row: dict[str, Any]) -> float:
    prog, broken = _d(row.get("progress")), _d(row.get("broken"))
    vals = [float(p) for k in _LEVELS
            if isinstance(p := prog.get(k), int | float) and not broken.get(k)]
    return max(vals) if vals else -1.0


def _scan_line(row: dict[str, Any]) -> str:
    """One Scanner row as one line, in the table's order: the rank, the setup,
    the levels, the tape, the options read, the calendar."""
    sym = row.get("sym")
    if not row.get("ok"):
        return f"{sym} · no data: {row.get('error') or 'not loaded yet'}"
    score, setup = _d(row.get("score")), _d(row.get("setup"))
    entry, opt = _d(setup.get("entry")), _d(row.get("options"))
    parts = [f"{sym} · score {_num(score.get('total'))} {score.get('side') or 'no side'}"]
    if setup.get("note"):
        parts.append(f"{setup.get('state') or 'setup'}: {setup.get('note')}")
    if entry.get("price") is not None:
        parts.append(f"entry {entry.get('kind')} {_num(entry.get('price'))} "
                     f"({_num(entry.get('dist_atr'))} ATR)")
    broke = [k.upper() for k in _LEVELS if _d(row.get("broken")).get(k)]
    parts.append("broke " + " ".join(broke) if broke else "nothing broken")
    # Each pair's bars split the way between its two levels, so the far side
    # of a pair is under half by construction; the line keeps the near side.
    near = _toward(row, at_least=0.5)
    if near:
        parts.append("toward " + ", ".join(near))
    move = f"last {_num(row.get('last'))} · day {_num(row.get('chg_pct'))}%"
    if row.get("ext_pct") is not None:
        move += f" · ext {_num(row.get('ext_pct'))}%"
    parts.append(move)
    parts.append(f"rvol {_num(row.get('rvol'))} · RS vs SPY "
                 f"{_num(_d(row.get('rs')).get('SPY'))} ATR")
    side200 = {1: "above", -1: "below"}.get(int(row.get("trend200") or 0))
    if side200:
        parts.append(f"200 EMA {side200}")
    if opt.get("ok"):
        liq = _d(opt.get("liquidity"))
        o = f"options IV/RV {_num(opt.get('iv_rv'))} {opt.get('premium') or ''}".rstrip()
        o += f", liquidity {liq.get('grade')} ({_num(liq.get('spread_pct'))}% spread)"
        front = next((e for e in opt.get("em") or []
                      if isinstance(e, dict) and e.get("key") == "front"), None)
        if front:
            o += f", front expected move {_num(front.get('pct'))}%"
        parts.append(o)
    else:
        parts.append(f"options: {opt.get('error') or 'none'}")
    earn = _d(row.get("earnings"))
    if earn.get("date"):
        parts.append(f"earnings {earn.get('date')} {earn.get('when') or ''}".rstrip())
    promo = _d(row.get("promoted"))
    if promo:
        parts.append(f"promoted at {promo.get('mark')}: {promo.get('reason')}")
    return " · ".join(parts)


_SCAN_SORT: dict[str, Callable[[dict[str, Any]], float]] = {
    "score": lambda r: -float(_d(r.get("score")).get("total") or 0),
    "break": lambda r: -_nearest_break(r),
    "entry": lambda r: abs(float(_d(_d(r.get("setup")).get("entry")).get("dist_atr") or 99)),
    "rs": lambda r: -float(_d(r.get("rs")).get("SPY") or 0),
    "rvol": lambda r: -float(r.get("rvol") or 0),
    "move": lambda r: -abs(float(r.get("chg_pct") or 0)),
}


def _scanner(scan: dict[str, Any], a: dict[str, Any]) -> dict[str, Any]:
    """The Scanner table, ranked and filtered as asked, one line a name."""
    sort = str(a.get("sort") or "score")
    if sort not in _SCAN_SORT:
        sort = "score"
    side = a.get("side") if a.get("side") in ("long", "short") else None
    limit = a.get("limit")
    limit = limit if isinstance(limit, int) and not isinstance(limit, bool) else 40
    limit = max(1, min(40, limit))
    rows = [r for r in scan.get("rows") or [] if isinstance(r, dict)]
    live = [r for r in rows if r.get("ok")]
    if side:
        live = [r for r in live if _d(r.get("score")).get("side") == side]
    key = _SCAN_SORT[sort]
    if sort == "rs" and side == "short":
        live.sort(key=lambda r: -key(r))
    else:
        live.sort(key=key)
    reg, conv = _d(scan.get("regime")), _d(_d(scan.get("regime")).get("conviction"))
    out = {
        "as_of_utc": scan.get("built_utc"), "session": scan.get("session"),
        "trading_day": scan.get("trading_day"),
        "pre_market_levels_final": scan.get("pm_locked"),
        "tape": {f: conv.get(f) for f in ("bias", "grade", "agree", "total", "max_conviction")},
        "vix": {"last": _d(reg.get("vix")).get("last"), "band": reg.get("band")},
        "sort": sort, "side": side, "names": len(live), "shown": min(limit, len(live)),
        "format": "sym · score side · setup state: note · entry (distance in 10-minute ATRs) · "
                  "levels broken · progress toward unbroken levels · last · day % · ext % · "
                  "rvol · RS vs SPY in daily ATRs · 200 EMA side · options · earnings · promotion",
        "rows": [_scan_line(r) for r in live[:limit]],
        "no_data": [_scan_line(r) for r in rows if not r.get("ok")],
    }
    return _cap(out, SCANNER_CHARS)


def _when(utc: Any, now: datetime) -> str:
    """An ISO instant as the line prints it, or the raw value when it is not one."""
    if not isinstance(utc, str):
        return "—"
    try:
        at = datetime.fromisoformat(utc.replace("Z", "+00:00"))
    except ValueError:
        return utc
    return _stamp(at.timestamp(), now) or utc


def _wire(snap: dict[str, Any], a: dict[str, Any], now: datetime) -> dict[str, Any]:
    q = str(a.get("query") or "").strip()
    hours = _hours(a.get("hours"))
    desk = a.get("desk")
    since = now.timestamp() - hours * 3600
    words = [w for w in re.split(r"\W+", q.lower()) if len(w) >= 3]
    pool: list[tuple[float, str, str]] = []
    for h in snap.get("wire") or []:
        if not isinstance(h, dict):
            continue
        ts = h.get("ts")
        if not isinstance(ts, int | float) or ts < since:
            continue
        if desk and h.get("category") != desk:
            continue
        text = f"{h.get('title') or ''} {h.get('summary') or ''}".lower()
        line = (f"{_stamp(ts, now)} · {str(h.get('impact') or '').upper()} · "
                f"{h.get('category')} · {h.get('title')} — {h.get('publisher')}")
        summary = (h.get("summary") or "").strip()
        if summary:
            line += f" · {summary[:WIRE_SUMMARY]}"
        pool.append((float(ts), text, line))
    # Every word first; failing that, any word — a model searches "Nasdaq
    # futures oil Houthi" and the story says "Nasdaq" or "Houthi", not both.
    # The answer says which matched so the model knows how loose it was.
    match = "all"
    hits = [p for p in pool if all(w in p[1] for w in words)] if words else pool
    if words and not hits:
        match = "any"
        hits = [p for p in pool if any(w in p[1] for w in words)]
    hits.sort(key=lambda x: -x[0])
    return {"query": q or None, "hours": hours, "matches": len(hits),
            "match": match if words else None,
            "format": "time · impact · desk · title — publisher · summary",
            "items": [line for _, _, line in hits[:MAX_WIRE]]}


def _last(v: Any) -> Any:
    """A series' last value, or the value itself."""
    if isinstance(v, list):
        return v[-1] if v else None
    return v


def _bars(doc: dict[str, Any], sym: str, tf: str, now: datetime) -> dict[str, Any]:
    if not doc.get("ok"):
        return {"error": doc.get("error") or f"no bars for {sym}"}
    rows = [f"{_stamp(b.get('t'), now)} {_num(b.get('o'))} {_num(b.get('h'))} "
            f"{_num(b.get('l'))} {_num(b.get('c'))} {_num(b.get('v'))}"
            for b in (doc.get("bars") or [])[-MAX_BARS:] if isinstance(b, dict)]
    return _cap({"sym": sym, "tf": tf, "format": "time open high low close volume",
                 "bars": rows, "ema8_last": _last(doc.get("ema8")),
                 "vwap_last": _last(doc.get("vwap")), "levels": doc.get("levels"),
                 "signals": (doc.get("signals") or [])[-4:]})


def _calendar(snap: dict[str, Any], day: str) -> dict[str, Any]:
    rows = [r for r in snap.get("calendar") or []
            if isinstance(r, dict) and str(r.get("date") or "")[:10] == day]
    rows.sort(key=lambda r: str(r.get("et") or ""))
    # A full day is seventy-odd releases, most of them impact 1 and most of
    # those nothing this desk trades; past CALENDAR_ALL the low-impact rows
    # go, counted, and the model can ask for a date to see them.
    omitted = 0
    if len(rows) > CALENDAR_ALL:
        kept = [r for r in rows if (r.get("score") or 0) >= 2]
        omitted = len(rows) - len(kept)
        rows = kept
    lines: list[str] = []
    for r in rows:
        line = (f"{r.get('et') or '—'} {r.get('event')} ({r.get('country')}) · "
                f"act {_num(r.get('actual'))} · cons {_num(r.get('consensus'))} · "
                f"prev {_num(r.get('previous'))}")
        if r.get("surprise") not in (None, ""):
            line += f" · surprise {_num(r.get('surprise'))}"
        line += f" · impact {_num(r.get('score'))} · {r.get('session')}"
        if r.get("actual") not in (None, "") and r.get("read"):
            line += f" · read: {str(r.get('read'))[:120]}"
        lines.append(line)
    return _cap({"day": day, "releases": len(lines), "omitted_low_impact": omitted,
                 "format": "time name (country) · actual · consensus · previous · impact · session",
                 "rows": lines})


def _heavy_line(r: dict[str, Any]) -> str:
    line = (f"{r.get('symbol')} w{_num(r.get('weight_pct'))}% {_num(r.get('move_pct'))}% "
            f"({_num(r.get('index_points'))} pts)")
    p = _d(r.get("reported"))
    if p:
        line += (f" · reported {p.get('date')} {p.get('when') or ''} {p.get('eps_actual')} vs "
                 f"{p.get('eps_forecast')}")
        if p.get("surprise_pct") is not None:
            line += f" ({_num(p.get('surprise_pct'))}%)"
    h = _d(r.get("headline"))
    if h:
        line += (f" · \"{h.get('title')}\" — {h.get('publisher')}, {h.get('time_et')}, "
                 f"{h.get('impact')}")
    return line


def _earn_line(r: dict[str, Any]) -> str:
    line = ask._earn_line(r)
    if r.get("surprise_pct") is not None:
        line += f" ({_num(r.get('surprise_pct'))}% surprise)"
    return line


def _futures_digest(snap: dict[str, Any], book: str | None) -> dict[str, Any]:
    """The brief's digest, less the sections that have tools of their own, and
    only the book asked for where a section is keyed by book."""
    sess = report.resolve_session(snap.get("clock") or {}, "auto")
    full = report.build_digest(snap, sess, "all")
    own_tools = {"headlines", "heavyweights", "brief_tables", "catalysts", "event_risk",
                 "earnings", "index_movers"}
    # The book's own sections first: the cap drops from the end, and the
    # driver board is the last thing a question about a book can do without.
    first = ["engine_driver_board", "session_ranges", "volume_profile", "gamma_levels"]
    books = (book,) if book else BOOKS
    out: dict[str, Any] = {"books": list(books)}
    for k in [*first, *(k for k in full if k not in first)]:
        v = full.get(k)
        if k in own_tools or v is None:
            continue
        if isinstance(v, dict) and set(v) & set(BOOKS):
            out[k] = {b: v[b] for b in books if b in v}
        else:
            out[k] = v
    # All three boards' votes were eleven thousand characters, and with them
    # in front the cap kept nothing else (2026-10-31). Without a book the
    # board is its headline per book; the votes are a panel call away.
    if not book and isinstance(out.get("engine_driver_board"), dict):
        out["engine_driver_board"] = {
            b: {f: _d(v).get(f) for f in ("bias", "grade", "agree", "total", "conflict",
                                         "event_risk", "max_conviction", "treatment")}
            for b, v in out["engine_driver_board"].items()}
    return _name_dropped(_cap(out))


def _stocks_digest(scan: dict[str, Any], snap: dict[str, Any]) -> dict[str, Any]:
    """The plan's digest with the names as the scanner table's compact rows."""
    facts = stockplan.build_facts(scan, snap, top=stockplan.TOP_MAX)
    full = stockplan.build_digest(facts)

    # The tape and the names first; the strategy text last, since the prompt
    # already carries the strategy and the cap drops from the end.
    first = ["regime", "tape_count", "breadth", "fuel", "prints"]
    out: dict[str, Any] = {k: full[k] for k in first if k in full}
    # The names as the Scanner table's lines: as dicts they were forty-three
    # thousand characters and the cap dropped them whole (2026-10-31).
    rows = sorted((r for r in scan.get("rows") or [] if isinstance(r, dict) and r.get("ok")),
                  key=_SCAN_SORT["score"])
    out["names"] = [_scan_line(r) for r in rows[:DIGEST_NAMES]]
    for k, v in full.items():
        if k not in out and k not in ("names", "strategy"):
            out[k] = v
    if "strategy" in full:
        out["strategy"] = full["strategy"]
    return _name_dropped(_cap(out))


def _note(got: dict[str, Any], kind: str, book: str | None) -> dict[str, Any]:
    """A stored note cut to its calls and, for a brief, the one book's read."""
    note = _d(got.get("note"))
    head = {k: got.get(k) for k in ("written_et", "age_hours", "model", "session", "book")}
    if kind == "plan":
        names = note.get("names")
        plan_body = dict(note)
        if isinstance(names, list):
            plan_body["names"] = names[:DIGEST_NAMES]
        return _cap({**head, "note": plan_body})
    calls = [c for c in note.get("calls") or [] if isinstance(c, dict)]
    reads = [r for r in note.get("reads") or [] if isinstance(r, dict)]
    if book:
        calls = [c for c in calls if c.get("book") == book] or calls
        reads = [r for r in reads if r.get("book") == book]
    keep = ("thesis", "snapshot_watch", "gamma_read", "catalyst_notes", "risks", "cross_asset")
    body: dict[str, Any] = {k: note.get(k) for k in keep if note.get(k) not in (None, "", [])}
    body["calls"] = calls
    body["reads"] = reads
    return _cap({**head, "note": body})


# --------------------------------------------------------------------------
# The panels

#: Panels read from the brief's digest, and those from the stocks desk's context.
_FUTURES_DIGEST_PANELS = frozenset({
    "driver_board", "the_book", "session_ranges", "volume_profile", "gamma", "volatility",
    "expiry", "rates", "fed_diary", "cross_asset", "sector_rotation", "index_movers",
    "catalysts"})
_MARKET_PANELS = frozenset({
    "gamma", "rates", "cross_asset", "tape_count", "breadth", "fuel", "index_options",
    "prints", "sector_peers"})


def _by_book(v: Any, book: str | None) -> Any:
    if book and isinstance(v, dict) and set(v) & set(BOOKS):
        return {b: v[b] for b in (book,) if b in v}
    return v


def _r2(v: Any) -> Any:
    return round(v, 2) if isinstance(v, float) else v


def _event_line(e: dict[str, Any]) -> str:
    o = _d(e.get("outcome"))
    line = (f"{e.get('day')} {e.get('at_et')} {e.get('sym')} ({e.get('kind')}) "
            f"{e.get('side') or ''} {e.get('level') or ''} at {_num(e.get('price'))}")
    line = " ".join(line.split())
    if e.get("stop") is not None:
        line += f" · stop {_num(e.get('stop'))}"
    if e.get("score") is not None:
        line += f" · score {_num(e.get('score'))}"
    if o:
        line += (f" · {_num(o.get('r'))}R now, best {_num(o.get('mfe_r'))}R, "
                 f"worst {_num(o.get('mae_r'))}R")
        if o.get("hit_1r"):
            line += " · reached +1R"
        if o.get("stopped"):
            line += " · stopped"
        if not o.get("final"):
            line += " · still running"
    if e.get("retracted"):
        line += " · withdrawn"
    return line


def _source_line(key: str, s: dict[str, Any]) -> str:
    state = "ok" if s.get("ok") else "DOWN"
    if s.get("ok") and s.get("source") not in (None, "live"):
        state = f"serving a {s.get('source')} copy"
    line = f"{s.get('name') or key}: {state}"
    # Whole minutes, as the rail prints them: a raw 195.7333 was quoted as
    # 196 and flagged as unverified (2026-10-31).
    if isinstance(s.get("age_min"), int | float):
        line += f" · {round(s['age_min'])} min old"
    if isinstance(s.get("stale_age_min"), int | float):
        line += f" · stale {round(s['stale_age_min'])} min"
    if s.get("error"):
        line += f" · {str(s.get('error'))[:140]}"
    return line


def _panel(name: str, a: dict[str, Any], snap: dict[str, Any], scan: dict[str, Any] | None,
           more: Mapping[str, Callable[[], Any]], now: datetime) -> dict[str, Any]:
    """One panel by name, as the page shows it (PANELS). Pure given `more`."""
    if not name:
        return {"panels": [f"{k} — {v}" for k, v in PANELS.items()],
                "other_tools": "scanner, scanner_row, bars, levels, heavyweights, event_risk, "
                               "wire, calendar, earnings, sessions, note, digest"}
    if name not in PANELS:
        return {"error": f"no panel {name!r}", "panels": list(PANELS)}
    book = _book_arg(a)
    head: dict[str, Any] = {"panel": name, "where": PANELS[name].split(" · ")[0],
                            "as_of_et": (snap.get("clock") or {}).get("et")}
    fd: dict[str, Any] = {}
    if name in _FUTURES_DIGEST_PANELS:
        sess = report.resolve_session(snap.get("clock") or {}, "auto")
        fd = report.build_digest(snap, sess, "all")
    mk: dict[str, Any] = {}
    if name in _MARKET_PANELS:
        if scan is not None:
            mk = marketctx.build(scan, snap)
        elif name not in _FUTURES_DIGEST_PANELS:
            return {**head, "error": "the scanner has not built yet, so the stocks desk's "
                                     "context is not there"}

    def need(key: str) -> Any:
        fn = more.get(key)
        return fn() if fn else None

    body: dict[str, Any]
    if name == "driver_board":
        body = {"board": _by_book(fd.get("engine_driver_board"), book)}
    elif name == "the_book":
        body = {"book": fd.get("the_book")}
    elif name == "session_ranges":
        body = {"ranges": _by_book(fd.get("session_ranges"), book),
                "overnight": _by_book(fd.get("overnight_sessions"), book)}
    elif name == "volume_profile":
        body = {"profile": _by_book(fd.get("volume_profile"), book)}
    elif name == "gamma":
        body = {"futures": _by_book(fd.get("gamma_levels"), book), "etf_prices": mk.get("gamma")}
    elif name == "volatility":
        body = {"quotes": fd.get("volatility"), "term_structure": fd.get("vol_term_structure"),
                "put_call": snap.get("putcall")}
    elif name == "expiry":
        body = {"expiry": fd.get("expiry")}
    elif name == "cot":
        body = {"cot": _by_book(_d(snap.get("cot")).get("books"), book)}
    elif name == "tape_count":
        body = {"tape": mk.get("conviction")}
    elif name in ("breadth", "fuel", "index_options", "prints"):
        body = {name: mk.get(name)}
    elif name == "sector_peers":
        body = {"peers": mk.get("peers")}
    elif name == "rates":
        body = {"rates": fd.get("rates"), "fed_path": mk.get("fed"),
                "policy_meetings": snap.get("policy_meetings")}
    elif name == "fed_diary":
        body = {"fed_ahead": fd.get("fed_ahead"),
                "treasury_supply_ahead": fd.get("treasury_supply_ahead"),
                "fed_calendar": snap.get("fed"), "auctions": snap.get("auctions")}
    elif name == "cross_asset":
        body = {"dollar_and_commodities": fd.get("dollar_and_commodities"),
                "risk_appetite": fd.get("risk_appetite"), "multi_day": fd.get("multi_day"),
                "stocks_desk_rows": mk.get("macro")}
    elif name == "sector_rotation":
        body = {"read": fd.get("sector_rotation_1d_vs_spy"), "sectors": [
            {"etf": s.get("key"), "sector": s.get("label"), "last": s.get("last"),
             "day_pct": _r2(s.get("day_pct")), "week_pct": _r2(s.get("week_pct")),
             "month_pct": _r2(s.get("month_pct")), "vs_spy_day": _r2(s.get("rs_day")),
             "vs_spy_week": _r2(s.get("rs_week")), "vs_spy_month": _r2(s.get("rs_month"))}
            for s in snap.get("sectors") or [] if isinstance(s, dict)]}
    elif name == "index_movers":
        body = {"movers": fd.get("index_movers")}
    elif name == "catalysts":
        body = {"catalysts": fd.get("catalysts")}
    elif name == "pool":
        w = need("watchlist")
        if not isinstance(w, dict):
            return {**head, "error": "the pool is not readable here"}
        body = {"pinned": w.get("symbols"), "pool": w.get("pool"),
                "options_expiry_rule": optcalc.expiry_rule().get("text")}
    elif name == "signal_log":
        evs = need("events")
        if not isinstance(evs, list):
            return {**head, "error": "the signal log is not readable here"}
        sym = str(a.get("sym") or "").upper().strip()
        evs = [e for e in evs if isinstance(e, dict) and (not sym or e.get("sym") == sym)]
        body = {"sym": sym or None, "signals": len(evs),
                "format": "day time sym (kind) side level at price · stop · score · R now, "
                          "best, worst · flags; kinds: L retest, E entry, BO breakout, NEAR "
                          "90% to a level",
                "rows": [_event_line(e) for e in evs[-MAX_SIGNALS:]]}
    elif name == "record":
        st = need("stats")
        if not isinstance(st, dict):
            return {**head, "error": "the record is not readable here"}
        body = {"record": st}
    elif name == "past_notes":
        h = need("history")
        if not isinstance(h, dict):
            return {**head, "error": "past notes are not readable here"}
        body = {k: (v or [])[:MAX_PAST_NOTES] for k, v in h.items()}
    else:  # sources
        st = snap.get("status") or {}
        lines = [_source_line(k, s) for k, s in st.items() if isinstance(s, dict)]
        body = {"sources": len(lines), "problems": [ln for ln in lines if ": ok" not in ln],
                "all": lines}
    return _cap({**head, **body})


# --------------------------------------------------------------------------

def run(
    name: str,
    args: dict[str, Any] | None,
    *,
    snap: dict[str, Any],
    scan: dict[str, Any] | None,
    bars: Callable[[str, str], dict[str, Any]],
    brief: Callable[[str | None], dict[str, Any] | None],
    plan: Callable[[str | None], dict[str, Any] | None],
    now: datetime | None = None,
    more: Mapping[str, Callable[[], Any]] | None = None,
) -> dict[str, Any]:
    """Answer one tool call. Always a dict; an unknown name or a name the
    scanner does not track comes back as `{"error": ...}` the model can read,
    never an exception the route has to catch. `more` reads what lives in the
    collector rather than the snapshot — "watchlist" (the pool), "events" (the
    signal log, newest last), "stats" (the record), "history" (past notes)."""
    a = args if isinstance(args, dict) else {}
    now = now or report._now_et(snap)
    try:
        if name == "scanner":
            if scan is None:
                return {"error": "the scanner has not built yet"}
            return _scanner(scan, a)
        if name == "panel":
            return _panel(str(a.get("name") or ""), a, snap, scan, more or {}, now)
        if name == "scanner_row":
            sym = str(a.get("sym") or "").upper().strip()
            row = ask.selected_row(scan, sym)
            if row is None:
                have = [r.get("sym") for r in (scan or {}).get("rows") or []
                        if isinstance(r, dict)]
                return {"error": f"{sym or 'that name'} is not on the scanner's watchlist",
                        "watchlist": have}
            return _cap(_row_brief(row, now))
        if name == "bars":
            sym = str(a.get("sym") or "").upper().strip()
            tf = str(a.get("tf") or "10m")
            if tf not in ("1m", "3m", "5m", "10m", "D"):
                tf = "10m"
            return _bars(bars(sym, tf), sym, tf, now)
        if name == "wire":
            return _wire(snap, a, now)
        if name == "levels":
            book = _book_arg(a, "NQ") or "NQ"
            lad = report.live_ladders(snap).get(book)
            return _cap(lad) if lad else {"error": f"no ladder for {book} yet"}
        if name == "heavyweights":
            book = str(a.get("book") or "NQ").upper()
            rows = events.heavyweights(snap, book, now)
            return {"book": book,
                    "format": "symbol weight move (index points) · print · headline",
                    "rows": [_heavy_line(r) for r in rows]}
        if name == "event_risk":
            return {"since": "the last cash close", "events": events.event_risk(snap, now)}
        if name == "earnings":
            earn = report.digest_earnings(snap.get("earnings") or [], now)
            return {k: [_earn_line(r) for r in v] for k, v in earn.items()}
        if name == "calendar":
            return _calendar(snap, _day_of(a.get("day"), now))
        if name == "sessions":
            st = sessions.session_state(now)
            return {"et": st.get("et_time"), "phase": st.get("phase"), "boxes": st.get("boxes"),
                    "next": (st.get("markers") or [None])[0],
                    "open": [s["label"] for s in st.get("sessions") or [] if s.get("open")]}
        if name == "digest":
            if str(a.get("desk") or "futures") == "stocks":
                if scan is None:
                    return {"error": "the scanner has not built yet"}
                return _stocks_digest(scan, snap)
            return _futures_digest(snap, _book_arg(a))
        if name == "note":
            kind = "plan" if str(a.get("kind") or "brief") == "plan" else "brief"
            nid = a.get("id") if isinstance(a.get("id"), str) else None
            rec = (plan if kind == "plan" else brief)(nid)
            got = ask.latest_note(rec)
            if got:
                return _note(got, kind, _book_arg(a))
            return {"error": f"no {kind}" + (f" {nid}" if nid else " stored")}
        return {"error": f"unknown tool {name!r}", "tools": [t["name"] for t in SPEC]}
    except (ValueError, TypeError, KeyError, AttributeError, ZeroDivisionError) as e:
        return {"error": f"{name} failed: {e.__class__.__name__}: {e}"}
