"""
The rework of 2026-11-14 (owner: "do what you recommend ... the whole purpose of the
scanner is to identify stocks that are more likely to be strong trenders").

News is fuel and the price picks the side: a story earns its grade whichever side the
setup is on (tests/test_catalyst.py, test_catalysts.py and test_quant_audit.py hold the
headlines). Here: what did NOT move with it, the previous session's story, and the
model's read of a major story, both logged and neither scored.
"""

from __future__ import annotations

import io
import json
import urllib.error
from datetime import UTC, datetime
from typing import Any

from newsterminal import newsread, scan, scanlog, scanscore


def _h(title: str, age_min: float = 60.0, pub: str = "Reuters") -> dict[str, Any]:
    return {"title": title, "age_min": age_min, "publisher": pub, "kind": "news"}


# ---- what did not move ----------------------------------------------------------------


def test_a_story_that_says_no_way_still_needs_the_tape() -> None:
    # The record tested stories that READ against the side. One that reads no way earns
    # nothing until the name has moved against SPY, as before.
    t = "Merck to Buy Verona Pharma for $10 Billion"
    quiet = scanscore.catalyst_read("long", None, [_h(t)], None, sym="MRK", names=["Merck"],
                                    tape=0.2)
    assert quiet["pts"] == 0 and quiet["note"].startswith("no directional catalyst")
    moving = scanscore.catalyst_read("long", None, [_h(t)], None, sym="MRK", names=["Merck"],
                                     tape=-0.9)
    # The tape has spoken, down: the deal pays the long its grade and the row says so.
    assert moving["pts"] == 20 and moving["item"]["src"] == "tape"
    assert "its direction from the tape" in moving["reads_against"]


def test_another_companys_event_under_the_name_never_pays() -> None:
    # Listed under Apple, and Foxconn's beat. It set no direction, which was enough to
    # earn nothing only while the tape was quiet; it is asked outright now.
    t = "Apple Supplier Foxconn Beats Estimates"
    for tape in (None, 0.9, -0.9):
        got = scanscore.catalyst_read("long", None, [_h(t)], None, sym="AAPL", names=["Apple"],
                                      tape=tape)
        assert got["pts"] == 0 and got["item"] is None
    # An analyst's note and a bid for the name are the name's own.
    up = "Bank of America Securities Upgrades Micron to Buy"
    assert scanscore.catalyst_read("long", None, [_h(up)], None, sym="MU",
                                   names=["Micron"])["pts"] == 12


def test_rs_is_ten_and_capped_at_five_off_a_live_entry() -> None:
    assert (scanscore.W_RS, scanscore.RS_POOR) == (10, 5)
    # The parts a setup can earn: 103 once the daily frame's six went (2026-11-15), 98 since
    # the VIX's five went on the evening of 2026-11-19, shown capped at 100, ranked on the sum.
    full = (max(scanscore.W_STRUCTURE.values()) + scanscore.W_RS + scanscore.W_ENTRY
            + scanscore.W_VOLUME[0][1] + scanscore.W_MARKET + scanscore.W_CATALYST)
    assert full == 98 and not hasattr(scanscore, "W_FRAME")
    assert not hasattr(scanscore, "W_CONFIRM")


# ---- the previous session's story: on the row and in the log, never in the score ------


