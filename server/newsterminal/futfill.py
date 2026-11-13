"""
The last ten minutes of a futures chart, from the ETF that tracks it.

WHY (owner, 2026-11-14: "can you get live futures free?", then "do option 1"). CME
licenses its real-time data, so every free source runs about ten minutes behind:
Yahoo's NQ=F, ES=F, GC=F, SI=F and CL=F bars stop ten minutes back, and the price
stream carries stocks and ETFs, not futures. The ETFs that track them (QQQ, SPY,
GLD, SLV, USO) trade in real time from 04:00 to 20:00 ET. Over a few minutes the
ratio of a future to its ETF hardly moves (the basis, a dividend, a roll are days
long), so the ratio measured where both have bars carries the ETF's minutes into
the future's prices:

  - the BARS: the ETF's one-minute bars after the future's last minute, each price
    times the ratio, volume nought (so VWAP, which needs real volume, is untouched);
  - the TICK: the ETF's live trade times the ratio, each second, on the last candle.

WHEN IT FILLS: only between 04:00 and 17:00 ET on a trading day, and never more than
MAX_GAP_SEC past the future's last bar. Before 04:00 the ETFs do not trade; from
17:00 the futures halt for the hour while the ETFs' late session runs on, and a fill
there would draw prices the future never traded. Outside that window the chart is
the future's own bars, ten minutes behind, as it was.

Pure: the collector fetches and holds the bars (collector.futures_bars, futures_tick).
"""

from __future__ import annotations

from datetime import datetime
from typing import Any

from .holidays import is_trading_day
from .scan import ET, Bar

#: The ETF each book is carried by.
PROXY: dict[str, str] = {"NQ": "QQQ", "ES": "SPY", "GC": "GLD", "SIL": "SLV", "CL": "USO"}
#: Minutes the ratio is the median of: enough that one odd print does not set it.
RATIO_MIN = 10
#: The most a fill reaches past the future's last bar: the feed's delay is ten minutes,
#: and a gap much longer than that is a feed that has stopped, not a delay.
MAX_GAP_SEC = 30 * 60
#: ET minutes of the day a fill may cover: from the ETFs' first trades to the futures' halt.
FILL_FROM, FILL_TO = 4 * 60, 17 * 60


def ratio(fut: list[Bar], etf: list[Bar], n: int = RATIO_MIN) -> tuple[float, int] | None:
    """(future ÷ ETF, the last minute both have a bar for): the median of the last `n`
    shared minutes' closes. None when they share none. Pure."""
    by = {b.t: b.close for b in etf if b.close > 0}
    pairs = [(b.t, b.close / by[b.t]) for b in fut if b.close > 0 and b.t in by]
    if not pairs:
        return None
    last = pairs[-n:]
    rs = sorted(r for _, r in last)
    return rs[len(rs) // 2], last[-1][0]


def fillable(t: int) -> bool:
    """Whether a minute starting at epoch `t` is one a fill may draw. Pure."""
    et = datetime.fromtimestamp(t, ET)
    m = et.hour * 60 + et.minute
    return is_trading_day(et.date()) and FILL_FROM <= m < FILL_TO


def fill(fut_last: int, etf: list[Bar], r: float, now_ts: int) -> list[Bar]:
    """The ETF's one-minute bars after the future's last minute `fut_last`, in the
    future's prices, volume nought: what the chart draws for the minutes CME's feed
    has not sent yet. Pure."""
    return [Bar(b.t, b.open * r, b.high * r, b.low * r, b.close * r, 0.0)
            for b in etf
            if fut_last < b.t <= now_ts and b.t - fut_last <= MAX_GAP_SEC and fillable(b.t)]


def bar_quote(b: Bar, now_ts: float) -> dict[str, Any]:
    """The ETF's newest one-minute bar as a quote, for when the stream sends nothing for it
    (live 2026-11-14: GLD, SLV and USO had no stream trades, so the gold, silver and crude
    charts had no last candle). At most a minute and the bars' fifteen-second cache old. Pure."""
    et = datetime.fromtimestamp(b.t, ET)
    m = et.hour * 60 + et.minute
    session = "pre" if m < 9 * 60 + 30 else "rth" if m < 16 * 60 else "post"
    return {"price": b.close, "at": float(min(now_ts, b.t + 59)), "session": session,
            "minute": {"t": b.t, "o": b.open, "h": b.high, "l": b.low, "c": b.close},
            "via": "bars"}


def scaled_tick(q: dict[str, Any] | None, r: float, book: str, proxy: str) -> dict[str, Any] | None:
    """The ETF's last trade and this minute's candle in the future's prices, or None when
    the ETF has no trade, or its trade is outside the fill's hours. Pure."""
    if not q or not isinstance(q.get("price"), int | float) or not q.get("at"):
        return None
    if not fillable(int(float(q["at"]))):
        return None
    m = q.get("minute")
    minute = None
    if isinstance(m, dict) and all(isinstance(m.get(k), int | float) for k in ("o", "h", "l", "c")):
        minute = {"t": m.get("t"), **{k: round(float(m[k]) * r, 4) for k in ("o", "h", "l", "c")}}
    return {**q, "sym": book, "price": round(float(q["price"]) * r, 4), "minute": minute,
            "via": "etf", "proxy": proxy, "ratio": round(r, 6),
            # "bars" when the ETF's newest minute bar stood in for a stream trade: up to a
            # minute old, whatever `at` says, and the chart's chip says so.
            "source": "bars" if q.get("via") == "bars" else "trade"}
