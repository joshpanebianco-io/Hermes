"""
Day 1, Day 2, Day 3: the ledger and what a track is called.

APP is the worked example: +31.04% on 4.0x volume on Thu 5 Nov 2026, a Day 2 on
Friday that broke $365.33 and closed above it, a Day 3 on Monday.
"""

from __future__ import annotations

from datetime import date
from typing import Any

import pytest

from newsterminal import momentum as m

THU, FRI, MON, TUE = date(2026, 11, 5), date(2026, 11, 6), date(2026, 11, 9), date(2026, 11, 10)


def row(sym: str = "APP", **kw: Any) -> dict[str, Any]:
    base: dict[str, Any] = {
        "sym": sym, "name": sym, "sector": "XLK", "cap": 130e9, "avg": 5e6, "close": 391.0,
        "chg": 9.86, "open": 372.0, "high": 398.0, "low": 368.0, "vol": 10.5e6,
        "o1": 300.0, "h1": 365.33, "l1": 338.88, "c1": 356.0, "v1": 20e6,
        "h2": 290.0, "l2": 268.0, "c2": 271.67, "v2": 6e6,
    }
    base.update(kw)
    return base


def store() -> m.MomentumStore:
    return m.MomentumStore(path="nul")


def test_the_first_run_seeds_yesterdays_day_1_with_today_as_its_day_2() -> None:
    s = store()
    assert s.update([row()], FRI)
    t = s.tracks["APP|2026-11-05"]
    assert t["side"] == "long" and t["move"] == pytest.approx(31.04, abs=0.01) and t["vx"] == 4.0
    assert [b["day"] for b in t["days"]] == ["2026-11-06"]
    assert t["d1"]["h"] == 365.33
    assert s.last_day == "2026-11-06"


def test_today_can_be_a_day_1_of_its_own() -> None:
    s = store()
    s.update([row("NEW", chg=-22.0, vol=10e6, c1=100.0, c2=100.0)], FRI)
    assert s.tracks["NEW|2026-11-06"]["side"] == "short"
    assert "NEW|2026-11-05" not in s.tracks


@pytest.mark.parametrize(
    "kw", [{"chg": 9.9}, {"vol": 7e6}, {"cap": 2e8}, {"chg": None}, {"avg": None}],
)
def test_what_is_not_a_day_1(kw: dict[str, Any]) -> None:
    s = store()
    s.last_day = "2026-11-05"  # past the first run, so only today can qualify
    s.update([row("NOPE", **{"chg": 22.0, "vol": 10e6, **kw})], FRI)
    assert not s.tracks


def test_the_books_close_once_a_session_and_a_track_takes_each_days_bar() -> None:
    s = store()
    s.update([row()], FRI)
    assert not s.update([row()], FRI)
    assert s.update([row(close=400.0, high=405.0, low=389.0, chg=2.3)], MON)
    t = s.tracks["APP|2026-11-05"]
    assert [b["day"] for b in t["days"]] == ["2026-11-06", "2026-11-09"]
    assert t["days"][-1]["c"] == 400.0
    assert not s.update([row()], FRI)  # a read of an older session does nothing


def test_the_day_number_counts_trading_days_and_a_session_in_progress() -> None:
    s = store()
    s.update([row()], FRI)
    t = s.tracks["APP|2026-11-05"]
    # Sunday night: Friday was the last session, its Day 2.
    assert s.stage(t, date(2026, 11, 8), session_on=False) == 2
    # Monday once the pre-market is on: its Day 3.
    assert s.stage(t, MON, session_on=True) == 3
    assert s.stage(t, TUE, session_on=True) == 4
    assert m.sessions_after(THU, MON) == 2
    # Thanksgiving is not a session.
    assert m.sessions_after(date(2026, 11, 25), date(2026, 11, 27)) == 1


def test_an_old_track_expires() -> None:
    s = store()
    s.update([row()], FRI)
    for d in (MON, TUE, date(2026, 11, 11)):
        s.update([row(chg=1.0, vol=1e6)], d)
    assert "APP|2026-11-05" in s.tracks       # Day 5 on the 11th
    s.update([row(chg=1.0, vol=1e6)], date(2026, 11, 12))
    assert "APP|2026-11-05" not in s.tracks   # Day 6 on the 12th


@pytest.mark.parametrize(
    ("side", "basis", "hi", "lo", "last", "want"),
    [("long", "last", 398.0, 368.0, 391.0, ("Broke PDH, closed above", "confirmed")),
     ("long", "rth", 398.0, 368.0, 391.0, ("Broke PDH, above it", "confirmed")),
     ("long", "last", 370.0, 345.0, 350.0, ("Broke PDH, faded", "watch")),
     ("long", "last", 360.0, 345.0, 350.0, ("Inside day", "inside")),
     ("long", "last", 364.0, 330.0, 335.0, ("Under PDH", "watch")),
     ("long", "pre", None, None, 370.0, ("Above PDH", "confirmed")),
     ("long", "pre", None, None, 360.0, ("Under PDH", "watch")),
     ("long", "last", 364.0, 290.0, 295.0, ("Lost Day 1's low", "failed")),
     ("short", "last", 360.0, 330.0, 335.0, ("Broke PDL, closed below", "confirmed")),
     ("short", "last", 370.0, 345.0, 350.0, ("Over PDL", "watch")),
     ("short", "last", 360.0, 345.0, 350.0, ("Inside day", "inside"))],
)
def test_what_a_track_is_called(side: str, basis: str, hi: float | None, lo: float | None,
                                last: float, want: tuple[str, str]) -> None:
    assert m.state_of(side, basis, hi, lo, last, 365.33, 338.88, 300.0, 400.0) == want


def _table(s: m.MomentumStore, rows: dict[str, dict[str, Any]], **kw: Any) -> dict[str, Any]:
    def read(sym: str) -> dict[str, Any]:
        r = rows[sym]
        return {"last": r["close"], "chg": r["chg"], "pdh": r["h1"], "pdl": r["l1"],
                "adv_pct": 210.0, "pd_state": "above", "live": False}

    args: dict[str, Any] = {"read": read, "raw": rows.get, "catalyst": lambda _s: None,
                            "spark": lambda _s: None, "tracked": frozenset(), "pinned": frozenset(),
                            "basis": "last", "today": date(2026, 11, 8), "min_move": 20.0,
                            "cap": 2e9, "chip": "all", "forming": []}
    args.update(kw)
    return s.table(**args)


def test_the_table_reads_a_track_against_now() -> None:
    s = store()
    s.update([row()], FRI)
    got = _table(s, {"APP": row()})
    r = got["rows"][0]
    assert (r["stage"], r["side"], r["moved"], r["state"]) == (2, "long", "2026-11-05",
                                                               "Broke PDH, closed above")
    assert r["to_level"] == pytest.approx(7.0, abs=0.1) and r["level"] == 365.33
    assert got["chips"]["day2"] == 1 and got["chips"]["long"] == 1


def test_the_filters_take_a_track_out_without_losing_it() -> None:
    s = store()
    s.update([row(move=None, c1=120.0, c2=100.0, h1=125.0, l1=110.0)], FRI)   # a 20% Day 1
    s.update([row("SMALL", cap=5e8, c1=150.0, c2=100.0)], FRI)
    rows = {"APP": row(c1=120.0, c2=100.0, h1=125.0, l1=110.0)}
    assert len(_table(s, rows, min_move=30.0)["rows"]) == 0
    assert len(_table(s, rows, min_move=20.0)["rows"]) == 1
