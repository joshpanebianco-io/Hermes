/**
 * What Hermes is told before it reads a question — assembled here, pure, so
 * the whole prompt can be held in one hand.
 *
 * THREE LAYERS, ALL OF THEM THE TERMINAL'S OWN WORDS.
 *
 *   1. The persona and the rules. The notes' rules restated for a
 *      conversation: write from the data, quote the figure where the claim is
 *      made, never do arithmetic, never issue a call. A mechanical check runs
 *      on the answer and the reader sees any figure it could not find.
 *
 *   2. The product — every tab and panel in a sentence or two, from the
 *      README, so "what is this panel?" has an answer in the terminal's
 *      vocabulary rather than a textbook's.
 *
 *   3. The live data — the digest the desk's own note is written from
 *      (server/newsterminal/ask.py), the selected scanner row, the latest note.
 *      Every figure in it is formatted as the page prints it, so a figure the
 *      model quotes is one the check can verify.
 *
 * TWO SEATS (2026-10-30). The panel beside a tab is handed that desk and
 * answers short (`askSystem`). The Hermes tab is handed the whole terminal —
 * both desks, every scanner name, both latest notes — and may answer at the
 * length and in the shape the question deserves (`hermesSystem`). The
 * grounding rules are the same words in both; only the seat and the length
 * differ, so a figure is held to one standard wherever it is quoted.
 */

/** How much of the conversation travels with each question, in the panel. */
export const MAX_TURNS = 12;
/** And on the Hermes tab, where a thread is the point. */
export const HERMES_TURNS = 24;
/**
 * Per message, in characters. Twelve thousand, not four: a reader pastes a
 * table into the chat and asks about it (2026-10-30, a day's earnings — the
 * last rows were cut off at 4,000 and Hermes said so). Still a question with
 * something attached, not a document.
 */
export const MAX_MESSAGE_CHARS = 12_000;

/**
 * What the collector hands over for a question (ask.py `context` for the
 * panel; `whole_context` for the tab, which fills the second group).
 */
export interface AskContext {
  tab: string;
  desk: "futures" | "stocks" | null;
  digest: Record<string, unknown> | null;
  selected: Record<string, unknown> | null;
  note: Record<string, unknown> | null;
  gaps: string[];
  /** The Hermes tab's whole terminal. Absent on the panel's context. */
  futures?: Record<string, unknown> | null;
  stocks?: Record<string, unknown> | null;
  scanner?: Record<string, unknown> | null;
  brief?: Record<string, unknown> | null;
  plan?: Record<string, unknown> | null;
}

const PERSONA = `You are Hermes, the assistant built into the Hermes terminal — a personal pre-session desk. Its owner trades NQ, ES and GC futures across the Asia, London and New York sessions, and US stocks and ETFs through options in the New York session on one strategy: a break of the pre-market high or low (PMH / PML) or the previous day's high or low (PDH / PDL), entered on the RETEST of that level — or on VWAP / the 8 EMA wave when price has run too far from it — read on 10-minute bars (their LE_Model script, which the Scanner ports).`;

const PANEL_SEAT = ` You sit beside the page they have open and explain anything they ask: what a panel shows, what a reading means, how a figure is worked out, a market concept, or what the live data says right now.`;

const TAB_SEAT = ` This is your own tab. The whole terminal is in front of you — both desks' live data, every scanner name, the latest Analysis brief and the latest Game plan — and the reader has come here to think something through with you rather than to check one panel.`;

const PANEL_LENGTH = `- Short and plain. Two to six sentences for a question; a few bullets for a comparison or a list. No headings. Plain words first, the term second ("the gamma flip — the price where dealer hedging changes sign").`;

