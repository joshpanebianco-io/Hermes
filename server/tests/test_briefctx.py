"""The Market Report's Market Context (briefctx.py): three lines the engine writes.

The worked case is the close of Fri 20 Nov 2026, the figures the section was mocked on.
"""

from __future__ import annotations

from datetime import datetime
from typing import Any
from zoneinfo import ZoneInfo

from newsterminal import briefctx as bc

ET = ZoneInfo("America/New_York")
SAT = datetime(2026, 11, 21, 12, 0, tzinfo=ET)

OUTLOOK = {"ok": True, "label": "Fri 20 Nov · close", "name": "Forced selling",
           "what": "stocks, metals and bitcoin sold, bonds and oil bid",
           "tell": "Unusual: gold fell with stocks.",
           "sentiment": {"score": -78, "label": "Extreme fear"}}

#: The eleven and the two that are the market, as the snapshot had them that Friday.
SECTORS = [{"key": k, "label": label, "day_pct": d} for k, label, d in (
    ("XLP", "Cons. Staples", 0.67), ("XLV", "Health Care", -0.12), ("XLE", "Energy", -0.62),
    ("XLU", "Utilities", -0.74), ("XLRE", "Real Estate", -0.98), ("XLF", "Financials", -1.82),
    ("XLB", "Materials", -2.19), ("XLC", "Communication", -2.66),
    ("XLY", "Cons. Discretionary", -2.95), ("XLI", "Industrials", -3.09),
    ("XLK", "Technology", -7.27), ("SPY", "S&P 500", -3.64), ("RSP", "Equal weight", -1.98))]


def _asset(regime: str, flip: float, puts: list[float], calls: list[float] | None = None,
           em: tuple[float, float] | None = None) -> dict[str, Any]:
    levels = [{"key": "flip", "price": flip}]
    levels += [{"key": f"put_{i + 1}", "price": p} for i, p in enumerate(puts)]
    levels += [{"key": f"call_{i + 1}", "price": p} for i, p in enumerate(calls or [])]
    return {"ok": True, "regime": regime, "levels": levels,
            "em_lo": em[0] if em else None, "em_hi": em[1] if em else None}


NQ = _asset("NEG", 26790.0, [24719.0, 25749.0, 25955.0], em=(24284.0, 26298.0))
ES = _asset("NEG", 7249.0, [6982.0, 6932.0, 7032.0], em=(6764.0, 7169.0))


def _snap(**over: Any) -> dict[str, Any]:
    base: dict[str, Any] = {
        "outlook": OUTLOOK, "sectors": SECTORS, "sector_ext": {},
        "gex": {"enabled": True, "assets": {"NQ": NQ, "ES": ES}},
        "status": {"gex": {"ok": True, "source": "live"}},
        "quotes": [{"key": "NQ", "last": 25291.0}, {"key": "ES", "last": 6935.0},
                   {"key": "SPY", "last": 689.81}],
    }
    return {**base, **over}


def test_the_pulse_is_the_cards_scale_pattern_and_sentence() -> None:
    assert bc.pulse_line(OUTLOOK) == ("Extreme fear (-78). Forced selling: stocks, metals and "
                                      "bitcoin sold, bonds and oil bid. Unusual: gold fell with "
                                      "stocks.")
    # A quiet day has nothing sold or bid to name, and a record line may carry no scale.
    quiet = {"ok": True, "name": "Quiet", "what": "", "tell": "Nothing moved half a usual day.",
             "sentiment": None}
    assert bc.pulse_line(quiet) == "Quiet. Nothing moved half a usual day."
    assert bc.pulse_line({"ok": False, "why": "not read"}) is None and bc.pulse_line(None) is None


