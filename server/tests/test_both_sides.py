"""
A short is a long turned upside down (owner, 2026-11-14: "trending means ... trending
which is both to the upside or downside ... audit it and make sure stuff is functioning
correctly").

THE TEST IS A MIRROR. Turn a price series over (p becomes 2M - p: every high a low,
every break of PDH a break of PDL, the same sizes in dollars and ATRs, the same volume)
and the engine must give the mirror answer: the same setup on the other side, the same
signals at the same bars, the same score part by part, the same outcome. The audit ran
that on the real bars of 131 names at 69 instants over three sessions (9,039 rows,
27,117 scores, 383 outcomes) and the engine held everywhere; these keep it so, on bars
made here.

WHAT THE AUDIT DID FIND, each kept below: bad news that read no direction where its good
twin read one (a failed trial, an index removal, a lost contract, a fall "on downgrade"),
so it earned nothing until the tape spoke; a target touched to the cent and filed as
missed, because the feed's prices are single precision; the tape's "divergence" and the
daily frame's 52-week line, which had words for one side only.
"""

from __future__ import annotations

import random
from datetime import datetime, timedelta
from typing import Any

import pytest

from newsterminal import catalysts, frame, scan, scanlog, scanscore
from newsterminal.scan import Bar
from newsterminal.sources import pool

ET = scan.ET
FLIP = {"long": "short", "short": "long", None: None}
SWAP = {"PDH": "PDL", "PDL": "PDH", "PMH": "PML", "PML": "PMH", "VWAP": "VWAP", "EMA8": "EMA8",
        None: None}
LOW = {"pdh": "pdl", "pdl": "pdh", "pmh": "pml", "pml": "pmh"}


# ---- the engine on mirrored bars ------------------------------------------------------


def _walk(seed: int, drift: float) -> list[Bar]:
    """Four sessions of five-minute bars, 04:00 to 20:00 ET, a random walk with a drift,
    quiet outside the session. Mon 9 to Thu 12 Nov 2026."""
    rng = random.Random(seed)
    bars: list[Bar] = []
    px = 100.0
    for day in (9, 10, 11, 12):
        t = datetime(2026, 11, day, 4, 0, tzinfo=ET)
        end = datetime(2026, 11, day, 20, 0, tzinfo=ET)
        while t < end:
            rth = (9, 30) <= (t.hour, t.minute) < (16, 0)
            vol = (0.35 if rth else 0.12) * (1.0 + 0.6 * rng.random())
            o = px
            c = o + drift * (1.0 if rth else 0.3) + rng.gauss(0.0, vol)
            hi = max(o, c) + abs(rng.gauss(0.0, vol / 2))
            lo = min(o, c) - abs(rng.gauss(0.0, vol / 2))
            bars.append(Bar(int(t.timestamp()), round(o, 2), round(hi, 2), round(lo, 2),
                            round(c, 2), float(rng.randint(20_000, 400_000) if rth else
                                               rng.randint(500, 9_000))))
            px = c
            t += timedelta(minutes=5)
    return bars


def _turn(bars: list[Bar], m: float) -> list[Bar]:
    return [b._replace(open=2 * m - b.open, high=2 * m - b.low, low=2 * m - b.high,
                       close=2 * m - b.close) for b in bars]


def _near(a: float | None, b: float | None, tol: float = 1e-3) -> bool:
    if a is None or b is None:
        return a is None and b is None
    return abs(a - b) <= tol * max(1.0, abs(a), abs(b))


INSTANTS = [(d, h, m) for d in (11, 12) for h, m in
            ((8, 0), (9, 20), (9, 36), (9, 55), (10, 25), (11, 5), (12, 15), (13, 35), (14, 45),
             (15, 25), (15, 55), (16, 30))]


@pytest.mark.parametrize(("seed", "drift"), [(1, 0.02), (2, -0.02), (3, 0.0), (4, 0.05), (5, -0.05),
                                             (6, 0.01), (7, -0.01)])
