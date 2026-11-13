"""
Insider trades, read from the SEC's Form 4s: the ones that are news.

THE ASK (owner, 2026-11-13): "it's not about entries, its about context though.. similar
to news. a insider buying or selling stocks is a big deal". A Form 4 is filed within two
business days of any trade by an officer, a director or a holder of 10% or more. Most of
them are pay and paperwork: stock awards (code A), option exercises (M), shares held back
for tax (F), gifts (G), and sales scheduled months ahead under a Rule 10b5-1 plan. A
megacap files dozens a month, which is why the filings under a name left Form 4 out
(sources/scanner.FORMS). What is news, and what this keeps:

  - an OPEN-MARKET BUY (code P) of BUY_MIN dollars or more: an insider spending their own
    money, which they do for one reason;
  - an OPEN-MARKET SALE (code S) of SELL_MIN dollars or more that was NOT under a 10b5-1
    plan (the form's own box since 2023, or its footnotes say so): a discretionary sale.

Each filing's lines are summed per side, so a buy done in ten fills at ten prices reads
as one buy at its average price. A trade is kept for WINDOW_DAYS. Context, never a score:
the rows carry it as a tag, a flag and a chip (collector._payload, the Setups table).

Pure but for `InsiderBook`'s file.
"""

from __future__ import annotations

import json
import os
import re
import xml.etree.ElementTree as ET
from datetime import date, timedelta
from typing import Any

from ..config import CACHE_DIR

STATE_FILE = os.path.join(CACHE_DIR, "insider_form4.json")
SEC_DOC = "https://www.sec.gov/Archives/edgar/data/{cik}/{acc}/{doc}"
#: The trades worth a line (module docstring).
BUY_MIN = 100_000.0
SELL_MIN = 1_000_000.0
WINDOW_DAYS = 30
#: Parsed filings are dropped from the file this long after they were filed.
KEEP_DAYS = 45
#: A filing whose document will not read is tried this many times, then left.
MAX_TRIES = 3

_TITLES = (
    (re.compile(r"\bchief executive|\bceo\b", re.I), "CEO"),
    (re.compile(r"\bchief financial|\bcfo\b", re.I), "CFO"),
    (re.compile(r"\bchief operating|\bcoo\b", re.I), "COO"),
    (re.compile(r"\bchief technology|\bcto\b", re.I), "CTO"),
    (re.compile(r"\bpresident\b", re.I), "President"),
    (re.compile(r"\bchair", re.I), "Chair"),
    (re.compile(r"\bgeneral counsel|chief legal", re.I), "General counsel"),
)
_PLAN = re.compile(r"10b5-1", re.I)
_NOT_PLAN = re.compile(r"\bnot\b[^.]{0,40}\b(?:pursuant|under)\b[^.]{0,40}10b5-1", re.I)


def form4_refs(doc: Any, cik: int, today: date, days: int = WINDOW_DAYS) -> list[dict[str, Any]]:
    """The Form 4s an EDGAR submissions JSON lists in the last `days`: each one's
    accession, when it was filed, the page to read it on and its raw XML. Pure."""
    try:
        r = doc["filings"]["recent"]
        forms = r["form"]
    except (KeyError, TypeError):
        return []
    cutoff = today - timedelta(days=days)
    out: list[dict[str, Any]] = []
    for i, form in enumerate(forms):
        try:
            filed = date.fromisoformat(r["filingDate"][i])
        except (ValueError, IndexError, KeyError, TypeError):
            continue
        if filed < cutoff:
            break  # newest first
        if form not in ("4", "4/A"):
            continue
        acc = str(r["accessionNumber"][i]).replace("-", "")
        page = str((r.get("primaryDocument") or [""] * len(forms))[i] or "")
        # The listed document is the SEC's styled page ("xslF345X05/form4.xml"); the
        # filing's own XML is the same name at the top of the folder.
        raw = page.rsplit("/", 1)[-1]
        if not raw.lower().endswith(".xml"):
            continue
        out.append({"acc": acc, "filed": filed.isoformat(), "form": form,
                    "url": SEC_DOC.format(cik=cik, acc=acc, doc=page),
                    "xml": SEC_DOC.format(cik=cik, acc=acc, doc=raw)})
    return out


def _text(el: ET.Element | None, path: str) -> str | None:
    if el is None:
        return None
    hit = el.find(path)
    if hit is None or hit.text is None:
        return None
    s = hit.text.strip()
    return s or None


