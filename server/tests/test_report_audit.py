"""
The note generator's audit (2026-11-05): what a note is handed, and how it is
told to weigh it.

Read against the live wire that morning, twenty-one HIGH stories were on the tape
and two of them reached the model, because the headline list was cut by the clock.
The prompt forbade COT and put/call while the driver board printed both. A cash
move from yesterday had no date on it. And the rules for weighing a session lay
across five paragraphs, two of them at odds about macro.
"""

from __future__ import annotations

import re
from datetime import datetime
from typing import Any
from zoneinfo import ZoneInfo

import pytest

from newsterminal import report, stockplan
from newsterminal.sources import cot, earnings

ET = ZoneInfo("America/New_York")
# Thursday 5 November 2026, 05:40 ET: the pre-market, after Wednesday's close.
NOW = datetime(2026, 11, 5, 5, 40, tzinfo=ET)


def _h(title: str, impact: str, region: str, hours_ago: float) -> dict[str, Any]:
    at = NOW.timestamp() - hours_ago * 3600
    return {"title": title, "impact": impact, "region": region, "category": "markets",
            "publisher": "P", "ts": at,
            "utc": datetime.fromtimestamp(at, ET).isoformat(), "url": "u"}


def _snap(wire: list[dict[str, Any]] | None = None) -> dict[str, Any]:
    return {"clock": {"et": NOW.isoformat()}, "wire": wire or []}


def test_every_high_story_reaches_the_model_however_old_the_list_runs() -> None:
    # A newest-first wire: forty fresh medium stories on top of the HIGH ones,
    # each with words of its own so none folds into another.
    words = ["alpha", "bravo", "chart", "delta", "ember", "frost", "glade", "heron", "inlet",
             "joust", "knoll", "lemon"]
    fresh = [_h(f"{words[i % 12]} {words[(i * 5 + 1) % 12]} medium story number{i}x",
                "medium", "global", 0.1 * i) for i in range(40)]
    high = [_h("Fed chair signals emergency cut", "high", "us", 9.0),
            _h("Oil tanker sunk in Hormuz strait", "high", "global", 10.0),
            _h("Nvidia export licence revoked outright", "high", "us", 11.0)]
    rows = report._headlines(_snap([*fresh, *high]), "ny", NOW)
    assert [r["impact"] for r in rows[:3]] == ["high", "high", "high"]
    assert {r["title"] for r in rows[:3]} == {h["title"] for h in high}
    assert len(rows) <= report.HEADLINES_MAX
    assert [r["id"] for r in rows[:2]] == ["h1", "h2"]


def test_one_story_takes_one_row_and_counts_its_tellings() -> None:
    wire = [_h("Bank of England Eyes First Rate Hike Since 2023", "high", "global", 1),
            _h("BOE Poised for First Rate Hike in Three Years", "high", "global", 2),
            _h("Bank of England poised to hike: first rate rise", "high", "global", 3),
            _h("Israel strikes southern Lebanon again", "high", "global", 4)]
    rows = report._headlines(_snap(wire), "london", NOW)
    assert len(rows) == 2 and rows[0]["also"] == 2 and "also" not in rows[1]


def test_since_the_close_outranks_older_and_home_outranks_elsewhere() -> None:
    wire = [_h("Old medium from home turf", "medium", "us", 40),
            _h("Tokyo press conference fresh", "medium", "apac", 2),
            _h("Washington budget fresh today", "medium", "us", 3)]
    titles = [r["title"] for r in report._headlines(_snap(wire), "ny", NOW)]
    assert titles == ["Washington budget fresh today", "Tokyo press conference fresh",
                      "Old medium from home turf"]


def test_medium_stories_from_elsewhere_are_capped_and_high_never_is() -> None:
    words = ["amber", "birch", "cedar", "dune", "elm", "fern", "gorse", "hazel", "iris",
             "juniper", "kelp", "larch", "moss"]
    wire = [_h(f"{w} press", "medium", "apac", 1.0 + i)
            for i, w in enumerate(words)]
    wire += [_h(f"{w} crisis", "high", "apac", 1.0 + i)
             for i, w in enumerate(words[:10])]
    rows = report._headlines(_snap(wire), "ny", NOW)
    assert sum(r["impact"] == "high" for r in rows) == 10
    assert sum(r["impact"] == "medium" for r in rows) == report.HEADLINES_ELSEWHERE


