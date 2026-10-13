import { NextResponse } from "next/server";
import type { Watchlist } from "@/types/scanner";
import { failureReason } from "@/lib/offline";

/**
 * The scanner's watchlist — read it, or replace it.
 *
 * The collector owns the list (it is what decides which names get fetched),
 * validates it and persists it; this proxy only forwards. It still refuses
 * anything that is not `{ symbols: string[] }` before it leaves the machine's
 * web half, because this is a proxy, not a tunnel.
 */

export const dynamic = "force-dynamic";
export const revalidate = 0;

const API = process.env.NT_API ?? "http://127.0.0.1:8100";
const URL_ = `${API.replace(/\/$/, "")}/api/scanner/watchlist`;

const empty = (error: string): Watchlist => ({ symbols: [], default: [], error });

export async function GET() {
  try {
    const r = await fetch(URL_, { cache: "no-store", signal: AbortSignal.timeout(6000) });
    if (!r.ok) return NextResponse.json(empty(`collector returned HTTP ${r.status}`));
    return NextResponse.json((await r.json()) as Watchlist);
  } catch (e) {
    return NextResponse.json(empty(failureReason(e)));
  }
}

export async function POST(req: Request) {
  let body: unknown;
  try {
    body = await req.json();
  } catch {
    return NextResponse.json(empty("body is not JSON"), { status: 400 });
  }
  const symbols = (body as { symbols?: unknown })?.symbols;
  if (!Array.isArray(symbols) || !symbols.every((s) => typeof s === "string")) {
    return NextResponse.json(empty("expected { symbols: string[] }"), { status: 400 });
  }
  try {
    const r = await fetch(URL_, {
      method: "POST",
      cache: "no-store",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ symbols }),
      signal: AbortSignal.timeout(6000),
    });
    const data = (await r.json().catch(() => null)) as Watchlist | { detail?: unknown } | null;
    if (!r.ok) {
      const detail = data && "detail" in data ? JSON.stringify(data.detail) : `HTTP ${r.status}`;
      return NextResponse.json(empty(`collector refused it: ${detail}`), { status: r.status });
    }
    return NextResponse.json(data as Watchlist);
  } catch (e) {
    return NextResponse.json(empty(failureReason(e)), { status: 502 });
  }
}
