"""
The scanner's read — the macro regime, the score, the flags, and the join.

THE SCORE IS A HEURISTIC RANK, NOT A CALIBRATED PROBABILITY. Every weight below
is a judgement about what the owner's strategy rewards — a stock already outside
both of its levels, strong against SPY, sitting at its entry, on volume, with the
tape and the sector behind it — and none of them has been fitted to outcomes.
The number orders a watchlist; it does not say how often the trade works. That
is why every row carries its parts: the reader can see that a 71 is "structure
30, RS 18, location 14, volume 0, market 9" and disagree with any of them.

AUDITED AGAINST ITS OWN RECORD (owner, 2026-11-05: "an audit of the ranking logic
... ensure it is as good as it should be"). On 325 live signals over ten sessions,
the top third of each day's signals by score reached +1R 52.9% of the time and the
bottom third 52.9%: the rank did not separate them. What changed: the top location
score (a retest) did worst of the live states, the tape penalty hit signals that did
no worse than the rest, the daily frame and the catalyst were underweight, and RVOL
paid for the wrong band. Read it with every day counting the same, since two busy
sessions are 126 of those signals. Every signal made +1R 45.6%, +2R 32.5%, +0.23 R
held. The old weights' top five a day made 40.0%, 32.0%, +0.45 R, and these make 46
to 48%, 38 to 40%, +0.55 R (a range, because the log cannot split RVOL's 1.25x band).
The top third stays near the average at +1R, so what the rank adds is how far a trade
runs, which is what a momentum strategy is after. All of it was read on the data the
choices came from, over ten sessions: a better prior, not a measurement.
tools/fit_score.py prints the same tests as the record grows.

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
from collections.abc import Callable, Sequence
from datetime import UTC, date, datetime
from functools import lru_cache
from typing import Any
from zoneinfo import ZoneInfo

from . import frame, marketctx, optcalc, releases, targets
from .catalysts import (
    MAJOR,
    MINOR,
    NOISE,
    NOTABLE,
    TALK,
    TIER_PENALTY,
    TIER_POINTS,
    about,
    acted,
    analyst_upgrade,
    grade,
    lead,
    move_grade,
    moved,
    own_parts,
    rated_both,
    someone_else,
    stated_move,
    stated_today,
    story,
)
from .holidays import news_since, next_trading_day, prev_trading_day
from .scan import Clock
from .sources.shortint import squeeze_flag
from .volterm import state as volterm_state
from .volterm import vix_month

#: Names whose own news feed is never read (the wire covers the index ETFs).
_NO_OWN_NEWS = frozenset({"SPY", "QQQ", "IWM"})

ET = ZoneInfo("America/New_York")

# ---- the weights (a heuristic rank — see the module docstring) --------------
#
# REWEIGHTED 2026-11-13 ON THE QUANT AUDIT (owner: "do everything you recommend"). On
# the 481 live scored signals of sixteen sessions, with every day's own average taken
# out: ENTRY LOCATION was the best part, ahead on 12 of 13 days (+28 points of +1R hit
# rate, and on both halves of the record); MARKET alignment next, 9 of 12 (+22). RS,
# the largest part at 25, did WORSE where it earned most, and only because of where
# the entry was: strong RS with an extended entry lost 30 points of hit rate and
# 0.89 R held (n 36), strong RS with a good entry held +0.30 R. RVOL showed nothing on
# the trade (ahead 4 of 11 days) although it is the best read of how far a name will
# still move (rest-of-day range on 9 of 9 sessions in the 5-minute bars): a filter,
# not a direction. Structure paid 18 or 30 to 470 of 481 signals and so told them
# apart hardly at all; the daily frame showed no edge (7 of 14 days), and a year of
# daily bars showed yesterday's and the month's momentum telling nothing of the next
# day. So: location 14 → 25, market 15 → 20, RS 25 → 20 and paid in full only on a
# live entry (RS_POOR otherwise), RVOL 15 → 8 and a gate on the top of the list
# (RVOL_GATE), structure 30 → 20, frame 12 → 6. In-sample, on the same sixteen days:
# a better prior, not a measurement. tools/fit_score.py --since 2026-11-13 reads only
# the signals on these weights; keep a change only if it holds on both halves.
W_STRUCTURE = {2: 20, 1: 12}
W_APPROACH = 7
# THE STRATEGY DECIDES THIS ONE (owner, 2026-11-05: "the strategy revolves around
# trending stocks and momentum"), and the Pine ranks by RS. The record cannot settle
# it: inside a day strong RS reached +2R more often on 3 days of 8, at 79% against 44%
# on Nov 2 and 29% against 58% on Oct 30, and 20 and 25 rank about even. RS is measured
# from yesterday's close, so it includes the gap; the log keeps the 1-hour RS beside it
# (scanlog `ctx`) to test RS now against RS since the close.
W_RS = 20
RS_FULL = 1.0  # RS of +1 daily ATR over SPY earns the whole RS part
#: RS is paid in full only on a live entry (retest, pullback, near VWAP / the 8 EMA);
#: anywhere else — extended far from it, failed, approaching, chop, the wrong side of
#: VWAP, or a pre-market plan whose RS is the gap — at most this (2026-11-13).
RS_POOR = 5
RS_GOOD_ENTRY = frozenset({"retest", "pullback", "extended_near"})
# A LIVE ENTRY IS A LIVE ENTRY (2026-11-05). A retest earned 20, the most, and did
# the worst of the live states on both halves of the record: +1R 30% and 45%, where
# a pullback made 54% and 57%, and near-VWAP or the 8 EMA 46% and 87%. The strategy's
# entry is still the retest, and 47 signals are thin, so it is not marked below the
# others; it has only stopped outranking them. Wrong side of VWAP stays at zero: 22%
# and 44% on the same split, which settles that open call.
W_LOCATION = {
    "retest": 25, "pullback": 25, "extended_near": 25, "extended_far": 7,
    "approaching": 11, "forming": 14, "failed": 0, "chop": 0,
}
# RVOL PAYS FROM 1.5x (2026-11-05). Inside a day, signals at 1.5x or more reached +2R
# more often on 5 days of 6, while 1.0x to 1.5x did worse than under 1.0x, ahead on 2
# days of 9. Thin: 49 signals at 1.5x or more, 33 of them from two sessions. The 1.25x
# step is the owner's, and untested: the log held only the points, so it cannot split
# that band. `ctx` keeps the raw RVOL from here on.
W_VOLUME = ((2.0, 8), (1.5, 6), (1.25, 3), (1.0, 2))
#: THE GATE (2026-11-13): in the regular session a name under this RVOL does not make
#: the top GATE_TOP of the list, whatever it scores. RVOL says whether a name is still
#: moving; a setup on a name the market has left alone is not a top-ten trade.
RVOL_GATE = 1.0
GATE_TOP = 10

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
# ("forming"). That was before the catalyst became a part of its own (below), and
# the parts now add past 100 and are capped, before the bell and after it.
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
# DOUBLED (2026-11-05): a catalyst with the side reached +1R 63% of the time against
# 51% with none. RAISED TO 20 (owner, 2026-11-10: "news is what stocks actually move on
# since we trade high momentum and volume break and retests"): on twenty sessions the
# catalyst was worth +0.82 R held inside each day against -0.06 R for RS, which has 25,
# and at 12 it ranked below the frame. The tiers under it are catalysts.TIER_POINTS.
W_CATALYST = 20
CATALYST_FRESH_MIN = 16 * 60  # a headline since yesterday's close (16:00 → 08:00)
# THE CATALYST IS ITS OWN PART NOW, ALL SESSION (owner, 2026-10-23: "i want
# the rankings to be as high probability as possible"). It used to be a count
# of fresh headlines inside the pre-open "in play" part; it now reads the
# DIRECTION of four things against the side — a report's surprise sign, a
# rating or target change, guidance raised or cut, an offering or a material
# 8-K — and earns with the side, costs against it. A story that says the name
# moved and why is read by the move's direction since 2026-11-10 (catalysts.moved):
# "Broadcom Stocks Jump 8.21% as Investors Eye $21.7 Billion AI Revenue Guide" is
# the news the stock is moving on, and it earned nothing because it is not a
# rating. A prior, not a finding: logged on every signal so tools/fit_score.py
# can keep it or throw it out. Major news against the side costs 10 (2026-11-10;
# it was 6, the same as an analyst's note).
P_CATALYST = -10
#: An offering filed against a long keeps the old six: a form, not a headline.
P_OFFERING = -6
W_INPLAY = W_GAP + W_PMVOL
#: Until this ET minute after the bell, a name with no RVOL yet keeps its in-play part.
OPENING_INPLAY_END = 9 * 60 + 45
# THE CLOCK, FROM THE RECORD (1,258 settled signals to 2026-11-04): (L)/(E) signals
# in the first thirty minutes reached +1R 39% of the time and in the last hour 36%,
# against 52% from 10:00 to 14:00, and on both halves of the record. A penalty: it
# never pushes a name up. 14:00 to 15:00 made 50% on one half and 35% on the other,
# so it stays out of the window for now.
P_CLOCK = -10
CLOCK_OPEN_MIN = 30
CLOCK_CLOSE_MIN = 60
RECORD_OPEN_WIN = 39
RECORD_CLOSE_WIN = 36
#: The penalty is about a signal that is live, so it lapses this long after the bar.
CLOCK_FRESH_MIN = 30
# THE TAPE PENALTY IS GONE (2026-11-05). It took 10 points off a setup against a
# moderate or strong tape on a reading of the first 453 signals. Since it was added,
# the 88 signals it fired on reached +1R 57% of the time against 52% for the rest,
# and did at least as well on both halves. A setup with the tape still earns its
# Market points, and the Market line now says when one runs against it.
TAPE_GRADES = ("moderate", "strong")
#: The record line needs this many settled signals before it says a rate.
RECORD_MIN = 10
RECORD_SOLID = 30
#: The daily frame (frame.py): the whole part with the daily trend, half of
#: it between the averages, nothing against it — and a flag when against.
#: DOUBLED (2026-11-05): 56% against the 46% of a setup against the daily trend.
W_FRAME = 6
W_BIAS = 11
W_CONFIRM = 5
W_SECTOR = 4
W_MARKET = W_BIAS + W_CONFIRM + W_SECTOR
SECTOR_MIN = 0.2  # pp of excess return over SPY before a sector counts as a tailwind
P_FUEL = -10
FUEL_USED = 1.2  # the day's range as a multiple of daily ATR
P_EVENT = -10
EVENT_MIN = 30
P_EARN_AMC = -5
P_FAILED = -15
# THE STRATEGY TRADES THE OPTION (2026-11-05). A name whose at-the-money spread is
# graded poor can be the best chart on the list and still give the edge away getting
# in and out, so it should not sit at the top of a list read for trades. Reasoned,
# not measured: the record is in stock R, and it is logged from here to be tested.
P_LIQUIDITY = -5

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
#: younger than ADV_MIN sessions has none. THIRTY (2026-11-10, it was twenty): the
#: one window every "share of an average day" on the desk now reads — the pool,
#: the wide scan and the Day 2/3 ledger take TradingView's 30-day average, and the
#: screener offers no twenty. RVOL is another thing (scan.RVOL_SESSIONS): volume
#: SO FAR against the same time of day, which a whole-day average cannot give.
ADV_SESSIONS = 30
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


def avg_day(volumes: list[float]) -> float | None:
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

    `pct_adv` is pre-market share volume as a percentage of the average day
    (ADV_SESSIONS) — 5% before the bell is a name in play; 0.3% is not.
    """
    if not read:
        return None
    vol = read.get("volume")
    pct = (round(vol / adv * 100.0, 2)
           if isinstance(vol, (int, float)) and isinstance(adv, (int, float)) and adv > 0
           else None)
    out = {"volume": vol, "pct_adv": pct, "high": read.get("high"), "low": read.get("low"),
           "last": read.get("last"), "asof": read.get("asof")}
    # "screener" when the wide read stood in for Nasdaq's (fifteen minutes behind).
    if read.get("source"):
        out["source"] = read["source"]
    return out


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
    """The report that matters to a session: last night's, today's, or the week's. Pure.

    LAST NIGHT IS THE LAST TRADING DAY'S EVENING (quant audit, 2026-11-13). It was the
    calendar day before, so on a Monday Friday's after-the-close report was nobody's,
    and the same the morning after a holiday. A report after the close of any day from
    the previous trading day on is last night's (`last_night`), and it is the report
    that matters ahead of the week's next one; `days` stays the calendar count."""
    best: dict[str, Any] | None = None
    best_key: tuple[int, int] | None = None
    prev = prev_trading_day(trading_day)
    for r in rows:
        if (r.get("symbol") or "").upper() != sym:
            continue
        try:
            d = date.fromisoformat(str(r.get("date")))
        except ValueError:
            continue
        days = (d - trading_day).days
        last_night = r.get("when") == "after" and prev <= d < trading_day
        if not last_night and (days < 0 or days > 5):
            continue
        key = (0 if last_night or days == 0 else 1, abs(days))
        if best_key is None or key < best_key:
            best_key = key
            best = {"date": d.isoformat(), "when": r.get("when") or "unspecified", "days": days,
                    "eps_forecast": r.get("eps_forecast"), "eps_actual": r.get("eps_actual"),
                    "surprise_pct": r.get("surprise_pct")}
            if last_night:
                best["last_night"] = True
    return best


