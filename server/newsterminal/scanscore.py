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

from . import frame, marketctx, optcalc, releases, targets
from .holidays import next_trading_day
from .scan import Clock
from .sources.shortint import squeeze_flag
from .volterm import state as volterm_state
from .volterm import vix_month

#: Names whose own news feed is never read (the wire covers the index ETFs).
_NO_OWN_NEWS = frozenset({"SPY", "QQQ", "IWM"})

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

# ---- in play: the volume part's stand-in before the bell ----------------------
# BEFORE 09:30 RVOL DOES NOT EXIST (Yahoo's pre-market bars carry no volume), so
# the ten volume points were zero for every name and the pre-open rank was RS
# alone: at 05:22 ET on 2026-10-14 DELL led on RS with nothing broken, while MU
# — down on ASML's miss, 1.07% of its average day already traded — sat eighth.
# EllyD picks "what's moving pre-market" (owner, 2026-10-14: "do what you
# recommend"), so until the open the part is IN PLAY: how far the name has
# gapped in its own daily ATRs, how much of an average day has traded before
# the bell (Nasdaq's read, sources/premarket.py), and whether there is a fresh
# reason. 22 points, because the pre-open location part tops out at 8
# ("forming"), so structure 30 + RS 25 + location 8 + in play 22 + market 15 is
# the same 100 the session's parts add to.
#
# Worked examples, the live payload at 06:02 ET on 2026-10-14 (the part is
# rounded once, as a whole):
#   DELL  gap |556.48 − 572.47| / ATR 26.66 = 0.60 → 8 × (0.60 − 0.10) / 0.65 = 6.15
#         pre-market 1.07% of ADV → 8 × ln(1.07 / 0.25) / ln(16)            = 4.20
#         2 headlines since the close                                       = 1
#                                                               in play 11.35 → 11
#   SNDK  gap 0.40 ATR → 3.73 · 1.95% of ADV → 5.93 · 2 headlines → 1     → 11
#   MU    gap 0.28 ATR → 2.21 · 1.25% of ADV → 4.64 · 8 headlines → 2     → 9
#   GME   gap 0.54 ATR → 5.39 · 0.61% of ADV → 2.57 · 4 headlines → 2     → 10
#   NVDA  gap 0.10 ATR → 0    · 0.48% of ADV → 1.88 · 2 headlines → 1     → 3
# Against the RS-only rank those moved DELL 30 → 41, SNDK 25 → 36, MU 22 → 31
# and NVDA 26 → 29. A name that reported after yesterday's close, gapping
# three-quarters of an ATR on 4% of its day, earns all 22.
W_GAP = 8
GAP_MIN = 0.10  # daily ATRs — below this the "gap" is the overnight drift
GAP_FULL = 0.75  # daily ATRs for the whole gap part
W_PMVOL = 8
PMVOL_MIN = 0.25  # % of ADV — nothing below it (Nasdaq's quiet names sit at 0.1–0.3)
PMVOL_FULL = 4.0  # % of ADV for the whole part; log-scaled between the two
W_CATALYST = 6
CATALYST_FRESH_MIN = 16 * 60  # a headline since yesterday's close (16:00 → 08:00)
# THE CATALYST IS ITS OWN PART NOW, ALL SESSION (owner, 2026-10-23: "i want
# the rankings to be as high probability as possible"). It used to be a count
# of fresh headlines inside the pre-open "in play" part; it now reads the
# DIRECTION of four things against the side — a report's surprise sign, a
# rating or target change, guidance raised or cut, an offering or a material
# 8-K — and earns with the side, costs against it, and ignores a story that
# only describes the price move. A prior, not a finding: logged on every
# signal so tools/fit_score.py can keep it or throw it out.
P_CATALYST = -6
W_INPLAY = W_GAP + W_PMVOL
# THE CLOCK AND THE TAPE, FROM THE RECORD (453 settled signals to 2026-10-21):
# (L)/(E) signals in the first thirty minutes reached +1R 36% of the time and
# in the last hour 37%, against 50–60% in between; longs on a short tape 41%
# against shorts 58%. Both are penalties: they never push a name up.
P_CLOCK = -10
CLOCK_OPEN_MIN = 30
CLOCK_CLOSE_MIN = 60
RECORD_OPEN_WIN = 36
RECORD_CLOSE_WIN = 37
P_TAPE = -10
TAPE_GRADES = ("moderate", "strong")
#: The record line needs this many settled signals before it says a rate.
RECORD_MIN = 10
RECORD_SOLID = 30
#: The daily frame (frame.py): the whole part with the daily trend, half of
#: it between the averages, nothing against it — and a flag when against.
W_FRAME = 6
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
# MIRRORED IN src/lib/vix.ts — the VIX card's click-through draws the same four
# bands from its own copy of these three numbers. Change both or the card's
# band word and its table disagree.
VIX_GRIND = 13.0
VIX_NORMAL = 20.0
VIX_STRESSED = 28.0
# TWO SUB-LINES INSIDE THE BANDS (owner, 2026-10-23: "i hear people talking
# specifically about being over 18"). The bands above score and stay; these
# only change the words. 18 is the VIX's long-run median (about 17.6 since
# 1990): over it the market pays more than usual for protection, the implied
# S&P day crosses ±1.1% and the gamma flip tends to sit near spot. 35 is
# panic: the VIX's own mean reversion becomes the trade, not the level.
VIX_MEDIAN = 18.0
VIX_PANIC = 35.0


