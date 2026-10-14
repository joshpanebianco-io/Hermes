"""
The wire — every desk's headlines on one tape.

WHAT IS DIFFERENT HERE FROM GEXYGEN. That project ships commercially, so its
wire is confined to US Government works and openly-licensed feeds: titles and
links only, no summary, and the big agencies excluded outright. This terminal
runs on one desk for one reader, which is the use every publisher's RSS terms
actually contemplate — so the wires come back, the summary line comes with
them, and Reuters and AP are recovered through Google News' index because
neither serves a usable public feed of its own any more.

The rules that keep that honest are still here, because they are good practice
rather than a licence condition: every item names its publisher on the line,
every item links back to the publisher's own page, and nothing is cached
beyond the poll interval.

CATEGORY IS ASSIGNED TWICE. Once from the feed it arrived on — a Bloomberg
Economics item is macro by construction — and then again from the headline
text, which can promote it. A strike on a refinery arriving on the world feed
is energy news; the feed cannot know that and the words can.
"""

from __future__ import annotations

import re
import urllib.parse
from datetime import UTC, datetime, timedelta
from email.utils import parsedate_to_datetime
from typing import Any

from ..config import BROWSER_UA
from ..http import SourceStatus, clean_text, feed_body, fetch, rss_items


def gnews(query: str, when: str = "1d") -> str:
    """A Google News search feed.

    EXISTS BECAUSE OF WHAT IT RECOVERS. Reuters and AP no longer serve a usable
    public RSS feed of their own, and they are the two desks whose absence is
    most felt on a market tape. Google indexes both, so a `site:` query gets
    their headlines back — with the outlet named in the title suffix, which
    `parse_feed` lifts off and uses as the attribution.

    The locale triplet is identical on every one of these and was repeated six
    times before this helper; the URLs were also long enough that the feed
    table could not be read without horizontal scrolling.
    """
    return (
        "https://news.google.com/rss/search?q="
        + urllib.parse.quote(f"{query} when:{when}", safe="+():")
        + "&hl=en-US&gl=US&ceid=US:en"
    )


# category, feed url, publisher, section, region
#
# `category` is the DEFAULT for everything on the feed; the classifier below can
# override it upward. `region` is fixed by the feed and is not overridden — it
# says whose session this desk covers, which is a property of the publication
# rather than of any one headline.
#
# THE REGION COLUMN EXISTS BECAUSE THIS DESK TRADES THREE SESSIONS. A tape
# weighted entirely to New York is the wrong tape at 21:00 ET when Tokyo is
# opening, so Nikkei Asia, SCMP, the Japan Times, CNBC Asia, ABC Australia and
# the RBA sit alongside the US desks and can be filtered to on their own.
FEEDS: list[tuple[str, str, str, str, str]] = [
    # ---- the two wires, via Google News' index -------------------------------
    ("markets", gnews("site:reuters.com markets OR economy"), "Reuters", "Markets", "global"),
    ("geo", gnews("site:reuters.com world OR conflict OR sanctions"), "Reuters", "World", "global"),
    ("macro", gnews("site:apnews.com economy OR inflation OR federal reserve"),
     "AP", "Economy", "us"),
    # ---- US market desks -----------------------------------------------------
    ("markets", "https://www.cnbc.com/id/20910258/device/rss/rss.html", "CNBC", "Markets", "us"),
    ("markets", "https://www.cnbc.com/id/100003114/device/rss/rss.html", "CNBC", "Top", "us"),
    ("markets", "https://feeds.content.dowjones.io/public/rss/RSSMarketsMain",
     "WSJ", "Markets", "us"),
    ("geo", "https://feeds.content.dowjones.io/public/rss/RSSWorldNews", "WSJ", "World", "global"),
    ("markets", "https://feeds.content.dowjones.io/public/rss/mw_topstories",
     "MarketWatch", "Top", "us"),
    ("markets", "https://feeds.bloomberg.com/markets/news.rss", "Bloomberg", "Markets", "global"),
    ("macro", "https://feeds.bloomberg.com/economics/news.rss",
     "Bloomberg", "Economics", "global"),
    ("markets", "https://www.ft.com/markets?format=rss", "FT", "Markets", "global"),
    ("markets", "https://finance.yahoo.com/news/rssindex", "Yahoo Finance", "Top", "us"),
    ("markets", "https://www.investing.com/rss/news.rss", "Investing.com", "News", "global"),
    ("macro", "https://rss.nytimes.com/services/xml/rss/nyt/Economy.xml", "NYT", "Economy", "us"),
    ("markets", "https://rss.nytimes.com/services/xml/rss/nyt/Business.xml",
     "NYT", "Business", "us"),
    ("markets", "https://feeds.feedburner.com/zerohedge/feed", "ZeroHedge", "Markets", "us"),
    # ---- Asia-Pacific --------------------------------------------------------
    ("markets", "https://asia.nikkei.com/rss/feed/nar", "Nikkei Asia", "Asia", "apac"),
    ("markets", "https://www.cnbc.com/id/19832390/device/rss/rss.html",
     "CNBC", "Asia markets", "apac"),
    ("markets", "https://www.scmp.com/rss/92/feed", "SCMP", "Business", "apac"),
    ("macro", "https://www.scmp.com/rss/4/feed", "SCMP", "China", "apac"),
    ("macro", "https://www.japantimes.co.jp/feed/", "Japan Times", "Japan", "apac"),
    ("macro", "https://www.abc.net.au/news/feed/51892/rss.xml", "ABC", "Australia", "apac"),
    ("policy", "https://www.rba.gov.au/rss/rss-cb-media-releases.xml", "RBA", "Policy", "apac"),
    ("macro", gnews("(Bank of Japan OR PBOC OR RBA OR Nikkei OR Hang Seng) markets"),
     "Google News", "Asia", "apac"),
    # ---- Europe and the UK ---------------------------------------------------
    ("macro", "https://feeds.bbci.co.uk/news/business/rss.xml", "BBC", "Business", "uk"),
    ("markets", "https://www.cnbc.com/id/19794221/device/rss/rss.html",
     "CNBC", "Europe markets", "eu"),
    ("policy", "https://www.bankofengland.co.uk/rss/news", "Bank of England", "Policy", "uk"),
    ("policy", "https://www.ecb.europa.eu/rss/press.html", "ECB", "Press", "eu"),
    ("macro", "https://rss.dw.com/rdf/rss-en-bus", "DW", "Business", "eu"),
    # ---- geopolitics ---------------------------------------------------------
    ("geo", "https://feeds.bbci.co.uk/news/world/rss.xml", "BBC", "World", "global"),
    ("geo", "https://www.aljazeera.com/xml/rss/all.xml", "Al Jazeera", "World", "global"),
    ("geo", "https://www.theguardian.com/world/rss", "Guardian", "World", "global"),
    ("geo", "https://rss.nytimes.com/services/xml/rss/nyt/World.xml", "NYT", "World", "global"),
    ("geo", gnews("war OR ceasefire OR missile OR sanctions OR tariff"),
     "Google News", "Conflict", "global"),
    # ---- energy and commodities ---------------------------------------------
    ("energy", gnews("OPEC OR crude oil OR natural gas OR refinery"),
     "Google News", "Energy", "global"),
    ("energy", "https://www.theguardian.com/business/oil/rss", "Guardian", "Oil", "global"),
    # ---- policy: the institutions' own words --------------------------------
    ("policy", "https://www.federalreserve.gov/feeds/press_monetary.xml",
     "Federal Reserve", "Monetary", "us"),
    ("policy", "https://www.federalreserve.gov/feeds/speeches.xml",
     "Federal Reserve", "Speeches", "us"),
    ("policy", gnews("ECB OR Bank of Japan OR Bank of England OR PBOC rate", "2d"),
     "Google News", "Central banks", "global"),
]

