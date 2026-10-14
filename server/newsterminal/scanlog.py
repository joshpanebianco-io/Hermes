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
records them without alerting on a signal from two hours ago. A backfilled
event carries NO score (audit, 2026-10-14): the score its row has when the
replay finds it is the score hours later — 0 after the close — and the record
would file a strong signal under "score < 40".

ONLY FINAL BARS, AND A SECOND LOOK (audit, 2026-10-14). A signal is read off a
bar only once that name's bars were downloaded after the bar closed
(scan.CLOSE_LAG_SEC). Yahoo still revises a bar now and then — a pre-market
print dropped, a late trade added — so every logged (L), (E) and breakout is
checked again against the newest final bars (`revalidate`): one that no longer
exists is RETRACTED (kept, flagged, out of the record and announced as
withdrawn), and one whose price or stop moved is corrected, the first figures
kept beside it. A finished day is settled once more against bars read after
its close (`settle`) and marked `checked`.

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
from .scan import BAR_SEC, CLOSE_LAG_SEC, ET, SRC_SEC, Bar, fmt_px

EVENTS_FILE = os.path.join(CACHE_DIR, "scanner_events.jsonl")
KEEP_DAYS = 30
LIVE_LAG_SEC = 2 * BAR_SEC  # found within two bars of the bar closing
#: A day whose last bars never arrived settles anyway this long after its
#: close, on what there is — the bars will not get any better.
SETTLE_ANYWAY_SEC = 3600
#: Retractions the alert feed reports, by day: today's and the session before.
RETRACT_DAYS = 2
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
        # The row's score NOW — which is the signal's only when found live.
        "score": score if live else None,
        "note": note,
        "live": live,
        "outcome": blank_outcome() if kind in TRADES else None,
    }


def signal_events(sym: str, signals: Iterable[dict[str, Any]], score: int | None, day: str,
                  now_ts: float) -> list[dict[str, Any]]:
    """The (L) / (E) / breakout events one name's replayed signals imply. Pure."""
    out: list[dict[str, Any]] = []
    for sg in signals:
        kind = sg.get("kind")
        if kind not in KINDS or sg.get("t") is None or sg.get("price") is None:
            continue
        side = str(sg.get("side"))
        text = str(sg.get("note") or "")
        note = f"{_LABEL[kind]} {side} — {text[:1].lower()}{text[1:]}"
        out.append(_event(sym, kind, side, sg.get("level"), int(sg["t"]), sg["price"],
                          sg.get("stop"), score, note, day, now_ts))
    return out


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
        out += signal_events(sym, r.get("signals") or [], score, day, now_ts)
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


def _moved(a: Any, b: Any) -> bool:
    if a is None or b is None:
        return (a is None) != (b is None)
    return abs(float(a) - float(b)) > 1e-6


def revalidate(ev: dict[str, Any], found: dict[str, dict[str, Any]], final_to: int | None,
               now_ts: float) -> bool:
    """Check one logged (L) / (E) / breakout against `found` — the events the newest
    bars imply, by dedupe key — once its bar is final in them (`final_to`). In place;
    returns whether `ev` changed.

    Gone → retracted (kept, flagged). Price or stop moved → corrected, with the
    first figures kept under `revised` and the outcome recomputed from scratch.
    Back again → the retraction lifted. A bar not yet final is left alone.
    """
    if ev.get("kind") not in KINDS or final_to is None or int(ev["t"]) + BAR_SEC > final_to:
        return False
    cur = found.get(dedupe_key(ev))
    if cur is None:
        if ev.get("retracted"):
            return False
        ev["retracted"] = True
        ev["retracted_ts"] = _iso(now_ts)
        return True
    changed = False
    if ev.pop("retracted", None):
        ev.pop("retracted_ts", None)
        changed = True
    if _moved(ev.get("price"), cur["price"]) or _moved(ev.get("stop"), cur.get("stop")):
        ev.setdefault("revised", {"price": ev.get("price"), "stop": ev.get("stop"),
                                  "note": ev.get("note")})
        ev["price"], ev["stop"], ev["note"] = cur["price"], cur.get("stop"), cur["note"]
        if ev.get("outcome") is not None:
            ev["outcome"] = blank_outcome()
        changed = True
    return changed


