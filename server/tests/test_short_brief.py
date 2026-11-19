"""The short brief (2026-11-15): the owner asked for reports that are concise and say
what actually moves the market. A real Indexes note had come back at 1,850 words with
the same facts in nine places.

What is held here: the shape has five parts and no more, the counts and the word
limits are checked on the way back and an over-long answer is sent back once, the
figures the model is shown are at the precision the page prints, and a note stored in
the longer shape still reads.

Later the same day it became the market report (brief_version 3): a call's three
reasons are one comment a factor, for every factor the bias weighs, and neither
dealer gamma nor a moving average is in it (tests/test_market_report.py has the rows,
the levels and what the model is shown).
"""

from __future__ import annotations

import json
from datetime import UTC, datetime
from typing import Any

import pytest

from newsterminal import report, tools


def _facts() -> dict[str, Any]:
    return {"books": ["NQ"], "headlines": [{"id": "h1"}, {"id": "h2"}, {"id": "h3"}, {"id": "h4"}],
            "snapshot": [], "catalysts": [{"id": "c1"}, {"id": "c2"}, {"id": "c3"}, {"id": "c4"}],
            "rotation": {}, "partial": [], "ladders": [], "gamma": [], "as_of": "now"}


def _f(*pairs: tuple[str, str]) -> list[dict[str, str]]:
    return [{"key": k, "line": line} for k, line in pairs]


FOUR = _f(("rates", "a"), ("catalysts", "b"), ("structure", "c"), ("event", "d"))


def _brief(**over: Any) -> dict[str, Any]:
    b: dict[str, Any] = {
        "thesis": "Core CPI is the day.",
        "calls": [{"book": "NQ", "open_bias": "leaning bearish", "conviction": 3,
                   "factors": FOUR, "plan": "Below value low targets Friday's low.",
                   "wrong_if": "Acceptance above value high."}],
        "today": [{"id": f"c{i}", "note": "n"} for i in (1, 2, 3, 4)],
        "risks": ["ra", "rb", "rc", "rd"],
        "headlines": [{"id": f"h{i}", "books": ["NQ"], "note": "n"} for i in (1, 2, 3, 4)],
        # The briefing's list (brief_version 4): three items, so none is sent back as short.
        "movers": [{"id": "c1", "impact": "high", "effect": "pressure", "why": "yields up"},
                   {"id": "h1", "impact": "medium", "effect": "two-way", "why": "tariff risk"},
                   {"id": "c2", "impact": "low", "effect": "priced", "why": "already traded"}],
    }
    b.update(over)
    return b


def test_the_shape_is_a_bottom_line_a_list_and_a_call_and_the_older_parts_still_read() -> None:
    # Brief_version 4 (owner, 2026-11-19: a report "given to a ceo"): the bottom line, what
    # can move prices, a call a book. Nothing else is asked for.
    assert set(report.SCHEMA["properties"]) == {"thesis", "movers", "calls"}
    call = report.SCHEMA["properties"]["calls"]["items"]["properties"]
    assert set(call) == {"book", "open_bias", "conviction"}
    item = report.SCHEMA["properties"]["movers"]["items"]["properties"]
    assert set(item) == {"id", "impact", "effect", "why"}
    assert report.SCHEMA["properties"]["movers"]["minItems"] == report.MOVERS_MIN
    # An answer in the older shape still reads: a stored 3 is drawn again from it.
    out = report.sanitize_brief(_brief(), _facts())
    assert out is not None
    # A comment a factor, every one kept: nothing that moves the score is cut to three.
    assert out["calls"][0]["factors"] == FOUR and "why" not in out["calls"][0]
    assert [t["id"] for t in out["today"]] == ["c1", "c2", "c3"]
    assert out["risks"] == ["ra", "rb", "rc"]
    assert [h["id"] for h in out["headlines"]] == ["h1", "h2", "h3"]


def test_a_brief_needs_no_read_only_a_thesis_and_a_call_per_book() -> None:
    assert report.sanitize_brief({"thesis": "t", "calls": [
        {"book": "NQ", "open_bias": "neutral", "conviction": 1}]}, _facts()) is not None
    assert report.sanitize_brief({"thesis": "", "calls": [
        {"book": "NQ", "open_bias": "neutral", "conviction": 1}]}, _facts()) is None


def test_the_limits_are_in_the_prompt_and_the_loose_shape() -> None:
    p = report.system_prompt("ny", "indexes")
    # The parts the briefing asks for; the older parts' limits hold only an older answer.
    for key in ("thesis", "mover"):
        cap = report.LIMITS[key]
        assert f"{cap} words" in p, key
        assert f"{cap} words at most" in report.LOOSE_SHAPE, key
    # The longer shape's fields are named nowhere a model is told what to write.
    for gone in ("gamma_read", "catalyst_notes", "rotation_read", "cross_asset", "at_open",
                 "rest_of_day", "snapshot_watch", "`chain`", "`drivers`"):
        assert gone not in p and gone not in report.LOOSE_SHAPE, gone


