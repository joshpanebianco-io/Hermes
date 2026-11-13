/**
 * The terminal's tabs, in bar order — the one list.
 *
 * It used to be written out six times (the page's URL parse twice, the
 * Terminal's type and its storage guard, the header's type and its labels), so
 * adding the Scanner took four edits and any one of them forgotten would have
 * been a tab the URL could not open or storage would silently refuse.
 *
 * ONE BAR, NOT TWO DESKS (owner, 2026-10-30: "instead of having the futures
 * and stock & options toggle global, we have it in this analysis section").
 * For a fortnight the header carried a desk switch and each desk its own
 * tabs — Macro · Analysis for the futures, Macro · Scanner · Analysis for the
 * stocks — which meant two Macro tabs showing the same wire and calendar in
 * different orders, and a switch you had to flip before the tab you wanted
 * was even on the bar. Now the bar is one list for both desks, cut by what a
 * page is FOR rather than which book it is about:
 *
 *   Dashboard  the session on one page, built from the tabs below: the read,
 *              the game plan, the top setups, the list, the news, the sectors
 *              (owner, 2026-11-09)
 *   Macro      what is happening and what is scheduled — the wire, the
 *              calendar, prints and the Fed path, the diaries, earnings,
 *              rates, rotation, the movers, the macro board
 *   Sectors    where the money is: the sector and theme heat map, the industries,
 *              and the stocks in each. A Scanner view until 2026-11-10; its own
 *              tab because it answers a market question (which group is working)
 *              before the Scanner's (which stock, which level), so it sits on
 *              the bar between Macro and the Scanner, and on a side screen all session
 *   Scanner    the stocks desk's break-and-retest scanner
 *   Futures    every futures book traded, NQ, ES, GC, silver and crude: an
 *              overview of the five and a view per contract (its chart with the
 *              levels, the ladder, session ranges, the profile, gamma) and the
 *              written brief (owner, 2026-11-10: "a seperate futures section").
 *              It took Structure's place; Structure's stocks half was the
 *              Scanner's Index view until 2026-11-13 (see SCAN_VIEWS)
 *   Hermes AI  the assistant with the whole terminal in front of it
 *   Settings
 *
 * ANALYSIS IS NOT A TAB ANY MORE (owner, 2026-11-11: "do what you recommend best").
 * It held the two written notes behind a desk switch, and by then each was a
 * duplicate or a stray: its futures half was the very panel Futures already shows
 * as its Brief view, and its stocks half, the written game plan, had last been
 * generated on 29 Oct, since when the Dashboard's own game plan card has done that
 * job every morning. So each note lives with its desk: the brief is Futures → Brief,
 * the written plan is the Scanner's Game plan view, one click from the
 * Dashboard's card. The bar is seven pages (the number keys that reached them went on 2026-11-11).
 *
 * The desk therefore survives only as what a question to Hermes is labelled with:
 * the side of the terminal the reader was last on (Terminal.tsx). The keys are what
 * `?tab=` and storage hold; the old keys still resolve (`resolveTab`), so a link to
 * the report, the plan, Analysis or the Market tab opens the right place.
 */

export type Desk = "futures" | "stocks";

export const TABS = [
  { key: "dashboard", label: "Dashboard" },
  { key: "terminal", label: "Macro" },
  // Between Macro and the Scanner since 2026-11-11, at the owner's word: which group
  // is working, then which stock. It sat after the Scanner, then after Futures.
  { key: "sectors", label: "Sectors" },
  // "Stocks" on the bar since 2026-11-12 (owner: "can we change the name of Scanner to
  // Stocks?"), beside Futures: the two desks by name. Only the name the reader sees
  // changed. The key stays "scanner", so `?tab=scanner`, the remembered tab, every
  // stored `scan.*` choice and the collector's routes are what they were; and "the
  // scanner" is still what the engine that ranks the list is called.
  { key: "scanner", label: "Stocks" },
  // After the Scanner since 2026-11-11, at the owner's word; it sat after Macro.
  { key: "futures", label: "Futures" },
  { key: "hermes", label: "Hermes AI" },
  { key: "settings", label: "Settings" },
] as const;

export type Tab = (typeof TABS)[number]["key"];

export const TAB_KEYS: readonly Tab[] = TABS.map((t) => t.key);

/*
 * THE SCANNER'S VIEWS, the strip inside the Scanner. One list, so the strip, the
 * Dashboard's links into a view and the question to Hermes all name the same ones.
 * (A sidebar listed them too from 2026-11-09 to 2026-11-11, behind a setting; the
 * owner kept the top bar and it was taken out.)
 *
 * THE INDEX VIEW WENT ON 2026-11-13 (owner: "i want to streamline the
 * app and make it have the most useful informaiton visible without clutter and noise",
 * and for everything but the Dashboard "do what you think best"). It was a page of
 * eight panels about SPY, QQQ and IWM, and what a session is traded off was already
 * nearer the eye: the three and the VIX are in the band over every view, the tape's
 * lean is the Tape figure on the Setups row (its hover is the vote by vote count),
 * breadth is the Dashboard's card, the VIX's curve and the put/call ratios are on
 * Futures. What it alone drew (the three against their levels as a table, dealer gamma
 * in ETF prices, the index options, the fuel) Hermes still reads: the collector serves
 * all of it and `/api/market` is polled as before.
 *
 * ONE LIST SINCE 2026-11-13: TODAY (owner: "we really need to overhaul the whole stocks
 * scanner section ... instead we have set ups that just change and display the best
 * options for a given period"; then "yes go ahead with everything proposed"). Setups,
 * Breakouts, Extended hours and Day 2/3 were four answers to "what should I look at
 * now", each ranked its own way. Today is one list that changes what it ranks by with
 * the clock (server today.py): the evening's movers, the pre-market's names in play, the
 * open's triggers, the session's setups. The strip is Scanner, Charts (the Multicharts
 * view) and Market (the overview). The four old
 * views stay reachable for a week behind Settings → Interface (`group: "legacy"`,
 * lib/legacyViews.ts), then go. A browser that remembers one of them opens Today.
 */
