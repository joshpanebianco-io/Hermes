"""
Volume profile — where the volume actually traded, cut the way the desk trades.

THREE WINDOWS, AND WHICH ONES EXIST DEPENDS ON THE CLOCK (owner spec,
2026-09-01):

  prev RTH     the most recent COMPLETED 09:30-16:00 ET cash session — the
               reference levels everyone marks before any session.
  overnight    the most recent COMPLETED 18:00 -> 09:30 Globex session. In New
               York that is the block that ended at this morning's open; while
               Asia or London trade, tonight's is the DEVELOPING profile, so
               the completed one is the night before. Two different windows
               either way, never the same numbers twice.
  developing   anchored 18:00 ET while Asia/London trade, re-anchored 09:30
               once New York opens. The live one.

THE TWO COMPLETED ROWS ARE NAMED BY WHETHER ANYTHING HAS SUPERSEDED THEM.
"Recent" means nothing of that kind has begun since — it is still the latest
word that kind of session has said. "Prev" means a newer one exists, developing
or complete. So the kind that is developing right now is the one that pushes
its own predecessor back, and the two labels swap at 09:30 and 18:00.

THE LEVELS, not the histogram. POC is the price with the most volume (the
magnet), VAH/VAL bound the 70% value area (acceptance). They are read beside
the gamma walls: a put wall sitting on yesterday's VAL is confluence, and
confluence is the whole reason these numbers are on a news terminal.

APPROXIMATE BY CONSTRUCTION, AND LABELLED AS SUCH. True profiles are built
from ticks; these are built from 5-minute bars with each bar's volume spread
uniformly across its high-low range. On most days POC lands within a couple
of ticks of the exchange-accurate figure; on fast trend days it can sit a
node away. Context-grade, not execution-grade — the chart platforms own the
execution-grade version.

PURE. Bars in, levels out; the fetch lives in sources/profiles.py.
"""

from __future__ import annotations

from datetime import date, datetime, time, timedelta
from typing import Any
from zoneinfo import ZoneInfo

from .holidays import close_time, is_trading_day

ET = ZoneInfo("America/New_York")

RTH_OPEN = time(9, 30)
RTH_CLOSE = time(16, 0)
GLOBEX_OPEN = time(18, 0)

# GOLD'S DAY IS NOT THE EQUITY DAY (review, 2026-10-14). The COMEX day session
# runs 08:20-13:30 ET and gold settles on its last minute, so gold's "prior
# RTH" is that window — the equity 09:30-16:00 one it used to share put
# gold's value area across two and a half hours of post-settlement drift and
# missed the 08:30 data reaction entirely. Books not listed keep 09:30-16:00.
RTH_HOURS: dict[str, tuple[time, time]] = {
    "GC": (time(8, 20), time(13, 30)),
}

# The value area convention: the smallest set of bins around the POC holding
# this share of the window's volume. 70% is the standard nobody argues with.
VALUE_AREA = 0.70

# Bin sizes are chosen from a ladder of prices a human would quote, targeting
# roughly this many bins across the window — enough resolution to separate
# nodes, few enough that 5m bars can fill them meaningfully.
TARGET_BINS = 60
NICE_STEPS = [0.1, 0.25, 0.5, 1.0, 2.0, 2.5, 5.0, 10.0, 20.0, 25.0, 50.0]

# A window with fewer traded bars than this has no profile worth stating.
MIN_BARS = 6


def pick_bin(lo: float, hi: float) -> float:
    """The nice step that lands nearest TARGET_BINS across [lo, hi]."""
    span = max(hi - lo, 1e-9)
    return min(NICE_STEPS, key=lambda s: abs(span / s - TARGET_BINS))


