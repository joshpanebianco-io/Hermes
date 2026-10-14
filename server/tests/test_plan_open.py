"""The Game plan's pre-open mode (owner, 2026-10-14: "do what you recommend
all at once") — final-level targets, if/then triggers, no filler cards, and the
clock and the release risks written by the server from the calendar.

The names below are the 05:18 ET facts of 2026-10-14, the plan that took
GME's still-forming pre-market high as its target and filled four cards with
"No trade — price has not broken the pre-market low".
"""

from __future__ import annotations

from datetime import date
from typing import Any

from newsterminal import stockplan as sp


def _n(sym: str, side: str, kind: str, entry: float, last: float, *, pdh: float, pdl: float,
       pmh: float, pml: float, pdc: float, atr_b: float, atr_d: float,
       forming: bool = True, em: tuple[int, float, float] | None = None,
       session: str = "pre") -> dict[str, Any]:
    n: dict[str, Any] = {
        "sym": sym, "side": side, "entry": {"kind": kind, "price": entry, "dist_atr": 1.0},
        "last": last, "atr_b": atr_b, "atr_d": atr_d, "pm_forming": forming,
        "levels": {"pdh": pdh, "pdl": pdl, "pmh": pmh, "pml": pml, "pdc": pdc},
        "options": None if em is None else {"em_front_dte": em[0], "em_front_hi": em[1],
                                            "em_front_lo": em[2]},
    }
    n["targets"] = sp.target_candidates(n)
    n["invalid_if"] = sp.invalid_if(n)
    n["open_if"] = sp.open_if(n) if session in sp.OPEN_SESSIONS else None
    return n


def GME(**kw: Any) -> dict[str, Any]:
    return _n("GME", "long", "PDH", 27.53, 27.69, pdh=27.53, pdl=26.75, pmh=27.78, pml=27.56,
              pdc=27.22, atr_b=0.12, atr_d=0.99, **kw)


def DELL() -> dict[str, Any]:
    return _n("DELL", "short", "PML", 552.66, 555.03, pdh=579.74, pdl=548.4, pmh=576.77,
              pml=552.66, pdc=572.47, atr_b=3.38, atr_d=26.66)


def SPY() -> dict[str, Any]:
    return _n("SPY", "long", "PDH", 778.75, 779.94, pdh=778.75, pdl=775.95, pmh=779.98,
              pml=778.01, pdc=778.01, atr_b=0.44, atr_d=5.86, em=(0, 783.85, 775.53))


def _facts(*names: dict[str, Any], session: str = "pre", events: list[Any] | None = None,
           ) -> dict[str, Any]:
    return {"session": session, "trading_day": "2026-10-14", "names": list(names),
            "events": events or []}


def _plan(sym: str, side: str = "long", **kw: str) -> dict[str, Any]:
    return {"sym": sym, "side": side, "conviction": 3, "plan": kw.pop("plan", f"{sym} plan"),
            "trigger": kw.get("trigger", "Retest of the level"),
            "invalidation": kw.get("invalidation", ""), "target": kw.get("target", ""),
            "options": "o", "why": ["Structure: s", "RS: r", "Macro: m", "News: n"]}


# -------------------------------------------------------------------- targets


def test_a_forming_pre_market_high_is_never_a_target_before_the_open() -> None:
    # GME long at PDH 27.53, last 27.69: the floor is 1.5 × 0.12 = 0.18 past the
    # entry (27.71) and past the last price. PMH 27.78 is still forming; PDL and
    # the previous close are below; a day's range from the close (27.22 + 0.99)
    # is the one final candidate.
    assert GME()["targets"] == [{"label": "a day's average range from the close",
                                 "price": 28.21}]
    # Once the pre-market locks (in the session), PMH 27.78 is 0.25 past the
    # entry and past the last — a target, and the nearest.
    locked = GME(forming=False, session="rth")
    assert locked["targets"][0] == {"label": "PMH", "price": 27.78}


def test_a_level_nearer_than_a_stop_and_a_half_is_not_a_target() -> None:
    # DELL short at PML 552.66 with a 3.38 ten-minute ATR: the floor is 5.07, so
    # a target must sit at or below 547.59. PDL 548.4 is 4.26 away — 1.26 ATRs.
    t = DELL()["targets"]
    assert all(c["label"] != "PDL" for c in t)
    assert t == [{"label": "a day's average range from the close", "price": 545.81}]


def test_the_same_day_straddle_is_a_target_and_a_near_twin_is_dropped() -> None:
    # SPY's 0DTE straddle high 783.85; its day-range 778.01 + 5.86 = 783.87 says
    # the same thing 0.02 away, inside half a reach (0.33), and is not repeated.
    assert SPY()["targets"] == [{"label": "today's expected-move high", "price": 783.85}]


# ------------------------------------------------------------------ enforcing


