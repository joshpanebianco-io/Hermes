"""
The NYSE's calendar — the days the cash market is shut, and the days it shuts early.

WHY A HAND-KEPT TABLE, when everything else here is derived. The session clock,
the volume profiles and the scanner all have to know whether New York is
trading, and every way of guessing it went wrong in the review of 2026-10-13:
the session clock printed "NY morning" and the New York row OPEN on
Thanksgiving; the profiles would have called Thanksgiving's thin futures
session Friday's "previous RTH"; and the scanner's own guess (no SPY print by
04:30) read the first half hour of every holiday as a pre-market. A holiday is
a published fact, not an inference from the tape — so it is written down.

THE SOURCE. https://www.nyse.com/markets/hours-calendars (2026 and 2027, read
2026-10-13; 2028, read 2026-10-14), and Kiplinger's 2025 table for the 2025
early closes. 2025-01-09 —
the national day of mourning for President Carter, when the NYSE closed — is
not on any recurring calendar and is listed by hand.

IT RUNS OUT. The table covers 2025–2028 and says so (`covered`); a date past it
falls back to "every weekday trades", which is what this code did before the
table existed. tests/test_holidays.py fails once the current year is no longer
covered, which is the reminder to extend it.

CME'S GLOBEX KEEPS ITS OWN HOURS, and the two tables at the foot say which
(review, 2026-10-14: the brief called Thanksgiving morning "NY underway"). On
most NYSE holidays the equity-index and metal futures still trade — an
abbreviated session that halts at 13:00 ET — so Asia and London happen as
usual. Only Christmas, New Year's Day and Good Friday shut Globex outright,
and on the cash market's half days the futures halt at 13:15 ET.
"""

from __future__ import annotations

from datetime import date, time, timedelta

HOLIDAYS: dict[date, str] = {
    # 2025
    date(2025, 1, 1): "New Year's Day",
    date(2025, 1, 9): "National Day of Mourning (President Carter)",
    date(2025, 1, 20): "Martin Luther King, Jr. Day",
    date(2025, 2, 17): "Washington's Birthday",
    date(2025, 4, 18): "Good Friday",
    date(2025, 5, 26): "Memorial Day",
    date(2025, 6, 19): "Juneteenth",
    date(2025, 7, 4): "Independence Day",
    date(2025, 9, 1): "Labor Day",
    date(2025, 11, 27): "Thanksgiving Day",
    date(2025, 12, 25): "Christmas Day",
    # 2026
    date(2026, 1, 1): "New Year's Day",
    date(2026, 1, 19): "Martin Luther King, Jr. Day",
    date(2026, 2, 16): "Washington's Birthday",
    date(2026, 4, 3): "Good Friday",
    date(2026, 5, 25): "Memorial Day",
    date(2026, 6, 19): "Juneteenth",
    date(2026, 7, 3): "Independence Day (observed)",
    date(2026, 9, 7): "Labor Day",
    date(2026, 11, 26): "Thanksgiving Day",
    date(2026, 12, 25): "Christmas Day",
    # 2027
    date(2027, 1, 1): "New Year's Day",
    date(2027, 1, 18): "Martin Luther King, Jr. Day",
    date(2027, 2, 15): "Washington's Birthday",
    date(2027, 3, 26): "Good Friday",
    date(2027, 5, 31): "Memorial Day",
    date(2027, 6, 18): "Juneteenth (observed)",
    date(2027, 7, 5): "Independence Day (observed)",
    date(2027, 9, 6): "Labor Day",
    date(2027, 11, 25): "Thanksgiving Day",
    date(2027, 12, 24): "Christmas Day (observed)",
    # 2028 — New Year's Day falls on a Saturday and is not observed.
    date(2028, 1, 17): "Martin Luther King, Jr. Day",
    date(2028, 2, 21): "Washington's Birthday",
    date(2028, 4, 14): "Good Friday",
    date(2028, 5, 29): "Memorial Day",
    date(2028, 6, 19): "Juneteenth",
    date(2028, 7, 4): "Independence Day",
    date(2028, 9, 4): "Labor Day",
    date(2028, 11, 23): "Thanksgiving Day",
    date(2028, 12, 25): "Christmas Day",
}

