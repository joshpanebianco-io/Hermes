"""
The volume-profile source — v8 chart bars for the three books.

WHY v8 AND NOT THE SPARK ENDPOINT everything else uses: spark at 5d/5m
returns closes only — probed 2026-09-01, `quote keys: ['close']`, no volume —
and a volume profile without volume is a price histogram. The v8 chart
endpoint carries the full OHLCV per bar. One request per asset rather than
one batched request, which at three assets on a five-minute cadence is a
price not worth engineering around.

FIVE DAYS OF 5-MINUTE BARS so the previous RTH session survives weekends and
the odd holiday walk-back. ~55KB per asset.
"""

from __future__ import annotations

import urllib.parse
from datetime import datetime
from typing import Any
from zoneinfo import ZoneInfo

from ..config import BROWSER_UA
from ..http import SourceStatus, fetch, json_body
from ..profile import assemble

ET = ZoneInfo("America/New_York")

CHART = (
    "https://query1.finance.yahoo.com/v8/finance/chart/{sym}"
    "?range=5d&interval=5m"
)

# The three books, same futures contracts the ranges panel segments.
ASSETS: list[tuple[str, str]] = [
    ("NQ", "NQ=F"),
    ("ES", "ES=F"),
    ("GC", "GC=F"),
]


def collect() -> tuple[dict[str, Any], SourceStatus]:
    """Profiles for the three books: prev RTH, overnight, developing."""
    st = SourceStatus("Volume profile")
    now_et = datetime.now(ET)
    assets: dict[str, Any] = {}
    errors: list[str] = []

    for key, sym in ASSETS:
        url = CHART.format(sym=urllib.parse.quote(sym, safe=""))
        r = st.absorb(fetch(url, key=f"chart5m_{key}", ttl_sec=240.0, ua=BROWSER_UA, timeout=25,
                            stale_max_sec=1800.0, validate=json_body))
        if not r.ok or r.body is None:
            errors.append(f"{key}: {r.error or 'empty'}")
            assets[key] = {"ok": False, "error": r.error or "empty response", "rows": []}
            continue
        try:
            doc = r.json()
            res = (doc.get("chart") or {}).get("result") or []
            resp = res[0]
            stamps = resp.get("timestamp") or []
            q = ((resp.get("indicators") or {}).get("quote") or [{}])[0]
            meta = resp.get("meta") or {}
        except (ValueError, TypeError, IndexError, AttributeError) as e:
            errors.append(f"{key}: parse {e}")
            assets[key] = {"ok": False, "error": f"parse: {e}", "rows": []}
            continue

        n = len(stamps)
        rows = assemble(
            list(stamps),
            list((q.get("high") or [None] * n)[:n]),
            list((q.get("low") or [None] * n)[:n]),
            list((q.get("volume") or [None] * n)[:n]),
            now_et,
            opens=list((q.get("open") or [None] * n)[:n]),
        )
        if not rows:
            assets[key] = {"ok": False, "error": "no window had enough traded bars", "rows": []}
            continue
        assets[key] = {
            "ok": True,
            "rows": rows,
            "last": meta.get("regularMarketPrice"),
        }

    ok_count = sum(1 for v in assets.values() if v.get("ok"))
    st.items = ok_count
    if errors:
        st.notes.extend(errors[:3])
    if ok_count == 0 and errors:
        st.error = "; ".join(errors[:2])
    st.settle(ok_count > 0, "asset")
    if st.ok:
        st.notes.append("approximate: 5m bars, volume spread across each bar's range")
    return {"assets": assets}, st