# What never belongs on a trading desk's tape. Features, service journalism,
# listicles, obituaries — the material a general-news feed carries between the
# news. This is the single highest-value filter in the module: without it the
# tape is roughly half advice columns.
NOISE = re.compile(
    r"^(?:how|why|what|who|where|when|should|could|would|can|is|are|do|does|will)\b|"
    r"\bbest\b|\btop \d|\bthese \d|\b\d+ (?:stocks|picks|names|ways|reasons|charts|things|"
    r"lessons|tips)\b|things to know|what to know|explained|explainer|podcast|"
    r"\breviews?\b|quiz|crossword|recipe|horoscope|\badvice\b|your money|side hustle|"
    r"mortgage rate|credit card|\bretire\b|newsletter|puzzle|obituar|dies at|\bdied\b|"
    r"live updates|watch:|video:|photos?:|in pictures|opinion:|\bhoroscope\b|"
    r"deals?:|sale:|discount|black friday|gift guide|"
    # THE SYNDICATED-ADVICE BLOCK. Yahoo Finance's index feed is largely Motley
    # Fool copy, which is written to a handful of templates: a Buffett hook, a
    # "History Says" backtest, a "Prediction:" and a "Should You Buy". None of
    # it is news and all of it arrives dated within the hour, so without this
    # it sits at the top of the tape displacing the wires.
    # ['’] EVERYWHERE AN APOSTROPHE APPEARS. Publishers typeset a curly U+2019
    # and the straight ASCII one is what a regex gets written with, so
    # `here'?s` matched none of the copy it was aimed at — the headline that
    # exposed it was "…— here’s what you can do before inflation eats into
    # your savings", sitting at the top of the tape.
    # FIRST-PERSON ADVICE COLUMNS. MarketWatch runs "The Moneyist" on its top-
    # stories feed, so a trading tape was carrying "My contractor handed my
    # $42,000 pool upgrade to a subcontractor" and "My friend is charging
    # everyone $80 to attend her 30th birthday party". No market headline is
    # written in the first person, which makes this the cheapest reliable test
    # there is — anchored to the start so a quoted "my" mid-headline survives.
    r"^(?:my|our|i|we|he|she|they)\b|"
    r"\bmy (?:husband|wife|son|daughter|mother|father|friend|boss|landlord|neighbou?r)\b|"
    r"warren buffett|motley fool|history says|prediction:|here['’]?s (?:why|what|how)|"
    r"should you (?:buy|sell|own)|social security|\b401\(?k\)?\b|\bIRA\b|"
    r"dividend (?:king|aristocrat)|"
    r"stock split|millionaire|wealth|\bcramer\b|jim cramer|analyst (?:says|thinks)|"
    r"\bthis \d+\b|\b\d+ (?:no-brainer|magnificent|incredible|surefire)|"
    # CORPORATE APPOINTMENT PR. Investing.com carries a company newswire, and
    # on a quiet morning five of the top twelve headlines were "X appoints Y to
    # board" — a genuine press release, and never an index event.
    #
    # SCOPED TO APPOINTMENTS ONLY, not to departures: "Intel CEO steps down"
    # moves the stock and therefore the index, so `steps down` and `resigns`
    # are deliberately absent. Matched on the verb the PR uses — appoints,
    # names, elects — which is why "John Ternus becomes Apple CEO" survives.
    r"\bappoints?\b|\bnames?\b[^.]{0,40}\b(?:chief|CEO|CFO|CTO|COO|president|chairman)\b|"
    r"\belects?\b[^.]{0,30}\bboard\b|joins? the board|to the board of|"
    r"board of directors\b|\bboard chair(?:man|woman|person)?\b|"
    # NEWSLETTERS AND QUOTE PAGES. "Before the Bell: What every Canadian
    # investor needs to know today", "AP top stories October 14" and "Xiaomi
    # Corporation (1810.HK) stock price, news, quote and history" all reached
    # the tape on 2026-10-14 — a table of contents and a ticker page, not news.
    r"needs? to know|\bbefore the bell:|\btop stories\b|stock price, news, quote",
    re.I,
)

