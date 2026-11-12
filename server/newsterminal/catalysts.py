"""
How much a headline matters — one grade, read by the score, the pool and the tables.

WHY GRADE IT (owner, 2026-11-09: "news is the engine of moves"). The signal log
agrees, as far as it can: on the seven sessions with enough of both, signals with
news behind them reached +2R 47.5% of the time against 35.8% with none, and held
+0.96 R against +0.27 R, on both halves of the record, though no more often
reached +1R (44 signals, in-sample). So news makes a move run; it does not make
a level hold.

BUT THE NEWEST STORY IS THE WRONG TEST. On all five of the biggest breakouts of
Friday 6 Nov that were checked, the newest headline was an analyst's note written
AFTER the move: IRTC's was "Cut to Neutral From Buy by Citigroup", while the
cause, five stories further down, was "iRhythm plunges after Q3 miss". The score
paid a price-target tweak the same twelve points as an earnings beat, and an FDA
approval or a takeover nothing, because neither looks like a rating.

THE TIERS.
  1  Major — it changes what the company is worth today: a report, guidance, an
     FDA or trial readout, a deal, a contract, an offering, a probe, or a story
     that names why the stock moved.
  2  Notable — someone with a following changed their mind: an upgrade, a
     downgrade, an initiation.
  3  Minor — a price-target tweak, a reiteration, a preview, a stock list, and
     a move with no reason given ("Micron, Amkor and Nvidia shares skyrocket").
  0  Noise — the law firms' "investors have an opportunity to join" notices.
     Counted for nothing, and shown nowhere.

WHOSE STORY IT IS (owner, 2026-11-10: "news is what stocks actually move on since
we trade high momentum and volume break and retests"). Read against the Scanner at
03:20 ET that morning, 30 of 33 names had nothing from their news, and one of the
three that did was paid for another company's: GOOGL +8 for "AMD Stock Rises On
Google Cloud Deal, Wall Street Upgrade". A feed for a ticker carries any story that
names it. So a story counts for the name it LEADS with (`about`), and a story that
says the name moved and why counts in the move's direction (`moved`): 21 major
stories since the close that morning, "Broadcom Stocks Jump 8.21% as Investors Eye
$21.7 Billion AI Revenue Guide" among them, had earned nothing because they read
like a price move rather than a rating.

These are words on a headline, not a judgement of the story; a rough rule that
sorts the common cases. Pure, and `tests/test_catalysts.py` keeps the examples.
"""

from __future__ import annotations

import re
from collections.abc import Sequence
from functools import lru_cache
from typing import NamedTuple

MAJOR, NOTABLE, MINOR, NOISE = 1, 2, 3, 0


class Grade(NamedTuple):
    tag: str
    tier: int


