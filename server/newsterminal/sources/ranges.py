"""
Session ranges — where each desk traded, not just where the day traded.

WHY THIS IS THE BIGGEST GAP A PRE-OPEN NOTE HAD. A day high and low says the
range was 240 points and nothing about who set it. "London already took out the
Asia high and failed" and "Asia set the high at 20:00 and we have bled since"
are the same two numbers and opposite sessions. The owner trades Asia and
London as well as New York, so the question is not only "what happened
overnight" — it is "what happened in the session I am about to trade, and in
the one that just handed over to it".

FIVE WINDOWS, IN ET, AND THEY DO NOT OVERLAP.

  asia      18:00 → 02:00   Globex reopens; Tokyo and Hong Kong lead
  london    02:00 → 05:00   the London OPEN window, where Europe does its damage
  euro_mid  05:00 → 08:00   European midday; US premarket starts building
  preny     08:00 → 09:30   the overlap and the 08:30 data window
  ny        09:30 → 16:00   US cash

The boundaries are the handovers a trader actually uses, not the exchanges'
own hours — London cash runs to 11:30 ET but by 09:30 the flow is American, and
a "London range" that included the US open would describe neither.

LONDON IS THE OPEN WINDOW, 02:00-05:00, AND IT STARTS BEFORE THE CASH BELL.
The LSE opens at 08:00 London, which is 03:00 ET all year (the two
hemispheres shift together for this pair).
But European flow is already in by then: Eurex futures open at 08:00 CET —
02:00 ET — and the London desks are at their screens an hour before the cash
open. The hour from 02:00 is European-driven, and counting it as Asia described
it as thin Globex drift when it is nothing of the kind. `resolve_session` in
report.py has always used 02:00 for the same reason; the windows here now agree
with it instead of contradicting it by an hour.

IT ENDS AT 05:00 BECAUSE THAT IS WHERE THE DAMAGE IS DONE. "London took out the
Asia high" is a claim about the OPEN move; run the window to 08:00 and it
absorbs three hours of midday drift and stops meaning that. So the leftovers get
their own window rather than diluting this one — euro_mid exists to be somewhere
else for them to go. Note the report still writes a LONDON SESSION note across
roughly 02:00-07:30 (resolve_session); this row is labelled "London open" so two
different spans are never both called London.

EVERYTHING IN ET, converted from the bar's own epoch. The instruments settle on
CME's clock, which is New York's; deriving from local time would put every
boundary an hour out for the weeks the two hemispheres' DST disagree.

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
from datetime import datetime
from typing import Any
from zoneinfo import ZoneInfo

from ..config import BROWSER_UA
from ..http import SourceStatus, fetch, json_body
from .profiles import CHART as V8_CHART

ET = ZoneInfo("America/New_York")

# key, label, start hour (ET), end hour (ET). A window whose start is greater
# than its end wraps midnight.
WINDOWS: list[tuple[str, str, float, float]] = [
    ("asia", "Asia", 18.0, 2.0),
    ("london", "London open", 2.0, 5.0),
    ("euro_mid", "Europe midday", 5.0, 8.0),
    ("preny", "Pre-NY", 8.0, 9.5),
    ("ny", "New York", 9.5, 16.0),
]

# Which books get segmented. Deliberately only the three actually traded: this
# costs one extra request and forty instruments' worth of it would buy nothing.
ASSETS: list[tuple[str, str]] = [
    ("NQ", "NQ=F"),
    ("ES", "ES=F"),
    ("GC", "GC=F"),
]


def _in_window(hour: float, start: float, end: float) -> bool:
    """Does an ET hour-of-day fall in a window that may wrap midnight?"""
    return start <= hour < end if start < end else (hour >= start or hour < end)


def segment(
    stamps: list[int], highs: list[float | None], lows: list[float | None],
    closes: list[float | None], last: float | None, now_et: datetime,
) -> list[dict[str, Any]]:
    """Bars → one row per session window. Pure, so it is the testable part.

    Only the MOST RECENT occurrence of each window is kept. A two-day pull
    spans two Asia sessions on a Tuesday, and merging them into one high and low
    would describe a range that never traded as a single session.

    EACH ROW SAYS WHEN IT WAS AND WHETHER IT IS FINISHED, which it did not used
    to. "Most recent" means yesterday's for every window that has not come round
    again: at 01:00 ET the London, Pre-NY and New York rows are all the previous
    day's, and with only `%H:%M` on them nothing said so. A model handed a row
    labelled "London 03:00-07:45" at one in the morning reads it as today's and
    writes about a session that has not happened yet. `date` and `status` are
    what make a stale row admit to being stale, and `prior_day` is the same
    admission as one boolean, for the panel that draws every row on a shared
    axis and would otherwise invite reading yesterday's rows as a timeline.
    """
    now_h = now_et.hour + now_et.minute / 60.0
    out: list[dict[str, Any]] = []
    for key, label, start, end in WINDOWS:
        # Walk backwards and stop at the first gap, so what is collected is the
        # latest contiguous run inside this window rather than every bar that
        # ever fell in it.
        picked: list[tuple[int, float, float, float]] = []
        seen_any = False
        for i in range(len(stamps) - 1, -1, -1):
            et_h = datetime.fromtimestamp(stamps[i], ET)
            h = et_h.hour + et_h.minute / 60.0
            inside = _in_window(h, start, end)
            if inside:
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
        out.append({
            "key": key,
            "label": label,
            "ok": True,
            "high": round(hi, 4),
            "low": round(lo, 4),
            "open": round(op, 4),
            "close": round(cl, 4),
            "range": round(rng, 4),
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
            # "live" while the clock is still inside this window, so a range
            # that is still being built is never read as a finished one.
            "status": "live" if _in_window(now_h, start, end) else "complete",
            "start_ts": picked[0][0],
        })

    # WHICH ROWS ARE THE PREVIOUS DAY'S. The windows are listed in the order a
    # Globex day runs them, so anything listed AFTER the newest row has not come
    # round again yet and is yesterday's. The second clause is the quarter-hour
    # after a handover: the clock is inside the window but its first bar has
    # not printed, so the row wearing "live" is still last night's.
    dated = [i for i, r in enumerate(out) if r["ok"]]
    if dated:
        newest = max(dated, key=lambda i: out[i]["start_ts"])
        for i in dated:
            out[i]["prior_day"] = i > newest or (out[i]["status"] == "live" and i != newest)
    return out


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
        assets[key] = {
            "last": last,
            "sessions": segment(
                list(stamps[:n]),
                list((q.get("high") or [None] * n)[:n]),
                list((q.get("low") or [None] * n)[:n]),
                list(closes[:n]),
                last,
                now_et,
            ),
        }

    st.items = len(assets)
    st.settle(len(assets) > 0, "asset")
    return {"assets": assets}, st
