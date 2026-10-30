"""
What Hermes, the terminal's assistant, is shown with every question.

THE BRIEFS' DIGESTS, NOT A THIRD ONE (owner, 2026-10-14: "a chatbot that uses
our llm model that we can ask it to explain anything"). The futures Analysis
and the stocks Game plan already compress the collector's state into the facts
a desk would read out loud — `report.build_digest` and `stockplan.build_digest`
— with every figure formatted the way the page prints it. The assistant is
handed the one for the desk the reader has open, so a level it quotes is the
level beside it, and "what is this?" is answered from the same numbers the
note would be written from. About ten thousand tokens either way, measured.

WHAT TRAVELS BESIDE IT. On the Scanner, the selected name's whole row — its
levels, setup, signals, score parts, options and catalysts — because the
question there is usually about the row under the cursor, and the plan's
digest only carries its top names. On Analysis and Game plan, the latest note
itself, so "what does this paragraph mean?" has the paragraph.

PURE BAR THE TWO DIGEST CALLS, which are pure themselves; nothing here fetches.
A digest that cannot be built is a stated gap in the context, never an error
that costs the reader the answer.
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

from . import report, stockplan

#: Macro and Structure both read the futures digest — the brief's facts carry
#: the calendar, earnings and rotation as well as the ranges and the gamma.
FUTURES_TABS = frozenset({"terminal", "structure", "report"})
#: "tape" is Structure's stocks & options half (2026-10-30): the index's
#: levels and the tape count, read from the stocks digest.
STOCKS_TABS = frozenset({"market", "tape", "scanner", "plan"})
#: The Hermes tab — the assistant on a page of its own, reading BOTH desks
#: (owner, 2026-10-30: "complete access to the hermesx context of everything").
HERMES_TAB = "hermes"
TABS = FUTURES_TABS | STOCKS_TABS | {"settings", HERMES_TAB}

#: Headlines and filings kept on the selected row — enough to name the
#: catalyst, not a reading list.
ROW_NEWS = 5
ROW_FILINGS = 3


def selected_row(scan: dict[str, Any] | None, sym: str | None) -> dict[str, Any] | None:
    """The scanner row for `sym`, its headline and filing lists cut short. Pure."""
    if not scan or not sym:
        return None
    want = sym.strip().upper()
    for r in scan.get("rows") or []:
        if isinstance(r, dict) and r.get("sym") == want:
            out = dict(r)
            out["news"] = [
                {k: n.get(k) for k in ("title", "publisher", "utc")}
                for n in (r.get("news") or [])[:ROW_NEWS] if isinstance(n, dict)
            ]
            out["filings"] = list((r.get("filings") or [])[:ROW_FILINGS])
            return out
    return None


def note_age_hours(rec: dict[str, Any], now: datetime) -> float | None:
    """Hours since a stored note was written, one decimal; None if undated. Pure."""
    try:
        made = datetime.fromisoformat(str(rec.get("created_utc")))
    except ValueError:
        return None
    if made.tzinfo is None:
        made = made.replace(tzinfo=UTC)
    return round(max(0.0, (now - made).total_seconds() / 3600.0), 1)


def latest_note(rec: dict[str, Any] | None, now: datetime | None = None) -> dict[str, Any] | None:
    """A stored report or plan, cut to what the reader is reading: when it was
    written and how long ago, by which model, and the note. None when there is
    no good one. Pure but for the default clock.

    THE AGE TRAVELS WITH IT (audit, 2026-10-14): the Analysis tab had opened on
    a twenty-day-old gold brief, and an assistant quoting that note's levels as
    if current would repeat the page's mistake in its own voice."""
    if not isinstance(rec, dict) or not rec.get("ok"):
        return None
    note = rec.get("report") if rec.get("report") is not None else rec.get("plan")
    if note is None:
        return None
    return {
        "written_et": rec.get("et_label") or rec.get("created_et"),
        "age_hours": note_age_hours(rec, now or datetime.now(UTC)),
        "model": rec.get("model"),
        "session": rec.get("session_label") or rec.get("session"),
        "book": rec.get("asset_label") or rec.get("asset"),
        "note": note,
    }


