"""
The scanner's read — the macro regime, the score, the flags, and the join.

THE SCORE IS A HEURISTIC RANK, NOT A CALIBRATED PROBABILITY. Every weight below
is a judgement about what the owner's strategy rewards — a stock already outside
both of its levels, strong against SPY, sitting at its entry, on volume, with the
tape and the sector behind it — and none of them has been fitted to outcomes.
The number orders a watchlist; it does not say how often the trade works. That
is why every row carries its parts: the reader can see that a 71 is "structure
30, RS 22, location 14, volume 0, market 5" and disagree with any of them.

VIX IS THE WEATHER, NOT A SIGNAL. It never picks a stock. It sets the band the
session is likely to run in (how far a level trade can go, how wide the noise
is), and its intraday direction against SPY says whether the tape is confirming
or diverging. Both reach the score only through `market`, and the band reaches
the page as a sentence rather than as points — a low-vol day does not make one
breakout better than another, it makes all of them worse, which is a note to
the reader and not a reordering.

COMPUTED ON READ. The technicals are refreshed by the collector's scanner job;
this joins them with whatever the snapshot holds now (VIX, sectors, the
calendar, earnings, the wire, per-ticker headlines and filings), so a print that
lands moves the regime on the next poll rather than the next fetch.
"""

from __future__ import annotations

import math
import re
from datetime import UTC, date, datetime
from typing import Any
from zoneinfo import ZoneInfo

from .scan import Clock
from .volterm import state as volterm_state

ET = ZoneInfo("America/New_York")

# ---- the weights (a heuristic rank — see the module docstring) --------------
W_STRUCTURE = {2: 30, 1: 18}
W_APPROACH = 10
W_RS = 25
RS_FULL = 1.0  # RS of +1 daily ATR over SPY earns the whole RS part
W_LOCATION = {
    "retest": 20, "pullback": 14, "extended_near": 12, "extended_far": 4,
    "approaching": 6, "forming": 8, "failed": 0, "chop": 0,
}
W_VOLUME = ((2.0, 10), (1.5, 7), (1.0, 4))
W_BIAS = 8
W_CONFIRM = 4
W_SECTOR = 3
SECTOR_MIN = 0.2  # pp of excess return over SPY before a sector counts as a tailwind
P_FUEL = -10
FUEL_USED = 1.2  # the day's range as a multiple of daily ATR
P_EVENT = -10
EVENT_MIN = 30
P_EARN_AMC = -5
P_FAILED = -15

# ---- the regime's thresholds --------------------------------------------------
VIX_GRIND = 13.0
VIX_NORMAL = 20.0
VIX_STRESSED = 28.0
SPY_FLAT = 0.15  # % — below this SPY has not moved
VIX_FLAT = 1.5  # % — below this VIX has not moved
EVENT_HORIZON_MIN = 6 * 60
EVENT_RECENT_MIN = 15

NEWS_MAX = 8
NEWS_DAYS = 3
FILINGS_MAX = 5


def _q(quotes: list[dict[str, Any]], key: str) -> dict[str, Any] | None:
    return next((q for q in quotes if q.get("key") == key), None)


def _sign(x: float | None, flat: float) -> int:
    if x is None or abs(x) < flat:
        return 0
    return 1 if x > 0 else -1


def _move(row: dict[str, Any] | None, session: str) -> float | None:
    """The move that says which way a benchmark is going NOW: the pre-market gap
    before the bell (and overnight), the regular session's change after it."""
    if row is None:
        return None
    if session in ("pre", "closed") and row.get("ext_pct") is not None:
        return float(row["ext_pct"])
    v = row.get("chg_pct")
    return float(v) if v is not None else None


def _tape(row: dict[str, Any] | None, sym: str) -> dict[str, Any] | None:
    if row is None or not row.get("ok"):
        return None
    return {"sym": sym, "last": row.get("last"), "chg_pct": row.get("chg_pct"),
            "ext_pct": row.get("ext_pct"), "trend": row.get("trend", 0),
            "lvl_state": row.get("lvl_state", 0)}


