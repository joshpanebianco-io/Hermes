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
 *   Macro      what is happening and what is scheduled — the wire, the
 *              calendar, prints and the Fed path, the diaries, earnings,
 *              rates, rotation, the movers, the macro board
 *   Structure  where price is and how it is positioned — the driver board,
 *              the book, session ranges, the volume profile, the levels, dealer
 *              gamma in futures and in ETF prices, the vol curve, the tape
 *              count; behind the desk switch, each desk's half the whole page
 *   Scanner    the stocks desk's break-and-retest scanner
 *   Analysis   the written read — and the one place the desk is a question:
 *              the futures brief or the stocks game plan, behind a switch
 *              on that tab, remembered
 *   Hermes AI  the assistant with the whole terminal in front of it
 *   Settings
 *
 * The desk therefore survives as one remembered choice worn by the two tabs
 * whose reads differ by desk — Analysis and Structure (the owner asked for
 * the switch on Structure after a day with both halves side by side) — and
 * as what a question to Hermes is labelled with. The keys are what `?tab=` and storage
 * hold; the old keys still resolve (`resolveTab`), so a link to the report, the
 * plan or the Market tab opens the right place.
 */

export type Desk = "futures" | "stocks";

/** The two halves of Analysis — the futures brief, the stocks game plan. */
export const DESKS: readonly { key: Desk; label: string; short: string }[] = [
  { key: "futures", label: "Futures", short: "Futures" },
  { key: "stocks", label: "Stocks & Options", short: "Stocks" },
];

export const TABS = [
  { key: "terminal", label: "Macro" },
  { key: "structure", label: "Structure" },
  { key: "scanner", label: "Scanner" },
  { key: "analysis", label: "Analysis" },
  { key: "hermes", label: "Hermes AI" },
  { key: "settings", label: "Settings" },
] as const;

export type Tab = (typeof TABS)[number]["key"];

export const TAB_KEYS: readonly Tab[] = TABS.map((t) => t.key);

/** The tabs that wear the desk switch; `D` flips it in place on these. */
export const DESK_TABS: ReadonlySet<Tab> = new Set<Tab>(["structure", "analysis"]);

export function isTab(v: unknown): v is Tab {
  return typeof v === "string" && (TAB_KEYS as readonly string[]).includes(v);
}

export function isDesk(v: unknown): v is Desk {
  return v === "futures" || v === "stocks";
}

/**
 * The keys the bar used to have, and where each opens now. A remembered tab
 * or a shared link from before the one bar still lands somewhere sensible —
 * the report and the plan on their half of Analysis, the Market tab on Macro.
 */
const LEGACY: Record<string, { tab: Tab; desk?: Desk }> = {
  market: { tab: "terminal" },
  report: { tab: "analysis", desk: "futures" },
  plan: { tab: "analysis", desk: "stocks" },
};

/** A `?tab=` value, current or old, as the tab it opens — null for one that is neither. */
export function resolveTab(raw: unknown): { tab: Tab; desk?: Desk } | null {
  if (typeof raw !== "string") return null;
  if (isTab(raw)) return { tab: raw };
  return LEGACY[raw] ?? null;
}

export function tabLabel(t: Tab): string {
  return TABS.find((x) => x.key === t)?.label ?? t;
}

export function deskLabel(d: Desk): string {
  return DESKS.find((x) => x.key === d)?.label ?? d;
}

/** The browser tab's title — "HERMES · Macro", "HERMES · Structure · Futures". */
export function pageTitle(t: Tab, desk: Desk): string {
  return DESK_TABS.has(t) ? `HERMES · ${tabLabel(t)} · ${deskLabel(desk)}` : `HERMES · ${tabLabel(t)}`;
}

/**
 * The key the collector's Ask context knows for a tab (server ask.py): the
 * two tabs with the desk switch are their half — the brief and the plan are
 * different notes and different digests, and Structure's stocks half reads
 * the stocks digest ("tape"); everything else is its own key.
 */
export function askTab(t: Tab, desk: Desk): string {
  if (t === "analysis") return desk === "futures" ? "report" : "plan";
  if (t === "structure") return desk === "futures" ? "structure" : "tape";
  return t;
}