const TAB_LENGTH = `- At the length the question deserves. A quick check gets a line or two. A review or a run-down gets structure: short headings (## Beats), bullets, or a small table (| Name | Reported | Estimate |) when the reader is comparing names or figures. No preamble, no padding, no closing summary. Plain words first, the term second ("the gamma flip — the price where dealer hedging changes sign").
- For a question about a trade or a setup, answer in four short parts, in this order and with these words as the headings: what the data says · what the strategy needs to see · where it is wrong · what would change the read.`;

const GROUNDING = `- Ground every claim about the market in the LIVE DATA below and quote the figure where you use it. If the data does not carry a figure, say so in words; never estimate one.
- Copy every figure exactly as the data prints it. Never add, subtract, round, convert, average or rescale a number. A mechanical check compares every numeral you write with the data, and any it cannot find is shown to the reader as unverified.
- For a concept (the vol term structure, dealer gamma, implied against realised volatility, relative strength in ATRs, VWAP, a value area…), explain it in general terms first, then tie it to the live figures.
- Context, not calls. Never tell the reader to buy, sell, go long or go short, and never say a level "will" hold. For a setup, say what the strategy needs to see (the trigger), where it is wrong (the invalidation), and what the context says for and against it.
- Say how old a figure is when it matters: the data carries as-of times and ages, CME futures on the board trail the exchange by about ten minutes, a market that is shut shows its last print (a row marked closed), option chains are fifteen minutes delayed at source, and anything listed under gaps is missing. The latest note carries age_hours: past a few hours, say how old it is before quoting it, and never present its levels or prices as current.
- Name a figure in words, never by its data key: "the pre-market move", not "ext_pct"; "relative strength against SPY", not "rs_spy".
- The scanner's score is a heuristic rank, not a probability. VIX is the weather, not a signal — it sets the regime, the side the market is paying and the stop width, never which name to pick. Keep both framings.
- Your training memory predates today. Everything about the current state of the world — a price, a level, a print, a headline, who holds an office, what the Fed is doing — comes from the data in this request or is unknown to you. General knowledge is for concepts, never for figures or news. If the question is about something the terminal does not show, say so and answer the concept only.
- A figure or a headline from an earlier turn of this chat is stale: the market has moved since. Never carry one into a new answer as current. Re-read it from the data (or a tool) before quoting it; if you cannot, say it is from an earlier turn and may have moved.`;

const TAB_SPAN = `- Both desks are in front of you. When a question spans them — a futures move and the names it hits, a stock's report and the index it weighs on — read across them, and say which desk a figure comes from when it could be either.
- The reader may paste figures of their own. Read them, say they are theirs rather than the terminal's, and put the terminal's own figures beside them where it has any.`;

const RULES = `${PERSONA}${PANEL_SEAT}

HOW TO ANSWER
${PANEL_LENGTH}
${GROUNDING}`;

const HERMES_RULES = `${PERSONA}${TAB_SEAT}

HOW TO ANSWER
${TAB_LENGTH}
${GROUNDING}
${TAB_SPAN}`;

/** The same seat on the slim picture: the glance is in front of the model, the rest is a tool call away. */
const TAB_SEAT_SLIM = ` This is your own tab. The desk at a glance is in front of you, and the whole terminal is within reach through your tools — both desks' live data, every scanner name, the latest Analysis brief and the latest Game plan — and the reader has come here to think something through with you rather than to check one panel.`;
const HERMES_SLIM_RULES = `${PERSONA}${TAB_SEAT_SLIM}

HOW TO ANSWER
${TAB_LENGTH}
${GROUNDING}
${TAB_SPAN}`;

