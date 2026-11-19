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

THE ENGINE'S SCORE NOW SITS BESIDE THE MODEL'S VIEW (owner, 2026-10-22: "do
everything you recommend"). The driver board (drivers.py) reads each book's
drivers with stated thresholds and weighs them for the session (bias.py); the
digest hands the model that score, and `sanitize_brief` caps a call's conviction
at the board's ceiling, and at 3 against the board's lean — the game plan's rule
since 2026-10-14, applied here. The model still forms the view (the decision
above stands); it can no longer be more confident than the arithmetic.
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
from collections.abc import Iterable
from datetime import UTC, date, datetime, timedelta
from datetime import time as dtime
from decimal import ROUND_HALF_UP, Decimal
from typing import Any
from zoneinfo import ZoneInfo

from . import bias as bias_mod
from . import events as events_mod
from . import holidays as holidays_mod
from . import releases, structure
from .config import CACHE_DIR, UA
from .holidays import close_time, cme_closed, is_trading_day
from .profile import reads as profile_reads
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
from .volterm import BOOK_DP, EM_VOL, quote_key

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
# Ten attempts at up to ninety seconds each is fifteen minutes. Attempts are
# only STARTED while there is budget left (`_ATTEMPT_RESERVE` below), and each
# one is cut off at ATTEMPT_WALL_SEC, so the whole run is bounded at
# BUDGET_SEC - _ATTEMPT_RESERVE + ATTEMPT_WALL_SEC: eight minutes at the very
# worst, with a note at the end of it more often than not.
#
# 330 AND NOT 210 (2026-10-27). The budget used to fit inside the web proxy's
# 290s window, because the browser held the POST open for the whole
# generation. It no longer does — the POST starts a job and the page polls it
# (jobs.py) — so the budget is what a reader will wait, not what a proxy
# allows. And 210 with a 240s attempt cap would be worse than no cap at all:
# an attempt abandoned at 240s would leave no room to try the next model, and
# the one run that went long that morning (332s) was a VALID brief.
BUDGET_SEC = 330.0
REQUEST_TIMEOUT_SEC = 70

# HOW LONG ONE ATTEMPT MAY RUN, wall clock, before it is abandoned and the
# chain moves on to the next model.
#
# REQUEST_TIMEOUT_SEC does not bound this and cannot: it is passed to
# `urlopen`, whose timeout applies to each socket read, and OpenRouter keeps
# the connection alive with an 11-byte whitespace chunk every three seconds
# while the provider is still writing (measured 2026-10-27). A free pool that
# has slowed to a crawl therefore never idles for 70 seconds — one brief ran
# 332s and a second generation the same morning ran nine minutes and produced
# nothing, with nothing in this file able to stop either. `_post` reads the
# body a chunk at a time and checks this deadline between chunks, which the
# keep-alive turns into a check every three seconds.
#
# 240 IS ABOVE EVERY GOOD REPORT ON RECORD. The eight stored before the cap
# took 92, 97, 130, 141, 163, 179 and 213 seconds, and then 332. A cap has to
# sit clearly above the normal range so that it only fires on a run that has
# gone wrong; 150 — the first figure proposed — would have cut three briefs
# that were fine.
ATTEMPT_WALL_SEC = 240.0

# What one attempt is assumed to cost when deciding whether to start another.
#
# The TYPICAL cost, not the cap. Reserving ATTEMPT_WALL_SEC would let a second
# attempt follow only a quick refusal, never a slow one — and a slow first
# attempt is exactly when the fallback is wanted. Measured at ~150s against a
# saturated free pool; 90 leaves the budget room for one fallback after an
# attempt that ran to the cap.
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
            "rather than follow it."
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
            "09:30 open set the day."
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
    "SIL": ("SI_silver_futures",),
    "CL": ("CL_crude_futures",),
}

# THE MARKET REPORT'S FOUR SUBJECTS (owner, 2026-11-15: "we have a pill selector where
# we can select say Indexes, gold, silver, oil and then another pill ... Asia, London,
# New York"). `indexes` is NQ and ES together, each with its ETF, which is one subject:
# QQQ and SPY are the same two indexes in another wrapper. Gold, silver and crude are
# one book each. `all` (the three the brief began with) and the single index books stay
# so a note stored under them still opens with its own label; the page no longer
# offers them.

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
    "indexes": {
        "label": "Indexes",
        "instruments": "NQ/QQQ and ES/SPY",
        "drivers": (
            "The two US equity indexes, each a future and the ETF on the same index: a level "
            "on NQ is a level on QQQ and a level on ES one on SPY, so write the call once per "
            "index. It holds for both wrappers and the reader knows it: spend no words saying "
            "so. Say where the Nasdaq and the S&P agree "
            "and, more usefully, where they do not: the Nasdaq leading or lagging the broader "
            "index is itself the read. `index_movers` usually IS the Nasdaq's story; sector "
            "rotation and breadth carry more of the S&P's."
        ),
    },
    "SIL": {
        "label": "Silver",
        "instruments": "silver futures (SIL)",
        "drivers": (
            "Silver is a monetary metal with an industrial half, and NOT an equity index: the "
            "equity blocks mostly do not apply to it. What moves it: real yields, the policy "
            "path and the dollar, as they move gold; gold itself, which silver follows and "
            "then outruns in both directions; and copper, which says whether the industrial "
            "half is with the move. The gold/silver ratio says which metal is leading. Ignore "
            "sector rotation and index constituents unless equities are moving hard enough to "
            "be a risk signal in their own right."
        ),
    },
    "CL": {
        "label": "Crude oil",
        "instruments": "WTI crude oil futures (CL)",
        "drivers": (
            "Crude is a dollar-priced barrel that trades on demand, on its own stocks and on "
            "supply risk, and NOT an equity index: the equity blocks mostly do not apply to "
            "it. What moves it: the dollar; the products (gasoline and heating oil: whether "
            "refiners are pulling the barrel through); the demand read from copper and credit; "
            "the weekly inventories; and the Gulf, OPEC and war headlines, which are supply "
            "risk and cut either way. Brent beside WTI says whether a move is the world's or "
            "America's. The 10-year and the VIX are not crude votes. Ignore sector rotation "
            "and index constituents unless equities are moving hard enough to be a demand "
            "signal in their own right."
        ),
    },
}

#: The Stocks desk's report (owner, 2026-11-16: "in stocks it will just be combination
#: overview of SPY, QQQ, IWM with just NY for the session", the market report sheet the
#: Futures tab has). The three index funds in one report, New York only, read through
#: the Stocks tape count, which is one bias for all three (`_etf_facts`).
ETF_ASSET = "etfs"
ETF_BOOKS: tuple[str, ...] = ("SPY", "QQQ", "IWM")
ASSETS[ETF_ASSET] = {
    "label": "SPY · QQQ · IWM",
    "instruments": ("SPY, QQQ and IWM, the index funds on the S&P 500, the Nasdaq 100 "
                    "and the Russell 2000"),
    "drivers": (
        "The three index funds the stocks desk trades the session through, in one report "
        "for New York. QQQ is the cap-weighted Nasdaq 100, where a handful of megacaps are "
        "the move and the front of the curve hits hardest; SPY is the broad S&P 500, where "
        "sector rotation and breadth carry more of it; IWM is the Russell 2000's small caps, "
        "the most rate-sensitive and the most domestic of the three, which lead or lag the "
        "others on the curve and on credit. Say where the three agree and, more usefully, "
        "where they do not: small caps against megacaps is itself the read."
    ),
}

#: The books behind a subject that is more than one.
ASSET_BOOKS: dict[str, tuple[str, ...]] = {
    "all": ("NQ", "ES", "GC"),
    "indexes": ("NQ", "ES"),
    ETF_ASSET: ETF_BOOKS,
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
    """The open-vs-value and now-vs-value facts for one asset's profiles.

    PROFILE'S NOW (2026-10-22): the source attaches `reads` to every asset
    (profile.reads) so the Volume profile panel prints the same facts this
    digest carries; a snapshot from an older collector is read the same way.
    `session` is unused and kept for the call sites.
    """
    del session
    got = asset.get("reads")
    if isinstance(got, dict):
        return {k: v for k, v in got.items() if k != "text"}
    return {k: v for k, v in profile_reads(asset).items() if k != "text"}


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

#: Every book a brief can carry a call for. Silver and crude since 2026-11-15, when the
#: driver board came to score them (drivers.py, bias.py).
BOOKS: tuple[str, ...] = ("NQ", "ES", "GC", "SIL", "CL")
#: The books that are an equity index, with the ETF on each.
INDEX_BOOKS: tuple[str, ...] = ("NQ", "ES")
BOOK_LABELS = {"NQ": "NQ", "ES": "ES", "GC": "Gold (GC)", "SIL": "Silver (SIL)", "CL": "Crude (CL)"}
# BOOK_DP AND EM_VOL ARE VOLTERM'S NOW (imported above): the Terminal's
# implied-day rows quote the same decimals and read the same index per book, so
# the two maps are stated once, there. BOOK_DP: NQ in whole points, ES in
# quarters, gold in tenths — a ladder printing 29,408.00 carries three
# characters of noise a row. EM_VOL: the implied vol that stands in for the
# expected move when GEXYGEN is not answering — a one-day, one-standard-deviation
# move, labelled as exactly that on the page because it is wider than an options
# desk's own band and must not be mistaken for it.

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
    return list(ASSET_BOOKS[book]) if book in ASSET_BOOKS else [book]


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
    equity = any(b in books for b in INDEX_BOOKS)
    metal = any(b in books for b in ("GC", "SIL"))
    rows: list[dict[str, Any]] = []

    for b in books:
        # Silver and crude ride the board, and the daily context, as SILVER and WTI.
        q = _q(quotes, quote_key(b))
        if not q:
            continue
        bits: list[str] = []
        if q.get("prev") is not None:
            bits.append(f"settle {q['prev']:,.{BOOK_DP[b]}f}")
        bits += _wk_mo(_ctx(snap, quote_key(b)), month=True)
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

    if metal:
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

    # Each book's own vol index, off the daily context: gold's, silver's, crude's.
    for b, key in (("GC", "GVZ"), ("SIL", "VXSLV"), ("CL", "OVX")):
        vol = _ctx(snap, key) if b in books else None
        if vol and vol.get("last") is not None:
            rows.append(_srow(key, key, vol["last"], 1, chg=vol.get("day_pct"),
                              sub=" · ".join(_wk_mo(vol))))

    # Crude is a context row on every other note; on its own it is the book above, and
    # what stands beside it is Brent and the two products.
    if "CL" in books:
        for key, label, dp in (("BRENT", "Brent", 2), ("RBOB", "Gasoline", 4),
                               ("HEATOIL", "Heating oil", 4)):
            leg = _q(quotes, key)
            if leg:
                rows.append(_srow(key, label, leg["last"], dp, chg=leg.get("pct"),
                                  sub=aged(leg, [])))
    else:
        wti = _q(quotes, "WTI")
        if wti:
            rows.append(_srow("WTI", "WTI", wti["last"], 2, chg=wti.get("pct"),
                              sub=aged(wti, _wk_mo(_ctx(snap, "WTI"), month=True))))

    jpy = _q(quotes, "USDJPY")
    if jpy:
        rows.append(_srow("USDJPY", "USD/JPY", jpy["last"], 2, chg=jpy.get("chg"), unit="pts",
                          sub=aged(jpy, _wk_mo(_ctx(snap, "USDJPY")))))

    if "GC" in books and "SIL" not in books:
        si = _q(quotes, "SILVER")
        if si:
            rows.append(_srow("SILVER", "Silver", si["last"], 2, chg=si.get("pct"),
                              sub=aged(si, _wk_mo(_ctx(snap, "SILVER")))))
    # Silver's note reads gold beside it, and both metals' notes and crude's read copper.
    if "SIL" in books and "GC" not in books:
        gc = _q(quotes, "GC")
        if gc:
            rows.append(_srow("GOLD", "Gold", gc["last"], 1, chg=gc.get("pct"),
                              sub=aged(gc, _wk_mo(_ctx(snap, "GC"), month=True))))
    if any(b in books for b in ("SIL", "CL")):
        cu = _q(quotes, "COPPER")
        if cu:
            rows.append(_srow("COPPER", "Copper", cu["last"], 2, chg=cu.get("pct"),
                              sub=aged(cu, [])))
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
    snap: dict[str, Any], book: str, session: str, now: datetime, live: bool = False
) -> dict[str, Any] | None:
    """Every price the session trades against, in price order, measured from last.

    `live` is the Structure tab's ladder (2026-10-30): the brief's rows plus
    the ones a note does not need but a desk watching the tape does — VWAP
    from the reopen and from the cash open, the opening range, and today's
    two opens — read from the ranges source, which computes them from the
    same bars as the session boxes."""
    q = _q(snap.get("quotes") or [], quote_key(book)) or {}
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
    # New York opens into everything traded since 18:00 — the ranges' own
    # `overnight` box (sessions.OVERNIGHT), one row from the reopen to the
    # cash open, so a print in the gap between the Asia and London boxes still
    # counts; London opens into Asia. An Asia note's handover is the New York
    # day, which the prior-RTH rows below already carry, so it gets no range
    # row of its own.
    sessions = {s.get("key"): s for s in rng.get("sessions") or [] if s.get("ok")}
    handover = {
        "ny": (("overnight",), "ON"),
        "london": (("asia",), "Asia"),
    }
    if session in handover:
        keys, prefix = handover[session]
        # TODAY'S WINDOWS ONLY (review, 2026-10-14). A row that has not come
        # round again is yesterday's — at 07:50 ET the old Pre-NY row went into
        # the max with the rest, and the ladder printed yesterday's high,
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

    if live:
        vw = rng.get("vwap") or {}
        add(vw.get("globex"), "VWAP since 18:00", "vwap")
        add(vw.get("rth"), "VWAP since 09:30", "vwap")
        orange = rng.get("opening_range") or {}
        if orange.get("high") is not None:
            tag = "" if orange.get("complete") else " so far"
            add(orange["high"], f"Opening range high{tag}", "range")
            add(orange["low"], f"Opening range low{tag}", "range")
        on = sessions.get("overnight")
        if on and not on.get("prior_day"):
            add(on.get("open"), "Globex open 18:00", "open")
        ny = sessions.get("ny")
        if ny and not ny.get("prior_day"):
            add(ny.get("open"), "RTH open 09:30", "open")
    # The ten-minute 200 EMA is a level the note can use too (owner, 2026-10-30:
    # "does the analysis generate take into consideration the EMAs?").
    e200 = rng.get("ema200_10m") or {}
    add(e200.get("value"), "200 EMA (10m)", "ema")

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

    # THE BANDS, THE FUEL, YESTERDAY'S SHAPE AND THE REGIME LINE (structure.py,
    # 2026-10-30). The band width and the fuel's yardstick are the book's own
    # daily ATR (history.py); without one, the expected move stands in for the
    # width and the fuel line says only what it can.
    frame = ((snap.get("history") or {}).get("books") or {}).get(book) or {}
    atr = frame.get("atr14") if isinstance(frame, dict) and frame.get("ok") else None
    bands = structure.confluence(out, atr or em, last, dp)
    # The cards ride with every ladder, the note's included: the brief reads
    # fuel, yesterday's shape and the regime line the same way the tab does.
    cards: dict[str, Any] = {
        "confluence": bands,
        "fuel": structure.fuel(rng.get("sessions") or [], atr, em, dp),
        "yesterday": structure.yesterday(rng.get("sessions") or [], atr, q.get("prev"), dp),
        "regime": structure.regime(frame if isinstance(frame, dict) else None, last, dp),
        "ema200_10m": rng.get("ema200_10m"),
    }

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
        "rows": out, "note": " ".join(notes) or None, **cards,
    }


def live_ladder(snap: dict[str, Any], book: str) -> dict[str, Any] | None:
    """One book's live ladder, for the futures chart's levels."""
    try:
        return _ladder(snap, book, "ny", _now_et(snap), live=True)
    except (ValueError, TypeError, KeyError, AttributeError, ZeroDivisionError):
        return None


def live_ladders(snap: dict[str, Any]) -> dict[str, Any]:
    """The Structure tab's levels, one ladder per book, off the snapshot's own
    clock — computed per request (api.py /api/terminal), never stored, so the
    page and Hermes read the same figures the brief would."""
    now = _now_et(snap)
    out: dict[str, Any] = {}
    for book in BOOK_LABELS:
        try:
            out[book] = _ladder(snap, book, "ny", now, live=True)
        except (ValueError, TypeError, KeyError, AttributeError, ZeroDivisionError):
            out[book] = None
    return out


def _session_type(snap: dict[str, Any], books: list[str]) -> dict[str, Any]:
    """Will New York trend or range, per book (daytype.py, computed on read in the
    snapshot): the record's counts for a day like today, the call, and the rule for
    reading it. The model narrates the counts; it never turns them into odds."""
    held = (snap.get("daytype") or {}).get("books") or {}
    out: dict[str, Any] = {
        "how_to_read": "Counts over the record's sessions, never probabilities: the call is "
                       "the side the holding conditions' counts lean to, 'No lean' means the "
                       "record does not separate today, and a condition under 50 sessions is "
                       "shown but does not vote. Quote the counts ('2 trend days in 142'), "
                       "not a percentage, and say 'so far' while the night is not finished.",
        "record": (snap.get("daytype") or {}).get("record"),
    }
    for b in books:
        e = held.get(b)
        if not isinstance(e, dict) or not isinstance(e.get("lean"), dict):
            continue
        ln = e["lean"]
        out[b] = {"call": ln.get("word"), "why": ln.get("why"), "night": ln.get("night"),
                  "yesterday": ln.get("prev"), "holds": ln.get("holds"), "base": ln.get("base"),
                  "today_finished_as": e.get("label")}
    return out


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


#: A central bank's decision, wherever it is made: it reaches every book through rates and FX.
_DECISION = re.compile(r"rate decision|interest rate|monetary policy|press conference", re.I)
_SPEAKS = re.compile(r"\b(?:speaks|testifies|speech|testimony)\b", re.I)
_CHAIR = re.compile(r"(?<!vice )\bchair\b", re.I)
_NAME_SUFFIX = frozenset({"jr", "sr", "ii", "iii"})


