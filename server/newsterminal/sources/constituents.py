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

A SECOND ISSUER BEHIND EACH (2026-11-14). That held until iShares' own download
link answered 404 for two days, sibling addresses on its other sites served web
pages, and the card was a fortnight from empty with nothing to fall back to. So
each index has a second file from another issuer of a full-replication fund on
it: Invesco's QQQ holdings (JSON) for the Nasdaq 100 and State Street's SPY
workbook for the S&P 500 — the .xlsx parser after all, forty lines of the
standard library. iShares is still asked first and used whenever it answers;
the second is read only while the first is failing or stale, and the card says
whose weights it is showing. A source that has just failed is not asked again
for an hour: the dead link was being requested every ninety seconds.

THE TABS ARE THE FUNDS. The keys stay the futures books (NQ, ES) because the
bias, the drivers and the report read the baskets by book; `FUND` is what the
card labels them (owner, 2026-11-17: "change NQ and ES to QQQ and SPY").

NO RUSSELL 2000 BASKET. An IWM tab was built on 17 Nov 2026 (State Street's
Irish Russell 2000 workbook, joined to TradingView's members by ISIN, since
iShares' IWM file serves a web page) and taken out the same day at the owner's
word. The index has 1,900 names and no heavyweights: its top forty are 11% of
it, and before that day's open they added up to +0.01% while IWM traded -0.33%.
Named contribution does not explain a small-cap move; a sector split of the
whole index would, and is not built.

GERMAN LOCALE. The files come from iShares' German site — "8,37" is eight point
three seven and "2.506.028.501,10" is two and a half billion. Parsed
explicitly, because `float("8,37")` raises and `float("2.506")` silently
returns 2.506.
"""

from __future__ import annotations

import csv
import io
import json
import re
import time
import zipfile
from collections.abc import Callable
from dataclasses import dataclass
from datetime import date
from typing import Any
from xml.etree import ElementTree

from ..config import BROWSER_UA
from ..http import FetchResult, SourceStatus, csv_body, fetch, json_body
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

#: What the card calls each basket: the fund a trader watches for it (module docstring).
FUND = {"NQ": "QQQ", "ES": "SPY"}

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
    # Holdings change once a day at most, so each file is cached hard: re-fetching
    # one every minute would be rude for a file that cannot have moved.
    baskets: dict[str, tuple[list[dict[str, Any]], str | None, str]] = {}
    for key, _label, _idx, _url in FUNDS:
        basket = _weights(key, st, notes)
        if basket is not None:
            baskets[key] = basket

    # ---- one quote pass for every name across both baskets ------------------
    wanted: list[str] = []
    for rows, _, _ in baskets.values():
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
        rows, as_of, issuer = baskets[key]
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
            "fund": FUND.get(key),
            # The file's date in one style whoever published it, and whose file it is.
            "as_of": as_of_text(as_of),
            "weights_from": issuer,
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


def with_pre(block: dict[str, Any], pre_of: Callable[[str], float | None]) -> dict[str, Any]:
    """The index movers before the bell (the audit of 2026-11-16: at 08:16 ET on a Monday
    the map read Friday's moves, NVDA -2.01% while it traded -2.92%). Each member gains
    its pre-market move (`pre_pct`, from the wide screener, fifteen minutes behind, None
    for a name that has not traded) and that times its weight (`pre_contribution`), and
    each index what those add up to (`pre_net`) and how many traded (`pre_traded`).
    `pct` and `contribution` stay the session's: the engine's leaders read them. Pure."""
    out: dict[str, Any] = {}
    for key, ix in (block.get("indices") or {}).items():
        members = []
        for m in ix.get("members") or []:
            p = pre_of(str(m.get("symbol") or ""))
            w = m.get("weight")
            weighted = p is not None and isinstance(w, int | float)
            members.append({**m, "pre_pct": round(p, 2) if p is not None else None,
                            "pre_contribution": round(w * p / 100.0, 4) if weighted else None})
        traded = [m for m in members if m["pre_contribution"] is not None]
        out[key] = {**ix, "members": members,
                    "pre_net": round(sum(m["pre_contribution"] for m in traded), 3),
                    "pre_traded": len(traded)}
    return {**block, "indices": out, "pre": True}


def _holdings_body(body: bytes) -> str | None:
    """The holdings CSV, or why not — named for iShares' failure in particular."""
    h = body[:400].decode("utf-8", errors="replace").lstrip("\ufeff \t\r\n").lower()
    if h.startswith("<"):
        return "iShares served a web page, not the CSV"
    return csv_body(body)


# ------------------------------------------------------------ second sources

INVESCO_QQQ = ("https://dng-api.invesco.com/cache/v1/accounts/en_US/shareclasses/QQQ"
               "/holdings/fund?idType=ticker&productType=ETF")
SSGA_SPY = ("https://www.ssga.com/us/en/intermediary/library-content/products/fund-data"
            "/etfs/us/holdings-daily-us-en-spy.xlsx")

#: A source that failed or fell back to its old copy is not asked again before this.
RETRY_SEC = 3600.0

#: Invesco lists the fund's cash, futures and collateral beside its shares.
_EQUITY = re.compile(r"stock|depositor?y receipt", re.I)

_XLSX = "{http://schemas.openxmlformats.org/spreadsheetml/2006/main}"
#: No holdings workbook is near this; a part that is has not come from a fund.
_XLSX_PART_MAX = 16 * 1024 * 1024

_MONTHS = {"jan": 1, "feb": 2, "mar": 3, "mrz": 3, "mär": 3, "apr": 4, "may": 5, "mai": 5,
           "jun": 6, "jul": 7, "aug": 8, "sep": 9, "oct": 10, "okt": 10, "nov": 11,
           "dec": 12, "dez": 12}
_MONTH_NAMES = ("Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec")


def as_of_text(raw: Any) -> str | None:
    """A holdings file's date as "12 Nov 2026", whoever wrote it. Pure.

    iShares' German file says "10.Nov.2026" (and "10.Okt.2026"), Invesco "2026-11-12",
    State Street "12-Nov-2026". Anything else is passed through as it came.
    """
    if not raw:
        return None
    s = str(raw).strip()
    iso = re.match(r"^(\d{4})-(\d{2})-(\d{2})", s)
    if iso:
        y, mo, d = int(iso.group(1)), int(iso.group(2)), int(iso.group(3))
    else:
        named = re.match(r"^(\d{1,2})[.\-\s/]+([A-Za-zä]{3})[A-Za-zä]*\.?[.\-\s/]+(\d{4})", s)
        month = _MONTHS.get(named.group(2).lower()) if named else None
        if named is None or month is None:
            return s
        y, mo, d = int(named.group(3)), month, int(named.group(1))
    try:
        date(y, mo, d)
    except ValueError:
        return s
    return f"{d} {_MONTH_NAMES[mo - 1]} {y}"


def parse_invesco(body: bytes) -> tuple[list[dict[str, Any]], str | None]:
    """Invesco's holdings JSON for a fund → equity rows with weights. Pure."""
    doc = json.loads(body.decode("utf-8-sig", errors="replace"))
    if not isinstance(doc, dict):
        return [], None
    rows: list[dict[str, Any]] = []
    for h in doc.get("holdings") or []:
        if not isinstance(h, dict):
            continue
        sym = str(h.get("ticker") or "").strip().upper()
        w = h.get("percentageOfTotalNetAssets")
        if not _EQUITY.search(str(h.get("securityTypeName") or "")) or not _TICKER.match(sym):
            continue
        if not isinstance(w, (int, float)) or isinstance(w, bool) or w <= 0:
            continue
        rows.append({"symbol": sym, "name": str(h.get("issuerName") or "").strip(),
                     "sector": "", "weight": round(float(w), 4)})
    rows.sort(key=lambda x: -x["weight"])
    as_of = doc.get("effectiveDate")
    return rows, str(as_of) if as_of else None


def parse_spdr(body: bytes) -> tuple[list[dict[str, Any]], str | None]:
    """State Street's daily holdings workbook → equity rows with weights. Pure.

    An .xlsx is a zip: the first sheet's cells, and the table of shared strings most
    of them point into. The sheet opens with the fund's name, its ticker and
    "Holdings: As of 12-Nov-2026", then a header row found by its "Ticker" and
    "Weight" cells rather than counted to, as iShares' is.
    """
    with zipfile.ZipFile(io.BytesIO(body)) as z:
        names = z.namelist()
        sheet = next((n for n in sorted(names) if n.startswith("xl/worksheets/sheet")), None)
        if sheet is None:
            return [], None

        def part(name: str) -> bytes:
            if z.getinfo(name).file_size > _XLSX_PART_MAX:
                raise ValueError(f"{name} is too large to be a holdings sheet")
            return z.read(name)

        shared: list[str] = []
        if "xl/sharedStrings.xml" in names:
            for si in ElementTree.fromstring(part("xl/sharedStrings.xml")).iter(f"{_XLSX}si"):
                shared.append("".join(t.text or "" for t in si.iter(f"{_XLSX}t")))
        grid: list[dict[str, str]] = []
        for row in ElementTree.fromstring(part(sheet)).iter(f"{_XLSX}row"):
            cells: dict[str, str] = {}
            for c in row.iter(f"{_XLSX}c"):
                col = re.sub(r"\d", "", c.get("r") or "")
                v = c.find(f"{_XLSX}v")
                raw = v.text if v is not None and v.text else ""
                if c.get("t") == "s":
                    text = shared[int(raw)] if raw.isdigit() and int(raw) < len(shared) else ""
                elif c.get("t") == "inlineStr":
                    text = "".join(t.text or "" for t in c.iter(f"{_XLSX}t"))
                else:
                    text = raw
                cells[col] = text.strip()
            grid.append(cells)

    as_of: str | None = None
    cols: dict[str, str] | None = None
    rows: list[dict[str, Any]] = []
    for cells in grid:
        if cols is None:
            if cells.get("A", "").lower().startswith("holdings"):
                m = re.search(r"\d{1,2}-[A-Za-z]{3}-\d{4}", cells.get("B", ""))
                as_of = m.group(0) if m else as_of
            by_name = {v: k for k, v in cells.items()}
            if "Ticker" in by_name and "Weight" in by_name:
                cols = by_name
            continue
        # "BRK.B" is "BRK-B" on the tape the returns come from.
        sym = cells.get(cols["Ticker"], "").upper().replace(".", "-")
        if not _TICKER.match(sym):
            continue
        try:
            w = float(cells.get(cols["Weight"], ""))
        except ValueError:
            continue
        if w <= 0:
            continue
        name = cells.get(cols.get("Name", ""), "")
        sector = cells.get(cols.get("Sector", ""), "")
        rows.append({"symbol": sym, "name": name.title(),
                     "sector": "" if sector == "-" else sector, "weight": round(w, 4)})
    rows.sort(key=lambda x: -x["weight"])
    return rows, as_of


def _invesco_body(body: bytes) -> str | None:
    """Invesco's JSON with a holdings list in it, or why not."""
    bad = json_body(body)
    if bad:
        return bad
    return None if b'"holdings"' in body[:4000] else "Invesco's reply has no holdings in it"


def _xlsx_body(body: bytes) -> str | None:
    """A workbook is a zip, and a zip starts "PK". An error page does not."""
    return None if body[:2] == b"PK" else "State Street served something other than the workbook"


@dataclass(frozen=True)
class _Source:
    """One issuer's file for one index: where it is, and how to read it."""

    issuer: str
    url: str
    key: str
    validate: Callable[[bytes], str | None]
    parse: Callable[[FetchResult], tuple[list[dict[str, Any]], str | None]]


def _ishares(key: str, url: str) -> _Source:
    # `holdings2_`: a fresh key, so the HTML page the old URL left in the `holdings_`
    # entries is never read again. `_holdings_body` keeps the next web page from
    # replacing a good file.
    return _Source("iShares", url, f"holdings2_{key}", _holdings_body,
                   lambda r: parse_holdings(r.text))


#: Per index, in the order asked: iShares, then another issuer's fund on the same index.
SOURCES: dict[str, list[_Source]] = {
    "NQ": [
        _ishares("NQ", FUNDS[0][3]),
        _Source("Invesco QQQ", INVESCO_QQQ, "holdings_invesco_qqq", _invesco_body,
                lambda r: parse_invesco(r.body or b"")),
    ],
    "ES": [
        _ishares("ES", FUNDS[1][3]),
        _Source("SPDR SPY", SSGA_SPY, "holdings_ssga_spy", _xlsx_body,
                lambda r: parse_spdr(r.body or b"")),
    ],
}

#: A source's last failed or stale read, and when it may be asked again.
_held: dict[str, tuple[FetchResult, float]] = {}


def _read(s: _Source) -> FetchResult:
    """One source through the cache, not asked again within `RETRY_SEC` of failing."""
    now = time.time()
    held = _held.get(s.key)
    if held is not None and now < held[1]:
        return held[0]
    # TWO WEEKS OF FALLBACK, NOT FOUR DAYS (2026-11-14). At four days iShares' last
    # good file (read 07:09 ET on Thu 12 Nov) would have stopped being served at about
    # 07:10 ET on the Monday. A weight moves a few hundredths of a point in a
    # fortnight and the card prints the file's date, so an old file is a small error
    # that says what it is; no file is no card.
    r = fetch(s.url, key=s.key, ttl_sec=6 * 3600.0, ua=BROWSER_UA, timeout=40,
              stale_max_sec=14 * 86400.0, validate=s.validate)
    if not r.ok or r.source == "stale":
        _held[s.key] = (r, now + RETRY_SEC)
    else:
        _held.pop(s.key, None)
    return r


def _weights(key: str, st: SourceStatus,
             notes: list[str]) -> tuple[list[dict[str, Any]], str | None, str] | None:
    """The first source with a current file; failing that, the newest old copy.

    Only the read that is USED is counted on the status, so a dead first source
    behind a live second one does not date the card: the age chip is the age of
    the weights on screen.
    """
    old: tuple[_Source, FetchResult, list[dict[str, Any]], str | None] | None = None
    for s in SOURCES.get(key, []):
        r = _read(s)
        if not r.ok:
            notes.append(f"{key} weights, {s.issuer}: {r.error}")
            continue
        try:
            rows, as_of = s.parse(r)
        except (csv.Error, ValueError, KeyError, zipfile.BadZipFile, ElementTree.ParseError) as e:
            notes.append(f"{key} weights, {s.issuer}: parse: {e}")
            continue
        if not rows:
            notes.append(f"{key} weights, {s.issuer}: no equity rows found")
            continue
        if r.source != "stale":
            st.absorb(r)
            return rows, as_of, s.issuer
        notes.append(f"{key} weights, {s.issuer}: not answering ({r.error})")
        if old is None or (r.age_min or 0.0) < (old[1].age_min or 0.0):
            old = (s, r, rows, as_of)
    if old is None:
        return None
    st.absorb(old[1])
    return old[2], old[3], old[0].issuer