const PRODUCT = `THE TABS — one bar for both desks (the futures books, and the stocks & options names)
- Macro (tab "terminal") — what is happening and what is scheduled. The Wire: ~40 news feeds merged into one tape, each headline on a desk (markets, companies, macro, policy, geopolitics, energy) with an impact tier — HIGH is a thing that happened. The macro board: VIX, energy, rates, FX, metals, the global indices and crypto with day-range bars. Rates: the Treasury curve 1M–30Y with basis-point changes, 2s10s / 3m10y / 5s30s, the 10Y breakeven, the fed funds futures strip and the FOMC path in basis points priced per meeting. Sector rotation: the eleven sector ETFs as excess return against SPY over 1D / 1W / 1M, and breadth as equal-weight (RSP) against cap-weight (SPY). Index movers: the top NDX / SPX names by contribution (weight × return). Economic calendar: impact-scored, actual · consensus · previous, tagged with the session it lands in. Today's prints against consensus, and the Fed path. Fed & Treasury diary: FOMC, Fed speakers, the Beige Book, coupon auctions. Earnings: the week's large caps and the watchlist's names, before the open (BMO) or after the close (AMC), estimate against actual. The sector peers reporting this week, and the cross-asset moves the names' drivers are read from.
- Structure (tab "structure") — where price is and how it is positioned. The driver board: per futures book, which way the engine's count leans, how many reads agree, and how to treat it. The book: NQ/QQQ, ES/SPY, GC/GLD, YM, RTY with day-range bars and sparklines. Session ranges: the four boxes a trader draws — Asia 20:00–00:00 ET, London 02:00–05:00, the pre-market 04:00–09:30 and New York 09:30–16:00 — and what each traded per instrument; a high or low in amber has been taken out. The data also carries the overnight as one range, 18:00 to the cash open. Volume profile: POC, VAH and VAL for the previous RTH, the completed overnight and the developing session, approximate (from 5-minute bars). Gamma levels: call walls, put walls and the gamma flip from the optional GEXYGEN service, with the regime (positive gamma dampens moves, negative amplifies); dealer gamma in ETF prices, and the index ETFs' options. Vol term structure: VIX9D, VIX, VIX3M, VIX6M and SKEW, with VIX/VIX3M against 1.00 — contango is calm, backwardation stressed. The tape count: how many market reads lean long or short (it caps the Game plan's conviction), breadth, and fuel — how much of the day's expected move is already spent. Levels: a live ladder per futures book — prior settle, prior RTH high, low and POC, the overnight high and low, today's Globex and RTH opens, VWAP since 18:00 and since 09:30, the opening range, the expected-move band and the gamma walls — each with its distance from last; and the index ETFs' own levels (SPY, QQQ, IWM): PDH, PDL, PMH, PML and VWAP, with which have been taken out. The ladder also brackets confluence bands — three or more rows inside a quarter of an ATR, named under the ladder as one level — carries the ten-minute 200 EMA as a row, and shows the daily 200 EMA beneath it as the regime line. Session ranges carries a fuel line (today's range so far against the 14-day ATR and the expected move, and whether it was spent overnight or in New York) and Volume profile a line on yesterday's shape (trend day or range day, where it closed in its range, the gap at the 18:00 reopen). The driver board votes the ten-minute 200 EMA as "10m trend" and the daily 200 EMA as "Daily 200", and the Scanner's 200 column shows each name's side of its own. The page shows one desk at a time behind a Futures / Stocks & options switch, the same switch Analysis wears. Sessions: the same four boxes with countdowns, each on the reader's own clock too, the phase headline, the next box boundary, NYSE holidays and half days.
- Scanner (tab "scanner") — the break-and-retest scanner on 10-minute bars across the watchlist. Score: a heuristic rank built from structure (levels broken), RS, entry location, volume, the market and the sector, less fuel already used; before 09:30 the volume part is "In play" instead — the gap in daily ATRs, pre-market volume as a share of an average day, and a catalyst (earnings across the open, or headlines since the close). Setup and entry: the level to retest, or VWAP / the 8 EMA wave when price is extended, with the distance in 10-minute ATRs. RS vs SPY: today's move in the name's daily ATRs minus SPY's in its own. % change (chg_pct) is the regular session against the previous close — before 09:30 it is still YESTERDAY's move; pre/post (ext_pct) is the move outside the session against the previous close (pre-market) or today's close (after hours). Neither is a distance from a level: where price sits against PMH / PML / PDH / PDL is read from the levels and the last price. Before the open nothing has broken yet — PMH / PML are still forming, every setup is a plan, and the ranks rest on relative strength and how in play a name is, not on a confirmed break; say so when asked which setup is best. RVOL: volume to now against the same time on prior sessions. PDH / PDL / PMH / PML bars: how far price has travelled toward each level, filled once broken. Trend: ▲ above PDH and PMH, ▼ below PDL and PML, ⚠ inside. Options: IV30 against RV20 read as cheap, fair or rich. The Options view adds IV rank, the expected move from the front and weekly straddles, 25-delta skew, liquidity, flow (put/call volume), the suggested 0.60-delta contract and its debit spread, and the premium at risk per contract to the stock stop. In the regular session prices are seconds old, signals land just after each 10-minute bar closes, and a contract marked "est" is its fifteen-minute-delayed quote moved through delta and gamma to the live stock price. The detail pane shows the selected name's chart, its setup, why it ranks where it does, its signals and its options. The Signal log keeps every signal and its outcome in R.
- Analysis (tab "report" on its futures half, "plan" on its stocks & options half) — the written read, behind one switch. Futures: the AI pre-session brief for Asia, London or New York and NQ, ES or GC: the thesis, a call per book with its conviction and the price that makes it wrong, the snapshot, a level ladder per book, the dealer-gamma read, catalysts, the read per book, rotation and the headlines that move price; the engine computes every table and the model writes around them. Stocks & options: the AI pre-open game plan for the top scanner names: the regime, and per name what to watch, the trigger and the invalidation, with conviction capped by the tape count.
- Hermes AI (tab "hermes") — you, on a page of your own: a chat with the whole terminal within reach — every panel above is one tool call away.
- Settings — the interface (Quiet or Classic), alerts, the options budget and the watchlist. The reader's own alert and options settings come with the live data when the request carries them; the watchlist and the pool behind it are the Scanner's.

THE STRATEGY'S MARKS
(L) is the retest signal — price came back to a broken level and held it. (E) is the entry candle on the wave. ◆ is a breakout. PMH / PML are the pre-market high and low, final at 09:30 ET. PDH / PDL are the previous regular session's high and low. The 8 EMA wave is the band between the 8, 9 and 10 EMAs. VWAP is anchored at 09:30 ET.`;