def test_too_long_names_the_part_and_lets_a_quarter_over_through() -> None:
    cap = report.LIMITS["thesis"]
    assert report.too_long(_brief(thesis=" ".join(["w"] * cap))) == []
    assert report.too_long(_brief(thesis=" ".join(["w"] * int(cap * report.LIMIT_SLACK)))) == []
    over = report.too_long(_brief(thesis=" ".join(["w"] * (cap + 20))))
    assert over == [f"thesis is {cap + 20} words (limit {cap})"]
    b = report.sanitize_brief(_brief(), _facts())
    assert b is not None
    b["calls"][0]["factors"][1]["line"] = " ".join(["w"] * 40)
    b["risks"][2] = " ".join(["w"] * 30)
    assert report.too_long(b) == [
        f"NQ catalysts is 40 words (limit {report.LIMITS['factor']})",
        f"risk 3 is 30 words (limit {report.LIMITS['risks']})",
    ]


def test_the_guard_reads_every_part_the_model_wrote() -> None:
    b = report.sanitize_brief(_brief(
        thesis="t 1", calls=[{"book": "NQ", "open_bias": "neutral", "conviction": 1,
                              "factors": _f(("rates", "w 2")), "plan": "p 3",
                              "wrong_if": "x 4"}],
        today=[{"id": "c1", "note": "n 5"}], risks=["r 6"],
        headlines=[{"id": "h1", "books": ["NQ"], "note": "h 7"}],
        movers=[{"id": "c2", "impact": "high", "effect": "pressure", "why": "m 8"}]), _facts())
    assert b is not None
    assert report.unverified(b, "nothing") == ["1", "2", "3", "4", "5", "6", "7", "8"]
    assert report.brief_words(b) == 16


def _generate(monkeypatch: pytest.MonkeyPatch, answers: list[dict[str, Any]]) -> tuple[
        dict[str, Any], list[list[dict[str, str]]]]:
    asked: list[list[dict[str, str]]] = []

    def answer(payload: dict[str, Any], key: str) -> dict[str, Any]:
        asked.append(payload["messages"])
        body = json.dumps(answers[min(len(asked), len(answers)) - 1])
        return {"choices": [{"message": {"content": body}, "finish_reason": "stop"}]}

    monkeypatch.setattr(report, "_post", answer)
    monkeypatch.setattr(report, "_key", lambda: "k")
    monkeypatch.setattr(report, "_store", lambda rep: None)
    monkeypatch.setattr(report, "build_facts", lambda *a, **k: _facts())
    monkeypatch.setattr(report, "build_digest", lambda *a, **k: {"NQ": {"last": 30707}})
    return report.generate({"clock": {}}, asset="NQ"), asked


def test_an_over_long_answer_is_sent_back_once_and_the_shorter_one_kept(
        monkeypatch: pytest.MonkeyPatch) -> None:
    long = _brief(thesis=" ".join(["word"] * 90))
    rep, asked = _generate(monkeypatch, [long, _brief()])
    assert rep["ok"] is True and len(asked) == 2
    assert "breaks the brief's limits: thesis is 90 words (limit 40)" in asked[1][-1]["content"]
    assert rep["report"]["thesis"] == "Core CPI is the day."
    assert rep["brief_version"] == 4
    assert rep["words"] == report.brief_words(rep["report"]) < 60
    assert "ok after re-ask" in rep["attempts"][-1]["note"]


def test_a_second_answer_that_is_no_shorter_is_not_taken(monkeypatch: pytest.MonkeyPatch) -> None:
    long = _brief(thesis=" ".join(["word"] * 90))
    rep, asked = _generate(monkeypatch, [long, _brief(thesis=" ".join(["again"] * 95))])
    assert rep["ok"] is True and len(asked) == 2  # one re-ask, never a third
    assert rep["report"]["thesis"].startswith("word word")
    assert "still over" in rep["attempts"][-1]["note"]


def test_a_shorter_answer_is_not_worth_an_invented_number(monkeypatch: pytest.MonkeyPatch) -> None:
    long = _brief(thesis=" ".join(["word"] * 90))
    rep, _ = _generate(monkeypatch, [long, _brief(thesis="NQ to 99999")])
    assert rep["report"]["thesis"].startswith("word word") and rep["unverified"] == []


