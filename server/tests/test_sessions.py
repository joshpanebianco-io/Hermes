"""
The session clock's headline must never contradict the boxes printed under it.

That is the invariant these tests exist for. `_phase` returns one line — "Asia
session", "Between Asia and London", "Weekend" — and the panel prints it
directly above the four box rows (owner, 2026-10-30: the Sessions panel follows
the session ranges' boxes). When the two are derived independently they drift,
and the drift is invisible to every type checker and every unit test that only
looks at one side.

The bug that first locked this down, reported 2026-08-31 at 20:51 ET: the label
read "Globex — New futures session under way" while Sydney and Tokyo were both
marked OPEN two lines below it. The rows are boxes now, not cities, and the
headline is read off the same `in_box` the rows are.
"""

from __future__ import annotations

from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

import pytest

from newsterminal.sessions import box_state, globex_open, in_box, session_state

ET = ZoneInfo("America/New_York")


def at(y: int, mo: int, d: int, h: int, mi: int = 0) -> datetime:
    return datetime(y, mo, d, h, mi, tzinfo=ET)


def phase(when: datetime) -> str:
    return session_state(when)["phase"]["key"]


def boxes(when: datetime) -> dict[str, dict]:
    return {b["key"]: b for b in box_state(when)}


# --- the invariant ------------------------------------------------------------


def test_the_headline_never_contradicts_the_boxes() -> None:
    """Ten days at 15-minute resolution, across a weekend and a clock change."""
    bad: list[str] = []
    when = at(2026, 10, 23, 0, 0)  # a Friday; the UK changes clocks on the 25th
    for _ in range(4 * 24 * 10):
        st = session_state(when)
        key = st["phase"]["key"]
        asia, london, pre = (in_box(k, when) for k in ("asia", "london", "premkt"))
        rows = {b["key"]: b["open"] for b in st["boxes"]}
        stamp = when.strftime("%a %d %H:%M")
        if key == "asia" and not (asia and rows["asia"]):
            bad.append(f"{stamp}: says Asia, Asia's box is not open")
        if key == "london" and not (london and not pre):
            bad.append(f"{stamp}: says London, boxes say {london=} {pre=}")
        if key == "handover" and not (london and pre):
            bad.append(f"{stamp}: says London into the pre-market, boxes say {london=} {pre=}")
        if key == "preopen" and not (pre and not london):
            bad.append(f"{stamp}: says pre-market, boxes say {london=} {pre=}")
        if key == "globex" and (asia or london or pre or not globex_open(when)):
            bad.append(f"{stamp}: says Globex, a box is open or the market is shut")
        if key == "weekend" and (globex_open(when) or any(rows.values())):
            bad.append(f"{stamp}: says Weekend, something is open")
        when += timedelta(minutes=15)
    assert bad == []


# --- the boxes, on the clock ----------------------------------------------------


def test_the_asian_evening_is_asia_and_the_hours_before_it_are_globex() -> None:
    """Asia's box is 20:00-00:00 ET. Before it, futures are trading and nothing
    the panel draws is — and the headline says so rather than claiming Asia."""
    assert phase(at(2026, 8, 31, 18, 30)) == "globex"
    assert session_state(at(2026, 8, 31, 18, 30))["phase"]["label"] == "Globex reopen"
    assert phase(at(2026, 8, 31, 19, 59)) == "globex"
    assert phase(at(2026, 8, 31, 20, 0)) == "asia"
    assert phase(at(2026, 8, 31, 20, 51)) == "asia"


def test_the_box_is_drawn_in_et_so_the_season_does_not_move_it() -> None:
    """The headline used to follow Sydney's open, which swings between 18:00 and
    20:00 ET across the year. The owner's box is the one on the chart, 20:00 ET
    in every season (2026-10-30), so 18:30 is Globex in August AND January."""
    assert phase(at(2026, 8, 31, 18, 30)) == "globex"
    assert phase(at(2027, 1, 12, 18, 30)) == "globex"
    assert phase(at(2027, 1, 12, 20, 30)) == "asia"


def test_the_gap_between_asia_and_london_says_so() -> None:
    st = session_state(at(2026, 9, 1, 0, 30))
    assert st["phase"]["key"] == "globex"
    assert st["phase"]["label"] == "Between Asia and London"


def test_the_hour_before_london_is_frankfurt_not_a_gap() -> None:
    """Owner, 2026-10-30 at 02:39 ET: "2:00 - 3:00 est should be Frankfurt not
    between asia and london". That week the UK had left summer time and the US
    had not, so London's 07:00 box opened at 03:00 ET and the headline called
    the hour before it a gap. Europe's day starts at 02:00 ET on the owner's
    clock; in a normal week London's box opens at the same minute and takes
    the headline, in a mismatch week Frankfurt holds it for the hour."""
    # The mismatch week (UK back to GMT 25 Oct, US to EST 1 Nov).
    assert phase(at(2026, 10, 30, 1, 30)) == "globex"
    assert session_state(at(2026, 10, 30, 2, 30))["phase"]["label"] == "Frankfurt session"
    assert phase(at(2026, 10, 30, 2, 59)) == "frankfurt"
    assert phase(at(2026, 10, 30, 3, 0)) == "london"
    # March's mismatch runs the same way (US forward 14 Mar 2027, UK 28 Mar).
    assert phase(at(2027, 3, 16, 2, 30)) == "frankfurt"
    assert phase(at(2027, 3, 16, 3, 0)) == "london"
    # A normal week: 07:00 London IS 02:00 ET, and the London box has the headline.
    assert phase(at(2026, 11, 10, 1, 59)) == "globex"
    assert phase(at(2026, 11, 10, 2, 0)) == "london"
    assert phase(at(2026, 8, 31, 2, 0)) == "london"


