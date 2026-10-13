import { NextResponse } from "next/server";
import type { ScannerPayload } from "@/types/scanner";
import { failureReason } from "@/lib/offline";

/**
 * The scanner's door to the collector — same reasoning as /api/terminal: the
 * collector's address is server-side configuration, and a dead collector is a
 * normal state that comes back as a 200 with an `offline` block rather than an
 * HTTP error.
 *
 * ITS OWN ROUTE, NOT A BLOCK ON /api/terminal. The scanner carries thirty
 * names' levels, signals, headlines and filings; the terminal poll runs every
 * twenty seconds on every tab whether or not the scanner is open. So the
 * scanner is fetched only while its tab is on screen.
 */

export const dynamic = "force-dynamic";
export const revalidate = 0;

const API = process.env.NT_API ?? "http://127.0.0.1:8100";

function offline(reason: string): ScannerPayload {
  return {
    ok: false,
    built_utc: new Date().toISOString(),
    status: null,
    age_min: null,
    session: "closed",
    trading_day: "",
    pm_locked: false,
    bench: "SPY",
    watchlist: [],
    regime: {
      vix: { last: null, pct: null, chg: null, ratio: null, shape: "unknown", vvix: null, vvix_pct: null },
      band: null,
      spy_em_pct: null,
      tape: { SPY: null, QQQ: null, IWM: null },
      bias: null,
      confirm: null,
      event: null,
      notes: [],
    },
    rows: [],
    offline: { reason, api: API },
  };
}

export async function GET() {
  try {
    const r = await fetch(`${API.replace(/\/$/, "")}/api/scanner`, {
      cache: "no-store",
      signal: AbortSignal.timeout(8000),
    });
    if (!r.ok) return NextResponse.json(offline(`collector returned HTTP ${r.status}`));
    const data = (await r.json()) as ScannerPayload;
    return NextResponse.json(data, { headers: { "Cache-Control": "no-store, max-age=0" } });
  } catch (e) {
    return NextResponse.json(offline(failureReason(e)));
  }
}