def test_the_engine_gives_the_mirror_answer_on_mirrored_bars(seed: int, drift: float) -> None:
    bars, spy = _walk(seed, drift), _walk(100 + seed, drift / 2)
    m, ms = bars[-1].close, spy[-1].close
    fbars, fspy = _turn(bars, m), _turn(spy, ms)
    sides: set[str | None] = set()
    for d, hh, mm in INSTANTS:
        now = datetime(2026, 11, d, hh, mm, tzinfo=ET)
        clk = scan.clock_at(now)
        t1, t2 = scan.technicals(bars, [], clk), scan.technicals(fbars, [], clk)
        s1, s2 = scan.technicals(spy, [], clk), scan.technicals(fspy, [], clk)
        r1, r2 = scan.row_of("X", t1, s1, None, clk), scan.row_of("X", t2, s2, None, clk)
        at = f"seed {seed} {now:%d %H:%M}"
        assert r1["ok"] and r2["ok"], at
        assert r2["lvl_state"] == -r1["lvl_state"] and r2["trend"] == -r1["trend"], at
        for k in ("atr_b", "atr_d", "range_used", "rvol"):
            assert _near(r1[k], r2[k]), (at, k, r1[k], r2[k])
        rs1, rs2 = r1["rs"]["SPY"], r2["rs"]["SPY"]
        assert _near(rs1, -rs2 if rs2 is not None else None, 5e-3), (at, rs1, rs2)
        for k in LOW:
            assert r1["broken"][k] == r2["broken"][LOW[k]], (at, k)
            a, b = r1["levels"][k], r2["levels"][LOW[k]]
            assert _near(a, 2 * m - b if b is not None else None, 1e-4), (at, k, a, b)
        a1, a2 = r1["setup"], r2["setup"]
        sides.add(a1["side"])
        assert a2["side"] == FLIP[a1["side"]], (at, a1, a2)
        assert a2["state"] == a1["state"] and a2["level"] == SWAP[a1["level"]], (at, a1, a2)
        assert bool(a1.get("lost_vwap")) == bool(a2.get("lost_vwap")), at
        e1, e2 = a1.get("entry"), a2.get("entry")
        assert (e1 is None) == (e2 is None), at
        if e1 is not None and e2 is not None:
            assert e2["kind"] == SWAP[e1["kind"]], at
            assert _near(e1["dist_atr"], -e2["dist_atr"], 2e-2), at
        g1 = sorted(r1["signals"], key=lambda x: (x["t"], x["kind"], x["side"]))
        g2 = sorted(r2["signals"], key=lambda x: (x["t"], x["kind"], FLIP[x["side"]]))
        assert [(x["kind"], x["t"], x["side"], x["level"]) for x in g1] == [
            (y["kind"], y["t"], FLIP[y["side"]], SWAP[y["level"]]) for y in g2], at
        for x, y in zip(g1, g2, strict=True):
            assert _near(x["price"], 2 * m - y["price"], 1e-4), at
            if x["stop"] is not None:
                assert _near(x["stop"], 2 * m - y["stop"], 1e-4), at
                if x["kind"] in ("L", "E") and hh == 16:
                    day = now.date().isoformat()
                    o1 = scanlog.compute_outcome({**x, "day": day}, bars, now.timestamp())
                    o2 = scanlog.compute_outcome({**y, "day": day}, fbars, now.timestamp())
                    for k in ("hit_1r", "hit_2r", "stopped", "final"):
                        assert o1[k] == o2[k], (at, x["kind"], x["side"], x["at_et"], k)
                    for k in ("r", "mfe_r", "mae_r", "ret_close_r"):
                        assert _near(o1[k], o2[k], 5e-3), (at, k, o1[k], o2[k])
        # And the score, part by part, in the mirrored market: the tape, the VIX's
        # direction, the sector and the daily trend turned over with the name.
        for vix in (-3.0, 0.0, 3.0):
            tape1 = {"SPY": scan.row_of("SPY", s1, s1, None, clk)}
            tape2 = {"SPY": scan.row_of("SPY", s2, s2, None, clk)}
            for f in ("chg_pct", "ext_pct"):   # a percent's base moves with the mirror
                v = tape1["SPY"].get(f)
                tape2["SPY"][f] = -v if v is not None else None
            reg1 = scanscore.regime([{"key": "VIX", "last": 19.0, "pct": vix}], tape1, [],
                                    clk.session, now)
            reg2 = scanscore.regime([{"key": "VIX", "last": 19.0, "pct": -vix}], tape2, [],
                                    clk.session, now)
            fr1 = {"trend": "up", "text": ""}
            fr2 = {"trend": "down", "text": ""}
            head = [{"title": "Acme Beats Estimates and Raises Guidance", "age_min": 60.0,
                     "publisher": "Reuters"}]
            c1 = scanscore.catalyst_read(a1["side"], None, head, None)
            c2 = scanscore.catalyst_read(a2["side"], None, head, None)
            sc1 = scanscore.score_row(r1, reg1, 0.5, None, None, clk.session, frame_read=fr1,
                                      catalyst=c1, now=now)
            sc2 = scanscore.score_row(r2, reg2, -0.5, None, None, clk.session, frame_read=fr2,
                                      catalyst=c2, now=now)
            p1 = {p["key"]: round(p["pts"], 3) for p in sc1["parts"]}
            p2 = {p["key"]: round(p["pts"], 3) for p in sc2["parts"]}
            assert p1 == p2, (at, vix, a1["side"], a1["state"], p1, p2)
            assert sc1["raw"] == pytest.approx(sc2["raw"]) and sc2["side"] == FLIP[sc1["side"]]
    assert sides - {None}, "the walk never took a side"


