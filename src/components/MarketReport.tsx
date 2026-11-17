"use client";

import type { ReportSession, Terminal as TerminalData } from "@/types/terminal";
import { Report } from "@/components/panels/Report";
import type { ReportController } from "@/lib/useReport";
import type { ReportDesk } from "@/lib/reportDesk";

/**
 * The Market Report view, on the Futures tab after CL and on the Stocks tab after Charts
 * (owner, 2026-11-16: "in both futures and stocks lets add Market Report tab with the
 * generate funcitonality next to cl and then next to charts").
 *
 *   futures   a pill for each of NQ, ES, GC, SIL and CL, and one for each of Asia,
 *             London and New York.
 *   stocks    SPY · QQQ · IWM, for New York: the three funds in one report, read
 *             through the Stocks tape (server report._etf_facts).
 *
 * WHERE IT HAS BEEN. The written read was the Analysis tab's until 2026-11-11, the
 * Futures tab's Brief view and the Stocks tab's Market view until 2026-11-15, then one
 * Market Report page right of Futures, which left the navigation on the morning of
 * 2026-11-16 for the Bias card's slide-out. The slide-out stays: it is the engine's read
 * now; this is the written one. Old links to the page (`?tab=report`, `plan`,
 * `analysis`) open the Futures view (lib/tabs).
 *
 * THE SESSION THE CLOCK SAYS is the one the futures board is weighing for
 * (`drivers.weights`, server drivers.weights_for): the session trading now or opening
 * next, New York from two hours before its bell. It is the pill that is lit until
 * another is picked, and it is not remembered: a page opened in the New York morning
 * is not left on last night's Asia. The Stocks report is New York's alone.
 */
const CLOCK: Record<string, ReportSession> = { asia: "asia", london: "london", ny_pre: "ny", ny_live: "ny" };

export function MarketReportView({ data, report, desk }: { data: TerminalData; report: ReportController; desk: ReportDesk }) {
  const clockSession = desk === "stocks" ? "ny" : (CLOCK[data.drivers?.weights ?? ""] ?? "ny");
  return <Report {...report} clockSession={clockSession} desk={desk} />;
}
