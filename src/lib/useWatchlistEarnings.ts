"use client";

import { useEffect, useState } from "react";
import type { EarningsRow } from "@/types/terminal";
import type { ScannerPayload } from "@/types/scanner";

const NONE: never[] = [];
const NO_WATCH: ReadonlySet<string> = new Set();
const WATCH_POLL_SEC = 60;

/**
 * The scanner's watchlist, and the earnings its names carry — the smaller
 * names' reports are not in the terminal's earnings block, which is about what
 * moves an index. Polled once a minute while the Macro tab is mounted; a dead
 * collector simply leaves the last answer (or nothing) in place.
 *
 * It lived in the stocks desk's Market tab; with one Macro tab for both desks
 * (lib/tabs.ts) the earnings panel there marks the watchlist for everyone.
 */
export function useWatchlistEarnings(): { watch: ReadonlySet<string>; extra: EarningsRow[] } {
  const [state, setState] = useState<{ watch: ReadonlySet<string>; extra: EarningsRow[] }>({
    watch: NO_WATCH,
    extra: NONE,
  });
  useEffect(() => {
    let live = true;
    const load = async () => {
      try {
        const r = await fetch("/api/scanner", { cache: "no-store" });
        const d = (await r.json()) as ScannerPayload;
        if (!live || d.offline) return;
        const extra: EarningsRow[] = d.rows
          .filter((x) => x.ok && x.earnings)
          .map((x) => ({
            symbol: x.sym,
            name: x.name ?? x.sym,
            date: x.earnings!.date,
            when: x.earnings!.when,
            eps_forecast: x.earnings!.eps_forecast,
            eps_actual: x.earnings!.eps_actual,
            surprise_pct: x.earnings!.surprise_pct,
            market_cap: null,
            bellwether: false,
          }));
        setState({ watch: new Set(d.watchlist), extra });
      } catch {
        /* keep what we have */
      }
    };
    void load();
    const id = setInterval(load, WATCH_POLL_SEC * 1000);
    return () => {
      live = false;
      clearInterval(id);
    };
  }, []);
  return state;
}
