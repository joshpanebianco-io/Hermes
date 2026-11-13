import { NextResponse } from "next/server";
import type { TickPayload } from "@/types/scanner";
import { scanProxy } from "@/lib/scanProxy";

/**
 * A futures chart's live last candle, polled every second: the tracking ETF's last trade
 * in the future's prices (server futfill.py), since CME's own bars run ten minutes behind.
 */

export const dynamic = "force-dynamic";
export const revalidate = 0;

const BOOKS = new Set(["NQ", "ES", "GC", "SIL", "CL"]);

export async function GET(_req: Request, { params }: { params: Promise<{ book: string }> }) {
  const book = (await params).book.toUpperCase();
  if (!BOOKS.has(book)) return NextResponse.json({ ok: false, sym: book } satisfies TickPayload, { status: 400 });
  return scanProxy<TickPayload>(`/api/futures/tick/${book}`, { ok: false, sym: book });
}
