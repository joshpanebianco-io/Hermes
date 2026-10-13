"""
Rates — the curve, the policy rate, and what the market thinks happens next.

THREE SOURCES, THREE CLOCKS, DELIBERATELY NOT MERGED.

  Treasury    the par yield and real yield curves. A daily print, published
              late afternoon ET, US Government work.
  NY Fed      EFFR and SOFR — where policy ACTUALLY is today, published
              at 08:00 ET for the prior business day.
  CME (Yahoo) the 30-day fed funds futures strip — where the market thinks
              policy GOES. This is the same instrument CME's own FedWatch
              tool is built on.

WHY THE STRIP RATHER THAN A HEADLINE PROBABILITY. "72% chance of a cut in
March" is a derived, assumption-laden number: it needs a meeting calendar, an
assumed move size, and a convention for handling the month a meeting falls
mid-way through. The strip itself needs none of that — each contract settles to
the average daily fed funds rate over its month, so `100 − price` IS the
market's expected average policy rate for that month, and the difference
between two of them is the tightening or easing priced between them. That is
the honest primitive, and it is what this panel shows.
"""

from __future__ import annotations

import csv
import io
from datetime import UTC, datetime
from typing import Any

from ..config import UA
from ..http import SourceStatus, csv_body, fetch, json_body
from .quotes import _spark

TREASURY = (
    "https://home.treasury.gov/resource-center/data-chart-center/interest-rates/"
    "daily-treasury-rates.csv/{year}/all?type={kind}&field_tdr_date_value={year}"
    "&page&_format=csv"
)
NYFED = "https://markets.newyorkfed.org/api/rates/all/latest.json"

# CME month codes. The strip is built by walking forward from the current
# month, so this list is indexed by calendar month rather than searched.
MONTH_CODE = "FGHJKMNQUVXZ"

# Which tenors the curve panel shows. The full Treasury CSV carries thirteen;
# these are the ones that price the trades on this desk, and a curve panel that
# shows all thirteen is a table nobody reads.
NOMINAL = [("1 Mo", "1M"), ("3 Mo", "3M"), ("6 Mo", "6M"), ("1 Yr", "1Y"),
           ("2 Yr", "2Y"), ("5 Yr", "5Y"), ("10 Yr", "10Y"), ("30 Yr", "30Y")]


# (rows, the source's own as-of date, error) — a three-tuple rather than a
# dataclass because it has exactly one caller, twice.
CurveResult = tuple[list[dict[str, Any]], str | None, str | None]


def _curve(kind: str, key: str, wanted: list[tuple[str, str]],
           st: SourceStatus | None = None) -> CurveResult:
    """One Treasury CSV → today's level and yesterday's, per tenor.

    The file is the whole year, newest first, so a single request answers both
    the level and the change — and the change is computed from two rows of the
    SAME file, so it can never be a comparison against a differently-revised
    vintage.
    """
    year = datetime.now(UTC).year
    # Two days: the curve is a once-a-day print, so a day-old copy is the
    # latest one there is on a holiday, and anything older is a missed print.
    r = fetch(TREASURY.format(year=year, kind=kind), key=key, ttl_sec=3600.0, ua=UA, timeout=25,
              stale_max_sec=2 * 86400.0, validate=csv_body)
    if st is not None:
        st.absorb(r)
    if not r.ok or r.body is None:
        return [], None, r.error or "empty response"
    try:
        rows = list(csv.DictReader(io.StringIO(r.body.decode("utf-8-sig"))))
    except (UnicodeDecodeError, csv.Error) as e:
        return [], None, f"parse: {e}"
    if len(rows) < 2 or "Date" not in (rows[0] or {}):
        return [], None, "unexpected CSV shape"

    today, prior = rows[0], rows[1]
    out: list[dict[str, Any]] = []
    for col, label in wanted:
        try:
            v = float(today.get(col, "") or "nan")
            p = float(prior.get(col, "") or "nan")
        except ValueError:
            continue
        if v != v:  # NaN — the tenor was not published today
            continue
        out.append({
            "key": label,
            "label": label,
            "value": v,
            # In basis points, which is the unit a rate change is discussed in.
            "chg_bp": round((v - p) * 100, 1) if p == p else None,
        })
    return out, today.get("Date"), None


def _strip(months: int = 15,
           st: SourceStatus | None = None) -> tuple[list[dict[str, Any]], str | None]:
    """The fed funds futures strip → the market's expected policy path.

    `100 − price` is the contract's implied average fed funds rate for its
    delivery month. Fetched through the same batched spark endpoint the board
    uses, so the whole strip is one request.
    """
    now = datetime.now(UTC)
    codes: list[tuple[str, str, int, int]] = []
    y, m = now.year, now.month
    for _ in range(months):
        codes.append((f"ZQ{MONTH_CODE[m - 1]}{str(y)[2:]}.CBT", f"{y}-{m:02d}", y, m))
        m += 1
        if m > 12:
            m, y = 1, y + 1

    got, err = _spark([c[0] for c in codes], "1d", "1d", ttl=600.0, st=st, stale_max=86400.0)
    out: list[dict[str, Any]] = []
    for sym, ym, y, m in codes:
        resp = got.get(sym)
        if not resp:
            continue
        px = (resp.get("meta") or {}).get("regularMarketPrice")
        if px is None:
            continue
        out.append({
            "code": sym.replace(".CBT", ""),
            "month": ym,
            "label": datetime(y, m, 1).strftime("%b %y"),
            "price": px,
            "implied": round(100.0 - px, 4),
        })
    return out, err


