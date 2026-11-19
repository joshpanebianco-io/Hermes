"use client";

import type { BreadthAll } from "@/types/terminal";

/**
 * Breadth across the whole market — how many stocks moved, and by how much.
 *
 * The index can be flat with half its members down 5% and the other half up 5%, and
 * a sector table cannot show that. This counts every US stock at $2bn+ off the wide
 * read (sources/universe.py), so it is fifteen minutes behind: a picture of the day,
 * not a trigger.
 *
 * The bars and the count each way, drawn in the Dashboard's Breadth card. Macro had a
 * panel of the same bars until 2026-11-13, when the page lost its two duplicates
 * (MacroBoard.tsx).
 */
export function BreadthBars({
  data,
  barHeight = 92,
}: {
  data: Pick<BreadthAll, "buckets" | "advancers" | "decliners">;
  /** The bars' area, their counts above them included (the Dashboard's card fills its row). */
  barHeight?: number;
}) {
  const max = Math.max(1, ...data.buckets.map((b) => b.n));
  const total = Math.max(1, data.advancers + data.decliners);
  // The tallest bar is the area less its count's line.
  const tall = Math.max(20, barHeight - 24);
  return (
    <>
      <div className="grid grid-cols-8 items-end gap-1.5" style={{ height: barHeight }}>
        {data.buckets.map((b) => (
          <div key={b.label} className="flex h-full flex-col justify-end text-center" title={`${b.n} names`}>
            <span className="fig text-[10px] text-ink-3">{b.n}</span>
            <span
              className="mt-0.5 block rounded-[1px]"
              style={{ height: `${Math.max(2, (b.n / max) * tall)}px`, background: b.side === "up" ? "var(--call)" : "var(--put)", opacity: 0.85 }}
            />
          </div>
        ))}
      </div>
      <div className="mt-1 grid grid-cols-8 gap-1.5">
        {data.buckets.map((b) => (
          <span key={b.label} className="fig text-center text-[9.5px] text-ink-3">
            {b.label}
          </span>
        ))}
      </div>
      <div className="mt-2 flex h-[4px] gap-px" aria-hidden>
        <span className="h-full" style={{ width: `${(data.decliners / total) * 100}%`, background: "var(--put)" }} />
        <span className="h-full" style={{ width: `${(data.advancers / total) * 100}%`, background: "var(--call)" }} />
      </div>
      <p className="fig mt-1.5 flex justify-between text-[11px]">
        <span className="down">{data.decliners.toLocaleString()} decliners</span>
        <span className="up">{data.advancers.toLocaleString()} advancers</span>
      </p>
    </>
  );
}
