"""
The scanner's event log — the feed alerts are raised from, and the record the
score will one day be judged against.

WHY THE ENGINE KEEPS IT, NOT THE PAGE. LE_Model.pine alerts on its signals; the
terminal now does too (owner instruction, 2026-10-13: alerts, and "signal
logging so the score can be calibrated"). An alert raised by diffing two polls
in the browser would fire twice in two tabs, never fire with the page closed,
and leave no record. So the collector detects each signal once, gives it an id
that keeps counting across restarts, and the page only asks "anything after
id N?".

WHAT IS AN EVENT. The script's own signals on confirmed ten-minute bars — an (L)
retest, an (E) trigger, a ◆ breakout — and NEAR: a name ninety per cent of the
way to a level during the regular session, the script's "about to break". They
are read off the same replay the scanner row is built from; nothing new is
fetched for them.

LIVE OR BACKFILLED. After a restart the replay finds the morning's signals all
over again. Those already in the file are recognised by their key (day, name,
kind, side, level, bar) and skipped; any it did not have are logged, but marked
`live: false` — found more than two bars after the bar closed — so the page
records them without alerting on a signal from two hours ago.

THE OUTCOME OF EVERY (L) AND (E). Entry is the signal price, the stop is the
script's own "stop idea" (the (L) bar's low/high, the (E) candle's), and R is
the distance between them. From the signal on, the log tracks the best and
worst excursion in R, whether +1R (and +2R) came before the stop, and where
price stood 30 and 60 minutes after the signal bar and at the close. That is
the dataset the heuristic weights in scanscore.py can later be fitted to.

ON A TEN-MINUTE BAR THE ORDER INSIDE IT IS UNKNOWN. When one bar reaches both
+1R and the stop, the log counts it STOPPED — the conservative reading, since a
record that flatters the strategy is worse than none. Outcomes are read off the
5-minute bars, which halves how often that happens.
"""

from __future__ import annotations

import json
import os
import threading
from collections.abc import Iterable
from datetime import UTC, date, datetime, timedelta
from typing import Any

from .config import CACHE_DIR
from .holidays import close_minute
from .scan import BAR_SEC, ET, SRC_SEC, Bar, fmt_px

EVENTS_FILE = os.path.join(CACHE_DIR, "scanner_events.jsonl")
KEEP_DAYS = 30
LIVE_LAG_SEC = 2 * BAR_SEC  # found within two bars of the bar closing
KINDS = ("L", "E", "BO")
NEAR = "NEAR"
NEAR_PCT = 0.90
TRADES = ("L", "E")  # the kinds with an entry, a stop and an outcome

_LABEL = {"L": "(L)", "E": "(E)", "BO": "◆", NEAR: "Near"}


def _iso(t: float) -> str:
    return datetime.fromtimestamp(t, UTC).isoformat()


def _hm(t: float) -> str:
    return datetime.fromtimestamp(t, ET).strftime("%H:%M")


def dedupe_key(ev: dict[str, Any]) -> str:
    """One signal is one event however often the replay finds it. NEAR is once per
    level per day, whatever bar it was first seen on."""
    if ev["kind"] == NEAR:
        return f"{ev['day']}|{ev['sym']}|NEAR|{ev['level']}"
    return f"{ev['day']}|{ev['sym']}|{ev['kind']}|{ev['side']}|{ev['level']}|{ev['t']}"


def blank_outcome() -> dict[str, Any]:
    return {"r": None, "mfe_r": None, "mae_r": None, "hit_1r": None, "hit_2r": None,
            "stopped": None, "ret_30m_r": None, "ret_60m_r": None, "ret_close_r": None,
            "final": False}


def _event(sym: str, kind: str, side: str, level: str | None, bar_t: int, price: float,
           stop: float | None, score: int | None, note: str, day: str,
           now_ts: float) -> dict[str, Any]:
    live = now_ts - (bar_t + BAR_SEC) <= LIVE_LAG_SEC
    return {
        "id": 0,
        "ts": _iso(now_ts),
        "bar_ts": _iso(bar_t),
        "t": bar_t,
        "at_et": _hm(bar_t),
        "day": day,
        "sym": sym,
        "kind": kind,
        "side": side,
        "level": level,
        "price": round(float(price), 4),
        "stop": round(float(stop), 4) if stop is not None else None,
        "score": score,
        "note": note,
        "live": live,
        "outcome": blank_outcome() if kind in TRADES else None,
    }


