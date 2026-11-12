"""
Two years of New York sessions, labelled, with what was known at 09:00 ET —
and the base rates of one against the other (newsterminal/daytype.py).

    python -I tools/daytype_backfill.py            # NQ, ES and GC
    python -I tools/daytype_backfill.py --book NQ  # one book
    python -I tools/daytype_backfill.py --out cache/daytype_backfill.json

THE SESSION IS THE CASH ETF'S, THE NIGHT AND THE YARDSTICK ARE THE FUTURE'S. Yahoo
aligns an ETF's hourly bars to 09:30 and a future's to the hour, so QQQ, SPY and
GLD give a clean 09:30–16:00 bar set for the label, and NQ=F, ES=F and GC=F give
the night and the 09:00 print. The ATR is the future's own, over its Globex day
(18:00 to 17:00 ET, cut from the same hourly bars), because that is the ATR the
ladder's "yesterday" card and the collector's live card measure by (history.py's
daily bars, structure.atr14) — a Yahoo daily futures bar IS the Globex day
(checked 2026-11-10: identical highs and lows) — and a cash-hours ATR runs a third
smaller, which would make the backfill call "trend day" on sessions the ladder
calls normal. It is applied to the ETF's session as a percent of price. Gold's
"New York" is the 09:30–16:00 box the Session ranges panel draws, so GLD's cash
session stands for it; COMEX's own 08:20–13:30 is not what either measures. The
futures' hourly history starts in June 2024, so the tables run from July 2024.

A personal read of Yahoo's public endpoint, like every other read in this
terminal: eight requests, a browser User-Agent, nothing stored but the rows.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import urllib.request
from collections import defaultdict
from datetime import date, datetime, time
from typing import Any

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from newsterminal import daytype
from newsterminal.config import BROWSER_UA, CACHE_DIR
from newsterminal.daytype import ET, Bar, at
from newsterminal.holidays import is_trading_day
from newsterminal.sessions import globex_trade_date

BOOKS = {"NQ": ("QQQ", "NQ=F"), "ES": ("SPY", "ES=F"), "GC": ("GLD", "GC=F")}
CHART = "https://query1.finance.yahoo.com/v8/finance/chart/{sym}?range={rng}&interval={iv}"
#: A full session has seven hourly bars from 09:30; a half day four. Half days are
#: left out of the labels (they are not a normal session) but kept as "yesterday".
FULL_BARS = 6


def chart(sym: str, rng: str, iv: str) -> list[Bar]:
    req = urllib.request.Request(CHART.format(sym=sym, rng=rng, iv=iv),
                                 headers={"User-Agent": BROWSER_UA, "Accept": "application/json"})
    with urllib.request.urlopen(req, timeout=40) as r:
        doc = json.loads(r.read())
    res = doc["chart"]["result"][0]
    q = res["indicators"]["quote"][0]
    out: list[Bar] = []
    for t, o, h, lo, c in zip(res["timestamp"], q["open"], q["high"], q["low"], q["close"], strict=True):
        if None in (o, h, lo, c):
            continue
        out.append((int(t), float(o), float(h), float(lo), float(c)))
    return out


def sessions_of(bars: list[Bar]) -> dict[date, tuple[float, float, float, float, int]]:
    """{session day: (o, h, l, c, bars)} from an ETF's 09:30-aligned hourly bars."""
    by: dict[date, list[Bar]] = defaultdict(list)
    for b in bars:
        d = datetime.fromtimestamp(b[0], ET)
        if time(9, 30) <= d.time() < time(16, 0):
            by[d.date()].append(b)
    out: dict[date, tuple[float, float, float, float, int]] = {}
    for d, bs in sorted(by.items()):
        bs.sort()
        out[d] = (bs[0][1], max(b[2] for b in bs), min(b[3] for b in bs), bs[-1][4], len(bs))
    return out


def globex_days(bars: list[Bar]) -> dict[date, tuple[float, float, float, float]]:
    """{trade date: (o, h, l, c)} from a future's hourly bars, cut the way the exchange
    cuts them (sessions.globex_trade_date): 18:00 ET to the next day's 17:00."""
    by: dict[date, list[Bar]] = defaultdict(list)
    for b in bars:
        by[globex_trade_date(datetime.fromtimestamp(b[0], ET))].append(b)
    out: dict[date, tuple[float, float, float, float]] = {}
    for d, bs in sorted(by.items()):
        bs.sort()
        out[d] = (bs[0][1], max(b[2] for b in bs), min(b[3] for b in bs), bs[-1][4])
    return out


def daily_at(bars: list[Bar], d: date, t: time, field: int) -> float | None:
    """One hourly bar's figure: the bar starting at `t` ET on `d`."""
    ts = int(at(d, t).timestamp())
    for b in bars:
        if b[0] == ts:
            return b[field]
    return None


