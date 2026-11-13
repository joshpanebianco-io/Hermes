"""
The Futures section's chart: one book's bars with the levels it trades against.

WHY ITS OWN ROUTE (owner, 2026-11-10: "a seperate futures section that has all
info related to futures that we trade - nq, es, gc, sil, cl1"). The Scanner's
chart reads the stocks store, whose levels are a stock's: the previous regular
session and the pre-market. A future trades nearly round the clock from the
18:00 ET reopen, and its levels are the overnight's, the cash session's and the
dealers' (report.live_ladders, the rows the Levels panel lists). So this reads
the contract's own bars from Yahoo and hands the chart the shape the Scanner's
chart already draws, with the overnight standing where the pre-market stands:

    pdh / pdl   the prior regular session's high and low (09:30-16:00 ET)
    pmh / pml   the overnight's high and low, the 18:00 reopen to 09:30;
                "forming" until 09:30, as a stock's pre-market range is
    lines       the gamma flip and walls, the prior settle, the opening range
    em          the expected move's band

VWAP IS ANCHORED, AND CARRIES ITS BANDS (owner, 2026-11-10: "for futures have
vwap anchored at 18:00 with the 1st and 2nd deviation bands with options to
toggle how many bands we show and what we anchor it to"). Four anchors, each a
VWAP and its volume-weighted standard deviation, so the chart switches between
them without asking again:

    globex   each 18:00 reopen, the futures day: the ladder's "VWAP since 18:00"
    london   each London open, 07:00 London (02:00 ET most of the year)
    rth      each 09:30 cash open: the ladder's "VWAP since 09:30", built to the
             16:00 close and then held, as the ladder holds it, until the next
             open; none on a day the NYSE is shut
    week     each week's Sunday reopen

They are summed over the download's own one- or five-minute bars, not the
view's, so a VWAP reads the same on every timeframe, matches the ladder's row,
and starts at its anchor even inside an hour bar. Bars before the day's London
or New York open still belong to the day before's. The first period of a
download is cut off at its start, so it is left blank rather than drawn wrong.
`starts` says where each period begins, for the chart to break the line there.

THE CHART MARKS EACH 18:00 REOPEN (`opens`), where the futures day starts,
instead of shading a stock's extended hours: on a future the overnight is
part of the day.

A LONG BAR IS READ BY ITS LAST MINUTE, as the Scanner's 60-minute view is: the
09:00 hour holds the cash open and is the session's, not the overnight's.

Pure but for the fetch, which is the collector's: `parse` and `series` are the
testable parts.
"""

from __future__ import annotations

import math
from datetime import datetime, time
from typing import Any

from .holidays import is_trading_day
from .scan import ET, Bar, ema, resample
from .sessions import LONDON_DESKS, NY_CLOSE, NY_OPEN, globex_trade_date, london_at

#: The five books and the contracts Yahoo quotes them under.
SYMBOL: dict[str, str] = {
    "NQ": "NQ=F", "ES": "ES=F", "GC": "GC=F", "SIL": "SI=F", "CL": "CL=F",
}
#: Each view's download: (Yahoo interval, range). Short views from one-minute
#: bars, the hour views from a month of five-minute bars.
SOURCE: dict[str, tuple[str, str]] = {
    "1m": ("1m", "5d"), "3m": ("1m", "5d"), "5m": ("5m", "10d"), "10m": ("5m", "10d"),
    "30m": ("5m", "1mo"), "60m": ("5m", "1mo"), "D": ("1d", "1y"),
}
STEP: dict[str, int] = {
    "1m": 60, "3m": 180, "5m": 300, "10m": 600, "30m": 1800, "60m": 3600, "D": 86400,
}
CHART = ("https://query1.finance.yahoo.com/v8/finance/chart/{sym}"
         "?range={rng}&interval={iv}&includePrePost=true")
#: The most bars a view ships: enough to reach back past the last 18:00 reopen on
#: every view. The averages and VWAP are computed on everything before the cut.
MAX_BARS: dict[str, int] = {
    "1m": 1500, "3m": 600, "5m": 600, "10m": 400, "30m": 400, "60m": 400, "D": 400,
}
#: Where a VWAP can be anchored; see the module's note.
ANCHORS = ("globex", "london", "rth", "week")
#: Ladder rows drawn as lines, by kind; the rest are the chart's own series or bands.
LINE_KINDS = {"flip": "flip", "call": "call", "put": "put"}

