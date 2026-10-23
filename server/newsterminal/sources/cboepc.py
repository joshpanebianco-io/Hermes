"""
Cboe's daily put/call ratios — the market-wide options positioning the desk
had no number for.

WHAT IT IS. Cboe publishes, after each close, the day's put and call volume
by segment as ratios: total, index, equity, ETP, VIX, SPX. The EQUITY ratio
is the one the tape quotes as a sentiment gauge — single-stock options are
where retail and the hedgers meet, and a very low ratio (calls piled up) has
preceded pullbacks often enough to be a warning, a high one (puts piled up)
to be support. Contrarian and slow: a read for the week, never a timing
tool for the open, and the sentence says so.

THE FILE IS ONE PER DAY AND NEVER CHANGES, so each is fetched once and kept
in a small log (cache/cboe_pc.jsonl); the log is what makes a 20-day average
and a percentile possible. A cold start backfills forty trading days at five
files a tick, so the averages fill in within minutes.

WHEN TODAY'S EXISTS. The file appears some time after 16:15 ET; before then
the latest is the previous trading day's, and a 403 (not published yet) is
not an error, just not yet.
"""

from __future__ import annotations

import json
import os
from datetime import UTC, date, datetime
from typing import Any
from zoneinfo import ZoneInfo

from ..config import BROWSER_UA, CACHE_DIR
from ..holidays import is_trading_day, prev_trading_day
from ..http import SourceStatus, fetch, json_body

ET = ZoneInfo("America/New_York")
URL = "https://cdn.cboe.com/data/us/options/market_statistics/daily/{d}_daily_options"
LOG_FILE = os.path.join(CACHE_DIR, "cboe_pc.jsonl")

#: Cboe's row names → the keys kept.
RATIOS: dict[str, str] = {
    "TOTAL PUT/CALL RATIO": "total",
    "INDEX PUT/CALL RATIO": "index",
    "EQUITY PUT/CALL RATIO": "equity",
    "EXCHANGE TRADED PRODUCTS PUT/CALL RATIO": "etp",
    "CBOE VOLATILITY INDEX (VIX) PUT/CALL RATIO": "vix",
    "SPX + SPXW PUT/CALL RATIO": "spx",
}
#: Days kept and averaged, and how many a cold start fetches.
KEEP_DAYS = 120
BACKFILL_DAYS = 40
PER_TICK = 5
AVG_DAYS = 20
#: The rules of thumb for the equity and total ratios (module docstring).
EQUITY_LOW = 0.55
EQUITY_HIGH = 0.80
TOTAL_LOW = 0.80
TOTAL_HIGH = 1.10
#: Minutes after midnight ET at which today's file is first tried.
PUBLISH_MIN = 16 * 60 + 30


def parse(doc: Any) -> dict[str, float] | None:
    """Cboe's daily document → {total, index, equity, …}. Pure; None when empty."""
    rows = (doc or {}).get("ratios") if isinstance(doc, dict) else None
    out: dict[str, float] = {}
    for r in rows or []:
        if not isinstance(r, dict):
            continue
        key = RATIOS.get(str(r.get("name") or "").strip().upper())
        if key is None:
            continue
        try:
            out[key] = float(str(r.get("value")))
        except (TypeError, ValueError):
            continue
    return out or None


def latest_day(now: datetime) -> date:
    """The newest trading day whose file may exist: today once PUBLISH_MIN
    has passed on a trading day, else the previous trading day. Pure."""
    et = now.astimezone(ET)
    d = et.date()
    if is_trading_day(d) and et.hour * 60 + et.minute >= PUBLISH_MIN:
        return d
    return prev_trading_day(d)


def equity_read(v: float | None) -> str | None:
    if v is None:
        return None
    if v <= EQUITY_LOW:
        return ("call-heavy: complacent. A contrarian warning for longs over the week, "
                "not a reason to sell the open.")
    if v >= EQUITY_HIGH:
        return ("put-heavy: hedged. Contrarian support — a market this protected falls "
                "less easily.")
    return "normal: no sentiment edge from the equity book."


def total_read(v: float | None) -> str | None:
    if v is None:
        return None
    if v <= TOTAL_LOW:
        return "light hedging across the market."
    if v >= TOTAL_HIGH:
        return "heavy hedging across the market."
    return "hedging in its normal range."


