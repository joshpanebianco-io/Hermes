import { NextResponse } from "next/server";
import type { ScanBars } from "@/types/scanner";
import { scanProxy } from "@/lib/scanProxy";

/** One name's bars on `?tf=` (1m, 3m, 5m, 10m, D), wave, VWAP and levels — what the detail pane's chart draws. */

export const dynamic = "force-dynamic";
export const revalidate = 0;

// The collector's own watchlist rule; anything else never leaves the web half.
const SYM = /^[A-Z0-9][A-Z0-9.-]{0,9}$/;
const TF = new Set(["1m", "3m", "5m", "10m", "D"]);

const empty = (sym: string): ScanBars => ({
  ok: false,
  sym,
  bars: [],
  ema8: [],
  ema9: [],
  ema10: [],
  vwap: [],
  levels: { pdh: null, pdl: null, pmh: null, pml: null, pm_done: false },
  sessions: [],
  signals: [],
});

export async function GET(req: Request, { params }: { params: Promise<{ sym: string }> }) {
  const sym = (await params).sym.toUpperCase();
  if (!SYM.test(sym)) return NextResponse.json({ ...empty(sym), error: "not a ticker" }, { status: 400 });
  const raw = new URL(req.url).searchParams.get("tf") ?? "10m";
  const tf = TF.has(raw) ? raw : "10m";
  return scanProxy<ScanBars>(`/api/scanner/bars/${encodeURIComponent(sym)}?tf=${tf}`, empty(sym));
}
