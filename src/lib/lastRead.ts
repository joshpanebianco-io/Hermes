/**
 * The last read of each page's data, held for as long as the tab is open.
 *
 * WHY (owner, 2026-11-20: "do a sweep of the app and tidy up any cache loading bugs ...
 * so that the app looks a bit more polished when loading stuff"). A page is unmounted
 * when its tab is left (Terminal renders one page at a time), so its data went with it:
 * every return to the Dashboard, Sectors or Stocks showed the loader for a second or
 * three, and every chart and slide-out started blank, for figures the page had on screen
 * a moment before. Now a page opens on what it last showed and its first poll replaces
 * it, which is what it would have shown had it stayed mounted. The cards' age chips and
 * the pages' own "read Xm ago" lines say how old that is.
 *
 * MEMORY ONLY, NEVER STORAGE. Nothing derived from market data is written to the browser
 * (lib/usePersisted): a reload starts empty. And the browser's only: the server renders
 * with nothing here (a module on the server is shared by every request), and the first
 * client render after a load finds it empty too, so hydration never sees a difference.
 */

/** Charts and names are many: the oldest reads go past this many. */
const MAX = 80;
const READS = new Map<string, unknown>();

/** The last read under `key`, or null: on the server, or before the first read lands. */
export function lastRead<T>(key: string): T | null {
  if (typeof window === "undefined") return null;
  return (READS.get(key) as T | undefined) ?? null;
}

/** Keep `value` as the last read under `key`, and hand it back. */
export function keepRead<T>(key: string, value: T): T {
  if (typeof window === "undefined") return value;
  READS.delete(key);
  READS.set(key, value);
  if (READS.size > MAX) {
    const oldest = READS.keys().next().value;
    if (oldest !== undefined) READS.delete(oldest);
  }
  return value;
}
