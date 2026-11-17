"""The market report (2026-11-15) and the trend reads leaving the scores with it.

The owner, of the short brief: "need to rework the report, so it looks like a nice
concise readable report aesthetically pleasing. i dont think we need to mention gex
since it does impact bias. we should mention all the factors impacting the bias, like
news, macro, geopolitics important news, volume profile structure. i dont think we need
to include about the ema's". Then: "i think we drop ema's from the bias and scoring of
stocks", and asked whether the plain daily trend read should go with them: every one.

What is held here: the page gets one row for every factor the bias weighs, in the
engine's order with the engine's tag and share, and event risk last; the levels a call
is traded against carry no gamma level and no average; the model is shown neither; a
stock's score has no daily-frame part and still flags a setup against the daily trend;
and Hermes reads the rows as the page prints them.
"""

from __future__ import annotations

import json
import re
from typing import Any

import pytest

from newsterminal import report, scanscore, tools


def _vote(label: str, family: str | None, vote: str = "neutral", value: str = "v",
          live: bool = True, **extra: Any) -> dict[str, Any]:
    return {"label": label, "family": family, "vote": vote, "value": value,
            "can_vote_now": live, **extra}


def _board(events: int = 3) -> dict[str, Any]:
    event = (_vote("Event risk", None, value=f"{events} since the close",
                   note="Tanker attacked in Hormuz (oil, risk) — risk on the tape caps "
                        "conviction a notch lower")
             if events else _vote("Event risk", None, value="none", note="nothing"))
    return {
        "families": [
            {"key": "structure", "label": "Intraday structure", "weight": 33, "score": 50},
            {"key": "rates", "label": "Rates & dollar", "weight": 21, "score": -100},
            {"key": "risk", "label": "Risk appetite", "weight": 20, "score": 0},
            {"key": "catalysts", "label": "Catalysts", "weight": 13, "score": None},
            {"key": "participation", "label": "Participation", "weight": 13, "score": 0},
            # A family with no weight in this session is no row (a board stored with
            # the daily family still in it reads the same way).
            {"key": "daily", "label": "Daily trend", "weight": 0, "score": 100},
        ],
        "votes": [
            _vote("Value", "structure", "long", "above (VAH 30,400)"),
            _vote("Session", "structure", value="inside Asia's range"),
            _vote("10Y", "rates", "short", "4.10% +6.0bp"),
            _vote("Dollar", "rates", "short", "99.0 +0.4%"),
            _vote("VIX", "risk", "long", "16.0 -5.0%"),
            _vote("Credit", "risk", "short", "HYG -0.3%"),
            _vote("VIX curve", "risk", value="0.90"),
            _vote("US prints", "catalysts", live=False, value="—"),
            _vote("Sectors", "participation", value="5 of 11 up"),
            _vote("Leaders", "participation", value="flat"),
            _vote("Dealer gamma", None, value="negative γ · below flip"),
            _vote("Daily 200", "daily", "long", "above"),
            event,
        ],
    }


# ---- what is driving the bias: a row a factor ------------------------------------------


def test_every_factor_the_bias_weighs_is_a_row_in_the_engines_order() -> None:
    rows = report.factors_of("NQ", _board())
    assert [(r["key"], r["name"], r["sub"], r["weight"], r["lean"], r["tag"]) for r in rows] == [
        ("structure", "Volume profile & structure", None, 33, "bull", "Bullish"),
        ("rates", "Macro", "rates & dollar", 21, "bear", "Bearish"),
        ("risk", "Risk appetite", None, 20, "mixed", "Mixed"),
        ("catalysts", "News & data", None, 13, "none", "Nothing yet"),
        ("participation", "Participation", "sectors & leaders", 13, "neutral", "Neutral"),
        ("event", "Geopolitics & events", "lowers conviction, not a side", None, "damp",
         "3 stories"),
    ]
    # The shares are the session's hundred: what the slider beside them was scored on.
    assert sum(r["weight"] for r in rows if r["weight"]) == 100
    by = {r["key"]: r for r in rows}
    assert by["structure"]["reads"] == ["Value: above (VAH 30,400)", "Session: inside Asia's range"]
    assert by["catalysts"]["reads"] == []           # a read with nothing to print is not one
    assert by["event"]["reads"][0].startswith("Tanker attacked in Hormuz")