def next_event(calendar: list[dict[str, Any]], now: datetime) -> dict[str, Any] | None:
    """The next US release worth stopping for (score ≥ 4), or one that printed in
    the last quarter hour. Pure."""
    now_ts = now.timestamp()
    best: dict[str, Any] | None = None
    for r in calendar:
        if r.get("region") != "us" or (r.get("score") or 0) < 4 or r.get("ts") is None:
            continue
        in_min = (float(r["ts"]) - now_ts) / 60.0
        if in_min < -EVENT_RECENT_MIN or in_min > EVENT_HORIZON_MIN:
            continue
        if best is None or in_min < best["in_min"]:
            best = {"title": r.get("event") or "", "et": r.get("et") or "",
                    "in_min": round(in_min, 1), "score": r.get("score") or 0}
    return best


def regime(quotes: list[dict[str, Any]], tape_rows: dict[str, dict[str, Any] | None],
           calendar: list[dict[str, Any]], session: str, now: datetime) -> dict[str, Any]:
    """VIX, its band, the tape and the bias — the context every row is scored in. Pure."""
    vq, vvq = _q(quotes, "VIX"), _q(quotes, "VVIX")
    vt = volterm_state(quotes)
    vix_last = vq.get("last") if vq else None
    vix_pct = vq.get("pct") if vq else None
    shape = vt.get("shape") or "unknown"

    band: str | None = None
    if vix_last is not None:
        if shape == "backwardation" or vix_last >= VIX_STRESSED:
            band = "stressed"
        elif vix_last < VIX_GRIND:
            band = "grind"
        elif vix_last < VIX_NORMAL:
            band = "normal"
        else:
            band = "elevated"
    em = vix_last / math.sqrt(252.0) if vix_last is not None else None

    spy, qqq = tape_rows.get("SPY"), tape_rows.get("QQQ")
    spy_dir = _sign(_move(spy, session), SPY_FLAT)
    vix_dir = _sign(vix_pct, VIX_FLAT)

    # THE BIAS: the two index ETFs' own level state (the strategy's own read of
    # them), or their move while both are still inside their levels, plus VIX's
    # direction against them. Two votes the same way is a lean; anything less is
    # no lean, because a scanner that always has a bias is a scanner that is
    # usually guessing.
    votes = 0
    states = [r.get("lvl_state", 0) if r else 0 for r in (spy, qqq)]
    if any(states):
        votes += sum(_sign(float(s), 0.5) for s in states)
    else:
        votes += sum(_sign(_move(r, session), SPY_FLAT) for r in (spy, qqq))
    votes -= vix_dir
    bias = "long" if votes >= 2 else "short" if votes <= -2 else None

    confirm: str | None = None
    if spy_dir == 1 and vix_dir == -1:
        confirm = "confirm"
    elif spy_dir == 1 and vix_dir == 1:
        confirm = "divergence"
    elif spy_dir == -1 and vix_dir == 1:
        confirm = "risk_off"
    elif spy_dir == 0 and vix_dir == 0 and spy is not None and vix_pct is not None:
        confirm = "chop"

    event = next_event(calendar, now)
    notes: list[str] = []
    if vix_last is not None:
        v = f"VIX {vix_last:.1f}"
        notes.append({
            "grind": f"{v} is in the grind band (under {VIX_GRIND:.0f}): tight ranges and "
                     "breakouts that fail back into rotation — size down or take scalps.",
            "normal": f"{v} is in the normal band: structured break-and-retest trades with "
                      "normal stops.",
            "elevated": f"{v} is elevated: wider ranges and noise — widen stops, take partials "
                        "earlier, and don't fade strength.",
            "stressed": f"{v} with the curve "
                        f"{'in backwardation' if shape == 'backwardation' else 'stressed'}: "
                        "levels hold less in this tape — cut size hard.",
        }[band or "normal"])
    if em is not None and spy and spy.get("last"):
        pts = em / 100.0 * float(spy["last"])
        notes.append(f"SPY's implied one-day move is ±{em:.2f}% (±{pts:.2f}).")
    if confirm == "confirm":
        notes.append("SPY up, VIX down — a healthy trend; continuation setups are favoured.")
    elif confirm == "divergence":
        notes.append("SPY up but VIX up too — hedging demand under the rally; be quicker to "
                     "take profits on longs.")
    elif confirm == "risk_off":
        notes.append("SPY down, VIX up — risk-off; shorts on weak names are favoured, don't "
                     "catch the knife.")
    elif confirm == "chop":
        notes.append("SPY and VIX both flat — expect rotation; levels are more likely to be "
                     "faded than broken.")
    if event is not None:
        if event["in_min"] >= 0:
            notes.append(f"{event['title']} at {event['et']} ET, in "
                         f"{_dur(event['in_min'])} — let it print before taking a level.")
        else:
            notes.append(f"{event['title']} printed {abs(round(event['in_min']))} min ago — "
                         "the first range after a print is noise.")

    return {
        "vix": {
            "last": vix_last, "pct": vix_pct, "chg": vq.get("chg") if vq else None,
            "ratio": vt.get("ratio"), "shape": shape,
            "vvix": vvq.get("last") if vvq else None, "vvix_pct": vvq.get("pct") if vvq else None,
        },
        "band": band,
        "spy_em_pct": round(em, 3) if em is not None else None,
        "tape": {k: _tape(tape_rows.get(k), k) for k in ("SPY", "QQQ", "IWM")},
        "bias": bias,
        "confirm": confirm,
        "event": event,
        "notes": notes,
    }