_RATING = re.compile(
    r"downgrad|price target|\bPT\b|initiat\w* (?:coverage|at\b|with\b)|coverage initiated|"
    r"reiterat|overweight|underweight|"
    r"outperform|underperform|\bbuy rating|\bsell rating|neutral rating", re.I)
_EARN = re.compile(
    r"earnings|results|\bEPS\b|revenue|guidance|outlook|quarter|\bQ[1-4]\b|beats?\b|miss(es)?\b",
    re.I)
_FILING = re.compile(r"\b8-K\b|\b10-[QK]\b|SEC filing|files? for|offering|prospectus", re.I)


def news_kind(title: str) -> str:
    """rating | earnings | filing | news, from the headline alone. Pure.
    An upgrade is a rating only in an analyst's sentence (catalysts.analyst_upgrade)."""
    if _RATING.search(title) or analyst_upgrade(title):
        return "rating"
    if _EARN.search(title):
        return "earnings"
    if _FILING.search(title):
        return "filing"
    return "news"


def _story(title: str) -> str:
    return re.sub(r"[^a-z0-9 ]", "", title.lower())[:80]


def names_of(aliases: Sequence[str], own: Sequence[str] = ()) -> list[str]:
    """The words a headline calls the company: the table's or the filer's short
    name, and the own feed's looser first word. Pure."""
    return [*aliases, *(n for n in own if n and n not in aliases)]


