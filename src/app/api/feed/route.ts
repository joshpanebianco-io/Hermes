import { NextResponse } from "next/server";
import type { PriceFeed } from "@/types/feed";
import { failureReason } from "@/lib/offline";

/**
 * The live-price feed switch: Webull's trades beside Yahoo's stream, or Yahoo alone
 * (server sources/webull.py `feed_mode`; owner, 2026-11-18: "make sure our current
 * implementation is kept as a fallback so it's easy to revert and switch between").
 *
 * A proxy, not a tunnel: a POST that is not `{ feed: "webull" | "yahoo" | null }` is
 * refused before it leaves the web half.
 */

export const dynamic = "force-dynamic";
export const revalidate = 0;

const API = process.env.NT_API ?? "http://127.0.0.1:8100";
const URL_ = `${API.replace(/\/$/, "")}/api/feed`;

const empty = (error: string): Partial<PriceFeed> & { error: string } => ({ error });

export async function GET() {
  try {
    const r = await fetch(URL_, { cache: "no-store", signal: AbortSignal.timeout(6000) });
    if (!r.ok) return NextResponse.json(empty(`HTTP ${r.status}`), { status: r.status });
    return NextResponse.json((await r.json()) as PriceFeed);
  } catch (e) {
    return NextResponse.json(empty(failureReason(e)), { status: 502 });
  }
}

export async function POST(req: Request) {
  let body: unknown;
  try {
    body = await req.json();
  } catch {
    return NextResponse.json(empty("body is not JSON"), { status: 400 });
  }
  const feed = (body as { feed?: unknown })?.feed;
  if (!(feed === "webull" || feed === "yahoo" || feed === null)) {
    return NextResponse.json(empty('expected { feed: "webull" | "yahoo" | null }'), { status: 400 });
  }
  try {
    const r = await fetch(URL_, {
      method: "POST",
      cache: "no-store",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ feed }),
      signal: AbortSignal.timeout(10000),
    });
    const data = (await r.json().catch(() => null)) as PriceFeed | { detail?: unknown } | null;
    if (!r.ok) {
      const detail = data && "detail" in data ? JSON.stringify(data.detail) : `HTTP ${r.status}`;
      return NextResponse.json(empty(`collector refused it: ${detail}`), { status: r.status });
    }
    return NextResponse.json(data as PriceFeed);
  } catch (e) {
    return NextResponse.json(empty(failureReason(e)), { status: 502 });
  }
}
