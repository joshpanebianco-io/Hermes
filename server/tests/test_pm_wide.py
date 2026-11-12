"""
The pre-market range on a day the bars start late (scan.technicals `pm_wide`,
ScanStore.pm_wide).

Worked on Wed 11 Nov 2026, the morning Yahoo had no pre-market bar before 05:20 ET
for any Nasdaq-listed name: NVDA's bars ran 177.02 to 178.36 and the pre-market had
already traded 172.66.
"""

from __future__ import annotations

from datetime import date, datetime
from typing import Any

from newsterminal import scan
from newsterminal.scan import ET, Bar
from newsterminal.sources import scanner as scan_src


def et(y: int, mo: int, d: int, h: int, mi: int) -> datetime:
    return datetime(y, mo, d, h, mi, tzinfo=ET)


def ts(y: int, mo: int, d: int, h: int, mi: int) -> int:
    return int(et(y, mo, d, h, mi).timestamp())


def _bars() -> list[Bar]:
    # Tuesday's whole session, then Wednesday's pre-market from 05:20 only.
    tue = [Bar(ts(2026, 11, 10, 9, 30) + i * 300, 180, 181, 179, 180, 1000.0) for i in range(78)]
    wed = [Bar(ts(2026, 11, 11, 5, 20) + i * 300, 177.5, 178.36, 177.02, 178.0, 0.0)
           for i in range(6)]
    return tue + wed


def test_a_second_read_widens_a_pre_market_range_the_bars_cut_short() -> None:
    clock = scan.clock_at(et(2026, 11, 11, 5, 50))
    bars = _bars()
    alone = scan.technicals(bars, [], clock)
    assert (alone.pmh, alone.pml) == (178.36, 177.02)
    assert (alone.pmh_bars, alone.pml_bars) == (178.36, 177.02)
    # The screener's read: a low the bars never saw, and a high a quarter hour behind them.
    wide = scan.technicals(bars, [], clock, pm_wide=(177.74, 172.66))
    assert (wide.pmh, wide.pml) == (178.36, 172.66)
    assert (wide.pmh_bars, wide.pml_bars) == (178.36, 177.02)
    # Half a read, or a figure that is not a price, changes only what it can.
    assert scan.technicals(bars, [], clock, pm_wide=(None, 172.66)).pmh == 178.36
    odd = scan.technicals(bars, [], clock, pm_wide=(0.0, -1.0))
    assert (odd.pmh, odd.pml) == (178.36, 177.02)
    # No pre-market bars at all (two names had none that morning): the read stands in.
    none = scan.technicals(bars[:78], [], clock, pm_wide=(236.01, 234.0))
    assert (none.pmh, none.pml, none.pmh_bars, none.pml_bars) == (236.01, 234.0, None, None)
    # The row carries both, so the page can say the candles stop short of the level.
    row = scan.row_of("NVDA", wide, None, None, clock)
    assert (row["levels"]["pml"], row["levels"]["pml_bars"]) == (172.66, 177.02)
    assert (row["levels"]["pmh"], row["levels"]["pmh_bars"]) == (178.36, 178.36)


def test_the_widest_range_of_the_day_is_kept_and_the_next_day_starts_clean(tmp_path: Any) -> None:
    s = scan_src.ScanStore(str(tmp_path / "wl.json"))
    wed = date(2026, 11, 11)
    assert s.pm_wide("NVDA", wed) is None          # no second read at all
    reads: dict[str, tuple[float | None, float | None]] = {"NVDA": (177.74, 172.66)}
    s.pm_hint = lambda sym, td: reads.get(sym)
    assert s.pm_wide("NVDA", wed) == (177.74, 172.66)
    # Later: a higher high, and a low that reaches less far. The range only grows.
    reads["NVDA"] = (178.40, 174.00)
    assert s.pm_wide("NVDA", wed) == (178.40, 172.66)
    # The read drops the name (its columns rolled, the feed is down): the level holds.
    reads.clear()
    assert s.pm_wide("NVDA", wed) == (178.40, 172.66)
    assert s.pm_wide("AAPL", wed) is None
    # A figure that is not a price is not a range.
    reads["AAPL"] = (0.0, None)
    assert s.pm_wide("AAPL", wed) is None
    # The next day starts from nothing.
    reads["NVDA"] = (171.0, 169.0)
    assert s.pm_wide("NVDA", date(2026, 11, 12)) == (171.0, 169.0)