def vix_sub(last: float | None, band: str | None) -> str | None:
    """quiet / heavy inside the normal band, panic inside stressed, else None. Pure."""
    if last is None or band is None:
        return None
    if band == "normal":
        return "heavy" if last >= VIX_MEDIAN else "quiet"
    if band == "stressed" and last >= VIX_PANIC:
        return "panic"
    return None
SPY_FLAT = 0.15  # % — below this SPY has not moved
VIX_FLAT = 1.5  # % — below this VIX has not moved
EVENT_HORIZON_MIN = 6 * 60
EVENT_RECENT_MIN = 15

NEWS_MAX = 8
#: Average daily volume: the last ADV_SESSIONS completed sessions; a listing
#: younger than ADV_MIN sessions has none.
ADV_SESSIONS = 20
ADV_MIN = 10
#: Sector peers' reports, from the trading day through this many trading days on.
PEER_DAYS = 3
PEERS_MAX = 6
#: Share classes of one company — never each other's peer.
_TWINS = {"GOOG": "GOOGL", "GOOGL": "GOOG", "BRK.B": "BRK-B", "BRK-B": "BRK.B"}
_WHEN_ORDER = {"pre": 0, "unspecified": 1, "after": 2}
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
    near: list[dict[str, Any]] = []
    for r in calendar:
        if r.get("region") != "us" or (r.get("score") or 0) < 4 or r.get("ts") is None:
            continue
        in_min = (float(r["ts"]) - now_ts) / 60.0
        if in_min < -EVENT_RECENT_MIN or in_min > EVENT_HORIZON_MIN:
            continue
        near.append(r)
    if not near:
        return None
    # BY RELEASE (releases.py): 08:30 on CPI day read "CPI, n.s.a" — one of the
    # release's seven rows, and the one nobody prices. The release's lead names it.
    rel = min(
        releases.group(near, event=lambda r: str(r.get("event") or ""), when=lambda r: r["ts"],
                       country=lambda r: r.get("country"), score=lambda r: int(r.get("score") or 0),
                       figures=lambda r: (r.get("actual_raw"), r.get("consensus_raw"),
                                          r.get("previous_raw"))),
        key=lambda g: float(g.lead["ts"]),
    )
    r = rel.lead
    return {"title": r.get("event") or "", "et": r.get("et") or "",
            "in_min": round((float(r["ts"]) - now_ts) / 60.0, 1), "score": r.get("score") or 0}


def regime(quotes: list[dict[str, Any]], tape_rows: dict[str, dict[str, Any] | None],
           calendar: list[dict[str, Any]], session: str, now: datetime,
           context: list[dict[str, Any]] | None = None) -> dict[str, Any]:
    """VIX, its band, the tape and the bias — the context every row is scored in. Pure.
    `context` is the daily-close block, for the VIX against its own month."""
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
    sub = vix_sub(vix_last, band)
    month = vix_month(context or [], quotes)
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
        # Mean reversion under the median, trend over it (owner, 2026-10-23):
        # the words the VIX table (lib/vix) gives the same rows — its tape
        # column, then after the dash its trade column, written for the desk's
        # own break-and-retest. Change one side and change the other.
        normal = (f"{v} is in the normal band, over the median of {VIX_MEDIAN:.0f}: moves carry, "
                  "breaks run to the next level and trends hold into the close, 1%-plus days "
                  "are normal — the best tape for break-and-retest: full size, stops one notch "
                  "wider, let winners reach target."
                  if sub == "heavy" else
                  f"{v} is in the normal band, under the median of {VIX_MEDIAN:.0f}: moves fade "
                  "inside the day, a break usually comes back to retest and the retest usually "
                  "holds — break-and-retest at normal size and normal stops; wait for the "
                  "retest, don't buy the first push.")
        stressed = (f"{v} is in panic territory ({VIX_PANIC:.0f} and up): two to three percent "
                    "a day and retests rarely hold — don't trade stock levels; the trade is the "
                    "VIX itself coming back down once the curve flattens."
                    if sub == "panic" else
                    f"{v} with the curve "
                    f"{'in backwardation' if shape == 'backwardation' else 'stressed'}: "
                    "big ranges both ways, every stock trades as the index and stops get hit "
                    "by noise — cut size hard or sit out; rallies are short-covering until the "
                    "curve flattens.")
        notes.append({
            "grind": f"{v} is in the grind band (under {VIX_GRIND:.0f}): small ranges, breakouts "
                     "stall and fall back inside the range — fade the edges or take scalps, "
                     "half size, don't chase a break.",
            "normal": normal,
            "elevated": f"{v} is elevated: big moves that extend then whip back, stocks move with "
                        "the index not their own story — trade with the index direction only, "
                        "wider stops, partials early, smaller size, don't fade strength.",
            "stressed": stressed,
        }[band or "normal"])
        if month is not None:
            notes.append(f"Against its own month {v} sits at the {month['pctile']}th percentile "
                         f"({month['lo']:.1f}–{month['hi']:.1f}).")
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
            # The VIX against its own month (volterm.vix_month): the other
            # granularity — an 18 after a week at 13 is not an 18 after a week at 25.
            "month": month,
        },
        "band": band,
        # quiet / heavy inside normal, panic inside stressed — words, never score.
        "sub": sub,
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


