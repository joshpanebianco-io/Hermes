"""
Heavyweights and event risk (events.py), and how they vote (drivers.py) and
reach the brief (report.py) — owner, 2026-10-30: the bias was blind to a
megacap's print and to a strike on Saudi oil.
"""

from __future__ import annotations

from datetime import datetime
from typing import Any
from zoneinfo import ZoneInfo

from newsterminal import drivers, events, report

ET = ZoneInfo("America/New_York")


def at(y: int, mo: int, d: int, h: int, mi: int = 0) -> datetime:
    return datetime(y, mo, d, h, mi, tzinfo=ET)


def _wire(title: str, when: datetime, category: str = "corp", impact: str = "high",
          publisher: str = "WSJ", summary: str = "") -> dict[str, Any]:
    return {"title": title, "category": category, "impact": impact, "publisher": publisher,
            "ts": when.timestamp(), "utc": when.isoformat(), "summary": summary, "also": []}


NOW = at(2026, 10, 29, 21, 0)  # Thursday evening, after Alphabet's print


def _snap() -> dict[str, Any]:
    return {
        "constituents": {"indices": {"NQ": {"index": "NDX", "members": [
            {"symbol": "NVDA", "weight": 8.04, "pct": -0.8, "contribution": -0.0642},
            {"symbol": "AAPL", "weight": 7.77, "pct": 1.48, "contribution": 0.1148},
            {"symbol": "MSFT", "weight": 6.1, "pct": -0.16, "contribution": -0.0098},
            {"symbol": "GOOGL", "weight": 2.95, "pct": -12.64, "contribution": -0.3729},
            # Six middling weights, so the top ten by weight stops above the two below.
            *[{"symbol": sym, "weight": w, "pct": 0.1, "contribution": 0.001}
              for sym, w in (("ADBE", 1.2), ("PEP", 1.0), ("CSCO", 0.9), ("TMUS", 0.9),
                             ("QCOM", 0.8), ("TXN", 0.7))],
            {"symbol": "FTNT", "weight": 0.55, "pct": -20.09, "contribution": -0.1105},
            {"symbol": "ORLY", "weight": 0.3, "pct": 0.2, "contribution": 0.0006},
        ]}}},
        "earnings": [
            {"symbol": "GOOGL", "date": "2026-10-28", "when": "after",
             "eps_actual": "$2.12", "eps_forecast": "$2.94", "surprise_pct": -27.89},
            {"symbol": "MSFT", "date": "2026-10-28", "when": "after",
             "eps_actual": "$4.89", "eps_forecast": "$4.71", "surprise_pct": 3.82},
            # Last week's print is not "just reported".
            {"symbol": "NVDA", "date": "2026-10-20", "when": "after",
             "eps_actual": "$1.00", "eps_forecast": "$0.90", "surprise_pct": 11.1},
            # Tonight's, no actual yet.
            {"symbol": "AAPL", "date": "2026-10-29", "when": "after",
             "eps_actual": None, "eps_forecast": "$1.98", "surprise_pct": None},
        ],
        "wire": [
            _wire("Google erases a record $500 billion as AI eats into sales",
                  at(2026, 10, 29, 20, 50), "corp"),
            _wire("Alphabet revenue miss revives AI capex jitters",
                  at(2026, 10, 29, 17, 0), "markets", "medium"),
            _wire("Houthi forces claim six attacks on Saudi airports, oil facilities",
                  at(2026, 10, 29, 18, 30), "geo"),
            _wire("Houthis strike Saudi oil facilities, Riyadh says",
                  at(2026, 10, 29, 18, 45), "geo", publisher="Reuters"),
            _wire("Senator briefed on Iran war plans warns of escalation",
                  at(2026, 10, 29, 19, 10), "policy"),
            # Before the close, and below HIGH: neither counts.
            _wire("Japan to scale back fuel subsidies as Iran war costs mount",
                  at(2026, 10, 29, 10, 0), "geo"),
            _wire("Nvidia chief seen as target of Chinese spy plot",
                  at(2026, 10, 29, 20, 0), "geo", "medium"),
        ],
    }


def test_heavyweights_join_weight_print_and_headline() -> None:
    rows = events.heavyweights(_snap(), "NQ", NOW)
    by = {r["symbol"]: r for r in rows}
    # The largest weights, heaviest first, plus the small name whose move alone is a story.
    assert [r["symbol"] for r in rows][:3] == ["NVDA", "AAPL", "MSFT"]
    assert "FTNT" in by and "ORLY" not in by
    assert rows[0]["id"] == "w1"
    g = by["GOOGL"]
    assert g["reported"] == {"date": "2026-10-28", "when": "after", "eps_actual": "$2.12",
                             "eps_forecast": "$2.94", "surprise_pct": -27.89}
    # The HIGH headline wins over the newer medium one.
    assert g["headline"]["title"].startswith("Google erases")
    assert by["NVDA"]["reported"] is None and by["AAPL"]["reported"] is None
    assert events.heavyweights(_snap(), "GC", NOW) == []


