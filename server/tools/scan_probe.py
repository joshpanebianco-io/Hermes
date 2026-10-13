"""Replay the scanner's clock and levels at the boundary instants, on real bars.

    python tools/scan_probe.py [SYM ...]        (default: AAPL SPY)

Exists because the owner checks session logic by reading the ACTUAL OUTPUT at
the edges — 03:59 vs 04:00, 09:29 vs 09:30, 15:59 vs 16:00, 19:59 vs 20:00 and
the weekend — rather than a description of the rule. One download of five days
of 5-minute bars; each instant sees only the bars that had COMPLETED by then, so
nothing here is computed with hindsight.
"""

from __future__ import annotations

import sys
import urllib.parse
from datetime import datetime, timedelta

sys.path.insert(0, __file__.rsplit("tools", 1)[0])

from newsterminal import scan
from newsterminal.config import BROWSER_UA
from newsterminal.http import fetch
from newsterminal.scan import ET
from newsterminal.sources.scanner import CHART


def bars_for(sym: str) -> tuple[list[scan.Bar], list[scan.DayBar]]:
    q = urllib.parse.quote(sym)
    r = fetch(CHART.format(sym=q, rng="5d", iv="5m"), key=f"probe5m_{sym}", ttl_sec=60,
              ua=BROWSER_UA)
    d = fetch(CHART.format(sym=q, rng="3mo", iv="1d"), key=f"probe1d_{sym}", ttl_sec=3600,
              ua=BROWSER_UA)
    bars, _ = scan.parse_chart(r.json()) if r.ok else ([], {})
    return bars, scan.parse_daily(d.json()) if d.ok else []


def instants(now: datetime) -> list[datetime]:
    """Every boundary on the last two weekdays in the data, plus the weekend."""
    today = now.date()
    prev = today - timedelta(days=1)
    while prev.weekday() >= 5:
        prev -= timedelta(days=1)
    sat = today - timedelta(days=(today.weekday() - 5) % 7 or 7)
    fri = sat - timedelta(days=1)
    hm = [(3, 59), (4, 0), (9, 29), (9, 30), (9, 40), (15, 59), (16, 0), (19, 59), (20, 0)]
    out = [datetime(prev.year, prev.month, prev.day, h, m, tzinfo=ET) for h, m in hm]
    out += [datetime(today.year, today.month, today.day, h, m, tzinfo=ET) for h, m in hm]
    out += [datetime(fri.year, fri.month, fri.day, 20, 0, tzinfo=ET),
            datetime(sat.year, sat.month, sat.day, 12, 0, tzinfo=ET)]
    return sorted(out)


def f(x: float | None) -> str:
    return "—" if x is None else f"{x:.2f}"


def main() -> None:
    syms = sys.argv[1:] or ["AAPL", "SPY"]
    now = datetime.now(ET)
    print(f"now {now:%a %Y-%m-%d %H:%M} ET — each row sees only bars completed by its instant")
    for sym in syms:
        bars, daily = bars_for(sym)
        print(f"\n{sym}: {len(bars)} bars, {len(daily)} daily")
        print(f"{'instant':<16}{'trading_day':<13}{'session':<8}{'pd from':<12}"
              f"{'PDH':>9}{'PDL':>9}{'PMH':>9}{'PML':>9}  {'pm_done':<8}{'lvl':>4}{'last':>10}")
        for t in instants(now):
            if t > now:
                print(f"{t:%a %m-%d %H:%M}   (in the future — no bars yet)")
                continue
            done = [b for b in bars if b.t + scan.SRC_SEC <= t.timestamp()]
            spy_ref = done  # holiday detection reads the symbol's own tape here
            clock = scan.clock_at(t, scan.is_holiday(t, spy_ref))
            tech = scan.technicals(done, daily, clock)
            pdd = tech.pdh_day.strftime("%a %m-%d") if tech.pdh_day else "—"
            print(f"{t:%a %m-%d %H:%M}  {clock.trading_day:%a %m-%d}    {clock.session:<8}"
                  f"{pdd:<12}{f(tech.pdh):>9}{f(tech.pdl):>9}{f(tech.pmh):>9}{f(tech.pml):>9}"
                  f"  {('yes' if tech.pm_done else 'no'):<8}{tech.lvl_state:>4}{f(tech.last):>10}")


if __name__ == "__main__":
    main()