def news_for(sym: str, own: list[dict[str, Any]], wire: list[dict[str, Any]],
             aliases: list[str], now: datetime, limit: int | None = NEWS_MAX,
             names: Sequence[str] = (), strict: bool = True) -> list[dict[str, Any]]:
    """The ticker's own headlines plus any wire story that names it. Pure.

    THE WIRE MATCH IS STRICT ON PURPOSE: the cashtag, or a company name written
    as a proper noun on a word boundary. "Meta" in "metadata" or "Intel" in
    "intelligence" would put a macro tape's worth of noise under a stock.

    AND THE STORY HAS TO BE THE NAME'S (owner, 2026-11-10). A feed for a ticker
    carries any story that names it: GOOGL's held "AMD Stock Rises On Google Cloud
    Deal, Wall Street Upgrade", and AMZN's a Dow wrap. A story that names the
    company only after its first joiner is dropped (catalysts.about); `names` are
    the words the headline would call it by.

    AND IT HAS TO BE A STORY (owner, 2026-11-11: "only … news that can actually
    impact the market and stocks"). `catalysts.story` is the one test, for this list
    and for the lead story alike: the lead names the company (a headline that does not
    name it at all is somebody else's, where the names are known), and it describes
    an event, not a template, a diary note, a preview, an opinion, a list or a recap.
    102 of the 254 stories under the thirty-six names that morning were not. `strict`
    is whether the names are the table's (see catalysts.story): a guessed name is not
    held against a headline that does not carry it.
    """
    now_ts = now.timestamp()
    cutoff = now_ts - NEWS_DAYS * 86400
    pats = [re.compile(rf"\${re.escape(sym)}\b")]
    pats += [re.compile(rf"\b{re.escape(a)}\b") for a in aliases if a]
    called = names or names_of(aliases)
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
        if story(it.get("title") or "", sym, called, str(it.get("publisher") or ""),
                 strict) is None:
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
        if limit is not None and len(out) >= limit:
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
# "UPGRADE" IS READ BY catalysts.analyst_upgrade, not by its stem here: a Christmas
# tree's "major holiday upgrade" cost Home Depot's short six (audit, 2026-11-11). And
# A BID IS GOOD NEWS FOR THE TARGET ONLY: "takeover offer" and "buyout bid" were bullish
# for whichever name the headline led with, so "IDP Education mulls Blackstone's revised
# $571 million takeover offer" cost a Blackstone short ten. The passive forms stay
# ("to be acquired", "acquired by"), whose subject is the company being bought; a
# target's own jump on a bid is read as its move (catalysts.moved).
_BULL = re.compile(
    r"rais\w* (?:its |the |their )?(?:price )?target|"
    r"lift\w* (?:its |the )?(?:price )?target|price target (?:raised|lifted|increased|hiked)|"
    r"raised to (?:buy|outperform|overweight|strong buy)|"
    r"initiat\w*[^.]{0,40}\b(?:buy|outperform|overweight)\b|reiterat\w*[^.]{0,20}\bbuy\b|"
    r"rais\w* (?:full[- ]year |fy ?\d* |annual |its |the )?(?:guidance|outlook|forecast)|"
    r"hik\w* (?:its |the )?(?:guidance|outlook|forecast)|"
    r"(?:guidance|outlook|forecast) (?:raised|lifted|hiked|boosted)|\bbeats?\b|"
    r"\btops? (?:estimates|expectations)|"
    r"\bfda (?:approv|clear)|approved by the fda|met (?:its |the )?primary endpoint|"
    r"positive (?:phase|topline|trial|data)|to be acquired|acquired by|"
    r"\b(?:wins?|awarded)\b[^.]{0,40}\bcontract\b|"
    # The events the words did not reach (quant audit, 2026-11-13): guidance however it
    # is worded ("Raises 2026 Revenue Forecast" was no direction), a trial that met its
    # goal, a seat in an index, a buyback, a split, a raised or special dividend, a
    # court win.
    r"\b(?:rais|lift|boost|hik|increas)\w*\b[^.;]{0,30}\b(?:guidance|outlook|forecasts?|"
    r"projections?)\b|\bguides? (?:above|higher|up|ahead)\b|"
    r"\b(?:strong|upbeat|bullish|robust|solid|rosy|better[- ]than[- ]expected)\s+"
    r"(?:guidance|outlook|forecast)\b|"
    r"\b(?:guidance|outlook|forecast) (?:tops|beats|above|exceeds)\b|"
    r"\b(?:meets?|met|achieves?|achieved|hits?|hit)\b[^.;]{0,30}\b(?:primary|main|key) "
    r"(?:endpoint|goal)|\bstatistically significant\b|"
    r"\bpositive (?:results|readout|interim|pivotal)\b|"
    r"\b(?:join|joins|joining|to join|added to|to be added to|inclusion in|included in|"
    r"enters?|to enter)\s+(?:the\s+)?(?:s&p|nasdaq[- ]100|dow\b)|"
    r"\bbuybacks?\b|\b(?:share|stock) repurchases?\b|\brepurchase (?:program|plan)\b|"
    r"\b(?:[2-9]|1\d|20)[- ]for[- ]1\b|(?<!reverse )\b(?:stock|share) split\b|"
    r"\bspecial (?:cash )?dividend\b|\b(?:raises?|raised|increases?|increased|hikes?|hiked|"
    r"boosts?|boosted)\b[^.;]{0,30}\bdividends?\b|"
    r"\b(?:wins?|won)\b[^.;]{0,30}\b(?:lawsuit|case|appeal|ruling|verdict|patent)\b|"
    r"\b(?:lawsuit|case|suit) (?:dismissed|tossed)\b",
    re.I)