def high_for_the_books(rows: Iterable[dict[str, Any]]) -> bool:
    """Is this release HIGH IMPACT FOR THE BOOKS THE NOTE IS ABOUT? Pure.

    THE CHIP SAID "HIGH IMPACT" FOR WHOEVER PUBLISHED IT (owner, 2026-11-12: "fix
    catalyst ... weighting"). It was lit by the calendar's score of 4, which a
    tier-one print earns in its own country: on an NQ brief UK GDP, Euro Zone GDP and a
    Japanese PPI each wore the chip a US jobless-claims print wears, and so did a
    governor's speech on another subject. For NQ, ES and gold the tape stops for a US
    tier-one release (score 5) and for a central bank's decision anywhere; a foreign
    print is still listed, and a speech is high only when it is the Chair's."""
    for x in rows:
        event, sc = str(x.get("event") or ""), int(x.get("score") or 0)
        if _SPEAKS.search(event):
            if _CHAIR.search(event):
                return True
            continue
        if sc >= 5 or (sc >= 4 and _DECISION.search(event)):
            return True
    return False


def _speaker(title: Any) -> str:
    """A diary speech's last name, lower case: "Speech - Governor Michael S. Barr" → "barr"."""
    words = [w.strip(",.").lower() for w in str(title or "").split()]
    while words and words[-1] in _NAME_SUFFIX:
        words.pop()
    return words[-1] if words else ""


def _holiday_catalysts(now: datetime) -> list[dict[str, Any]]:
    """Today's and the next three days' market holidays and early closes, as catalysts:
    a day the bond market, London or Tokyo is shut changes what the other rows mean."""
    out: list[dict[str, Any]] = []
    for h in holidays_mod.notices(now.date(), now.date() + timedelta(days=3)):
        d = date.fromisoformat(str(h["date"]))
        at = datetime(d.year, d.month, d.day, tzinfo=ET)
        day = _when_label(at, now).split(" ")[0]
        out.append(_cat(
            "holiday", at, now, f"{h['label']} · {h['name']}",
            when=f"{day} all day" if h["kind"] == "closed" else day,
            country=h["country"], note=h["note"]))
    return out


#: A release that is crude's own, wherever it prints (lib/futures.ts ENERGY, by hand).
_ENERGY_EVENT = re.compile(
    r"crude|\boil\b|\beia\b|opec|gasoline|distillate|baker hughes|rig count", re.I)


#: EARLIER THIS WEEK (owner, 2026-11-19: "economic calender events on the day or earlier in
#: the week that have an impact"). The calendar read twelve hours back; a high-impact US
#: print or a Fed decision from earlier in the week is still in the price and is why yields
#: or the dollar sit where they do. So the calendar also reaches back to the week's
#: Monday, and three days at least (a Monday report reads Friday's payrolls), for what
#: has printed and is high impact for the books: flagged `earlier`, at most this many.
WEEK_BACK_DAYS = 3
WEEK_BACK_MAX = 6
#: How far back a heavyweight's results stay on the calendar: the evening before's too.
EARNINGS_BACK_H = 30


def _week_lo(now: datetime) -> float:
    """The earliest instant the calendar reads back to for this week's prints. Pure."""
    monday = (now - timedelta(days=now.weekday())).replace(hour=0, minute=0, second=0,
                                                            microsecond=0)
    return min(monday.timestamp(), (now - timedelta(days=WEEK_BACK_DAYS)).timestamp())


def _catalysts(snap: dict[str, Any], books: list[str], now: datetime) -> list[dict[str, Any]]:
    """Everything scheduled from twelve hours back to three days out, in time order, and
    this week's high-impact prints before that (`earlier`, WEEK_BACK_DAYS)."""
    now_ts = now.timestamp()
    lo, hi = now_ts - 12 * 3600, now_ts + 3 * 86400
    week = _week_lo(now)
    items: list[dict[str, Any]] = []

    data: list[dict[str, Any]] = []
    for r in snap.get("calendar") or []:
        ts = r.get("ts")
        if ts is None or not week <= ts <= hi or (r.get("score") or 0) < 3:
            continue
        # `core` is the calendar's own "does this reach NQ, ES or GC" test.
        # Without it the first live brief (2026-09-15) listed eleven foreign
        # CPI and PPI prints by title alone — "CPI", "CPI", "Core CPI".
        # Crude's own releases (the weekly inventories, OPEC) carry no macro theme, so
        # the calendar does not mark them core: a crude note lists them by name.
        if not r.get("core") and not ("CL" in books and _ENERGY_EVENT.search(
                str(r.get("event") or ""))):
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
        # Before the twelve hours: only what printed and is high impact for the books.
        earlier = r["ts"] < lo
        if earlier and not (any(bool(x.get("released")) for x in rel.rows)
                            and high_for_the_books(rel.rows)):
            continue
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
            high=high_for_the_books(rel.rows),
            # Whose figure the actual is, when it is the agency's own and not only
            # the calendar feed's (sources/official.py): "BLS", "Census", "BEA", "EIA".
            **({"official": r["official"].get("by")}
               if isinstance(r.get("official"), dict) else {}),
            **({"also": [{"title": x.get("event"), "actual": x.get("actual_raw"),
                           "consensus": x.get("consensus_raw"),
                           "previous": x.get("previous_raw")} for x in rel.subs]}
               if rel.subs else {}),
            **({"earlier": True} if earlier else {}),
            # What the release is about (calendar.themes_of): whether the bias counts it
            # (`bias_links`: an index book counts inflation prints alone).
            themes=[str(t) for t in r.get("themes") or []],
        ))

    # The FOMC a week out is on the brief every day of that week; a speech is
    # only worth a row inside the three-day window.
    meetings = {m.get("date"): m for m in (snap.get("policy_meetings") or {}).get("meetings") or []}
    for e in snap.get("fed") or []:
        ts = e.get("ts")
        if ts is None or not week <= ts <= now_ts + 7 * 86400 or (not e.get("major") and ts > hi):
            continue
        # Earlier this week: a decision or the Chair's word only (`major`).
        if ts < lo and not e.get("major"):
            continue
        note = e.get("note")
        m = meetings.get(e.get("date")) if e.get("kind") == "FOMC" else None
        if m and m.get("move_bp") is not None and m.get("implied_after") is not None:
            note = (f"{m['move_bp']:+.0f}bp priced ({m.get('stance')}), "
                    f"{m['implied_after']:.2f}% implied after")
        # ONE SPEECH, ONE ROW. The calendar lists "FOMC Member Barr Speaks" and the
        # Board's diary "Speech - Governor Michael S. Barr", the same speech at the same
        # minute: both were catalysts, both "High impact". The calendar's row stays and
        # takes the diary's note, which is what the speech is about.
        if e.get("kind") in ("Speech", "Testimony"):
            who = _speaker(e.get("title"))
            twin = next((c for c in items if c["kind"] == "data" and abs(c["ts"] - ts) < 90
                         and who and who in str(c["title"]).lower()), None)
            if twin is not None:
                twin["note"] = twin.get("note") or note
                continue
        items.append(_cat("fed", datetime.fromtimestamp(ts, ET), now, e.get("title"),
                          country="US", released=ts < now_ts, high=bool(e.get("major")),
                          note=note, **({"earlier": True} if ts < lo else {})))

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

    if any(b in books for b in INDEX_BOOKS):
        # Thirty hours back, not twelve (2026-11-19): by 09:00 a heavyweight's results of
        # the evening before (16:05) were seventeen hours old and off the list, and they
        # are what a morning report most has to say something about.
        lo_earn = now_ts - EARNINGS_BACK_H * 3600
        for e in snap.get("earnings") or []:
            if not e.get("bellwether") and (e.get("market_cap") or 0) < 200e9:
                continue
            when = _earnings_moment(e)
            if when is None or not lo_earn <= when.timestamp() <= now_ts + 2 * 86400:
                continue
            said = {"pre": "before the open", "after": "after the close"}.get(
                str(e.get("when") or ""), "time TBC")
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
    done = [c for c in items if c["ts"] < now_ts and not c.get("earlier")][-6:]
    # This week's earlier prints have their own few, so the morning's releases do not
    # push them off, nor they the morning's.
    week_done = [c for c in items if c.get("earlier")][-WEEK_BACK_MAX:]
    # A holiday is a day, not a minute: today's stays on the list all day, at the head of its day.
    kept = sorted(week_done + done + ahead + _holiday_catalysts(now), key=lambda c: c["ts"])
    for i, c in enumerate(kept, start=1):
        c["id"] = f"c{i}"
    return kept


def _leg(snap: dict[str, Any], key: str) -> dict[str, Any] | None:
    row = next((s for s in snap.get("sectors") or [] if s.get("key") == key), None)
    return row or _ctx(snap, key)


def _rotation(snap: dict[str, Any], books: list[str]) -> dict[str, Any]:
    """The ratio strip with five-day direction, and the index heavyweights' moves."""
    specs: list[tuple[str, str, str, str]] = []
    if any(b in books for b in INDEX_BOOKS):
        specs += [(name, a, b, "equity") for name, a, b in EQUITY_RATIOS]
    if "GC" in books:
        specs += [(name, a, b, "gold") for name, a, b in GOLD_RATIOS]
    elif "SIL" in books:
        # Silver's own note reads the one ratio that is about silver.
        specs += [(name, a, b, "gold") for name, a, b in GOLD_RATIOS if "Silver" in name]

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


#: Headlines the digest carries, and how many of them may be medium-impact
#: stories from outside the session's own regions.
HEADLINES_MAX = 32
HEADLINES_ELSEWHERE = 8


def _headlines(snap: dict[str, Any], session: str, now: datetime) -> list[dict[str, Any]]:
    """The material wire, most important first, each with an id the brief picks by.

    RANKED BY WHAT IT IS, NOT BY HOW NEW IT IS (audit, 2026-11-05). This took
    the first twenty-four of the session's regions and eight of the rest, and
    the wire is newest first with medium and HIGH mixed, so the cut fell by the
    clock. Read against the live wire that morning: twenty-one HIGH stories on
    the wire, two of them handed to the model — a note could not weigh what it
    was never shown. Now one row per story (eight tellings of one rate decision
    are one story, with `also` saying how many), HIGH first, then what has
    landed since the last cash close, then the session's own regions.

    WEIGHTED TO THE SESSION BEING TRADED. For an Asia note, an item from
    Nikkei Asia or the RBA is worth more than a US market wrap, and the reverse
    holds at 09:00 ET. Nothing HIGH is dropped for being from the wrong desk — a
    strike on a refinery is an Asia story too; only the medium stories from
    elsewhere are capped.
    """
    homes = _session_homes(session)
    since = events_mod.last_close(now).timestamp()

    def stamp(h: dict[str, Any]) -> float:
        ts = h.get("ts")
        return float(ts) if isinstance(ts, int | float) else 0.0

    material = sorted(
        (h for h in snap.get("wire") or [] if h.get("impact") in {"high", "medium"}),
        key=lambda h: (h.get("impact") != "high", stamp(h) < since,
                       h.get("region") not in homes, -stamp(h)),
    )
    kept: list[tuple[dict[str, Any], int]] = []
    elsewhere = 0
    for h, also in events_mod.distinct_stories(material):
        if len(kept) >= HEADLINES_MAX:
            break
        if h.get("impact") != "high" and h.get("region") not in homes:
            if elsewhere >= HEADLINES_ELSEWHERE:
                continue
            elsewhere += 1
        kept.append((h, also))
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
            **({"also": also} if also else {}),
        }
        for i, (h, also) in enumerate(kept, start=1)
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
    if any(b in books for b in INDEX_BOOKS):
        wanted += ["VIX", "VXN", "VIX3M"]
    if "SIL" in books:
        wanted += ["SILVER", "GC", "COPPER"]
    if "CL" in books:
        wanted += ["BRENT", "RBOB", "HEATOIL", "COPPER"]
    have = {q.get("key") for q in snap.get("quotes") or []}
    missing = [k for k in wanted if k not in have]
    if missing and (status.get("quotes") or {}).get("ok"):
        out.append(f"No quote for {', '.join(missing)}.")
    return out


# --------------------------------------------------------------------------
# What is driving the bias, as the report prints it (2026-11-15).
# --------------------------------------------------------------------------
#
# THE REPORT NAMES EVERY FACTOR THE BIAS WEIGHS (owner: "we should mention all the
# factors impacting the bias, like news, macro, geopolitics important news, volume
# profile structure"). The short brief gave the model three bullets to pick reasons
# with, and what it left out was simply not on the page. So the page now carries one
# row for every family with a weight in this session, in the engine's order, with the
# engine's own tag and share of the score: those cannot disagree with the slider,
# because they are the same arithmetic. The model writes the comment beside each.
#
# DEALER GAMMA IS NOT A ROW AND IS NOT IN THE REPORT (the same message: "i dont think
# we need to mention gex"). It has not voted since 2026-11-12; a regime that is no
# side had a card, a ladder of walls and a clause in every plan. It stays on the
# Futures page. Event risk is not a side either, but it lowers the ceiling on the
# call, and the owner named it: it is the last row, marked for what it does.
#
# PLAIN NAMES. "Catalysts" is News & data, "Rates & dollar" is Macro, "Intraday
# structure" is Volume profile & structure.
#
# NO TREND ROW (owner, the same day: "i dont think we need to include about the
# ema's", then "i think we drop ema's from the bias and scoring of stocks"). The bias
# has no trend family to print (bias.BOARD_FAMILY has the why), and the model is not
# handed a moving average to write about (`report_view`).

#: family → (the row's name, the small line under it).
FACTOR_NAMES: dict[str, tuple[str, str | None]] = {
    "catalysts": ("News & data", None),
    "rates": ("Macro", "rates & dollar"),
    "risk": ("Risk appetite", None),
    "structure": ("Volume profile & structure", None),
    "participation": ("Participation", "sectors & leaders"),
}
BOOK_FACTOR_NAMES: dict[str, dict[str, tuple[str, str | None]]] = {
    "SIL": {"rates": ("Macro", "rates, dollar & metals")},
    "CL": {"rates": ("Macro", "dollar & products"), "risk": ("Demand", "credit & copper"),
           "catalysts": ("Inventories & data", None)},
}
#: Every key a factor comment may carry: the families and the event row.
FACTOR_KEYS: tuple[str, ...] = (*FACTOR_NAMES, "event")
_LEADING_INT = re.compile(r"^\s*(\d+)")


def factors_of(book: str, board: dict[str, Any]) -> list[dict[str, Any]]:
    """One row a factor for a book's board, heaviest first, the event row last. Pure.

    `lean` is what the family's own score says: bull or bear by its sign, mixed when
    it is level with votes both ways, neutral when nothing leans, none when no vote
    in it can speak at this hour. `reads` are the engine's figures behind it, for the
    hover and for a report whose model wrote no comment.
    """
    votes = [v for v in board.get("votes") or [] if isinstance(v, dict)]
    names = {**FACTOR_NAMES, **BOOK_FACTOR_NAMES.get(book, {})}
    if book == "TAPE":
        names = {**names, **TAPE_FACTOR_NAMES}
    out: list[dict[str, Any]] = []
    for fam in board.get("families") or []:
        key = fam.get("key") if isinstance(fam, dict) else None
        weight = int(fam.get("weight") or 0) if isinstance(fam, dict) else 0
        if not isinstance(key, str) or weight <= 0:
            continue
        mine = [v for v in votes if v.get("family") == key]
        live = [v for v in mine if v.get("can_vote_now")]
        score = fam.get("score")
        longs = sum(1 for v in live if v.get("vote") == "long")
        shorts = sum(1 for v in live if v.get("vote") == "short")
        if not live or score is None:
            lean, tag = "none", "Nothing yet" if key == "catalysts" else "Not live yet"
        elif score > 0:
            lean, tag = "bull", "Bullish"
        elif score < 0:
            lean, tag = "bear", "Bearish"
        elif longs and shorts:
            lean, tag = "mixed", "Mixed"
        else:
            lean, tag = "neutral", "Neutral"
        name, sub = names.get(key, (str(fam.get("label") or key), None))
        out.append({
            "key": key, "name": name, "sub": sub, "weight": weight, "lean": lean, "tag": tag,
            "reads": [f"{v.get('label')}: {v.get('value')}"
                      for v in mine if v.get("value") not in (None, "", "—")],
        })
    ev = next((v for v in votes if v.get("label") == "Event risk"), None)
    m = _LEADING_INT.match(str((ev or {}).get("value") or ""))
    n = int(m.group(1)) if m else 0
    note = str((ev or {}).get("note") or "").strip()
    out.append({
        "key": "event", "name": "Geopolitics & events", "sub": "lowers conviction, not a side",
        "weight": None, "lean": "damp" if n else "neutral",
        "tag": f"{n} stor{'y' if n == 1 else 'ies'}" if n else "Quiet",
        "reads": [note] if n and note else ["No high-impact story since the close"],
    })
    return out


