import { NextResponse } from "next/server";
import type { PlanFeed } from "@/types/plan";
import { failureReason } from "@/lib/offline";

/**
 * The Game plan proxy — GET reads the last plan, POST writes a new one.
 *
 * The futures Report's arrangement exactly (see /api/report): the collector's
 * address stays server-side, a dead collector comes back as a 200 with an
 * `offline` block, and a generation is given minutes, because a free model
 * reading the scanner's top names and their option chains is not quick.
 */

export const dynamic = "force-dynamic";
export const revalidate = 0;
// The report's measured ceiling: a saturated free pool walks the fallback
// chain, and cutting a generation off at two minutes threw away answers that
// were about to land.
export const maxDuration = 300;

const API = process.env.NT_API ?? "http://127.0.0.1:8100";

function offline(reason: string): PlanFeed {
  return {
    config: { enabled: false, model: "" },
    latest: null,
    history: [],
    offline: { reason, api: API },
  };
}

async function call(method: "GET" | "POST", timeoutMs: number, qs = "") {
  const r = await fetch(`${API.replace(/\/$/, "")}/api/plan${qs}`, {
    method,
    cache: "no-store",
    signal: AbortSignal.timeout(timeoutMs),
  });
  // A 404 is not an outage: the collector answered, but it is running code
  // from before the Game plan existed. Say so, and what fixes it.
  if (r.status === 404) throw new Error("the running collector predates the Game plan — restart it to load it");
  if (!r.ok) throw new Error(`collector returned HTTP ${r.status}`);
  return (await r.json()) as PlanFeed;
}

// Whitelisted, as the report proxy whitelists its pickers: a proxy, not a tunnel.
const TOPS = new Set(["4", "6", "8", "10"]);

export async function GET() {
  try {
    return NextResponse.json(await call("GET", 10_000));
  } catch (e) {
    return NextResponse.json(offline(failureReason(e)));
  }
}

export async function POST(req: Request) {
  const top = new URL(req.url).searchParams.get("top") ?? "";
  try {
    return NextResponse.json(await call("POST", 290_000, TOPS.has(top) ? `?top=${top}` : ""));
  } catch (e) {
    return NextResponse.json(offline(failureReason(e)));
  }
}
