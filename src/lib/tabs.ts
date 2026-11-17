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
 *   Futures    every futures book traded, NQ, ES, GC, silver and crude: a view
 *              per contract (its chart with the levels, the news that reaches it,
 *              session ranges, the profile, gamma; no overview since 2026-11-14) and the
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
 * AND THE TWO NOTES HAVE ONE PAGE AGAIN: MARKET REPORT (owner, 2026-11-15: "i want to
 * remove the market section from stocks and brief section from futures and consolidate it
 * all into one area", then "instead of Analysis lets call it Market Report and have it
 * after the Futures on the right of it"). What sent Analysis away no longer holds: the
 * stocks note writes itself every morning now, and the reader picks what a report is
 * about (Indexes, Gold, Silver, Oil) and which session it is for (Asia, London, New York)
 * from two rows of pills, where the old tab had a desk switch. The stocks overview is
 * not on it: it was, under Indexes for New York, for an afternoon, until the owner had
 * it taken off ("that info is easily seen in the stocks seciton"); it is read on the
 * Dashboard's card. So the Stocks strip has no Market view and Futures no Brief view,
 * and the bar is eight pages.
 *
 * AND THEN A VIEW ON EACH DESK (owner, 2026-11-16). That morning the page left the bar
 * ("remove it form the nav bar, and then just utilise the pop up cards when you click on
 * the bias"), and the Bias card's board became a slide-out. That afternoon the report
 * came back, as a view of each desk rather than a page: "in both futures and stocks lets
 * add Market Report tab with the generate funcitonality next to cl and then next to
 * charts". Futures → Market Report writes one book (NQ, ES, GC, SIL or CL) for Asia,
 * London or New York; Stocks → Market Report writes SPY, QQQ and IWM together for New
 * York (lib/reportDesk). So "report" is no page key any more and the bar is seven pages;
 * `?tab=report`, `plan` and `analysis` open the Futures view, the Stocks view for `plan`
 * (`LEGACY`).
 *
 * The desk therefore survives only as what a question to Hermes is labelled with:
 * the side of the terminal the reader was last on (Terminal.tsx). The keys are what
 * `?tab=` and storage hold; the old keys still resolve (`resolveTab`), so a link to
 * the report, the plan, Analysis or the Market tab opens the right place.
 */

// Type-only, so the node tests that run this file never load it.
import type { FutView } from "@/lib/futures";

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
  // No Market Report page since 2026-11-16: it is a view of Futures and of Stocks.
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
 * open's triggers, the session's setups. The strip is Scanner and Charts (the Multicharts
 * view); Market, the written overview, was a third until 2026-11-15, when it went to the
 * Market Report page. The four old
 * views stay reachable for a week behind Settings → Interface (`group: "legacy"`,
 * lib/legacyViews.ts), then go. A browser that remembers one of them opens Today.
 */
export const SCAN_VIEWS = [
  // Called Today until 2026-11-13 ("i think we hsould rename 'today' to Scanner"); the key stays.
  { key: "today", label: "Scanner", group: "main", title: "The best stocks for the hour it is: the evening's movers, then what is in play into the open, then the session's setups from the bell" },
  { key: "multi", label: "Charts", group: "main", title: "Six live charts of the list's best names, three across and two down" },
  // The written report, after Charts since 2026-11-16 (owner: "in both futures and stocks
  // lets add Market Report tab with the generate funcitonality next to cl and then next to
  // charts"): SPY, QQQ and IWM together, for New York (lib/reportDesk). It is not the
  // 09:00 market overview, which still writes itself for the Dashboard's card.
  { key: "report", label: "Market Report", group: "main", title: "The written report: SPY, QQQ and IWM together, for New York" },
  // No Record view since 2026-11-13 ("can we get rid of the record section completely"):
  // the signal log is still kept on the server, read by the score card and Hermes.
  // No Market view since 2026-11-15: the written overview has no page (the Dashboard's
  // Market overview card reads it). A link to "plan" opens the Market Report view.
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
  /** The Futures tab's view. */
  fut?: FutView;
}

/**
 * The keys the bar used to have, and where each opens now. A remembered tab
 * or a shared link from before still lands somewhere sensible: the report and
 * Analysis on the Futures tab's Market Report view, the plan (the stocks note) on the
 * Stocks tab's, the Market tab on Macro.
 */
const LEGACY: Record<string, Landing> = {
  market: { tab: "terminal" },
  // Structure split on 2026-11-10: its link opens the futures half's new home.
  structure: { tab: "futures" },
  report: { tab: "futures", fut: "report" },
  analysis: { tab: "futures", fut: "report" },
  plan: { tab: "scanner", scan: "report" },
};

/**
 * A `?tab=` value, current or old, as where it opens — null for one that is
 * neither.
 */
export function resolveTab(raw: unknown): Landing | null {
  if (typeof raw !== "string") return null;
  if (isTab(raw)) return { tab: raw };
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
 * keeps the names it had: the futures digest is "structure", and either desk's Market
 * Report view is "report", the written brief's key, so Hermes is handed the latest
 * report there; everything else is its own key too. ("plan", the stocks overview, and
 * "tape", the stocks digest, were views no page asks as any more: Hermes reaches both
 * through its tools.)
 */
export function askTab(t: Tab, scan?: ScanView, fut?: FutView): string {
  if ((t === "futures" && fut === "report") || (t === "scanner" && scan === "report")) return "report";
  return t === "futures" ? "structure" : t;
}
