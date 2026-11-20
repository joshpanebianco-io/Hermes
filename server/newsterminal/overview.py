"""
The Market overview — the Stocks desk's written read of the market before the open.

WHY IT REPLACED THE GAME PLAN'S PER-NAME PLANS (owner, 2026-11-13, agreed in
the session): the Today list already ranks the names for the hour and the
Setups table carries each one's levels, so a model rewriting a plan per name
said again what the table showed. What the desk lacked was the market around
the names: where the indexes sit against their levels, which sectors lead and
why, the day's prints and the Fed, the few stories that matter, and what that
means for the list. The strip's "Game plan" became "Market" and writes this.

THE GAME PLAN'S CONTRACT, KEPT. The tables are the server's and the words are
the model's: `build_facts` computes every figure the page prints (most of it
the game plan's own `stockplan.build_facts`), the model writes prose only, a
story it picks must be one of the ids it was shown, every numeral it writes is
checked against what it saw (one re-ask, then `unverified`), and the clock and
the release risks are written from the calendar by the server. The model chain,
budget and storage are stockplan's (`ask_chain`, `_store`): an overview is kept
in the plans folder with `kind: "overview"`, so the older game plans stay in
the same history and still open.

WRITTEN BY ITSELF AT 09:00 ET (`auto_due`), as well as on the button: half an
hour before the bell the pre-market has had five hours, the 08:30 prints are
out, and there is time to read it.
"""

from __future__ import annotations

import json
import os
from datetime import UTC, datetime, time
from typing import Any
from zoneinfo import ZoneInfo

from . import report as rp
from . import stockplan as sp
from .holidays import is_trading_day

ET = ZoneInfo("America/New_York")

KIND = "overview"

#: The automatic write: from 09:00 ET on a trading day, until the bell. Two tries
#: at most, five minutes apart, so a model that refuses once gets a second go
#: and one that refuses twice does not spend the half hour.
AUTO_AT = time(9, 0)
AUTO_UNTIL = time(9, 30)
AUTO_TRIES = 2
AUTO_GAP_MIN = 5.0

INDEXES = ("SPY", "QQQ", "IWM")
SECTOR_N = 3
THEME_N = 3
STORY_N = 12
TODAY_N = 8
NEWS_MAX = 5


# --------------------------------------------------------------------------
# The facts.
# --------------------------------------------------------------------------


def _num(v: Any) -> float | None:
    return float(v) if isinstance(v, int | float) and not isinstance(v, bool) else None


def _d(v: Any) -> dict[str, Any]:
    return v if isinstance(v, dict) else {}


def where_word(last: float | None, lv: dict[str, Any]) -> str | None:
    """Where a price sits against the previous day's range. Pure."""
    pdh, pdl = _num(lv.get("pdh")), _num(lv.get("pdl"))
    if last is None or pdh is None or pdl is None:
        return None
    if last > pdh:
        return "above the previous day's high"
    if last < pdl:
        return "below the previous day's low"
    return "inside the previous day's range"


def index_rows(scan: dict[str, Any]) -> list[dict[str, Any]]:
    """SPY, QQQ and IWM against their own levels, from the engine's rows. Pure."""
    by = {r.get("sym"): r for r in scan.get("rows") or [] if isinstance(r, dict) and r.get("ok")}
    out: list[dict[str, Any]] = []
    for sym in INDEXES:
        r = by.get(sym)
        if r is None:
            continue
        lv = _d(r.get("levels"))
        last = _num(r.get("last"))
        fr = _d(r.get("frame_read"))
        out.append({
            "sym": sym, "last": sp._r(last), "chg_pct": sp._r(r.get("chg_pct")),
            "ext_pct": sp._r(r.get("ext_pct")),
            "levels": {k: sp._r(lv.get(k)) for k in ("pdh", "pdl", "pmh", "pml", "pdc")},
            "where": where_word(last, lv),
            "ema200_10m": {1: "above", -1: "below"}.get(int(r.get("trend200") or 0)),
            "daily": fr.get("text") if isinstance(fr.get("text"), str) else None,
        })
    return out


