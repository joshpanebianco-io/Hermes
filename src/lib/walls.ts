/**
 * A gamma wall's rank as chevrons, not a trailing digit (owner, 2026-11-14: "on the gex
 * levels in futures, can we make the put and call walls have the arrows instead of
 * numbers?"). GEXYGEN's convention, and the Gamma panel's here: three chevrons is the
 * heaviest wall on its side, one the third; up for calls, down for puts. The collector
 * names them "Call wall", "Call wall 2", "Call wall 3" (server sources/gex.py), which put
 * the weakest claim in the most prominent place and left the heaviest with no mark at all.
 *
 * THE TRIANGLES ARE DRAWN, NOT TYPED (owner, the same morning: "a bit smaller", "slightly
 * bigger", "i dont like the dip shape", then "do option 3"). A font offers a solid flat
 * triangle at 11px (▲) or 6px (▴) and nothing between that is not a dipped arrowhead (⮝),
 * so the chart draws the wall's label itself (ScanChart's Overlays) with triangles of its
 * own size (the Futures Overview, which set them in a smaller type, went on 2026-11-14).
 * This says what to draw.
 */

const WALL = /^(Call|Put) wall(?: ([123]))?$/i;

export interface WallRank {
  /** "Call wall" or "Put wall". */
  word: string;
  /** Triangles: 3 for the heaviest wall on its side, 1 for the third. */
  n: number;
  /** A call wall's point up, a put wall's down. */
  up: boolean;
}

/** "Call wall 2" → { word: "Call wall", n: 2, up: true }; null for any other level. */
export function wallRank(label: string): WallRank | null {
  const m = WALL.exec(label.trim());
  if (!m) return null;
  const call = m[1].toLowerCase() === "call";
  return { word: call ? "Call wall" : "Put wall", n: 4 - Number(m[2] ?? 1), up: call };
}
