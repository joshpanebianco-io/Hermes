"""
Structure reads the Structure tab did not have (owner, 2026-10-30: "is there
anything else worth adding to the structure tabs?" — "lets do it").

FOUR PURE BUILDERS, each a few lines of arithmetic on data the collector
already holds, each printed as one line the tab shows and the brief can name:

  fuel        How much of a normal day the book has already traded — today's
              range so far against the 14-day ATR and the expected move, and
              WHERE it was spent (overnight, or in New York). "Has NQ done its
              day's work before the open?" is the question a 09:40 retest
              depends on; the stocks desk had it and the futures desk did not.
  yesterday   The shape of the prior cash session — trend day or range day,
              where it closed in its range, and the gap at the Globex reopen.
              A trend day that closed on its low followed by a flat night reads
              nothing like a range day, and the tab showed the levels but not
              the shape.
  confluence  Ladder rows within a quarter of an ATR of each other, grouped.
              When a put wall, a prior low and VWAP sit together, the band is
              the level, not any one row.
  the 200s    The ten-minute 200 EMA, the strategy's side filter on its own
              timeframe (longs above it, shorts below; retests against it tend
              to fail) — a ladder row, a driver vote and a scanner column —
              and the daily 200 EMA as the regime line under the ladder.

THE EMA IS PINE'S, mirrored from scan.ema (seeded with the first value, alpha
2 / (n + 1)) rather than imported, because scan imports this module for the
scanner's own 200 and a cycle would be the price of sharing six lines.
"""

from __future__ import annotations

from collections.abc import Iterable, Sequence
from typing import Any, Protocol

#: The long EMA, on the ten-minute chart and on the daily.
EMA_LEN = 200
#: Bars the EMA's slope is read over — an hour on ten-minute bars.
EMA_SLOPE_BARS = 6
#: Inside this many percent over those bars the slope reads "flat".
EMA_SLOPE_PCT = 0.02
#: Price within this many percent of the line is "on it", not a side.
ON_LINE_PCT = 0.05
#: The same for the daily 200, a line read in percent rather than ticks.
DAILY_ON_PCT = 0.5
#: The daily ATR's length.
ATR_LEN = 14
#: Rows this many ATRs apart, top to bottom, are one band.
CONFLUENCE_ATR = 0.25
#: A band needs this many rows to be named.
CONFLUENCE_MIN = 3
#: A session this many ATRs wide, closing in its outer fifth, is a trend day.
TREND_DAY_ATR = 1.2
#: A session this narrow is a range day.
RANGE_DAY_ATR = 0.8
#: The outer fifth of the range, for the close.
CLOSE_EDGE = 0.2
#: A night that has used less than this much of the ATR is a quiet one.
QUIET_NIGHT_ATR = 0.4
#: With this much or less of a normal day left, a retest has little room.
LITTLE_LEFT_PCT = 35
#: Ten minutes, for bucketing five-minute closes.
TEN_MIN = 600


class _Day(Protocol):
    @property
    def high(self) -> float: ...
    @property
    def low(self) -> float: ...
    @property
    def close(self) -> float: ...


def ema(xs: Sequence[float], n: int) -> list[float]:
    """Pine's ta.ema, as scan.ema computes it. Pure."""
    alpha = 2.0 / (n + 1)
    out: list[float] = []
    e: float | None = None
    for x in xs:
        e = x if e is None else alpha * x + (1 - alpha) * e
        out.append(e)
    return out


def atr14(days: Sequence[_Day], n: int = ATR_LEN) -> float | None:
    """The mean true range of the last `n` sessions, oldest first. Pure."""
    trs: list[float] = []
    prev: float | None = None
    for d in days:
        h, lo, c = float(d.high), float(d.low), float(d.close)
        trs.append(h - lo if prev is None else max(h - lo, abs(h - prev), abs(lo - prev)))
        prev = c
    if len(trs) < n:
        return None
    return sum(trs[-n:]) / n


def ema_read(closes: Sequence[float], n: int = EMA_LEN) -> dict[str, Any] | None:
    """The long EMA's last value and its slope over the last hour of bars, or
    None until `n` closes are held — never a shorter average wearing the name."""
    xs = [float(c) for c in closes]
    if len(xs) < n:
        return None
    e = ema(xs, n)
    value = e[-1]
    back = e[-1 - EMA_SLOPE_BARS] if len(e) > EMA_SLOPE_BARS else e[0]
    chg = (value - back) / back * 100.0 if back else 0.0
    slope = "rising" if chg > EMA_SLOPE_PCT else "falling" if chg < -EMA_SLOPE_PCT else "flat"
    return {"value": round(value, 4), "slope": slope, "bars": len(xs)}


