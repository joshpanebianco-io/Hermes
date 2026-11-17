"""
The two rules here are invertible — wrong in a way that still looks right.

`volterm` decides which end of the curve means trouble. Flip the ratio and it
reports calm during a panic, with no error and no missing data. `fedcal` turns
"3,4" into a date; read the wrong end and a two-day FOMC lands on its second
day, a day late for anyone positioning into it.
"""

from __future__ import annotations

from datetime import date

import pytest

from newsterminal import volterm
from newsterminal.sources import fedcal


def q(key: str, last: float, pct: float | None = None) -> dict:
    return {"key": key, "last": last, "pct": pct}


# --- volterm -----------------------------------------------------------------


@pytest.mark.parametrize(
    ("vix", "vix3m", "shape"),
    [
        # The calm shape: the quarter prices more vol than the month.
        (15.0, 18.0, "contango"),
        # The stressed shape: the month overtakes the quarter.
        (28.0, 22.0, "backwardation"),
        # Inside FLAT_BAND either side of 1.00 — not saying anything yet.
        (20.0, 20.0, "flat"),
        (20.1, 20.0, "flat"),
        (19.9, 20.0, "flat"),
    ],
)
def test_shape_follows_the_ratio(vix: float, vix3m: float, shape: str) -> None:
    st = volterm.state([q("VIX", vix), q("VIX3M", vix3m)])
    assert st["shape"] == shape
    assert st["ratio"] == pytest.approx(vix / vix3m, abs=1e-4)


def test_band_edges_are_the_boundary() -> None:
    """Just outside FLAT_BAND is a verdict; just inside is not."""
    over = volterm.state([q("VIX", 100 * (1 + volterm.FLAT_BAND) + 0.5), q("VIX3M", 100.0)])
    under = volterm.state([q("VIX", 100 * (1 - volterm.FLAT_BAND) - 0.5), q("VIX3M", 100.0)])
    assert over["shape"] == "backwardation"
    assert under["shape"] == "contango"


def test_missing_tenors_degrade_rather_than_raise() -> None:
    st = volterm.state([q("VIX9D", 12.0)])
    assert st["shape"] == "unknown"
    assert st["ratio"] is None
    assert [p["key"] for p in st["points"]] == ["VIX9D"]


def test_points_keep_curve_order_not_quote_order() -> None:
    """The panel draws them top to bottom; the quote list is unordered."""
    st = volterm.state([q("VIX6M", 20.0), q("VIX", 15.0), q("VIX3M", 18.0), q("VIX9D", 12.0)])
    assert [p["key"] for p in st["points"]] == ["VIX9D", "VIX", "VIX3M", "VIX6M"]


def test_a_null_last_is_not_a_zero() -> None:
    st = volterm.state([q("VIX", 15.0), q("VIX3M", 18.0), {"key": "VIX9D", "last": None}])
    assert [p["key"] for p in st["points"]] == ["VIX", "VIX3M"]
    assert st["shape"] == "contango"


# --- fedcal ------------------------------------------------------------------

TODAY = date(2026, 9, 1)


def ev(**kw) -> dict:
    base = {
        "type": "Speeches",
        "month": "2026-09",
        "days": "3",
        "time": "8:30 a.m.",
        "title": "Speech - Governor X",
    }
    return {**base, **kw}


def test_two_day_meeting_schedules_against_the_first_day() -> None:
    meeting = ev(type="FOMC", days="16,17", title="FOMC Meeting", time="2:00 p.m.")
    (row,) = fedcal.parse([meeting], TODAY)
    assert row["date"] == "2026-09-16"
    assert row["days"] == 2
    assert row["in_days"] == 15


def test_stat_releases_are_dropped() -> None:
    assert fedcal.parse([ev(type="Stat", title="H.15 Selected Interest Rates")], TODAY) == []