def summarise(log: dict[str, dict[str, float]]) -> dict[str, Any] | None:
    """The newest day's ratios with the 20-day averages, each ratio's percentile
    over the days held, and the reads. Pure. None without a day."""
    if not log:
        return None
    days = sorted(log)
    today = days[-1]
    cur = log[today]
    window = [log[d] for d in days[-AVG_DAYS:]]
    avg: dict[str, float | None] = {}
    pct: dict[str, int | None] = {}
    for k in RATIOS.values():
        xs = [w[k] for w in window if k in w]
        avg[k] = round(sum(xs) / len(xs), 2) if xs else None
        allx = [log[d][k] for d in days if k in log[d]]
        v = cur.get(k)
        pct[k] = (round(sum(1 for x in allx if x <= v) / len(allx) * 100.0)
                  if v is not None and len(allx) >= 10 else None)
    return {
        "date": today, "ratios": cur, "avg20": avg, "pctile": pct, "days": len(days),
        "read": {"equity": equity_read(cur.get("equity")), "total": total_read(cur.get("total"))},
    }


class PutCallStore:
    """The per-day ratios held between ticks, on disk as JSON lines."""

    def __init__(self, path: str = LOG_FILE) -> None:
        self.path = path
        self.log: dict[str, dict[str, float]] = {}
        self.missing: dict[str, float] = {}  # day → epoch after which to retry
        self._load()

    def _load(self) -> None:
        try:
            with open(self.path, encoding="utf-8") as f:
                for line in f:
                    try:
                        r = json.loads(line)
                        d = date.fromisoformat(str(r["date"])).isoformat()
                        vals = {k: float(v) for k, v in (r.get("ratios") or {}).items()}
                    except (ValueError, KeyError, TypeError):
                        continue
                    if vals:
                        self.log[d] = vals
        except OSError:
            pass

    def _save(self) -> None:
        tmp = self.path + ".tmp"
        try:
            os.makedirs(os.path.dirname(self.path) or ".", exist_ok=True)
            with open(tmp, "w", encoding="utf-8") as f:
                for d in sorted(self.log)[-KEEP_DAYS:]:
                    f.write(json.dumps({"date": d, "ratios": self.log[d]}) + "\n")
            os.replace(tmp, self.path)
        except OSError:
            pass

    def wanted(self, now: datetime) -> list[str]:
        """Trading days not yet held, newest first, back to BACKFILL_DAYS."""
        d = latest_day(now)
        out: list[str] = []
        t = now.timestamp()
        for _ in range(BACKFILL_DAYS):
            k = d.isoformat()
            if k not in self.log and self.missing.get(k, 0.0) <= t:
                out.append(k)
            d = prev_trading_day(d)
        return out

    def tick(self, now: datetime | None = None) -> tuple[dict[str, Any] | None, SourceStatus]:
        now = now or datetime.now(UTC)
        st = SourceStatus("Cboe put/call")
        fetched = 0
        errors: list[str] = []
        for day in self.wanted(now)[:PER_TICK]:
            r = fetch(URL.format(d=day), key=f"cboepc_{day}", ttl_sec=30 * 86400.0,
                      ua=BROWSER_UA, timeout=20, stale_ok=False,
                      headers={"Accept": "application/json"}, validate=json_body)
            fetched += 1
            if not r.ok or r.body is None:
                # Not published yet (403 from the CDN) or a holiday the
                # calendar missed: try again in an hour, never every tick.
                self.missing[day] = now.timestamp() + 3600.0
                if r.status not in (403, 404):
                    errors.append(f"{day}: {r.error or 'unavailable'}")
                continue
            try:
                vals = parse(r.json())
            except ValueError as e:
                errors.append(f"{day}: unreadable ({e})")
                continue
            if vals:
                self.log[day] = vals
        if fetched:
            self._save()
        summary = summarise(self.log)
        st.items = len(self.log)
        if errors:
            st.error = errors[0]
        st.ok = summary is not None
        st.source = "live" if st.ok else "unavailable"
        st.age_min = 0.0 if st.ok else None
        if st.ok:
            st.last_ok_utc = datetime.now(UTC).isoformat()
            st.notes = [f"latest {summary['date'] if summary else '—'} · {len(self.log)} days held"]
            latest = latest_day(now).isoformat()
            if summary and summary["date"] < latest:
                st.notes.append(f"{latest}'s file not published yet")
        return summary, st