def build(
    bars: list[tuple[float, float, float]],
) -> dict[str, Any] | None:
    """(high, low, volume) bars -> {poc, vah, val, low, high, volume, bin}.

    Each bar's volume is spread uniformly across the bins its range overlaps,
    proportional to the overlap — a bar that clips the top of a bin gives that
    bin only the clipped share. The value area grows outward from the POC,
    taking whichever neighbouring bin is heavier, until it holds VALUE_AREA of
    the total. That is the classic expansion; ties go higher, which matches
    the convention charting platforms use.
    """
    bars = [(h, low, v) for h, low, v in bars if v and v > 0 and h is not None and low is not None]
    if len(bars) < MIN_BARS:
        return None

    lo = min(b[1] for b in bars)
    hi = max(b[0] for b in bars)
    if hi <= lo:
        return None
    step = pick_bin(lo, hi)
    base = int(lo / step) * step  # snap the first edge to the grid
    nbins = int((hi - base) / step) + 1
    vol = [0.0] * nbins

    for h, low_, v in bars:
        top = max(h, low_)
        bot = min(h, low_)
        if top == bot:
            i = min(nbins - 1, max(0, int((bot - base) / step)))
            vol[i] += v
            continue
        span = top - bot
        i0 = max(0, int((bot - base) / step))
        i1 = min(nbins - 1, int((top - base) / step))
        for i in range(i0, i1 + 1):
            b_lo = base + i * step
            b_hi = b_lo + step
            overlap = min(top, b_hi) - max(bot, b_lo)
            if overlap > 0:
                vol[i] += v * (overlap / span)

    total = sum(vol)
    if total <= 0:
        return None

    poc_i = max(range(nbins), key=lambda i: (vol[i], i))  # ties go higher
    in_area = {poc_i}
    acc = vol[poc_i]
    lo_i = hi_i = poc_i
    while acc < VALUE_AREA * total and (lo_i > 0 or hi_i < nbins - 1):
        up = vol[hi_i + 1] if hi_i < nbins - 1 else -1.0
        dn = vol[lo_i - 1] if lo_i > 0 else -1.0
        if up >= dn:
            hi_i += 1
            acc += max(up, 0.0)
            in_area.add(hi_i)
        else:
            lo_i -= 1
            acc += max(dn, 0.0)
            in_area.add(lo_i)

    centre = lambda i: base + i * step + step / 2  # noqa: E731

    # THE SHAPE, in market-profile vocabulary, from where the volume sits.
    # POC in the upper third is a P (acceptance near the highs, the
    # short-covering look); lower third is a b (acceptance low, the long-
    # liquidation look); the middle is balance. A second node at least 40%
    # of the POC's weight, separated by a valley under half the lesser
    # peak, marks a double distribution — two auctions in one window, and
    # the valley between them is the reference the day trades around.
    poc_pos = (centre(poc_i) - lo) / max(hi - lo, 1e-9)
    shape = "P (accepted high)" if poc_pos >= 0.66 else (
        "b (accepted low)" if poc_pos <= 0.34 else "D (balanced)"
    )
    second_i = None
    for i in range(nbins):
        if i == poc_i or vol[i] < 0.4 * vol[poc_i]:
            continue
        a, b = sorted((i, poc_i))
        valley = min(vol[a:b + 1]) if b > a else vol[a]
        deep_valley = valley < 0.5 * min(vol[i], vol[poc_i])
        if deep_valley and (second_i is None or vol[i] > vol[second_i]):
            second_i = i
    if second_i is not None:
        shape = "double distribution"

    return {
        "poc": round(centre(poc_i), 4),
        "poc_pos": round(poc_pos, 2),
        "shape": shape,
        "second_node": round(centre(second_i), 4) if second_i is not None else None,
        "vah": round(base + (hi_i + 1) * step, 4),
        "val": round(base + lo_i * step, 4),
        "low": round(lo, 2),
        "high": round(hi, 2),
        "volume": round(total),
        "bin": step,
        "bars": len(bars),
    }


def value_position(price: float | None, vah: float | None, val: float | None) -> str | None:
    """Above value, inside value, or below value — the market-profile read.

    One classifier used for BOTH facts the report states: where the session
    OPENED relative to prior value, and where price trades NOW relative to
    each reference window. Inside is val <= p <= vah inclusive, so a print
    sitting exactly on the edge is "inside" — an auction touching its
    boundary has not left it.
    """
    if price is None or vah is None or val is None:
        return None
    if price > vah:
        return "above_value"
    if price < val:
        return "below_value"
    return "inside_value"


