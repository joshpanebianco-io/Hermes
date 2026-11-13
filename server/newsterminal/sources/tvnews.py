"""
Stock news tagged by ticker — TradingView's public news flow.

WHY THIS AND NOT THE WIRE. The wire is ~40 feeds of what the world is doing, and
a story reaches a stock only if a headline happens to name it (scanscore.news_for).
The Scanner's own per-ticker feeds are Yahoo's RSS, one name at a time, so only the
forty names on the list have any. The wide scan needs to know about thousands.

    GET https://news-mediator.tradingview.com/public/news-flow/v2/news
        ?filter=lang:en&filter=market:stock&filter=market_country:US
        &client=screener&streaming=false

answers 200 stories in one request of about 100 KB, each with the tickers it is
about in `relatedSymbols`. PROBED 2026-11-09, a Sunday night: 193 of 200 carried
symbols and the 200 reached back 31 hours (a busy weekday reaches much less, so
it is read every two minutes and the stories are kept). Dow Jones, Reuters,
Benzinga, Seeking Alpha, GlobeNewswire and more on the one request.

THE PER-NAME READ FILLS THE GAPS. `news-headlines.tradingview.com/v2/headlines`
takes one symbol and answers its last 200 stories. A name that broke out before
the flow was first read, or whose story fell off the flow's 200, gets read this
way: only the names at the top of the wide scan, one every few seconds, each at
most every fifteen minutes.

THE STORY SHOWN IS THE MOST IMPORTANT ONE OF THE LAST DAY, NOT THE NEWEST
(catalysts.py has why). A personal read of a public page's data, like the pool:
one request a pass, a browser User-Agent, a 403 or 429 answered with a pause.
"""

from __future__ import annotations

import json
import os
import threading
import time
import urllib.parse
from collections.abc import Callable, Iterable, Sequence
from datetime import UTC, datetime
from typing import Any
from zoneinfo import ZoneInfo

from ..catalysts import MAJOR, NOISE, grade, stated_move, stated_today, story
from ..config import BROWSER_UA, CACHE_DIR
from ..holidays import news_since
from ..http import SourceStatus, fetch, json_body

_ET = ZoneInfo("America/New_York")


def since_close(at: float) -> float:
    """When the news the session at `at` trades on starts (holidays.news_since): the
    previous trading day's close. Every window here reaches back at least that far
    (quant audit, 2026-11-13): counted only in hours from now, Friday's after-close
    news had left every window by Monday's pre-market. Pure."""
    return news_since(datetime.fromtimestamp(at, _ET)).timestamp()

FLOW_URL = ("https://news-mediator.tradingview.com/public/news-flow/v2/news"
            "?filter=lang:en&filter=market:stock&filter=market_country:US"
            "&client=screener&streaming=false")
SYM_URL = "https://news-headlines.tradingview.com/v2/headlines?client=web&lang=en&symbol={sym}"
STORY_BASE = "https://www.tradingview.com"
HEADERS = {
    "Accept": "application/json",
    "Origin": "https://www.tradingview.com",
    "Referer": "https://www.tradingview.com/",
}
STATE_FILE = os.path.join(CACHE_DIR, "tv_news.json")
US_EXCHANGES = frozenset({"NASDAQ", "NYSE", "AMEX", "NYSE ARCA", "NYSEARCA", "BATS"})

FLOW_SEC = 120.0
FLOW_IDLE_SEC = 900.0
SYM_TICK_SEC = 3.0
SYM_TTL_SEC = 900.0
PAUSE_SEC = 600.0
#: How long a story is kept (a long weekend and a day), and how far back the
#: catalyst looks from the session on the page.
KEEP_HOURS = 120.0
CATALYST_HOURS = 30.0
#: A major story this young puts a name ahead (the tables) and earns the pool's points.
FRESH_HOURS = 18.0
#: A story about more names than this is a round-up, not that name's news.
MAX_RELATED = 3
#: Every so often, not on every read: the file is a few hundred KB.
SAVE_SEC = 300.0


