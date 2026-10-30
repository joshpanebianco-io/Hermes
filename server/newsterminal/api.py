"""
The HTTP surface — thin on purpose.

Every route is a read of the collector's current snapshot. There is no fetching
on the request path at all, so a route cannot be slow and cannot fail because
an upstream is down: it returns what the collector holds, with the age of each
block beside it, and the client decides how to present something eleven minutes
old. The one upstream call a reader can ask for — a report or a game plan from
a model — runs on a thread of its own and is polled by id (jobs.py), so even
that never holds a request open.

WHY /api/terminal EXISTS. The dashboard wants every block on first paint. Nine
round trips to nine routes would be nine chances to render a half-page, and the
whole object is small enough (~250 KB with the wire) that one request is
simply better. The per-block routes stay because they are what a poll of a
single panel should hit, and what makes this debuggable with curl.
"""

from __future__ import annotations

import contextlib
import re
from collections.abc import AsyncIterator
from datetime import UTC, datetime
from typing import Annotated, Any

from fastapi import FastAPI, Path, Query, Request, Response
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from starlette.middleware.base import RequestResponseEndpoint

from . import ask as ask_mod
from . import config, jobs, optcalc
from . import report as report_mod
from . import stockplan as plan_mod
from . import tools as tools_mod
from .collector import COLLECTOR
from .sessions import session_state


@contextlib.asynccontextmanager
async def lifespan(_app: FastAPI) -> AsyncIterator[None]:
    COLLECTOR.start()
    try:
        yield
    finally:
        COLLECTOR.stop()


app = FastAPI(title="HERMES", version="0.1.0", lifespan=lifespan)

# The Next server component calls this from the same machine; the browser never
# does. Localhost only, and only the dev ports — this service holds nothing
# secret but there is no reason for it to answer anyone else.
ORIGINS = ("http://localhost:3100", "http://127.0.0.1:3100")

app.add_middleware(
    CORSMiddleware,
    allow_origins=list(ORIGINS),
    allow_methods=["GET", "POST"],
    allow_headers=["*"],
)


@app.middleware("http")
async def same_desk_writes(request: Request, call_next: RequestResponseEndpoint) -> Response:
    """CORS STOPS A PAGE READING THE ANSWER, NOT SENDING THE REQUEST. A query-
    string POST is a "simple" request, so any website open in the same browser
    could fire `POST /api/report` at this port and spend a model call — the
    response is withheld, the work is done. A browser always names the page a
    write came from; the Next server's own fetch names none. So a write that
    names a foreign origin is refused before it reaches a route (audit,
    2026-10-14)."""
    origin = request.headers.get("origin")
    if request.method not in ("GET", "HEAD", "OPTIONS") and origin and origin not in ORIGINS:
        return Response("cross-origin write refused", status_code=403)
    return await call_next(request)


@app.get("/api/health")
def health() -> dict[str, Any]:
    snap = COLLECTOR.snapshot()
    return {
        "ok": snap["ok"],
        "built_utc": snap["built_utc"],
        "started_utc": snap["started_utc"],
        "status": snap["status"],
        "age_min": snap["age_min"],
        "counts": {
            "quotes": len(snap.get("quotes") or []),
            "wire": len(snap.get("wire") or []),
            "calendar": len(snap.get("calendar") or []),
            "sectors": len(snap.get("sectors") or []),
            "gex_assets": sum(
                1 for v in ((snap.get("gex") or {}).get("assets") or {}).values() if v.get("ok")
            ),
        },
        "config": {
            "gexygen_api": config.GEXYGEN_API or None,
            "fred_key": bool(config.FRED_KEY),
            "eia_key": bool(config.EIA_KEY),
        },
    }


@app.get("/api/terminal")
def terminal() -> dict[str, Any]:
    """Everything, one request. What the dashboard's first paint reads. The
    levels ladders are arithmetic on the snapshot (report.live_ladders), done
    here per request rather than stored, so they are never older than it."""
    snap = COLLECTOR.snapshot()
    return {**snap, "ladders": report_mod.live_ladders(snap)}


@app.get("/api/clock")
def clock() -> dict[str, Any]:
    """Computed fresh rather than read from the snapshot — it is arithmetic on
    the wall clock, so serving it at the collector's cadence would show a
    countdown that jumps in twenty-second steps."""
    return session_state()


@app.get("/api/quotes")
def quotes(group: str | None = Query(None)) -> dict[str, Any]:
    snap = COLLECTOR.snapshot()
    rows = snap.get("quotes") or []
    if group:
        rows = [r for r in rows if r.get("group") == group]
    return {"rows": rows, "status": (snap["status"] or {}).get("quotes"),
            "age_min": (snap["age_min"] or {}).get("quotes")}


