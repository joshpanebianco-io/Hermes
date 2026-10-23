"use client";

import type { CalendarRow } from "@/types/terminal";
import { Popover } from "@/components/ui/Popover";
import { cn } from "@/lib/cn";

/**
 * A print's click-through on the futures Calendar: the figures, the read —
 * hot, cold or in line — and what that means for NQ, ES and GC.
 *
 * THE CALENDAR STILL COLOURS BY MAGNITUDE AND NEVER GREEN-FOR-GOOD; that rule
 * holds. What was missing (owner, 2026-10-22) was the second step: the
 * stocks desk read every print hot or cold since October and the futures
 * desk never showed it, nor what a hot print does per book. The read and
 * the sentences are the collector's (releases.read_of, releases.implication)
 * so the Calendar, the Macro tab and the driver board say the same thing.
 */

const BOOKS = ["NQ", "ES", "GC"] as const;

export const READ_WORD: Record<NonNullable<CalendarRow["read"]>, string> = {
  hot: "hot",
  cold: "cold",
  inline: "in line",
};

/** A surprise is amber whichever way it went — the calendar's own rule. */
export const readTone = (r: CalendarRow["read"]) => (r === "hot" || r === "cold" ? "text-flip-fig" : "text-ink-3");

export function PrintPopover({
  r,
  className,
  children,
}: {
  r: CalendarRow;
  className?: string;
  children: React.ReactNode;
}) {
  return (
    <Popover
      label={`What ${r.event} means`}
      title="Click for what this print means for each book"
      className={className}
      panel={<PrintRead r={r} />}
    >
      {children}
    </Popover>
  );
}

function PrintRead({ r }: { r: CalendarRow }) {
  const read = r.read ?? null;
  return (
    <div className="w-[min(520px,calc(100vw-24px))] px-4 py-3 text-ink">
      <div className="flex flex-wrap items-baseline gap-x-2 gap-y-1">
        <span className="qt-cap text-[10.5px] text-ink-3">What the print means</span>
        <span className="text-[14px] font-semibold text-ink">{r.event}</span>
        <span className="fig text-[11px] text-ink-3">
          {r.country}
          {r.et ? ` · ${r.et} ET` : ""}
        </span>
      </div>
      <p className="fig mt-1.5 text-[12px] text-ink-2">
        act <span className={cn(readTone(read))}>{r.actual_raw ?? "—"}</span> · cons{" "}
        <span className="text-ink">{r.consensus_raw ?? "—"}</span> · prev <span className="text-ink">{r.previous_raw ?? "—"}</span>
        {read && (
          <span className={cn("qt-cap ml-2 text-[10.5px]", readTone(read))}>{READ_WORD[read]}</span>
        )}
      </p>

      {r.meaning ? (
        <dl className="mt-2.5 grid grid-cols-[34px_minmax(0,1fr)] gap-x-3 gap-y-2 text-[11.5px] leading-[1.5]">
          {BOOKS.map((b) => (
            <div key={b} className="contents">
              <dt className="fig text-[12px] text-ink">{b}</dt>
              <dd className="text-ink-2">{r.meaning![b]}</dd>
            </div>
          ))}
        </dl>
      ) : (
        <p className="mt-2.5 text-[11.5px] leading-[1.5] text-ink-2">
          {read
            ? "A decision's surprise has no sign to read: the statement, the path priced after it and the press conference decide."
            : "Not printed yet, or no consensus to read it against."}
        </p>
      )}

      <p className="mt-2.5 border-t border-ring pt-2 text-[11px] leading-[1.45] text-ink-3">
        Hot is the stronger economy: a beat on inflation, jobs or growth, a miss on unemployment, claims or
        inventories. In line is within half a percent of consensus. The first reaction is through yields, which
        is why every line names the 10Y; the driver board counts the inflation reads and names the rest.
      </p>
    </div>
  );
}