def test_the_rotation_names_both_ends_and_who_carried_the_day() -> None:
    assert bc.rotation_line(SECTORS) == (
        "1 of 11 sectors up. Leading: Cons. Staples +0.67%, Health Care -0.12%, Energy -0.62%. "
        "Lagging: Technology -7.27%, Industrials -3.09%, Cons. Discretionary -2.95%. "
        "Equal weight beat the S&P by 1.7 points: the selling was heaviest in the largest names.")
    # The mirror: an up day the largest names made, and one the average stock made.
    up = [{**s, "day_pct": -s["day_pct"]} for s in SECTORS]
    assert bc.rotation_line(up).endswith(
        "The S&P beat equal weight by 1.7 points: the largest names carried it.")
    broad = [{**s, "day_pct": 2.4 if s["key"] == "RSP" else 1.2 if s["key"] == "SPY"
              else abs(s["day_pct"])} for s in SECTORS]
    assert bc.rotation_line(broad).endswith(
        "Equal weight beat the S&P by 1.2 points: the average stock did better than the index.")
    # Close together, the two are not set against each other.
    near = [{**s, "day_pct": -3.3 if s["key"] == "RSP" else s["day_pct"]} for s in SECTORS]
    assert "Equal weight" not in bc.rotation_line(near) and "beat" not in bc.rotation_line(near)
    # Before the bell it says so, and leaves the equal-weight fund, which has hardly traded.
    pre = bc.rotation_line(SECTORS, pre=True)
    assert pre.startswith("Before the bell, 1 of 11 sectors up.") and "Equal weight" not in pre
    # Too few sectors with a move is no row at all.
    assert bc.rotation_line(SECTORS[:5]) is None
    assert bc.rotation_line([{**s, "day_pct": None} for s in SECTORS]) is None


def test_a_books_gamma_is_its_regime_its_flip_and_its_walls() -> None:
    assert bc.gamma_line("NQ", 25291.0, NQ, dp=0) == (
        "NQ 25,291: negative gamma, 1,499 below the flip at 26,790, so dealers chase moves and "
        "breaks run. Put walls 25,955, 25,749, 24,719. Expected move 24,284 to 26,298.")
    # A half tick prints as the report's own key levels print it (Last 25,126), and the
    # distance is between the two printed prices: 26,790 less 25,126.
    assert (bc.gamma_line("NQ", 25126.5, NQ, dp=0) or "").startswith(
        "NQ 25,126: negative gamma, 1,664 below the flip at 26,790,")
    # Each contract to its own decimals: gold to one, silver to three, a whole price whole.
    gc = _asset("NEG", 3692.0, [3602.0], em=(3432.0, 3646.0))
    assert (bc.gamma_line("GC", 3515.4, gc, dp=1) or "").startswith(
        "GC 3,515.4: negative gamma, 176.6 below the flip at 3,692,")
    assert (bc.gamma_line("SIL", 41.07, _asset("NEG", 42.0, [40.0]), dp=3) or "").startswith(
        "SIL 41.070: negative gamma, 0.930 below the flip at 42,")
    # Positive gamma, above the flip, with calls: its own words, and never a side.
    pos = _asset("POS", 82.0, [80.0], [86.0, 88.0, 87.0], em=(79.0, 89.0))
    assert bc.gamma_line("CL", 83.62, pos) == (
        "CL 83.62: positive gamma, 1.62 above the flip at 82, so dealers lean against moves and "
        "ranges tend to hold. Put wall 80. Call walls 86, 87, 88. Expected move 79 to 89.")
    # Two walls at one price are one wall (silver's that Friday: 43, 42, 42, 40).
    sil = _asset("NEG", 43.0, [42.0, 42.0, 40.0])
    assert "Put walls 42, 40." in (bc.gamma_line("SIL", 41.08, sil) or "")
    # Nothing from the feed for the book, or no price to place it by: no line.
    assert bc.gamma_line("GC", 3539.0, {"ok": False}) is None
    assert bc.gamma_line("GC", None, NQ) is None