# Days the cash market closes at 13:00 ET.
EARLY_CLOSES: dict[date, str] = {
    date(2025, 7, 3): "Day before Independence Day",
    date(2025, 11, 28): "Day after Thanksgiving",
    date(2025, 12, 24): "Christmas Eve",
    date(2026, 11, 27): "Day after Thanksgiving",
    date(2026, 12, 24): "Christmas Eve",
    date(2027, 11, 26): "Day after Thanksgiving",
    date(2028, 7, 3): "Day before Independence Day",
    date(2028, 11, 24): "Day after Thanksgiving",
}

EARLY_CLOSE = time(13, 0)
REGULAR_CLOSE = time(16, 0)
COVERED_YEARS = range(2025, 2029)


def covered(d: date) -> bool:
    """Is `d` inside the years this table was written for?"""
    return d.year in COVERED_YEARS


def holiday_name(d: date) -> str | None:
    return HOLIDAYS.get(d)


def is_holiday(d: date) -> bool:
    """A weekday the NYSE does not open. Weekends are not holidays — they are weekends."""
    return d in HOLIDAYS


def is_trading_day(d: date) -> bool:
    return d.weekday() < 5 and d not in HOLIDAYS


def early_close(d: date) -> time | None:
    """13:00 on a half day, otherwise None."""
    return EARLY_CLOSE if d in EARLY_CLOSES else None


def close_time(d: date) -> time:
    """When the regular session ends on `d` — 13:00 on a half day, else 16:00."""
    return early_close(d) or REGULAR_CLOSE


def close_minute(d: date) -> int:
    """`close_time` as minutes of the ET day."""
    t = close_time(d)
    return t.hour * 60 + t.minute


def next_trading_day(d: date) -> date:
    """The first trading day strictly after `d`."""
    d += timedelta(days=1)
    while not is_trading_day(d):
        d += timedelta(days=1)
    return d


def prev_trading_day(d: date) -> date:
    """The last trading day strictly before `d`."""
    d -= timedelta(days=1)
    while not is_trading_day(d):
        d -= timedelta(days=1)
    return d


# ---------------------------------------------------------------- CME Globex
#
# The trade dates with NO Globex session for the equity-index and metal
# futures: no reopen the evening before, no Asia, no London. Christmas and New
# Year's Day every year; Good Friday where CME closed (2025) or is expected to
# (2027, 2028). 2026's Good Friday is left off unverified — it was payrolls
# day, and it is past.
CME_CLOSED: dict[date, str] = {
    date(2025, 1, 1): "New Year's Day",
    date(2025, 4, 18): "Good Friday",
    date(2025, 12, 25): "Christmas Day",
    date(2026, 1, 1): "New Year's Day",
    date(2026, 12, 25): "Christmas Day",
    date(2027, 1, 1): "New Year's Day",
    date(2027, 3, 26): "Good Friday",
    date(2027, 12, 24): "Christmas Day (observed)",
    date(2028, 4, 14): "Good Friday",
    date(2028, 12, 25): "Christmas Day",
}

# Where an abbreviated Globex trade date halts, in ET: 13:00 on an NYSE holiday
# CME does not close for, 13:15 on the cash market's half days.
CME_HOLIDAY_HALT = time(13, 0)
CME_EARLY_HALT = time(13, 15)


def cme_closed(d: date) -> bool:
    """Is `d` a weekday trade date with no Globex session at all?"""
    return d in CME_CLOSED


def cme_halt(d: date) -> time | None:
    """When trade date `d`'s Globex session halts early, or None for a full day."""
    if d in CME_CLOSED:
        return time(0, 0)
    if d in HOLIDAYS:
        return CME_HOLIDAY_HALT
    if d in EARLY_CLOSES:
        return CME_EARLY_HALT
    return None