def build(book: str) -> list[dict[str, Any]]:
    etf, fut = BOOKS[book]
    e_bars = chart(etf, "730d", "60m")
    f_bars = chart(fut, "730d", "60m")
    vix_h = chart("^VIX", "730d", "60m")
    vix_d = chart("^VIX", "2y", "1d")
    vix3m_d = chart("^VIX3M", "2y", "1d")
    sess = sessions_of(e_bars)
    days = sorted(sess)
    # The yardstick: the future's Globex-day ATR (module docstring), as a percent of
    # its close at the previous cash close, applied to the ETF's session in its own
    # points.
    fdays = globex_days(f_bars)
    atr_fut = daytype.atr_series([(d, *fdays[d]) for d in sorted(fdays)])
    vix_close = {datetime.fromtimestamp(b[0], ET).date(): b[4] for b in vix_d}
    vix3m_close = {datetime.fromtimestamp(b[0], ET).date(): b[4] for b in vix3m_d}
    rows: list[dict[str, Any]] = []
    prev: dict[str, Any] | None = None
    prev_prev: dict[str, Any] | None = None
    for i, d in enumerate(days):
        o, h, lo, c, n = sess[d]
        a_fut = atr_fut.get(d)
        prev_day = days[i - 1] if i else None
        fut_close_prev = daily_at(f_bars, prev_day, time(15, 0), 4) if prev_day else None
        if a_fut is None or not prev_day or not fut_close_prev or not is_trading_day(d):
            continue
        atr_pct = a_fut / fut_close_prev * 100.0
        a = atr_pct / 100.0 * sess[prev_day][3]
        lab = daytype.label(o, h, lo, c, a, sess[prev_day][1], sess[prev_day][2])
        vix_now = daily_at(vix_h, d, time(9, 0), 1)
        vprev = vix_close.get(prev_day) if prev_day else None
        v3prev = vix3m_close.get(prev_day) if prev_day else None
        feats = daytype.features(
            d, prev, prev_prev, f_bars, atr_pct, fut_close_prev,
            vix_now if vix_now is not None else vprev,
            (vprev / v3prev) if vprev and v3prev else None)
        row = {**feats, **lab, "book": book, "high": h, "low": lo, "bars": n,
               "ratio": (daily_at(f_bars, d, time(15, 0), 4) or 0) / c if c else None,
               "half_day": n < FULL_BARS}
        rows.append(row)
        prev_prev, prev = prev, {**row, "day": d}
    return rows


def report(book: str, rows: list[dict[str, Any]]) -> str:
    full = [r for r in rows if not r["half_day"] and r.get("prev_type")]
    first, last = full[0]["day"], full[-1]["day"]
    out = [f"\n=== {book}  {len(full)} full sessions, {first} to {last}"
           + ("  (GLD's 09:30–16:00 stands for GC's New York box)" if book == "GC" else "")]
    out.append(daytype.table(daytype.base_rates(full)))
    # What follows what.
    out.append("\nwhat followed each kind of day (row: yesterday → today):")
    for p in ("trend", "normal", "range"):
        sub = [r for r in full if r["prev_type"] == p]
        if sub:
            rt = daytype.rates(sub)
            out.append(f"  after a {p:6} day  n={rt['n']:>3}  trend {rt['trend']:.0%}  normal {rt['normal']:.0%}  range {rt['range']:.0%}  inside {rt['inside']:.0%}")
    # The two strongest pairs, if they add anything.
    quiet_inside = [r for r in full if r.get("overnight_atr") is not None and r["overnight_atr"] < daytype.QUIET_ATR and r.get("prev_inside")]
    big_out = [r for r in full if r.get("open_vs_prev") and r["open_vs_prev"] != "inside" and r.get("overnight_atr") is not None and r["overnight_atr"] >= daytype.BIG_ATR]
    for name, sub in (("quiet night after an inside day", quiet_inside), ("big night, 09:00 outside yesterday's range", big_out)):
        rt = daytype.rates(sub)
        if rt.get("n"):
            out.append(f"  {name:44} n={rt['n']:>3}  trend {rt['trend']:.0%}  range {rt['range']:.0%}" + (" *" if rt["n"] < daytype.BASE_MIN else ""))
    return "\n".join(out)


def main() -> None:
    # Windows' console is cp1252 by default, and the tables carry arrows and dashes.
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")  # type: ignore[union-attr]
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--book", choices=sorted(BOOKS), action="append")
    ap.add_argument("--out", default=os.path.join(CACHE_DIR, "daytype_backfill.json"))
    args = ap.parse_args()
    books = args.book or ["NQ", "ES", "GC"]
    all_rows: dict[str, list[dict[str, Any]]] = {}
    for book in books:
        rows = build(book)
        all_rows[book] = rows
        print(report(book, rows))
    os.makedirs(os.path.dirname(args.out), exist_ok=True)
    with open(args.out, "w", encoding="utf-8") as f:
        json.dump({"built_utc": datetime.now(tz=ET).isoformat(), "rows": all_rows}, f, default=str)
    print(f"\nrows written to {args.out}")


if __name__ == "__main__":
    main()