const TAB_LABEL: Record<string, string> = {
  terminal: "the Macro tab (what is happening and what is scheduled)",
  structure: "the Structure tab, on its futures half (the book, session ranges, value, the levels, gamma, the vol curve)",
  tape: "the Structure tab, on its stocks & options half (the index's levels, dealer gamma in ETF prices, the tape count)",
  report: "the Analysis tab, on its futures half (the AI pre-session brief)",
  plan: "the Analysis tab, on its stocks & options half (the AI game plan)",
  scanner: "the Scanner",
  market: "the Macro tab",
  hermes: "the Hermes AI tab",
  settings: "Settings",
};

const block = (title: string, v: unknown) => `\n${title}\n\`\`\`json\n${JSON.stringify(v, null, 1)}\n\`\`\`\n`;

const gapsBlock = (ctx: AskContext) =>
  ctx.gaps.length ? `\nDATA GAPS RIGHT NOW\n${ctx.gaps.map((g) => `- ${g}`).join("\n")}\n` : "";

/** The Hermes tab's opening picture (ask.slim_context) and the selected scanner name beside it. */
export interface SlimContext {
  tab: string;
  desk: "futures" | "stocks" | null;
  slim: Record<string, unknown>;
  selected: Record<string, unknown> | null;
}

/**
 * The tool rules, for the tool set this question was handed.
 *
 * A QUESTION ACROSS NAMES STARTS WITH THE TABLE (owner, 2026-10-31: "fix
 * hermes not calling the scanner tool"). Asked which names were closest to a
 * break and which had the cleanest options read, the model read the stocks
 * digest — whose names the cap had dropped — and told the reader the options
 * read was out of reach, without calling scanner_row once. The table is now a
 * tool of its own and the rule names the questions it is for; and no answer
 * may say the terminal lacks something before the tool or panel that holds it
 * has been asked ("make sure hermes ai has the context of the ENTIRE app").
 */
