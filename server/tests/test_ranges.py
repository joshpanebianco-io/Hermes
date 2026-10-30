"""
The session boxes, and what each row admits about itself.

THE ROWS ARE THE FOUR BOXES A TRADER DRAWS (owner, 2026-10-30): Asia 20:00 to
midnight ET, London 02:00 to 05:00 (on London's clock), the pre-market 04:00
to 09:30, New York 09:30 to 16:00 — plus the overnight, 18:00 to the cash open,
which the brief's ladder reads and the panel does not draw. They overlap and
they leave gaps, so the old guarantees ("every minute in exactly one window",
"the rows after the newest are yesterday's") are gone, and these tests pin
what replaced them: each box collects its own bars, and a row is the previous
day's by Globex trade date.

THE OLDER BUG THEY STILL GUARD AGAINST. A London brief once printed "The
London session opened at 29,263.75" — the 18:00 Globex open lifted from the
volume-profile block, because the rows carried no open of their own and
nothing said which day they were from.
"""

from __future__ import annotations

from datetime import datetime, timedelta
from typing import Any
from zoneinfo import ZoneInfo

from newsterminal.sources.ranges import segment

ET = ZoneInfo("America/New_York")


def bars(start: datetime, count: int, first: float = 29200.0, step: float = 5.0) -> Any:
    """`count` 15-minute closes walking up from `first`, starting at `start`."""
    stamps, closes = [], []
    price = first
    for i in range(count):
        stamps.append(int((start + timedelta(minutes=15 * i)).timestamp()))
        closes.append(price)
        price += step
    return stamps, [None] * count, [None] * count, closes


def rows(now: datetime, start: datetime, count: int) -> dict[str, dict[str, Any]]:
    stamps, highs, lows, closes = bars(start, count)
    out = segment(stamps, highs, lows, closes, closes[-1], now)
    return {r["key"]: r for r in out if r["ok"]}


def upto(now: datetime, start: datetime) -> dict[str, dict[str, Any]]:
    """Bars from `start` to the last quarter-hour at or before `now`."""
    count = int((now - start) / timedelta(minutes=15)) + 1
    return rows(now, start, count)


TUE_1800 = datetime(2026, 9, 15, 18, 0, tzinfo=ET)


def test_the_rows_are_the_four_boxes_and_the_overnight() -> None:
    """Read at 10:00 Wednesday with bars from Tuesday's reopen."""
    r = upto(datetime(2026, 9, 16, 10, 0, tzinfo=ET), TUE_1800)
    assert set(r) == {"asia", "london", "premkt", "ny", "overnight"}
    assert (r["asia"]["start_et"], r["asia"]["end_et"]) == ("20:00", "23:45")
    assert (r["london"]["start_et"], r["london"]["end_et"]) == ("02:00", "04:45")
    assert (r["premkt"]["start_et"], r["premkt"]["end_et"]) == ("04:00", "09:15")
    assert (r["ny"]["start_et"], r["ny"]["end_et"]) == ("09:30", "10:00")
    assert (r["overnight"]["start_et"], r["overnight"]["end_et"]) == ("18:00", "09:15")
    assert [x["label"] for x in (r["asia"], r["london"], r["premkt"], r["ny"], r["overnight"])] == [
        "Asia", "London", "Pre-market", "New York", "Overnight",
    ]


def test_each_box_opens_on_its_own_print() -> None:
    """The field whose absence sent a model looking elsewhere for one."""
    r = upto(datetime(2026, 9, 16, 10, 0, tzinfo=ET), TUE_1800)
    assert r["overnight"]["open"] == 29200.0     # the 18:00 print
    assert r["asia"]["open"] == 29240.0          # the 20:00 print — not Globex's reopen
    assert r["london"]["open"] == 29360.0        # the 02:00 print
    assert r["premkt"]["open"] == 29400.0        # the 04:00 print
    assert r["asia"]["date"] == "Tue 15" and r["london"]["date"] == "Wed 16"


def test_london_and_the_premarket_share_an_hour() -> None:
    """04:30 ET: both boxes are live, and each holds the 04:00-04:30 bars as its own."""
    r = upto(datetime(2026, 9, 16, 4, 30, tzinfo=ET), TUE_1800)
    assert r["london"]["status"] == "live" and r["premkt"]["status"] == "live"
    assert r["london"]["high"] == r["premkt"]["high"]     # the 04:30 print, in both
    assert r["london"]["low"] == 29360.0 and r["premkt"]["low"] == 29400.0


def test_the_gaps_have_no_live_box() -> None:
    """19:30, 00:30 and 16:30 ET belong to no box; only the overnight is live at night."""
    live = lambda now: {k for k, x in upto(now, TUE_1800).items() if x["status"] == "live"}  # noqa: E731
    assert live(datetime(2026, 9, 16, 19, 30, tzinfo=ET)) == {"overnight"}
    assert live(datetime(2026, 9, 16, 0, 30, tzinfo=ET)) == {"overnight"}
    assert live(datetime(2026, 9, 16, 16, 30, tzinfo=ET)) == set()
    assert live(datetime(2026, 9, 16, 23, 0, tzinfo=ET)) == {"asia", "overnight"}