def _dur(m: float) -> str:
    m = max(0, round(m))
    if m < 60:
        return f"{m} min"
    h, mm = divmod(m, 60)
    return f"{h}h {mm:02d}m" if mm else f"{h}h"


# ------------------------------------------------------------------ the joins


def earnings_for(sym: str, rows: list[dict[str, Any]], trading_day: date) -> dict[str, Any] | None:
    """The report that matters to a session: last night's, today's, or the week's. Pure."""
    best: dict[str, Any] | None = None
    for r in rows:
        if (r.get("symbol") or "").upper() != sym:
            continue
        try:
            d = date.fromisoformat(str(r.get("date")))
        except ValueError:
            continue
        days = (d - trading_day).days
        if days < -1 or days > 5:
            continue
        if days == -1 and r.get("when") != "after":
            continue
        if best is None or abs(days) < abs(best["days"]):
            best = {"date": d.isoformat(), "when": r.get("when") or "unspecified", "days": days,
                    "eps_forecast": r.get("eps_forecast"), "eps_actual": r.get("eps_actual"),
                    "surprise_pct": r.get("surprise_pct")}
    return best


_RATING = re.compile(
    r"upgrad|downgrad|price target|\bPT\b|initiat|reiterat|overweight|underweight|"
    r"outperform|underperform|\bbuy rating|\bsell rating|neutral rating", re.I)
_EARN = re.compile(
    r"earnings|results|\bEPS\b|revenue|guidance|outlook|quarter|\bQ[1-4]\b|beats?\b|miss(es)?\b",
    re.I)
_FILING = re.compile(r"\b8-K\b|\b10-[QK]\b|SEC filing|files? for|offering|prospectus", re.I)


def news_kind(title: str) -> str:
    """rating | earnings | filing | news, from the headline alone. Pure."""
    if _RATING.search(title):
        return "rating"
    if _EARN.search(title):
        return "earnings"
    if _FILING.search(title):
        return "filing"
    return "news"


def _story(title: str) -> str:
    return re.sub(r"[^a-z0-9 ]", "", title.lower())[:80]


def news_for(sym: str, own: list[dict[str, Any]], wire: list[dict[str, Any]],
             aliases: list[str], now: datetime) -> list[dict[str, Any]]:
    """The ticker's own headlines plus any wire story that names it. Pure.

    THE WIRE MATCH IS STRICT ON PURPOSE: the cashtag, or a company name written
    as a proper noun on a word boundary. "Meta" in "metadata" or "Intel" in
    "intelligence" would put a macro tape's worth of noise under a stock.
    """
    now_ts = now.timestamp()
    cutoff = now_ts - NEWS_DAYS * 86400
    pats = [re.compile(rf"\${re.escape(sym)}\b")]
    pats += [re.compile(rf"\b{re.escape(a)}\b") for a in aliases if a]
    items: list[dict[str, Any]] = [dict(x) for x in own]
    for w in wire:
        title = w.get("title") or ""
        if any(p.search(title) for p in pats):
            items.append({"title": title, "url": w.get("url") or "",
                          "publisher": w.get("publisher") or "", "ts": w.get("ts"),
                          "utc": w.get("utc")})
    seen: set[str] = set()
    out: list[dict[str, Any]] = []
    for it in sorted(items, key=lambda x: -(x.get("ts") or 0)):
        ts = it.get("ts")
        if ts is not None and ts < cutoff:
            continue
        k = _story(it.get("title") or "")
        if not k or k in seen:
            continue
        seen.add(k)
        out.append({
            "title": it.get("title") or "",
            "url": it.get("url") or "",
            "publisher": it.get("publisher") or "",
            "utc": it.get("utc"),
            "age_min": round((now_ts - ts) / 60.0, 1) if ts is not None else None,
            "kind": it.get("kind") or news_kind(it.get("title") or ""),
        })
        if len(out) >= NEWS_MAX:
            break
    return out


