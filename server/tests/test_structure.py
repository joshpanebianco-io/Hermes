"""Fuel, yesterday's shape, confluence and the 200 EMAs (structure.py)."""

from __future__ import annotations

from typing import Any, NamedTuple

import pytest

from newsterminal import structure


class Day(NamedTuple):
    high: float
    low: float
    close: float


def _box(key: str, high: float, low: float, open_: float, close: float, *,
         prior_day: bool = False, status: str = "complete") -> dict[str, Any]:
    return {"key": key, "ok": True, "high": high, "low": low, "open": open_, "close": close,
            "range": high - low, "prior_day": prior_day, "status": status}


def test_the_atr_is_the_mean_true_range_of_the_last_fourteen() -> None:
    days = [Day(110, 90, 100)] * 13 + [Day(130, 100, 120)]      # a gap day at the end
    assert structure.atr14(days) == pytest.approx((20 * 13 + 30) / 14)
    assert structure.atr14(days[:10]) is None


def test_the_ten_minute_200_ema_buckets_five_minute_closes_and_reads_its_slope() -> None:
    stamps = [1_700_000_000 + 300 * i for i in range(500)]
    closes = [100.0 + i * 0.1 for i in range(500)]                 # drifting up
    got = structure.ema200_10m(stamps, closes)
    assert got is not None and got["bars"] == 250 and got["slope"] == "rising"
    assert got["value"] == pytest.approx(structure.ema([closes[2 * i + 1] for i in range(250)],
                                                       200)[-1], abs=1e-4)
    assert structure.ema200_10m(stamps[:300], closes[:300]) is None   # 150 bars: no 200 yet
    flat = structure.ema_read([100.0] * 300)
    assert flat is not None and flat["slope"] == "flat"


def test_which_side_of_the_line() -> None:
    assert structure.side_of(28_900.0, 28_712.0) == "above"
    assert structure.side_of(28_700.0, 28_712.0) == "on"          # within 0.05%
    assert structure.trend_of_line(28_500.0, 28_712.0) == -1
    assert structure.trend_of_line(None, 28_712.0) == 0


def test_fuel_reads_the_night_against_a_normal_day() -> None:
    night = [_box("asia", 29_131, 28_822, 29_109, 28_947),
             _box("overnight", 29_180, 28_822, 29_164, 28_950, status="live")]
    f = structure.fuel(night, atr=412.0, em=480.0)
    assert f is not None and f["range"] == 358 and f["atr_pct"] == 87 and f["em_pct"] == 75
    assert f["line"] == ("range so far 358 · 87% of the 14-day ATR (412) · "
                         "75% of the expected move (±480)")
    assert f["read"] == ("all of it overnight — the open has 13% of a normal day left, "
                         "less room for a retest to travel")
    quiet = structure.fuel([_box("overnight", 29_100, 29_000, 29_050, 29_080, status="live")],
                           atr=412.0, em=None)
    assert quiet is not None and quiet["read"].startswith("a quiet night — 76% of a normal day")
    day = [*night, _box("ny", 29_400, 28_700, 28_950, 29_350, status="live")]
    d = structure.fuel(day, atr=412.0, em=480.0)
    assert d is not None and d["read"].startswith("mostly in New York")
    assert structure.fuel([_box("ny", 1, 0, 0, 1, prior_day=True)], 1.0, 1.0) is None


def test_yesterday_names_the_shape_and_the_gap() -> None:
    boxes = [_box("ny", 29_900, 29_414, 29_850, 29_453, prior_day=True),
             _box("overnight", 29_500, 29_300, 29_415, 29_350, status="live")]
    y = structure.yesterday(boxes, atr=400.0, settle=29_453.0)
    assert y is not None and y["shape"] == "trend day down" and y["close_pos"] == 0.08
    assert y["text"] == ("trend day down · range 486 (1.2× ATR) · closed at 8% of its range · "
                         "gap at 18:00 -38 (0.1 ATR)")
    narrow = structure.yesterday([_box("ny", 29_600, 29_400, 29_450, 29_550, prior_day=True)],
                                 atr=412.0, settle=None)
    assert narrow is not None and narrow["shape"] == "range day" and narrow["gap"] is None
    assert structure.yesterday([_box("asia", 1, 0, 0, 1)], 1.0, None) is None


def test_confluence_bands_rows_within_a_quarter_atr_and_leaves_last_out() -> None:
    rows = [
        {"price": 29_405.0, "label": "Prior RTH low", "kind": "ref"},
        {"price": 29_000.0, "label": "Last", "kind": "last"},
        {"price": 28_948.0, "label": "Prior settle", "kind": "ref"},
        {"price": 28_940.0, "label": "Put wall", "kind": "put"},
        {"price": 28_934.0, "label": "VWAP since 18:00", "kind": "vwap"},
        {"price": 28_900.0, "label": "Expected move low", "kind": "em"},
        {"price": 28_500.0, "label": "Put wall 2", "kind": "put"},
    ]
    bands = structure.confluence(rows, atr=100.0, last=29_000.0)
    assert len(bands) == 1
    assert bands[0]["labels"] == ["Prior settle", "Put wall", "VWAP since 18:00"]
    assert bands[0]["hi"] == 28_948.0 and bands[0]["lo"] == 28_934.0 and bands[0]["dist"] == -59
    assert bands[0]["text"].startswith("Confluence 28,934–28,948: prior settle, put wall, vwap")
    assert [r.get("band") for r in rows] == [None, None, 0, 0, 0, None, None]
    assert structure.confluence(rows, atr=None) == []


def test_the_regime_line_names_the_side_and_what_it_means() -> None:
    up = structure.regime({"ema200": 24_980.0}, 28_970.0)
    assert up is not None and up["above"] and up["pct"] == 15.97
    assert up["text"].startswith("200-day EMA 24,980, 16.0% below last — above it, "
                                  "the daily regime is up")
    down = structure.regime({"ema200": 30_000.0}, 28_970.0)
    assert down is not None and not down["above"] and "rallies are sold" in down["text"]
    assert structure.regime({"sma200": 1.0}, 28_970.0) is None
