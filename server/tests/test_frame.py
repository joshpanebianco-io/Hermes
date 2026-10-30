"""The daily frame: levels from finished sessions only, the read against a live
print, and the with / against word the score and the flag use."""

from __future__ import annotations

from datetime import date, timedelta

import pytest

from newsterminal import frame
from newsterminal.scan import DayBar


def _days(n: int, start: float = 100.0, step: float = 0.5, first: date = date(2025, 10, 1),
          high_pad: float = 1.0) -> list[DayBar]:
    out: list[DayBar] = []
    d, px = first, start
    while len(out) < n:
        if d.weekday() < 5:
            out.append(DayBar(d, px, px + high_pad, px - high_pad, px, 1_000.0))
            px += step
        d += timedelta(days=1)
    return out


def test_frame_uses_finished_sessions_only_and_names_the_averages() -> None:
    days = _days(260)
    today = days[-1].day  # the newest bar is today's, still forming
    fr = frame.frame_of(days, today)
    assert fr["as_of"] == days[-2].day.isoformat()
    assert fr["sessions"] == 259
    closes = [d.close for d in days[:-1]]
    assert fr["sma20"] == pytest.approx(sum(closes[-20:]) / 20, abs=1e-6)
    assert fr["sma200"] == pytest.approx(sum(closes[-200:]) / 200, abs=1e-6)
    assert fr["wk52_hi"] == pytest.approx(max(d.high for d in days[:-1][-252:]))
    assert fr["prev_close"] == closes[-1]
    # The 200 EMA and the 14-day ATR ride with the frame (structure.py, 2026-10-30).
    assert fr["ema200"] is not None and fr["atr14"] is not None


def test_short_history_has_no_long_average_wearing_the_name() -> None:
    fr = frame.frame_of(_days(60), date(2026, 12, 31))
    assert fr["sma20"] is not None and fr["sma50"] is not None
    assert fr["sma200"] is None and fr["ema200"] is None


def test_last_week_is_the_completed_week_before_today() -> None:
    # Tuesday 2026-10-20: last week is Mon 12 – Fri 16 October.
    days = _days(30, first=date(2026, 9, 7))
    today = date(2026, 10, 20)
    fr = frame.frame_of(days, today)
    week = [d for d in days if date(2026, 10, 12) <= d.day <= date(2026, 10, 16)]
    assert fr["pw_hi"] == pytest.approx(max(d.high for d in week))
    assert fr["pw_lo"] == pytest.approx(min(d.low for d in week))
    assert fr["pw_close"] == pytest.approx(week[-1].close)


def test_read_words_the_position_and_the_trend() -> None:
    fr = {"sma20": 100.0, "sma50": 95.0, "sma200": 90.0, "wk52_hi": 120.0, "wk52_lo": 80.0,
          "pw_hi": 105.0, "pw_lo": 98.0}
    up = frame.read(fr, 110.0)
    assert up is not None
    assert up["trend"] == "up"
    assert up["text"] == ("Above the 20, 50 and 200-day · 8.3% under the 52-week high · "
                          "above last week's range")
    down = frame.read(fr, 85.0)
    assert down is not None and down["trend"] == "down"
    assert down["text"].startswith("Below the 20, 50 and 200-day")
    mixed = frame.read(fr, 97.0)
    assert mixed is not None and mixed["trend"] == "mixed"
    assert mixed["text"].startswith("Above the 50 and 200-day, below the 20-day")
    assert mixed["pw"] == "below"


def test_read_without_the_fifty_has_no_trend_and_no_frame_is_none() -> None:
    assert frame.read({"sma20": 100.0, "sma50": None, "sma200": None}, 101.0)["trend"] is None
    assert frame.read(None, 100.0) is None
    assert frame.read({"sma20": 1.0}, None) is None


@pytest.mark.parametrize(
    ("trend", "side", "word"),
    [("up", "long", "with"), ("up", "short", "against"), ("down", "short", "with"),
     ("down", "long", "against"), ("mixed", "long", "mixed"), (None, "long", None),
     ("up", None, None)],
)
def test_with_side(trend: str | None, side: str | None, word: str | None) -> None:
    assert frame.with_side({"trend": trend}, side) == word
