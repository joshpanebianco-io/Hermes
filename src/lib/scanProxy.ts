import { NextResponse } from "next/server";
import { failureReason } from "@/lib/offline";

/**
 * The scanner's read-only doors to the collector — events, stats, one name's
 * bars — share one shape: forward a whitelisted path, answer 200 with the
 * collector's body, and turn a dead collector into a body with an `offline`
 * block rather than an HTTP error (the same contract /api/terminal keeps).
 */

const API = process.env.NT_API ?? "http://127.0.0.1:8100";

export async function scanProxy<T extends object>(path: string, empty: T): Promise<NextResponse> {
  try {
    const r = await fetch(`${API.replace(/\/$/, "")}${path}`, {
      cache: "no-store",
      signal: AbortSignal.timeout(8000),
    });
    if (!r.ok) {
      return NextResponse.json({ ...empty, offline: { reason: `collector returned HTTP ${r.status}`, api: API } });
    }
    return NextResponse.json(await r.json(), { headers: { "Cache-Control": "no-store, max-age=0" } });
  } catch (e) {
    return NextResponse.json({ ...empty, offline: { reason: failureReason(e), api: API } });
  }
}

/** A non-negative integer query value, clamped — anything else falls back. */
export function intParam(v: string | null, fallback: number, max: number): number {
  const n = Number(v);
  return Number.isInteger(n) && n >= 0 ? Math.min(n, max) : fallback;
}