# Words that promote an item's category regardless of which feed carried it.
# Ordered by priority — the first hit wins, so a headline about an oil facility
# being struck lands in energy rather than geo.
PROMOTE: list[tuple[str, re.Pattern[str]]] = [
    ("policy", re.compile(
        r"\bFOMC\b|\bFed\b|Federal Reserve|Powell|rate (?:cut|hike|decision|path)|"
        r"basis points?|\bBOJ\b|Bank of Japan|\bECB\b|Lagarde|Bank of England|\bBoE\b|"
        r"\bPBOC\b|monetary policy|quantitative|dot plot|Jackson Hole|beige book", re.I)),
    ("macro", re.compile(
        r"\bCPI\b|\bPCE\b|inflation|payrolls?|\bjobs? report\b|unemployment|jobless claims|"
        r"\bGDP\b|retail sales|\bISM\b|\bPMI\b|consumer confidence|housing starts|"
        r"durable goods|trade deficit|recession|stagflation|deflation", re.I)),
    ("energy", re.compile(
        r"\bOPEC\b|crude|\bWTI\b|\bBrent\b|refiner|pipeline|natural gas|\bLNG\b|"
        r"barrel|oil (?:price|output|supply|demand|field)|gasoline|diesel|"
        r"drilling|\bEIA\b|strategic petroleum", re.I)),
    # ---------------------------------------------------------------- corp
    #
    # SPLIT OUT OF `markets` (2026-09-01). `markets` was the largest desk by
    # some way — 149 of 400 — and it was doing three jobs at once: index and
    # rates news, single-company news, and the analyst-action wire. On one
    # sample it held "Treasury 10-Year Yield Tops 4.75%" and "BMO Capital
    # maintains Market Perform on Stride stock at $93 target" side by side,
    # which are not the same kind of thing for a desk trading index futures.
    #
    # NOT FILTERED OUT, CATEGORISED. A Broadcom guide-down is an NQ event and a
    # Stride rating is not, and no regex can reliably tell them apart — so both
    # stay on the tape and the reader gets one chip to drop the whole desk when
    # they want the index-level view.
    #
    # ORDERED AFTER policy/macro/energy so a company story that is really a
    # macro or energy story keeps the bigger desk: "Trump to host oil
    # executives" is energy, not corp.
    ("corp", re.compile(
        # the analyst-action wire, which is most of the volume
        r"\b(?:raises?|lowers?|cuts?|lifts?|trims?|boosts?)\s+(?:the\s+)?"
        r"(?:\w+\s+){0,3}(?:price\s+)?target\b|"
        r"\bprice target\b|\breiterates?\b|\bmaintains?\b|\binitiate[sd]?\b|"
        r"\b(?:up|down)grade[sd]?\b|\b(?:Buy|Sell|Hold|Neutral|Outperform|Underperform|"
        r"Overweight|Underweight|Market Perform)\b|"
        # results and guidance
        r"\bQ[1-4]\b|\b(?:first|second|third|fourth)[- ]quarter\b|\bfull[- ]year results\b|"
        r"\bearnings\b|\brevenue\b|\bprofit\b|\bguidance\b|\bEPS\b|"
        r"\bpreliminary results\b|\breports? (?:a )?(?:loss|profit)\b|"
        # corporate actions
        r"\bacquisitions?\b|\bacquires?\b|\bmerger\b|\btakeover\b|\bbuyback\b|"
        r"\bdividend\b|\bspin[- ]?off\b|\bstake in\b|\bIPO\b|\bdelist\b|"
        # single-stock price action
        r"\bstock (?:hits?|jumps?|slides?|falls?|rises?|surges?|drops?|climbs?|pulls? back)\b|"
        r"\b52-week (?:low|high)\b|\bshares? (?:jump|slide|fall|rise|surge|drop|tumble)\b|"
        # insider and director dealings — a whole newswire of its own
        r"\b(?:insider|director|officer|executive)s?\b[^.]{0,40}"
        r"\b(?:buys?|bought|sells?|sold|acquires?|disposes?)\b|"
        r"\bcommon stock\b|\bSEC filing\b|\bForm 4\b|"
        # corporate investment and tie-ups
        r"\binvest(?:s|ing|ed|ment)\b[^.]{0,20}\$|\bpartnership\b|\bjoint venture\b|"
        # A TICKER IN PARENTHESES is the cheapest single-stock signal there is —
        # "Martin Marietta Materials (MLM) Stock Pulls Back" — and it appears in
        # a large share of syndicated equity copy. The lookahead excludes the
        # handful of non-ticker capitals that show up in the same position;
        # without it "Federal Reserve (US)" and "gross domestic product (GDP)"
        # would both become company news.
        r"\([A-Z]{2,5}\)(?<!\(US\))(?<!\(EU\))(?<!\(UK\))(?<!\(UN\))(?<!\(AI\))"
        r"(?<!\(IPO\))(?<!\(CEO\))(?<!\(CFO\))(?<!\(GDP\))(?<!\(CPI\))(?<!\(PCE\))"
        r"(?<!\(FED\))(?<!\(ECB\))(?<!\(BOJ\))(?<!\(OPEC\))(?<!\(NATO\))",
        re.I)),
    ("geo", re.compile(
        r"\bwar\b|missile|drone strike|airstrike|ceasefire|invasion|troops|militar|"
        r"sanction|embargo|tariff|trade war|\bNATO\b|Kremlin|Ukraine|Russia|Israel|Iran|"
        r"Gaza|Taiwan|North Korea|Houthi|Red Sea|Strait of Hormuz|coup|"
        r"nuclear|conflict|border clash|peace (?:deal|talks)", re.I)),
]

