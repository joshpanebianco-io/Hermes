"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import type { MarketCtx } from "@/types/market";

/**
 * The stocks desk's market context, polled every twenty seconds while the
 * Market tab is mounted — and only then: the terminal's own poll carries the
 * shared panels, so this one exists only for the conviction board.
 *
 * Null until the first answer; a response that lands after a newer one is
 * dropped (the same sequence guard the terminal and scanner polls keep). A
 * fetch that throws keeps the last good context on screen with `failed` set.
 */

const POLL_SEC = 20;

export function useMarket(): { ctx: MarketCtx | null; failed: string | null } {
  const [ctx, setCtx] = useState<MarketCtx | null>(null);
  const [failed, setFailed] = useState<string | null>(null);
  const seq = useRef(0);

  const load = useCallback(async () => {
    const mine = ++seq.current;
    try {
      const r = await fetch("/api/market", { cache: "no-store" });
      const next = (await r.json()) as MarketCtx;
      if (mine !== seq.current) return;
      setCtx(next);
      setFailed(null);
    } catch (e) {
      if (mine === seq.current) setFailed(e instanceof Error ? e.message : "request failed");
    }
  }, []);

  useEffect(() => {
    void load();
    const id = setInterval(load, POLL_SEC * 1000);
    return () => {
      clearInterval(id);
      // Anything still in flight belongs to a tab that has gone.
      seq.current += 1;
    };
  }, [load]);

  return { ctx, failed };
}