def test_the_previous_sessions_major_story_is_found_and_only_that() -> None:
    fresh, prior = 1000.0, 2440.0   # minutes back: this session's window, and the one before
    news = [
        _h("Acme Raises Full-Year Outlook", 1500.0),            # yesterday morning: major
        _h("Acme Shares Jump 9% After Raising Its Outlook", 1300.0),  # the newer major one
        _h("Barclays upgrades Acme to Buy", 1200.0),            # notable: not a day-2 story
        _h("Acme Beats Estimates", 300.0),                      # today's: the catalyst's
        _h("Acme Wins $2 Billion Contract", 4000.0),            # two sessions back
        _h("Will Acme Beat Estimates Again in Its Next Earnings Report?", 1400.0),  # talk
    ]
    got = scanscore.prior_story(news, "ACME", ["Acme"], fresh_min=fresh, prior_min=prior)
    assert got is not None
    assert (got["title"], got["tier"], got["age_min"]) == (
        "Acme Shares Jump 9% After Raising Its Outlook", 1, 1300.0)
    assert scanscore.prior_story(news[2:], "ACME", ["Acme"], fresh_min=fresh,
                                 prior_min=prior) is None
    assert scanscore.prior_story(news, "ACME", ["Acme"], fresh_min=None, prior_min=prior) is None
    # A story of a 1% move is nobody's first day (live, 2026-11-14, on Apple's row); one
    # that states no figure stands.
    small = [_h("Apple Stocks Rise 1.04% as Siri AI-Powered HomeView and Apple TV Hit Shelves",
                1200.0)]
    assert scanscore.prior_story(small, "AAPL", ["Apple"], fresh_min=fresh, prior_min=prior) is None
    bare = [_h("Nvidia Shares Drop Again as Investors Eye Fallout From Huang's Removal", 1200.0)]
    got = scanscore.prior_story(bare, "NVDA", ["Nvidia"], fresh_min=fresh, prior_min=prior)
    assert got is not None and got["tag"] == "Move"


def test_outlook_the_mail_app_is_not_a_companys_outlook() -> None:
    from newsterminal import catalysts

    # Live, 2026-11-14: held under Microsoft as a major Earnings story.
    app = catalysts.grade("Microsoft Says Outage Disrupting Outlook Is Improving")
    assert app.tag != "Earnings" and app.tier != catalysts.MAJOR
    # A company's outlook is still guidance.
    assert catalysts.grade("Acme Lowers Full-Year Outlook").tag == "Guidance"
    assert catalysts.grade("Microsoft Raises Outlook on Cloud Demand").tier == catalysts.MAJOR


def test_the_previous_story_is_a_flag_and_a_log_field_and_earns_nothing() -> None:
    row = {"lvl_state": 2, "rs": {"SPY": 0.9}, "rvol": 1.6, "range_used": 0.5,
           "setup": {"side": "long", "state": "retest", "level": "PMH", "lost_vwap": False,
                     "entry": {"kind": "PMH", "price": 1.0, "dist_atr": 0.1}}}
    reg = {"bias": "long", "confirm": "confirm"}
    cat = scanscore.catalyst_read("long", None, [], None, sym="ACME", names=["Acme"])
    bare = scanscore.score_row(row, reg, None, None, None, catalyst=dict(cat))
    cat["prior"] = {"tag": "Guidance", "tier": 1, "title": "Acme Raises Full-Year Outlook",
                    "publisher": "Reuters", "age_min": 1500.0}
    with_prior = scanscore.score_row(row, reg, None, None, None, catalyst=cat)
    assert with_prior["raw"] == bare["raw"]
    flags = scanscore.flags_for({**row, "score": with_prior}, None, None, [], [], "rth",
                                catalyst=cat)
    assert {"kind": "prior", "tone": "info",
            "text": 'Previous session\'s story · Guidance: Reuters: "Acme Raises Full-Year '
                    'Outlook"'} in flags
    news = scanlog.news_ctx(with_prior, {"size": "big", "line": "Raised the year's outlook"})
    assert news is not None
    assert news["prior"] == {"tag": "Guidance", "tier": 1, "age_min": 1500.0}
    assert news["size"] == "big" and news["pts"] == 0
    # No read, no prior: both None, and the older fields as they were.
    plain = scanlog.news_ctx(bare)
    assert plain is not None and plain["prior"] is None and plain["size"] is None


