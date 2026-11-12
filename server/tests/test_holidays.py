"""
The NYSE calendar and the session clock that reads it — the instants the review
of 2026-10-13 found wrong, pinned as they now read (tools/clock_probe.py prints
the same table for a human to check).
"""

from __future__ import annotations

from datetime import UTC, date, datetime, time
from zoneinfo import ZoneInfo

import pytest

from newsterminal import holidays
from newsterminal.sessions import session_state

ET = ZoneInfo("America/New_York")


def st_at(y: int, mo: int, d: int, h: int, mi: int, fold: int = 0) -> dict:
    return session_state(datetime(y, mo, d, h, mi, fold=fold, tzinfo=ET).astimezone(UTC))


def row(st: dict, key: str) -> dict:
    return next(x for x in st["sessions"] if x["key"] == key)


def marker(st: dict, label: str) -> dict | None:
    return next((x for x in st["markers"] if x["label"] == label), None)


# --- the table -------------------------------------------------------------------


def test_the_table_still_covers_this_year() -> None:
    """Fails the year the table runs out — the reminder to extend it."""
    assert holidays.covered(datetime.now(ET).date())


@pytest.mark.parametrize(
    ("d", "trading", "close"),
    [
        (date(2026, 11, 26), False, time(16, 0)),  # Thanksgiving
        (date(2026, 11, 27), True, time(13, 0)),  # the half day after it
        (date(2026, 7, 3), False, time(16, 0)),  # Independence Day, observed
        (date(2027, 6, 18), False, time(16, 0)),  # Juneteenth, observed
        (date(2025, 1, 9), False, time(16, 0)),  # the Carter day of mourning
        (date(2026, 10, 13), True, time(16, 0)),
        (date(2026, 10, 17), False, time(16, 0)),  # a Saturday is not a trading day
        # 2028, from NYSE's page (read 2026-10-14): New Year's Day is a Saturday
        # and is not observed, so Friday Dec 31 2027 and Monday Jan 3 trade.
        (date(2027, 12, 31), True, time(16, 0)),
        (date(2028, 1, 3), True, time(16, 0)),
        (date(2028, 4, 14), False, time(16, 0)),  # Good Friday
        (date(2028, 11, 24), True, time(13, 0)),  # the half day after Thanksgiving
    ],
)
def test_trading_days_and_closes(d: date, trading: bool, close: time) -> None:
    assert holidays.is_trading_day(d) is trading
    assert holidays.close_time(d) == close


def test_next_and_previous_skip_holidays_and_weekends() -> None:
    assert holidays.next_trading_day(date(2026, 11, 25)) == date(2026, 11, 27)
    assert holidays.prev_trading_day(date(2026, 11, 27)) == date(2026, 11, 25)
    assert holidays.next_trading_day(date(2026, 12, 24)) == date(2026, 12, 28)


# --- the bond market, London and Tokyo ---------------------------------------------


def test_the_other_tables_still_cover_today() -> None:
    """Fails the day one of them runs out: SIFMA publishes the next year each December."""
    today = datetime.now(ET).date()
    for name, last in holidays.coverage().items():
        assert today <= date.fromisoformat(last), f"{name} runs out on {last}: read the page again"


def test_veterans_day_shuts_the_bonds_and_not_the_stocks() -> None:
    # Wed 11 Nov 2026: the day the brief quoted Tuesday's +10bp as the day's move.
    d = date(2026, 11, 11)
    assert holidays.is_trading_day(d) is True
    assert holidays.bond_closed(d) == "Veterans Day"
    (row_,) = holidays.notices(d, d)
    assert (row_["label"], row_["kind"], row_["score"]) == ("US bond market closed", "closed", 4)
    assert "Stocks and futures trade as usual" in str(row_["note"])
    # The day before and the day after, bonds trade: no row at all.
    assert holidays.notices(date(2026, 11, 10), date(2026, 11, 10)) == []
    assert holidays.bond_closed(date(2026, 11, 12)) is None