# ---- the prompt ------------------------------------------------------------------------

PROG_PRE = {"underway": False, "opens_et": "09:30", "phrase": "3h 50m", "hours": "09:30–16:00 ET"}
PROG_LIVE = {"underway": True, "opened_et": "09:30", "phrase": "1h", "hours": "09:30–16:00 ET",
             "minutes_in": 60}


@pytest.mark.parametrize(
    ("session", "prog", "first", "positioning_role"),
    [("asia", PROG_LIVE, "Session tape", "a reference"),
     ("london", PROG_LIVE, "Session tape", "a reference"),
     ("ny", PROG_PRE, "Macro", "who is crowded"),
     ("ny", PROG_LIVE, "Structure", "who is crowded")],
)
def test_the_layers_weigh_by_session(session: str, prog: dict[str, Any], first: str,
                                     positioning_role: str) -> None:
    layers = report.session_layers(session, prog)
    assert layers[0][0] == first
    # Positioning is COT and put/call in every session: dealer gamma left the report
    # (2026-11-15), so no row says it "sets how far" or is "decisive", and no row
    # names a moving average.
    assert next(role for name, role, _ in layers if name == "Positioning") == positioning_role
    assert not any(re.search(r"\b(?:gamma|emas?|daily frame|200-day)\b",
                             f"{name} {role} {what}", re.I) for name, role, what in layers)
    # Macro stays in every table: the owner's rule that the US is the anchor.
    assert any(name == "Macro" for name, _, _ in layers)
    text = report.system_prompt(session, "all", prog)
    assert "HOW THE LAYERS WEIGH IN THIS NOTE" in text
    assert f"1. {first}" in text


def test_the_prompt_no_longer_forbids_what_the_board_prints() -> None:
    text = report.system_prompt("ny", "all", PROG_PRE)
    banned = text.split("WHAT THIS DATA DOES NOT HAVE:")[1].split("Never mention them")[0]
    assert "COT" not in banned and "put/call" not in banned
    assert "the weekly COT and the Cboe" in text
    # And the thin tape no longer tells it to weigh macro down in so many words.
    assert "the macro story down" not in report.system_prompt("asia", "all", PROG_LIVE)
    assert "THE NEWS IS DATA" in text and "EARNINGS HAVE A CLOCK" in text
    assert "index points)" not in text


def test_the_digest_carries_positioning_the_weighting_and_a_date_on_cash_moves() -> None:
    snap = {
        **_snap(),
        "cot": {"books": {
            "NQ": {"ok": True, "spec": "Leveraged funds", "as_of": "2026-10-27", "net": -5619,
                   "chg": 2069, "pct_oi": -2.0, "pctile": 92, "word": "crowded long",
                   "read": "crowded", "weeks": 60},
            "GC": {"ok": True, "spec": "Managed money", "as_of": "2026-10-27", "net": 10,
                   "chg": 1, "pct_oi": 1.0, "pctile": 50, "word": "middling", "read": "m"},
            "ES": {"ok": False}}},
        "putcall": {"date": "2026-11-04", "ratios": {"equity": 0.44}, "avg20": {"equity": 0.59},
                    "pctile": {"equity": 6}, "read": {"equity": "call-heavy"}, "days": [1, 2]},
    }
    d = report.build_digest(snap, "ny", "all")
    assert set(d["positioning"]["cot_weekly"]) == {"NQ", "GC"}
    assert d["positioning"]["cot_weekly"]["NQ"]["pctile"] == 92
    assert "days" not in d["positioning"]["cboe_put_call"]
    assert d["session_weighting"][0].startswith("Macro: ")
    assert d["cash_moves_basis"].startswith("the regular session of Wed 04 Nov")
    # A gold note is not told about the equity put/call.
    gold = report.build_digest(snap, "ny", "GC")
    assert set(gold["positioning"]["cot_weekly"]) == {"GC"}
    assert "cboe_put_call" not in gold["positioning"]