def test_the_build_reaches_back_a_session_for_the_story_and_lists_three_days() -> None:
    # Monday 16 Nov 2026, 10:00 ET. Friday's window opened Thursday 15:30; a story from
    # Friday 08:00 is four calendar days of news_for's three back by Monday afternoon.
    now = datetime(2026, 11, 16, 15, 0, tzinfo=UTC)
    clk = scan.clock_at(now.astimezone(scan.ET))
    fri = datetime(2026, 11, 13, 13, 0, tzinfo=UTC).timestamp()      # Fri 08:00 ET
    old = datetime(2026, 11, 11, 21, 0, tzinfo=UTC).timestamp()      # Wed 16:00 ET
    sat = datetime(2026, 11, 14, 15, 0, tzinfo=UTC).timestamp()      # Sat 10:00 ET
    base = {"sym": "ACME", "ok": True, "last": 105.0, "levels": {"pdc": 100.0},
            "lvl_state": 2, "rs": {"SPY": 0.9}, "rvol": 1.6, "range_used": 0.5,
            "setup": {"side": "long", "state": "retest", "level": "PMH", "lost_vwap": False,
                      "entry": {"kind": "PMH", "price": 1.0, "dist_atr": 0.1}}}
    own = [{"title": "Acme Raises Full-Year Outlook", "url": "u1", "publisher": "Reuters",
            "ts": fri},
           {"title": "Acme Wins $2 Billion Contract", "url": "u2", "publisher": "Reuters",
            "ts": old},
           # Plain news that says no way: since the close, so listed, and worth nothing.
           {"title": "Acme Opens New Plant in Ohio", "url": "u3", "publisher": "Reuters",
            "ts": sat, "summary": "A summary that must never reach the row."}]
    seen: list[tuple[str, Any]] = []

    def read(sym: str, item: dict[str, Any] | None, earn: dict[str, Any] | None,
             ) -> dict[str, Any] | None:
        seen.append((sym, item))
        return {"size": "big", "line": "x"}

    p = scanscore.build({"rows": {"ACME": base}, "fetched": {}}, quotes=[], sectors=[],
                        calendar=[], earnings=[], wire=[], news={"ACME": own}, filings={},
                        aliases={"ACME": ["Acme"]}, status=None, watchlist=["ACME"], clock=clk,
                        now=now, news_read=read)
    row = p["rows"][0]
    cat = next(x for x in row["score"]["parts"] if x["key"] == "catalyst")
    assert cat["pts"] == 0                       # nothing since Friday's close
    assert cat["read"]["prior"]["title"] == "Acme Raises Full-Year Outlook"
    assert any(f["kind"] == "prior" for f in row["flags"])
    # The row's list is the three days it says, and no summary rides on it.
    assert [n["title"] for n in row["news"]] == ["Acme Opens New Plant in Ohio"]
    assert "summary" not in row["news"][0]
    assert row["news_read"] == {"size": "big", "line": "x"} and seen == [("ACME", None)]


# ---- the model's read of a major story -------------------------------------------------


def _row(item: dict[str, Any] | None, **kw: Any) -> dict[str, Any]:
    part = {"key": "catalyst", "pts": 20, "max": 20, "read": {"item": item}}
    return {"sym": "ACME", "ok": True, "score": {"parts": [part]}, "news": [], "earnings": None,
            **kw}


MAJOR = {"tag": "Guidance", "tier": 1, "src": "words", "age_min": 90.0,
         "title": "Acme Raises Full-Year Outlook to $4.10 a Share"}


def test_only_a_major_story_is_read_and_a_report_goes_by_its_date() -> None:
    key = newsread.story_key
    assert key("ACME", MAJOR, None) == "ACME|acme raises fullyear outlook to 410 a share"
    assert key("ACME", {**MAJOR, "tier": 2}, None) is None
    assert key("ACME", {"tag": "Filing", "tier": 1, "src": "filing", "title": None}, None) is None
    report = {"tag": "Report", "tier": 1, "src": "report", "title": None}
    assert key("ACME", report, {"date": "2026-11-13"}) == "ACME|report|2026-11-13"
    assert key("ACME", report, None) is None and key("ACME", None, None) is None


