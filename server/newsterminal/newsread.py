"""
What the model makes of a name's major story: how big it is, in one line.

CONTEXT, NEVER SCORE (owner, 2026-11-14: "does it take into consideration the content
of the news not just the heading?"). The score reads headlines by rule, and a rule can
say what a story IS (a report, a deal, an upgrade) but not how big: a beat by a cent
and a beat with the year's guide raised are both "Earnings", twenty points. Reading the
rest by rule was tried on the wire and misfiled stories on a passing mention (wire.py's
`classify`), so the reading is the model's: once a story, kept, from the text the desk
already holds. It lands as one line on the row and as `size` in the signal log
(scanlog `ctx.news`), and it earns nothing until tools/fit_score.py can show that big
stories run further than ordinary ones.

WHAT THE MODEL IS SHOWN, AND ONLY THAT: the ticker, the headline that decided the
catalyst part, its feed summary where there is one (Yahoo's per-ticker RSS and the wire
carry a sentence or two; most full articles are behind a paywall and are not fetched),
the report's EPS against the estimate where the story is a report, and up to three more
of the name's headlines since the close. A figure in its line that is not in that text
is struck with the line (the briefs' numerals guard, report.known_numerals).

ONLY MAJOR STORIES, ONLY NAMES ON THE LIST, A FEW AT A TIME. The models are OpenRouter's
free pool (report.py has what that means): slow, shared and rate-limited, and the 09:00
overview and the briefs draw on the same key. So one request reads up to BATCH stories,
no more often than GAP_SEC, at most DAILY_MAX requests a New York day, and never while
a brief or an overview is being written (the clock in api.py). A failure is a missing
line and nothing else: the row, the score and the log do not wait for it.

NOTHING OF THE OWNER GOES WITH IT: a browser User-Agent and no attribution headers,
unlike the briefs' own request; the payload is public headlines and tickers.
"""

from __future__ import annotations

import contextlib
import json
import os
import re
import threading
import time
import urllib.error
import urllib.request
from collections.abc import Callable, Iterable
from datetime import datetime
from typing import Any
from zoneinfo import ZoneInfo

from . import report as rp
from .catalysts import MAJOR
from .config import BROWSER_UA, CACHE_DIR

ET = ZoneInfo("America/New_York")
STATE_FILE = os.path.join(CACHE_DIR, "news_reads.json")
SIZES = ("big", "ordinary", "unclear")
#: Stories a request, seconds between requests, requests a day.
BATCH = 8
GAP_SEC = 300.0
DAILY_MAX = 24
#: A read is kept this long (a long weekend and a day), then asked again if still live.
KEEP_SEC = 6 * 86400.0
#: One attempt's wall clock, and how many a request may make down the model chain.
WALL_SEC = 100.0
MAX_ATTEMPTS = 3
LINE_MAX = 110
OTHERS_MAX = 3
SUMMARY_MAX = 320

SYSTEM = """You grade stock news for a day trader who trades momentum breakouts in US stocks.
For each story, judge how big it is as a reason for that stock to keep moving today.

Use ONLY the text you are given for the story: its headline, its summary, the report
figures and the other headlines. Do not use anything you know about the company, and do
not guess at what the text does not say.

size:
- "big": news that changes what the company earns or is worth: results with the outlook
  raised or cut, a large surprise either way, an acquisition or a bid, a regulator's
  decision, a major contract or partnership, a large offering, a probe, a profit warning.
- "ordinary": real news, but routine: results about in line with nothing said on the
  outlook, a small contract, a product note, an analyst's change, a move with a thin
  reason.
- "unclear": the text does not say enough to judge.

line: at most 14 words of plain English saying what happened, with the key figure if one
is given. Write figures exactly as they appear in the text. No advice, no prediction, and
never the words bullish, bearish, buy or sell."""

