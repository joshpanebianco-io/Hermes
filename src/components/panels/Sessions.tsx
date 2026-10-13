"use client";

import type { Clock } from "@/types/terminal";
import { Module } from "@/components/ui/Module";
import { inMin } from "@/lib/format";
import { localClock } from "@/lib/clock";
import { useNow } from "@/lib/useNow";
import { cn } from "@/lib/cn";

/**
 * The session clock — who is trading, and what happens next.
 *
 * WHY THIS PANEL EXISTS AT ALL. Every number on the board means something
 * different depending on who is awake to trade it. A forty-handle move in ES
 * at 03:00 ET is London repricing the overnight; the same move at 09:31 is the
 * New York open and is worth ten times the attention. Without this the board
 * flatters the quietest hours of the day.
 *
 * THE OVERLAP GETS ITS OWN LINE. London and New York open together from 08:00
 * to 11:30 ET, both of the two deepest pools at once, and that is where the
 * day's range is usually set. It is not derivable at a glance from two rows of
 * open/closed, so it is stated.
 */
export function Sessions({ clock: rawClock }: { clock: Clock }) {
  // Its own second hand: the countdowns move every second, the shell does not.
  const now = useNow(1000);
  const clock = localClock(rawClock, now) ?? rawClock;
  const next = clock.markers?.[0];

  return (
    <Module title="Sessions" sub={clock.et_date} bodyClassName="px-0 py-0">
      {/* ---- the phase, in one line ------------------------------------- */}
      <div className="border-b border-ring/40 px-3 py-2">
        <div className="flex items-baseline gap-2">
          <span className="fig text-[16px] text-ink">{clock.et_time}</span>
          <span className="eyebrow text-[9px]">ET</span>
          {clock.overlap && (
            <span
              className="fig qt-pill ml-auto rounded bg-flip/15 px-1.5 py-px text-[9.5px] text-flip [--pill-hue:var(--flip-fig)]"
              title="London and New York both open — the deepest liquidity of the day"
            >
              OVERLAP
            </span>
          )}
        </div>
        <div className="mt-0.5 text-[11px] text-ink-2">{clock.phase.label}</div>
        <div className="text-[10px] text-ink-3">{clock.phase.note}</div>
      </div>

      {/* ---- the cities -------------------------------------------------- */}
      <ul className="py-0.5">
        {clock.sessions.map((s) => (
          <li key={s.key} className="hit flex items-center gap-2 px-3 py-[3px]">
            <span
              className={cn(
                "h-[6px] w-[6px] shrink-0 rounded-full",
                s.open ? "bg-call live-dot" : "bg-ink-4/50",
              )}
              aria-hidden
            />
            <span
              className={cn(
                "w-[74px] shrink-0 text-[11px]",
                s.open ? "text-ink" : "text-ink-3",
              )}
            >
              {s.label}
            </span>
            <span className="fig w-[42px] shrink-0 text-[10.5px] text-ink-3">{s.local_time}</span>
            <span className="flex-1 truncate text-[9.5px] text-ink-3">{s.hours}</span>
            <span
              className={cn(
                "fig shrink-0 text-right text-[10px]",
                s.open ? "text-ink-3" : "text-ink-4",
              )}
            >
              {s.weekend ? "weekend" : `${s.next === "opens" ? "in" : "for"} ${inMin(s.next_min)}`}
            </span>
          </li>
        ))}
      </ul>

      {/* ---- what happens next ------------------------------------------ */}
      {next && (
        <div className="border-t border-ring/40 px-3 py-1.5">
          <div className="flex items-baseline gap-2">
            <span className="eyebrow text-[9px]">Next</span>
            <span className="text-[11px] text-ink">{next.label}</span>
            <span className="fig ml-auto text-[10.5px] text-flip">{inMin(next.in_min)}</span>
          </div>
          <div className="text-[9.5px] text-ink-3">{next.note}</div>
        </div>
      )}
    </Module>
  );
}
