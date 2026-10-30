"""
The live levels ladder: VWAP, the opening range and the opens, from the bars
the session boxes already use — and the ladder that carries them (owner,
2026-10-30: the Structure tab's "structure worth tracking").
"""

from __future__ import annotations

from datetime import datetime, timedelta
from typing import Any
from zoneinfo import ZoneInfo

from newsterminal import report
from newsterminal.sources.ranges import anchors, opening_range, vwap_since

ET = ZoneInfo("America/New_York")
Bars = tuple[list[int], list[float], list[float], list[float], list[float]]


def _bars(start: datetime, count: int, step_min: int = 5) -> Bars:
    stamps, highs, lows, closes, vols = [], [], [], [], []
    for i in range(count):
        t = start + timedelta(minutes=step_min * i)
        c = 29000.0 + i
        stamps.append(int(t.timestamp()))
        highs.append(c + 1.0)
        lows.append(c - 1.0)
        closes.append(c)
        vols.append(100.0 if i % 2 == 0 else 300.0)
    return stamps, highs, lows, closes, vols


def at(y: int, mo: int, d: int, h: int, mi: int = 0) -> datetime:
    return datetime(y, mo, d, h, mi, tzinfo=ET)


def test_vwap_weights_by_volume_and_falls_back_to_the_mean() -> None:
    start = at(2026, 9, 15, 18, 0)
    st, hi, lo, cl, vo = _bars(start, 4)
    # Typical prices 29000, 29001, 29002, 29003 with volumes 100, 300, 100, 300.
    assert vwap_since(st, hi, lo, cl, vo, start.timestamp()) == 29001.75
    # From the third bar on: 29002 and 29003 at 100 and 300.
    assert vwap_since(st, hi, lo, cl, vo, st[2]) == 29002.75
    # To an end, exclusive: the first two bars only.
    assert vwap_since(st, hi, lo, cl, vo, st[0], st[2]) == 29000.75
    # No volume at all: the plain mean stands in.
    assert vwap_since(st, hi, lo, cl, [None] * 4, start.timestamp()) == 29001.5
    assert vwap_since(st, hi, lo, cl, vo, st[-1] + 1) is None


def test_the_opening_range_is_the_first_half_hour_and_says_when_it_is_done() -> None:
    open_at = at(2026, 9, 16, 9, 30)
    st, hi, lo, cl, _ = _bars(open_at, 12)                         # 09:30 to 10:25
    ts = open_at.timestamp()
    # Six bars in, 09:30-09:55: still building.
    r = opening_range(st, hi, lo, cl, ts, at(2026, 9, 16, 9, 50).timestamp())
    assert r == {"high": 29006.0, "low": 28999.0, "complete": False}
    # After 10:00 the range is done, and the 10:00 bar itself is outside it.
    r = opening_range(st, hi, lo, cl, ts, at(2026, 9, 16, 10, 20).timestamp())
    assert r == {"high": 29006.0, "low": 28999.0, "complete": True}
    assert opening_range(st, hi, lo, cl, at(2026, 9, 17, 9, 30).timestamp(), 0) is None


def test_the_anchors_are_the_last_reopen_and_todays_cash_open() -> None:
    g, rth = anchors(at(2026, 9, 16, 11, 0))
    assert g.isoformat() == "2026-09-15T18:00:00-04:00"
    assert rth is not None and rth.isoformat() == "2026-09-16T09:30:00-04:00"
    g, rth = anchors(at(2026, 9, 16, 8, 0))
    assert rth is None                                               # cash has not opened
    g, rth = anchors(at(2026, 9, 19, 12, 0))                         # Saturday
    assert g.isoformat() == "2026-09-17T18:00:00-04:00" and rth is None   # Thursday's, all weekend
    g, _ = anchors(at(2026, 9, 16, 19, 0))
    assert g.isoformat() == "2026-09-16T18:00:00-04:00"