def test_a_brief_inside_its_limits_is_asked_for_once(monkeypatch: pytest.MonkeyPatch) -> None:
    rep, asked = _generate(monkeypatch, [_brief()])
    assert rep["ok"] is True and len(asked) == 1 and rep["attempts"] == []


def test_the_digest_is_shown_at_the_precision_the_page_prints() -> None:
    digest = {
        "index_movers": {"NQ": {"net_contribution_pct": -1.1543, "biggest": [
            {"symbol": "AMZN", "weight_pct": 4.2983, "change_pct": -2.5149, "index_pp": -0.3763}]}},
        "dollar_and_commodities": {"EURUSD": {"last": 1.10284}, "DXY": {"last": 103.4113},
                                   "USDJPY": {"last": 159.686}},
        "brief_tables": {"snapshot": [{"key": "US10Y", "last": 5.154, "chg": -1.2324}],
                         "ladders": [
            {"book": "NQ", "dp": 0, "last": 28150.25,
             "rows": [{"price": 28206.3935, "label": "200 EMA (10m)"}, {"price": 28150.25}],
             "confluence": [{"lo": 28206.3935, "hi": 28210.75}],
             "regime": {"ema200": 28436.3307, "pct": -1.0061},
             "ema200_10m": {"value": 28206.3935, "slope": "falling"}},
            {"book": "ES", "dp": 2, "last": 7600.8842, "rows": [{"price": 7600.8842}]}]},
        "ok": True, "n": 3, "text": "28206.3935 stays as written",
    }
    before = json.dumps(digest)
    out = report.shown(digest)
    assert json.dumps(digest) == before  # a copy: the page's tables are not touched
    mover = out["index_movers"]["NQ"]["biggest"][0]
    assert (mover["weight_pct"], mover["change_pct"], mover["index_pp"]) == (4.3, -2.51, -0.38)
    assert out["index_movers"]["NQ"]["net_contribution_pct"] == -1.15
    fx = out["dollar_and_commodities"]
    assert fx["EURUSD"]["last"] == 1.1028  # an exchange rate keeps its four places
    assert (fx["DXY"]["last"], fx["USDJPY"]["last"]) == (103.41, 159.69)
    assert out["brief_tables"]["snapshot"][0] == {"key": "US10Y", "last": 5.154, "chg": -1.23}
    nq, es = out["brief_tables"]["ladders"]
    # NQ's ladder prints whole points, so that is what the model is given to quote.
    assert [r["price"] for r in nq["rows"]] == [28206, 28150] and nq["last"] == 28150
    assert nq["confluence"] == [{"lo": 28206, "hi": 28211}]
    assert nq["regime"] == {"ema200": 28436, "pct": -1.01}
    assert nq["ema200_10m"] == {"value": 28206, "slope": "falling"}
    assert es["rows"][0]["price"] == 7600.88 and es["last"] == 7600.88
    assert out["ok"] is True and out["n"] == 3 and out["text"] == "28206.3935 stays as written"
    assert report.shown({"NQ": {"last": 30707}}) == {"NQ": {"last": 30707}}


def test_the_boards_score_carries_what_it_is_over() -> None:
    snap = {"clock": {"et": "2026-11-16T10:00:00-05:00"}, "drivers": {"books": {"NQ": {
        "votes": [{"label": "10Y", "family": "rates", "vote": "short"}], "bias": "short",
        "score": -37, "basis": "whole", "coverage": 62, "max_conviction": 3}}}}
    assert report._drivers(snap, ["NQ"])["NQ"]["basis"] == "whole"


NOW = datetime(2026, 11, 16, 15, 0, tzinfo=UTC)


def test_hermes_reads_a_short_brief_with_its_clock_joined_to_the_calendar() -> None:
    rec = {"id": "x", "created_utc": NOW.isoformat(), "model": "m", "session": "ny", "asset": "NQ",
           "format": "brief", "brief_version": 2,
           "report": {"thesis": "t", "calls": [{"book": "NQ", "plan": "p"}],
                      "today": [{"id": "c2", "note": "a miss reprices the cut"}], "risks": ["r"],
                      "headlines": []},
           "facts": {"catalysts": [{"id": "c2", "when": "Today 08:30 ET", "title": "CPI"}],
                     "headlines": []}}
    note = tools._note({"note": rec["report"]}, "brief", None, rec["facts"])["note"]
    assert note["today"] == ["Today 08:30 ET CPI — a miss reprices the cut"]
    assert note["calls"] == [{"book": "NQ", "plan": "p"}] and "reads" not in note
    assert note["risks"] == ["r"]