_NOISE = re.compile(
    r"class action|shareholder (alert|investigation|rights)|investors? (have|who|are encouraged|"
    r"should|with losses)|law firm|law offices|\bLLP\b|pomerantz|rosen law|levi & korsinsky|"
    r"bragar eagel|faruqi|hagens berman|robbins geller|kessler topaz|lead plaintiff|"
    r"deadline alert|securities (fraud|litigation)|investigation (of|on behalf)",
    re.I,
)
# WRITTEN TO A TEMPLATE ABOUT ANY STOCK ON ANY DAY (audit, 2026-11-11; owner: "make sure
# it's only getting news that can actually impact the market and stocks"). Read line by
# line that morning, 42 of the 254 stories held under the thirty-six names were these,
# most of them under Yahoo's name: the fund-flow line ("ETFs Are Buying Amazon (AMZN) on
# Monday", "Micron (MU) Sees $554.6 Million in Net ETF Buying on Nov. 9", "What iShares
# MSCI USA Min Vol Factor ETF (USMV) Bought: Microsoft Leads"), the fair-value line
# ("Dell (DELL) Stock May Be 42% Undervalued Following AI Server Backlog News"), the
# comparison ("INTC vs. TSM: Which Semiconductor Stock Has More Upside Now?"), the
# index-tracker's note ("Here's Why Oracle (ORCL) Fell More Than Broader Market"), the
# formal name with a question hung on it ("Oracle Corporation (ORCL) Is Joining the $1.2
# Trillion AI Spending Boom: Is the Risk Being Overlooked?") and the rich-list item
# ("Cathie Wood Dumps $3 Million of This Magnificent Seven Stock" was Amazon's lead
# story). None says anything happened to the company. Noise: scored nothing, shown
# nowhere, like the law firms' notices.
_FILLER = re.compile(
    r"\bETFs? (?:are|were) (?:buying|selling)|\b\d+ ETFs (?:add|trim|cut|sell|buy)|"
    r"\bnet ETF (?:buying|selling)\b|\bin ETF (?:buying|selling)\b|\bETFs pile in\b|"
    r"\bETF buying after\b|^what .{3,90} (?:bought|sold):|"
    r"\b\d+% (?:under|over)valued\b|\b(?:under|over)valuation case\b|"
    r"\b(?:still|may|might|could) (?:still )?(?:look|be|seem) (?:\d+% )?(?:under|over)valued\b|"
    r"\b(?:below|above) fair value\b|\bvaluation (?:test|check)\b|\bintrinsic value\b|"
    # The verdict-as-headline ("Sandisk Appears a Highly Lucrative Investment After
    # Recent AI Meltdown" led Sandisk's row the minute the rest of its filler went).
    r"\bappears (?:to be )?an? (?:\w+ ){0,3}(?:investment|buy|bet|pick|opportunity)\b|"
    r"\blucrative investment\b|"
    r"\bvs\.? .{2,60}: which\b|\bor [A-Z][\w.&-]*: which\b|which .{0,40}\bstock (?:is|has)\b|"
    r"\bis a trending stock\b|\bfacts to (?:know|note)\b|bigger fall than the market|"
    r"\b(?:fell|rose|gained|dipped|slid) more than (?:the )?broader market\b|"
    r"\bregisters a bigger\b|\blaps the stock market\b|\bsurpasses market returns\b|"
    r"\bnet worth\b|\bcathie wood\b|"
    r"\bhold (?:it )?forever\b|\bfor the next decade\b|\bbuy and hold\b|\bin my \d0s\b|"
    r"\bdear .{2,40} fans\b|^correction to\b|^weekly recap:|^social buzz:|\bwallstreetbets\b|"
    # A digest of a call that has been held: the report was the event.
    r"\bearnings call (?:highlights|transcript)\b|^q[1-4] rundown:|"
    r"\bvs\.? other\b.{0,40}\bstocks\b|"
    # A multiple is arithmetic on the price, whatever word follows it ("Netflix trades at
    # under 18x earnings after a steep valuation reset" read as a major Earnings story).
    r"\bvaluation reset\b|"
    r"\btrades at (?:under |over |about |just |around |nearly )?\d+(?:\.\d+)?x\b|"
    # The formal name and its ticker, then a question: nothing in front of it happened.
    # "Sandisk (SNDK) Dropped, So What Is Behind Its Latest Move?" was a major move
    # against a Sandisk long, ten points, by its "So" (found live, 2026-11-11).
    r"\([A-Z]{1,5}\)[^?]{0,150}[:,]\s*(?:so |and |but )?"
    r"(?:is|are|can|could|will|should|has|have|does|do|what)\b[^:?]{0,100}\?\s*$|"
    # The same question without the ticker, and the note that answers it with nothing.
    # ("… shares skyrocket, what you need to know" is not here: it says the name moved,
    # and has been a bare move, three points, since 10 November.)
    r"\bwhat(?:['’]s| is) (?:behind|going on|driving)\b|"
    r"\btake profits\b|\bor buy more\b|\bor a buy\b|"
    # A comparison is a column, whoever leads it; so is a place on somebody's list.
    r"^[\w.&'’ -]{2,40} vs\.? [\w.&'’ -]{2,40}:|\bone of \d+ (?:\w+ ){0,4}stocks\b",
    re.I,
)
# THE COMPANY TALKING ABOUT ITSELF WITH NOTHING IN IT TO TRADE (the same audit): a
# diary note ("Supermicro Announces Participation in Upcoming Investor Events" and
# "Dell Technologies to Hold Conference Call Nov. 24 to Discuss Third Quarter Fiscal
# 2027 Financial Results" were those names' lead stories; Mobileye's, filed under
# Intel, read as a major Earnings story by its "Fourth Quarter"), a ceremony ("Oracle
# Celebrates Groundbreaking on Future Global Headquarters in Nashville"), a marketing
# index. The date of a report is the calendar's to give. A product, a partnership or
# a contract is not here: those are things the company did.
_PR = re.compile(
    r"\b(?:to (?:participate|present|speak)|participation|presenting) (?:in|at)\b.{0,90}"
    r"\b(?:conferences?|summit|symposium|forum|investor (?:day|events?))\b|"
    r"\bannounces? participation\b|\bupcoming (?:investor )?(?:conferences?|events?)\b|"
    r"\bto (?:hold|host|webcast) .{0,50}\b(?:conference call|earnings call|webcast)\b|"
    r"\b(?:sets|announces|schedules) (?:the )?(?:date|timing) (?:for|of)\b|"
    # "Onfolio Holdings Sets Third Quarter 2026 Earnings Call for November 17, 2026, at
    # 8:00 a.m. ET" was a major Earnings story on the Dashboard.
    r"\b(?:sets|schedules)\b.{0,60}\b(?:earnings|results|conference) (?:call|release|date)\b|"
    # A sponsorship, and the housekeeping of a company's own debt ("World Team Tennis
    # Names Coinbase as Presenting Partner" led Coinbase's row; "BWX Technologies, Inc.
    # Announces Pricing Terms, Expiration and Results of Cash Tender Offers and Consent
    # Solicitations" was a major Earnings story by its "Results"). A tender offer for
    # another company's shares is a deal and is not here.
    r"\b(?:presenting|official|title|founding|exclusive|global) (?:partner|sponsor)\b|"
    r"\bsponsorship\b|\bconsent solicitations?\b|\bpricing terms\b.{0,60}\btender offers?\b|"
    r"\btender offers? (?:and|for) .{0,60}\b(?:notes|debentures|bonds)\b|"
    r"\bcelebrates?\b|\bgroundbreaking\b|\bbreaks ground\b|\bribbon[- ]cutting\b|"
    r"\bgrand opening\b|\b(?:sovereignty|sustainability|readiness|trends?|confidence) index:|"
    r"\brecogni[sz]ed (?:as|by|for)\b|\bnamed (?:a |an |one of |to )(?:the )?"
    r"(?:leader|best|top|most|fortune|forbes|time)\b",
    re.I,
)
_LIST = re.compile(
    r"stocks? (moving|to watch|to buy|that)|\bmovers\b|top (gainers|losers)|biggest (gainers|"
    r"losers|movers)|stock market today|bulls and bears|market (wrap|update|recap)|"
    r"\bstocks? (rise|fall|close|open|end|slide|climb)\b|why .{0,40} (stock|shares) (is|are)\b|"
    # The digests and the templates (audit, 2026-11-11): "Zacks Industry Outlook
    # Highlights Union Pacific, CSX and Norfolk Southern" was UNP's Earnings story, by
    # its "outlook", and "AM Markets Need to Know: Huang faces FBI probe … and more"
    # cost SPCX ten as a probe of its own.
    r"\bzacks\b|bull of the day|bear of the day|markets? need to know|\band more\s*$|"
    r"things to know|morning (brief|bid|call|wrap)|week ahead|key (facts|takeaways)|"
    r"what you should know|here['’]?s (why|what)|trending stock|investors heavily search|"
    r"brokers suggest|\b\d+ (reasons|things)\b",
    re.I,
)
# A PREVIEW IS TALK ABOUT A REPORT THAT HAS NOT HAPPENED. Widened 2026-11-11: "Will
# Broadcom Inc. (AVGO) Beat Estimates Again in Its Next Earnings Report?" earned AVGO
# the whole twenty as an earnings beat, and "Home Depot (HD) Reports Next Week: Wall
# Street Expects Earnings Growth" and "HD Q3'26 Earnings: revenue estimate is 42.79B
# USD" were both its major Earnings story a week before the report.
_PREVIEW = re.compile(
    r"what to (expect|look for|watch)|earnings preview|"
    r"(ahead of|before|into|heading into|going into) "
    r"(its |the |q[1-4] |quarterly |earnings |next )*(earnings|results|report|print)\b|"
    r"expected to report|will report|set to report|scheduled to report|"
    r"to (report|announce) .{0,40}(results|earnings)|to (host|hold) .{0,40}call|"
    r"(results|earnings) (date|release date|conference call)|earnings call is live|"
    r"next (earnings|quarterly) report|"
    r"reports? (next week|tomorrow|this week|on (mon|tues|wednes|thurs|fri)day)|"
    r"(wall street|analysts?|the street) (expects?|projects?|forecasts?)\b|"
    r"(expected|likely|poised|predicted|projected) to (beat|miss|top|post|deliver|surpass|grow)|"
    r"(revenue|earnings|eps|sales) estimates? (is|are|of|at)\b|"
    r"earnings (on the horizon|on deck|to watch|countdown)|countdown to|in the cards",
    re.I,
)
# AN OPINION IS SOMEBODY ASKING WHAT TO DO, NOT SOMETHING THAT HAPPENED: advice, a
# headline that is one question, or a statement followed by one ("ARM Just Dropped
# 13% After Earnings. Is It Time to Sell, or Load Up?", "Apple Inc. (AAPL) Rallied
# 15% as Investors Reassessed Its Growth: What's Next for the Stock?"). A move's own
# teaser after a colon ("… Drops 31% on $115 Billion Deal: Is the Selloff Overdone?")
# is left alone: the move in front of it is the news.
_ASKS = r"\?\s*(?:[-–—|]\s*[\w. ]+)?$"
_OPINION = re.compile(
    r"should you (buy|sell|hold|worry)|time to (buy|sell)|buy,? sell,? or hold|buy or sell\b|"
    r"is it (a buy|too late|time to)|better buy\b|\bload up\b|buy the dip|"
    r"what['’]?s next for|"
    # A forecast of a move is not the move: "How Micron Stock Can Soar 148% and End Its
    # Slump" read as Micron's own move (audit, 2026-11-11).
    r"\b(?:can|could|may|might|will) (?:soar|surge|jump|rally|climb|rise|double|triple|"
    r"skyrocket|plunge|crash|fall|drop|sink)\b|"
    # A verdict on a move, and a columnist's reading of a report (the same audit:
    # "Marvell Stock's Selloff Is Overdone as …" was a major move against a long, and
    # "Robinhood's Latest Earnings Report Tells You All You Need to Know About …" a
    # major Earnings story).
    r"\bis overdone\b|\btells you (?:all|everything)\b|\ball you need to know\b|"
    r"\bthese \d+ numbers\b|"
    rf"^(?:will|can|could|should|is|are|does|do|did|has|have)\b.*{_ASKS}|"
    rf"\.\s+(?:will|can|could|should|is|are|was|does|did)\b[^.]*{_ASKS}|"
    # The question hung on a comma, advice by its first word, and a dismissal: "As
    # Democrats Take Over Congress, Is Palantir Stock at Risk?", "INTC Stock Down 57% in
    # the Past 6 Months: Should You Exercise Caution?", "Forget Palantir? This IPO …".
    rf",\s+(?:is|are|will|can|could|should)\b[^,.]*{_ASKS}|\bshould you\b|^forget\b",
    re.I,
)
# AN EXPLAINER IS SOMEBODY'S ACCOUNT, NOT THE EVENT (the same audit: "Why Alphabet and
# Amazon Will Always Need Nvidia" was both names' lead story, "What Nebius Group Buyers
# Were Betting On"). Only where the headline carries no move: "Why Sandisk Stock Dropped
# Again on Tuesday" still says the name moved, and stays a bare move.
_EXPLAINER = re.compile(r"^(?:why|how|what)\b", re.I)
_TARGET = re.compile(
    r"price target|\bpt\b|maintains|\bis maintained at\b|reiterat|raises? target|cuts? target|"
    r"lifts? target|"
    r"(lowers?|trims?) target",
    re.I,
)
_RATED = (r"strong buy|buy|sell|hold|neutral|outperform|underperform|overweight|underweight|"
          r"equal[- ]weight|market[- ]perform|sector[- ]perform|peer[- ]perform|in[- ]line|"
          r"accumulate|reduce")