def test_one_row_a_market_a_day_and_what_each_says() -> None:
    by = {(r["date"], r["market"]): r for r in holidays.notices(date(2026, 1, 1), date(2027, 1, 1))}
    # Thanksgiving: stocks and bonds both, futures to their halt; the half day after it.
    assert by[("2026-11-26", "us")]["label"] == "US markets closed"
    assert "13:00 ET halt" in str(by[("2026-11-26", "us")]["note"])
    assert by[("2026-11-27", "us")]["label"] == "Early close · stocks 13:00, bonds 14:00 ET"
    # Christmas: Globex is shut too.
    assert "Globex is shut too" in str(by[("2026-12-25", "us")]["note"])
    # Good Friday 2026: the NYSE shut, the bond market to noon (SIFMA), London shut.
    assert by[("2026-04-03", "us")]["label"] == "NYSE closed · bonds to 12:00 ET"
    assert by[("2026-04-03", "uk")]["label"] == "UK bank holiday"
    # A bond-only early close, and Columbus Day, which the NYSE trades through.
    assert by[("2026-05-22", "us")]["label"] == "Bond market closes early, 14:00 ET"
    assert by[("2026-10-12", "us")]["label"] == "US bond market closed"
    assert by[("2026-10-12", "japan")]["name"] == "Health and Sports Day"
    # London's summer bank holiday is London's alone.
    assert ("2026-08-31", "us") not in by and by[("2026-08-31", "uk")]["region"] == "uk"
    # In date order, the United States first on a shared day.
    rows = holidays.notices(date(2026, 12, 24), date(2026, 12, 31))
    assert [(r["date"], r["market"]) for r in rows] == [
        ("2026-12-24", "us"), ("2026-12-25", "us"), ("2026-12-25", "uk"), ("2026-12-28", "uk"),
        ("2026-12-31", "us"), ("2026-12-31", "japan")]


def test_past_a_tables_end_it_says_nothing() -> None:
    # Columbus Day 2027 is a bond holiday in fact; the table stops at 1 Jan 2027, so no row.
    assert holidays.bond_closed(date(2027, 10, 11)) is None
    assert [r for r in holidays.notices(date(2027, 10, 11), date(2027, 10, 11))] == []
    # The NYSE's own table still answers for 2027.
    assert holidays.notices(date(2027, 11, 25), date(2027, 11, 25))[0]["label"] == "NYSE closed"


# --- the session clock -------------------------------------------------------------


def test_london_keeps_londons_clock_in_the_dst_mismatch_week() -> None:
    """2026-10-26: the UK is on GMT, the US still on EDT — London's 08:00 is 04:00 ET
    and its 07:00, where the London box opens, is 03:00. The marker used to say 5
    minutes beside a London row that said 65."""
    st = st_at(2026, 10, 26, 2, 55)
    assert row(st, "london")["next_min"] == 65           # the LSE's cash open, 08:00 London
    m = marker(st, "London opens")                        # the box, 07:00 London
    assert m is not None and (m["in_min"], m["et"]) == (5, "03:00")
    normal = marker(st_at(2026, 10, 19, 1, 55), "London opens")
    assert normal is not None and (normal["in_min"], normal["et"]) == (5, "02:00")


def test_elapsed_time_counts_the_repeated_hour() -> None:
    """The two 01:30s of 2026-11-01 are an hour apart, and so are their countdowns."""
    first = marker(st_at(2026, 11, 1, 1, 30, fold=0), "Globex open")
    second = marker(st_at(2026, 11, 1, 1, 30, fold=1), "Globex open")
    assert first is not None and second is not None
    assert first["in_min"] - second["in_min"] == 60


def test_markers_skip_the_weekend() -> None:
    """Friday 17:00 is the weekend: no Saturday "London open" in the next four."""
    st = st_at(2026, 10, 16, 17, 0)
    assert st["phase"]["key"] == "weekend"
    assert all(m["in_min"] >= 49 * 60 for m in st["markers"])  # nothing before Sunday 18:00


def test_thanksgiving_is_a_holiday_not_a_new_york_morning() -> None:
    st = st_at(2026, 11, 26, 10, 0)
    assert st["phase"]["key"] == "holiday"
    assert row(st, "newyork")["open"] is False
    assert row(st, "newyork")["holiday"] == "Thanksgiving Day"
    assert marker(st, "NYSE open") is None or marker(st, "NYSE open")["in_min"] > 23 * 60
    assert st["overlap"] is False


def test_the_half_day_closes_at_one() -> None:
    before = st_at(2026, 11, 27, 12, 59)
    assert before["phase"]["key"] == "close"
    assert row(before, "newyork")["open"] is True
    m = marker(before, "New York closes")
    assert m is not None and (m["in_min"], m["et"]) == (1, "13:00")
    after = st_at(2026, 11, 27, 13, 30)
    assert after["phase"]["key"] == "post"
    assert row(after, "newyork")["open"] is False
    assert "early close" in row(after, "newyork")["hours"]
