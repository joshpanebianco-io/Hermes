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
 *
 * EVERY SOURCE MEANS EVERY SOURCE (review, 2026-10-13). The rail named six of
 * the sixteen, so when iShares changed its download URL the Index movers feed
 * died without the rail ever mentioning it — the exact failure this rail
 * exists to make impossible. It now lists whatever the collector reports, in
 * reading order, and stays one line by being compact about health: a healthy
 * source is a dot and its name (the detail is in its hover), and anything
 * down or serving STALE bytes — a cached copy shown because the upstream
 * failed — opens up with its age and its reason, red for down, amber for
 * stale. A dead feed can no longer look like a quiet one.
 */

/** Reading order; anything the collector adds later lands after these. */
const ORDER = [
  "quotes", "wire", "gex", "ranges", "profiles", "sectors", "constituents", "calendar",
  "earnings", "fed", "auctions", "rates", "context", "scanner", "scan_news", "scan_sec",
];

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
  const names = [
    ...ORDER.filter((n) => n in status),
    ...Object.keys(status).filter((n) => !ORDER.includes(n)).sort(),
  ];

  return (
    <footer className="flex flex-wrap items-center gap-x-3 gap-y-1 border-t border-ring bg-surface/40 px-3 py-1.5 qt:gap-x-4 qt:bg-transparent qt:px-6 qt:py-2">
      {names.map((n) => {
        const s = status[n];
        const a = ages[n];
        const stale = s.ok && s.source === "stale";
        const open = !s.ok || stale;
        const label = n.replace(/_/g, " ");
        return (
          <div
            key={n}
            className="flex items-center gap-1.5"
            title={[
              `${label}: ${!s.ok ? "down" : stale ? "serving a stale copy" : "ok"}`,
              s.ok ? `${s.items} items · ${s.source}` : null,
              a !== undefined ? `refreshed ${age(a)} ago` : null,
              s.error,
              ...(s.notes ?? []),
            ]
              .filter(Boolean)
              .join("\n")}
          >
            <span
              className={cn(
                "h-[6px] w-[6px] rounded-full",
                !s.ok ? "bg-err" : stale ? "bg-warn" : "bg-call",
              )}
              aria-hidden
            />
            <span
              className={cn(
                "fig text-[9.5px] tracking-wide uppercase qt:text-[10.5px]",
                !s.ok ? "text-err" : stale ? "text-warn" : "text-ink-3",
              )}
            >
              {label}
            </span>
            {n === "wire" && s.ok && s.notes?.[0] && (
              <span className="fig text-[9.5px] text-ink-3 qt:text-[10.5px]">{s.notes[0]}</span>
            )}
            {open && (
              <>
                <span className={cn("fig text-[9.5px] qt:text-[10.5px]", stale ? "text-warn" : "text-err")}>
                  {stale ? `stale${s.age_min != null ? ` ${age(s.age_min)}` : ""}` : a !== undefined ? age(a) : "never"}
                </span>
                {s.error && (
                  <span
                    className={cn(
                      "fig max-w-[240px] truncate text-[9.5px] qt:text-[10.5px]",
                      stale ? "text-warn" : "text-err",
                    )}
                  >
                    {s.error}
                  </span>
                )}
              </>
            )}
          </div>
        );
      })}

      <div className="ml-auto flex items-center gap-3">
        <span className="fig text-[9px] text-ink-3 qt:text-[10px]">
          poll {pollSec}s
          {lastPoll ? ` · ${lastPoll.toLocaleTimeString("en-US", { hour12: false })}` : ""}
        </span>
        <span className="fig text-[9px] text-ink-3 qt:text-[10px]" title="This terminal is for one desk only. Yahoo quotes and publisher RSS are personal-use; neither may be redistributed.">
          PERSONAL USE
        </span>
      </div>
    </footer>
  );
}