def test_the_walks_reach_both_sides_and_every_live_state() -> None:
    # The mirror test is only worth what it visits: longs and shorts, at the level,
    # pulled back, extended, failed and before the bell, with (L) and (E) signals.
    seen: set[tuple[str | None, str]] = set()
    kinds: set[tuple[str, str]] = set()
    for seed, drift in ((1, 0.02), (2, -0.02), (3, 0.0), (4, 0.05), (5, -0.05), (6, 0.01),
                        (7, -0.01)):
        bars, spy = _walk(seed, drift), _walk(100 + seed, drift / 2)
        for d, hh, mm in INSTANTS:
            clk = scan.clock_at(datetime(2026, 11, d, hh, mm, tzinfo=ET))
            r = scan.row_of("X", scan.technicals(bars, [], clk), scan.technicals(spy, [], clk),
                            None, clk)
            seen.add((r["setup"]["side"], r["setup"]["state"]))
            kinds |= {(s["kind"], s["side"]) for s in r["signals"]}
    for side in ("long", "short"):
        for state in ("forming", "retest", "pullback", "extended"):
            assert (side, state) in seen, (side, state)
        assert ("L", side) in kinds and ("BO", side) in kinds, side


# ---- the score on a mirrored row ---------------------------------------------------------


def _row(side: str, state: str, lvl: int, rs: float, dist: float, lost: bool) -> dict[str, Any]:
    long_ = side == "long"
    level = ("PMH" if long_ else "PML")
    s = 1 if long_ else -1
    return {"sym": "X", "lvl_state": s * lvl, "rs": {"SPY": s * rs}, "rvol": 1.6, "range_used": 0.6,
            "broken": {"pdh": long_ and lvl >= 1, "pmh": long_ and lvl == 2,
                       "pdl": (not long_) and lvl >= 1, "pml": (not long_) and lvl == 2},
            "levels": {"pm_done": True, "pdc": 100.0}, "last": 100.0 + s * 2.0, "atr_d": 4.0,
            "setup": {"side": side, "state": state, "level": level, "lost_vwap": lost,
                      "entry": {"kind": level, "price": 1.0, "dist_atr": s * dist}}}


@pytest.mark.parametrize("state", ["retest", "pullback", "extended", "approaching", "forming",
                                   "failed", "chop"])
@pytest.mark.parametrize("lvl", [0, 1, 2])
@pytest.mark.parametrize("rs", [-0.4, 0.3, 1.5])
def test_a_short_scores_what_its_mirror_long_scores(state: str, lvl: int, rs: float) -> None:
    for dist, lost in ((0.2, False), (3.0, False), (0.2, True)):
        for bias, conf, frame_up, session in (("long", "confirm", True, "rth"),
                                              ("short", "risk_off", False, "rth"),
                                              (None, "divergence", True, "pre"),
                                              (None, None, False, "rth")):
            mirror_bias = FLIP[bias]
            mirror_conf = {"confirm": "risk_off", "risk_off": "confirm",
                           "divergence": "divergence_down", None: None}[conf]
            long_ = scanscore.score_row(
                _row("long", state, lvl, rs, dist, lost), {"bias": bias, "confirm": conf}, 0.5,
                None, None, session, frame_read={"trend": "up" if frame_up else "down", "text": ""})
            short = scanscore.score_row(
                _row("short", state, lvl, rs, dist, lost),
                {"bias": mirror_bias, "confirm": mirror_conf}, -0.5, None, None, session,
                frame_read={"trend": "down" if frame_up else "up", "text": ""})
            a = {p["key"]: p["pts"] for p in long_["parts"]}
            b = {p["key"]: p["pts"] for p in short["parts"]}
            assert a == b, (state, lvl, rs, dist, lost, bias, conf, a, b)
            assert long_["raw"] == short["raw"] and long_["total"] == short["total"]


