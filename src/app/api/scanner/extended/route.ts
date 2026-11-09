import { scanProxy } from "@/lib/scanProxy";
import { wideParams } from "@/lib/wideParams";

/** One extended session's gappers. Only the named filters leave the web half. */

export const dynamic = "force-dynamic";
export const revalidate = 0;

export async function GET(req: Request) {
  const q = wideParams(req.url, ["session", "cap", "vol", "chip"]);
  return scanProxy(`/api/scanner/extended?${q}`, { ok: false, rows: [], chips: {}, stats: {}, reference: [] });
}