def _num(s: str | None) -> float | None:
    try:
        return float(s) if s is not None else None
    except ValueError:
        return None


def _flag(s: str | None) -> bool:
    return (s or "").strip().lower() in ("1", "true")


def who_of(rel: ET.Element | None, name: str | None) -> str:
    """The insider in a word or two: the officer's title made short, else Director,
    10% owner or Insider; with their name. Pure."""
    title = _text(rel, "officerTitle")
    role = None
    if title:
        role = next((short for pat, short in _TITLES if pat.search(title)), title.strip()[:40])
    elif _flag(_text(rel, "isDirector")):
        role = "Director"
    elif _flag(_text(rel, "isTenPercentOwner")):
        role = "10% owner"
    role = role or "Insider"
    return f"{role} {name}" if name else role


def parse_form4(xml: str) -> dict[str, Any] | None:
    """A Form 4's XML → {"who", "symbol", "planned", "lines": [{code, date, shares,
    price, value, acquired}]}, the open-market lines only (codes P and S). None when the
    document will not read. Pure."""
    try:
        root = ET.fromstring(xml)
    except ET.ParseError:
        return None
    if root.tag != "ownershipDocument":
        return None
    owner = root.find("reportingOwner")
    name = _text(owner, "reportingOwnerId/rptOwnerName")
    rel = owner.find("reportingOwnerRelationship") if owner is not None else None
    notes = {fn.get("id"): "".join(fn.itertext()) for fn in root.iter("footnote")}
    plan_box = _flag(_text(root, "aff10b5One"))
    lines: list[dict[str, Any]] = []
    for tx in root.iter("nonDerivativeTransaction"):
        code = _text(tx, "transactionCoding/transactionCode")
        if code not in ("P", "S"):
            continue
        shares = _num(_text(tx, "transactionAmounts/transactionShares/value"))
        price = _num(_text(tx, "transactionAmounts/transactionPricePerShare/value"))
        refs = [f.get("id") for f in tx.iter("footnoteId")]
        said = " ".join(notes.get(r, "") for r in refs if r)
        planned = plan_box or (bool(_PLAN.search(said)) and not _NOT_PLAN.search(said))
        lines.append({
            "code": code, "date": _text(tx, "transactionDate/value"), "shares": shares,
            "price": price, "planned": planned,
            "value": shares * price if shares is not None and price is not None else None,
            "acquired": _text(tx, "transactionAmounts/transactionAcquiredDisposedCode/value"),
        })
    # A plan named only in a footnote no line points at still covers the form's sales,
    # unless it says the sales were not under one.
    loose = " ".join(notes.values())
    if _PLAN.search(loose) and not _NOT_PLAN.search(loose):
        for ln in lines:
            if ln["code"] == "S":
                ln["planned"] = True
    return {"who": who_of(rel, name), "symbol": _text(root, "issuer/issuerTradingSymbol"),
            "planned": plan_box, "lines": lines}


def notable(parsed: dict[str, Any], filed: str, url: str) -> list[dict[str, Any]]:
    """The trades in one parsed Form 4 that are news (module docstring): its open-market
    buys summed, kept at BUY_MIN; its discretionary sales summed, kept at SELL_MIN.
    Pure."""
    out: list[dict[str, Any]] = []
    for side, code, floor in (("buy", "P", BUY_MIN), ("sell", "S", SELL_MIN)):
        lines = [ln for ln in parsed.get("lines") or []
                 if ln["code"] == code and ln.get("value")
                 and not (side == "sell" and ln["planned"])]
        if not lines:
            continue
        value = sum(ln["value"] for ln in lines)
        shares = sum(ln["shares"] or 0.0 for ln in lines)
        if value < floor or shares <= 0:
            continue
        days = sorted(ln["date"] for ln in lines if ln.get("date"))
        out.append({"side": side, "who": parsed.get("who") or "Insider", "value": round(value),
                    "shares": round(shares), "price": round(value / shares, 2),
                    "date": days[-1] if days else filed, "filed": filed, "url": url})
    return out


def norm_sym(s: Any) -> str:
    """A ticker as the filings and the app both can match it: upper case, a class share's
    dash as a dot (BRK-B and BRK.B are one stock). Pure."""
    return str(s or "").strip().upper().replace("-", ".")


def money(v: float) -> str:
    """$1.2M, $340k, $2.1B. Pure."""
    a = abs(v)
    if a >= 1e9:
        return f"${v / 1e9:.1f}B"
    if a >= 1e6:
        return f"${v / 1e6:.1f}M"
    return f"${round(v / 1e3):.0f}k"


