"""The live stream: reading a frame, sorting a trade into its session, building candles."""

from __future__ import annotations

import base64
import json
import struct
from datetime import datetime

import pytest

from newsterminal import scan
from newsterminal.scan import ET, Bar
from newsterminal.sources import stream


def _varint(n: int) -> bytes:
    out = bytearray()
    while True:
        b = n & 0x7F
        n >>= 7
        out.append(b | (0x80 if n else 0))
        if not n:
            return bytes(out)


def _zig(n: int) -> int:
    return (n << 1) ^ (n >> 63)


def frame(sym: str, price: float, at_ms: int, hours: int = 1, vol: int | None = None) -> str:
    s = sym.encode()
    b = bytes([(1 << 3) | 2]) + _varint(len(s)) + s
    b += bytes([(2 << 3) | 5]) + struct.pack("<f", price)
    b += bytes([(3 << 3)]) + _varint(_zig(at_ms))
    b += bytes([(7 << 3)]) + _varint(hours)
    if vol is not None:
        b += bytes([(9 << 3)]) + _varint(_zig(vol))
    return json.dumps({"type": "pricing", "message": base64.b64encode(b).decode()})


def ts(y: int, mo: int, d: int, h: int, mi: int, s: int = 0) -> float:
    return datetime(y, mo, d, h, mi, s, tzinfo=ET).timestamp()


MON_0945 = ts(2026, 11, 9, 9, 45)


def test_a_frame_reads_back_as_a_trade() -> None:
    got = stream.parse_frame(frame("NVDA", 179.97, int(MON_0945 * 1000), vol=123456),
                             now=MON_0945 + 2)
    assert got is not None
    sym, t = got
    assert sym == "NVDA" and t.price == pytest.approx(179.97, abs=1e-3)
    assert t.at == MON_0945 and t.session == "rth" and t.day_volume == 123456
    assert t.recv == MON_0945 + 2


@pytest.mark.parametrize(
    "raw",
    ["{\"type\":\"heartbeat\"}", "not base64!!", "", json.dumps({"message": 7}),
     frame("X", 0.0, int(MON_0945 * 1000))],
)
def test_what_is_not_a_trade_is_skipped_not_raised(raw: str) -> None:
    assert stream.parse_frame(raw, now=MON_0945) is None


def test_a_time_a_day_out_is_not_a_trade() -> None:
    raw = frame("X", 5.0, int(MON_0945 * 1000))
    assert stream.parse_frame(raw, now=MON_0945 + 2 * 86400) is None


@pytest.mark.parametrize(
    ("at", "want"),
    [((2026, 11, 9, 3, 59), None), ((2026, 11, 9, 4, 0), "pre"), ((2026, 11, 9, 9, 29), "pre"),
     ((2026, 11, 9, 9, 30), "rth"), ((2026, 11, 9, 15, 59), "rth"), ((2026, 11, 9, 16, 0), "post"),
     ((2026, 11, 9, 19, 59), "post"), ((2026, 11, 9, 20, 0), None),
     ((2026, 11, 8, 12, 0), None),   # a Sunday
     ((2026, 11, 26, 12, 0), None),  # Thanksgiving
     ((2026, 11, 27, 12, 59), "rth"), ((2026, 11, 27, 13, 0), "post"),
     ((2026, 11, 27, 17, 0), None)],
)
def test_the_session_comes_from_the_trades_own_clock(at: tuple[int, ...], want: str | None) -> None:
    assert stream.session_of_ts(ts(*at)) == want


def _s() -> stream.PriceStream:
    s = stream.PriceStream()
    s.check.path = "nul"
    return s


def test_overnight_prints_stay_out_of_the_candles_and_the_last_trade() -> None:
    s = _s()
    night = ts(2026, 11, 8, 22, 34)
    s.take(frame("NVDA", 179.97, int(night * 1000), hours=4))
    assert s.last_trade("NVDA") is None
    q = s.quote("NVDA")
    assert q is not None and "price" not in q
    assert q["overnight"]["price"] == pytest.approx(179.97, abs=1e-3)