def collect() -> tuple[dict[str, Any], SourceStatus]:
    """Everything the rates panel needs, in one object."""
    st = SourceStatus("Rates")
    notes: list[str] = []

    nominal, as_of, err_n = _curve("daily_treasury_yield_curve", "ust_nominal", NOMINAL, st)
    real, real_as_of, err_r = _curve("daily_treasury_real_yield_curve", "ust_real",
                                     [("5 YR", "5Y real"), ("10 YR", "10Y real"),
                                      ("30 YR", "30Y real")], st)
    if err_n:
        notes.append(f"nominal curve: {err_n}")
    if err_r:
        notes.append(f"real curve: {err_r}")

    by = {row["key"]: row["value"] for row in nominal}
    spreads: list[dict[str, Any]] = []
    if "2Y" in by and "10Y" in by:
        v = by["10Y"] - by["2Y"]
        spreads.append({
            "key": "2s10s", "label": "2s10s", "value": round(v * 100, 1), "unit": "bp",
            # The sign of this spread is the single most-watched recession
            # tell on the curve, so it is stated rather than left to be read
            # off a minus sign.
            "note": "inverted" if v < 0 else "positive",
        })
    if "3M" in by and "10Y" in by:
        v = by["10Y"] - by["3M"]
        spreads.append({"key": "3m10y", "label": "3m10y", "value": round(v * 100, 1),
                        "unit": "bp", "note": "inverted" if v < 0 else "positive"})
    if "5Y" in by and "30Y" in by:
        spreads.append({"key": "5s30s", "label": "5s30s",
                        "value": round((by["30Y"] - by["5Y"]) * 100, 1), "unit": "bp", "note": ""})

    real_by = {r["key"]: r["value"] for r in real}
    if "10Y" in by and "10Y real" in real_by:
        # The 10-year breakeven: nominal minus real. Arithmetic on two rows
        # already on screen, so it can never disagree with them.
        spreads.append({
            "key": "be10", "label": "10Y breakeven",
            "value": round(by["10Y"] - real_by["10Y real"], 3), "unit": "%",
            "note": "market-implied inflation, next 10 years",
        })

    # ---- where policy is now ------------------------------------------------
    policy: dict[str, Any] = {}
    r = st.absorb(fetch(NYFED, key="nyfed_rates", ttl_sec=3600.0, ua=UA, timeout=20,
                        stale_max_sec=2 * 86400.0, validate=json_body))
    if r.ok:
        try:
            for row in (r.json() or {}).get("refRates") or []:
                t = row.get("type")
                if t in {"EFFR", "SOFR"} and row.get("percentRate") is not None:
                    policy[t] = {"rate": row["percentRate"], "as_of": row.get("effectiveDate")}
        except (ValueError, TypeError, AttributeError) as e:
            notes.append(f"NY Fed: {e}")
    else:
        notes.append(f"NY Fed: {r.error}")

    # ---- where the market thinks it goes ------------------------------------
    strip, err_s = _strip(st=st)
    if err_s:
        notes.append(f"fed funds strip: {err_s}")

    path: dict[str, Any] = {}
    if strip:
        front = strip[0]["implied"]
        last = strip[-1]["implied"]
        # Signed, in basis points: negative is easing priced, positive is
        # tightening. Named `move_bp` rather than `cuts_bp` for exactly that
        # reason — a field called "cuts" holding a negative number when the
        # market prices hikes is a bug waiting to be read out loud.
        path = {
            "front": front,
            "front_label": strip[0]["label"],
            "horizon": last,
            "horizon_label": strip[-1]["label"],
            "move_bp": round((last - front) * 100, 1),
            "direction": "tightening" if last > front else ("easing" if last < front else "flat"),
        }
        effr = (policy.get("EFFR") or {}).get("rate")
        if effr is not None:
            path["vs_effr_bp"] = round((last - float(effr)) * 100, 1)

    ok = bool(nominal or strip or policy)
    st.items = len(nominal) + len(strip)
    st.notes = notes
    if notes and not ok:
        st.error = notes[0]
    st.settle(ok, "request")

    return {
        "curve": nominal,
        "real": real,
        "spreads": spreads,
        "policy": policy,
        "strip": strip,
        "path": path,
        "as_of": as_of,
        "real_as_of": real_as_of,
        "attribution": "U.S. Treasury (public domain) · NY Fed · CME via Yahoo",
    }, st
