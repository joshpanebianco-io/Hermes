"use client";

import { ago } from "@/lib/format";
import { useNow } from "@/lib/useNow";

/**
 * "14m" — a headline's age, ticking on its own.
 *
 * The age is the only thing on a wire row that changes with the clock, so it
 * is the only thing that subscribes to it: a tick re-renders these spans, not
 * the list of 150 rows they sit in. Thirty seconds, because the label moves in
 * whole minutes. Empty until mounted, like `ago` itself.
 */
export function Ago({ utc, className }: { utc: string | null | undefined; className?: string }) {
  const now = useNow(30_000);
  return <span className={className}>{ago(utc, now)}</span>;
}