def context(tab: str, snap: dict[str, Any], scan: dict[str, Any] | None = None,
            sym: str | None = None, note: dict[str, Any] | None = None) -> dict[str, Any]:
    """Everything the assistant reads for a question asked on `tab`. Pure."""
    out: dict[str, Any] = {"tab": tab, "desk": None, "digest": None, "selected": None,
                           "note": latest_note(note), "gaps": []}
    try:
        if tab in FUTURES_TABS:
            out["desk"] = "futures"
            sess = report.resolve_session(snap.get("clock") or {}, "auto")
            out["digest"] = report.build_digest(snap, sess, "all")
        elif tab in STOCKS_TABS and scan is not None:
            out["desk"] = "stocks"
            # The row first: it needs nothing the digest does, and must not be
            # lost with it.
            out["selected"] = selected_row(scan, sym)
            facts = stockplan.build_facts(scan, snap, top=stockplan.TOP_MAX)
            out["digest"] = stockplan.build_digest(facts)
    except (ValueError, TypeError, KeyError, AttributeError, ZeroDivisionError) as e:
        out["gaps"].append(f"The live digest could not be built ({e.__class__.__name__}: {e}).")
    return out


# --------------------------------------------------------------------------
# The Hermes tab — the whole terminal, both desks at once.
# --------------------------------------------------------------------------
#
# The side panel answers beside ONE tab and is handed that desk's digest, which
# is what a question asked beside a panel is about. The tab is a different
# ask (owner, 2026-10-30: a chat "in its own tab … with complete access to the
# hermesx context of everything"): there is no panel beside it, so the
# question may be about anything on either desk, and the answer has to be
# written from both. So it gets both digests, both latest notes, and — since
# the stocks digest carries only its top names in full — every scanner name
# in one compact row, enough to rank, place and read it without its chart.
# About twenty-five thousand tokens, measured; the free model's window is
# forty times that.

#: Flags kept per scanner name in the compact table — the catalyst and the
#: state, not the whole list.
TABLE_FLAGS = 4


def _dict(v: Any) -> dict[str, Any]:
    """`v` when it is a dict, else an empty one — a row's optional blocks, typed."""
    return v if isinstance(v, dict) else {}


def scanner_table(scan: dict[str, Any] | None) -> dict[str, Any] | None:
    """Every scanner name that has data, one compact row each, best score first.
    Pure. None when there is no scanner payload at all.

    The figures are the row's own, unrounded: the chat's numeral check accepts
    a figure quoted to two places (prompt.ts twoPlaces), so 70.8854 may be
    written 70.89 and still verify, while a figure not here cannot."""
    if not isinstance(scan, dict):
        return None
    names: list[dict[str, Any]] = []
    for r in scan.get("rows") or []:
        if not isinstance(r, dict) or not r.get("ok"):
            continue
        score, setup, levels = _dict(r.get("score")), _dict(r.get("setup")), _dict(r.get("levels"))
        earn, opt = _dict(r.get("earnings")), _dict(r.get("options"))
        frame, broken, rs = _dict(r.get("frame_read")), _dict(r.get("broken")), _dict(r.get("rs"))
        liq = _dict(opt.get("liquidity"))
        names.append({
            "sym": r.get("sym"),
            "name": r.get("name"),
            "sector": r.get("sector"),
            "last": r.get("last"),
            "chg_pct": r.get("chg_pct"),
            "ext_pct": r.get("ext_pct"),
            "rvol": r.get("rvol"),
            "rs_vs_spy_atr": rs.get("SPY"),
            "trend": r.get("trend"),
            "score": score.get("total"),
            "side": score.get("side"),
            "setup": setup.get("note"),
            "setup_state": setup.get("state"),
            "levels": {k: levels.get(k) for k in ("pdh", "pdl", "pmh", "pml", "vwap")},
            "broken": [k.upper() for k, v in broken.items() if v],
            "daily_frame": frame.get("text"),
            "earnings": (f"{earn.get('date')} {earn.get('when') or ''}".strip()
                         if earn.get("date") else None),
            "options": ({
                "iv30": opt.get("iv30"), "rv20": opt.get("rv20"),
                "premium": opt.get("premium"), "liquidity": liq.get("grade"),
                "earnings_in": opt.get("earnings_in"),
            } if opt.get("ok") else None),
            "flags": [f["text"] for f in (r.get("flags") or [])
                      if isinstance(f, dict) and f.get("text")][:TABLE_FLAGS],
        })
    names.sort(key=lambda n: -int(n["score"] or 0))
    return {
        "as_of_utc": scan.get("built_utc"),
        "session": scan.get("session"),
        "trading_day": scan.get("trading_day"),
        "regime": scan.get("regime"),
        "names": names,
    }