def test_gamma_and_trend_are_no_row() -> None:
    rows = report.factors_of("NQ", _board())
    text = json.dumps(rows).lower()
    assert "gamma" not in text and "flip" not in text
    assert "daily" not in {r["key"] for r in rows} and "200" not in text
    assert "daily" not in report.FACTOR_KEYS
    assert set(report.FACTOR_KEYS) == {"catalysts", "rates", "risk", "structure",
                                       "participation", "event"}
    # The model can only comment on a row there is.
    keys = report.SCHEMA["properties"]["calls"]["items"]["properties"]["factors"]["items"][
        "properties"]["key"]["enum"]
    assert set(keys) == set(report.FACTOR_KEYS)


def test_a_quiet_tape_is_a_quiet_row_and_one_story_is_one() -> None:
    quiet = report.factors_of("NQ", _board(events=0))[-1]
    assert (quiet["lean"], quiet["tag"]) == ("neutral", "Quiet")
    assert quiet["reads"] == ["No high-impact story since the close"]
    assert report.factors_of("NQ", _board(events=1))[-1]["tag"] == "1 story"


def test_crude_and_silver_name_their_rows_for_what_is_in_them() -> None:
    names = {r["key"]: (r["name"], r["sub"]) for r in report.factors_of("CL", _board())}
    assert names["rates"] == ("Macro", "dollar & products")
    assert names["risk"] == ("Demand", "credit & copper")
    assert names["catalysts"] == ("Inventories & data", None)
    sil = {r["key"]: (r["name"], r["sub"]) for r in report.factors_of("SIL", _board())}
    assert sil["rates"] == ("Macro", "rates, dollar & metals")


# ---- the levels a call is traded against -------------------------------------------------


def _ladder() -> dict[str, Any]:
    return {"book": "NQ", "dp": 0, "rows": [
        {"price": 30950.0, "label": "Call wall", "kind": "gex"},
        {"price": 30610.4, "label": "ON high", "kind": "range"},
        {"price": 30500.0, "label": "Prior RTH high", "kind": "ref"},
        {"price": 30310.0, "label": "200 EMA (10m)", "kind": "ema"},
        {"price": 30250.6, "label": "Prior RTH POC", "kind": "ref"},
        {"price": 30200.0, "label": "Gamma flip", "kind": "gex"},
        {"price": 30120.0, "label": "Last", "kind": "last"},
        {"price": 30111.0, "label": "VWAP since 18:00", "kind": "vwap"},
        {"price": 30090.0, "label": "Prior settle", "kind": "ref"},
        {"price": 30050.0, "label": "ON low", "kind": "range"},
        {"price": 29900.0, "label": "Prior RTH low", "kind": "ref"},
        {"price": 29800.0, "label": "Expected move low", "kind": "em"},
    ]}


def _profiles() -> dict[str, Any]:
    return {"profiles": {"assets": {"NQ": {"ok": True, "rows": [
        {"key": "prev_rth", "date": "Fri 13 Nov", "vah": 30400.2, "val": 30100.0,
         "poc": 30250.6, "high": 30500.0, "low": 29900.0}]}}}}


def test_the_key_levels_are_range_value_and_last_low_to_high() -> None:
    lv = report.key_levels(_profiles(), "NQ", _ladder())
    assert lv is not None and lv["dp"] == 0
    assert [(m["price"], m["label"], m["kind"]) for m in lv["marks"]] == [
        (29900, "Fri low", "range"), (30050, "Overnight low", "range"),
        (30100, "Value low", "value"), (30120, "Last", "last"), (30251, "POC", "poc"),
        (30400, "Value high", "value"), (30500, "Fri high", "range"),
        (30610, "Overnight high", "range"),
    ]
    # No gamma level, no average, no VWAP, no expected move and no settle among them.
    labels = " ".join(m["label"] for m in lv["marks"]).lower()
    assert not re.search(r"wall|flip|gamma|ema|vwap|expected|settle", labels)


def _ranges(overnight_ts: int, ny_ts: int, ny_status: str = "complete") -> dict[str, Any]:
    return {"ranges": {"assets": {"NQ": {"sessions": [
        {"key": "overnight", "ok": True, "status": "complete", "start_ts": overnight_ts},
        {"key": "asia", "ok": True, "status": "complete", "start_ts": overnight_ts + 7200},
        {"key": "ny", "ok": True, "status": ny_status, "start_ts": ny_ts}]}}}}