def adv20(volumes: list[float]) -> float | None:
    """Average daily volume over the last ADV_SESSIONS completed sessions. Pure.

    `volumes` are the daily bars' volumes BEFORE the trading day, oldest first —
    today's part-session bar would drag the average down all morning. A zero
    (a bar Yahoo never filled) is skipped, not averaged in. Fewer than ADV_MIN
    sessions — a fresh listing — is None, not a guess.
    """
    vs = [v for v in volumes if isinstance(v, (int, float)) and v > 0][-ADV_SESSIONS:]
    if len(vs) < ADV_MIN:
        return None
    return float(round(sum(vs) / len(vs)))


def premkt_for(read: dict[str, Any] | None, adv: float | None) -> dict[str, Any] | None:
    """The row's `premkt` from today's Nasdaq read (sources/premarket.py). Pure.

    `pct_adv` is pre-market share volume as a percentage of the twenty-session
    average day — 5% before the bell is a name in play; 0.3% is not.
    """
    if not read:
        return None
    vol = read.get("volume")
    pct = (round(vol / adv * 100.0, 2)
           if isinstance(vol, (int, float)) and isinstance(adv, (int, float)) and adv > 0
           else None)
    return {"volume": vol, "pct_adv": pct, "high": read.get("high"), "low": read.get("low"),
            "last": read.get("last"), "asof": read.get("asof")}


def peers_for(sym: str, sector: str | None, earnings: list[dict[str, Any]],
              trading_day: date, sector_map: dict[str, str]) -> list[dict[str, Any]]:
    """Big caps in the row's sector reporting from the trading day through
    PEER_DAYS trading days on, soonest first. Pure.

    The earnings rows are the calendar's: a big cap (the panel's $50B floor, or a
    bellwether) or one of the watchlist's own names, tagged `watch_only`. Only
    the big caps count — a small name on the watchlist moves on its own report,
    not its sector's — and never the name itself or its other share class. The
    sector is the scanner's static table (sources/scanner.SECTOR) applied to the
    reporter's ticker; a reporter the table does not know is nobody's peer. The
    calendar reads four days ahead, so on a Thursday or Friday the third
    trading day can fall past what it holds.
    """
    if not sector:
        return []
    until = trading_day
    for _ in range(PEER_DAYS):
        until = next_trading_day(until)
    me = {sym, _TWINS.get(sym, sym)}
    found: dict[str, tuple[tuple[Any, ...], dict[str, Any]]] = {}
    for r in earnings:
        s = str(r.get("symbol") or "").upper()
        if not s or s in me or r.get("watch_only") or sector_map.get(s) != sector:
            continue
        try:
            d = date.fromisoformat(str(r.get("date")))
        except ValueError:
            continue
        if d < trading_day or d > until:
            continue
        when = str(r.get("when") or "unspecified")
        cap = r.get("market_cap")
        key = (d, _WHEN_ORDER.get(when, 1), not r.get("bellwether"),
               -(cap if isinstance(cap, (int, float)) else 0.0), s)
        if s not in found or key < found[s][0]:
            found[s] = (key, {"sym": s, "date": d.isoformat(), "when": when,
                              "days": (d - trading_day).days})
    return [p for _, p in sorted(found.values(), key=lambda kv: kv[0])][:PEERS_MAX]