@app.get("/api/wire")
def wire(
    category: str | None = Query(None),
    limit: int = Query(120, ge=1, le=400),
) -> dict[str, Any]:
    snap = COLLECTOR.snapshot()
    items = snap.get("wire") or []
    if category and category != "all":
        items = [i for i in items if i.get("category") == category]
    return {
        "items": items[:limit],
        "total": len(snap.get("wire") or []),
        "feeds": snap.get("wire_feeds") or [],
        "status": (snap["status"] or {}).get("wire"),
        "age_min": (snap["age_min"] or {}).get("wire"),
    }


@app.get("/api/calendar")
def calendar(min_score: int = Query(0, ge=0, le=5)) -> dict[str, Any]:
    snap = COLLECTOR.snapshot()
    rows = [r for r in (snap.get("calendar") or []) if r.get("score", 0) >= min_score]
    return {"rows": rows, "status": (snap["status"] or {}).get("calendar"),
            "age_min": (snap["age_min"] or {}).get("calendar")}


@app.get("/api/rates")
def rates() -> dict[str, Any]:
    snap = COLLECTOR.snapshot()
    return {"rates": snap.get("rates") or {}, "status": (snap["status"] or {}).get("rates"),
            "age_min": (snap["age_min"] or {}).get("rates")}


@app.get("/api/sectors")
def sectors() -> dict[str, Any]:
    snap = COLLECTOR.snapshot()
    return {"rows": snap.get("sectors") or [], "status": (snap["status"] or {}).get("sectors"),
            "age_min": (snap["age_min"] or {}).get("sectors")}


@app.get("/api/gex")
def gex() -> dict[str, Any]:
    snap = COLLECTOR.snapshot()
    return {"gex": snap.get("gex") or {}, "status": (snap["status"] or {}).get("gex"),
            "age_min": (snap["age_min"] or {}).get("gex")}


# A stored note's id — the timestamp slug report.generate and stockplan.generate
# mint (`20261021-061500`). Checked on the way in because it becomes a path.
_NOTE_ID = r"^\d{8}-\d{6}$"
_NOTE_ID_RE = re.compile(_NOTE_ID)


def _note_ids(ids: list[str] | None) -> list[str]:
    """The ids that look like ids. A list query cannot carry a per-item pattern
    the way `Path` does, so the shape check is here; the storage basenames each
    one as well — two locks, as on the single-id routes."""
    return [i for i in (ids or []) if _NOTE_ID_RE.match(i)]


# ---------------------------------------------------------------- report
#
# Generating a report is an explicit act by the reader — running it on the
# collector's timer would burn a free tier's daily quota on reports nobody
# asked for — and it takes one to five minutes on a free model. It used to run
# ON the request path, and the POST was held open for the whole of it; since
# 2026-10-27 the POST starts a job and answers at once, and the page polls
# `/api/report/job/{id}` until the note is written (jobs.py says why). One
# report and one game plan at a time: a second press joins the running job.

_REPORTS = jobs.Runner("report")
_PLANS = jobs.Runner("game plan")


def _report_feed() -> dict[str, Any]:
    return {"config": report_mod.configured(), "latest": report_mod.latest(),
            "history": report_mod.history()}


@app.get("/api/report")
def report_latest() -> dict[str, Any]:
    """The most recent report, the history list, whether a key is set — and
    the job being written right now, if there is one, so a page that loads
    mid-generation picks the clock back up rather than showing the old note
    as though nothing had been asked for."""
    return {**_report_feed(), "job": _REPORTS.running()}


@app.get("/api/report/job/{job_id}")
def report_job(job_id: str = Path(..., pattern=_NOTE_ID)) -> dict[str, Any]:
    """Where a generation stands. Done, `latest` is the note it wrote — stored
    and first in `history` when it succeeded, the failed envelope when it did
    not — which is exactly what the POST used to answer with. Running, `latest`
    is still the last stored note, so the page has something under the clock.
    Lost (the collector restarted underneath it), the page says so."""
    view, result = _REPORTS.get(job_id)
    feed = _report_feed()
    if result is not None:
        feed["latest"] = result
    return {**feed, "job": view}


@app.get("/api/report/{report_id}")
def report_one(report_id: str) -> dict[str, Any]:
    return {"config": report_mod.configured(), "latest": report_mod.load(report_id)}


