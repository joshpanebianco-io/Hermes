import { NextResponse } from "next/server";
import type { ReportFeed } from "@/types/terminal";
import { failureReason } from "@/lib/offline";

/**
 * Where a report's generation stands — polled by the page every few seconds
 * until the job is done (src/lib/jobs.ts says why the page polls at all).
 *
 * The answer has the shape the POST used to return once the model was done:
 * the note as `latest`, the refreshed history, and the job's state beside
 * them. The id is the note's own timestamp slug, validated as the one-report
 * route validates it and for the same reason: it becomes a path upstream.
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
  } satisfies ReportFeed);
}

export async function GET(_req: Request, ctx: { params: Promise<{ id: string }> }) {
  const { id } = await ctx.params;
  if (!ID.test(id)) return offline(`not a job id: ${id}`);
  try {
    const r = await fetch(`${API.replace(/\/$/, "")}/api/report/job/${id}`, {
      cache: "no-store",
      signal: AbortSignal.timeout(10_000),
    });
    // A 404 is not an outage: the collector answered, but it is running code
    // from before generations were jobs. Say so, and what fixes it.
    if (r.status === 404) throw new Error("the running collector predates job polling — restart it with .\\dev.ps1 -Restart");
    if (!r.ok) throw new Error(`collector returned HTTP ${r.status}`);
    return NextResponse.json((await r.json()) as ReportFeed);
  } catch (e) {
    return offline(failureReason(e));
  }
}
