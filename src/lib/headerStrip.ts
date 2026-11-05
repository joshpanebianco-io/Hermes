import type { Quote } from "@/types/terminal";

/**
 * What the header's strip draws, and how much of it fits. Pure, so it can be
 * tested without a browser; the drawing is components/shell/HeaderStrip.tsx.
 *
 * IN TRADING ORDER, GROUPED: the three books, the two index ETFs, the vol pair,
 * then the macro that moves them. A window too narrow for all of it loses the
 * right-hand end first, so NQ is the last thing to go.
 */
export const STRIP_GROUPS: readonly (readonly string[])[] = [
  ["NQ", "ES", "GC"],
  ["SPY", "QQQ"],
  ["VIX", "VVIX"],
  ["US10Y", "DXY", "WTI", "BTC"],
];

export interface StripTile {
  quote: Quote;
  /** Draws the group's divider. Never on the first tile, which has nothing to divide from. */
  startsGroup: boolean;
}

/** The strip's tiles. A key the feed does not carry yet is simply not drawn. */
export function stripTiles(quotes: readonly Quote[]): StripTile[] {
  const out: StripTile[] = [];
  for (const group of STRIP_GROUPS) {
    let first = true;
    for (const key of group) {
      const quote = quotes.find((q) => q.key === key);
      if (!quote) continue;
      out.push({ quote, startsGroup: first && out.length > 0 });
      first = false;
    }
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

/**
 * How many tiles fit, from the left. All of them if they fit with no count beside
 * them; otherwise room is kept for the count, and it is as many as that leaves.
 *
 * `room` IS THE STRIP'S WHOLE WIDTH, never the space left beside the count. That
 * space shrinks when the count appears, so measuring against it had two stable
 * answers: a strip that overflowed once, say before the web font landed, kept its
 * count for good with room to spare, and 1920 sat at nine of eleven (2026-11-06).
 */
export function fitCount(widths: readonly number[], gap: number, room: number, countWidth: number): number {
  const total = widths.reduce((sum, w) => sum + w, 0) + gap * Math.max(0, widths.length - 1);
  if (total <= room) return widths.length;
  const left = room - countWidth - gap;
  let used = 0;
  let fit = 0;
  for (const w of widths) {
    const next = used + (fit > 0 ? gap : 0) + w;
    if (next > left) break;
    used = next;
    fit += 1;
  }
  return fit;
}
