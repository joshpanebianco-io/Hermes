<div align="center">
  <img src="docs/media/hermes-icon.png" alt="" width="128" height="128" />
  <h1>Hermes</h1>

  <p><strong>Financial Markets &amp; Macro News Terminal</strong> with two desks.
  One for <strong>US stocks and ETFs traded through options</strong>: the
  break-and-retest scanner, Cboe's option chains read for the trade, a tape count
  that caps conviction, a pre-open game plan written from the scanner's own facts,
  and Hermes to explain any figure on the screen. One for trading Nasdaq,
  S&amp;P 500 and Gold futures across the Asia, London and New York sessions — a
  live news wire, the driver board, dealer options positioning and gamma levels, the
  economic calendar, earnings, and a Fed &amp; Treasury diary — with
  <strong>AI-powered session reads</strong> built from facts the engine computed.</p>

  <p>
    <img alt="Next.js 15" src="https://img.shields.io/badge/Next.js-15-black" />
    <img alt="React 19" src="https://img.shields.io/badge/React-19-149eca" />
    <img alt="TypeScript" src="https://img.shields.io/badge/TypeScript-strict-3178c6" />
    <img alt="FastAPI" src="https://img.shields.io/badge/FastAPI-collector-009688" />
    <img alt="Python 3.11" src="https://img.shields.io/badge/Python-3.11-3776ab" />
    <img alt="Tests" src="https://img.shields.io/badge/tests-778%20passing-2ea44f" />
    <img alt="Personal use" src="https://img.shields.io/badge/data-personal%20use%20only-orange" />
  </p>
</div>

![Hermes terminal](docs/media/hero.png)

---

## The stocks & options desk

The desk for the US stocks and ETFs I trade **through options** in the New York
session — a different instrument, a different clock and a different risk unit from
the futures — so it has panels of its own: the Scanner, the game plan, the tape
count. The wire, the calendar, the vol curve and rotation are shared, because macro
moves both books. Since 2026-10-30 both desks share **one tab bar** and one header
strip, cut by what a page is for rather than which book it is about: **Macro** (what
is happening and what is scheduled), **Structure** (where price is and how it is
positioned — the book, session ranges, the volume profile, dealer gamma, the vol
curve, the tape count), **Scanner**, **Analysis** (the futures brief or the stocks
game plan, behind one switch on that tab), **Hermes AI** and **Settings**.

Every part of it is built the same way, and this section walks them in order: the
engine computes a figure, the figure opens a read of what it means for this trade,
and only at the end does a model write anything — the Analysis tab's game plan, and
Hermes when asked.

### Structure — is the tape with me?
![Macro](docs/media/market.png)

- **Tape conviction** — eleven independent reads of the tape (SPY and QQQ against
  their own levels, which way VIX is moving and its curve, sectors moving, equal
  weight against SPY, credit, the 10Y, the dollar, index volume, index leaders), each
  a vote with its threshold stated. The count is graded weak / moderate / strong and
  **caps the game plan's convictions**: one read agreeing caps a plan at 3 of 5, and
  strong is six or more agreeing with at most one against.
- **Breadth** — sectors up against down, equal weight against the cap-weighted
  index, and how many of the NDX and SPX names are up with what the top three carry.
- **Fuel** — how much of the implied day SPY and QQQ have already used, from the gap
  and the pre-market, so a break into a spent range reads as one.
- **Prints & the Fed** — the session's US releases against consensus, and the FOMC
  path meeting by meeting. **Cross-asset** — the 2Y, the 10Y, 2s10s, credit, the
  dollar, long bonds, oil, gold and bitcoin: what stocks lean on today.
- **The wire and the calendar**, shared with the futures desk; the calendar's `MINE`
  filter here means *US releases that move stocks*.

### The Scanner — break and retest, ranked
![Scanner](docs/media/scanner.png)

The **Scanner** tab is the `LE_Model.pine` scanner, computed by the engine instead
of drawn by TradingView, for the New York strategy it was written for: a name
breaks its **pre-market** or **previous-day** high (low), and the trade is the
**retest** of that level — or of **VWAP / the 8 EMA wave** when price has run too
far from the level for it to come back.

- **Every column the Pine's scanner has** — Price, Volume, % Change, Pre/Post %,
  RS vs SPY, PDH / PDL / PMH / PML Break (the script's ten-segment bars, a filled
  square once broken, dots while the pre-market range forms, amber at 90% where its
  "about to break" alert fires) and Trend (▲ ▼ ⚠) — under the script's own names,
  with the engine's score, setup and entry in front of them. An **Options** column
  set swaps them for the options read below; the ticker column stays pinned while
  the rest scroll sideways on a narrow screen.
- **The Pine, ported faithfully** — PDH / PDL from the previous regular session,
  PMH / PML from 04:00–09:29, break progress toward each level (a bar, or a filled
  square once broken), the Pine's trend and wave state, the 8/9/10 EMA wave on
  ten-minute bars, and **relative strength vs SPY and QQQ** with each move scaled by
  that name's own daily ATR. The `(L)` level-retest and `(E)` 8-EMA signals are
  replayed on confirmed ten-minute bars, in the script's own order of operations.
