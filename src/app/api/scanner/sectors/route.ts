import { scanProxy } from "@/lib/scanProxy";

/** The Sectors view: the sector and theme ETFs with what their stocks did, and the industries. */

export const dynamic = "force-dynamic";
export const revalidate = 0;

export async function GET() {
  return scanProxy("/api/scanner/sectors", { ok: false, cards: [], industries: [] });
}
