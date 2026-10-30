"use client";

import { Report } from "@/components/panels/Report";
import { StockPlan } from "@/components/panels/StockPlan";
import { DeskSwitch } from "@/components/panels/DeskSwitch";
import type { ReportController } from "@/lib/useReport";
import type { PlanController } from "@/lib/useStockPlan";
import type { Desk } from "@/lib/tabs";

/**
 * Analysis — the written read, behind the desk switch.
 *
 * THE DESK SWITCH LIVES HERE AND ON STRUCTURE, not in the header (owner,
 * 2026-10-30: "instead of having the futures and stock & options toggle
 * global, we have it in this analysis section"). Only the note differs by
 * desk — the futures brief for NQ, ES and GC, or the stocks game plan for
 * the scanner's top names — so the switch sits above the note it chooses,
 * remembered, with `D` flipping it from anywhere.
 *
 * BOTH NOTES KEEP THEIR STATE while the other is on screen: the controllers
 * are the Terminal's (useReport, useStockPlan), so a brief still being
 * written is still being written when you flip to the plan and back.
 */
const SUB = {
  futures: "The pre-session brief — NQ, ES and GC for Asia, London or New York.",
  stocks: "The pre-open game plan — the scanner's top names for the New York session.",
} as const;

export function Analysis({
  desk,
  onDesk,
  report,
  plan,
}: {
  desk: Desk;
  onDesk: (d: Desk) => void;
  report: ReportController;
  plan: PlanController;
}) {
  return (
    <div className="flex min-h-0 flex-1 flex-col">
      <DeskSwitch desk={desk} onDesk={onDesk} sub={SUB} />
      {desk === "futures" ? <Report {...report} /> : <StockPlan {...plan} />}
    </div>
  );
}