# ---------------------------------------------------------------- impact
#
# THREE TIERS, AND THE TOP ONE HAS TO STAY SMALL. An "important" list that
# matches half the feed ranks nothing — the whole value of a HIGH filter is
# that switching to it leaves you with six lines rather than sixty.
#
# HIGH is a released number or a decided event that reprices the front of the
# curve or the index on the spot: the print itself, the decision itself, the
# shooting itself. MEDIUM is the material that moves things over a session —
# officials talking, policy proposed, a large deal, a supply disruption. LOW is
# everything else, which is most of the tape and is still worth carrying.

IMPACT_HIGH = re.compile(
    # policy, decided
    r"\bFOMC\b|rate (?:cut|hike|decision)|cuts? rates?|raises? rates?|hikes? rates?|"
    r"basis[- ]point (?:cut|hike)|emergency (?:meeting|cut|rate)|"
    # the prints that stop the tape
    r"\bCPI\b|\bPCE\b|payrolls?|jobs report|inflation (?:rose|fell|jumped|cooled|accelerat)|"
    r"unemployment rate|\bGDP\b (?:grew|shrank|contracted|rose|fell)|"
    # market structure breaking
    r"halt(?:ed|s)? trading|circuit breaker|trading suspended|"
    r"\bdefault(?:s|ed)?\b|downgrade[sd]? (?:the |its )?(?:US|U\.S\.|sovereign|credit)|"
    # `bankrupt` and `bailout` are events; a bare `collapse` was not — it fired
    # on "collapse of Earn lending program", a settled arbitration about a
    # crypto product, and ranked it beside a strike on Iran.
    r"bankrupt|bail(?:out|s out)|"
    # shooting, not talking
    r"(?<!home )invasion|invade[sd]?|ceasefire|nuclear (?:test|strike|weapon)|"
    r"(?:air)?strikes? on|missile(?:s)? (?:hit|struck|launched)|attack(?:s|ed) on|"
    r"assassinat|declares? war|shuts? down the strait|"
    # Added after they ranked low on a live tape. Each describes a thing that
    # HAS happened, which is the whole test for this tier.
    r"\bfighting\b|retaliat|escalat|exchanges? (?:of )?(?:fire|strikes)|"
    # supply, decided
    r"\bOPEC\+?\b.{0,24}(?:cut|raise|boost|output|quota)|"
    r"government shutdown|debt ceiling",
    re.I,
)

IMPACT_MEDIUM = re.compile(
    r"\bFed\b|Powell|Federal Reserve|\bECB\b|Lagarde|Bank of (?:Japan|England)|\bBOJ\b|\bBoE\b|"
    r"\bPBOC\b|central bank|monetary policy|dot plot|minutes|beige book|Jackson Hole|"
    r"\bPPI\b|\bISM\b|\bPMI\b|retail sales|jobless claims|\bJOLTS\b|"
    r"consumer (?:confidence|sentiment)|"
    r"tariff|sanction|embargo|export control|trade (?:deal|war|talks)|"
    # A bare \boil\b rather than the three narrow phrases: "Renewed US-Iran
    # fighting sends oil above $90" matched none of supply, output or price and
    # ranked low, which on an oil-driven tape is the wrong answer.
    r"\bOPEC\b|crude|refiner|pipeline|\bLNG\b|\boil\b|\bgas prices?\b|"
    r"earnings|guidance|profit warning|revenue (?:miss|beat)|"
    r"acquisition|merger|\btakeover\b|\bIPO\b|buyback|"
    r"layoffs|strike (?:action|by workers)|labou?r dispute|"
    r"yields? (?:rose|fell|jumped|surged)|"
    r"dollar (?:rose|fell|surged|slid)|"
    r"drone|troops|border|conflict|protest|election|referendum",
    re.I,
)


