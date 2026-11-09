import type { CSSProperties } from "react";

/**
 * How strongly a card on the heat map is tinted, and which way.
 *
 * ON A SQUARE ROOT. Theme funds move several times what a sector does: scaled in a
 * straight line, a day with Space up 9% leaves Technology's +1.45% looking flat, when
 * that is the biggest move among the eleven. The root keeps the middle of the range
 * visible without changing the order of anything.
 */

/** The strongest a tint gets, as a percentage of the side's hue. */
export const MAX_TINT = 34;
/** Under this much of the board's biggest move a card stays clear. */
const QUIET = 0.02;

/** 0 to MAX_TINT for a move, against the biggest on the board. */
export function tintPct(v: number | null | undefined, max: number): number {
  if (v == null || !Number.isFinite(v) || max <= 0) return 0;
  const share = Math.min(1, Math.abs(v) / max);
  return share < QUIET ? 0 : Math.round(Math.sqrt(share) * MAX_TINT);
}

/** The card's background: green up, pink down, in the terminal's own side hues. */
export function heatStyle(v: number | null | undefined, max: number): CSSProperties | undefined {
  const p = tintPct(v, max);
  if (!p) return undefined;
  return { background: `color-mix(in oklab, var(${(v as number) >= 0 ? "--call" : "--put"}) ${p}%, transparent)` };
}

/** The biggest move on the board, never under a point, so a dead day is not painted loud. */
export function heatMax(values: ReadonlyArray<number | null | undefined>): number {
  return Math.max(1, ...values.map((v) => (v == null || !Number.isFinite(v) ? 0 : Math.abs(v))));
}
