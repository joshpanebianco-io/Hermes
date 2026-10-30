import { NextResponse } from "next/server";
import type { PlanFeed } from "@/types/plan";
import { failureReason } from "@/lib/offline";

/**
 * Where a game plan's generation stands — the report's job route exactly
 * (/api/report/job/[id]), polled by the page until the plan is written.
 */

export const dynamic = "force-dynamic";
export const revalidate = 0;

const API = process.env.NT_API ?? "http://127.0.0.1:8100";
const ID = /^[0-9]{8}-[0-9]{6}$/;

function offline(reason: string): NextResponse {
  return NextResponse.json({
    config: { enabled: false, model: "" },
    latest: null,
    history: [],
    offline: { reason, api: API },
  } satisfies PlanFeed);
}

export async function GET(_req: Request, ctx: { params: Promise<{ id: string }> }) {
  const { id } = await ctx.params;
  if (!ID.test(id)) return offline(`not a job id: ${id}`);
  try {
    const r = await fetch(`${API.replace(/\/$/, "")}/api/plan/job/${id}`, {
      cache: "no-store",
      signal: AbortSignal.timeout(10_000),
    });
    if (r.status === 404) throw new Error("the running collector predates job polling — restart it with .\\dev.ps1 -Restart");
    if (!r.ok) throw new Error(`collector returned HTTP ${r.status}`);
    return NextResponse.json((await r.json()) as PlanFeed);
  } catch (e) {
    return offline(failureReason(e));
  }
}
