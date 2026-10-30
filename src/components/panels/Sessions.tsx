"use client";

import type { Clock } from "@/types/terminal";
import { Module } from "@/components/ui/Module";
import { inMin } from "@/lib/format";
import { localClock, localWindow, readerZone } from "@/lib/clock";
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
 *
 * THE ROWS ARE THE FOUR BOXES (owner, 2026-10-30: "make the sessions section
 * accordingly" — the session ranges' Asia, London, pre-market and New York).
 * They were seven cities with local times; the boxes are what the desk
 * actually trades by, and the ranges panel beside this one draws the same
 * four, so the two read as one thing. Each row carries its ET window, the
 * same window on the reader's own clock (the owner trades New York from
 * Australia, and "20:00 ET" is a sum they should not have to do), and how
 * long until it opens or closes. The cities stay in the data for the header's
 * New York countdown and for Hermes.
 */
export function Sessions({ clock: rawClock }: { clock: Clock }) {
  // Its own second hand: the countdowns move every second, the shell does not.
  const now = useNow(1000);
  const clock = localClock(rawClock, now) ?? rawClock;
  const next = clock.markers?.[0];
  const zone = readerZone(now);

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

      {/* ---- the boxes --------------------------------------------------- */}
      <ul className="@container py-0.5">
        {(clock.boxes ?? []).map((b) => (
          <li
            key={b.key}
            className="hit flex items-center gap-2 px-3 py-[3px]"
            title={`${b.label} · ${b.start_et}–${b.end_et} ET${zone ? ` · ${localWindow(b.opens_utc, b.closes_utc, zone.tz)} ${zone.zone}` : ""} · ${
              b.open ? `open, closes in ${inMin(b.next_min)}` : `opens in ${inMin(b.next_min)}`
            }`}
          >
            <span
              className={cn("h-[6px] w-[6px] shrink-0 rounded-full", b.open ? "bg-call live-dot" : "bg-ink-4/50")}
              aria-hidden
            />
            <span className={cn("w-[74px] shrink-0 text-[11px]", b.open ? "text-ink" : "text-ink-3")}>{b.label}</span>
            <span className="fig shrink-0 text-[10px] text-ink-3">
              {b.start_et}–{b.end_et} <span className="eyebrow text-[8px]">ET</span>
            </span>
            {/* The reader's own clock, when it is not New York's — hidden in a
                column too narrow to carry it, where the hover still has it. */}
            <span className="fig hidden min-w-0 flex-1 truncate text-[10px] text-ink-4 @min-[340px]:block">
              {zone ? `${localWindow(b.opens_utc, b.closes_utc, zone.tz)} ${zone.zone}` : ""}
            </span>
            <span className="flex-1 @min-[340px]:hidden" />
            <span className={cn("fig shrink-0 text-right text-[10px]", b.open ? "text-ink-3" : "text-ink-4")}>
              {b.next === "opens" ? "in" : "for"} {inMin(b.next_min)}
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
