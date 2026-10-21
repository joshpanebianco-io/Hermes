"""
The session report — a model reads the whole terminal and calls a bias.

OWNER'S DECISION, 2026-08-31: THE MODEL DOES THE ANALYSIS. The alternative on
the table was a scored rules engine that decides the bias deterministically and
cites the arithmetic behind every line, with the model used only to narrate it.
The owner chose the model-forms-the-view version knowing the trade: two runs on
identical data can disagree, and there is no arithmetic to audit when it is
wrong. That is recorded here rather than argued again.

WHAT IS DONE ANYWAY, BECAUSE IT COSTS NOTHING AND MAKES THE CALL CHECKABLE:

  1. The model is handed a CURATED DIGEST, not the raw snapshot. 250 KB of
     per-strike maps and 300 headlines would bury the signal and cost a fortune
     in tokens; ~2 kB of the figures a desk would actually read does not. What
     goes in is decided here, in `build_digest`, where it can be reviewed.
  2. Every report is STAMPED with the model, the moment, and the digest it saw.
     A bias you cannot reproduce is a bias you cannot learn from, so the inputs
     are stored beside the output.
  3. The output is a STRUCTURED OBJECT, not prose. A schema means the panel
     renders fields rather than regexing paragraphs, and it forces the model to
     commit to a direction and a conviction instead of hedging in adjectives.
     Since 2026-09-16 that object is a pre-session BRIEF, laid out like the
     owner's own morning routine: a thesis, a call per book, a regime chain
     and a read per book. Its tables are not the model's at all — see
     `build_facts`.
  4. Reports are KEPT. The one you took at 09:00 is still there at 15:00, which
     is the only way to find out whether the calls are any good.

NO KEY, NO REPORT. There is deliberately no fallback that fabricates a bias
locally — a made-up view presented in the same panel as a real one is exactly
the failure this project's sister README calls the worst thing it could do.
"""

from __future__ import annotations

import contextlib
import json
import math
import os
import re
import time
import urllib.error
import urllib.request
from datetime import UTC, datetime, timedelta
from datetime import time as dtime
from decimal import ROUND_HALF_UP, Decimal
from typing import Any
from zoneinfo import ZoneInfo

from . import releases
from .config import CACHE_DIR, UA
from .holidays import close_time, cme_closed, is_trading_day
from .profile import value_position
from .sessions import (
    GLOBEX_REOPEN,
    LONDON_DESKS,
    LONDON_OPEN_END,
    NY_OPEN,
    PRE_NY,
    globex_trade_date,
    london_at,
    overlap_end,
)

ET = ZoneInfo("America/New_York")

OPENROUTER = "https://openrouter.ai/api/v1/chat/completions"

# Free on OpenRouter and one of only a handful of free models that support
# `structured_outputs`, which the schema below depends on. Overridable because
# the free roster changes month to month.
DEFAULT_MODEL = os.environ.get("NT_REPORT_MODEL", "nvidia/nemotron-3.5-super-vl:free")

# ---------------------------------------------------------------------------
# THE FALLBACK CHAIN, AND WHY A SINGLE FREE MODEL ID IS NOT ENOUGH.
#
# A `:free` variant does not get its own capacity — it routes to a provider
# pool shared by every OpenRouter user on that model, and when the pool is
# saturated the request comes back 429 with `upstream_provider_shared_pool`. It
# is not our quota, retrying does not help, and it lasts as long as it lasts:
# the very first report generated on this desk hit it four times in a row.
#
# So the model is a LIST rather than a value. The configured model is tried
# first and the rest are tried in order, and the report records which one
# actually answered — a note written by the second choice must say so, because
# "which model wrote this" is half the provenance.
#
# Every entry supports `structured_outputs`, which is not optional here: the
# schema is what makes the model commit to a direction instead of hedging, and
# a model without it would return prose the panel cannot render.
#
# THE ROSTER ROTS (2026-10-21): `z-ai/glm-5.2:free` was delisted outright, and
# `nvidia/nemotron-3-super-120b-a12b:free` is still listed but every request
# comes back 404 "Function ... not found" from Nvidia in under a second — the
# deployment behind it is gone, not wobbling. A dead entry costs four of the
# ten attempts (two modes, two tries each), so dead ids are removed, not kept
# for luck. When a report starts failing, re-run `tools/budget_probe.py` against
# each entry before touching anything else.
FALLBACK_MODELS = [
    "dots-studio/dots-3-note-preview:free",
    "xingchen-agi/xing4.0-29b-a4b:free",
]

# HOW MUCH THE MODEL MAY THINK — A TOKEN CAP, NOT AN EFFORT LEVEL.
#
# `{"effort": "low"}` was the hint here, and Nvidia's free endpoint ignores it:
# handed the London digest, nemotron-3.5-super-vl deliberated through all
# 16,000 completion tokens and never reached the JSON (2026-10-21: one attempt,
# 230s, finish_reason=length, 37k chars of thinking). `max_tokens` on the
# reasoning block is what that provider honours, and OpenRouter maps it to an
# effort level for providers that only take one of those. Measured on the same
# digest, same model, strict schema: capped at 3,000 -> 98s, 2,999 reasoning
# tokens, a valid brief; reasoning off -> 43s, a valid brief. The cap keeps the
# short think the note was written to have, at a cost near the 90s
# _ATTEMPT_RESERVE, with room for a second attempt inside BUDGET_SEC. Shared
# with the game plan (stockplan.py); the chat has its own, smaller, in
# src/lib/ask/llm.ts.
REASONING: dict[str, Any] = {"max_tokens": 3000}

# Statuses worth trying again for. A 401 is the key and no other model will fix
# it; a 400 outside strict-schema mode is our request and moving on would hide
# it behind a different model's answer.
#
# 404 IS IN HERE, WHICH LOOKS WRONG AND IS NOT. The free Nvidia endpoint returns
# 404 intermittently for identical requests — measured with
# `server/tools/budget_probe.py`: max_tokens 200 gave 404, 3000 succeeded, 4000
# succeeded, 8000 gave "Service temporarily unavailable". It is not a route that
# does not exist and it is not a budget ceiling; it is a shared free endpoint
# falling over. Treating it as fatal ended the whole chain on a coin flip.
RETRYABLE = {404, 408, 425, 429, 500, 502, 503, 504}

# Provider-level wobbles that arrive as a 200 with an `error` body rather than
# as a status code.
TRANSIENT_TEXT = re.compile(
    r"temporarily|rate.?limit|unavailable|overload|capacity|try again|timeout",
    re.I,
)

# Tries per (model, mode) pair before moving on, and the ceiling on the lot.
# The failures above are intermittent, so one extra try converts most of them;
# the cap stops a bad afternoon turning one press of Generate into thirty
# requests against a free quota.
TRIES_PER_PAIR = 2
MAX_ATTEMPTS = 10

# A WALL-CLOCK CEILING, because the attempt count alone does not bound anything.
#
# Ten attempts at up to ninety seconds each is fifteen minutes, and a GC report
# generated during a saturated afternoon ran past the route handler's own 290s
# timeout — the browser gave up on a generation the collector was still paying
# for. Attempts are only STARTED while there is budget left, so the last one
# can still overrun by its own timeout; 210 plus a 70s request fits inside the
# route's window with room to return the failure.
BUDGET_SEC = 210.0
REQUEST_TIMEOUT_SEC = 70

# What one attempt is assumed to cost when deciding whether to start another.
#
# Larger than REQUEST_TIMEOUT_SEC on purpose. That constant is passed to
# `urlopen`, whose timeout applies to each socket operation rather than to the
# request as a whole, so a response that arrives slowly but steadily can run
# far past it — observed at ~150s per attempt against a saturated free pool
# while the socket option said 70. This is the figure the budget reserves, so
# the endpoint's worst case is roughly BUDGET_SEC rather than BUDGET_SEC plus
# one unbounded request.
_ATTEMPT_RESERVE = 90.0


def model_chain(preferred: str) -> list[str]:
    """The configured model first, then the others, without duplicates."""
    chain = [preferred]
    chain.extend(m for m in FALLBACK_MODELS if m != preferred)
    return chain

REPORTS_DIR = os.path.join(CACHE_DIR, "reports")
KEEP = 40


def _key() -> str:
    return os.environ.get("OPENROUTER_API_KEY", "").strip()


# --------------------------------------------------------------------------
# The digest — what the model is allowed to see.
# --------------------------------------------------------------------------


def _q(quotes: list[dict[str, Any]], key: str) -> dict[str, Any] | None:
    return next((q for q in quotes if q.get("key") == key), None)


# --------------------------------------------------------------------------
# How old each price is.
#
# THE DIGEST USED TO CARRY NO AGES AT ALL (review, 2026-10-14). The CME futures
# quotes run about ten minutes behind the exchange, and after the cash close
# the 10-year's last print was 14:59 ET for the rest of the night — and the
# brief read every one of them as "now". The board rows now say what they are
# (`feed`, from quotes.feed_state); an older snapshot without it falls back to
# the print's own age.
# --------------------------------------------------------------------------

#: A print older than this, with no `feed` to say otherwise, is not current.
NOT_CURRENT_MIN = 30.0
FUTURES_DELAY_NOTE = (
    "CME futures quotes (NQ, ES, GC, YM, RTY, crude, metals, the note futures) come "
    "via Yahoo about 10 minutes behind the exchange"
)


def _print_age(q: dict[str, Any], now: datetime | None) -> tuple[str | None, str | None]:
    """(feed, last print in ET) for one board row. `feed` is live, delayed,
    stale or closed, or None when nothing says. Pure."""
    feed = q.get("feed") if isinstance(q.get("feed"), str) else None
    qt = q.get("quote_time")
    if not isinstance(qt, int | float) or qt <= 0 or now is None:
        return feed, None
    when = datetime.fromtimestamp(qt, ET)
    if feed is None and (now.timestamp() - qt) / 60.0 > NOT_CURRENT_MIN:
        feed = "stale"
    return feed, when.strftime("%H:%M ET" if when.date() == now.date() else "%a %H:%M ET")


def _not_current(q: dict[str, Any] | None, now: datetime | None) -> str | None:
    """"last print 14:59 ET" for a row that is stale or shut, else None."""
    if not q:
        return None
    feed, label = _print_age(q, now)
    if feed in ("stale", "closed") and label:
        return f"last print {label}"
    return None


def _brief(q: dict[str, Any] | None, now: datetime | None = None) -> dict[str, Any] | None:
    """One instrument, trimmed to what a read actually uses — and, when its
    last print is not current, when that was."""
    if not q:
        return None
    out: dict[str, Any] = {
        "last": q.get("last"),
        "pct": round(q["pct"], 2) if q.get("pct") is not None else None,
    }
    feed, label = _print_age(q, now)
    if feed in ("stale", "closed") and label:
        out["not_current"] = f"{feed}: last print {label}"
    if q.get("range_pos") is not None:
        # Where in the day's range the last print sits — the figure that says
        # whether a gain is being held or given back.
        out["day_range_pos"] = round(q["range_pos"], 2)
    if q.get("high") is not None and q.get("low") is not None:
        out["day_high"], out["day_low"] = q["high"], q["low"]
    return out


# --------------------------------------------------------------------------
# Which session the note is for.
#
# THIS DESK TRADES THREE OF THEM. A note written for the New York open is the
# wrong note at 20:00 ET when Tokyo is about to go, and the difference is not
# cosmetic: the instruments that lead are different, the calendar is different,
# the liquidity is different, and what "overnight" even refers to inverts. So
# the session is a parameter, `auto` resolves it from the ET clock, and the
# prompt below is assembled around whichever one is chosen.
# --------------------------------------------------------------------------

# WHAT LEADS EACH SESSION NAMES ONLY WHAT THE DIGEST CARRIES (review,
# 2026-10-14). London's line listed "Bunds and Gilts", which the data has never
# held, and a stored brief duly cited a Gilt move nobody had measured. Every
# instrument named here is a row the digest prints.
#
# The hours are not here: they move with the clocks, and `session_hours`
# writes them for the day the note is for.
SESSIONS: dict[str, dict[str, str]] = {
    "asia": {
        "label": "Asia",
        "leads": "Nikkei, Hang Seng, Shanghai, KOSPI, ASX; USD/JPY, AUD/USD, USD/CNY",
        "handover": "New York's close is the handover — Asia opens reacting to it",
        "character": (
            "Thinner than New York. Index futures often range unless a regional print or "
            "a policy headline moves them, and USD/JPY tends to lead the Nasdaq future "
            "rather than follow it. Gamma walls hold more easily in thin liquidity."
        ),
    },
    "london": {
        "label": "London",
        "leads": "FTSE, DAX, Euro Stoxx; EUR/USD, GBP/USD; the US curve as Europe trades it",
        "handover": "Asia's session is the handover — London reprices what Asia did",
        "character": (
            "The first real liquidity of the day. London routinely takes out the Asia "
            "high or low and either extends or reverses it, so where price sits against "
            "the Asia range is the single most useful fact at 03:00."
        ),
    },
    "ny": {
        "label": "New York",
        "leads": "NQ/ES/YM/RTY, the sector SPDRs, the Treasury curve, the dollar",
        "handover": "Asia and London are the handover — the US opens into their range",
        "character": (
            "The deepest liquidity and the widest ranges. The 08:30 data window and the "
            "09:30 open set the day; dealer gamma matters most here because the option "
            "volume that creates it is American."
        ),
    },
}


# --------------------------------------------------------------------------
# Which book the note is about.
#
# `all` is the default and covers the three together, which is the right note
# when you are deciding what to trade. The single-asset choices are for when
# you have already decided: they narrow the gamma, the session ranges and the
# index movers to that instrument and tell the model what drives it.
#
# GOLD IS NOT A THIRD EQUITY INDEX, and the `drivers` line is where that is
# said. Sector rotation and index constituents explain NQ and ES and explain
# nothing about GC — real rates, the dollar and geopolitics do. A single-asset
# note that dutifully worked through XLK's relative strength on the way to a
# gold call would be padding at best.
# --------------------------------------------------------------------------

# Which quotes ARE each book, as opposed to context for it. Kept beside ASSETS
# so the focus split and the prose describing it cannot drift apart.
BOOK_KEYS: dict[str, tuple[str, ...]] = {
    "NQ": ("NQ_futures", "QQQ"),
    "ES": ("ES_futures", "SPY"),
    "GC": ("GC_gold_futures", "GLD"),
}

ASSETS: dict[str, dict[str, str]] = {
    "all": {
        "label": "NQ · ES · GC",
        "instruments": "NQ/QQQ, ES/SPY and GC/GLD",
        "drivers": (
            "Cover all three. Say where they agree and, more usefully, where they do not — "
            "equities and gold diverging is itself the read."
        ),
    },
    "NQ": {
        "label": "NQ",
        "instruments": "NQ futures and QQQ",
        "drivers": (
            "The Nasdaq 100 is cap-weighted and its top handful of names are about 43% of it, "
            "so `index_movers` usually IS the story. It is the longest-duration equity index, "
            "so the front of the curve and the policy path hit it hardest. Technology's "
            "relative strength matters more here than the rest of the sector table."
        ),
    },
    "ES": {
        "label": "ES",
        "instruments": "ES futures and SPY",
        "drivers": (
            "Broader than the Nasdaq, so sector rotation carries more of the explanation and "
            "no single name dominates the way it does in NQ. Breadth — equal weight against "
            "cap weight — says whether a move is the whole market or the top of it."
        ),
    },
    "GC": {
        "label": "GC",
        "instruments": "GC futures and GLD",
        "drivers": (
            "Gold is NOT an equity index and the equity blocks mostly do not apply to it. "
            "What moves it: real yields and the policy path, the dollar, and geopolitical "
            "risk. Ignore sector rotation and index constituents unless equities are moving "
            "hard enough to be a risk signal in their own right."
        ),
    },
}


def resolve_asset(want: str) -> str:
    return want if want in ASSETS else "all"