SKELETON = """{ "reads": [ { "id": "s1", "size": "big" | "ordinary" | "unclear",
               "line": "at most 14 words" } ] }   // one per story, by its id"""

_NORM = re.compile(r"[^a-z0-9 ]")
_SPACE = re.compile(r"\s+")
_CALLS = re.compile(r"\b(?:bullish|bearish|buy|sell)\b", re.I)


def norm(title: str) -> str:
    """A headline as a key: lower case, letters and digits, the first eighty. Pure."""
    return _NORM.sub("", (title or "").lower())[:80]


def story_key(sym: str, item: dict[str, Any] | None,
              earnings: dict[str, Any] | None) -> str | None:
    """The key a deciding story is read and kept by, or None for one that is not read:
    anything under major, and a filing (a form says what it is). A report is keyed by
    its date, a headline by its words. Pure."""
    if not isinstance(item, dict) or item.get("tier") != MAJOR or item.get("src") == "filing":
        return None
    if item.get("tag") == "Report":
        day = (earnings or {}).get("date")
        return f"{sym}|report|{day}" if day else None
    title = norm(str(item.get("title") or ""))
    return f"{sym}|{title}" if title else None


def report_text(earnings: dict[str, Any] | None) -> str | None:
    """The report's figures as the calendar has them, in words. Pure."""
    e = earnings or {}
    act, est, sp = e.get("eps_actual"), e.get("eps_forecast"), e.get("surprise_pct")
    if act in (None, ""):
        return None
    out = f"EPS {act}"
    if est not in (None, ""):
        out += f" against an estimate of {est}"
    if isinstance(sp, (int, float)):
        out += f" (a surprise of {sp:+.1f}%)"
    return out


def candidate(row: dict[str, Any],
              summary_of: Callable[[str], str | None] | None = None) -> dict[str, Any] | None:
    """A scanner row → what the model would be shown for its deciding story, or None
    where there is nothing to read (no major story decided its catalyst part). Pure."""
    sym = str(row.get("sym") or "")
    parts = (row.get("score") or {}).get("parts") if isinstance(row.get("score"), dict) else None
    part = next((p for p in parts or [] if isinstance(p, dict) and p.get("key") == "catalyst"),
                None)
    read = part.get("read") if isinstance(part, dict) else None
    item = read.get("item") if isinstance(read, dict) else None
    earn = row.get("earnings") if isinstance(row.get("earnings"), dict) else None
    key = story_key(sym, item, earn)
    if not sym or key is None or not isinstance(item, dict):
        return None
    title = str(item.get("title") or "").strip()
    # The name's other headlines from about the same time: the story's own age and six
    # hours, eighteen at least. A report has no age and may be Friday's on a Monday, so
    # its headlines reach back four days.
    age = item.get("age_min")
    reach = (4 * 1440.0 if item.get("tag") == "Report"
             else max((age if isinstance(age, (int, float)) else 0.0) + 360.0, 18 * 60.0))
    news = [n for n in row.get("news") or [] if isinstance(n, dict) and n.get("title")
            and isinstance(n.get("age_min"), (int, float)) and n["age_min"] <= reach]
    head = title or next((str(n["title"]) for n in news), "")
    if not head and report_text(earn) is None:
        return None
    others = [str(n["title"]).strip() for n in news
              if norm(str(n["title"])) != norm(head)][:OTHERS_MAX]
    summary = (summary_of(head) if summary_of and head else None) or ""
    return {"key": key, "sym": sym, "tag": item.get("tag"), "headline": head,
            "summary": _SPACE.sub(" ", summary).strip()[:SUMMARY_MAX],
            "report": report_text(earn), "others": others}


def candidates(rows: Iterable[dict[str, Any]],
               summary_of: Callable[[str], str | None] | None = None) -> list[dict[str, Any]]:
    """Every row's story worth a read, in the list's order, one a key. Pure."""
    out: list[dict[str, Any]] = []
    seen: set[str] = set()
    for r in rows:
        if not isinstance(r, dict) or not r.get("ok"):
            continue
        c = candidate(r, summary_of)
        if c is not None and c["key"] not in seen:
            seen.add(c["key"])
            out.append(c)
    return out