def _when(v: Any) -> float | None:
    return float(v) if isinstance(v, int | float) and v > 0 else None


def tickers_of(item: dict[str, Any]) -> list[str]:
    """The US tickers a story is about, "NASDAQ:AAPL" → "AAPL". Pure."""
    out: list[str] = []
    for s in item.get("relatedSymbols") or []:
        raw = s.get("symbol") if isinstance(s, dict) else None
        if not isinstance(raw, str) or ":" not in raw:
            continue
        ex, sym = raw.split(":", 1)
        if ex.upper() in US_EXCHANGES and sym:
            out.append(sym.upper())
    return out


def _provider(item: dict[str, Any]) -> str:
    p = item.get("provider")
    if isinstance(p, dict):
        return str(p.get("name") or p.get("id") or "")
    return str(item.get("source") or p or "")


def story_of(item: dict[str, Any], want: str | None = None) -> dict[str, Any] | None:
    """A reply's item → the story kept. Pure. `want` names the ticker of a per-name read,
    whose items do not always list it; noise and undated items are dropped here."""
    title = str(item.get("title") or "").strip()
    at = _when(item.get("published"))
    if not title or at is None:
        return None
    g = grade(title)
    if g.tier == NOISE:
        return None
    syms = tickers_of(item)
    if want and want not in syms:
        syms = [want, *syms]
    if not syms:
        return None
    path = item.get("storyPath")
    url = (STORY_BASE + path if isinstance(path, str) and path.startswith("/")
           else str(item.get("link") or ""))
    return {"id": str(item.get("id") or f"{at}-{title[:40]}"), "title": title, "url": url,
            "provider": _provider(item), "at": at, "syms": syms, "tag": g.tag, "tier": g.tier}


def parse(doc: Any, want: str | None = None) -> list[dict[str, Any]]:
    """A reply → its stories. Pure."""
    items = doc.get("items") if isinstance(doc, dict) else None
    if not isinstance(items, list):
        return []
    return [s for s in (story_of(i, want) for i in items if isinstance(i, dict)) if s]


def best(stories: Iterable[dict[str, Any]], sym: str, now: float,
         hours: float = CATALYST_HOURS, names: Sequence[str] = (),
         strict: bool = True,
         move: Callable[[], float | None] | None = None) -> dict[str, Any] | None:
    """The most important story about `sym` in the window: tier, then newest, or None
    when nothing held is one. It has to BE this name's story (catalysts.story; `names`
    are what a headline calls the company): its lead names the company and it describes
    an event. A story tagged with this ticker alone used to be taken on trust, so a
    market wrap the wire tagged CRWV led CoreWeave's row over its own earnings jump, and
    Mobileye's conference notice led Intel's as a major Earnings story (audit,
    2026-11-11). A name the table has no words for is still left to the feed's tag, and
    so is a headline that does not name a company whose words are only a guess (`strict`
    is False; catalysts.story). The story comes back with the grade it has AS this
    name's (a list that is the name's own move is a Move). The window reaches back
    `hours`, or to the previous session's close where that is further (`since_close`).
    A story that states a move the name has not made since the previous close is an
    earlier day's and is passed over (catalysts.STATED_MIN): `move` gives the name's
    move (%), asked only when a story states one. Pure."""
    cut = min(now - hours * 3600.0, since_close(now))
    mine: list[tuple[int, float, dict[str, Any]]] = []
    moved: list[float | None] = []
    for s in stories:
        if s["at"] < cut or sym not in s["syms"] or len(s["syms"]) > MAX_RELATED:
            continue
        g = story(s["title"], sym, names, str(s.get("provider") or ""), strict)
        if g is None:
            continue
        said = stated_move(s["title"], sym, names) if move is not None else None
        if said is not None:
            if not moved:
                moved.append(move() if move is not None else None)
            if not stated_today(said, moved[0]):
                continue
        mine.append((g.tier, -s["at"], {**s, "tag": g.tag, "tier": g.tier}))
    return min(mine, key=lambda x: x[:2])[2] if mine else None


