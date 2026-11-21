"""
The Market Outlook: what the markets are doing TOGETHER, read as one pattern.

WHY (owner, 2026-11-21: "should we add a Market Outlook card that compares Stocks/the
major indices, gold, silv, bitcoin, us bonds, oil, USD since theyre represent different
aspects. eg usually when one drops another will go up and vice versa, which means if all
drop at the same time, that is indicitive of something?"; of the mock on that Friday's
close: "go ahead as mocked, keep the name Market Outlook"). Every one of these prices was
already on the Macro board, a row each, and nothing read them against each other. On Fri
20 Nov the S&P fell 3.2%, gold 4.0% and silver 7.3% while the 10-year note rose: on a
plain fear day gold holds or rises, so gold falling with stocks is the day's fact, and no
panel said it.

EACH MOVE IN ITS OWN USUAL DAY (drivestats.py: the mean absolute daily change over the
last twenty sessions), because a 1% day is nothing for silver and a great deal for the
note. A market has moved from half a usual day (drivestats.START), which is also where a
driver starts to count on the bias board.

THE PATTERN is a fixed rule over three markets, stocks, bonds and gold, with the dollar
as a tiebreak (`classify`), and "Mixed" or "Quiet" whenever they do not line up, which is
most days. It says what today is; it does not say what tomorrow will be.

IT IS CONTEXT AND NOT A VOTE. Nothing here feeds the bias or the Scanner's score, and the
card prints every move in ink: a sign is not a side. Each day's read is written to
cache/outlook_record.jsonl once its figures are final, so what followed each pattern can
be counted later; until then the patterns' meanings are the textbook's, not this desk's
record.

WHAT THE FIGURES ARE. The live quote's change, the same figure the Macro board prints.
While the futures are shut (the weekend, the daily break) that is the session just
finished, and bitcoin, which never shuts, is read for that same day (`coin_change`).
Overnight, from the 18:00 ET reopen to 04:00, the quotes are a session a few hours old,
so the card keeps the last close's read from the record and says the night in a line.

PURE but for `read` and `append`.
"""

from __future__ import annotations

import json
import os
from datetime import UTC, date, datetime, timedelta
from typing import Any
from zoneinfo import ZoneInfo

from . import drivestats
from .config import CACHE_DIR

ET = ZoneInfo("America/New_York")

RECORD_NAME = "outlook_record.jsonl"
RECORD_FILE = os.path.join(CACHE_DIR, RECORD_NAME)

#: The card's rows, in its order: the quote's key, its group's word, the row's own name
#: (none where the group's word is the name).
ROWS: tuple[tuple[str, str, str], ...] = (
    ("ES", "Stocks", "S&P 500"),
    ("NQ", "Stocks", "Nasdaq 100"),
    # "US 10-year", not "10Y note" (owner, 2026-11-21: "what are the bond 10y note? is that
    # bond 1d? or 1y etc?"): beside a column of one-day moves, "10Y" read as a time span.
    ("ZN", "Bonds", "US 10-year"),
    ("DXY", "Dollar", "DXY"),
    ("GC", "Gold", ""),
    ("SILVER", "Silver", ""),
    ("WTI", "Oil", "WTI"),
    ("BTC", "Bitcoin", ""),
)
#: The quote keys behind each leg the rule reads; stocks is the mean of its two.
LEGS: dict[str, tuple[str, ...]] = {
    "stocks": ("ES", "NQ"), "bonds": ("ZN",), "dollar": ("DXY",), "gold": ("GC",),
    "silver": ("SILVER",), "oil": ("WTI",), "bitcoin": ("BTC",),
}
#: The legs a sentence names, in the order it names them (the dollar is said on its own).
SAID: tuple[str, ...] = ("stocks", "bonds", "gold", "silver", "oil", "bitcoin")

#: A market has moved from this many usual days, either way.
MOVE = drivestats.START
#: One, two and three arrows: from MOVE, and from these.
ARROWS: tuple[float, float] = (1.5, 2.5)
#: Bitcoin's usual day when the feed has too little history to measure one, in percent.
BTC_USUAL = 2.5
#: The rows a record line is not written without a measured usual day for (`record_line`).
RECORD_NEEDS: tuple[str, ...] = ("ES", "ZN", "GC")