export const TOOL_RULES = (tools: string[]): string => {
  const has = (n: string) => tools.includes(n);
  const where = [
    has("scanner") && "scanner for the Scanner table",
    has("scanner_row") && "scanner_row for one stock or ETF in full",
    has("bars") && "bars for its chart",
    has("levels") && "levels for a futures book's ladder",
    has("heavyweights") && "heavyweights and event_risk for what is moving the index",
    has("wire") && "wire for why something moved",
    has("earnings") && "earnings and calendar for what printed and what is scheduled",
    has("sessions") && "sessions for the clock",
    has("note") && "note for the latest brief or plan",
    has("panel") &&
      "panel for every other panel on every tab — the driver board, session ranges, value, gamma, volatility, the expiries, the COT, rates and the Fed path, the Fed diary, cross-asset, sector rotation, index movers, the catalysts, the tape count, breadth, fuel, index options, today's prints, the pool, the signal log and record, past notes and source health",
  ].filter(Boolean);
  return [
    `YOUR TOOLS\nYou can ask the collector for more: ${tools.join(", ")}. THE DESK NOW below is a glance, not the data; the whole terminal — every tab, every panel, every scanner name, both latest notes — is behind these tools.`,
    `- Before answering about a name, a level, a headline, a print, a panel or a session, call the tool that holds it: ${where.join("; ")}.`,
    has("scanner")
      ? "- A question across scanner names — which is closest to a break, which setup or options read is best or cleanest, the strongest or the weakest, a ranking, a comparison — starts with scanner, which carries every name's setup, entry distance, breaks, options read and earnings in one line each. Then read the one to three names you single out with scanner_row, in the same round. A table line carries no contract: for a name's suggested contract, its premium and its R, read that name's scanner_row before saying anything about them. Never answer a question about the names from the glance's top list alone."
      : "",
    `- Never tell the reader the terminal does not show something until you have called the tool${has("panel") ? " or the panel" : ""} that holds it. If an answer lists dropped sections${has("panel") ? " or ask_panel_for, fetch those through panel" : ", ask for them another way"} rather than going without.`,
    `- Call several tools in one round when a question needs several. digest is a whole desk at once and large; prefer ${[has("scanner") && "scanner", has("panel") && "panel", "the narrower tools"].filter(Boolean).join(", ")}.`,
    "- Quote figures from what the tools return, never from memory. A follow-up leans on earlier turns — re-read what it needs through the tools, because an earlier answer's figures are not data. If a tool returns an error, say what is missing rather than guessing.",
  ]
    .filter(Boolean)
    .join("\n");
};

/** The reader's own settings (Settings tab, kept in their browser), as the request carries them. */
export interface ReaderPrefs {
  budget: number | null;
  zeroDte: boolean;
  alerts: { on: boolean; desktop: boolean; sound: boolean; kinds: string[]; minScore: number } | null;
}

const ALERT_KIND: Record<string, string> = {
  L: "the (L) retest",
  E: "the (E) entry",
  BO: "the ◆ breakout",
  NEAR: "90% of the way to a level",
};

