import type { Quote } from "@/types/terminal";

/**
 * Which quotes a row of price tiles draws, and how a print's age reads. Pure, so it
 * can be tested without a browser; the drawing is components/market/QuoteTiles.tsx.
 *
 * THE HEADER STRIP IS GONE (owner, 2026-11-10: "lets remove the" eleven "from the top
 * and move them in there appropriate places else where", then "swap outright"). Each
 * figure now sits on the page that uses it: the books on Futures, the macro on Macro's
 * board, the index ETFs and VIX in the Stocks tab's masthead, and one row on the
 * Dashboard. Those rows keep the strip's rules: trading order, grouped, a delayed print
 * says how late it is, a shut market's figure dims.
 */

/** The Stocks tab's masthead: the index ETFs a stock is read against, and the VIX band. */
export const SCAN_GROUPS: readonly (readonly string[])[] = [["SPY", "QQQ", "IWM"], ["VIX"]];

/**
 * The Dashboard's row: the same four, SPY, QQQ, IWM and VIX.
 *
 * WHY (owner, 2026-11-12: "can we get the NQ specific stuff out of dashboard since we
 * have a specific futures tab", then "on the card below the nav one can we just have
 * spy, qqq, iwm, VIX"). It was all eleven of the old header's figures, led by NQ, ES
 * and gold. The Dashboard is the stocks session on one page, so it carries what a stock
 * is read against and nothing else: the futures are on Futures, and the 10-year, the
 * dollar, crude, bitcoin and VVIX are on Macro's board. Its own name, so the two rows
 * can part again without a search for who else reads the list.
 */
export const DASH_GROUPS: readonly (readonly string[])[] = SCAN_GROUPS;

/**
 * The Sidebar interface's header, where the prices stand beside the page's name on
 * every page (shell/SideHeader): the same four as the Stocks tab's masthead, and on a
 * Futures page the three scored books in their place, because each desk shows its own
 * (owner, 2026-11-11 and 2026-11-12). VIX is on both: both desks size off it.
 */
export const SIDE_GROUPS: readonly (readonly string[])[] = SCAN_GROUPS;
export const SIDE_FUT_GROUPS: readonly (readonly string[])[] = [["NQ", "ES", "GC"], ["VIX"]];

/**
 * The groups' quotes, in the groups' order whatever order the feed sends. A key the
 * feed does not carry yet is left out, and so is a group left empty by that.
 */
export function quoteGroups(quotes: readonly Quote[], groups: readonly (readonly string[])[]): Quote[][] {
  const out: Quote[][] = [];
  for (const group of groups) {
    const got = group.map((k) => quotes.find((q) => q.key === k)).filter((q): q is Quote => q !== undefined);
    if (got.length > 0) out.push(got);
  }
  return out;
}

/**
 * How late a delayed print is, "10m". Null when it is not delayed, the lag is
 * unknown, or it rounds to less than `atLeast` minutes.
 */
export function lagText(q: Pick<Quote, "feed" | "lag_min">, atLeast = 0): string | null {
  if (q.feed !== "delayed" || q.lag_min == null) return null;
  const min = Math.round(q.lag_min);
  return min >= atLeast ? `${min}m` : null;
}

/** A figure's ink: dimmed when its market is shut or has not printed in half an hour. */
export function quoteInk(q: Pick<Quote, "feed">): string {
  return q.feed === "closed" || q.feed === "stale" ? "text-ink-3" : "text-ink";
}
