"""The Sectors cards outside the session (2026-11-16).

The owner, shown that the cards held Friday's moves at 07:00 ET on a Monday while XLK
traded 1.4% lower and SMH 3.4% lower: "do they move during extended hours also?. i think
we should make the app update as to wait theyre actually doing. right now im missing the
sectors information going into the aopen and to do my analysis before the open".

What is held here: a fund's last extended trade is read against its last regular close
(Yahoo's regularMarketPrice outside the session, never chartPreviousClose); a trade in
the session is no extended read; the close is a half day's 13:00 when it is one; the
reads run each minute only while the funds can trade outside the session; before the
bell the cards are the pre-market's (their move, their distance from SPY's, and their
stocks' own pre-market counts), after the close the day stays the session's and the
after-hours move rides beside it; a fund with no trade in the stretch says nothing
rather than repeating an older one.
"""

from __future__ import annotations

from datetime import datetime
from typing import Any
from zoneinfo import ZoneInfo

from newsterminal.sources import quotes as q
from newsterminal.sources import universe as u

ET = ZoneInfo("America/New_York")


def ts(y: int, mo: int, d: int, h: int, mi: int) -> int:
    return int(datetime(y, mo, d, h, mi, tzinfo=ET).timestamp())


def resp(bars: list[tuple[int, float | None]], ref: float = 100.0) -> dict[str, Any]:
    """A spark response as Yahoo sends it, with the extended bars asked for."""
    return {"meta": {"regularMarketPrice": ref, "chartPreviousClose": 90.0},
            "timestamp": [t for t, _ in bars],
            "indicators": {"quote": [{"close": [c for _, c in bars]}]}}


MON = (2026, 11, 16)


def test_before_the_bell_the_move_is_against_the_last_close() -> None:
    bars = [(ts(*MON, 4, 0), 99.5), (ts(*MON, 4, 5), None), (ts(*MON, 6, 40), 98.63)]
    x = q.ext_read(resp(bars))
    assert x is not None
    assert (x["kind"], x["day"], x["px"], x["bars"]) == ("pre", "2026-11-16", 98.63, 2)
    # Against regularMarketPrice (the last close), not chartPreviousClose.
    assert round(x["pct"], 2) == -1.37
    assert x["at"] == ts(*MON, 6, 40)


def test_a_trade_in_the_session_is_no_extended_read() -> None:
    assert q.ext_read(resp([(ts(*MON, 4, 0), 99.0), (ts(*MON, 10, 5), 101.0)])) is None
    assert q.ext_read(resp([])) is None
    assert q.ext_read(None) is None
    assert q.ext_read(resp([(ts(*MON, 7, 0), 99.0)], ref=0.0)) is None


def test_after_the_close_it_is_the_after_hours_and_a_half_day_closes_at_13() -> None:
    x = q.ext_read(resp([(ts(*MON, 15, 55), 100.0), (ts(*MON, 16, 30), 100.5)], ref=100.0))
    assert x is not None and x["kind"] == "post" and round(x["pct"], 2) == 0.5 and x["bars"] == 1
    # Friday 27 Nov 2026, the day after Thanksgiving, closes at 13:00.
    half = q.ext_read(resp([(ts(2026, 11, 27, 12, 55), 50.0), (ts(2026, 11, 27, 13, 30), 49.5)],
                           ref=50.0))
    assert half is not None and half["kind"] == "post"


def test_the_reads_run_each_minute_only_while_the_funds_can_trade_outside_the_session() -> None:
    at = lambda h, mi, d=MON: datetime(*d, h, mi, tzinfo=ET)  # noqa: E731
    assert q.extended_now(at(7, 0)) and q.extended_now(at(4, 0)) and q.extended_now(at(18, 0))
    assert not q.extended_now(at(12, 0)) and not q.extended_now(at(21, 0))
    assert not q.extended_now(at(3, 30))
    assert not q.extended_now(at(7, 0, (2026, 11, 14)))          # a Saturday
    assert not q.extended_now(at(7, 0, (2026, 11, 26)))          # Thanksgiving