def _sector_row(r: dict[str, Any], moves: dict[str, dict[str, Any]],
                names: dict[str, Any] | None, side: str) -> dict[str, Any]:
    key = str(r.get("key") or "")
    out: dict[str, Any] = {
        "key": key, "label": r.get("label"), "day_pct": sp._r(r.get("day_pct")),
        "rs_day": sp._r(r.get("rs_day")), "week_pct": sp._r(r.get("week_pct")),
        # The textbook drivers and today's verdict on them (stockplan.SECTOR_DRIVERS):
        # what the model may name as a cause, besides a story.
        "drivers": [f"{d['label']} {d['move']}: {d['effect']} ({d['why']})"
                    for d in sp.macro_for("", key, moves)],
    }
    slot = _d(_d(names).get(key))
    if slot:
        out["names"] = [f"{x.get('sym')} {x['chg']:+.2f}%" for x in slot.get(side) or []
                        if isinstance(x, dict) and isinstance(x.get("chg"), int | float)][:3]
    return out


def sector_table(snap: dict[str, Any], moves: dict[str, dict[str, Any]],
                 session: str) -> dict[str, Any]:
    """The sector SPDRs and the theme funds against SPY, best and worst, each with
    the drivers it answers to and the biggest names moving in it. Pure.

    BEFORE THE BELL THE FUNDS' MOVE IS THE LAST SESSION'S: their quotes are the
    regular session's, while the names under them (the wide read's leaders) move on
    the pre-market. `basis` says which, so the page and the model both can."""
    wide = _d(snap.get("breadth_all"))
    leaders = _d(wide.get("leaders")) or None

    def ranked(rows: Any, n: int) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
        live = [r for r in rows or [] if isinstance(r, dict) and r.get("key") not in ("SPY", "RSP")
                and _num(r.get("rs_day")) is not None]
        live.sort(key=lambda r: -float(r["rs_day"]))
        # A leader beat SPY and a laggard trailed it: on a day every fund rose with
        # the index, "leaders" are the ones that rose MORE.
        lead = [_sector_row(r, moves, leaders, "up") for r in live if r["rs_day"] > 0][:n]
        lag = [_sector_row(r, moves, leaders, "down") for r in live[::-1] if r["rs_day"] < 0][:n]
        return lead, lag

    s_lead, s_lag = ranked(snap.get("sectors"), SECTOR_N)
    t_lead, t_lag = ranked(snap.get("themes"), THEME_N)
    return {
        "basis": ("the last session (the funds do not trade before the bell)"
                  if session in ("pre", "closed") else "today"),
        "names_basis": "pre-market" if wide.get("basis") == "pre" else "the session",
        "leaders": s_lead, "laggards": s_lag, "themes_up": t_lead, "themes_down": t_lag,
    }


def wide_breadth(snap: dict[str, Any]) -> dict[str, Any] | None:
    """Advancers and decliners at $2bn+ from the wide read, and how many it covers."""
    w = snap.get("breadth_all")
    if not isinstance(w, dict) or not w.get("ok"):
        return None
    return {"advancers": w.get("advancers"), "decliners": w.get("decliners"),
            "traded": w.get("names"), "of": w.get("of"),
            "basis": "pre-market" if w.get("basis") == "pre" else "the session"}


def story_rows(stories: list[dict[str, Any]] | None) -> list[dict[str, Any]]:
    """The stock news the Dashboard leads with (tvnews.top), numbered s1… so a
    pick can only point at one of them. Pure."""
    out: list[dict[str, Any]] = []
    for s in stories or []:
        if not isinstance(s, dict) or not s.get("title"):
            continue
        out.append({"id": f"s{len(out) + 1}", "syms": [str(x) for x in s.get("syms") or []][:4],
                    "tag": str(s.get("tag") or ""), "title": str(s["title"]),
                    "publisher": str(s.get("provider") or ""), "url": str(s.get("url") or ""),
                    "age_min": sp._r(s.get("age_min"), 0)})
        if len(out) >= STORY_N:
            break
    return out


