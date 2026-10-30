"""
Session ranges — where each desk traded, not just where the day traded.

WHY THIS IS THE BIGGEST GAP A PRE-OPEN NOTE HAD. A day high and low says the
range was 240 points and nothing about who set it. "London already took out the
Asia high and failed" and "Asia set the high at 20:00 and we have bled since"
are the same two numbers and opposite sessions. The owner trades Asia and
London as well as New York, so the question is not only "what happened
overnight" — it is "what happened in the session I am about to trade, and in
the one that just handed over to it".

FOUR BOXES, AND THEY ARE ALLOWED TO OVERLAP (owner, 2026-10-30). In ET:

  asia       20:00 → 00:00   the box every chart draws for Tokyo and Hong Kong
  london     02:00 → 05:00   07:00-10:00 London — the open window, where Europe
                             does its damage
  premkt     04:00 → 09:30   NYSE's own pre-market, overlapping London's last hour
  ny         09:30 → 16:00   US cash

  overnight  18:00 → 09:30   the ladder's, not a row: everything traded since
                             Globex reopened, so a print in a gap between the
                             boxes still counts toward the ON high

These are the session boxes a trader draws, not a partition of the clock —
nothing claims 18:00-20:00, 00:00-02:00 or the after-hours, and London and the
pre-market share an hour. For a fortnight before this the panel cut one
contiguous Globex day into six windows (Asia from 18:00, London open, Europe
midday, pre-NY, New York, post-close), which answered "where did every minute
go" at the cost of rows nobody draws on a chart. The calendar's "prints in the
X session" tag still needs a partition and keeps one (sessions.desk_window);
the boxes live beside it (sessions.BOXES, in_box).

LONDON IS 07:00-10:00 LONDON, AND IT STARTS BEFORE THE CASH BELL. The LSE opens
at 08:00 London, but European flow is already in by then: Eurex futures open at
08:00 CET and the London desks are at their screens an hour before the cash
open. Written on London's clock (review, 2026-10-14) because "02:00 ET all
year" is an hour out for the week between the UK's clock change and the US's,
and the three weeks the other way every March.

TRUE HIGHS AND LOWS, FROM v8 BARS (review, 2026-10-13). This used to read the
batched spark endpoint, which returns closes only — so every "high" was the
highest 15-minute CLOSE. Last night's NQ Asia window: true high 30,906.00 vs
close-high 30,897.75, true low 30,604.75 vs close-low 30,620.00. The panel's
amber "taken out" marks and the brief's "Asia high taken out" lines rest on
these figures, so they now come from the 5-minute OHLC bars the volume profile
already fetches — the SAME request and cache key (`chart5m_*`), read here on a
one-minute clock, so the profiles' five-minute job mostly finds them cached.
"""

from __future__ import annotations

import urllib.parse
from datetime import date, datetime, timedelta
from typing import Any
from zoneinfo import ZoneInfo

from .. import structure
from ..config import BROWSER_UA
from ..holidays import is_trading_day
from ..http import SourceStatus, fetch, json_body
from ..sessions import (
    BOXES,
    GLOBEX_REOPEN,
    NY_CLOSE,
    NY_OPEN,
    OVERNIGHT,
    globex_open,
    globex_trade_date,
    in_box,
)
from .profiles import CHART as V8_CHART

ET = ZoneInfo("America/New_York")

# Which books get segmented. Deliberately only the three actually traded: this
# costs one extra request and forty instruments' worth of it would buy nothing.
ASSETS: list[tuple[str, str]] = [
    ("NQ", "NQ=F"),
    ("ES", "ES=F"),
    ("GC", "GC=F"),
]


