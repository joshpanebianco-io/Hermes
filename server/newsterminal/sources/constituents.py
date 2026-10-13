"""
What the heavy names are doing — the two or three stocks that ARE the move.

THE ARGUMENT, WHICH IS GEXYGEN'S AND IS RIGHT. NQ is a cap-weighted basket in
which the top nine names are about 43% of it: NVDA 8.4%, AAPL 7.5%, MSFT 6.1%,
MU 4.6%, AMZN 4.6%. On most days two or three of them supply most of the index
move. So the useful ranking is not percent change, it is CONTRIBUTION — weight
times return — because a 6% move in a 0.3% weight is noise and a 2% move in an
8% weight is the tape. That distinction is the whole reason this panel exists
rather than a list of biggest movers.

WEIGHTS FROM THE ISSUER, RETURNS FROM THE TAPE. iShares publishes the full
holdings of its NASDAQ-100 and S&P 500 UCITS trackers as CSV — both are
full-replication funds, so their baskets ARE the indices, and the file is the
fund's own disclosure rather than the index provider's IP. Returns come from
the same batched Yahoo endpoint the board uses.

ONE PARSER FOR BOTH, and that is why iShares is used for the S&P rather than
SSGA's own SPY file: SSGA publishes .xlsx, which is a zip of XML and a parser
this service does not otherwise need. Two indices in one CSV shape is worth
more than sourcing each from its own issuer.

GERMAN LOCALE. The files come from iShares' German site — "8,37" is eight point
three seven and "2.506.028.501,10" is two and a half billion. Parsed
explicitly, because `float("8,37")` raises and `float("2.506")` silently
returns 2.506.
"""

from __future__ import annotations

import csv
import io
import re
from typing import Any

from ..config import BROWSER_UA
from ..http import SourceStatus, csv_body, fetch
from .quotes import CHUNK, _chunks, _spark

# key, label, the index the basket tracks, holdings URL
FUNDS: list[tuple[str, str, str, str]] = [
    (
        "NQ",
        "Nasdaq 100",
        "NDX",
        # THE HOLDINGS MOVED (review, 2026-10-13). The old `.ajax?fileType=csv`
        # address started answering with the fund's ~3MB web page, which parsed
        # to no rows and left Index movers empty for both indices. This is the
        # file the page's own download button now links to; same German CSV.
        "https://www.ishares.com/de/privatanleger/de/produkte/253741"
        "/ishares-nasdaq-100-ucits-etf/latest-holdings.csv",
    ),
    (
        "ES",
        "S&P 500",
        "SPX",
        "https://www.ishares.com/de/privatanleger/de/produkte/253743"
        "/ishares-core-s-p-500-ucits-etf/latest-holdings.csv",
    ),
]

# How many names to quote per index. The top 40 of the NDX is roughly 75% of it
# and costs four batched requests; the long tail cannot move an index enough to
# be worth a fifth.
TOP_N = 40

_TICKER = re.compile(r"^[A-Z][A-Z.\-]{0,6}$")


def _de_num(s: str) -> float | None:
    """German-formatted number to float. '8,37' -> 8.37, '1.234,5' -> 1234.5."""
    t = (s or "").strip().strip('"')
    if not t:
        return None
    t = t.replace(".", "").replace(",", ".")
    try:
        return float(t)
    except ValueError:
        return None


def parse_holdings(text: str) -> tuple[list[dict[str, Any]], str | None]:
    """An iShares holdings CSV → equity rows with weights. Pure.

    The file opens with a title line and a blank before the real header, so the
    header row is found rather than assumed — iShares has moved it before, and
    a hard-coded skip would silently produce zero holdings rather than an error.
    """
    # The file is served UTF-8 with a BOM, so the first character of the first
    # line is U+FEFF and every `startswith` against it fails silently — which
    # is how the as-of date came back None while the holdings parsed fine.
    lines = text.lstrip("﻿").splitlines()
    start = None
    as_of = None
    for i, line in enumerate(lines[:12]):
        if as_of is None and line.lower().startswith("fondsposition per"):
            m = re.search(r'"([^"]+)"', line)
            as_of = m.group(1) if m else None
        if line.startswith("Emittententicker") or line.startswith("Ticker"):
            start = i
            break
    if start is None:
        return [], as_of

    rows: list[dict[str, Any]] = []
    for r in csv.DictReader(io.StringIO("\n".join(lines[start:]))):
        sym = (r.get("Emittententicker") or r.get("Ticker") or "").strip().strip('"')
        # The basket carries cash lines, futures and FX alongside the equities.
        # A weight without a real ticker is not a company.
        if not _TICKER.match(sym):
            continue
        asset_class = (r.get("Anlageklasse") or "").strip()
        if asset_class and "Aktien" not in asset_class:
            continue
        w = _de_num(r.get("Gewichtung (%)") or "")
        if w is None or w <= 0:
            continue
        rows.append(
            {
                "symbol": sym,
                "name": (r.get("Name") or "").strip().strip('"').title(),
                "sector": (r.get("Sektor") or "").strip().strip('"'),
                "weight": w,
            }
        )
    rows.sort(key=lambda x: -x["weight"])
    return rows, as_of