def test_the_tape_votes_the_same_both_ways() -> None:
    def reg(spy_state: int, qqq_state: int, spy_move: float, vix: float) -> dict[str, Any]:
        tape = {"SPY": {"ok": True, "lvl_state": spy_state, "chg_pct": spy_move},
                "QQQ": {"ok": True, "lvl_state": qqq_state, "chg_pct": spy_move}}
        return scanscore.regime([{"key": "VIX", "last": 19.0, "pct": vix}], tape, [], "rth",
                                datetime(2026, 11, 12, 11, 0, tzinfo=ET))

    words = {"confirm": "risk_off", "risk_off": "confirm", "divergence": "divergence_down",
             "divergence_down": "divergence", "chop": "chop", None: None}
    for a in (-2, -1, 0, 1, 2):
        for b in (-2, -1, 0, 1, 2):
            for move in (-0.6, -0.1, 0.0, 0.1, 0.6):
                for vix in (-4.0, 0.0, 4.0):
                    up, down = reg(a, b, move, vix), reg(-a, -b, -move, -vix)
                    assert down["bias"] == FLIP[up["bias"]], (a, b, move, vix)
                    assert down["confirm"] == words[up["confirm"]], (a, b, move, vix)
    # The word the falling tape did not have: SPY down with the VIX down.
    assert reg(0, 0, -0.6, -4.0)["confirm"] == "divergence_down"
    assert any("take profits on shorts" in n for n in reg(0, 0, -0.6, -4.0)["notes"])


def test_the_rank_and_the_pool_do_not_know_a_side() -> None:
    def row(sym: str, rs: float, dist: float) -> dict[str, Any]:
        return {"sym": sym, "ok": True, "score": {"total": 60, "raw": 60}, "rs": {"SPY": rs},
                "setup": {"entry": {"dist_atr": dist}}}

    # A tie goes to the name nearest its entry, then the one further from SPY: weak or
    # strong.
    strong, weak = scanscore.rank_key(row("A", 1.2, 0.5)), scanscore.rank_key(row("A", -1.2, -0.5))
    assert strong[:4] == weak[:4]
    # In play is the size of the move: a gap down is a gap up.
    up = scanscore.in_play({"last": 106.0, "atr_d": 4.0, "levels": {"pdc": 100.0}}, None)
    down = scanscore.in_play({"last": 94.0, "atr_d": 4.0, "levels": {"pdc": 100.0}}, None)
    assert up == down

    def pooled(pm: float, hi: float, lo: float) -> dict[str, Any]:
        return {"symbol": "X", "close": 100.0, "change": 0.0, "volume": 1e6, "avg_vol": 1e6,
                "atr": 4.0, "cap": 3e9, "pm_change": pm - 100.0, "pm_volume": 40_000.0,
                "pm_close": pm, "earn_next": None, "earn_last": None, "earn_last_when": None,
                "high": hi, "low": lo, "h1": hi, "l1": lo}

    from datetime import date

    g_up = pool.in_play(pooled(106.0, 103.0, 97.0), "pre", date(2026, 11, 16))
    g_dn = pool.in_play(pooled(94.0, 103.0, 97.0), "pre", date(2026, 11, 16))
    assert g_up["score"] == g_dn["score"] and g_up["gap_atr"] == g_dn["gap_atr"]
    assert (g_up["through"], g_dn["through"]) == ("PDH", "PDL")
    assert g_up["outside"] and g_dn["outside"]


# ---- the news: bad news is read as its good twin is --------------------------------------

