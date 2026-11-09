import { NextResponse } from "next/server";
import type { NamePayload } from "@/types/scanner";
import { scanProxy } from "@/lib/scanProxy";

/** One name's whole row, tracked or not: what the slide-out reads. */

export const dynamic = "force-dynamic";
export const revalidate = 0;

const SYM = /^[A-Z0-9][A-Z0-9.-]{0,9}$/;

const empty = (sym: string, error: string | null): NamePayload => ({
  ok: false,
  sym,
  row: null,
  error,
  tracked: false,
  pinned: false,
  session: null,
  trading_day: null,
  stage: null,
});

export async function GET(_req: Request, { params }: { params: Promise<{ sym: string }> }) {
  const sym = (await params).sym.toUpperCase();
  if (!SYM.test(sym)) return NextResponse.json(empty(sym, "not a ticker"), { status: 400 });
  return scanProxy<NamePayload>(`/api/scanner/name/${encodeURIComponent(sym)}`, empty(sym, null));
}
