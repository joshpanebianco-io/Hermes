"""Hermes's tools (tools.py) and the slim picture the tab opens on (ask.slim_context)."""

from __future__ import annotations

import json
from datetime import datetime
from typing import Any
from zoneinfo import ZoneInfo

from newsterminal import ask, tools

ET = ZoneInfo("America/New_York")
NOW = datetime(2026, 10, 29, 21, 0, tzinfo=ET)


def _item(title: str, category: str, impact: str, publisher: str, age_s: float,
          summary: str = "") -> dict[str, Any]:
    return {"title": title, "category": category, "impact": impact, "publisher": publisher,
            "ts": NOW.timestamp() - age_s, "summary": summary}


def _snap() -> dict[str, Any]:
    return {
        "clock": {"et": NOW.isoformat(), "phase": {"label": "Asia session"},
                  "boxes": [{"key": "asia", "label": "Asia", "open": True}]},
        "quotes": [{"key": "NQ", "last": 29000.0, "pct": -1.7, "feed": "delayed"},
                   {"key": "VIX", "last": 17.2, "pct": 1.7, "feed": "closed"}],
        "drivers": {"books": {"NQ": {"bias": "short", "grade": "weak", "agree": 3, "total": 14,
                                     "conflict": True, "event_risk": True, "max_conviction": 2,
                                     "treatment": "Lean short NQ, weak…", "votes": []}}},
        "wire": [
            _item("Alphabet revenue miss revives AI capex jitters", "markets", "high", "WSJ",
                  3600, "Google parent fell twelve percent."),
            _item("Crude jumps as Houthis strike Saudi oil facilities", "geo", "high",
                  "Reuters", 7200),
            _item("A week-old story about tariffs", "policy", "medium", "FT", 8 * 86400),
        ],
        "calendar": [
            {"date": "2026-10-30", "et": "08:30", "event": "Chicago PMI",
             "country": "United States", "actual": None, "consensus": "54.8",
             "previous": "58.8", "surprise": None, "score": 3, "session": "premkt",
             "read": None},
            {"date": "2026-10-29", "et": "22:30", "event": "BoJ Outlook Report",
             "country": "Japan", "actual": None, "consensus": None, "previous": None,
             "surprise": None, "score": 2, "session": "asia", "read": None},
        ],
        "earnings": [
            {"symbol": "GOOGL", "date": "2026-10-28", "when": "after", "eps_actual": "$2.12",
             "eps_forecast": "$2.94", "surprise_pct": -27.89, "market_cap": 3.9e12},
            {"symbol": "AAPL", "date": "2026-10-30", "when": "after", "eps_actual": None,
             "eps_forecast": "$1.98", "surprise_pct": None, "market_cap": 3.8e12},
        ],
        "constituents": {"indices": {"NQ": {"index": "NDX", "members": [
            {"symbol": "GOOGL", "weight": 2.95, "pct": -12.64, "contribution": -0.3729},
            {"symbol": "AAPL", "weight": 7.77, "pct": 1.48, "contribution": 0.1148},
        ]}}},
    }


def _scan() -> dict[str, Any]:
    conviction = {"bias": "short", "grade": "weak", "agree": 2, "total": 11, "max_conviction": 3}
    return {"session": "closed",
            "regime": {"vix": {"last": 17.2, "shape": "contango"}, "band": "normal",
                       "spy_em_pct": 1.08, "conviction": conviction},
            "rows": [
                {"sym": "AMZN", "ok": True, "last": 225.99, "score": {"total": 77, "side": "short"},
                 "setup": {"note": "Below PDL 241.24 — plan"}, "news": [{"title": "h"}] * 8,
                 "filings": [{"form": "8-K"}] * 5, "record": {"big": True}},
                {"sym": "SPY", "ok": True, "last": 764.73, "score": {"total": 40, "side": None},
                 "setup": {"note": "inside"}, "news": [], "filings": []},
            ]}


def _bars_doc(sym: str, tf: str) -> dict[str, Any]:
    ok = sym == "AMZN"
    return {"ok": ok, "tf": tf, "error": None if ok else "no bars",
            "bars": [{"t": NOW.timestamp() - 600 * i, "o": 1.0, "h": 2.0, "l": 0.5, "c": 1.5,
                      "v": 10.0} for i in range(60, 0, -1)],
            "ema8": 1.4, "vwap": 1.3, "levels": {"pdh": 2.0}, "sessions": [], "signals": []}


BRIEF = {"ok": True, "et_label": "Thu 29 Oct, 09:32 ET", "model": "m",
         "created_utc": "2026-10-29T13:32:25+00:00",
         "report": {"thesis": "NQ is an Alphabet story"}}


