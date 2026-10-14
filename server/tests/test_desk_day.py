"""
The desk day — one definition of when each session runs, on each city's clock.

THE INSTANTS THE REVIEW OF 2026-10-14 FOUND WRONG, pinned as they now read:
the brief called Friday 20:30 ET "Asia, 2h 30m in" with Globex shut for the
weekend, and Saturday 10:00 and Thanksgiving morning "New York underway"; and
three ET-constant definitions of London were an hour out for the week between
the UK's clock change (Oct 25) and the US's (Nov 1), and three weeks every
March. Every expectation below was printed from the code at the instant named
and checked against the city clocks by hand.
"""

from __future__ import annotations

from datetime import datetime
from typing import Any
from zoneinfo import ZoneInfo

import pytest

from newsterminal import report, sessions
from newsterminal.sources.calendar import session_of

ET = ZoneInfo("America/New_York")


def at(y: int, mo: int, d: int, h: int, mi: int = 0) -> datetime:
    return datetime(y, mo, d, h, mi, tzinfo=ET)


def auto(when: datetime) -> str:
    return report.resolve_session({"et": when.isoformat()})


# --- #7: a session is underway only when it is actually running ----------------


@pytest.mark.parametrize(
    ("when", "session", "opens_et"),
    [
        (at(2026, 10, 16, 20, 30), "asia", "Sun 18:00"),  # Friday night: Globex shut
        (at(2026, 10, 17, 10, 0), "asia", "Sun 18:00"),   # Saturday: Monday's Asia prep
        (at(2026, 11, 26, 10, 0), "asia", "18:00"),       # Thanksgiving: no New York
        (at(2026, 12, 24, 19, 0), "asia", "Sun 18:00"),   # no reopen into Christmas
        (at(2026, 10, 14, 16, 30), "asia", "18:00"),      # the weekday post-close lull
    ],
)
def test_nothing_running_resolves_to_what_opens_next(
    when: datetime, session: str, opens_et: str
) -> None:
    assert auto(when) == session
    p = report.session_progress(session, when)
    assert p["underway"] is False
    assert p["opens_et"] == opens_et


def test_new_york_is_never_underway_when_the_nyse_is_shut() -> None:
    for when in (at(2026, 10, 17, 10, 0), at(2026, 11, 26, 10, 0)):
        p = report.session_progress("ny", when)
        assert p["underway"] is False, when
    # The next New York after Thanksgiving is Friday's half day.
    p = report.session_progress("ny", at(2026, 11, 26, 10, 0))
    assert p["opens_et"] == "Fri 09:30"
    assert "09:30–13:00 ET" in p["hours"]


def test_the_week_starts_at_sundays_reopen() -> None:
    p = report.session_progress("asia", at(2026, 10, 18, 18, 30))
    assert (p["underway"], p["minutes_in"], p["opened_et"]) == (True, 30, "18:00")
    assert auto(at(2026, 10, 18, 18, 30)) == "asia"


def test_thanksgiving_morning_still_has_a_london_session() -> None:
    """Globex trades an abbreviated session on Thanksgiving, so London happens."""
    assert auto(at(2026, 11, 26, 7, 45)) == "london"
    assert report.session_progress("london", at(2026, 11, 26, 7, 45))["underway"] is True


@pytest.mark.parametrize(
    ("when", "session"),
    [
        (at(2026, 10, 14, 1, 59), "asia"),
        (at(2026, 10, 14, 2, 0), "london"),
        (at(2026, 10, 14, 7, 29), "london"),
        (at(2026, 10, 14, 7, 30), "ny"),     # two hours before the bell
        (at(2026, 10, 14, 15, 59), "ny"),
        (at(2026, 10, 14, 16, 0), "asia"),
    ],
)
def test_an_ordinary_weekday_keeps_its_old_switches(when: datetime, session: str) -> None:
    assert auto(when) == session


# --- #10: London on London's clock ---------------------------------------------


@pytest.mark.parametrize(
    ("when", "window", "session"),
    [
        # Fri 23 Oct: both on summer time, London 07:00 is 02:00 ET.
        (at(2026, 10, 23, 2, 30), "london", "london"),
        # Mon 26 Oct: UK on GMT, US on EDT — London 07:00 is 03:00 ET.
        (at(2026, 10, 26, 2, 30), "asia", "asia"),
        (at(2026, 10, 26, 3, 0), "london", "london"),
        (at(2026, 10, 26, 5, 30), "london", "london"),
        (at(2026, 10, 26, 6, 0), "euro_mid", "london"),
        # Mon 2 Nov: both on standard time — back to 02:00 ET.
        (at(2026, 11, 2, 2, 30), "london", "london"),
        # Tue 16 Mar 2027: US on EDT, UK still on GMT — 03:00 ET again.
        (at(2027, 3, 16, 2, 30), "asia", "asia"),
        (at(2027, 3, 16, 3, 0), "london", "london"),
    ],
)
def test_london_starts_at_0700_london_every_week(
    when: datetime, window: str, session: str
) -> None:
    assert sessions.desk_window(when) == window
    assert auto(when) == session


