"""
What the brief is handed, where a sign or a date could be read the wrong way (owner,
2026-11-12: "fix catalyst and read weighting - 10y yield etc and gamma levels incorrect
bias - positive doesnt mean bullish and vice versa").

The worked day is Wed 11 Nov 2026, Veterans Day: stocks traded, the bond market did not,
and the evening's brief wrote Tuesday's +10bp as the day's move in the 10-year.
"""

from __future__ import annotations

from datetime import date, datetime
from typing import Any
from zoneinfo import ZoneInfo

from newsterminal import drivers, report, tools

ET = ZoneInfo("America/New_York")
TUESDAYS_CURVE = {"as_of": "11/10/2026"}


# ---- the curve has a date --------------------------------------------------------------


def test_on_a_bond_holiday_the_curve_says_whose_day_it_is() -> None:
    got = report.curve_date(TUESDAYS_CURVE, date(2026, 11, 11))
    assert got["curve_as_of"] == "Tue 10 Nov"
    assert "THAT day's change" in got["curve_basis"] and "not today's" in got["curve_basis"]
    assert got["cash_treasuries_today"].startswith("shut all day (Veterans Day)")


def test_the_morning_after_it_names_the_day_with_no_curve() -> None:
    # Thursday morning: the latest curve is still Tuesday's, because Wednesday had none.
    got = report.curve_date(TUESDAYS_CURVE, date(2026, 11, 12))
    assert "curve_basis" in got and "cash_treasuries_today" not in got
    assert got["cash_treasuries_last_shut"] == "Wed 11 Nov (Veterans Day): there is no curve for it"


def test_todays_curve_needs_no_warning_and_a_missing_date_says_nothing() -> None:
    assert report.curve_date({"as_of": "11/10/2026"}, date(2026, 11, 10)) == {
        "curve_as_of": "Tue 10 Nov"}
    # An ordinary next morning: yesterday's curve, dated, and no holiday to name.
    monday = report.curve_date({"as_of": "11/06/2026"}, date(2026, 11, 9))
    assert set(monday) == {"curve_as_of", "curve_basis"}
    assert report.curve_date({}, date(2026, 11, 11)) == {}
    assert report.curve_date({"as_of": "soon"}, date(2026, 11, 11)) == {}


def test_the_10_year_cannot_vote_on_a_bond_holiday() -> None:
    quotes = [{"key": "US10Y", "last": 4.998, "chg": 0.08, "feed": "live"}]
    shut = drivers._yields(quotes, "NQ", date(2026, 11, 11))
    assert shut["live"] is False and shut["vote"] == "neutral"
    assert "shut today (Veterans Day)" in shut["note"]
    # The same figure the day before is a vote, and a rise is a headwind: never a long.
    open_ = drivers._yields(quotes, "NQ", date(2026, 11, 10))
    assert (open_["live"], open_["vote"]) == (True, "short")
    assert drivers._yields(quotes, "GC", date(2026, 11, 10))["vote"] == "short"
    falling = [{"key": "US10Y", "last": 4.90, "chg": -0.08, "feed": "live"}]
    assert drivers._yields(falling, "NQ", date(2026, 11, 10))["vote"] == "long"


# ---- what is high impact for the books ---------------------------------------------------


def _row(event: str, score: int) -> dict[str, Any]:
    return {"event": event, "score": score}


def test_high_impact_is_for_the_books_not_for_whoever_published() -> None:
    high = report.high_for_the_books
    # A US tier-one print stops the tape; the same print abroad is listed, not lit.
    assert high([_row("Initial Jobless Claims", 5)]) is True
    assert high([_row("GDP q/q", 4)]) is False                 # the UK's, or the Euro Zone's
    assert high([_row("PPI m/m", 4)]) is False                 # Japan's
    # A central bank's decision reaches every book, wherever it is made.
    assert high([_row("BoJ Interest Rate Decision", 4)]) is True
    assert high([_row("ECB Monetary Policy Statement", 4)]) is True
    # A speech is high only when it is the Chair's.
    assert high([_row("FOMC Member Barr Speaks", 5)]) is False
    assert high([_row("FOMC Chair Powell Speaks", 5)]) is True
    assert high([_row("FOMC Vice Chair Jefferson Speaks", 5)]) is False
    # One release, several series: any one of them can light it.
    assert high([_row("CPI y/y", 3), _row("Core CPI m/m", 5)]) is True


# ---- the catalysts: one row a speech, and the holidays -----------------------------------


def _snap(now: datetime) -> dict[str, Any]:
    at = now.replace(hour=10, minute=0).timestamp() + 86400
    return {
        "calendar": [{
            "event": "FOMC Member Barr Speaks", "country": "United States", "ts": at,
            "score": 5, "core": True, "released": False, "session": "ny",
            "actual_raw": None, "consensus_raw": None, "previous_raw": None, "surprise": None}],
        "fed": [{"kind": "Speech", "title": "Speech - Governor Michael S. Barr", "ts": at,
                 "date": "2026-11-12", "major": True,
                 "note": "Artificial Intelligence and Inequality"}],
    }


def test_one_speech_is_one_catalyst_and_keeps_what_it_is_about() -> None:
    now = datetime(2026, 11, 11, 19, 30, tzinfo=ET)
    cats = [c for c in report._catalysts(_snap(now), ["NQ"], now) if c["kind"] != "holiday"]
    assert [c["title"] for c in cats] == ["FOMC Member Barr Speaks"]
    assert cats[0]["note"] == "Artificial Intelligence and Inequality"
    assert cats[0]["high"] is False                            # a governor, not the Chair


def test_todays_holiday_heads_the_catalysts_all_day() -> None:
    now = datetime(2026, 11, 11, 19, 30, tzinfo=ET)
    cats = report._catalysts(_snap(now), ["NQ"], now)
    first = cats[0]
    assert (first["kind"], first["id"], first["when"]) == ("holiday", "c1", "Today all day")
    assert first["title"] == "US bond market closed · Veterans Day"
    assert first["released"] is False and "10-year does not print" in first["note"]
    # A quiet week has none.
    calm = datetime(2026, 11, 4, 9, 0, tzinfo=ET)
    assert [c for c in report._catalysts({}, ["NQ"], calm) if c["kind"] == "holiday"] == []


# ---- Hermes's calendar lists them too ----------------------------------------------------


def test_the_calendar_tool_lists_the_holidays_ahead() -> None:
    body = tools._calendar({"calendar": []}, "2026-11-11")
    shut = body["market_holidays_from_this_day"]
    assert shut[0].startswith("2026-11-11 · US bond market closed · Veterans Day")
    assert any("2026-11-26 · US markets closed · Thanksgiving Day" in s for s in shut)