# ----------------------------------------------------------------- the score


def _part(key: str, label: str, pts: float, mx: int, note: str) -> dict[str, Any]:
    # Whole points, so the breakdown on screen adds up to the total it sits under.
    return {"key": key, "label": label, "pts": round(pts), "max": mx, "note": note}


def score_row(row: dict[str, Any], reg: dict[str, Any], sector_rs: float | None,
              earnings: dict[str, Any] | None, event: dict[str, Any] | None,
              session: str = "rth") -> dict[str, Any]:
    """The contract's score: five parts and the penalties, every one listed. Pure."""
    setup = row.get("setup") or {}
    side = setup.get("side")
    state = setup.get("state") or "chop"
    parts: list[dict[str, Any]] = []
    d = 1 if side == "long" else -1 if side == "short" else 0

    # ---- structure ------------------------------------------------------------
    s = (row.get("lvl_state") or 0) * d
    if d and s in W_STRUCTURE:
        pts = W_STRUCTURE[s]
        note = ("outside both levels" if s == 2 else "outside one level (inside setup)")
    elif state == "approaching":
        pts, note = W_APPROACH, f"approaching {setup.get('level') or 'a level'}"
    else:
        pts, note = 0, "inside the levels" if d else "no side"
    parts.append(_part("structure", "Structure", pts, 30, note))

    # ---- relative strength ---------------------------------------------------
    rs = (row.get("rs") or {}).get("SPY")
    if d and rs is not None:
        frac = max(0.0, min(1.0, rs * d / RS_FULL))
        parts.append(_part("rs", "RS vs SPY", frac * W_RS, W_RS,
                           f"{rs:+.2f} ATR vs SPY"))
    else:
        parts.append(_part("rs", "RS vs SPY", 0, W_RS,
                           "no RS yet" if rs is None else "no side"))

    # ---- location ------------------------------------------------------------
    entry = setup.get("entry")
    loc_key = state
    if state == "extended":
        near = entry is not None and abs(entry.get("dist_atr") or 99) <= 1.0
        loc_key = "extended_near" if near else "extended_far"
    pts = W_LOCATION.get(loc_key, 0)
    note = {
        "retest": "at the broken level", "pullback": "between the level and extended",
        "extended_near": "extended — near VWAP / 8 EMA",
        "extended_far": "extended — far from entry",
        "approaching": "not broken yet", "forming": "pre-market plan", "failed": "failed break",
        "chop": "no entry",
    }.get(loc_key, loc_key)
    if setup.get("lost_vwap") and state != "forming":
        pts, note = 0, "wrong side of VWAP"
    if not d:
        pts, note = 0, "no side"
    parts.append(_part("location", "Location", pts, 20, note))

    # ---- volume --------------------------------------------------------------
    rvol = row.get("rvol")
    pts = 0
    if rvol is not None:
        for floor, p in W_VOLUME:
            if rvol >= floor:
                pts = p
                break
    if rvol is not None:
        vnote = f"RVOL {rvol:.2f}"
    elif session in ("pre", "closed"):
        vnote = "RVOL starts at the open — Yahoo's pre-market bars carry no volume"
    else:
        vnote = "no RVOL yet"
    parts.append(_part("volume", "Relative volume", pts, 10, vnote))

    # ---- market --------------------------------------------------------------
    pts, bits = 0, []
    if d and reg.get("bias") == side:
        pts += W_BIAS
        bits.append("tape agrees")
    conf = reg.get("confirm")
    if (side == "long" and conf == "confirm") or (side == "short" and conf == "risk_off"):
        pts += W_CONFIRM
        bits.append("VIX confirms")
    if d and sector_rs is not None and abs(sector_rs) >= SECTOR_MIN and sector_rs * d > 0:
        pts += W_SECTOR
        bits.append("sector tailwind")
    parts.append(_part("market", "Market", pts, 15, ", ".join(bits) or "no tailwind"))

    # ---- penalties -----------------------------------------------------------
    ru = row.get("range_used")
    if ru is not None and ru >= FUEL_USED:
        parts.append(_part("fuel", "Range used", P_FUEL, 0, f"{ru:.1f}× daily ATR used"))
    if event is not None and 0 <= event["in_min"] <= EVENT_MIN:
        parts.append(_part("event", "Event", P_EVENT, 0,
                           f"{event['title']} in {round(event['in_min'])} min"))
    if earnings is not None and earnings["days"] == 0 and earnings["when"] == "after":
        parts.append(_part("earnings", "Earnings", P_EARN_AMC, 0, "reports after the close"))
    if state == "failed":
        parts.append(_part("failed", "Failed break", P_FAILED, 0,
                           f"{setup.get('level') or 'level'} broke and failed"))

    total = max(0, min(100, sum(p["pts"] for p in parts)))
    return {"total": total, "side": side, "parts": parts}