# --------------------------------------------------------------------------
# When each session actually runs.
#
# EVERY BOUNDARY ON ITS OWN CITY'S CLOCK, FROM sessions.py (review,
# 2026-10-14). These were ET constants — London from 02:00, Asia to 03:00 —
# an hour out for the weeks the UK's and the US's clocks disagree, and one of
# three different definitions of London across the terminal. Now:
#
#   asia     18:00 ET     -> 07:00 London   Sun–Thu evenings Globex reopens
#   london   07:00 London -> 08:00 ET       weekdays Globex trades
#   ny       09:30 ET     -> NYSE close     NYSE trading days
#
# AND ONLY ON THE DAYS IT RUNS. The clock used to be pure time-of-day, so it
# called Friday 20:30 ET "Asia, 2h 30m in" with Globex shut for the weekend,
# and Saturday 10:00 and Thanksgiving morning "New York underway". A session
# is underway only inside an occurrence that actually happened.
# --------------------------------------------------------------------------

# How long before its bell the note becomes New York's: the 07:30 switch
# `auto` has always made, so the London note stops at the US pre-open.
NY_LEAD_MIN = 120


def _session_spans(session: str, around: datetime) -> list[tuple[datetime, datetime]]:
    """Every (open, close) of `session` from two days before `around` to nine
    after, in ET, skipping the days it does not run. Pure."""
    base = around.astimezone(ET).date()
    out: list[tuple[datetime, datetime]] = []
    for k in range(-2, 10):
        d = base + timedelta(days=k)
        if session == "asia":
            if d.weekday() not in (6, 0, 1, 2, 3):
                continue
            opened = datetime.combine(d, GLOBEX_REOPEN, tzinfo=ET)
            trade = globex_trade_date(opened)
            if cme_closed(trade):
                continue
            closed = london_at(trade, LONDON_DESKS).astimezone(ET)
        elif session == "london":
            if d.weekday() >= 5 or cme_closed(d):
                continue
            opened = london_at(d, LONDON_DESKS).astimezone(ET)
            closed = datetime.combine(d, PRE_NY, tzinfo=ET)
        else:
            if not is_trading_day(d):
                continue
            opened = datetime.combine(d, NY_OPEN, tzinfo=ET)
            closed = datetime.combine(d, close_time(d), tzinfo=ET)
        out.append((opened, closed))
    return out


def _hm(t: datetime) -> str:
    return t.astimezone(ET).strftime("%H:%M")


def session_hours(session: str, opened: datetime) -> str:
    """The session's hours in ET for the occurrence that opens at `opened`,
    with the cities that define it — right in the mismatch weeks and in both
    halves of the year. The prompt's Tokyo hours were an EST-only constant,
    an hour out all summer. Pure."""
    if session == "asia":
        trade = globex_trade_date(opened)
        end = london_at(trade, LONDON_DESKS)

        def city(zone: str, o: dtime, c: dtime) -> str:
            tz = ZoneInfo(zone)
            return (f"{_hm(datetime.combine(trade, o, tzinfo=tz))}–"
                    f"{_hm(datetime.combine(trade, c, tzinfo=tz))}")

        return (f"{_hm(opened)}–{_hm(end)} ET (Tokyo "
                f"{city('Asia/Tokyo', dtime(9, 0), dtime(15, 30))}, Hong Kong "
                f"{city('Asia/Hong_Kong', dtime(9, 30), dtime(16, 0))} ET)")
    d = opened.astimezone(ET).date()
    if session == "london":
        win_end = london_at(d, LONDON_OPEN_END)
        lse_open = london_at(d, dtime(8, 0))
        return (f"{_hm(opened)}–08:00 ET; the OPEN window is {_hm(opened)}–{_hm(win_end)} ET "
                f"(07:00–10:00 London: European futures from {_hm(opened)}, "
                f"LSE cash {_hm(lse_open)}–{_hm(overlap_end(d))} ET)")
    return (f"09:30–{close_time(d):%H:%M} ET, with the London overlap 08:00–"
            f"{_hm(overlap_end(d))} ET around the open")


def session_progress(session: str, now_et: datetime) -> dict[str, Any]:
    """Where `now` sits against the session the note is being written for.

    THE FACT THE BRIEF WAS MISSING. Everything downstream — the prompt's field
    descriptions, the panel's headings — was written for a note composed BEFORE
    the bell: "the call for the start of the session", "where price sits at the
    start". Pressing Generate five hours into Asia produced exactly that note, a
    call for an open that had already happened, read against levels price had
    long since left. The digest carried `as_of_et` all along, but the field spec
    said "at the start" and the field spec won.

    So this states it outright and the prompt branches on it. `underway` is the
    load-bearing bit; the minutes are what let the note say how far in it is.
    Elapsed time is measured on timestamps, so the night the clocks change
    counts its real minutes.
    """
    now = now_et.astimezone(ET)
    key = session if session in SESSIONS else "ny"
    spans = _session_spans(key, now)
    for opened, closed in spans:
        if opened <= now < closed:
            minutes_in = int((now.timestamp() - opened.timestamp()) / 60.0)
            return {
                "underway": True,
                "minutes_in": minutes_in,
                "opened_et": _hm(opened),
                "phrase": _span(minutes_in),
                "hours": session_hours(key, opened),
            }
    opens = next((o for o, _ in spans if o > now), None)
    if opens is None:  # unreachable with a ten-day walk; never fatal
        return {"underway": False, "minutes_until": None, "opens_et": None,
                "phrase": "", "hours": ""}
    minutes_until = max(0, int((opens.timestamp() - now.timestamp()) / 60.0))
    return {
        "underway": False,
        "minutes_until": minutes_until,
        # The weekday when it is not today: "Sun 18:00", not an 18:00 that
        # reads as tonight on a Friday.
        "opens_et": opens.strftime("%H:%M" if opens.date() == now.date() else "%a %H:%M"),
        "phrase": _span(minutes_until),
        "hours": session_hours(key, opens),
    }


def resolve_session(clock: dict[str, Any], want: str = "auto") -> str:
    """Which session a note is being written for.

    `auto` resolves to the session that is trading now, or else the one that
    opens next — which is what someone pressing Generate almost always means.
    New York takes over two hours before its bell. Between 16:00 and 18:00 ET,
    over a weekend and on Thanksgiving morning nothing is running, and the
    honest answer is the one that opens next: Asia, on Sunday evening if need
    be — never a New York "underway" with the market shut.
    """
    if want in SESSIONS:
        return want
    try:
        now = datetime.fromisoformat(str(clock.get("et"))).astimezone(ET)
    except ValueError:
        return "ny"
    progs = {k: session_progress(k, now) for k in SESSIONS}
    ny = progs["ny"]
    if ny["underway"] or (ny.get("minutes_until") or 10**9) <= NY_LEAD_MIN:
        return "ny"
    for k in ("london", "asia"):
        if progs[k]["underway"]:
            return k
    return min(SESSIONS, key=lambda k: progs[k].get("minutes_until") or 10**9)


def _span(minutes: int) -> str:
    """90 -> "1h 30m", 2790 -> "1d 22h 30m". Rounded to the minute; nobody reads
    seconds off a brief."""
    days, rest = divmod(max(0, minutes), 24 * 60)
    h, m = divmod(rest, 60)
    parts = [f"{days}d"] if days else []
    if h:
        parts.append(f"{h}h")
    if m or not parts:
        parts.append(f"{m}m")
    return " ".join(parts)


def _vp_reads(asset: dict[str, Any], session: str) -> dict[str, Any]:
    """The open-vs-value and now-vs-value facts for one asset's profiles."""
    rows = {r.get("key"): r for r in (asset.get("rows") or [])}
    out: dict[str, Any] = {}
    prev = rows.get("prev_rth")
    dev = rows.get("dev")
    last = asset.get("last")

    if dev is not None and prev is not None and dev.get("open") is not None:
        pos = value_position(dev["open"], prev.get("vah"), prev.get("val"))
        if pos:
            # NAMED FOR WHAT IT IS, AFTER IT WAS CITED AS SOMETHING ELSE. This
            # was `session_open`, and a London brief read that as London's open
            # and printed "The London session opened at 29,263.75" — a real
            # number from this very field, which was the 18:00 ET Globex open,
            # because the developing profile is still anchored at 18:00 all the
            # way to 09:30. The key now names its anchor, and says in-band what
            # it is not.
            out["developing_profile_open"] = {
                "price": dev["open"],
                "anchored_et": dev.get("start_et"),
                "this_is": (
                    f"the opening print of the profile developing since "
                    f"{dev.get('start_et')} ET — NOT the open of the session this "
                    f"note is written for. For that, use session_ranges[].open."
                ),
                "vs_prev_rth_value": pos,
            }

    if last is not None:
        now: dict[str, Any] = {"price": last}
        for key, name in (
            ("prev_rth", "vs_prev_rth_value"),
            ("overnight", "vs_overnight_value"),
        ):
            # THE OVERNIGHT ROW USED TO BE DROPPED OUTSIDE NEW YORK, because
            # `windows()` only emitted one during RTH and a note written for
            # Asia would otherwise have cited a window that was still forming.
            # It now emits the last COMPLETED overnight at every hour, which is
            # a real reference in every session — so price is read against it in
            # every session too.
            r = rows.get(key)
            if r is None:
                continue
            pos = value_position(last, r.get("vah"), r.get("val"))
            if pos:
                now[name] = pos
        if len(now) > 1:
            out["price_now"] = now
    return out


# --------------------------------------------------------------------------
# The brief's facts — every figure on the page that is not an opinion.
#
# THE ENGINE COMPUTES, THE MODEL NARRATES, and the brief is where that line is
# drawn hardest. A pre-session brief is mostly tables: the snapshot, the levels
# ladder, the gamma card, the catalysts, the ratio strip. Had the model written
# them, every figure on the page would be a transcription that could slip, and
# a mistyped call wall in a table looks exactly as authoritative as a real one.
# So they are built here, stored beside the report, and rendered by the panel
# from this object. The model is shown the same numbers in the digest and
# writes only the read, pointing at rows by `id` or `key` when it annotates.
# --------------------------------------------------------------------------

BOOKS: tuple[str, ...] = ("NQ", "ES", "GC")
BOOK_LABELS = {"NQ": "NQ", "ES": "ES", "GC": "Gold (GC)"}
# Decimals a level is quoted to: NQ in whole points, ES in quarters, gold in
# tenths. A ladder printing 29,408.00 carries three characters of noise a row.
BOOK_DP = {"NQ": 0, "ES": 2, "GC": 1}

# The implied vol that stands in for the expected move when GEXYGEN is not
# answering: a one-day, one-standard-deviation move. Labelled as exactly that
# on the page, because it is wider than an options desk's own band and must not
# be mistaken for it.
EM_VOL = {"NQ": "VXN", "ES": "VIX", "GC": "GVZ"}

# Rank-2 and rank-3 walls make the ladder only within this many expected moves
# of price. All seven gamma levels plus the ranges would bury the three prices
# the session actually trades against: at 2.5 the first live NQ ladder ran to
# seventeen rows.
WALL_REACH_EM = 1.5

# The ratio strip. Every ratio reads "the first leg against the second": up
# means the first is winning. Legs come from the sector SPDRs or the daily
# context block.
EQUITY_RATIOS: list[tuple[str, str, str]] = [
    ("XLK/XLU", "XLK", "XLU"),
    ("XLK/SPY", "XLK", "SPY"),
    ("XLC/XLP", "XLC", "XLP"),
    ("QQQ/IWM", "QQQ", "IWM"),
    ("QQQ/SPY", "QQQ", "SPY"),
    ("XLP/SPY", "XLP", "SPY"),
]
GOLD_RATIOS: list[tuple[str, str, str]] = [
    ("GDX/GLD", "GDX", "GLD"),
    ("Gold/Silver", "GC", "SILVER"),
]
# A five-day ratio change inside this band is flat. Two ETFs rarely finish a
# week at exactly the same return, and an arrow on a 0.1% drift is an arrow on
# noise.
RATIO_FLAT_PCT = 0.25

# The collector blocks the brief leans on, worded for its partial-data banner.
BRIEF_SOURCES = {
    "quotes": "Quotes",
    "gex": "GEXYGEN gamma levels",
    "ranges": "Session ranges",
    "profiles": "Volume profiles",
    "context": "Daily history (week and month changes)",
    "sectors": "Sector ETFs",
    "calendar": "Economic calendar",
    "rates": "Treasury curve",
    "constituents": "Index constituents",
    "wire": "Wire",
}


def books_for(asset: str) -> list[str]:
    """The books a brief carries a call for."""
    book = resolve_asset(asset)
    return list(BOOKS) if book == "all" else [book]


def _ctx(snap: dict[str, Any], key: str) -> dict[str, Any] | None:
    return next((r for r in snap.get("context") or [] if r.get("key") == key), None)


def _now_et(snap: dict[str, Any]) -> datetime:
    """The snapshot's own clock, so the facts describe the moment the data does."""
    try:
        return datetime.fromisoformat(str((snap.get("clock") or {}).get("et"))).astimezone(ET)
    except ValueError:
        return datetime.now(ET)


def _when_label(when: datetime, now: datetime) -> str:
    """Calendar time the way a desk says it: Today 08:30 ET, Tomorrow 14:00 ET, Thu 22:30 ET."""
    days = (when.date() - now.date()).days
    hm = when.strftime("%H:%M")
    if days == 0:
        return f"Today {hm} ET"
    if days == 1:
        return f"Tomorrow {hm} ET"
    return f"{when:%a} {hm} ET"


def _stamp_label(utc: str | None, now: datetime) -> str:
    """A headline's filing time in ET — bare when today, with the weekday when not."""
    if not utc:
        return ""
    try:
        when = datetime.fromisoformat(utc).astimezone(ET)
    except ValueError:
        return ""
    return when.strftime("%H:%M ET" if when.date() == now.date() else "%a %H:%M ET")


def _srow(
    key: str,
    label: str,
    last: float | None,
    dp: int,
    *,
    chg: float | None = None,
    unit: str = "pct",
    last2: float | None = None,
    suffix: str = "",
    tag: str | None = None,
    sub: str = "",
) -> dict[str, Any]:
    return {
        "key": key, "label": label, "last": last, "last2": last2, "dp": dp,
        "suffix": suffix, "chg": round(chg, 3) if chg is not None else None,
        "chg_unit": unit, "tag": tag, "sub": sub or None,
    }


def _wk_mo(row: dict[str, Any] | None, month: bool = False) -> list[str]:
    out: list[str] = []
    if row and row.get("week_pct") is not None:
        out.append(f"wk {row['week_pct']:+.1f}%")
    if row and month and row.get("month_pct") is not None:
        out.append(f"1M {row['month_pct']:+.1f}%")
    return out


