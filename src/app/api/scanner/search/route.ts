import type { SearchHit } from "@/types/scanner";
import { scanProxy } from "@/lib/scanProxy";

/** Tickers and company names across the wide read, for the search box. */

export const dynamic = "force-dynamic";
export const revalidate = 0;

export async function GET(req: Request) {
  const q = (new URL(req.url).searchParams.get("q") ?? "").slice(0, 40);
  return scanProxy<{ results: SearchHit[] }>(`/api/scanner/search?q=${encodeURIComponent(q)}`, { results: [] });
}