def peer_flag(peers: list[dict[str, Any]], trading_day: date) -> dict[str, Any] | None:
    """ "Peer TSM reports Thu" — the soonest peer, and how many more. Pure."""
    if not peers:
        return None
    p = peers[0]
    d = date.fromisoformat(p["date"])
    day = ("today" if d == trading_day else "tomorrow" if (d - trading_day).days == 1
           else d.strftime("%a"))
    more = f" +{len(peers) - 1}" if len(peers) > 1 else ""
    return {"kind": "earnings", "tone": "info", "text": f"Peer {p['sym']} reports {day}{more}"}


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


def in_play(row: dict[str, Any], premkt: dict[str, Any] | None) -> tuple[float, str]:
    """Before the bell: the gap and the pre-market volume → (points, note).
    Side-blind on purpose — a name is in play whichever way it gapped, and the
    side is RS's call. The catalyst is its own part (catalyst_read). Pure."""
    bits: list[str] = []
    pts = 0.0

    # The gap in the name's own daily ATRs: the pre-market (or after-hours) last
    # against the previous close — the same move RS sets against SPY's.
    last, atr = row.get("last"), row.get("atr_d")
    pdc = (row.get("levels") or {}).get("pdc")
    if isinstance(last, (int, float)) and isinstance(pdc, (int, float)) \
            and isinstance(atr, (int, float)) and atr > 0:
        gap = abs(last - pdc) / atr
        pts += W_GAP * max(0.0, min(1.0, (gap - GAP_MIN) / (GAP_FULL - GAP_MIN)))
        bits.append(f"gap {gap:.2f} ATR")
    else:
        bits.append("no gap read")

    pct = (premkt or {}).get("pct_adv")
    if isinstance(pct, (int, float)):
        if pct > PMVOL_MIN:
            frac = math.log(pct / PMVOL_MIN) / math.log(PMVOL_FULL / PMVOL_MIN)
            pts += W_PMVOL * min(1.0, frac)
        bits.append(f"pre-market {pct:.2f}% of ADV")
    else:
        bits.append("no pre-market volume yet")
    return pts, " · ".join(bits)


# ---- the catalyst, read for direction ---------------------------------------
#
# FOUR THINGS CARRY DIRECTION; A PRICE-MOVE STORY DOES NOT. A title can say
# "upgraded" and "misses" at once — those are skipped as ambiguous rather than
# netted. The kinds the headline classifier assigns (news_kind) were never
# trusted as catalysts (13 of 31 names on 2026-10-14 were "rating" on
# reiterations); these patterns are narrower and name the action.
_BULL = re.compile(
    r"upgrad|rais\w* (?:its |the |their )?(?:price )?target|"
    r"lift\w* (?:its |the )?(?:price )?target|"
    r"initiat\w*[^.]{0,40}\b(?:buy|outperform|overweight)\b|reiterat\w*[^.]{0,20}\bbuy\b|"
    r"rais\w* (?:full[- ]year |fy ?\d* |annual |its |the )?(?:guidance|outlook|forecast)|"
    r"hik\w* (?:its |the )?(?:guidance|outlook|forecast)|\bbeats?\b|"
    r"\btops? (?:estimates|expectations)",
    re.I)
_BEAR = re.compile(
    r"downgrad|cut\w* (?:its |the |their )?(?:price )?target|"
    r"lower\w* (?:its |the )?(?:price )?target|"
    r"trim\w* (?:its |the )?(?:price )?target|"
    r"initiat\w*[^.]{0,40}\b(?:sell|underperform|underweight)\b|"
    r"cut\w* (?:full[- ]year |fy ?\d* |annual |its |the )?(?:guidance|outlook|forecast)|"
    r"lower\w* (?:its |the )?(?:guidance|outlook|forecast)|slash\w* (?:guidance|outlook|forecast)|"
    r"withdraw\w* (?:its )?guidance|\bmiss(?:es|ed)?\b|\bfalls? short\b|"
    r"\b(?:secondary|stock|share) offering|\bprobe\b|investigat|\brecall\b|lawsuit",
    re.I)
_OFFERING_FORMS = ("S-1", "S-3", "424B", "F-1", "F-3")


def headline_direction(title: str) -> str | None:
    """"bull", "bear", or None — the four catalyst kinds, by what the title says
    was done, never by the price move it describes. Both ways at once is None."""
    bull, bear = bool(_BULL.search(title)), bool(_BEAR.search(title))
    if bull == bear:
        return None
    return "bull" if bull else "bear"