def test_the_session_hours_the_prompt_states_follow_the_clocks() -> None:
    assert report.session_hours("london", at(2026, 10, 23, 2, 0)).startswith(
        "02:00–08:00 ET; the OPEN window is 02:00–05:00 ET")
    assert report.session_hours("london", at(2026, 10, 26, 3, 0)).startswith(
        "03:00–08:00 ET; the OPEN window is 03:00–06:00 ET")
    # Tokyo 09:00 JST is 20:00 EDT and 19:00 EST: the old constant was right
    # only in winter.
    assert "Tokyo 20:00–02:30" in report.session_hours("asia", at(2026, 10, 14, 18, 0))
    assert "Tokyo 19:00–01:30" in report.session_hours("asia", at(2026, 11, 2, 18, 0))
    assert "overlap 08:00–12:30 ET" in report.session_hours("ny", at(2026, 10, 26, 9, 30))
    assert "overlap 08:00–11:30 ET" in report.session_hours("ny", at(2026, 10, 23, 9, 30))


def test_the_overlap_ends_at_the_lse_close() -> None:
    assert sessions.session_state(at(2026, 10, 23, 11, 45))["overlap"] is False
    assert sessions.session_state(at(2026, 10, 26, 11, 45))["overlap"] is True
    assert sessions.session_state(at(2026, 10, 26, 12, 30))["overlap"] is False


def test_the_calendar_files_uk_gdp_under_london() -> None:
    """07:00 London is 02:00 ET most weeks — it used to be tagged Asia."""
    assert session_of(at(2026, 10, 23, 2, 0)) == "london"
    assert session_of(at(2026, 10, 26, 3, 0)) == "london"
    assert session_of(at(2026, 10, 26, 2, 0)) == "asia"  # 06:00 London that week
    assert session_of(at(2026, 10, 14, 19, 50)) == "asia"
    assert session_of(at(2026, 10, 14, 8, 30)) == "preny"
    assert session_of(at(2026, 10, 14, 16, 30)) == "closed"


# --- Globex's own calendar -----------------------------------------------------


@pytest.mark.parametrize(
    ("when", "open_"),
    [
        (at(2026, 10, 16, 16, 59), True),
        (at(2026, 10, 16, 17, 0), False),   # Friday's halt is the weekend
        (at(2026, 10, 17, 12, 0), False),
        (at(2026, 10, 18, 18, 0), True),    # Sunday's reopen
        (at(2026, 10, 14, 17, 30), False),  # the maintenance hour
        (at(2026, 11, 26, 12, 59), True),   # Thanksgiving's abbreviated session
        (at(2026, 11, 26, 13, 0), False),
        (at(2026, 11, 27, 13, 15), False),  # the half day's early halt
        (at(2026, 12, 24, 18, 30), False),  # no reopen into Christmas
        (at(2026, 12, 27, 18, 0), True),
    ],
)
def test_globex_open(when: datetime, open_: bool) -> None:
    assert sessions.globex_open(when) is open_


# --- #11: 17:00 is the halt, not the settlement --------------------------------


def test_the_markers_name_the_settlements_and_the_halt() -> None:
    labels = {m["label"]: m for m in sessions.session_state(at(2026, 10, 16, 12, 0))["markers"]}
    assert "CME settlement" not in labels
    assert labels["Gold settlement"]["et"] == "13:30"
    assert labels["Globex halt"]["et"] == "17:00"
    assert "settle" in labels["NYSE close"]["note"]
    # The half day halts early, and the marker says when.
    half = {m["label"]: m for m in sessions.session_state(at(2026, 11, 27, 12, 0))["markers"]}
    assert half["Globex halt"]["et"] == "13:15"


def test_christmas_is_a_closed_market_not_a_cash_holiday() -> None:
    ph = sessions.session_state(at(2026, 12, 25, 10, 0))["phase"]
    assert ph["key"] == "holiday" and "futures and cash shut" in ph["note"]
    ph = sessions.session_state(at(2026, 11, 26, 10, 0))["phase"]
    assert "13:00" in ph["note"]


# --- #8: the ladder's overnight is tonight's -----------------------------------


