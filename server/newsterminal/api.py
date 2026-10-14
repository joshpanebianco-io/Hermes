"""
The HTTP surface — thin on purpose.

Every route is a read of the collector's current snapshot. There is no fetching
on the request path at all, so a route cannot be slow and cannot fail because
an upstream is down: it returns what the collector holds, with the age of each
block beside it, and the client decides how to present something eleven minutes
old.

WHY /api/terminal EXISTS. The dashboard wants every block on first paint. Nine
round trips to nine routes would be nine chances to render a half-page, and the
whole object is small enough (~250 KB with the wire) that one request is
simply better. The per-block routes stay because they are what a poll of a
single panel should hit, and what makes this debuggable with curl.
"""

from __future__ import annotations

import contextlib
from collections.abc import AsyncIterator
from typing import Any

from fastapi import FastAPI, Path, Query, Request, Response
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from starlette.middleware.base import RequestResponseEndpoint

from . import ask as ask_mod
from . import config, optcalc
from . import report as report_mod
from . import stockplan as plan_mod
from .collector import COLLECTOR
from .sessions import session_state
from .sources import scanner as scan_src


@contextlib.asynccontextmanager
async def lifespan(_app: FastAPI) -> AsyncIterator[None]:
    COLLECTOR.start()
    try:
        yield
    finally:
        COLLECTOR.stop()


app = FastAPI(title="HERMESX", version="0.1.0", lifespan=lifespan)

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
    """Everything, one request. What the dashboard's first paint reads."""
    return COLLECTOR.snapshot()


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


# ---------------------------------------------------------------- report
#
# The one place in this service that does work on the request path, and it has
# to: generating a report is an explicit act by the reader, it takes ten to
# thirty seconds, and running it on the collector's timer would burn a free
# tier's daily quota on reports nobody asked for.


@app.get("/api/report")
def report_latest() -> dict[str, Any]:
    """The most recent report, plus the history list and whether a key is set."""
    return {
        "config": report_mod.configured(),
        "latest": report_mod.latest(),
        "history": report_mod.history(),
    }


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


@app.post("/api/report")
def report_generate(
    label: str = Query("manual", max_length=40),
    session: str = Query("auto", pattern="^(auto|asia|london|ny)$"),
    asset: str = Query("all", pattern="^(all|NQ|ES|GC)$"),
) -> dict[str, Any]:
    """Generate a new report against the collector's current snapshot.

    `session` picks which trading session the note is written for; `auto`
    resolves it from the ET clock, which is what pressing Generate almost
    always means.
    """
    rep = report_mod.generate(
        COLLECTOR.snapshot(), label=label, session=session, asset=asset
    )
    return {"config": report_mod.configured(), "latest": rep, "history": report_mod.history()}


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


@app.get("/api/scanner")
def scanner() -> dict[str, Any]:
    return COLLECTOR.scanner_payload()


@app.get("/api/scanner/watchlist")
def scanner_watchlist() -> dict[str, Any]:
    # The options expiry rule rides along for Settings' copy: one rule, worded
    # once (optcalc.expiry_rule), on the scanner's lightest read.
    return {"symbols": COLLECTOR.scan.watchlist(), "default": list(scan_src.DEFAULT_WATCHLIST),
            "rejected": [], "options_rule": optcalc.expiry_rule()}


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
    """Replace the list. Invalid entries come back in `rejected` rather than
    failing the whole save; an empty or all-invalid list keeps the old one."""
    ok, bad = COLLECTOR.set_watchlist(body.symbols)
    return {"symbols": ok, "default": list(scan_src.DEFAULT_WATCHLIST), "rejected": bad}


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
# futures report's history never carries a stock plan and the reverse. Like
# the report, generating is the one thing here that works on the request
# path — an explicit act by the reader, a minute or three on a free model.

_PLAN_ID = r"^\d{8}-\d{6}$"


def _plan_feed() -> dict[str, Any]:
    return {"config": plan_mod.configured(), "latest": plan_mod.latest(),
            "history": plan_mod.history()}


@app.get("/api/plan")
def plan_latest() -> dict[str, Any]:
    """The most recent game plan, the history list, and whether a key is set."""
    return _plan_feed()


@app.get("/api/plan/{plan_id}")
def plan_one(plan_id: str = Path(..., pattern=_PLAN_ID)) -> dict[str, Any]:
    return {"config": plan_mod.configured(), "latest": plan_mod.load(plan_id)}


@app.delete("/api/plan/{plan_id}")
def plan_delete(plan_id: str = Path(..., pattern=_PLAN_ID)) -> dict[str, Any]:
    """Drop one stored plan and hand back the list without it (see report_delete)."""
    gone = plan_mod.remove(plan_id)
    return {**_plan_feed(), "deleted": gone}


@app.get("/api/ask/context")
def ask_context(
    tab: str = Query("terminal", pattern="^(terminal|report|market|scanner|plan|settings)$"),
    sym: str | None = Query(None, max_length=12),
) -> dict[str, Any]:
    """What the assistant reads for a question asked on `tab` (ask.py): the
    desk's brief digest, the selected scanner row, the latest note. A read of
    what the collector holds — the model is called by the web app, not here."""
    snap = COLLECTOR.snapshot()
    scan = COLLECTOR.scanner_payload() if tab in ask_mod.STOCKS_TABS else None
    note = report_mod.latest() if tab == "report" else plan_mod.latest() if tab == "plan" else None
    return ask_mod.context(tab, snap, scan, sym, note)


@app.post("/api/plan")
def plan_generate(top: int = Query(plan_mod.TOP_DEFAULT, ge=plan_mod.TOP_MIN,
                                   le=plan_mod.TOP_MAX)) -> dict[str, Any]:
    """Write a game plan for the top `top` scanner names, against the live state."""
    rep = plan_mod.generate(COLLECTOR.scanner_payload(), COLLECTOR.snapshot(), top=top)
    return {"config": plan_mod.configured(), "latest": rep, "history": plan_mod.history()}