def test_a_night_from_before_the_last_session_is_not_the_handover() -> None:
    """A Sunday morning, 15 Nov 2026: the ranges still held Thursday night's box, and
    the report printed "Overnight low 28,243" above a last price of 28,035."""
    thu_1800, fri_0930, fri_1800 = 1794524400, 1794580200, 1794610800
    labels = lambda snap: [m["label"] for m in report.key_levels(  # noqa: E731
        {**_profiles(), **snap}, "NQ", _ladder())["marks"]]
    # Thursday night's range, after Friday's session has closed: left off.
    weekend = labels(_ranges(thu_1800, fri_0930))
    assert "Overnight high" not in weekend and "Overnight low" not in weekend
    assert weekend == ["Fri low", "Value low", "Last", "POC", "Value high", "Fri high"]
    # The night after that session is the one the open inherits: kept.
    assert "Overnight low" in labels(_ranges(fri_1800, fri_0930))
    # And so is last night's while today's session is still trading.
    assert "Overnight high" in labels(_ranges(thu_1800, fri_0930, "live"))
    # London's handover is Asia's range, by the same rule.
    lad = {"book": "NQ", "dp": 0, "rows": [
        {"price": 30120.0, "label": "Last", "kind": "last"},
        {"price": 30300.0, "label": "Asia high", "kind": "range"},
        {"price": 30000.0, "label": "Asia low", "kind": "range"}]}
    stale = report.key_levels(_ranges(thu_1800, fri_0930), "NQ", lad)
    assert stale is not None and [m["label"] for m in stale["marks"]] == ["Last"]
    fresh = report.key_levels(_ranges(fri_1800, fri_0930), "NQ", lad)
    assert fresh is not None and len(fresh["marks"]) == 3


def test_a_sentence_loses_the_list_mark_and_the_count_a_model_left_on_it() -> None:
    out = report.sanitize_brief({
        "thesis": "Iran-Bahrain strikes cap conviction. (39 words){",
        "calls": [{"book": "NQ", "open_bias": "neutral", "conviction": 1,
                   "factors": [{"key": "rates", "line": "- 10Y closed 5.15%, +5.1bp Friday."},
                               {"key": "risk", "line": "-1.65% on the day for tech. (9 words)"}],
                   "plan": "1. Hold above 28,030 targets 28,399.", "wrong_if": "• Below 27,805 }"}],
        "risks": ["> Iran-Bahrain drone strikes spike oil.", "10Y above 5.2% hits duration.",
                  "* Crowded longs (98th percentile) flush."],
    }, {"books": ["NQ"]})
    assert out is not None
    assert out["thesis"] == "Iran-Bahrain strikes cap conviction."
    call = out["calls"][0]
    assert [f["line"] for f in call["factors"]] == [
        "10Y closed 5.15%, +5.1bp Friday.", "-1.65% on the day for tech."]
    assert call["plan"] == "Hold above 28,030 targets 28,399."
    assert call["wrong_if"] == "Below 27,805"
    assert out["risks"] == ["Iran-Bahrain drone strikes spike oil.",
                            "10Y above 5.2% hits duration.",
                            "Crowded longs (98th percentile) flush."]


def test_a_comment_does_not_say_the_tag_printed_beside_it() -> None:
    """The second real report: "Bullish; NQ 28034.75 above Friday VAH 28,030" under a
    tag that already said Bullish, on every row of both books."""
    out = report.sanitize_brief({
        "thesis": "No live print ahead of the open.",
        "calls": [{"book": "NQ", "open_bias": "leaning bullish", "conviction": 2, "factors": [
            {"key": "structure", "line": "Bullish; NQ above Friday VAH 28,030, acceptance higher."},
            {"key": "rates", "line": "Not live yet; 10Y closed 5.15% Friday."},
            {"key": "catalysts", "line": "Nothing yet: Barr speaks Monday before the bell."},
            {"key": "risk", "line": "Neutral VIX curve at 0.94, normal contango."},
            {"key": "event", "line": "5 stories since the close cap conviction a notch."}]}],
        "today": [{"id": "c1", "note": "Sets the rate tone before the open."},
                  {"id": "c2", "note": "Lands after this session closes; not in play."}],
        "risks": [": Iran escalation in Bahrain spikes oil.", ": crowded longs flush on a break."],
    }, {"books": ["NQ"], "catalysts": [{"id": "c1", "when": "Mon 05:00 ET", "title": "Barr"},
                                       {"id": "c2", "when": "Tue 08:30 ET", "title": "Retail"}]})
    assert out is not None
    assert [f["line"] for f in out["calls"][0]["factors"]] == [
        "NQ above Friday VAH 28,030, acceptance higher.",
        "10Y closed 5.15% Friday.",
        "Barr speaks Monday before the bell.",
        "Neutral VIX curve at 0.94, normal contango.",      # a word of the sentence, not a tag
        "5 stories since the close cap conviction a notch.",
    ]
    # A row listed to say it does not matter is not on the clock.
    assert out["today"] == [{"id": "c1", "note": "Sets the rate tone before the open."}]
    assert out["risks"] == ["Iran escalation in Bahrain spikes oil.",
                            "Crowded longs flush on a break."]
    assert "say it holds for both wrappers" not in report.system_prompt("ny", "indexes")