# HIGH IS A THING THAT HAPPENED, NOT A THING THAT MIGHT.
#
# The keyword lists cannot tell a decision from speculation about a decision,
# and the difference is the whole meaning of the tier: "Fed cuts rates" and
# "Fed rate cut expectations build" share every keyword and are not remotely
# the same headline. Three real examples that ranked HIGH before this guard —
# "ECB Rate Hike Threatens GBP Yield Advantage" (a forecast column), "Global
# markets fall as Fed rate hike expectations weigh" (a market report), and
# "Iran Receive Framework Ceasefire Proposal" (a proposal, not a ceasefire).
#
# A headline that hits the HIGH list AND carries one of these is demoted to
# medium rather than dropped: it is still worth reading, it just did not happen.
SPECULATIVE = re.compile(
    r"expectation|forecast|outlook|preview|\bbets?\b|\bodds\b|\bpoll\b|survey|"
    r"proposal|proposed|plan(?:s|ned)? to|considering|weigh(?:s|ing)? |mulls?|"
    r"could|\bmay\b|might|likely|expected to|set to|threatens?|risks?|fears?|"
    r"speculat|rumou?r|reportedly|sources say|\bif\b|\bwould\b|analysts?|"
    r"prediction|projected|estimate[sd]?|"
    # A bank's house view and an official's hint are both worth reading and
    # neither is a decision: "Barclays sees two more Fed rate hikes", "Fed Chair
    # Signals Possible September Rate Hike", "chances of a rate hike rise".
    r"\bsees\b|\bchances?\b|possible|possibly|signals?|hints?|suggests?|"
    # `\bbacks?\b` was here for "Fed backs a cut" and caught "Iran fires back",
    # demoting a live exchange of fire to speculation. Dropped — `signals` and
    # `flags` already cover the phrase it was for, and no term in this list is
    # worth a false negative on a conflict headline.
    r"flags?|floats?|\bopen to\b|\bpaves?\b",
    re.I,
)


# A COMPLETED ACT, WHICH OUTRANKS ANY SPECULATIVE WORD IN THE SAME HEADLINE.
#
# The speculative guard on its own was too blunt: it demoted "US CPI rose 3.1%
# in August, above forecasts" because of the word `forecasts`, and "Renewed
# US-Iran fighting sends oil above $90, threatening higher gas prices" because
# of `threatening` — in both, the speculative word describes the CONSEQUENCE of
# something that has already happened, not the event itself.
#
# So the two lists are read in order: a decided verb beats a speculative noun.
# Only the verbs of the events this tier is for, deliberately — no bare "fall"
# or "rise", which appear in every market wrap ever written.
DECIDED = re.compile(
    r"\b(?:rose|fell|jumped|surged|slid|climbed|dropped|plunged|"
    r"came in|beat|missed|topped|"
    r"struck|strikes|attacked|attacks|hit|launched|fired|bombed|seized|"
    r"halted|suspended|declared|invaded|defaulted|downgraded|"
    r"escalat\w*|retaliat\w*|fighting|resumed|reopened)\b"
    # RATE MOVES, NOT RATE TALK: the verb has to be doing something to a rate.
    # A bare `hikes` counted as decided until "Barclays sees two more Fed rate
    # hikes this year" came off the tape — there it is a noun, and the headline
    # is a bank's house view rather than a decision.
    r"|\b(?:cuts?|hikes?|hiked|raises?|raised|slashed|lifted|holds?|held)\s+"
    r"(?:its\s+|the\s+|key\s+|benchmark\s+)*rates?\b"
    r"|\b(?:cut|hike|raise|lift)\w*\s+(?:rates?\s+)?by\s+\d+",
    re.I,
)


def impact_of(title: str) -> str:
    """"high" | "medium" | "low" for one headline. Pure."""
    if IMPACT_HIGH.search(title):
        if DECIDED.search(title) or not SPECULATIVE.search(title):
            return "high"
        return "medium"
    if IMPACT_MEDIUM.search(title):
        return "medium"
    return "low"

# Publisher name as it appears in a Google News title suffix — " - Reuters".
_GN_SUFFIX = re.compile(r"\s+-\s+[A-Z][A-Za-z0-9.& ]{2,30}$")


def is_section_page(title: str) -> bool:
    """True for an index page that Google indexed as though it were a story.

    A `site:` query returns an outlet's TOPIC pages alongside its articles —
    "Washington", "Donald Trump", "NFL Scores, News & Stats | Latest Super Bowl
    News". They arrive dated, they look like headlines, and they are links to a
    section front. Three shapes catch effectively all of them: a pipe (section
    fronts are titled "A | B"), a trailing SEO tail, and a title too short to
    be a sentence — a real headline has a subject and a verb, which does not
    happen in three words.
    """
    if "|" in title or "»" in title:
        return True
    tail = r"\b(news|scores|stats|headlines|latest updates|topics?|archive)\s*$"
    if re.search(tail, title, re.I):
        return True
    return len(title.split()) < 4


def _when(raw: str) -> datetime | None:
    """RFC-822 or ISO-8601, whichever the feed used. None if unparseable."""
    if not raw:
        return None
    try:
        d = parsedate_to_datetime(raw)
        return d if d.tzinfo else d.replace(tzinfo=UTC)
    except (TypeError, ValueError, IndexError):
        pass
    try:
        d = datetime.fromisoformat(raw.replace("Z", "+00:00"))
        return d if d.tzinfo else d.replace(tzinfo=UTC)
    except ValueError:
        return None