# --- the week's real boundaries ----------------------------------------------


@pytest.mark.parametrize(
    ("when", "key"),
    [
        # Friday: cash shuts 16:00, futures settle and stop at 17:00.
        (at(2026, 8, 28, 16, 30), "post"),
        (at(2026, 8, 28, 17, 30), "weekend"),
        (at(2026, 8, 29, 12, 0), "weekend"),  # Saturday
        (at(2026, 8, 30, 12, 0), "weekend"),  # Sunday, before the reopen
        # Sunday 18:00 ET IS the new week — and 08:00 Monday in Sydney, which is
        # this desk's own Monday morning.
        (at(2026, 8, 30, 18, 30), "globex"),
        (at(2026, 8, 30, 21, 0), "asia"),
    ],
)
def test_the_week_is_bounded_by_globex_not_the_calendar(when: datetime, key: str) -> None:
    assert phase(when) == key


@pytest.mark.parametrize(
    ("hour", "minute", "key"),
    [
        (3, 30, "london"),     # London's box alone
        (4, 30, "handover"),   # London's last hour is the pre-market's first
        (5, 0, "preopen"),     # the pre-market alone
        (8, 30, "preopen"),
        (10, 0, "open"),
        (12, 30, "midday"),
        (15, 0, "close"),
        (16, 30, "post"),
        (17, 30, "halt"),
    ],
)
def test_the_new_york_ladder_keeps_its_own_clock(hour: int, minute: int, key: str) -> None:
    """ET is New York's local time, so these boundaries are exact year-round."""
    assert phase(at(2026, 9, 1, hour, minute)) == key


# --- the box rows ---------------------------------------------------------------


def test_each_box_counts_down_to_its_next_occurrence() -> None:
    """Tuesday 00:30 ET, both hemispheres on summer time."""
    b = boxes(at(2026, 9, 1, 0, 30))
    assert [k for k in b] == ["asia", "london", "premkt", "ny"]
    assert not any(x["open"] for x in b.values())
    assert (b["asia"]["next"], b["asia"]["next_min"]) == ("opens", 19 * 60 + 30)   # tonight 20:00
    assert (b["london"]["next"], b["london"]["next_min"]) == ("opens", 90)         # 02:00
    assert (b["premkt"]["next"], b["premkt"]["next_min"]) == ("opens", 210)        # 04:00
    assert (b["ny"]["next"], b["ny"]["next_min"]) == ("opens", 540)                # 09:30
    assert (b["asia"]["start_et"], b["asia"]["end_et"]) == ("20:00", "00:00")
    assert (b["premkt"]["start_et"], b["premkt"]["end_et"]) == ("04:00", "09:30")


def test_two_boxes_are_open_at_half_past_four() -> None:
    b = boxes(at(2026, 9, 1, 4, 30))
    assert b["london"]["open"] and (b["london"]["next"], b["london"]["next_min"]) == ("closes", 30)
    assert b["premkt"]["open"] and (b["premkt"]["next"], b["premkt"]["next_min"]) == ("closes", 300)
    assert not b["asia"]["open"] and not b["ny"]["open"]


def test_friday_night_counts_down_to_sunday() -> None:
    """Friday 00:30: Asia's next box is Sunday 20:00, because Globex is shut
    Friday evening — not "tonight"."""
    b = boxes(at(2026, 9, 4, 0, 30))
    assert b["asia"]["next_min"] == 2 * 24 * 60 + 19 * 60 + 30
    # Saturday: nothing open, New York opens Monday (the 12th, not the 5th —
    # that Monday is Labor Day, and the box skips it like the NYSE does).
    b = boxes(at(2026, 9, 12, 12, 0))
    assert not any(x["open"] for x in b.values())
    assert b["ny"]["next_min"] == 45 * 60 + 30
    assert boxes(at(2026, 9, 5, 12, 0))["ny"]["next_min"] == 45 * 60 + 30 + 24 * 60


def test_london_box_keeps_londons_clock_in_the_mismatch_week() -> None:
    """Mon 26 Oct 2026: the UK on GMT, the US still on EDT — London's 07:00 is
    03:00 ET. A week later both are on standard time and it is 02:00 again."""
    b = boxes(at(2026, 10, 26, 1, 0))
    assert (b["london"]["start_et"], b["london"]["end_et"]) == ("03:00", "06:00")
    b = boxes(at(2026, 11, 2, 1, 0))
    assert (b["london"]["start_et"], b["london"]["end_et"]) == ("02:00", "05:00")


def test_new_york_box_keeps_the_nyse_calendar() -> None:
    """The day after Thanksgiving closes at 13:00; Thanksgiving itself has no box."""
    b = boxes(at(2026, 11, 27, 10, 0))
    assert b["ny"]["open"] and b["ny"]["end_et"] == "13:00"
    b = boxes(at(2026, 11, 26, 10, 0))
    assert not b["ny"]["open"] and b["ny"]["start_et"] == "09:30" and b["ny"]["next"] == "opens"


def test_the_next_marker_is_a_box_boundary() -> None:
    labels = [m["label"] for m in session_state(at(2026, 9, 1, 0, 30))["markers"]]
    assert labels[0] == "London opens"
    labels = [m["label"] for m in session_state(at(2026, 9, 1, 19, 30))["markers"]]
    assert labels[0] == "Asia opens"