def key_levels(snap: dict[str, Any], book: str,
               ladder: dict[str, Any] | None) -> dict[str, Any] | None:
    """The levels a call is traded against, low to high, for the report's ruler: the
    prior session's high and low, its value area and point of control, the handover
    range and the last price. No gamma level and no trend line: those are not the
    report's. At the book's own decimals, as the page prints them. Pure."""
    if not ladder:
        return None
    dp = int(ladder.get("dp") or 0)

    def at(x: float) -> float:
        return round(x, dp) if dp else round(x)

    prof = ((snap.get("profiles") or {}).get("assets") or {}).get(book) or {}
    prev = next((r for r in prof.get("rows") or [] if r.get("key") == "prev_rth"), None) \
        if prof.get("ok") else None
    day = str((prev or {}).get("date") or "").split(" ")[0] or "Prior"
    rename = {"Prior RTH high": f"{day} high", "Prior RTH low": f"{day} low",
              "Prior RTH POC": "POC", "ON high": "Overnight high", "ON low": "Overnight low",
              "RTH high so far": "Session high", "RTH low so far": "Session low"}
    # A HANDOVER RANGE FROM BEFORE THE LAST SESSION IS NOT THE HANDOVER (the first real
    # report, written on a Sunday morning for Monday's open): the ranges still held
    # Thursday night's box, so "Overnight low 28,243" printed above a last price of
    # 28,035. Friday's session had already traded through it; the night it names is
    # not the one the open inherits. A range that began before the last COMPLETE New
    # York session began is left off; one that follows it, or runs into a session
    # still trading, stays.
    rng = ((snap.get("ranges") or {}).get("assets") or {}).get(book) or {}
    boxes = {s.get("key"): s for s in rng.get("sessions") or []
             if isinstance(s, dict) and s.get("ok")}
    ny = boxes.get("ny") or {}
    done = ny.get("start_ts") if ny.get("status") == "complete" else None

    def stale(key: str) -> bool:
        began = (boxes.get(key) or {}).get("start_ts")
        return (isinstance(done, int | float) and isinstance(began, int | float)
                and began < done)

    gone = {label for key, labels in (("overnight", ("ON high", "ON low")),
                                      ("asia", ("Asia high", "Asia low")))
            if stale(key) for label in labels}
    marks: list[dict[str, Any]] = []
    for r in ladder.get("rows") or []:
        kind, label = r.get("kind"), str(r.get("label") or "")
        if kind not in ("range", "ref", "last") or label == "Prior settle" or label in gone:
            continue
        marks.append({"price": at(float(r["price"])), "label": rename.get(label, label),
                      "kind": "last" if kind == "last" else "poc" if label.endswith("POC")
                      else "range"})
    if prev:
        for k, label in (("vah", "Value high"), ("val", "Value low")):
            v = prev.get(k)
            if isinstance(v, int | float) and not isinstance(v, bool):
                marks.append({"price": at(float(v)), "label": label, "kind": "value"})
    marks.sort(key=lambda mk: mk["price"])
    return {"dp": dp, "marks": marks} if marks else None


# --------------------------------------------------------------------------
# What can move prices (brief_version 4, 2026-11-19).
# --------------------------------------------------------------------------
#
# THE REPORT AS A BRIEFING (owner: "format the market report to look like a professional
# market report that would be given to a ceo ... list what things can impact prices going
# into a session, eg news, macro events, headlines, earnings, geopolitics, vix, economic
# calender events on the day or earlier in the week that have an impact and then a brief
# summary on why each thing has an impact and kepe it concise and easily digestable", then
# "do what you recommend best"). The page is a bottom line, then one list of what can move
# prices, each item with its impact, what it does to the book and one line on why, then
# the call and its levels as before. The model picks the items and writes the why; what
# each item IS (the release and its figures, the headline, the yields, the VIX) is the
# collector's, printed from the facts, so a figure on the list is never the model's.
#
# Most items are rows the report already has: a `catalysts` id (a release, the Fed, an
# auction, a heavyweight's results, this week's earlier prints) or a `headlines` id. The
# rest are the three below, built here: rates and the dollar, the VIX, and positioning.
# THE VIX IS WEATHER (the owner's rule, and bias.BOARD_FAMILY since the evening of
# 2026-11-19): its row is always on the list, and what it does is said as the ranges it
# makes, never as a side. No dealer gamma (the owner, 2026-11-15: "i dont think we need to
# mention gex"), here as everywhere in the report.

#: How far an item can move the book this session, as the page prints it.
IMPACTS = ("high", "medium", "low")
#: What an item does to the book: helps it up, presses it down, could go either way, says
#: nothing for a side, or already traded. "regime" is the VIX's alone, and the server's.
EFFECTS = ("supportive", "pressure", "two-way", "neutral", "priced")
#: The VIX's band (scanscore.regime's rule) → the word for its ranges and the line on why.
VIX_REGIME: dict[str, tuple[str, str]] = {
    "grind": ("Small ranges", "Low volatility: small ranges, so a breakout needs proof."),
    "normal": ("Normal ranges", "Normal volatility: the day's ranges as usual."),
    "elevated": ("Wider ranges", "Elevated: moves extend, then whip back. Size down."),
    "stressed": ("Wide, fast ranges", "Stressed: wide, fast swings. Cut size or sit out."),
}


def _vix_band(last: float, shape: str | None) -> str:
    """The VIX's band as scanscore.regime draws it. Pure, bar the lazy import (scanscore
    reaches this module through marketctx)."""
    from . import scanscore

    if shape == "backwardation" or last >= scanscore.VIX_STRESSED:
        return "stressed"
    if last < scanscore.VIX_GRIND:
        return "grind"
    return "normal" if last < scanscore.VIX_NORMAL else "elevated"


def context_movers(snap: dict[str, Any], books: list[str], drivers: dict[str, Any],
                   now: datetime) -> list[dict[str, Any]]:
    """The items on the report's list that are not a calendar row or a headline: rates and
    the dollar, the VIX, and positioning, each with what it is in the collector's words
    (`what`). The VIX's carries its `regime` word and a `why` of the server's own, for a
    report whose model wrote none. Pure."""
    quotes = snap.get("quotes") or []
    out: list[dict[str, Any]] = []

    ten, dxy = _q(quotes, "US10Y"), _q(quotes, "DXY")
    parts: list[str] = []
    # Crude is priced in dollars and does not read the 10-year (bias.py): its row is the dollar.
    if ten and ten.get("last") is not None and "CL" not in books:
        t = f"10Y {ten['last']:.3f}%"
        if ten.get("chg") is not None:
            t += f" ({ten['chg'] * 100:+.1f}bp)"
        if stamp := _not_current(ten, now):
            t += f", {stamp}"
        parts.append(t)
    if dxy and dxy.get("last") is not None:
        t = f"Dollar {dxy['last']:.2f}"
        if dxy.get("pct") is not None:
            t += f" ({dxy['pct']:+.2f}%)"
        parts.append(t)
    if parts:
        out.append({"id": "rates", "what": " · ".join(parts)})

    vix = _q(quotes, "VIX")
    if vix and vix.get("last") is not None:
        vt = snap.get("volterm") or {}
        shape = str(vt.get("shape") or "") or None
        t = f"VIX {vix['last']:.1f}"
        if vix.get("pct") is not None:
            t += f" ({vix['pct']:+.1f}%)"
        if vt.get("ratio") is not None:
            t += f" · curve {vt['ratio']:.2f}"
            if shape and shape != "unknown":
                t += f", {shape}"
        word, why = VIX_REGIME[_vix_band(float(vix["last"]), shape)]
        out.append({"id": "vix", "what": t, "regime": word, "why": why})

    cot = [(b, c) for b in books for c in ((drivers.get(b) or {}).get("context") or [])
           if isinstance(c, dict) and str(c.get("label") or "").startswith("COT ·")
           and c.get("value") not in (None, "", "—")]
    if cot:
        spec = str(cot[0][1]["label"]).removeprefix("COT · ")
        out.append({"id": "positioning",
                    "what": f"{spec}: " + " · ".join(f"{b} {c['value']}" for b, c in cot)})
    return out


# HOW EACH ITEM FEEDS THE BIAS (owner, 2026-11-19: "you didnt do what i said in regards to
# explaining how each thing impacts the market or contributes to the bias", then "do what
# you recommend"). The list said what each item does to the market and nothing tied it to
# the bias drawn above it. Each item now names the factor of the engine's bias it is
# counted in, with that factor's share of the score and its tag as the table prints them,
# or why the bias does not count it. The engine's arithmetic, not the model's: an index
# book counts US inflation prints alone (drivers._prints), crude its inventories and US
# growth prints, a print votes until its day's close, and the stocks tape reads prices,
# not the calendar.
_NOT_COUNTED: dict[str, tuple[str, str]] = {
    "print": ("Read, not counted", "only US inflation prints vote"),
    "print_cl": ("Read, not counted", "crude counts its inventories and US growth prints"),
    "foreign": ("Not counted", "the bias reads US prints"),
    "earlier": ("In the price", "it voted on its day"),
    "fed": ("Not counted", "it reaches the bias through yields (Macro)"),
    "earnings": ("Not counted", "already in the index's price"),
    "holiday": ("Not counted", "it changes what the other rows mean"),
    "vix": ("Not in the bias", "weather: how far moves run, never a side"),
    "positioning": ("Not in the bias", "context: what a break would find, never a side"),
    "tape": ("Not counted", "the tape reads prices; this reaches it through SPY's and QQQ's moves"),
    "session": ("Not weighed", "its factor has no weight in this session"),
}


def bias_links(facts: dict[str, Any]) -> dict[str, dict[str, Any]]:
    """For every item the list can hold, by id: the factor of the engine's bias it is
    counted in, as the report's table prints it ({key, name, weight, tag, lean}), or why
    it is not counted ({key: None, name, note}). The futures report reads its book's table
    (`facts.factors`), the Stocks report the tape's (`facts.market_factors`). Pure."""
    shared = "market_factors" in facts
    books = list(facts.get("books") or [])
    rows = (facts.get("market_factors") or []) if shared else (
        ((facts.get("factors") or {}).get(books[0]) or []) if books else [])
    fam = {r["key"]: r for r in rows if isinstance(r, dict) and r.get("key")}
    crude = not shared and bool(books) and books[0] == "CL"

    def no(why: str) -> dict[str, Any]:
        name, note = _NOT_COUNTED[why]
        return {"key": None, "name": name, "note": note}

    def counted(key: str, note: str | None = None) -> dict[str, Any]:
        r = fam.get(key)
        if r is None:
            return no("session")
        return {"key": key, "name": r.get("name"), "weight": r.get("weight"),
                "tag": r.get("tag"), "lean": r.get("lean"), **({"note": note} if note else {})}

    out: dict[str, dict[str, Any]] = {}
    for c in facts.get("catalysts") or []:
        if not isinstance(c, dict) or not c.get("id"):
            continue
        kind, themes = c.get("kind"), set(c.get("themes") or [])
        if kind == "earnings":
            link = no("earnings")
        elif kind == "holiday":
            link = no("holiday")
        elif shared:
            link = no("tape")
        elif kind in ("fed", "auction"):
            link = no("earlier") if c.get("earlier") else no("fed")
        elif c.get("earlier"):
            link = no("earlier")
        elif c.get("country") not in ("United States", "US", None):
            link = no("foreign")
        elif crude:
            energy = bool(_ENERGY_EVENT.search(str(c.get("title") or "")))
            link = counted("catalysts") if energy or "growth" in themes else no("print_cl")
        else:
            link = counted("catalysts") if "inflation" in themes else no("print")
        out[str(c["id"])] = link
    for h in facts.get("headlines") or []:
        if isinstance(h, dict) and h.get("id"):
            out[str(h["id"])] = counted("event", "lowers the ceiling on the call, never a side")
    for m in facts.get("context_movers") or []:
        mid = str(m.get("id"))
        out[mid] = (counted("rates") if mid == "rates" else no("vix") if mid == "vix"
                    else no("positioning"))
    return out


def _link_words(link: dict[str, Any]) -> str:
    """A link as the model reads it: "Macro, 30% of the bias, Not live yet". Pure."""
    if link.get("key") is None:
        return f"{link.get('name')}: {link.get('note')}"
    weight = f", {link['weight']}% of the bias" if link.get("weight") is not None else ""
    note = f" ({link['note']})" if link.get("note") else ""
    return f"{link.get('name')}{weight}, {link.get('tag')}{note}"


def movers_menu(facts: dict[str, Any]) -> dict[str, Any]:
    """What the model may put on the list, as the digest hands it over: the calendar's and
    the wire's ids are already there; these are the rest, by id, with what each is, and
    how the engine's bias counts every one of them (`bias_links`), which the page prints
    beside the item. Pure."""
    # The VIX's band word goes with it: the page prints it as the item's effect, and the
    # first briefing's why said "normal ranges" beside a printed "Wider ranges".
    links = facts.get("bias_links") or bias_links(facts)
    return {"other_movers": [{"id": m["id"], "what": m["what"],
                              **({"ranges": m["regime"]} if m.get("regime") else {})}
                             for m in facts.get("context_movers") or []],
            "feeds_the_bias": {k: _link_words(v) for k, v in links.items()}}


def report_view(digest: dict[str, Any], facts: dict[str, Any]) -> dict[str, Any]:
    """The digest as the REPORT's model reads it: no dealer gamma anywhere (its block,
    its card, its walls on the ladder, its row on the board, the board's line on how
    to treat the score) and no moving average (the ladder's two EMA lines and its
    daily-regime sentence), the key levels in the ladder's place, and the rows the
    page will print beside the call. What it cannot see it cannot write. Hermes reads
    the digest whole (tools.py); this is only for the report. Pure."""
    out = dict(digest)
    out.pop("gamma_levels", None)
    tables = dict(out.get("brief_tables") or {})
    ladders = tables.pop("ladders", None) or []
    tables.pop("gamma", None)
    out["brief_tables"] = tables
    out["key_levels"] = facts.get("levels") or {}
    # How much of the day's range is used and what yesterday was: the ladder's two
    # range cards. Its `regime` (the 200-day line) and `ema200_10m` stay behind.
    cards = {lad.get("book"): {k: lad.get(k) for k in ("fuel", "yesterday") if lad.get(k)}
             for lad in ladders if isinstance(lad, dict)}
    if any(cards.values()):
        out["range_so_far"] = cards
    board: dict[str, Any] = {}
    for b, d in (out.get("engine_driver_board") or {}).items():
        if isinstance(d, dict):
            d = {k: v for k, v in d.items() if k not in ("treatment", "regime")}
            d["votes"] = [v for v in d.get("votes") or []
                          if not (isinstance(v, dict) and v.get("label") == "Dealer gamma")]
        board[b] = d
    if board:
        out["engine_driver_board"] = board
    out["factors_on_the_page"] = {
        b: [{k: f.get(k) for k in ("key", "name", "weight", "tag")} for f in rows]
        for b, rows in (facts.get("factors") or {}).items()}
    out.update(movers_menu(facts))
    return out


def build_facts(snap: dict[str, Any], session: str = "ny", asset: str = "all") -> dict[str, Any]:
    """Every table on the brief, computed from the snapshot. No I/O."""
    books = books_for(asset)
    now = _now_et(snap)
    ladders = [lad for b in books if (lad := _ladder(snap, b, session, now))]
    by_book = {lad["book"]: lad for lad in ladders}
    drivers = _drivers(snap, books, session, now)
    facts = {
        "books": books,
        "as_of": f"{now:%a %d %b %Y}, {now:%H:%M} ET",
        "partial": _partial(snap, books),
        "snapshot": _snapshot(snap, books, now),
        "ladders": ladders,
        "gamma": [card for b in books if (card := _gamma_card(snap, b, by_book.get(b)))],
        # Will New York trend or range (daytype.py): the record's counts for a day
        # like today, per book. The call reads them; it does not re-derive them.
        "session_type": _session_type(snap, books),
        "catalysts": _catalysts(snap, books, now),
        "rotation": _rotation(snap, books),
        "headlines": _headlines(snap, session, now),
        # The driver board's read per book (drivers.py), weighed for the session
        # this note is written for: the ceiling the call's conviction is capped at.
        "drivers": drivers,
        # What is driving each book's bias, a row a factor (`factors_of`), and the
        # levels its call is traded against (`key_levels`): the report's two tables.
        "factors": {b: factors_of(b, drivers[b]) for b in books if b in drivers},
        "levels": {b: lv for b in books if (lv := key_levels(snap, b, by_book.get(b)))},
        # THE CATALYSTS THE BIAS WAS BLIND TO (events.py, 2026-10-30): the names
        # moving each equity index, with their prints and headlines, and the
        # high-impact events since the close. The call's `catalyst` cites them.
        "heavyweights": {b: events_mod.heavyweights(snap, b, now)
                         for b in books if b in INDEX_BOOKS},
        "event_risk": events_mod.event_risk(snap, now),
        # The list's items that are not a calendar row or a headline (2026-11-19).
        "context_movers": context_movers(snap, books, drivers, now),
    }
    # How the engine's bias counts each item the list can hold (2026-11-19).
    facts["bias_links"] = bias_links(facts)
    return facts


def _drivers(snap: dict[str, Any], books: list[str], session: str = "ny",
             now: datetime | None = None) -> dict[str, Any]:
    """Each book's read, cut to what the brief caps by.

    WEIGHED FOR THE SESSION THE NOTE IS FOR (2026-11-05). The live board weighs for
    the clock; a London note pressed in Asia hours is read with London's weights,
    or the ceiling on its call would be Asia's."""
    drivers = snap.get("drivers") if isinstance(snap.get("drivers"), dict) else {}
    boards = (drivers or {}).get("books") or {}
    key = None
    if now is not None:
        key = bias_mod.session_key(session, bool(session_progress(session, now)["underway"]))
    out: dict[str, Any] = {}
    for b in books:
        bd = boards.get(b)
        if not isinstance(bd, dict) or not bd.get("votes"):
            continue
        if key and bd.get("session_key") != key:
            bd = {**bd, **bias_mod.board_read(
                b, bd["votes"], key, regime=bd.get("regime"),
                ny_open=bool((drivers or {}).get("ny_open")),
                events=int(bd.get("event_count") or 0))}
        out[b] = _board_view(bd)
    return out


def _board_view(bd: dict[str, Any]) -> dict[str, Any]:
    """A board as the brief stores it: a futures book's (drivers.py) or the stocks
    tape's (marketctx), cut to what the report caps by and prints. Pure."""
    return {
        "bias": bd.get("bias"), "score": bd.get("score"), "coverage": bd.get("coverage"),
        # What the score is over (bias.read): the page draws it on the bias scale
        # beside the call, and a score with no basis is taken for the older rule.
        "basis": bd.get("basis"),
        "grade": bd.get("grade"), "max_conviction": bd.get("max_conviction"),
        "agree": bd.get("agree"), "against": bd.get("against"),
        "neutral": bd.get("neutral"), "live": bd.get("live"),
        "cannot_vote": bd.get("cannot_vote"), "total": bd.get("total"),
        "weights_for": bd.get("weight_label"),
        "families": [{k: f.get(k) for k in ("key", "label", "weight", "score")}
                     for f in bd.get("families") or [] if isinstance(f, dict)],
        "macro_lean": bd.get("macro_lean"), "structure_lean": bd.get("structure_lean"),
        "conflict": bool(bd.get("conflict")),
        "treatment": bd.get("treatment"),
        # A read in no family (dealer gamma, event risk) is not a side, and says so.
        "votes": [{"label": v.get("label"), "family": v.get("family"),
                   "value": v.get("value"),
                   "vote": v.get("vote") if v.get("family") else "not a side",
                   "can_vote_now": v.get("live", True), "note": v.get("note")}
                  for v in bd.get("votes") or [] if isinstance(v, dict)],
        "context": [{"label": c.get("label"), "value": c.get("value"), "note": c.get("note")}
                    for c in bd.get("context") or [] if isinstance(c, dict)],
    }