def segment(
    stamps: list[int], highs: list[float | None], lows: list[float | None],
    closes: list[float | None], last: float | None, now_et: datetime,
) -> list[dict[str, Any]]:
    """Bars → one row per session box, and one for the overnight. Pure, so it
    is the testable part.

    Only the MOST RECENT occurrence of each box is kept. A two-day pull spans
    two Asia sessions on a Tuesday, and merging them into one high and low
    would describe a range that never traded as a single session.

    A BAR MAY SIT IN TWO BOXES. London and the pre-market share 04:00-05:00
    ET, and the overnight contains the night's boxes; each box collects its
    own run of bars independently, so the London high is London's whether or
    not the pre-market also saw it.

    EACH ROW SAYS WHEN IT WAS AND WHETHER IT IS FINISHED, which it did not use
    to. "Most recent" means yesterday's for every box that has not come round
    again: at 01:00 ET the London, pre-market and New York rows are all the
    previous day's, and with only `%H:%M` on them nothing said so. A model
    handed a row labelled "London 03:00-07:45" at one in the morning reads it
    as today's and writes about a session that has not happened yet. `date`
    and `status` are what make a stale row admit to being stale, and
    `prior_day` is the same admission as one boolean, for the panel that draws
    every row on a shared axis and would otherwise invite reading yesterday's
    rows as a timeline.

    PRIOR DAY IS BY GLOBEX TRADE DATE. The boxes are not a partition, so "the
    rows listed after the newest one are yesterday's" no longer holds. A row is
    the previous day's when the trade date its window opened in is behind the
    trade date the clock is in — Thursday's New York row once Thursday 18:00
    has turned the day to Friday. While Globex is shut (the weekend, the
    maintenance hour) the reference is the newest row's own day, so Friday's
    rows read as Friday's all weekend rather than as stale.
    """
    open_now = globex_open(now_et)
    when = [datetime.fromtimestamp(t, ET) for t in stamps]
    out: list[dict[str, Any]] = []
    for key, label in [*BOXES, OVERNIGHT]:
        # Walk backwards and stop at the first gap, so what is collected is the
        # latest contiguous run inside this box rather than every bar that
        # ever fell in it.
        picked: list[tuple[int, float, float, float]] = []
        seen_any = False
        for i in range(len(stamps) - 1, -1, -1):
            if in_box(key, when[i]):
                hi, lo, cl = highs[i], lows[i], closes[i]
                # A bar with a close but no high/low (a hole in a thin futures
                # minute) falls back to its close rather than being dropped.
                v = cl if cl is not None else None
                if v is not None:
                    picked.append((stamps[i], hi if hi is not None else v,
                                   lo if lo is not None else v, v))
                seen_any = True
            elif seen_any:
                break

        if not picked:
            out.append({
                "key": key, "label": label, "ok": False,
                "high": None, "low": None, "open": None, "close": None,
                "range": None, "pos": None, "bars": 0, "start_et": None, "end_et": None,
            })
            continue

        picked.reverse()
        hi = max(p[1] for p in picked)
        lo = min(p[2] for p in picked)
        op, cl = picked[0][3], picked[-1][3]
        rng = hi - lo
        # CENTS, NOT FOUR PLACES: Yahoo's gold bars are float32 underneath, so
        # 4163.7 arrives as 4163.7002 and survived a round to 4. The brief then
        # printed "opened at 4163.7002", and its numeral check flagged a correct
        # "4163.8" because the digest only held 4163.7998 (2026-10-14).
        out.append({
            "key": key,
            "label": label,
            "ok": True,
            "high": round(hi, 2),
            "low": round(lo, 2),
            "open": round(op, 2),
            "close": round(cl, 2),
            "range": round(rng, 2),
            "chg_pct": ((cl - op) / op * 100.0) if op else None,
            # Where the CURRENT price sits inside that session's range — the
            # figure that answers "have we taken out the Asia high".
            "pos": ((last - lo) / rng) if (last is not None and rng > 0) else None,
            "bars": len(picked),
            "start_et": datetime.fromtimestamp(picked[0][0], ET).strftime("%H:%M"),
            "end_et": datetime.fromtimestamp(picked[-1][0], ET).strftime("%H:%M"),
            # The calendar day the window STARTED on — not the day it ended,
            # because Asia begins the evening before the session it feeds.
            "date": datetime.fromtimestamp(picked[0][0], ET).strftime("%a %d"),
            # "live" while the clock is inside this box AND the market trades,
            # so a range still being built is never read as a finished one —
            # and Friday's New York row does not read "live" all weekend.
            "status": "live" if open_now and in_box(key, now_et) else "complete",
            "start_ts": picked[0][0],
        })

    def day_of(r: dict[str, Any]) -> date:
        return globex_trade_date(datetime.fromtimestamp(r["start_ts"], ET))

    dated = [r for r in out if r["ok"]]
    if dated:
        ref = globex_trade_date(now_et) if open_now else max(day_of(r) for r in dated)
        for r in dated:
            r["prior_day"] = day_of(r) < ref
    return out


# --------------------------------------------------------------------------
# VWAP and the opening range — the levels the strategy enters on, from the
# same bars (owner, 2026-10-30: the Structure tab's live levels ladder).
# --------------------------------------------------------------------------

#: The opening range is the cash session's first half hour.
OPENING_RANGE_MIN = 30


def vwap_since(
    stamps: list[int], highs: list[float | None], lows: list[float | None],
    closes: list[float | None], volumes: list[float | None],
    start_ts: float, end_ts: float | None = None,
) -> float | None:
    """The volume-weighted average of the typical price over the bars from
    `start_ts` (to `end_ts`, exclusive, when given). Pure.

    A bar without volume weighs nothing; if no bar in the window carries any,
    the plain mean of the typical prices stands in and is still a fair
    "where has it traded" — Yahoo's futures bars carry volume, its ETF bars
    sometimes do not."""
    num = den = 0.0
    plain: list[float] = []
    for t, h, lo, c, v in zip(stamps, highs, lows, closes, volumes, strict=False):
        if c is None or t < start_ts or (end_ts is not None and t >= end_ts):
            continue
        tp = ((h if h is not None else c) + (lo if lo is not None else c) + c) / 3.0
        plain.append(tp)
        if v:
            num += tp * v
            den += v
    if den > 0:
        return round(num / den, 2)
    return round(sum(plain) / len(plain), 2) if plain else None