TWINS = [
    ("Acme Stock Jumps 8% After Earnings Beat", "Acme Stock Falls 8% After Earnings Miss"),
    ("Acme Shares Surge 12% on Raised Guidance", "Acme Shares Plunge 12% on Lowered Guidance"),
    ("Acme Soars 20% as AI Demand Lifts Outlook", "Acme Sinks 20% as AI Demand Hits Outlook"),
    ("Acme Climbs 5% After Record Quarter", "Acme Slides 5% After Weak Quarter"),
    ("Acme Stock Is Rising Today", "Acme Stock Is Falling Today"),
    ("Acme Pops 7% After FDA Approval", "Acme Dives 7% After FDA Rejection"),
    ("Acme Beats Estimates", "Acme Misses Estimates"),
    ("Acme Raises Full-Year Outlook", "Acme Cuts Full-Year Outlook"),
    ("Morgan Stanley Upgrades Acme to Overweight", "Morgan Stanley Downgrades Acme to Underweight"),
    ("Acme Price Target Raised to $50 at UBS", "Acme Price Target Cut to $50 at UBS"),
    ("FDA Approves Acme's New Drug", "FDA Rejects Acme's New Drug"),
    # The four the audit found reading no way, or a tier apart, on the bad side or the good:
    ("Acme Phase 3 Trial Meets Primary Endpoint",
     "Acme Phase 3 Trial Fails to Meet Primary Endpoint"),
    ("Acme Set to Join S&P 500", "Acme to Be Removed From S&P 500"),
    ("Acme Wins $2 Billion Pentagon Contract", "Acme Loses $2 Billion Pentagon Contract"),
    ("Acme Rallies 6% on Upgrade", "Acme Tumbles 6% on Downgrade"),
    ("Acme Wins Patent Lawsuit", "Acme Loses Patent Lawsuit"),
]


@pytest.mark.parametrize(("good", "bad"), TWINS)
def test_bad_news_is_read_as_its_good_twin_is(good: str, bad: str) -> None:
    def read(title: str) -> tuple[int, str | None, int, int]:
        h = [{"title": title, "age_min": 60.0, "publisher": "Reuters"}]
        d = (catalysts.moved(title, "ACME", ["Acme"])
             or scanscore.headline_direction(title, "ACME", ["Acme"]))
        lo = scanscore.catalyst_read("long", None, h, None, sym="ACME", names=["Acme"])["pts"]
        sh = scanscore.catalyst_read("short", None, h, None, sym="ACME", names=["Acme"])["pts"]
        return catalysts.grade(title).tier, d, lo, sh

    g_tier, g_dir, g_long, g_short = read(good)
    b_tier, b_dir, b_long, b_short = read(bad)
    assert g_tier == b_tier, (good, bad)
    assert (g_dir, b_dir) == ("bull", "bear"), (good, g_dir, bad, b_dir)
    # Each pays the setup, long or short, what its twin pays.
    assert (g_long, g_short) == (b_short, b_long) and g_long > 0, (g_long, g_short, b_long, b_short)


#: The price-move words added in pairs on 2026-11-14 (catalysts._UP / _DOWN): each read
#: no move either way before.
VERBS = [("Advances", "Declines"), ("Rebounds", "Retreats"), ("Bounces", "Dips"),
         ("Moves Higher", "Moves Lower"), ("Trades Higher", "Trades Lower"),
         ("Heads Higher", "Heads Lower"), ("Edges Up", "Edges Down"),
         ("Ticks Higher", "Ticks Lower"), ("Adds", "Sheds"), ("Shoots Up", "Collapses"),
         # And a few of the old ones, so the list is not only the new.
         ("Jumps", "Falls"), ("Surges", "Plunges"), ("Climbs", "Slides")]


@pytest.mark.parametrize(("up", "down"), VERBS)
def test_a_fall_is_read_as_a_rise_is_whatever_the_verb(up: str, down: str) -> None:
    for verb, want, sign in ((up, "bull", 1.0), (down, "bear", -1.0)):
        title = f"Acme Stock {verb} 7% After Earnings"
        assert catalysts.moved(title, "ACME", ["Acme"]) == want, title
        assert catalysts.stated_move(title, "ACME", ["Acme"]) == sign * 7.0, title
        assert catalysts.grade(title).tier == catalysts.MAJOR, title
        # With no report in it the move and its reason are the story, either way.
        bare = f"Acme Stock {verb} 7% After Analyst Day"
        assert catalysts.grade(bare) == ("Move", catalysts.MAJOR), bare


@pytest.mark.parametrize("title", [
    "Acme Declines to Comment on Report",
    "Acme Declines Offer From Beta",
    "Acme Advances Drug Into Phase 3 Trial",
    "Acme Advances as Leader in AI Chips",
    "Acme Dips Into Reserves to Fund Dividend",
    "Acme Retreats From China Market",
    "Acme Sheds 500 Jobs in Restructuring",
    "Acme Adds 200 Stores in Expansion",
    "Acme Loses 7% of Its Market Share",
    "Acme Rebounds From Supply Problems",
])
def test_a_word_that_is_not_about_the_price_is_not_a_move(title: str) -> None:
    assert catalysts.moved(title, "ACME", ["Acme"]) is None, title
    assert catalysts.stated_move(title, "ACME", ["Acme"]) is None, title
    assert catalysts.move_grade(title) is None, title


