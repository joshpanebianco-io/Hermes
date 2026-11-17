"""The cash market outside the session, wherever the app shows it (the audit of 2026-11-16).

The owner, after the Sectors cards and the Dashboard's game plan were found reading
Friday's session at 07:00 ET on a Monday: "can we do an audit everywhere to make sure we
dont have the same issue we had before with sectors in other places". At 08:16 ET the
audit found two more: the price board's US-listed funds (the SPY, QQQ and IWM tiles on
the Dashboard, Stocks and Sectors, the Macro board) read Friday's close (SPY 754.37 while
it traded 749.89), and the Macro tab's index movers read Friday's moves (NVDA -2.01%
while it traded -2.92%).

What is held here: a board fund carries its extended trade beside its regular price, a
pre-market read only on its own day and an after-hours one through the night; a row the
read does not cover, or a futures row, is untouched; the regular figures the engine reads
never change; before the bell each index member carries its own pre-market move and its
weight times that, and a name that has not traded says nothing.
"""

from __future__ import annotations

from typing import Any

from newsterminal.sources import constituents as cons
from newsterminal.sources import quotes as q

MON = "2026-11-16"


def row(key: str, last: float, pct: float) -> dict[str, Any]:
    return {"key": key, "last": last, "pct": pct, "feed": "closed"}


BOARD = [row("SPY", 754.37, -0.36), row("QQQ", 679.89, -1.20), row("NQ", 27668.0, -1.31),
         row("TLT", 79.38, -0.43)]


def test_a_board_fund_carries_its_pre_market_trade_beside_its_regular_price() -> None:
    ext = {"SPY": {"kind": "pre", "day": MON, "px": 749.89, "pct": -0.59, "at": 1, "bars": 40},
           "QQQ": {"kind": "pre", "day": "2026-11-13", "px": 680.0, "pct": 0.02, "at": 1},
           "NQ": {"kind": "pre", "day": MON, "px": 1.0, "pct": 9.0, "at": 1}}
    out = {r["key"]: r for r in q.with_ext(BOARD, ext, MON)}
    assert out["SPY"]["ext"] == {"kind": "pre", "px": 749.89, "pct": -0.59, "at": 1, "day": MON}
    # The engine's figures are the session's still.
    assert (out["SPY"]["last"], out["SPY"]["pct"]) == (754.37, -0.36)
    # Another day's pre-market is not this morning's; a future is not a board fund here.
    assert "ext" not in out["QQQ"] and "ext" not in out["NQ"] and "ext" not in out["TLT"]
    # The stored rows are not touched.
    assert "ext" not in BOARD[0]


def test_after_the_close_the_after_hours_trade_rides_through_the_night() -> None:
    ext = {"TLT": {"kind": "post", "day": "2026-11-13", "px": 79.5, "pct": 0.15, "at": 2}}
    out = {r["key"]: r for r in q.with_ext(BOARD, ext, MON)}
    assert out["TLT"]["ext"]["kind"] == "post" and out["TLT"]["ext"]["pct"] == 0.15


def test_the_read_covers_the_boards_funds_as_well_as_the_sectors() -> None:
    assert set(q.BOARD_EXT) == {"SPY", "QQQ", "IWM", "GLD", "HYG", "TLT"}


def test_before_the_bell_each_index_member_carries_its_own_pre_market_move() -> None:
    block = {"indices": {"NQ": {"label": "Nasdaq 100", "net_contribution": -1.06, "members": [
        {"symbol": "NVDA", "weight": 8.4, "pct": -2.01, "contribution": -0.1688},
        {"symbol": "AAPL", "weight": 7.5, "pct": 0.39, "contribution": 0.0293},
        {"symbol": "QUIET", "weight": 0.5, "pct": 0.1, "contribution": 0.0005},
    ]}}}
    pre = {"NVDA": -2.92, "AAPL": 0.41}
    out = cons.with_pre(block, pre.get)
    nq = out["indices"]["NQ"]
    by = {m["symbol"]: m for m in nq["members"]}
    assert (by["NVDA"]["pre_pct"], by["NVDA"]["pre_contribution"]) == (-2.92, -0.2453)
    # A name with no pre-market trade says nothing, and is not counted.
    assert by["QUIET"]["pre_pct"] is None and by["QUIET"]["pre_contribution"] is None
    assert nq["pre_traded"] == 2
    both = by["NVDA"]["pre_contribution"] + by["AAPL"]["pre_contribution"]
    assert nq["pre_net"] == round(both, 3)
    # The session's figures, which the engine's leaders read, are as they were.
    assert by["NVDA"]["pct"] == -2.01 and nq["net_contribution"] == -1.06
    assert out["pre"] is True and "pre" not in block
