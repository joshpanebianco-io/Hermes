/**
 * The market report's key levels on one line (panels/Brief `KeyLevels`): where each
 * level sits between the lowest and the highest, and which row under the line its
 * label takes.
 *
 * WHY A LAYOUT AND NOT JUST A PERCENTAGE. The levels are the prior session's high and
 * low, its value area and point of control, and the handover range: they bunch. A
 * value low 20 points under the last price printed its label on top of the next one,
 * so each label is given the first row where it clears the one before it, and two
 * levels at the same printed price share one mark ("Fri high · Overnight high").
 *
 * The last price is not one of the rows: it is the dot on the line with its figure
 * above it, so it is never crowded by the levels it is being read against.
 *
 * Pure: widths are estimated from the text's length, so the same marks at the same
 * width always lay out the same way and it can be tested without a browser.
 */

export interface LevelMark {
  price: number;
  label: string;
  kind: "range" | "poc" | "value" | "last";
}

export interface RulerMark {
  price: number;
  /** The names at this price, in the order they came. */
  labels: string[];
  kind: "range" | "poc" | "value";
  /** The tick's place along the line, in px from its left end. */
  x: number;
  /** The label's box: its left edge and width in px, and the row it sits on (0 is nearest the line). */
  left: number;
  width: number;
  lane: number;
}

export interface Ruler {
  marks: RulerMark[];
  /** How many rows of labels there are under the line. */
  lanes: number;
  last: { price: number; x: number } | null;
  /** The value area as a stretch of the line, when both of its ends are among the marks. */
  value: [number, number] | null;
}

/** Room at each end of the line, so an end tick is not flush with the card's edge. */
export const RULER_PAD = 8;
/** An 11px figure or word, per character, erring wide. */
const CHAR = 6.6;
const LABEL_PAD = 8;
const GAP = 10;
export const MAX_LANES = 3;

const RANK = { poc: 2, value: 1, range: 0 } as const;

export function priceText(price: number, dp: number): string {
  return price.toLocaleString("en-US", { minimumFractionDigits: dp, maximumFractionDigits: dp });
}

export function layoutRuler(marks: readonly LevelMark[], width: number, dp: number): Ruler | null {
  const all = marks.filter((m) => Number.isFinite(m.price));
  if (all.length < 2 || !(width > 4 * RULER_PAD)) return null;
  const lo = Math.min(...all.map((m) => m.price));
  const hi = Math.max(...all.map((m) => m.price));
  if (!(hi > lo)) return null;
  const at = (p: number) => RULER_PAD + ((p - lo) / (hi - lo)) * (width - 2 * RULER_PAD);

  const merged = new Map<string, RulerMark>();
  for (const m of all) {
    if (m.kind === "last") continue;
    const key = priceText(m.price, dp);
    const got = merged.get(key);
    if (got) {
      if (!got.labels.includes(m.label)) got.labels.push(m.label);
      if (RANK[m.kind] > RANK[got.kind]) got.kind = m.kind;
    } else {
      merged.set(key, { price: m.price, labels: [m.label], kind: m.kind, x: at(m.price), left: 0, width: 0, lane: 0 });
    }
  }

  const out = [...merged.values()].sort((a, b) => a.x - b.x);
  const ends: number[] = [];
  for (const m of out) {
    const chars = Math.max(priceText(m.price, dp).length, m.labels.join(" · ").length);
    m.width = Math.min(width, chars * CHAR + LABEL_PAD);
    m.left = Math.max(0, Math.min(width - m.width, m.x - m.width / 2));
    // The first row where it clears what is already there; with every row taken, the
    // one whose last label ends soonest, so what overlap there is, is the least.
    let lane = ends.findIndex((end) => m.left >= end + GAP);
    if (lane === -1) {
      if (ends.length < MAX_LANES) lane = ends.length;
      else lane = ends.indexOf(Math.min(...ends));
    }
    m.lane = lane;
    ends[lane] = m.left + m.width;
  }

  const last = all.find((m) => m.kind === "last");
  const area = all.filter((m) => m.kind === "value").map((m) => m.price);
  return {
    marks: out,
    lanes: Math.max(1, ends.length),
    last: last ? { price: last.price, x: at(last.price) } : null,
    value: area.length === 2 ? [at(Math.min(...area)), at(Math.max(...area))] : null,
  };
}

/** How far a level is from the last price, signed, at the book's decimals: "+364", "−20". */
export function fromLast(price: number, last: number | null | undefined, dp: number): string | null {
  if (last == null || !Number.isFinite(last)) return null;
  const d = price - last;
  const body = priceText(Math.abs(d), dp);
  return d > 0 ? `+${body}` : d < 0 ? `−${body}` : body;
}