def _range(key: str, hi: float, lo: float, prior: bool) -> dict[str, Any]:
    return {"key": key, "ok": True, "high": hi, "low": lo, "open": lo, "close": hi,
            "range": hi - lo, "prior_day": prior, "status": "complete"}


def test_the_ladder_leaves_yesterdays_windows_out_of_the_overnight() -> None:
    """07:50 ET: Pre-NY is yesterday's. Its 31,089 high is not the ON high."""
    snap = {
        "clock": {"et": at(2026, 10, 14, 7, 50).isoformat()},
        "quotes": [{"key": "NQ", "last": 30800.0, "prev": 30700.0, "pct": 0.3}],
        "ranges": {"assets": {"NQ": {"last": 30800.0, "sessions": [
            _range("asia", 30906.0, 30604.75, False),
            _range("london", 30850.0, 30700.0, False),
            _range("euro_mid", 30880.0, 30760.0, False),
            _range("preny", 31089.0, 30950.0, True),
            _range("ny", 31100.0, 30900.0, True),
        ]}}},
    }
    ladder = report.build_facts(snap, "ny", "NQ")["ladders"][0]
    rows = {r["label"]: r["price"] for r in ladder["rows"]}
    assert rows["ON high"] == 30906.0
    assert rows["ON low"] == 30604.75
    assert 31089.0 not in rows.values()


# --- #1 and #9: what the brief is told about its data --------------------------


def test_the_digest_says_how_old_each_price_is() -> None:
    now = at(2026, 10, 14, 20, 0)
    snap = {
        "clock": {"et": now.isoformat()},
        "quotes": [
            # A row from the new board, with its feed state.
            {"key": "NQ", "last": 30800.0, "pct": 0.3, "feed": "delayed", "lag_min": 10.0,
             "quote_time": int(at(2026, 10, 14, 19, 50).timestamp())},
            {"key": "US10Y", "last": 4.12, "pct": -0.4, "chg": -0.023, "feed": "closed",
             "quote_time": int(at(2026, 10, 14, 14, 59).timestamp())},
            # An older snapshot's row, with no feed: its own age decides.
            {"key": "DXY", "last": 99.1, "pct": 0.1, "chg": 0.1,
             "quote_time": int(at(2026, 10, 13, 16, 0).timestamp())},
            {"key": "VIX", "last": 16.0, "pct": 1.0,
             "quote_time": int(at(2026, 10, 14, 19, 59).timestamp())},
        ],
    }
    d = report.build_digest(snap, "asia", "all")
    feed = d["price_feed"]
    assert feed["delayed"] == ["NQ"]
    assert feed["not_current"] == {
        "US10Y": "closed: last print 14:59 ET",
        "DXY": "stale: last print Tue 16:00 ET",
    }
    assert "10 minutes" in feed["futures"]
    assert d["the_book"]["NQ_futures"].get("not_current") is None
    assert d["dollar_and_commodities"]["DXY"]["not_current"] == "stale: last print Tue 16:00 ET"
    assert "not_current" not in d["volatility"]["VIX"]
    # And on the page: the snapshot's 10Y row admits it.
    snap_rows = {r["key"]: r for r in report.build_facts(snap, "asia", "all")["snapshot"]}
    assert "last print 14:59 ET" in (snap_rows["US10Y"]["sub"] or "")


def test_the_prompt_names_no_market_the_data_does_not_carry() -> None:
    for session in ("asia", "london", "ny"):
        for asset in ("all", "GC", "NQ"):
            prog = report.session_progress(session, at(2026, 10, 14, 1, 0))
            text = report.system_prompt(session, asset, prog)
            # Each may appear only inside the "does not have" list, never as a channel.
            for invented in ("Shanghai premium", "Indian buying", "LBMA", "Bunds and Gilts"):
                assert invented not in text, (session, asset, invented)
            assert "NEITHER DOES A MARKET, FLOW OR DATA" in text
            assert "PRICES HAVE AGES" in text
    assert "Bunds" not in report.SESSIONS["london"]["leads"]


# --- gold's own day session ---------------------------------------------------


def test_golds_rth_is_the_comex_day_session() -> None:
    from newsterminal.profile import windows

    ws = {w["key"]: w for w in windows(at(2026, 10, 14, 11, 0), "GC")}
    assert (ws["prev_rth"]["start"].strftime("%H:%M"), ws["prev_rth"]["end"].strftime("%H:%M")) \
        == ("08:20", "13:30")
    assert ws["dev"]["label"] == "Live · 08:20"
    # After gold settles the day is complete, while the equity books still trade.
    assert "dev" not in {w["key"] for w in windows(at(2026, 10, 14, 14, 0), "GC")}
    assert "dev" in {w["key"] for w in windows(at(2026, 10, 14, 14, 0), "NQ")}
