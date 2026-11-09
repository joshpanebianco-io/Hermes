import { NextResponse } from "next/server";
import type { TickPayload } from "@/types/scanner";
import { scanProxy } from "@/lib/scanProxy";

/** The last trade and this minute's candle: what an open chart polls every second. */

export const dynamic = "force-dynamic";
export const revalidate = 0;

const SYM = /^[A-Z0-9][A-Z0-9.-]{0,9}$/;

export async function GET(_req: Request, { params }: { params: Promise<{ sym: string }> }) {
  const sym = (await params).sym.toUpperCase();
  if (!SYM.test(sym)) return NextResponse.json({ ok: false, sym } satisfies TickPayload, { status: 400 });
  return scanProxy<TickPayload>(`/api/scanner/tick/${encodeURIComponent(sym)}`, { ok: false, sym });
}