def whole_context(
    snap: dict[str, Any],
    scan: dict[str, Any] | None = None,
    sym: str | None = None,
    brief: dict[str, Any] | None = None,
    plan: dict[str, Any] | None = None,
    desk: str | None = None,
) -> dict[str, Any]:
    """Everything the assistant reads on its own tab: both desks' digests, the
    scanner table, the selected name, the latest brief and the latest game
    plan. `desk` is the one the reader came from — the tab belongs to both.
    Pure. A digest that cannot be built is a gap, never an error."""
    out: dict[str, Any] = {
        "tab": HERMES_TAB, "desk": desk if desk in ("futures", "stocks") else None,
        # The side panel's fields, empty: one reader on the web side handles both shapes.
        "digest": None, "selected": None, "note": None, "gaps": [],
        "futures": None, "stocks": None, "scanner": None,
        "brief": latest_note(brief), "plan": latest_note(plan),
    }
    try:
        sess = report.resolve_session(snap.get("clock") or {}, "auto")
        out["futures"] = report.build_digest(snap, sess, "all")
    except (ValueError, TypeError, KeyError, AttributeError, ZeroDivisionError) as e:
        out["gaps"].append(f"The futures digest could not be built ({e.__class__.__name__}: {e}).")
    if scan is None:
        out["gaps"].append("The scanner has not built yet, so there is no stocks desk data.")
        return out
    out["selected"] = selected_row(scan, sym)
    out["scanner"] = scanner_table(scan)
    try:
        facts = stockplan.build_facts(scan, snap, top=stockplan.TOP_MAX)
        out["stocks"] = stockplan.build_digest(facts)
    except (ValueError, TypeError, KeyError, AttributeError, ZeroDivisionError) as e:
        out["gaps"].append(f"The stocks digest could not be built ({e.__class__.__name__}: {e}).")
    return out


# --------------------------------------------------------------------------
# The slim context — the Hermes tab's picture of the desk, with tools behind it.
# --------------------------------------------------------------------------
#
# A FEW THOUSAND TOKENS, NOT FORTY-SEVEN (owner, 2026-10-30: "is there a
# method to also be more efficient and save tokens?"). The whole-terminal
# context above is still what the dry run and the no-tools fallback use; the
# tab now opens on this instead — enough to answer a quick question outright
# and to know what to ask for (tools.py) — and fetches the rest per question.

#: Scanner names the picture carries, best score first.
SLIM_NAMES = 8
#: Headlines the picture carries, HIGH impact first, newest first.
SLIM_HEADLINES = 6
#: Heavyweights the picture carries per index.
SLIM_HEAVY = 6

_STRIP = ("NQ", "ES", "GC", "SPY", "QQQ", "IWM", "VIX", "VXN", "US10Y", "DXY", "WTI", "BTC")


def _two(v: Any) -> Any:
    return round(v, 2) if isinstance(v, float) else v


def _q(snap: dict[str, Any], key: str) -> dict[str, Any] | None:
    quotes = snap.get("quotes") or []
    return next((q for q in quotes if isinstance(q, dict) and q.get("key") == key), None)


def _print_line(p: dict[str, Any] | None) -> str | None:
    if not p or not p.get("eps_actual"):
        return None
    return f"{p['eps_actual']} vs {p['eps_forecast']}"


def _earn_line(r: dict[str, Any]) -> str:
    line = f"{r.get('symbol')} {r.get('date')} {r.get('when') or ''}".strip()
    if r.get("eps_actual"):
        line += f" {r.get('eps_actual')} vs {r.get('eps_forecast')}"
    return line


