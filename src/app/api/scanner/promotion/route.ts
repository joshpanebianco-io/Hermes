import { NextResponse } from "next/server";
import type { Watchlist } from "@/types/scanner";
import { failureReason } from "@/lib/offline";

/**
 * The pool's promotion switch — on or off.
 *
 * The collector owns the pool (sources/pool.py) and answers with the same
 * read the watchlist route gives, so the editor repaints from one shape.
 * Like the watchlist route this is a proxy, not a tunnel: anything that is
 * not `{ on: boolean }` is refused before it leaves the web half.
 */

export const dynamic = "force-dynamic";
export const revalidate = 0;

const API = process.env.NT_API ?? "http://127.0.0.1:8100";
const URL_ = `${API.replace(/\/$/, "")}/api/scanner/promotion`;

const empty = (error: string): Watchlist => ({ symbols: [], default: [], error });

export async function POST(req: Request) {
  let body: unknown;
  try {
    body = await req.json();
  } catch {
    return NextResponse.json(empty("body is not JSON"), { status: 400 });
  }
  const on = (body as { on?: unknown })?.on;
  if (typeof on !== "boolean") {
    return NextResponse.json(empty("expected { on: boolean }"), { status: 400 });
  }
  try {
    const r = await fetch(URL_, {
      method: "POST",
      cache: "no-store",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ on }),
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
