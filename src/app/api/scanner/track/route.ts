import { NextResponse } from "next/server";
import { failureReason } from "@/lib/offline";

/** Put a name from the wide scan on today's list. It rolls off with the day. */

export const dynamic = "force-dynamic";
export const revalidate = 0;

const API = process.env.NT_API ?? "http://127.0.0.1:8100";
const SYM = /^[A-Z0-9][A-Z0-9.-]{0,9}$/;

export async function POST(req: Request) {
  let sym: unknown;
  try {
    sym = ((await req.json()) as { sym?: unknown })?.sym;
  } catch {
    return NextResponse.json({ ok: false, error: "body is not JSON" }, { status: 400 });
  }
  if (typeof sym !== "string" || !SYM.test(sym)) {
    return NextResponse.json({ ok: false, error: "not a ticker" }, { status: 400 });
  }
  try {
    const r = await fetch(`${API.replace(/\/$/, "")}/api/scanner/track`, {
      method: "POST",
      cache: "no-store",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ sym }),
      signal: AbortSignal.timeout(6000),
    });
    return NextResponse.json(await r.json(), { status: r.status });
  } catch (e) {
    return NextResponse.json({ ok: false, error: failureReason(e) }, { status: 502 });
  }
}