def opening_range(
    stamps: list[int], highs: list[float | None], lows: list[float | None],
    closes: list[float | None], open_ts: float, now_ts: float,
) -> dict[str, Any] | None:
    """The high and low of the cash session's first thirty minutes, and whether
    the half hour is over. None before its first bar. Pure."""
    end_ts = open_ts + OPENING_RANGE_MIN * 60
    hi = lo = None
    for t, h, l_, c in zip(stamps, highs, lows, closes, strict=False):
        if c is None or not open_ts <= t < end_ts:
            continue
        bh, bl = (h if h is not None else c), (l_ if l_ is not None else c)
        hi = bh if hi is None else max(hi, bh)
        lo = bl if lo is None else min(lo, bl)
    if hi is None or lo is None:
        return None
    return {"high": round(hi, 2), "low": round(lo, 2), "complete": now_ts >= end_ts}


def anchors(now_et: datetime) -> tuple[datetime, datetime | None]:
    """Where today's VWAPs start: the most recent Globex reopen (18:00 ET on a
    trading evening — Thursday's, all weekend), and the cash open if New York
    is trading today and has opened. Pure."""
    g = datetime.combine(now_et.date(), GLOBEX_REOPEN, tzinfo=ET)
    if now_et < g:
        g -= timedelta(days=1)
    while not globex_open(g + timedelta(minutes=1)):
        g -= timedelta(days=1)
    rth = datetime.combine(now_et.date(), NY_OPEN, tzinfo=ET)
    return g, rth if (is_trading_day(now_et.date()) and now_et >= rth) else None


def collect() -> tuple[dict[str, Any], SourceStatus]:
    """Session ranges for the three books, from 5-minute OHLC bars."""
    st = SourceStatus("Session ranges")
    now_et = datetime.now(ET)
    assets: dict[str, Any] = {}
    for key, sym in ASSETS:
        url = V8_CHART.format(sym=urllib.parse.quote(sym, safe=""))
        r = st.absorb(fetch(url, key=f"chart5m_{key}", ttl_sec=60.0, ua=BROWSER_UA, timeout=25,
                            stale_max_sec=600.0, validate=json_body))
        if not r.ok:
            st.error = st.error or f"{key}: {r.error}"
            continue
        try:
            resp = ((r.json().get("chart") or {}).get("result") or [None])[0]
        except (ValueError, TypeError, AttributeError, IndexError) as e:
            st.error = st.error or f"{key}: parse {e}"
            continue
        if not isinstance(resp, dict):
            continue
        meta = resp.get("meta") or {}
        last = meta.get("regularMarketPrice")
        stamps = resp.get("timestamp") or []
        try:
            q = ((resp.get("indicators") or {}).get("quote") or [{}])[0]
        except (IndexError, TypeError, AttributeError):
            continue
        closes = q.get("close") or []
        if not stamps or not closes:
            continue
        n = min(len(stamps), len(closes))
        st_, hi_, lo_, cl_ = (
            list(stamps[:n]),
            list((q.get("high") or [None] * n)[:n]),
            list((q.get("low") or [None] * n)[:n]),
            list(closes[:n]),
        )
        vol = list((q.get("volume") or [None] * n)[:n])
        g, rth = anchors(now_et)
        rth_close = (datetime.combine(rth.date(), NY_CLOSE, tzinfo=ET).timestamp()
                     if rth is not None else None)
        assets[key] = {
            "last": last,
            "sessions": segment(st_, hi_, lo_, cl_, last, now_et),
            # The levels the strategy enters on, from the same bars (2026-10-30).
            "vwap": {
                "globex": vwap_since(st_, hi_, lo_, cl_, vol, g.timestamp()),
                "rth": (vwap_since(st_, hi_, lo_, cl_, vol, rth.timestamp(), rth_close)
                        if rth is not None else None),
            },
            "opening_range": (opening_range(st_, hi_, lo_, cl_, rth.timestamp(), now_et.timestamp())
                              if rth is not None else None),
            # The strategy's side filter on its own timeframe (2026-10-30), from
            # the same five days of bars, bucketed to ten minutes.
            "ema200_10m": structure.ema200_10m(st_, cl_),
        }

    st.items = len(assets)
    st.settle(len(assets) > 0, "asset")
    return {"assets": assets}, st