def shown(c: dict[str, Any]) -> dict[str, Any]:
    """One story as the model sees it (no key: the id stands for it). Pure."""
    out: dict[str, Any] = {"ticker": c["sym"], "kind": c.get("tag"), "headline": c["headline"]}
    if c.get("summary"):
        out["summary"] = c["summary"]
    if c.get("report"):
        out["report"] = c["report"]
    if c.get("others"):
        out["other_headlines"] = c["others"]
    return out


def messages(cands: list[dict[str, Any]]) -> list[dict[str, str]]:
    digest = {f"s{i}": shown(c) for i, c in enumerate(cands, start=1)}
    return [{"role": "system", "content": SYSTEM},
            {"role": "user", "content": (
                f"```json\n{json.dumps(digest, indent=1, ensure_ascii=False)}\n```\n\n"
                f"Grade each of the {len(cands)} stories.")}]


def schema(n: int) -> dict[str, Any]:
    one = {"type": "object", "additionalProperties": False,
           "required": ["id", "size", "line"],
           "properties": {"id": {"type": "string", "enum": [f"s{i}" for i in range(1, n + 1)]},
                          "size": {"type": "string", "enum": list(SIZES)},
                          "line": {"type": "string"}}}
    return {"type": "object", "additionalProperties": False, "required": ["reads"],
            "properties": {"reads": {"type": "array", "items": one}}}


def clean_line(line: Any, seen: str) -> str:
    """The model's line, held to the text it was shown: one line, at most LINE_MAX, no
    call on direction, and no figure the text does not carry (else no line at all). Pure."""
    text = _SPACE.sub(" ", str(line or "")).strip().strip('"').rstrip(".")
    if not text or _CALLS.search(text):
        return ""
    known = rp.known_numerals(seen)
    if any(k not in known for k in rp.numerals_in(text)):
        return ""
    if len(text) > LINE_MAX:
        text = text[:LINE_MAX].rsplit(" ", 1)[0] + "…"
    return text


def sanitize(obj: Any, cands: list[dict[str, Any]]) -> dict[str, dict[str, Any]]:
    """The model's answer → {story key: {size, line}}, only for stories it was shown and
    sizes on the list. Pure."""
    reads = obj.get("reads") if isinstance(obj, dict) else None
    out: dict[str, dict[str, Any]] = {}
    for r in reads if isinstance(reads, list) else []:
        if not isinstance(r, dict):
            continue
        m = re.fullmatch(r"s(\d+)", str(r.get("id") or ""))
        i = int(m.group(1)) - 1 if m else -1
        size = str(r.get("size") or "").lower()
        if not 0 <= i < len(cands) or size not in SIZES:
            continue
        c = cands[i]
        seen = json.dumps(shown(c), ensure_ascii=False)
        out[c["key"]] = {"size": size, "line": clean_line(r.get("line"), seen)}
    return out


def _post(payload: dict[str, Any], key: str, wall_sec: float = WALL_SEC) -> dict[str, Any]:
    """One request to OpenRouter, under a browser User-Agent and with no attribution
    headers (the module docstring), cut off at `wall_sec` as the briefs' is."""
    req = urllib.request.Request(
        rp.OPENROUTER, data=json.dumps(payload).encode("utf-8"),
        headers={"Authorization": f"Bearer {key}", "Content-Type": "application/json",
                 "User-Agent": BROWSER_UA})
    deadline = time.monotonic() + wall_sec
    with urllib.request.urlopen(req, timeout=rp.REQUEST_TIMEOUT_SEC) as r:
        body: Any = json.loads(rp._read_by(r, deadline, wall_sec).decode("utf-8"))
    return body if isinstance(body, dict) else {}


