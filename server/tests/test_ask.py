"""What Hermes is shown (ask.py) — the desk's digest, the selected row, the latest note."""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

from newsterminal import ask


def _scan() -> dict[str, Any]:
    news = [{"title": f"h{i}", "publisher": "P", "utc": "2026-10-13T12:00:00Z", "url": "u"}
            for i in range(9)]
    msft = {"sym": "MSFT", "last": 541.15, "news": news, "filings": [{"form": "8-K"}] * 5}
    return {"rows": [msft, {"sym": "AAPL", "last": 340.35, "news": [], "filings": []}]}


def test_the_selected_row_is_whole_but_its_reading_list_is_short() -> None:
    row = ask.selected_row(_scan(), "msft")
    assert row is not None and row["last"] == 541.15
    assert len(row["news"]) == ask.ROW_NEWS and set(row["news"][0]) == {"title", "publisher", "utc"}
    assert len(row["filings"]) == ask.ROW_FILINGS
    assert ask.selected_row(_scan(), "ZZZZ") is None
    assert ask.selected_row(None, "MSFT") is None and ask.selected_row(_scan(), None) is None


def test_latest_note_reads_a_brief_or_a_plan_and_skips_a_failure() -> None:
    brief = {"ok": True, "et_label": "Tue 13 Oct, 08:10 ET", "model": "m",
             "created_utc": "2026-10-13T12:10:00+00:00",
             "session_label": "New York", "asset_label": "All books",
             "report": {"thesis": "t"}}
    now = datetime(2026, 10, 14, 5, 16, tzinfo=UTC)
    assert ask.latest_note(brief, now) == {"written_et": "Tue 13 Oct, 08:10 ET", "age_hours": 17.1,
                                           "model": "m", "session": "New York",
                                           "book": "All books", "note": {"thesis": "t"}}
    plan = {"ok": True, "et_label": "x", "model": "m", "plan": {"names": []}}
    got = ask.latest_note(plan) or {}
    # An undated note still reads; its age is unknown, not zero.
    assert got.get("note") == {"names": []} and got.get("age_hours") is None
    assert ask.latest_note({"ok": False, "report": {"thesis": "t"}}) is None
    assert ask.latest_note(None) is None


def test_context_names_the_desk_and_never_raises() -> None:
    fut = ask.context("terminal", {})
    assert fut["desk"] == "futures" and fut["selected"] is None
    # Structure is the same desk's digest under another tab (2026-10-30), and
    # its stocks half ("tape") reads the stocks desk's.
    assert ask.context("structure", {})["desk"] == "futures"
    assert ask.context("tape", {}, _scan())["desk"] == "stocks"
    assert fut["digest"] is not None or fut["gaps"]  # built, or the gap is said
    stocks = ask.context("scanner", {}, _scan(), "MSFT")
    assert stocks["desk"] == "stocks"
    # The row survives even when a thin payload cannot make a digest.
    assert stocks["selected"] is not None and stocks["selected"]["sym"] == "MSFT"
    # Settings carries no live data, and says nothing is wrong.
    s = ask.context("settings", {})
    assert (s["desk"], s["digest"], s["gaps"]) == (None, None, [])


# ---------------------------------------------------------------- the Hermes tab

def _row(sym: str, total: int, side: str | None, ok: bool = True) -> dict[str, Any]:
    return {
        "sym": sym, "name": sym, "ok": ok, "sector": "XLK", "last": 70.8854, "chg_pct": -3.622,
        "ext_pct": -23.009, "rvol": None, "rs": {"SPY": -3.39, "QQQ": -3.04}, "trend": 0,
        "score": {"total": total, "side": side, "parts": [{"key": "rs", "pts": 25}]},
        "setup": {"side": side, "state": "forming", "level": "PDL",
                  "note": "Holding below PDL 90.84 — plan: the retest of it after the open"},
        "levels": {"pdh": 93.5, "pdl": 90.838, "pdc": 92.07, "pmh": None, "pml": None,
                   "vwap": None, "ema8": 71.14},
        "broken": {"pdh": False, "pdl": True, "pmh": False, "pml": False},
        "frame_read": {"text": "Below the 20, 50 and 200-day"},
        "earnings": {"date": "2026-10-29", "when": "after", "days": -1},
        "options": {"ok": True, "iv30": 61.339, "rv20": 53.728, "premium": "fair",
                    "liquidity": {"grade": "poor"}, "earnings_in": None,
                    "contracts": [{"strike": 81.0}] * 4},
        "flags": [{"kind": "earnings", "text": f"flag {i}"} for i in range(6)],
        "news": [{"title": "h"}] * 8, "filings": [{"form": "8-K"}] * 5, "signals": [1, 2, 3],
    }


def test_the_scanner_table_is_one_compact_row_per_live_name_best_first() -> None:
    scan = {"built_utc": "2026-10-30T01:00:00+00:00", "session": "closed",
            "trading_day": "2026-10-30", "regime": {"band": "normal"},
            "rows": [_row("INTC", 86, "short"), _row("AAPL", 91, "long"),
                     _row("DEAD", 99, "long", ok=False)]}
    t = ask.scanner_table(scan)
    assert t is not None and [n["sym"] for n in t["names"]] == ["AAPL", "INTC"]
    intc = t["names"][1]
    assert intc["score"] == 86 and intc["side"] == "short" and intc["broken"] == ["PDL"]
    assert intc["levels"] == {"pdh": 93.5, "pdl": 90.838, "pmh": None, "pml": None, "vwap": None}
    assert intc["earnings"] == "2026-10-29 after"
    assert intc["options"] == {"iv30": 61.339, "rv20": 53.728, "premium": "fair",
                               "liquidity": "poor", "earnings_in": None}
    # The chart, the headlines, the filings and the signal list stay behind.
    assert not {"news", "filings", "signals", "contracts", "parts"} & set(intc)
    assert len(intc["flags"]) == ask.TABLE_FLAGS
    assert t["regime"] == {"band": "normal"} and t["trading_day"] == "2026-10-30"
    assert ask.scanner_table(None) is None


def test_the_whole_context_reads_both_desks_and_both_notes() -> None:
    brief = {"ok": True, "et_label": "b", "model": "m", "report": {"thesis": "t"}}
    plan = {"ok": True, "et_label": "p", "model": "m", "plan": {"lead": "l"}}
    scan = {"rows": [_row("INTC", 86, "short")]}
    out = ask.whole_context({}, scan, "INTC", brief, plan, "stocks")
    assert out["tab"] == "hermes" and out["desk"] == "stocks"
    assert (out["brief"] or {}).get("note") == {"thesis": "t"}
    assert (out["plan"] or {}).get("note") == {"lead": "l"}
    assert out["selected"] is not None and out["selected"]["sym"] == "INTC"
    assert out["scanner"] is not None and out["scanner"]["names"][0]["sym"] == "INTC"
    # Each desk's digest is built, or its absence is said — never raised.
    assert out["futures"] is not None or any("futures" in g for g in out["gaps"])
    assert out["stocks"] is not None or any("stocks" in g for g in out["gaps"])
    # The side panel's fields ride along empty, so one reader handles both shapes.
    assert (out["digest"], out["note"]) == (None, None)


def test_the_whole_context_says_when_the_scanner_is_not_there_yet() -> None:
    out = ask.whole_context({}, None, None, None, None, "nowhere")
    assert out["desk"] is None and out["scanner"] is None and out["stocks"] is None
    assert any("scanner" in g for g in out["gaps"])
    assert out["brief"] is None and out["plan"] is None