def catalyst_read(side: str | None, earnings: dict[str, Any] | None,
                  news: list[dict[str, Any]] | None,
                  filings: list[dict[str, Any]] | None) -> dict[str, Any]:
    """The catalyst part: {pts, note, against} — points with the side (up to
    W_CATALYST), P_CATALYST against it with the item quoted in `against`, zero
    with no directional item. Pure.

    Items: a report since the close with its surprise sign (W_CATALYST); a
    rating, target or guidance headline since the close (W_CATALYST); a beat or
    miss headline (W_CATALYST); an offering filed in the last three days (3,
    bear); a bankruptcy 8-K (W_CATALYST, bear). The strongest item each way
    decides; against wins a tie, because the downside of ranking a name into
    its own bad news is the larger one.
    """
    items: list[tuple[str, int, str]] = []  # (direction, weight, text)
    days, when = (earnings or {}).get("days"), (earnings or {}).get("when")
    sp = (earnings or {}).get("surprise_pct")
    if earnings and (days == -1 or (days == 0 and when == "pre")):
        when_txt = "after the close" if days == -1 else "this morning"
        if isinstance(sp, (int, float)) and sp != 0:
            items.append(("bull" if sp > 0 else "bear", W_CATALYST,
                          f"reported {when_txt}, EPS {sp:+.1f}% vs estimate"))
    fresh = [h for h in news or []
             if isinstance(h, dict) and h.get("age_min") is not None
             and h["age_min"] <= CATALYST_FRESH_MIN]
    for h in fresh:
        d = headline_direction(str(h.get("title") or ""))
        if d is None:
            continue
        pub = str(h.get("publisher") or "").strip()
        age = h.get("age_min")
        age_txt = f"{round(age / 60)}h" if isinstance(age, (int, float)) and age >= 60 else (
            f"{round(age)}m" if isinstance(age, (int, float)) else "")
        text = f"{pub + ': ' if pub else ''}\"{str(h.get('title') or '').strip()[:90]}\""
        items.append((d, W_CATALYST, f"{text} ({age_txt})" if age_txt else text))
    for f in filings or []:
        form = str((f or {}).get("form") or "")
        desc = str((f or {}).get("desc") or form)
        if form.startswith(_OFFERING_FORMS):
            items.append(("bear", 3, f"offering filed: {desc[:60]}"))
        elif form.startswith("8-K") and "bankruptcy" in desc.lower():
            items.append(("bear", W_CATALYST, f"8-K: {desc[:60]}"))
    if side not in ("long", "short") or not items:
        n_fresh = len(fresh)
        why = ("no side" if side not in ("long", "short") else
               f"no directional catalyst · {n_fresh} headline{'s' if n_fresh != 1 else ''} "
               f"since the close" if n_fresh else "no directional catalyst · no headlines since "
               "the close")
        return {"pts": 0, "note": why, "against": None}
    mine = "bull" if side == "long" else "bear"
    with_items = sorted((it for it in items if it[0] == mine), key=lambda x: -x[1])
    against_items = sorted((it for it in items if it[0] != mine), key=lambda x: -x[1])
    best_with = with_items[0] if with_items else None
    best_against = against_items[0] if against_items else None
    if best_against and (best_with is None or best_against[1] >= best_with[1]):
        note = f"against the {side} · {best_against[2]}"
        if best_with:
            note += f" · with it: {best_with[2]}"
        return {"pts": P_CATALYST, "note": note, "against": best_against[2]}
    assert best_with is not None
    note = f"with the {side} · {best_with[2]}"
    if best_against:
        note += f" · against it: {best_against[2]}"
    return {"pts": min(best_with[1], W_CATALYST), "note": note, "against": None}


def _signal_minute(at_et: Any) -> int | None:
    m = re.match(r"^(\d{1,2}):(\d{2})", str(at_et or ""))
    return int(m.group(1)) * 60 + int(m.group(2)) if m else None


def latest_trade_signal(signals: list[dict[str, Any]] | None) -> dict[str, Any] | None:
    """The row's newest (L) or (E) today, or None. Pure."""
    for sg in reversed(signals or []):
        if isinstance(sg, dict) and sg.get("kind") in ("L", "E"):
            return sg
    return None


def clock_penalty(signals: list[dict[str, Any]] | None) -> tuple[int, str] | None:
    """P_CLOCK when the newest (L)/(E) fired in the first CLOCK_OPEN_MIN minutes
    or the last CLOCK_CLOSE_MIN of the regular session, with the record's rate
    in the note; None otherwise. Pure."""
    sg = latest_trade_signal(signals)
    if sg is None:
        return None
    m = _signal_minute(sg.get("at_et"))
    if m is None:
        return None
    label = f"({sg['kind']}) at {sg.get('at_et')}"
    if 9 * 60 + 30 <= m < 9 * 60 + 30 + CLOCK_OPEN_MIN:
        return P_CLOCK, (f"{label}, first {CLOCK_OPEN_MIN} minutes: {RECORD_OPEN_WIN}% of "
                         f"such signals reached +1R")
    if m >= 16 * 60 - CLOCK_CLOSE_MIN:
        return P_CLOCK, f"{label}, last hour: {RECORD_CLOSE_WIN}% of such signals reached +1R"
    return None