def candidates(rows: Iterable[dict[str, Any]], session: str, day: str,
               now: datetime) -> list[dict[str, Any]]:
    """Every event the payload's rows imply right now — new or not. Pure."""
    now_ts = now.timestamp()
    out: list[dict[str, Any]] = []
    for r in rows:
        if not r.get("ok"):
            continue
        sym = str(r.get("sym"))
        score = (r.get("score") or {}).get("total")
        for sg in r.get("signals") or []:
            kind = sg.get("kind")
            if kind not in KINDS or sg.get("t") is None or sg.get("price") is None:
                continue
            side = str(sg.get("side"))
            text = str(sg.get("note") or "")
            note = f"{_LABEL[kind]} {side} — {text[:1].lower()}{text[1:]}"
            out.append(_event(sym, kind, side, sg.get("level"), int(sg["t"]), sg["price"],
                              sg.get("stop"), score, note, day, now_ts))
        if session != "rth" or r.get("last") is None:
            continue
        prog = r.get("progress") or {}
        lv = r.get("levels") or {}
        for key, name in (("pdh", "PDH"), ("pmh", "PMH"), ("pdl", "PDL"), ("pml", "PML")):
            p = prog.get(key)
            if p is None or p < NEAR_PCT:
                continue
            if key in ("pmh", "pml") and not lv.get("pm_done"):
                continue
            side = "long" if key in ("pdh", "pmh") else "short"
            bar_t = int(now_ts) - int(now_ts) % BAR_SEC
            note = (f"Near {side} — {round(p * 100)}% of the way to {name} "
                    f"{fmt_px(lv.get(key))}")
            out.append(_event(sym, NEAR, side, name, bar_t, r["last"], None, score, note, day,
                              now_ts))
    return out


