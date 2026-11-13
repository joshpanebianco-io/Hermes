import { scanProxy } from "@/lib/scanProxy";

/** The Stocks tab's Today list: the phase it is, and the names ranked for it. */

export const dynamic = "force-dynamic";
export const revalidate = 0;

export async function GET() {
  return scanProxy("/api/scanner/today", { ok: false, phase: null, phases: [], rows: [], note: null, favs_tracked: null });
}