_RATING = re.compile(
    r"downgrad|initiat\w* (?:coverage|at\b|with\b)|coverage initiated|"
    rf"initiat\w*[^.]{{0,40}}\b(?:{_RATED})\b|"
    r"(?:resumes?|assumes?|starts?) coverage|cut to (neutral|hold|sell|underperform|underweight|"
    r"market perform|sector perform|equal[- ]weight|in[- ]line|peer perform)|"
    r"raised to (buy|outperform|overweight|strong buy)",
    re.I,
)
# "UPGRADE" IS AN ANALYST'S WORD ONLY IN AN ANALYST'S SENTENCE (audit, 2026-11-11: "Home
# Depot brings back viral Christmas tree with major holiday upgrade" was a notable
# rating change and cost HD's short six). It counts when the stock was upgraded (the
# passive: "Coinbase upgraded"), when a rating or a firm is named, or when the headline
# talks about the stock, and never when the thing upgraded is a product.
_UPGRADE = re.compile(r"\bupgrad(?:e[sd]?|ing)\b", re.I)
_UP_PRODUCT = re.compile(
    r"\b(?:software|system|hardware|network|holiday|chip|platform|app|fleet|store|"
    r"infrastructure|grid|product|free|autopilot|fsd|ios|windows|android|iphone|ipad|mac|"
    r"model|memory|security|firmware|engine|battery|capacity|facility|plant|service|feature|"
    r"design|technology|digital|cloud|data[- ]cent(?:er|re)|ai|tree|menu|website|site|"
    r"terminal|cabin|seat|loyalty|membership|plan)\s+upgrad|"
    r"\bupgrad\w*\s+(?:cycle|program|kit|path|package|rollout|costs?|work|project)\b|"
    r"\bupgrad\w*\s+(?:its|their)\s+(?!rating|view|recommendation|stance|outlook|price)|"
    rf"\bupgrad\w*\s+to\s+(?:its|the|a)\s+(?!(?:{_RATED})\b)",
    re.I,
)
#: "Coinbase upgraded", "upgraded to Buy", "upgraded at Citi": the stock was. Not "its
#: upgraded cabins", where the word describes a thing.
_UP_PASSIVE = re.compile(
    r"\bupgraded\b(?=\s*(?:$|[,;:]|(?:to|at|by|from|on|as|after|despite|amid|following|with|"
    r"ahead)\b))", re.I)