# --------------------------------------------------------------------------
# The Stocks desk's report: SPY, QQQ and IWM for New York (2026-11-16).
# --------------------------------------------------------------------------
#
# ONE BIAS FOR THE THREE. The stocks desk already weighs the market as one tape
# (marketctx.votes, bias.tape_read): SPY and QQQ against their levels, the VIX and its
# curve, credit, yields and the dollar, the sectors, equal weight, index volume and the
# leaders. That is the read the Stocks tab's Tape card prints, so it is the read this
# report's single drivers table prints, once, above three calls. It is taken from the
# scanner's payload as it stood when Generate was pressed, with event risk added as the
# futures boards carry it (a row that is no side and takes a notch off the ceiling).
#
# EACH FUND ITS OWN LEVELS. A call is traded against the fund's own previous-day and
# pre-market high and low, the levels the owner's strategy draws, not a futures ladder.
#
# THE REST IS THE INDEXES REPORT'S. The calendar, the headlines, the rotation, the
# snapshot and every macro block are built as an Indexes report's are (NQ and ES are
# the same two indexes in futures prices), and the futures-only parts (ladders, gamma,
# the session-type record) are left out of what the page prints.

#: The tape's families as the report names them (FACTOR_NAMES has the futures' names).
TAPE_FACTOR_NAMES: dict[str, tuple[str, str | None]] = {
    "levels": ("Index levels", "SPY and QQQ against their own"),
    "risk": ("Risk appetite", "credit beyond the S&P's own move"),
    "rates": ("Macro", "rates & dollar"),
    "participation": ("Participation", "sectors, equal weight, volume & leaders"),
}
#: Every key a comment on the tape's table may carry (the futures' are FACTOR_KEYS).
TAPE_FACTOR_KEYS: tuple[str, ...] = (*TAPE_FACTOR_NAMES, "event")
#: A fund's levels on the report's ruler, in the strategy's own names.
_FUND_LEVELS: tuple[tuple[str, str], ...] = (
    ("pdh", "PDH"), ("pdl", "PDL"), ("pmh", "PMH"), ("pml", "PML"), ("pdc", "Prev close"))


def _num_or_none(v: Any) -> float | None:
    return float(v) if isinstance(v, int | float) and not isinstance(v, bool) else None


def _fund_rows_by_sym(scan: dict[str, Any] | None) -> dict[str, dict[str, Any]]:
    return {r["sym"]: r for r in (scan or {}).get("rows") or []
            if isinstance(r, dict) and r.get("ok") and r.get("sym") in ETF_BOOKS}


def fund_levels(row: dict[str, Any] | None) -> dict[str, Any] | None:
    """One fund's levels for the report's ruler, low to high: PDH, PDL, PMH, PML, the
    previous close and the last price, at cents. Pure."""
    if not isinstance(row, dict):
        return None
    lv = row.get("levels") if isinstance(row.get("levels"), dict) else {}
    marks = [{"price": round(v, 2), "label": label, "kind": "range"}
             for k, label in _FUND_LEVELS if (v := _num_or_none(lv.get(k))) is not None]
    last = _num_or_none(row.get("last"))
    if last is not None:
        marks.append({"price": round(last, 2), "label": "Last", "kind": "last"})
    marks.sort(key=lambda mk: mk["price"])
    return {"dp": 2, "marks": marks} if len(marks) >= 2 else None


def fund_rows(scan: dict[str, Any] | None) -> list[dict[str, Any]]:
    """SPY, QQQ and IWM against their own levels, for the model: the move, the move
    outside the session, the levels and where the last price sits. No trend read (the
    report argues from none). Pure."""
    by = _fund_rows_by_sym(scan)
    out: list[dict[str, Any]] = []
    for sym in ETF_BOOKS:
        r = by.get(sym)
        if r is None:
            continue
        lv = r.get("levels") if isinstance(r.get("levels"), dict) else {}
        last = _num_or_none(r.get("last"))
        pdh, pdl = _num_or_none(lv.get("pdh")), _num_or_none(lv.get("pdl"))
        pmh, pml = _num_or_none(lv.get("pmh")), _num_or_none(lv.get("pml"))
        where = None
        if last is not None and pdh is not None and pdl is not None:
            where = ("above the previous day's high" if last > pdh else
                     "below the previous day's low" if last < pdl else
                     "inside the previous day's range")
        pm = None
        if last is not None and pmh is not None and pml is not None:
            pm = ("above the pre-market high" if last > pmh else
                  "below the pre-market low" if last < pml else "inside the pre-market range")
        out.append({
            "sym": sym, "last": _num_or_none(r.get("last")),
            "chg_pct": _num_or_none(r.get("chg_pct")), "ext_pct": _num_or_none(r.get("ext_pct")),
            "levels": {k: _num_or_none(lv.get(k)) for k in ("pdh", "pdl", "pmh", "pml", "pdc")},
            "against_previous_day": where, "against_pre_market": pm,
        })
    return out


def market_board(scan: dict[str, Any] | None, snap: dict[str, Any],
                 now: datetime) -> dict[str, Any] | None:
    """The stocks tape count as a report board: the Scanner's own read (marketctx,
    weighed by bias.tape_read for the scanner's session) with event risk added as a
    row that is no side and lowers the ceiling a notch, as on a futures board. Pure,
    bar the lazy import (drivers imports this module)."""
    c = (((scan or {}).get("regime") or {}).get("conviction")
         if isinstance((scan or {}).get("regime"), dict) else None)
    if not isinstance(c, dict) or not c.get("votes"):
        return None
    from . import drivers as drivers_mod

    events = events_mod.event_risk(snap, now)
    ev = drivers_mod._event_risk(events)
    cap = c.get("max_conviction")
    if ev.get("damper") and isinstance(cap, int):
        cap = max(1, cap - 1)
    board = {**c, "max_conviction": cap, "votes": [*c["votes"], {**ev, "family": None}],
             "event_count": len(events) if ev.get("damper") else 0}
    return _board_view(board)


def _etf_facts(snap: dict[str, Any], scan: dict[str, Any] | None,
               base: dict[str, Any]) -> dict[str, Any]:
    """The Stocks report's tables: an Indexes report's (`base`) with the three funds as
    its books, the tape as its one board and each fund's own levels. Pure."""
    now = _now_et(snap)
    market = market_board(scan, snap, now)
    by = _fund_rows_by_sym(scan)
    partial = list(base.get("partial") or [])
    if market is None:
        partial.append("The Stocks tape count has not been read yet: the market bias is missing.")
    if len(by) < len(ETF_BOOKS):
        missing = ", ".join(s for s in ETF_BOOKS if s not in by)
        partial.append(f"The scanner has no row for {missing} yet: no levels for it.")
    out = {
        **base,
        "books": list(ETF_BOOKS),
        "partial": partial,
        "ladders": [], "gamma": [], "session_type": {},
        "drivers": {}, "factors": {},
        "levels": {s: lv for s in ETF_BOOKS if (lv := fund_levels(by.get(s)))},
        # The one bias the three calls are read against, and its table (`factors_of`).
        "market": market,
        "market_factors": factors_of("TAPE", market) if market else [],
        "funds": fund_rows(scan),
    }
    # The list's links read the tape's table, not the Indexes report's.
    out["bias_links"] = bias_links(out)
    return out


def etf_view(digest: dict[str, Any], facts: dict[str, Any]) -> dict[str, Any]:
    """An Indexes digest as the Stocks report's model reads it: `report_view`'s cuts,
    then the futures boards and range cards out and the funds, the tape and the funds'
    levels in. Pure."""
    out = report_view(digest, {**facts, "levels": {}, "factors": {}})
    for k in ("engine_driver_board", "range_so_far", "the_book_this_note_is_about",
              "other_books_context_only"):
        out.pop(k, None)
    out["writing_about"] = ASSETS[ETF_ASSET]["instruments"]
    out["the_funds_this_note_is_about"] = list(ETF_BOOKS)
    out["index_funds"] = facts.get("funds") or []
    board = dict(facts.get("market") or {})
    board.pop("treatment", None)
    out["stocks_tape_count"] = board or None
    out["key_levels"] = facts.get("levels") or {}
    out["factors_on_the_page"] = {"market": [
        {k: f.get(k) for k in ("key", "name", "weight", "tag")}
        for f in facts.get("market_factors") or []]}
    out["futures_blocks"] = (
        "session_ranges, volume_profile, session_type_lean and the NQ and ES rows are the "
        "Nasdaq 100's and the S&P 500's futures: the same indexes as QQQ and SPY in futures "
        "prices, read as context for the open. No fund level comes from them, and the "
        "Russell 2000 has no future here.")
    return out


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


# --------------------------------------------------------------------------
# Earnings in the digest — the latest prints and the next scheduled.
# --------------------------------------------------------------------------

#: How many of the most recent prints the digest carries, newest day first and
#: biggest first within it.
EARNINGS_REPORTED = 8
#: How many of the reports still to come it carries, soonest first.
EARNINGS_AHEAD = 8

#: Where in the ET day a report lands, by Nasdaq's timing field: before the
#: open prints around 08:00, after the close in the first minutes past 16:00,
#: and an unspecified one is placed at noon so it sorts inside its own day.
_EARNINGS_HOUR = {"pre": (8, 0), "after": (16, 5)}


def _earnings_moment(e: dict[str, Any]) -> datetime | None:
    """When a report row prints, in ET; None for a row with no readable date. Pure.
    The table is events.py's (PRINT_HOUR), read from there so the heavyweights
    block and this agree on when a print landed."""
    return events_mod.print_moment(e)


def _earnings_row(e: dict[str, Any], printed: bool) -> dict[str, Any]:
    row: dict[str, Any] = {
        "symbol": e.get("symbol"), "name": e.get("name"), "date": e.get("date"),
        "when": e.get("when"), "eps_forecast": e.get("eps_forecast"),
    }
    if printed:
        row["eps_actual"] = e.get("eps_actual")
        row["surprise_pct"] = e.get("surprise_pct")
    return row


def digest_earnings(
    rows: list[dict[str, Any]], now: datetime
) -> dict[str, list[dict[str, Any]]]:
    """The reports a session note needs: what printed most recently, and what
    is still to come. Pure.

    NOT THE FIRST FOURTEEN ROWS (owner, 2026-10-30: "yesterday we had all
    these GOOG ... MSFT", after Hermes said they were not in the table). The
    collector keeps two days back and four ahead, sorted oldest first, so a
    plain `[:14]` was always the oldest day's rows: Visa and Coca-Cola from
    Monday, while Alphabet's Wednesday miss — the thing actually moving NQ —
    sat at row 25 and never reached the model. The slice has to be anchored
    on now, from both sides.

    `reported` is the latest prints, newest day first and biggest first
    within it, so "what did Alphabet do" is answered from the top. `ahead` is
    every report still to come, soonest first and biggest first within a day.

    `awaiting_figures` IS WHAT HAS REPORTED BY THE CLOCK AND HAS NO EPS ON THE
    FEED YET (2026-11-05). The feed lags the print by hours, and these used to
    sit in `ahead`: the 19:29 ET note on 4 November said "ARM and QCOM report
    after the close", three hours after they had. They are the overnight's gap
    risk, so they stay in view, under a name that says what they are. A row that
    has passed its moment by more than the print window is a no-show on the
    feed, not a scheduled risk, and is dropped. Each list is capped — eight of
    each is the old budget of fourteen, spent where the reader is looking.
    """
    today = now.astimezone(ET).date().isoformat()
    kept = [e for e in rows if isinstance(e, dict) and _earnings_moment(e) is not None]

    def when_and_size(e: dict[str, Any]) -> tuple[str, float]:
        return str(e.get("date")), float(e.get("market_cap") or 0)

    printed = sorted((e for e in kept if e.get("eps_actual")), key=when_and_size, reverse=True)
    unprinted = [e for e in kept if not e.get("eps_actual")]
    waiting = sorted((e for e in unprinted if events_mod._just_reported(e, now)),
                     key=when_and_size, reverse=True)
    due = sorted(
        (e for e in unprinted
         if str(e.get("date")) >= today and not events_mod._just_reported(e, now)),
        key=lambda e: (when_and_size(e)[0], -when_and_size(e)[1]),
    )
    return {
        "reported": [_earnings_row(e, printed=True) for e in printed[:EARNINGS_REPORTED]],
        "awaiting_figures": [_earnings_row(e, printed=False) for e in waiting[:EARNINGS_AHEAD]],
        "ahead": [_earnings_row(e, printed=False) for e in due[:EARNINGS_AHEAD]],
    }


def _positioning(snap: dict[str, Any], want_equity: bool, wanted: Any) -> dict[str, Any]:
    """COT per book and, for the equity books, the Cboe put/call ratios. Pure.

    THE BOARD HAD THEM AND THE PROMPT FORBADE THEM (audit, 2026-11-05). COT and
    put/call joined the driver board as context rows on 2026-10-22, while the
    prompt went on listing both under what the data does not have and telling
    the model never to mention them. So the positioning layer of every note
    was the gamma map alone."""
    raw = snap.get("cot")
    books = (raw.get("books") or {}) if isinstance(raw, dict) else {}
    fields = ("spec", "as_of", "net", "chg", "pct_oi", "pctile", "word", "read")
    cot = {
        b: {k: c.get(k) for k in fields}
        for b, c in books.items() if isinstance(c, dict) and c.get("ok") and wanted(b)
    }
    pc = snap.get("putcall") if isinstance(snap.get("putcall"), dict) else None
    out: dict[str, Any] = {"cot_weekly": cot}
    if want_equity and pc and pc.get("ratios"):
        out["cboe_put_call"] = {k: pc.get(k) for k in ("date", "ratios", "avg20", "pctile", "read")}
    return out


def curve_date(rates: dict[str, Any], today: date) -> dict[str, str]:
    """Which day Treasury's curve is for, and whose move its changes are. Pure.

    THE CURVE WENT TO THE MODEL WITH NO DATE ON IT. Treasury publishes one curve a
    day, after the close, and none on a bond holiday. On the evening of Wed 11 Nov
    2026 (Veterans Day) the latest was Tuesday's: 4.98%, +10bp on Monday. The brief
    wrote "10Y closed 4.98%, +10.0bp at the 14:59 ET cash close" as the day's driver
    and leaned bearish on it, with the 10-year's own row two lines away saying +1.5bp.
    So the block says which day it is, that its changes are that day's, and when the
    cash market was shut."""
    try:
        d = datetime.strptime(str(rates.get("as_of") or ""), "%m/%d/%Y").date()
    except ValueError:
        return {}
    out = {"curve_as_of": f"{d:%a} {d.day} {d:%b}"}
    if d < today:
        out["curve_basis"] = (
            f"Treasury's daily curve for {d:%a} {d.day} {d:%b}, the latest published: every "
            "chg_bp below is THAT day's change from the day before it, not today's. Today's "
            "10-year is the US10Y row of brief_tables.snapshot.")
    shut = holidays_mod.bond_closed(today)
    if shut:
        out["cash_treasuries_today"] = (
            f"shut all day ({shut}): no curve for today and no live yield, so rates cannot "
            "make a new call today")
    else:
        # Shut on a day since the curve: that is why the curve is older than yesterday's.
        gap = [x for x in (d + timedelta(days=i) for i in range(1, max(0, (today - d).days)))
               if holidays_mod.bond_closed(x)]
        if gap:
            x = gap[-1]
            out["cash_treasuries_last_shut"] = (
                f"{x:%a} {x.day} {x:%b} ({holidays_mod.bond_closed(x)}): there is no curve for it")
    return out


def _cash_moves_basis(now: datetime) -> str:
    """Which session a cash figure's change belongs to, in words. Pure.

    The constituents and the sector SPDRs read the regular session, so at 03:00
    ET "AAPL +5.31%" is yesterday's move — and a note with nothing to say so
    wrote it as today's."""
    et = now.astimezone(ET)
    day = et.date()
    if is_trading_day(day) and NY_OPEN <= et.time() < close_time(day):
        return "today's regular session, so far"
    last = events_mod.last_close(et)
    return (f"the regular session of {last:%a %d %b} — the cash market has not traded since, "
            "so these are not overnight moves")


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
        "SI_silver_futures": brief("SILVER"),
        "CL_crude_futures": brief("WTI"),
        "YM_dow": brief("YM"),
        "RTY_russell": brief("RTY"),
    }
    # The quotes that ARE the subject: one book's, or the two indexes' with their ETFs.
    # `all` holds nothing back.
    focus_keys = () if asset == "all" else tuple(
        k for b in facts["books"] for k in BOOK_KEYS.get(b, ()))
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
        return key in facts["books"]

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
            # The entry levels the strategy uses, from the same bars (2026-10-30).
            "vwap": v.get("vwap"),
            "opening_range": v.get("opening_range"),
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
                    # The same as a percentage, which is how a note says it: "93%
                    # of its range" was flagged as a figure the data did not carry.
                    "percent_of_range": round(r["pos"] * 100) if r.get("pos") is not None else None,
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
        # How this note's layers weigh, as the prompt states it, kept with the
        # note so a stored brief says what it was asked to do.
        "session_weighting": [f"{layer}: {role}"
                              for layer, role, _ in session_layers(session, _prog)],
        # WHOSE MOVE A CASH FIGURE IS. See `_cash_moves_basis`.
        "cash_moves_basis": _cash_moves_basis(now),
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
        # The days a market this note leans on is shut or shuts early (holidays.py).
        "market_holidays": [
            {"date": h["date"], "what": h["label"], "holiday": h["name"], "means": h["note"]}
            for h in holidays_mod.notices(now.date() - timedelta(days=1),
                                          now.date() + timedelta(days=3))
        ],
        "rates": {
            **curve_date(rates, now.date()),
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
        # What a move will find: who is crowded, and how hedged the market is.
        # Slow, and never a direction on its own.
        "positioning": _positioning(snap, any(b in facts["books"] for b in INDEX_BOOKS), wanted),
        # What each session traded, and where price sits inside each range.
        # The most useful block on the page for a handover read: "London has
        # already taken out the Asia high" is one number here and an inference
        # from four elsewhere.
        "session_ranges": ranges,
        # WILL NEW YORK TREND OR RANGE (daytype.py): per book, the conditions that
        # hold today with their counts over the record, and the call. Counts,
        # never probabilities — narrate them as counts.
        "session_type_lean": {k: v for k, v in facts.get("session_type", {}).items()
                              if k in ("how_to_read", "record") or wanted(k)},
        # THE ENGINE'S OWN SCORE, per book: every driver a vote with its
        # threshold and reason, weighed by family for this session, the grade,
        # the macro-against-structure conflict and the treatment line. The
        # call's conviction may not exceed `max_conviction`, nor 3 against
        # `bias`, so narrate it, never re-derive it.
        "engine_driver_board": {k: v for k, v in facts.get("drivers", {}).items()
                                if wanted(k)},
        "expiry": snap.get("expiry") or {},
        # The latest prints and the next scheduled, anchored on now — not the
        # first rows of a week-long list (digest_earnings says what went wrong).
        "earnings": digest_earnings(snap.get("earnings") or [], now),
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
                        "index_pp": m["contribution"],
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
        # WHAT THE INDEX IS BEING MOVED BY, NAME BY NAME: the biggest weights
        # and the biggest movers, each with its contribution, its print if it
        # just reported, and the headline that explains it. Cite by id.
        "heavyweights": facts.get("heavyweights") or {},
        # The high-impact geopolitics, policy and energy wire since the last
        # close, one row per story, with the channels it reaches. Cite by id.
        "event_risk": facts.get("event_risk") or [],
        # THE TABLES THE PAGE PRINTS, exactly as it prints them. Levels named in
        # prose should come from these ladders so the words and the table agree.
        "brief_tables": {k: facts[k] for k in ("snapshot", "ladders", "gamma", "rotation")},
        "data_gaps": facts["partial"],
    }