- **The setup, in words** — retest live, pulling back, extended (so the entry
  reference becomes VWAP or the 8 EMA), near a break, failed, or inside and
  chopping — with the entry price and price's distance from it in ten-minute ATRs.
- **The daily frame** — a year of daily bars per name: above or below the 20, 50
  and 200-day, the distance from the 52-week high, last week's range. A sixth score
  part (with the daily trend, between the averages, or against it), and a flag when
  a setup runs against it: a PDH break inside a downtrend is not the same trade as
  one at new highs.
- **Short interest** — the share of the float sold short and the days to cover,
  from FINRA via Yahoo; a short on a name past 15% carries a squeeze flag, a long
  the fuel.
- **The weather strip** — VIX, its curve (VIX/VIX3M) and VVIX, the one-day implied
  SPY move (VIX ÷ √252), SPY / QQQ / IWM against their *own* levels, the tape's
  bias (confirmed or contradicted by which way VIX is moving), and the next
  high-impact US print. **VIX never ranks a name by itself**: it is the weather,
  and it reaches a score only through the market part. The four bands (13 / 20 /
  28) score; two sub-lines inside them only change the words: **18**, the VIX's
  long-run median, below which the tape tends to mean-revert inside the day
  (dealers long gamma: the retest holds, fades work) and above which it tends to trend
  (dealers short gamma: breaks run, stops a notch wider, 1%-plus days normal),
  with the chip reading `Normal · 18+`; and **35**, panic, where the VIX's own
  mean reversion is the trade. The level is a proxy for the gamma flip, which
  the driver board reads directly, and the table says so. Every row of the table
  has two columns, *what the tape does* and *how to trade it*, the second written
  for the desk's own break-and-retest: does the retest hold, how wide the stop,
  what size. Every VIX figure's click-through also
  reads the level against its own month: the percentile of the last twenty closes,
  because an 18 after a week at 13 is not an 18 after a week at 25.

  ![The VIX bands](docs/media/vix-bands.png)
- **A ranked list, not a black box** — every score is a sum of named parts
  (structure 30 · relative strength 25 · entry location 20 · relative volume 10,
  or before the bell the gap and the pre-market volume · market 15 · the daily
  frame 6 · the catalyst 6, less penalties for a spent daily range, a print inside
  30 minutes, an after-the-close report today, a failed break, a signal in the
  first thirty minutes or the last hour, a setup against a moderate or strong
  tape, or a catalyst against the side), each listed with the points it earned.
  The **catalyst** reads direction, never a count: a report's surprise sign, a
  rating or target change, guidance raised or cut, an offering filed — with the
  side it earns, against it it costs and the headline is quoted on the row. The
  clock and tape penalties come from the signal log (36% of signals in the first
  half hour reached +1R against 60% in the hour after; longs on a short tape 41%
  against shorts 58%). It orders the list; it is a **heuristic rank, not a measured
  probability**, and the page never calls it one. What it does show is **the
  record**: under the parts, what logged signals of the same kind, side and score
  band did, with their count, from ten of them and marked small under thirty.
- **What the chart does not show** — each name's headlines (Yahoo's per-ticker
  feed, tagged rating / earnings / filing), its next or latest earnings with BMO /
  AMC and the surprise, and its SEC filings from the last three days (8-K items,
  offerings, 10-Q / 10-K) straight from EDGAR.
- **A chart for the selected name** — ten-minute candles with PDH / PDL (solid) and
  PMH / PML (dashed) as the Pine draws them, the 8 EMA wave tinted by the level
  state, VWAP, the signals where they fired, and extended hours shaded — plus a
  one-click **open in TradingView**.

  ![Scanner detail](docs/media/scanner-detail.png)
- **Alerts on every tab** — the Pine's alerts, raised by the terminal: a toast, a
  chime (rising for a long, falling for a short) and, once allowed, a desktop
  notification when a name fires an `(L)`, an `(E)`, a ◆ breakout, or gets 90% of
  the way to a level. Only live events alert — a reload or a collector restart never
  replays the morning. What fires, the minimum score and the sound are in
  Settings → Alerts.
- **The signal log** — every signal the engine saw, kept for 30 days with what it
  did afterwards **in R**, where R is the Pine's own stop idea: the best and worst
  excursion, whether +1R came before the stop, and where it stood 30 and 60 minutes
  on and at the close — and a record by group (kind, side, score band). A bar that
  touches both the stop and +1R counts as stopped. It is a record, not a forecast,
  and it says so while the sample is small; it is what the score's weights get
  calibrated against. Every signal now logs the score's parts, and
  `server/tools/fit_score.py` reports the win rate by band, each part's lift and a
  logistic slope — it never rewrites a weight; the record is read and the weights
  changed by hand with its output beside the change.
- **A pinned list, and a pool behind it** — the Pine's names by default, up to 40,
  kept by the collector; SPY, QQQ and IWM are always fetched as the benchmarks. A
  symbol Yahoo does not know backs off instead of being retried every tick. What the
  pinned list leaves of the 40 is filled from **the pool**: every US common line and
  DR at $5bn+ (about 1,600 names) read in one request from TradingView's public
  screener, gated to the ~250 that trade $500m+ a day with a 1.5%+ ATR, ranked by
  the scanner's own in-play arithmetic (the gap in the name's ATRs, the pre-market
  volume against an average day, a report in play) and promoted at four marks:
  08:00, 09:00 and 09:25 ET replace the pre-market list whole, 10:00 fills the slots
  they leave for the opening drive, and from then the list holds until the day
  rolls. A promoted row says so, with the mark and the reason; the editor shows
  today's promotions with a pin for any you want to keep, the names in play that
  did not make the cut, and a switch to turn promotion off.