_UP_RATED = re.compile(
    rf"\bupgrad\w*\b[^.;]{{0,60}}\b(?:{_RATED})\b|\b(?:{_RATED})\b[^.;]{{0,30}}\bupgrad", re.I)
_UP_SAYS = re.compile(
    r"\b(?:analysts?|rating|wall street|brokerage|broker|price target|coverage|stock|shares|"
    r"morgan stanley|goldman|jpmorgan|j\.p\. morgan|citi|citigroup|bofa|bank of america|"
    r"wells fargo|barclays|ubs|deutsche|jefferies|piper sandler|oppenheimer|keybanc|"
    r"raymond james|evercore|bernstein|wedbush|needham|stifel|mizuho|rbc|bmo|td cowen|cowen|"
    r"baird|truist|susquehanna|cantor|loop capital|rosenblatt|wolfe|hsbc|macquarie|"
    r"guggenheim|canaccord|benchmark|d\.?a\.? davidson|william blair|morningstar|argus|"
    r"daiwa|nomura|clsa|redburn|melius|btig|scotiabank|seaport|northland|roth|kbw)\b",
    re.I,
)
_UP_FIRM = re.compile(r"\b[Uu]pgrad\w*\s+(?:by|from|at)\s+[A-Z]")


def analyst_upgrade(title: str) -> bool:
    """Is this headline an analyst raising a rating, and not a product getting better?
    Pure."""
    t = title or ""
    if not _UPGRADE.search(t) or _UP_PRODUCT.search(t):
        return False
    return bool(_UP_PASSIVE.search(t) or _UP_RATED.search(t) or _UP_SAYS.search(t)
                or _UP_FIRM.search(t))
