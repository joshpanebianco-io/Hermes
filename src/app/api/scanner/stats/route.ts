import type { ScanStats } from "@/types/scanner";
import { intParam, scanProxy } from "@/lib/scanProxy";

/** How the logged signals have done — win rate to +1R and average R, by group. */

export const dynamic = "force-dynamic";
export const revalidate = 0;

export async function GET(req: Request) {
  const days = intParam(new URL(req.url).searchParams.get("days"), 20, 30);
  return scanProxy<ScanStats>(`/api/scanner/stats?days=${days}`, {
    days,
    from: "",
    to: "",
    total: 0,
    groups: [],
  });
}