def test_the_past_and_the_far_future_are_both_out_of_the_window() -> None:
    rows = fedcal.parse(
        [ev(days="1", month="2026-08"), ev(days="3"), ev(days="15", month="2026-10")],
        TODAY,
    )
    assert [r["date"] for r in rows] == ["2026-09-03"]


@pytest.mark.parametrize(
    ("raw", "et"),
    [
        ("8:30 a.m.", "08:30"),
        ("2:00 p.m.", "14:00"),
        ("12:00 p.m.", "12:00"),  # noon is 12, not 24
        ("12:30 a.m.", "00:30"),  # midnight is 0, not 12
        ("", None),
        ("TBA", None),
    ],
)
def test_et_times_parse_across_the_noon_boundary(raw: str, et: str | None) -> None:
    (row,) = fedcal.parse([ev(time=raw)], TODAY)
    assert row["et"] == et
    assert (row["utc"] is None) == (et is None)


def test_principals_are_major_and_a_panellist_is_not() -> None:
    rows = fedcal.parse(
        [
            ev(days="3", title="Speech - Governor Christopher J. Waller"),
            ev(days="4", type="Conferences", title="Community Banking Research Conference"),
            ev(days="5", type="Beige", title="Beige Book"),
        ],
        TODAY,
    )
    assert [r["major"] for r in rows] == [True, False, True]


def test_escaped_html_is_stripped_from_titles() -> None:
    (row,) = fedcal.parse([ev(title="Speech &amp; <em>Discussion</em> - Chair Powell")], TODAY)
    assert row["title"] == "Speech & Discussion - Chair Powell"
    assert row["major"] is True


def test_rows_sort_by_date_then_time_with_untimed_last() -> None:
    rows = fedcal.parse(
        [ev(days="3", time="2:00 p.m."), ev(days="3", time=""), ev(days="2", time="9:00 a.m.")],
        TODAY,
    )
    assert [(r["date"], r["et"]) for r in rows] == [
        ("2026-09-02", "09:00"),
        ("2026-09-03", "14:00"),
        ("2026-09-03", None),
    ]


def test_a_malformed_day_is_skipped_not_fatal() -> None:
    rows = fedcal.parse([ev(days="31", month="2026-09"), ev(days="3")], TODAY)
    assert [r["date"] for r in rows] == ["2026-09-03"]


# --- the meeting page: the schedule past December -----------------------------
#
# The events feed stops at 31 December. On 13 Nov 2026 it held one FOMC, so the Rates
# card's path was one row while the strip priced fourteen months. The Board's meeting
# page carries next year; these are its cells as the page prints them.


def _block(year: int, *rows: tuple[str, str]) -> str:
    cells = "".join(
        f'<div class="row fomc-meeting">'
        f'<div class="fomc-meeting__month col-xs-5"><strong>{month}</strong></div>\n'
        f'<div class="fomc-meeting__date col-xs-4">{days}</div>'
        f'<div class="col-xs-12 fomc-meeting__minutes"></div></div>\n'
        for month, days in rows
    )
    return f'<div class="panel-heading"><h4><a id="1">{year} FOMC Meetings</a></h4></div>\n{cells}'


# The order the page prints its blocks in: this year, older years, then next year last.
PAGE = (
    _block(2026, ("January", "27-28"), ("October", "27-28"), ("December", "8-9*"))
    + _block(2025, ("August", "22 (notation vote)"), ("December", "9-10*"))
    + _block(2027, ("January", "26-27"), ("March", "16-17"), ("April", "27-28"), ("June", "8-9"))
)
NOV13 = date(2026, 11, 13)


def test_the_page_gives_the_meetings_still_to_decide_first_day_and_length() -> None:
    assert fedcal.schedule_from_page(PAGE, NOV13) == [
        {"date": "2026-12-08", "days": 2},
        {"date": "2027-01-26", "days": 2},
        {"date": "2027-03-16", "days": 2},
        {"date": "2027-04-27", "days": 2},
        {"date": "2027-06-08", "days": 2},
    ]


