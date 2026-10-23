"""The driver board's ceiling on the futures brief: a call's conviction may not
exceed the book's max, nor 3 against the board's lean (report.sanitize_brief)."""

from __future__ import annotations

from typing import Any

import pytest

from newsterminal import report


def _obj(bias: str, conviction: int) -> dict[str, Any]:
    return {
        "thesis": "One idea.",
        "calls": [{"book": "NQ", "open_bias": bias, "conviction": conviction,
                   "rest_of_day": "Lean", "rest_of_day_bias": bias, "wrong_if": "x", "why": ["a"]}],
        "reads": [{"book": "NQ", "regime": "r", "chain": ["a"], "at_open": "o", "wrong_if": "w",
                   "rest_of_day": "d", "flips": [], "drivers": []}],
    }


def _facts(max_conviction: int, lean: str | None) -> dict[str, Any]:
    return {"books": ["NQ"], "headlines": [], "snapshot": [], "catalysts": [],
            "rotation": {"ratios": []},
            "drivers": {"NQ": {"bias": lean, "max_conviction": max_conviction}}}


@pytest.mark.parametrize(
    ("bias", "asked", "cap", "lean", "want"),
    [("bearish", 5, 4, "short", 4),      # the board's ceiling
     ("bullish", 5, 4, "short", 3),      # against the board's lean: 3 at most
     ("bullish", 2, 4, "short", 2),      # never raised
     ("neutral", 5, 4, "short", 4),      # neutral is not against
     ("bearish", 5, 5, None, 5)],        # no lean, no cap below the board's max
)
def test_conviction_is_capped_by_the_board(bias: str, asked: int, cap: int, lean: str | None,
                                           want: int) -> None:
    out = report.sanitize_brief(_obj(bias, asked), _facts(cap, lean))
    assert out is not None
    assert out["calls"][0]["conviction"] == want


def test_no_board_no_cap() -> None:
    facts = _facts(2, "short")
    del facts["drivers"]
    out = report.sanitize_brief(_obj("bullish", 5), facts)
    assert out is not None and out["calls"][0]["conviction"] == 5
