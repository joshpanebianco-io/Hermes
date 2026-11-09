"""
What the theme funds hold, so a card on the Sectors page can list its stocks.

WHY (owner, 2026-11-09: a sector heat map like the one in the screenshots). Nine
themes map cleanly onto TradingView's `industry`: every biotech, every regional bank.
The rest are baskets no industry describes (cybersecurity, cloud, quantum, space, solar),
so only the fund can say what is in them. Solar is why that had to be checked against
the funds: TradingView's `Alternative Power Generation` is Brookfield and Talen, and it
files First Solar and Sunrun as chipmakers.

YAHOO NAMES THE TOP TEN AND NO MORE, so these lists are short, and the page says so.
Holdings move slowly: a week between reads, one fund a tick, and what was last read
is kept on disk, so a restart reads nothing.

FIVE FUNDS ARE MOSTLY FOREIGN LISTINGS. DRAM's top ten is Samsung, SK Hynix and cash;
FXI's is Hong Kong lines that trade in no US session. Their own lists cannot answer
what a US trader is asking, so US_LISTED names the American lines that trade with the
theme. That is a judgement, not the fund's holdings, and the page labels it as one.

OIL & GAS E&P IS HAND-WRITTEN TOO, for another reason. TradingView files EOG, Devon and
Occidental under `Integrated Oil` with Exxon and Shell, and XOP's own top ten mixes in
Exxon, Chevron and a refiner, so neither says who the American producers are.

Personal use only, like every other Yahoo read here. Optional as well: a card whose
list has not arrived still shows its ETF.
"""

from __future__ import annotations

import json
import time
from datetime import UTC, datetime
from typing import Any

from ..http import CACHE, SourceStatus
from .shortint import YahooSession

#: The themes no industry describes, whose members only the fund can name.
FUNDS: tuple[str, ...] = ("CIBR", "SKYY", "QTUM", "ARKK", "PAVE", "WGMI", "NASA", "GRID", "BOTZ",
                          "TAN", "DRAM", "URA", "COPX", "KWEB", "FXI")

#: The American lines that trade with a theme its fund cannot describe (module docstring).
#: Hand-written (2026-11-09), each checked against the screener that day.
US_LISTED: dict[str, tuple[str, ...]] = {
    # TradingView's two producer groups, American names only, less the majors, midstream
    # and services. No fund behind it, so Yahoo is never asked.
    "XOP": ("COP", "EOG", "OXY", "FANG", "DVN", "EQT", "EXE", "PR", "OVV", "APA", "RRC", "AR",
            "CHRD", "SM", "MGY", "MTDR", "MUR", "CNX", "CRGY", "CRC", "CRK", "GPOR", "TALO",
            "NOG", "BKV", "MNR", "KOS", "REPX", "HPK", "DEC", "INR", "TXO", "GRNT", "VTS",
            "EGY", "WTI", "SD", "SOC", "FTW"),
    "DRAM": ("MU", "WDC", "STX", "SNDK"),
    "URA": ("CCJ", "UEC", "NXE", "UUUU", "DNN", "LEU", "OKLO"),
    "COPX": ("FCX", "SCCO", "TECK", "HBM", "ERO"),
    "KWEB": ("BABA", "PDD", "JD", "BIDU", "NTES", "TCOM", "BILI", "TME", "VIPS"),
    "FXI": ("BABA", "JD", "BIDU", "NTES", "TCOM", "NIO", "XPEV", "LI", "BEKE", "YUMC", "ZTO"),
}

#: Names below a fund's top ten that the owner's reference screenshots tag to the theme
#: (2026-11-09). Yahoo stops at ten, which left AMD out of Quantum and CrowdStrike out of
#: Cloud. Only what those screenshots show, so these lists stay partial.
BEYOND_TOP_TEN: dict[str, tuple[str, ...]] = {
    "CIBR": ("MSFT", "IBM", "ANET"),
    "SKYY": ("CSCO", "PANW", "CRWD"),
    "QTUM": ("NVDA", "AMD", "MU", "INTC"),
    "ARKK": ("AMD", "AVGO", "PLTR"),
}

MODULE = "topHoldings"
TICK_SEC = 30.0
TTL_SEC = 7 * 24 * 3600.0
PAUSE_SEC = 900.0
FAIL_BASE = 600.0
FAIL_CAP = 6 * 3600.0