def flags_for(row: dict[str, Any], earnings: dict[str, Any] | None,
              event: dict[str, Any] | None, news: list[dict[str, Any]],
              filings: list[dict[str, Any]], session: str) -> list[dict[str, Any]]:
    """The few things a reader must see before taking the trade. Pure."""
    out: list[dict[str, Any]] = []

    def add(kind: str, tone: str, text: str) -> None:
        out.append({"kind": kind, "tone": tone, "text": text})

    if earnings is not None:
        days, when = earnings["days"], earnings["when"]
        sp = earnings.get("surprise_pct")
        tail = f" ({sp:+.1f}% surprise)" if isinstance(sp, (int, float)) else ""
        if days == -1:
            add("earnings", "good", f"Reported after yesterday's close — in play{tail}")
        elif days == 0 and when == "pre":
            add("earnings", "good", f"Reported this morning — in play{tail}")
        elif days == 0 and when == "after":
            add("earnings", "warn", "Reports after the close today — holding risk")
        elif days == 0:
            add("earnings", "info", "Reports today (time unconfirmed)")
        else:
            wd = date.fromisoformat(earnings["date"]).strftime("%a")
            tag = {"pre": " before the open", "after": " after the close"}.get(when, "")
            add("earnings", "info", f"Reports {wd}{tag}")
    if event is not None and 0 <= event["in_min"] <= EVENT_MIN:
        add("event", "warn", f"{event['title']} in {round(event['in_min'])} min")
    for f in filings[:2]:
        form = f.get("form") or ""
        offering = form.startswith(("S-1", "S-3", "424B", "F-1", "F-3"))
        add("filing", "warn" if offering else "info",
            f"{'Offering filed' if offering else form}: {f.get('desc') or form}")
    fresh = [n for n in news if n.get("age_min") is not None and n["age_min"] <= 24 * 60]
    rating = next((n for n in fresh if n.get("kind") == "rating"), None)
    if rating is not None:
        add("news", "info", f"Analyst: {rating['title'][:90]}")
    elif fresh:
        add("news", "info", f"{len(fresh)} headline{'s' if len(fresh) != 1 else ''} in 24h")
    setup = row.get("setup") or {}
    if setup.get("state") == "extended":
        e = setup.get("entry")
        if e is not None:
            what = "the 8 EMA" if e["kind"] == "EMA8" else e["kind"]
            add("extended", "warn",
                f"Extended — wait for {what} ({abs(e.get('dist_atr') or 0):.1f} ATR away)")
        else:
            add("extended", "warn", "Extended — no VWAP or 8 EMA to lean on")
    ru = row.get("range_used")
    if ru is not None and ru >= FUEL_USED:
        add("fuel", "warn", f"{ru:.1f}× daily ATR already used — fuel spent")
    ext = row.get("ext_pct")
    if session in ("pre", "closed") and ext is not None and abs(ext) >= 2.0:
        add("gap", "info", f"Gapping {ext:+.1f}%")
    return out


# ------------------------------------------------------------------- payload