def test_candles_build_tick_by_tick_and_a_late_trade_does_not_move_the_last() -> None:
    s = _s()
    for sec, px in ((5, 100.0), (20, 101.0), (40, 99.5), (55, 100.5)):
        s.take(frame("AAA", px, int(ts(2026, 11, 9, 10, 0, sec) * 1000)))
    q = s.quote("AAA")
    assert q is not None
    m = q["minute"]
    assert (m["o"], m["h"], m["l"], m["c"]) == (100.0, 101.0, 99.5, 100.5)
    assert m["t"] == int(ts(2026, 11, 9, 10, 0))
    # Earlier than the newest print: not the last trade.
    s.take(frame("AAA", 98.0, int(ts(2026, 11, 9, 10, 0, 30) * 1000)))
    assert s.last_trade("AAA") == (100.5, ts(2026, 11, 9, 10, 0, 55))


def test_a_share_class_comes_back_in_the_scanners_spelling() -> None:
    s = _s()
    assert s.take(frame("BRK-B", 480.0, int(MON_0945 * 1000))) == "BRK.B"
    assert s.last_trade("BRK.B") is not None


def test_what_is_wanted_is_named_lists_and_open_charts_inside_the_cap() -> None:
    s = _s()
    s.set_targets("tracked", ["AAPL", "NVDA"])
    s.set_targets("candidates", ["NVDA", "IRTC"])
    s.touch("ZZZ")
    assert s.wanted() == ["ZZZ", "AAPL", "NVDA", "IRTC"]
    s.set_targets("candidates", [f"X{i}" for i in range(stream.MAX_NAMES + 50)])
    assert len(s.wanted()) == stream.MAX_NAMES


def test_the_check_scores_a_finished_bucket_and_counts_a_silent_one() -> None:
    chk = stream.StreamCheck(path="nul")
    t0 = int(ts(2026, 11, 9, 10, 0))
    c = stream.Candles()
    for i, px in enumerate((100.0, 100.5, 99.8, 100.2, 100.1)):
        c.add(px, t0 + i * 60)
    bars = [Bar(t0, 100.0, 100.5, 99.8, 100.1, 1000.0),
            Bar(t0 + 300, 100.0, 101.0, 99.0, 100.5, 1000.0)]
    # Only the first bucket is in a download made after it closed.
    assert chk.compare("AAA", c, bars, fetched=t0 + 300 + 40) == 1
    slot = chk.days["2026-11-09"]["rth"]
    assert (slot["compared"], slot["close_ok"], slot["high_ok"], slot["low_ok"]) == (1, 1, 1, 1)
    # The second bucket, now final, has no stream candles.
    assert chk.compare("AAA", c, bars, fetched=t0 + 700) == 1
    assert slot["missing"] == 1
    # Nothing is scored twice.
    assert chk.compare("AAA", c, bars, fetched=t0 + 900) == 0


def test_live_bars_take_the_streams_trade_in_every_session_not_overnight() -> None:
    from newsterminal.sources.scanner import ScanStore

    class Fake:
        def __init__(self, px: float, at: float) -> None:
            self.px, self.at = px, at

        def last_trade(self, _s: str) -> tuple[float, float]:
            return (self.px, self.at)

    store = ScanStore("nul")
    bar_t = int(ts(2026, 11, 9, 7, 0))
    store.bars["AAA"] = [Bar(bar_t, 10.0, 10.2, 9.9, 10.1, 0.0)]
    store.fetched["AAA"] = bar_t + 60
    store.stream = Fake(10.5, bar_t + 120)
    pre = scan.clock_at(datetime(2026, 11, 9, 7, 3, tzinfo=ET))
    bars = store.live_bars("AAA", pre)
    assert bars is not None and (bars[-1].close, bars[-1].high) == (10.5, 10.5)
    # A trade the bars were read after is already in them.
    store.fetched["AAA"] = bar_t + 200
    assert store.live_bars("AAA", pre) == store.bars["AAA"]
