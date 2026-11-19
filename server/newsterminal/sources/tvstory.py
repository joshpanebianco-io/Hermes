"""
A news story's own text, from TradingView's story page data — what the model reads
beside the headline (newsread.py).

WHY (owner, 2026-11-18: "so what is the ai reading? just the headline or the content
too?" → "do what you recommend to make our scanner more accurate"). The model was shown
a headline and, for about one story in eight, a feed's cut-off sentence. A beat with the
guidance cut in the fourth paragraph read as a beat.

    GET https://news-headlines.tradingview.com/v2/story?id=<story id>&lang=en

answers the story's body as a small tree of paragraphs (`astDescription`) with a
`shortDescription`. PROBED 2026-11-18 at 03:00 ET, one story a provider: Reuters gave its
first paragraphs (about 1,000 characters) although the feed marks it paywalled; PR
Newswire, BusinessWire and GlobeNewswire the whole release; dpa-AFX, Quartr and
TradingView's own write-ups a body; Dow Jones NOTHING (its flashes are the headline);
Seeking Alpha only its disclaimer, dropped here.

ONLY THE STORIES THE MODEL IS ABOUT TO READ, ONE AT A TIME. A few a request, the
model's clock is five minutes apart (newsread.GAP_SEC), each story read once and kept a
week. A browser User-Agent, nothing of the owner's, a 403 or 429 answered with a pause.
"""

from __future__ import annotations

import json
import os
import re
import threading
import time
import urllib.parse
from typing import Any

from ..config import BROWSER_UA, CACHE_DIR
from ..http import fetch, json_body
from .tvnews import HEADERS

STORY_URL = "https://news-headlines.tradingview.com/v2/story?{q}"
STATE_FILE = os.path.join(CACHE_DIR, "story_text.json")
#: What the model is shown of a story: the lead paragraphs, where the news is.
BODY_MAX = 1200
#: Shorter than this is not a body (a dateline, a disclaimer's stub).
BODY_MIN = 80
KEEP_SEC = 7 * 86400.0
PAUSE_SEC = 600.0
#: At most this many stories read in one call (the model reads 8 a request).
PER_CALL = 10

#: A TradingView story page: https://www.tradingview.com/news/<id>-<slug>/. Ids are
#: "provider:hash:0", "DJN_DN20261111003179:0", "urn:summary_document_report:quartr.com:
#: 4002724:0"; Reuters' are "tag:reuters.com,2026:newsml_…:0", the page dropping "tag:".
_URL_ID = re.compile(r"tradingview\.com/news/(.+?:\d+)(?=[-/]|$)", re.I)
_SPACE = re.compile(r"[ \t\xa0]+")
_LINES = re.compile(r"\n\s*\n+")
#: A provider's boilerplate, which is not the story.
_BOILER = re.compile(
    r"^(?:content provided by seeking alpha|this (?:article|content) (?:was|is) "
    r"(?:generated|provided)|copyright|\(c\)|©|for more news|see more on)", re.I)


def id_from_url(url: str | None) -> str | None:
    """A TradingView story's id from its page's address, or None. The stories held know
    their own ids (tvnews NewsStore.ids_by_url); this is for one that is not held. Pure."""
    m = _URL_ID.search(url or "")
    if not m:
        return None
    sid = m.group(1)
    return f"tag:{sid}" if sid.lower().startswith("reuters.com,") else sid


def flatten(node: Any) -> str:
    """TradingView's paragraph tree → plain text, a line a paragraph. Pure."""
    if isinstance(node, str):
        return node
    if isinstance(node, list):
        return "".join(flatten(k) for k in node)
    if isinstance(node, dict):
        kids = node.get("children")
        text = flatten(kids) if kids is not None else ""
        if node.get("type") in ("p", "li", "h1", "h2", "h3", "h4", "tr", "blockquote"):
            return text + "\n\n"
        if node.get("type") in ("td", "th"):
            return text + " "
        return text
    return ""


def body_of(doc: Any, limit: int = BODY_MAX) -> str:
    """A story reply → its text for the model: the body's paragraphs (else the short
    description), boilerplate lines dropped, cut at `limit` on a word. "" when there is
    nothing worth showing. Pure."""
    if not isinstance(doc, dict):
        return ""
    raw = flatten(doc.get("astDescription")) or str(doc.get("shortDescription") or "")
    paras = []
    for p in _LINES.split(raw.replace("\r", "")):
        p = _SPACE.sub(" ", p.replace("\n", " ")).strip()
        if p and not _BOILER.search(p):
            paras.append(p)
    text = "\n".join(paras).strip()
    if len(text) < BODY_MIN:
        return ""
    if len(text) > limit:
        text = text[:limit].rsplit(" ", 1)[0] + " …"
    return text


class StoryText:
    """Story bodies by TradingView id, read on demand and kept a week on disk."""

    def __init__(self, path: str = STATE_FILE) -> None:
        self.path = path
        self._lock = threading.Lock()
        #: {id: {"text": str, "at": epoch}}; "" for a story read and found empty.
        self.texts: dict[str, dict[str, Any]] = {}
        self.pause_until = 0.0
        self._load()

    def _load(self) -> None:
        try:
            with open(self.path, encoding="utf-8") as f:
                d = json.load(f)
        except (OSError, ValueError):
            return
        now = time.time()
        for k, v in (d.items() if isinstance(d, dict) else []):
            if (isinstance(v, dict) and isinstance(v.get("text"), str)
                    and isinstance(v.get("at"), (int, float)) and now - v["at"] < KEEP_SEC):
                self.texts[str(k)] = v

    def _save(self) -> None:
        with self._lock:
            body = dict(self.texts)
        tmp = self.path + ".tmp"
        try:
            os.makedirs(os.path.dirname(self.path), exist_ok=True)
            with open(tmp, "w", encoding="utf-8") as f:
                json.dump(body, f)
            os.replace(tmp, self.path)
        except OSError:
            pass

    def get(self, sid: str | None) -> str | None:
        """The story's text as held: a string ("" when it had none), None if not read."""
        if not sid:
            return None
        with self._lock:
            v = self.texts.get(sid)
        return v["text"] if v is not None else None

    def read(self, ids: list[str], now: float | None = None) -> int:
        """Read the stories not held yet, PER_CALL at most; how many were read. Never
        raises: a story that fails is left unread and tried on a later call."""
        now = now or time.time()
        if now < self.pause_until:
            return 0
        todo = [i for i in dict.fromkeys(ids) if i and self.get(i) is None][:PER_CALL]
        done = 0
        for sid in todo:
            url = STORY_URL.format(q=urllib.parse.urlencode({"id": sid, "lang": "en"}))
            r = fetch(url, key=None, ttl_sec=0.0, timeout=15, ua=BROWSER_UA, headers=HEADERS,
                      stale_ok=False, store=False, validate=json_body)
            if r.status in (403, 429):
                self.pause_until = now + PAUSE_SEC
                break
            if not r.ok:
                continue
            try:
                text = body_of(r.json())
            except ValueError:
                continue
            with self._lock:
                self.texts[sid] = {"text": text, "at": now}
            done += 1
            time.sleep(0.8)
        if done:
            with self._lock:
                for k in [k for k, v in self.texts.items() if now - v.get("at", 0) >= KEEP_SEC]:
                    del self.texts[k]
            self._save()
        return done
