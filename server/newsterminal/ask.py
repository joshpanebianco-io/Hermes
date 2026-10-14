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

FUTURES_TABS = frozenset({"terminal", "report"})
STOCKS_TABS = frozenset({"market", "scanner", "plan"})
TABS = FUTURES_TABS | STOCKS_TABS | {"settings"}

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