def _session_close_ts(day: date) -> int:
    m = close_minute(day)
    return int(datetime(day.year, day.month, day.day, m // 60, m % 60, tzinfo=ET).timestamp())


def compute_outcome(ev: dict[str, Any], bars5: list[Bar], now_ts: float,
                    asof: float | None = None) -> dict[str, Any]:
    """An (L) or (E)'s result so far, off completed 5-minute bars. Pure.

    The (L) enters at its bar's close, so the bars after it count; the (E)
    triggers inside its bar, so that bar counts too — its low (for a long) can
    already be the stop. Same-bar stop and target is STOPPED (module docstring).

    `asof` is when `bars5` were downloaded: a bar that had not ended
    CLOSE_LAG_SEC before it is only part of a bar and is not read. FINAL ONLY
    ON BARS THAT REACH THE BELL (audit, 2026-10-14): an outcome used to settle
    at 16:00 on whatever copy of the bars was held — one read at 15:58 has no
    15:55 bar, so its close return was the 15:50 bar's, filed for good. Now it
    settles once bars read after the close cover it, or, when the last bars
    never come (a halt), SETTLE_ANYWAY_SEC after the bell on what there is.
    """
    out = blank_outcome()
    entry, stop = float(ev["price"]), ev.get("stop")
    day = date.fromisoformat(ev["day"])
    close_ts = _session_close_ts(day)
    known = now_ts if asof is None else min(now_ts, asof - CLOSE_LAG_SEC)
    if stop is None or abs(entry - float(stop)) <= 0:
        out["final"] = known >= close_ts
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
        if b.t >= close_ts or end > known:
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
    # A bar ending at the bell was read whole — or there was nothing after the
    # signal to read (an (L) on the day's last bar).
    covered = last_end >= close_ts or start >= close_ts
    if known >= close_ts and covered and last_close is not None:
        out["ret_close_r"] = round(s * (last_close - entry) / r, 3)
    if known >= close_ts and (covered or now_ts >= close_ts + SETTLE_ANYWAY_SEC):
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
        if e.get("kind") in TRADES and not e.get("retracted")
        and (e.get("outcome") or {}).get("final")
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
                        # Logged before backfills stopped carrying a score: the
                        # one they have is from hours later (module docstring).
                        if ev.get("live") is False:
                            ev["score"] = None
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
                now: datetime | None = None,
                fetched: dict[str, float] | None = None) -> list[dict[str, Any]]:
        """Log what is new in this payload, check today's logged signals against
        the newest final bars, and update open outcomes. Returns the new.

        `fetched` is when each name's `bars` were downloaded — an outcome reads
        only the bars that had ended by then (compute_outcome)."""
        now = now or datetime.now(UTC)
        day = str(payload.get("trading_day") or "")
        if not day:
            return []
        rows = [r for r in payload.get("rows") or [] if isinstance(r, dict)]
        now_ts = now.timestamp()
        new: list[dict[str, Any]] = []
        changed = False
        with self._lock:
            for c in candidates(rows, str(payload.get("session")), day, now):
                k = dedupe_key(c)
                if k in self._keys:
                    continue
                c["id"] = self._next
                self._next += 1
                self._keys.add(k)
                self.events.append(c)
                new.append(c)
                changed = True
            # The second look at what was logged today (module docstring).
            found: dict[str, tuple[dict[str, dict[str, Any]], int | None]] = {}
            for r in rows:
                if r.get("ok"):
                    evs = signal_events(str(r.get("sym")), r.get("signals") or [], None, day,
                                        now_ts)
                    found[str(r.get("sym"))] = ({dedupe_key(e): e for e in evs}, r.get("final_to"))
            for e in self.events:
                if e.get("day") == day and e.get("sym") in found:
                    got, final_to = found[e["sym"]]
                    changed |= revalidate(e, got, final_to, now_ts)
            changed |= self._outcomes(bars, now_ts, fetched or {})
            if changed:
                self._save(now.astimezone(ET).date())
        return new

    def _outcomes(self, bars: dict[str, list[Bar]], now_ts: float,
                  fetched: dict[str, float]) -> bool:
        """Every open outcome brought up to date. Under the lock."""
        changed = False
        for e in self.events:
            o = e.get("outcome")
            if o is None or o.get("final") or e.get("retracted"):
                continue
            b = bars.get(e["sym"])
            if not b:
                continue
            o2 = compute_outcome(e, b, now_ts, fetched.get(e["sym"]))
            if o2 != o:
                e["outcome"] = o2
                changed = True
        return changed

    def unchecked(self, before: str) -> dict[str, set[str]]:
        """{day: names} with a logged (L), (E) or breakout from a finished day
        (before `before`, the trading day) not yet settled against final bars."""
        out: dict[str, set[str]] = {}
        with self._lock:
            for e in self.events:
                if e.get("kind") in KINDS and not e.get("checked") and e.get("day", "") < before:
                    out.setdefault(e["day"], set()).add(e["sym"])
        return out

    def settle(self, day: str, by_sym: dict[str, tuple[list[dict[str, Any]], int | None]],
               now: datetime | None = None) -> int:
        """Settle a FINISHED day against its signals replayed from bars read after
        its close — {name: (signals, final_to)}. Each logged event is checked
        (`revalidate`) and marked `checked` once the bars reach the bell; a
        signal those bars hold that was never logged is logged now, not live.
        Returns how many events changed or were added."""
        now = now or datetime.now(UTC)
        now_ts = now.timestamp()
        close = _session_close_ts(date.fromisoformat(day))
        n = 0
        with self._lock:
            for sym, (signals, final_to) in by_sym.items():
                evs = signal_events(sym, signals, None, day, now_ts)
                got = {dedupe_key(e): e for e in evs}
                whole = final_to is not None and final_to >= close
                for e in self.events:
                    if e.get("day") != day or e.get("sym") != sym or e.get("kind") not in KINDS:
                        continue
                    hit = revalidate(e, got, final_to, now_ts)
                    if whole and not e.get("checked"):
                        e["checked"] = True
                        hit = True
                    n += hit
                if not whole:
                    continue
                for k, c in got.items():
                    if k in self._keys:
                        continue
                    c["id"] = self._next
                    c["checked"] = True
                    self._next += 1
                    self._keys.add(k)
                    self.events.append(c)
                    n += 1
            if n:
                self._save(now.astimezone(ET).date())
        return n

    def since(self, since: int, limit: int = 200) -> dict[str, Any]:
        """Events with id > since, and `retracted`: the ids of the last
        RETRACT_DAYS days' withdrawn events, so a page that announced one can
        say it was withdrawn."""
        with self._lock:
            latest = self._next - 1
            evs = [dict(e) for e in self.events if e["id"] > since][:limit]
            days = sorted({str(e.get("day", "")) for e in self.events})[-RETRACT_DAYS:]
            gone = [e["id"] for e in self.events if e.get("retracted") and e.get("day") in days]
        return {"latest": latest, "events": evs, "retracted": gone}

    def stats(self, days: int = 20, today: date | None = None) -> dict[str, Any]:
        with self._lock:
            evs = list(self.events)
        return stats(evs, days, today or datetime.now(ET).date())
