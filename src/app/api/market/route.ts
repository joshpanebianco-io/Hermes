import { NextResponse } from "next/server";
import type { MarketCtx } from "@/types/market";
import { failureReason } from "@/lib/offline";

/**
 * The Market tab's door to the collector — the stocks desk's conviction board:
 * the tape count, breadth, fuel, prints and the Fed path, gamma in ETF prices,
 * the index ETFs' option flow and the sector peers reporting this week.
 *
 * Same contract as /api/scanner: the collector's address stays server-side, and
 * a dead collector (or one started before this route existed) comes back as a
 * 200 with an `offline` block, so the tab says why it is empty rather than
 * failing.
 */

export const dynamic = "force-dynamic";
export const revalidate = 0;

const API = process.env.NT_API ?? "http://127.0.0.1:8100";

function offline(reason: string): MarketCtx {
  return {
    ok: false,
    built_utc: new Date().toISOString(),
    session: "closed",
    conviction: { bias: null, agree: 0, against: 0, neutral: 0, total: 0, grade: "none", max_conviction: 2, votes: [] },
    breadth: { sectors_up: 0, sectors_down: 0, sectors_total: 0, rsp_vs_spy: null, indices: [] },
    fuel: [],
    prints: [],
    fed: null,
    macro: [],
    gamma: null,
    index_options: [],
    peers: [],
    offline: { reason, api: API },
  };
}

export async function GET() {
  try {
    const r = await fetch(`${API.replace(/\/$/, "")}/api/market`, {
      cache: "no-store",
      signal: AbortSignal.timeout(8000),
    });
    if (r.status === 404) {
      return NextResponse.json(offline("the running collector predates the market context — restart it"));
    }
    if (!r.ok) return NextResponse.json(offline(`collector returned HTTP ${r.status}`));
    const data = (await r.json()) as MarketCtx;
    return NextResponse.json(data, { headers: { "Cache-Control": "no-store, max-age=0" } });
  } catch (e) {
    return NextResponse.json(offline(failureReason(e)));
  }
}