def test_pre_open_target_and_trigger_are_replaced_and_the_fixes_say_why() -> None:
    body = {"headline": "h", "plans": [_plan("GME", target="PMH 27.78.",
                                             invalidation="A close below the PDH 27.53")]}
    out = sp.sanitize_plan(body, _facts(GME()))
    assert out is not None
    p = out["plans"][0]
    assert p["target"] == "28.21 (a day's average range from the close)"
    assert p["trigger"].startswith("If it opens above PDH 27.53 and the first 10-minute bar")
    assert p["invalidation"] == "A close below the PDH 27.53"            # stands
    assert [(f["field"], f["was"]) for f in p["fixes"]] == [
        ("trigger", "Retest of the level"), ("target", "PMH 27.78.")]
    assert "still forming" in p["fixes"][1]["why"]
    # The replaced fields are the server's words: the guard does not read them.
    prose = sp.plan_prose(out)
    assert "PMH 27.78." not in prose and p["target"] not in prose


def test_a_conditional_trigger_and_a_valid_target_stand() -> None:
    body = {"headline": "h", "plans": [_plan(
        "SPY", trigger="If SPY holds PDH 778.75 into the open, the retest of it",
        target="The expected-move high 783.85", invalidation="A 10-minute close below 778.75")]}
    p = sp.sanitize_plan(body, _facts(SPY()))["plans"][0]  # type: ignore[index]
    assert p["fixes"] == []
    assert p["target"] == "The expected-move high 783.85"


def test_before_the_open_even_a_conditional_trigger_is_the_rules_words() -> None:
    # The live replay's CRWV: the model copied the if/then and wrote "PDH" for
    # PDL in its last clause. Same figure, so only replacing it catches it.
    crwv = _n("CRWV", "short", "PDL", 76.12, 75.4, pdh=80.5, pdl=76.12, pmh=79.0, pml=75.2,
              pdc=77.85, atr_b=0.6, atr_d=4.84)
    slip = ("If it opens below PDL 76.12 and the first 10-minute bar closes below it: the "
            "retest of PDL 76.12 from below that holds. If it opens above, it needs a "
            "10-minute close below PDH 76.12 first.")
    body = {"headline": "h", "plans": [_plan("CRWV", "short", trigger=slip)]}
    p = sp.sanitize_plan(body, _facts(crwv))["plans"][0]  # type: ignore[index]
    assert p["trigger"].endswith("a 10-minute close below PDL 76.12 first.")
    assert all(f["field"] != "trigger" for f in p["fixes"])   # a copy, not a correction


def test_the_rules_own_invalidation_back_is_not_a_fix() -> None:
    # DELL's PML is still forming, but "…once it locks." is invalid_if's own text.
    said = "A 10-minute close back above PML 552.66 once it locks."
    assert DELL()["invalid_if"] == said
    body = {"headline": "h", "plans": [_plan("DELL", "short", trigger="If it", invalidation=said)]}
    p = sp.sanitize_plan(body, _facts(DELL()))["plans"][0]  # type: ignore[index]
    assert p["invalidation"] == said
    assert all(f["field"] != "invalidation" for f in p["fixes"])


def test_an_invalidation_on_the_profit_side_is_replaced() -> None:
    body = {"headline": "h", "plans": [_plan("SPY", trigger="If it holds",
                                             target="783.85", invalidation="Above 781")]}
    p = sp.sanitize_plan(body, _facts(SPY()))["plans"][0]  # type: ignore[index]
    assert p["invalidation"] == "A 10-minute close back below PDH 778.75."
    assert p["fixes"][0]["field"] == "invalidation"


def test_in_the_session_the_trigger_is_the_models_own() -> None:
    gme = GME(forming=False, session="rth")
    body = {"headline": "h", "plans": [_plan("GME", target="PMH 27.78")]}
    p = sp.sanitize_plan(body, _facts(gme, session="rth"))["plans"][0]  # type: ignore[index]
    assert p["trigger"] == "Retest of the level" and p["target"] == "PMH 27.78"
    assert p["fixes"] == []


def test_spy_carries_no_relative_strength_against_itself() -> None:
    body = {"headline": "h", "plans": [_plan("SPY", trigger="If it holds", target="783.85")]}
    p = sp.sanitize_plan(body, _facts(SPY()))["plans"][0]  # type: ignore[index]
    assert [w.split(":")[0] for w in p["why"]] == ["Structure", "Macro", "News"]


def test_prices_skip_percentages_times_and_bar_lengths() -> None:
    n = GME()
    assert sp._prices("PMH 27.78 at 09:30 on the 10-minute chart, 2.5% move, 28 x", n) == [27.78]


# ---------------------------------------------------------------- no filler


def test_a_no_trade_card_becomes_one_watch_line_with_the_open_condition() -> None:
    dash = {"sym": "DELL", "side": "short", "conviction": 1,
            "plan": "No trade – price has not broken the pre-market low.",
            "trigger": "–", "invalidation": "–", "target": "–", "options": "–", "why": []}
    out = sp.sanitize_plan({"headline": "h", "plans": [dash]}, _facts(DELL()))
    assert out is not None and out["plans"] == []
    assert out["watch"] == [{"sym": "DELL", "why": (
        "Once the pre-market low locks at 09:30 (552.66 so far): a 10-minute close below it, "
        "then the retest from below that holds.")}]


