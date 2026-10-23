"""
Commitments of Traders — who is positioned which way in the three books.

WHY A NEWS TERMINAL CARRIES IT. The brief's own prompt listed COT positioning
as a thing the data did not have (owner, 2026-10-22: the assessment named it
first among the missing inputs). Positioning is not direction — a crowded
short does not say the market falls — but it says what a move will find:
forced buyers on a rally when the funds are short at a yearly extreme,
forced sellers on a break when they are long. That is the read the driver
board carries beside the day's votes, as context rather than a vote.

THE CFTC'S OWN API, free and keyless. The Traders in Financial Futures
report for the index futures (`gpe5-46if`: dealers, asset managers,
leveraged funds, other), the Disaggregated report for gold (`72hh-3qpy`:
producers, swap dealers, managed money, other). The speculative group whose
net the desk reads is LEVERAGED FUNDS for NQ and ES and MANAGED MONEY for GC
— the hedge funds, which is who the tape means by "positioning". The
consolidated index rows (big and e-mini together) are the ones read, as the
tape reads them. Weekly, as of Tuesday, published Friday afternoon, and the
row says which Tuesday.

A YEAR OF WEEKS, so the net can be ranked against itself: "net short 48k" is
a number, "the 12th percentile of the year" is a read.
"""

from __future__ import annotations

import urllib.parse
from datetime import date
from typing import Any

from ..http import SourceStatus, fetch, json_body

TFF = "https://publicreporting.cftc.gov/resource/gpe5-46if.json"
DISAGG = "https://publicreporting.cftc.gov/resource/72hh-3qpy.json"

#: book → (dataset, the CFTC's market name, the speculative group's columns,
#: the other group shown beside it)
MARKETS: dict[str, dict[str, Any]] = {
    "NQ": {"url": TFF, "name": "NASDAQ-100 Consolidated",
           "spec": ("Leveraged funds", "lev_money_positions_long", "lev_money_positions_short"),
           "other": ("Asset managers", "asset_mgr_positions_long", "asset_mgr_positions_short")},
    "ES": {"url": TFF, "name": "S&P 500 Consolidated",
           "spec": ("Leveraged funds", "lev_money_positions_long", "lev_money_positions_short"),
           "other": ("Asset managers", "asset_mgr_positions_long", "asset_mgr_positions_short")},
    "GC": {"url": DISAGG, "name": "GOLD",
           "spec": ("Managed money", "m_money_positions_long_all", "m_money_positions_short_all"),
           "other": ("Producers and merchants", "prod_merc_positions_long",
                     "prod_merc_positions_short")},
}
WEEKS = 60
#: Percentile of the year at or beyond which the net is "crowded".
CROWDED_LONG = 80.0
CROWDED_SHORT = 20.0
#: Six hours: the report lands once a week.
TTL_SEC = 6 * 3600.0
STALE_MAX_SEC = 21 * 86400.0


def _f(v: Any) -> float | None:
    try:
        return float(v)
    except (TypeError, ValueError):
        return None


def _day(v: Any) -> str | None:
    s = str(v or "")[:10]
    try:
        return date.fromisoformat(s).isoformat()
    except ValueError:
        return None


def summarise(rows: list[dict[str, Any]], spec: tuple[str, str, str],
              other: tuple[str, str, str]) -> dict[str, Any] | None:
    """A market's weekly rows (newest first) → the speculative net, its week
    change, its share of open interest, its percentile of the year, a word and
    the sentence. Pure. None without a current row."""
    nets: list[tuple[str, float, float, float]] = []
    for r in rows:
        d = _day(r.get("report_date_as_yyyy_mm_dd"))
        lo, sh = _f(r.get(spec[1])), _f(r.get(spec[2]))
        oi = _f(r.get("open_interest_all"))
        if d is None or lo is None or sh is None:
            continue
        nets.append((d, lo - sh, oi or 0.0, lo + sh))
    if not nets:
        return None
    nets.sort(key=lambda x: x[0], reverse=True)
    d, net, oi, _gross = nets[0]
    year = [n for _, n, _, _ in nets[:52]]
    pctile = round(sum(1 for n in year if n <= net) / len(year) * 100.0) if year else None
    prev = nets[1][1] if len(nets) > 1 else None
    chg = net - prev if prev is not None else None
    word = (None if pctile is None else "crowded long" if pctile >= CROWDED_LONG
            else "crowded short" if pctile <= CROWDED_SHORT else "middling")
    other_row = rows[0] if rows else {}
    olo, osh = _f(other_row.get(other[1])), _f(other_row.get(other[2]))
    side = "long" if net >= 0 else "short"
    bits = [f"{spec[0]} net {side} {abs(net):,.0f} contracts"]
    if oi:
        bits[0] += f" ({abs(net) / oi * 100.0:.0f}% of open interest)"
    if chg is not None:
        bits.append(f"{chg:+,.0f} on the week")
    if pctile is not None:
        bits.append(f"{pctile}th percentile of the year: {word}")
    read = ", ".join(bits) + "."
    if word == "crowded short":
        read += " A rally finds forced buyers; the dips are already sold."
    elif word == "crowded long":
        read += " A break finds forced sellers; room for a flush."
    elif word:
        read += " No positioning edge either way."
    return {
        "as_of": d, "spec": spec[0], "net": round(net),
        "prev": round(prev) if prev is not None else None,
        "chg": round(chg) if chg is not None else None, "oi": round(oi) if oi else None,
        "pct_oi": round(net / oi * 100.0, 1) if oi else None,
        "pctile": pctile, "word": word, "read": read,
        "other": None if olo is None or osh is None else {
            "label": other[0], "net": round(olo - osh)},
        "weeks": len(nets),
    }


def _query(url: str, name: str) -> str:
    q = urllib.parse.urlencode({
        "$where": f"contract_market_name='{name}'",
        "$order": "report_date_as_yyyy_mm_dd DESC",
        "$limit": str(WEEKS),
    })
    return f"{url}?{q}"


def collect() -> tuple[dict[str, Any], SourceStatus]:
    """Each book's positioning. One request per market."""
    st = SourceStatus("CFTC COT")
    books: dict[str, Any] = {}
    errors: list[str] = []
    for key, m in MARKETS.items():
        r = st.absorb(fetch(_query(m["url"], m["name"]), key=f"cot_{key}", ttl_sec=TTL_SEC,
                            timeout=30, stale_max_sec=STALE_MAX_SEC, validate=json_body))
        if not r.ok or r.body is None:
            errors.append(f"{key}: {r.error or 'empty'}")
            books[key] = {"ok": False, "error": r.error or "empty response"}
            continue
        try:
            rows = r.json()
        except ValueError as e:
            errors.append(f"{key}: parse {e}")
            books[key] = {"ok": False, "error": f"parse: {e}"}
            continue
        summary = summarise(rows if isinstance(rows, list) else [], m["spec"], m["other"])
        if summary is None:
            books[key] = {"ok": False, "error": "no rows for the market"}
            continue
        books[key] = {"ok": True, "market": m["name"], **summary}
    ok = sum(1 for b in books.values() if b.get("ok"))
    st.items = ok
    if errors:
        st.notes.extend(errors[:3])
    if ok == 0 and errors:
        st.error = "; ".join(errors[:2])
    st.settle(ok > 0, "market")
    return {"books": books}, st