_BEAR = re.compile(
    r"downgrad|cut\w* (?:its |the |their )?(?:price )?target|"
    r"lower\w* (?:its |the )?(?:price )?target|"
    r"trim\w* (?:its |the )?(?:price )?target|price target (?:cut|lowered|trimmed|reduced)|"
    r"cut to (?:neutral|hold|sell|underperform|underweight|market perform|sector perform|"
    r"equal[- ]weight|in[- ]line|peer perform)|"
    r"initiat\w*[^.]{0,40}\b(?:sell|underperform|underweight)\b|"
    r"cut\w* (?:full[- ]year |fy ?\d* |annual |its |the )?(?:guidance|outlook|forecast)|"
    r"lower\w* (?:its |the )?(?:guidance|outlook|forecast)|slash\w* (?:guidance|outlook|forecast)|"
    r"withdraw\w* (?:its )?guidance|"
    r"(?:guidance|outlook|forecast) (?:cut|lowered|slashed|trimmed|withdrawn)|"
    r"\bmiss(?:es|ed)?\b|\bfalls? short\b|"
    r"\b(?:secondary|stock|share) offering|\bprobes?\b|investigat|\brecalls?\b|lawsuits?|"
    r"\bsued\b|"
    r"\bfda (?:rejects?|declines?|refuses?)|complete response letter|clinical hold|"
    r"(?:trial|study) (?:fails|failed)|failed (?:to meet|its) primary|\bbankrupt|\bchapter 11\b|"
    # (2026-11-13) Guidance cut however it is worded; equity raised (common stock, a
    # convertible, a registered direct, an at-the-market programme); a trial that missed;
    # an index exit; an executive leaving; a short seller; a dividend cut; a reverse split.
    r"\b(?:cut|lower|slash|trim|reduc|withdr[ae]w|pull|suspend)\w*\b[^.;]{0,30}"
    r"\b(?:guidance|outlook|forecasts?|projections?)\b|\bguides? (?:below|lower|down|light)\b|"
    r"\b(?:weak|soft|disappointing|downbeat|gloomy|bleak|cautious|tepid|lackluster|"
    r"lacklustre|light)\s+(?:guidance|outlook|forecast)\b|"
    r"\b(?:guidance|outlook|forecast) (?:misses|disappoints|below|trails)\b|"
    r"\b(?:public|follow-on|upsized|proposed|underwritten|registered direct|at-the-market)\s+"
    r"(?:equity\s+)?offering\b|"
    r"\boffering of\b[^.;]{0,40}\b(?:common|ordinary|shares|stock|ads|adss|american depositary|"
    r"units|warrants)\b|\bconvertible (?:senior )?notes\b|\bat-the-market\b|"
    r"\b(?:fails?|failed|misses?|missed|did not meet|didn['’]t meet|does not meet)\b[^.;]{0,30}"
    r"\b(?:primary|main|key) (?:endpoint|goal)|(?:trial|study) (?:halted|stopped|paused)\b|"
    r"\bdiscontinu\w* (?:the )?(?:trial|study|development|program)\b|\bcrl\b|"
    r"\b(?:removed|dropped|deleted|to be removed|to be dropped|exits?|to exit)\s+(?:from\s+)?"
    r"(?:the\s+)?(?:s&p|nasdaq[- ]100|dow\b)|"
    r"\b(?:ceo|chief executive|cfo|chief financial officer|founder)\b[^.;]{0,40}"
    r"\b(?:steps? down|stepping down|resigns?|resigned|to step down|ousted|exits?|departs?|"
    r"departure|to depart|to leave|leaving|fired|terminated)\b|"
    r"\b(?:ousts?|fires?)\s+(?:its\s+)?(?:ceo|chief executive|cfo)\b|"
    r"\bshort[- ]sellers?\b|\bshort report\b|\bshort position in\b|"
    r"\b(?:hindenburg|muddy waters|citron research|spruce point|culper research|kerrisdale|"
    r"grizzly research|wolfpack research|iceberg research|fuzzy panda|blue orca|"
    r"white diamond research|bleecker street research|viceroy research)\b|"
    r"\b(?:cuts?|slashes?|slashed|suspends?|suspended|eliminates?|eliminated|halts?|halted|"
    r"omits?)\b[^.;]{0,30}\bdividends?\b|\breverse (?:stock )?split\b",
    re.I)
_OFFERING_FORMS = ("S-1", "S-3", "424B", "F-1", "F-3")


def headline_direction(title: str, sym: str | None = None,
                       names: Sequence[str] = ()) -> str | None:
    """"bull", "bear", or None — by what the title says was done, never by the price
    move it describes. Both ways at once is None.

    READ IN THE NAME'S OWN CLAUSE (quant audit, 2026-11-13). The words were read across
    the whole title, so another company's news set this one's direction: "Intel Jumps
    After AMD Misses Estimates" cost an Intel long ten. With the name known (`sym`,
    `names`), the words are read in the lead it heads (catalysts.lead: up to the first
    "after", "as", "on" …); and where the name is the OBJECT of the action
    (catalysts.acted), the action is the direction: upgraded is bull, downgraded bear,
    bid for bull (a target is paid a premium), a short seller's target bear. Pure.

    Kept by its arguments, as catalysts.grade is: it is asked for every fresh headline
    under every name on every read of the list (2026-11-11: uncached regular expressions
    on that path pinned the collector)."""
    return _direction(title or "", sym or "", tuple(names))


@lru_cache(maxsize=32768)
def _direction(title: str, sym: str, names: tuple[str, ...]) -> str | None:
    """`headline_direction` on arguments that can be a key."""
    scope = title
    if sym:
        # One firm raising it and another cutting it is no direction (catalysts.rated_both).
        if rated_both(title, sym, names):
            return None
        done = acted(title, sym, names)
        if done == "up":
            return "bull"
        if done in ("down", "short"):
            return "bear"
        g = grade(title)
        if done == "deal" and g.tag == "Deal":
            return "bull"
        # An analyst's note is the named company's from end to end: its action comes
        # after the joiner ("Bernstein maintains Home Depot at Market Perform, raises price
        # target to $357"), so it is read whole, as far as it speaks for the name
        # (catalysts.own_parts: "Intel Upgraded as AMD Downgraded" is Intel's upgrade).
        if g.tag in ("Analyst", "Target"):
            scope = own_parts(title, sym, names)
        elif about(title, sym, names):
            if someone_else(title, sym, names):
                return None
            scope = " ".join(lead(title, sym, names)) or title
    bull = bool(_BULL.search(scope)) or analyst_upgrade(scope)
    bear = bool(_BEAR.search(scope))
    if bull == bear:
        return None
    return "bull" if bull else "bear"


#: THE TAPE HAS THE LAST WORD (quant audit, 2026-11-13). A headline's direction is read
#: from words; the market's is read from the price. Where the name has moved at least
#: this far against SPY since the previous close (RS, in its daily ATRs), a story whose
#: words point the other way is set aside rather than scored either way ("Palantir Stock
#: Falls Despite Earnings Beat" was +20 to a long), and a major or notable story whose
#: words give no direction ("Acme Reports Q3 Results", "Merck to Buy Verona", "Acme CEO
#: Steps Down") takes the tape's. Under it the tape has not spoken and the words stand.
TAPE_CLEAR = 0.5