#: THE SENTIMENT SCALE (owner, 2026-11-21: "a visual indicator ... like if it shows risk on,
#: or risk off or extreme greed or extreme fear ... kind of like a market sentiment visual
#: indicator"; of the picture at -78, Extreme fear: "i like it"). How hard risk is being
#: bought or sold TODAY, -100 to +100: each leg's move in its own usual day, capped at
#: SENT_CAP, weighed, and scaled so that every leg at the cap is 100. The legs and their
#: weights are a judgement, not a fit.
#:
#: STOCKS, THE VIX, CREDIT AND BITCOIN, AND NOT THE HAVENS. Gold, bonds and the dollar
#: are what the pattern is read from, and they cannot also be the amount: on Fri 20 Nov
#: gold fell 2.9 usual days WITH stocks, and a scale that reads a haven sold as appetite
#: for risk would have set that against the S&P's fall and called the day near neutral.
#: The VIX counts here because this is a scale of fear and not a side: it votes on nothing
#: (bias.py), and this number feeds nothing.
SENTIMENT: tuple[tuple[str, int], ...] = (("stocks", 40), ("vix", 25), ("credit", 20),
                                          ("bitcoin", 15))
SENT_CAP = 3.0
#: The scale's words, from the score each starts at; under the first it is "Extreme fear".
SENT_WORDS: tuple[tuple[int, str], ...] = ((60, "Extreme greed"), (20, "Greed"),
                                           (-19, "Neutral"), (-59, "Fear"))

#: The quotes are today's from the pre-market's start to the futures' daily break, ET minutes.
LIVE_FROM = 4 * 60
LIVE_TO = 17 * 60

#: Each pattern: its name, and what it is in a sentence, while it is happening and after.
PATTERNS: dict[str, tuple[str, str, str]] = {
    "sold": ("Everything sold",
             "Unusual: stocks, bonds and gold are all falling. Only cash is holding.",
             "Unusual: stocks, bonds and gold all fell. Only cash held."),
    "rates_shock": ("Rates shock",
                    "Stocks and bonds are falling together: yields are driving.",
                    "Stocks and bonds fell together: yields were driving."),
    "forced": ("Forced selling",
               "Unusual: gold is falling with stocks.",
               "Unusual: gold fell with stocks."),
    "risk_off": ("Risk-off",
                 "Money is leaving stocks for safety.",
                 "Money left stocks for safety."),
    "rally": ("Everything rally",
              "Unusual: stocks, bonds and gold are all rising.",
              "Unusual: stocks, bonds and gold all rose."),
    "rates_relief": ("Rates relief",
                     "Stocks and bonds are rising together: falling yields are driving.",
                     "Stocks and bonds rose together: falling yields were driving."),
    "risk_on": ("Risk-on",
                "Money is leaving safety for stocks.",
                "Money left safety for stocks."),
    "stocks_alone": ("Stocks alone",
                     "Stocks are moving on their own: bonds, gold and the dollar are not.",
                     "Stocks moved on their own: bonds, gold and the dollar did not."),
    "mixed": ("Mixed", "No pattern across the markets.", "No pattern across the markets."),
    "quiet": ("Quiet", "Nothing has moved half a usual day.", "Nothing moved half a usual day."),
}


def _num(v: Any) -> float | None:
    if isinstance(v, bool) or not isinstance(v, int | float):
        return None
    f = float(v)
    return f if f == f else None


def _up(x: float | None) -> bool:
    return x is not None and x >= MOVE


def _dn(x: float | None) -> bool:
    return x is not None and x <= -MOVE


def arrows(mult: float | None) -> int:
    """A move's arrows, signed: none under MOVE usual days, then one, two, three. Pure."""
    if mult is None or abs(mult) < MOVE:
        return 0
    n = 1 + sum(1 for step in ARROWS if abs(mult) >= step)
    return n if mult > 0 else -n


def legs_of(mults: dict[str, float]) -> dict[str, float | None]:
    """The rule's legs from each quote's move in usual days: stocks the mean of the S&P
    and the Nasdaq, each of the rest its own row. Pure."""
    out: dict[str, float | None] = {}
    for leg, keys in LEGS.items():
        got = [mults[k] for k in keys if k in mults]
        out[leg] = sum(got) / len(got) if got else None
    return out


