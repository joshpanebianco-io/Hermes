import { NextResponse } from "next/server";
import type { PlanFeed } from "@/types/plan";
import { failureReason } from "@/lib/offline";

/**
 * One stored plan by id — reopen it, or delete it.
 *
 * The id goes into a path on the collector, so it is validated rather than
 * trusted, and on DELETE that matters most: anything that is not a plain slug
 * never leaves this process. The collector basenames it as well — this is the
 * outer of two locks.
 */

export const dynamic = "force-dynamic";
export const revalidate = 0;

const API = process.env.NT_API ?? "http://127.0.0.1:8100";
const ID = /^[0-9A-Za-z][0-9A-Za-z_-]{0,47}$/;

function offline(reason: string): NextResponse {
  return NextResponse.json({
    config: { enabled: false, model: "" },
    latest: null,
    history: [],
    offline: { reason, api: API },
  } satisfies PlanFeed);
}

async function proxy(id: string, method: "GET" | "DELETE"): Promise<NextResponse> {
  if (!ID.test(id)) return offline(`not a plan id: ${id}`);
  try {
    const r = await fetch(`${API.replace(/\/$/, "")}/api/plan/${id}`, {
      method,
      cache: "no-store",
      signal: AbortSignal.timeout(10_000),
    });
    if (!r.ok) throw new Error(`collector returned HTTP ${r.status}`);
    return NextResponse.json((await r.json()) as PlanFeed);
  } catch (e) {
    return offline(failureReason(e));
  }
}

export async function GET(_req: Request, ctx: { params: Promise<{ id: string }> }) {
  return proxy((await ctx.params).id, "GET");
}

export async function DELETE(_req: Request, ctx: { params: Promise<{ id: string }> }) {
  return proxy((await ctx.params).id, "DELETE");
}