def tape_penalty(side: str | None, conviction: dict[str, Any] | None) -> tuple[int, str] | None:
    """P_TAPE for a setup against the tape count's moderate or strong lean. Pure."""
    if side not in ("long", "short") or not isinstance(conviction, dict):
        return None
    bias, grade = conviction.get("bias"), conviction.get("grade")
    if bias in ("long", "short") and bias != side and grade in TAPE_GRADES:
        return P_TAPE, (f"{side} against a {grade} {bias} tape, {conviction.get('agree')} of "
                        f"{conviction.get('total')} agree")
    return None


def score_band(total: int | float | None) -> str | None:
    """The record's bands: "<40", "40-59", "60+". Pure."""
    if total is None:
        return None
    return "60+" if total >= 60 else "40-59" if total >= 40 else "<40"


def record_for(row_kind: str | None, side: str | None, total: int | float | None,
               table: dict[str, dict[str, Any]] | None) -> dict[str, Any] | None:
    """The record line: settled signals of this kind, side and band (scanlog
    record_table), from RECORD_MIN of them, flagged small under RECORD_SOLID. Pure."""
    band = score_band(total)
    if not table or row_kind not in ("L", "E") or side not in ("long", "short") or band is None:
        return None
    r = table.get(f"{band}|{row_kind}|{side}")
    if not r or (r.get("n") or 0) < RECORD_MIN:
        return None
    return {"kind": row_kind, "side": side, "band": band, "n": r["n"], "win_1r": r.get("win_1r"),
            "avg_close_r": r.get("avg_close_r"), "sessions": r.get("sessions"),
            "small": r["n"] < RECORD_SOLID}


def implied_kind(row: dict[str, Any]) -> str | None:
    """The signal kind a row's setup implies: today's newest (L)/(E), else (L)
    for a retest or pullback and (E) for an extended name. Pure."""
    sg = latest_trade_signal(row.get("signals"))
    if sg is not None:
        return str(sg.get("kind"))
    state = (row.get("setup") or {}).get("state")
    return "L" if state in ("retest", "pullback") else "E" if state == "extended" else None