def _snapshot(
    snap: dict[str, Any], books: list[str], now: datetime | None = None
) -> list[dict[str, Any]]:
    """The handful of instruments the brief is read against, each with its context.

    A row whose last print is not current says so in its sub-line ("last print
    14:59 ET"), on the page as well as in the digest."""
    quotes = snap.get("quotes") or []

    def aged(q: dict[str, Any] | None, bits: list[str]) -> str:
        stamp = _not_current(q, now)
        return " · ".join([*bits, stamp] if stamp else bits)

    rates = snap.get("rates") or {}
    equity = any(b in books for b in ("NQ", "ES"))
    rows: list[dict[str, Any]] = []

    for b in books:
        q = _q(quotes, b)
        if not q:
            continue
        bits: list[str] = []
        if q.get("prev") is not None:
            bits.append(f"settle {q['prev']:,.{BOOK_DP[b]}f}")
        bits += _wk_mo(_ctx(snap, b), month=True)
        rows.append(_srow(b, BOOK_LABELS[b], q["last"], BOOK_DP[b], chg=q.get("pct"),
                          sub=aged(q, bits)))

    dxy = _q(quotes, "DXY")
    if dxy:
        rows.append(_srow("DXY", "DXY", dxy["last"], 2, chg=dxy.get("chg"), unit="pts",
                          sub=aged(dxy, _wk_mo(_ctx(snap, "DXY")))))

    ten = _q(quotes, "US10Y")
    if ten:
        bits = []
        closes = (_ctx(snap, "US10Y") or {}).get("closes") or []
        if len(closes) >= 6:
            bits.append(f"{closes[-6]:.2f} → {ten['last']:.2f} in 5 sessions")
        if ten.get("wk52_high") and ten["last"] >= ten["wk52_high"] - 0.02:
            bits.append("at its 52-week high")
        rows.append(_srow(
            "US10Y", "US 10Y", ten["last"], 2, suffix="%", unit="bp",
            chg=ten["chg"] * 100.0 if ten.get("chg") is not None else None,
            sub=aged(ten, bits),
        ))

    if "GC" in books:
        real = next((r for r in rates.get("real") or [] if r.get("key") == "10Y real"), None)
        if real:
            be = next((s for s in rates.get("spreads") or [] if s.get("key") == "be10"), None)
            bits = [f"breakeven {be['value']:.2f}%"] if be else []
            if rates.get("real_as_of"):
                bits.append(f"Treasury {rates['real_as_of']}")
            rows.append(_srow("REAL10", "10Y real", real["value"], 2, suffix="%", unit="bp",
                              chg=real.get("chg_bp"), sub=" · ".join(bits)))

    if equity:
        vix, vxn, v3 = _q(quotes, "VIX"), _q(quotes, "VXN"), _q(quotes, "VIX3M")
        vt = snap.get("volterm") or {}
        if vix or vxn:
            bits = [f"VIX3M {v3['last']:.1f}"] if v3 else []
            if vt.get("ratio") is not None:
                bits.append(f"VIX/VIX3M {vt['ratio']:.2f}")
            shape = str(vt.get("shape") or "")
            rows.append(_srow(
                "VOL", "VIX / VXN", (vix or {}).get("last"), 1, last2=(vxn or {}).get("last"),
                tag=shape.capitalize() if shape not in {"", "unknown"} else None,
                sub=aged(vix or vxn, bits),
            ))

    if "GC" in books:
        gvz = _ctx(snap, "GVZ")
        if gvz:
            rows.append(_srow("GVZ", "GVZ", gvz["last"], 1, chg=gvz.get("day_pct"),
                              sub=" · ".join(_wk_mo(gvz))))

    wti = _q(quotes, "WTI")
    if wti:
        rows.append(_srow("WTI", "WTI", wti["last"], 2, chg=wti.get("pct"),
                          sub=aged(wti, _wk_mo(_ctx(snap, "WTI"), month=True))))

    jpy = _q(quotes, "USDJPY")
    if jpy:
        rows.append(_srow("USDJPY", "USD/JPY", jpy["last"], 2, chg=jpy.get("chg"), unit="pts",
                          sub=aged(jpy, _wk_mo(_ctx(snap, "USDJPY")))))

    if "GC" in books:
        si = _q(quotes, "SILVER")
        if si:
            rows.append(_srow("SILVER", "Silver", si["last"], 2, chg=si.get("pct"),
                              sub=aged(si, _wk_mo(_ctx(snap, "SILVER")))))
    return rows


def _gex_asset(snap: dict[str, Any], book: str) -> dict[str, Any]:
    result: dict[str, Any] = ((snap.get("gex") or {}).get("assets") or {}).get(book) or {}
    return result


def _expected_move(
    snap: dict[str, Any], book: str, last: float
) -> tuple[float | None, str | None, float | None, float | None]:
    """(half-width, basis, low, high): GEXYGEN's own band first, implied vol second."""
    g = _gex_asset(snap, book)
    hi, lo = g.get("em_hi"), g.get("em_lo")
    if g.get("ok") and hi is not None and lo is not None and hi > lo:
        return (hi - lo) / 2.0, "GEXYGEN", float(lo), float(hi)
    key = EM_VOL[book]
    src = _q(snap.get("quotes") or [], key) or _ctx(snap, key)
    iv = (src or {}).get("last")
    if not iv:
        return None, None, None, None
    em = last * float(iv) / 100.0 / math.sqrt(252.0)
    return em, f"1σ from {key} {float(iv):.1f}", last - em, last + em


def _ladder(
    snap: dict[str, Any], book: str, session: str, now: datetime
) -> dict[str, Any] | None:
    """Every price the session trades against, in price order, measured from last."""
    q = _q(snap.get("quotes") or [], book) or {}
    rng = ((snap.get("ranges") or {}).get("assets") or {}).get(book) or {}
    last = q.get("last") if q.get("last") is not None else rng.get("last")
    if last is None:
        return None
    dp = BOOK_DP[book]
    em, em_basis, em_lo, em_hi = _expected_move(snap, book, last)
    rows: list[dict[str, Any]] = []

    def add(price: Any, label: str, kind: str) -> None:
        if isinstance(price, int | float):
            rows.append({"price": float(price), "label": label, "kind": kind})

    g = _gex_asset(snap, book)
    if g.get("ok"):
        for lv in g.get("levels") or []:
            near = em is not None and abs(lv["price"] - last) <= WALL_REACH_EM * em
            if lv.get("side") == "flip" or lv.get("rank") == 1 or near:
                add(lv["price"], lv["label"], lv.get("side") or "ref")
    if em_lo is not None and em_hi is not None:
        add(em_hi, "Expected move high", "em")
        add(em_lo, "Expected move low", "em")

    # WHICH RANGE IS "THE OVERNIGHT" DEPENDS ON THE SESSION BEING WRITTEN FOR.
    # New York opens into everything traded since 18:00; London opens into
    # Asia. An Asia note's handover is the New York day, which the prior-RTH
    # rows below already carry, so it gets no range row of its own.
    sessions = {s.get("key"): s for s in rng.get("sessions") or [] if s.get("ok")}
    handover = {
        "ny": (("asia", "london", "euro_mid", "preny"), "ON"),
        "london": (("asia",), "Asia"),
    }
    if session in handover:
        keys, prefix = handover[session]
        # TODAY'S WINDOWS ONLY (review, 2026-10-14). At 07:50 ET the Pre-NY row
        # is yesterday's — its window has not come round again — and it went
        # into the max with the rest, so the ladder printed yesterday's high,
        # 31,089, as the "ON high" against a true overnight high of 30,906.
        # The ranges flag such rows `prior_day`; they are not the overnight.
        picked = [sessions[k] for k in keys
                  if k in sessions and not sessions[k].get("prior_day")]
        if picked:
            add(max(s["high"] for s in picked), f"{prefix} high", "range")
            add(min(s["low"] for s in picked), f"{prefix} low", "range")
    hour = now.hour + now.minute / 60.0
    if (session == "ny" and 9.5 <= hour < 16.0 and "ny" in sessions
            and not sessions["ny"].get("prior_day")):
        add(sessions["ny"]["high"], "RTH high so far", "range")
        add(sessions["ny"]["low"], "RTH low so far", "range")

    prof = ((snap.get("profiles") or {}).get("assets") or {}).get(book) or {}
    prev = next((r for r in prof.get("rows") or [] if r.get("key") == "prev_rth"), None)
    if prof.get("ok") and prev:
        add(prev.get("high"), "Prior RTH high", "ref")
        add(prev.get("low"), "Prior RTH low", "ref")
        add(prev.get("poc"), "Prior RTH POC", "ref")
    add(q.get("prev"), "Prior settle", "ref")

    out: list[dict[str, Any]] = []
    seen: set[tuple[float, str]] = set()
    for r in sorted(rows, key=lambda r: -r["price"]):
        if (round(r["price"], 2), r["label"]) in seen:
            continue
        seen.add((round(r["price"], 2), r["label"]))
        r["dist"] = round(r["price"] - last, dp)
        r["inside_em"] = em_lo is not None and em_hi is not None and em_lo <= r["price"] <= em_hi
        out.append(r)
    # Last goes in after the sort, below any level printing at exactly spot,
    # so float noise cannot shuffle a wall to the wrong side of price.
    at = next((i for i, r in enumerate(out) if r["price"] < last), len(out))
    out.insert(at, {"price": float(last), "label": "Last", "kind": "last",
                    "dist": None, "inside_em": True})

    notes: list[str] = []
    if not g.get("ok"):
        notes.append("No gamma levels for this book: GEXYGEN is not answering for it.")
    elif g.get("regime") == "NEG":
        notes.append("Negative gamma: dealer hedging chases moves, so a wall that gives way "
                     "tends to accelerate the break rather than stop it.")
    elif g.get("regime") == "POS":
        notes.append("Positive gamma: dealer hedging leans against moves, so the walls tend "
                     "to hold and price pins between them.")
    if em_basis and em_basis != "GEXYGEN":
        notes.append(f"Expected move is a one-day {em_basis}, not GEXYGEN's band.")
    return {
        "book": book, "label": BOOK_LABELS[book], "last": float(last), "dp": dp,
        "em": round(em, dp) if em is not None else None, "em_basis": em_basis,
        "rows": out, "note": " ".join(notes) or None,
    }


def _gamma_card(
    snap: dict[str, Any], book: str, ladder: dict[str, Any] | None
) -> dict[str, Any] | None:
    """The dealer-gamma summary for one book: regime, flip distance, walls."""
    g = _gex_asset(snap, book)
    if not g.get("ok"):
        return None
    lv = {x["key"]: x["price"] for x in g.get("levels") or []}
    last = (ladder or {}).get("last") or g.get("spot")
    flip, em = lv.get("flip"), (ladder or {}).get("em")
    dp = BOOK_DP[book]
    dist = (flip - last) if (flip is not None and last) else None
    return {
        "book": book, "label": BOOK_LABELS[book], "dp": dp, "regime": g.get("regime"),
        "last": last, "flip": flip,
        "flip_dist": round(dist, dp) if dist is not None else None,
        "flip_dist_pct": round(dist / last * 100.0, 2) if dist is not None else None,
        # How many expected moves away the flip sits: "0.7% away" says little
        # until it is known whether today prices a 0.5% or a 2% range.
        "flip_em": round(abs(dist) / em, 1) if (dist is not None and em) else None,
        "call_wall": lv.get("call_1"), "put_wall": lv.get("put_1"),
        "em": em, "em_basis": (ladder or {}).get("em_basis"),
    }


def _cat(kind: str, at: datetime, now: datetime, title: Any, **extra: Any) -> dict[str, Any]:
    # `at`, not `when`: earnings override the `when` LABEL through **extra
    # ("Today after the close"), and a parameter of the same name made that
    # call a TypeError the moment a bellwether reported.
    item: dict[str, Any] = {
        "kind": kind, "ts": at.timestamp(), "when": _when_label(at, now), "title": title,
        "country": None, "lands_in_session": None, "released": False, "actual": None,
        "consensus": None, "previous": None, "surprise": None, "high": False, "note": None,
    }
    item.update(extra)
    return item


def _catalysts(snap: dict[str, Any], books: list[str], now: datetime) -> list[dict[str, Any]]:
    """Everything scheduled from twelve hours back to three days out, in time order."""
    now_ts = now.timestamp()
    lo, hi = now_ts - 12 * 3600, now_ts + 3 * 86400
    items: list[dict[str, Any]] = []

    data: list[dict[str, Any]] = []
    for r in snap.get("calendar") or []:
        ts = r.get("ts")
        if ts is None or not lo <= ts <= hi or (r.get("score") or 0) < 3:
            continue
        # `core` is the calendar's own "does this reach NQ, ES or GC" test.
        # Without it the first live brief (2026-09-15) listed eleven foreign
        # CPI and PPI prints by title alone — "CPI", "CPI", "Core CPI".
        if not r.get("core"):
            continue
        # Past its time but with no actual yet is neither upcoming nor printed.
        if ts < now_ts and not r.get("released"):
            continue
        # And an actual on a print still in the future is a timestamp that is
        # wrong, not a release that came early. Seen live on 2026-09-15: China's
        # retail sales and the UK's jobs data stamped a day late with their
        # actuals already in, which listed yesterday's prints as upcoming.
        if ts > now_ts and r.get("released"):
            continue
        data.append(r)

    # ONE CATALYST PER RELEASE (see releases.py): the 08:30 CPI was seven
    # catalysts, seven of the ten "ahead" slots and five near-identical notes.
    # The lead series is the row; the others ride on it as `also`, and the
    # index levels and unadjusted twins are left out — no one prices them, and
    # a figure the model never sees is one it cannot misquote.
    for rel in releases.group(
        data, event=lambda r: str(r.get("event") or ""), when=lambda r: r.get("ts"),
        country=lambda r: r.get("country"), score=lambda r: int(r.get("score") or 0),
        figures=lambda r: (r.get("actual_raw"), r.get("consensus_raw"), r.get("previous_raw")),
    ):
        r = rel.lead
        items.append(_cat(
            "data", datetime.fromtimestamp(r["ts"], ET), now, r.get("event"),
            country=r.get("country"),
            # Which trading session the print lands in — an Asia note cares
            # about the 21:30 ET GDP in a way a NY note does not.
            lands_in_session=r.get("session"),
            released=any(bool(x.get("released")) for x in rel.rows),
            actual=r.get("actual_raw"),
            consensus=r.get("consensus_raw"), previous=r.get("previous_raw"),
            surprise=round(r["surprise"], 2) if r.get("surprise") is not None else None,
            high=any((x.get("score") or 0) >= 4 for x in rel.rows),
            **({"also": [{"title": x.get("event"), "actual": x.get("actual_raw"),
                           "consensus": x.get("consensus_raw"),
                           "previous": x.get("previous_raw")} for x in rel.subs]}
               if rel.subs else {}),
        ))

    # The FOMC a week out is on the brief every day of that week; a speech is
    # only worth a row inside the three-day window.
    meetings = {m.get("date"): m for m in (snap.get("policy_meetings") or {}).get("meetings") or []}
    for e in snap.get("fed") or []:
        ts = e.get("ts")
        if ts is None or not lo <= ts <= now_ts + 7 * 86400 or (not e.get("major") and ts > hi):
            continue
        note = e.get("note")
        m = meetings.get(e.get("date")) if e.get("kind") == "FOMC" else None
        if m and m.get("move_bp") is not None and m.get("implied_after") is not None:
            note = (f"{m['move_bp']:+.0f}bp priced ({m.get('stance')}), "
                    f"{m['implied_after']:.2f}% implied after")
        items.append(_cat("fed", datetime.fromtimestamp(ts, ET), now, e.get("title"),
                          country="US", released=ts < now_ts, high=bool(e.get("major")),
                          note=note))

    for a in snap.get("auctions") or []:
        ts = a.get("ts")
        if ts is None or not a.get("major") or not lo <= ts <= hi:
            continue
        amt = a.get("amount_bn")
        items.append(_cat(
            "auction", datetime.fromtimestamp(ts, ET), now, f"{a.get('label')} auction",
            country="US", released=ts < now_ts,
            note=(f"${amt:g}bn" + (", reopening" if a.get("reopening") else "")) if amt else None,
        ))

    if any(b in books for b in ("NQ", "ES")):
        for e in snap.get("earnings") or []:
            if not e.get("bellwether") and (e.get("market_cap") or 0) < 200e9:
                continue
            try:
                day = datetime.strptime(str(e.get("date")), "%Y-%m-%d")
            except ValueError:
                continue
            timing = str(e.get("when") or "")
            hh, mm = {"pre": (8, 0), "after": (16, 5)}.get(timing, (12, 0))
            when = day.replace(hour=hh, minute=mm, tzinfo=ET)
            if not lo <= when.timestamp() <= now_ts + 2 * 86400:
                continue
            said = {"pre": "before the open", "after": "after the close"}.get(timing, "time TBC")
            items.append(_cat(
                "earnings", when, now, f"{e.get('symbol')} earnings",
                when=f"{_when_label(when, now).split(' ')[0]} {said}",
                released=bool(e.get("eps_actual")), actual=e.get("eps_actual"),
                consensus=e.get("eps_forecast"),
            ))

    # WHAT IS STILL TO COME OUTRANKS WHAT ALREADY PRINTED. Capped in plain time
    # order, the list filled with the morning's releases and dropped the next
    # day's FOMC — the one row a pre-session brief exists to carry. So the next
    # ten scheduled items are kept first, then the six most recent prints, and
    # only then does the lot go back into time order.
    items.sort(key=lambda c: c["ts"])
    ahead = [c for c in items if c["ts"] >= now_ts][:10]
    done = [c for c in items if c["ts"] < now_ts][-6:]
    kept = sorted(done + ahead, key=lambda c: c["ts"])
    for i, c in enumerate(kept, start=1):
        c["id"] = f"c{i}"
    return kept


