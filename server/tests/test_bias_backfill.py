"""tools/bias_backfill.py: the clock and the roll rules a backfilled read stands on."""

from __future__ import annotations

import importlib.util
from datetime import date, datetime
from pathlib import Path
from zoneinfo import ZoneInfo

_spec = importlib.util.spec_from_file_location(
    "bias_backfill", Path(__file__).resolve().parent.parent / "tools" / "bias_backfill.py")
assert _spec is not None and _spec.loader is not None
bf = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(bf)

ET = ZoneInfo("America/New_York")


def ts(y: int, m: int, d: int, h: int, mi: int = 0) -> int:
    return int(datetime(y, m, d, h, mi, tzinfo=ET).timestamp())


def bar(t: int, c: float, lo: float | None = None, hi: float | None = None,
        o: float | None = None, v: float = 100.0) -> tuple[int, float, float, float, float, float]:
    return (t, c if o is None else o, c if hi is None else hi, c if lo is None else lo, c, v)


def test_a_price_is_the_last_printed_by_then() -> None:
    s = bf.Series([bar(ts(2025, 3, 4, 8), 10.0), bar(ts(2025, 3, 4, 9), 11.0),
                   bar(ts(2025, 3, 4, 10), 12.0, o=11.5)])
    assert s.at(ts(2025, 3, 4, 7)) is None
    # On the hour the bar that ended wins the tie with the one that opened.
    assert s.at(ts(2025, 3, 4, 10)).price == 11.0
    assert s.at(ts(2025, 3, 4, 10, 30)).price == 11.0
    assert s.at(ts(2025, 3, 4, 11)).price == 12.0
    # After a gap (the 10-year's bars start at :20) a bar's open is the newest print.
    t = bf.Series([bar(ts(2025, 3, 3, 14, 20), 4.50), bar(ts(2025, 3, 4, 8, 20), 4.55, o=4.52)])
    p = t.at(ts(2025, 3, 4, 8, 45))
    assert (p.price, p.asof) == (4.52, ts(2025, 3, 4, 8, 20))
    assert t.live(ts(2025, 3, 4, 8, 45)) and not t.live(ts(2025, 3, 4, 3, 0))


def _quiet(day: tuple[int, int, int], hours: range, px: float) -> list:
    return [bar(ts(*day, h), px, lo=px * 0.9995, hi=px * 1.0005, o=px * 0.9997) for h in hours]


def test_a_seam_is_a_bar_whose_whole_range_left_the_last_close() -> None:
    bars = _quiet((2025, 3, 4), range(1, 11), 100.0)
    bars.append(bar(ts(2025, 3, 4, 11), 101.8, lo=101.5, hi=102.0, o=101.6))  # a switch
    bars.append(bar(ts(2025, 3, 4, 12), 101.9, lo=99.9, hi=104.0, o=104.0))  # a bad open
    bars += _quiet((2025, 3, 4), range(13, 17), 101.9)
    bars.append(bar(ts(2025, 3, 4, 18), 103.9, lo=103.5, hi=104.0, o=103.6))  # the halt: a gap
    s = bf.Series(bars)
    assert s.seams() == [10]


def test_a_weekend_roll_is_placed_at_the_bar_that_jumped() -> None:
    fut = (_quiet((2025, 3, 6), range(9, 17), 1000.0) + _quiet((2025, 3, 7), range(9, 17), 1000.0)
           + _quiet((2025, 3, 9), range(18, 24), 1010.0)
           + _quiet((2025, 3, 10), range(0, 17), 1010.0))
    days = ((2025, 3, 6), (2025, 3, 7), (2025, 3, 10))
    etf = [bar(ts(y, m, d, h, 30), 100.0) for (y, m, d) in days for h in range(9, 16)]
    f = bf.Series(fut)
    spans = bf.roll_spans(f, bf.Series(etf), 0.5, 1)
    sunday = f.ts.index(ts(2025, 3, 9, 18))
    assert spans == [(sunday - 1, sunday)]
    # A read from Friday into Monday straddles it; one from Monday's open does not.
    assert bf.crosses(spans, f.ts.index(ts(2025, 3, 7, 9)), f.ts.index(ts(2025, 3, 10, 15)))
    assert not bf.crosses(spans, f.ts.index(ts(2025, 3, 10, 9)), f.ts.index(ts(2025, 3, 10, 15)))
    # Gold's ratio steps down only on a basis move: a sign-checked book ignores it.
    assert bf.roll_spans(bf.Series([(t, o * 0.99, h * 0.99, lo * 0.99, c * 0.99, v)
                                    if t >= ts(2025, 3, 9, 18) else (t, o, h, lo, c, v)
                                    for t, o, h, lo, c, v in fut]),
                         bf.Series(etf), 0.5, 1) == []


def test_the_marks_of_a_session() -> None:
    names = lambda td: [m for m, _ in bf.mark_instants(td)]  # noqa: E731
    every = ["20:00", "03:30", "08:45", "09:25", "10:30", "12:00", "14:00"]
    # Monday: Sunday's evening is its 20:00.
    assert names(date(2025, 3, 3)) == every
    assert bf.mark_instants(date(2025, 3, 3))[0][1] == datetime(2025, 3, 2, 20, 0, tzinfo=ET)
    # The day after Thanksgiving closes at 13:00; Thanksgiving's evening is its 20:00.
    assert names(date(2025, 11, 28)) == every[:-1]
    # The Tuesday after Labor Day reads Monday's evening.
    assert bf.mark_instants(date(2025, 9, 2))[0][1] == datetime(2025, 9, 1, 20, 0, tzinfo=ET)


def _two_days() -> object:
    bars = []
    for h in range(0, 24):
        if h != 17:
            bars.append(bar(ts(2025, 3, 3, h), 100.0 + h, lo=99.0 + h, hi=101.0 + h, v=10.0 + h))
    for h in range(0, 11):
        bars.append(bar(ts(2025, 3, 4, h), 200.0 + h, lo=199.0 + h, hi=201.0 + h))
    return bf.Series(bars)


def test_the_box_the_board_reads_is_the_last_completed() -> None:
    s = _two_days()
    rows, first = bf.boxes(s, datetime(2025, 3, 4, 10, 0, tzinfo=ET))
    got = {r["label"]: (r["low"], r["high"]) for r in rows}
    assert "New York" not in got  # under way: the collector marks it live, the board skips it
    assert got["Pre-market"] == (203.0, 209.0)  # Tuesday 04:00-08:00 bars
    assert got["London"] == (201.0, 205.0)  # 02:00-04:00 ET while London is on GMT
    assert s.ts[first] == ts(2025, 3, 4, 4)
    rows, first = bf.boxes(s, datetime(2025, 3, 4, 3, 0, tzinfo=ET))
    assert "London" not in {r["label"] for r in rows}  # under way
    assert s.ts[first] == ts(2025, 3, 3, 20)  # Asia's
    rows, first = bf.boxes(s, datetime(2025, 3, 3, 20, 0, tzinfo=ET))
    got = {r["label"]: (r["low"], r["high"]) for r in rows}
    assert "Asia" not in got and got["New York"] == (108.0, 116.0)  # the 09:00-15:00 bars
    assert s.ts[first] == ts(2025, 3, 3, 9)


def test_the_prior_value_area_sits_inside_the_session() -> None:
    s = _two_days()
    va, first = bf.value_area(s, datetime(2025, 3, 4, 10, 0, tzinfo=ET), "NQ")
    assert va is not None and s.ts[first] == ts(2025, 3, 3, 9)
    assert 108.0 <= va["val"] <= va["poc"] <= va["vah"] <= 116.0
