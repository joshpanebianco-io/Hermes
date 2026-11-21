/**
 * The Market Outlook (server outlook.py `build`): the markets read against each other.
 * Served on /api/terminal as `outlook` for Macro's board, and on /api/dashboard as
 * `outlook` for the Dashboard's card. Absent from a collector older than 2026-11-21.
 */

export interface OutlookRow {
  /** The quote's key: ES, NQ, ZN, DXY, GC, SILVER, WTI, BTC. */
  key: string;
  /** The group's word, printed on its first row: "Stocks", "Bonds", "Gold". */
  group: string;
  /** The row's own name, empty where the group's word is the name. */
  name: string;
  /** The move, in percent. */
  pct: number;
  /** The move in its own usual days, signed, to one decimal. */
  mult: number;
  /** -3 to 3: none under half a usual day, then one, two, three. */
  arrows: number;
  /** False when the usual day is a stated one: too little history to measure it. */
  sized: boolean;
  /** A line for the row's hover: the 10-year yield's change, on the bond row. */
  note: string | null;
  /**
   * The bond row's yield change in basis points, printed beside its name; null on every
   * other row, and on the bond row until the cash yield has traded that day.
   */
  yield_bp?: number | null;
}

export interface MarketOutlook {
  ok: boolean;
  /** Why there is no read, when `ok` is false. */
  why?: string;
  /** What the figures are: today's, the session just finished, or the night's. */
  state?: "live" | "close" | "overnight";
  /** The day the figures are about, ISO. */
  day?: string;
  /** "record": the last close as it was written, shown overnight. */
  from?: "live" | "record";
  /** "Fri 20 Nov · close", "Mon 23 Nov · live". */
  label?: string;
  key?: string;
  /** The pattern: "Forced selling", "Risk-off", "Mixed". */
  name?: string;
  /** What moved: "stocks and metals sold, bonds bid". Empty when nothing did. */
  what?: string;
  /** The pattern in a sentence. */
  tell?: string;
  rows?: OutlookRow[];
  /**
   * The fear-to-greed scale (server outlook.py `sentiment`): today's risk appetite,
   * -100 to +100, from stocks, the VIX, high-yield credit and bitcoin, each in its usual
   * day. Null without stocks to read; absent on a record line from before it was kept.
   */
  sentiment?: { score: number; label: string; legs: { key: string; weight: number; mult: number }[] } | null;
  /** The sessions of the daily history that showed this pattern. */
  seen?: { n: number; of: number };
  /** The night so far, under a close read off the record. */
  overnight?: { name: string; what: string } | null;
}