def test_one_comment_under_two_factors_of_a_book_is_named_for_the_re_ask() -> None:
    """The first real short brief (2026-11-15) was inside every limit and said one
    sentence twice. In the report's rows that is one comment under two factors of the
    same book. The same macro under two BOOKS is not a repeat: the dollar is the
    dollar for both, and each book's table is read alone."""
    same = "No live macro print, Fed speaker, or prior RTH profile exists for Monday's open."
    b = {"thesis": "Nothing is live: trade the level, not a direction.",
         "calls": [
             {"book": "NQ", "factors": _f(
                 ("catalysts", same),
                 ("rates", "No live macro print, Fed speaker or prior RTH profile exists "
                           "for the open."),
                 ("participation", "Technology lagged at -1.65% relative strength."))},
             {"book": "ES", "factors": _f(
                 ("catalysts", same),
                 ("participation", "Staples led at 1.78% relative strength."))}]}
    assert report.repeats(b) == ["NQ rates repeats NQ catalysts"]
    assert report.faults(b) == ["NQ rates repeats NQ catalysts"]
    # Two short fragments share their nouns by chance and are not a repeat.
    short = {"thesis": "CPI day.", "calls": [{"book": "NQ", "factors": _f(
        ("catalysts", "CPI day."), ("rates", "CPI day."))}]}
    assert report.repeats(short) == []


def test_a_repeat_is_sent_back_with_the_limits(monkeypatch: pytest.MonkeyPatch) -> None:
    same = "No live macro print or Fed speaker exists for the open today."
    twice = {**_brief(), "calls": [{"book": "NQ", "open_bias": "neutral", "conviction": 1,
                                    "factors": _f(("catalysts", same),
                                                  ("rates", same.replace("today", "at all"))),
                                    "plan": "p", "wrong_if": "w"}]}
    rep, asked = _generate(monkeypatch, [twice, _brief()])
    assert len(asked) == 2 and "NQ rates repeats NQ catalysts" in asked[1][-1]["content"]
    assert rep["report"]["calls"][0]["factors"] == FOUR


def test_an_id_is_taken_out_of_a_sentence_and_a_half_year_is_not() -> None:
    out = report.sanitize_brief(_brief(
        thesis="c1: CPI is the day.",
        risks=["h1 Iran story can gap crude", "The story (h2) matters; H1 guidance holds"],
        today=[{"id": "c1", "note": "c1 a miss reprices the cut"}]), _facts())
    assert out is not None
    assert out["thesis"] == "CPI is the day."
    assert out["risks"] == ["Iran story can gap crude", "The story matters; H1 guidance holds"]
    # A sentence that lost its front starts with a capital (2026-11-15, the market report).
    assert out["today"] == [{"id": "c1", "note": "A miss reprices the cut"}]


def test_a_risk_that_restates_a_reason_is_named_too() -> None:
    """The second real short brief: the crowded position was a reason and then a risk."""
    b = {"thesis": "No print is live; structure leads.",
         "calls": [{"book": "NQ", "factors": _f(("participation", (
             "Leveraged funds crowded long 6,114 contracts, 98th percentile; a break finds "
             "forced sellers.")))}],
         "risks": ["Iran tanker attacks in Hormuz lift oil and risk premiums.",
                   "Crowded NQ longs (6,114 contracts, 98th pct) can flush on a break."]}
    assert report.repeats(b) == ["risk 2 repeats NQ participation"]


def test_a_note_on_the_clock_does_not_say_its_rows_time_and_name_again() -> None:
    """Two real short briefs opened each note with its row, the second after being told
    not to: the row prints when and what, the note says what it does."""
    barr = {"id": "c5", "when": "Mon 05:00 ET", "title": "FOMC Member Barr Speaks"}
    sales = {"id": "c10", "when": "Tue 08:30 ET", "title": "Retail Sales Ex Autos m/m"}
    assert report._drop_clock(
        "Barr speaks Mon 05:00 ET pre-market; hawkish tone would press gold before the bell.",
        barr) == "Hawkish tone would press gold before the bell."
    assert report._drop_clock(
        "Retail Sales Ex Autos Tue 08:30 ET premkt; consensus 0.4%, a miss cuts rate-hike pricing.",
        sales) == "Consensus 0.4%, a miss cuts rate-hike pricing."
    # A first clause that says something of its own stays, and so does a note with one clause.
    kept = "Priced for a hold at 05:00; a cut lifts gold."
    assert report._drop_clock(kept, barr) == kept
    assert report._drop_clock("Barr speaks Mon 05:00 ET", barr) == "Barr speaks Mon 05:00 ET"
    facts = {**_facts(), "catalysts": [barr]}
    out = report.sanitize_brief(_brief(today=[
        {"id": "c5", "note": "Barr speaks Mon 05:00 ET: a hawkish tilt hits rates."}]), facts)
    assert out is not None
    assert out["today"] == [{"id": "c5", "note": "A hawkish tilt hits rates."}]