# A world feed carries the whole world, and most of it is not a market event.
# An item that arrives on one and matches no desk keyword has to clear this to
# stay: it is the difference between a geopolitics column and a tape with
# "airline defends low-altitude stunt over packed stadium" on it.
# THE POLICE BLOTTER, dropped on any desk. Observed 2026-09-01: "Man shot and
# killed in Sydney home invasion was 'targeted attack', police believe"
# (Guardian, world feed) rode the HIGH crawl beside an actual strike on Iran.
# One word did all of it — `invasion`, written for armies, matching a burglary
# — which put the story through the geo gate AND ranked it top-tier. The list
# below names crime-story shapes, not violence words: "stabbed" appears here
# and not in IMPACT_HIGH because a knife in a headline is almost never a
# market event, while "missile" is almost always one.
CRIME = re.compile(
    r"home invasion|carjack|burglar|stabb(?:ing|ed)|manslaughter|homicide|"
    r"murder (?:charge|trial|case|probe|investigation)|"
    r"(?:man|woman|teen(?:ager)?|boy|girl) (?:shot|killed|stabbed|found dead)|"
    r"shot (?:dead|and killed)|shooting at a? ?(?:school|mall|club|church)|"
    r"body (?:found|discovered)|missing (?:man|woman|child|person|teen)|"
    r"sexual assault|domestic violence|hit[- ]and[- ]run|drink[- ]driving",
    re.I,
)

# The exception that proves the rule: violence against a market figure IS
# market news — a shot CEO repriced an insurer's whole sector in 2024. If the
# same headline names one of these, the crime drop stands down and the impact
# tiers judge it like anything else.
# `\bCEO\b` — the line was once saved with two literal backspace characters
# where the word boundaries belong, so "CEO" could never match and "Insurer CEO
# shot dead" was dropped as a police story (review, 2026-10-13).
CRIME_GUARD = re.compile(
    r"\bCEO\b|chief executive|executive|founder|chair(?:man|woman)?|banker|"
    r"fund manager|hedge fund|billionaire|governor|minister|president|"
    r"central bank|trader",
    re.I,
)


def is_local_crime(title: str) -> bool:
    """A police-blotter story with no market figure in it. Pure."""
    return bool(CRIME.search(title)) and not CRIME_GUARD.search(title)


GEO_RELEVANT = re.compile(
    r"sanction|tariff|embargo|export control|\boil\b|\bgas\b|energy|shipping|strait|canal|"
    r"central bank|currency|\bdebt\b|default|election|parliament|coalition|government|"
    r"minister|president|summit|\btrade\b|supply chain|chip|semiconductor|rare earth|"
    r"wheat|grain|\bport\b|pipeline|nuclear|treaty|\bdeal\b|talks|strike|protest|"
    r"inflation|economy|economic|\bGDP\b|growth|budget|stimulus|"
    r"\bwar\b|militar|missile|drone|troops|ceasefire|(?<!home )invasion|attack|conflict",
    re.I,
)


# ---------------------------------------------------------------- off-market
#
# NOT MARKET NEWS, ON FEEDS THAT ARE MOSTLY MARKET NEWS (owner review,
# 2026-10-14). The morning's tape opened on "'I earn $110,000 a year': I lost
# my home in the Great Recession…" (MarketWatch) and "PM says housework makes
# her busier than male predecessors" (Japan Times), and further down carried a
# sumo retrospective, two NFL injury notes, a Winnie-the-Pooh exhibition and a
# celebrity's penthouse sale. Two tests, each conservative.

# WHAT A TRADING TAPE NEVER DROPS. A headline naming any of these stays,
# whatever else it looks like: a central bank, a print, a market or an index, a
# commodity or a currency, shooting or sanctions, a corporate event, a ticker,
# or one of the companies that move the indices. "'I'll Be Short Whole Year':
# Paul Tudor Jones Warns Of … Equity Supply Tsunami" opens on a first-person
# quote and is a market story — `equity` is what keeps it.
MARKET_TERMS = re.compile(
    r"\b(?:Fed|FOMC|Federal Reserve|ECB|BOJ|BoE|PBOC|RBA|RBI|SNB|central banks?|"
    r"Treasur(?:y|ies)|CPI|PPI|PCE|GDP|payrolls?|jobless claims|PMI|ISM|retail sales|"
    r"inflation|S&P|Nasdaq|Dow|Nikkei|Hang Seng|FTSE|DAX|Sensex|stocks?|"
    r"shares?|equit(?:y|ies)|bonds?|yields?|futures|oil|crude|OPEC|gold|silver|copper|"
    r"natural gas|LNG|wheat|iron ore|dollar|yen|yuan|euro|sterling|rupee|bitcoin|crypto|"
    r"war|missiles?|invasion|ceasefire|troops|military|sanctions?|tariffs?|embargo|"
    r"nuclear|earnings|IPO|merger|acquisitions?|bankrupt\w*)\b|"
    # A ticker in parentheses, "(MLM)" or "(1810.HK)".
    r"\([A-Z0-9]{1,5}(?:\.[A-Z]{1,2})?\)|"
    # The names that move NQ / ES / GC by themselves. Case-sensitive, so "shell
    # company" and "intelligence" are not Shell and Intel.
    r"(?-i:\b(?:Apple|Microsoft|Nvidia|Amazon|Alphabet|Google|Meta|Tesla|Broadcom|"
    r"Netflix|Disney|Berkshire|JPMorgan|Goldman|Morgan Stanley|Citigroup|Wells Fargo|"
    r"Bank of America|BlackRock|Walmart|Exxon|Chevron|Aramco|Shell|BP|BHP|Rio Tinto|"
    r"Toyota|Sony|SoftBank|Samsung|TSMC|ASML|Alibaba|Tencent|BYD|Xiaomi|Huawei|Boeing|"
    r"Airbus|Intel|AMD|Micron|Oracle|Salesforce|IBM|OpenAI|Anthropic|SpaceX|Palantir|"
    r"Uber|Visa|Mastercard|UnitedHealth|Eli Lilly|Novo Nordisk|MUFG|Nomura|HSBC|"
    r"Barclays|UBS)\b)",
    re.I,
)