@app.delete("/api/report/{report_id}")
def report_delete(report_id: str) -> dict[str, Any]:
    """Drop one stored report, and hand back the list without it.

    The refreshed `history` and `latest` come back in the same response rather
    than leaving the panel to re-fetch: deleting the report you are currently
    reading has to leave something coherent on screen, and a second round trip
    is a window in which the list and the open report disagree.

    A 404 would be the pedantic answer for an id that is already gone, but
    "gone" is exactly the state the caller asked for — a double-click on the
    confirm should not raise. `deleted` says which actually happened.
    """
    gone = report_mod.remove(report_id)
    return {
        "config": report_mod.configured(),
        "latest": report_mod.latest(),
        "history": report_mod.history(),
        "deleted": gone,
    }


@app.delete("/api/report")
def report_delete_many(
    ids: Annotated[list[str] | None, Query()] = None,
    every: bool = Query(False, alias="all"),
) -> dict[str, Any]:
    """Drop several stored reports — `?ids=a&ids=b` — or every one — `?all=1` —
    and hand back the list without them, as the single delete does.

    ONE TRIP, NOT ONE PER ROW (owner, 2026-10-21: "multi select delete and
    delete all options"). N single deletes land N feeds in network order and
    the list flickers through states nobody asked for. `all` means every file
    the collector keeps, not the twenty the list shows — `history` is capped
    at twenty while KEEP holds forty. `deleted` names what went, so the panel
    can tell a miss from a delete.
    """
    gone = report_mod.remove_all() if every else report_mod.remove_many(_note_ids(ids))
    return {
        "config": report_mod.configured(),
        "latest": report_mod.latest(),
        "history": report_mod.history(),
        "deleted": gone,
    }


@app.post("/api/report")
def report_generate(
    label: str = Query("manual", max_length=40),
    session: str = Query("auto", pattern="^(auto|asia|london|ny)$"),
    asset: str = Query("all", pattern="^(all|NQ|ES|GC)$"),
) -> dict[str, Any]:
    """Start writing a report against the collector's current snapshot and
    answer at once with the job; the page polls `/api/report/job/{id}` for the
    note. A report already being written is handed back instead of a second
    one being started.

    `session` picks which trading session the note is written for; `auto`
    resolves it from the ET clock, which is what pressing Generate almost
    always means. The snapshot is taken HERE, on the request, so the note
    describes the terminal as it stood when Generate was pressed.
    """
    snap = COLLECTOR.snapshot()
    now = datetime.now(UTC)
    sess = report_mod.resolve_session(snap.get("clock") or {}, session)
    book = report_mod.resolve_asset(asset)
    # What the page may show while it waits, and what a crash envelope is
    # captioned with (jobs.Runner): the same fields the note itself carries.
    meta = {
        "model": report_mod.DEFAULT_MODEL, "label": label,
        "session": sess, "session_label": report_mod.SESSIONS[sess]["label"],
        "asset": book, "asset_label": report_mod.ASSETS[book]["label"],
        "et_label": now.astimezone(report_mod.ET).strftime("%a %d %b, %H:%M ET"),
    }
    job = _REPORTS.start(
        report_mod.note_id(now), meta,
        lambda: report_mod.generate(snap, label=label, session=session, asset=asset, now=now),
    )
    return {**_report_feed(), "job": job}


@app.get("/api/ranges")
def ranges() -> dict[str, Any]:
    snap = COLLECTOR.snapshot()
    return {"ranges": snap.get("ranges") or {}, "status": (snap["status"] or {}).get("ranges"),
            "age_min": (snap["age_min"] or {}).get("ranges")}


@app.get("/api/constituents")
def constituents() -> dict[str, Any]:
    snap = COLLECTOR.snapshot()
    return {"constituents": snap.get("constituents") or {},
            "status": (snap["status"] or {}).get("constituents"),
            "age_min": (snap["age_min"] or {}).get("constituents")}


@app.get("/api/fed")
def fed() -> dict[str, Any]:
    snap = COLLECTOR.snapshot()
    return {"rows": snap.get("fed") or [], "status": (snap["status"] or {}).get("fed"),
            "age_min": (snap["age_min"] or {}).get("fed")}


@app.get("/api/earnings")
def earnings() -> dict[str, Any]:
    snap = COLLECTOR.snapshot()
    return {"rows": snap.get("earnings") or [], "status": (snap["status"] or {}).get("earnings"),
            "age_min": (snap["age_min"] or {}).get("earnings")}