def test_the_overnight_keeps_what_falls_between_the_boxes() -> None:
    """A spike at 01:00 ET — after Asia's box, before London's — is nobody's high
    but the overnight's, which is what the ladder's ON high is read from."""
    stamps, highs, lows, closes = bars(TUE_1800, 45)                  # to 05:00 Wed
    at_0100 = int(datetime(2026, 9, 16, 1, 0, tzinfo=ET).timestamp())
    closes[stamps.index(at_0100)] = 31000.0
    out = {r["key"]: r for r in segment(stamps, highs, lows, closes, closes[-1],
                                        datetime(2026, 9, 16, 5, 30, tzinfo=ET)) if r["ok"]}
    assert out["overnight"]["high"] == 31000.0
    assert out["asia"]["high"] < 31000.0 and out["london"]["high"] < 31000.0


def test_a_row_is_the_prior_days_by_globex_trade_date() -> None:
    """Two days of bars, read at instants of the second day."""
    start = datetime(2026, 9, 14, 18, 0, tzinfo=ET)                   # Monday's reopen

    def prior(now: datetime) -> dict[str, bool]:
        return {k: r["prior_day"] for k, r in upto(now, start).items()}

    # 03:00 Wednesday, London live: tonight's Asia, London and overnight are
    # this trade date's; Tuesday's pre-market and New York are not.
    assert prior(datetime(2026, 9, 16, 3, 0, tzinfo=ET)) == {
        "asia": False, "london": False, "premkt": True, "ny": True, "overnight": False,
    }
    # 17:00 Wednesday, the maintenance hour: one whole day, nothing stale.
    assert not any(prior(datetime(2026, 9, 16, 17, 0, tzinfo=ET)).values())
    # 18:15 Wednesday: the Globex day has turned, so every box is Wednesday's
    # and only the overnight — begun at 18:00 — is tonight's.
    assert prior(datetime(2026, 9, 16, 18, 15, tzinfo=ET)) == {
        "asia": True, "london": True, "premkt": True, "ny": True, "overnight": False,
    }


def test_a_live_box_with_no_bar_yet_is_still_last_nights() -> None:
    """20:05, the clock is in Asia's box but its 20:00 bar has not printed.

    The row says "live" because the clock says so, and its numbers are last
    night's — and it says that too."""
    start = datetime(2026, 9, 14, 18, 0, tzinfo=ET)
    stamps, highs, lows, closes = bars(start, 200)                    # last bar Wed 19:45
    out = segment(stamps, highs, lows, closes, closes[-1], datetime(2026, 9, 16, 20, 5, tzinfo=ET))
    r = {x["key"]: x for x in out}
    assert r["asia"]["status"] == "live" and r["asia"]["date"] == "Tue 15"
    assert r["asia"]["prior_day"] is True
    assert r["overnight"]["prior_day"] is False and r["overnight"]["status"] == "live"


def test_london_keeps_londons_clock_in_the_mismatch_week() -> None:
    """Mon 2026-10-26: the UK is on GMT, the US still on EDT, so London's 07:00
    is 03:00 ET. The pre-market box is ET's and stays at 04:00."""
    r = upto(datetime(2026, 10, 26, 7, 0, tzinfo=ET), datetime(2026, 10, 25, 18, 0, tzinfo=ET))
    assert (r["london"]["start_et"], r["london"]["end_et"]) == ("03:00", "05:45")
    assert r["premkt"]["start_et"] == "04:00"
    # A week later both are on standard time and it is 02:00 again.
    r = upto(datetime(2026, 11, 2, 7, 0, tzinfo=ET), datetime(2026, 11, 1, 18, 0, tzinfo=ET))
    assert (r["london"]["start_et"], r["london"]["end_et"]) == ("02:00", "04:45")


def test_the_tagging_windows_still_cover_the_day_once_each() -> None:
    """The calendar's "prints in the X session" tag is the contiguous partition
    (sessions.desk_window): every minute of a Globex day belongs to exactly one,
    in the order the day runs them — in a normal week and in the mismatch week."""
    from newsterminal.sessions import DESK_WINDOWS, desk_window

    order = [k for k, _ in DESK_WINDOWS]
    assert order == ["asia", "london", "premkt", "ny", "post"]
    for day in (datetime(2026, 10, 19, 18, 0, tzinfo=ET), datetime(2026, 10, 26, 18, 0, tzinfo=ET)):
        seen: list[str] = []
        for m in range(0, 24 * 60, 5):
            k = desk_window(day + timedelta(minutes=m))
            if k is None:
                # 17:00-18:00 is the maintenance hour and belongs to nothing.
                assert 23 * 60 <= m < 24 * 60, m
                continue
            if not seen or seen[-1] != k:
                seen.append(k)
        assert seen == order, (day, seen)


def test_nothing_is_live_or_stale_while_globex_is_shut() -> None:
    """Saturday 10:00 is inside the clock's New York hours, and Friday's rows are
    complete and Friday's — not live, and not dimmed as last week's."""
    r = upto(datetime(2026, 10, 17, 10, 0, tzinfo=ET), datetime(2026, 10, 15, 18, 0, tzinfo=ET))
    assert all(x["status"] == "complete" for x in r.values())
    assert not any(x["prior_day"] for x in r.values())