export const SCAN_VIEWS = [
  // Called Today until 2026-11-13 ("i think we hsould rename 'today' to Scanner"); the key stays.
  { key: "today", label: "Scanner", group: "main", title: "The best stocks for the hour it is: the evening's movers, then what is in play into the open, then the session's setups from the bell" },
  { key: "multi", label: "Charts", group: "main", title: "Six live charts of the list's best names, three across and two down" },
  // No Record view since 2026-11-13 ("can we get rid of the record section completely"):
  // the signal log is still kept on the server, read by the score card and Hermes.
  // The stocks half of what was the Analysis tab. Next to Record (owner, 2026-11-13: "can we
  // move game plan next to Record?"); it was a button on Today for an hour. Later the same day
  // the per-name plans gave way to a market overview, and the view was renamed Market (the
  // key stays "plan": the routes, the store and Hermes's tab name are the plan's).
  { key: "plan", label: "Market", group: "main", title: "The market overview, written at 09:00 ET: the indexes against their levels, the sectors, the macro, the news that matters and what it means for today's list" },
  { key: "setups", label: "Setups", group: "legacy", title: "The list, ranked: levels, signals, the score and the options" },
  { key: "breakouts", label: "Breakouts", group: "legacy", title: "Every US stock against its levels" },
  { key: "extended", label: "Extended hours", group: "legacy", title: "The pre-market and after-hours gappers" },
  { key: "day23", label: "Day 2/3", group: "legacy", title: "The big movers, and whether they are still moving" },
] as const;

export type ScanView = (typeof SCAN_VIEWS)[number]["key"];

export const SCAN_VIEW_KEYS: readonly ScanView[] = SCAN_VIEWS.map((v) => v.key);

/** The views the strip and the sidebar list: the main four, and the old four while
 *  Settings keeps them. */
export function stripViews(legacy: boolean): readonly (typeof SCAN_VIEWS)[number][] {
  return SCAN_VIEWS.filter((v) => v.group === "main" || (legacy && v.group === "legacy"));
}

/** A view that is only shown while Settings keeps the old ones. */
export function isLegacyView(v: ScanView): boolean {
  return SCAN_VIEWS.find((x) => x.key === v)?.group === "legacy";
}

/** The view to open: a remembered old view opens Today once the old ones are off. */
export function shownView(v: ScanView, legacy: boolean): ScanView {
  return !legacy && isLegacyView(v) ? "today" : v;
}

export function isTab(v: unknown): v is Tab {
  return typeof v === "string" && (TAB_KEYS as readonly string[]).includes(v);
}

export function isDesk(v: unknown): v is Desk {
  return v === "futures" || v === "stocks";
}

/** Where a link lands: a tab, and the view inside it when the link means one. */
export interface Landing {
  tab: Tab;
  /** The Scanner's view. */
  scan?: ScanView;
  /** The Futures section's view; only the brief is ever named by a link. */
  fut?: "brief";
}

/**
 * The keys the bar used to have, and where each opens now. A remembered tab
 * or a shared link from before still lands somewhere sensible: the report on
 * the Futures section's Brief, the plan on the Scanner's Game plan, the Market
 * tab on Macro.
 */
const LEGACY: Record<string, Landing> = {
  market: { tab: "terminal" },
  // Structure split on 2026-11-10: its link opens the futures half's new home.
  structure: { tab: "futures" },
  report: { tab: "futures", fut: "brief" },
  plan: { tab: "scanner", scan: "plan" },
};

/**
 * A `?tab=` value, current or old, as where it opens — null for one that is
 * neither. `desk` is the old `?desk=` beside `?tab=analysis`: the stocks half was
 * the plan, and with no desk named Analysis opened on the brief.
 */
export function resolveTab(raw: unknown, desk?: unknown): Landing | null {
  if (typeof raw !== "string") return null;
  if (isTab(raw)) return { tab: raw };
  if (raw === "analysis") return desk === "stocks" ? LEGACY.plan : LEGACY.report;
  return LEGACY[raw] ?? null;
}

export function tabLabel(t: Tab): string {
  return TABS.find((x) => x.key === t)?.label ?? t;
}

/** The browser tab's title — "HERMES · Macro", "HERMES · Stocks". */
export function pageTitle(t: Tab): string {
  return `HERMES · ${tabLabel(t)}`;
}

/** The side of the terminal a page belongs to, for a page that belongs to one. */
export function deskOf(t: Tab): Desk | null {
  if (t === "futures") return "futures";
  return t === "dashboard" || t === "scanner" || t === "sectors" ? "stocks" : null;
}

/**
 * The key the collector's Ask context knows for a page (server ask.py), which
 * keeps the names it had: the futures digest is "structure", the two written
 * notes are "report" (the brief, Futures → Brief) and "plan" (the game plan, the
 * Scanner's Game plan view); everything else is its own key. ("tape", the stocks digest,
 * was the Scanner's Index view; no page asks as it since that view went.)
 */
export function askTab(t: Tab, view?: ScanView, fut?: string): string {
  if (t === "futures") return fut === "brief" ? "report" : "structure";
  if (t === "scanner" && view === "plan") return "plan";
  return t;
}