def _leg(snap: dict[str, Any], key: str) -> dict[str, Any] | None:
    row = next((s for s in snap.get("sectors") or [] if s.get("key") == key), None)
    return row or _ctx(snap, key)


def _rotation(snap: dict[str, Any], books: list[str]) -> dict[str, Any]:
    """The ratio strip with five-day direction, and the index heavyweights' moves."""
    specs: list[tuple[str, str, str, str]] = []
    if any(b in books for b in ("NQ", "ES")):
        specs += [(name, a, b, "equity") for name, a, b in EQUITY_RATIOS]
    if "GC" in books:
        specs += [(name, a, b, "gold") for name, a, b in GOLD_RATIOS]

    ratios: list[dict[str, Any]] = []
    for name, key_a, key_b, group in specs:
        leg_a, leg_b = _leg(snap, key_a), _leg(snap, key_b)
        if not leg_a or not leg_b or not leg_a.get("last") or not leg_b.get("last"):
            continue
        chg = None
        if leg_a.get("week_pct") is not None and leg_b.get("week_pct") is not None:
            chg = ((1 + leg_a["week_pct"] / 100.0) / (1 + leg_b["week_pct"] / 100.0) - 1) * 100.0
        way = "flat"
        if chg is not None and abs(chg) >= RATIO_FLAT_PCT:
            way = "up" if chg > 0 else "down"
        level = leg_a["last"] / leg_b["last"]
        ratios.append({
            "id": name, "group": group, "level": round(level, 3 if level < 10 else 2),
            "chg_5d": round(chg, 2) if chg is not None else None, "dir": way,
        })

    index = "NQ" if "NQ" in books else ("ES" if "ES" in books else None)
    megacaps: list[dict[str, Any]] = []
    proxy_key = {"NQ": "QQQ", "ES": "SPY"}.get(index or "")
    if index:
        idx = ((snap.get("constituents") or {}).get("indices") or {}).get(index) or {}
        heavy = sorted(idx.get("members") or [], key=lambda m: -(m.get("weight") or 0))[:8]
        megacaps = [
            {"symbol": m.get("symbol"), "pct": m.get("pct"), "weight": m.get("weight")}
            for m in heavy
        ]
    proxy = _q(snap.get("quotes") or [], proxy_key) if proxy_key else None
    return {
        "ratios": ratios,
        "megacaps": megacaps,
        "megacap_index": proxy_key,
        "index_pct": round(proxy["pct"], 2) if proxy and proxy.get("pct") is not None else None,
    }


def _session_homes(session: str) -> set[str]:
    """The wire regions a session's desk counts as its own tape.

    Sets, because a session can have more than one home region: London's tape
    is the UK's AND the euro area's — with only "eu" here, the Bank of England
    ranked as foreign news in a London note.
    """
    return {
        "asia": {"apac", "global"},
        "london": {"uk", "eu", "global"},
        "ny": {"us", "global"},
    }.get(session, {"us", "global"})


def _headlines(snap: dict[str, Any], session: str, now: datetime) -> list[dict[str, Any]]:
    """The material wire, weighted to the session, each with an id the brief picks by.

    WEIGHTED TO THE SESSION BEING TRADED. For an Asia note, an item from
    Nikkei Asia or the RBA is worth more than a US market wrap, and the reverse
    holds at 09:00 ET. Regional items for the session come first, the rest
    follow, and nothing is dropped for being from the wrong desk — a strike on a
    refinery is an Asia story too.
    """
    homes = _session_homes(session)
    material = [h for h in snap.get("wire") or [] if h.get("impact") in {"high", "medium"}]
    local = [h for h in material if h.get("region") in homes]
    rest = [h for h in material if h.get("region") not in homes]
    return [
        {
            "id": f"h{i}",
            # In ET. The digest used to print the UTC clock under a `time_et`
            # key, four hours out for every headline the model timed.
            "time_et": _stamp_label(h.get("utc"), now),
            "impact": h.get("impact"),
            "desk": h.get("category"),
            "region": h.get("region"),
            "publisher": h.get("publisher"),
            "title": h.get("title"),
            "url": h.get("url"),
        }
        for i, h in enumerate([*local[:24], *rest[:8]], start=1)
    ]


def _partial(snap: dict[str, Any], books: list[str]) -> list[str]:
    """What the brief is missing today, worded for the banner at the top of it."""
    status = snap.get("status") or {}
    out: list[str] = []
    for key, name in BRIEF_SOURCES.items():
        st = status.get(key)
        if st is None:
            out.append(f"{name}: not collected yet.")
        elif not st.get("ok"):
            err = str(st.get("error") or "").strip()
            out.append(f"{name} unavailable" + (f" ({err[:90]})" if err else "") + ".")
        elif st.get("source") == "stale" or st.get("stale_age_min") is not None:
            # A cached copy behind a dead upstream is not "ok" for a brief: the
            # note would be written on frozen numbers with nothing to say so
            # (review, 2026-10-13).
            age = st.get("stale_age_min")
            when = f" from {float(age):.0f} min ago" if isinstance(age, (int, float)) else ""
            out.append(f"{name}: upstream unreachable — figures are a cached copy{when}.")
    if (status.get("gex") or {}).get("ok"):
        for b in books:
            g = _gex_asset(snap, b)
            if not g.get("ok"):
                why = f" ({g['error']})" if g.get("error") else ""
                out.append(f"No gamma levels for {b}{why}.")
    wanted = ["DXY", "US10Y", "WTI", "USDJPY"]
    if any(b in books for b in ("NQ", "ES")):
        wanted += ["VIX", "VXN", "VIX3M"]
    have = {q.get("key") for q in snap.get("quotes") or []}
    missing = [k for k in wanted if k not in have]
    if missing and (status.get("quotes") or {}).get("ok"):
        out.append(f"No quote for {', '.join(missing)}.")
    return out


def build_facts(snap: dict[str, Any], session: str = "ny", asset: str = "all") -> dict[str, Any]:
    """Every table on the brief, computed from the snapshot. No I/O."""
    books = books_for(asset)
    now = _now_et(snap)
    ladders = [lad for b in books if (lad := _ladder(snap, b, session, now))]
    by_book = {lad["book"]: lad for lad in ladders}
    return {
        "books": books,
        "as_of": f"{now:%a %d %b %Y}, {now:%H:%M} ET",
        "partial": _partial(snap, books),
        "snapshot": _snapshot(snap, books, now),
        "ladders": ladders,
        "gamma": [card for b in books if (card := _gamma_card(snap, b, by_book.get(b)))],
        "catalysts": _catalysts(snap, books, now),
        "rotation": _rotation(snap, books),
        "headlines": _headlines(snap, session, now),
    }


# The board rows the digest prints, for `price_feed`'s list of what is not current.
_DIGEST_KEYS = (
    "NQ", "QQQ", "ES", "SPY", "GC", "GLD", "YM", "RTY", "N225", "HSI", "SHCOMP", "KOSPI",
    "ASX", "FTSE", "DAX", "SX5E", "VIX", "VVIX", "MOVE", "VXN", "VIX3M", "US10Y", "DXY",
    "USDJPY", "EURUSD", "GBPUSD", "AUDUSD", "USDCNY", "WTI", "BRENT", "NATGAS", "SILVER",
    "COPPER", "BTC", "HYG", "TLT",
)


def _price_feed(quotes: list[dict[str, Any]], now: datetime) -> dict[str, Any]:
    """The board's age in one block: what is delayed, and what has stopped. Pure."""
    delayed: list[str] = []
    stopped: dict[str, str] = {}
    for key in _DIGEST_KEYS:
        q = _q(quotes, key)
        if not q:
            continue
        feed, label = _print_age(q, now)
        if feed == "delayed":
            delayed.append(key)
        elif feed in ("stale", "closed") and label:
            stopped[key] = f"{feed}: last print {label}"
    return {
        "board_read_et": now.strftime("%H:%M ET"),
        "futures": FUTURES_DELAY_NOTE,
        "delayed": delayed,
        "not_current": stopped,
    }