def _material(snap: dict[str, Any]) -> list[dict[str, Any]]:
    """HIGH then medium, newest first within each."""
    items = [h for h in snap.get("wire") or []
             if isinstance(h, dict) and h.get("impact") in ("high", "medium")]
    rank = {"high": 0, "medium": 1}
    return sorted(items, key=lambda h: (rank.get(str(h.get("impact")), 2), -(h.get("ts") or 0)))


def slim_context(
    snap: dict[str, Any],
    scan: dict[str, Any] | None = None,
    brief: dict[str, Any] | None = None,
    plan: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """The desk in a glance, for a model that can ask for more. Pure but for the clock."""
    from . import events, report  # local: report imports this module's siblings

    now = report._now_et(snap)
    clock = snap.get("clock") or {}
    boards = ((snap.get("drivers") or {}).get("books") or {})
    out: dict[str, Any] = {
        "as_of_et": clock.get("et"),
        "phase": (clock.get("phase") or {}).get("label"),
        "boxes_open": [b.get("label") for b in clock.get("boxes") or [] if b.get("open")],
        # The change to two places: the model quoted -2.00510790880184% once,
        # and the numeral check accepts a figure quoted to two places anyway.
        "strip": [
            {"key": k, "last": q.get("last"), "pct": _two(q.get("pct")), "feed": q.get("feed")}
            for k in _STRIP if (q := _q(snap, k))
        ],
        "driver_board": {
            k: {f: b.get(f) for f in ("bias", "grade", "agree", "total", "conflict",
                                      "event_risk", "max_conviction", "treatment")}
            for k, b in boards.items() if isinstance(b, dict)
        },
        "event_risk": [
            {"id": e["id"], "time_et": e.get("time_et"), "title": e.get("title"),
             "channels": e.get("channels")}
            for e in events.event_risk(snap, now)
        ],
        "heavyweights_nq": [
            {"symbol": r["symbol"], "move_pct": r.get("move_pct"),
             "index_points": r.get("index_points"), "reported": _print_line(r.get("reported"))}
            for r in events.heavyweights(snap, "NQ", now)[:SLIM_HEAVY]
        ],
        "earnings": {
            k: [_earn_line(r) for r in v[:SLIM_HEAVY]]
            for k, v in report.digest_earnings(snap.get("earnings") or [], now).items()
        },
        "headlines": [
            {"impact": h.get("impact"), "desk": h.get("category"), "title": h.get("title")}
            for h in _material(snap)[:SLIM_HEADLINES]
        ],
        "scanner": None,
        "notes": {"brief": None, "plan": None},
        "gaps": [],
    }
    if scan is not None:
        rows = [r for r in scan.get("rows") or [] if isinstance(r, dict) and r.get("ok")]
        rows.sort(key=lambda r: -int(((r.get("score") or {}).get("total")) or 0))
        reg = scan.get("regime") or {}
        conv = reg.get("conviction") or {}
        vix = reg.get("vix") or {}
        out["scanner"] = {
            "session": scan.get("session"),
            "regime": {"vix": vix.get("last"), "band": reg.get("band"),
                       "shape": vix.get("shape"), "spy_em_pct": reg.get("spy_em_pct")},
            "tape": {f: conv.get(f) for f in ("bias", "grade", "agree", "total", "max_conviction")},
            "top": [
                {"sym": r.get("sym"), "score": (r.get("score") or {}).get("total"),
                 "side": (r.get("score") or {}).get("side"),
                 "setup": (r.get("setup") or {}).get("note")}
                for r in rows[:SLIM_NAMES]
            ],
            "watchlist": [r.get("sym") for r in rows],
        }
    else:
        out["gaps"].append("The scanner has not built yet, so there is no stocks desk data.")
    for key, rec in (("brief", brief), ("plan", plan)):
        got = latest_note(rec)
        if got:
            note = got.get("note") or {}
            lead = note.get("thesis") if isinstance(note, dict) else None
            if lead is None and isinstance(note, dict):
                lead = note.get("lead") or note.get("headline")
            fields = ("written_et", "age_hours", "session", "book")
            out["notes"][key] = {k: got.get(k) for k in fields}
            out["notes"][key]["lead"] = lead
    return out
