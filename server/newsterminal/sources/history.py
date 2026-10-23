"""
A year of daily bars for the three books — the daily frame the Terminal lacked.

WHY A SOURCE OF ITS OWN. The context feed (sources/quotes.py) keeps a month
of closes for the week-and-month figures, and the brief is the only reader.
The frame wants a year of highs, lows and closes — the 200-day average and
the 52-week extremes — and the batched spark endpoint returns closes only,
so this is the v8 chart endpoint, one request per book, once an hour: three
requests an hour for levels that move once a day.

THE FRAME IS COMPUTED HERE AND READ ELSEWHERE. Levels only (frame.frame_of),
from sessions that have finished on the Globex calendar; whoever holds the
live print reads them (frame.read) — the driver board and the Session ranges
panel. Personal use only, like every other Yahoo read in this terminal.
"""

from __future__ import annotations

import urllib.parse
from datetime import UTC, date, datetime
from typing import Any

from .. import scan
from ..config import BROWSER_UA
from ..frame import frame_of
from ..http import SourceStatus, fetch, json_body
from ..sessions import globex_trade_date

CHART = "https://query1.finance.yahoo.com/v8/finance/chart/{sym}?range=1y&interval=1d"

BOOKS: list[tuple[str, str]] = [("NQ", "NQ=F"), ("ES", "ES=F"), ("GC", "GC=F")]

#: How long a copy is served before going upstream, and how old a stale copy
#: may be served when upstream fails. Daily levels: an hour, and three days.
TTL_SEC = 3600.0
STALE_MAX_SEC = 3 * 86400.0


def collect(now: datetime | None = None) -> tuple[dict[str, Any], SourceStatus]:
    """Each book's daily frame. `now` is for the tests; the clock otherwise."""
    st = SourceStatus("Daily history")
    now = now or datetime.now(UTC)
    today: date = globex_trade_date(now)
    frames: dict[str, Any] = {}
    errors: list[str] = []
    for key, sym in BOOKS:
        url = CHART.format(sym=urllib.parse.quote(sym, safe=""))
        r = st.absorb(fetch(url, key=f"hist1d_{key}", ttl_sec=TTL_SEC, ua=BROWSER_UA,
                            timeout=25, stale_max_sec=STALE_MAX_SEC, validate=json_body))
        if not r.ok or r.body is None:
            errors.append(f"{key}: {r.error or 'empty'}")
            frames[key] = {"ok": False, "error": r.error or "empty response"}
            continue
        try:
            days = scan.parse_daily(r.json())
        except ValueError as e:
            errors.append(f"{key}: parse {e}")
            frames[key] = {"ok": False, "error": f"parse: {e}"}
            continue
        if not days:
            frames[key] = {"ok": False, "error": "no daily bars"}
            continue
        frames[key] = {"ok": True, **frame_of(days, today)}
    ok = sum(1 for f in frames.values() if f.get("ok"))
    st.items = ok
    if errors:
        st.notes.extend(errors[:3])
    if ok == 0 and errors:
        st.error = "; ".join(errors[:2])
    st.settle(ok > 0, "book")
    return {"books": frames, "today": today.isoformat()}, st