def _session_close_ts(day: date) -> int:
    m = close_minute(day)
    return int(datetime(day.year, day.month, day.day, m // 60, m % 60, tzinfo=ET).timestamp())


def compute_outcome(ev: dict[str, Any], bars5: list[Bar], now_ts: float) -> dict[str, Any]:
    """An (L) or (E)'s result so far, off completed 5-minute bars. Pure.

    The (L) enters at its bar's close, so the bars after it count; the (E)
    triggers inside its bar, so that bar counts too — its low (for a long) can
    already be the stop. Same-bar stop and target is STOPPED (module docstring).
    """
    out = blank_outcome()
    entry, stop = float(ev["price"]), ev.get("stop")
    day = date.fromisoformat(ev["day"])
    close_ts = _session_close_ts(day)
    if stop is None or abs(entry - float(stop)) <= 0:
        out["final"] = now_ts >= close_ts
        return out
    r = abs(entry - float(stop))
    out["r"] = round(r, 4)
    s = 1.0 if ev["side"] == "long" else -1.0
    t0 = int(ev["t"])
    start = t0 if ev["kind"] == "E" else t0 + BAR_SEC
    ref = t0 + BAR_SEC  # the 30/60-minute marks run from the signal bar's close

    mfe = mae = 0.0
    seen = False
    hit1: bool | None = None
    hit2: bool | None = None
    stopped: bool | None = None
    ret30 = ret60 = None
    last_close: float | None = None
    last_end = 0
    for b in bars5:
        if b.t < start:
            continue
        end = b.t + SRC_SEC
        if b.t >= close_ts or end > now_ts:
            break
        seen = True
        fav = (b.high - entry) if s > 0 else (entry - b.low)
        adv = (entry - b.low) if s > 0 else (b.high - entry)
        mfe, mae = max(mfe, fav), max(mae, adv)
        stop_hit = adv >= r
        if hit1 is None and stopped is None:
            if stop_hit:  # including the bar that also made +1R
                stopped, hit1, hit2 = True, False, False
            elif fav >= r:
                hit1, stopped = True, False
                if fav >= 2 * r:
                    hit2 = True
        elif hit1 and hit2 is None:
            if stop_hit:
                hit2 = False
            elif fav >= 2 * r:
                hit2 = True
        if ret30 is None and end >= ref + 1800:
            ret30 = s * (b.close - entry) / r
        if ret60 is None and end >= ref + 3600:
            ret60 = s * (b.close - entry) / r
        last_close, last_end = b.close, end

    if seen:
        out["mfe_r"] = round(mfe / r, 3)
        out["mae_r"] = round(mae / r, 3)
    out["hit_1r"], out["hit_2r"], out["stopped"] = hit1, hit2, stopped
    out["ret_30m_r"] = round(ret30, 3) if ret30 is not None else None
    out["ret_60m_r"] = round(ret60, 3) if ret60 is not None else None
    if now_ts >= close_ts and last_close is not None and last_end >= close_ts:
        out["ret_close_r"] = round(s * (last_close - entry) / r, 3)
    if now_ts >= close_ts:
        out["final"] = True
        # Settled with neither: it did not reach +1R and was never stopped.
        for k in ("hit_1r", "hit_2r", "stopped"):
            if out[k] is None:
                out[k] = False
    return out


def stats(events: Iterable[dict[str, Any]], days: int, today: date) -> dict[str, Any]:
    """Settled (L)/(E) outcomes over the last `days`, grouped. Pure."""
    start = today - timedelta(days=days)
    rows = [
        e for e in events
        if e.get("kind") in TRADES and (e.get("outcome") or {}).get("final")
        and (e.get("outcome") or {}).get("r") is not None
        and start < date.fromisoformat(e["day"]) <= today
    ]

    def avg(xs: list[float | None]) -> float | None:
        v = [x for x in xs if x is not None]
        return round(sum(v) / len(v), 3) if v else None

    def group(key: str, evs: list[dict[str, Any]]) -> dict[str, Any]:
        n = len(evs)
        outs = [e["outcome"] for e in evs]
        return {
            "key": key,
            "n": n,
            "win_1r": round(sum(1 for o in outs if o.get("hit_1r")) / n, 3) if n else None,
            "avg_close_r": avg([o.get("ret_close_r") for o in outs]),
            "avg_mfe_r": avg([o.get("mfe_r") for o in outs]),
            "avg_mae_r": avg([o.get("mae_r") for o in outs]),
        }

    def scored(lo: float, hi: float) -> list[dict[str, Any]]:
        return [e for e in rows if e.get("score") is not None and lo <= e["score"] < hi]

    groups = [group("all", rows)]
    for kind in TRADES:
        for side in ("long", "short"):
            groups.append(group(f"{kind} {side}",
                                [e for e in rows if e["kind"] == kind and e["side"] == side]))
    groups += [group("score ≥ 60", scored(60, 1e9)), group("score 40–59", scored(40, 60)),
               group("score < 40", scored(-1e9, 40))]
    return {"days": days, "from": (start + timedelta(days=1)).isoformat(),
            "to": today.isoformat(), "total": len(rows), "groups": groups}


class EventLog:
    """The persisted log: `observe` on the scanner thread, `since`/`stats` from the API."""

    def __init__(self, path: str = EVENTS_FILE) -> None:
        self._lock = threading.Lock()
        self._path = path
        self.events: list[dict[str, Any]] = []
        self._keys: set[str] = set()
        self._next = 1
        self._load()

    def _load(self) -> None:
        try:
            with open(self._path, encoding="utf-8") as f:
                for line in f:
                    line = line.strip()
                    if not line:
                        continue
                    try:
                        ev = json.loads(line)
                    except ValueError:
                        continue
                    if isinstance(ev, dict) and isinstance(ev.get("id"), int):
                        self.events.append(ev)
        except OSError:
            return
        self.events.sort(key=lambda e: e["id"])
        self._keys = {dedupe_key(e) for e in self.events}
        self._next = max((e["id"] for e in self.events), default=0) + 1

    def _save(self, today: date) -> None:
        cutoff = (today - timedelta(days=KEEP_DAYS)).isoformat()
        self.events = [e for e in self.events if e.get("day", "") >= cutoff]
        tmp = self._path + ".tmp"
        try:
            os.makedirs(os.path.dirname(self._path), exist_ok=True)
            with open(tmp, "w", encoding="utf-8") as f:
                for e in self.events:
                    f.write(json.dumps(e, separators=(",", ":")) + "\n")
            os.replace(tmp, self._path)
        except OSError:
            pass  # a log that cannot be written is a shorter log, not a broken scanner

    def observe(self, payload: dict[str, Any], bars: dict[str, list[Bar]],
                now: datetime | None = None) -> list[dict[str, Any]]:
        """Log what is new in this payload and update open outcomes. Returns the new."""
        now = now or datetime.now(UTC)
        day = str(payload.get("trading_day") or "")
        if not day:
            return []
        new: list[dict[str, Any]] = []
        changed = False
        with self._lock:
            for c in candidates(payload.get("rows") or [], str(payload.get("session")), day, now):
                k = dedupe_key(c)
                if k in self._keys:
                    continue
                c["id"] = self._next
                self._next += 1
                self._keys.add(k)
                self.events.append(c)
                new.append(c)
                changed = True
            now_ts = now.timestamp()
            for e in self.events:
                o = e.get("outcome")
                if o is None or o.get("final"):
                    continue
                b = bars.get(e["sym"])
                if not b:
                    continue
                o2 = compute_outcome(e, b, now_ts)
                if o2 != o:
                    e["outcome"] = o2
                    changed = True
            if changed:
                self._save(now.astimezone(ET).date())
        return new

    def since(self, since: int, limit: int = 200) -> dict[str, Any]:
        with self._lock:
            latest = self._next - 1
            evs = [dict(e) for e in self.events if e["id"] > since][:limit]
        return {"latest": latest, "events": evs}

    def stats(self, days: int = 20, today: date | None = None) -> dict[str, Any]:
        with self._lock:
            evs = list(self.events)
        return stats(evs, days, today or datetime.now(ET).date())