def test_a_negation_is_read_for_what_it_says() -> None:
    d = scanscore.headline_direction
    assert d("Acme Fails to Beat Estimates", "ACME", ["Acme"]) == "bear"
    assert d("Acme Did Not Meet Its Primary Endpoint", "ACME", ["Acme"]) == "bear"
    assert d("SEC Drops Probe Into Acme", "ACME", ["Acme"]) in ("bull", None)   # not bear
    assert d("Acme Lawsuit Dismissed by Federal Judge", "ACME", ["Acme"]) == "bull"
    # Two real things, two ways, is still no direction.
    assert d("Acme Beats and Misses", "ACME", ["Acme"]) is None
    # What is different by design: a cut dividend is trouble (notable), a raised one routine.
    assert catalysts.grade("Acme Cuts Quarterly Dividend 10%").tier == catalysts.NOTABLE
    assert catalysts.grade("Acme Raises Quarterly Dividend 10%").tier == catalysts.MINOR


# ---- the outcome: a touch to the cent ------------------------------------------------------


def _five(t0: int, rows: list[tuple[float, float, float, float]]) -> list[Bar]:
    return [Bar(t0 + 300 * i, o, h, lo, c, 1000.0) for i, (o, h, lo, c) in enumerate(rows)]


def test_a_target_touched_to_the_cent_is_reached_whatever_the_feed_rounded_it_to() -> None:
    # HIMS, 11 Nov 2026: (E) long at 14:30, entry 20.66, stop 20.50. The 15:00 bar's high
    # was 20.82, which Yahoo's single-precision price holds as 20.81999969482422.
    t0 = int(datetime(2026, 11, 11, 14, 30, tzinfo=ET).timestamp())
    hi = 20.81999969482422
    bars = _five(t0, [(20.66, 20.69, 20.62, 20.66), (20.66, hi, 20.66, 20.70),
                      (20.70, 20.70, 20.50, 20.52)])
    bars.append(Bar(int(datetime(2026, 11, 11, 15, 55, tzinfo=ET).timestamp()), 20.52, 20.55,
                    20.51, 20.53, 1000.0))
    now = datetime(2026, 11, 11, 16, 30, tzinfo=ET).timestamp()
    long_ = {"kind": "E", "side": "long", "price": 20.66, "stop": 20.50, "t": t0,
             "day": "2026-11-11", "risk_min": 0.042}
    o = scanlog.compute_outcome(long_, bars, now)
    assert (o["hit_1r"], o["stopped"], o["hit_2r"]) == (True, False, False)
    # The same trade upside down, around 20.66, with the same rounding on the other side.
    m = 20.66
    short = {**long_, "side": "short", "stop": 2 * m - 20.50}
    o2 = scanlog.compute_outcome(short, _turn(bars, m), now)
    assert (o2["hit_1r"], o2["stopped"], o2["hit_2r"]) == (True, False, False)
    # A hair is not a tick: a high one whole cent short of +1R is not +1R.
    near = _five(t0, [(20.66, 20.81, 20.62, 20.70), (20.70, 20.70, 20.50, 20.52)])
    assert scanlog.compute_outcome(long_, near, now)["hit_1r"] is False


# ---- the words -----------------------------------------------------------------------------


def test_the_daily_frame_names_the_nearer_extreme() -> None:
    fr = {"sma20": 100.0, "sma50": 100.0, "wk52_hi": 200.0, "wk52_lo": 80.0,
          "pw_hi": 110.0, "pw_lo": 90.0}
    low = frame.read(fr, 84.0)
    assert low is not None and low["trend"] == "down"
    assert "5.0% over the 52-week low" in low["text"] and "52-week high" not in low["text"]
    assert "at a 52-week low" in frame.read(fr, 79.0)["text"]
    high = frame.read({**fr, "sma20": 150.0, "sma50": 150.0}, 190.0)
    assert high is not None and high["trend"] == "up"
    assert "5.0% under the 52-week high" in high["text"]
    assert "at a 52-week high" in frame.read(fr, 201.0)["text"]
    # And the trend the score reads is the same rule turned over.
    assert frame.with_side(low, "short") == "with" and frame.with_side(low, "long") == "against"
    assert frame.with_side(high, "long") == "with" and frame.with_side(high, "short") == "against"
