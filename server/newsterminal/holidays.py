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

from datetime import date, datetime, time, timedelta

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


# ---------------------------------------------------------------- the news day
#
# WHEN TODAY'S NEWS STARTS (quant audit, 2026-11-13). The score counted a headline for
# sixteen hours back from NOW, so a story at 16:05 left the score at 08:05 the next
# morning, before the open it was the reason for, and on a Monday nothing from Friday's
# close counted anywhere. The news a session trades on is everything since the previous
# session's close: a weekend and a holiday are skipped, a half day closes at 13:00, and
# the last half hour of that session is included, because a story at 15:45 moved the
# close and the next open alike.
NEWS_MARGIN_MIN = 30
#: The ET minute the news day rolls to the next trading day: 20:00, when the scanner's
#: own day rolls (the after-hours session is over).
NEWS_ROLL_MIN = 20 * 60


def news_day(et: datetime) -> date:
    """The trading day a moment's news is for: today until 20:00 ET on a trading day,
    else the next trading day (weekends and holidays included). Pure; `et` in New York
    time."""
    d = et.date()
    if is_trading_day(d) and et.hour * 60 + et.minute < NEWS_ROLL_MIN:
        return d
    return next_trading_day(d)


def news_since(et: datetime, day: date | None = None) -> datetime:
    """When the news for `day` (else the day `et` falls in, `news_day`) starts: the
    previous trading day's regular close, NEWS_MARGIN_MIN before it. Monday's starts at
    Friday's close, the day after Thanksgiving's at Wednesday's. Pure; `et` aware, in
    New York time, and the answer in the same zone."""
    prev = prev_trading_day(day or news_day(et))
    m = close_minute(prev) - NEWS_MARGIN_MIN
    return datetime(prev.year, prev.month, prev.day, m // 60, m % 60, tzinfo=et.tzinfo)


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


# ------------------------------------------------- the bond market, London, Tokyo
#
# THE OTHER CALENDARS THE DESK TRADES THROUGH (owner, 2026-11-12: "macro section
# doesnt list bank holidays etc?"). It did not, and nothing else here knew them
# either. On Wed 11 Nov 2026, Veterans Day, stocks traded and the cash Treasury
# market did not: the 10-year never printed, Treasury published no curve, and the
# evening's brief quoted Tuesday's +10bp as the day's move and leaned on it. A day
# the bond market is shut is a fact about every rates read on the page, and a day
# London or Tokyo is shut is a fact about how thin that session is.
#
# THE BOND MARKET KEEPS SIFMA'S RECOMMENDED CLOSES, not the NYSE's table: it shuts
# for Columbus Day and Veterans Day when stocks trade, and where the NYSE shuts for
# Good Friday 2026 it closes at noon. Early closes are 14:00 ET unless listed.
#
# THE SOURCES, all read 2026-11-12:
#   US bonds  https://www.sifma.org/resources/general/holiday-schedule/ (US
#             section): 2026 in full and New Year's Day 2027. The rest of 2027 was
#             not yet published.
#   UK        https://www.gov.uk/bank-holidays.json, the england-and-wales
#             division: 2026 to 2028.
#   Japan     the same SIFMA page's Japan section, its Japanese holidays only (it
#             also lists the US and UK closes its members observe): 2026 and New
#             Year's Day 2027.
#
# THEY RUN OUT, each at its own date (`*_COVERED`), and past it the calendar says
# nothing rather than guessing. tests/test_holidays.py fails once today is past a
# table's end, which is the reminder to read the page again.
BOND_HOLIDAYS: dict[date, str] = {
    date(2026, 1, 1): "New Year's Day",
    date(2026, 1, 19): "Martin Luther King Day",
    date(2026, 2, 16): "Presidents Day",
    date(2026, 5, 25): "Memorial Day",
    date(2026, 6, 19): "Juneteenth",
    date(2026, 7, 3): "Independence Day (observed)",
    date(2026, 9, 7): "Labor Day",
    date(2026, 10, 12): "Columbus Day",
    date(2026, 11, 11): "Veterans Day",
    date(2026, 11, 26): "Thanksgiving Day",
    date(2026, 12, 25): "Christmas Day",
    date(2027, 1, 1): "New Year's Day",
}
#: The bond market's early closes: when, and the holiday the page lists it under.
BOND_EARLY: dict[date, tuple[time, str]] = {
    date(2026, 4, 3): (time(12, 0), "Good Friday"),
    date(2026, 5, 22): (time(14, 0), "Friday before Memorial Day"),
    date(2026, 7, 2): (time(14, 0), "Day before Independence Day (observed)"),
    date(2026, 11, 27): (time(14, 0), "Day after Thanksgiving"),
    date(2026, 12, 24): (time(14, 0), "Christmas Eve"),
    date(2026, 12, 31): (time(14, 0), "New Year's Eve"),
}
BOND_COVERED = (date(2026, 1, 1), date(2027, 1, 1))

UK_HOLIDAYS: dict[date, str] = {
    date(2026, 1, 1): "New Year's Day",
    date(2026, 4, 3): "Good Friday",
    date(2026, 4, 6): "Easter Monday",
    date(2026, 5, 4): "Early May bank holiday",
    date(2026, 5, 25): "Spring bank holiday",
    date(2026, 8, 31): "Summer bank holiday",
    date(2026, 12, 25): "Christmas Day",
    date(2026, 12, 28): "Boxing Day (substitute day)",
    date(2027, 1, 1): "New Year's Day",
    date(2027, 3, 26): "Good Friday",
    date(2027, 3, 29): "Easter Monday",
    date(2027, 5, 3): "Early May bank holiday",
    date(2027, 5, 31): "Spring bank holiday",
    date(2027, 8, 30): "Summer bank holiday",
    date(2027, 12, 27): "Christmas Day (substitute day)",
    date(2027, 12, 28): "Boxing Day (substitute day)",
    date(2028, 1, 3): "New Year's Day (substitute day)",
    date(2028, 4, 14): "Good Friday",
    date(2028, 4, 17): "Easter Monday",
    date(2028, 5, 1): "Early May bank holiday",
    date(2028, 5, 29): "Spring bank holiday",
    date(2028, 8, 28): "Summer bank holiday",
    date(2028, 12, 25): "Christmas Day",
    date(2028, 12, 26): "Boxing Day",
}
UK_COVERED = (date(2026, 1, 1), date(2028, 12, 31))

JP_HOLIDAYS: dict[date, str] = {
    date(2026, 1, 1): "New Year's Day",
    date(2026, 1, 2): "Bank Holiday",
    date(2026, 1, 12): "Coming-of-Age Day",
    date(2026, 2, 11): "National Foundation Day",
    date(2026, 2, 23): "Emperor's Birthday",
    date(2026, 3, 20): "Vernal Equinox Day",
    date(2026, 4, 29): "Showa Day",
    date(2026, 5, 4): "Greenery Day",
    date(2026, 5, 5): "Children's Day",
    date(2026, 5, 6): "Constitution Day (observed)",
    date(2026, 7, 20): "Marine Day",
    date(2026, 8, 11): "Mountain Day",
    date(2026, 9, 21): "Respect-for-the-Aged Day",
    date(2026, 9, 22): "Silver Week bridge holiday",
    date(2026, 9, 23): "Autumnal Equinox",
    date(2026, 10, 12): "Health and Sports Day",
    date(2026, 11, 3): "Culture Day",
    date(2026, 11, 23): "Labour Thanksgiving Day",
    date(2026, 12, 31): "Bank Holiday",
    date(2027, 1, 1): "New Year's Day",
}
JP_COVERED = (date(2026, 1, 1), date(2027, 1, 1))


def bond_closed(d: date) -> str | None:
    """The holiday the cash Treasury market is shut for on `d`, or None: a day it
    trades, or one past the end of the table."""
    return BOND_HOLIDAYS.get(d)


def _hm(t: time) -> str:
    return f"{t.hour:02d}:{t.minute:02d}"


def _us_notice(d: date) -> dict[str, object] | None:
    """What is shut or shut early in the United States on `d`, as one row."""
    stock, half = HOLIDAYS.get(d), EARLY_CLOSES.get(d)
    bond, bond_half = BOND_HOLIDAYS.get(d), BOND_EARLY.get(d)
    if not (stock or half or bond or bond_half):
        return None
    futures = ("Globex is shut too." if d in CME_CLOSED
               else "Index and metal futures trade to a 13:00 ET halt.")
    if stock and bond:
        name, kind, score, label = stock, "closed", 5, "US markets closed"
        note = f"The NYSE and the bond market are shut. {futures}"
    elif stock:
        name, kind, score = stock, "closed", 5
        label = (f"NYSE closed · bonds to {_hm(bond_half[0])} ET" if bond_half else "NYSE closed")
        note = (f"The NYSE is shut{' and the bond market closes early' if bond_half else ''}. "
                f"{futures}")
    elif bond:
        name, kind, score, label = bond, "closed", 4, "US bond market closed"
        note = ("Stocks and futures trade as usual. Cash Treasuries do not: the 10-year does "
                "not print and Treasury publishes no curve for the day, so every yield on the "
                "page is the session before's.")
    elif half and bond_half:
        name, kind, score = half, "early", 3
        label = f"Early close · stocks 13:00, bonds {_hm(bond_half[0])} ET"
        note = "The NYSE closes at 13:00 ET and index futures halt at 13:15; a thin afternoon."
    elif half:
        name, kind, score, label = half, "early", 3, "NYSE closes early, 13:00 ET"
        note = "The NYSE closes at 13:00 ET and index futures halt at 13:15; a thin afternoon."
    else:
        assert bond_half is not None
        name, kind, score = bond_half[1], "early", 3
        label = f"Bond market closes early, {_hm(bond_half[0])} ET"
        note = "Stocks trade the full day. Cash Treasuries stop early, so the rates reads go quiet."
    return {"date": d.isoformat(), "market": "us", "country": "United States", "region": "us",
            "name": name, "kind": kind, "label": label, "note": note, "score": score}


def notices(lo: date, hi: date) -> list[dict[str, object]]:
    """Every day from `lo` to `hi` a market the desk trades through is shut or shuts
    early, in date order: the United States (stocks, bonds, or both, as one row), then
    London, then Tokyo. A day outside a table's years has no row from it. Pure."""
    out: list[dict[str, object]] = []
    d = lo
    while d <= hi:
        us = _us_notice(d)
        if us:
            out.append(us)
        uk = UK_HOLIDAYS.get(d)
        if uk:
            out.append({
                "date": d.isoformat(), "market": "uk", "country": "United Kingdom",
                "region": "uk", "name": uk, "kind": "closed", "label": "UK bank holiday",
                "note": "London's cash markets are shut: no UK data, and a thinner London "
                        "session in the futures.",
                "score": 3})
        jp = JP_HOLIDAYS.get(d)
        if jp:
            out.append({
                "date": d.isoformat(), "market": "japan", "country": "Japan", "region": "apac",
                "name": jp, "kind": "closed", "label": "Japan holiday",
                "note": "Tokyo's cash markets are shut: no Japan data, and a thinner Asia "
                        "session in the futures.",
                "score": 3})
        d += timedelta(days=1)
    return out


def coverage() -> dict[str, str]:
    """The last day each of the other tables answers for, for the tests and the page."""
    return {"us_bonds": BOND_COVERED[1].isoformat(), "uk": UK_COVERED[1].isoformat(),
            "japan": JP_COVERED[1].isoformat()}