def test_in_the_session_the_funds_are_read_each_minute_and_kept_under_it() -> None:
    # The owner's yes (2026-11-16) to reading the sector and theme funds each minute in the
    # session, where it was five: the job asks for 60 s while this holds, and a read is
    # kept under that, so each run asks Yahoo afresh.
    at = lambda h, mi, d=MON: datetime(*d, h, mi, tzinfo=ET)  # noqa: E731
    assert q.regular_now(at(9, 30)) and q.regular_now(at(15, 59)) and q.regular_now(at(16, 4))
    assert not q.regular_now(at(9, 29)) and not q.regular_now(at(16, 5))
    assert not q.regular_now(at(11, 0, (2026, 11, 14)))          # a Saturday
    assert q.regular_now(at(12, 50, (2026, 11, 27)))             # the half day's session
    assert not q.regular_now(at(13, 10, (2026, 11, 27)))         # ...which closes at 13:00
    assert q.SECTOR_TTL < 60


def test_which_stretch_the_cards_show() -> None:
    now = datetime(*MON, 7, 0, tzinfo=ET)
    pre = {"kind": "pre", "day": "2026-11-16"}
    assert u.cards_phase(pre, now) == "pre"
    assert u.cards_phase(pre, datetime(*MON, 10, 0, tzinfo=ET)) == "rth"
    # Before SPY's first pre-market trade, Friday's after hours is the last there is.
    assert u.cards_phase({"kind": "post", "day": "2026-11-13"}, now) == "post"
    assert u.cards_phase(None, now) == "last"
    # A pre-market read from another day is not this morning's.
    assert u.cards_phase({"kind": "pre", "day": "2026-11-13"}, now) == "last"


def test_a_groups_stats_can_read_a_function_of_the_row() -> None:
    rows = [{"sym": "A", "chg": 1.0, "pm": -2.0}, {"sym": "B", "chg": -1.0, "pm": None},
            {"sym": "C", "chg": 2.0, "pm": 0.5}]
    s = u.span_stats(rows, lambda r: r["pm"])
    assert (s["up"], s["down"], s["median"]) == (1, 1, -0.75)
    assert u.span_stats(rows, "chg")["up"] == 2


def _store() -> u.UniverseStore:
    s = u.UniverseStore(path="nul")
    s.pm_ref, s.ah_ref = {}, {}
    rows = [
        {"sym": "AAA", "cap": 5e9, "sector": "XLK", "industry": "Semiconductors", "chg": 2.0,
         "w1": 3.0, "m1": 1.0, "pm_chg": -1.5, "pm_h": 1, "pm_l": 1, "pm_vol": 1},
        {"sym": "BBB", "cap": 5e9, "sector": "XLK", "industry": "Semiconductors", "chg": 1.0,
         "w1": 3.0, "m1": 1.0, "pm_chg": -0.5, "pm_h": 1, "pm_l": 1, "pm_vol": 1},
    ]
    s.rows, s.by_sym, s.read_at = rows, {r["sym"]: r for r in rows}, 1_794_000_000.0
    return s


ETFS = [
    {"key": "SPY", "label": "S&P 500", "day_pct": -0.36, "week_pct": 2.6, "month_pct": -2.0},
    {"key": "XLK", "label": "Technology", "day_pct": -2.01, "week_pct": 1.0, "month_pct": 0.5,
     "rs_day": -1.65},
    {"key": "XLU", "label": "Utilities", "day_pct": 0.5, "week_pct": 1.0, "month_pct": 0.5,
     "rs_day": 0.86},
]


def test_before_the_bell_the_cards_and_their_counts_are_the_pre_markets() -> None:
    now = datetime(*MON, 7, 5, tzinfo=ET)
    ext = {"SPY": {"kind": "pre", "day": "2026-11-16", "pct": -0.51, "at": 1, "bars": 38},
           "XLK": {"kind": "pre", "day": "2026-11-16", "pct": -1.76, "at": 2, "bars": 13}}
    h = _store().heatmap(ETFS, now=now, ext=ext)
    assert (h["cards_phase"], h["ext_day"], h["counts_pre"]) == ("pre", "2026-11-16", True)
    assert h["spy"]["ext"] == -0.51
    xlk = next(c for c in h["cards"] if c["key"] == "XLK")
    assert xlk["ext_pct"] == -1.76 and xlk["rs_ext"] == -1.25 and xlk["ext_bars"] == 13
    # The session's figures are still there for the line beside it.
    assert xlk["day_pct"] == -2.01
    # Its stocks' counts are their pre-market moves: both down before the bell.
    assert (xlk["day"]["up"], xlk["day"]["down"]) == (0, 2)
    # A fund with no pre-market trade yet says nothing rather than an older move.
    xlu = next(c for c in h["cards"] if c["key"] == "XLU")
    assert xlu["ext_pct"] is None and xlu["rs_ext"] is None


