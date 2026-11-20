import { cn } from "@/lib/cn";
import type { RefreshPhase } from "@/lib/refresh";

/**
 * The refresh button's icon through a press (lib/refresh useRefreshPress): the arrows at
 * rest, spinning while the read is in flight, a green tick for a moment once it has landed.
 */
export function RefreshGlyph({ phase, size = 15 }: { phase: RefreshPhase; size?: number }) {
  if (phase === "done") {
    return (
      <svg aria-hidden width={size} height={size} viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.4" strokeLinecap="round" strokeLinejoin="round" className="refresh-done text-call">
        <path d="M5 12.5l4.5 4.5L19 7.5" />
      </svg>
    );
  }
  return (
    <svg aria-hidden width={size} height={size} viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" className={cn(phase === "busy" && "animate-spin text-ink")}>
      <path d="M21 12a9 9 0 1 1-2.6-6.4L21 8" />
      <path d="M21 3v5h-5" />
    </svg>
  );
}

/** What the button says on hover and to a screen reader, through a press. */
export function refreshWord(phase: RefreshPhase, idle: string): string {
  return phase === "busy" ? "Refreshing…" : phase === "done" ? "Refreshed just now" : idle;
}
