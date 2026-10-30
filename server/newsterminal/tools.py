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

TOOLS BELONG TO A DESK. A question about a stock has no use for the levels
ladder's schema and a question about NQ none for the scanner row's; the
schemas ride along on every round, so `spec_for` hands the route only the
desk's set (the web's router picks the desk from the question).
"""

from __future__ import annotations

import json
import re
from collections.abc import Callable
from datetime import datetime, timedelta
from typing import Any
from zoneinfo import ZoneInfo

from . import ask, events, report, sessions, stockplan

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
#: A calendar day with more releases than this loses its impact-1 rows.
CALENDAR_ALL = 30
#: The futures books, for a digest or a note asked without one.
BOOKS = ("NQ", "ES", "GC")
#: Which desk each tool serves; "both" rides with either.
DESKS: dict[str, str] = {
    "scanner_row": "stocks", "bars": "stocks",
    "levels": "futures", "heavyweights": "futures", "event_risk": "futures",
    "wire": "both", "earnings": "both", "calendar": "both", "sessions": "both",
    "digest": "both", "note": "both",
}

_STR: dict[str, Any] = {"type": "string"}


def _params(props: dict[str, Any], required: list[str] | None = None) -> dict[str, Any]:
    return {"type": "object", "properties": props, "required": required or [],
            "additionalProperties": False}


def _tool(name: str, description: str, params: dict[str, Any]) -> dict[str, Any]:
    return {"name": name, "description": description, "parameters": params}


_BOOK = {"type": "string", "enum": list(BOOKS)}

#: The list the model is shown, in OpenAI's function-calling shape.
SPEC: list[dict[str, Any]] = [
    _tool("scanner_row",
          "One watchlist name's scanner row: last, levels (PDH, PDL, PMH, PML, VWAP), what "
          "has broken, the setup and entry, the score and its parts, options context (IV "
          "against RV, the expected move, the suggested contract), earnings date, recent "
          "headlines and filings. Use for any question about a stock or index ETF the "
          "scanner tracks.",
          _params({"sym": {**_STR, "description": "Ticker, e.g. AMZN or SPY"}}, ["sym"])),
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
]


def spec_for(desk: str | None) -> list[dict[str, Any]]:
    """The tools for one desk ("futures" or "stocks"), or all of them."""
    if desk not in ("futures", "stocks"):
        return list(SPEC)
    return [t for t in SPEC if DESKS.get(t["name"], "both") in (desk, "both")]


def _size(v: Any) -> int:
    return len(json.dumps(v, default=str))


def _cap(v: Any) -> Any:
    """Cut an answer to MAX_CHARS of JSON: lists from the end first, then whole
    sections from the end, NAMED in `dropped` so the model knows what it did
    not get and can ask for it another way. Never a cut mid-JSON — the first
    cut did that to a digest and handed the model half a brace."""
    if _size(v) <= MAX_CHARS:
        return v
    if isinstance(v, list):
        while len(v) > 1 and _size(v) > MAX_CHARS:
            v = v[: max(1, len(v) * 2 // 3)]
        return v
    if isinstance(v, dict):
        out = dict(v)
        for k, item in out.items():
            if isinstance(item, list) and _size(out) > MAX_CHARS:
                out[k] = _cap(item)
        dropped: list[str] = []
        while len(out) > 1 and _size({**out, "dropped": dropped}) > MAX_CHARS:
            k = next(reversed(out))
            dropped.insert(0, k)
            out.pop(k)
        if dropped:
            out["dropped"] = dropped
        if _size(out) > MAX_CHARS:
            return {"truncated": True, "text": json.dumps(out, default=str)[:MAX_CHARS]}
        return out
    return {"truncated": True, "text": json.dumps(v, default=str)[:MAX_CHARS]}


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
    }


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
    return _cap(out)


def _stocks_digest(scan: dict[str, Any], snap: dict[str, Any]) -> dict[str, Any]:
    """The plan's digest with the names as the scanner table's compact rows."""
    facts = stockplan.build_facts(scan, snap, top=stockplan.TOP_MAX)
    full = stockplan.build_digest(facts)
    table = ask.scanner_table(scan) or {}
    # The tape and the names first; the strategy text last, since the prompt
    # already carries the strategy and the cap drops from the end.
    first = ["regime", "tape_count", "breadth", "fuel", "prints"]
    out: dict[str, Any] = {k: full[k] for k in first if k in full}
    out["names"] = (table.get("names") or [])[:DIGEST_NAMES]
    for k, v in full.items():
        if k not in out and k not in ("names", "strategy"):
            out[k] = v
    if "strategy" in full:
        out["strategy"] = full["strategy"]
    return _cap(out)


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
) -> dict[str, Any]:
    """Answer one tool call. Always a dict; an unknown name or a name the
    scanner does not track comes back as `{"error": ...}` the model can read,
    never an exception the route has to catch."""
    a = args if isinstance(args, dict) else {}
    now = now or report._now_et(snap)
    try:
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
