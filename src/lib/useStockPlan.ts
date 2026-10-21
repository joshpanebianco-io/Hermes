"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import type { PlanFeed, PlanTop } from "@/types/plan";
import { usePersisted } from "./usePersisted";

/**
 * The Game plan tab's state, owned above the tab switch — `useReport`'s
 * arrangement, for the same reasons (see that file): a generation outlives the
 * panel, so leaving the tab while a plan is being written does not abandon
 * it; `seq` lets only the newest generation land and `openSeq` only the newest
 * reopen; and an offline answer is folded into what the page already holds
 * rather than wiping the plan and the history under a "no key" screen.
 */

function land(prev: PlanFeed | null, next: PlanFeed): PlanFeed {
  if (!next.offline || !prev) return next;
  return { ...prev, offline: next.offline };
}

const isTop = (v: unknown): v is PlanTop => v === 4 || v === 6 || v === 8 || v === 10;

export interface PlanController {
  top: PlanTop;
  setTop: (v: PlanTop) => void;
  feed: PlanFeed | null;
  busy: boolean;
  viewing: string | null;
  generate: () => void;
  open: (id: string) => void;
  discard: (id: string) => void;
  discardMany: (ids: string[]) => void;
  discardAll: () => void;
  retry: () => void;
  startedAt: number | null;
}

export function useStockPlan(initial: PlanFeed | null = null): PlanController {
  const [feed, setFeed] = useState<PlanFeed | null>(initial);
  const [busy, setBusy] = useState(false);
  const [startedAt, setStartedAt] = useState<number | null>(null);
  const [viewing, setViewing] = useState<string | null>(null);
  const [top, setTop] = usePersisted<PlanTop>("plan.top", 6, isTop);
  const seq = useRef(0);
  const openSeq = useRef(0);

  const refresh = useCallback(async () => {
    try {
      const r = await fetch("/api/plan", { cache: "no-store" });
      const next = (await r.json()) as PlanFeed;
      setFeed((prev) => land(prev, next));
    } catch {
      /* the route handler returns an offline body rather than throwing */
    }
  }, []);

  useEffect(() => {
    if (!initial) void refresh();
  }, [initial, refresh]);

  const generate = useCallback(() => {
    setBusy(true);
    setStartedAt(Date.now());
    setViewing(null);
    const mine = ++seq.current;
    void (async () => {
      try {
        const r = await fetch(`/api/plan?top=${top}`, { method: "POST", cache: "no-store" });
        const next = (await r.json()) as PlanFeed;
        if (mine === seq.current) {
          setFeed((prev) => land(prev, next));
          if (!next.offline) {
            setViewing(null);
            openSeq.current += 1;
          }
        }
      } catch {
        /* same */
      } finally {
        if (mine === seq.current) {
          setBusy(false);
          setStartedAt(null);
        }
      }
    })();
  }, [top]);

  const open = useCallback((id: string) => {
    setViewing(id);
    const mine = ++openSeq.current;
    void (async () => {
      try {
        const r = await fetch(`/api/plan/${encodeURIComponent(id)}`, { cache: "no-store" });
        const next = (await r.json()) as PlanFeed;
        if (mine !== openSeq.current) return;
        setFeed((f) => (next.offline ? land(f, next) : f ? { ...f, latest: next.latest, offline: undefined } : next));
      } catch {
        /* same */
      }
    })();
  }, []);

  const discard = useCallback((id: string) => {
    void (async () => {
      try {
        const r = await fetch(`/api/plan/${encodeURIComponent(id)}`, { method: "DELETE", cache: "no-store" });
        const next = (await r.json()) as PlanFeed;
        if (next.offline) {
          setFeed((prev) => land(prev, next));
          return;
        }
        setViewing((v) => (v === id ? null : v));
        setFeed(next);
      } catch {
        /* same */
      }
    })();
  }, []);


  /*
   * SEVERAL AT ONCE, OR ALL — one DELETE on the collection, not one per row.
   * A loop of single deletes lands N feeds in whatever order the network
   * chooses and the list flickers through states nobody asked for; the
   * collector does the lot and hands back one list. `viewing` clears when
   * the plan being read is among those gone — with "all" it always is.
   */
  const discardSet = useCallback((qs: string, gone: (id: string) => boolean) => {
    void (async () => {
      try {
        const r = await fetch(`/api/plan?${qs}`, { method: "DELETE", cache: "no-store" });
        const next = (await r.json()) as PlanFeed;
        if (next.offline) {
          setFeed((prev) => land(prev, next));
          return;
        }
        setViewing((v) => (v !== null && gone(v) ? null : v));
        setFeed(next);
      } catch {
        /* same */
      }
    })();
  }, []);
  const discardMany = useCallback(
    (ids: string[]) =>
      discardSet(ids.map((id) => `ids=${encodeURIComponent(id)}`).join("&"), (v) => ids.includes(v)),
    [discardSet],
  );
  const discardAll = useCallback(() => discardSet("all=1", () => true), [discardSet]);

  const retry = useCallback(() => void refresh(), [refresh]);

  return { top, setTop, feed, busy, viewing, generate, open, discard, discardMany, discardAll, retry, startedAt };
}
