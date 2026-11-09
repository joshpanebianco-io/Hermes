import { useMemo } from "react";
import { nextEvent } from "@/lib/events";
import { groupReleases } from "@/lib/releases";
import type { CalendarRow } from "@/types/terminal";

/** "Wed " when the event falls on another New York day than now, else nothing. */
export function etDay(ts: number, now: number): string {
  const day = (ms: number) => new Date(ms).toLocaleDateString("en-US", { timeZone: "America/New_York", weekday: "short" });
  const d = day(ts * 1000);
  return d === day(now) ? "" : `${d} `;
}

/**
 * The next US print scored 4+, however far off: what a page shows when none falls
 * inside the six hours the engine prices in. By release, so 08:30 reads "Core CPI
 * m/m", CPI's lead series, rather than whichever of its seven rows the feed listed
 * first (lib/releases).
 */
export function useNextPrint(calendar: CalendarRow[], now: number | null): CalendarRow | null {
  const leads = useMemo(
    () =>
      groupReleases(calendar, (r) => ({
        event: r.event,
        when: r.ts,
        country: r.country,
        score: r.score,
        figures: [r.actual_raw, r.consensus_raw, r.previous_raw],
      })).map((x) => x.lead),
    [calendar],
  );
  return useMemo(
    () => (now === null ? null : nextEvent(leads, now / 1000, (r) => r.region === "us" && r.score >= 4)),
    [leads, now],
  );
}