RTH_OPEN, RTH_CLOSE, HALT, REOPEN = time(9, 30), time(16, 0), time(17, 0), time(18, 0)


def parse(doc: Any) -> list[Bar]:
    """Yahoo's chart reply → bars, holes dropped. Pure."""
    try:
        res = (doc.get("chart") or {}).get("result") or []
        r = res[0]
        stamps = r.get("timestamp") or []
        q = ((r.get("indicators") or {}).get("quote") or [{}])[0]
    except (AttributeError, IndexError, TypeError):
        return []
    out: list[Bar] = []
    cols = [q.get(k) or [] for k in ("open", "high", "low", "close", "volume")]
    for i, t in enumerate(stamps):
        vals = [c[i] if i < len(c) else None for c in cols]
        o, h, lo, c, v = vals
        if not all(isinstance(x, int | float) and math.isfinite(x) for x in (o, h, lo, c)):
            continue
        out.append(Bar(int(t), float(o), float(h), float(lo), float(c),
                       float(v) if isinstance(v, int | float) and math.isfinite(v) else 0.0))
    return out


def session_of(t: int, step: int) -> str | None:
    """pre (the overnight) / rth / post for a bar, read by its last minute. Pure."""
    end = datetime.fromtimestamp(t + max(step, 60) - 60, ET).time()
    if RTH_OPEN <= end < RTH_CLOSE:
        return "rth"
    if RTH_CLOSE <= end < HALT:
        return "post"
    if HALT <= end < REOPEN:
        return None
    return "pre"


def _row(ladder: dict[str, Any] | None, label: str) -> float | None:
    for r in (ladder or {}).get("rows") or []:
        if r.get("label") == label and isinstance(r.get("price"), int | float):
            return float(r["price"])
    return None


def _period(anchor: str, t: int) -> object | None:
    """The VWAP period a bar opening at `t` belongs to: its futures day, its week,
    or its day once the London or New York open is reached. None before that
    open: the bar still belongs to the period before. Pure."""
    dt = datetime.fromtimestamp(t, ET)
    g = globex_trade_date(dt)
    if anchor == "globex":
        return g
    if anchor == "week":
        return g.isocalendar()[:2]
    if anchor == "rth" and not is_trading_day(g):
        return None
    at = (datetime.combine(g, NY_OPEN, tzinfo=ET) if anchor == "rth"
          else london_at(g, LONDON_DESKS).astimezone(ET))
    return g if dt >= at else None


def _counts(anchor: str, period: object, t: int) -> bool:
    """Whether a bar adds to its period's VWAP: every bar does, but the cash
    session's VWAP takes only 09:30 to 16:00 of its own day. Pure."""
    if anchor != "rth":
        return True
    dt = datetime.fromtimestamp(t, ET)
    return dt.date() == period and NY_OPEN <= dt.time() < NY_CLOSE


def anchored(src: list[Bar], shown: list[Bar], step: int, anchor: str) -> dict[str, Any]:
    """VWAP from `anchor` and its volume-weighted standard deviation, summed over
    the source bars and read at the close of each shown bar; and the shown bars
    where a period starts. Blank through the download's first period. Pure.

    The deviation is taken about a reference price (the period's first typical
    price), so the sums stay small and the variance does not come out of the
    difference of two numbers near a price squared."""
    vwap: list[float | None] = []
    sd: list[float | None] = []
    periods: list[object | None] = []
    cur: object | None = None
    seen = False   # whether the current period's start is in the download
    ref = sv = svd = svd2 = 0.0
    j = 0
    for b in shown:
        end = b.t + step
        while j < len(src) and src[j].t < end:
            s = src[j]
            k = _period(anchor, s.t)
            if j == 0:
                cur = k
            elif k is not None and k != cur:
                cur, seen, ref, sv, svd, svd2 = k, True, 0.0, 0.0, 0.0, 0.0
            j += 1
            if not seen or s.volume <= 0 or not _counts(anchor, cur, s.t):
                continue
            tp = (s.high + s.low + s.close) / 3.0
            if sv == 0:
                ref = tp
            d = tp - ref
            sv += s.volume
            svd += s.volume * d
            svd2 += s.volume * d * d
        periods.append(cur if seen else None)
        if seen and sv > 0:
            m = svd / sv
            vwap.append(round(ref + m, 4))
            sd.append(round(math.sqrt(max(0.0, svd2 / sv - m * m)), 4))
        else:
            vwap.append(None)
            sd.append(None)
    starts = [i for i in range(1, len(shown))
              if periods[i] is not None and periods[i] != periods[i - 1]]
    return {"vwap": vwap, "sd": sd, "starts": starts}