# A FIGURE AS THE PAGE PRINTS IT (2026-11-15). The digest carried what the sources
# gave: a 200 EMA of 28206.3935 beside a ladder that prints 28,206, a contribution of
# -0.3763 percentage points. A model copies what it is shown, and a real note printed
# both as they stood. The guard cannot help: it is exact on the value, so the rounded
# figure a person would write is the one it flags. So the digest is tidied before it is
# shown, and what is stored on the report is what was shown.
_TWO_PLACES = re.compile(r"(?:_pct|_pp)$|^(?:chg|pct|weight|week_change|month_change)$")


def _tidy(v: Any, key: str = "") -> Any:
    """Floats at a printable precision: two places for a percentage, a share or any
    figure of 10 and over, four for the rest (an exchange rate, a ratio). Pure."""
    if isinstance(v, bool):
        return v
    if isinstance(v, float):
        if not math.isfinite(v):
            return v
        return round(v, 2 if (_TWO_PLACES.search(key) or abs(v) >= 10) else 4)
    if isinstance(v, dict):
        return {k: _tidy(x, str(k)) for k, x in v.items()}
    if isinstance(v, list | tuple):
        return [_tidy(x, key) for x in v]
    return v


def shown(digest: dict[str, Any]) -> dict[str, Any]:
    """The digest as the model reads it: a copy, every figure tidied, and each
    ladder's levels at the ladder's own decimals, which is how the page prints them
    (NQ in whole points). The facts the page draws from are not touched. Pure."""
    out: dict[str, Any] = _tidy(digest)
    src = (digest.get("brief_tables") or {}).get("ladders") or []
    dst = (out.get("brief_tables") or {}).get("ladders") or []
    for a, b in zip(src, dst, strict=False):
        dp = a.get("dp") if isinstance(a, dict) else None
        if not isinstance(dp, int) or not isinstance(b, dict):
            continue

        def at(x: Any, dp: int = dp) -> Any:
            if isinstance(x, bool) or not isinstance(x, int | float):
                return x
            return round(x, dp) if dp else round(x)

        b["last"] = at(a.get("last"))
        for ra, rb in zip(a.get("rows") or [], b.get("rows") or [], strict=False):
            rb["price"] = at(ra.get("price"))
        for ca, cb in zip(a.get("confluence") or [], b.get("confluence") or [], strict=False):
            if isinstance(ca, dict) and isinstance(cb, dict):
                cb["lo"], cb["hi"] = at(ca.get("lo")), at(ca.get("hi"))
        if isinstance(a.get("regime"), dict) and isinstance(b.get("regime"), dict):
            b["regime"]["ema200"] = at(a["regime"].get("ema200"))
        if isinstance(a.get("ema200_10m"), dict) and isinstance(b.get("ema200_10m"), dict):
            b["ema200_10m"]["value"] = at(a["ema200_10m"].get("value"))
    return out


# --------------------------------------------------------------------------
# The schema. Forces a direction and a conviction rather than adjectives.
# --------------------------------------------------------------------------

BIASES = ("bullish", "leaning bullish", "neutral", "leaning bearish", "bearish")

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
#: A book as a model names it when it does not use the key.
_BOOK_WORDS = {"GOLD": "GC", "SILVER": "SIL", "SI": "SIL", "CRUDE": "CL", "CRUDE OIL": "CL",
               "OIL": "CL", "WTI": "CL"}
_BIAS = {"type": "string", "enum": list(BIASES)}

# THE BRIEF, SHORT (owner, 2026-11-15: "can we work on really making the reports
# concise and impactful?", then "i want it to be really hard hitting impactful stuff
# that actually matters and makes a difference to the markets"). The shape before
# this asked for thirteen parts: a call and then a full read per book, a note on every
# table, a rotation paragraph, a cross-asset paragraph. A real Indexes note came back
# at 1,850 words with the same four facts in nine places, beside tables that already
# printed them. What is left is what only a judgement supplies: the day in two
# sentences, a call per book with its reasons, its plan and what kills it, what is on
# the clock, and what could break it. Words only, as before: every figure lives in
# the facts, and an `id` is how a note finds its row (`sanitize_brief`).
#
# THE LIMITS ARE COUNTED IN WORDS AND CHECKED. They are printed into the prompt from
# this table and held on the way back (`too_long`), because "be brief" is an
# instruction a model agrees with and then writes four paragraphs.
#
# A note stored before this has the older shape and no `brief_version`; the page
# still draws it (Brief.tsx).
# 3 IS THE MARKET REPORT (later the same day: "need to rework the report, so it looks
# like a nice concise readable report", "make it look like professional market
# report"). The three reasons of 2 became one comment a factor, for every factor the
# bias weighs (`factors_of`), so nothing that moves the score is left off the page;
# and dealer gamma left the report. A 2 keeps its layout on the page.
# 4 IS THE BRIEFING (2026-11-19, "What can move prices" above `context_movers`): a bottom
# line, the list (`movers`), and a call a book with the engine's own table and levels
# under it. The model writes no comment a factor (the list says each thing once, with its
# why, and the table prints the engine's reads), no plan and no invalidation (off the
# page since 2026-11-17), and no calendar notes, risks or headline notes (the list is
# all three). `sanitize_brief` still reads every older field, so a 3 drawn again or an
# answer in the old shape loses nothing.
BRIEF_VERSION = 4

# "mover" WAS 16 (the evening of 2026-11-19), and the owner's first word on the result was
# "you didnt do what i said in regards to explaining how each thing impacts the market":
# sixteen words held a figure and a verdict, never the channel. Two sentences now.
LIMITS: dict[str, int] = {
    "thesis": 40, "factor": 20, "plan": 28, "wrong_if": 16,
    "today": 14, "risks": 14, "headlines": 12, "mover": 40,
}
#: The list holds at least this many items and at most MOVERS_MAX.
MOVERS_MIN = 3
MOVERS_MAX = 10
#: A quarter over is let through: a bullet two words long of its limit is not worth
#: forty seconds of a second answer.
LIMIT_SLACK = 1.25

_MOVER = _obj({
    "id": {**_STR, "description": (
        "What can move the book: a `catalysts` id (c…), a `headlines` id (h…) or an "
        "`other_movers` id (rates, vix, positioning)."
    )},
    "impact": {"type": "string", "enum": list(IMPACTS)},
    "effect": {"type": "string", "enum": list(EFFECTS)},
    "why": {**_STR, "description": (
        f"Two sentences, {LIMITS['mover']} words at most: how it moves the market (the "
        "channel, plainly), then what a surprise, a break or an escalation does to the book."
    )},
})
SCHEMA: dict[str, Any] = _obj({
    "thesis": {**_STR, "description": (
        f"The bottom line in one or two plain sentences, {LIMITS['thesis']} words at most."
    )},
    "movers": _arr(_MOVER, MOVERS_MIN, MOVERS_MAX),
    "calls": _arr(_obj({
        "book": _BOOK,
        "open_bias": _BIAS,
        "conviction": {"type": "integer", "minimum": 1, "maximum": 5},
    }), 1, 3),
})

# THE STOCKS REPORT'S SHAPE (2026-11-16): one bias for the three funds, read once at the
# top, and a call per fund.
_ETF = {"type": "string", "enum": list(ETF_BOOKS)}
_CALL = SCHEMA["properties"]["calls"]["items"]["properties"]
SCHEMA_ETFS: dict[str, Any] = _obj({
    "thesis": SCHEMA["properties"]["thesis"],
    "movers": SCHEMA["properties"]["movers"],
    "calls": _arr(_obj({
        "book": _ETF, "open_bias": _BIAS, "conviction": _CALL["conviction"],
    }), 3, 3),
})


def schema_for(asset: str) -> dict[str, Any]:
    """The strict schema a subject is answered in. Pure."""
    return SCHEMA_ETFS if resolve_asset(asset) == ETF_ASSET else SCHEMA

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
story.""",
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

# Silver and crude (2026-11-15), each stated separately for the reason gold is.
TRANSMISSION_SIL = """\
SILVER TRADES AS GOLD'S HIGH-BETA SHADOW AND AS AN INDUSTRIAL METAL AT ONCE. As with
gold, much of the physical market trades in London and Asia, so a move there can be
real flow rather than drift. BUT THIS DATA CARRIES NO PHYSICAL-MARKET SERIES — no fix
prices, no regional premiums, no ETF holdings, no industrial or solar demand figures,
and no positioning in silver (the COT here covers NQ, ES and gold only). Do not name
any of them as a fact or a driver; if a headline reports one, cite that headline as
the source. What the data does carry, and what sets the level: US real yields
(`rates.real`) and the policy path, the dollar (DXY, USD/JPY), GOLD beside silver (the
gold/silver ratio says which metal is leading), COPPER (the industrial half), VXSLV,
and the session ranges. A silver thesis that never says what gold is doing is
incomplete."""

TRANSMISSION_CL = """\
CRUDE IS A GLOBAL BARREL PRICED IN DOLLARS, AND EACH SESSION CAN MOVE IT FOR ITS OWN
REASON: Asia is where the marginal demand is, London is where Brent trades and where
the Gulf and Russia headlines usually land, and New York is where the US data, the
weekly inventories (Wednesday 10:30 ET) and the products trade. BUT THIS DATA CARRIES
NO SUPPLY SERIES — no OPEC production or quota figures, no refinery runs, no Cushing
or regional stocks, no tanker rates, and no positioning in crude (the COT here covers
NQ, ES and gold only). Do not name any of them as a fact or a driver; if a headline
reports one, cite that headline as the source. What the data does carry, and what
sets the level: the dollar, Brent beside WTI, gasoline and heating oil (whether
refiners are pulling the barrel through), copper and credit as the demand read, OVX,
the weekly inventories row once it has printed, the session ranges, and the
geopolitics and energy headlines. Those headlines are SUPPLY RISK and cut either way:
say which way THIS one cuts, with its id, never that risk is simply bullish. The
10-year and the VIX are not crude drivers on their own; cite them only through the
dollar or through demand."""


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

THAT THINNESS CHANGES THE READING, structurally rather than narratively. The
SESSION'S OWN EVIDENCE decides the path here: the developing profile and the
range so far are built from the tape actually trading, they update with every
bar, and in a thin book acceptance means more, not less. Macro keeps the
direction only through what is live right now, and the weighting below says what
that is. Say explicitly when a move looks like position-driven drift rather than
a repricing.
"""


# HOW THE LAYERS WEIGH, SESSION BY SESSION (owner, 2026-11-05: "every like macro,
# positioning, structure, session etc is weighted accordingly depending on what
# session it is"). The rules were all in this prompt already, scattered across
# five paragraphs, and two of them disagreed about macro. Here they are one table:
# what each layer does in this session and which of its inputs are live, in the
# order they should move the call. Words and an order, not percentages: a note is
# a judgement, and a number here would be precision nobody has measured. The US
# stays the anchor for direction in every row (the owner's rule above); what
# changes is how much of it is live and what else may be believed.
_WEIGHTING: dict[str, list[tuple[str, str, str]]] = {
    "asia": [
        ("Session tape", "leads the path",
         "Asia's range so far, the developing profile, acceptance against the New York close. "
         "It is the only evidence still being written."),
        ("Structure", "frames it",
         "prior value and the New York range: what the tape is being judged against."),
        ("Macro", "the anchor, mostly at its close",
         "the cash 10Y, credit and the VIX are shut, so they are closing prints that frame the "
         "call and cannot make a new one. Live: USD/JPY, the dollar, oil, gold and last night's "
         "US earnings."),
        ("News", "through the channels only",
         "HIGH stories since the close first, and only where they reach a book through the "
         "channels above."),
        ("Positioning", "a reference",
         "COT and put/call are slow background, never tonight's direction."),
    ],
    "london": [
        ("Session tape", "leads the path",
         "what London does with the Asia range — taken out and held, or rejected — is the read."),
        ("Macro", "the anchor, and it is waking up",
         "rates and the dollar as Europe trades them, European data and central banks today, "
         "all ahead of the 08:30 ET US window, which remains the event."),
        ("News", "since the close",
         "HIGH stories first; a European policy decision today outranks anything overnight."),
        ("Structure", "frames it",
         "prior value and the prior session's range: the frame New York will inherit."),
        ("Positioning", "a reference",
         "COT and put/call are slow background."),
    ],
    "ny_pre": [
        ("Macro", "sets the direction",
         "the 08:30 window, what is priced for the Fed, and the earnings from last night and "
         "this morning: this is what the open is positioning for."),
        ("News", "since the close",
         "HIGH stories first: whatever changed overnight is what the open has to price."),
        ("Structure", "sets the path",
         "the overnight range against prior value is the range the open breaks or defends."),
        ("Positioning", "who is crowded",
         "COT and put/call say who is crowded and what a break will find, never a direction."),
        ("Session tape", "the handover",
         "Asia and London are context here, not the subject."),
    ],
    "ny_live": [
        ("Structure", "leads the path",
         "acceptance against prior value, the opening range, VWAP, and the levels this session "
         "has already taken or rejected."),
        ("Positioning", "who is crowded",
         "COT and put/call say who is crowded and what a break will find, never which way."),
        ("Macro", "direction, where it is live",
         "prints that have landed, and how the curve and the dollar reacted. A print the tape "
         "has faded does not anchor by reputation."),
        ("Breadth and heavyweights", "confirm or deny",
         "whether the move is the index's top weights or the whole market."),
        ("News", "what just changed",
         "HIGH stories since the close; anything mid-session outranks the morning's read."),
    ],
}


def session_layers(session: str, prog: dict[str, Any]) -> list[tuple[str, str, str]]:
    """The layers for this note, heaviest first: (layer, its role, what is live). Pure."""
    if session == "ny" or session not in _WEIGHTING:
        return _WEIGHTING["ny_live" if prog.get("underway") else "ny_pre"]
    return _WEIGHTING[session]


def _weighting(session: str, prog: dict[str, Any]) -> str:
    """The table as the prompt prints it."""
    rows = "\n".join(f"  {i}. {layer} — {role}: {what}"
                     for i, (layer, role, what) in enumerate(session_layers(session, prog), 1))
    return f"""\
HOW THE LAYERS WEIGH IN THIS NOTE, heaviest first. Where they disagree the higher \
row decides the path and the conflict lowers conviction; the list (`movers`) says \
what moves each layer.
{rows}"""


def _transmission(session: str, asset: str) -> str:
    """The session's transmission channels for the book being written about."""
    block = TRANSMISSION.get(session, TRANSMISSION["ny"])
    own = {"GC": TRANSMISSION_GC, "SIL": TRANSMISSION_SIL, "CL": TRANSMISSION_CL}.get(
        resolve_asset(asset))
    return f"{block}\n\n{own}" if own else block


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
  * `thesis` starts from where price sits NOW: which levels this session has already \
taken or rejected, and what is next from here.
  * `movers` leads with what is still to come; a print already out is there only for \
what it did, and its effect is usually `priced`.

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
  session_type_lean   will New York trend or range: the conditions that hold \
today with their counts over the record, and the call. Counts, never odds — say \
"2 trend days in 142" — and gold's New York box rarely earns a call by this rule, \
so read its night in ATRs and leave the call alone when it says No lean.
  rates            the policy path and the curve. Real yields are the carrying \
cost of a zero-coupon asset, so gold trades the front of the curve and what is \
priced into it.
  dollar_and_commodities   the unit gold is priced in, plus silver and copper — \
which say whether a metals move is monetary or industrial.

Then positioning (the weekly COT: who is crowded, what a break would find), \
volatility, the volume profile levels, the calendar ahead, expiry and the \
headlines — context, cited where it changes the read. Sector rotation and \
index constituents are equity internals: bring them in only when equities \
are moving hard enough to be a risk signal for gold in their own right, \
never as structure."""
    elif resolve_asset(asset) == "SIL":
        must_read = """\
  session_ranges   what each session traded, and where price sits inside each. \
The most important block for a handover: 0 is that session's low, 1 its high, \
above 1 means the high has been taken out.
  rates            the policy path and the curve. Real yields are the carrying \
cost of a metal that pays nothing, so silver trades the front of the curve and \
what is priced into it, as gold does.
  dollar_and_commodities   the unit silver is priced in, plus copper, which says \
whether the industrial half is with the move; and gold, in `brief_tables.snapshot` \
and the gold/silver ratio, which says whether silver is following or leading.