- **Keyboard** — the rows are in the tab order, Enter picks one, ↑ / ↓ walk the list.

Relative volume starts at the open: Yahoo's pre-market bars carry no volume, and
the column says so rather than guessing.

### Options — Cboe's chains, read the way a trade is decided
![Scanner options](docs/media/scanner-options.png)

Every scanner name carries its options context, from **Cboe's free delayed chains**
(about fifteen minutes behind, read directly — the index ETFs every five minutes,
single names every ten, one request every ten seconds at most):

- **Is premium cheap or rich?** IV30 against 20-day realised volatility — under
  0.90 cheap, over 1.25 rich — and an **IV rank** that builds from a daily log
  (it says how many of the twenty sessions it needs it has).
- **How far does the market expect it to go?** The front expiry's at-the-money
  straddle as a dollar and percentage band — **0DTE on SPY, QQQ and IWM** when
  one is listed — and the weekly's, drawn on the chart as a dotted band.
- **Can it be traded, and should it be held?** The at-the-money spread and open
  interest graded good / ok / poor, the 25-delta skew, and a warning when earnings
  land before the expiry (implied volatility collapses after the report).
- **The contract.** For the setup's side: a long option at the strike nearest
  0.60 delta, and a debit spread selling the 0.30 delta, each with its premium,
  delta, theta and spread — and **the premium at risk to the setup's own stop**
  (stop distance × delta × 100, an approximation it names). Set a risk per trade
  in Settings → Options and it also says how many contracts that buys. Rules, not
  advice.
- **The reward half.** Each contract is also priced at the **first target** by the
  plan's own rule — what it is worth there, the reward per contract after half the
  bid-ask, and that against the risk: **the option's own R**, which the stock's
  hides. The structure the engine picks is the one with the better R when both are
  priced, the premium rule otherwise, and the card says which.
- **The earnings number.** With a report ahead: the straddle covering it, net of the
  expiry before it the event alone, against the name's close-to-close moves on its
  last four reports (Nasdaq's dates, the reaction day picked by volume) — dear,
  cheap or about right. And the **term structure**, at-the-money IV per expiry,
  where event premium shows as a front priced above the back.
- **Positioning on the name.** Open interest is logged per session, so the flow
  line reads the change since yesterday on each side and on the busiest strikes,
  and today's chain volume against the name's own twenty-session average —
  **unusual** past twice it.
- **Every figure opens what it means for this trade** — IV30, realised, the premium
  verdict, the rank, the straddle, skew, liquidity, flow and earnings, each read with
  the name's own state (rich says the spread, a rank still building says how many
  sessions it has, a flow leaning against the side says so).

  ![What the options figures mean](docs/media/options-read.png)

### Analysis — the game plan, written from the scanner's facts
![Game plan](docs/media/plan.png)

A pre-open plan for the New York session, generated on demand: pick how many names
(4 / 6 / 8 / 10) and press **Generate**. The collector reads the live scanner into
`facts` — levels, relative strength, the setup, each name's option chain, the tape
count, the weather and today's prints — and the page shows the stages as they run:
*reading the scanner's top names · placing price against PDH and PMH · reading the
option chains · weighing the prints and the tape · writing the plans*. The same
model chain as the futures brief (OpenRouter, free models first, falling through on
failure) then writes only the words.

- **The lead** — one line on the tape and what it allows: the count, the cap on
  conviction, and the setups worth taking. Under it the regime in a paragraph, then
  the facts as cards: VIX, the implied SPY day, the index lean, the tape, breadth,
  fuel, gamma and the flip, the next FOMC, macro today and the prints that matter.
