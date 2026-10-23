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
/**
 * scanscore.VIX_MEDIAN / VIX_PANIC — two sub-lines inside the bands (owner,
 * 2026-10-23: "being over 18"). Words only: the four bands above still score.
 * 18 is the VIX's long-run median; 35 is where its own mean reversion is the
 * trade.
 */
export const VIX_MEDIAN = 18;
export const VIX_PANIC = 35;
/** volterm.FLAT_BAND — a ratio within this of 1.00 is "flat", not a shape. */
export const CURVE_FLAT_BAND = 0.02;

const SQRT252 = Math.sqrt(252);

export type VixBand = "grind" | "normal" | "elevated" | "stressed";
/** quiet / heavy inside normal, panic inside stressed — scanscore.vix_sub. */
export type VixSub = "quiet" | "heavy" | "panic";
export type CurveShape = "contango" | "flat" | "backwardation" | "unknown";
/** The six rows of the table: the four bands, normal and stressed split at their sub-lines. */
export type VixRow = "grind" | "normal_quiet" | "normal_heavy" | "elevated" | "stressed" | "panic";

/** scanscore's sub-line rule, exactly. */
export function vixSub(last: number | null | undefined, band: VixBand | null): VixSub | null {
  if (last == null || !Number.isFinite(last) || band == null) return null;
  if (band === "normal") return last >= VIX_MEDIAN ? "heavy" : "quiet";
  if (band === "stressed" && last >= VIX_PANIC) return "panic";
  return null;
}

/** Which table row a band and its sub-line land on. */
export function vixRow(band: VixBand | null, sub: VixSub | null): VixRow | null {
  if (band === "normal") return sub === "heavy" ? "normal_heavy" : "normal_quiet";
  if (band === "stressed") return sub === "panic" ? "panic" : "stressed";
  return band;
}

/** The band word on a chip, with the sub-line where there is one: "Normal · 18+". */
export function bandChip(band: VixBand | null, sub: VixSub | null): string | null {
  if (band == null) return null;
  const base = BAND_LABEL[band];
  if (sub === "heavy") return `${base} · ${VIX_MEDIAN}+`;
  if (sub === "panic") return `${base} · ${VIX_PANIC}+`;
  return base;
}

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
  key: VixRow;
  /** The band this row belongs to — the chip's word and the row's hue. */
  band: VixBand;
  label: string;
  /** "under 13", "13 – 18", "35 and up". */
  range: string;
  /** The implied SPY day the row covers: "±0.8% – ±1.1%". */
  move: string;
  /** What the tape does in it: ranges, breaks, whether the retest holds. */
  tape: string;
  /** How to trade it, in the stocks desk's own terms: size, stops, what to wait for. */
  trade: string;
}

const pm = (vix: number) => `±${impliedDayPct(vix).toFixed(1)}%`;

/**
 * The six rows in order — the four bands with normal split at the median and
 * stressed at panic — their edges written from the constants above and their
 * words the scanner's own notes (scanscore.py), split in two.
 *
 * TAPE AND TRADE ARE SEPARATE COLUMNS (owner, 2026-10-23: "make it easier to
 * understand and how to trade when the vix is at each number"). One read used
 * to carry what the tape does, why, and what to do about it in a sentence, and
 * the what-to-do was the part buried at the end. The why stays in the paragraph
 * above the table; the trade column is written for the desk's own
 * break-and-retest — does the retest hold, how wide the stop, what size.
 */
export const BANDS: readonly BandRow[] = [
  {
    key: "grind",
    band: "grind",
    label: BAND_LABEL.grind,
    range: `under ${VIX_GRIND}`,
    move: `under ${pm(VIX_GRIND)}`,
    tape: "Small ranges. Breakouts stall and fall back inside the range.",
    trade: "Fade the edges or take scalps. Half size. Don't chase a break.",
  },
  {
    key: "normal_quiet",
    band: "normal",
    label: `${BAND_LABEL.normal} · quiet`,
    range: `${VIX_GRIND} – ${VIX_MEDIAN}`,
    move: `${pm(VIX_GRIND)} – ${pm(VIX_MEDIAN)}`,
    tape: "Moves fade inside the day. A break usually comes back to retest, and the retest usually holds.",
    trade: "Break-and-retest at normal size and normal stops. Wait for the retest, don't buy the first push.",
  },
  {
    key: "normal_heavy",
    band: "normal",
    label: `${BAND_LABEL.normal} · heavy`,
    range: `${VIX_MEDIAN} – ${VIX_NORMAL}`,
    move: `${pm(VIX_MEDIAN)} – ${pm(VIX_NORMAL)}`,
    tape: "Moves carry. Breaks run to the next level and trends hold into the close. 1%-plus days are normal.",
    trade: "The best tape for break-and-retest. Full size, stops one notch wider, let winners reach target.",
  },
  {
    key: "elevated",
    band: "elevated",
    label: BAND_LABEL.elevated,
    range: `${VIX_NORMAL} – ${VIX_STRESSED}`,
    move: `${pm(VIX_NORMAL)} – ${pm(VIX_STRESSED)}`,
    tape: "Big moves that extend, then whip back. Stocks start moving with the index, not their own story.",
    trade: "Trade with the index direction only. Wider stops, partials early, smaller size. Don't fade strength.",
  },
  {
    key: "stressed",
    band: "stressed",
    label: BAND_LABEL.stressed,
    range: `${VIX_STRESSED} – ${VIX_PANIC}`,
    move: `${pm(VIX_STRESSED)} – ${pm(VIX_PANIC)}`,
    tape: "Big ranges both ways, not trends. Every stock trades as the index. Stops get hit by noise.",
    trade: "Cut size hard or sit out. Rallies are short-covering, not trends to hold, until the curve flattens.",
  },
  {
    key: "panic",
    band: "stressed",
    label: "Panic",
    range: `${VIX_PANIC} and up`,
    move: `${pm(VIX_PANIC)} and up`,
    tape: "Two to three percent a day. Retests rarely hold. Past 40 is a crisis print (2008, March 2020).",
    trade: "Don't trade stock levels. The trade is the VIX itself coming back down once the curve flattens.",
  },
];