Then volatility (VXSLV in the snapshot), the volume profile levels, the calendar \
ahead and the headlines — context, cited where it changes the read. There is no \
session-type record and no COT for silver: say nothing about either. Sector \
rotation and index constituents are equity internals: bring them in only when \
equities are moving hard enough to be a risk signal for silver in their own \
right, never as structure."""
    elif resolve_asset(asset) == "CL":
        must_read = """\
  session_ranges   what each session traded, and where price sits inside each. \
The most important block for a handover: 0 is that session's low, 1 its high, \
above 1 means the high has been taken out.
  dollar_and_commodities   the unit the barrel is priced in, Brent beside WTI, \
and copper for demand; gasoline and heating oil are in `brief_tables.snapshot` and \
say whether refiners are pulling the barrel through.
  catalysts        the weekly inventories and anything from OPEC, with the figure \
once printed: a build is more crude in store, a draw less. Where the row carries no \
consensus, quote the week's change itself and say there is no forecast to hold it to.

Then the headlines (the Gulf, Russia, OPEC and sanctions are supply risk and cut \
either way), volatility (OVX in the snapshot), the volume profile levels, credit \
as a demand read, and the calendar ahead — context, cited where it changes the \
read. There is no session-type record and no COT for crude: say nothing about \
either. The 10-year, the VIX, sector rotation and index constituents are not \
crude's: bring equities in only when they are moving hard enough to be a demand \
signal in their own right, never as structure."""
    elif resolve_asset(asset) == ETF_ASSET:
        must_read = """\
  index_funds      SPY, QQQ and IWM against their own levels: the move, the move \
outside the session, the previous day's high and low (PDH, PDL), the pre-market high \
and low (PMH, PML), the previous close, and where the last price sits against each \
range. The most important block: every call is traded against these.
  stocks_tape_count   the one bias for the three funds, vote by vote: SPY and QQQ \
against their levels, credit, yields and the dollar, the sectors, equal weight, index \
volume and the leaders. The VIX's level, curve and day are on it as weather, no side.
  index_movers     WHICH NAMES supplied the move in the Nasdaq 100 and the S&P 500. \
Use the contribution figures, which are weight times return.
  sector_rotation  WHICH SECTORS are being bought, as excess return over SPY. \
Defensives leading is a different tape from technology leading, and small caps \
against megacaps is IWM against QQQ.

Then rates and the policy path (IWM is the most rate-sensitive of the three), \
credit, volatility, the calendar ahead, earnings and the headlines, and as context \
for the open the futures blocks (`futures_blocks` says what they are) — cited where \
they change the read."""
    else:
        must_read = """\
  session_ranges   what each session traded, and where price sits inside each. \
The most important block for a handover: 0 is that session's low, 1 its high, \
above 1 means the high has been taken out.
  session_type_lean   will New York trend or range: every condition that holds \
today (the night so far in ATRs, yesterday's shape, the gap, the VIX band) with its \
count over two years of sessions, and the call. Counts, never odds — say "2 trend \
days in 142", never a percentage — and let it shape the call's targets and size \
(a range day wants the edges faded and less room; a trend day more possible wants \
room to run), never its side.
  index_movers     WHICH NAMES supplied the move. These indices are \
cap-weighted and two or three names are usually the day, so "NQ is down" and \
"NQ is down because AMZN is off 2.5%" are different notes. Use the contribution \
figures, which are weight times return — not the raw percent changes.
  sector_rotation  WHICH SECTORS are being bought, as excess return over SPY. \
Defensives leading is a different tape from technology leading.

Then rates and the policy path, positioning (the weekly COT and the Cboe \
put/call ratios: who is crowded and how hedged the market is — what a move will \
find, never a direction on its own), volatility, the volume profile (POC is the \
magnet, VAH/VAL bound acceptance; STATE where the session opened and where \
price trades now against prior value — the classifier already decided, cite \
it), the \
dollar and commodities, the calendar ahead, earnings, expiry and the \
headlines — context, cited where it changes the read."""

    book_list = ", ".join(books_for(asset))
    return f"""You are a markets strategist writing the pre-session brief for one \
trader's desk. They trade NQ/QQQ, ES/SPY and GC/GLD futures and ETFs, and silver \
and WTI crude futures, and they trade the Asia, London and New York sessions.

THIS BRIEF IS ABOUT {a["instruments"].upper()}.
  {a["drivers"]}

THIS BRIEF IS FOR THE {s["label"].upper()} SESSION, {prog.get("hours")}.
  What leads it: {s["leads"]}
  Handover: {s["handover"]}
  How it usually behaves: {s["character"]}

{_transmission(session, asset)}

US MACRO AND THE FED ARE THE ANCHOR IN EVERY SESSION, INCLUDING THIS ONE. These \
are US-priced books: NQ and ES are claims on US earnings discounted at US real \
rates, gold and silver are priced against the same curve and the same dollar, and \
crude is priced in that dollar and trades American demand and American stocks. The \
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

WHAT THIS DATA DOES NOT HAVE: strike-level open interest, \
ETF flows or holdings, European or Japanese government bond yields, gold fixes \
or physical premiums. Never mention them. A figure that is not in the data \
does not go in the brief, however standard it would be in one — AND NEITHER \
DOES A MARKET, FLOW OR DATA SERIES. Every driver you name must be a block or row in the data, or a \
headline you cite by id. "Gilts sold off", "Indian demand", "the fix was \
strong" are claims about data you were not given; leave them out.

PRICES HAVE AGES. `price_feed` says how old the board is: the CME futures \
quotes run about ten minutes behind the exchange, and any row listed under \
`not_current` stopped printing hours ago (a cash yield after its close, an \
index whose exchange is shut). Quote those as the last or closing print \
("10Y closed 4.12%"), never as where the market is now, and do not build a \
"right now" read on them.

READ EVERY BLOCK OF THE DATA BEFORE YOU CONCLUDE, AND WRITE ONLY WHAT MOVED THE \
CALL. Notes written before this instruction cited the \
session ranges and silently ignored sector rotation in three runs out of five — \
that was not a judgement that it did not matter, it was the block not being read. \
Reading is not optional; mentioning is. Each of these answers a different \
question, and each is weighed before the call is made:

{must_read}

A block that did not move the call stays out of the brief. What is not \
acceptable is not looking.

THE NEWS IS DATA, AND IT IS RANKED. `headlines` carries one row per story, HIGH \
first, then what has landed since the last cash close, then the session's own \
regions; `also` counts the other tellings of it. Read every HIGH row before you \
conclude. One that reaches a book — through rates, the dollar, oil, chips, tariffs, \
war or fiscal policy — goes on the list (`movers`) by its id and, if it is the day's \
story, in the bottom line. Coverage is not importance, and a story with no channel to \
the book is not a driver however loud it is. `event_risk` is the same wire's \
geopolitics, policy and energy desks, for the books' ceilings.

EARNINGS HAVE A CLOCK. `earnings.awaiting_figures` have already reported by the \
calendar and the feed has no EPS for them yet: say they have reported and the \
figures are not in, never that they report later. `earnings.ahead` is still to \
come. On a `heavyweights` row, `reported.reaction_in` false means the move shown \
is the session BEFORE the report.

CASH MOVES HAVE A DATE. `cash_moves_basis` says which session the constituents, \
the heavyweights' moves and the sector rotation belong to. Before the open they \
are the last session's: quote them as that ("AAPL rose 5.31% in Wednesday's \
session"), never as today's. `index_pp` is that name's contribution to the index \
in PERCENTAGE POINTS (weight times return), not index points: write "0.42 \
percentage points of the index".

DEALER GAMMA IS NOT IN THIS REPORT. It is not a side, the bias does not weigh it \
and the page does not print it. Never mention gamma, the flip, a call or put wall, \
dealer hedging or pinning, and never use one of those levels: every level you \
name is in `key_levels`.

THE CURVE HAS A DATE. `rates.curve` is Treasury's daily curve for \
`rates.curve_as_of`, published after that day's close, and each `chg_bp` in it is \
THAT day's change. When `rates.curve_basis` is present the curve is not today's: \
never write its change as today's move or as "the close". The 10-year's move \
today is the US10Y row of `brief_tables.snapshot`, and where that row says it \
last printed at its close, rates cannot make a new call. `market_holidays` lists \
the days a market this note leans on is shut or shuts early: the cash Treasury \
market on Columbus Day and Veterans Day while stocks trade, London, Tokyo. When \
one is today or was the last session, say what it does to the read (no rates \
read, a thin London, no Japan prints) and do not lean on a figure it left stale.

THE ENGINE HAS ALREADY WEIGHED THE DRIVERS. `engine_driver_board` is, per \
book, every macro and structure read as a vote with its threshold and its \
reason, grouped into `families`, each with its weight for this session and its \
own score (event risk is listed with them and is "not a side": it does not vote, \
it lowers the ceiling). `score` runs from -100 to +100 over the whole of this \
session's weight: a family that cannot vote at this hour counts as no lean, so a \
score on little of the weight sits near zero by itself and is never to be scaled \
again; `coverage` is how much of the weight can vote. A vote with \
`can_vote_now` false has no market or no input behind it at this hour: it neither \
agrees nor disagrees, so do not count it either way. There is a `conflict` flag \
when the macro families and the structure families disagree. \
Read it first. THE PAGE DRAWS THIS SCORE ON A SCALE BESIDE YOUR CALL, so never \
print the score, the coverage or a count of votes: name the one family or vote \
that carries the call, with its figure. The call's `conviction` may not exceed \
the book's `max_conviction`, and may not exceed 3 when the call runs against the \
board's `bias` — the server enforces both, so rank inside that ceiling. Where you \
disagree with a vote, say which and why, with the figure; never re-derive the \
score. No trend line or moving average votes: do not argue a call from one.

THE PAGE IS A BRIEFING FOR SOMEONE WITH A MINUTE. It prints, in this order: your \
bottom line (`thesis`); WHAT CAN MOVE PRICES, the items you pick (`movers`), grouped by \
kind (the day's economic data, this week's earlier prints, the Fed and the Treasury, \
earnings, geopolitics and headlines, rates and the dollar, volatility and \
positioning), each printed with what it is from the data (the release with its \
actual, consensus and prior, the results, the headline, the yields and the dollar, \
the VIX) and your impact, effect and why beside it; then each book's call, with the \
engine's score on a scale, the engine's table of the factors the bias weighs \
(`factors_on_the_page`, with its own tags and reads) and a ruler of the key levels \
(`key_levels`: the prior session's high and low, its value area and point of control, \
the handover range and the last price). You write none of the tables. Never restate \
what a row already prints, and take every level you name from `key_levels`, as it is \
printed there.

{_live_framing(session, prog)}
{_weighting(session, prog)}

HOW THE BIAS IS FORMED, AND IN WHAT ORDER. Macro sets the DIRECTION: the data \
that printed, what is priced for the Fed, the policy path, the dollar and the \
curve are why the market wants to go somewhere, and the call is anchored there \
whenever any of it is live today. Structure sets the PATH: where the session \
opened against prior value, the profile's shape and second node, the session \
ranges decide whether the macro lean is being ACCEPTED or \
REJECTED by the tape, and they supply every level the call names. Read them \
together, never one without the other — a bearish print with price accepted \
above prior value is a CONFLICT, and a conflict lowers \
conviction rather than picking a side. On a day with no print and no speaker, \
say so and let structure lead: macro that is not moving today does not anchor \
a call by reputation.

THIS BRIEF IS SHORT, AND SHORT IS THE JOB. The reader has the tables beside your \
words and reads your part in under a minute before trading. What they need from \
you is the judgement no table makes: what actually moves this market in this \
session, which way, where, and what proves it wrong. A long brief is one that has \
not decided.

  * LEAD WITH WHAT MOVES PRICE. Rank everything you read by how far it can move \
the book in THIS session: a print with a consensus to miss, what is priced for the \
Fed, a heavyweight's results, a story the wire ranks HIGH, a level whose break \
changes how the day trades. Write the top of that ranking and nothing below it. A \
true fact that would not change a trade is left out.
  * EVERY SENTENCE IS A CAUSE AND WHAT IT DOES TO THE BOOK, with the figure. Never \
a figure alone, never an effect with no figure behind it.
  * SAY EACH FACT ONCE, where it does the most work. One item on the list, one why; \
two items are never one story told twice; the bottom line names the decider and the \
list explains the rest.
  * NO MOVING AVERAGES. The bias does not weigh a trend line, so the report does \
not argue from one: never write "EMA", "SMA", "200-day" or "trend line".
  * NO PREAMBLE, NO HEDGE, NO NARRATION. Not "it is worth noting", "could \
potentially", "remains to be seen", "investors will watch", "amid", "as markets \
digest", "overall". Not a sentence about what the data is or what you are about to \
say. Plain words, active verbs, short sentences; a bullet may be a fragment.
  * FIGURES AS THE PAGE PRINTS THEM: copied from the data, never more than two \
decimals (an exchange rate as it is given), a level exactly as \
`key_levels` has it, no arithmetic of your own.
  * AN ID IS NEVER PROSE. `h3` or `c2` goes in an `id` field and nowhere else; in \
a sentence, name the story or the release.
  * THE WORD LIMITS BELOW ARE HARD, AND SO IS "ONCE". An answer over a limit, or \
with two items that say one thing, is sent back.

Field by field:
  thesis     THE BOTTOM LINE, {LIMITS["thesis"]} words at most, one or two sentences: \
the call and the one thing that decides it, with its level or figure. It is read \
first, by someone with a minute. With nothing live, say so in one sentence and name \
the range. Never the last price for its own sake: the page prints it.
  movers     WHAT CAN MOVE PRICES, {MOVERS_MIN} to {MOVERS_MAX} items, the most \
important first. Rank everything you read by how far it can move {book_list} in THIS \
session and list the top of it:
    - every high-impact release and Fed event on the session's day, printed or due \
(`catalysts` rows with `high` true), and a speaker or an auction that can move the \
curve;
    - this week's earlier prints (`catalysts` rows with `earlier` true) that still \
explain where yields, the dollar or the book sit;
    - a heavyweight's results, reported or due;
    - the stories the wire ranks HIGH that reach the book through a channel (rates, \
the dollar, oil, chips, tariffs, war, fiscal policy): one item a story;
    - `other_movers`: `rates` (the 10-year and the dollar), `vix` (the page always \
lists it and prints its band's word, `ranges`, as its effect: say what that does to \
stops and size, in agreement with it, never a side) and `positioning` (who is \
crowded and what a break would find).
    Nothing that lands after this session closes, and no routine release to fill \
the list: three items that matter beat ten that do not. Each item:
      id       the row's id, exactly as given (c3, h7, rates).
      impact   high, medium or low: how far it can move the book in this session.
      effect   what it does to {book_list}: supportive (pushes it up), pressure \
(pushes it down), two-way (could go either way: a release still to print, a story \
still developing), neutral (no side for the book: printed in line, or nothing in it \
for this market), priced (it printed earlier and the market has traded it).
      why      TWO SENTENCES, {LIMITS["mover"]} words at most, for a reader who is not a \
trader. First HOW it moves the market: the channel, plainly ("A low claims print says \
hiring is still tight, which keeps the Fed from cutting and lifts yields, and that \
weighs on tech valuations"). Then WHAT A SURPRISE, A BREAK OR AN ESCALATION DOES to \
the book, or why it matters in this session ("A high print does the reverse; it is the \
only release before the open, so it decides whether the gap holds"). Do not open with \
the item's name or time: its row prints them. A figure that explains the channel may \
be quoted, copied from the data.
    The page prints beside each item how the engine's bias counts it \
(`feeds_the_bias`, by id: the factor, its share and its tag, or why it is not \
counted). Agree with it: an item the bias does not count is never said to drive the \
bias, and where the factor cannot vote yet (a cash market shut, a print still to come), \
say when it will.
  calls      Exactly one per book in scope.
    open_bias, conviction   The side and its strength, 1-5. THE CALL IS THE CALL: \
the bottom line and the list argue the side named here and no other. If the words \
say a book leans short, `open_bias` is leaning bearish; if the call is neutral, \
nothing in the brief calls it a lean.

Be concrete and unhedged in the direction call. Do not use disclaimers, do not \
mention that you are an AI, and do not recommend position sizes or give \
financial advice — describe conditions and levels, which is what a desk brief \
does.""" + _etf_rules(asset)


def _etf_rules(asset: str) -> str:
    """What changes for the Stocks report: read last, so it overrides the per-book
    rules above where the two differ. Empty for every other subject. Pure."""
    if resolve_asset(asset) != ETF_ASSET:
        return ""
    return """

THIS REPORT IS THE STOCKS DESK'S: SPY, QQQ AND IWM FOR NEW YORK, AND FOUR THINGS \
ABOVE ARE DIFFERENT FOR IT. Where this section and the text above disagree, this \
section is right.
  1. ONE BIAS FOR ALL THREE. There is no `engine_driver_board`: the bias is \
`stocks_tape_count`, the stocks desk's tape count, and the page draws it once, on a \
scale, above the three calls. Each call's `conviction` may not exceed its \
`max_conviction`, and may not exceed 3 when the call runs against its `bias`; the \
server enforces both. The three funds may still differ: QQQ under its PML while IWM \
holds its range is a call each, and the difference is the read.
  2. THE LIST IS FOR US STOCKS. An item's `effect` is what it does to SPY, QQQ and IWM \
together. Where it hits one harder than the others (rates on IWM, chips on QQQ), the \
`why` says so. The page prints the tape's table once, `factors_on_the_page.market`, \
above the calls, on the engine's own reads: you write no comment for it.
  3. EACH FUND'S LEVELS ARE ITS OWN. A level in the bottom line is that fund's PDH, \
PDL, PMH, PML or previous close from `key_levels` and `index_funds`, exactly as \
printed. Never a futures level, a value area or a point of control: those are NQ's \
and ES's (`futures_blocks`).
  4. NEW YORK ONLY. The report is for the regular session, 09:30 to 16:00 ET."""


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


# AN ID WRITTEN INTO A SENTENCE: "h1 Iran-Europe attack story can gap crude" was a
# risk in the first short brief (2026-11-15), as "catalyst_ids: w8, w10." had been in
# the first long one. The ids are the sanitiser's to join on, not the reader's to see.
# Lower case only: "H1" is the first half of a year.
_ID_IN_PROSE = re.compile(r"\(?\b[hcwe]\d{1,3}\b\)?[:,]?\s*")