/** The settings as the prompt reads them: what the Scanner's contracts and alerts are set to. */
export function prefsBlock(p: ReaderPrefs | null | undefined): string {
  if (!p) return "";
  const budget = p.budget != null ? `$${p.budget} of premium at risk on one trade` : "not set, so the Scanner shows no contract count";
  const dte = p.zeroDte ? "offered on SPY, QQQ and IWM when one is listed" : "off, so every name gets the weekly";
  const a = p.alerts;
  const kinds = a && a.kinds.length ? a.kinds.map((k) => ALERT_KIND[k] ?? k).join(", ") : "no signal kinds";
  const alerts = !a
    ? "not known"
    : a.on
      ? `on, for ${kinds}, ${a.minScore > 0 ? `names scoring ${a.minScore} or more` : "every score"}; sound ${a.sound ? "on" : "off"}, desktop notifications ${a.desktop ? "on" : "off"}`
      : "off";
  return `\nTHE READER'S SETTINGS (the Settings tab, kept in this browser)\n- Options budget: ${budget}.\n- Same-day (0DTE) contracts: ${dte}.\n- Alerts: ${alerts}.\n`;
}

/** The whole system message, for the panel beside a tab. */
export function askSystem(ctx: AskContext, sym: string | null): string {
  const where = TAB_LABEL[ctx.tab] ?? "the terminal";
  const picked = ctx.tab === "scanner" && sym ? ` They have ${sym} selected in the Scanner — "this", "it" or "the setup" most likely means ${sym}.` : "";
  const desk = ctx.desk === "futures" ? "futures" : "stocks & options";
  const from = ctx.desk === "futures" ? "the Analysis brief" : "the Game plan";
  return [
    RULES,
    `\nON THE READER'S SCREEN\nThey are on ${where}.${picked}\n`,
    `THE PRODUCT — what every tab and panel shows\n${PRODUCT}\n`,
    gapsBlock(ctx),
    ctx.digest
      ? block(`LIVE DATA — the ${desk} desk right now: the same facts ${from} is written from, figures formatted as the page prints them`, ctx.digest)
      : "\nLIVE DATA — none for this tab. Answer about the product and concepts; say plainly that live figures are on the desks' own tabs.\n",
    ctx.selected ? block(`THE SELECTED SCANNER ROW — ${sym ?? "the selected name"}: everything its row and detail pane show`, ctx.selected) : "",
    ctx.note
      ? block(`THE LATEST ${ctx.tab === "report" ? "ANALYSIS BRIEF" : "GAME PLAN"} — what the reader is reading on this tab`, ctx.note)
      : "",
  ].join("");
}

/**
 * The whole system message for the Hermes tab: the same persona and the same
 * grounding rules, the whole terminal behind them. Each block is named for
 * the desk it belongs to, so an answer that spans both can say which is
 * which; a block that is missing says so rather than disappearing, so the
 * model does not invent the desk it cannot see.
 */
export function hermesSystem(ctx: AskContext, sym: string | null, summary = "", prefs: ReaderPrefs | null = null): string {
  const from = ctx.desk === "stocks" ? "the stocks & options desk" : ctx.desk === "futures" ? "the futures desk" : "the terminal";
  const picked = sym && ctx.selected ? ` ${sym} is selected in the Scanner — "this", "it" or "the setup" may mean ${sym}.` : "";
  return [
    HERMES_RULES,
    `\nON THE READER'S SCREEN\nThey are on the Hermes AI tab, having come from ${from}.${picked}\n`,
    prefsBlock(prefs),
    summary ? `\nEARLIER IN THIS CHAT (a summary of turns no longer shown)\n${summary}\n` : "",
    `THE PRODUCT — what every tab and panel shows\n${PRODUCT}\n`,
    gapsBlock(ctx),
    ctx.futures
      ? block("LIVE DATA — THE FUTURES DESK right now: the facts the Analysis brief is written from, figures formatted as the page prints them", ctx.futures)
      : "\nLIVE DATA — THE FUTURES DESK: not available right now (see the gaps). Say so if asked about it.\n",
    ctx.stocks
      ? block("LIVE DATA — THE STOCKS & OPTIONS DESK right now: the facts the Game plan is written from, its top names in full", ctx.stocks)
      : "\nLIVE DATA — THE STOCKS & OPTIONS DESK: not available right now (see the gaps). Say so if asked about it.\n",
    ctx.scanner ? block("THE SCANNER — every name on the watchlist, one row each, best score first", ctx.scanner) : "",
    ctx.selected ? block(`THE SELECTED SCANNER ROW — ${sym ?? "the selected name"}: everything its row and detail pane show`, ctx.selected) : "",
    ctx.brief
      ? block("THE LATEST ANALYSIS BRIEF (futures) — age_hours says how long ago it was written", ctx.brief)
      : "\nTHE LATEST ANALYSIS BRIEF (futures): none stored.\n",
    ctx.plan
      ? block("THE LATEST GAME PLAN (stocks) — age_hours says how long ago it was written", ctx.plan)
      : "\nTHE LATEST GAME PLAN (stocks): none stored.\n",
  ].join("");
}