- **Per name, last and closed:** the plans come after everything that describes the
  session, one closed row each — the side, the name, the conviction (never above
  the tape's cap) and the plan cut to one line — and a click opens the card: the
  plan in full, the trigger, the invalidation, the first target, **how to express
  it in options** (long or spread from implied vs realised, which expiry, earnings
  inside it), why — each reason naming its layer — and the scanner's facts beside it.
- **The facts beside the prose are the server's**, printed from the scanner, never
  from the model; a plan for a name that is not in the facts is dropped, and every
  number in the prose is checked against the data — any it cannot find is listed in
  an Unverified banner (the same guard as the futures brief).
- Also: the clock (prints, the open, lunch, the close) and the risks, read before
  the plans; the names to leave alone and on watch, after them.
- **Past plans** are kept to judge against the day, with the facts they were written
  from; select several and delete those, or every one. A plan written for a session
  that has passed says so in red at the top — its levels and prices are not today's.

### Hermes — ask about any part of it
![Hermes](docs/media/hermes.png)

The terminal's assistant, in a panel beside the page rather than over it: the **Ask
Hermes** key on the status rail, or `A`. It answers from the desk's live digest —
the same facts the plan is written from, plus the tab on screen and the Scanner's
selected name — and streams the answer as it is written.

- **Openers follow the tab.** On Macro: *what is the tape count saying, and why? is
  breadth confirming the move? how should VIX shape my stops today?* On the Scanner
  with a name selected: *explain its setup · what would trigger and invalidate it ·
  which contract fits it and why · why does it rank where it does.* On Analysis:
  *summarise the game plan · which name has the best context · what would change the
  plan at the open · explain the conviction cap.*
- **Every figure in an answer is checked** against the data the model was shown; any
  it cannot find is named under the answer, shown and marked rather than passed off.
- The thread survives closing the panel, and which model answered, and how long it
  took, is printed under each reply.

### What the engine computes and what a model writes

| Part | The engine computes | A model writes |
|---|---|---|
| **Macro** | the eleven tape reads, their grade and the conviction cap; breadth, fuel, the prints against consensus | nothing |
| **Scanner** | levels, breaks, the setup state and entry, the score and its parts, the daily frame, the catalyst's direction, the signal log | nothing |
| **Options** | implied against realised, the straddles, liquidity, skew, flow, the earnings number, the contract and its R | nothing |
| **Every click-through** | the read of each figure for this name's trade, from stated rules | nothing |
| **Analysis** | the facts: every card and every number beside the prose | the plan — lead, regime, per-name plans, what to leave alone, the clock, the risks |
| **Hermes** | the live digest the answer must quote | the answer, every figure in it checked |

### Hermes AI — the whole terminal in one chat

The side panel (`A`) answers beside the tab you have open. The **Hermes AI** tab, after
Analysis, is the same assistant on a page of its own, laid out like
the chats you know — past chats down the left, the thread in the middle, the box at
the bottom. It opens on the desk at a glance — the clock, the strip, each book's
driver board, event risk, the index heavyweights, earnings, the top headlines, the
scanner's leaders and the latest notes, a few thousand tokens in all — and reaches
for the rest with **tools**: a scanner name's whole row, a book's live levels, the
wire, the calendar, the heavyweights, the sessions, a chart's last bars, a whole
desk's digest, the latest brief or plan. Each call shows under the answer while it
runs ("Reading AMZN's scanner row"). A question about a trade is answered in four
parts: what the data says, what the strategy needs to see, where it is wrong, what
would change the read. Answers may run longer here and carry headings, bullets and
tables; every figure is still checked against the data the model was shown or
fetched, and any it cannot find is named under the answer. Past the last
twenty-four turns a chat's older turns are folded into a short summary the next
question carries, so an earlier thread still means something. Chats are kept in
this browser only. `NT_HERMES_MODEL` runs this tab alone on a model you name; by
default it uses the same free chain as the notes and the panel. The footer under
each answer shows the model, the time, the tokens it took and how many came from
the provider's cache.

A router in front of the model decides how much a question gets. A handful of checks
— the phase, whether a box is open, a strip quote — are answered from the glance
without a model at all. A quick check gets the glance, no tools and no thinking. A
name, a level, a why or a comparison gets the full kit, with the tool set of the
desk the question names (the futures set or the stocks set, not both). Tool answers
are written for a model to read, one line per headline, release or bar, so a row
costs a third of what the panel's JSON would. The fixed start of the prompt is
marked for the provider's cache, which an Anthropic model needs telling about.
`npm test` runs the router's tests; `scripts/hermes-bakeoff.mjs` compares models.

---

## The futures desk

NQ, ES and GC across Asia, London and New York: the **Macro** and **Structure** tabs,
and the futures half of **Analysis** — one bar with the stocks desk (above).

### The Wire
![The wire](docs/media/wire.png)

~40 RSS and query feeds (Reuters, AP, Bloomberg, WSJ, FT, CNBC, Nikkei Asia, SCMP,
Japan Times, the ECB, the Bank of England, the RBA and more), merged into one tape:

- **Desk classification** — every headline lands on a desk: `markets`, `companies`,
  `macro`, `policy`, `geopolitics`, `energy`. Title-only classification, because
  summaries lie about what a story is.
- **Impact tiers** — `HIGH` is a thing that *happened* (a rate decision, a strike, a
  print landing); speculation about the same event is demoted. Filterable.
- **A relevance gate** — world-feed items must earn a place on a market tape.
  Police-blotter stories are dropped on every desk (a "home invasion" is not an
  invasion), unless the story touches a market figure — violence against a CEO has
  repriced a sector before.
- **Cross-feed dedupe** that keeps the desk that filed first, encoding repair for
  double-encoded publishers, and section-page detection for query feeds.

### The driver board
Across the top of the futures Macro tab, one cell per book: which way the engine's count
leans, how many reads agree, the grade, and one line on how to treat it. Each cell
opens the full board — every driver a vote with its threshold and its reason, in
three layers: **macro** sets the direction (the 10Y's day change, the dollar,
credit, the VIX and its curve, today's inflation prints), **positioning** says how
far a move runs (dealer gamma and spot against the flip), **structure** says
whether the tape accepts it (prior value, the last session's range, the daily
frame, the daily 200 EMA, the ten-minute 200 EMA, breadth and the index leaders). A macro lean the structure rejects is named
as a **conflict**, which lowers conviction rather than picking a side. Under the
votes, the context rows that never vote: the CFTC's **Commitments of Traders**
(leveraged funds for the index futures, managed money for gold, with the net's
percentile of the year), Cboe's daily **put/call** ratios, and OpEx week. The
thresholds are the stocks desk's own where one exists, the grade is its
arithmetic, and the Analysis brief is handed the count and may not be more
confident than it.

### Session ranges, volume profile & dealer gamma
![Levels](docs/media/levels.png)

The left column's core: three panels, one price ladder each, `NQ / ES / GC` pickers on all.

- **Session ranges** — the four boxes a trader draws, in ET: Asia 20:00–00:00, London
  02:00–05:00 (on London's clock, 07:00–10:00), the pre-market 04:00–09:30 and New York
  09:30–16:00 — what each traded, from true 5-minute highs and lows, every bar on one shared price axis with the current price as a single line through all
  of them. A staircase is a trend, a stack is a range; a high or low printed in amber has
  been taken out — the handover read. Rows that are still yesterday's are dimmed. Under
  the rows, **fuel**: today's range so far against the 14-day ATR and the expected move,
  and whether it was spent overnight or in New York — has the book already done its day's
  work before the open?
- **Volume profile** — POC, VAH and VAL for three windows cut the way sessions are
  actually traded: the **previous RTH** (09:30–16:00 ET) as every session's reference,
  the **completed overnight** (18:00–09:30) once New York is trading, and a
  **developing profile** anchored at 18:00 ET through Asia/London and re-anchored at
  09:30 at the cash open. Each row draws its value area as a band, its POC as a tick,
  and live price as a marker. Built from 5-minute bars and labelled `≈` because that
  is what it is: zones, not ticks. Under the rows, **the read in words**: where the
  session opened against prior value and where price trades now — acceptance,
  the failed break and the 80% rule, the rotation day — with the prior session's
  shape (P, b, D, two distributions). The sentence opens the market-profile rules
  it is read by.
- **Gamma levels** — the seven prices where dealer hedging turns: three call walls,
  three put walls and the gamma flip for the **0DTE book**, with the regime badge
  (positive γ dampens moves; negative amplifies). Rank is drawn as chevrons —
  `▲▲▲` is the heaviest wall, not a footnote number. Sourced from a separate options
  analytics service over HTTP; if that service is down, this panel says so and shows
  nothing, because a stale gamma level is worse than none. Under the regime, **one
  sentence**: spot against the flip in points and in the book's own one-sigma day,
  the regime's rule (fade into the walls, or trade the break), the walls either
  side, OpEx week — and it opens the dealer-flow rules behind each.

### The session clock & the vol curve
![Clock and vol](docs/media/clock.png)

- **Sessions** — the same four boxes as the session ranges, each with its ET window,
  the window on your own clock, and a countdown to its open or close; a phase headline
  (*"London into the pre-market — both boxes open"*) **read off the same boxes**, so it
  can never contradict the rows beneath it, and the week is bounded by Globex (Sunday
  18:00 ET is Monday morning, not the weekend). The NEXT marker counts down to the box
  boundaries — and shows an FOMC entry **only when the Fed's own calendar says there is
  one**. NYSE **holidays and half days** come from one
  table checked against the exchange's own calendar (Thanksgiving reads as a holiday,
  the day after closes at 13:00), countdowns skip weekends, and London's markers run
  on London's clock — so the weeks when the UK and the US change DST on different
  Sundays no longer put the London open an hour out.
- **Volatility** — the VIX curve (VIX9D → VIX → VIX3M → VIX6M plus SKEW) with the
  VIX/VIX3M ratio drawn against 1.00: contango is the calm shape, backwardation the
  stressed one, and the crossover usually leads the index rather than following it.
  Under it, the **implied day** per book: the one-sigma move in NQ, ES and GC's own
  points from VXN, VIX and GVZ, how much of it today's Globex range has used
  (room / normal / stretched) and implied against twenty-day realised (cheap / fair /
  rich) — the stocks desk's own thresholds, so the two desks agree — with GEXYGEN's
  narrower 0DTE band beside it when that is up. Each row, and every VIX figure, opens
  the bands and what they mean for the desk.

### Rates, the policy path, and the FOMC meeting-by-meeting read
![Rates](docs/media/rates.png)

- The Treasury **curve** (1M→30Y) with daily basis-point changes, the classic spreads
  (2s10s, 3m10y, 5s30s) and the 10Y breakeven.
- The **fed funds futures strip** (15 months of ZQ contracts) rendered as the market's
  expected policy path.
- **FOMC path** — the strip un-mixed against the Fed's actual meeting dates into
  **basis points priced per meeting** (`Sep 16 +17bp → 3.79%`). Never "a 72% chance of
  a cut": probability framing needs an assumed move size, and this never assumes one.
  The one convention (day-count around mid-month decisions) is documented and tested.
  The path and the spreads open **what they mean**: the next decision in words, what
  the day's move in the 10Y does to each book, what the curve's shape says.
- **Cboe put/call** — the daily total, index and equity ratios with the log's
  twenty-day average, on the Volatility panel of both desks; a sentiment read for the
  week, never a timing tool for the open, and it says so.

### The book, index movers & sector rotation
![Macro](docs/media/macro.png)

- **The book** — NQ/QQQ, ES/SPY, GC/GLD, YM, RTY with day-range position bars and
  sparklines.
- **Index movers** — the top ~40 NDX/SPX names by **contribution** (weight × return),
  as a heat-map or ranked list, with the honest footer: how much of the index the
  shown names are, and what they added to it today. "NQ is down" and "NQ is down
  because two names are" are different facts.
- **Sector rotation** — the eleven S&P sector ETFs as **excess return vs SPY** (the
  only view that says anything on a day when everything is red), plus the breadth
  line: equal-weight against cap-weight, i.e. is this move the market or just its top.

### Calendar, Fed & Treasury diary, earnings
![Diary](docs/media/diary.png)

- **Economic calendar** — impact-scored, region-filterable (US/EU/UK/APAC), each event
  tagged with the trading session it lands in, and a `MINE` filter that narrows to
  releases that actually reach NQ, ES or GC. Three figures per row — `act · cons ·
  prev` — because markets move on the gap between actual and consensus, not on the
  number itself. Once a print lands it carries its **read** — hot (the stronger
  economy), cold or in line — and the chip opens what that means for NQ, ES and GC,
  by theme: a hot CPI through the discount rate, a hot payrolls through the Fed, in
  the server's words, the same ones the driver board counts.
- **Fed & Treasury** — one diary of scheduled US rates risk: FOMC meetings, the Beige
  Book, governor speeches and testimony from the Board's own calendar, merged
  chronologically with **coupon auction supply** (3Y/10Y/30Y, reopenings named what
  the market calls them) from TreasuryDirect — because a tailed 30Y at 13:01 ET is an
  equity event for the longest-duration index on the board.
- **Earnings** — the coming week's large caps ($50bn+ and bellwethers), BMO/AMC
  tagged, estimates marked with an `e`, and actuals shown against the estimate and
  coloured by the surprise once they print.

### The AI session read
![Session report](docs/media/report.png)

The Analysis tab generates a **pre-session brief** on demand: pick the session (Asia /
London / New York / auto-by-clock) and the book (NQ / ES / GC / all three). The
collector computes every table on the page from the live snapshot, then an LLM (via
OpenRouter, with a model-and-mode fallback chain) writes the read around them. Top to
bottom:

- **Partial data** — which sources were down when it was written, so a missing level
  is a stated gap rather than a silent one.
- **Thesis and calls** — the one idea of the day, then a card per book: the call at
  the open with its conviction, the rest-of-day lean, and the price that makes it
  wrong.
- **Snapshot** — the books, the dollar, the 10Y (and the real yield for gold), vol,
  oil and the yen, with week and month context; the model flags the rows to watch.
- **Levels** — a ladder per book in price order: gamma flip and walls, the
  expected-move band (GEXYGEN's own, or a one-day 1σ from VXN / VIX / GVZ when it is
  down), the overnight or handover range, prior-RTH high / low / POC and settle, each
  measured from last.
- **Dealer gamma** — regime, the flip's distance in percent and in expected moves,
  the walls.
- **Catalysts** — data, the Fed (with what each FOMC has priced), long-end auctions
  and bellwether earnings, from twelve hours back to three days out; the model notes
  the ones that matter.
- **The read** — per book: the regime, the macro transmission as a chain of causes,
  the open, the invalidation, the rest of day, what flips it, and drivers tagged
  bear / bull / mixed / neutral.
- **Rotation** — six equity ratios (or GDX/GLD and gold/silver) with five-day
  direction, the megacaps' moves, and the model's read of the tape.
- **Headlines that move price** — picked from the wire by id and tagged with the books
  they move.
- **Past calls** — every prior brief kept with its full digest and tables attached, so
  any call can be audited against exactly the data it saw.

The design principle throughout: **the engine computes, the model narrates.**

- The tables are never the model's. The page prints them from computed facts, and the
  model's notes join onto rows by id — a note pointing at an id that does not exist is
  dropped before it is stored.

- The digest is scoped to the chosen book — the instrument's own data is one block,
  everything else is explicitly `context_only`, because structure is obeyed where
  instructions are merely read.
- Headlines are re-weighted to the session's home region; the calendar block tags
  which events land inside the session being written.
- The volume-profile block states the market-profile reads **as computed facts**:
  each window's shape (P / b / D / double distribution), where the session *opened*
  relative to prior value, and where price trades *now* — above value, inside, or
  below. The model is told to cite the classifier's decisions, not to re-derive them.
- Every claim in the note must quote a figure from the digest; a hedged guess
  presented confidently is treated as worse than no note — and that is **checked**,
  not hoped for: every number in the model's prose is matched against the digest,
  the model is asked once more if any are missing, and any that survive are listed
  in an **Unverified figures** banner above the note.
- A source serving a stale cached copy when the note is written is named in the
  **Partial data** banner with the copy's age, so a brief is never written on frozen
  prices without saying so.

Reports persist to disk with their full digest attached, so any note can be audited
against exactly the data it saw.

---

## Why this exists

I trade US stocks and ETFs through options in the New York session, on one
strategy: a break of the pre-market or previous-day high (low), entered on the
retest — or on VWAP / the 8 EMA when price runs too far. The questions before the
open are always the same: is the tape with me, which names are strongest against the
market, which levels are they about to break, and what are the options pricing?

I also trade **NQ, ES and GC** futures across the **Asia, London and New York**
sessions, where the questions are different: what happened while I was away, what is
scheduled to happen while I'm trading, where are the levels that matter, and what
regime am I stepping into? Answering either set meant a dozen tabs — news sites, an
economic calendar, a rates page, a charting platform, an options dashboard.

Hermes folds all of it into one screen, in the spirit of an institutional terminal:
**everything states its own age, its own source, and its own limitations.** Every
figure that changes flashes. Every panel answers exactly one question. And an LLM
writes a session note at the end — but only from facts the engine has already
computed, never from vibes.

It is named for Hermes: god of messages, information and speed, which is the whole
job description.

---

## The screen

One tab bar for both desks — **Macro** · **Structure** · **Scanner** · **Analysis** ·
**Hermes AI** · **Settings**. Structure and Analysis carry the one desk switch — the
futures or the stocks & options read — and remember it as one choice; `1`–`6` move
between tabs, `D` flips the desk and `A` opens Hermes. Both desks are walked above. On the Macro tab,
three columns on one session clock:

| Column | Question it answers |
|---|---|
| **Left** | *What is the market doing?* — the macro board, rates & the policy path, sector rotation, index movers |
| **Middle** | *What is happening?* — the wire: ~40 feeds, classified, deduplicated, impact-ranked |
| **Right** | *What is scheduled?* — the economic calendar, today's prints and the Fed path, the Fed & Treasury diary, earnings with the watchlist marked, the sector peers reporting, cross-asset moves |

The Structure tab is the other three questions, one desk at a time behind the same
**Futures / Stocks & options** switch Analysis wears: *where are we?* — the book, session ranges,
the volume profile (with **yesterday's shape** under it: trend day or range day, the
close in its range, the gap at the reopen) and a live **levels ladder** per book (prior
settle, prior RTH, the overnight, today's opens, VWAP from 18:00 and from 09:30, the
opening range, the expected move, the walls, the ten-minute 200 EMA), with **confluence
bands** bracketed where three or more rows sit inside a quarter of an ATR and the daily
200 EMA beneath it as the regime line, and the index ETFs' own levels; *how is it positioned?* —
dealer gamma for the futures and in ETF prices, and the index ETFs' options; *is the
tape with me?* — the vol curve, the tape count, breadth, fuel and the session clock,
under the driver board.

Above them: the desk's instrument strip (with the time in New York *and* in your own zone),
and a crawl of only the **high-impact** headlines. Below: a status rail listing
**every** data source — a dot for a healthy one, and anything down or serving a
**stale** cached copy expanded with its error and age (red, or amber for stale) —
because a terminal that hides a dead feed is lying to you.

---

## The chassis

**Quiet Terminal is the default interface** — GEXYGEN's flat chassis, carried
across by copying (never by linkage): one neutral grey ramp, hairlines instead of
cards, sentence-case section titles, condensed caps labels, square markers, IBM
Plex Sans / Condensed / Mono, and a header that carries the instrument strip as
label-over-figure in one band. The data hues are the only colour on the screen.
**Classic** — the carded, neon, mono-caps chassis this terminal shipped with — is
one click away in Settings → Interface; everything Quiet changes is scoped under
`.ui-qt`, so Classic is simply the absence of the class.

Either way: three-hue discipline (a colour on a figure means calls, puts, or the
flip — decoration lives on its own tokens), an animated frame light (a
compositor-only rotation — it costs the page nothing measurable), a wordmark
and helm that wash on one shared cycle, and a change-flash on every figure that
ticks. Themes are configurable, per-panel filters persist in `localStorage`, and
the whole board is keyboard-free by design — it is meant to be *read*.

---

## What it gathers

| Source | What | Cadence |
|---|---|---|
| Yahoo Finance (spark) | 50+ instrument quotes: futures, ETFs, FX, rates, vol complex, global indices, crypto | 20s |
| Yahoo Finance (chart) | 5-minute OHLCV bars for NQ/ES/GC → session ranges & volume profiles | 1–5 min |
| Publisher RSS + query feeds | ~40 feeds across six desks, region-tagged | 2 min |
| Nasdaq | Economic calendar (consensus/actual/previous) and the earnings calendar | 10 min |
| U.S. Treasury (yields) & fed funds futures | The curve, spreads, and the ZQ strip | 30 min |
| Federal Reserve (`calendar.json`) | FOMC dates, speeches, testimony, Beige Book | 1 h |
| TreasuryDirect | Upcoming coupon auctions | 6 h |
| iShares holdings CSVs | NDX/SPX constituent weights → contribution math | daily |
| Yahoo Finance (chart, per stock) | 5-minute bars 04:00–20:00 for every watchlist name → the Scanner's levels, wave, VWAP and signals; daily bars for the ATR | ~90 s a name in session (SPY/QQQ/IWM 30 s), 15 min closed; daily 6 h |
| TradingView (public screener, one POST) | Every US common line and DR at $5bn+ with close, change, volume, 30-day average volume, 14-day ATR, pre-market change and volume, report dates → the Scanner's pool and its promotions | 5 min 04:00–10:30 ET, 30 min otherwise |
| Yahoo Finance (per-ticker RSS) | Each watchlist name's headlines | 10 min a name |
| Cboe (delayed option chains) | Each watchlist name's chain → IV, the straddle's expected move, skew, liquidity, the suggested contracts; a daily IV log for IV rank | 5 min SPY/QQQ/IWM, 10 min singles, in session; hourly otherwise |
| SEC EDGAR | Each watchlist name's filings from the last three days | 30 min a name |
| A companion options-analytics service | The seven dealer-gamma levels per book, over HTTP | 30 s |
| OpenRouter | The futures session note and the stocks game plan (configurable model, fallback chain) | on demand |

Everything flows through one **warm-snapshot collector**: a single background thread
polls each source on its own cadence into memory; the API serves reads from that
snapshot and never blocks on a fetch. Slow sources can be stale — and say so — but
the terminal itself is always instant.

```mermaid
flowchart LR
    subgraph Collector["FastAPI collector · one warm loop"]
        Q[quotes] --> S[(snapshot)]
        W[wire] --> S
        C[calendar] --> S
        R[rates] --> S
        P[profiles] --> S
        F[fed + auctions] --> S
        G[gamma sidecar] --> S
    end
    S --> API["/api/terminal"]
    API --> NX[Next.js proxy]
    NX --> UI[React terminal]
    S --> D[report digest]
    D --> LLM[OpenRouter] --> N[session note]
```

---

## Running it

Windows, Node 20+, Python 3.11+.

```powershell
npm install
cp .env.example .env.local     # add an OpenRouter key if you want session reports
.\dev.ps1                      # every half as a tab in one window, then the browser
npm run shortcut               # optional: the same thing, on the desktop
```

- Web: **http://localhost:3100** · Collector: **http://127.0.0.1:8100**
- `.\server\run.ps1` starts the collector alone — its window *is* the feed log: one
  row per source per refresh, with ages and item counts. Always start it through the
  script; it is what loads `.env.local`.
- The gamma panel reads a companion options service on `:8000`; without it, that one
  panel reports itself unavailable and everything else runs normally. `dev.ps1` will
  start that service too if it finds it beside this repo (or at `NT_GEXYGEN_HOME`) —
  a launch-time convenience only, skipped with `-NoGexygen`, and silent about every
  way it can be absent.
- Switches: `-Restart` (the collector again, in its own tab, rereading `.env.local` — how
  new Python code or a config edit goes live), `-Windows` (a window per half instead of
  tabs), `-CollectorOnly` (feeds, no web, no browser), `-NoBrowser`, `-Force`
  (start anyway, and clash), `-Prod` (the web half as a production build in
  `.next-prod` rather than `next dev` — lighter for a screen left open all day;
  `npm run prod` does the same by hand). Everything already listening is left alone, so a second
  run restarts nothing and is simply how you get the browser tab back.
- `npm run shortcut` puts a **HERMES** launcher on the desktop, winged helm and all,
  pointed at `dev.ps1`; `npm run shortcut:collector` adds a feed-only one beside it.
  The icon is `public/hermes.ico`, rendered from the same traced path as the header
  by `npm run icon` — re-run that only if the mark or its hues change.

Checks: `npm run check` runs TypeScript, ESLint, Ruff, mypy (strict) and the pytest
suite — 316 tests, most of them regression tests bought with a real observed bug:
the classifier rules, the FOMC un-mixing, the profile session windows, the
scanner's Pine port and its clock boundaries, the JSON
extractor's four observed wrappings.

---

## Honest limitations

- **Personal-use data.** The quote and news sources here are free feeds that are fine
  to read at one desk and are **not redistributable**. This repository is published as
  code; if you deploy it for anyone but yourself, replace `server/newsterminal/sources/quotes.py`
  and `wire.py` with licensed sources first. That constraint shaped the design and is
  a feature of it, not an oversight.
- **Volume profiles are approximate** — built from 5-minute bars, labelled `≈` in the
  UI, and intended as context. Execution-grade profiles belong to tick data.
- **Yahoo's extended hours are partial.** Pre-market bars carry no volume (so relative
  volume starts at the open), and earlier days come back without their post-market
  beyond the 16:00 print — so the scanner's EMA wave skips the previous evening that
  TradingView, with extended hours on, would include. The four levels are unaffected.
- **The scanner's score is a heuristic rank**, not a probability — until the signal
  log has enough settled sessions to calibrate it.
- **Free-tier LLMs are flaky.** The report chain retries across models and modes,
  parses JSON out of four kinds of wrapper, and fails loudly with the full attempt
  trail when the pools are saturated.
- **Desktop-width layout** (≥1280px). It is a terminal; it assumes a monitor.

---

## The mark

The winged helm is my own line art. In the app it lives as a single traced vector
path (`src/lib/hermesMark.ts`), recoloured live to the terminal's chrome hues. The
icon reads that same file rather than copying it, and adds only what a wallpaper
does not supply: a chassis-black tile under the lockup's green-to-pink wash. The
browser tab and the desktop shortcut share that one `.ico`, so the launcher, the tab
it opens and the page inside it are one identity.
