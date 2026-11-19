"""
The model reads the story, and says which way (owner, 2026-11-18: "so what is the ai
reading? just the headline or the content too?" → "do what you recommend to make our
scanner more accurate").

Every headline here is off the list that morning: Nvidia's long flagged by "Cantor
Fitzgerald's … Lutnick probe", Google's $10 million purchase of a bankrupt airline's data
read as its own legal trouble, and Walmart paid twenty points for a preview.
"""

from __future__ import annotations

import json
from datetime import UTC, datetime
from typing import Any

from newsterminal import catalysts, newsread, scanscore
from newsterminal.sources import tvstory


def _h(title: str, age_min: float = 60.0, pub: str = "Reuters", url: str = "") -> dict[str, Any]:
    return {"title": title, "age_min": age_min, "publisher": pub, "kind": "news", "url": url}


# ---- the story's text ------------------------------------------------------------------


def test_a_story_id_comes_from_its_page_address() -> None:
    url = ("https://www.tradingview.com/news/reuters.com,2026:newsml_L1N3X0:0-lowe-s-raises-"
           "annual-sales-forecast/")
    # Reuters' page drops its id's "tag:", and Quartr's id has colons of its own.
    assert tvstory.id_from_url(url) == "tag:reuters.com,2026:newsml_L1N3X0:0"
    assert tvstory.id_from_url("https://www.tradingview.com/news/tradingview:33bd56214dcd1:0-"
                               "broadridge-names/") == "tradingview:33bd56214dcd1:0"
    assert tvstory.id_from_url("https://www.tradingview.com/news/urn:summary_document_report:"
                               "quartr.com:4002724:0-mist-launch/") == \
        "urn:summary_document_report:quartr.com:4002724:0"
    assert tvstory.id_from_url("https://www.tradingview.com/news/DJN_DN20261111003179:0-data"
                               "-centers/") == "DJN_DN20261111003179:0"
    assert tvstory.id_from_url("https://finance.yahoo.com/news/x.html") is None
    assert tvstory.id_from_url(None) is None


def test_the_body_is_the_paragraphs_without_the_boilerplate() -> None:
    doc = {"astDescription": {"type": "root", "children": [
        {"type": "p", "children": ["Home-improvement retailer Lowe's ", {"type": "symbol",
                                   "params": {}}, " raised its annual sales forecast on "
                                   "Wednesday, banking on resilient demand from contractors."]},
        {"type": "p", "children": ["Demand for repair-and-maintenance projects has held up."]},
        {"type": "p", "children": ["Copyright 2026 Reuters."]}]}}
    text = tvstory.body_of(doc)
    assert text.startswith("Home-improvement retailer Lowe's raised its annual sales forecast")
    assert "\nDemand for repair" in text and "Copyright" not in text
    # Dow Jones answers no body, Seeking Alpha its disclaimer: nothing worth showing.
    assert tvstory.body_of({"shortDescription": ""}) == ""
    disclaimer = ("Content provided by Seeking Alpha is intended for information purposes "
                  "only, and that Seeking Alpha does not offer any investment advice.")
    assert tvstory.body_of({"astDescription": {"type": "root", "children": [
        {"type": "p", "children": [disclaimer]}]}}) == ""
    # Cut on a word, at the most the model is shown.
    long = {"shortDescription": "word " * 600}
    assert len(tvstory.body_of(long)) <= tvstory.BODY_MAX + 2


def test_a_story_is_read_once_and_kept(tmp_path: Any, monkeypatch: Any) -> None:
    calls: list[str] = []

    class R:
        ok, status = True, 200

        def json(self) -> dict[str, Any]:
            return {"shortDescription": "Acme raised its full-year outlook to $4.10 a share "
                                        "on data-centre demand, and said orders rose 30%."}

    def fake(url: str, **kw: Any) -> R:
        calls.append(url)
        assert kw["ua"].startswith("Mozilla/5.0") and "@" not in kw["ua"]
        return R()

    monkeypatch.setattr(tvstory, "fetch", fake)
    monkeypatch.setattr(tvstory.time, "sleep", lambda s: None)
    st = tvstory.StoryText(str(tmp_path / "t.json"))
    assert st.read(["a:1:0", "a:1:0", "b:2:0"]) == 2 and len(calls) == 2
    assert st.read(["a:1:0"]) == 0 and len(calls) == 2
    assert (st.get("a:1:0") or "").startswith("Acme raised")
    assert tvstory.StoryText(str(tmp_path / "t.json")).get("b:2:0") is not None
    assert st.get("zzz") is None


# ---- the model's direction in the score's read ------------------------------------------


NVDA_FLAG = "Cantor Fitzgerald's Nvidia business interests targeted in Democrats' Lutnick probe"