def today_rows(today: dict[str, Any] | None) -> dict[str, Any]:
    """The top of the Today list as it stands (today.py), without the tracked names
    it lists below its ranking. Pure."""
    t = _d(today)
    phase = _d(t.get("phase"))
    rows: list[dict[str, Any]] = []
    for r in t.get("rows") or []:
        if not isinstance(r, dict) or r.get("listed") or not r.get("sym"):
            continue
        story = _d(r.get("story")) or None
        rows.append({"sym": str(r["sym"]), "name": r.get("name"), "sector": r.get("sector"),
                     "chg_pct": sp._r(r.get("chg")), "lean": r.get("lean"),
                     "why": [str(w) for w in r.get("why") or [] if isinstance(w, str)][:4],
                     "story": None if story is None else {
                         "title": str(story.get("title") or ""), "tag": story.get("tag")}})
        if len(rows) >= TODAY_N:
            break
    return {"phase": phase.get("label"), "title": phase.get("title"), "rows": rows}


def build_facts(scan: dict[str, Any], snap: dict[str, Any], today: dict[str, Any] | None,
                stories: list[dict[str, Any]] | None) -> dict[str, Any]:
    """The overview's tables: the game plan's market blocks (stockplan.build_facts,
    without its names), the indexes against their levels, the sectors, the stories
    and the top of the Today list."""
    base = sp.build_facts(scan, snap, top=sp.TOP_MIN)
    base.pop("names", None)
    # The per-name lines of the plan's banner say nothing about the market.
    base["partial"] = [p for p in base.get("partial") or []
                       if not p.startswith(("Options chains", "Headlines still loading"))]
    session = str(base.get("session") or "closed")
    moves = sp.macro_moves(snap.get("quotes") or [])
    base.update({
        "kind": KIND,
        "index": index_rows(scan),
        "wide_breadth": wide_breadth(snap),
        "sectors": sector_table(snap, moves, session),
        "stories": story_rows(stories),
        "today": today_rows(today),
    })
    return base


# --------------------------------------------------------------------------
# What the model is told.
# --------------------------------------------------------------------------


def system_prompt(session: str) -> str:
    when = {
        "pre": "It is the pre-market: the bell is at 09:30 and the pre-market high and low are "
               "still forming.",
        "rth": "The session is underway: write what the market is doing, not what the open "
               "might do.",
        "post": "The session has closed: write it for the next session (trading_day).",
        "closed": "The market is closed: write it for the next session (trading_day).",
    }.get(session, "Write it for the next New York session.")
    return f"""\
You are the head of a New York equities desk writing the market overview one trader reads \
before the session. {when} The trader trades US stocks intraday: breaks and retests of the \
pre-market and previous-day highs and lows. This is not a plan for any one name — the trader \
has a ranked list for that. It is the market those names trade in, read in plain English.

The data: `index` is SPY, QQQ and IWM against their own levels (where each sits against the \
previous day's range, its pre-market high and low, its side of the ten-minute 200 EMA, its \
daily frame). `regime` is VIX, its band and curve shape and SPY's implied one-day move. \
`tape_count` is the engine's score of the tape from -100 to +100, with how many of its reads \
are live. `breadth` is sector funds up and down and equal weight against SPY; `wide_breadth` is \
advancers and decliners across every US stock at $2bn+ (before the bell, those that have \
traded pre-market, out of `of`). `fuel` is how much of its implied day each index has used. \
`sectors` is the sector funds and theme funds best and worst against SPY (`basis` says whether \
that is today or the last session), each with the macro drivers it answers to and today's \
verdict, and the biggest names moving in it. `macro` is the day's macro moves and the \
market's high-impact headlines (ids m1…); `stories` are the stock stories leading the tape \
(ids s1…). `prints` are the session's US releases against consensus, `fed` is what the next \
meetings price, `gamma` is dealer gamma in SPY and QQQ (POS damps moves, NEG lets breaks \
run — a regime, not a direction), `put_call` is how hedged the market is. `today` is the top \
of the trader's ranked list as it stands, each with why it ranks.

Write:
- `headline`: ONE line in your own words — the day's stance and what matters most. Never a \
news headline.
- `read`: three or four sentences. Where SPY, QQQ and IWM sit against their levels (as \
printed), VIX and its band, the tape's score and how many reads are live, breadth. Say \
plainly whether the tape leans, and how firmly.
- `sectors`: two or three sentences. The leaders and the laggards by name, as printed, and \
what is driving them: a driver from their list or a story from `stories` or `macro`. When \
nothing in the data explains a move, give the move without a cause — never invent one. Say \
when the funds' moves are the last session's.
- `macro`: two or three sentences. Today's prints with their times and what they could do to \
the tape; the next Fed meeting and what is priced; the 10-year, the dollar and crude as \
printed (a quote at its last close says so, with no verdict).
- `news`: three to five stories by id, from `stories` or `macro.headlines`, each with ONE \
line on why it matters for today's tape — the market, a sector, or a name in play. Pick by \
what moves prices today, not by what is newest.
- `risks`: one to three concrete ways today goes against the read — a level giving way, the \
tape turning, a crowded theme. The server lists the calendar itself, so leave releases out.
- `focus`: two or three sentences on what it means for today's list: the side and the \
sectors to favour or avoid, and the top of `today` in one line naming two to four of its \
symbols and why they rank.

Rules:
- Every number you write must be copied exactly from the data: prices, levels, percentages, \
times, counts. No arithmetic, no rounding. If a number you want is not printed, say it in words.
- Give every figure its unit. A fund's or a name's move is a percentage ("Energy rose 1.51%"); \
a fund's distance from SPY is in percentage points ("1.87 points ahead of SPY"); a yield's move \
is in basis points as printed. Never a bare "at 1.51".
- A move's sign is not a side. A rising yield, dollar or VIX is not bearish by itself, and \
gamma's sign is not a direction: say what it does, as the drivers' verdicts and the data say.
- Plain trader's English. Never print a field name or a JSON key (not rs_day, ext_pct, \
wide_breadth, tape_count or any other): say "against SPY", "in the pre-market", "the tape \
score".
- Be concrete. No disclaimers, no position sizes, no mention of being an AI."""


