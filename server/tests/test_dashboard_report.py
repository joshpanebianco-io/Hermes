"""The Dashboard's Market report card and the 09:00 write (2026-11-16).

The owner, of the Dashboard: "the pre market card is a bit redundant or could be merged
into the today game plan one, and then also market overview", then "do waht you recommend
best". The overview card read a note written at 22:23 ET on a Saturday about the Monday
after, still arguing from the ten-minute 200 EMA. Its place is the Stocks report's, and the
09:00 ET write is that report's.

What is held here: the card is the newest Stocks report's (a futures report is not it), with
its summary, the market's bias, the three calls and three risks; a poll reads one file at
most; the 09:00 write is due once on a trading day between 09:00 and the bell, not when a
Stocks report has been written since 09:00, and twice at most, five minutes apart.
"""

from __future__ import annotations

import json
import os
from datetime import datetime
from typing import Any
from zoneinfo import ZoneInfo

import pytest

from newsterminal import report

ET = ZoneInfo("America/New_York")


def rep(rid: str, asset: str, thesis: str = "Tape leans short into the open.") -> dict[str, Any]:
    return {
        "id": rid, "ok": True, "asset": asset, "label": "auto", "et_label": "Mon 16 Nov, 09:00 ET",
        "created_et": "2026-11-16T09:00:05-05:00", "session_underway": False, "format": "brief",
        "report": {"thesis": thesis, "risks": ["a", "b", "c", "d"],
                   "calls": [
                       {"book": "SPY", "open_bias": "leaning bearish", "conviction": 3,
                        "plan": "p"},
                       {"book": "QQQ", "open_bias": "bearish", "conviction": 4, "plan": "p"},
                       {"book": "IWM", "open_bias": "neutral", "conviction": 1, "plan": "p"}]},
        "facts": {"market": {"bias": "short", "score": -52, "basis": "whole", "grade": "strong",
                             "votes": []}},
    }


def test_the_card_is_the_summary_the_markets_bias_the_three_calls_and_three_risks() -> None:
    c = report.card_of(rep("20261116-090005", "etfs"))
    assert c is not None
    assert c["thesis"] == "Tape leans short into the open." and c["auto"] is True
    assert c["market"] == {"bias": "short", "score": -52, "basis": "whole", "grade": "strong"}
    assert [x["book"] for x in c["calls"]] == ["SPY", "QQQ", "IWM"]
    assert c["calls"][1] == {"book": "QQQ", "open_bias": "bearish", "conviction": 4}
    assert c["risks"] == ["a", "b", "c"]
    # A futures report, or a failed one, is not the card.
    assert report.card_of(rep("x", "NQ")) is None
    assert report.card_of({**rep("x", "etfs"), "ok": False}) is None


def test_the_card_is_the_newest_stocks_reports_and_a_futures_report_does_not_hide_it(
        tmp_path: Any, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(report, "REPORTS_DIR", str(tmp_path))
    monkeypatch.setattr(report, "_ASSET_OF", {})
    monkeypatch.setattr(report, "_CARD", {"key": None, "card": None})
    files = [("20261115-080000", "etfs", "old"), ("20261116-063505", "etfs", "new"),
             ("20261116-070000", "NQ", "futures")]
    for rid, asset, thesis in files:
        (tmp_path / f"{rid}.json").write_text(json.dumps(rep(rid, asset, thesis)), encoding="utf-8")
    assert report.latest_card()["thesis"] == "new"
    # Asked again, the futures file is known by its subject and not opened.
    calls: list[str] = []
    real = report.load
    monkeypatch.setattr(report, "load", lambda i: (calls.append(i), real(i))[1])
    assert report.latest_card()["thesis"] == "new" and calls == []
    assert report.latest_card("CL") is None
    os.remove(tmp_path / "20261116-063505.json")
    monkeypatch.setattr(report, "load", real)
    assert report.latest_card()["thesis"] == "old"


def at(h: int, m: int, day: int = 16) -> datetime:
    return datetime(2026, 11, day, h, m, tzinfo=ET)


def test_the_0900_write_is_the_stocks_reports_once_a_trading_day() -> None:
    assert report.auto_due(at(9, 0), [], [])
    assert report.auto_due(at(9, 29), [], [])
    assert not report.auto_due(at(8, 59), [], []) and not report.auto_due(at(9, 30), [], [])
    assert not report.auto_due(at(9, 5, 14), [], [])                     # a Saturday
    # A Stocks report written since 09:00 is the morning's; one from 06:35 is not; a
    # futures one never.
    since = [{"asset": "etfs", "created_et": "2026-11-16T09:01:00-05:00"}]
    early = [{"asset": "etfs", "created_et": "2026-11-16T06:35:05-05:00"},
             {"asset": "NQ", "created_et": "2026-11-16T09:02:00-05:00"}]
    assert not report.auto_due(at(9, 10), since, [])
    assert report.auto_due(at(9, 10), early, [])
    # Two tries at most, five minutes apart.
    assert not report.auto_due(at(9, 3), [], [at(9, 0)])
    assert report.auto_due(at(9, 6), [], [at(9, 0)])
    assert not report.auto_due(at(9, 20), [], [at(9, 0), at(9, 6)])