# ---------------------------------------------------------------- scanner
#
# Its own routes rather than more of /api/terminal: the scanner is a tab, read
# only while it is open, and its rows (bars-derived state, headlines, filings
# for up to forty names) would otherwise ride along on every twenty-second poll
# of the board. Same rule as everything else here: a read of what the collector
# already holds, never a fetch.


class WatchlistIn(BaseModel):
    symbols: list[str]


class PromotionIn(BaseModel):
    on: bool


@app.get("/api/scanner")
def scanner() -> dict[str, Any]:
    return COLLECTOR.scanner_payload()


@app.get("/api/scanner/watchlist")
def scanner_watchlist() -> dict[str, Any]:
    """The pinned list, the pool's view (today's promotions, the names in play,
    the marks) and, for Settings' copy, the options expiry rule — one rule,
    worded once (optcalc.expiry_rule), on the scanner's lightest read."""
    return {**COLLECTOR.watchlist_payload(), "options_rule": optcalc.expiry_rule()}


@app.get("/api/scanner/events")
def scanner_events(
    since: int = Query(0, ge=0),
    limit: int = Query(200, ge=1, le=500),
) -> dict[str, Any]:
    """Events with id > since, oldest first, and the latest id that exists — so a
    client starting at `since=latest` only ever sees new ones. A `since` past the
    end is answered with no events, not an error: that is how a page starts."""
    return COLLECTOR.events.since(since, limit)


@app.get("/api/scanner/stats")
def scanner_stats(days: int = Query(20, ge=1, le=30)) -> dict[str, Any]:
    """Settled (L)/(E) outcomes over the last `days`, grouped by kind, side and score."""
    return COLLECTOR.events.stats(days)


@app.get("/api/scanner/bars/{sym}")
def scanner_bars(sym: str, tf: str = Query("10m", pattern=r"^(1m|3m|5m|10m|D)$")) -> dict[str, Any]:
    """One name's chart on `tf` (1m, 3m, 5m, 10m or D): bars, the EMA wave,
    VWAP, levels and signals. Always 200; `ok: false` with an `error` when the
    name has no bars."""
    return COLLECTOR.scanner_bars(sym[:12], tf)



@app.post("/api/scanner/watchlist")
def scanner_watchlist_set(body: WatchlistIn) -> dict[str, Any]:
    """Replace the pinned list. Invalid entries come back in `rejected` rather
    than failing the whole save; an empty or all-invalid list keeps the old one.
    The pool's promotions are not part of it — they come and go on their own."""
    _ok, bad = COLLECTOR.set_watchlist(body.symbols)
    return {**COLLECTOR.watchlist_payload(bad), "options_rule": optcalc.expiry_rule()}


@app.post("/api/scanner/promotion")
def scanner_promotion(body: PromotionIn) -> dict[str, Any]:
    """Switch the pool's promotion on or off (sources/pool.py). Off takes
    today's promoted names off the list at once; on reads the pool again and
    re-runs today's latest mark. Answers with the watchlist read."""
    COLLECTOR.set_promotion(body.on)
    return {**COLLECTOR.watchlist_payload(), "options_rule": optcalc.expiry_rule()}


# ---------------------------------------------------------------- market
#
# The stocks desk's context (marketctx.py): the tape count and its grade,
# breadth, fuel, today's prints, the Fed path, gamma in ETF prices, the index
# ETFs' options and the sector peers reporting. Computed on read from the
# scanner payload and the snapshot, like the Scanner itself.


@app.get("/api/market")
def market() -> dict[str, Any]:
    return COLLECTOR.market_payload()


# ---------------------------------------------------------------- game plan
#
# The stocks desk's brief (stockplan.py): its own routes and storage, so the
# futures report's history never carries a stock plan and the reverse. Written
# as the report is — a job started by the POST and polled by id — because it
# is the same minutes on the same free model.

_PLAN_ID = _NOTE_ID


def _plan_feed() -> dict[str, Any]:
    return {"config": plan_mod.configured(), "latest": plan_mod.latest(),
            "history": plan_mod.history()}


@app.get("/api/plan")
def plan_latest() -> dict[str, Any]:
    """The most recent game plan, the history list, whether a key is set, and
    the job being written right now, if any (see report_latest)."""
    return {**_plan_feed(), "job": _PLANS.running()}


@app.get("/api/plan/job/{job_id}")
def plan_job(job_id: str = Path(..., pattern=_PLAN_ID)) -> dict[str, Any]:
    """Where a game plan's generation stands (see report_job)."""
    view, result = _PLANS.get(job_id)
    feed = _plan_feed()
    if result is not None:
        feed["latest"] = result
    return {**feed, "job": view}