def test_a_book_priced_in_cents_keeps_them_and_no_ladder_is_no_levels() -> None:
    lad = {"book": "SIL", "dp": 2, "rows": [
        {"price": 49.126, "label": "Last", "kind": "last"},
        {"price": 49.804, "label": "Asia high", "kind": "range"}]}
    lv = report.key_levels({}, "SIL", lad)
    assert lv == {"dp": 2, "marks": [{"price": 49.13, "label": "Last", "kind": "last"},
                                     {"price": 49.8, "label": "Asia high", "kind": "range"}]}
    assert report.key_levels({}, "SIL", None) is None
    assert report.key_levels({}, "SIL", {"dp": 2, "rows": [
        {"price": 50.0, "label": "Call wall", "kind": "gex"}]}) is None


# ---- what the report's model is shown -----------------------------------------------------


def test_the_model_is_shown_no_gamma_and_no_moving_average() -> None:
    facts = {"levels": {"NQ": report.key_levels(_profiles(), "NQ", _ladder())},
             "factors": {"NQ": report.factors_of("NQ", _board())}}
    digest = {
        "gamma_levels": {"NQ": {"regime": "NEG", "flip": 30200}},
        "volume_profile": {"NQ": {"vah": 30400}},
        "brief_tables": {
            "snapshot": [{"key": "NQ", "last": 30120}],
            "gamma": [{"book": "NQ", "regime": "NEG"}],
            "ladders": [{**_ladder(), "fuel": {"text": "0.6 ATR used"},
                         "yesterday": {"text": "a trend day down"},
                         "regime": {"ema200": 28419, "text": "200-day EMA 28,419, below it"},
                         "ema200_10m": {"value": 30310, "slope": "falling"}}],
        },
        "engine_driver_board": {"NQ": {
            "score": -11, "regime": "NEG",
            "treatment": "Lean short NQ. Negative gamma: breaks run.",
            "votes": [{"label": "Dealer gamma", "value": "negative γ"},
                      {"label": "10Y", "value": "4.10%"}]}},
    }
    before = json.dumps(digest)
    view = report.report_view(digest, facts)
    assert json.dumps(digest) == before                       # a copy: Hermes reads it whole
    text = json.dumps(view, ensure_ascii=False).lower()
    assert not re.search(r"gamma|flip|wall|γ|\bema|200-day", text)
    assert view["key_levels"] == facts["levels"]
    assert view["range_so_far"] == {"NQ": {"fuel": {"text": "0.6 ATR used"},
                                          "yesterday": {"text": "a trend day down"}}}
    assert set(view["brief_tables"]) == {"snapshot"}
    assert view["engine_driver_board"]["NQ"] == {
        "score": -11, "votes": [{"label": "10Y", "value": "4.10%"}]}
    assert view["factors_on_the_page"]["NQ"][0] == {
        "key": "structure", "name": "Volume profile & structure", "weight": 33, "tag": "Bullish"}
    assert view["volume_profile"] == {"NQ": {"vah": 30400}}   # the profile is a factor


@pytest.mark.parametrize("session", ["asia", "london", "ny"])
@pytest.mark.parametrize("asset", ["indexes", "GC", "SIL", "CL"])
def test_the_prompt_names_gamma_and_averages_only_to_rule_them_out(session: str,
                                                                   asset: str) -> None:
    for prog in ({"underway": False, "opens_et": "09:30", "phrase": "3h", "hours": "h"},
                 {"underway": True, "opened_et": "09:30", "phrase": "1h", "hours": "h",
                  "minutes_in": 60}):
        p = report.system_prompt(session, asset, prog)
        for line in p.splitlines():
            if re.search(r"gamma|\bflip\b|call wall|put wall", line, re.I):
                assert line.startswith("DEALER GAMMA IS NOT IN THIS REPORT"), line[:120]
            if re.search(r"\b(?:EMAs?|SMAs?|200-day|moving average|trend line)\b", line):
                assert "NO MOVING AVERAGES" in line or "moving average votes" in line, line[:120]
        assert "`factors`" in p and "`why`" not in p