# THE SHAPES OF A LIFESTYLE PIECE, dropped on any feed unless MARKET_TERMS
# speaks for the headline. A first-person quote opening the line is the
# advice column's signature ("'I earn…'", "'I am a pretty cautious person':
# My financial adviser…", "'I applied for 200 jobs'") — the plain first-person
# opening is already in NOISE, but a leading quote mark hid these from it.
OFF_MARKET = re.compile(
    r"^[\"'‘’“”]\s*(?:I|I['’](?:m|ve|d|ll)|my|we|we['’](?:re|ve)|our)\b|"
    r"\bmy (?:financial )?(?:adviser|advisor|planner)\b|"
    r"\b(?:earns?|earning|makes?|making|made)\s+[$£€]\s?\d[\d,.]*\s?k?\s+a\s+year\b|"
    r"\bselling (?:his|her|their)\b.{0,60}\b(?:home|house|penthouse|mansion|estate|"
    r"apartment|condo)\b|\bpenthouse\b|\bmansion\b|"
    r"\bnew episodes?\b|\bseason (?:run|finale|premiere)\b|\bfinale\b|\bdocumentary\b|"
    r"\bbox office\b|\bexhibition\b|\balbum\b|\bconcert\b|"
    r"\b(?:NFL|NBA|NHL|MLB|WNBA|NCAA|UEFA|FIFA|Formula One|Grand Prix|sumo|"
    r"Premier League|Champions League|World Series|Super Bowl)\b|"
    r"^(?:choosing|picking|finding) (?:a|an|the|your)\b",
    re.I,
)

# GENERAL-NEWS FEEDS ON A MARKET DESK, as (publisher, section) in FEEDS. Each
# is on the tape for the market stories it carries — Japan's and China's
# economy, Australia's miners, AP's economics desk, ZeroHedge's macro — and
# each also carries the rest of a newspaper: baseball, pop music, a cop-killer
# trial, a ferret census. An item on one of these that no desk keyword
# promoted has to name something economic to stay, the same bar GEO_RELEVANT
# sets for the world feeds.
GENERAL_FEEDS: frozenset[tuple[str, str]] = frozenset({
    ("Japan Times", "Japan"),
    ("SCMP", "China"),
    ("AP", "Economy"),
    ("ZeroHedge", "Markets"),
    ("ABC", "Australia"),
})

ECONOMIC = re.compile(
    r"\b(?:markets?|compan(?:y|ies)|firms?|business|industr(?:y|ial)|banks?|banking|"
    r"lenders?|investors?|invest\w*|funds?|debt|loans?|credit|prices?|pricing|exports?|"
    r"imports?|trade|econom(?:y|ies|ic)|tax(?:es)?|budget|fiscal|spending|regulators?|"
    r"fined?|fines|penalt(?:y|ies)|IMF|World Bank|OECD|G7|G20|APEC|billion|million|jobs|"
    r"wages?|layoffs?|redundanc(?:y|ies)|unions?|insolven\w*|AI|chips?|semiconductors?|"
    r"tech|mining|mines?|steel|harvest|rice|carmakers?|automakers?|EVs?|airlines?|"
    r"property|housing|deals?|ministers?|ministry|government|parliament|election|navy|"
    r"naval|warships?|aircraft carrier|carrier group|drills|recession|hurricanes?|"
    r"typhoons?|earthquakes?)\b|[$£€¥]\s?\d",
    re.I,
)


def is_off_market(title: str, publisher: str, section: str) -> bool:
    """A lifestyle piece, or a general-news item with nothing economic in it. Pure.

    `publisher` and `section` are the feed's as registered in FEEDS, not the
    outlet a Google News suffix names.
    """
    if MARKET_TERMS.search(title):
        return False
    if OFF_MARKET.search(title):
        return True
    if (publisher, section) not in GENERAL_FEEDS:
        return False
    if any(p.search(title) for _, p in PROMOTE):
        return False
    return not (ECONOMIC.search(title) or GEO_RELEVANT.search(title))


def classify(default: str, title: str, summary: str = "") -> str:
    """Which desk this headline belongs to. Pure.

    THE TITLE ONLY, never the summary. Matching the summary too was quietly
    wrong: a Bloomberg piece headlined "India's Economy Grows Faster Than
    Expected" landed on the geo desk because its blurb mentioned a border
    dispute three sentences in. The headline is what the reader is shown and
    what they judge the category against, so it is what the category is built
    from. `summary` stays in the signature because callers pass it and a future
    tie-break may want it.
    """
    for cat, pat in PROMOTE:
        if pat.search(title):
            return cat
    return default