const NO_TOOLS = `NO TOOLS ON THIS QUESTION
It reads as a quick check, so answer it from THE DESK NOW below in a line or two. If it actually needs a name's row, a book's ladder, the wire or a note, say so in one line and the reader can ask again naming it.`;

/**
 * The Hermes tab's system message on the slim picture, in two parts: the
 * same persona and grounding rules, the tools it may call and the product
 * (fixed — the same bytes every turn, which the provider's cache is told
 * about, llm.ts cachePrefix), then the reader's screen, a summary of earlier
 * turns and the desk at a glance (live). A few thousand tokens where the
 * whole-terminal message was forty-seven (2026-10-30).
 */
export function hermesSlimParts(
  ctx: SlimContext,
  sym: string | null,
  extras: { summary: string; tools: string[]; prefs?: ReaderPrefs | null },
): { fixed: string; live: string } {
  const from = ctx.desk === "stocks" ? "the stocks & options desk" : ctx.desk === "futures" ? "the futures desk" : "the terminal";
  const picked = sym && ctx.selected ? ` ${sym} is selected in the Scanner — "this", "it" or "the setup" may mean ${sym}.` : "";
  const gaps = Array.isArray(ctx.slim.gaps) && ctx.slim.gaps.length ? `\nDATA GAPS RIGHT NOW\n${(ctx.slim.gaps as string[]).map((g) => `- ${g}`).join("\n")}\n` : "";
  const fixed = [
    HERMES_SLIM_RULES,
    `\n${extras.tools.length ? TOOL_RULES(extras.tools) : NO_TOOLS}\n`,
    `\nTHE PRODUCT — what every tab and panel shows\n${PRODUCT}\n`,
  ].join("");
  const live = [
    `\nON THE READER'S SCREEN\nThey are on the Hermes AI tab, having come from ${from}.${picked}\n`,
    prefsBlock(extras.prefs),
    extras.summary ? `\nEARLIER IN THIS CHAT (a summary of turns no longer shown)\n${extras.summary}\n` : "",
    gaps,
    block("THE DESK NOW — the glance: the clock, the strip, the driver board, event risk, the heavyweights, earnings, the top headlines, the scanner's top names with their entry and options read, the latest notes, and any data source that is down", ctx.slim),
    ctx.selected ? block(`THE SELECTED SCANNER ROW — ${sym ?? "the selected name"}: everything its row and detail pane show`, ctx.selected) : "",
  ].join("");
  return { fixed, live };
}

/** The two parts as one message. */
export function hermesSlimSystem(ctx: SlimContext, sym: string | null, extras: { summary: string; tools: string[]; prefs?: ReaderPrefs | null }): string {
  const p = hermesSlimParts(ctx, sym, extras);
  return p.fixed + p.live;
}

const NUM = /\d+(?:[.,]\d+)*/g;

