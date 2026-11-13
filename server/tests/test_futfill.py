"""The ETF fill for the futures charts (futfill.py): the ratio, the hours it fills, the
gap it will not cross, and the tick in the future's prices."""

from __future__ import annotations

from datetime import datetime
from zoneinfo import ZoneInfo

from newsterminal import futfill as ff
from newsterminal.scan import Bar

ET = ZoneInfo("America/New_York")


def t(h: int, m: int, day: int = 13) -> int:
    return int(datetime(2026, 11, day, h, m, tzinfo=ET).timestamp())


def bar(at: int, c: float) -> Bar:
    return Bar(at, c, c + 1.0, c - 1.0, c, 100.0)


def test_the_ratio_is_the_median_of_the_shared_minutes() -> None:
    fut = [bar(t(9, m), 25000.0 + m) for m in range(0, 12)]
    etf = [bar(t(9, m), 600.0) for m in range(0, 20)]
    etf[5] = bar(t(9, 5), 1.0)   # one odd print does not set it
    r = ff.ratio(fut, etf)
    assert r is not None
    assert abs(r[0] - (25000.0 + 7) / 600.0) < 0.02 and r[1] == t(9, 11)
    assert ff.ratio(fut, [bar(t(10, 0), 600.0)]) is None


def test_it_fills_after_the_futures_last_minute_in_the_futures_prices() -> None:
    etf = [bar(t(9, m), 600.0) for m in range(0, 25)]
    got = ff.fill(t(9, 12), etf, 42.0, t(9, 22))
    assert [b.t for b in got] == [t(9, m) for m in range(13, 23)]
    assert got[0].close == 600.0 * 42.0 and got[0].volume == 0.0


def test_it_never_fills_the_halt_the_small_hours_or_a_shut_day() -> None:
    etf = [bar(t(16, 50) + 60 * i, 600.0) for i in range(20)]           # 16:50 to 17:09
    got = ff.fill(t(16, 49), etf, 2.0, t(17, 9))
    assert max(datetime.fromtimestamp(b.t, ET).hour * 60 + datetime.fromtimestamp(b.t, ET).minute
               for b in got) == 16 * 60 + 59
    assert ff.fill(t(3, 0), [bar(t(3, 30), 600.0)], 2.0, t(3, 40)) == []
    assert not ff.fillable(t(10, 0, day=14))                              # Saturday
    assert ff.fillable(t(4, 0)) and not ff.fillable(t(3, 59))


def test_a_stopped_feed_is_not_filled_past_half_an_hour() -> None:
    etf = [bar(t(10, 0) + 60 * i, 600.0) for i in range(60)]
    got = ff.fill(t(10, 0), etf, 2.0, t(10, 59))
    assert got[-1].t - t(10, 0) <= ff.MAX_GAP_SEC


def test_the_tick_is_the_etfs_trade_in_the_futures_prices() -> None:
    q = {"price": 600.5, "at": float(t(9, 40)), "session": "rth",
         "minute": {"t": t(9, 40), "o": 600.0, "h": 601.0, "l": 599.5, "c": 600.5}}
    got = ff.scaled_tick(q, 41.6, "NQ", "QQQ")
    assert got is not None and got["sym"] == "NQ" and got["via"] == "etf"
    assert got["price"] == round(600.5 * 41.6, 4) and got["minute"]["h"] == round(601.0 * 41.6, 4)
    assert ff.scaled_tick({**q, "at": float(t(17, 30))}, 41.6, "NQ", "QQQ") is None
    assert ff.scaled_tick(None, 41.6, "NQ", "QQQ") is None


def test_with_no_stream_trade_the_newest_minute_bar_stands_in() -> None:
    q = ff.bar_quote(Bar(t(9, 41), 300.0, 301.0, 299.0, 300.5, 10.0), float(t(9, 41) + 20))
    assert q["price"] == 300.5 and q["at"] == float(t(9, 41) + 20) and q["session"] == "rth"
    got = ff.scaled_tick(q, 10.9, "GC", "GLD")
    assert got is not None and got["price"] == round(300.5 * 10.9, 4)
    assert ff.bar_quote(Bar(t(8, 0), 1, 1, 1, 1, 0), float(t(8, 5)))["session"] == "pre"