def test_the_model_is_shown_the_headline_its_summary_the_report_and_the_nights_headlines() -> None:
    earn = {"date": "2026-11-13", "eps_actual": "1.05", "eps_forecast": "0.94",
            "surprise_pct": 11.7}
    row = _row(MAJOR, earnings=earn, news=[
        _h(MAJOR["title"], 90.0), _h("Acme Tops Third-Quarter Estimates", 120.0),
        _h("An old Acme story", 5000.0)])
    c = newsread.candidate(row, lambda t: "Acme lifted its 2026 profit forecast on data-centre "
                                          "demand and said orders rose 30%.")
    assert c is not None
    assert newsread.shown(c) == {
        "ticker": "ACME", "kind": "Guidance", "headline": MAJOR["title"],
        "summary": "Acme lifted its 2026 profit forecast on data-centre demand and said orders "
                   "rose 30%.",
        "report": "EPS 1.05 against an estimate of 0.94 (a surprise of +11.7%)",
        "other_headlines": ["Acme Tops Third-Quarter Estimates"]}
    assert newsread.candidate(_row({**MAJOR, "tier": 3})) is None
    assert newsread.candidate(_row(None)) is None
    # One a story, in the list's order, and only rows that are up.
    twice = newsread.candidates([row, dict(row), {**row, "ok": False}])
    assert [x["key"] for x in twice] == [c["key"]]


def test_the_answer_is_held_to_what_the_model_was_shown() -> None:
    c = newsread.candidate(_row(MAJOR))
    assert c is not None
    other = dict(c, key="OTHR|x", sym="OTHR", headline="Other Co Wins a Contract")
    got = newsread.sanitize({"reads": [
        {"id": "s1", "size": "big", "line": "Raised its full-year outlook to $4.10 a share."},
        {"id": "s2", "size": "huge", "line": "not a size on the list"},
        {"id": "s9", "size": "big", "line": "not a story it was shown"}]}, [c, other])
    # No direction given: "unclear" (2026-11-18); `text`: it read the headline alone.
    assert got == {c["key"]: {"size": "big", "direction": "unclear",
                              "line": "Raised its full-year outlook to $4.10 a share",
                              "text": False}}
    # A figure the text does not carry, and a call on direction: the size stands, no line.
    seen = json.dumps(newsread.shown(c))
    assert newsread.clean_line("Outlook raised 12% to $4.10", seen) == ""
    assert newsread.clean_line("A bullish raise of the outlook", seen) == ""
    assert newsread.clean_line("  Outlook raised to $4.10\n a share ", seen) == \
        "Outlook raised to $4.10 a share"
    assert newsread.sanitize({"reads": "nope"}, [c]) == {} and newsread.sanitize(None, [c]) == {}


def _answer(reads: list[dict[str, Any]]) -> dict[str, Any]:
    return {"choices": [{"message": {"content": json.dumps({"reads": reads})}}]}


def test_the_ask_walks_the_chain_and_sends_nothing_of_the_owner() -> None:
    c = newsread.candidate(_row(MAJOR))
    assert c is not None
    calls: list[dict[str, Any]] = []

    def post(payload: dict[str, Any], key: str) -> dict[str, Any]:
        calls.append(payload)
        if len(calls) == 1:   # the schema refused: the same model once more in JSON mode
            raise urllib.error.HTTPError("u", 400, "bad schema", {}, io.BytesIO(b"{}"))  # type: ignore[arg-type]
        return _answer([{"id": "s1", "size": "ordinary", "direction": "bullish",
                         "line": "Outlook raised"}])

    got, attempts = newsread.ask([c], "k", model="m1", post=post)
    assert got == {c["key"]: {"size": "ordinary", "direction": "bullish",
                              "line": "Outlook raised", "text": False, "model": "m1"}}
    assert [a["mode"] for a in attempts] == ["schema", "json"]
    assert calls[0]["response_format"]["type"] == "json_schema"
    assert calls[1]["response_format"] == {"type": "json_object"}
    # What goes out is the public text and nothing else.
    sent = json.dumps(calls[0])
    assert "ACME" in sent and MAJOR["title"] in sent
    for private in ("HERMES", "localhost", "protonmail", "@"):
        assert private not in sent

    # Busy (429): on to the next model, not the same one again; three attempts at most.
    busy: list[str] = []

    def refuse(payload: dict[str, Any], key: str) -> dict[str, Any]:
        busy.append(payload["model"])
        raise urllib.error.HTTPError("u", 429, "busy", {}, io.BytesIO(b"{}"))  # type: ignore[arg-type]

    got, attempts = newsread.ask([c], "k", model="m1", post=refuse)
    assert got == {} and len(attempts) <= newsread.MAX_ATTEMPTS and len(set(busy)) == len(busy)