def test_after_the_close_the_day_stays_the_sessions_with_the_after_hours_beside_it() -> None:
    now = datetime(*MON, 17, 30, tzinfo=ET)
    ext = {"SPY": {"kind": "post", "day": "2026-11-16", "pct": 0.2, "at": 1, "bars": 10},
           "XLK": {"kind": "post", "day": "2026-11-16", "pct": 0.6, "at": 2, "bars": 4},
           # An older after-hours trade is not this evening's.
           "XLU": {"kind": "post", "day": "2026-11-13", "pct": 0.1, "at": 3, "bars": 1}}
    h = _store().heatmap(ETFS, now=now, ext=ext)
    assert (h["cards_phase"], h["counts_pre"]) == ("post", False)
    xlk = next(c for c in h["cards"] if c["key"] == "XLK")
    assert xlk["ext_pct"] == 0.6 and xlk["day"]["up"] == 2     # the session's own counts
    assert next(c for c in h["cards"] if c["key"] == "XLU")["ext_pct"] is None


def test_from_the_bell_to_0945_the_counts_stay_the_pre_markets() -> None:
    # Handover audit, 09:36 ET on 16 Nov 2026: the cards were the session's at 09:30 but
    # the screener, fifteen minutes behind, still had Friday's `chg`, and the counts under
    # today's fund moves were Friday's. Until 09:45 they are the stocks' pre-market moves.
    h = _store().heatmap(ETFS, now=datetime(*MON, 9, 36, tzinfo=ET), ext={})
    assert (h["cards_phase"], h["basis"], h["counts_pre"]) == ("rth", "pre", True)
    xlk = next(c for c in h["cards"] if c["key"] == "XLK")
    assert xlk["day_pct"] == -2.01                               # the fund's own move, live
    assert (xlk["day"]["up"], xlk["day"]["down"]) == (0, 2)      # not Friday's (2, 0)
    # From 09:45 the screener is on the session and the counts are its moves.
    h = _store().heatmap(ETFS, now=datetime(*MON, 9, 46, tzinfo=ET), ext={})
    assert (h["basis"], h["counts_pre"]) == ("rth", False)
    xlk = next(c for c in h["cards"] if c["key"] == "XLK")
    assert (xlk["day"]["up"], xlk["day"]["down"]) == (2, 0)


def test_the_screener_reads_again_the_tick_its_basis_changes(monkeypatch: Any) -> None:
    # Handover audit, 09:45:10 ET on 16 Nov 2026: a 09:44:16 read (the pre-market's
    # columns) was served as the session's until the next read, up to two minutes on.
    from newsterminal.http import FetchResult
    asked: list[float] = []

    def fake(*_a: Any, **_k: Any) -> FetchResult:
        asked.append(1.0)
        return FetchResult(ok=False, body=None, source="live", age_min=None, error="test")

    monkeypatch.setattr(u, "fetch", fake)
    s = _store()
    s.last_attempt = 0.0
    s.tick(datetime(*MON, 9, 44, 16, tzinfo=ET))
    assert len(asked) == 1 and s.tried_basis == "pre"
    # 54 seconds on, well inside the two-minute wait: the flip makes it due.
    s.tick(datetime(*MON, 9, 45, 10, tzinfo=ET))
    assert len(asked) == 2 and s.tried_basis == "rth"
    # Once, not every tick: thirty seconds later it waits its turn again.
    s.tick(datetime(*MON, 9, 45, 40, tzinfo=ET))
    assert len(asked) == 2


def test_in_the_session_there_is_nothing_extended() -> None:
    h = _store().heatmap(ETFS, now=datetime(*MON, 11, 0, tzinfo=ET),
                         ext={"SPY": {"kind": "pre", "day": "2026-11-16", "pct": -0.5}})
    assert h["cards_phase"] == "rth" and h["ext_day"] is None
    assert all(c["ext_pct"] is None for c in h["cards"])