def _run(name: str, args: dict[str, Any] | None = None,
         scan: dict[str, Any] | None = None) -> Any:
    return tools.run(name, args, snap=_snap(), scan=scan if scan is not None else _scan(),
                     bars=_bars_doc, brief=lambda i: BRIEF, plan=lambda i: None, now=NOW)


def test_the_spec_names_every_tool_run_knows() -> None:
    names = {t["name"] for t in tools.SPEC}
    for n in names:
        out = _run(n, {"sym": "AMZN", "book": "NQ", "kind": "brief", "desk": "futures"})
        assert "error" not in out, (n, out)
    assert _run("nothing")["error"].startswith("unknown tool")
    assert all(t["parameters"]["type"] == "object" for t in tools.SPEC)


def test_scanner_row_is_the_whole_row_cut_short_or_names_the_watchlist() -> None:
    row = _run("scanner_row", {"sym": "amzn"})
    assert row["sym"] == "AMZN" and len(row["news"]) == ask.ROW_NEWS and "record" not in row
    miss = _run("scanner_row", {"sym": "ZZZZ"})
    assert "not on the scanner" in miss["error"] and miss["watchlist"] == ["AMZN", "SPY"]


def test_bars_are_the_last_few_hours_in_et() -> None:
    out = _run("bars", {"sym": "AMZN", "tf": "10m"})
    assert len(out["bars"]) == tools.MAX_BARS
    assert out["bars"][-1] == "20:50 ET 1 2 0.5 1.5 10"      # one line per bar, not a dict
    assert out["vwap_last"] == 1.3 and out["format"].startswith("time")
    assert "error" in _run("bars", {"sym": "QQQ"})


def test_wire_search_matches_words_within_the_window() -> None:
    out = _run("wire", {"query": "alphabet miss"})
    assert out["matches"] == 1 and "Alphabet revenue miss" in out["items"][0]
    assert out["items"][0].startswith("20:00 ET · HIGH · markets · ")
    assert "— Reuters" in _run("wire", {"desk": "geo"})["items"][0]
    assert _run("wire", {"query": "tariffs"})["matches"] == 0                 # eight days old
    loose = _run("wire", {"query": "alphabet houthis"})                    # no story has both
    assert loose["match"] == "any" and loose["matches"] == 2
    assert _run("wire", {"query": "alphabet miss"})["match"] == "all"
    assert _run("wire", {"query": "tariffs", "hours": 400})["matches"] == 0   # capped at a week
    newest = _run("wire", {})
    assert newest["matches"] == 2 and "Alphabet" in newest["items"][0]


def test_calendar_takes_a_day_word() -> None:
    tomorrow = _run("calendar", {"day": "tomorrow"})
    assert tomorrow["rows"] == [
        "08:30 Chicago PMI (United States) · act — · cons 54.8 · prev 58.8 · impact 3 · premkt"
    ]
    assert _run("calendar", {})["rows"][0].startswith("22:30 BoJ Outlook Report (Japan)")
    assert _run("calendar", {"day": "2026-10-30"})["day"] == "2026-10-30"
    # A crowded day keeps its impact-2+ rows and counts the rest.
    crowd = [{"date": "2026-10-30", "et": f"{h:02d}:00", "event": f"e{h}", "country": "X",
              "score": 1 if h % 3 else 2, "session": "ny"} for h in range(40)]
    busy = tools.run("calendar", {"day": "tomorrow"}, snap={**_snap(), "calendar": crowd},
                     scan=None, bars=_bars_doc, brief=lambda i: None, plan=lambda i: None,
                     now=NOW)
    assert busy["releases"] == 14 and busy["omitted_low_impact"] == 26


def test_earnings_heavyweights_events_and_notes_come_from_the_same_builders() -> None:
    e = _run("earnings")
    assert e["reported"] == ["GOOGL 2026-10-28 after $2.12 vs $2.94 (-27.89% surprise)"]
    assert e["ahead"] == ["AAPL 2026-10-30 after"]
    h = _run("heavyweights", {"book": "NQ"})
    assert h["rows"][0].startswith("AAPL w7.77% 1.48% (0.1148 pts)")
    assert "reported 2026-10-28 after $2.12 vs $2.94 (-27.89%)" in h["rows"][1]
    ev = _run("event_risk")["events"]
    assert len(ev) == 1 and "oil" in ev[0]["channels"]
    note = _run("note", {"kind": "brief"})
    assert note["note"]["thesis"].startswith("NQ is") and note["age_hours"] is not None
    assert "error" in _run("note", {"kind": "plan"})