/** A numeral as a comparable key: "30,707" = "30707", "1.10" = "1.1". */
function numKey(tok: string): string | null {
  // A comma followed by exactly three digits groups thousands; any other
  // comma is punctuation between two numbers ("3,4" is not three point four).
  const grouped = /^\d{1,3}(?:,\d{3})+(?:\.\d+)?$/.test(tok);
  const clean = grouped ? tok.replace(/,/g, "") : tok.split(",")[0];
  const v = Number(clean);
  return Number.isFinite(v) ? String(Math.round(v * 10_000) / 10_000) : null;
}

/** A key with three or more decimals rounded half up to two, as a key — on
 *  the digits, not a float ((1.005).toFixed(2) is "1.00"). Null otherwise. */
function twoPlaces(k: string): string | null {
  const m = /^(\d+)\.(\d{3,})$/.exec(k);
  if (!m) return null;
  const cents = Number(m[1] + m[2].slice(0, 2)) + (Number(m[2][2]) >= 5 ? 1 : 0);
  const s = String(cents).padStart(3, "0");
  return numKey(`${s.slice(0, -2)}.${s.slice(-2)}`);
}

/** Every numeral in a text, as keys. */
export function numeralsIn(s: string): string[] {
  const out: string[] = [];
  for (const m of s.matchAll(NUM)) {
    const k = numKey(m[0]);
    if (k != null) out.push(k);
  }
  return out;
}

/**
 * Numerals in an answer that nothing the model was shown contains. Small
 * integers pass — "the 8 EMA", "two or three names", a numbered list: a level
 * or a percentage the model invented is never a single digit, and flagging
 * every bullet's "1." would teach the reader to ignore the flag.
 */
export function unverifiedNumerals(answer: string, known: Iterable<string>): string[] {
  const k = new Set(known);
  // Two places is quoting, not rounding — the notes' rule (report.known_numerals):
  // 102.228 may be written 102.23; 15.19 written 15.2, or 4.96 written 5, may not.
  for (const n of [...k]) {
    const t = twoPlaces(n);
    if (t != null) k.add(t);
  }
  const bad = new Set<string>();
  for (const n of numeralsIn(answer.replace(NAMED, " "))) {
    if (k.has(n)) continue;
    if (/^\d{1,2}$/.test(n) && Number(n) <= 12) continue;
    bad.add(n);
  }
  return [...bad];
}

/**
 * Numerals that are names, not figures, and so never checked: an index, a
 * moving average, a tenor, an option term. "The S&P 500" was flagged as a 500
 * the data did not carry (owner, 2026-10-30) — the terminal calls it ES or
 * SPX. Anything with a unit or a currency stays a figure.
 */
const NAMED =
  /\b(?:S&P ?500|SPX ?500|Nasdaq[- ]?100|NDX ?100|Russell ?[12]000|Nikkei ?225|FTSE ?(?:100|250)|DAX ?40|(?:Euro ?)?Stoxx ?(?:50|600)|CAC ?40|Dow ?30|TSX ?60|ASX ?200|KOSPI ?200|\d{1,3}[- ]?(?:day|dma|ema|sma|yr|year)s?|\d{1,2}[- ]?[Yy]|0DTE|VIX ?(?:9D|3M|6M)|Mag(?:nificent)? ?7|Q[1-4]|(?:19|20)\d\d)\b/g;

/**
 * The unverified figures split two ways: those an EARLIER answer in this chat
 * carried (true when written, stale now — the model repeated itself instead of
 * re-reading) and those nowhere at all. The page shows them differently,
 * because the first is "may have moved" and the second is "invented".
 */
export function splitUnverified(answer: string, known: Iterable<string>, earlier: Iterable<string>): { unverified: string[]; carried: string[] } {
  const bad = unverifiedNumerals(answer, known);
  const stillBad = new Set(unverifiedNumerals(answer, [...known, ...earlier]));
  return { unverified: bad.filter((n) => stillBad.has(n)), carried: bad.filter((n) => !stillBad.has(n)) };
}
