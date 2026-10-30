"use client";

import { useEffect, useState } from "react";
import type { ScanRow, ScannerPayload } from "@/types/scanner";

/** The index ETFs the stocks desk reads the tape through, in the order the strip shows them. */
export const INDEX_ETFS = ["SPY", "QQQ", "IWM"] as const;

const POLL_SEC = 20;

/**
 * The scanner's own rows for SPY, QQQ and IWM — their levels, what has been
 * taken out, the setup read — polled while the Structure tab is mounted.
 *
 * NOT A SECOND COMPUTATION. The scanner already works these three names out
 * for the tape count and the game plan, on 10-minute bars with the same
 * level rules as every other name; this reads those rows and nothing else,
 * so the Index levels panel and the Scanner agree to the cent.
 */
export function useIndexLevels(): { rows: ScanRow[] | null; failed: string | null } {
  const [rows, setRows] = useState<ScanRow[] | null>(null);
  const [failed, setFailed] = useState<string | null>(null);
  useEffect(() => {
    let live = true;
    const load = async () => {
      try {
        const r = await fetch("/api/scanner", { cache: "no-store" });
        const d = (await r.json()) as ScannerPayload;
        if (!live) return;
        if (d.offline) {
          setFailed(d.offline.reason);
          return;
        }
        const by = new Map(d.rows.map((x) => [x.sym, x]));
        setRows(INDEX_ETFS.map((s) => by.get(s)).filter((x): x is ScanRow => Boolean(x)));
        setFailed(null);
      } catch (e) {
        if (live) setFailed(e instanceof Error ? e.message : "request failed");
      }
    };
    void load();
    const id = setInterval(load, POLL_SEC * 1000);
    return () => {
      live = false;
      clearInterval(id);
    };
  }, []);
  return { rows, failed };
}