def test_the_models_direction_replaces_the_words() -> None:
    earn = {"date": "2026-11-17", "days": -1, "when": "after", "surprise_pct": 7.9,
            "last_night": True}
    news = [_h(NVDA_FLAG, 120.0, "CNBC")]
    # The words: "probe" reads against the long, and the row is flagged.
    words = scanscore.catalyst_read("long", earn, news, None, sym="NVDA",
                                    names=["Nvidia", "NVIDIA"], tape=0.1)
    assert words["reads_against"] and words["reads_against_title"] == NVDA_FLAG
    assert words["pts"] == 20 and words["item"]["tag"] == "Report"

    # The model read it as not Nvidia's own news: no flag, the points as they were.
    def model(title: str | None) -> str | None:
        return "bull" if title is None else ""

    read = scanscore.catalyst_read("long", earn, news, None, sym="NVDA",
                                   names=["Nvidia", "NVIDIA"], tape=0.1, model_dir=model)
    assert read["reads_against"] is None and read["pts"] == 20
    assert read["item"]["src"] == "model" and "its direction from the model's read" in read["note"]


def test_the_model_overrules_the_eps_sign_and_the_tape_still_overrules_the_model() -> None:
    # A beat with the outlook cut: the sign says long, the model says bearish.
    earn = {"date": "2026-11-17", "days": -1, "when": "after", "surprise_pct": 4.0,
            "last_night": True}
    bear = scanscore.catalyst_read("long", earn, [], None, sym="ACME", names=["Acme"],
                                   tape=0.1, model_dir=lambda t: "bear")
    assert bear["pts"] == 20 and bear["item"]["dir"] == "bear" and bear["item"]["with"] is False
    assert "its direction from the model's read" in bear["note"]
    # Not read yet: the sign, as before.
    sign = scanscore.catalyst_read("long", earn, [], None, sym="ACME", names=["Acme"],
                                   tape=0.1, model_dir=lambda t: None)
    assert sign["item"]["dir"] == "bull" and sign["item"]["src"] == "report"
    # The tape has clearly gone the other way: the model's word is overruled, it still pays.
    over = scanscore.catalyst_read("long", earn, [], None, sym="ACME", names=["Acme"],
                                   tape=0.9, model_dir=lambda t: "bear")
    assert over["pts"] == 20 and over["item"]["src"] == "overruled" and over["item"]["dir"] is None


def test_the_stocks_own_move_still_comes_before_the_model() -> None:
    t = "Acme Stock Jumps 9% After Raising Its Outlook"
    got = scanscore.catalyst_read("long", None, [_h(t)], None, sym="ACME", names=["Acme"],
                                  tape=0.1, day_move=9.0, model_dir=lambda title: "bear")
    assert got["item"]["src"] == "move" and got["item"]["dir"] == "bull"


def test_a_story_the_model_reads_no_way_goes_to_the_tape_as_the_words_did() -> None:
    t = "Merck to Buy Verona Pharma for $10 Billion"
    quiet = scanscore.catalyst_read("long", None, [_h(t)], None, sym="MRK", names=["Merck"],
                                    tape=0.2, model_dir=lambda title: "")
    assert quiet["pts"] == 0
    moving = scanscore.catalyst_read("long", None, [_h(t)], None, sym="MRK", names=["Merck"],
                                     tape=0.9, model_dir=lambda title: "")
    assert moving["pts"] == 20 and moving["item"]["src"] == "tape"


# ---- what the model is asked ----------------------------------------------------------


def _row(read: dict[str, Any], news: list[dict[str, Any]], sym: str = "NVDA",
         earnings: dict[str, Any] | None = None) -> dict[str, Any]:
    return {"sym": sym, "ok": True, "news": news, "earnings": earnings,
            "score": {"parts": [{"key": "catalyst", "read": read}]}}


def test_a_report_is_shown_with_its_own_headline_not_the_newest() -> None:
    earn = {"date": "2026-11-17", "eps_actual": "2.68", "eps_forecast": "2.48",
            "surprise_pct": 8.4}
    news = [_h("Kevin O'Leary Says Nvidia Needs Leader Who Can Manage International "
               "Pressure", 30.0, url="https://finance.yahoo.com/x"),
            _h("Nvidia Beats Third-Quarter Estimates as Data-Centre Sales Jump", 400.0,
               url="https://www.tradingview.com/news/reuters.com,2026:abc:0-nvidia-beats/")]
    item = {"tag": "Report", "tier": 1, "src": "report", "title": None}
    c = newsread.candidate(_row({"item": item}, news, earnings=earn))
    assert c is not None and c["key"] == "NVDA|report|2026-11-17"
    assert c["headline"].startswith("Nvidia Beats Third-Quarter")
    assert tvstory.id_from_url(c["url"]) == "tag:reuters.com,2026:abc:0"