def build_digest(
    snap: dict[str, Any],
    session: str = "ny",
    asset: str = "all",
    facts: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """The terminal, compressed to the facts a desk would read out loud."""
    if facts is None:
        facts = build_facts(snap, session, asset)
    quotes = snap.get("quotes") or []
    clock = snap.get("clock") or {}
    # Off the SNAPSHOT's clock, not the wall clock, so the digest and the note
    # describe the same instant even if the snapshot is a little behind. One
    # binding, reused by the gamma age below for the same reason.
    now = _now_et(snap)
    _prog = session_progress(session, now)

    def brief(key: str) -> dict[str, Any] | None:
        return _brief(_q(quotes, key), now)
    rates = snap.get("rates") or {}
    sectors = snap.get("sectors") or []
    gex = (snap.get("gex") or {}).get("assets") or {}

    # THE BLOCK NAMES CARRY THE SCOPE, because a structure is obeyed where an
    # instruction is only read. Told in prose to write about NQ but handed eight
    # instruments in one block called `the_book`, the model treated all eight as
    # the subject and returned gold and ES calls inside a note the reader had
    # scoped to NQ. Splitting the block makes the wrong answer harder to write
    # than the right one. The context stays — NQ leading ES is a genuine read —
    # but it can no longer be mistaken for the thing being traded.
    all_books: dict[str, Any] = {
        "NQ_futures": brief("NQ"),
        "QQQ": brief("QQQ"),
        "ES_futures": brief("ES"),
        "SPY": brief("SPY"),
        "GC_gold_futures": brief("GC"),
        "GLD": brief("GLD"),
        "YM_dow": brief("YM"),
        "RTY_russell": brief("RTY"),
    }
    focus_keys = BOOK_KEYS.get(asset, ())
    if focus_keys:
        book: dict[str, Any] = {
            "the_book_this_note_is_about": {k: all_books[k] for k in focus_keys},
            "other_books_context_only": {
                k: v for k, v in all_books.items() if k not in focus_keys
            },
        }
    else:
        # All three books are the subject, so there is nothing to hold back.
        book = {"the_book": all_books}

    # ONE PLACE DECIDES WHAT "FOCUSED" MEANS, so the three per-instrument
    # blocks cannot disagree about which book the note is for.
    def wanted(key: str) -> bool:
        return asset == "all" or key == asset

    # ---- gamma: the seven levels per asset, with spot placed among them ----
    gamma: dict[str, Any] = {}
    for name, v in gex.items():
        if not v.get("ok") or not wanted(name):
            continue
        gamma[name] = {
            "spot": v.get("spot"),
            "regime": v.get("regime"),
            "regime_means": (
                "dealer hedging dampens moves; expect mean reversion between walls"
                if v.get("regime") == "POS"
                else "dealer hedging amplifies moves; expect trend and range extension"
            ),
            # NO SNAPSHOT AGE HERE, AND THE REASON IS WORTH KEEPING. It was
            # added to let the model see how stale the positioning is overnight,
            # and measured on GEXYGEN's GENERATED_UNIX — which is when GEXYGEN
            # last COMPUTED the map, not when the open interest behind it last
            # moved. GEXYGEN recomputes continuously while it runs, so the field
            # read 0 at every hour, and `gex.py` fetches with ttl 0 and
            # stale_ok=False, so a dead GEXYGEN yields no levels rather than old
            # ones. The number could therefore only ever say "fresh" — which at
            # 03:00 ET is precisely the wrong impression. The staleness that
            # matters is unconditional outside RTH and is stated in the prompt
            # instead: OI clears once a day, so out of hours this is the US
            # close's positioning.
            "levels": [
                {
                    "label": lv["label"],
                    "price": lv["price"],
                    "distance_pct": (
                        round(lv["dist_pct"], 2) if lv.get("dist_pct") is not None else None
                    ),
                }
                for lv in (v.get("levels") or [])
            ],
        }

    # ---- sectors: the ends of the ranking, not all thirteen ---------------
    movable = [
        s for s in sectors
        if s.get("key") not in {"SPY", "RSP"} and s.get("rs_day") is not None
    ]
    ranked = sorted(movable, key=lambda s: -(s["rs_day"]))
    rsp = next((s for s in sectors if s.get("key") == "RSP"), None)

    # ---- what each session actually did ------------------------------------
    ranges = {}
    for name, v in ((snap.get("ranges") or {}).get("assets") or {}).items():
        if not wanted(name):
            continue
        ranges[name] = {
            "last": v.get("last"),
            "sessions": [
                {
                    "session": r["label"],
                    # THE OPEN, WHICH THIS BLOCK USED TO WITHHOLD. Asked where
                    # price sat at the session's start and given only a high and
                    # a low, a model goes looking elsewhere in the digest and
                    # finds a number that is an open of something else. Giving
                    # it the right one is the fix; `developing_profile_open`
                    # carrying a disclaimer is only the guard rail.
                    "open": r.get("open"),
                    "high": r["high"],
                    "low": r["low"],
                    "range": round(r["range"], 1) if r.get("range") is not None else None,
                    "change_pct": round(r["chg_pct"], 2) if r.get("chg_pct") is not None else None,
                    # 0 at that session's low, 1 at its high, >1 means the
                    # current price has taken the session's high out.
                    "where_price_sits": round(r["pos"], 2) if r.get("pos") is not None else None,
                    # WHEN, AND WHETHER IT IS FINISHED. "Most recent" is
                    # yesterday's for any window that has not come round again,
                    # so at 01:00 ET the London and New York rows are the
                    # previous day's. Without these two the model reads every
                    # row as today's and writes about a session that has not
                    # happened yet.
                    "date": r.get("date"),
                    "status": r.get("status"),
                    "window_et": f"{r.get('start_et')}-{r.get('end_et')}",
                }
                for r in (v.get("sessions") or [])
                if r.get("ok")
            ],
        }

    return {
        "writing_for_session": SESSIONS.get(session, SESSIONS["ny"])["label"],
        "session_hours": _prog.get("hours"),
        "writing_about": ASSETS[resolve_asset(asset)]["instruments"],
        "as_of_et": clock.get("et"),
        # HOW OLD THE PRICES ARE — see `_print_age`. Read beside every figure.
        "price_feed": _price_feed(quotes, now),
        # STATED AS DATA AS WELL AS IN THE PROMPT. The prompt tells the model
        # how to write; this lets it reason about how far in it is — an Asia
        # note twenty minutes after the bell and one five hours in are different
        # notes, and only the second one has a session range worth reading.
        "session_underway": _prog["underway"],
        "session_opened_et": _prog.get("opened_et"),
        "session_opens_et": _prog.get("opens_et"),
        "minutes_into_session": _prog.get("minutes_in"),
        "minutes_until_session": _prog.get("minutes_until"),
        "session_phase": (clock.get("phase") or {}).get("label"),
        "sessions_open": [s["label"] for s in (clock.get("sessions") or []) if s.get("open")],
        "london_ny_overlap": clock.get("overlap"),
        "next_session_events": [
            {"event": m["label"], "et": m["et"], "in_minutes": m["in_min"]}
            for m in (clock.get("markers") or [])[:3]
        ],
        **book,
        "overnight_sessions": {
            # ASX included because the desk is in Sydney: for an Asia-session
            # note the home index is not "overnight", it is the tape.
            k: brief(k)
            for k in ("N225", "HSI", "SHCOMP", "KOSPI", "ASX", "FTSE", "DAX", "SX5E")
        },
        "volatility": {k: brief(k) for k in ("VIX", "VVIX", "MOVE", "VXN")},
        # THE SHAPE, NOT JUST THE LEVEL. Contango is the calm shape; the near
        # tenor overtaking the far one is the stressed one, and that crossover
        # usually leads the index rather than following it.
        "vol_term_structure": snap.get("volterm") or {},
        # WHERE THE VOLUME TRADED, cut by session exactly as the owner trades
        # it, WITH THE READS STATED AS FACTS rather than left for the model
        # to derive: each window carries its shape (P/b/D/double) and the
        # block names where the session OPENED and where price trades NOW
        # relative to prior value. "Opened below prior VAL and is still
        # below it" is a different day from "opened below and reclaimed" —
        # the classifier decides, the model narrates. Approximate (5m bars):
        # zones, not ticks.
        "volume_profile": {
            name: {
                "windows": [
                    {
                        "window": r.get("label"),
                        "span_et": f"{r.get('start_et')}-{r.get('end_et')}",
                        "poc": r.get("poc"),
                        "vah": r.get("vah"),
                        "val": r.get("val"),
                        "shape": r.get("shape"),
                        "poc_in_range_0to1": r.get("poc_pos"),
                        **(
                            {"second_node": r.get("second_node")}
                            if r.get("second_node") is not None
                            else {}
                        ),
                    }
                    # Every row, overnight included — see `_vp_reads`. The
                    # digest carries the three references the spec asks for at
                    # all hours: last completed RTH, last completed overnight,
                    # and the profile developing off the session's own anchor.
                    for r in (v.get("rows") or [])
                ],
                **_vp_reads(v, session),
            }
            for name, v in ((snap.get("profiles") or {}).get("assets") or {}).items()
            if wanted(name) and v.get("ok")
        },
        # Coupon supply. A tailed 10s or 30s auction reprices the long end at
        # 13:01 ET, and the longest-duration equity index moves with it.
        "treasury_supply_ahead": [
            {
                "date": a.get("date"),
                "closes_et": a.get("et"),
                "tenor": a.get("label"),
                "amount_bn": a.get("amount_bn"),
                "reopening": a.get("reopening"),
                "in_days": a.get("in_days"),
            }
            for a in (snap.get("auctions") or [])[:6]
        ],
        # Scheduled Fed risk. The headlines block carries what has been said;
        # this is what is about to be.
        "fed_ahead": [
            {
                "date": e.get("date"),
                "et": e.get("et"),
                "kind": e.get("kind"),
                "what": e.get("title"),
                "in_days": e.get("in_days"),
            }
            for e in (snap.get("fed") or [])[:8]
        ],
        "rates": {
            "effr": (rates.get("policy") or {}).get("EFFR", {}).get("rate"),
            "curve": {r["key"]: {"yield": r["value"], "chg_bp": r.get("chg_bp")}
                      for r in (rates.get("curve") or [])},
            # TIPS yields, Treasury's own daily print: gold's carrying cost, and
            # the half of a 10Y move that is not inflation.
            "real": {r["key"]: {"yield": r["value"], "chg_bp": r.get("chg_bp")}
                     for r in (rates.get("real") or [])},
            "spreads": {r["label"]: f"{r['value']}{r.get('unit', '')}"
                        for r in (rates.get("spreads") or [])},
            "policy_path": rates.get("path") or {},
            # Per-meeting, chained from EFFR: WHICH decision carries the move.
            # "+59bp by October" and "+16bp on Sep 16, +7bp on Oct 28" are
            # different notes, and only the second can be wrong-footed by one
            # speech.
            "fomc_meetings_priced": [
                {
                    "decision": m.get("date"),
                    "priced_bp": m.get("move_bp"),
                    "stance": m.get("stance"),
                    "implied_after_pct": m.get("implied_after"),
                }
                for m in (snap.get("policy_meetings") or {}).get("meetings") or []
            ][:6],
        },
        # The crosses each session's `leads` line names: EUR/USD and GBP/USD
        # for London, AUD/USD and USD/CNY for Asia — so a channel the prompt
        # points at has a figure behind it.
        "dollar_and_commodities": {
            k: brief(k)
            for k in ("DXY", "USDJPY", "EURUSD", "GBPUSD", "AUDUSD", "USDCNY",
                      "WTI", "BRENT", "NATGAS", "SILVER", "COPPER")
        },
        "risk_appetite": {k: brief(k) for k in ("BTC", "HYG", "TLT")},
        # Week and month changes from daily bars: the "WTI +11% on the week"
        # figures a one-day board cannot give. `week_change` is a plain
        # difference, which is how a yield's move is said.
        "multi_day": {
            r["key"]: {
                "last": r.get("last"),
                "week_pct": round(r["week_pct"], 2) if r.get("week_pct") is not None else None,
                "month_pct": round(r["month_pct"], 2) if r.get("month_pct") is not None else None,
                "week_change": round(r["week_chg"], 3) if r.get("week_chg") is not None else None,
            }
            for r in snap.get("context") or []
        },
        "gamma_levels": gamma,
        # What each session traded, and where price sits inside each range.
        # The most useful block on the page for a handover read: "London has
        # already taken out the Asia high" is one number here and an inference
        # from four elsewhere.
        "session_ranges": ranges,
        "expiry": snap.get("expiry") or {},
        "earnings": [
            {
                "symbol": e.get("symbol"),
                "name": e.get("name"),
                "date": e.get("date"),
                "when": e.get("when"),
                "eps_forecast": e.get("eps_forecast"),
                "eps_actual": e.get("eps_actual"),
            }
            for e in (snap.get("earnings") or [])[:14]
        ],
        # WHAT ACTUALLY MOVED THE INDEX, name by name. The rotation block
        # says which sectors are being bought; this says which individual
        # weights supplied today's move, which on a cap-weighted index is
        # usually two or three names and is a different question.
        "index_movers": {
            k: {
                "covered_weight_pct": v.get("covered_weight"),
                "net_contribution_pct": v.get("net_contribution"),
                "biggest": [
                    {
                        "symbol": m["symbol"],
                        "weight_pct": m["weight"],
                        "change_pct": m["pct"],
                        "index_points_pct": m["contribution"],
                    }
                    for m in (v.get("members") or [])[:8]
                ],
            }
            for k, v in ((snap.get("constituents") or {}).get("indices") or {}).items()
            if wanted(k)
        },
        "sector_rotation_1d_vs_spy": {
            "leading": [
                {"sector": s["label"], "rs_pct": round(s["rs_day"], 2)} for s in ranked[:4]
            ],
            "lagging": [
                {"sector": s["label"], "rs_pct": round(s["rs_day"], 2)} for s in ranked[-4:]
            ],
            "breadth_rsp_vs_spy_pct": round(rsp["rs_day"], 2)
            if rsp and rsp.get("rs_day") is not None
            else None,
        },
        # Scheduled risk from twelve hours back to three days out — data, the
        # Fed, long-end auctions, bellwether earnings — each with the `id` the
        # brief's catalyst notes point at.
        "catalysts": [{k: v for k, v in c.items() if k != "ts"} for c in facts["catalysts"]],
        # The material wire, each with the `id` the brief picks headlines by.
        "headlines": [{k: v for k, v in h.items() if k != "url"} for h in facts["headlines"]],
        # THE TABLES THE PAGE PRINTS, exactly as it prints them. Levels named in
        # prose should come from these ladders so the words and the table agree.
        "brief_tables": {k: facts[k] for k in ("snapshot", "ladders", "gamma", "rotation")},
        "data_gaps": facts["partial"],
    }


# --------------------------------------------------------------------------
# The schema. Forces a direction and a conviction rather than adjectives.
# --------------------------------------------------------------------------

BIASES = ("bullish", "leaning bullish", "neutral", "leaning bearish", "bearish")
TONES = ("bear", "bull", "mixed", "neutral")

_STR: dict[str, Any] = {"type": "string"}


def _obj(props: dict[str, Any]) -> dict[str, Any]:
    """A strict-mode object: every property required, nothing extra allowed."""
    return {
        "type": "object", "additionalProperties": False,
        "required": list(props), "properties": props,
    }


def _arr(items: dict[str, Any], lo: int, hi: int) -> dict[str, Any]:
    return {"type": "array", "minItems": lo, "maxItems": hi, "items": items}


_BOOK = {"type": "string", "enum": list(BOOKS)}
_BIAS = {"type": "string", "enum": list(BIASES)}

# THE BRIEF. Words only: every figure it annotates lives in the facts, and the
# `id`/`key` fields are how an annotation finds its row. See `sanitize_brief`
# for what happens to one that points at nothing.
SCHEMA: dict[str, Any] = _obj({
    "thesis": {**_STR, "description": "One or two plain sentences: the idea of the day."},
    "calls": _arr(_obj({
        "book": _BOOK,
        "open_bias": _BIAS,
        "conviction": {"type": "integer", "minimum": 1, "maximum": 5},
        "rest_of_day": {**_STR, "description": "Short label, e.g. 'Neutral to leaning bearish'."},
        "rest_of_day_bias": _BIAS,
        "wrong_if": {**_STR, "description": "Under 60 characters, using ladder levels."},
        # THE JUSTIFICATION, IN LAYERS. Two to four bullets, each naming its
        # layer, so a call cannot be asserted without saying what it rests on:
        # the macro driver, whether structure confirms or conflicts, and what
        # tipped it. The owner asked for the bias to explain itself
        # (2026-09-16); a bias with a conviction score and no reasoning is a
        # number that cannot be argued with, which is not a virtue.
        "why": _arr(
            {
                **_STR,
                "description": (
                    "One reason, prefixed with its layer: "
                    "Macro:, Positioning:, Structure:, Session:."
                ),
            },
            2, 4,
        ),
    }), 1, 3),
    "snapshot_watch": _arr(_obj({"key": _STR, "note": _STR}), 0, 5),
    "gamma_read": _STR,
    "catalysts_intro": _STR,
    "catalyst_notes": _arr(_obj({"id": _STR, "note": _STR}), 0, 14),
    "reads": _arr(_obj({
        "book": _BOOK,
        "regime": _STR,
        "chain": _arr(_STR, 2, 6),
        "at_open": _STR,
        "wrong_if": _STR,
        "rest_of_day": _STR,
        "flips": _arr(_STR, 1, 3),
        "drivers": _arr(_obj({
            "label": _STR, "text": _STR, "tone": {"type": "string", "enum": list(TONES)},
        }), 3, 8),
    }), 1, 3),
    "rotation_read": _STR,
    "ratio_reads": _arr(_obj({"id": _STR, "read": _STR}), 0, 8),
    "rotation_notes": _arr(_STR, 0, 3),
    "headlines": _arr(_obj({"id": _STR, "books": _arr(_BOOK, 1, 3), "note": _STR}), 0, 6),
    "cross_asset": _STR,
    "risks": _arr(_STR, 0, 4),
})

# What a non-US session can actually do to a US-priced book, and through which
# channel. One entry per session; the gold line is separate because the answer
# genuinely differs for it.
#
# WHY THIS EXISTS AT ALL. The prompt already named what LEADS each session
# (SESSIONS["leads"]) and never said how any of it reaches the thing being
# traded. That is an invitation to treat correlation as cause: handed a Hang
# Seng print and asked for an NQ call, a model will happily make the Hang Seng
# the reason. These name the transmission instead, so a regional fact has to
# earn its way into the call through a channel that exists.
#
# THE OWNER'S RULE, KEPT: US macro and the Fed remain the anchor in every
# session. What changes by session is which OTHER evidence is admissible and how
# far a break should be believed — never the weight of the US itself.
#
# AND THEY NAME ONLY CHANNELS THE DIGEST CAN SHOW (review, 2026-10-14). The
# London block sent the model to "Bunds and Gilts" and the gold block to "the
# LBMA fixes", "Shanghai premiums" and "Indian buying" — none of which this
# data has ever carried — and a stored GC brief duly repeated all three as if
# they had been read. The figure check catches an invented number, not an
# invented market. So each channel now points at the block where it shows, and
# anything without one is admissible only from a headline that states it.
TRANSMISSION: dict[str, str] = {
    "asia": """\
ASIA REACHES A US BOOK THROUGH THREE CHANNELS, AND ESSENTIALLY NO OTHERS:
  * USD/JPY and the BoJ — a funding channel, not a sentiment one. Yen strength
    forces carry unwinds and that lands hardest on the long-duration index.
    USD/JPY is in `dollar_and_commodities`; the BoJ is in the catalysts or the
    headlines when it is in play at all.
  * China growth and policy — the Chinese prints in `catalysts`, USD/CNY, and
    stimulus or PBOC headlines. Real, but second-order for the indices and
    first-order for commodities and the dollar.
  * Taiwan and the semiconductor complex — TSMC, export curbs, Taiwan risk,
    as the headlines and `index_movers` show them. This one hits NQ directly
    through the semis, not through "Asian equities".
A Nikkei or Hang Seng move on its own is CORRELATION, not cause: those indices
are usually reacting to the same US close the reader already knows about. Say
what Asia did, but only let it move the call when it arrives through one of the
three channels above.""",
    "london": """\
LONDON REACHES A US BOOK MAINLY THROUGH RATES AND THE DOLLAR, and it matters
more than Asia does:
  * European rates trade into the US curve, and the US curve is the discount
    rate under the index — long duration first. THIS DATA CARRIES NO EUROPEAN
    YIELDS: what it has is the US curve itself (`rates.curve`, the 10-year in
    the snapshot), which is where a European rates move shows up for these
    books. Name a Bund or Gilt move only if a headline states one, and say so.
  * EUR/USD and GBP/USD are the other side of the dollar
    (`dollar_and_commodities`), so European data moves the DXY that gold and
    the multinationals are priced against.
  * European data and ECB/BoE speakers, as `catalysts` and the headlines list
    them, set the day's rate narrative before New York has an opinion.
Liquidity is genuinely here, so London is where the overnight range gets
resolved rather than merely drifted through — and it is positioning ahead of
the 08:30 ET US print, which remains the actual event.""",
    "ny": """\
NEW YORK IS THE SESSION EVERYTHING ELSE WAS POSITIONING FOR. The 08:30 data
window, the 09:30 open, Fed speakers and the auction cycle are the drivers, and
the overnight is now the range being broken or defended rather than a separate
story. Dealer gamma matters most here because the option volume that creates it
is American.""",
}

# Gold's answer to the same question is different enough to state separately.
TRANSMISSION_GC = """\
GOLD IS THE ONE BOOK WHERE THE NON-US SESSIONS ARE MORE THAN A TIMEZONE: London
and Asia are where much of the physical market trades, so a move there can be
real flow rather than drift. BUT THIS DATA CARRIES NO PHYSICAL-MARKET SERIES —
no fix prices, no regional premiums or import figures, no ETF holdings, no
central-bank purchases. Do not name any of them as a fact or a driver; if a
headline reports one, cite that headline as the source. What the data does
carry, and what sets the level: US real yields (`rates.real`) and the policy
path, the dollar (DXY, USD/JPY), silver and copper beside gold, GVZ, and the
session ranges. A gold thesis that never mentions real rates is incomplete."""


def _thin_tape(session: str) -> str:
    """What the overnight tape's thinness does to the reading — outside NY only.

    Empty for New York, because every sentence in it is about being away from
    New York. A note for the session with the deepest book does not need to be
    told that overnight turnover is light; including it anyway was prompt
    tonnage the model had to spend attention discarding.
    """
    if session == "ny":
        return ""
    return """
Overnight turnover is a fraction of the day's and most of the overnight range is
positioning rather than information — after-hours US earnings, which print at
16:00-16:30 ET before Globex has even reopened, routinely move NQ overnight more
than anything on the regional tape.

THAT THINNESS CHANGES THE READING, structurally rather than narratively. Weight
the SESSION'S OWN EVIDENCE up and the macro story down: the developing profile
and the range so far are built from the tape actually trading, they update with
every bar, and in a thin book acceptance means more, not less. Say explicitly
when a move looks like position-driven drift rather than a repricing.

DEALER GAMMA IS THE EXCEPTION, AND IT SPLITS IN TWO. Overnight a wall is a
LEVEL, NOT A FORCE. The pin works through dealers hedging in a deep book, and
that flow is largely absent out of hours — desks that can hedge overnight mostly
wait for liquidity rather than work size into Globex. So:
  * A POSITIVE-GAMMA PIN IS WEAKER HERE than the same setup at 10:30 ET. Cite
    the walls as reference geometry and as the frame New York will open into;
    do not claim price should pin between them tonight on hedging that is not
    happening.
  * THE FLIP CUTS THE OTHER WAY. Negative gamma in a thin book is MORE
    dangerous, not less: whatever hedging flow does arrive moves price further
    than it would in depth, which is how overnight cascades happen at all. Spot
    below the flip out of hours deserves more weight, not less.
AND THE MAP ITSELF IS THE US CLOSE'S. Open interest clears once a day and the
options barely trade out of hours, so this is where dealers WERE when New York
shut, not where they are now. Usually still fair — positions do not move much
when nothing trades — but it is one more reason to read the walls as geometry
overnight rather than as a live constraint.
"""


def _transmission(session: str, asset: str) -> str:
    """The session's transmission channels for the book being written about."""
    block = TRANSMISSION.get(session, TRANSMISSION["ny"])
    if resolve_asset(asset) == "GC":
        return f"{block}\n\n{TRANSMISSION_GC}"
    return block


def _live_framing(session: str, prog: dict[str, Any]) -> str:
    """The paragraph that turns a pre-open template into a note written from here.

    It sits immediately above "Field by field", because that block is what was
    overriding the clock: the digest always said `as_of_et: 23:28`, and the
    field spec always said "the call for the start of the session". A model
    handed both writes to the spec. This reframes the three fields that name the
    open, in the same breath as the instruction that names them.
    """
    label = SESSIONS.get(session, SESSIONS["ny"])["label"]
    if not prog.get("underway"):
        return f"""\
{label.upper()} HAS NOT OPENED YET — it starts at {prog.get('opens_et')} ET, in \
{prog.get('phrase')}. This is a note written BEFORE the bell, so the fields \
below mean exactly what they say: the call is for the open, and the levels are \
the ones price will meet when it gets there.
"""
    return f"""\
{label.upper()} IS ALREADY TRADING — it opened at {prog.get('opened_et')} ET, \
{prog.get('phrase')} ago, and the digest is a snapshot of RIGHT NOW rather than \
of the open. WRITE THE NOTE FROM HERE.

Read every field below that names "the open" as "from this moment":
  * `open_bias` is your call for the REMAINDER of the session, from the current \
price — not a call for an open that has already happened.
  * `at_open` describes where price sits NOW, and what this session has already \
done to get there: the range it has built, which levels it has taken or \
rejected, whether it is holding above or below them.
  * `rest_of_day` is the path from this moment to the close.

The session's own developing profile and its range so far are the live \
evidence; the completed reference windows are what it is being judged against. \
Do not narrate the open as though it were ahead, and do not state a level as \
untested if this session has already traded through it.
"""


def system_prompt(session: str, asset: str = "all", prog: dict[str, Any] | None = None) -> str:
    """The instructions, assembled around the session AND the book being traded.

    ONE PROMPT PER COMBINATION RATHER THAN ONE GENERIC ONE. A note that says
    "the open" without saying which open is describing nothing, and a model
    given a New York framing will reach for the Fed and the sector tape at
    20:00 ET when the reader is about to trade the Nikkei. The same holds for
    the instrument: told to write about gold, a model handed the equity blocks
    will work through technology's relative strength on the way to a call that
    has nothing to do with it. Both blocks below name what actually drives the
    thing being written about.
    """
    s = SESSIONS.get(session, SESSIONS["ny"])
    if prog is None:
        prog = session_progress(session, datetime.now(ET))
    a = ASSETS[resolve_asset(asset)]

    # THE MUST-READ LIST BENDS WITH THE BOOK, because the fixed one contradicted
    # the asset drivers. GC's drivers said "ignore sector rotation and index
    # constituents" while the static list three paragraphs later ordered both to
    # "appear somewhere in the note" — two instructions pulling opposite ways in
    # one prompt, resolved by whichever the model happened to weight. Worse, a
    # GC digest carries an EMPTY index_movers block (constituents are filtered
    # to the asset, and gold has none), so the old rule demanded a citation from
    # a block with nothing in it.
    #
    # The rotation ARITHMETIC never changes — eleven S&P sectors against their
    # own aggregate is one market-wide fact. What changes per book is whether
    # that fact is structure or weather: for ES it is the internal composition
    # of the thing being traded, for NQ it is mostly one row (technology's
    # relative strength), and for gold it is an equity risk signal at most.
    if resolve_asset(asset) == "GC":
        must_read = """\
  session_ranges   what each session traded, and where price sits inside each. \
The most important block for a handover: 0 is that session's low, 1 its high, \
above 1 means the high has been taken out.
  gamma_levels     where dealer hedging turns on the GC board, and the regime.
  rates            the policy path and the curve. Real yields are the carrying \
cost of a zero-coupon asset, so gold trades the front of the curve and what is \
priced into it.
  dollar_and_commodities   the unit gold is priced in, plus silver and copper — \
which say whether a metals move is monetary or industrial.

Then volatility, the volume profile levels, the calendar ahead, expiry and \
the headlines — context, cited where it changes the read. Sector rotation and \
index constituents are equity internals: bring them in only when equities \
are moving hard enough to be a risk signal for gold in their own right, \
never as structure."""
    else:
        must_read = """\
  session_ranges   what each session traded, and where price sits inside each. \
The most important block for a handover: 0 is that session's low, 1 its high, \
above 1 means the high has been taken out.
  gamma_levels     where dealer hedging turns, and the regime.
  index_movers     WHICH NAMES supplied the move. These indices are \
cap-weighted and two or three names are usually the day, so "NQ is down" and \
"NQ is down because AMZN is off 2.5%" are different notes. Use the contribution \
figures, which are weight times return — not the raw percent changes.
  sector_rotation  WHICH SECTORS are being bought, as excess return over SPY. \
Defensives leading is a different tape from technology leading.

Then rates and the policy path, volatility, the volume profile (POC is the \
magnet, VAH/VAL bound acceptance; STATE where the session opened and where \
price trades now against prior value — the classifier already decided, cite \
it — and name any confluence between profile levels and gamma walls), the \
dollar and commodities, the calendar ahead, earnings, expiry and the \
headlines — context, cited where it changes the read."""

    book_list = ", ".join(books_for(asset))
    return f"""You are a markets strategist writing the pre-session brief for one \
trader's desk. They trade NQ/QQQ, ES/SPY and GC/GLD futures and ETFs, and they \
trade the Asia, London and New York sessions.

THIS BRIEF IS ABOUT {a["instruments"].upper()}.
  {a["drivers"]}

THIS BRIEF IS FOR THE {s["label"].upper()} SESSION, {prog.get("hours")}.
  What leads it: {s["leads"]}
  Handover: {s["handover"]}
  How it usually behaves: {s["character"]}

{_transmission(session, asset)}

US MACRO AND THE FED ARE THE ANCHOR IN EVERY SESSION, INCLUDING THIS ONE. These \
are US-priced books: NQ and ES are claims on US earnings discounted at US real \
rates, and gold is priced against the same curve and the same dollar. The \
session above decides WHICH OTHER EVIDENCE IS ADMISSIBLE and how far to believe \
a break; it never demotes the US.
{_thin_tape(session)}
Write about THAT session. Conditions from the other two are context for it, \
never the subject — say what they hand over, then say what it means for the \
one being traded.

THE SAME RULE BINDS THE INSTRUMENT, and more strictly. Calls and reads are \
issued for {book_list} and nothing else. Where the brief is scoped to one book \
the others appear under `other_books_context_only`, and they are exactly that: \
cite them where they change the read, since a divergence is worth a sentence, \
and never issue a call on them.

Write from the data you are given and nothing else. Every claim rests on a \
figure that appears in that data, and the figure is quoted where the claim is \
made ("10Y 4.99%, +6bp", not "yields are up"). If the data does not support a \
view, the call is neutral with a low conviction — a hedged guess presented \
confidently is worse than no brief.

WHAT THIS DATA DOES NOT HAVE: COT positioning, options open interest or \
put/call ratios, net gamma notional, ETF flows or holdings, European or \
Japanese government bond yields, gold fixes or physical premiums. Never \
mention them. A figure that is not in the data does not go in the brief, \
however standard it would be in one — AND NEITHER DOES A MARKET, FLOW OR DATA \
SERIES. Every driver you name must be a block or row in the data, or a \
headline you cite by id. "Gilts sold off", "Indian demand", "the fix was \
strong" are claims about data you were not given; leave them out.

PRICES HAVE AGES. `price_feed` says how old the board is: the CME futures \
quotes run about ten minutes behind the exchange, and any row listed under \
`not_current` stopped printing hours ago (a cash yield after its close, an \
index whose exchange is shut). Quote those as the last or closing print \
("10Y closed 4.12%"), never as where the market is now, and do not build a \
"right now" read on them.

WORK THROUGH EVERY BLOCK OF THE DATA BEFORE YOU CONCLUDE. Notes written before \
this instruction cited the gamma levels and the session ranges and silently \
ignored sector rotation in three runs out of five — that was not a judgement \
that it did not matter, it was the block not being read. Each of these answers \
a different question, and the first four should appear somewhere in the brief:

{must_read}

If a block genuinely says nothing today, leave it out rather than padding. \
What is not acceptable is not looking.

Read the gamma levels the way a dealer-flow trader does: positive gamma means \
hedging dampens moves and price tends to pin between the walls; negative gamma \
means hedging amplifies them and ranges extend. Spot's position against the \
gamma flip and the expected move is the single most important structural fact \
on the page. If `expiry` says it is OpEx week, say what that does to the walls.

THE PAGE IS ALREADY BUILT AROUND YOUR WORDS. The snapshot, the levels ladder, \
the dealer gamma card, the catalyst list, the ratio table and the headline \
list are printed from `brief_tables`, `catalysts` and `headlines` exactly as \
the data has them. Do not rebuild those tables in prose. Write the read that \
sits beside them, point at rows by `key` or `id` where a field asks for one, \
and take any level you name from `brief_tables.ladders`.

{_live_framing(session, prog)}
HOW THE BIAS IS FORMED, AND IN WHAT ORDER. Macro sets the DIRECTION: the data \
that printed, what is priced for the Fed, the policy path, the dollar and the \
curve are why the market wants to go somewhere, and the call is anchored there \
whenever any of it is live today. Structure sets the PATH: where the session \
opened against prior value, the profile's shape and second node, the session \
ranges and the gamma map decide whether the macro lean is being ACCEPTED or \
REJECTED by the tape, and they supply every level the call names. Read them \
together, never one without the other — a bearish print with price accepted \
above prior value and above the flip is a CONFLICT, and a conflict lowers \
conviction rather than picking a side. On a day with no print and no speaker, \
say so and let structure lead: macro that is not moving today does not anchor \
a call by reputation. Gamma's weight follows the session — decisive in New \
York where the hedging flow is real, a reference elsewhere.

Field by field:
  thesis          One or two plain sentences: the single idea that explains \
today across the books, and the one figure to watch. It is the page's headline.
  calls           Exactly one per book in scope. `open_bias` is the call for \
the start of the session and `conviction` its strength, 1-5. `rest_of_day` is \
a short label for how the session evolves after the open ("Neutral to leaning \
bearish", "Leaning bearish, conditional") and `rest_of_day_bias` its \
direction. `wrong_if` is the price condition that kills the call, under 60 \
characters. `why` is two to four bullets that justify the bias, EACH PREFIXED \
WITH ITS LAYER — "Macro:", "Positioning:", "Structure:", "Session:" — in that \
order where they apply: the macro driver with its figure; the positioning read \
(the gamma regime, spot against the flip); the structure read (opened above or \
below prior value, the profile's shape, which range level is holding); and what \
the session does to the weighting. Name the conflict if there is one. This is \
the part the reader argues with, so it has to be concrete enough to argue with.
  snapshot_watch  Up to five `brief_tables.snapshot` keys that matter most \
today, each with a few words on why.
  gamma_read      One or two sentences: what the regime, the flip and the \
expected move mean for how far today's ranges run.
  catalysts_intro One or two sentences framing the calendar: what today is \
positioning for.
  catalyst_notes  Notes on the catalyst ids that matter, each saying what the \
print or event means (a miss, a beat, what is priced). Skip the rest. A data \
catalyst's `also` lists the other series of the same release (core and \
headline, monthly and annual): one note covers the release.
  reads           Exactly one per book in scope:
    regime        The regime in a few words ("Hike repricing / inflation \
scare", "Real-yield primacy").
    chain         The macro transmission as 3-5 links from cause to effect, \
each a few words carrying its figure: "Oil +26% in a month", "Inflation \
impulse", "Hike priced for tomorrow", "Real yields up (10Y real +17bp wk)", \
"Discount-rate squeeze on megacaps". Only transmissions the data shows.
    at_open       Two to four sentences: where price sits against the levels \
at the start and why that is the lean.
    wrong_if      The full invalidation: acceptance beyond which ladder level, \
and what that opens.
    rest_of_day   Two to four sentences: the conditional path, what breaks \
next and where it targets.
    flips         One to three events or prints, not levels, that would \
reverse the view.
    drivers       Four to eight rows: a short `label` ("10Y", "DXY", \
"Rotation", "Vol", "Megacaps", "Geopolitics"), a few words of `text` with the \
figure, and a `tone` for THIS book: bear, bull, mixed or neutral.
  rotation_read   One or two sentences on what the ratio table says about the \
tape: broadening, concentration, defensive, a rate scare.
  ratio_reads     A few words on each ratio id that matters.
  rotation_notes  Up to three extra observations with figures (the megacaps, \
the gold complex).
  headlines       Three to six headline ids that move price today, each with \
the books it moves and one line on why.
  cross_asset     One or two sentences: are the books moving on one driver or \
diverging, and what to watch because of it.
  risks           Up to four short ways the read dies.

Be concrete and unhedged in the direction call. Do not use disclaimers, do not \
mention that you are an AI, and do not recommend position sizes or give \
financial advice — describe conditions and levels, which is what a desk brief \
does."""


_FENCE = re.compile(r"```(?:json)?\s*(.+?)\s*```", re.S)


def extract_json(text: str) -> Any | None:
    """The first JSON object in a model's answer, however it wrapped it.

    THREE WRAPPINGS SEEN IN PRACTICE, all from models that claim structured
    output support. A reasoning model prefixes its working ("Let me look at the
    gamma structure first… {…}"); a chat-tuned one fences the block in
    ```json; a third adds a sentence of preamble. Refusing all three and
    calling it a schema failure threw away answers that were sitting right
    there — the JSON was correct, the envelope was not.

    Brace-matched rather than regexed, because the report contains nested
    objects and a non-greedy `\\{.*\\}` stops at the first inner brace.
    """
    if not text:
        return None
    for candidate in (text, *(m.group(1) for m in _FENCE.finditer(text))):
        candidate = candidate.strip()
        # EVERY BRACE GETS A TURN, leftmost first — a fourth wrapping arrived
        # live on 2026-09-01: a stray opening brace before the real object
        # ("{\n\n{ ...an entire valid, correctly-scoped report... }").
        # Matched only from the first brace, the orphan never closes, depth
        # never returns to zero, and a complete answer was thrown away with
        # "no JSON object" — during upstream saturation, when answers are
        # most expensive to re-ask for. Leftmost-first keeps the outermost
        # parseable object winning; the cap is because a pathological answer
        # is all braces.
        starts = [i for i, ch in enumerate(candidate) if ch == "{"][:8]
        for start in starts:
            depth, in_str, esc = 0, False, False
            for i in range(start, len(candidate)):
                ch = candidate[i]
                if in_str:
                    if esc:
                        esc = False
                    elif ch == "\\":
                        esc = True
                    elif ch == '"':
                        in_str = False
                    continue
                if ch == '"':
                    in_str = True
                elif ch == "{":
                    depth += 1
                elif ch == "}":
                    depth -= 1
                    if depth == 0:
                        # strict=False: a raw line break or tab inside a string
                        # is the commonest way a long free-model answer stops
                        # being strict JSON, and strict parsing then fell
                        # through to the first INNER object — a single plan,
                        # reported as "needs a headline" (2026-10-13).
                        with contextlib.suppress(ValueError, TypeError):
                            return json.loads(candidate[start : i + 1], strict=False)
                        break
    return None


def _text(v: Any) -> str:
    return v.strip() if isinstance(v, str) else ""


def _texts(v: Any, cap: int) -> list[str]:
    if not isinstance(v, list):
        return []
    return [x.strip() for x in v if isinstance(x, str) and x.strip()][:cap]


def _dicts(v: Any) -> list[dict[str, Any]]:
    return [x for x in v if isinstance(x, dict)] if isinstance(v, list) else []


def norm_bias(v: Any) -> str | None:
    """A bias in the schema's words, from the words a model actually used.

    THE LOOSE MODE ENFORCES NOTHING, and a model that has just been told about a
    brief full of "Lean Bear" writes "lean bear" back. That is the right call in
    the wrong spelling, so it is mapped rather than thrown away; anything that
    is not recognisably one of the five still is.
    """
    if not isinstance(v, str):
        return None
    t = re.sub(r"[\s_-]+", " ", v.strip().lower())
    t = re.sub(r"\blean(s|ing)?\b", "leaning", t)
    t = re.sub(r"\bbear\b", "bearish", t)
    t = re.sub(r"\bbull\b", "bullish", t)
    return t if t in BIASES else None


def _picks(
    v: Any, field: str, allowed: set[str], text_field: str, cap: int
) -> list[dict[str, str]]:
    """Annotations whose `field` names a real row, first mention wins."""
    out: list[dict[str, str]] = []
    seen: set[str] = set()
    for x in _dicts(v):
        k, text = x.get(field), _text(x.get(text_field))
        if isinstance(k, str) and k in allowed and k not in seen and text:
            seen.add(k)
            out.append({field: k, text_field: text})
    return out[:cap]


def sanitize_brief(obj: Any, facts: dict[str, Any]) -> dict[str, Any] | None:
    """The model's brief, checked against the facts it is allowed to point at.

    THE SCHEMA IS ONLY ENFORCED BY THE PROVIDER IN STRICT MODE, and the weaker
    mode below enforces nothing — so the shape is checked here rather than
    assumed. And more than the shape: a note on a catalyst id that does not
    exist, or a call on a book the brief is not about, is dropped here, so the
    panel can join on ids without guarding every one.

    None when what is left is not a brief: no thesis, a book in scope without a
    call, or no read at all.
    """
    if not isinstance(obj, dict):
        return None
    books: list[str] = list(facts.get("books") or BOOKS)

    calls: dict[str, dict[str, Any]] = {}
    for c in _dicts(obj.get("calls")):
        book, bias = c.get("book"), norm_bias(c.get("open_bias"))
        if not isinstance(book, str) or book not in books or book in calls or bias is None:
            continue
        try:
            conviction = int(c.get("conviction") or 0)
        except (TypeError, ValueError):
            conviction = 1
        calls[book] = {
            "book": book,
            "open_bias": bias,
            "conviction": min(5, max(1, conviction)),
            "rest_of_day": _text(c.get("rest_of_day")),
            # The chip's colour only — the label beside it carries the words —
            # so an unreadable direction falls back to the open call's.
            "rest_of_day_bias": norm_bias(c.get("rest_of_day_bias")) or bias,
            "wrong_if": _text(c.get("wrong_if")),
            "why": _texts(c.get("why"), 4),
        }

    reads: dict[str, dict[str, Any]] = {}
    for r in _dicts(obj.get("reads")):
        book = r.get("book")
        if not isinstance(book, str) or book not in books or book in reads:
            continue
        reads[book] = {
            "book": book,
            "regime": _text(r.get("regime")),
            "chain": _texts(r.get("chain"), 6),
            "at_open": _text(r.get("at_open")),
            "wrong_if": _text(r.get("wrong_if")),
            "rest_of_day": _text(r.get("rest_of_day")),
            "flips": _texts(r.get("flips"), 3),
            "drivers": [
                {
                    "label": _text(d.get("label")),
                    "text": _text(d.get("text")),
                    "tone": d.get("tone") if d.get("tone") in TONES else "neutral",
                }
                for d in _dicts(r.get("drivers"))[:8]
                if _text(d.get("label"))
            ],
        }

    thesis = _text(obj.get("thesis"))
    if not thesis or not reads or any(b not in calls for b in books):
        return None

    headline_ids = {h["id"] for h in facts.get("headlines") or []}
    headlines: list[dict[str, Any]] = []
    for h in _dicts(obj.get("headlines")):
        hid = h.get("id")
        if not isinstance(hid, str) or hid not in headline_ids:
            continue
        if any(x["id"] == hid for x in headlines):
            continue
        # "Gold" is what a model writes for GC more often than not.
        named = {str(x).strip().upper().replace("GOLD", "GC") for x in h.get("books") or []
                 } if isinstance(h.get("books"), list) else set()
        headlines.append({
            "id": hid, "books": [b for b in BOOKS if b in named], "note": _text(h.get("note")),
        })

    return {
        "thesis": thesis,
        "calls": [calls[b] for b in books],
        "snapshot_watch": _picks(
            obj.get("snapshot_watch"), "key",
            {row["key"] for row in facts.get("snapshot") or []}, "note", 5,
        ),
        "gamma_read": _text(obj.get("gamma_read")),
        "catalysts_intro": _text(obj.get("catalysts_intro")),
        "catalyst_notes": _picks(
            obj.get("catalyst_notes"), "id",
            {c["id"] for c in facts.get("catalysts") or []}, "note", 14,
        ),
        "reads": [reads[b] for b in books if b in reads],
        "rotation_read": _text(obj.get("rotation_read")),
        "ratio_reads": _picks(
            obj.get("ratio_reads"), "id",
            {r["id"] for r in (facts.get("rotation") or {}).get("ratios") or []}, "read", 8,
        ),
        "rotation_notes": _texts(obj.get("rotation_notes"), 3),
        "headlines": headlines[:6],
        "cross_asset": _text(obj.get("cross_asset")),
        "risks": _texts(obj.get("risks"), 4),
    }


# --------------------------------------------------------------------------
# The numeral guard — every number the model prints must be one it was shown.
# --------------------------------------------------------------------------
#
# THE RULE THE PROMPT STATES, NOW CHECKED (review, 2026-10-13). "Every claim
# must quote a figure from the digest" was an instruction and nothing more: a
# model that rounded 4.96% to 5%, worked out a difference, or invented a level
# printed it in the same frame as the server's exact tables. Ported from
# GEXYGEN's brief (lib/brief/schema.ts `numeralGuard`): exact on the VALUE,
# lenient on the spelling — "30,707", "30707" and "+30,707" are one number,
# "1.10" and "1.1" are one number. A rounded figure, a computed one and an
# invented one are exactly what it catches. One corrective re-ask names them;
# whatever survives is stored on the report as `unverified` for the page to
# flag — shown and marked, never passed off.

_NUM = re.compile(r"\d+(?:[.,]\d+)*")
_GROUPED = re.compile(r"^\d{1,3}(?:,\d{3})+(?:\.\d+)?$")


def _num_key(tok: str) -> str | None:
    """A numeral as a comparable key. Pure.

    A comma followed by exactly three digits groups thousands; any other comma
    is punctuation between two numbers ("3,4" is not three point four).
    """
    clean = tok.replace(",", "") if _GROUPED.match(tok) else tok.split(",")[0]
    try:
        v = float(clean)
    except ValueError:
        return None
    if not math.isfinite(v):
        return None
    return f"{round(v * 10_000) / 10_000:.4f}".rstrip("0").rstrip(".")


# AN INDEX'S NAME IS NOT A FIGURE: "mega-cap tech lagging S&P 500" put "500"
# in a London brief's unverified banner (2026-10-14). Only the names' own
# numbers — "Nasdaq 30,794" is still a price and still checked.
_INDEX_NAME = re.compile(
    r"\b(?:S&P|Nasdaq|Russell|FTSE|(?:Euro\s)?Stoxx|DAX|CAC|Nikkei|ASX|Hang\sSeng)"
    r"[\s-]?(?:40|50|100|200|225|250|500|600|1000|2000|3000)\b(?![.,]\d)",
    re.IGNORECASE,
)


def numerals_in(text: str) -> list[str]:
    """Every numeral in a text, as keys, in order. Pure."""
    out: list[str] = []
    for m in _NUM.finditer(_INDEX_NAME.sub(" ", text or "")):
        k = _num_key(m.group(0))
        if k is not None:
            out.append(k)
    return out


def brief_prose(b: dict[str, Any]) -> list[str]:
    """Every string the model wrote in a sanitised brief — what the guard reads. Pure."""
    out: list[str] = [b.get("thesis") or ""]
    for c in b.get("calls") or []:
        out += [*c.get("why", []), c.get("rest_of_day") or "", c.get("wrong_if") or ""]
    out += [x.get("note") or "" for x in b.get("snapshot_watch") or []]
    out += [b.get("gamma_read") or "", b.get("catalysts_intro") or ""]
    out += [x.get("note") or "" for x in b.get("catalyst_notes") or []]
    for r in b.get("reads") or []:
        out += [r.get("regime") or "", *r.get("chain", []), r.get("at_open") or "",
                r.get("wrong_if") or "", r.get("rest_of_day") or "", *r.get("flips", [])]
        for d in r.get("drivers") or []:
            out += [d.get("label") or "", d.get("text") or ""]
    out += [b.get("rotation_read") or ""]
    out += [x.get("read") or "" for x in b.get("ratio_reads") or []]
    out += list(b.get("rotation_notes") or [])
    out += [x.get("note") or "" for x in b.get("headlines") or []]
    out += [b.get("cross_asset") or "", *b.get("risks", [])]
    return [x for x in out if x]


def known_numerals(seen: str) -> set[str]:
    """The keys a note may print: every numeral in what the model saw, plus
    each one carrying three or more decimals rounded to two. Pure.

    TWO PLACES IS QUOTING, NOT ROUNDING (owner, 2026-10-14: "do what you
    recommend"). A London brief printed the dollar index 102.228 as "102.23"
    and the 10Y's 5.217% as "5.22%", and the red banner put both beside an
    invented level — so the banner taught the reader to skim past it. Dropping
    a third decimal changes nothing a trader reads; what the guard is for still
    fails: 4.96 written "5" (rounded further), 15.19 written "15.2" (a figure
    that already had two places), 4170.5 written "4171" (a level that isn't).
    """
    known = set(numerals_in(seen))
    for k in list(known):
        if "." in k and len(k.split(".")[1]) >= 3:
            two = Decimal(k).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
            if (kk := _num_key(str(two))) is not None:
                known.add(kk)
    return known


def unverified(b: dict[str, Any], seen: str) -> list[str]:
    """The numerals in the brief that the text the model was shown does not contain."""
    known = known_numerals(seen)
    bad: list[str] = []
    for s in brief_prose(b):
        for k in numerals_in(s):
            if k not in known and k not in bad:
                bad.append(k)
    return bad


def guard_retry(bad: list[str]) -> str:
    """The corrective re-ask — GEXYGEN's wording."""
    return (
        f"Your answer used numbers that do not appear in the data: {', '.join(bad[:12])}. "
        "Rewrite it using ONLY figures copied exactly from the data — no rounding, no "
        "arithmetic, no new levels. Where you wanted a number that is not printed there, "
        "say it in words. Return the whole JSON object again."
    )


def _reask(payload: dict[str, Any], key: str, content: str, bad: list[str],
           facts: dict[str, Any]) -> tuple[dict[str, Any] | None, dict[str, Any] | None, str]:
    """One corrective re-ask on the same model and mode → (brief, doc, outcome)."""
    retry = dict(payload)
    retry["messages"] = [*payload["messages"], {"role": "assistant", "content": content},
                         {"role": "user", "content": guard_retry(bad)}]
    try:
        doc = _post(retry, key)
        msg = doc["choices"][0]["message"]
        text = msg.get("content") or msg.get("reasoning") or ""
    except (urllib.error.URLError, OSError, ValueError, KeyError, IndexError, TypeError) as e:
        return None, None, f"re-ask failed: {e}"
    obj = extract_json(text if isinstance(text, str) else str(text))
    fixed = sanitize_brief(obj, facts) if obj is not None else None
    if fixed is None:
        return None, None, "re-ask did not return a brief"
    return fixed, doc, "re-asked"


def loose_ask(messages: list[dict[str, str]]) -> dict[str, str]:
    """The user turn, with the schema spelled out for the no-schema pass.

    In `json_object` mode the provider guarantees valid JSON and NOTHING about
    its shape, so the shape has to be in the prompt. Written as an annotated
    skeleton rather than as the JSON Schema itself: the schema is 90 lines of
    `additionalProperties` and `minItems` that cost tokens and describe
    validation rather than intent, and a model reads an example better.
    """
    return {
        "role": "user",
        "content": (
            messages[-1]["content"]
            + "\n\nReturn ONLY a JSON object, no prose around it, exactly this shape:\n"
            + """{
  "thesis": "one or two sentences",
  "calls": [ { "book": "NQ" | "ES" | "GC",
               "open_bias": one of "bullish" | "leaning bullish" | "neutral" |
                           "leaning bearish" | "bearish",
               "conviction": integer 1-5,
               "rest_of_day": "short label", "rest_of_day_bias": one of the same five,
               "wrong_if": "under 60 characters" } ],            // one per book in scope
  "snapshot_watch": [ { "key": "US10Y", "note": "..." } ],       // 0-5
  "gamma_read": "...",
  "catalysts_intro": "...",
  "catalyst_notes": [ { "id": "c2", "note": "..." } ],
  "reads": [ { "book": "NQ", "regime": "...", "chain": [ "...", "..." ],
               "at_open": "...", "wrong_if": "...", "rest_of_day": "...",
               "flips": [ "..." ],
               "drivers": [ { "label": "10Y", "text": "...",
                              "tone": "bear" | "bull" | "mixed" | "neutral" } ] } ],
  "rotation_read": "...",
  "ratio_reads": [ { "id": "QQQ/IWM", "read": "..." } ],
  "rotation_notes": [ "..." ],
  "headlines": [ { "id": "h3", "books": [ "NQ", "GC" ], "note": "..." } ],
  "cross_asset": "...",
  "risks": [ "..." ]
}"""
        ),
    }


def _post(
    payload: dict[str, Any], key: str, timeout: int = REQUEST_TIMEOUT_SEC
) -> dict[str, Any]:
    body = json.dumps(payload).encode("utf-8")
    req = urllib.request.Request(
        OPENROUTER,
        data=body,
        headers={
            "Authorization": f"Bearer {key}",
            "Content-Type": "application/json",
            "User-Agent": UA,
            # OpenRouter asks for these two so a request can be attributed;
            # they are not secret and not required, but sending them is the
            # polite side of a free tier.
            "HTTP-Referer": "http://localhost:3100",
            "X-Title": "HERMESX",
        },
    )
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return json.loads(r.read().decode("utf-8"))


def generate(
    snap: dict[str, Any],
    model: str | None = None,
    label: str = "manual",
    session: str = "auto",
    asset: str = "all",
) -> dict[str, Any]:
    """Build the digest, ask the model, store and return the report."""
    key = _key()
    now = datetime.now(UTC)
    et = now.astimezone(ET)
    model = model or DEFAULT_MODEL
    sess = resolve_session(snap.get("clock") or {}, session)
    book = resolve_asset(asset)

    base: dict[str, Any] = {
        "ok": False,
        "id": f"{et:%Y%m%d-%H%M%S}",
        "created_utc": now.isoformat(),
        "created_et": et.isoformat(),
        "et_label": et.strftime("%a %d %b, %H:%M ET"),
        "model": model,
        "label": label,
        "session": sess,
        "session_label": SESSIONS[sess]["label"],
        "asset": book,
        "asset_label": ASSETS[book]["label"],
        # "brief" since 2026-09-16. Reports stored before then have no format
        # and the old note's shape, and the panel still renders those.
        "format": "brief",
        "facts": None,
        "report": None,
        "error": None,
        "digest": None,
        "usage": None,
        # Numerals in the prose the data does not contain, after one re-ask —
        # the page banners them. Empty when every figure checked out.
        "unverified": [],
    }

    if not key:
        base["error"] = (
            "No OPENROUTER_API_KEY. Add one to .env.local and restart the collector — "
            "the report is written by a model and there is deliberately no local "
            "fallback that would invent a bias."
        )
        return base

    facts = build_facts(snap, sess, book)
    digest = build_digest(snap, sess, book, facts)
    base["digest"] = digest
    base["facts"] = facts
    # ONE progress reading shared by the prompt and the envelope, taken off the
    # snapshot's clock. Computing it twice would let a generation that straddles
    # 09:30 be instructed one way and labelled the other.
    prog = session_progress(sess, _now_et(snap))
    # Stored so the panel can label the note the way it was written — a call
    # made from mid-session printed under "At the open" is the same mistake in
    # the UI that the prompt just stopped making.
    base["session_underway"] = prog["underway"]

    messages = [
        {"role": "system", "content": system_prompt(sess, book, prog)},
        {
            "role": "user",
            "content": (
                f"Terminal snapshot at {digest.get('as_of_et')} "
                f"({digest.get('session_phase')}).\n\n"
                f"```json\n{json.dumps(digest, indent=1, default=str)}\n```\n\n"
                f"Write the brief for the {SESSIONS[sess]['label']} session, "
                + (
                    f"which opened {prog['phrase']} ago and is trading now — "
                    "write it from the current price, not for the open. "
                    if prog["underway"]
                    else f"which opens in {prog['phrase']} ({prog.get('opens_et')} ET). "
                )
                + f"About {ASSETS[book]['instruments']}. "
                f"Books in scope: {', '.join(facts['books'])}."
            ),
        },
    ]

    attempts: list[dict[str, Any]] = []
    # (model, mode) pairs, weakest-last.
    #
    # THE MODE HAS TO DEGRADE AS WELL AS THE MODEL, because "supports
    # structured_outputs" in OpenRouter's metadata describes the MODEL and the
    # request is served by a PROVIDER. On the first real run, dots-3-note's
    # provider rejected a strict schema outright with a 400 while advertising
    # support for it. `json_object` asks only for valid JSON, which nearly
    # every provider honours, and the schema is described in the prompt instead
    # — with `valid_report` checking the shape on the way back, since nothing
    # is enforcing it any more.
    plan: list[tuple[str, str]] = []
    for candidate in model_chain(model):
        plan.append((candidate, "schema"))
    for candidate in model_chain(model):
        plan.append((candidate, "json"))
    # Each pair gets more than one shot, because the failures are intermittent.
    plan = [pair for pair in plan for _ in range(TRIES_PER_PAIR)]

    started = time.monotonic()
    for candidate, mode in plan:
        if len(attempts) >= MAX_ATTEMPTS:
            break
        # RESERVE ROOM FOR THE ATTEMPT, do not merely check the budget is
        # unspent.
        #
        # This was `elapsed > BUDGET_SEC`, which bounds when an attempt may
        # START and says nothing about when the endpoint RETURNS: a request
        # beginning at 209s with the budget at 210 is allowed, and the caller
        # then waits for however long that request takes. Measured on a
        # saturated free pool: two attempts, 301 seconds, and a `curl -m 280`
        # gave up before the answer arrived.
        #
        # AND THE PER-REQUEST TIMEOUT IS NOT A CEILING EITHER. `urlopen`'s
        # `timeout` is per socket operation, not per request — every chunk that
        # arrives resets it. A reasoning model that trickles bytes while it
        # deliberates never idles for 70 seconds, so REQUEST_TIMEOUT_SEC = 70
        # sat there while single attempts ran past 150s. That is why the
        # reservation below is `_ATTEMPT_RESERVE` rather than
        # REQUEST_TIMEOUT_SEC: the reserve is what an attempt actually costs,
        # observed, not what the socket option claims to bound it at.
        elapsed = time.monotonic() - started
        if elapsed + _ATTEMPT_RESERVE > BUDGET_SEC:
            attempts.append({
                "model": candidate, "mode": mode,
                "error": (
                    f"not attempted — {elapsed:.0f}s of the {BUDGET_SEC:.0f}s budget "
                    f"spent, too little left to finish one"
                ),
            })
            break
        payload: dict[str, Any] = {
            "model": candidate,
            "messages": messages if mode == "schema" else [*messages[:-1], loose_ask(messages)],
            # Low but not zero: the schema already constrains the shape, and a
            # touch of variation keeps the prose from reading like a template.
            "temperature": 0.3,
            # 6000, NOT 2000, BECAUSE REASONING IS COUNTED IN IT.
            #
            # `max_tokens` caps completion tokens and the thinking is completion
            # tokens too — a trivial "return this JSON" ask to Nemotron spent 39
            # of its 48 there. The report body is around 1,200 tokens, so a
            # 2,000 budget left almost nothing once a reasoning model had
            # deliberated, and a truncated answer arrives here as the useless
            # "no JSON object in the answer".
            #
            # It is NOT a provider ceiling: `budget_probe.py` got a 404 at 200
            # and a clean answer at 4,000 from the same endpoint minutes apart.
            # That flakiness is handled by RETRYABLE, not by this number.
            #
            # Raised again to 12,000 after watching real runs come back with
            # `finish_reason=length` at 6,000 — a reasoning model handed the
            # full digest deliberates for thousands of tokens before it writes
            # anything, and a truncated answer costs the whole attempt.
            #
            # And to 16,000 for the brief (2026-09-16): its answer is about three
            # times the old note's — a thesis, then a call and a full read per
            # book — and the reasoning still comes out of the same budget.
            "max_tokens": 16000,
            # Ask for a short think rather than none: these models reason by
            # default and excluding it outright degrades the answer, but the
            # note does not need three thousand tokens of deliberation. Capped
            # in tokens, because an effort hint is ignored — see REASONING.
            "reasoning": REASONING,
        }
        if mode == "schema":
            payload["response_format"] = {
                "type": "json_schema",
                "json_schema": {"name": "session_bias", "strict": True, "schema": SCHEMA},
            }
        else:
            payload["response_format"] = {"type": "json_object"}

        try:
            doc = _post(payload, key)
        except urllib.error.HTTPError as e:
            # The body carries OpenRouter's actual complaint — a saturated
            # shared pool, an unknown model id, a schema the model cannot
            # honour — and the bare status code alone would send you looking in
            # the wrong place.
            detail = ""
            with contextlib.suppress(OSError):
                detail = e.read().decode("utf-8", errors="replace")[:400]
            err = f"HTTP {e.code}: {detail or e.reason}"
            attempts.append({"model": candidate, "mode": mode, "error": err})
            # A 400 on the strict schema is the provider refusing the
            # schema, not a bug in it — the loose pass exists for exactly
            # that, so keep going. Anything else non-retryable stops here.
            if e.code in RETRYABLE or (e.code == 400 and mode == "schema"):
                continue
            base["error"] = f"OpenRouter {err}"
            base["attempts"] = attempts
            return base
        except (urllib.error.URLError, OSError, ValueError) as e:
            attempts.append({"model": candidate, "mode": mode, "error": f"unreachable: {e}"})
            continue

        if doc.get("error"):
            msg = str(doc["error"].get("message", doc["error"]))
            attempts.append({"model": candidate, "mode": mode, "error": msg})
            if TRANSIENT_TEXT.search(msg):
                continue
            base["error"] = f"OpenRouter: {msg}"
            base["attempts"] = attempts
            return base

        try:
            choice = doc["choices"][0]
            msg = choice["message"]
            finish = choice.get("finish_reason")
        except (KeyError, IndexError, TypeError):
            attempts.append({"model": candidate, "mode": mode,
                             "error": "unexpected response shape"})
            continue

        # `content` CAN BE NULL, AND IS, ON REASONING MODELS. Several of them
        # return an empty content with the whole answer in `reasoning`, and one
        # crashed the generator outright by reaching `content[:2000]` on a
        # None. Coerced to a string, with `reasoning` as the fallback source —
        # the JSON is often in there verbatim and `extract_json` will find it.
        content = msg.get("content") or msg.get("reasoning") or ""
        if not isinstance(content, str):
            content = str(content)
        if not content.strip():
            attempts.append({
                "model": candidate, "mode": mode,
                "error": f"empty answer (finish_reason={finish})",
            })
            continue

        report = extract_json(content)
        if report is None:
            # Not "it ignored the schema" — the JSON may be there and wrapped.
            # `extract_json` already tried the fences and the preamble, so
            # reaching here means there is no object in the answer at all.
            attempts.append({
                "model": candidate, "mode": mode,
                # `finish_reason=length` here means the budget ran out mid
                # answer, which is a different fix from a model that will not
                # produce JSON at all.
                "error": f"no JSON object in the answer (finish_reason={finish}, "
                         f"{len(content)} chars)",
            })
            base["raw"] = content[:2000]
            continue
        brief = sanitize_brief(report, facts)
        if brief is None:
            attempts.append({
                "model": candidate, "mode": mode,
                "error": "JSON did not match the brief shape (needs a thesis, a readable "
                         f"call for each of {', '.join(facts['books'])}, and a read)",
            })
            base["raw"] = content[:2000]
            continue

        # THE NUMERAL GUARD (see `unverified`). What the model saw is the user
        # turn — the digest and its framing — so that is what a figure must
        # come from.
        seen = messages[-1]["content"]
        bad = unverified(brief, seen)
        if bad:
            note = f"unverified numerals: {', '.join(bad[:8])}"
            if (time.monotonic() - started) + _ATTEMPT_RESERVE <= BUDGET_SEC:
                fixed, doc2, outcome = _reask(payload, key, content, bad, facts)
                if fixed is not None and doc2 is not None:
                    bad2 = unverified(fixed, seen)
                    outcome = ("ok after re-ask" if not bad2
                               else f"re-ask still unverified: {', '.join(bad2[:8])}")
                    if len(bad2) < len(bad):
                        brief, bad, doc = fixed, bad2, doc2
                note += f" · {outcome}"
            attempts.append({"model": candidate, "mode": mode, "note": note})
        base["unverified"] = bad

        base["ok"] = True
        base["report"] = brief
        base["mode"] = mode
        # THE MODEL THAT ANSWERED, not the one asked for. A note written by the
        # second choice has to say so — "which model wrote this" is half the
        # provenance, and the panel prints this field.
        base["model"] = candidate
        base["usage"] = doc.get("usage")
        base["attempts"] = attempts
        _store(base)
        return base

    # Everything in the chain refused.
    base["attempts"] = attempts
    first = attempts[0]["error"] if attempts else "no models attempted"
    tried = ", ".join(f"{a['model']} ({a.get('mode', '?')})" for a in attempts)
    spent = time.monotonic() - started
    base["error"] = (
        f"Every free model refused in {spent:.0f}s. Tried: {tried}. "
        f"First reason — {first}"
    )
    return base


# --------------------------------------------------------------------------
# Storage — reports are kept so the calls can be judged later.
# --------------------------------------------------------------------------


def _store(rep: dict[str, Any]) -> None:
    os.makedirs(REPORTS_DIR, exist_ok=True)
    path = os.path.join(REPORTS_DIR, f"{rep['id']}.json")
    tmp = path + ".tmp"
    try:
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump(rep, f)
        os.replace(tmp, path)
    except OSError:
        return
    # Trim oldest beyond KEEP. A cache that cannot be pruned is a slower
    # history list, never a reason to lose the report just written.
    with contextlib.suppress(OSError):
        # `name`, not `f` — the file handle above is still bound to `f` at this
        # point and reusing it here is the same one-name-two-meanings shadow
        # that mypy caught in the source modules.
        files = sorted(n for n in os.listdir(REPORTS_DIR) if n.endswith(".json"))
        for name in files[:-KEEP]:
            os.remove(os.path.join(REPORTS_DIR, name))


def history(limit: int = 20) -> list[dict[str, Any]]:
    """Stored reports, newest first — id, time and the call, without the digest."""
    if not os.path.isdir(REPORTS_DIR):
        return []
    out: list[dict[str, Any]] = []
    try:
        files = sorted((f for f in os.listdir(REPORTS_DIR) if f.endswith(".json")), reverse=True)
    except OSError:
        return []
    for f in files[:limit]:
        try:
            with open(os.path.join(REPORTS_DIR, f), encoding="utf-8") as fh:
                d = json.load(fh)
        except (OSError, ValueError):
            continue
        r = d.get("report") or {}
        bias, conviction, headline = r.get("bias"), r.get("conviction"), r.get("headline")
        if d.get("format") == "brief":
            # A brief carries a call per book; the list shows the first, which
            # is the only one when the brief is scoped to a single book.
            first = (r.get("calls") or [{}])[0]
            bias, conviction = first.get("open_bias"), first.get("conviction")
            headline = r.get("thesis")
        out.append({
            "id": d.get("id"),
            "et_label": d.get("et_label"),
            "created_et": d.get("created_et"),
            "label": d.get("label"),
            "model": d.get("model"),
            "session": d.get("session"),
            "session_label": d.get("session_label"),
            "asset": d.get("asset"),
            "asset_label": d.get("asset_label"),
            "bias": bias,
            "conviction": conviction,
            "headline": headline,
        })
    return out


def load(report_id: str) -> dict[str, Any] | None:
    path = os.path.join(REPORTS_DIR, f"{os.path.basename(report_id)}.json")
    try:
        with open(path, encoding="utf-8") as fh:
            result: dict[str, Any] = json.load(fh)
            return result
    except (OSError, ValueError):
        return None


def latest() -> dict[str, Any] | None:
    h = history(1)
    return load(h[0]["id"]) if h and h[0].get("id") else None


def remove(report_id: str) -> bool:
    """Delete one stored report. True if a file went, False if there was none.

    `os.path.basename` for the same reason `load` uses it: the id arrives from
    the panel and is pasted into a path, so a traversal has to be impossible by
    construction rather than by trusting the caller. The route validates the
    shape as well — two locks on a door that only this app's own history list
    ever knocks on, because the cost of being wrong here is deleting something
    outside REPORTS_DIR.

    NOT RECOVERABLE, and deliberately not softened with a trash folder. The
    reports directory is already a KEEP-capped ring buffer that drops its oldest
    entries without ceremony; a second, quieter copy of the thing the owner
    just asked to be gone would be a surprise, not a safety net. The confirm
    step lives in the UI, where the person is.
    """
    path = os.path.join(REPORTS_DIR, f"{os.path.basename(report_id)}.json")
    try:
        os.remove(path)
    except OSError:
        return False
    return True


def configured() -> dict[str, Any]:
    """What the panel needs to explain itself when there is no key."""
    return {"enabled": bool(_key()), "model": DEFAULT_MODEL}
