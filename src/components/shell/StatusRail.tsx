"use client";

import type { SourceStatus } from "@/types/terminal";
import { age } from "@/lib/format";
import { cn } from "@/lib/cn";

/**
 * The status rail — where a terminal puts its state.
 *
 * EVERY SOURCE, ALWAYS VISIBLE, WHETHER OR NOT IT IS HEALTHY. The temptation
 * is to show only the failures and keep the rail quiet; the problem is that an
 * empty rail then means both "everything is fine" and "the status block itself
 * is broken". A row per source, green when it is fine, is the only version
 * where absence of an alarm is evidence rather than an assumption.
 *
 * The wire's row carries its own sub-count — 28 feeds behind one name — so a
 * tape running on nineteen of twenty-eight publishers says so rather than
 * looking identical to a healthy one.
 */
export function StatusRail({
  status,
  ages,
  pollSec,
  lastPoll,
}: {
  status: Record<string, SourceStatus>;
  ages: Record<string, number>;
  pollSec: number;
  lastPoll: Date | null;
}) {
  const names = ["quotes", "wire", "gex", "sectors", "calendar", "rates"];

  return (
    <footer className="flex flex-wrap items-center gap-x-3 gap-y-1 border-t border-ring bg-surface/40 px-3 py-1.5 qt:gap-x-5 qt:bg-transparent qt:px-6 qt:py-2">
      {names.map((n) => {
        const s = status[n];
        const a = ages[n];
        return (
          <div
            key={n}
            className="flex items-center gap-1.5"
            title={
              s
                ? [s.error, ...(s.notes ?? [])].filter(Boolean).join(" · ") ||
                  `${s.items} items, ${s.source}`
                : "not reported yet"
            }
          >
            <span
              className={cn(
                "h-[6px] w-[6px] rounded-full",
                !s ? "bg-ink-4/40" : s.ok ? "bg-call" : "bg-err",
              )}
              aria-hidden
            />
            <span className="fig text-[9.5px] tracking-wide text-ink-4 uppercase qt:text-[10.5px]">{n}</span>
            {s?.ok && (
              <span className="fig text-[9.5px] text-ink-3 qt:text-[10.5px]">
                {s.items}
                {n === "wire" && s.notes?.[0] ? ` · ${s.notes[0]}` : ""}
              </span>
            )}
            {a !== undefined && <span className="fig text-[9px] text-ink-4 qt:text-[10px]">{age(a)}</span>}
            {s && !s.ok && s.error && (
              <span className="fig max-w-[220px] truncate text-[9.5px] text-err">{s.error}</span>
            )}
          </div>
        );
      })}

      <div className="ml-auto flex items-center gap-3">
        <span className="fig text-[9px] text-ink-4">
          poll {pollSec}s
          {lastPoll ? ` · ${lastPoll.toLocaleTimeString("en-US", { hour12: false })}` : ""}
        </span>
        <span className="fig text-[9px] text-ink-4" title="This terminal is for one desk only. Yahoo quotes and publisher RSS are personal-use; neither may be redistributed.">
          PERSONAL USE
        </span>
      </div>
    </footer>
  );
}