def _obj(props: dict[str, Any]) -> dict[str, Any]:
    return {"type": "object", "additionalProperties": False, "required": list(props),
            "properties": props}


_S: dict[str, Any] = {"type": "string"}


def schema(ids: list[str]) -> dict[str, Any]:
    """The strict schema — a pick's id is an enum, so it cannot name a story it was not shown."""
    pick = _obj({"id": {"type": "string", "enum": ids or ["m1"]}, "why": _S})
    return _obj({
        "headline": _S, "read": _S, "sectors": _S, "macro": _S,
        "news": {"type": "array", "minItems": 0, "maxItems": NEWS_MAX, "items": pick},
        "risks": {"type": "array", "minItems": 0, "maxItems": 3, "items": _S},
        "focus": _S,
    })


SKELETON = """{
  "headline": "one line",
  "read": "the indexes against their levels, VIX, the tape, breadth",
  "sectors": "leaders and laggards and what drives them",
  "macro": "the prints and their times, the Fed, yields / dollar / crude",
  "news": [ { "id": "an id from stories or macro.headlines", "why": "one line" } ],
  "risks": [ "..." ],
  "focus": "the side and sectors to favour, the top of the list in one line"
}"""


def build_digest(facts: dict[str, Any]) -> dict[str, Any]:
    """Exactly what the model is shown."""
    td = sp._parse_day(facts.get("trading_day")) or datetime.now(ET).date()
    return {
        "as_of_et": facts["as_of"],
        "session": facts["session"],
        "trading_day": facts["trading_day"],
        "clock": sp._clock(td),
        "index": facts.get("index") or [],
        "regime": facts["regime"],
        **sp._market_digest(facts),
        "wide_breadth": facts.get("wide_breadth"),
        "sectors": facts.get("sectors"),
        "macro": facts.get("macro") or {"moves": [], "headlines": []},
        "stories": [{k: s[k] for k in ("id", "syms", "tag", "title", "publisher", "age_min")}
                    for s in facts.get("stories") or []],
        "today": facts.get("today"),
        "calendar": facts.get("calendar") or [],
        "partial": facts.get("partial") or [],
    }


def story_ids(facts: dict[str, Any]) -> list[str]:
    return ([str(h["id"]) for h in (facts.get("macro") or {}).get("headlines") or []]
            + [str(s["id"]) for s in facts.get("stories") or []])


# --------------------------------------------------------------------------
# What comes back.
# --------------------------------------------------------------------------