def classify(legs: dict[str, float | None]) -> str | None:
    """The pattern's key, or None without stocks, bonds and gold to read. Pure.

    Stocks set the side, then bonds and gold say which kind of day it is:

      stocks down   bonds down and gold down     everything sold
                    bonds down                   rates shock
                    gold down, bonds not         forced selling
                    bonds, gold or dollar up     risk-off
      stocks up     bonds up and gold up         everything rally
                    bonds up                     rates relief
                    bonds, gold or dollar down   risk-on
      either        the other three flat         stocks alone

    Anything else is mixed, or quiet when nothing at all has moved. Gold falling WITH
    stocks while bonds are not sold is the one with no mirror: when yields are not the
    reason, a haven sold beside the thing it hedges is selling to raise cash."""
    s, b, g, d = (legs.get(k) for k in ("stocks", "bonds", "gold", "dollar"))
    if s is None or b is None or g is None:
        return None
    still = not (_up(b) or _dn(b) or _up(g) or _dn(g) or _up(d) or _dn(d))
    if _dn(s):
        if _dn(b):
            return "sold" if _dn(g) else "rates_shock"
        if _dn(g):
            return "forced"
        if _up(b) or _up(g) or _up(d):
            return "risk_off"
        return "stocks_alone" if still else "mixed"
    if _up(s):
        if _up(b):
            return "rally" if _up(g) else "rates_relief"
        if _dn(b) or _dn(g) or _dn(d):
            return "risk_on"
        return "stocks_alone" if still else "mixed"
    moved = any(_up(legs.get(k)) or _dn(legs.get(k)) for k in LEGS)
    return "mixed" if moved else "quiet"


def _join(words: list[str]) -> str:
    return words[0] if len(words) == 1 else f"{', '.join(words[:-1])} and {words[-1]}"


def _named(keys: list[str]) -> list[str]:
    """Gold and silver together are "metals", where gold stood."""
    if "gold" in keys and "silver" in keys:
        return ["metals" if k == "gold" else k for k in keys if k != "silver"]
    return keys


def what_of(legs: dict[str, float | None]) -> str:
    """What moved, in words: "stocks and metals sold, bonds bid, dollar up". Pure."""
    sold = _named([k for k in SAID if _dn(legs.get(k))])
    bid = _named([k for k in SAID if _up(legs.get(k))])
    parts = ([f"{_join(sold)} sold"] if sold else []) + ([f"{_join(bid)} bid"] if bid else [])
    d = legs.get("dollar")
    if _up(d) or _dn(d):
        parts.append("dollar up" if _up(d) else "dollar down")
    return ", ".join(parts)


def sentiment_word(score: int) -> str:
    """Extreme fear to Extreme greed: fear from -20, extreme from -60, and the mirror. Pure."""
    return next((word for floor, word in SENT_WORDS if score >= floor), "Extreme fear")


def sentiment(legs: dict[str, float | None]) -> dict[str, Any] | None:
    """The scale off its legs in usual days: `stocks`, `vix` (its own move, turned over
    here: a rising VIX is fear), `credit`, `bitcoin`. A leg not read is left out and the
    rest carry its weight; without stocks there is no scale. Pure."""
    parts: list[tuple[str, int, float]] = []
    for name, weight in SENTIMENT:
        m = legs.get(name)
        if m is None:
            continue
        m = -m if name == "vix" else m
        parts.append((name, weight, max(-SENT_CAP, min(SENT_CAP, m))))
    if not any(name == "stocks" for name, _, _ in parts):
        return None
    total = sum(w for _, w, _ in parts)
    score = round(100.0 * sum(w * m for _, w, m in parts) / SENT_CAP / total)
    return {"score": score, "label": sentiment_word(score),
            "legs": [{"key": n, "weight": w, "mult": round(m, 1)} for n, w, m in parts]}


def _traded_on(q: dict[str, Any] | None, day: date) -> bool:
    """Whether a quote's last trade was on `day` (ET). Pure."""
    at = _num((q or {}).get("quote_time"))
    return bool(at) and datetime.fromtimestamp(at or 0.0, ET).date() == day


