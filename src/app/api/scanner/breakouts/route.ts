import { scanProxy } from "@/lib/scanProxy";
import { wideParams } from "@/lib/wideParams";

/** The wide scan against the levels. Only the named filters leave the web half. */

export const dynamic = "force-dynamic";
export const revalidate = 0;

export async function GET(req: Request) {
  const q = wideParams(req.url, ["chip", "cap", "vol", "rvol", "sector", "theme", "industry", "sort", "listing"]);
  return scanProxy(`/api/scanner/breakouts?${q}`, { ok: false, rows: [], chips: {}, stats: {} });
}