def line_of(t: dict[str, Any]) -> str:
    """One trade in words: "CEO Jane Doe bought $1.2M at $41.20 on 10 Nov". Pure."""
    try:
        d = date.fromisoformat(str(t["date"]))
        when = f"{d.day} {d.strftime('%b')}"
    except ValueError:
        when = str(t["date"])
    verb = "bought" if t["side"] == "buy" else "sold"
    return f"{t['who']} {verb} {money(t['value'])} at ${t['price']:,.2f} on {when}"


class InsiderBook:
    """The Form 4s read so far, by accession, kept on disk: a filing never changes, so
    each is fetched once. Written on the collector's SEC job thread."""

    def __init__(self, path: str = STATE_FILE) -> None:
        self.path = path
        #: accession → {"filed", "url", "trades": notable(...)}
        self.docs: dict[str, dict[str, Any]] = {}
        self.tries: dict[str, int] = {}
        self._load()

    def _load(self) -> None:
        try:
            with open(self.path, encoding="utf-8") as f:
                d = json.load(f)
        except (OSError, ValueError):
            return
        if isinstance(d, dict) and isinstance(d.get("docs"), dict):
            self.docs = {str(k): v for k, v in d["docs"].items() if isinstance(v, dict)}

    def save(self, today: date) -> None:
        cut = (today - timedelta(days=KEEP_DAYS)).isoformat()
        self.docs = {k: v for k, v in self.docs.items() if str(v.get("filed") or "") >= cut}
        tmp = self.path + ".tmp"
        try:
            os.makedirs(os.path.dirname(self.path) or ".", exist_ok=True)
            with open(tmp, "w", encoding="utf-8") as f:
                json.dump({"docs": self.docs}, f)
            os.replace(tmp, self.path)
        except OSError:
            pass

    def wanted(self, refs: list[dict[str, Any]]) -> list[dict[str, Any]]:
        """The refs not read yet and not given up on, newest first. A filing read before
        its issuer was kept, and that has a trade to show, is read again so the trade
        can be put under the right stock (`trades_of`)."""
        return [r for r in refs
                if (r["acc"] not in self.docs
                    or ("issuer" not in self.docs[r["acc"]] and self.docs[r["acc"]].get("trades")))
                and self.tries.get(r["acc"], 0) < MAX_TRIES]

    def take(self, ref: dict[str, Any], xml: str | None) -> bool:
        """Read one filing's XML in. True when it read."""
        parsed = parse_form4(xml) if xml else None
        if parsed is None:
            self.tries[ref["acc"]] = self.tries.get(ref["acc"], 0) + 1
            return False
        self.docs[ref["acc"]] = {"filed": ref["filed"], "url": ref["url"],
                                 "issuer": norm_sym(parsed.get("symbol")),
                                 "trades": notable(parsed, ref["filed"], ref["url"])}
        return True

    def trades_of(self, sym: str, today: date,
                  days: int = WINDOW_DAYS) -> list[dict[str, Any]]:
        """The notable trades IN `sym`'s stock over the last `days`, newest first.

        BY THE ISSUER ON THE FILING, NOT BY WHOSE LIST IT CAME FROM (2026-11-13). A
        company's EDGAR list carries the Form 4s it files as an OWNER too: HOOD's showed
        "10% owner Robinhood Markets, Inc. sold $3.1M at $24.77", which was Robinhood
        selling another company's shares, and the row read it as an insider sale of HOOD.
        Matching on the issuer also keeps a name's trades through a restart and whether
        or not the name is tracked: the book, not the day's list, holds them."""
        want = norm_sym(sym)
        cut = (today - timedelta(days=days)).isoformat()
        out = [t for d in self.docs.values() if want and d.get("issuer") == want
               for t in d.get("trades") or [] if str(t.get("date") or "") >= cut]
        out.sort(key=lambda t: (str(t.get("date") or ""), t.get("value") or 0), reverse=True)
        return out

    def trades(self, refs: list[dict[str, Any]], today: date,
               days: int = WINDOW_DAYS) -> list[dict[str, Any]]:
        """A name's notable trades over the last `days`, newest first."""
        cut = (today - timedelta(days=days)).isoformat()
        out = [t for r in refs for t in (self.docs.get(r["acc"]) or {}).get("trades") or []
               if str(t.get("date") or "") >= cut]
        out.sort(key=lambda t: (str(t.get("date") or ""), t.get("value") or 0), reverse=True)
        return out