class NewsStore:
    """The stories held. Written on the wide thread; read from the API's."""

    def __init__(self, path: str = STATE_FILE) -> None:
        self._lock = threading.Lock()
        self.path = path
        self.stories: dict[str, dict[str, Any]] = {}
        self.by_sym: dict[str, list[dict[str, Any]]] = {}
        self.last_flow = 0.0
        self.pause_until = 0.0
        self.sym_read: dict[str, float] = {}
        self.queue: list[str] = []
        self._saved = 0.0
        #: What a headline calls each company, set by the collector: the store knows
        #: tickers only, and the lead test (catalysts.about) needs the name.
        self.names: Callable[[str], Sequence[str]] | None = None
        #: Whether those names are the table's, and so can be held to (catalysts.story's
        #: `strict`); a filer's first word is a guess. Set by the collector; unset, they
        #: are taken as given.
        self.sure: Callable[[str], bool] | None = None
        #: A name's move since the previous close (%), set by the collector, for the
        #: stories that state one (`best`). Unset, no story is held to its number.
        self.move: Callable[[str], float | None] | None = None
        self._load()

    # ---- persistence --------------------------------------------------------

    def _load(self) -> None:
        try:
            with open(self.path, encoding="utf-8") as f:
                d = json.load(f)
        except (OSError, ValueError):
            return
        if isinstance(d, dict):
            for s in d.get("stories") or []:
                if isinstance(s, dict) and s.get("id") and s.get("at"):
                    # Graded again on the way in: a story keeps the grade it was filed
                    # with, and a change to the grader (2026-11-11) would otherwise
                    # reach the tables only as the old stories aged out, days later.
                    g = grade(str(s.get("title") or ""))
                    if g.tier == NOISE:
                        continue
                    s["tag"], s["tier"] = g.tag, g.tier
                    self.stories[str(s["id"])] = s
            self._reindex(time.time())

    def _save(self, now: float) -> None:
        if now - self._saved < SAVE_SEC:
            return
        self._saved = now
        with self._lock:
            rows = list(self.stories.values())
        tmp = self.path + ".tmp"
        try:
            os.makedirs(os.path.dirname(self.path), exist_ok=True)
            with open(tmp, "w", encoding="utf-8") as f:
                json.dump({"saved_utc": datetime.now(UTC).isoformat(), "stories": rows}, f)
            os.replace(tmp, self.path)
        except OSError:
            pass

    def _reindex(self, now: float) -> None:
        """Old stories go; the per-ticker index is rebuilt from what is left."""
        cut = now - KEEP_HOURS * 3600.0
        with self._lock:
            self.stories = {k: s for k, s in self.stories.items() if s["at"] >= cut}
            idx: dict[str, list[dict[str, Any]]] = {}
            for s in self.stories.values():
                for sym in s["syms"]:
                    idx.setdefault(sym, []).append(s)
            self.by_sym = idx

    def _add(self, rows: list[dict[str, Any]], now: float) -> None:
        with self._lock:
            for s in rows:
                self.stories[s["id"]] = s
        self._reindex(now)

    # ---- the reads ----------------------------------------------------------

    def want(self, symbols: Iterable[str]) -> None:
        """The names worth a per-name read, best first (the top of the wide scan)."""
        self.queue = list(symbols)

    def tick_flow(self, session_on: bool, now: float | None = None) -> tuple[SourceStatus, bool]:
        """One read of the market-wide flow, when due. (status, whether it read)"""
        t = now if now is not None else time.time()
        st = SourceStatus("Stock news")
        due = t - self.last_flow >= (FLOW_SEC if session_on else FLOW_IDLE_SEC)
        if not due or t < self.pause_until:
            st.items = len(self.stories)
            st.settle(bool(self.stories), "read")
            return st, False
        self.last_flow = t
        r = st.absorb(fetch(FLOW_URL, key="tv_news_flow", ttl_sec=0.0, timeout=20, ua=BROWSER_UA,
                            headers=HEADERS, stale_max_sec=3600.0, validate=json_body))
        if r.status in (403, 429):
            self.pause_until = t + PAUSE_SEC
        fresh = 0
        if r.ok:
            try:
                rows = parse(r.json())
            except (ValueError, TypeError):
                rows = []
            fresh = len([s for s in rows if s["id"] not in self.stories])
            if rows:
                self._add(rows, t)
        else:
            st.error = r.error
        st.items = len(self.stories)
        st.notes = [f"{fresh} new stories" if r.ok else "read failed"]
        st.settle(bool(self.stories), "read")
        self._save(t)
        return st, True

    def tick_symbol(self, exchange_of: dict[str, str], now: float | None = None) -> bool:
        """At most one per-name read: the first queued name not read lately."""
        t = now if now is not None else time.time()
        if t < self.pause_until:
            return False
        sym = next((s for s in self.queue
                    if t - self.sym_read.get(s, 0.0) >= SYM_TTL_SEC and s in exchange_of), None)
        if sym is None:
            return False
        self.sym_read[sym] = t
        full = urllib.parse.quote(f"{exchange_of[sym]}:{sym}", safe="")
        r = fetch(SYM_URL.format(sym=full), key=f"tv_news_{sym}", ttl_sec=0.0, timeout=15,
                  ua=BROWSER_UA, headers=HEADERS, stale_ok=False, store=False, validate=json_body)
        if r.status in (403, 429):
            self.pause_until = t + PAUSE_SEC
        if r.ok:
            try:
                rows = parse(r.json(), want=sym)
            except (ValueError, TypeError):
                rows = []
            cut = t - KEEP_HOURS * 3600.0
            rows = [s for s in rows if s["at"] >= cut]
            if rows:
                self._add(rows, t)
                self._save(t)
        return True

    # ---- what the tables read -----------------------------------------------

    def _called(self, sym: str) -> Sequence[str]:
        return self.names(sym) if self.names else ()

    def _strict(self, sym: str) -> bool:
        return self.sure(sym) if self.sure else True

    def _whose(self, s: dict[str, Any]) -> bool:
        """Is this a story of any name it is tagged with (catalysts.story)? The feeds
        for every name ask it, so a wrap tagged with one ticker is nobody's news."""
        return any(story(s["title"], sym, self._called(sym), str(s.get("provider") or ""),
                         self._strict(sym)) is not None for sym in s["syms"])

    def catalyst(self, sym: str, now: float | None = None,
                 ref: float | None = None) -> dict[str, Any] | None:
        """The name's most important story of the last day, for a row.

        `ref` is the moment "the last day" is counted back from: now in a session, the
        end of the last session when none is on. A page opened on Sunday night shows
        Friday, and Friday's report is what moved it, however many hours ago that is.
        """
        t = now if now is not None else time.time()
        anchor = ref if ref is not None else t
        with self._lock:
            stories = list(self.by_sym.get(sym) or [])
        mover = self.move
        s = best(stories, sym, anchor, names=self._called(sym), strict=self._strict(sym),
                 move=(lambda: mover(sym)) if mover is not None else None)
        if s is None:
            return None
        # Fresh: FRESH_HOURS old at most, or since the previous session's close, so
        # Monday's pre-market still counts Friday evening's report.
        fresh = anchor - s["at"] <= FRESH_HOURS * 3600.0 or s["at"] >= since_close(anchor)
        return {"title": s["title"], "url": s["url"], "provider": s["provider"], "tag": s["tag"],
                "tier": s["tier"], "age_min": round((t - s["at"]) / 60.0, 1),
                "major": s["tier"] == MAJOR and fresh}

    def major(self, sym: str, now: float | None = None) -> str | None:
        """The tag of a fresh major story about the name, or None — the pool's question."""
        c = self.catalyst(sym, now)
        return str(c["tag"]) if c and c.get("major") else None

    def headlines(self, sym: str, now: float | None = None,
                  limit: int = 40) -> list[dict[str, Any]]:
        """The name's stories, newest first, in the scanner's own headline shape: the
        ones that are its stories (catalysts.story), not everything tagged with it."""
        t = now if now is not None else time.time()
        names = self._called(sym)
        with self._lock:
            stories = [s for s in (self.by_sym.get(sym) or []) if len(s["syms"]) <= MAX_RELATED]
        strict = self._strict(sym)
        stories = [s for s in stories if story(s["title"], sym, names,
                                               str(s.get("provider") or ""), strict) is not None]
        stories.sort(key=lambda s: -s["at"])
        return [{"title": s["title"], "url": s["url"], "publisher": s["provider"], "ts": s["at"],
                 "utc": datetime.fromtimestamp(s["at"], UTC).isoformat(),
                 "age_min": round((t - s["at"]) / 60.0, 1)}
                for s in stories[:limit]]

    def top(self, limit: int = 30, now: float | None = None,
            keep: Callable[[str], bool] | None = None) -> list[dict[str, Any]]:
        """The freshest major stories, whole, for the Dashboard's feed. One event once: a
        bankruptcy filing came in five times from five wires, and that was the whole
        card (2026-11-09). The newest of each name and kind stands for the rest.

        `keep` says which names the reader could act on: a story stays when it is about
        one of them. The flow is every US listing, and without it the card was a
        micro-cap newswire ("Onfolio Holdings Sets Third Quarter 2026 Earnings Call
        …", "EDRY: Revenue and adjusted EBITDA surged …") on a desk that trades names
        at two billion and over (2026-11-11). None keeps them all."""
        t = now if now is not None else time.time()
        cut = min(t - CATALYST_HOURS * 3600.0, since_close(t))
        with self._lock:
            rows = [s for s in self.stories.values() if s["tier"] == MAJOR
                    and s["at"] >= cut
                    and len(s["syms"]) <= MAX_RELATED]
        rows.sort(key=lambda s: -s["at"])
        seen: set[tuple[tuple[str, ...], str]] = set()
        out: list[dict[str, Any]] = []
        for s in rows:
            key = (tuple(s["syms"]), s["tag"])
            if key in seen:
                continue
            # A story of a name the reader could act on: both asked of the SAME name. A
            # wrap tagged with an index and with CoreWeave ("Nasdaq Futures Rally as AI
            # Optimism Returns", IXIC and CRWV) is not CoreWeave's story, and the index,
            # which has no name to be held to, is nothing to act on.
            provider = str(s.get("provider") or "")
            if not any((keep is None or keep(sym))
                       and story(s["title"], sym, self._called(sym), provider,
                                 self._strict(sym)) is not None for sym in s["syms"]):
                continue
            seen.add(key)
            out.append({"syms": s["syms"], "tag": s["tag"], "title": s["title"], "url": s["url"],
                        "provider": s["provider"], "age_min": round((t - s["at"]) / 60.0, 1)})
            if len(out) == limit:
                break
        return out

    def panel(self, syms: Iterable[str] | None = None, limit: int = 40,
              now: float | None = None) -> list[str]:
        """The freshest major stories, one line each, for Hermes."""
        t = now if now is not None else time.time()
        keep = set(syms) if syms is not None else None
        cut = min(t - CATALYST_HOURS * 3600.0, since_close(t))
        with self._lock:
            rows = [s for s in self.stories.values() if s["tier"] == MAJOR
                    and s["at"] >= cut
                    and len(s["syms"]) <= MAX_RELATED
                    and (keep is None or keep & set(s["syms"]))]
        rows.sort(key=lambda s: -s["at"])
        rows = [s for s in rows if self._whose(s)]
        return [f"{','.join(s['syms'])} [{s['tag']}] {s['title']} "
                f"({s['provider']}, {round((t - s['at']) / 3600.0, 1)}h ago)" for s in rows[:limit]]
