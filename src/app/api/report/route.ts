import { NextResponse } from "next/server";
import type { ReportFeed } from "@/types/terminal";
import { failureReason } from "@/lib/offline";

/**
 * The report proxy — GET reads the last one, POST writes a new one.
 *
 * SAME REASONING AS /api/terminal: the collector's address is server-side
 * configuration and the browser has no business knowing it. What is different
 * here is the timeout. Generating a report means a round trip to a model that
 * is thinking, and on a free tier that can take most of a minute — so this one
 * waits far longer than the terminal poll, and the panel shows a working state
 * rather than a spinner with no explanation.
 */

export const dynamic = "force-dynamic";
export const revalidate = 0;
// FIVE MINUTES, MEASURED RATHER THAN GUESSED. A first real run took 188
// seconds: the free pool for the preferred model was saturated, so the chain
// walked to the next one, and a free reasoning endpoint handed the full digest
// is simply slow. 120s cut off a report that was about to arrive, which is the
// worst of both — the tokens were spent and the answer was thrown away.
export const maxDuration = 300;

const API = process.env.NT_API ?? "http://127.0.0.1:8100";

function offline(reason: string): ReportFeed {
  return {
    config: { enabled: false, model: "" },
    latest: null,
    history: [],
    offline: { reason, api: API },
  };
}

async function call(method: "GET" | "POST" | "DELETE", timeoutMs: number, qs = "") {
  const r = await fetch(`${API.replace(/\/$/, "")}/api/report${qs}`, {
    method,
    cache: "no-store",
    signal: AbortSignal.timeout(timeoutMs),
  });
  if (!r.ok) throw new Error(`collector returned HTTP ${r.status}`);
  return (await r.json()) as ReportFeed;
}

/*
 * THE PICKER'S CHOICE USED TO DIE RIGHT HERE. The panel sent
 * `?session=asia&asset=NQ`, this proxy forwarded a bare POST, and the
 * collector fell back to its defaults — so every report generated through
 * the UI was auto/all-books no matter what was selected ("even when i have
 * an asset selected, it still seems to generate report for all 3"). The
 * values are whitelisted rather than passed through raw because this is
 * still a proxy, not a tunnel.
 */
const SESSIONS = new Set(["auto", "asia", "london", "ny"]);
const ASSETS = new Set(["all", "NQ", "ES", "GC"]);

function pickQuery(req: Request): string {
  const u = new URL(req.url);
  const qs = new URLSearchParams();
  const session = u.searchParams.get("session") ?? "";
  const asset = u.searchParams.get("asset") ?? "";
  if (SESSIONS.has(session)) qs.set("session", session);
  if (ASSETS.has(asset)) qs.set("asset", asset);
  const out = qs.toString();
  return out ? `?${out}` : "";
}

export async function GET() {
  try {
    return NextResponse.json(await call("GET", 10_000));
  } catch (e) {
    return NextResponse.json(offline(failureReason(e)));
  }
}

export async function POST(req: Request) {
  try {
    return NextResponse.json(await call("POST", 290_000, pickQuery(req)));
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
