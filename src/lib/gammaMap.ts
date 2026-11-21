/**
 * THE GAMMA MAP'S LAYOUT (the Market Report's Market Context, 2026-11-21): where the price,
 * the flip, the walls and the expected move sit along one line, and which row each wall's
 * label takes so two that are close do not print over each other.
 *
 * The line runs from the lowest of them to the highest with a little room at each end, and
 * more beyond the flip when the flip is the end: the far side of the flip is the other
 * regime's zone, and a zone a few pixels wide would not read as one. Pure.
 */

export type GammaKind = "put" | "call" | "flip";

export interface GammaLevels {
  last: number;
  flip: number | null;
  puts: readonly number[];
  calls: readonly number[];
  em: readonly [number, number] | null;
}

export interface GammaMark {
  kind: GammaKind;
  price: number;
  /** Pixels from the line's left end. */
  x: number;
  /** The row its label takes under the line: 0 the nearest. */
  lane: number;
}

export interface GammaLayout {
  /** The price's place, in pixels. */
  last: number;
  /** The flip's place, or null when the feed has none. */
  flip: number | null;
  /** The expected move's two ends, a future's own. */
  em: [number, number] | null;
  /** The walls and the flip, left to right. */
  marks: GammaMark[];
  /** How many rows the labels take. */
  lanes: number;
}

/** Room at an end of the line, as a share of the span between its lowest and highest level. */
export const GAMMA_PAD = 0.07;
/** Room beyond the flip when the flip is the end: the other regime's zone. */
export const GAMMA_ZONE = 0.2;
/**
 * Half a label's width and the least gap between two in one row, in pixels: the wider of
 * a label's two lines is its price ("25,955" at 11.5px is some 46px), with room to spare.
 */
export const GAMMA_LABEL_HALF = 30;
export const GAMMA_LABEL_GAP = 6;

export function layoutGamma(g: GammaLevels, width: number): GammaLayout | null {
  if (!(width > 0) || !Number.isFinite(g.last)) return null;
  const levels: { kind: GammaKind; price: number }[] = [
    ...g.puts.map((price) => ({ kind: "put" as const, price })),
    ...g.calls.map((price) => ({ kind: "call" as const, price })),
    ...(g.flip != null ? [{ kind: "flip" as const, price: g.flip }] : []),
  ].filter((m) => Number.isFinite(m.price));
  const all = [g.last, ...levels.map((m) => m.price), ...(g.em ?? [])];
  const lo = Math.min(...all);
  const hi = Math.max(...all);
  // One price and nothing else to set it against: a line a hundredth of it wide.
  const span = hi - lo || Math.abs(g.last) * 0.01 || 1;
  const from = lo - span * (g.flip != null && g.flip === lo ? GAMMA_ZONE : GAMMA_PAD);
  const to = hi + span * (g.flip != null && g.flip === hi ? GAMMA_ZONE : GAMMA_PAD);
  const at = (p: number) => ((p - from) / (to - from)) * width;

  const marks: GammaMark[] = levels.map((m) => ({ ...m, x: at(m.price), lane: 0 })).sort((a, b) => a.x - b.x);
  // Each label takes the nearest row whose last label ends clear of it.
  const ends: number[] = [];
  for (const m of marks) {
    let lane = ends.findIndex((right) => m.x - GAMMA_LABEL_HALF > right + GAMMA_LABEL_GAP);
    if (lane < 0) {
      lane = ends.length;
      ends.push(0);
    }
    ends[lane] = m.x + GAMMA_LABEL_HALF;
    m.lane = lane;
  }
  return {
    last: at(g.last),
    flip: g.flip != null ? at(g.flip) : null,
    em: g.em ? [at(g.em[0]), at(g.em[1])] : null,
    marks,
    lanes: ends.length,
  };
}

/** A level as the map prints it: to the instrument's decimals, and whole when it is whole. */
export function gammaPrice(v: number, dp: number): string {
  const whole = Math.abs(v - Math.round(v)) < 1e-9;
  return v.toLocaleString("en-US", { minimumFractionDigits: whole ? 0 : dp, maximumFractionDigits: whole ? 0 : dp });
}
