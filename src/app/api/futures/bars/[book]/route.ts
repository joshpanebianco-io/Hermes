import { NextResponse } from "next/server";
import type { ScanBars } from "@/types/scanner";
import { scanProxy } from "@/lib/scanProxy";

/** One futures book's chart on `?tf=`: the contract's bars, its averages, VWAP from each reopen, and the ladder's levels. */

export const dynamic = "force-dynamic";
export const revalidate = 0;

const BOOKS = new Set(["NQ", "ES", "GC", "SIL", "CL"]);
const TF = new Set(["1m", "3m", "5m", "10m", "30m", "60m", "D"]);

const empty = (book: string): ScanBars => ({
  ok: false,
  sym: book,
  bars: [],
  ema8: [],
  ema9: [],
  ema10: [],
  vwap: [],
  levels: { pdh: null, pdl: null, pmh: null, pml: null, pm_done: false },
  sessions: [],
  signals: [],
});

export async function GET(req: Request, { params }: { params: Promise<{ book: string }> }) {
  const book = (await params).book.toUpperCase();
  if (!BOOKS.has(book)) return NextResponse.json({ ...empty(book), error: "not a futures book" }, { status: 400 });
  const raw = new URL(req.url).searchParams.get("tf") ?? "10m";
  const tf = TF.has(raw) ? raw : "10m";
  return scanProxy<ScanBars>(`/api/futures/bars/${book}?tf=${tf}`, empty(book));
}