def prev_trading_day(d: datetime) -> datetime:
    """The NYSE trading day before `d` — holidays skipped (review, 2026-10-13).

    Weekday-only, it made Thanksgiving's thin 09:30-13:00 futures session the
    "Prev RTH" for the Friday after: the walk-back in `assemble` only fires on
    a window with NO bars, and the index futures do trade that morning.
    """
    d = d - timedelta(days=1)
    while not is_trading_day(d.date()):
        d = d - timedelta(days=1)
    return d


def rth_close(day: date, book: str | None = None) -> time:
    """16:00, or 13:00 on a half day — where that day's cash profile ends. Gold's
    is its 13:30 settlement."""
    if book in RTH_HOURS:
        return RTH_HOURS[book][1]
    return close_time(day)


def rth_open(book: str | None = None) -> time:
    """09:30, or a book's own day-session open (gold's 08:20)."""
    return RTH_HOURS[book][0] if book in RTH_HOURS else RTH_OPEN


def windows(now_et: datetime, book: str | None = None) -> list[dict[str, Any]]:
    """Which profiles exist right now, and their [start, end) instants.

    THREE REFERENCES AT ALL HOURS: the last completed RTH, the last completed
    overnight, and the session developing now. The developing window's anchor
    is the spec's whole point — 18:00 ET while Asia and London trade, 09:30
    once New York opens — and the two completed windows are the handover it is
    being read against.

    THE OVERNIGHT ROW IS THE LAST **COMPLETED** ONE, WHICH IS NOT THE SAME AS
    "last night". Inside New York that is the 18:00-09:30 block that just
    finished a few hours ago. Inside Asia or London the session forming right
    now IS an overnight, so the completed one is the night BEFORE — and it is
    still the right reference, because the level a trader checks at 23:00 is
    where the previous night's volume built, not where tonight's has got to so
    far. That second row used to be dropped entirely outside New York on the
    grounds that one set of numbers should not wear two names; correct about
    the names, wrong about the row, because the developing profile and the
    previous night are different windows and the reader wants both.

    "RECENT" VS "PREV" IS NOT DECORATION, IT IS THE COUNT. A completed window is
    RECENT while nothing of its kind has begun since — it is still the latest
    word that kind of session has said. It becomes PREV the moment a newer one
    exists, developing or complete, because there is now something in front of
    it. So the kind that is currently developing is the one that pushes its own
    predecessor back: in Asia the RTH above is the most recent cash session
    there is ("Recent RTH") while last night has already been superseded by
    tonight ("Prev overnight"), and once New York opens those two swap. In the
    16:00-18:00 lull nothing is developing, so neither has been superseded and
    both read "Recent".
    """
    d = now_et.date()
    t = now_et.time()
    o = rth_open(book)

    def close(day: date) -> time:
        return rth_close(day, book)

    def at(day: Any, tm: time) -> datetime:
        return datetime(day.year, day.month, day.day, tm.hour, tm.minute, tzinfo=ET)

    def overnight_before(ref: datetime, label: str) -> dict[str, Any]:
        """The overnight that ENDED at `ref`'s 09:30 — so 18:00 the trading day before.

        Anchored to the cash day it fed into rather than to a calendar
        subtraction, which is what carries it over weekends: on Sunday evening
        `ref` is Friday, so this is Thursday 18:00 -> Friday 09:30 rather than a
        Saturday window with no bars in it.
        """
        return {
            "key": "overnight", "label": label, "kind": "done",
            "start": at(prev_trading_day(ref), GLOBEX_OPEN), "end": at(ref, o),
        }

    out: list[dict[str, Any]] = []

    trading = is_trading_day(d)
    if o <= t < close(d) and trading:
        # New York is trading: yesterday's cash, the completed overnight, and
        # the live RTH profile off the 09:30 anchor (gold's 08:20).
        prev = prev_trading_day(now_et)
        out.append({"key": "prev_rth", "label": "Prev RTH", "kind": "done",
                    "start": at(prev, o), "end": at(prev, close(prev.date()))})
        out.append({"key": "overnight", "label": "Recent overnight", "kind": "done",
                    "start": at(prev, GLOBEX_OPEN), "end": at(d, o)})
        out.append({"key": "dev", "label": f"Live · {o:%H:%M}", "kind": "live",
                    "start": at(d, o), "end": now_et})
    elif close(d) <= t < GLOBEX_OPEN and trading:
        # Post-close lull: today's cash just completed; nothing develops
        # until Globex reopens at 18:00.
        prev = prev_trading_day(now_et)
        out.append({"key": "prev_rth", "label": "Recent RTH", "kind": "done",
                    "start": at(d, o), "end": at(d, close(d))})
        out.append({"key": "overnight", "label": "Recent overnight", "kind": "done",
                    "start": at(prev, GLOBEX_OPEN), "end": at(d, o)})
    elif t >= GLOBEX_OPEN:
        # Globex evening (Asia). Sunday's reference cash day is Friday.
        rth_day = d if trading else prev_trading_day(now_et).date()
        out.append({"key": "prev_rth", "label": "Recent RTH", "kind": "done",
                    "start": at(rth_day, o), "end": at(rth_day, close(rth_day))})
        out.append(overnight_before(at(rth_day, o), "Prev overnight"))
        out.append({"key": "dev", "label": "Live · 18:00", "kind": "live",
                    "start": at(d, GLOBEX_OPEN), "end": now_et})
    else:
        # Globex morning (late Asia / London / pre-NY), t < 09:30. The anchor
        # is yesterday 18:00 by the calendar — which on Monday morning is
        # Sunday, where the bars genuinely start.
        anchor_day = d - timedelta(days=1)
        prev = prev_trading_day(now_et)
        out.append({"key": "prev_rth", "label": "Recent RTH", "kind": "done",
                    "start": at(prev, o), "end": at(prev, close(prev.date()))})
        out.append(overnight_before(prev, "Prev overnight"))
        if now_et.weekday() < 5 and anchor_day.weekday() != 5:  # Saturday has no bars
            out.append({"key": "dev", "label": "Live · 18:00", "kind": "live",
                        "start": at(anchor_day, GLOBEX_OPEN), "end": now_et})

    return out


