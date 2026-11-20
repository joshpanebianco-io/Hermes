import { FUT_VIEW_KEYS, type FutView } from "@/lib/futures";
import { SCAN_VIEW_KEYS, TAB_KEYS, type ScanView, type Tab } from "@/lib/tabs";

/**
 * Where the reader was: the page, the Stocks view and the Futures view, as a cookie.
 *
 * WHY (the loading sweep, 2026-11-20, on the owner's "tidy up any cache loading bugs").
 * The three are remembered in storage (usePersisted), which the server cannot read, so
 * a reload drew the default first and swapped a second later: the Futures desk's NQ book
 * (its chart starting to load) before the Market Report view it was left on, the
 * Scanner's list before Charts, and a bare address drew Macro before the Dashboard. The
 * server reads this cookie and draws the right one in the first frame, as it does the
 * theme and the interface. Storage stays the copy the pages read; this mirrors it.
 */
export const PLACE_COOKIE = "nt_place";

export interface Place {
  tab: Tab | null;
  scan: ScanView | null;
  fut: FutView | null;
}

/** "futures.today.report": each part checked against this build's own lists. */
export function parsePlace(raw: string | undefined): Place {
  const [t, s, f] = (raw ?? "").split(".");
  return {
    tab: (TAB_KEYS as readonly string[]).includes(t) ? (t as Tab) : null,
    scan: (SCAN_VIEW_KEYS as readonly string[]).includes(s) ? (s as ScanView) : null,
    fut: (FUT_VIEW_KEYS as readonly string[]).includes(f) ? (f as FutView) : null,
  };
}

export function placeCookie(tab: Tab, scan: ScanView, fut: FutView): string {
  return `${PLACE_COOKIE}=${tab}.${scan}.${fut}; path=/; max-age=31536000; samesite=lax`;
}
