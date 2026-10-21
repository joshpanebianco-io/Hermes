/**
 * The VIX bands — what a level means for the desk, as the scanner reads it.
 *
 * THE THRESHOLDS ARE THE SERVER'S (scanscore.py VIX_GRIND / VIX_NORMAL /
 * VIX_STRESSED, and volterm.py FLAT_BAND for the curve), mirrored here so the
 * band word on the card and the table behind it can never disagree: the card
 * shows the band the scanner scored every row in, and this is the table of
 * the same four. Change one side and change the other — scanscore.py says so
 * beside its constants.
 *
 * THE IMPLIED-MOVE COLUMN IS COMPUTED, NOT TYPED. VIX is an annualised
 * one-sigma; divided by √252 it is the one-day move the options market prices
 * for SPY — the same arithmetic as the "Implied SPY day" card beside it. So
 * each band's move range is written from its threshold and cannot drift.
 *
 * Pure. No React, no fetch.
 */

export const VIX_GRIND = 13;
export const VIX_NORMAL = 20;
export const VIX_STRESSED = 28;
/** volterm.FLAT_BAND — a ratio within this of 1.00 is "flat", not a shape. */
export const CURVE_FLAT_BAND = 0.02;

const SQRT252 = Math.sqrt(252);

export type VixBand = "grind" | "normal" | "elevated" | "stressed";
export type CurveShape = "contango" | "flat" | "backwardation" | "unknown";

/** The one-day, one-sigma move a VIX level prices, in percent. */
export function impliedDayPct(vix: number): number {
  return vix / SQRT252;
}

/** scanscore's band rule, exactly: backwardation is stressed at any level. */
export function vixBand(last: number | null | undefined, shape?: string | null): VixBand | null {
  if (last == null || !Number.isFinite(last)) return null;
  if (shape === "backwardation" || last >= VIX_STRESSED) return "stressed";
  if (last < VIX_GRIND) return "grind";
  if (last < VIX_NORMAL) return "normal";
  return "elevated";
}

/** volterm's shape rule for a VIX ÷ VIX3M ratio. */
export function curveShape(ratio: number | null | undefined): CurveShape {
  if (ratio == null || !Number.isFinite(ratio)) return "unknown";
  if (ratio > 1 + CURVE_FLAT_BAND) return "backwardation";
  if (ratio < 1 - CURVE_FLAT_BAND) return "contango";
  return "flat";
}

export const BAND_LABEL: Record<VixBand, string> = {
  grind: "Grind",
  normal: "Normal",
  elevated: "Elevated",
  stressed: "Stressed",
};

export interface BandRow {
  key: VixBand;
  label: string;
  /** "under 13", "13 – 20", "28 and up". */
  range: string;
  /** The implied SPY day the band covers: "±0.8% – ±1.3%". */
  move: string;
  /** What the tape does in it, and what to do about it. */
  read: string;
}

const pm = (vix: number) => `±${impliedDayPct(vix).toFixed(1)}%`;

/**
 * The four bands in order, their edges written from the constants above and
 * their reads the scanner's own notes (scanscore.py), one sentence longer.
 */
export const BANDS: readonly BandRow[] = [
  {
    key: "grind",
    label: BAND_LABEL.grind,
    range: `under ${VIX_GRIND}`,
    move: `under ${pm(VIX_GRIND)}`,
    read: "Tight ranges. Breakouts fail back into rotation. Size down or scalp. Protection is cheap.",
  },
  {
    key: "normal",
    label: BAND_LABEL.normal,
    range: `${VIX_GRIND} – ${VIX_NORMAL}`,
    move: `${pm(VIX_GRIND)} – ${pm(VIX_NORMAL)}`,
    read: "Structured break-and-retest trades with normal stops. The long-run average sits here, around 19.",
  },
  {
    key: "elevated",
    label: BAND_LABEL.elevated,
    range: `${VIX_NORMAL} – ${VIX_STRESSED}`,
    move: `${pm(VIX_NORMAL)} – ${pm(VIX_STRESSED)}`,
    read: "Wider ranges and noise. Widen stops, take partials earlier, don't fade strength.",
  },
  {
    key: "stressed",
    label: BAND_LABEL.stressed,
    range: `${VIX_STRESSED} and up`,
    move: `${pm(VIX_STRESSED)} and up`,
    read: "Levels hold less. Cut size hard. Rallies are short-covering until the curve flattens. Past 40 is a crisis print (2008, March 2020).",
  },
];
