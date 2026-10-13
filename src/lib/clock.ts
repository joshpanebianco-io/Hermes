import type { Clock } from "@/types/terminal";

/**
 * The payload's clock, advanced locally between polls.
 *
 * THE CLOCK TICKS LOCALLY. Polling at twenty seconds would give a session
 * countdown that jumps in twenty-second steps, which looks broken. The payload
 * carries the collector's ET instant; this advances it to the reader's `now`
 * and the next poll corrects any drift. Called by the components that print it
 * (the header, the session table), each on its own one-second tick — see
 * `useNow`.
 *
 * `now === null` means "first render, before mount" and returns the collector's
 * own clock untouched, so server and client hydrate the same string.
 *
 * Only the displayed time and the countdowns move; open/closed and the phase
 * stay as the collector computed them, because recomputing a session boundary
 * in the browser would need the whole zone table and would be a second
 * implementation that could disagree with the first.
 */
export function localClock(clock: Clock | null | undefined, now: number | null): Clock | null {
  if (!clock) return null;
  const base = Date.parse(clock.et);
  if (now === null || Number.isNaN(base)) return clock;

  const elapsedMin = (now - base) / 60000;
  return {
    ...clock,
    et_time: new Date(now).toLocaleTimeString("en-US", {
      hour12: false,
      timeZone: "America/New_York",
    }),
    sessions: clock.sessions.map((s) => ({
      ...s,
      next_min: Math.max(0, s.next_min - elapsedMin),
    })),
    markers: clock.markers.map((m) => ({
      ...m,
      in_min: Math.max(0, m.in_min - elapsedMin),
    })),
  };
}

/**
 * The reader's own wall clock and zone, for the header — the owner trades New
 * York from Australia, and "09:30 ET" is a sum they should not have to do at
 * midnight. Null when the reader IS on New York time (it would repeat the ET
 * clock beside itself) and before mount.
 *
 * en-AU names Australian zones the way they are said there ("AEDT"); any other
 * zone gets its locale's short name ("BST", "GMT+1").
 */
export function readerClock(now: number | null): { time: string; zone: string } | null {
  if (now === null) return null;
  let tz: string;
  try {
    tz = Intl.DateTimeFormat().resolvedOptions().timeZone;
  } catch {
    return null;
  }
  if (!tz || tz === "America/New_York") return null;
  const d = new Date(now);
  const locale = tz.startsWith("Australia/") ? "en-AU" : undefined;
  const time = d.toLocaleTimeString("en-GB", { hour: "2-digit", minute: "2-digit", hour12: false, timeZone: tz });
  const zone =
    new Intl.DateTimeFormat(locale, { timeZone: tz, timeZoneName: "short" })
      .formatToParts(d)
      .find((p) => p.type === "timeZoneName")?.value ?? tz;
  return { time, zone };
}