def test_net_print_points_is_the_reported_names_only() -> None:
    rows = events.heavyweights(_snap(), "NQ", NOW)
    net, who = events.net_print_points(rows)
    assert who == ["MSFT", "GOOGL"] and net == -0.383


def test_event_risk_is_the_high_wire_since_the_close_grouped_by_story() -> None:
    ev = events.event_risk(_snap(), NOW)
    titles = [e["title"] for e in ev]
    # Newest first, the two Houthi headlines folded into one, nothing from
    # before 16:00 and nothing below HIGH.
    assert titles == ["Senator briefed on Iran war plans warns of escalation",
                      "Houthis strike Saudi oil facilities, Riyadh says"]
    assert ev[1]["channels"][:2] == ["oil", "war"] and ev[0]["id"] == "e1"
    assert events.last_close(NOW) == at(2026, 10, 29, 16, 0)
    assert events.last_close(at(2026, 10, 30, 9, 0)) == at(2026, 10, 29, 16, 0)
    assert events.last_close(at(2026, 11, 1, 12, 0)) == at(2026, 10, 30, 16, 0)  # Sunday


def test_the_board_votes_on_prints_and_damps_on_events() -> None:
    board = drivers.build(_snap(), "closed", NOW)["books"]["NQ"]
    votes = {v["key"]: v for v in board["votes"]}
    assert votes["hw_prints"]["vote"] == "short" and "GOOGL" in votes["hw_prints"]["value"]
    assert votes["event_risk"]["vote"] == "neutral" and votes["event_risk"]["damper"] is True
    assert board["event_risk"] is True
    assert "Event risk since the close (2)" in board["treatment"]
    # The same count without the event is one notch higher.
    quiet = dict(_snap())
    quiet["wire"] = [h for h in quiet["wire"] if h["category"] == "corp"]
    calm = drivers.build(quiet, "closed", NOW)["books"]["NQ"]
    assert calm["max_conviction"] == board["max_conviction"] + 1
    assert drivers.build(quiet, "closed", NOW)["books"]["NQ"]["event_risk"] is False
    # Gold gets the damper and never the prints vote.
    gc = drivers.build(_snap(), "closed", NOW)["books"]["GC"]
    keys = {v["key"] for v in gc["votes"]}
    assert "event_risk" in keys and "hw_prints" not in keys


def test_the_brief_carries_the_blocks_and_keeps_only_cited_ids() -> None:
    snap = {**_snap(), "clock": {"et": NOW.isoformat()},
            "quotes": [{"key": "NQ", "last": 29000.0, "prev": 29500.0, "pct": -1.7}]}
    facts = report.build_facts(snap, "ny", "NQ")
    assert [r["symbol"] for r in facts["heavyweights"]["NQ"]][:2] == ["NVDA", "AAPL"]
    assert facts["event_risk"][0]["id"] == "e1"
    digest = report.build_digest(snap, "ny", "NQ", facts)
    assert "heavyweights" in digest and "event_risk" in digest
    brief = report.sanitize_brief({
        "thesis": "t",
        "calls": [{"book": "NQ", "open_bias": "bearish", "conviction": 4, "rest_of_day": "r",
                   "rest_of_day_bias": "bearish", "wrong_if": "w",
                   "why": ["Macro: x", "Structure: y"],
                   # The first live note wrote the ids into the sentence too
                   # (2026-10-30 02:46 ET); the tail is cut, the ids stay in their field.
                   "catalyst": "Alphabet's miss, $2.12 against $2.94, is 0.37 points of the "
                               "index. catalyst_ids: w4, e9.",
                   "catalyst_ids": ["w4", "e9", 7]}],
        "reads": [{"book": "NQ", "regime": "r", "chain": [], "at_open": "a", "wrong_if": "w",
                   "rest_of_day": "d", "flips": [], "drivers": []}],
    }, facts)
    assert brief is not None
    call = brief["calls"][0]
    assert call["catalyst"] == "Alphabet's miss, $2.12 against $2.94, is 0.37 points of the index."
    assert call["catalyst_ids"] == ["w4"]


def test_an_untimed_print_is_placed_after_the_close() -> None:
    """Alphabet's row carried no time of day; at noon it left the vote's window
    at midnight on the second night, a day earlier than an after-close print."""
    untimed = {"symbol": "GOOGL", "date": "2026-10-28", "when": "unspecified",
               "eps_actual": "$2.12", "eps_forecast": "$2.94"}
    at = events.print_moment(untimed)
    assert at is not None and (at.hour, at.minute) == (16, 5)
    early = datetime(2026, 10, 30, 3, 45, tzinfo=ET)       # 35h40m after 16:05 Wednesday
    assert events._just_reported(untimed, early)
    late = datetime(2026, 10, 30, 4, 30, tzinfo=ET)        # past the 36-hour window
    assert not events._just_reported(untimed, late)
