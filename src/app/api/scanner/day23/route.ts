import { scanProxy } from "@/lib/scanProxy";
import { wideParams } from "@/lib/wideParams";

/** The Day 1 / 2 / 3 ledger read against now. Only the named filters leave the web half. */

export const dynamic = "force-dynamic";
export const revalidate = 0;

export async function GET(req: Request) {
  const q = wideParams(req.url, ["move", "cap", "chip"]);
  return scanProxy(`/api/scanner/day23?${q}`, { ok: false, rows: [], chips: {} });
}
