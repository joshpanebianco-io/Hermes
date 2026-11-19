"""
High impact news — the Dashboard card of what can move the whole market today.

WHY (owner, 2026-11-19, ~10:45 ET): "lets replace the live signals card on dashboard with a High
Impact News card or something named similar, tha tlists things like important headlines,
geopolitcs, IPO's earnigns ofr the day etc". The mock (the real page at 2560 with this card in
the middle of row two) was approved as shown: "the dashboard mock is good".

TWO PARTS, NO MODEL. Every line is the collector's own data: the wire's impact grade and desk
(sources/wire.py), the calendar's score, figures and hot/cold read (sources/calendar.py,
releases.read_of), the earnings rows.

TODAY, in time order (`today_rows`):
  * the day's US prints that matter (calendar score 4+, or a core release at 3+), with the
    figure against what was expected and the calendar's read once out, "due" before;
  * the Fed's voices and decisions ("Fed's Barr speaks", "spoke" once its time has passed);
  * the big reports (a bellwether, or $50bn+): before the open with beat / missed / met
    against the forecast, after the close by name until their figures come in;
  * an IPO the headlines are full of (IPO_MIN stories in a day), with the newest headline;
  * a big foreign print (score 4+ and core), one a country and time, named by its family
    ("CPI, the headline and core") when a release comes as many rows.
HEADLINES (`headlines`): the wire's high-impact stories of the last HIGH_HOURS, then its medium
geopolitics, energy and policy of the last MEDIUM_HOURS, one a story, an IPO's own stories left
to its row; HEAD_MAX, newest first.
"""

from __future__ import annotations

import re
from collections.abc import Iterable
from datetime import datetime
from typing import Any

from .scan import ET

#: The headlines' reach and size.
HIGH_HOURS = 12.0
MEDIUM_HOURS = 6.0
MEDIUM_DESKS = ("geo", "energy", "policy")
HEAD_MAX = 8
#: A US print that matters, and a foreign one.
US_SCORE, US_CORE_SCORE = 4, 3
FOREIGN_SCORE = 4
#: A report big enough for the card.
REPORT_CAP = 50e9
#: An IPO the headlines are full of: this many stories in IPO_HOURS.
IPO_MIN = 3
IPO_HOURS = 24.0
IPO_ROWS = 2

DESK = {"geo": "Geopolitics", "energy": "Energy", "policy": "Policy", "macro": "Macro",
        "markets": "Markets", "corp": "Companies"}
COUNTRY = {"United States": "US", "United Kingdom": "UK", "Euro Zone": "Euro area",
           "New Zealand": "NZ", "South Korea": "Korea", "Hong Kong": "Hong Kong"}
#: A release that arrives as many rows (headline, core, m/m, y/y) is named by its family.
FAMILIES = ("CPI", "PPI", "PCE", "GDP", "PMI", "Retail Sales", "Unemployment", "Employment",
            "Rate Decision", "Trade Balance", "Industrial Production")

_FED = re.compile(r"\bFOMC\b|\bFed\b|\bPowell\b", re.I)
_IPO = re.compile(r"\bI\.?P\.?O\.?s?\b")
#: The company before "IPO" in a headline: "Anthropic IPO", "Anthropic's Record-Breaking IPO",
#: "Anthropic’s Blockbuster I.P.O.".
#: Case matters for the name (a capital starts each word), not for the words between.
_IPO_CO = re.compile(r"([A-Z][\w.&-]+(?:\s[A-Z][\w.&-]+)?)(?:'s|’s)?\s+"
                     r"(?i:(?:record[- ]breaking|record|blockbuster|biggest|big|mega)\s+)*"
                     r"I\.?P\.?O")
#: Words that sit before "IPO" and are not a company.
_NOT_CO = {"the", "an", "a", "its", "this", "record", "biggest", "big", "blockbuster", "mega",
           "retail", "us", "u.s.", "new", "first", "after", "before", "ahead", "since", "s",
           "investors", "traders", "upcoming", "planned", "hot", "next"}


def _num(v: Any) -> float | None:
    return float(v) if isinstance(v, int | float) and not isinstance(v, bool) else None


def _money(v: Any) -> float | None:
    """An EPS as the earnings rows carry it ("$2.68", "($0.05)", "-0.05"), or None. Pure."""
    if isinstance(v, int | float) and not isinstance(v, bool):
        return float(v)
    if not isinstance(v, str) or not v.strip():
        return None
    s = v.strip().replace(",", "")
    neg = s.startswith("(") and s.endswith(")")
    s = s.strip("()").replace("$", "")
    try:
        x = float(s)
    except ValueError:
        return None
    return -x if neg else x


def _figure(c: dict[str, Any], key: str) -> str | None:
    raw = c.get(f"{key}_raw")
    if isinstance(raw, str) and raw.strip():
        return raw.strip()
    v = _num(c.get(key))
    if v is None:
        return None
    return f"{v / 1000:.0f}K" if abs(v) >= 10_000 else f"{v:g}"