def day_move_of(row: dict[str, Any]) -> float | None:
    """The name's move since the previous close (%), whatever the session: the pre-market
    or after-hours print included. Pure."""
    last, pdc = row.get("last"), (row.get("levels") or {}).get("pdc")
    if isinstance(last, (int, float)) and isinstance(pdc, (int, float)) and pdc > 0:
        return (last / pdc - 1.0) * 100.0
    return None


def catalyst_read(side: str | None, earnings: dict[str, Any] | None,
                  news: list[dict[str, Any]] | None,
                  filings: list[dict[str, Any]] | None, sym: str | None = None,
                  names: Sequence[str] = (), *, tape: float | None = None,
                  fresh_min: float | None = None,
                  day_move: float | None = None) -> dict[str, Any]:
    """The catalyst part: {pts, note, against} — points with the side (up to
    W_CATALYST), P_CATALYST against it with the item quoted in `against`, zero
    with no directional item. Pure.

    Items: a report since the close with its surprise sign (W_CATALYST); a
    headline since the close with a direction, GRADED BY WHAT IT IS
    (catalysts.py, owner 2026-11-09): a beat, guidance, an FDA readout, a deal or
    the name's move with its reason W_CATALYST, an upgrade or downgrade 12, a
    price-target tweak 3, a law firm's notice nothing. The direction is what the
    headline says was done, else which way it says the name moved (`sym` and
    `names` find the name in it; catalysts.moved). An offering filed in the last
    three days (3, bear); a bankruptcy 8-K (W_CATALYST, bear). The strongest item each way decides;
    against wins a tie, because the downside of ranking a name into its own bad
    news is the larger one. A minor note against the side costs 3 where it used
    to cost the full penalty, since it now earns only 3 with it.
    """
    # (direction, weight, text, penalty, what it was: the grade, where its direction came
    # from and its age — logged with each signal so the record can test the news, phase 3)
    items: list[tuple[str, int, str, int, dict[str, Any]]] = []
    # The tape's direction, when it has spoken (TAPE_CLEAR); None when it has not.
    tape_dir = (("bull" if tape > 0 else "bear")
                if isinstance(tape, (int, float)) and abs(tape) >= TAPE_CLEAR else None)
    set_aside: list[str] = []
    # Stories whose stated move the name has not made today (STATED_MIN), and analyst
    # headlines that rate it both ways (catalysts.rated_both).
    earlier: list[str] = []
    mixed = 0

    def heard(d: str, text: str) -> bool:
        """Does the tape let a direction read from words stand? Records it if not."""
        if tape_dir is not None and d != tape_dir:
            set_aside.append(text)
            return False
        return True

    days, when = (earnings or {}).get("days"), (earnings or {}).get("when")
    sp = (earnings or {}).get("surprise_pct")
    last_night = bool((earnings or {}).get("last_night")) or days == -1
    if earnings and (last_night or (days == 0 and when == "pre")):
        when_txt = "after the close" if last_night else "this morning"
        if isinstance(sp, (int, float)) and sp != 0:
            d0 = "bull" if sp > 0 else "bear"
            text0 = f"reported {when_txt}, EPS {sp:+.1f}% vs estimate"
            if heard(d0, text0):
                items.append((d0, W_CATALYST, text0, P_CATALYST,
                              {"tag": "Report", "tier": MAJOR, "src": "report", "age_min": None}))
    window = fresh_min if isinstance(fresh_min, (int, float)) else CATALYST_FRESH_MIN
    fresh = [h for h in news or []
             if isinstance(h, dict) and h.get("age_min") is not None
             and h["age_min"] <= window]
    for h in fresh:
        title = str(h.get("title") or "")
        g = grade(title)
        # NOTHING HAPPENED, OR NOT TO THIS NAME (audit, 2026-11-11, on that evening's
        # list: six of the twenty rows the catalyst had scored were misread). A preview
        # or an opinion describes no event, so it has no direction ("Will Broadcom Beat
        # Estimates Again in Its Next Earnings Report?" was a twenty-point beat). And
        # where the company's name is known and the headline does not carry it, the
        # story is somebody else's that the feed filed here: "Trade Desk's Jeff Green
        # Says Growth Still Falls Short" paid a Netflix short, and a morning round-up's
        # "Huang faces FBI probe" cost SpaceX ten. A name the table has no words for is
        # still left to its feed.
        if g.tier == NOISE:
            continue
        if sym and names and about(title, sym, names) is None:
            continue
        mv = moved(title, sym, names) if sym else None
        # The name's own move, not a wrap: "Amazon Stocks Rise 4.05% as JPMorgan Adds
        # It to Focus List" is a List by its words until Amazon is known to lead it.
        # AND NOT A PREVIEW EITHER (2026-11-11): "NBIS Stock Jumps Over 11% On CoreWeave
        # Boost: Analysts Expect Over Six-Fold Growth In Sales In Upcoming Q3 Report" is
        # talk by its second half, so it led Nebius's row as its move (catalysts.story
        # reads it so) and earned the score nothing. Asked before talk is set aside.
        if mv and g.tag in ("List", "Preview"):
            g = move_grade(title) or g
        if g.tag in TALK:
            continue
        pub = str(h.get("publisher") or "").strip()
        age = h.get("age_min")
        age_txt = f"{round(age / 60)}h" if isinstance(age, (int, float)) and age >= 60 else (
            f"{round(age)}m" if isinstance(age, (int, float)) else "")
        text = f"{pub + ': ' if pub else ''}\"{str(h.get('title') or '').strip()[:90]}\""
        text = f"{text} ({age_txt})" if age_txt else text
        if sym and rated_both(title, sym, names):
            # Two calls, two ways: no direction, and not the tape's either.
            mixed += 1
            continue
        said = stated_move(title, sym, names) if sym else None
        if not stated_today(said, day_move):
            assert said is not None and day_move is not None
            earlier.append(f"{text} says {said:+.1f}%, the name is {day_move:+.1f}% since "
                           "the close")
            continue
        # THE NAME'S OWN STATED MOVE FIRST (2026-11-13): it is the market's verdict on the
        # news, where the event's words may be anybody's ("Palantir Stock Falls Despite
        # Earnings Beat" was a beat). Then the words, in the name's own clause. Then, for
        # a story that matters and says no way, the tape (TAPE_CLEAR).
        d = mv or headline_direction(title, sym, names)
        src = "move" if mv else "words"
        if d is not None:
            if not heard(d, text):
                continue
        elif g.tier in (MAJOR, NOTABLE) and tape_dir is not None:
            d, src = tape_dir, "tape"
            text = f"{text} · its direction from the tape"
        else:
            continue
        items.append((d, min(TIER_POINTS[g.tier], W_CATALYST), text, TIER_PENALTY[g.tier],
                      {"tag": g.tag, "tier": g.tier, "src": src,
                       "age_min": age if isinstance(age, (int, float)) else None}))
    for f in filings or []:
        form = str((f or {}).get("form") or "")
        desc = str((f or {}).get("desc") or form)
        if form.startswith(_OFFERING_FORMS):
            text = f"offering filed: {desc[:60]}"
            if heard("bear", text):
                items.append(("bear", 3, text, P_OFFERING,
                              {"tag": "Filing", "tier": MINOR, "src": "filing", "age_min": None}))
        elif form.startswith("8-K") and "bankruptcy" in desc.lower():
            items.append(("bear", W_CATALYST, f"8-K: {desc[:60]}", P_CATALYST,
                          {"tag": "Filing", "tier": MAJOR, "src": "filing", "age_min": None}))
    more = f" and {len(set_aside) - 1} more" if len(set_aside) > 1 else ""
    aside = f" · set aside, the tape disagrees: {set_aside[0]}{more}" if set_aside else ""
    if earlier:
        more = f" and {len(earlier) - 1} more" if len(earlier) > 1 else ""
        aside += f" · set aside, an earlier move: {earlier[0]}{more}"
    if mixed:
        aside += (" · set aside, analysts rating it both ways" if mixed == 1 else
                  f" · set aside, {mixed} headlines rating it both ways")
    # What the record keeps of the read (scanlog ctx `news`, phase 3 of the quant audit):
    # how many headlines were in the window, how many the tape set aside, and the item
    # that decided the part — its grade, its direction and where that came from.
    seen = {"fresh": len(fresh), "set_aside": len(set_aside), "earlier": len(earlier),
            "mixed": mixed}
    if side not in ("long", "short") or not items:
        n_fresh = len(fresh)
        why = ("no side" if side not in ("long", "short") else
               f"no directional catalyst · {n_fresh} headline{'s' if n_fresh != 1 else ''} "
               f"since the close" if n_fresh else "no directional catalyst · no headlines since "
               "the close")
        return {"pts": 0, "note": why + aside, "against": None, "item": None, **seen}
    mine = "bull" if side == "long" else "bear"
    with_items = sorted((it for it in items if it[0] == mine), key=lambda x: -x[1])
    against_items = sorted((it for it in items if it[0] != mine), key=lambda x: -x[1])
    best_with = with_items[0] if with_items else None
    best_against = against_items[0] if against_items else None
    if best_against and (best_with is None or best_against[1] >= best_with[1]):
        note = f"against the {side} · {best_against[2]}"
        if best_with:
            note += f" · with it: {best_with[2]}"
        return {"pts": best_against[3], "note": note + aside, "against": best_against[2],
                "item": {**best_against[4], "dir": best_against[0], "with": False}, **seen}
    assert best_with is not None
    note = f"with the {side} · {best_with[2]}"
    if best_against:
        note += f" · against it: {best_against[2]}"
    return {"pts": min(best_with[1], W_CATALYST), "note": note + aside, "against": None,
            "item": {**best_with[4], "dir": best_with[0], "with": True}, **seen}