def test_the_flagged_story_and_an_untracked_names_story_are_read_too() -> None:
    news = [_h(NVDA_FLAG, 120.0, "CNBC")]
    row = _row({"item": {"tag": "Report", "tier": 1, "src": "report", "title": None},
                "reads_against_title": NVDA_FLAG}, news,
               earnings={"date": "2026-11-17", "eps_actual": "2.68"})
    flag = newsread.flag_candidate(row)
    assert flag is not None and flag["key"] == f"NVDA|{newsread.norm(NVDA_FLAG)}"
    story = {"title": "TPG nears take-private deal for BILL Holdings, source says", "tier": 1,
             "tag": "Deal", "url": "https://www.tradingview.com/news/reuters.com,2026:x:0-tpg/"}
    assert newsread.story_candidate("BILL", story)["key"].startswith("BILL|tpg nears")
    assert newsread.story_candidate("BILL", {**story, "tier": 3}) is None
    # The Scanner's list first, in its order; a tracked name brings its two stories, and
    # the story its row shows when that is another major one.
    shows = {"title": "Nvidia Sued Over Chip Export Disclosures", "tier": 1, "tag": "Legal"}
    got = newsread.candidates([row], listed=[{"sym": "BILL", "story": story},
                                             {"sym": "NVDA", "story": shows}])
    assert [c["key"].split("|")[0] for c in got] == ["BILL", "NVDA", "NVDA", "NVDA"]
    assert got[1]["key"] == "NVDA|report|2026-11-17"
    assert got[3]["headline"] == shows["title"]
    # The flagged headline reaches the candidate through the catalyst part's read.
    cat = scanscore.catalyst_read("long", None, [_h(NVDA_FLAG, 120.0, "CNBC")], None,
                                  sym="NVDA", names=["Nvidia"], tape=0.1)
    assert cat["reads_against_title"] == NVDA_FLAG


def test_the_model_is_shown_the_text_and_asked_for_a_direction() -> None:
    c = newsread.story_candidate("BILL", {"title": "TPG nears take-private deal for BILL",
                                          "tier": 1, "tag": "Deal", "url": ""})
    assert c is not None
    c["text"] = "TPG is in advanced talks to take BILL Holdings private at $72 a share."
    shown = newsread.shown(c)
    assert shown["text"].startswith("TPG is in advanced talks") and "summary" not in shown
    one = newsread.schema(1)["properties"]["reads"]["items"]
    assert one["properties"]["direction"]["enum"] == list(newsread.DIRECTIONS)
    got = newsread.sanitize({"reads": [{"id": "s1", "size": "big", "direction": "bullish",
                                        "line": "TPG in talks to take BILL private at $72"}]}, [c])
    assert got[c["key"]] == {"size": "big", "direction": "bullish", "text": True,
                             "line": "TPG in talks to take BILL private at $72"}
    odd = newsread.sanitize({"reads": [{"id": "s1", "size": "big", "direction": "up",
                                        "line": ""}]}, [c])
    assert odd[c["key"]]["direction"] == "unclear"
    assert "bullish" in newsread.SYSTEM and "never the words bullish" in newsread.SYSTEM


def test_a_read_from_before_the_direction_is_read_again(tmp_path: Any) -> None:
    path = tmp_path / "reads.json"
    now = datetime(2026, 11, 18, 8, 0, tzinfo=UTC).timestamp()
    path.write_text(json.dumps({"reads": {"S0|t": {"size": "big", "line": "x", "at": now}}}),
                    encoding="utf-8")
    store = newsread.ReadStore(str(path))
    cands = [{"key": "S0|t", "sym": "S0", "headline": "t"}]
    assert [c["key"] for c in store.pending(cands, now)] == ["S0|t"]
    assert store.direction("S0", "t") is None
    assert store.for_story("S0", "t") == {"size": "big", "direction": None, "line": "x",
                                          "headline": None, "text": False}


# ---- the misreads of that morning ------------------------------------------------------


def test_a_report_that_could_offer_clues_is_a_preview() -> None:
    t = "Target, Walmart Q3 Earnings Could Offer Consumer Health & Inflation Clues for Investors"
    assert catalysts.grade(t).tag == "Preview"
    assert catalysts.story(t, "WMT", ["Walmart"]) is None
    # A report that has happened is still one.
    assert catalysts.grade("Walmart Q3 Earnings Beat Estimates, Raises Outlook").tier == 1


def test_somebody_elses_bankruptcy_is_not_the_names() -> None:
    t = ("Google Gets Court Approval to Buy Bankrupt Spirit Airlines' Internal Data for "
         "$10 Million to Train AI Models Despite Employee Privacy Concerns")
    g = catalysts.grade(t)
    assert g.tag != "Legal" and g.tier != 1
    assert scanscore.headline_direction(t, "GOOGL", ["Google", "Alphabet"]) is None
    # The name's own bankruptcy still is.
    for own in ("Spirit Airlines Files for Bankruptcy Protection",
                "Spirit Airlines Goes Bankrupt as Fares Collapse"):
        assert catalysts.grade(own).tag == "Legal"
        assert scanscore.headline_direction(own) == "bear"