#: The trend in the report's words (owner, 2026-11-15, of the EMAs: "i dont think we
#: need to include about the ema's"). The prompt asks for it; a model that has just
#: read "200-day EMA" in its data writes it back.
_PLAIN_TREND: tuple[tuple[re.Pattern[str], str], ...] = (
    (re.compile(r"\b10[- ]?(?:minute|min|m) 200[- ]?EMA\b", re.I), "10-minute trend line"),
    (re.compile(r"\b200[- ]?day (?:EMA|SMA)\b", re.I), "200-day average"),
    (re.compile(r"\b(\d{1,3})[- ]?day (?:EMA|SMA)\b", re.I), r"\1-day average"),
    (re.compile(r"\b200[- ]?EMA\b", re.I), "trend line"),
    (re.compile(r"\b(?:EMA|SMA)s\b"), "averages"),
    (re.compile(r"\b(?:EMA|SMA)\b"), "average"),
)


# WHAT A MODEL LEAVES ON A SENTENCE (the first real market report, 2026-11-15): the
# summary came back as "... Iran-Bahrain strikes cap conviction. (39 words){" (its own
# count against the limit, and a brace from the JSON around it), and every risk began
# "> ". A list mark in front (a quote mark, a dash, a bullet, "1.") and a count or a
# brace behind are not the sentence. A leading "-1.65%" or "10Y" is: the mark must be
# followed by a space. The second real report's risks began ": " (an id and a colon,
# the id taken out), so a stray colon, semicolon or comma in front goes the same way,
# and a sentence that lost its front starts with a capital.
_LIST_MARK = re.compile(r"^\s*(?:[>*•–—:;,-]+|\d{1,2}[.)])\s+")
_TAIL_NOISE = re.compile(r"(?:\s*\(\s*\d{1,3}\s+words?\s*\))?[\s{}]*$", re.I)


def _prose(v: Any) -> str:
    """A sentence the model wrote, with any row id it carried taken out, and neither a
    list mark in front of it nor its own word count behind. Pure."""
    raw = _text(v)
    t = _ID_IN_PROSE.sub("", raw)
    for pat, plain in _PLAIN_TREND:
        t = pat.sub(plain, t)
    t = _TAIL_NOISE.sub("", _LIST_MARK.sub("", t))
    t = re.sub(r"\s{2,}", " ", t).strip()
    if t and not raw.lstrip().startswith(t[:1]):
        t = t[:1].upper() + t[1:]
    return t


# THE TAG IS THE ENGINE'S AND IS PRINTED BESIDE THE COMMENT (the second real report,
# 2026-11-15): told not to write it, the model opened every comment with it all the
# same: "Bullish; NQ above Friday VAH", "Not live yet; 10Y closed 5.15%". On the page
# that is the row's tag twice, and where the model's word differs from the engine's it
# is a second opinion nobody asked for. The opening word goes; the comment stays.
_TAG_LEAD = re.compile(
    r"^(?:bullish|bearish|mixed|neutral|nothing yet|not live yet|quiet)\s*[;:,.—–-]+\s+", re.I)


def _no_tag(line: str) -> str:
    rest = _TAG_LEAD.sub("", line)
    return rest[:1].upper() + rest[1:] if rest and rest != line else line


def _texts(v: Any, cap: int) -> list[str]:
    if not isinstance(v, list):
        return []
    return [t for x in v if (t := _prose(x))][:cap]


def _factor_lines(v: Any, allowed: set[str]) -> list[dict[str, str]]:
    """The model's comments, each on a factor the page has a row for, one a row."""
    out: list[dict[str, str]] = []
    seen: set[str] = set()
    for x in _dicts(v):
        k, line = x.get("key"), _no_tag(_prose(x.get("line")))
        if isinstance(k, str) and k in allowed and k not in seen and line:
            seen.add(k)
            out.append({"key": k, "line": line})
    return out[:8]


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
            out.append({field: k, text_field: _prose(text) if text_field == "note" else text})
    return out[:cap]


def sanitize_brief(obj: Any, facts: dict[str, Any]) -> dict[str, Any] | None:
    """The model's brief, checked against the facts it is allowed to point at.

    THE SCHEMA IS ONLY ENFORCED BY THE PROVIDER IN STRICT MODE, and the weaker
    mode below enforces nothing — so the shape is checked here rather than
    assumed. And more than the shape: a note on a catalyst id that does not
    exist, or a call on a book the brief is not about, is dropped here, so the
    panel can join on ids without guarding every one. The counts are held here
    too (three reasons, three items on the clock, three risks, three headlines);
    the words are held by `too_long`, which asks again.

    None when what is left is not a brief: no thesis, or a book in scope without
    a call.
    """
    if not isinstance(obj, dict):
        return None
    books: list[str] = list(facts.get("books") or BOOKS)
    # THE STOCKS REPORT (`_etf_facts`): one board, the tape, for every fund, and its
    # factors commented once at the top rather than under each call.
    shared = "market_factors" in facts
    market = facts.get("market") if shared else None

    calls: dict[str, dict[str, Any]] = {}
    for c in _dicts(obj.get("calls")):
        book = c.get("book")
        book = book.strip().upper() if isinstance(book, str) else book
        bias = norm_bias(c.get("open_bias"))
        if not isinstance(book, str) or book not in books or book in calls or bias is None:
            continue
        try:
            conviction = int(c.get("conviction") or 0)
        except (TypeError, ValueError):
            conviction = 1
        # THE BOARD'S CEILING (module docstring): the engine's max for the
        # book, and 3 against its lean. A bias is "against" when it points the
        # other way from the count's side; neutral is never against.
        board = (market or {}) if shared else (facts.get("drivers") or {}).get(book) or {}
        cap = board.get("max_conviction")
        if isinstance(cap, int):
            conviction = min(conviction, cap)
            lean = board.get("bias")
            way = "long" if "bullish" in bias else "short" if "bearish" in bias else None
            if lean in ("long", "short") and way is not None and way != lean:
                conviction = min(conviction, 3)
        calls[book] = {
            "book": book,
            "open_bias": bias,
            "conviction": min(5, max(1, conviction)),
            # A comment for a factor the page has no row for is dropped: the row is
            # the engine's, and a comment with no row would have nowhere to sit. A fund
            # on the Stocks report has no table of its own: the market's is at the top.
            "factors": [] if shared else _factor_lines(c.get("factors"), {
                r["key"] for r in (facts.get("factors") or {}).get(book) or []
                if isinstance(r, dict) and r.get("key")} or set(FACTOR_KEYS)),
            "plan": _prose(c.get("plan")),
            "wrong_if": _prose(c.get("wrong_if")),
        }

    thesis = _prose(obj.get("thesis"))
    if not thesis or any(b not in calls for b in books):
        return None
    rows = {c["id"]: c for c in facts.get("catalysts") or []
            if isinstance(c, dict) and c.get("id")}

    headline_ids = {h["id"] for h in facts.get("headlines") or []}
    headlines: list[dict[str, Any]] = []
    for h in _dicts(obj.get("headlines")):
        hid = h.get("id")
        if not isinstance(hid, str) or hid not in headline_ids:
            continue
        if any(x["id"] == hid for x in headlines):
            continue
        # "Gold" is what a model writes for GC more often than not, and "silver",
        # "crude", "oil" or "WTI" for the two newer books.
        named = {_BOOK_WORDS.get(w, w) for w in (str(x).strip().upper()
                                                 for x in h.get("books") or [])
                 } if isinstance(h.get("books"), list) else set()
        headlines.append({
            "id": hid, "books": [b for b in (*BOOKS, *ETF_BOOKS) if b in named],
            "note": _prose(h.get("note")),
        })

    out_top: dict[str, Any] = {}
    if shared:
        out_top["factors"] = _factor_lines(obj.get("factors"), {
            r["key"] for r in facts.get("market_factors") or []
            if isinstance(r, dict) and r.get("key")} or set(TAPE_FACTOR_KEYS))
    return {
        "thesis": thesis,
        **out_top,
        # What can move prices (brief_version 4): each item a row the facts have.
        "movers": _movers(obj.get("movers"), facts),
        "calls": [calls[b] for b in books],
        # What is on the clock, and only ids that are rows of the calendar the
        # page prints: the note is joined onto its row there, so it does not say
        # the row's time and name again (`_drop_clock`).
        "today": [
            {"id": t["id"], "note": _drop_clock(t["note"], rows.get(t["id"]) or {})}
            for t in _picks(obj.get("today"), "id", set(rows), "note", 3)
            # A row listed to say it does not matter is not on the clock: "lands after
            # this session closes; not in play" was the third item of a real report.
            if not _NOT_IN_PLAY.search(t["note"])
        ],
        "risks": _texts(obj.get("risks"), 3),
        "headlines": headlines[:3],
    }


#: The words a model writes for an impact and an effect, mapped onto the schema's: the
#: loose mode enforces nothing, and "Bearish" is the right answer misspelt.
_IMPACT_WORDS = {"high": "high", "medium": "medium", "med": "medium", "moderate": "medium",
                 "mid": "medium", "low": "low"}
_EFFECT_WORDS = {
    "supportive": "supportive", "support": "supportive", "supports": "supportive",
    "bullish": "supportive", "positive": "supportive", "tailwind": "supportive",
    "pressure": "pressure", "pressures": "pressure", "bearish": "pressure",
    "negative": "pressure", "headwind": "pressure",
    "two-way": "two-way", "two way": "two-way", "twoway": "two-way", "mixed": "two-way",
    "either way": "two-way", "either": "two-way", "binary": "two-way",
    "neutral": "neutral", "none": "neutral", "no side": "neutral",
    "priced": "priced", "priced in": "priced", "already priced": "priced",
}


def _movers(v: Any, facts: dict[str, Any]) -> list[dict[str, str]]:
    """The list, each item a row the facts have (a calendar row, a headline, or one of
    `context_movers`), first mention wins, MOVERS_MAX at most. An item with no why is
    dropped. THE VIX IS ALWAYS ON IT and is never a side: its effect is "regime" whatever
    was written, and where the model left it off, or wrote nothing on it, its line is the
    server's (`context_movers`). Pure."""
    cats = {c["id"]: c for c in facts.get("catalysts") or [] if isinstance(c, dict) and c.get("id")}
    heads = {h["id"] for h in facts.get("headlines") or [] if isinstance(h, dict) and h.get("id")}
    ctx = {m["id"]: m for m in facts.get("context_movers") or [] if isinstance(m, dict)}
    out: list[dict[str, str]] = []
    seen: set[str] = set()
    for x in _dicts(v):
        mid = x.get("id")
        if not isinstance(mid, str):
            continue
        mid = mid.strip()
        if mid.lower() in ctx:
            mid = mid.lower()
        if mid in seen or not (mid in cats or mid in heads or mid in ctx):
            continue
        why = _prose(x.get("why"))
        if mid in cats:
            why = _drop_clock(why, cats[mid])
        if not why and mid != "vix":
            continue
        seen.add(mid)
        out.append({
            "id": mid,
            "impact": _IMPACT_WORDS.get(str(x.get("impact") or "").strip().lower(), "medium"),
            "effect": "regime" if mid == "vix" else _EFFECT_WORDS.get(
                str(x.get("effect") or "").strip().lower(), "two-way"),
            "why": why,
        })
    out = out[:MOVERS_MAX]
    vix = ctx.get("vix")
    if vix is not None:
        have = next((m for m in out if m["id"] == "vix"), None)
        if have is None:
            out.append({"id": "vix", "impact": "medium", "effect": "regime",
                        "why": str(vix.get("why") or "")})
        elif not have["why"]:
            have["why"] = str(vix.get("why") or "")
    return out


def _on_the_session(c: dict[str, Any], session: str) -> bool:
    """Whether a calendar row is a high-impact release or Fed event of the session the
    report is for: not this week's earlier prints, and a release only when it lands in
    that session (New York's pre-market counts as New York's). Pure."""
    if not c.get("high") or c.get("earlier") or c.get("kind") not in ("data", "fed"):
        return False
    if c.get("kind") == "fed":
        return session == "ny"
    lands = c.get("lands_in_session")
    return lands in ("premkt", "ny") if session == "ny" else lands == session


def list_faults(b: dict[str, Any], facts: dict[str, Any], session: str) -> list[str]:
    """What sends a briefing back besides `faults`: a list of fewer than MOVERS_MIN items,
    or one that leaves out a high-impact release or Fed event of the session. Empty for a
    brief in the older shape (no list asked for). Pure."""
    movers = b.get("movers")
    if not isinstance(movers, list):
        return []
    out: list[str] = []
    real = [m for m in movers if m.get("id") != "vix"]
    # As many as the facts can give: a quiet Sunday with two rows is not short of a third.
    there = (len(facts.get("catalysts") or []) + len(facts.get("headlines") or [])
             + sum(1 for m in facts.get("context_movers") or [] if m.get("id") != "vix"))
    need = min(MOVERS_MIN, there)
    if len(real) < need:
        out.append(f"the list has {len(real)} items besides the VIX (at least {need})")
    have = {m.get("id") for m in movers}
    for c in facts.get("catalysts") or []:
        if isinstance(c, dict) and c.get("id") not in have and _on_the_session(c, session):
            out.append(f"the list leaves out {c['id']} ({c.get('title')}), "
                       "high impact this session")
    return out


#: The line for a high-impact row the model left off the list twice (`fill_missed`).
_MISSED_WHY = {
    False: "Due this session: a surprise either way reprices rates and the open.",
    True: "Printed this session: its surprise is what the market is trading now.",
}


def fill_missed(b: dict[str, Any], facts: dict[str, Any], session: str) -> None:
    """Put a high-impact row of the session the list still leaves out after the re-ask
    onto it, with the server's line: the reader is told about every one of them, model or
    no model. In place. Pure."""
    movers = b.get("movers")
    if not isinstance(movers, list):
        return
    have = {m.get("id") for m in movers}
    for c in facts.get("catalysts") or []:
        if isinstance(c, dict) and c.get("id") not in have and _on_the_session(c, session):
            done = bool(c.get("released"))
            movers.append({"id": c["id"], "impact": "high",
                           "effect": "priced" if done else "two-way",
                           "why": _MISSED_WHY[done], "server": True})


# THE ROW SAYS WHEN AND WHAT; THE NOTE SAYS WHAT IT DOES (2026-11-15). Two real short
# briefs in a row opened each note with its row: "Barr speaks Mon 05:00 ET pre-market;
# hawkish tone would press gold before the bell", printed under "Mon 05:00 ET · FOMC
# Member Barr Speaks", the second after the prompt said not to. So the opening clause
# goes when it holds nothing but the row's own words and the clock's. One word of
# anything else ("Priced for a hold at 14:00; a cut lifts gold") and it stays.
_CLOCK_WORDS = frozenset({
    "mon", "tue", "wed", "thu", "fri", "sat", "sun", "monday", "tuesday", "wednesday",
    "thursday", "friday", "saturday", "sunday", "today", "tomorrow", "tonight", "et",
    "premkt", "pre-market", "premarket", "session", "bell", "open", "close", "before",
    "after", "during", "ahead", "due", "lands", "prints", "speaks", "reports", "ny",
    "london", "asia", "morning", "afternoon", "evening", "am", "pm",
})
_FIRST_CLAUSE = re.compile(r"^(.{1,90}?)(?:;\s|:\s|\s[—–-]\s)(.+)$", re.DOTALL)
_NOT_IN_PLAY = re.compile(
    r"\bnot in play\b|\bafter (?:this|the) session (?:closes|ends|has closed)\b", re.I)


def _drop_clock(note: str, row: dict[str, Any]) -> str:
    """A note on a calendar row without the row's time and name in front of it. Pure."""
    m = _FIRST_CLAUSE.match(note)
    if not m:
        return note
    own = _content_words(row.get("title")) | _content_words(row.get("when")) | _CLOCK_WORDS
    if _content_words(m.group(1)) - own:
        return note
    rest = m.group(2).strip()
    return rest[:1].upper() + rest[1:] if rest else note


_WORD = re.compile(r"\S+")


def word_count(text: Any) -> int:
    return len(_WORD.findall(text)) if isinstance(text, str) else 0


def brief_words(b: dict[str, Any]) -> int:
    """How many words the model wrote in a sanitised brief. Pure."""
    return sum(word_count(x) for x in brief_prose(b))


def too_long(b: dict[str, Any]) -> list[str]:
    """The parts of a brief over their word limit, as the re-ask names them. Pure.

    Past LIMIT_SLACK only. Nothing is cut here: half a sentence is worse than a long
    one, so an over-long part is sent back to its author once and then printed as it
    came."""
    over: list[str] = []

    def check(what: str, text: Any, key: str) -> None:
        n, cap = word_count(text), LIMITS[key]
        if n > cap * LIMIT_SLACK:
            over.append(f"{what} is {n} words (limit {cap})")

    check("thesis", b.get("thesis"), "thesis")
    # The Stocks report's comments, written once for the market (`sanitize_brief`).
    for f in b.get("factors") or []:
        check(f"market {f.get('key')}", f.get("line"), "factor")
    for c in b.get("calls") or []:
        book = c.get("book")
        for f in c.get("factors") or []:
            check(f"{book} {f.get('key')}", f.get("line"), "factor")
        check(f"{book} plan", c.get("plan"), "plan")
        check(f"{book} wrong_if", c.get("wrong_if"), "wrong_if")
    for x in b.get("today") or []:
        check(f"today {x.get('id')}", x.get("note"), "today")
    for i, r in enumerate(b.get("risks") or [], 1):
        check(f"risk {i}", r, "risks")
    for x in b.get("headlines") or []:
        check(f"headline {x.get('id')}", x.get("note"), "headlines")
    for x in b.get("movers") or []:
        check(f"item {x.get('id')}", x.get("why"), "mover")
    return over