def ema200_10m(stamps: Iterable[Any], closes: Iterable[Any]) -> dict[str, Any] | None:
    """The ten-minute 200 EMA from five-minute bars: each ten-minute bucket's
    last close is that bar's close. Pure."""
    buckets: dict[int, float] = {}
    for t, c in zip(stamps, closes, strict=False):
        if isinstance(t, bool) or isinstance(c, bool):
            continue
        if not isinstance(t, int | float) or not isinstance(c, int | float):
            continue
        buckets[int(t) // TEN_MIN] = float(c)
    return ema_read(list(buckets.values()))


def side_of(last: float | None, line: float | None, band_pct: float = ON_LINE_PCT) -> str | None:
    """"above", "below" or "on" the line (within `band_pct`), or None."""
    if last is None or line is None or line <= 0:
        return None
    pct = (last - line) / line * 100.0
    if abs(pct) <= band_pct:
        return "on"
    return "above" if pct > 0 else "below"


def trend_of_line(last: float | None, line: float | None) -> int:
    """The scanner's column: 1 above the line, -1 below, 0 on it or unknown."""
    side = side_of(last, line)
    return 1 if side == "above" else -1 if side == "below" else 0


# --------------------------------------------------------------------------

def _fmt(v: float, dp: int) -> str:
    return f"{v:,.{dp}f}"


def _today(sessions: Iterable[Any]) -> list[dict[str, Any]]:
    return [s for s in sessions
            if isinstance(s, dict) and s.get("ok") and not s.get("prior_day")
            and isinstance(s.get("high"), int | float) and isinstance(s.get("low"), int | float)]


def fuel(sessions: Iterable[Any], atr: float | None, em: float | None, dp: int = 0
         ) -> dict[str, Any] | None:
    """Today's range so far against a normal day, and where it was spent."""
    boxes = _today(sessions)
    if not boxes:
        return None
    hi = max(float(s["high"]) for s in boxes)
    lo = min(float(s["low"]) for s in boxes)
    r = hi - lo
    by = {s.get("key"): s for s in boxes}
    on, ny = by.get("overnight"), by.get("ny")
    on_r = float(on["range"]) if on and isinstance(on.get("range"), int | float) else None
    ny_r = float(ny["range"]) if ny and isinstance(ny.get("range"), int | float) else None
    atr_pct = r / atr * 100.0 if atr else None
    em_pct = r / em * 100.0 if em else None
    bits = [f"range so far {_fmt(r, dp)}"]
    if atr_pct is not None and atr is not None:
        bits.append(f"{atr_pct:.0f}% of the {ATR_LEN}-day ATR ({_fmt(atr, dp)})")
    if em_pct is not None and em is not None:
        bits.append(f"{em_pct:.0f}% of the expected move (±{_fmt(em, dp)})")
    share_on = on_r / r if (on_r is not None and r > 0) else None
    share_ny = ny_r / r if (ny_r is not None and r > 0) else None
    if ny is None:
        quiet = atr_pct is not None and atr_pct < QUIET_NIGHT_ATR * 100.0
        where = "a quiet night" if quiet else "all of it overnight"
    elif share_ny is not None and share_ny >= 0.6:
        where = "mostly in New York"
    elif share_on is not None and share_on >= 0.6:
        where = "mostly overnight"
    else:
        where = "split between the night and the day"
    read = where
    if atr_pct is not None:
        left = max(0.0, 100.0 - atr_pct)
        ahead = "the open has" if ny is None else "there is"
        if left <= LITTLE_LEFT_PCT:
            read += f" — {ahead} {left:.0f}% of a normal day left, less room for a retest to travel"
        else:
            read += f" — {left:.0f}% of a normal day still ahead"
    return {
        "range": round(r, dp), "high": hi, "low": lo,
        "atr": round(atr, dp) if atr else None,
        "atr_pct": round(atr_pct) if atr_pct is not None else None,
        "em": round(em, dp) if em else None,
        "em_pct": round(em_pct) if em_pct is not None else None,
        "overnight": round(on_r, dp) if on_r is not None else None,
        "ny": round(ny_r, dp) if ny_r is not None else None,
        "line": " · ".join(bits), "read": read,
    }


def yesterday(sessions: Iterable[Any], atr: float | None, settle: float | None, dp: int = 0
              ) -> dict[str, Any] | None:
    """The prior cash session's shape, and the gap at the reopen that followed it."""
    rows = [s for s in sessions if isinstance(s, dict) and s.get("ok") and s.get("key") == "ny"]
    prior = next((s for s in rows if s.get("prior_day")), None) \
        or next((s for s in rows if s.get("status") == "complete"), None)
    if prior is None:
        return None
    vals = [prior.get(k) for k in ("open", "high", "low", "close")]
    nums = [float(v) for v in vals if isinstance(v, int | float) and not isinstance(v, bool)]
    if len(nums) != 4:
        return None
    o, h, lo, c = nums
    r = h - lo
    rng_atr = r / atr if atr else None
    pos = (c - lo) / r if r > 0 else None
    shape: str | None = None
    if rng_atr is not None and pos is not None:
        if rng_atr >= TREND_DAY_ATR and pos >= 1.0 - CLOSE_EDGE:
            shape = "trend day up"
        elif rng_atr >= TREND_DAY_ATR and pos <= CLOSE_EDGE:
            shape = "trend day down"
        elif rng_atr <= RANGE_DAY_ATR:
            shape = "range day"
        else:
            shape = "normal day"
    on = next((s for s in _today(sessions)
               if s.get("key") == "overnight" and isinstance(s.get("open"), int | float)), None)
    base = float(settle) if isinstance(settle, int | float) and not isinstance(settle, bool) else c
    gap = (float(on["open"]) - base) if on is not None else None
    gap_atr = gap / atr if (gap is not None and atr) else None
    parts = [shape or "yesterday"]
    parts.append(f"range {_fmt(r, dp)} ({rng_atr:.1f}× ATR)" if rng_atr is not None
                 else f"range {_fmt(r, dp)}")
    if pos is not None:
        parts.append(f"closed at {pos * 100:.0f}% of its range")
    if gap is not None:
        tail = f" ({abs(gap_atr):.1f} ATR)" if gap_atr is not None else ""
        parts.append(f"gap at 18:00 {gap:+,.{dp}f}{tail}")
    return {
        "shape": shape, "open": o, "high": h, "low": lo, "close": c, "range": round(r, dp),
        "range_atr": round(rng_atr, 2) if rng_atr is not None else None,
        "close_pos": round(pos, 2) if pos is not None else None,
        "gap": round(gap, dp) if gap is not None else None,
        "gap_atr": round(gap_atr, 2) if gap_atr is not None else None,
        "text": " · ".join(parts),
    }


def confluence(rows: list[dict[str, Any]], atr: float | None, last: float | None = None,
               dp: int = 0) -> list[dict[str, Any]]:
    """Group ladder rows (price order, highest first) that sit within a quarter
    of an ATR of each other. Members are marked `band`; the bands come back
    highest first, each with its labels. Last and the expected-move edges are
    not levels and never join a band."""
    if not atr or atr <= 0:
        return []
    width = CONFLUENCE_ATR * atr
    cand = [r for r in rows if r.get("kind") not in ("last", "em")
            and isinstance(r.get("price"), int | float)]
    groups: list[list[dict[str, Any]]] = []
    cur: list[dict[str, Any]] = []
    for r in cand:
        if cur and float(cur[0]["price"]) - float(r["price"]) <= width:
            cur.append(r)
        else:
            if len(cur) >= CONFLUENCE_MIN:
                groups.append(cur)
            cur = [r]
    if len(cur) >= CONFLUENCE_MIN:
        groups.append(cur)
    out: list[dict[str, Any]] = []
    for i, g in enumerate(groups):
        for r in g:
            r["band"] = i
        hi, lo = float(g[0]["price"]), float(g[-1]["price"])
        mid = (hi + lo) / 2.0
        out.append({
            "hi": hi, "lo": lo, "n": len(g), "labels": [str(r.get("label")) for r in g],
            "dist": round(mid - last, dp) if last is not None else None,
            "text": f"Confluence {_fmt(lo, dp)}–{_fmt(hi, dp)}: "
                    + ", ".join(str(r.get("label")).lower() for r in g)
                    + " — the level is the band, not any one row.",
        })
    return out


def regime(frame: dict[str, Any] | None, last: float | None, dp: int = 0
           ) -> dict[str, Any] | None:
    """The daily 200 EMA as the regime line: which side price is on, and what that side means."""
    line = (frame or {}).get("ema200") if isinstance(frame, dict) else None
    if not isinstance(line, int | float) or last is None or line <= 0:
        return None
    pct = (last / float(line) - 1.0) * 100.0
    above = pct > 0
    text = (f"200-day EMA {_fmt(float(line), dp)}, {abs(pct):.1f}% "
            f"{'below' if above else 'above'} last — "
            + ("above it, the daily regime is up; dips are bought until it breaks."
               if above else
               "below it, the daily regime is down; rallies are sold until it is reclaimed."))
    return {"ema200": round(float(line), 4), "pct": round(pct, 2), "above": above, "text": text}