def assemble(
    stamps: list[int],
    highs: list[float | None],
    lows: list[float | None],
    vols: list[float | None],
    now_et: datetime,
    opens: list[float | None] | None = None,
    book: str | None = None,
) -> list[dict[str, Any]]:
    """Bars + the clock -> the profile rows the panel and digest show.

    The prev-RTH window walks back up to four trading days if its first
    candidate has no bars — that is what quietly absorbs exchange holidays
    without a holiday calendar.
    """
    rows: list[dict[str, Any]] = []
    o = rth_open(book)
    for w in windows(now_et, book):
        start, end = w["start"], w["end"]
        tries = 0
        while True:
            s_ts, e_ts = start.timestamp(), end.timestamp()
            idxs = [i for i in range(len(stamps)) if s_ts <= stamps[i] < e_ts]
            picked = [(highs[i], lows[i], vols[i] or 0.0) for i in idxs]
            # The window's OPENING PRINT — the fact "opened above/inside/
            # below prior value" is judged from. First bar with an open.
            w_open = None
            if opens is not None:
                for i in idxs:
                    if opens[i] is not None:
                        w_open = opens[i]
                        break
            prof = build([(h, low, v) for h, low, v in picked if h is not None and low is not None])
            if prof is not None or w["key"] != "prev_rth" or tries >= 4:
                break
            # A holiday: slide the whole RTH window back one trading day.
            prev = prev_trading_day(start)
            start = datetime(
                prev.year, prev.month, prev.day, o.hour, o.minute, tzinfo=ET
            )
            close = rth_close(prev.date(), book)
            end = datetime(prev.year, prev.month, prev.day, close.hour, close.minute, tzinfo=ET)
            tries += 1
        if prof is None:
            continue
        rows.append({
            **prof,
            "open": round(w_open, 2) if w_open is not None else None,
            "key": w["key"],
            "label": w["label"],
            "kind": w["kind"],
            "date": start.strftime("%a %d"),
            "start_et": start.strftime("%H:%M"),
            "end_et": "now" if w["kind"] == "live" else end.strftime("%H:%M"),
        })
    return rows