def test_a_stored_report_says_which_shape_it_is() -> None:
    assert report.BRIEF_VERSION == 3
    assert "why" not in report.LIMITS and report.LIMITS["factor"] == 20


def test_an_average_the_model_wrote_anyway_is_put_in_plain_words() -> None:
    out = report.sanitize_brief({
        "thesis": "Below the 200-day EMA the tape is heavy.",
        "calls": [{"book": "NQ", "open_bias": "neutral", "conviction": 1,
                   "factors": [{"key": "structure", "line": "Under the 10m 200 EMA."}]}],
    }, {"books": ["NQ"]})
    assert out is not None
    assert "EMA" not in out["thesis"] and "EMA" not in out["calls"][0]["factors"][0]["line"]


# ---- Hermes reads the rows as the page prints them -----------------------------------------


def test_hermes_reads_a_calls_factors_joined_to_the_engines_rows() -> None:
    rows = report.factors_of("NQ", _board())
    rec = {"thesis": "t", "calls": [{"book": "NQ", "plan": "p", "factors": [
        {"key": "rates", "line": "The 10-year is up 6bp and the dollar firmer."}]}]}
    note = tools._note({"note": rec}, "brief", None, {"factors": {"NQ": rows}})["note"]
    got = note["calls"][0]["factors"]
    assert got[1] == ("Macro (rates & dollar): Bearish, 21% of the score. "
                      "The 10-year is up 6bp and the dollar firmer.")
    # A row the model left without a comment still reads, on the engine's own figures.
    assert got[0] == ("Volume profile & structure: Bullish, 33% of the score. "
                      "Value: above (VAH 30,400); Session: inside Asia's range")
    assert got[-1].startswith("Geopolitics & events (lowers conviction, not a side): 3 stories.")
    assert len(got) == len(rows)
    # A report stored without the rows is returned as it was written.
    bare = tools._note({"note": rec}, "brief", None, {})["note"]
    assert bare["calls"][0]["factors"] == rec["calls"][0]["factors"]


# ---- the stock score: no daily-frame part, and the flag stays ----------------------------


def _row(**kw: Any) -> dict[str, Any]:
    r: dict[str, Any] = {
        "lvl_state": 2, "rs": {"SPY": 0.6, "QQQ": 0.4}, "rvol": 1.6, "range_used": 0.5,
        "setup": {"side": "long", "state": "retest", "level": "PMH", "lost_vwap": False,
                  "entry": {"kind": "PMH", "price": 1.0, "dist_atr": 0.1}},
    }
    r.update(kw)
    return r


def test_the_daily_trend_earns_a_setup_nothing_either_way() -> None:
    reg = {"bias": "long", "confirm": "confirm"}
    up = {"trend": "up", "text": "above the 20, 50 and 200-day"}
    down = {"trend": "down", "text": "below the 20, 50 and 200-day"}
    scores = [scanscore.score_row(_row(), reg, 0.5, None, None, frame_read=fr)
              for fr in (None, up, down, {"trend": "mixed", "text": "between"})]
    assert len({(s["total"], s["raw"]) for s in scores}) == 1
    for s in scores:
        assert "frame" not in {p["key"] for p in s["parts"]}
        assert sum(p["pts"] for p in s["parts"]) == s["raw"]
    assert not hasattr(scanscore, "W_FRAME")


def test_a_setup_against_the_daily_trend_is_still_flagged() -> None:
    down = {"trend": "down", "text": "below the 20, 50 and 200-day"}
    flags = scanscore.flags_for(_row(), None, None, [], [], "rth", frame_read=down)
    frame_flags = [f for f in flags if f.get("kind") == "frame"]
    assert len(frame_flags) == 1 and frame_flags[0]["tone"] == "warn"
    assert frame_flags[0]["text"].startswith("Long into a daily downtrend")
    up = {"trend": "up", "text": "above"}
    assert not [f for f in scanscore.flags_for(_row(), None, None, [], [], "rth", frame_read=up)
                if f.get("kind") == "frame"]