_GUIDE = re.compile(
    r"(rais|cut|lower|hik|slash|lift|withdraw|reaffirm|boost|trim)\w* .{0,40}"
    r"(guidance|outlook|forecast)|(guidance|outlook|forecast) (cut|raise|hike|lowered|slashed)",
    re.I,
)
_EARN = re.compile(
    r"\bearnings\b|\bresults\b|\bq[1-4]\b|\b(first|second|third|fourth)[- ]quarter\b|\bquarterly\b|"
    r"\beps\b|\bbeats?\b|\bmiss(es|ed)?\b|\bprofit\b|guidance|outlook|\bforecasts?\b",
    re.I,
)
_FDA = re.compile(
    r"\bfda\b|\bphase (1|2|3|i{1,3})\b|\bclinical\b|\btopline\b|\bprimary endpoint\b|"
    r"\bcomplete response\b|\bpdufa\b",
    re.I,
)
_DEAL = re.compile(
    r"\bacqui(re|res|red|ring|sition)\b|\bmerger\b|\bmerge\b|\btakeover\b|\bbuyout\b|"
    r"\btake[- ]private\b|definitive agreement",
    re.I,
)
_CONTRACT = re.compile(r"\bcontract\b|\bawarded\b|\bwins?\b.{0,40}\b(deal|order)\b", re.I)
_OFFERING = re.compile(
    r"\b(public|secondary|stock|share|equity|convertible|notes?|registered direct)\s+offering\b|"
    r"\bprices? .{0,40}offering\b|\bat-the-market\b",
    re.I,
)
_LEGAL = re.compile(
    r"\bprobe\b|\bsubpoena|\bdoj\b|\bsec (charges|sues|probe)\b|\bbankrupt|\bchapter 11\b|"
    r"\brecall\b|\bantitrust\b|\bfraud\b",
    re.I,
)
# ---- a move, and which way ---------------------------------------------------------
# THE VERB NAMES THE DIRECTION. Explicit forms, not stems: "surg\w*" is also surgery,
# "tank\w*" a tanker, "zoom" and "rocket" are companies.
_UP = (r"soars?|soared|soaring|surges?|surged|surging|jumps?|jumped|jumping|"
       r"rall(?:y|ies|ied|ying)|climbs?|climbed|climbing|ris(?:e|es|en|ing)|rose|gains?|"
       r"gained|gaining|spikes?|spiked|spiking|pops|popped|rocketed|rocketing|"
       r"skyrockets?|skyrocketed|skyrocketing|leaps?|leapt|leaped|leaping")
_DOWN = (r"plunges?|plunged|plunging|sinks?|sank|sunk|sinking|tumbles?|tumbled|tumbling|"
         r"slumps?|slumped|slumping|crash|crashes|crashed|crashing|drops?|dropped|dropping|"
         r"fall|falls|fell|falling|slides?|slid|sliding|dives?|dove|diving|tanks?|tanked|"
         r"tanking|plummets?|plummeted|plummeting|nosedives?|nosedived|slips?|slipped|"
         r"slipping|craters?|cratered|cratering|skids?|skidded|sell[- ]?off|sells off|sold off")
_MOVE = re.compile(rf"\b(?:{_UP}|{_DOWN})\b", re.I)
#: What makes a move a story: the move and why. "Axon Stock Plunges as Delayed Drone
#: Deals Hit Revenue" says why; "five chip stocks skyrocket, what you need to know" does not.
#: WHEN IS NOT WHY (audit, 2026-11-11): "Why AMD shares are rallying on Tuesday?" and
#: "Why Sandisk Stock Dropped Again on Tuesday" were major, the day read as the reason.
_WHEN = (r"(?:mon|tues|wednes|thurs|fri|satur|sun)day|today|tonight|yesterday|"
         r"the (?:day|week|month|year|session|open|close|bell)|hours|close|open")
_REASON = re.compile(
    r"\b(on|after|as|amid|following|despite|behind|thanks to|due to|ahead of)\s+"
    rf"(?!(?:{_WHEN})\b)\S", re.I)
# A MOVE OVER A WEEK OR A MONTH IS A RECAP, NOT TODAY'S NEWS: "Oklo Soars 14% in a Week
# on a Narrower Loss and a Deal …" cost OKLO's short ten, "Dell Sinks 12% in a Week" and
# "Why Netflix Stock Plunged 11% in October" read as major. The period has to follow the
# move itself, so "jumps as it guides above estimates this quarter" is still a move.
_MONTHS = (r"january|february|march|april|may|june|july|august|september|october|november|"
           r"december")
_RECAP = re.compile(
    rf"\b(?:{_UP}|{_DOWN})\s+"
    r"(?:(?:nearly|almost|about|over|more than|another|around|roughly)\s+)?(?:\d[\d.,]*\s?%?\s+)?"
    r"(?:(?:in|over|during|for)\s+(?:a|one|the (?:past|last)|this|the)\s+"
    r"(?:week|month|year|quarter)\b|"
    r"(?:this|last|past)\s+(?:week|month|year|quarter)\b|"
    rf"in\s+(?:{_MONTHS}|20\d\d)\b|year[- ]to[- ]date\b|ytd\b|so far this\b)",
    re.I)


# THE SAME HEADLINES WERE GRADED ON EVERY READ (2026-11-11, found in the session by
# sampling the running collector). The Scanner's reply asks `story` about every headline
# held under every name, and each answer is some twenty regular expressions over the
# title: with the news rules of that morning 60% of the collector's samples were inside
# `story` and 38% in `grade` itself. The reply took two seconds, an open tab asks for it
# every five, and the process sat at 100% of a core until a slide-out's own read missed
# its eight seconds ("the collector did not answer in time"). A grade is a pure function
# of the words and a few thousand headlines are in play at once, so the answers are kept.
# Nothing about a grade changes: the same function, asked once per headline instead of
# once per headline per read.
_KEPT = 32768