def _print_line(c: dict[str, Any]) -> tuple[str, bool]:
    """One release's words and whether it is out. Pure."""
    name = str(c.get("event") or "")
    if c.get("released") and c.get("actual") is not None:
        a, e = _figure(c, "actual"), _figure(c, "consensus")
        line = f"{name}: {a}" + (f" against {e} expected" if e else "")
        if c.get("read"):
            line += f" · reads {c['read']}"
        return line, True
    return f"{name} · due", False


def _fed_line(c: dict[str, Any], now_hm: str) -> tuple[str, bool]:
    """A Fed row: a speaker by name ("Fed's Barr speaks"), a decision as a print. Pure."""
    name = str(c.get("event") or "")
    m = re.match(r"(?:FOMC|Fed)\s+(Member|Chair|Vice Chair|Governor|President)\s+(.+?)\s+Speaks?\b",
                 name, re.I)
    if not m:
        return _print_line(c)
    role, who = m.group(1), m.group(2)
    past = str(c.get("et") or "99:99") <= now_hm
    head = f"Fed Chair {who}" if role.lower() == "chair" else f"Fed's {who}"
    return f"{head} {'spoke' if past else 'speaks'}", past


def _family(names: list[str]) -> str:
    """Many rows of one release, named once: "CPI, the headline and core". Pure."""
    for fam in FAMILIES:
        if all(fam.lower() in n.lower() for n in names):
            core = any(re.search(r"\bcore\b|\bex[- ]", n, re.I) for n in names)
            return f"{fam}, the headline and core" if core and len(names) > 1 else fam
    first = names[0]
    return first if len(names) == 1 else f"{first} and {len(names) - 1} more"


def _reports(earnings: Iterable[dict[str, Any]], day: str) -> list[dict[str, Any]]:
    """The day's big reports as Today rows: before the open, then after the close. Pure."""
    big = [e for e in earnings if e.get("date") == day and e.get("symbol")
           and (e.get("bellwether") or (_num(e.get("market_cap")) or 0.0) >= REPORT_CAP)]
    big.sort(key=lambda e: -(_num(e.get("market_cap")) or 0.0))

    def said(e: dict[str, Any]) -> tuple[str, bool]:
        a, f = _money(e.get("eps_actual")), _money(e.get("eps_forecast"))
        if a is None:
            return str(e["symbol"]), False
        if f is None:
            return f"{e['symbol']} reported ({e.get('eps_actual')})", True
        word = "beat" if a > f else "missed" if a < f else "met"
        return f"{e['symbol']} {word} ({e.get('eps_actual')} vs {e.get('eps_forecast')})", True

    out: list[dict[str, Any]] = []
    pre = [said(e) for e in big if e.get("when") == "pre"]
    if pre:
        words = [w if done else f"{w} (no figure yet)" for w, done in pre]
        out.append({"t": "Before", "sort": "09:29", "kind": "Earnings",
                    "line": " · ".join(words), "done": any(d for _, d in pre)})
    post = [(said(e), e.get("when")) for e in big if e.get("when") != "pre"]
    if post:
        done = [w for (w, d), _ in post if d]
        due = [w + (" (time not set)" if when != "after" else "") for (w, d), when in post if not d]
        parts = done + ([", ".join(due) + " report after the close"] if due else [])
        out.append({"t": "After", "sort": "16:00", "kind": "Earnings",
                    "line": " · ".join(parts), "done": bool(done)})
    return out


def _ipo_company(title: str) -> str | None:
    m = _IPO_CO.search(title)
    if not m:
        return None
    words = [w for w in m.group(1).split() if w.lower().strip(".") not in _NOT_CO]
    return " ".join(words) or None


def ipo_rows(wire: Iterable[dict[str, Any]], now_ts: float
             ) -> tuple[list[dict[str, Any]], set[str]]:
    """(the IPOs the headlines are full of as Today rows, the titles they cover). An IPO row
    is a company named before "IPO" in IPO_MIN or more stories of the last IPO_HOURS, with
    the newest of them; IPO_ROWS at most, the most written about first. Pure."""
    recent = [w for w in wire if (ts := _num(w.get("ts"))) is not None
              and now_ts - ts <= IPO_HOURS * 3600 and _IPO.search(str(w.get("title") or ""))]
    # The companies named right before "IPO" somewhere, then every IPO story naming each
    # anywhere ("Traders bet on big IPO pop for Anthropic" is Anthropic's too).
    names = {co for w in recent if (co := _ipo_company(str(w["title"])))}
    by = {n: [w for w in recent if n.lower() in str(w["title"]).lower()] for n in names}
    rows: list[dict[str, Any]] = []
    covered: set[str] = set()
    for _name, ws in sorted(by.items(), key=lambda kv: -len(kv[1])):
        if len(rows) >= IPO_ROWS or len(ws) < IPO_MIN:
            break
        if any(str(w["title"]) in covered for w in ws[:1]):
            continue
        ws = sorted(ws, key=lambda w: -float(w["ts"]))
        rows.append({"t": "Today", "sort": "09:30", "kind": "IPO",
                     "line": f"{ws[0]['title']} · {len(ws)} IPO stories in the last day",
                     "done": True, "url": ws[0].get("url")})
        covered |= {str(w["title"]) for w in ws}
    return rows, covered