def test_in_the_session_the_watch_line_is_the_models_reason() -> None:
    dash = {"sym": "DELL", "side": "short", "conviction": 1,
            "plan": "No trade – inside both levels, nothing broken.",
            "trigger": "-", "invalidation": "-", "target": "-", "options": "-", "why": []}
    out = sp.sanitize_plan({"headline": "h", "plans": [dash]}, _facts(DELL(), session="rth"))
    assert out["watch"] == [{"sym": "DELL", "why": "Inside both levels, nothing broken."}]  # type: ignore[index]


# ------------------------------------------------------------- the day's clock


CPI_DAY: list[dict[str, Any]] = [
    {"et": "05:40", "title": "FOMC Member Bowman Speaks", "score": 5, "done": False,
     "themes": ["rates"]},
    {"et": "08:30", "title": "Core CPI m/m", "score": 5, "done": False, "consensus": "0.2%",
     "previous": "0.3%", "themes": ["inflation"]},
    {"et": "08:30", "title": "Core CPI y/y", "score": 5, "done": False, "consensus": "2.5%",
     "previous": "2.4%", "themes": ["inflation"]},
    {"et": "08:30", "title": "CPI y/y", "score": 5, "done": False, "consensus": "3.6%",
     "previous": "3.4%", "themes": ["inflation"]},
    {"et": "08:30", "title": "CPI, n.s.a”,", "score": 5, "done": False, "themes": ["inflation"]},
    {"et": "11:00", "title": "Cleveland CPI", "score": 5, "done": False, "previous": "0.2%"},
    {"et": "14:00", "title": "Beige Book", "score": 3, "done": False, "themes": ["rates"]},
    {"et": "22:55", "title": "FOMC Member Bowman Speaks", "score": 5, "done": False,
     "themes": ["rates"]},
]


def test_a_release_is_one_line_per_minute_and_family_without_the_garbage() -> None:
    g = sp.group_releases(CPI_DAY)
    assert [x["et"] + " " + x["family"] for x in g] == [
        "05:40 FOMC Member Bowman Speaks", "08:30 CPI", "11:00 CPI", "14:00 Beige Book",
        "22:55 FOMC Member Bowman Speaks"]
    assert sp.release_line(g[1]) == (
        "08:30 CPI — core m/m 0.2% expected (prev 0.3%), core y/y 2.5% expected (prev 2.4%), "
        "y/y 3.6% expected (prev 3.4%), n.s.a")
    assert sp.release_line(g[2]) == "11:00 Cleveland CPI — prev 0.2%"


def test_the_clock_and_the_release_risks_are_the_servers() -> None:
    facts = _facts(GME(), events=sp.group_releases(CPI_DAY))
    clock = sp.clock_lines(facts)
    assert clock[0] == "05:40 FOMC Member Bowman Speaks"
    assert clock[2:4] == ["09:30 the open", "10:00 the opening range is set"]
    assert clock[-1] == "16:00 the close"                    # 22:55 is after it
    risks = sp.event_risks(facts)
    assert [r.split(" — ")[0] for r in risks] == [
        "05:40 FOMC Member Bowman Speaks", "08:30 CPI", "11:00 Cleveland CPI", "14:00 Beige Book"]
    assert risks[1].endswith("levels formed ahead of it are provisional.")
    assert risks[3].endswith("let it print before taking a level.")
    # A model risk that restates a listed release is dropped; one about a level stays.
    body = {"headline": "h", "plans": [], "timing": ["08:30 CPI, n.s.a”,"],
            "risks": ["A hot CPI print lifts yields", "Bowman sounds hawkish",
                      "GME loses PDH 27.53 at the open"]}
    out = sp.sanitize_plan(body, facts)
    assert out is not None
    assert out["risks"] == ["GME loses PDH 27.53 at the open"]
    assert out["timing"] == clock and out["events"] == risks


def test_a_done_print_is_neither_on_the_clock_nor_a_risk() -> None:
    done = [{**x, "done": True} if x["et"] == "05:40" else x for x in CPI_DAY]
    facts = _facts(events=sp.group_releases(done))
    assert not any("Bowman" in x for x in sp.clock_lines(facts)[:2])
    assert not any("05:40" in r for r in sp.event_risks(facts))


def test_the_trading_days_prints_only_with_their_times() -> None:
    prints = [{"et": "08:30", "title": "CPI"}, {"et": "Thu 08:30", "title": "PPI"},
              {"et": "Wed 10:00", "title": "X"}]
    wed, thu = date(2026, 10, 14), date(2026, 10, 15)
    assert [(x["et"], x["title"]) for x in sp._day_prints(prints, wed, wed)] == [
        ("08:30", "CPI"), ("10:00", "X")]
    assert [(x["et"], x["title"]) for x in sp._day_prints(prints, thu, wed)] == [
        ("08:30", "PPI")]