def score_row(row: dict[str, Any], reg: dict[str, Any], sector_rs: float | None,
              earnings: dict[str, Any] | None, event: dict[str, Any] | None,
              session: str = "rth", premkt: dict[str, Any] | None = None,
              news: list[dict[str, Any]] | None = None,
              frame_read: dict[str, Any] | None = None,
              catalyst: dict[str, Any] | None = None,
              conviction: dict[str, Any] | None = None) -> dict[str, Any]:
    """The contract's score: seven parts and the penalties, every one listed. Pure.

    Before the bell (and overnight) the volume part is IN PLAY instead — see
    W_INPLAY. From 09:30 it is RVOL exactly as before. The daily frame
    (W_FRAME) and the catalyst (W_CATALYST, catalyst_read) are the sixth and
    seventh; the clock and the tape (P_CLOCK, P_TAPE) are penalties from the
    record. The total is capped at 100 as before.
    """
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

    # ---- volume (in play before the bell) -----------------------------------
    rvol = row.get("rvol")
    if session in ("pre", "closed"):
        ip, inote = in_play(row, premkt)
        parts.append(_part("inplay", "In play", ip, W_INPLAY, inote))
    else:
        pts = 0
        if rvol is not None:
            for floor, p in W_VOLUME:
                if rvol >= floor:
                    pts = p
                    break
        vnote = f"RVOL {rvol:.2f}" if rvol is not None else "no RVOL yet"
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

    # ---- the daily frame -----------------------------------------------------
    ws = frame.with_side(frame_read, side)
    ftext = (frame_read or {}).get("text") or ""
    if ws == "with":
        pts, note = W_FRAME, f"with the daily trend — {ftext}"
    elif ws == "mixed":
        pts, note = W_FRAME // 2, f"between the averages — {ftext}"
    elif ws == "against":
        pts, note = 0, f"against the daily trend — {ftext}"
    else:
        pts, note = 0, "no daily frame yet" if d else "no side"
    parts.append(_part("frame", "Daily frame", pts, W_FRAME, note))

    # ---- the catalyst, for direction ------------------------------------------
    cat = catalyst if catalyst is not None else catalyst_read(side, earnings, news, None)
    cpts = cat.get("pts") or 0
    parts.append(_part("catalyst", "Catalyst", cpts, W_CATALYST if cpts >= 0 else 0,
                       str(cat.get("note") or "")))

    # ---- penalties -----------------------------------------------------------
    clk = clock_penalty(row.get("signals"))
    if clk is not None:
        parts.append(_part("clock", "Clock", clk[0], 0, clk[1]))
    tp = tape_penalty(side, conviction)
    if tp is not None:
        parts.append(_part("tape", "Tape", tp[0], 0, tp[1]))
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
              filings: list[dict[str, Any]], session: str,
              frame_read: dict[str, Any] | None = None,
              short: dict[str, Any] | None = None,
              catalyst: dict[str, Any] | None = None) -> list[dict[str, Any]]:
    """The few things a reader must see before taking the trade. Pure."""
    out: list[dict[str, Any]] = []

    def add(kind: str, tone: str, text: str) -> None:
        out.append({"kind": kind, "tone": tone, "text": text})

    if catalyst and catalyst.get("against"):
        add("catalyst", "warn", f"Against: {catalyst['against']}")

    side = (row.get("setup") or {}).get("side") or (row.get("score") or {}).get("side")
    if frame.with_side(frame_read, side) == "against" and frame_read:
        trend = "downtrend" if frame_read.get("trend") == "down" else "uptrend"
        add("frame", "warn", f"{'Long' if side == 'long' else 'Short'} into a daily {trend}: "
                             f"{frame_read.get('text')}")
    sq = squeeze_flag(short, side)
    if sq is not None:
        add(sq["kind"], sq["tone"], sq["text"])

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
          watchlist: list[str], clock: Clock, now: datetime | None = None,
          options: dict[str, tuple[optcalc.Chain, float]] | None = None,
          closes: dict[str, list[float]] | None = None,
          iv_hist: dict[str, list[float]] | None = None,
          premkt: dict[str, dict[str, Any]] | None = None,
          sector_map: dict[str, str] | None = None,
          daily: dict[str, list[Any]] | None = None,
          shorts: dict[str, dict[str, Any]] | None = None,
          earn_hist: dict[str, list[dict[str, Any]]] | None = None,
          earn_next: dict[str, dict[str, Any]] | None = None,
          flow_ctx: dict[str, dict[str, Any]] | None = None,
          context: list[dict[str, Any]] | None = None,
          constituents: dict[str, Any] | None = None,
          record: dict[str, dict[str, Any]] | None = None) -> dict[str, Any]:
    """The /api/scanner payload (contract ScannerPayload). Pure.

    `daily` is each name's daily bars (the realised earnings moves), `shorts`
    its short interest (sources/shortint), `earn_hist` its past report dates
    (sources/earnhist) and `flow_ctx` the previous session's open interest and
    the chain's volume history (sources/options.OiLog) — all optional.

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
                 session, now, context=context)
    # THE TAPE COUNT BEFORE THE SCORE (marketctx.conviction_for), on the
    # technical rows as they stand: the tape penalty reads it, and the Market
    # tab prints the same count. Its failure is a missing count, never a
    # missing payload.
    try:
        reg["conviction"] = marketctx.conviction_for(
            {"session": session, "trading_day": td.isoformat(),
             "rows": [r for r in rows_in.values() if isinstance(r, dict)]},
            quotes, sectors, constituents, now)
    except (ValueError, TypeError, KeyError, ZeroDivisionError):
        reg["conviction"] = None
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
        # The calendar's row for the name, else its next report as Nasdaq
        # lists it (a week further out than the calendar feed reaches), so the
        # options maths can price the report whenever the chain covers it.
        earn = earnings_for(sym, earnings, td) or next_report((earn_next or {}).get(sym), td)
        nws = news_for(sym, news.get(sym) or [], wire, aliases.get(sym) or [], now)
        fil = [f for f in (filings.get(sym) or [])][:FILINGS_MAX]
        row["earnings"] = earn
        row["news"] = nws
        # WHETHER the name's own feed has been read yet — not the same as having
        # headlines. After a restart the news job works through the list a few
        # names a minute, and "no headlines" from a name not yet read is a
        # gap, not a fact (owner's game plan said "nothing stock-specific" for
        # names whose news had simply not loaded, 2026-10-13). The index ETFs
        # are never read for news — the wire covers them — so they count as read.
        row["news_loaded"] = sym in news or sym in _NO_OWN_NEWS
        row["filings"] = fil
        # The name's average day, and its pre-market against it — context on
        # every row, and before the bell part of the score (in play).
        adv = base.get("adv20")
        row["adv20"] = adv if isinstance(adv, (int, float)) else None
        row["premkt"] = premkt_for((premkt or {}).get(sym), row["adv20"])
        # The daily frame against the live print (frame.read); the levels
        # themselves (`frame`) ride along from the bars job.
        row["frame_read"] = frame.read(base.get("frame"), row.get("last"))
        row["short"] = (shorts or {}).get(sym)
        side0 = (row.get("setup") or {}).get("side")
        cat = catalyst_read(side0, earn, nws, fil)
        if row.get("ok"):
            row["score"] = score_row(row, reg, srs, earn, event, session,
                                     premkt=row["premkt"], news=nws,
                                     frame_read=row["frame_read"], catalyst=cat,
                                     conviction=reg.get("conviction"))
            row["flags"] = flags_for(row, earn, event, nws, fil, session,
                                     frame_read=row["frame_read"], short=row["short"],
                                     catalyst=cat)
        else:
            row["score"] = {"total": 0, "side": None, "parts": []}
            row["flags"] = []
        # The record line: settled signals of this kind, side and score band.
        row["record"] = record_for(implied_kind(row), row["score"].get("side"),
                                   row["score"].get("total"), record)
        if isinstance(row.get("setup"), dict):
            row["setup"] = {k: v for k, v in row["setup"].items() if k != "lost_vwap"}
        # After the score: the contract helper trades the row's side.
        fc = (flow_ctx or {}).get(sym) or {}
        row["options"] = options_for(sym, row, options, closes, iv_hist, td, now,
                                     reports=report_dates((earn_hist or {}).get(sym)),
                                     daily=(daily or {}).get(sym),
                                     oi_prev=fc.get("oi_prev"), vol_hist=fc.get("vol_hist"))
        # The first targets by the plan's rule — the options maths computed
        # them with the front straddle; without a chain, from the row alone.
        o = row["options"]
        row["targets"] = (o.get("targets") if isinstance(o, dict) and o.get("ok") else None) \
            or targets.target_candidates(targets.view(row, None))
        # Context, never score: its sector's big caps reporting this week.
        row["peers"] = peers_for(sym, sector, earnings, td, sector_map or {})
        pf = peer_flag(row["peers"], td)
        if pf is not None and row.get("ok"):
            row["flags"].append(pf)
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


def next_report(nxt: dict[str, Any] | None, trading_day: date) -> dict[str, Any] | None:
    """A name's next report from the history source (sources/earnhist.parse_next)
    in the row's own `earnings` shape — the calendar feed reaches a week ahead,
    this reaches as far as Nasdaq knows, with no estimate or actual. Pure."""
    if not isinstance(nxt, dict):
        return None
    try:
        d = date.fromisoformat(str(nxt.get("date")))
    except (ValueError, TypeError):
        return None
    days = (d - trading_day).days
    if days < 0:
        return None
    when = nxt.get("when") if nxt.get("when") in ("pre", "after", "unspecified") else "unspecified"
    return {"date": d.isoformat(), "when": when, "days": days,
            "eps_forecast": None, "eps_actual": None, "surprise_pct": None}


def report_dates(rows: list[dict[str, Any]] | None) -> list[date]:
    """The past report dates in a name's earnings history. Pure."""
    out: list[date] = []
    for r in rows or []:
        try:
            out.append(date.fromisoformat(str(r.get("date"))))
        except (ValueError, TypeError, AttributeError):
            continue
    return out


