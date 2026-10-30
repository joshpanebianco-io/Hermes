"use client";

import { DESKS, type Desk } from "@/lib/tabs";
import { segItem } from "@/lib/seg";

/**
 * The desk switch — Futures or Stocks & options — as a bar above a tab's
 * content. One remembered choice, shown on the tabs where the two desks'
 * reads differ: Analysis, where the note is a different document per desk,
 * and Structure (owner, 2026-10-30: "we should have the toggle for
 * structure"), where each desk's positioning panels want the whole page.
 * `D` flips it from anywhere.
 */
export function DeskSwitch({ desk, onDesk, sub }: { desk: Desk; onDesk: (d: Desk) => void; sub: Record<Desk, string> }) {
  return (
    <div className="flex shrink-0 flex-wrap items-center gap-x-3 gap-y-1 border-b border-ring px-3 py-1.5 qt:px-6">
      <span className="seg shrink-0" role="tablist" aria-label="Desk" title="Which desk's read — or press D">
        {DESKS.map((d) => (
          <button
            key={d.key}
            type="button"
            role="tab"
            aria-selected={desk === d.key}
            onClick={() => onDesk(d.key)}
            {...segItem(desk === d.key, { className: "text-[10px] tracking-[0.08em] uppercase qt:text-[12px]" })}
          >
            {d.label}
          </button>
        ))}
      </span>
      <span className="min-w-0 text-[11px] text-ink-3 qt:text-[12px]">{sub[desk]}</span>
    </div>
  );
}