def ask(cands: list[dict[str, Any]], key: str, model: str | None = None,
        post: Callable[[dict[str, Any], str], dict[str, Any]] | None = None,
        ) -> tuple[dict[str, dict[str, Any]], list[dict[str, Any]]]:
    """Ask the model chain to read `cands`; ({story key: read}, the attempts). Each
    model once with the strict schema; a model that refuses the schema once more in
    plain JSON mode. Never raises."""
    post = post or _post
    msgs = messages(cands)
    attempts: list[dict[str, Any]] = []
    pairs = [(m, mode) for m in rp.model_chain(model or rp.DEFAULT_MODEL)
             for mode in ("schema", "json")]
    skip_json: set[str] = set()
    for candidate_model, mode in pairs:
        if len(attempts) >= MAX_ATTEMPTS:
            break
        if mode == "json" and candidate_model in skip_json:
            continue
        user = msgs[1] if mode == "schema" else {
            "role": "user", "content": msgs[1]["content"]
            + "\n\nReturn ONLY a JSON object, no prose around it, exactly this shape:\n" + SKELETON}
        payload: dict[str, Any] = {
            "model": candidate_model, "messages": [msgs[0], user], "temperature": 0.2,
            "max_tokens": 6000, "reasoning": {"max_tokens": 1024},
            "response_format": (
                {"type": "json_schema",
                 "json_schema": {"name": "news_reads", "strict": True,
                                 "schema": schema(len(cands))}}
                if mode == "schema" else {"type": "json_object"}),
        }
        started = time.monotonic()
        try:
            doc = post(payload, key)
        except urllib.error.HTTPError as e:
            detail = ""
            with contextlib.suppress(OSError):
                detail = e.read().decode("utf-8", errors="replace")[:200]
            attempts.append({"model": candidate_model, "mode": mode,
                             "error": f"HTTP {e.code}: {detail or e.reason}"})
            if e.code in (401, 402, 403):
                break  # the key or the account: no other model will fix it
            if e.code != 400:
                skip_json.add(candidate_model)  # busy, not the schema: on to the next model
            continue
        except (rp.AttemptTimeout, urllib.error.URLError, OSError, ValueError) as e:
            attempts.append({"model": candidate_model, "mode": mode, "error": str(e)[:200]})
            skip_json.add(candidate_model)
            continue
        took = round(time.monotonic() - started, 1)
        if doc.get("error"):
            err = doc["error"]
            msg = str(err.get("message", err) if isinstance(err, dict) else err)
            attempts.append({"model": candidate_model, "mode": mode, "error": msg[:200]})
            continue
        try:
            m = doc["choices"][0]["message"]
        except (KeyError, IndexError, TypeError):
            attempts.append({"model": candidate_model, "mode": mode,
                             "error": "unexpected response shape"})
            continue
        content = m.get("content") or m.get("reasoning") or ""
        got = sanitize(rp.extract_json(content if isinstance(content, str) else str(content)),
                       cands)
        if not got:
            attempts.append({"model": candidate_model, "mode": mode, "sec": took,
                             "error": "no read in the answer"})
            continue
        attempts.append({"model": candidate_model, "mode": mode, "sec": took, "reads": len(got)})
        for v in got.values():
            v["model"] = candidate_model
        return got, attempts
    return {}, attempts