def test_the_stocks_report_carries_spy_alone_in_spys_prices() -> None:
    ctx = bc.build(_snap(), ["SPY", "QQQ", "IWM"], etf=True, now=SAT)
    assert ctx is not None and ctx["as_of"] == "Fri 20 Nov · close"
    assert [r["label"] for r in ctx["rows"]] == ["Market Pulse", "Sector Rotation", "Dealer Gamma"]
    # The S&P future's levels by the live ratio of the two quotes (689.81 over 6,935), and
    # no expected move: that band is the future's own.
    assert ctx["rows"][2]["text"] == (
        "SPY 689.81: negative gamma, 31.23 below the flip at 721.04, so dealers chase moves "
        "and breaks run. Put walls 699.46, 694.48, 689.51.")


#: Fri 20 Nov 2026 in epoch seconds: the 16:00 ET close, the future's 17:00 last print, the
#: fund's last after-hours trade at 20:00; and Mon 23 Nov at 08:50 and 09:00 ET.
FRI_1600, FRI_1700, FRI_2000 = 1795208400.0, 1795212000.0, 1795222800.0
MON_0850, MON_0900, MON_0929, MON_1100 = 1795441800.0, 1795442400.0, 1795444140.0, 1795449600.0


def _spy_line(spy: dict[str, Any], es: dict[str, Any]) -> str:
    ctx = bc.build(_snap(quotes=[{"key": "SPY", **spy}, {"key": "ES", **es}]),
                   ["SPY", "QQQ", "IWM"], etf=True, now=SAT)
    return next(r["text"] for r in (ctx or {})["rows"] if r["key"] == "gamma")


def test_spy_is_the_price_trading_now_and_the_ratio_pairs_one_moment() -> None:
    # Over the weekend, as it stood: SPY closed 689.81, last traded after hours at 697.49
    # three hours after the future's last print. The line is about 697.49, the report's
    # own Last; the levels are converted with the close, the print nearest the future's.
    line = _spy_line(
        {"last": 689.81, "quote_time": FRI_1600, "ext": {"kind": "post", "px": 697.49,
                                                         "at": FRI_2000}},
        {"last": 6935.0, "quote_time": FRI_1700})
    assert line == ("SPY 697.49: negative gamma, 23.55 below the flip at 721.04, so dealers "
                    "chase moves and breaks run. Put walls 699.46, 694.48, 689.51.")
    # Monday 09:00 ET, when the report writes itself: the future is down 1% from Friday
    # and SPY's `last` is still Friday's close. Paired with the pre-market print the flip
    # sits where it did against the fund (7,249 x 683.00 / 6,865 = 721.20); Friday's close
    # over Monday's future would have put it at 728.40, seven dollars out.
    pre = _spy_line(
        {"last": 689.81, "quote_time": FRI_1600, "ext": {"kind": "pre", "px": 683.0,
                                                         "at": MON_0900}},
        {"last": 6865.0, "quote_time": MON_0850})
    assert pre.startswith("SPY 683: negative gamma, 38.20 below the flip at 721.20,")
    # In the session the regular price is the newest, and the morning's pre-market print
    # is not taken for it.
    rth = _spy_line(
        {"last": 695.0, "quote_time": MON_1100, "ext": {"kind": "pre", "px": 683.0,
                                                        "at": MON_0929}},
        {"last": 6985.0, "quote_time": MON_1100})
    assert rth.startswith("SPY 695: negative gamma, 26.27 below the flip at 721.27,")
    # No stamps to pair by (an older row): the regular price, as before.
    assert bc.fund_prices({"last": 689.81}, None) == (689.81, 689.81)
    assert bc.fund_prices({"last": 689.81, "ext": {"px": 697.49}}, FRI_1700) == (689.81, 689.81)


def test_a_futures_report_carries_its_own_books() -> None:
    ctx = bc.build(_snap(), ["NQ"], etf=False, now=SAT)
    assert ctx is not None and [r["key"] for r in ctx["rows"]] == ["pulse", "rotation", "gamma"]
    assert ctx["rows"][2]["text"].startswith("NQ 25,291: negative gamma, 1,499 below the flip")
    # The book's own decimals reach the line: NQ whole, on a half tick too.
    half = _snap(quotes=[{"key": "NQ", "last": 25126.5}])
    assert bc.build(half, ["NQ"], etf=False, now=SAT)["rows"][2]["text"].startswith(
        "NQ 25,126: negative gamma, 1,664 below the flip at 26,790")
    # Two books in scope (an older Indexes report): a line each.
    both = bc.build(_snap(), ["NQ", "ES"], etf=False, now=SAT)
    assert both is not None and [r["text"][:2] for r in both["rows"] if r["key"] == "gamma"] == \
        ["NQ", "ES"]