def story_key(text: str) -> str:
    """The first eight significant words, folded — one story, many feeds."""
    words = re.sub(r"[^a-z0-9 ]", " ", text.lower()).split()
    return " ".join(words[:8])


def parse_feed(
    xml: str,
    publisher: str,
    section: str,
    default_cat: str,
    max_items: int = 25,
    via_google: bool = False,
    region: str = "global",
) -> list[dict[str, Any]]:
    """One feed's XML → tape items. Pure, so it is the part under test."""
    out: list[dict[str, Any]] = []
    for r in rss_items(xml, limit=60):
        title = r["title"].strip()
        if not title or not r["link"]:
            continue
        # GOOGLE NEWS APPENDS " - Publisher" TO EVERY TITLE, and the publisher
        # is already a column here, so the suffix is duplication eating the
        # width a headline needs. Keyed off the FEED being a Google one rather
        # than off `publisher == "Google News"`: the two wires are registered
        # under their own mastheads ("Reuters", "AP") precisely so the tape
        # attributes them correctly, which meant the strip never ran on them
        # and every AP line arrived reading "… - AP News".
        pub = publisher
        if via_google:
            m = _GN_SUFFIX.search(title)
            if m:
                # The suffix names the outlet that actually filed it, which is
                # better attribution than the query's own label.
                pub = m.group(0).lstrip(" -").strip()
                title = title[: m.start()].strip()
        if (NOISE.search(title) or is_local_crime(title) or is_section_page(title)
                or is_off_market(title, publisher, section)):
            continue
        cat = classify(default_cat, title)
        # An item that arrived on a world feed and stayed on the geo desk was
        # promoted by nothing — so it has to earn its place on a market tape.
        if cat == "geo" and default_cat == "geo" and not GEO_RELEVANT.search(title):
            continue
        when = _when(r["date"])
        summary = r.get("summary") or ""
        # A Google News summary is markup listing other outlets' versions of
        # the same story, never prose. Worse than nothing on a dense tape.
        if publisher == "Google News" or len(summary) < 40:
            summary = ""
        out.append(
            {
                "title": title,
                "url": r["link"],
                "publisher": pub,
                "section": section,
                "region": region,
                "category": cat,
                "summary": clean_text(summary)[:280],
                "utc": when.astimezone(UTC).isoformat() if when else None,
                "ts": when.timestamp() if when else None,
                "impact": impact_of(title),
            }
        )
        if len(out) >= max_items:
            break
    return out


def dedupe(items: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """One story, one line — keeping the earliest-filed copy's publisher.

    Not the newest: the desk that filed first is the one that broke it, and a
    tape that re-dates a story every time another outlet picks it up would show
    yesterday's news as breaking all afternoon.
    """
    seen: dict[str, dict[str, Any]] = {}
    for h in items:
        k = story_key(h["title"])
        if not k:
            continue
        prior = seen.get(k)
        if prior is None:
            seen[k] = dict(h, also=[])
            continue
        # Keep the earlier item; record the other publisher beside it.
        keep, drop = (prior, h)
        if (h.get("ts") or 0) and (prior.get("ts") or 0) and h["ts"] < prior["ts"]:
            keep, drop = h, prior
            keep = dict(keep, also=prior.get("also", []))
        if drop["publisher"] not in keep["also"] and drop["publisher"] != keep["publisher"]:
            keep["also"] = [*keep.get("also", []), drop["publisher"]][:4]
        seen[k] = keep
    return list(seen.values())


def collect() -> tuple[list[dict[str, Any]], list[SourceStatus]]:
    """Every feed, merged newest-first. One feed failing costs one feed."""
    items: list[dict[str, Any]] = []
    statuses: list[SourceStatus] = []
    cutoff = datetime.now(UTC) - timedelta(hours=36)

    for default_cat, url, publisher, section, region in FEEDS:
        st = SourceStatus(f"{publisher} · {section}")
        # Half an hour is as old as a feed's fallback copy may be: past that, the
        # publisher's stories are gone from the tape and its row says so,
        # rather than an old page sitting on it as though it were this morning.
        r = fetch(url, ttl_sec=110.0, ua=BROWSER_UA, timeout=18, stale_max_sec=1800.0,
                  validate=feed_body)
        st.absorb(r)
        st.source = r.source
        st.age_min = r.age_min
        if r.ok and r.source == "stale":
            st.error = f"unreachable — showing the copy from {r.age_min or 0:.0f}m ago ({r.error})"
        if not r.ok:
            st.error = r.error
            statuses.append(st)
            continue
        try:
            got = parse_feed(
                r.text, publisher, section, default_cat,
                via_google="news.google.com" in url,
                region=region,
            )
        except (re.error, ValueError, TypeError) as e:
            st.error = f"parse: {e}"
            statuses.append(st)
            continue
        # Undated items are kept: several feeds omit pubDate entirely, and
        # dropping them would silently lose whole publishers.
        got = [g for g in got if g["ts"] is None or datetime.fromtimestamp(g["ts"], UTC) > cutoff]
        items.extend(got)
        st.ok = True
        st.items = len(got)
        st.last_ok_utc = datetime.now(UTC).isoformat()
        statuses.append(st)

    merged = dedupe(items)
    # Undated items sort to the bottom rather than to 1970.
    merged.sort(key=lambda h: (h.get("ts") or 0), reverse=True)
    return merged[:400], statuses
