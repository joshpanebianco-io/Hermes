import type { ReportAsset, ReportSession } from "@/types/terminal";

/**
 * Which reports each desk writes and reads (owner, 2026-11-16: "in both futures and stocks
 * lets add Market Report tab with the generate funcitonality next to cl and then next to
 * charts. the one in futures will have selectors for NQ, ES, GC, SIL, and CL with Asia,
 * London and NY for the session selectors and in stocks it will just be combination
 * overview of SPY, QQQ, IWM with just NY for the session").
 *
 *   futures   one book a report, NQ, ES, GC, SIL or CL, for Asia, London or New York.
 *   stocks    SPY, QQQ and IWM in one report ("etfs"), for New York only.
 *
 * A REPORT IS READ UNDER EVERY BOOK IT CARRIES. The Market Report page wrote NQ and ES
 * together ("indexes") for a day, and the first briefs NQ, ES and gold ("all"): one of
 * those opens under each of its books, so nothing written before goes missing. The Stocks
 * desk reads its own report alone, and each desk's Past reports list is its own.
 *
 * Pure.
 */

export type ReportDesk = "futures" | "stocks";

export interface Pick<K extends string> {
  key: K;
  label: string;
  title: string;
}

export const SESSION_PICKS: readonly Pick<ReportSession>[] = [
  { key: "asia", label: "Asia", title: "18:00–03:00 ET · Nikkei, Hang Seng, USD/JPY" },
  { key: "london", label: "London", title: "03:00–08:00 ET · FTSE, DAX, EUR/USD, Bunds" },
  { key: "ny", label: "New York", title: "09:30–16:00 ET · the US open, the curve, the dollar" },
];

export const DESK_REPORT: Record<ReportDesk, { subjects: readonly Pick<ReportAsset>[]; sessions: readonly ReportSession[] }> = {
  futures: {
    subjects: [
      { key: "NQ", label: "NQ", title: "Nasdaq 100 futures · the megacaps, the front of the curve, technology" },
      { key: "ES", label: "ES", title: "S&P 500 futures · sector rotation and breadth carry more of it" },
      { key: "GC", label: "GC", title: "Gold futures · real yields, the dollar and geopolitics" },
      { key: "SIL", label: "SIL", title: "Silver futures · rates and the dollar as gold reads them, gold itself, and copper" },
      { key: "CL", label: "CL", title: "WTI crude futures · the dollar, the products, demand, the inventories and supply risk" },
    ],
    sessions: ["asia", "london", "ny"],
  },
  stocks: {
    subjects: [
      {
        key: "etfs",
        label: "SPY · QQQ · IWM",
        title: "The three index funds in one report, read through the Stocks tape, each against its own PDH, PDL, PMH and PML",
      },
    ],
    sessions: ["ny"],
  },
};

/** The books a stored report carries a call for. */
export function booksIn(asset: ReportAsset | null | undefined): string[] {
  switch (asset) {
    case "indexes":
      return ["NQ", "ES"];
    case "all":
    case null:
    case undefined:
      // A note from before the subject was stored was about all three.
      return ["NQ", "ES", "GC"];
    case "etfs":
      return ["etfs"];
    default:
      return [asset];
  }
}

/** The desk a stored report belongs to. */
export function deskOf(asset: ReportAsset | null | undefined): ReportDesk {
  return asset === "etfs" ? "stocks" : "futures";
}

/** Whether a stored report is read under a subject's pill. */
export function covers(asset: ReportAsset | null | undefined, subject: ReportAsset): boolean {
  return booksIn(asset).includes(subject);
}

/**
 * The pill a past report lights when it is opened by hand: its own book, or for one that
 * carries several, the book that is lit already when it is one of them, else its first.
 */
export function subjectFor(asset: ReportAsset | null | undefined, current: ReportAsset, desk: ReportDesk): ReportAsset {
  const subjects = DESK_REPORT[desk].subjects.map((s) => s.key);
  if (covers(asset, current)) return current;
  return (booksIn(asset).find((b) => (subjects as string[]).includes(b)) as ReportAsset | undefined) ?? current;
}

/** What a Past reports row says the report is about. */
export function assetWord(asset: ReportAsset | null | undefined): string {
  return asset === "etfs" ? "SPY · QQQ · IWM" : booksIn(asset).join(" · ");
}