@lru_cache(maxsize=_KEPT)
def grade(title: str) -> Grade:
    """A headline → its tag and tier. Pure. The order of the checks is the rule."""
    t = title or ""
    if _NOISE.search(t):
        return Grade("Notice", NOISE)
    if _PREVIEW.search(t):
        return Grade("Preview", MINOR)
    if _OPINION.search(t) or (_EXPLAINER.match(t) and not _MOVE.search(t)):
        return Grade("Opinion", MINOR)
    if _LIST.search(t):
        return Grade("List", MINOR)
    if _RECAP.search(t):
        return Grade("Recap", MINOR)
    # After the kinds above, which keep their names (and none of which is held as a
    # story either: NOT_NEWS); before the events, so a template cannot read as one.
    if _FILLER.search(t):
        return Grade("Filler", NOISE)
    if _PR.search(t):
        return Grade("PR", NOISE)
    # An analyst first: "Price Target Raised After Q3 Beat" is the note, not the beat.
    if _RATING.search(t) or analyst_upgrade(t):
        return Grade("Analyst", NOTABLE)
    if _TARGET.search(t):
        return Grade("Target", MINOR)
    if _GUIDE.search(t):
        return Grade("Guidance", MAJOR)
    if _FDA.search(t):
        return Grade("FDA", MAJOR)
    if _DEAL.search(t):
        return Grade("Deal", MAJOR)
    if _OFFERING.search(t):
        return Grade("Offering", MAJOR)
    if _LEGAL.search(t):
        return Grade("Legal", MAJOR)
    if _EARN.search(t):
        return Grade("Earnings", MAJOR)
    if _CONTRACT.search(t):
        return Grade("Contract", MAJOR)
    return move_grade(t) or Grade("News", MINOR)


@lru_cache(maxsize=_KEPT)
def move_grade(title: str) -> Grade | None:
    """The grade of a headline read as a move: major with its reason, minor without,
    None when no move verb is in it. The score reaches for it when a name's own move
    reads like a market wrap ("Amazon Stocks Rise 4.05% as JPMorgan Adds It to Focus
    List": "stocks rise" is the List rule) until the name is known to lead it. Pure."""
    t = title or ""
    mv = _MOVE.search(t)
    if not mv:
        return None
    if _RECAP.search(t):
        return Grade("Recap", MINOR)
    return Grade("Move", MAJOR if _REASON.search(t, mv.end()) else MINOR)


#: The grades that describe no event: nothing happened yet, or somebody is asking what
#: to do. The score reads no direction from them (scanscore.catalyst_read).
TALK = frozenset({"Preview", "Opinion"})


# ---- whose story it is, and which way it moved ----------------------------------------
# THE LEAD IS THE HEADLINE UP TO ITS FIRST JOINER, in pieces at its commas. "AMD Stock
# Rises On Google Cloud Deal" is AMD's; "Dow Jones Soars 1,132 Points As Amazon, Tesla
# Rally" is nobody's on the list; "Marvell Sinks 36%, Lumentum Drops 31% on $115 Billion
# Deal" is both of theirs. A name leads a piece from its first words (four at most:
# "Bank of America upgrades Micron", "Organigram to Acquire Aurora"), and a lead of more
# than three pieces is a round-up, as tvnews counts a story tagged with more than three
# names.
# A FULL STOP AFTER "INC" IS NOT THE END OF THE SENTENCE (audit, 2026-11-11): "Apple
# Inc. (AAPL) Rallied 15% as …" ended its lead at "Apple Inc", so the move after it was
# nobody's. An abbreviation's stop, and an initial's, do not break the lead.
_STOP = (r"(?<!\bInc)(?<!\bCorp)(?<!\bCo)(?<!\bLtd)(?<!\bvs)(?<!\bSt)(?<!\bJr)(?<!\bSr)"
         r"(?<!\bMr)(?<!\bMs)(?<!\bDr)(?<!\bNo)(?<!\bU\.S)(?<!\b[A-Z])\.\s")
_JOIN = re.compile(
    r"\s(?:on|as|after|amid|following|despite|while|behind|thanks to|due to|ahead of|but|"
    r"vs\.?|versus|than|like|when|because|since|with|from|at|for)\s|"
    rf"{_STOP}|\s[-–—]\s|[?!]\s",
    re.I)
_PIECE = re.compile(r"[,;:]\s+")
#: A short label before a colon ("Earnings call transcript: Infineon jumps …") is
#: skipped when it names nobody; "Nvidia: …" keeps its label as the lead.
_LABEL = re.compile(r"^([^:]{1,40}):\s+")
#: A piece of the lead that opens on a company's formal name and its ticker.
_HEAD_TICKER = re.compile(r"^[^()]{2,70}\(([A-Z]{1,5})\)")
#: A piece that opens on a reporting verb is what somebody said, not who it is about.
_SAYS = re.compile(
    r"^\W*(?:says?|said|sees?|warns?|calls?|expects?|thinks?|believes?|predicts?|tells?|"
    r"adds?|notes?|argues?)\b", re.I)
