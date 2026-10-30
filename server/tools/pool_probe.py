"""Read the pool now and print what it would promote, with the figures beside it.

    python tools/pool_probe.py [PINNED ...]     (default: the saved pinned list)

Exists for the same reason as scan_probe.py: the owner checks a rule by reading
its ACTUAL OUTPUT. One POST to TradingView's screener (sources/pool.py), then:
the counts through the gates, the top of the rank with each name's gap in
ATRs and volume share, the regular close beside the pre-market last — which is
how Monday's pre-market confirms the assumption the module docstring names —
and the list each mark would promote against the pinned names given.
"""

from __future__ import annotations

import json
import sys
from datetime import UTC, datetime

sys.path.insert(0, __file__.rsplit("tools", 1)[0])

from newsterminal import scan
from newsterminal.config import BROWSER_UA
from newsterminal.http import fetch
from newsterminal.sources import pool
from newsterminal.sources.scanner import load_watchlist


def main() -> int:
    pinned = [s.upper() for s in sys.argv[1:]] or load_watchlist()
    now = datetime.now(UTC)
    clock = scan.clock_at(now)
    r = fetch(pool.URL, key="probe_pool", ttl_sec=0.0, timeout=pool.TIMEOUT, ua=BROWSER_UA,
              headers=pool.HEADERS, validate=pool.pool_body,
              data=json.dumps(pool.query()).encode())
    if not r.ok:
        print(f"pool: {r.error}")
        return 1
    rows, err = pool.parse(r.json())
    if err:
        print(f"pool: {err}")
        return 1
    q = pool.qualify(rows)
    ranked = pool.rank(q, clock)
    et = clock.now.strftime("%a %d %b %H:%M ET")
    print(f"{et} · session {clock.session} · levels for {clock.trading_day} · "
          f"basis {pool.basis_for(clock)} · {r.source}, {len(r.body or b'') / 1024:.0f} KB")
    print(f"{len(rows)} common lines and DRs at ${pool.MIN_CAP / 1e9:.0f}bn+ → {len(q)} qualified "
          f"(${pool.MIN_DOLLAR_VOL / 1e6:.0f}m+ a day, ATR {pool.MIN_ATR_PCT}%+, ${pool.MIN_PRICE:.0f}+)")
    print(f"pinned {len(pinned)} → {max(0, pool.MAX_SYMBOLS - len(pinned))} slots\n")
    by = {x["symbol"]: x for x in q}
    print(f"{'rank':>4} {'sym':6} {'score':>5} {'gap':>5} {'vol%':>6}  {'close':>9} {'pm last':>9} "
          f"{'pm chg%':>7} {'pm vol':>10}  reason")
    for i, x in enumerate(ranked[:30], 1):
        raw = by[x["symbol"]]
        pm_last = raw.get("pm_close")
        pm_chg = raw.get("pm_change")
        print(f"{i:>4} {x['symbol']:6} {x['score']:>5} {x['gap_atr'] if x['gap_atr'] is not None else '—':>5} "
              f"{x['vol_pct'] if x['vol_pct'] is not None else '—':>6}  {raw.get('close') or 0:>9.2f} "
              f"{pm_last if pm_last is not None else 0:>9.2f} {pm_chg if pm_chg is not None else 0:>7.2f} "
              f"{int(raw.get('pm_volume') or 0):>10,}  {x['reason']}")
    for mark in ("08:00", "10:00"):
        cur = pool.promote(ranked, pinned, [], "09:25") if mark == "10:00" else []
        got = pool.promote(ranked, pinned, cur, mark)
        print(f"\nmark {mark}: {len(got)} promoted → " + ", ".join(f"{g['symbol']} {g['score']}" for g in got))
    return 0


if __name__ == "__main__":
    sys.exit(main())
