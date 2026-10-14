"use client";

import { cn } from "@/lib/cn";
import { useNow } from "@/lib/useNow";

/**
 * How old the note on the page is — said above it once it matters.
 *
 * WHY (audit, 2026-10-14). The Analysis tab opened on a gold brief written
 * twenty days earlier, GC 4,329 in its levels with GC at 4,183 on the board,
 * and nothing on the page said so; the Game plan showed an 11:04 plan at
 * 22:20 the same way. A note is written against one tape. Past a couple of
 * hours the reader is told to check it against this one; past half a day it
 * is plainly about a session that is gone.
 *
 * The minute clock is null until mounted (see useNow), so the server renders
 * no banner and the browser adds it a frame later — no hydration mismatch.
 */
const CHECK_MIN = 120;
const OLD_MIN = 12 * 60;

export function NoteAge({ createdUtc, what = "note" }: { createdUtc: string | null | undefined; what?: string }) {
  const now = useNow(60_000);
  if (!createdUtc || now === null) return null;
  const t = Date.parse(createdUtc);
  if (Number.isNaN(t)) return null;
  const min = (now - t) / 60000;
  if (min < CHECK_MIN) return null;
  const old = min >= OLD_MIN;
  return (
    <div
      role="note"
      className={cn(
        "border-b px-3 py-1.5 text-[11px] qt:px-5",
        old ? "border-err/40 bg-err/10 text-err" : "border-warn/40 bg-warn/10 text-warn",
      )}
    >
      <strong className="font-semibold">Written {span(min)} ago.</strong>{" "}
      {old
        ? `This ${what} describes a session that has passed — its levels and prices are not today's. Generate a fresh one before acting on it.`
        : `Prices have moved since — check its levels against the live tape, or generate a fresh one.`}
    </div>
  );
}

/** "3h", "20 days" — how long, in the unit a reader thinks in. */
function span(min: number): string {
  if (min < 60 * 36) return `${Math.round(min / 60)}h`;
  const d = Math.round(min / 1440);
  return `${d} day${d === 1 ? "" : "s"}`;
}