_LEAD_WORDS = 4
_LEAD_PRE = r"^\W*(?:[\w'’&.$%/-]+\s+){0," + str(_LEAD_WORDS) + "}?"
ROUNDUP = 3
#: Words that may sit between a name and its verb: "Broadcom Stocks Jump", "Nvidia
#: (NVDA) Stock Is Falling", "Apple's shares pop".
_FILL = (r"(?:\s*['’]s|\s+(?:\([A-Z.$:]{1,12}\)|stocks?|shares?|share price|inc\.?|corp\.?|"
         r"ltd\.?|plc|co\.?|technology|technologies|holdings|platforms|group|systems|"
         r"is|are|was|were|has|have|just|also|now|still))*")
_MOVE_DIR = re.compile(rf"{_FILL}\s+(?:({_UP})|({_DOWN}))\b", re.I)


class _Pats(NamedTuple):
    any: tuple[re.Pattern[str], ...]
    lead: tuple[re.Pattern[str], ...]
    #: The name as the object of an analyst's sentence: "… buy rating on Strategy".
    noted: tuple[re.Pattern[str], ...]


#: An analyst's note names its company after "on": "Cantor Fitzgerald reiterates buy
#: rating on Strategy with $208 target", "Citi raises price target on Apple to $400".
#: The lead there is the firm, and the story is still the company's.
_NOTED_PRE = (r"\b(?:rating|price target|target|coverage|estimates?|view|stance|bullish|bearish|"
              rf"{_RATED})\s+(?:on|for)\s+")


@lru_cache(maxsize=4096)
def _pats(sym: str, names: tuple[str, ...]) -> _Pats:
    # A ticker is matched as written (upper case); a one-letter one only as $X or (X),
    # or every "A" in a headline would be Agilent's.
    srcs: list[tuple[str, int]] = [(rf"[$(]{re.escape(sym)}\b", 0)]
    if len(sym) >= 2:
        srcs.append((rf"(?<![\w$]){re.escape(sym)}\b", 0))
    # A short name written in mixed case is matched as written: "Arm" is the company,
    # "arm" is somebody's investment arm. A filer's upper-case word ("HOME") is not.
    srcs += [(rf"\b{re.escape(n)}\b", 0 if len(n) <= 4 and not n.isupper() else re.I)
             for n in names if n and len(n) >= 2]
    return _Pats(tuple(re.compile(s, f) for s, f in srcs),
                 tuple(re.compile(_LEAD_PRE + s, f) for s, f in srcs),
                 tuple(re.compile(f"(?i:{_NOTED_PRE})" + s, f) for s, f in srcs))


def lead(title: str, sym: str = "", names: Sequence[str] = ()) -> list[str]:
    """The headline's lead, in pieces: up to its first joiner, past a label that names
    nobody, split at its commas. Pure."""
    t = (title or "").strip()
    m = _LABEL.match(t)
    if m and not any(p.search(m.group(1)) for p in _pats(sym, tuple(names)).any if sym):
        t = t[m.end():]
    j = _JOIN.search(t)
    if j:
        t = t[:j.start()]
    return [pc for pc in _PIECE.split(t) if pc.strip()]


def about(title: str, sym: str, names: Sequence[str] = ()) -> bool | None:
    """Is the story this name's? True when the lead names it, False when only the rest
    of the headline does or the lead is a round-up, None when the headline does not
    name it at all (a feed's story under a name the table does not know: left to the
    feed's own match). Pure."""
    pats = _pats(sym, tuple(names))
    if not any(p.search(title or "") for p in pats.any):
        return None
    pieces = lead(title, sym, names)
    if len(pieces) > ROUNDUP:
        return False
    # A HEADLINE THAT OPENS ON ANOTHER COMPANY'S NAME AND TICKER IS THAT COMPANY'S (audit,
    # 2026-11-11): "AMC Global Media Inc (AMCX) Q3 2026 Earnings Call Highlights:
    # Streaming Growth and Netflix Deal ..." was Netflix's by the piece after its colon,
    # and a major Earnings story there.
    head = _HEAD_TICKER.match(pieces[0]) if pieces else None
    if (head and sym and head.group(1) != sym.upper()
            and not any(lp.match(pieces[0]) for lp in pats.lead)):
        return False
    # AND WHAT SOMEBODY SAYS IS NOT THE SUBJECT: "Dan Niles Buys Nvidia Dip, Says Apple's
    # 2011 Rally After Steve Jobs' Exit Shows …" was Apple's lead story by its second
    # piece, over an upgrade four minutes old.
    told = [pc for pc in pieces if not _SAYS.match(pc)]
    return (any(lp.match(pc) for pc in told for lp in pats.lead)
            or any(p.search(title or "") for p in pats.noted))


def moved(title: str, sym: str, names: Sequence[str] = ()) -> str | None:
    """"bull" or "bear" when the lead says THIS name moved ("Micron Soars 5% as …"),
    by the verb that follows it; None otherwise. Pure."""
    pats = _pats(sym, tuple(names))
    pieces = lead(title, sym, names)
    if len(pieces) > ROUNDUP:
        return None
    for pc in pieces:
        for lp in pats.lead:
            m = lp.match(pc)
            if not m:
                continue
            v = _MOVE_DIR.match(pc, m.end())
            if v:
                return "bull" if v.group(1) else "bear"
    return None


