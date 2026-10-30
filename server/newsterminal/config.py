"""
Configuration — every value has a working default.

NOTHING HERE IS REQUIRED. The terminal runs with an empty environment; the
optional keys only widen coverage, and every panel that depends on one says so
on its own face rather than rendering an empty box. That is the same contract
GEXYGEN's `.env.example` makes, and it exists for the same reason: a terminal
that silently shows nothing is indistinguishable from a terminal that is
telling you nothing is happening.
"""

from __future__ import annotations

import os

# --------------------------------------------------------------------------
# Service
# --------------------------------------------------------------------------

HOST = os.environ.get("NT_HOST", "127.0.0.1")
PORT = int(os.environ.get("NT_PORT", "8100"))

CACHE_DIR = os.environ.get("NT_CACHE", os.path.join(os.path.dirname(__file__), "..", "cache"))

# One row per source per tick in the collector window. Set 0 for a silent run.
TICK_LOG = os.environ.get("NT_TICK_LOG", "1") != "0"

# --------------------------------------------------------------------------
# Poll cadences, seconds.
#
# THESE ARE NOT ALL THE SAME NUMBER ON PURPOSE. Quotes move continuously and
# cost one small JSON each; a publisher's RSS is regenerated every few minutes
# at best and polling it faster is rude without being informative; the Treasury
# curve is a once-a-day print. Matching the cadence to the source's own clock is
# what keeps ~40 upstreams inside a polite request budget.
# --------------------------------------------------------------------------

QUOTES_SEC = float(os.environ.get("NT_QUOTES_SEC", "20"))
WIRE_SEC = float(os.environ.get("NT_WIRE_SEC", "120"))
GEX_SEC = float(os.environ.get("NT_GEX_SEC", "30"))
CALENDAR_SEC = float(os.environ.get("NT_CALENDAR_SEC", "600"))
RATES_SEC = float(os.environ.get("NT_RATES_SEC", "1800"))

# --------------------------------------------------------------------------
# GEX levels — borrowed from the GEXYGEN compute service.
#
# WHY BORROWED RATHER THAN RECOMPUTED. GEXYGEN already turns an option chain
# into exactly the seven numbers this terminal wants (three call walls, three
# put walls, one flip) and publishes them at /api/levels.txt for its
# NinjaTrader indicator. Recomputing them here would mean a second Black-Scholes
# engine that can disagree with the first — the single worst outcome, because
# you would have two call walls on two screens and no way to know which is
# right. Empty string disables the panel outright.
# --------------------------------------------------------------------------

GEXYGEN_API = os.environ.get("NT_GEXYGEN_API", "http://127.0.0.1:8000")
GEX_ASSETS = [
    a.strip() for a in os.environ.get("NT_GEX_ASSETS", "NQ,ES,GC").split(",") if a.strip()
]

# --------------------------------------------------------------------------
# Optional keys. Absent is first-class.
# --------------------------------------------------------------------------

FRED_KEY = os.environ.get("FRED_API_KEY", "").strip()
EIA_KEY = os.environ.get("EIA_API_KEY", "").strip()

# --------------------------------------------------------------------------
# Identity.
#
# A REAL User-Agent WITH CONTACT DETAILS. SEC EDGAR rejects anything else
# outright (403), and every other publisher here is entitled to know who is
# polling them. This is a personal-use terminal; saying so is both honest and
# what keeps the requests welcome.
# --------------------------------------------------------------------------

UA = os.environ.get(
    "NT_USER_AGENT",
    "HERMES/0.1 (personal market terminal; joshpanebianco@protonmail.com)",
)

# Publisher RSS is served to browsers; a few CDNs vary their response on a
# browser-shaped UA. Used only for the news feeds, never for the agencies.
BROWSER_UA = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/126.0 Safari/537.36"
)
