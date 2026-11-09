import { scanProxy } from "@/lib/scanProxy";

/** The Dashboard tab, whole. */

export const dynamic = "force-dynamic";
export const revalidate = 0;

export async function GET() {
  return scanProxy("/api/dashboard", { ok: false, top: [], list: [], adds: [], stories: [], rotation: [] });
}
