import { cn } from "@/lib/cn";
import { scaleLabel, scalePos } from "@/lib/biasScale";

/**
 * The bias on a scale: bearish at the left end, bullish at the right, neutral in the
 * middle, and a mark where the score sits (lib/biasScale has the why).
 *
 * THE BAR RUNS FROM THE MIDDLE TO THE MARK, in the side's own hue. What it measures is
 * the distance from neutral, so a fill is the honest drawing here; the board's range bar
 * is a mark alone because that one is a position inside a range, with no zero.
 *
 * THE TWO SHORT TICKS ARE -50 AND +50, where a lean is graded strong: something to judge
 * "how close to the extreme" against without a number. The taller, heavier one is
 * neutral.
 *
 * DRAWN TO BE SEEN (the first build was a 3px bar on a surface grey with a 9px mark, and
 * on the page it was a dot and two specks: owner, of an earlier polish round, "barely
 * look different lol?"). A 5px bar, an 11px mark with the ground's colour round it so it
 * stands off the bar, and a track mixed from the ink.
 *
 * ONE MARK, ALWAYS SOLID. A read on few inputs was a ring with a faint bar until the
 * owner asked why it was a black circle (2026-11-15); the score is over the whole weight
 * now, so such a read sits near the middle and needs no drawing of its own (lib/biasScale).
 *
 * Spans throughout, so it can sit inside a card that is a button (the Futures bias card
 * opens the driver board) and inline in a line of type.
 */
export function BiasScale({
  score,
  side,
  ends = false,
  className,
  title,
}: {
  /** -100 to +100; null draws the empty scale. */
  score: number | null | undefined;
  /** The side the read came out on: the hue. No lean is grey wherever the mark sits. */
  side: "long" | "short" | null | undefined;
  /** The words "Bear" and "Bull" at the ends, where there is room for them. */
  ends?: boolean;
  className?: string;
  title?: string;
}) {
  const pos = scalePos(score);
  const fill = side === "long" ? "bg-call-fig" : side === "short" ? "bg-put-fig" : "bg-ink-3";
  const ring = side === "long" ? "border-call-fig" : side === "short" ? "border-put-fig" : "border-ink-3";
  return (
    <span className={cn("inline-flex items-center gap-1.5", className)} role="img" aria-label={scaleLabel(score)} title={title}>
      {ends && <span className="qt-cap shrink-0 text-[8.5px] leading-none text-ink-3">Bear</span>}
      <span className="relative block h-[13px] min-w-[40px] flex-1">
        {/* The track is a mix of the ink, not a surface tone: the cards are glass under
            Luminous and a surface grey on them was not there to see (the first build). */}
        <span className="absolute inset-x-0 top-1/2 h-[5px] -translate-y-1/2 rounded-[2px] bg-[color-mix(in_oklab,var(--ink-3)_34%,transparent)]" />
        {pos !== null && pos !== 50 && (
          <span
            className={cn("absolute top-1/2 h-[5px] -translate-y-1/2 rounded-[2px] opacity-90", fill)}
            style={{ left: `${Math.min(50, pos)}%`, width: `${Math.abs(pos - 50)}%` }}
          />
        )}
        <span className="absolute top-1/2 left-1/4 h-[9px] w-px -translate-y-1/2 bg-ink-3" />
        <span className="absolute top-1/2 left-3/4 h-[9px] w-px -translate-y-1/2 bg-ink-3" />
        <span className="absolute top-1/2 left-1/2 h-[13px] w-[2px] -translate-x-1/2 -translate-y-1/2 rounded-[1px] bg-ink-2" />
        {pos !== null && (
          <span
            className={cn(
              "absolute top-1/2 h-[11px] w-[11px] -translate-x-1/2 -translate-y-1/2 rounded-full border-2 shadow-[0_0_0_1.5px_var(--bg)]",
              ring,
              fill,
            )}
            // Held inside the track: at an extreme the mark sits on the end, not past it.
            style={{ left: `clamp(5.5px, ${pos}%, calc(100% - 5.5px))` }}
          />
        )}
      </span>
      {ends && <span className="qt-cap shrink-0 text-[8.5px] leading-none text-ink-3">Bull</span>}
    </span>
  );
}
