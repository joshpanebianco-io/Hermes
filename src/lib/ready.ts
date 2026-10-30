import type { Terminal as TerminalData } from "@/types/terminal";
import type { MarketFeed } from "@/lib/useMarket";

/**
 * Has a board got everything it reads, at least once?
 *
 * ONE LOADER, NOT ONE PER PANEL (owner, 2026-10-30). The collector builds its
 * snapshot source by source after a start, and for a minute or two the board
 * was a grid of helms, each panel waiting on its own feed. Now a board waits
 * as one, and the question it asks is the status rail's: a source that has
 * reported once — well or badly — has a `status` entry, and one that has not
 * yet run has none. The market context is the same question asked of its
 * own feed: answered, or failed, but not still pending.
 *
 * AN OFFLINE COLLECTOR IS READY. The banner says what is wrong and every
 * panel says it is empty; a helm that spun until the collector came back
 * would hide that, and the page would look hung rather than honest.
 */
export function boardReady(data: TerminalData, sources: readonly string[], market: MarketFeed): boolean {
  if (data.offline) return true;
  const st = data.status ?? {};
  if (!sources.every((k) => st[k] !== undefined)) return false;
  return market.ctx !== null || market.failed !== null;
}