def yield_bp(q: dict[str, Any] | None, day: date) -> float | None:
    """The 10-year yield's change on `day` in basis points, for the bond row, or None when
    the yield has not traded that day. The cash yield is quoted in US hours only, so until
    it opens it still holds the day before's change, and the row beside it is the note
    future's move of THIS day: the two would be about different days. Pure."""
    chg = _num((q or {}).get("chg"))
    return round(chg * 100.0, 1) if chg is not None and _traded_on(q, day) else None


def _dated(q: dict[str, Any] | None, day: date) -> float | None:
    """A cash-hours quote's change, when it is `day`'s: its regular session's if that
    traded on the day, else its pre-market trade of the day (quotes.with_ext). The VIX and
    high yield hold yesterday's change until they trade, and yesterday's is not today's. Pure."""
    if not q:
        return None
    if _traded_on(q, day):
        return _num(q.get("pct"))
    ext = q.get("ext")
    if isinstance(ext, dict) and ext.get("kind") == "pre" and ext.get("day") == day.isoformat():
        return _num(ext.get("pct"))
    return None


def state_of(es: dict[str, Any] | None, now: datetime) -> tuple[str, date]:
    """("live" | "close" | "overnight", the day the quotes' changes are about). Pure.

    Read off the S&P future's own feed and not the calendar: on a US holiday the future
    trades a short session, and a calendar would call those live moves the day before's
    close. Shut (the weekend, the 17:00 ET break, a holiday's halt), its change is the
    session just finished, dated by its last trade."""
    et = now.astimezone(ET)
    if es is not None and es.get("feed") == "closed":
        at = _num(es.get("quote_time"))
        return "close", (datetime.fromtimestamp(at, ET).date() if at else et.date())
    minute = et.hour * 60 + et.minute
    if LIVE_FROM <= minute < LIVE_TO:
        return "live", et.date()
    return "overnight", (et.date() + timedelta(days=1) if minute >= LIVE_TO else et.date())


def coin_change(row: dict[str, Any] | None, quote: dict[str, Any] | None, day: date,
                now: datetime) -> float | None:
    """Bitcoin's percent change on `day`, for a card about a session the shut markets'
    quotes still show. None when that day's change cannot be had: the row is then left
    off the card, never filled with another day's move. Pure.

    The coin's day is the UTC day, as its daily bars and its quote's previous close are
    (19:00 or 20:00 ET to the same hour the next evening): the nearest it has to a
    session. While that day is still running the quote IS its change. After it:

      its close        the quote's previous close when the day was yesterday, else its bar
      the close before that day's own bar

    THE BAR FOR THE DAY JUST ENDED CANNOT BE COUNTED ON (2026-11-21, 03:40 UTC, the card's
    first hour): Yahoo's daily bars ran 19 Nov, 21 Nov, with no bar for the 20th, so the
    card fell back to the quote and printed Saturday's -2.8% as Friday's move. Friday's
    was -5.0%, which the quote's own previous close gives."""
    q = quote or {}
    utc_day = now.astimezone(UTC).date()
    if day >= utc_day:
        return _num(q.get("pct"))
    hist = (row or {}).get("hist") or {}
    bars = dict(zip(hist.get("days") or [], hist.get("closes") or [], strict=False))

    def close_of(d: date) -> float | None:
        if d == utc_day - timedelta(days=1) and _num(q.get("prev")):
            return _num(q.get("prev"))
        return _num(bars.get(d.isoformat()))

    last, prev = close_of(day), close_of(day - timedelta(days=1))
    return (last / prev - 1.0) * 100.0 if last and prev else None


def history(context: list[dict[str, Any]], today: date) -> list[tuple[str, str]]:
    """(day, pattern) for every finished session the daily closes can size: each move in
    the usual day of the twenty sessions BEFORE it, so a day is read as it would have
    been read then. Oldest first. Pure."""
    keys = {k for ks in LEGS.values() for k in ks}
    mults: dict[str, dict[str, float]] = {}
    for row in context:
        key = str(row.get("key") or "")
        if key not in keys:
            continue
        series = sorted(drivestats.changes(row, today).items())
        out: dict[str, float] = {}
        for i, (day, chg) in enumerate(series):
            prior = [abs(c) for _, c in series[max(0, i - drivestats.USUAL_N):i]]
            if len(prior) >= drivestats.USUAL_MIN and sum(prior) > 0:
                out[day] = chg / (sum(prior) / len(prior))
        mults[key] = out
    if not all(k in mults for k in ("ES", "ZN", "GC")):
        return []
    days = sorted(set(mults["ES"]) & set(mults["ZN"]) & set(mults["GC"]))
    got: list[tuple[str, str]] = []
    for day in days:
        pattern = classify(legs_of({k: m[day] for k, m in mults.items() if day in m}))
        if pattern:
            got.append((day, pattern))
    return got


