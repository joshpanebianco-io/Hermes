import type { ScanEvents } from "@/types/scanner";
import { intParam, scanProxy } from "@/lib/scanProxy";

/**
 * The scanner's event feed — every (L), (E), breakout and near-break the
 * engine has seen, with what each signal did afterwards. Polled on every tab
 * by the alerts, and read whole by the signal log.
 */

export const dynamic = "force-dynamic";
export const revalidate = 0;

export async function GET(req: Request) {
  const u = new URL(req.url);
  // A cursor past any real id answers with `latest` and no events — how a
  // fresh page learns where "new" starts without replaying the day.
  const since = intParam(u.searchParams.get("since"), 0, Number.MAX_SAFE_INTEGER);
  const limit = intParam(u.searchParams.get("limit"), 200, 500);
  return scanProxy<ScanEvents>(`/api/scanner/events?since=${since}&limit=${limit}`, { latest: 0, events: [] });
}