# ---- a story, or not one ------------------------------------------------------------
#: THE GRADES THAT DESCRIBE NO EVENT (owner, 2026-11-11: "only … news that can actually
#: impact the market and stocks"). A preview is talk about a report that has not
#: happened, an opinion asks what to do, a list names a dozen stocks, a recap is last
#: week's move. They were minor, shown under the name and read by the score: "Nebius
#: Sinks 12% in a Week" was costing a Nebius long three points the morning it was up
#: eleven per cent. They keep their grade (the score still names what it skipped) and
#: are held under no name.
NOT_NEWS = frozenset({"Notice", "Filler", "PR", "Preview", "Opinion", "List", "Recap"})
#: Sites that rewrite the day's headlines or file a note on a tokenised copy of the
#: share ("Binance Will Support Sandisk's 8-for-1 SNDKB Stock Split" under Sandisk;
#: Coinpedia's rewrite was Nvidia's ten-point catalyst that morning). Lower case.
REWRITERS = frozenset({"binance news", "coinpedia", "cryptonews", "brave new coin",
                       "crypto briefing"})


def story(title: str, sym: str = "", names: Sequence[str] = (),
          publisher: str = "", strict: bool = True) -> Grade | None:
    """The headline as a story HELD UNDER `sym`: its grade, or None when it is not one.

    Not one when it describes no event (NOT_NEWS), comes from a rewriter, or is not
    this company's: with the company's names known (`names`), the lead has to name it
    (`about` is True). A feed files any story that mentions a ticker, and one tagged
    with this ticker alone was taken on trust: "Nasdaq Futures Rally as AI Optimism
    Returns" was CoreWeave's lead story over "CoreWeave stock jumps 15% premarket after
    Q3 revenue beats estimates", and Apple's was a fund manager's piece on Nvidia while
    "Apple Raised to Buy From Hold by China Renaissance" sat four minutes old under it
    (audit, 2026-11-11: all nineteen stories that did not name their company were
    another's). A name the table has no words for is still left to its feed.

    `strict` is whether the names can be trusted to be what a headline writes: the
    table's are (sources/scanner ALIASES), a filer's first word is a guess ("GENERAL"
    for General Electric, whose headlines say GE). Not strict, a headline that does not
    name the company at all is left to the feed's tag as it always was, and only one
    that names it outside its lead is dropped: a wrong guess must not cost a name every
    story it has.

    The name's own move keeps its place: "TSMC Stocks Rise 1.64% After October Sales
    Jump 59.7% to a Record" is a List by its words and a Move once TSMC is known to
    lead it, as the score has read it since 10 November. Pure.
    """
    # Kept by its arguments (see `grade`): the names as a tuple, the publisher as it is
    # compared, so one headline under one name is one entry however it is asked.
    return _story(title or "", sym, tuple(names), (publisher or "").strip().lower(), bool(strict))


@lru_cache(maxsize=2 * _KEPT)
def _story(title: str, sym: str, names: tuple[str, ...], publisher: str,
           strict: bool) -> Grade | None:
    """`story`, on arguments that can be a key: `publisher` already lower case."""
    if publisher in REWRITERS:
        return None
    # Asked outright, not left to the grade: a template that is also a List by its
    # words ("Here's Why Oracle (ORCL) Fell More Than Broader Market") would otherwise
    # be read below as Oracle's own move.
    if _FILLER.search(title) or _PR.search(title):
        return None
    # A ROUND-UP IS NOBODY'S, WHOEVER IT IS TAGGED WITH. `about` says so for a name it
    # knows; a tag the table has no words for (an index, a name from the wide scan) was
    # never asked, so "MU, AMD, AVGO, Other Chip Stocks Surge As CoreWeave Earnings
    # Reignite AI Trade" reached the Dashboard's stock news by its NDX tag (2026-11-11).
    if len(lead(title, sym, names)) > ROUNDUP:
        return None
    g = grade(title)
    if g.tier == NOISE:
        return None
    if sym and names:
        ab = about(title, sym, names)
        if ab is False or (ab is None and strict):
            return None
        mv = moved(title, sym, names)
        if g.tag in ("List", "Preview") and mv:
            g = move_grade(title) or g
        # A MOVE IS THE NAME'S ONLY WHEN THE NAME MOVED. "Dan Niles Buys Nvidia Dip, Says
        # Apple's 2011 Rally After Steve Jobs' Exit Shows …" is about Nvidia and was its
        # major Move story, by Apple's rally of fifteen years ago, ahead of a downgrade
        # ten minutes old. Somebody else's verb leaves an ordinary story.
        elif g.tag == "Move" and mv is None:
            g = Grade("News", MINOR)
    return None if g.tag in NOT_NEWS else g


#: A headline's share of the score's catalyst part, by tier. RAISED 2026-11-10 from
#: 12 / 8 / 3 (owner: "news is what stocks actually move on"): with news behind them
#: signals ran further (the module docstring), and inside each day the catalyst was
#: worth more held R than RS, which has 25 points. A judgement on that, not a fit.
TIER_POINTS = {MAJOR: 20, NOTABLE: 12, MINOR: 3, NOISE: 0}
#: What a headline against the side costs. Major news against the trade costs 10
#: (it was 6, the same as an analyst's note); the rest are as they were, since the
#: record on news against a trade is mixed.
TIER_PENALTY = {MAJOR: -10, NOTABLE: -6, MINOR: -3, NOISE: 0}
