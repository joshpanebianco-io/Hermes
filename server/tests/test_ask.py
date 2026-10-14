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
    assert fut["digest"] is not None or fut["gaps"]  # built, or the gap is said
    stocks = ask.context("scanner", {}, _scan(), "MSFT")
    assert stocks["desk"] == "stocks"
    # The row survives even when a thin payload cannot make a digest.
    assert stocks["selected"] is not None and stocks["selected"]["sym"] == "MSFT"
    # Settings carries no live data, and says nothing is wrong.
    s = ask.context("settings", {})
    assert (s["desk"], s["digest"], s["gaps"]) == (None, None, [])