# SAY IT ONCE, CHECKED (2026-11-15). The first real short brief was inside every word
# limit and still gave NQ and ES one sentence each, the same sentence: "No live macro
# print, Fed speaker, or prior RTH profile exists for Monday's open." Two index books
# share their macro on most days, so this is the commonest way a short note is longer
# than what it says. A reason is a repeat when three quarters of the shorter one's
# words are in the other; the thesis and every reason are held to it, across books.
# The plan and the invalidation are not: they are meant to name the same levels.
#
# A RISK IS HELD TIGHTER, at half. It is by definition what is not in the call, and
# the second real brief listed "Crowded NQ longs (6,114 contracts, 98th pct) can flush
# on a break" under a call whose third reason was the same position and the same two
# figures in other words.
REPEAT_SHARE = 0.75
RISK_REPEAT_SHARE = 0.5
_STOP = frozenset({
    "a", "an", "and", "are", "as", "at", "be", "been", "but", "by", "for", "from", "if", "in",
    "into", "is", "it", "its", "nor", "not", "of", "on", "or", "over", "so", "than", "that",
    "the", "then", "this", "to", "under", "was", "were", "while", "with",
})
_TOKEN = re.compile(r"[a-z0-9][a-z0-9.,%+-]*")


def _content_words(text: Any) -> set[str]:
    if not isinstance(text, str):
        return set()
    return {w for t in _TOKEN.findall(text.lower()) if (w := t.strip(".,")) and w not in _STOP}


def repeats(b: dict[str, Any]) -> list[str]:
    """What says a thing the report has already said, as the re-ask names it. Pure.

    Inside one book, two comments that are one comment; and a risk that restates the
    thesis or any comment. Two books' comments on the same market-wide factor are
    not a repeat: the dollar is the dollar for both, and each card is read alone."""
    out: list[str] = []
    said: list[tuple[str, set[str]]] = [("the thesis", _content_words(b.get("thesis")))]
    # The Stocks report's market comments are one more "book" here: read together, and
    # held against the risks, as a book's are.
    groups = ([{"book": "market", "factors": b["factors"]}] if b.get("factors") else []) \
        + list(b.get("calls") or [])
    for c in groups:
        book = c.get("book")
        parts = [(f"{book} {f.get('key')}", _content_words(f.get("line")))
                 for f in c.get("factors") or []]
        for i, (first, a) in enumerate(parts):
            for later, bb in parts[i + 1:]:
                small = min(len(a), len(bb))
                # Four words and up: two short fragments share their nouns by chance.
                if small >= 4 and len(a & bb) / small >= REPEAT_SHARE:
                    out.append(f"{later} repeats {first}")
        said += parts
    for i, risk in enumerate(b.get("risks") or [], 1):
        r = _content_words(risk)
        for name, a in said:
            small = min(len(a), len(r))
            if small >= 4 and len(a & r) / small >= RISK_REPEAT_SHARE:
                out.append(f"risk {i} repeats {name}")
                break
    # The list (brief_version 4): two items whose whys are one sentence are one story.
    whys = [(f"item {m.get('id')}", _content_words(m.get("why")))
            for m in b.get("movers") or [] if not m.get("server")]
    for i, (first, a) in enumerate(whys):
        for later, bb in whys[i + 1:]:
            small = min(len(a), len(bb))
            if small >= 4 and len(a & bb) / small >= REPEAT_SHARE:
                out.append(f"{later} repeats {first}")
    return out


def faults(b: dict[str, Any]) -> list[str]:
    """What sends a brief back besides a figure: a part over its limit, a reason
    said twice. Pure."""
    return [*too_long(b), *repeats(b)]


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
    out += [f.get("line") or "" for f in b.get("factors") or []]
    for c in b.get("calls") or []:
        out += [*(f.get("line") or "" for f in c.get("factors") or []),
                c.get("plan") or "", c.get("wrong_if") or ""]
    out += [x.get("note") or "" for x in b.get("today") or []]
    out += list(b.get("risks") or [])
    out += [x.get("note") or "" for x in b.get("headlines") or []]
    # The list's whys, the model's own: the VIX's and a filled row's line are the server's.
    server_lines = {w for _, w in VIX_REGIME.values()}
    out += [x.get("why") or "" for x in b.get("movers") or []
            if not x.get("server")
            and not (x.get("id") == "vix" and x.get("why") in server_lines)]
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


def length_retry(long: list[str]) -> str:
    """The re-ask for a brief over its limits or saying a thing twice (`faults`)."""
    return (
        f"Your answer breaks the brief's limits: {'; '.join(long[:10])}. Cut every "
        "over-long part to its limit: keep the strongest reason and drop what the tables "
        "already print. Say each fact once: a reason two books share belongs in the "
        "thesis, and the bullet that repeated it is dropped or replaced by something "
        "that is that book's own. Add nothing new, except an item the list was told it "
        "leaves out or is short of. Return the whole JSON object again."
    )


def retry_text(bad: list[str], long: list[str]) -> str:
    """One re-ask for both faults: a second answer costs the same either way."""
    return " ".join(x for x in (guard_retry(bad) if bad else "",
                                length_retry(long) if long else "") if x)


def _reask(payload: dict[str, Any], key: str, content: str, bad: list[str],
           facts: dict[str, Any], long: list[str] | None = None,
           ) -> tuple[dict[str, Any] | None, dict[str, Any] | None, str]:
    """One corrective re-ask on the same model and mode → (brief, doc, outcome)."""
    retry = dict(payload)
    retry["messages"] = [*payload["messages"], {"role": "assistant", "content": content},
                         {"role": "user", "content": retry_text(bad, long or [])}]
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


_LOOSE_MOVERS = f"""  "movers": [ {{ "id": "c3" | "h7" | "rates" | "vix" | "positioning",
                "impact": one of "high" | "medium" | "low",
                "effect": one of "supportive" | "pressure" | "two-way" | "neutral" | "priced",
                "why": "{LIMITS['mover']} words at most" }} ],
                // {MOVERS_MIN}-{MOVERS_MAX} items, the most important first"""

LOOSE_SHAPE = f"""{{
  "thesis": "the bottom line, one or two sentences, {LIMITS['thesis']} words at most",
{_LOOSE_MOVERS}
  "calls": [ {{ "book": one of the books in scope ("NQ", "ES", "GC", "SIL", "CL"),
               "open_bias": one of "bullish" | "leaning bullish" | "neutral" |
                           "leaning bearish" | "bearish",
               "conviction": integer 1-5 }} ]   // one per book
}}"""


LOOSE_SHAPE_ETFS = f"""{{
  "thesis": "the bottom line, one or two sentences, {LIMITS['thesis']} words at most",
{_LOOSE_MOVERS}
  "calls": [ {{ "book": one of "SPY", "QQQ", "IWM",
               "open_bias": one of "bullish" | "leaning bullish" | "neutral" |
                           "leaning bearish" | "bearish",
               "conviction": integer 1-5 }} ]   // all three
}}"""


def loose_ask(messages: list[dict[str, str]], shape: str = LOOSE_SHAPE) -> dict[str, str]:
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
            + shape
        ),
    }


class AttemptTimeout(TimeoutError):
    """An attempt abandoned at ATTEMPT_WALL_SEC while the provider was still writing."""


def _post(
    payload: dict[str, Any],
    key: str,
    timeout: int = REQUEST_TIMEOUT_SEC,
    wall_sec: float = ATTEMPT_WALL_SEC,
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
            "X-Title": "HERMES",
        },
    )
    deadline = time.monotonic() + wall_sec
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return json.loads(_read_by(r, deadline, wall_sec).decode("utf-8"))


def _read_by(r: Any, deadline: float, wall_sec: float) -> bytes:
    """The whole body, or AttemptTimeout once `deadline` has passed.

    `read1` hands back whatever one socket read delivered instead of filling a
    buffer — `read(n)` on a chunked body keeps taking chunks until it holds `n`
    bytes, which with 11-byte keep-alives is the whole wait. So the clock is
    checked at the pace bytes arrive: every three seconds while OpenRouter
    keeps the connection alive, and a true stall still raises the socket's own
    timeout as before. A fake response without `read1` (the tests') is read
    whole.
    """
    read1 = getattr(r, "read1", None)
    if read1 is None:
        whole: bytes = r.read()
        return whole
    parts: list[bytes] = []
    while True:
        if time.monotonic() > deadline:
            r.close()
            raise AttemptTimeout(
                f"abandoned after {wall_sec:.0f}s — the provider was still writing"
            )
        chunk: bytes = read1(65536)
        if not chunk:
            return b"".join(parts)
        parts.append(chunk)


def note_id(now: datetime) -> str:
    """The id a note minted at `now` gets — ET to the second. It is the file's
    name, and since jobs.py the id of the job that writes it, so the two are
    minted from one clock reading rather than two."""
    return f"{now.astimezone(ET):%Y%m%d-%H%M%S}"


def generate(
    snap: dict[str, Any],
    model: str | None = None,
    label: str = "manual",
    session: str = "auto",
    asset: str = "all",
    now: datetime | None = None,
    scan: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Build the digest, ask the model, store and return the report.

    `now` is the moment the note is dated from; the job runner passes the one
    it minted the job id from (api.py), so the report's id is the job's. `scan` is
    the scanner's payload, which the Stocks report (`ETF_ASSET`) reads its tape and
    its funds' levels from.
    """
    key = _key()
    now = now or datetime.now(UTC)
    et = now.astimezone(ET)
    model = model or DEFAULT_MODEL
    book = resolve_asset(asset)
    # The Stocks report is New York's alone, whatever was asked.
    sess = "ny" if book == ETF_ASSET else resolve_session(snap.get("clock") or {}, session)

    base: dict[str, Any] = {
        "ok": False,
        "id": note_id(now),
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
        # 2 is the short brief (2026-11-15, SCHEMA). The page reads this to choose
        # its layout; a note without it has the longer shape it was written in.
        "brief_version": BRIEF_VERSION,
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

    if book == ETF_ASSET:
        # An Indexes report's tables and digest, with the funds, the tape and their
        # levels in the futures' place (`_etf_facts`, `etf_view`).
        base_facts = build_facts(snap, sess, "indexes")
        facts = _etf_facts(snap, scan, base_facts)
        digest = etf_view(shown(build_digest(snap, sess, "indexes", base_facts)), facts)
    else:
        facts = build_facts(snap, sess, book)
        # As the model is shown it (`shown`): what is stored is what was read.
        # And as the REPORT is to read it: no dealer gamma, the key levels, the rows the
        # page prints (`report_view`).
        digest = report_view(shown(build_digest(snap, sess, book, facts)), facts)
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
    # Models abandoned at the wall clock. A pool that crawled for four minutes
    # is not going to be quick on its second try, so its other entries in the
    # plan are passed over rather than spent.
    slow: set[str] = set()
    for candidate, mode in plan:
        if len(attempts) >= MAX_ATTEMPTS:
            break
        if candidate in slow:
            continue
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
            "messages": messages if mode == "schema" else [*messages[:-1], loose_ask(
                messages, LOOSE_SHAPE_ETFS if book == ETF_ASSET else LOOSE_SHAPE)],
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
                "json_schema": {"name": "session_bias", "strict": True, "schema": schema_for(book)},
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
        except AttemptTimeout as e:
            # Not unreachable — the provider was answering, too slowly to wait
            # for. The next model gets what is left of the budget.
            attempts.append({"model": candidate, "mode": mode, "error": str(e)})
            slow.add(candidate)
            continue
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
                "error": "JSON did not match the brief shape (needs a thesis and a "
                         f"readable call for each of {', '.join(facts['books'])})",
            })
            base["raw"] = content[:2000]
            continue

        # THE NUMERAL GUARD (see `unverified`). What the model saw is the user
        # turn — the digest and its framing — so that is what a figure must
        # come from.
        seen = messages[-1]["content"]
        bad = unverified(brief, seen)
        # AND THE LIMITS AND THE REPEATS (`faults`), in the same single re-ask: they
        # are named together with any figure, and the second answer is judged on all.
        # With them, the list's own (`list_faults`): too short, or a high-impact
        # release of the session left off it.
        long = faults(brief) + list_faults(brief, facts, sess)
        if bad or long:
            note = " · ".join(x for x in (
                f"unverified numerals: {', '.join(bad[:8])}" if bad else "",
                f"over its limits: {'; '.join(long[:4])}" if long else "",
            ) if x)
            if (time.monotonic() - started) + _ATTEMPT_RESERVE <= BUDGET_SEC:
                fixed, doc2, outcome = _reask(payload, key, content, bad, facts, long)
                if fixed is not None and doc2 is not None:
                    bad2 = unverified(fixed, seen)
                    long2 = faults(fixed) + list_faults(fixed, facts, sess)
                    left = " · ".join(x for x in (
                        f"still unverified: {', '.join(bad2[:8])}" if bad2 else "",
                        f"still over: {'; '.join(long2[:4])}" if long2 else "",
                    ) if x)
                    outcome = f"re-ask {left}" if left else "ok after re-ask"
                    # Figures first: a shorter note is not worth an invented number.
                    if (len(bad2), len(long2)) < (len(bad), len(long)):
                        brief, bad, doc = fixed, bad2, doc2
                note += f" · {outcome}"
            attempts.append({"model": candidate, "mode": mode, "note": note})
        # Every high-impact release of the session is on the list, the model's or not.
        fill_missed(brief, facts, sess)
        base["unverified"] = bad
        base["words"] = brief_words(brief)

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


# ---- the Dashboard's report card and the 09:00 write (2026-11-16) --------------------
#
# WHY (owner, of the Dashboard: "the pre market card is a bit redundant or could be
# merged into the today game plan one, and then also market overview", then "do waht you
# recommend best"). The Market overview card read a note written at 22:23 ET on a
# Saturday, two days before the Monday it was about, which still argued from the
# ten-minute 200 EMA and dealer gamma. Its place is the Stocks report's (`ETF_ASSET`):
# the market report sheet for SPY, QQQ and IWM, and the 09:00 ET write is that report's
# now, so the card is the morning's own by the open.

#: The 09:00 write: from 09:00 ET on a trading day until the bell, two tries at most,
#: five minutes apart (the overview's rule, overview.auto_due).
AUTO_AT = dtime(9, 0)
AUTO_UNTIL = dtime(9, 30)
AUTO_TRIES = 2
AUTO_GAP_MIN = 5.0


def auto_due(now: datetime, hist: list[dict[str, Any]], tried: list[datetime],
             asset: str = ETF_ASSET) -> bool:
    """Whether the 09:00 Stocks report should be written now. Pure.

    A trading day, between 09:00 and the bell, with no report about `asset` written
    since 09:00, and fewer than AUTO_TRIES tries since 09:00, the last AUTO_GAP_MIN ago."""
    et = now.astimezone(ET)
    if not is_trading_day(et.date()) or not (AUTO_AT <= et.time() < AUTO_UNTIL):
        return False
    start = datetime.combine(et.date(), AUTO_AT, tzinfo=ET)
    for h in hist:
        try:
            t = datetime.fromisoformat(str(h.get("created_et")))
        except ValueError:
            continue
        if h.get("asset") == asset and t >= start:
            return False
    mine = [t for t in tried if t >= start]
    if len(mine) >= AUTO_TRIES:
        return False
    return not (mine and (now - max(mine)).total_seconds() < AUTO_GAP_MIN * 60.0)


def card_of(rep: dict[str, Any] | None) -> dict[str, Any] | None:
    """A stored Stocks report → the Dashboard's card: when it was written, the summary,
    the market's bias, each fund's call and up to three risks. None for anything else.
    Pure."""
    if not isinstance(rep, dict) or rep.get("asset") != ETF_ASSET or not rep.get("ok"):
        return None
    b = rep.get("report")
    if not isinstance(b, dict):
        return None
    m = (rep.get("facts") or {}).get("market") or {}
    return {
        "id": rep.get("id"), "et_label": rep.get("et_label"), "created_et": rep.get("created_et"),
        "auto": rep.get("label") == "auto", "underway": bool(rep.get("session_underway")),
        "thesis": b.get("thesis") or "",
        "market": {k: m.get(k) for k in ("bias", "score", "basis", "grade")} if m else None,
        "calls": [{k: c.get(k) for k in ("book", "open_bias", "conviction")}
                  for c in b.get("calls") or [] if isinstance(c, dict)],
        "risks": [r for r in b.get("risks") or [] if isinstance(r, str)][:3],
    }


_ASSET_OF: dict[str, tuple[float, str | None]] = {}
_CARD: dict[str, Any] = {"key": None, "card": None}


def latest_card(asset: str = ETF_ASSET) -> dict[str, Any] | None:
    """The newest stored report about `asset` as the Dashboard's card, or None. Each file's
    subject is remembered by its time on disk, so a poll reads one file at most."""
    try:
        files = sorted((f for f in os.listdir(REPORTS_DIR) if f.endswith(".json")),
                       reverse=True)
    except OSError:
        return None
    for f in files[:40]:
        try:
            mt = os.path.getmtime(os.path.join(REPORTS_DIR, f))
        except OSError:
            continue
        key = f"{f}:{mt}"
        known = _ASSET_OF.get(f)
        if known is not None and known[0] == mt and known[1] != asset:
            continue
        if known is not None and known[0] == mt and _CARD["key"] == key:
            return _CARD["card"]  # type: ignore[no-any-return]
        rep = load(f[:-5])
        got = rep.get("asset") if isinstance(rep, dict) else None
        _ASSET_OF[f] = (mt, got)
        if got == asset:
            card = card_of(rep)
            _CARD.update(key=key, card=card)
            return card
    return None


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


def remove_many(ids: Iterable[str]) -> list[str]:
    """Delete several stored reports; the ids that actually went, in the order asked.

    Each goes through `remove`, so each is basenamed: an id that is not a
    stored report — a traversal, a typo, one that already went — simply does
    not appear in the answer.
    """
    return [i for i in ids if remove(i)]


def remove_all() -> list[str]:
    """Delete every stored report — the directory's worth, not the list's.

    `history` shows the newest twenty while KEEP holds forty, so "all" has to
    be read off the disk or it would leave the older half behind and call the
    list empty. The ids that went, newest first.
    """
    try:
        names = sorted((n for n in os.listdir(REPORTS_DIR) if n.endswith(".json")), reverse=True)
    except OSError:
        return []
    return [n[:-5] for n in names if remove(n[:-5])]


def configured() -> dict[str, Any]:
    """What the panel needs to explain itself when there is no key."""
    return {"enabled": bool(_key()), "model": DEFAULT_MODEL}