def test_the_request_carries_a_browser_agent_and_no_attribution(monkeypatch: Any) -> None:
    held: dict[str, Any] = {}

    class Reply:
        def __enter__(self) -> Reply:
            return self

        def __exit__(self, *a: Any) -> None:
            return None

        def read(self) -> bytes:
            return b'{"ok": true}'

    def fake(req: Any, timeout: float = 0) -> Reply:
        held["headers"] = {k.lower(): v for k, v in req.header_items()}
        return Reply()

    monkeypatch.setattr(newsread.urllib.request, "urlopen", fake)
    assert newsread._post({"model": "m"}, "secret") == {"ok": True}
    h = held["headers"]
    assert h["user-agent"].startswith("Mozilla/5.0") and h["authorization"] == "Bearer secret"
    assert "x-title" not in h and "http-referer" not in h and "referer" not in h
    assert "@" not in h["user-agent"]


def test_the_store_paces_the_requests_and_keeps_the_reads(tmp_path: Any) -> None:
    path = str(tmp_path / "reads.json")
    store = newsread.ReadStore(path)
    now = datetime(2026, 11, 16, 14, 0, tzinfo=UTC).timestamp()
    cands = [{"key": f"S{i}|t", "sym": f"S{i}", "headline": f"h{i}"} for i in range(12)]
    assert store.due(now)
    todo = store.pending(cands, now)
    assert [c["key"] for c in todo] == [c["key"] for c in cands[:newsread.BATCH]]
    store.asked(todo, now)
    assert not store.due(now + 60) and store.due(now + newsread.GAP_SEC)
    store.put({"S0|t": {"size": "big", "direction": "bearish", "line": "A line", "model": "m",
                        "text": True}}, todo, now)
    # Read ones are done; the unanswered wait an hour; the rest come up next.
    nxt = store.pending(cands, now + 400)
    assert [c["key"] for c in nxt] == [c["key"] for c in cands[newsread.BATCH:]]
    assert "S1|t" in [c["key"] for c in store.pending(cands, now + 3700)]
    item = {"tag": "Guidance", "tier": 1, "src": "words", "title": "t"}
    assert store.for_item("S0", item, None) == {"size": "big", "direction": "bearish",
                                                "line": "A line", "headline": "h0", "text": True}
    # Which way, as the score reads it; a story not read is None.
    assert store.direction("S0", "t") == "bear" and store.direction("S5", "t") is None
    assert store.for_item("S5", item, None) is None
    assert store.for_item("S0", {**item, "tier": 2}, None) is None
    # The day's cap, and the file.
    for i in range(newsread.DAILY_MAX):
        store.asked([], now + 1000 * (i + 1))
    assert not store.due(now + 1000 * (newsread.DAILY_MAX + 3))   # the same New York day
    assert store.due(now + 86400 + 1000 * (newsread.DAILY_MAX + 3))
    again = newsread.ReadStore(path)
    assert again.for_item("S0", item, None) is not None
    assert again.health(now)["reads"] == 1