def _row(key: str, group: str, name: str, pct: float, mult: float, sized: bool,
         note: str | None = None, bp: float | None = None) -> dict[str, Any]:
    # What is printed is what is judged: the arrows and the pattern both read the move to
    # the one decimal the card shows, so a row printed "0.5×" always has its arrow.
    m = round(mult, 1)
    return {"key": key, "group": group, "name": name, "pct": round(pct, 2),
            "mult": m, "arrows": arrows(m), "sized": sized, "note": note,
            # The bond row's yield change in basis points; None on every other row.
            "yield_bp": bp}


def _day_word(d: date) -> str:
    return f"{d:%a} {d.day} {d:%b}"


def _read(rows: list[dict[str, Any]], past: bool) -> dict[str, Any] | None:
    """The pattern off a card's rows: its key, name, what moved and the sentence."""
    legs = legs_of({r["key"]: float(r["mult"]) for r in rows})
    key = classify(legs)
    if key is None:
        return None
    name, now_words, past_words = PATTERNS[key]
    return {"key": key, "name": name, "what": what_of(legs),
            "tell": past_words if past else now_words}


def build(snap: dict[str, Any], now: datetime,
          last: dict[str, Any] | None = None) -> dict[str, Any]:
    """The card. `last` is the newest line of the record (`read`), which the card shows
    overnight in place of a session a few hours old. Pure."""
    quotes = {str(q.get("key")): q for q in snap.get("quotes") or []
              if isinstance(q, dict) and q.get("key")}
    context = [c for c in snap.get("context") or [] if isinstance(c, dict)]
    by_key = {str(c.get("key")): c for c in context}
    es = quotes.get("ES") or quotes.get("NQ")
    state, day = state_of(es, now)
    today = now.astimezone(ET).date()
    # The usual day as it stood BEFORE the day being read: on a Saturday the closes hold
    # Friday, and a Friday sized against a month that includes it reads small (the card's
    # first build printed the S&P's -3.2% as 2.7 usual days; it was 3.0).
    st = drivestats.Stats(context, day if state == "close" else today)

    rows: list[dict[str, Any]] = []
    for key, group, name in ROWS:
        pct = _num((quotes.get(key) or {}).get("pct"))
        if key == "BTC" and state == "close":
            # The coin trades through the weekend: its quote is no longer that session's.
            # Failing its closes, the figure this same day's record line was written with.
            pct = coin_change(by_key.get("BTC"), quotes.get("BTC"), day, now)
            if pct is None and isinstance(last, dict) and last.get("day") == day.isoformat():
                pct = next((_num(r.get("pct")) for r in last.get("rows") or []
                            if isinstance(r, dict) and r.get("key") == "BTC"), None)
        if pct is None:
            continue
        usual, sized = st.usual(key)
        if key == "BTC" and not sized:
            usual = BTC_USUAL
        # The bond row is the note's PRICE, so that green is bonds bought as it is for every
        # other row; the yield, the figure a desk quotes, rides beside it when it is the day's.
        bp = yield_bp(quotes.get("US10Y"), day) if key == "ZN" else None
        note = f"The 10-year yield {bp:+.0f}bp" if bp is not None else None
        rows.append(_row(key, group, name, pct, pct / usual if usual else 0.0, sized, note, bp))

    read = _read(rows, past=state == "close")
    if read is None:
        return {"ok": False, "state": state,
                "why": "The quotes for stocks, bonds and gold have not all been read yet."}
    past = history(context, today)
    # The scale's legs: stocks and the coin as the rows have them, the VIX and high yield
    # off their own quotes when those are this day's.
    mults = {r["key"]: float(r["mult"]) for r in rows}

    def in_usual(key: str) -> float | None:
        moved = _dated(quotes.get(key), day)
        its_day = st.usual(key)[0]
        return moved / its_day if moved is not None and its_day else None

    out: dict[str, Any] = {
        "ok": True, "state": state, "day": day.isoformat(), "from": "live",
        "label": (f"{_day_word(day)} · close" if state == "close"
                  else f"{_day_word(day)} · live" if state == "live"
                  else "Overnight · since 18:00 ET"),
        **read, "rows": rows,
        "sentiment": sentiment({"stocks": legs_of(mults)["stocks"], "vix": in_usual("VIX"),
                                "credit": in_usual("HYG"), "bitcoin": mults.get("BTC")}),
        "seen": {"n": sum(1 for _, k in past if k == read["key"]), "of": len(past)},
        "overnight": None,
    }
    if state == "overnight" and isinstance(last, dict) and last.get("rows"):
        kept = from_record(last)
        if kept is not None:
            # The night in a line under the last close's read.
            kept["overnight"] = {"name": read["name"], "what": read["what"]}
            kept["seen"] = {"n": sum(1 for _, k in past if k == kept["key"]), "of": len(past)}
            return kept
    return out