@pytest.mark.parametrize(
    ("hour", "minute", "live"),
    [(9, 29, False), (9, 30, True), (15, 59, True), (16, 0, False), (20, 0, False)],
)
def test_cash_moves_are_today_only_inside_the_session(hour: int, minute: int, live: bool) -> None:
    got = report._cash_moves_basis(datetime(2026, 11, 5, hour, minute, tzinfo=ET))
    assert got.startswith("today's") is live
    weekend = report._cash_moves_basis(datetime(2026, 11, 7, 12, 0, tzinfo=ET))
    assert weekend.startswith("the regular session of Fri 06 Nov")


# ---- the game plan ---------------------------------------------------------------------


def test_the_plan_reads_one_row_per_story_back_to_the_close() -> None:
    wire = [_h("Bank of England Eyes First Rate Hike Since 2023", "high", "global", 1),
            _h("BOE Poised for First Rate Hike in Three Years", "high", "global", 2),
            _h("Israel strikes southern Lebanon again", "high", "global", 3),
            # 13.6 hours old: outside the old twelve-hour window, inside the close.
            _h("Democrats sweep the midterm elections", "high", "us", 13.6),
            _h("A medium story is not on this list", "medium", "us", 1)]
    got = stockplan.macro_headlines(wire, NOW)
    assert [r["title"][:6] for r in got] == ["Bank o", "Israel", "Democr"]
    assert [r["id"] for r in got] == ["m1", "m2", "m3"]
    # Monday's plan can see the weekend.
    monday = datetime(2026, 11, 9, 8, 0, tzinfo=ET)
    sat = {"title": "Weekend strike on refinery", "impact": "high",
           "utc": datetime(2026, 11, 7, 12, 0, tzinfo=ET).isoformat()}
    assert stockplan.macro_headlines([sat], monday)[0]["title"].startswith("Weekend")


def test_the_plan_digest_carries_the_put_call_when_it_has_one() -> None:
    assert stockplan._put_call(None) is None
    assert stockplan._put_call({"ratios": {}}) is None
    got = stockplan._put_call({"date": "d", "ratios": {"equity": 0.44}, "avg20": {}, "read": {},
                               "days": [1]})
    assert got is not None and "days" not in got


# ---- the earnings feed -----------------------------------------------------------------


@pytest.mark.parametrize(
    ("actual", "forecast", "want"),
    [("$1.84", "$1.68", 9.52),            # Nasdaq's own figure for AMD
     ("$0.15", "$0.22", -31.82),          # ARM, with "N/A" beside it on the page
     ("($0.10)", "($0.17)", 41.18),       # a smaller loss is a beat
     ("($0.20)", "($0.17)", -17.65),
     ("$1.00", None, None), (None, "$1.00", None), ("$1.00", "$0.00", None), ("N/A", "$1", None)],
)
def test_a_surprise_is_worked_out_when_the_page_has_none(
    actual: str | None, forecast: str | None, want: float | None
) -> None:
    assert earnings.surprise_of(actual, forecast) == want


def test_parse_day_keeps_nasdaqs_surprise_and_fills_a_missing_one() -> None:
    doc = {"data": {"rows": [
        {"symbol": "ARM", "name": "Arm", "time": "time-after-hours", "epsForecast": "$0.22",
         "eps": "$0.15", "surprise": "N/A", "marketCap": "$215,460,545,000"},
        {"symbol": "AMD", "name": "AMD", "time": "time-not-supplied", "epsForecast": "$1.68",
         "eps": "$1.84", "surprise": "9.5", "marketCap": "$790,000,000,000"},
        {"symbol": "COP", "name": "Conoco", "time": "time-pre-market", "epsForecast": "$3.06",
         "marketCap": "$173,473,137,000"},
    ]}}
    rows = {r["symbol"]: r for r in earnings.parse_day(doc, "2026-11-04")}
    assert rows["ARM"]["surprise_pct"] == -31.82 and rows["ARM"]["when"] == "after"
    assert rows["AMD"]["surprise_pct"] == 9.5
    assert rows["COP"]["surprise_pct"] is None and rows["COP"]["eps_actual"] is None


def test_a_percentile_has_its_right_ordinal() -> None:
    assert [cot.ordinal(n) for n in (1, 2, 3, 4, 11, 12, 13, 21, 92, 100)] == [
        "1st", "2nd", "3rd", "4th", "11th", "12th", "13th", "21st", "92nd", "100th"]