def _ours(sym: str) -> str:
    """Yahoo's BRK-B is the screener's BRK.B; a foreign line keeps its suffix, matching nothing."""
    return sym.replace("-", ".") if "." not in sym else sym


def parse(doc: Any) -> list[str] | None:
    """A quoteSummary document → the fund's holdings in the screener's symbols. Pure."""
    try:
        rows = doc["quoteSummary"]["result"][0]["topHoldings"]["holdings"]
    except (KeyError, IndexError, TypeError):
        return None
    if not isinstance(rows, list):
        return None
    names = [_ours(str(x.get("symbol") or "").strip().upper()) for x in rows if isinstance(x, dict)]
    return [s for s in names if s] or None


class HoldingsStore:
    """The funds' lists between reads. Its own cookie and crumb: it runs on the wide thread."""

    def __init__(self) -> None:
        self.session = YahooSession()
        self.data: dict[str, list[str]] = {}
        self.at: dict[str, float] = {}
        self.fails: dict[str, tuple[int, float]] = {}
        self.pause_until = 0.0
        self._warm = False

    def _warm_start(self) -> None:
        self._warm = True
        now = time.time()
        for fund in FUNDS:
            key = f"holdings_{fund}"
            blob, age = CACHE.read(key), CACHE.age_sec(key)
            if blob is None or age is None:
                continue
            try:
                got = json.loads(blob)
            except ValueError:
                continue
            if isinstance(got, list):
                self.data[fund] = [str(s) for s in got]
                self.at[fund] = now - age

    def due(self, t: float) -> list[str]:
        """The funds to read, longest unread first."""
        out: list[tuple[float, str]] = []
        for fund in FUNDS:
            n, until = self.fails.get(fund, (0, 0.0))
            if n and t < until:
                continue
            age = t - self.at.get(fund, 0.0)
            if age >= TTL_SEC:
                out.append((-age, fund))
        return [f for _, f in sorted(out)]

    def fetch_one(self, fund: str, t: float) -> str | None:
        code, body = self.session.summary(fund, MODULE)
        if code == 429:
            self.pause_until = t + PAUSE_SEC
        if code != 200 or not body:
            n = self.fails.get(fund, (0, 0.0))[0] + 1
            self.fails[fund] = (n, t + min(FAIL_BASE * 2 ** (n - 1), FAIL_CAP))
            return f"HTTP {code}" if code else "no crumb from Yahoo"
        try:
            names = parse(json.loads(body))
        except ValueError:
            names = None
        if names is None:
            self.at[fund] = t  # nothing to read: not again for a while
            return "no holdings in the reply"
        self.data[fund] = names
        self.at[fund] = t
        self.fails.pop(fund, None)
        CACHE.write(f"holdings_{fund}", json.dumps(names).encode())
        return None

    def tick(self, now: datetime | None = None) -> tuple[SourceStatus, bool]:
        """At most one fund read. Returns (status, whether a read happened)."""
        now = now or datetime.now(UTC)
        t = now.timestamp()
        if not self._warm:
            self._warm_start()
        st = SourceStatus("Fund holdings")
        read = False
        if t >= self.pause_until:
            for fund in self.due(t)[:1]:
                read = True
                err = self.fetch_one(fund, t)
                if err:
                    st.error = f"{fund}: {err}"
        have = [f for f in FUNDS if f in self.data]
        st.items = len(have)
        st.ok = bool(have)
        st.source = "live" if st.ok else "unavailable"
        st.age_min = max((t - self.at[f]) / 60.0 for f in have) if have else None
        if st.ok:
            st.last_ok_utc = datetime.now(UTC).isoformat()
        missing = [f for f in FUNDS if f not in self.data]
        if missing:
            st.notes.append(f"no list yet: {', '.join(missing[:5])}")
        return st, read

    def members(self) -> dict[str, frozenset[str]]:
        """Each theme's names: the fund's top ten, and the hand-written names it has."""
        out: dict[str, frozenset[str]] = {}
        for key in dict.fromkeys((*FUNDS, *US_LISTED)):
            top = self.data.get(key) or ()
            # A fund not read yet stays off the filters rather than offering three names.
            below = BEYOND_TOP_TEN.get(key, ()) if top else ()
            names = {*top, *US_LISTED.get(key, ()), *below}
            if names:
                out[key] = frozenset(names)
        return out