def test_a_two_day_meeting_is_still_ahead_on_its_decision_morning() -> None:
    """The feed drops a meeting once its FIRST day has passed; the decision is the second."""
    on_the_day = fedcal.schedule_from_page(PAGE, date(2026, 12, 9))
    assert on_the_day[0] == {"date": "2026-12-08", "days": 2}
    after = fedcal.schedule_from_page(PAGE, date(2026, 12, 10))
    assert after[0] == {"date": "2027-01-26", "days": 2}


def test_a_notation_vote_is_not_a_meeting_and_a_meeting_can_cross_a_month_end() -> None:
    page = _block(2030, ("March", "19 (notation vote)"), ("Apr/May", "30-1"),
                  ("June", "(cancelled)"), ("July", "30-31"), ("February", "30-31"))
    rows = fedcal.schedule_from_page(page, date(2030, 1, 2), horizon_days=400)
    # 30 April and 1 May; the decision is May's. February the 30th is not a day.
    assert rows == [{"date": "2030-04-30", "days": 2}, {"date": "2030-07-30", "days": 2}]
    assert fedcal._decision(rows[0]) == date(2030, 5, 1)


def test_the_horizon_and_an_unreadable_page_both_give_nothing_rather_than_guess() -> None:
    december = {"date": "2026-12-08", "days": 2}
    assert fedcal.schedule_from_page(PAGE, NOV13, horizon_days=60) == [december]
    assert fedcal.schedule_from_page("<html><body>Service unavailable</body></html>", NOV13) == []
    assert fedcal._schedule_body(b"<html>Service unavailable</html>") is not None
    assert fedcal._schedule_body(PAGE.encode()) is None


def test_the_feed_keeps_its_own_meetings_and_the_page_adds_the_ones_past_december() -> None:
    # The feed's December entry is one day, the 9th; the page's is the 8th and 9th.
    # Same decision, so the feed's stands untouched and is not listed twice.
    feed = [{"date": "2026-12-09", "days": 1}]
    merged = fedcal.with_schedule(feed, fedcal.schedule_from_page(PAGE, NOV13))
    assert merged == [
        {"date": "2026-12-09", "days": 1},
        {"date": "2027-01-26", "days": 2},
        {"date": "2027-03-16", "days": 2},
        {"date": "2027-04-27", "days": 2},
        {"date": "2027-06-08", "days": 2},
    ]
    # No page: the schedule is the feed's alone, as it always was.
    assert fedcal.with_schedule(feed, []) == feed
    # No feed meetings left (late December): the page carries the schedule by itself.
    january = {"date": "2027-01-26", "days": 2}
    assert fedcal.with_schedule([], [january]) == [january]


def test_the_path_reaches_past_december_once_the_page_is_read() -> None:
    """The strip of 13 Nov 2026 and the merged schedule: five meetings priced, not one."""
    from newsterminal.policy import meetings_priced

    strip = {"2026-11": 3.878, "2026-12": 4.07, "2027-01": 4.165, "2027-02": 4.32, "2027-03": 4.395,
             "2027-04": 4.49, "2027-05": 4.57, "2027-06": 4.645, "2027-07": 4.68}
    rates = {"policy": {"EFFR": {"rate": 3.88}},
             "strip": [{"month": k, "implied": v} for k, v in strip.items()]}
    feed = [{"date": "2026-12-09", "days": 1}]
    assert len(meetings_priced(rates, feed)["meetings"]) == 1
    pm = meetings_priced(rates, fedcal.with_schedule(feed, fedcal.schedule_from_page(PAGE, NOV13)))
    assert [(m["date"], round(m["move_bp"]), round(m["cum_bp"])) for m in pm["meetings"]] == [
        ("2026-12-09", 27, 27), ("2027-01-27", 17, 44), ("2027-03-17", 17, 61),
        ("2027-04-28", 8, 69), ("2027-06-09", 11, 80),
    ]
