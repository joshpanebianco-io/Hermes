/**
 * The terminal's tabs, in bar order — the one list.
 *
 * It used to be written out six times (the page's URL parse twice, the
 * Terminal's type and its storage guard, the header's type and its labels), so
 * adding the Scanner took four edits and any one of them forgotten would have
 * been a tab the URL could not open or storage would silently refuse.
 */

export const TABS = [
  { key: "terminal", label: "Terminal" },
  { key: "scanner", label: "Scanner" },
  { key: "report", label: "Report" },
  { key: "settings", label: "Settings" },
] as const;

export type Tab = (typeof TABS)[number]["key"];

export const TAB_KEYS: readonly Tab[] = TABS.map((t) => t.key);

export function isTab(v: unknown): v is Tab {
  return typeof v === "string" && (TAB_KEYS as readonly string[]).includes(v);
}
