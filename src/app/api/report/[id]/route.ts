import { NextResponse } from "next/server";
import type { ReportFeed } from "@/types/terminal";
import { failureReason } from "@/lib/offline";

/**
 * One stored report by id, so a past call can be reopened.
 *
 * The id is a timestamp slug the collector minted (`20260831-090500`) and it
 * goes into a path on the collector, so it is validated rather than trusted:
 * the panel is the only thing that produces these, but a route handler that
 * pastes a client string into an upstream URL has to say why it is safe.
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

/** GET and DELETE differ only in the verb, so the trip is written once. */
async function proxy(id: string, method: "GET" | "DELETE"): Promise<NextResponse> {
  if (!ID.test(id)) return offline(`not a report id: ${id}`);
  try {
    const r = await fetch(`${API.replace(/\/$/, "")}/api/report/${id}`, {
      method,
      cache: "no-store",
      signal: AbortSignal.timeout(10_000),
    });
    if (!r.ok) throw new Error(`collector returned HTTP ${r.status}`);
    return NextResponse.json((await r.json()) as ReportFeed);
  } catch (e) {
    return offline(failureReason(e));
  }
}

export async function GET(_req: Request, ctx: { params: Promise<{ id: string }> }) {
  return proxy((await ctx.params).id, "GET");
}

/**
 * Delete one stored report.
 *
 * THE ID PATTERN IS THE GUARD, and it matters more on this verb than on GET: a
 * malformed id on a read returns the offline body and nothing happens, while on
 * a delete it would be a path handed to `os.remove` on the collector. The
 * collector basenames it as well — this is the outer of two locks, not the only
 * one. Anything that is not exactly `YYYYMMDD-HHMMSS` never leaves this process.
 */
export async function DELETE(_req: Request, ctx: { params: Promise<{ id: string }> }) {
  return proxy((await ctx.params).id, "DELETE");
}