def test_a_source_with_nothing_to_say_leaves_its_row_out() -> None:
    # The gamma feed off, failing or serving a cached copy: a stale wall is worse than none.
    for gex, status in (({"enabled": False}, {"ok": True}),
                        ({"enabled": True, "assets": {"NQ": NQ}}, {"ok": False}),
                        ({"enabled": True, "assets": {"NQ": NQ}}, {"ok": True, "source": "stale"})):
        ctx = bc.build(_snap(gex=gex, status={"gex": status}), ["NQ"], etf=False, now=SAT)
        assert ctx is not None and [r["key"] for r in ctx["rows"]] == ["pulse", "rotation"]
    # Nothing read at all: no section, and nothing for the model.
    assert bc.build({}, ["NQ"], etf=False, now=SAT) is None
    assert bc.for_model(None) is None


def test_before_the_bell_the_rotation_is_the_funds_pre_market() -> None:
    mon = datetime(2026, 11, 23, 8, 30, tzinfo=ET)
    ext = {s["key"]: {"kind": "pre", "day": "2026-11-23", "pct": -s["day_pct"] / 10}
           for s in SECTORS}
    ctx = bc.build(_snap(sector_ext=ext), ["NQ"], etf=False, now=mon)
    row = next(r for r in (ctx or {})["rows"] if r["key"] == "rotation")
    # Monday's pre-market moves, not Friday's session: technology leads here.
    assert row["text"].startswith(
        "Before the bell, 10 of 11 sectors up. Leading: Technology +0.73%")


def test_the_model_reads_the_lines_the_page_prints() -> None:
    ctx = bc.build(_snap(), ["NQ"], etf=False, now=SAT)
    seen = bc.for_model(ctx)
    assert seen is not None and seen["as_of"] == "Fri 20 Nov · close"
    assert seen["lines"][0].startswith("Market Pulse: Extreme fear (-78).")
    assert seen["lines"][2].startswith("Dealer Gamma: NQ 25,291:")
    assert "none is a side" in seen["what_this_is"]


#: The card's rows that Friday, as outlook.py hands them on.
PULSE_ROWS = [
    {"key": "ES", "group": "Stocks", "name": "S&P 500", "pct": -3.6437, "mult": -3.42,
     "sized": True},
    {"key": "ZN", "group": "Bonds", "name": "US 10-year", "pct": 0.87, "mult": 2.81,
     "sized": True},
    {"key": "GC", "group": "Gold", "name": "Gold", "pct": -4.62, "mult": -3.3, "sized": True},
]