def series(bars: list[Bar], tf: str, now: datetime, ladder: dict[str, Any] | None,
           book: str = "") -> dict[str, Any]:
    """One view of a book: the bars, the averages, VWAP from each reopen, the
    session spans and the levels. Pure."""
    step = STEP.get(tf)
    if step is None:
        return {"ok": False, "sym": book, "tf": tf, "error": f"no {tf} view"}
    now_ts = int(now.timestamp())
    src = [b for b in bars if b.t <= now_ts]
    held = src if tf == "D" else resample(src, step)
    if not held:
        return {"ok": False, "sym": book, "tf": tf, "error": "no bars"}
    closes = [b.close for b in held]
    e8, e9, e10 = ema(closes, 8), ema(closes, 9), ema(closes, 10)
    e200 = ema(closes, 200) if len(closes) >= 200 else []
    # The 20 and the 50, for the reader who picks them on the chart (2026-11-11).
    e20 = ema(closes, 20) if len(closes) >= 20 else []
    e50 = ema(closes, 50) if len(closes) >= 50 else []
    start = max(0, len(held) - MAX_BARS.get(tf, 400))
    n = len(held) - start

    # Each anchor over the whole download, then cut to the bars shipped.
    vwaps: dict[str, Any] | None = None
    opens: list[int] = []
    if tf != "D":
        vwaps = {}
        for a in ANCHORS:
            got = anchored(src, held, step, a)
            vwaps[a] = {"vwap": got["vwap"][start:], "sd": got["sd"][start:],
                        "starts": [i - start for i in got["starts"] if i > start]}
        opens = [held[start + i].t for i in vwaps["globex"]["starts"]]

    sessions: list[dict[str, Any]] = []
    for b in held[start:]:
        if tf == "D":
            continue
        kind = session_of(b.t, step)
        if kind is None:
            continue
        if sessions and sessions[-1]["kind"] == kind and sessions[-1]["to"] >= b.t - 2 * step:
            sessions[-1]["to"] = b.t + step
        else:
            sessions.append({"kind": kind, "from": b.t, "to": b.t + step})

    et_now = now.astimezone(ET).time()
    levels = {
        "pdh": _row(ladder, "Prior RTH high"),
        "pdl": _row(ladder, "Prior RTH low"),
        "pmh": _row(ladder, "ON high"),
        "pml": _row(ladder, "ON low"),
        # The overnight is final once the cash session opens.
        "pm_done": RTH_OPEN <= et_now < REOPEN,
    }
    lines: list[dict[str, Any]] = []
    for r in (ladder or {}).get("rows") or []:
        label = str(r.get("label") or "")
        # The gamma levels only. The prior settle and the opening range were drawn too, as
        # grey references, until the owner had them off the chart (2026-11-14: "can we
        # remove those levels"); the ladder keeps both, for Hermes and the brief.
        tone = LINE_KINDS.get(str(r.get("kind")))
        if tone and isinstance(r.get("price"), int | float):
            lines.append({"v": float(r["price"]), "label": label, "tone": tone})
    hi, lo = _row(ladder, "Expected move high"), _row(ladder, "Expected move low")
    em = ({"lo": lo, "hi": hi, "label": f"EM ±{(hi - lo) / 2:,.{ladder.get('dp', 2)}f}"}
          if ladder and hi is not None and lo is not None else None)

    def cut(xs: list[float]) -> list[float | None]:
        # An average with too few bars behind it ships as blanks.
        return [round(x, 4) for x in xs[start:]] if xs else [None] * (len(held) - start)

    return {
        "ok": True,
        "sym": book,
        "tf": tf,
        "bars": [{"t": b.t, "o": round(b.open, 4), "h": round(b.high, 4), "l": round(b.low, 4),
                  "c": round(b.close, 4), "v": b.volume} for b in held[start:]],
        "ema8": cut(e8), "ema9": cut(e9), "ema10": cut(e10),
        "ema20": cut(e20), "ema50": cut(e50),
        "ema200": cut(e200),
        "vwap": vwaps["globex"]["vwap"] if vwaps else [None] * n,
        "vwaps": vwaps,
        "opens": opens,
        "levels": levels,
        "history": [],
        "sessions": sessions,
        "signals": [],
        "lines": lines,
        "em": em,
    }