def _signal_minute(at_et: Any) -> int | None:
    m = re.match(r"^(\d{1,2}):(\d{2})", str(at_et or ""))
    return int(m.group(1)) * 60 + int(m.group(2)) if m else None


def latest_trade_signal(signals: list[dict[str, Any]] | None) -> dict[str, Any] | None:
    """The row's newest (L) or (E) today, or None. Pure."""
    for sg in reversed(signals or []):
        if isinstance(sg, dict) and sg.get("kind") in ("L", "E"):
            return sg
    return None


def clock_penalty(signals: list[dict[str, Any]] | None,
                  now: datetime | None = None) -> tuple[int, str] | None:
    """P_CLOCK when the newest (L)/(E) fired in the first CLOCK_OPEN_MIN minutes
    or the last CLOCK_CLOSE_MIN of the regular session, with the record's rate
    in the note; None otherwise. Pure.

    ONLY WHILE THAT SIGNAL IS LIVE (2026-11-05). A 09:40 signal took ten points off
    its name for the rest of the day, so at 13:00 a clean retest was ranked down for
    something three hours old. With `now`, the penalty lapses CLOCK_FRESH_MIN after
    the bar."""
    sg = latest_trade_signal(signals)
    if sg is None:
        return None
    m = _signal_minute(sg.get("at_et"))
    if m is None:
        return None
    if now is not None:
        et = now.astimezone(ET)
        # Past the window, or a minute still to come today, which is yesterday's bar.
        if not 0 <= et.hour * 60 + et.minute - m <= CLOCK_FRESH_MIN:
            return None
    label = f"({sg['kind']}) at {sg.get('at_et')}"
    if 9 * 60 + 30 <= m < 9 * 60 + 30 + CLOCK_OPEN_MIN:
        return P_CLOCK, (f"{label}, first {CLOCK_OPEN_MIN} minutes: {RECORD_OPEN_WIN}% of "
                         f"such signals reached +1R")
    if m >= 16 * 60 - CLOCK_CLOSE_MIN:
        return P_CLOCK, f"{label}, last hour: {RECORD_CLOSE_WIN}% of such signals reached +1R"
    return None


def tape_against(side: str | None, conviction: dict[str, Any] | None) -> str | None:
    """The words for a setup against the tape's moderate or strong lean: a note on
    the Market line, not a penalty (see TAPE_GRADES). Pure."""
    if side not in ("long", "short") or not isinstance(conviction, dict):
        return None
    bias, grade = conviction.get("bias"), conviction.get("grade")
    if bias in ("long", "short") and bias != side and grade in TAPE_GRADES:
        return f"against a {grade} {bias} tape"
    return None


def liquidity_penalty(score: dict[str, Any], options: dict[str, Any] | None) -> dict[str, Any]:
    """The score with P_LIQUIDITY in it when the name's options are graded poor. It
    comes after the score because the contract helper reads the score's side. Pure."""
    liq = (options or {}).get("liquidity") or {}
    if not score.get("side") or not (options or {}).get("ok") or liq.get("grade") != "poor":
        return score
    spread = liq.get("spread_pct")
    note = (f"{spread:.1f}% at-the-money spread" if isinstance(spread, (int, float))
            else "wide spread")
    parts = [*score.get("parts", []), _part("liquidity", "Options liquidity", P_LIQUIDITY, 0, note)]
    raw = sum(p["pts"] for p in parts)
    return {**score, "parts": parts, "total": max(0, min(100, raw)), "raw": raw}