def _snap(now: datetime) -> dict[str, Any]:
    return {
        "clock": {"et": now.isoformat()},
        "quotes": [{"key": "NQ", "last": 29100.0, "prev": 29000.0, "pct": 0.3}],
        "ranges": {"assets": {"NQ": {
            "last": 29100.0,
            "vwap": {"globex": 29050.0, "rth": 29120.0},
            "opening_range": {"high": 29180.0, "low": 29080.0, "complete": False},
            "ema200_10m": {"value": 29060.0, "slope": "rising", "bars": 600},
            "sessions": [
                {"key": "overnight", "ok": True, "high": 29200.0, "low": 28900.0,
                 "open": 28950.0, "close": 29100.0, "range": 300.0, "prior_day": False,
                 "status": "complete"},
                {"key": "ny", "ok": True, "high": 29180.0, "low": 29080.0, "open": 29090.0,
                 "close": 29100.0, "range": 100.0, "prior_day": False, "status": "live"},
            ],
        }}},
    }


def test_the_live_ladder_carries_vwap_the_opening_range_and_the_opens() -> None:
    live = report.live_ladders(_snap(at(2026, 9, 16, 9, 50)))["NQ"]
    assert live is not None
    rows = {r["label"]: r for r in live["rows"]}
    assert rows["VWAP since 18:00"]["price"] == 29050.0
    assert rows["VWAP since 18:00"]["kind"] == "vwap"
    assert rows["VWAP since 09:30"]["price"] == 29120.0
    assert rows["Opening range high so far"]["price"] == 29180.0
    assert rows["Globex open 18:00"]["price"] == 28950.0
    assert rows["Globex open 18:00"]["kind"] == "open"
    assert rows["RTH open 09:30"]["price"] == 29090.0
    assert rows["ON high"]["price"] == 29200.0 and rows["Prior settle"]["price"] == 29000.0
    # Price order, last in place, distances measured from it.
    prices = [r["price"] for r in live["rows"]]
    assert prices == sorted(prices, reverse=True)
    assert rows["Last"]["dist"] is None and rows["VWAP since 09:30"]["dist"] == 20.0
    # The ten-minute 200 EMA is a row of its own kind, and the cards ride with the live ladder.
    assert rows["200 EMA (10m)"]["price"] == 29060.0 and rows["200 EMA (10m)"]["kind"] == "ema"
    assert live["ema200_10m"]["slope"] == "rising"
    assert live["fuel"] is not None and live["fuel"]["range"] == 300
    assert live["yesterday"] is None                      # no prior-day New York box in the fixture
    assert "regime" in live and "confluence" in live


def test_the_ladder_bands_its_close_rows_with_the_books_own_atr() -> None:
    snap = _snap(at(2026, 9, 16, 9, 50))
    snap["history"] = {"books": {"NQ": {"ok": True, "atr14": 100.0, "ema200": 27_000.0}}}
    # A quarter of a 100-point ATR is 25 points: the ON high, the opening range
    # high and the RTH high so far (29,200-29,180) are one band; the RTH open,
    # the opening range low and the RTH low so far (29,090-29,080) another.
    live = report.live_ladders(snap)["NQ"]
    assert live is not None
    bands = live["confluence"]
    # Rows at one price keep the order the ladder added them in (RTH before the live rows).
    assert [b["labels"] for b in bands] == [
        ["ON high", "RTH high so far", "Opening range high so far"],
        ["RTH open 09:30", "RTH low so far", "Opening range low so far"],
    ]
    assert bands[0]["hi"] == 29200.0 and bands[0]["lo"] == 29180.0 and bands[0]["dist"] == 90
    assert [r["label"] for r in live["rows"] if r.get("band") == 1] == bands[1]["labels"]
    assert live["regime"]["above"] and live["regime"]["text"].startswith("200-day EMA 27,000")
    assert live["fuel"]["atr_pct"] == 300 and live["fuel"]["line"].startswith("range so far 300")