class ReadStore:
    """The reads kept, by story key. Written on the clock's thread, read on the API's."""

    def __init__(self, path: str = STATE_FILE) -> None:
        self._lock = threading.Lock()
        self.path = path
        self.reads: dict[str, dict[str, Any]] = {}
        #: Stories asked about and not answered: (when, how many times), so a story the
        #: model keeps dropping is not asked for on every request.
        self.tried: dict[str, tuple[float, int]] = {}
        self.last_ask = 0.0
        self.asks: dict[str, int] = {}
        self.last_attempts: list[dict[str, Any]] = []
        self._load()

    def _load(self) -> None:
        try:
            with open(self.path, encoding="utf-8") as f:
                d = json.load(f)
        except (OSError, ValueError):
            return
        if not isinstance(d, dict):
            return
        now = time.time()
        for k, v in (d.get("reads") or {}).items():
            if (isinstance(v, dict) and v.get("size") in SIZES
                    and isinstance(v.get("at"), (int, float)) and now - v["at"] < KEEP_SEC):
                self.reads[str(k)] = v
        asks = d.get("asks")
        if isinstance(asks, dict):
            self.asks = {str(k): int(v) for k, v in asks.items() if isinstance(v, int)}

    def _save(self) -> None:
        with self._lock:
            body = {"reads": dict(self.reads), "asks": dict(self.asks)}
        tmp = self.path + ".tmp"
        try:
            os.makedirs(os.path.dirname(self.path), exist_ok=True)
            with open(tmp, "w", encoding="utf-8") as f:
                json.dump(body, f)
            os.replace(tmp, self.path)
        except OSError:
            pass

    @staticmethod
    def _day(now: float) -> str:
        return datetime.fromtimestamp(now, ET).date().isoformat()

    def due(self, now: float) -> bool:
        """Whether a request may be made: the gap since the last, and the day's count."""
        with self._lock:
            return (now - self.last_ask >= GAP_SEC
                    and self.asks.get(self._day(now), 0) < DAILY_MAX)

    def pending(self, cands: list[dict[str, Any]], now: float) -> list[dict[str, Any]]:
        """The stories not read yet, in the order given, a batch at most. One the model
        did not answer for waits an hour, and is given up on after three tries."""
        out: list[dict[str, Any]] = []
        with self._lock:
            for c in cands:
                if c["key"] in self.reads:
                    continue
                at, n = self.tried.get(c["key"], (0.0, 0))
                if n >= 3 or (n and now - at < 3600.0):
                    continue
                out.append(c)
                if len(out) >= BATCH:
                    break
        return out

    def asked(self, cands: list[dict[str, Any]], now: float) -> None:
        """A request is going out for these."""
        with self._lock:
            self.last_ask = now
            day = self._day(now)
            self.asks = {day: self.asks.get(day, 0) + 1}
            for c in cands:
                self.tried[c["key"]] = (now, self.tried.get(c["key"], (0.0, 0))[1] + 1)

    def put(self, got: dict[str, dict[str, Any]], cands: list[dict[str, Any]], now: float,
            attempts: list[dict[str, Any]] | None = None) -> None:
        by_key = {c["key"]: c for c in cands}
        with self._lock:
            self.last_attempts = list(attempts or [])
            for k, v in got.items():
                c = by_key.get(k) or {}
                self.reads[k] = {**v, "at": now, "sym": c.get("sym"),
                                 "headline": c.get("headline")}
                self.tried.pop(k, None)
            for k in [k for k, v in self.reads.items() if now - v.get("at", 0) >= KEEP_SEC]:
                del self.reads[k]
        self._save()

    def for_item(self, sym: str, item: dict[str, Any] | None,
                 earnings: dict[str, Any] | None) -> dict[str, Any] | None:
        """The read of a row's deciding story, as the row carries it, or None."""
        key = story_key(sym, item, earnings)
        if key is None:
            return None
        with self._lock:
            v = self.reads.get(key)
        if v is None:
            return None
        return {"size": v["size"], "line": v.get("line") or "", "headline": v.get("headline")}

    def health(self, now: float) -> dict[str, Any]:
        with self._lock:
            ago = round((now - self.last_ask) / 60.0, 1) if self.last_ask else None
            return {"reads": len(self.reads), "asks_today": self.asks.get(self._day(now), 0),
                    "daily_max": DAILY_MAX, "last_ask_min": ago,
                    "last_attempts": list(self.last_attempts)}