def _unwrap(obj: dict[str, Any]) -> dict[str, Any]:
    """The overview out of a one-key wrapper (stockplan._unwrap's drift). Pure."""
    if "headline" in obj or "read" in obj:
        return obj
    inner = [v for v in obj.values() if isinstance(v, dict)]
    if len(obj) == 1 and len(inner) == 1 and ("headline" in inner[0] or "read" in inner[0]):
        return inner[0]
    return obj


def sanitize(obj: Any, facts: dict[str, Any]) -> dict[str, Any] | None:
    """The model's overview, held to what it was shown. Pure.

    No headline, no overview. A pick that names a story it was not shown is
    dropped, a story picked twice keeps its first line, and each pick carries the
    story's own title, publisher and link from the facts (never the model's). The
    clock and the release risks are the calendar's (stockplan.clock_lines,
    event_risks), and a model risk that restates a release is dropped."""
    if not isinstance(obj, dict):
        return None
    obj = _unwrap(obj)
    headline = rp._text(obj.get("headline")) or rp._text(obj.get("title"))
    if not headline:
        return None
    pool: dict[str, dict[str, Any]] = {}
    for h in (facts.get("macro") or {}).get("headlines") or []:
        pool[str(h["id"])] = {"title": h.get("title"), "publisher": h.get("publisher"),
                              "syms": [], "tag": h.get("desk"), "url": "",
                              "age_min": h.get("age_min"), "wire": True}
    for s in facts.get("stories") or []:
        pool[str(s["id"])] = {k: s.get(k) for k in ("title", "publisher", "syms", "tag", "url",
                                                    "age_min")} | {"wire": False}
    news: list[dict[str, Any]] = []
    for p in rp._dicts(obj.get("news")):
        i, why = p.get("id"), rp._text(p.get("why"))
        if not isinstance(i, str) or i not in pool or not why or any(n["id"] == i for n in news):
            continue
        news.append({"id": i, "why": why, **pool[i]})
    return {
        "headline": headline,
        "read": rp._text(obj.get("read")),
        "sectors": rp._text(obj.get("sectors")),
        "macro": rp._text(obj.get("macro")),
        "news": news[:NEWS_MAX],
        "focus": rp._text(obj.get("focus")),
        "timing": sp.clock_lines(facts),
        "events": sp.event_risks(facts),
        "risks": [r for r in rp._texts(obj.get("risks"), 6) if not sp._covered(r, facts)][:3],
    }


def prose(b: dict[str, Any]) -> list[str]:
    """Every string the model wrote — what the numerals guard reads. Pure."""
    out = [b.get(k) or "" for k in ("headline", "read", "sectors", "macro", "focus")]
    out += [n.get("why") or "" for n in b.get("news") or []]
    out += list(b.get("risks") or [])
    return [x for x in out if x]


def unverified(b: dict[str, Any], seen: str) -> list[str]:
    """Numerals in the overview that the text the model was shown does not contain."""
    known = rp.known_numerals(seen)
    bad: list[str] = []
    for s in prose(b):
        for k in rp.numerals_in(s):
            if k not in known and k not in bad:
                bad.append(k)
    return bad


# --------------------------------------------------------------------------
# Generation and the 09:00 write.
# --------------------------------------------------------------------------


def generate(scan: dict[str, Any], snap: dict[str, Any], today: dict[str, Any] | None,
             stories: list[dict[str, Any]] | None, model: str | None = None,
             now: datetime | None = None, auto: bool = False) -> dict[str, Any]:
    """Build the facts, ask the model, store and return the overview. `now` is the
    moment it is dated from (the job's, so its id is the job's); `auto` marks the
    09:00 write."""
    key = rp._key()
    now = now or datetime.now(UTC)
    model = model or rp.DEFAULT_MODEL
    base: dict[str, Any] = {
        "ok": False, "kind": KIND, "auto": auto,
        "id": rp.note_id(now),
        "created_utc": now.isoformat(),
        "et_label": now.astimezone(ET).strftime("%a %d %b, %H:%M ET"),
        "model": model, "error": None, "raw": None, "usage": None, "digest": None,
        "unverified": [], "attempts": [], "facts": None, "plan": None,
    }
    if not key:
        base["error"] = ("No OPENROUTER_API_KEY. Add one to .env.local and restart the collector "
                         "— the overview is written by a model and there is deliberately no "
                         "local fallback.")
        return base
    facts = build_facts(scan, snap, today, stories)
    base["facts"] = facts
    if not facts["index"] and not facts["regime"].get("tape"):
        base["error"] = ("The scanner has no index data yet — it reads its list a third at a "
                         "time after a restart; try again in a couple of minutes.")
        return base
    digest = build_digest(facts)
    base["digest"] = digest
    messages = [
        {"role": "system", "content": system_prompt(facts["session"])},
        {"role": "user", "content": (
            f"Market snapshot at {facts['as_of']} (session: {facts['session']}).\n\n"
            f"```json\n{json.dumps(digest, indent=1, default=str)}\n```\n\n"
            f"{sp.tape_line(facts.get('conviction'))}\n\n"
            f"Write the market overview for {facts['trading_day']}.")},
    ]
    return sp.ask_chain(base, messages, schema(story_ids(facts)), "market_overview", SKELETON,
                        key=key, sanitize=lambda obj: sanitize(obj, facts), verify=unverified,
                        store=sp._store)