/* ------------------------------------------------------------------------ *
 * The implied day — each book's one-sigma move in its own points, how much
 * of it today's range has used, and implied against realised.
 *
 * THE THRESHOLDS ARE THE SERVER'S (volterm.py FUEL_ROOM / FUEL_STRETCHED,
 * optcalc.py PREMIUM_CHEAP / PREMIUM_RICH), mirrored here for the reason the
 * VIX bands are: the word on the row is the one the server scored, and the
 * table behind it is the same rule written out. Change one side and change
 * the other. They are the stocks desk's own numbers — the ETF fuel on the
 * weather strip and the premium verdict on every scanner name — so the two
 * desks never disagree about what "stretched" or "rich" means.
 * ------------------------------------------------------------------------ */

/** volterm.FUEL_ROOM / FUEL_STRETCHED — today's range ÷ the implied day. */
export const FUEL_ROOM = 0.6;
export const FUEL_STRETCHED = 1.0;
/** optcalc.PREMIUM_CHEAP / PREMIUM_RICH — implied ÷ realised. */
export const PREMIUM_CHEAP = 0.9;
export const PREMIUM_RICH = 1.25;

export type Fuel = "room" | "normal" | "stretched";
export type Premium = "cheap" | "fair" | "rich";

/** One row of a rule table: the word, the range it covers, what to do in it. */
export interface ReadRow<K extends string> {
  key: K;
  label: string;
  range: string;
  read: string;
}

/** Range used, in order: the reads are the futures desk's, for ranges, targets and stops. */
export const FUEL_ROWS: readonly ReadRow<Fuel>[] = [
  {
    key: "room",
    label: "Room",
    range: `under ${FUEL_ROOM}×`,
    read: "The day's move is still to come. Breaks of the overnight range have fuel behind them.",
  },
  {
    key: "normal",
    label: "Normal",
    range: `${FUEL_ROOM} – ${FUEL_STRETCHED.toFixed(1)}×`,
    read: "Targets inside the band, stops outside the noise.",
  },
  {
    key: "stretched",
    label: "Stretched",
    range: `over ${FUEL_STRETCHED.toFixed(1)}×`,
    read: "The day has done what was priced. Fade extremes, size down on continuation. A trend day runs on regardless.",
  },
];

/** Implied against realised, in order: a regime read for the futures desk, not a trade. */
export const PREMIUM_ROWS: readonly ReadRow<Premium>[] = [
  {
    key: "cheap",
    label: "Cheap",
    range: `under ${PREMIUM_CHEAP.toFixed(2)}`,
    read: "Moves have been bigger than the options price, usually after a shock. Don't trust the band; expect it to break.",
  },
  {
    key: "fair",
    label: "Fair",
    range: `${PREMIUM_CHEAP.toFixed(2)} – ${PREMIUM_RICH.toFixed(2)}`,
    read: "Options price about what has been happening. The band is a fair yardstick.",
  },
  {
    key: "rich",
    label: "Rich",
    range: `over ${PREMIUM_RICH.toFixed(2)}`,
    read: "Options price more than has been happening. The band is generous; the realised day is the better measure of the noise you are trading in.",
  },
];

/** Fuel's ink: room is fuel in the tank, stretched is the caution. */
export function fuelTone(f: Fuel | null | undefined): string {
  return f === "stretched" ? "text-flip-fig" : f === "room" ? "text-call-fig" : "text-ink-2";
}

/**
 * Premium's ink ON THE FUTURES DESK. The stocks desk colours cheap green
 * (ScanTable.premiumHue): cheap premium is a long option worth owning. A
 * futures trader buys no premium — cheap means realised has overtaken
 * implied and the band is about to be breached, which is the warning, so it
 * is red here. The word is the same on both desks; what it tells you to do
 * is not, and the colour follows the action.
 */
export function premiumTone(p: Premium | null | undefined): string {
  return p === "rich" ? "text-flip-fig" : p === "cheap" ? "text-put-fig" : "text-ink-2";
}
