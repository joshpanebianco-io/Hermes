import { NextResponse } from "next/server";
import type { PlanFeed } from "@/types/plan";
import { failureReason } from "@/lib/offline";

/**
 * The Game plan proxy — GET reads the last plan, POST writes a new one.
 *
 * The futures Report's arrangement exactly (see /api/report): the collector's
 * address stays server-side, a dead collector comes back as a 200 with an
 * `offline` block, and the POST starts a job rather than waiting on the
 * model — the page polls /api/plan/job/[id] for the plan.
 */

export const dynamic = "force-dynamic";
export const revalidate = 0;

const API = process.env.NT_API ?? "http://127.0.0.1:8100";

function offline(reason: string): PlanFeed {
  return {
    config: { enabled: false, model: "" },
    latest: null,
    history: [],
    offline: { reason, api: API },
  };
}

async function call(method: "GET" | "POST" | "DELETE", timeoutMs: number, qs = "") {
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
    return NextResponse.json(await call("POST", 15_000, TOPS.has(top) ? `?top=${top}` : ""));
  } catch (e) {
    return NextResponse.json(offline(failureReason(e)));
  }
}

/*
 * SEVERAL OR ALL, IN ONE TRIP: `?ids=a&ids=b`, or `?all=1`. The ids are
 * whitelisted by shape here as the single-id route does — a delete is the verb
 * that must never carry a path — and the collector basenames them as well.
 * Nothing valid forwards an empty delete, which removes nothing and hands the
 * list back as it is.
 */
const ID = /^[0-9]{8}-[0-9]{6}$/;

function deleteQuery(req: Request): string {
  const u = new URL(req.url);
  const qs = new URLSearchParams();
  if (u.searchParams.get("all") === "1") qs.set("all", "1");
  else for (const id of u.searchParams.getAll("ids")) if (ID.test(id)) qs.append("ids", id);
  const out = qs.toString();
  return out ? `?${out}` : "";
}

export async function DELETE(req: Request) {
  try {
    return NextResponse.json(await call("DELETE", 15_000, deleteQuery(req)));
  } catch (e) {
    return NextResponse.json(offline(failureReason(e)));
  }
}