# --------------------------------------------------------------------------
# The Dashboard's card (owner, 2026-11-13: the In play card was the Scanner's
# pre-market list twice, and this took its place).
# --------------------------------------------------------------------------

#: The last card built, keyed by the stored file's name and when it was written, so a
#: Dashboard poll reads a file only when a new overview has been stored.
_CARD: dict[str, Any] = {"key": None, "card": None}


def card_of(rec: dict[str, Any]) -> dict[str, Any] | None:
    """A stored overview → what the Dashboard's card prints: the headline, what it means
    for the list, and up to three risks (the calendar's first). None for anything else. Pure."""
    b = rec.get("plan")
    if rec.get("kind") != KIND or not rec.get("ok") or not isinstance(b, dict):
        return None
    facts = rec.get("facts") if isinstance(rec.get("facts"), dict) else {}
    return {"id": rec.get("id"), "et_label": rec.get("et_label"),
            "created_utc": rec.get("created_utc"), "auto": bool(rec.get("auto")),
            "trading_day": facts.get("trading_day"), "headline": b.get("headline") or "",
            "focus": b.get("focus") or "",
            "risks": [*(b.get("events") or []), *(b.get("risks") or [])][:3]}


def latest_card() -> dict[str, Any] | None:
    """The newest stored overview's card, or None when none has been written."""
    try:
        names = sorted((n for n in os.listdir(sp.PLANS_DIR) if n.endswith(".json")),
                       reverse=True)
    except OSError:
        return None
    for name in names[:10]:
        path = os.path.join(sp.PLANS_DIR, name)
        try:
            key = f"{name}:{os.path.getmtime(path)}"
        except OSError:
            continue
        if _CARD["key"] == key:
            return _CARD["card"]  # type: ignore[no-any-return]
        rec = sp.load(name[:-5])
        got = card_of(rec) if isinstance(rec, dict) else None
        if got is not None:
            _CARD.update(key=key, card=got)
            return got
    return None


def _created(h: dict[str, Any]) -> datetime | None:
    try:
        t = datetime.fromisoformat(str(h.get("created_utc")))
    except ValueError:
        return None
    return t if t.tzinfo else t.replace(tzinfo=UTC)


def auto_due(now: datetime, history: list[dict[str, Any]], tried: list[datetime]) -> bool:
    """Whether the 09:00 overview should be written now. Pure.

    A trading day, between 09:00 and the bell, with no overview written since
    09:00 (one written at 08:50 by hand is not the 09:00 one), and fewer than
    AUTO_TRIES tries since 09:00, the last at least AUTO_GAP_MIN ago."""
    et = now.astimezone(ET)
    if not is_trading_day(et.date()) or not (AUTO_AT <= et.time() < AUTO_UNTIL):
        return False
    start = datetime.combine(et.date(), AUTO_AT, tzinfo=ET)
    for h in history:
        t = _created(h)
        if h.get("kind") == KIND and t is not None and t >= start:
            return False
    mine = [t for t in tried if t >= start]
    if len(mine) >= AUTO_TRIES:
        return False
    return not (mine and (now - max(mine)).total_seconds() < AUTO_GAP_MIN * 60.0)