def collect() -> tuple[dict[str, Any], SourceStatus]:
    """Per index: the heavy names, their moves, and what each contributed."""
    st = SourceStatus("Constituents")
    out: dict[str, Any] = {}
    notes: list[str] = []

    # ---- weights ------------------------------------------------------------
    baskets: dict[str, tuple[list[dict[str, Any]], str | None]] = {}
    for key, _label, _idx, url in FUNDS:
        # Holdings change once a day at most, so this is cached hard — it is a
        # 17-83 KB download and re-fetching it every minute would be rude for
        # a file that cannot have moved.
        # `holdings2_`: a fresh key, so the HTML page the old URL left in the
        # `holdings_` entries is never read again. `csv_body` keeps the next
        # web page from replacing a good file.
        r = st.absorb(fetch(url, key=f"holdings2_{key}", ttl_sec=6 * 3600.0, ua=BROWSER_UA,
                            timeout=40, stale_max_sec=4 * 86400.0, validate=_holdings_body))
        if not r.ok:
            notes.append(f"{key} holdings: {r.error}")
            continue
        try:
            rows, as_of = parse_holdings(r.text)
        except (csv.Error, ValueError) as e:
            notes.append(f"{key} holdings parse: {e}")
            continue
        if rows:
            baskets[key] = (rows, as_of)
        else:
            notes.append(f"{key} holdings: no equity rows found")

    # ---- one quote pass for every name across both baskets ------------------
    wanted: list[str] = []
    for rows, _ in baskets.values():
        for h in rows[:TOP_N]:
            if h["symbol"] not in wanted:
                wanted.append(h["symbol"])

    quotes: dict[str, Any] = {}
    for chunk in _chunks(wanted, CHUNK):
        got, err = _spark(chunk, "1d", "1d", ttl=45.0, st=st, stale_max=600.0)
        quotes.update(got)
        if err:
            notes.append(f"quotes: {err}")

    # ---- weight x return ----------------------------------------------------
    for key, label, index, _url in FUNDS:
        if key not in baskets:
            continue
        rows, as_of = baskets[key]
        members: list[dict[str, Any]] = []
        for h in rows[:TOP_N]:
            resp = quotes.get(h["symbol"])
            if not resp:
                continue
            meta = resp.get("meta") or {}
            px = meta.get("regularMarketPrice")
            prev = meta.get("chartPreviousClose") or meta.get("previousClose")
            if px is None or not prev:
                continue
            pct = (px - prev) / prev * 100.0
            members.append(
                {
                    **h,
                    "last": px,
                    "pct": round(pct, 2),
                    # In index PERCENTAGE points. Summed over the whole basket
                    # this reconstructs the index move; over the top 40 it is
                    # most of it, which is the point.
                    "contribution": round(h["weight"] * pct / 100.0, 4),
                }
            )
        members.sort(key=lambda m: -abs(m["contribution"]))
        out[key] = {
            "label": label,
            "index": index,
            "as_of": as_of,
            "covered_weight": round(sum(m["weight"] for m in members), 2),
            # What the names shown add up to, as an index move. Read beside the
            # index's own change it says how much of today is these names and
            # how much is everything else.
            "net_contribution": round(sum(m["contribution"] for m in members), 3),
            "members": members,
        }

    st.items = sum(len(v["members"]) for v in out.values())
    st.notes = notes
    if notes and st.items == 0:
        st.error = notes[0]
    st.settle(st.items > 0, "request")
    return {"indices": out}, st


def _holdings_body(body: bytes) -> str | None:
    """The holdings CSV, or why not — named for iShares' failure in particular."""
    h = body[:400].decode("utf-8", errors="replace").lstrip("\ufeff \t\r\n").lower()
    if h.startswith("<"):
        return "iShares served a web page, not the CSV"
    return csv_body(body)
