/**
 * The terminal's desks and tabs, in bar order — the one list.
 *
 * It used to be written out six times (the page's URL parse twice, the
 * Terminal's type and its storage guard, the header's type and its labels), so
 * adding the Scanner took four edits and any one of them forgotten would have
 * been a tab the URL could not open or storage would silently refuse.
 *
 * TWO DESKS IN ONE APP (owner instruction, 2026-10-13: "do everything you
 * recommend" — the futures side and the stocks-and-ETFs-for-options side
 * separated). They trade different things on different clocks: NQ / ES / GC
 * across Asia, London and New York, read against macro and dealer gamma; and
 * single names and index ETFs in the New York session only, read against
 * their own levels, relative strength and the options chain. Each desk is a
 * set of tabs; Settings belongs to both. The desk is DERIVED from the tab, so
 * `?tab=` stays the whole URL and a link still opens exactly one place.
 */

export type Desk = "futures" | "stocks";

export const DESKS: readonly { key: Desk; label: string; short: string }[] = [
  { key: "futures", label: "Futures", short: "Futures" },
  { key: "stocks", label: "Stocks & Options", short: "Stocks" },
];

// ONE VOCABULARY ACROSS BOTH DESKS (owner instruction, 2026-10-14): each desk
// opens on its Macro tab — the tape and what is moving it — and closes on its
// Analysis tab, the written read (the futures brief; the stocks game plan).
// Only the labels changed: the keys are what `?tab=` and storage hold, so old
// links and remembered tabs still open the same place.
export const TABS = [
  { key: "terminal", label: "Macro", desk: "futures" },
  { key: "report", label: "Analysis", desk: "futures" },
  { key: "market", label: "Macro", desk: "stocks" },
  { key: "scanner", label: "Scanner", desk: "stocks" },
  { key: "plan", label: "Analysis", desk: "stocks" },
  { key: "settings", label: "Settings", desk: "both" },
] as const;

export type Tab = (typeof TABS)[number]["key"];

export const TAB_KEYS: readonly Tab[] = TABS.map((t) => t.key);

/** Where each desk opens when nothing has been remembered for it. */
export const DESK_HOME: Record<Desk, Tab> = { futures: "terminal", stocks: "scanner" };

export function isTab(v: unknown): v is Tab {
  return typeof v === "string" && (TAB_KEYS as readonly string[]).includes(v);
}

export function isDesk(v: unknown): v is Desk {
  return v === "futures" || v === "stocks";
}

/** The desk a tab belongs to; null for Settings, which belongs to both. */
export function deskOf(t: Tab): Desk | null {
  const d = TABS.find((x) => x.key === t)?.desk;
  return d === "futures" || d === "stocks" ? d : null;
}

/** A desk's tabs in bar order, Settings last — what the header shows and the number keys reach. */
export function tabsFor(desk: Desk): (typeof TABS)[number][] {
  return TABS.filter((t) => t.desk === desk || t.desk === "both");
}

export function tabLabel(t: Tab): string {
  return TABS.find((x) => x.key === t)?.label ?? t;
}

export function deskLabel(d: Desk): string {
  return DESKS.find((x) => x.key === d)?.label ?? d;
}

/** The browser tab's title for a tab — "HERMESX · Stocks & Options · Scanner". */
export function pageTitle(t: Tab, desk: Desk): string {
  return t === "settings" ? "HERMESX · Settings" : `HERMESX · ${deskLabel(desk)} · ${tabLabel(t)}`;
}