def today_rows(calendar: Iterable[dict[str, Any]], earnings: Iterable[dict[str, Any]],
               wire: Iterable[dict[str, Any]], now: datetime
               ) -> tuple[list[dict[str, Any]], set[str]]:
    """The day's scheduled movers in time order (module docstring), and the IPO headlines
    they cover. Pure."""
    et = now.astimezone(ET)
    day, now_hm = et.date().isoformat(), et.strftime("%H:%M")
    cal = [c for c in calendar if c.get("date") == day and c.get("event")]
    rows: list[dict[str, Any]] = []
    for c in cal:
        if c.get("region") != "us":
            continue
        score = int(c.get("score") or 0)
        if not (score >= US_SCORE or (c.get("core") and score >= US_CORE_SCORE)):
            continue
        fed = bool(_FED.search(str(c["event"])))
        line, done = _fed_line(c, now_hm) if fed else _print_line(c)
        rows.append({"t": c.get("et") or "", "sort": c.get("et") or "", "kind":
                     "Fed" if fed else "US data", "line": line, "done": done})
    groups: dict[tuple[str, str], list[dict[str, Any]]] = {}
    for c in cal:
        if c.get("region") == "us" or not c.get("core") or int(c.get("score") or 0) < FOREIGN_SCORE:
            continue
        groups.setdefault((str(c.get("et") or ""), str(c.get("country") or "")), []).append(c)
    for (t, country), cs in groups.items():
        if len(cs) == 1:
            line, done = _print_line(cs[0])
        else:
            line, done = _family([str(c["event"]) for c in cs]), all(c.get("released") for c in cs)
        rows.append({"t": t, "sort": t, "kind": COUNTRY.get(country, country) or "Abroad",
                     "line": line, "done": done})
    rows += _reports(earnings, day)
    wire = list(wire)
    ipos, covered = ipo_rows(wire, now.timestamp())
    rows += ipos
    rows.sort(key=lambda r: r["sort"])
    return [{k: v for k, v in r.items() if k != "sort"} for r in rows], covered


def _story(title: str) -> str:
    return " ".join(re.sub(r"[^a-z0-9 ]", " ", title.lower()).split()[:5])


def headlines(wire: Iterable[dict[str, Any]], now_ts: float, skip: Iterable[str] = (),
              limit: int = HEAD_MAX) -> list[dict[str, Any]]:
    """The wire's high-impact stories of the last HIGH_HOURS, then its medium geopolitics,
    energy and policy of the last MEDIUM_HOURS; one a story (its first five words), none of
    `skip` (titles a Today row covers); `limit`, newest first. Pure."""
    ws = [w for w in wire if _num(w.get("ts")) is not None and w.get("title")]
    high = sorted((w for w in ws if w.get("impact") == "high"
                   and now_ts - float(w["ts"]) <= HIGH_HOURS * 3600), key=lambda w: -float(w["ts"]))
    medium = sorted((w for w in ws if w.get("impact") == "medium"
                     and w.get("category") in MEDIUM_DESKS
                     and now_ts - float(w["ts"]) <= MEDIUM_HOURS * 3600),
                    key=lambda w: -float(w["ts"]))
    gone, keys, picked = set(skip), set(), []
    for w in [*high, *medium]:
        k = _story(str(w["title"]))
        if str(w["title"]) in gone or k in keys:
            continue
        keys.add(k)
        picked.append(w)
        if len(picked) >= limit:
            break
    picked.sort(key=lambda w: -float(w["ts"]))
    return [{"t": datetime.fromtimestamp(float(w["ts"]), ET).strftime("%H:%M"),
             "kind": DESK.get(str(w.get("category")), str(w.get("category") or "News")),
             "high": w.get("impact") == "high", "title": w["title"], "url": w.get("url"),
             "publisher": w.get("publisher"),
             "age_min": max(0, round((now_ts - float(w["ts"])) / 60))} for w in picked]


def build(wire: Iterable[dict[str, Any]], calendar: Iterable[dict[str, Any]],
          earnings: Iterable[dict[str, Any]], now: datetime, live: bool = True) -> dict[str, Any]:
    """The card: {today, heads, live}. `live` is whether the wire is reading. Pure."""
    wire = list(wire)
    today, covered = today_rows(calendar, earnings, wire, now)
    return {"today": today, "heads": headlines(wire, now.timestamp(), skip=covered),
            "live": live}