def test_a_tool_answer_is_capped() -> None:
    big = [_item("x" * 200, "corp", "high", "P", 1, "y" * 300) for _ in range(200)]
    out = tools.run("wire", {}, snap={**_snap(), "wire": big}, scan=None,
                    bars=_bars_doc, brief=lambda i: None, plan=lambda i: None, now=NOW)
    assert len(out["items"]) == tools.MAX_WIRE and out["matches"] == 200
    assert len(json.dumps(_run("digest", {"desk": "futures"}))) <= tools.MAX_CHARS + 200
    # A dict over the cap loses whole sections from the end, named — never half a brace.
    fat = {f"s{i}": "x" * 3000 for i in range(8)}
    fat["first"] = "keep"
    capped = tools._cap({"first": "keep", **fat})
    assert capped["first"] == "keep" and "truncated" not in capped
    assert capped["dropped"] and capped["dropped"][-1] == "s7"
    assert len(json.dumps(capped)) <= tools.MAX_CHARS


def test_the_slim_picture_is_small_and_says_what_it_knows() -> None:
    slim = ask.slim_context(_snap(), _scan(), brief=BRIEF)
    assert slim["phase"] == "Asia session" and slim["boxes_open"] == ["Asia"]
    assert slim["driver_board"]["NQ"]["event_risk"] is True
    assert slim["heavyweights_nq"][1]["reported"] == "$2.12 vs $2.94"
    assert slim["earnings"]["reported"] == ["GOOGL 2026-10-28 after $2.12 vs $2.94"]
    assert slim["scanner"]["top"][0]["sym"] == "AMZN"
    assert slim["scanner"]["tape"]["bias"] == "short"
    assert slim["notes"]["brief"]["lead"] == "NQ is an Alphabet story"
    assert slim["notes"]["plan"] is None
    assert len(json.dumps(slim)) < 6000
    assert ask.slim_context(_snap(), None)["gaps"]


def test_each_desk_gets_its_own_tools() -> None:
    names = lambda d: [t["name"] for t in tools.spec_for(d)]  # noqa: E731
    assert "levels" in names("futures") and "scanner_row" not in names("futures")
    assert "scanner_row" in names("stocks") and "levels" not in names("stocks")
    assert "wire" in names("futures") and "wire" in names("stocks")
    assert names("both") == names(None) == [t["name"] for t in tools.SPEC]
    assert set(tools.DESKS) == set(names(None))


def test_a_scanner_row_is_cut_to_what_a_question_turns_on() -> None:
    scan = _scan()
    scan["rows"][0]["options"] = {
        "ok": True, "iv30": 44.71, "rv20": 36.308, "premium": "fair", "skew": 1.77,
        "em": {"front": 24.535}, "liquidity": {"grade": "ok", "spread_pct": 4.45},
        "contracts": [{"strike": 220}] * 40, "term": [1, 2, 3],
        "flow": {"pc_vol": 2.439, "lean": "puts", "top": [{"strike": 220}] * 10},
    }
    scan["rows"][0]["score"] = {"total": 77, "side": "short", "parts": [
        {"label": "RS vs SPY", "pts": 25, "max": 25, "note": "-2.04 ATR vs SPY"}]}
    scan["rows"][0]["news"] = [{"title": "Amazon falls", "publisher": "WSJ",
                                "utc": "2026-10-30T00:30:00+00:00"}]
    row = _run("scanner_row", {"sym": "AMZN"}, scan=scan)
    assert row["options"]["iv30"] == 44.71 and "contracts" not in row["options"]
    assert row["options"]["flow"] == {"pc_vol": 2.439, "lean": "puts"}
    assert row["score"]["parts"] == ["RS vs SPY 25/25 — -2.04 ATR vs SPY"]
    assert row["news"] == ["Amazon falls — WSJ, 20:30 ET"]
    assert len(json.dumps(row)) < 1500


def test_a_note_can_be_cut_to_one_book() -> None:
    rec = {**BRIEF, "report": {
        "thesis": "t", "headlines": ["h"] * 30,
        "calls": [{"book": "NQ", "catalyst": "c"}, {"book": "ES"}, {"book": "GC"}],
        "reads": [{"book": "NQ", "regime": "r"}, {"book": "ES"}, {"book": "GC"}],
    }}
    out = tools.run("note", {"kind": "brief", "book": "ES"}, snap=_snap(), scan=None,
                    bars=_bars_doc, brief=lambda i: rec, plan=lambda i: None, now=NOW)
    assert [c["book"] for c in out["note"]["calls"]] == ["ES"]
    assert [r["book"] for r in out["note"]["reads"]] == ["ES"]
    assert "headlines" not in out["note"]          # the wire tool's, not the note's
    whole = tools.run("note", {"kind": "brief"}, snap=_snap(), scan=None, bars=_bars_doc,
                      brief=lambda i: rec, plan=lambda i: None, now=NOW)
    assert len(whole["note"]["reads"]) == 3
