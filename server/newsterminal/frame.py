"""
The daily frame — where price sits on the daily chart, for a book or a name.

WHY BOTH DESKS NEED IT (owner, 2026-10-22: "do everything you recommend" —
the assessment found no higher-timeframe context anywhere). The futures
Terminal reads sessions and the scanner reads ten-minute bars, and neither
said whether a break was happening at new highs or inside a downtrend. A
PDH break in a name below its 50 and 200-day and one at a 52-week high read
the same, and they are not the same trade.

THE FRAME IS LEVELS ONLY; THE READ IS DONE AGAINST THE LIVE PRICE. A source
computes the moving averages, the 52-week extremes and last week's range
from FINISHED sessions once an hour and stores them; whoever holds the
current print reads them (`read`), so a frame fetched at 09:00 is still
right at 15:00. Closes before `today` only: a session still forming would
move its own average with every print.

THE AVERAGES ARE SIMPLE, NOT EXPONENTIAL, and 20 / 50 / 200 — the ones the
tape talks about ("below the 200-day"). The ten-minute 8 EMA wave stays the
scanner's; this is the other timeframe, named as such.

PURE. Bars in, levels out; the fetch lives in sources/history.py for the
books and sources/scanner.py for the names.
"""

from __future__ import annotations

from collections.abc import Sequence
from datetime import date
from typing import Any, Protocol

SMA_LENS: tuple[int, ...] = (20, 50, 200)
#: Sessions in a trading year — the 52-week window.
YEAR = 252


class _Day(Protocol):
    """A daily bar as the frame reads it — scan.DayBar fits."""

    @property
    def day(self) -> date: ...
    @property
    def high(self) -> float: ...
    @property
    def low(self) -> float: ...
    @property
    def close(self) -> float: ...


def _mean(xs: list[float]) -> float | None:
    return sum(xs) / len(xs) if xs else None


def frame_of(days: Sequence[_Day], today: date) -> dict[str, Any]:
    """The daily levels from the finished sessions before `today`. Pure.

    `sma20/50/200` are null until that many sessions are held, never a
    shorter average wearing the name. `pw_*` is the last COMPLETED calendar
    week before today's — Monday to Friday, whatever was traded in it.
    """
    done = [d for d in days if d.day < today]
    closes = [float(d.close) for d in done]
    out: dict[str, Any] = {
        "as_of": done[-1].day.isoformat() if done else None,
        "sessions": len(done),
        "prev_close": closes[-1] if closes else None,
    }
    for n in SMA_LENS:
        m = _mean(closes[-n:]) if len(closes) >= n else None
        out[f"sma{n}"] = round(m, 4) if m is not None else None
    year = done[-YEAR:]
    out["wk52_hi"] = round(max(float(d.high) for d in year), 4) if year else None
    out["wk52_lo"] = round(min(float(d.low) for d in year), 4) if year else None
    # Last week's range: the newest completed ISO week before today's.
    this_week = today.isocalendar()[:2]
    weeks: dict[tuple[int, int], list[_Day]] = {}
    for d in done:
        wk = d.day.isocalendar()[:2]
        if wk < this_week:
            weeks.setdefault(wk, []).append(d)
    if weeks:
        last = weeks[max(weeks)]
        out["pw_hi"] = round(max(float(d.high) for d in last), 4)
        out["pw_lo"] = round(min(float(d.low) for d in last), 4)
        out["pw_close"] = round(float(last[-1].close), 4)
    else:
        out["pw_hi"] = out["pw_lo"] = out["pw_close"] = None
    return out


def _above(last: float, level: float | None) -> bool | None:
    return None if level is None else last > level


def read(frame: dict[str, Any] | None, last: float | None) -> dict[str, Any] | None:
    """The frame against a live price: above or below each average, the
    distance from the 52-week high and low, where price sits against last
    week's range, a one-word trend and the sentence the page prints. Pure.

    `trend` is "up" above both the 20 and the 50-day, "down" below both,
    "mixed" between. The 200-day is named in the text and never decides: a
    name can spend a year above it while rolling over, and a pullback to it
    inside an uptrend is not a downtrend.
    """
    if not frame or last is None or last <= 0:
        return None
    above = {n: _above(last, frame.get(f"sma{n}")) for n in SMA_LENS}
    known = [n for n in SMA_LENS if above[n] is not None]
    if 20 in known and 50 in known:
        # The 20 and the 50 decide; the 200 is named in the text only.
        if above[20] and above[50]:
            trend = "up"
        elif not above[20] and not above[50]:
            trend = "down"
        else:
            trend = "mixed"
    else:
        trend = None
    hi, lo = frame.get("wk52_hi"), frame.get("wk52_lo")
    hi_pct = round((last / hi - 1.0) * 100.0, 2) if hi else None
    lo_pct = round((last / lo - 1.0) * 100.0, 2) if lo else None
    pw_hi, pw_lo = frame.get("pw_hi"), frame.get("pw_lo")
    pw = (None if pw_hi is None or pw_lo is None
          else "above" if last > pw_hi else "below" if last < pw_lo else "inside")

    bits: list[str] = []
    if known:
        over = [str(n) for n in known if above[n]]
        under = [str(n) for n in known if not above[n]]

        def names(xs: list[str]) -> str:
            return (", ".join(xs[:-1]) + " and " + xs[-1] if len(xs) > 1 else xs[0]) + "-day"
        if over and not under:
            bits.append(f"Above the {names(over)}")
        elif under and not over:
            bits.append(f"Below the {names(under)}")
        else:
            bits.append(f"Above the {names(over)}, below the {names(under)}")
    if hi_pct is not None:
        bits.append("at a 52-week high" if hi_pct >= 0
                    else f"{abs(hi_pct):.1f}% under the 52-week high")
    if pw:
        bits.append(f"{pw} last week's range")
    return {
        "trend": trend,
        "above20": above[20], "above50": above[50], "above200": above[200],
        "wk52_hi_pct": hi_pct, "wk52_lo_pct": lo_pct,
        "pw": pw,
        "text": " · ".join(bits) if bits else None,
    }


def with_side(fr: dict[str, Any] | None, side: str | None) -> str | None:
    """"with" the daily trend, "against" it, or None — the score's and the flag's word."""
    if not fr or fr.get("trend") is None or side not in ("long", "short"):
        return None
    if fr["trend"] == "mixed":
        return "mixed"
    return "with" if (fr["trend"] == "up") == (side == "long") else "against"