# ---- the record ----------------------------------------------------------------------------


def record_line(out: dict[str, Any], now: datetime) -> dict[str, Any] | None:
    """The line a finished session leaves: its day, its pattern and every row's move. None
    unless `out` is a close read off the live quotes, with the three markets the pattern
    is read from sized off their own history. Pure.

    NOT BEFORE THE HISTORY HAS BEEN READ (2026-11-21, the record's first line): the job
    ran 25 seconds after a restart, ahead of the daily closes, and wrote the S&P's -3.2% as
    3.6 usual days off the stated fallback, where the measured figure is 3.0. A line is
    written once and never corrected, so it waits (collector._do_outlook_record)."""
    if not (out.get("ok") and out.get("state") == "close" and out.get("from") == "live"):
        return None
    sized = {r["key"] for r in out["rows"] if r.get("sized")}
    if not all(k in sized for k in RECORD_NEEDS):
        return None
    return {"day": out["day"], "at": round(now.timestamp()), "key": out["key"],
            "what": out["what"], "sentiment": out.get("sentiment"),
            "rows": [{"key": r["key"], "pct": r["pct"], "mult": r["mult"], "sized": r["sized"],
                      "note": r.get("note"), "yield_bp": r.get("yield_bp")}
                     for r in out["rows"]]}


def from_record(line: dict[str, Any]) -> dict[str, Any] | None:
    """A record line as the card: the read as it was written at that close. Pure."""
    names = {k: (g, n) for k, g, n in ROWS}
    rows = []
    for r in line.get("rows") or []:
        pct, mult = _num(r.get("pct")), _num(r.get("mult"))
        if r.get("key") in names and pct is not None and mult is not None:
            group, name = names[r["key"]]
            rows.append(_row(r["key"], group, name, pct, mult, bool(r.get("sized", True)),
                             r.get("note"), _num(r.get("yield_bp"))))
    read = _read(rows, past=True)
    try:
        day = date.fromisoformat(str(line.get("day")))
    except ValueError:
        return None
    if read is None:
        return None
    kept = line.get("sentiment")
    return {"ok": True, "state": "overnight", "day": day.isoformat(), "from": "record",
            "label": f"{_day_word(day)} · close", **read, "rows": rows,
            "sentiment": kept if isinstance(kept, dict) and "score" in kept else None,
            "seen": {"n": 0, "of": 0}, "overnight": None}


def read(path: str = RECORD_FILE) -> list[dict[str, Any]]:
    """Every line on file, oldest first; a line that will not parse is skipped."""
    out: list[dict[str, Any]] = []
    try:
        with open(path, encoding="utf-8") as f:
            for raw in f:
                try:
                    obj = json.loads(raw)
                except ValueError:
                    continue
                if isinstance(obj, dict) and obj.get("day"):
                    out.append(obj)
    except OSError:
        return []
    return out


def append(line: dict[str, Any], path: str = RECORD_FILE) -> None:
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "a", encoding="utf-8") as f:
        f.write(json.dumps(line, separators=(",", ":")) + "\n")