def rank_key(row: dict[str, Any]) -> tuple[Any, ...]:
    """The table's order: the raw score (score_row: the uncapped sum, so a penalty
    counts at the top), then on a tie the name nearest its entry, then the stronger
    against SPY, then the ticker, so a tie does not flicker. Pure."""
    entry = (row.get("setup") or {}).get("entry") or {}
    dist = entry.get("dist_atr")
    rs = (row.get("rs") or {}).get("SPY")
    sc = row.get("score") or {}
    raw = sc.get("raw")
    return (not row.get("ok"), -(raw if isinstance(raw, (int, float)) else sc.get("total", 0)),
            abs(dist) if isinstance(dist, (int, float)) else 99.0,
            -abs(rs) if isinstance(rs, (int, float)) else 0.0, str(row.get("sym")))


def rvol_gate(rows: list[dict[str, Any]], session: str) -> list[dict[str, Any]]:
    """The ranked list with no name under RVOL_GATE in its top GATE_TOP, in the regular
    session (RVOL_GATE). A gated name keeps its score and its place among the rest, and
    says why (`score.gated`). Before the bell and after it RVOL is not the read, and a
    name with no RVOL yet is not held back for it. Pure on the order; marks the rows."""
    if session != "rth":
        return rows

    def low(r: dict[str, Any]) -> bool:
        rv = r.get("rvol")
        return bool(r.get("ok")) and isinstance(rv, (int, float)) and rv < RVOL_GATE

    top: list[dict[str, Any]] = []
    rest: list[dict[str, Any]] = []
    for r in rows:
        (top if len(top) < GATE_TOP and r.get("ok") and not low(r) else rest).append(r)
    # Only a name the gate actually moved says so: one that would have ranked above the
    # last of the ten.
    if len(top) == GATE_TOP:
        last = rank_key(top[-1])
        for r in rest:
            if low(r) and isinstance(r.get("score"), dict) and rank_key(r) < last:
                r["score"]["gated"] = (f"RVOL {r['rvol']:.2f}, under {RVOL_GATE:g}: "
                                       f"kept out of the top {GATE_TOP}")
    return top + sorted(rest, key=rank_key)


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
            "held_r": r.get("held_r"),
            "sessions": r.get("sessions"),
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
              conviction: dict[str, Any] | None = None,
              now: datetime | None = None) -> dict[str, Any]:
    """The contract's score: seven parts and the penalties, every one listed. Pure.

    Before the bell (and overnight) the volume part is IN PLAY instead — see
    W_INPLAY. From 09:30 it is RVOL exactly as before. The daily frame
    (W_FRAME) and the catalyst (W_CATALYST, catalyst_read) are the sixth and
    seventh; the clock (P_CLOCK) is a penalty from the record. The total is capped
    at 100 as before.
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
        # Which levels, said plainly. AN OUTSIDE DAY IS THROUGH BOTH (owner,
        # 2026-11-13: "an outside day should be either above both premarket high and
        # previous day high or previous day low and pre market low"). This note used
        # to call a name through the previous day's level alone "an outside setup",
        # PMH not taken or not; the points were and are for the levels taken (two
        # score more than one), so only the words were wrong.
        broke = row.get("broken") or {}
        day_key, pm_key = ("pdh", "pmh") if d > 0 else ("pdl", "pml")
        word = "above" if d > 0 else "below"
        if s == 2:
            note = f"an outside day: {word} {day_key.upper()} and {pm_key.upper()}"
        elif broke.get(day_key) and not (row.get("levels") or {}).get("pm_done"):
            # Before the bell there is no pre-market level to have taken yet.
            note = f"{word} {day_key.upper()}, the pre-market range not set yet"
        elif broke.get(day_key):
            note = (f"{word} {day_key.upper()} only, {pm_key.upper()} not taken: "
                    "not an outside day")
        elif broke.get(pm_key):
            note = f"{word} {pm_key.upper()} only, inside yesterday's range"
        else:
            note = "through one level"
    elif state == "approaching":
        pts, note = W_APPROACH, f"approaching {setup.get('level') or 'a level'}"
    else:
        pts, note = 0, "inside the levels" if d else "no side"
    parts.append(_part("structure", "Structure", pts, max(W_STRUCTURE.values()), note))

    # Where the entry is: the location part below, and what RS is paid against it.
    entry = setup.get("entry")
    loc_key = state
    if state == "extended":
        near = entry is not None and abs(entry.get("dist_atr") or 99) <= 1.0
        loc_key = "extended_near" if near else "extended_far"
    good_entry = loc_key in RS_GOOD_ENTRY and not setup.get("lost_vwap")

    # ---- relative strength ---------------------------------------------------
    rs = (row.get("rs") or {}).get("SPY")
    if d and rs is not None:
        frac = max(0.0, min(1.0, rs * d / RS_FULL))
        rs_pts = frac * W_RS
        rs_note = f"{rs:+.2f} ATR vs SPY"
        if not good_entry and rs_pts > RS_POOR:
            rs_pts = RS_POOR
            rs_note += " · capped: no live entry"
        parts.append(_part("rs", "RS vs SPY", rs_pts, W_RS, rs_note))
    else:
        parts.append(_part("rs", "RS vs SPY", 0, W_RS,
                           "no RS yet" if rs is None else "no side"))

    # ---- location ------------------------------------------------------------
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
    parts.append(_part("location", "Location", pts, max(W_LOCATION.values()), note))

    # ---- volume (in play before the bell) -----------------------------------
    rvol = row.get("rvol")
    # IN PLAY HOLDS UNTIL RVOL EXISTS (quant audit, 2026-11-13). RVOL needs a finished
    # five-minute bar, so from 09:30 to 09:35 every name had neither part and the list
    # lost up to sixteen points at once at the bell. In the opening quarter hour only:
    # later, a missing RVOL is a gap in the bars, not the bell.
    opening = (now is not None and session == "rth" and rvol is None
               and now.astimezone(ET).hour * 60 + now.astimezone(ET).minute < OPENING_INPLAY_END)
    if session in ("pre", "closed") or opening:
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
        parts.append(_part("volume", "Relative volume", pts, W_VOLUME[0][1], vnote))

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
    against_tape = tape_against(side, conviction)
    if against_tape:
        bits.append(against_tape)
    parts.append(_part("market", "Market", pts, W_MARKET, ", ".join(bits) or "no tailwind"))

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
    cpart = _part("catalyst", "Catalyst", cpts, W_CATALYST if cpts >= 0 else 0,
                  str(cat.get("note") or ""))
    # What decided it, for the signal log (scanlog `ctx.news`); not drawn on the page.
    cpart["read"] = {"item": cat.get("item"), "fresh": cat.get("fresh"),
                     "set_aside": cat.get("set_aside")}
    parts.append(cpart)

    # ---- penalties -----------------------------------------------------------
    clk = clock_penalty(row.get("signals"), now)
    if clk is not None:
        parts.append(_part("clock", "Clock", clk[0], 0, clk[1]))
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

    # THE LIST IS RANKED ON THE RAW SUM (quant audit, 2026-11-13). The parts add past 100
    # and the total is capped to read as a score, so a name at 108 with a ten-point
    # penalty showed 100 beside a name at 100 without one, and the tie fell to entry
    # distance: the penalty did nothing where it mattered most. `raw` is uncapped and is
    # what `rank_key` sorts on; `total` is what the page shows.
    raw = sum(p["pts"] for p in parts)
    return {"total": max(0, min(100, raw)), "raw": raw, "side": side, "parts": parts}


def flags_for(row: dict[str, Any], earnings: dict[str, Any] | None,
              event: dict[str, Any] | None, news: list[dict[str, Any]],
              filings: list[dict[str, Any]], session: str,
              frame_read: dict[str, Any] | None = None,
              short: dict[str, Any] | None = None,
              catalyst: dict[str, Any] | None = None) -> list[dict[str, Any]]:
    """The few things a reader must see before taking the trade. Pure."""
    out: list[dict[str, Any]] = []

    def add(kind: str, tone: str, text: str) -> None:
        # Once each: a foreign filer's two 6-Ks were the same flag twice, and the
        # table keyed its chips on the text, which is what Next's overlay was
        # counting on the Scanner tab (2026-11-05).
        if not any(f["kind"] == kind and f["text"] == text for f in out):
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
        desc = f.get("desc") or form
        add("filing", "warn" if offering else "info",
            f"Offering filed: {desc}" if offering else form if desc == form else f"{form}: {desc}")
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
          own: dict[str, list[str]] | None = None,
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
          record: dict[str, dict[str, Any]] | None = None,
          promoted: dict[str, dict[str, Any]] | None = None,
          pool: dict[str, Any] | None = None,
          pinned: list[str] | None = None,
          top_story: Callable[[str], dict[str, Any] | None] | None = None,
          news_limit: int | None = NEWS_MAX,
          calendar_ok: bool | None = None,
          sure: Callable[[str], bool] | None = None) -> dict[str, Any]:
    """The /api/scanner payload (contract ScannerPayload). Pure.

    `sure` says whether a name's words are the table's, and so can be held against a
    headline that does not carry them (catalysts.story's `strict`); None trusts them all.

    `calendar_ok` is whether the economic calendar is loading (None: not known). No
    next release with the calendar down is a gap, not a clear morning, and the page
    must be able to say which (audit, 2026-11-11: Nasdaq had refused the feed for
    twelve hours and the page read "None scheduled").

    `promoted` is {symbol: why} for the names the pool put on the list today
    (sources/pool.py), `pool` the pool's own view and `pinned` the owner's
    list — `watchlist` is the union the rows are built for.

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
    reg["calendar_ok"] = calendar_ok
    if calendar_ok is False and reg.get("event") is None:
        reg["notes"].append("The economic calendar is not loading, so the next release is "
                            "unknown — check the day's prints before taking a level.")
    # THE TAPE COUNT BEFORE THE SCORE (marketctx.conviction_for), on the
    # technical rows as they stand: the Market line reads it, and the Market
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
    # The news this session trades on: since the previous trading day's close
    # (holidays.news_since), as minutes back from now — the catalyst's window.
    fresh_min = max(0.0, (now_ts - news_since(now.astimezone(ET), td).timestamp()) / 60.0)
    out_rows: list[dict[str, Any]] = []
    for sym in watchlist:
        base = rows_in.get(sym)
        age = round((now_ts - fetched[sym]) / 60.0, 2) if sym in fetched else None
        if base is None:
            empty = _empty(sym, age, "waiting for the first fetch")
            empty["promoted"] = (promoted or {}).get(sym)
            out_rows.append(empty)
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
        # The catalyst reads every headline it can see: the row carries the newest
        # eight, and an analyst's note on top of them must not hide the report.
        called = names_of(aliases.get(sym) or [], (own or {}).get(sym) or [])
        all_news = news_for(sym, news.get(sym) or [], wire, aliases.get(sym) or [], now,
                            limit=None, names=called, strict=sure(sym) if sure else True)
        nws = all_news[:NEWS_MAX]
        fil = [f for f in (filings.get(sym) or [])][:FILINGS_MAX]
        row["earnings"] = earn
        row["news"] = all_news if news_limit is None else all_news[:news_limit]
        row["catalyst"] = top_story(sym) if top_story else None
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
        adv = base.get("adv")
        row["adv"] = adv if isinstance(adv, (int, float)) else None
        row["premkt"] = premkt_for((premkt or {}).get(sym), row["adv"])
        # The daily frame against the live print (frame.read); the levels
        # themselves (`frame`) ride along from the bars job.
        row["frame_read"] = frame.read(base.get("frame"), row.get("last"))
        row["short"] = (shorts or {}).get(sym)
        row["promoted"] = (promoted or {}).get(sym)
        side0 = (row.get("setup") or {}).get("side")
        # The tape: the name's move against SPY since the previous close, in its daily
        # ATRs (RS) — what the news is checked against (TAPE_CLEAR).
        cat = catalyst_read(side0, earn, all_news, fil, sym=sym, names=called,
                            tape=(row.get("rs") or {}).get("SPY"), fresh_min=fresh_min,
                            day_move=day_move_of(row))
        if row.get("ok"):
            row["score"] = score_row(row, reg, srs, earn, event, session,
                                     premkt=row["premkt"], news=nws,
                                     frame_read=row["frame_read"], catalyst=cat,
                                     conviction=reg.get("conviction"), now=now)
            row["flags"] = flags_for(row, earn, event, nws, fil, session,
                                     frame_read=row["frame_read"], short=row["short"],
                                     catalyst=cat)
        else:
            row["score"] = {"total": 0, "side": None, "parts": []}
            row["flags"] = []
        if isinstance(row.get("setup"), dict):
            row["setup"] = {k: v for k, v in row["setup"].items() if k != "lost_vwap"}
        # After the score: the contract helper trades the row's side.
        fc = (flow_ctx or {}).get(sym) or {}
        row["options"] = options_for(sym, row, options, closes, iv_hist, td, now,
                                     reports=report_dates((earn_hist or {}).get(sym)),
                                     daily=(daily or {}).get(sym),
                                     oi_prev=fc.get("oi_prev"), vol_hist=fc.get("vol_hist"))
        row["score"] = liquidity_penalty(row["score"], row["options"])
        # The record line: settled signals of this kind, side and score band.
        row["record"] = record_for(implied_kind(row), row["score"].get("side"),
                                   row["score"].get("total"), record)
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

    out_rows.sort(key=rank_key)
    out_rows = rvol_gate(out_rows, session)
    # The engine's order, stamped: the page's Top 10 and Multicharts read it rather than
    # sort the capped total again (src/lib/multiChart.topScores).
    n = 0
    for r in out_rows:
        if r.get("ok") and isinstance(r.get("score"), dict):
            n += 1
            r["score"]["rank"] = n
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
        "pinned": list(pinned) if pinned is not None else list(watchlist),
        "pool": pool,
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
        "adv": None, "premkt": None, "peers": [],
        "frame": None, "frame_read": None, "short": None, "targets": [], "record": None,
        "promoted": None,
    }
