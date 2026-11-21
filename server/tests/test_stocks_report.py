"""The Stocks desk's market report: SPY, QQQ and IWM for New York (2026-11-16).

The owner: "in both futures and stocks lets add Market Report tab with the generate
funcitonality ... in stocks it will just be combination overview of SPY, QQQ, IWM with
just NY for the session", then, of two mocks, the one set as the Futures report is.

What is held here: the three funds are one subject with a call each; their one bias is
the Stocks tape count, printed once with its factors, which the model comments on once
at the top; each call is capped by the tape's ceiling, one notch lower with event risk
on the wire, and at 3 against its side; each fund is traded against its own PDH, PDL,
PMH and PML; the report is New York's whatever session is asked; and the futures
subjects are as they were.
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

from newsterminal import report

NOW = datetime(2026, 11, 16, 13, 45, tzinfo=UTC)


def _row(sym: str, last: float, pdh: float, pdl: float, pmh: float, pml: float,
         pdc: float) -> dict[str, Any]:
    return {"sym": sym, "ok": True, "last": last, "chg_pct": -0.4, "ext_pct": -0.3,
            "levels": {"pdh": pdh, "pdl": pdl, "pmh": pmh, "pml": pml, "pdc": pdc}}


def _scan(bias: str | None = "short", grade: str = "strong", cap: int = 5) -> dict[str, Any]:
    """A scanner payload as the collector serves it: the tape and the three rows."""
    votes = [
        {"key": "spy_levels", "label": "SPY vs its levels", "value": "gap −0.30%",
         "vote": "short", "note": "n", "live": True, "family": "levels"},
        {"key": "qqq_levels", "label": "QQQ vs its levels", "value": "gap −0.78%",
         "vote": "short", "note": "n", "live": True, "family": "levels"},
        {"key": "vix_dir", "label": "VIX direction", "value": "19.90 +3.1%",
         "vote": "short", "note": "n", "live": True, "family": "risk"},
        {"key": "dollar", "label": "Dollar", "value": "DXY 103.55 +0.14%",
         "vote": "neutral", "note": "n", "live": True, "family": "rates"},
        {"key": "sectors", "label": "Sectors", "value": "7 up · 4 down",
         "vote": "neutral", "note": "n", "live": False, "family": "participation"},
    ]
    return {
        "session": "pre",
        "regime": {"conviction": {
            "bias": bias, "score": -52, "basis": "whole", "coverage": 100, "grade": grade,
            "max_conviction": cap, "agree": 3, "against": 0, "neutral": 1, "live": 4,
            "cannot_vote": 1, "total": 5, "session_key": "before_open",
            "weight_label": "the pre-open's weight", "votes": votes,
            "families": [
                {"key": "levels", "label": "Index levels", "short": "Levels", "weight": 35,
                 "score": -100, "live": 2, "total": 2},
                {"key": "risk", "label": "Risk appetite", "short": "Risk", "weight": 35,
                 "score": -100, "live": 1, "total": 1},
                {"key": "rates", "label": "Rates & dollar", "short": "Rates & dollar",
                 "weight": 30, "score": 0, "live": 1, "total": 1},
                {"key": "participation", "label": "Participation", "short": "Participation",
                 "weight": 0, "score": None, "live": 0, "total": 1},
            ],
        }},
        "rows": [
            _row("SPY", 752.13, 760.12, 747.88, 753.01, 749.73, 754.37),
            _row("QQQ", 674.6, 688.75, 671.68, 675.27, 670.96, 679.89),
            _row("IWM", 276.52, 279.17, 274.67, 276.97, 275.97, 277.54),
            _row("NVDA", 1.0, 1, 1, 1, 1, 1),
        ],
    }


def _snap(wire: list[dict[str, Any]] | None = None) -> dict[str, Any]:
    return {"clock": {"et": "2026-11-16T08:45:00-05:00"}, "wire": wire or []}


def _facts(scan: dict[str, Any] | None = None, wire: list[dict[str, Any]] | None = None
           ) -> dict[str, Any]:
    base = {"books": ["NQ", "ES"], "partial": [], "catalysts": [], "headlines": []}
    return report._etf_facts(_snap(wire), _scan() if scan is None else scan, base)


def test_the_three_funds_are_one_subject_for_new_york():
    assert report.resolve_asset("etfs") == "etfs"
    assert report.books_for("etfs") == ["SPY", "QQQ", "IWM"]
    assert report.ASSETS["etfs"]["label"] == "SPY · QQQ · IWM"
    # The futures subjects are as they were, one book each where asked.
    assert report.books_for("NQ") == ["NQ"]
    assert report.books_for("indexes") == ["NQ", "ES"]
    assert report.schema_for("NQ") is report.SCHEMA


def test_one_bias_for_the_three_with_its_factors_printed_once():
    f = _facts()
    assert f["books"] == ["SPY", "QQQ", "IWM"]
    assert f["drivers"] == {} and f["factors"] == {}
    assert f["market"]["bias"] == "short" and f["market"]["score"] == -52
    rows = [(r["key"], r["name"], r["weight"], r["tag"]) for r in f["market_factors"]]
    # Heaviest first, a family with no weight at this hour left off, event risk last.
    assert rows == [
        ("levels", "Index levels", 35, "Bearish"),
        ("risk", "Risk appetite", 35, "Bearish"),
        ("rates", "Macro", 30, "Neutral"),
        ("event", "Geopolitics & events", None, "Quiet"),
    ]
    # Nothing a futures book prints: no ladder, no gamma, no session-type record.
    assert f["ladders"] == [] and f["gamma"] == [] and f["session_type"] == {}


def test_each_fund_is_traded_against_its_own_levels():
    f = _facts()
    spy = [(m["label"], m["price"]) for m in f["levels"]["SPY"]["marks"]]
    assert spy == [("PDL", 747.88), ("PML", 749.73), ("Last", 752.13), ("PMH", 753.01),
                   ("Prev close", 754.37), ("PDH", 760.12)]
    assert f["levels"]["SPY"]["dp"] == 2
    assert set(f["levels"]) == {"SPY", "QQQ", "IWM"}
    qqq = next(r for r in f["funds"] if r["sym"] == "QQQ")
    assert qqq["against_previous_day"] == "inside the previous day's range"
    assert qqq["against_pre_market"] == "inside the pre-market range"
    # No trend read reaches the model: the report argues from none.
    assert not any("ema" in k or "daily" in k for r in f["funds"] for k in r)


def test_a_missing_tape_or_fund_is_said_not_invented():
    scan = _scan()
    scan["regime"] = {}
    scan["rows"] = scan["rows"][:2]
    f = _facts(scan)
    assert f["market"] is None and f["market_factors"] == []
    assert any("tape count" in p for p in f["partial"])
    assert any("IWM" in p for p in f["partial"])
    assert "IWM" not in f["levels"]


def test_event_risk_takes_a_notch_off_the_tapes_ceiling():
    quiet = _facts()
    assert quiet["market"]["max_conviction"] == 5
    # A HIGH story on the geopolitics desk since Friday's close (events.EVENT_DESKS).
    wire = [{"impact": "high", "category": "geo", "ts": NOW.timestamp(),
             "title": "Tanker attacked in the Strait of Hormuz", "publisher": "Reuters",
             "url": "u1"}]
    loud = report._etf_facts(_snap(wire), _scan(), {"books": [], "partial": []})
    ev = loud["market_factors"][-1]
    assert (ev["key"], ev["lean"], ev["tag"]) == ("event", "damp", "1 story")
    assert loud["market"]["max_conviction"] == 4
    # Never below one.
    low = report._etf_facts(_snap(wire), _scan(grade="weak", cap=1), {"books": [], "partial": []})
    assert low["market"]["max_conviction"] == 1


def _answer(**over: Any) -> dict[str, Any]:
    a = {
        "thesis": "Tape leans short into the open: VIX up, QQQ under its previous close.",
        "factors": [{"key": "levels", "line": "Bearish; SPY and QQQ both gapped under the close."},
                    {"key": "risk", "line": "VIX 19.90 up 3.1%, protection being bought."},
                    {"key": "gamma", "line": "a row the page does not have"}],
        "calls": [
            {"book": "SPY", "open_bias": "bearish", "conviction": 5, "plan": "Lose PML 749.73.",
             "wrong_if": "Back over PMH 753.01."},
            {"book": "qqq", "open_bias": "lean bull", "conviction": 5, "plan": "p",
             "wrong_if": "w"},
            {"book": "IWM", "open_bias": "neutral", "conviction": 1, "plan": "p", "wrong_if": "w",
             "factors": [{"key": "rates", "line": "no table of its own"}]},
        ],
        "today": [], "risks": ["SPY and QQQ both gapped under the close."], "headlines": [],
    }
    a.update(over)
    return a


def test_the_answer_is_checked_against_the_tape():
    b = report.sanitize_brief(_answer(), _facts())
    assert b is not None
    # The market's comments at the top, a row the page has no place for dropped, the
    # engine's tag taken off the front of a comment.
    assert [f["key"] for f in b["factors"]] == ["levels", "risk"]
    assert b["factors"][0]["line"].startswith("SPY and QQQ")
    by = {c["book"]: c for c in b["calls"]}
    assert list(by) == ["SPY", "QQQ", "IWM"]
    # The tape's ceiling, and 3 against its side.
    assert by["SPY"]["conviction"] == 5
    assert by["QQQ"]["conviction"] == 3
    # A fund has no factors of its own.
    assert all(c["factors"] == [] for c in b["calls"])


def test_a_fund_without_a_call_is_not_a_report():
    a = _answer()
    a["calls"] = a["calls"][:2]
    assert report.sanitize_brief(a, _facts()) is None


def test_the_market_comments_are_held_to_the_limits_and_said_once():
    long = " ".join(["word"] * 40)
    b = report.sanitize_brief(_answer(factors=[{"key": "levels", "line": long}]), _facts())
    assert any(x.startswith("market levels") for x in report.too_long(b))
    # The one risk says a market comment again.
    b = report.sanitize_brief(_answer(), _facts())
    assert any(x.startswith("risk 1 repeats market") for x in report.repeats(b))
    # And the figures in them are checked like any other.
    assert "SPY and QQQ both gapped under the close." in report.brief_prose(b)


def test_the_prompt_says_what_is_different_and_the_schema_holds_it():
    p = report.system_prompt("ny", "etfs", {"underway": False, "hours": "09:30–16:00 ET",
                                            "opens_et": "09:30", "phrase": "45m"})
    assert "THIS REPORT IS THE STOCKS DESK'S" in p
    assert "index_funds" in p and "stocks_tape_count" in p
    assert "THIS REPORT IS THE STOCKS DESK'S" not in report.system_prompt(
        "ny", "NQ", {"underway": False, "hours": "x", "opens_et": "09:30", "phrase": "45m"})
    s = report.schema_for("etfs")
    call = s["properties"]["calls"]["items"]["properties"]
    assert call["book"]["enum"] == ["SPY", "QQQ", "IWM"]
    # Brief_version 4: the bottom line, the list and a call a fund; the tape's table
    # prints the engine's reads, with no comment of the model's.
    assert set(s["required"]) == {"thesis", "context", "movers", "calls"}
    assert "factors" not in call
    assert "levels" not in report.FACTOR_KEYS
    assert "THE LIST IS FOR US STOCKS" in p
    assert '"SPY", "QQQ", "IWM"' in report.LOOSE_SHAPE_ETFS