def build(scan: dict[str, Any], *, quotes: list[dict[str, Any]],
          sectors: list[dict[str, Any]], calendar: list[dict[str, Any]],
          earnings: list[dict[str, Any]], wire: list[dict[str, Any]],
          news: dict[str, list[dict[str, Any]]], filings: dict[str, list[dict[str, Any]]],
          aliases: dict[str, list[str]], status: dict[str, Any] | None,
          watchlist: list[str], clock: Clock, now: datetime | None = None) -> dict[str, Any]:
    """The /api/scanner payload (contract ScannerPayload). Pure.

    THE SESSION IS THE CLOCK'S, read now — not whatever the last job tick
    stored. Before the first tick there is no stored block at all, and a payload
    that said "closed" at 07:00 because no bars had landed yet was wrong about
    the one thing that needs no data.
    """
    now = now or datetime.now(UTC)
    rows_in: dict[str, dict[str, Any]] = scan.get("rows") or {}
    fetched: dict[str, float] = scan.get("fetched") or {}
    session = clock.session
    td = clock.trading_day

    reg = regime(quotes, {k: rows_in.get(k) for k in ("SPY", "QQQ", "IWM")}, calendar,
                 session, now)
    event = reg["event"]
    sector_rs = {s.get("key"): s.get("rs_day") for s in sectors}

    now_ts = now.timestamp()
    out_rows: list[dict[str, Any]] = []
    for sym in watchlist:
        base = rows_in.get(sym)
        age = round((now_ts - fetched[sym]) / 60.0, 2) if sym in fetched else None
        if base is None:
            out_rows.append(_empty(sym, age, "waiting for the first fetch"))
            continue
        row = {k: v for k, v in base.items() if k not in ("pdh_day", "sector")}
        row["age_min"] = age
        sector = base.get("sector")
        srs = sector_rs.get(sector) if sector else None
        row["sector"] = sector
        row["sector_rs"] = round(srs, 3) if isinstance(srs, (int, float)) else None
        earn = earnings_for(sym, earnings, td)
        nws = news_for(sym, news.get(sym) or [], wire, aliases.get(sym) or [], now)
        fil = [f for f in (filings.get(sym) or [])][:FILINGS_MAX]
        row["earnings"] = earn
        row["news"] = nws
        row["filings"] = fil
        if row.get("ok"):
            row["score"] = score_row(row, reg, srs, earn, event, session)
            row["flags"] = flags_for(row, earn, event, nws, fil, session)
        else:
            row["score"] = {"total": 0, "side": None, "parts": []}
            row["flags"] = []
        if isinstance(row.get("setup"), dict):
            row["setup"] = {k: v for k, v in row["setup"].items() if k != "lost_vwap"}
        out_rows.append(row)

    out_rows.sort(key=lambda r: (not r.get("ok"), -(r.get("score") or {}).get("total", 0)))
    ages = [r["age_min"] for r in out_rows if r.get("age_min") is not None]
    return {
        "ok": any(r.get("ok") for r in out_rows),
        "built_utc": now.astimezone(UTC).isoformat(),
        "status": status,
        "age_min": max(ages) if ages else None,
        "session": session,
        "trading_day": td.isoformat(),
        "pm_locked": clock.pm_locked,
        "bench": "SPY",
        "watchlist": watchlist,
        "regime": reg,
        "rows": out_rows,
    }


def _empty(sym: str, age: float | None, why: str) -> dict[str, Any]:
    return {
        "sym": sym, "name": None, "sector": None, "sector_rs": None, "ok": False, "error": why,
        "age_min": age, "last": None, "prev_close": None, "chg_pct": None, "ext_pct": None,
        "volume": None, "rvol": None, "atr_d": None, "atr_b": None,
        "rs": {"SPY": None, "QQQ": None}, "rs_1h": {"SPY": None, "QQQ": None},
        "levels": {"pdh": None, "pdl": None, "pdc": None, "pmh": None, "pml": None,
                   "pm_done": False, "vwap": None, "wave_hi": None, "wave_lo": None,
                   "ema8": None, "day_hi": None, "day_lo": None, "open": None},
        "progress": {"pdh": None, "pdl": None, "pmh": None, "pml": None},
        "broken": {"pdh": False, "pdl": False, "pmh": False, "pml": False},
        "lvl_state": 0, "trend": 0, "range_used": None,
        "setup": {"side": None, "state": "chop", "level": None, "entry": None, "note": why},
        "signals": [], "score": {"total": 0, "side": None, "parts": []}, "flags": [],
        "earnings": None, "news": [], "filings": [],
    }