@app.get("/api/plan/{plan_id}")
def plan_one(plan_id: str = Path(..., pattern=_PLAN_ID)) -> dict[str, Any]:
    return {"config": plan_mod.configured(), "latest": plan_mod.load(plan_id)}


@app.delete("/api/plan/{plan_id}")
def plan_delete(plan_id: str = Path(..., pattern=_PLAN_ID)) -> dict[str, Any]:
    """Drop one stored plan and hand back the list without it (see report_delete)."""
    gone = plan_mod.remove(plan_id)
    return {**_plan_feed(), "deleted": gone}


@app.delete("/api/plan")
def plan_delete_many(
    ids: Annotated[list[str] | None, Query()] = None,
    every: bool = Query(False, alias="all"),
) -> dict[str, Any]:
    """Drop several stored plans, or every one (see report_delete_many)."""
    gone = plan_mod.remove_all() if every else plan_mod.remove_many(_note_ids(ids))
    return {**_plan_feed(), "deleted": gone}


@app.get("/api/ask/context")
def ask_context(
    tab: str = Query("terminal",
                     pattern="^(terminal|structure|tape|report|market|scanner|plan|settings|hermes)$"),
    sym: str | None = Query(None, max_length=12),
    desk: str | None = Query(None, pattern="^(futures|stocks)$"),
    slim: bool = Query(False),
) -> dict[str, Any]:
    """What the assistant reads for a question asked on `tab` (ask.py): the
    desk's brief digest, the selected scanner row, the latest note. On its own
    tab (`hermes`) it reads both desks, every scanner name and both notes;
    `desk` is then the one the reader came from. A read of what the collector
    holds — the model is called by the web app, not here."""
    snap = COLLECTOR.snapshot()
    if tab == ask_mod.HERMES_TAB and slim:
        # The tab's opening picture (ask.slim_context); the tools fill the rest.
        return {"tab": tab, "desk": desk, "slim": ask_mod.slim_context(
            snap, COLLECTOR.scanner_payload(), report_mod.latest(), plan_mod.latest()),
            "selected": ask_mod.selected_row(COLLECTOR.scanner_payload(), sym)}
    if tab == ask_mod.HERMES_TAB:
        return ask_mod.whole_context(snap, COLLECTOR.scanner_payload(), sym,
                                     report_mod.latest(), plan_mod.latest(), desk)
    scan = COLLECTOR.scanner_payload() if tab in ask_mod.STOCKS_TABS else None
    note = report_mod.latest() if tab == "report" else plan_mod.latest() if tab == "plan" else None
    return ask_mod.context(tab, snap, scan, sym, note)


@app.get("/api/ask/tools")
def ask_tools(desk: str | None = Query(None, pattern="^(futures|stocks|both)$")) -> dict[str, Any]:
    """What Hermes may ask for (tools.py), in the shape a model is shown —
    one desk's set when the web's router names a desk, else all of it."""
    return {"tools": tools_mod.spec_for(desk)}


class ToolIn(BaseModel):
    name: str
    args: dict[str, Any] | None = None


@app.post("/api/ask/tool")
def ask_tool(body: ToolIn) -> dict[str, Any]:
    """Answer one of Hermes's tool calls from what the collector holds. Never
    a 500: a bad name or argument comes back as an `error` the model reads."""
    snap = COLLECTOR.snapshot()
    return tools_mod.run(
        body.name[:40], body.args,
        snap=snap, scan=COLLECTOR.scanner_payload(), bars=COLLECTOR.scanner_bars,
        brief=lambda i: report_mod.load(i) if i else report_mod.latest(),
        plan=lambda i: plan_mod.load(i) if i else plan_mod.latest(),
    )


@app.post("/api/plan")
def plan_generate(top: int = Query(plan_mod.TOP_DEFAULT, ge=plan_mod.TOP_MIN,
                                   le=plan_mod.TOP_MAX)) -> dict[str, Any]:
    """Start writing a game plan for the top `top` scanner names against the
    live state, and answer at once with the job (see report_generate)."""
    scan, snap = COLLECTOR.scanner_payload(), COLLECTOR.snapshot()
    now = datetime.now(UTC)
    meta = {
        "model": report_mod.DEFAULT_MODEL, "top": top,
        "et_label": now.astimezone(report_mod.ET).strftime("%a %d %b, %H:%M ET"),
    }
    job = _PLANS.start(
        report_mod.note_id(now), meta, lambda: plan_mod.generate(scan, snap, top=top, now=now)
    )
    return {**_plan_feed(), "job": job}