def options_for(sym: str, row: dict[str, Any],
                options: dict[str, tuple[optcalc.Chain, float]] | None,
                closes: dict[str, list[float]] | None, iv_hist: dict[str, list[float]] | None,
                trading_day: date, now: datetime, reports: list[date] | None = None,
                daily: list[Any] | None = None, oi_prev: dict[str, Any] | None = None,
                vol_hist: list[float] | None = None) -> dict[str, Any] | None:
    """The row's OptionsCtx (optcalc.options_ctx), or None before its first chain.

    A failure in the maths costs this one row its options, never the payload:
    the scanner's rank does not depend on them.
    """
    held = (options or {}).get(sym)
    if held is None:
        return None
    chain, fetched = held
    age = round((now.timestamp() - fetched) / 60.0, 2) if fetched else None
    try:
        return optcalc.options_ctx(chain, row, (closes or {}).get(sym) or [],
                                   (iv_hist or {}).get(sym) or [], trading_day, now, age,
                                   reports=reports, daily=daily, oi_prev=oi_prev,
                                   vol_hist=vol_hist)
    except (ValueError, TypeError, KeyError, ZeroDivisionError) as e:
        return optcalc.unavailable(f"options maths failed: {e.__class__.__name__}: {e}", age)


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
        "earnings": None, "news": [], "filings": [], "options": None,
        "adv20": None, "premkt": None, "peers": [],
        "frame": None, "frame_read": None, "short": None, "targets": [], "record": None,
    }