def test_the_panels_carry_the_figures_the_page_charts() -> None:
    ctx = bc.build(_snap(outlook={**OUTLOOK, "rows": PULSE_ROWS}), ["NQ"], etf=False, now=SAT)
    assert ctx is not None and bc.panels(ctx) == ["pulse", "rotation", "gamma"]
    # The Market Pulse: the scale's reading and a bar a market.
    pulse = ctx["pulse"]
    assert (pulse["score"], pulse["label"], pulse["name"]) == (-78, "Extreme fear",
                                                              "Forced selling")
    assert pulse["rows"][0] == {"key": "ES", "group": "Stocks", "name": "S&P 500",
                                "pct": -3.64, "mult": -3.4, "sized": True}
    # The sectors best to worst, the count, and the index against its equal-weight twin.
    rot = ctx["rotation"]
    assert (rot["up"], rot["down"], rot["n"], rot["pre"]) == (1, 10, 11, False)
    assert [s["key"] for s in rot["sectors"]][:2] == ["XLP", "XLV"]
    assert rot["sectors"][-1] == {"key": "XLK", "label": "Technology", "pct": -7.27}
    assert (rot["spy"], rot["rsp"]) == (-3.64, -1.98)
    assert rot["breadth"] == ("Equal weight beat the S&P by 1.7 points: the selling was "
                              "heaviest in the largest names.")
    # The gamma map: the price, the flip, the walls high to low, the level next to the
    # price on each side with how far it is, and the future's expected move.
    (g,) = ctx["gamma"]
    assert (g["name"], g["last"], g["dp"], g["regime"]) == ("NQ", 25291.0, 0, "NEG")
    assert (g["flip"], g["to_flip"], g["below_flip"]) == (26790.0, 1499.0, True)
    assert g["puts"] == [25955.0, 25749.0, 24719.0] and g["calls"] == []
    assert g["above"] == {"kind": "put", "price": 25749.0, "away": 458.0}
    assert g["below"] == {"kind": "put", "price": 24719.0, "away": 572.0}
    assert g["em"] == [24284.0, 26298.0]
    # The engine's line a panel is still there, and says what the map says.
    assert ctx["rows"][2]["text"] == bc.gamma_text(g)


def test_spy_has_no_expected_move_and_a_panel_with_nothing_is_not_there() -> None:
    ctx = bc.build(_snap(), ["SPY", "QQQ", "IWM"], etf=True, now=SAT)
    assert ctx is not None and ctx["gamma"][0]["name"] == "SPY" and ctx["gamma"][0]["em"] is None
    # Before the bell the index is not set against equal weight: no pair, no sentence.
    pre = bc.rotation_data(SECTORS, pre=True)
    assert pre is not None and (pre["spy"], pre["rsp"], pre["breadth"]) == (None, None, None)
    # The gamma feed off: two panels, and the model is told which.
    off = bc.build(_snap(gex={"enabled": False}), ["NQ"], etf=False, now=SAT)
    assert off is not None and "gamma" not in off and bc.panels(off) == ["pulse", "rotation"]
    assert bc.for_model(off)["panels"] == ["pulse", "rotation"]
    assert bc.panels(None) == [] and bc.panels({"rows": []}) == []


def test_the_model_reads_every_figure_a_chart_prints() -> None:
    ctx = bc.build(_snap(outlook={**OUTLOOK, "rows": PULSE_ROWS}), ["NQ"], etf=False, now=SAT)
    seen = bc.for_model(ctx)
    assert seen is not None and seen["panels"] == ["pulse", "rotation", "gamma"]
    # A market's move as its bar's figure prints it (one decimal), and its size.
    assert seen["market_pulse"]["markets"][0] == {
        "market": "S&P 500", "move_pct": -3.6, "times_its_usual_day": 3.4}
    assert seen["market_pulse"]["markets"][1]["market"] == "Bonds"
    assert (seen["market_pulse"]["score"], seen["market_pulse"]["reading"]) == (-78,
                                                                            "Extreme fear")
    rot = seen["sector_rotation"]
    assert (rot["sectors_up"], rot["sectors_down"], rot["of"]) == (1, 10, 11)
    assert rot["best_to_worst"][-1] == {"sector": "Technology", "move_pct": -7.27}
    assert (rot["sp500_pct"], rot["equal_weight_sp500_pct"]) == (-3.64, -1.98)
    # The gamma map's prices are handed over as the map prints them, so the paragraph
    # under it says "26,790" and not the bare float.
    (g,) = seen["dealer_gamma"]
    assert g["regime"] == "negative gamma" and g["price_is"] == "below the flip"
    assert (g["price"], g["flip"], g["distance_to_flip"]) == ("25,291", "26,790", "1,499")
    assert g["put_walls"] == ["25,955", "25,749", "24,719"] and g["call_walls"] == []
    assert g["nearest_level_above"] == {"level": "Put wall", "price": "25,749", "away": "458"}
    assert g["expected_move"] == {"low": "24,284", "high": "26,298"}
