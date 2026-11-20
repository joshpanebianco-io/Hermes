import { cn } from "@/lib/cn";
import { age } from "@/lib/format";

/**
 * A module — the terminal's one container.
 *
 * WHY NOT A CARD. A card floats on a page grid with a gap and a shadow; a
 * terminal is one chassis divided into panes. The module keeps a card's
 * anatomy (title, subtitle, right slot, body) because the information
 * hierarchy is the same, and drops the floating chrome because the claim is
 * different. The header's mono/uppercase/tracked typography IS the terminal
 * character — the vibrancy layer here is luminance, never texture.
 *
 * EVERY MODULE STATES ITS OWN AGE. `ageMin` prints in the header as a chip,
 * and it turns amber past ten minutes and red past sixty. Panels on this
 * screen run on clocks that are half an hour apart — the wire at two minutes,
 * the curve at thirty — and one shared "as of" in the corner of the page would
 * be a lie about five of the six.
 */
export function Module({
  title,
  sub,
  right,
  ageMin,
  every,
  ageNote,
  error,
  className,
  bodyClassName,
  scroll,
  large,
  children,
}: {
  title: string;
  sub?: string;
  right?: React.ReactNode;
  ageMin?: number | null;
  /**
   * Minutes between this module's reads, when that is slower than the chip's ten.
   *
   * THE CHIP WARNED ABOUT WORKING SOURCES (2026-11-14). Amber at ten minutes is right
   * for the wire and the board, which are read every minute or two. The curve and the
   * earnings are read every half hour and the Fed diary every hour, so their chips sat
   * amber for most of every cycle with nothing wrong. With the cadence given, the chip
   * is quiet until a read has been MISSED: amber past two cadences, red past six.
   */
  every?: number;
  /** Why the age is what it is, for the chip's hover: a source showing its last good copy says so here. */
  ageNote?: string | null;
  /** A degradation to state on the module's own face, never swallowed. */
  error?: string | null;
  className?: string;
  bodyClassName?: string;
  /** Give the body its own scroll rather than growing the page. */
  scroll?: boolean;
  /**
   * A step up in the header's type. The Report tab's two modules are a page
   * that is read, not a pane that is glanced at, and their header carries the
   * controls that write the page — so it is set a size larger than a pane's.
   */
  large?: boolean;
  children: React.ReactNode;
}) {
  return (
    <section className={cn("module", large && "module-lg", className)}>
      <div className="module-head">
        <h2 className="module-title">{title}</h2>
        {sub && (
          <span
            className={cn(
              "truncate text-ink-3",
              large ? "text-[11.5px] qt:text-[12.5px]" : "text-[10px] qt:text-[11.5px]",
            )}
          >
            {sub}
          </span>
        )}
        <div className="ml-auto flex items-center gap-2">
          {right}
          {ageMin !== undefined && ageMin !== null && <AgeChip m={ageMin} every={every} note={ageNote} />}
        </div>
      </div>
      {error && (
        <div className="border-b border-ring/60 bg-err/10 px-3 py-1.5 text-[10.5px] text-err">
          {error}
        </div>
      )}
      <div
        className={cn(
          "min-w-0 flex-1",
          scroll && "overflow-y-auto",
          bodyClassName ?? "px-3 py-2",
        )}
      >
        {children}
      </div>
    </section>
  );
}

/**
 * The freshness chip.
 *
 * THREE STATES, NOT A GRADIENT. Fresh is silent grey — the normal case must
 * not draw the eye. Amber past ten minutes says "check this before you act on
 * it"; red past an hour says "this is not current". A continuous colour ramp
 * would make every module faintly alarming all the time, which trains you to
 * ignore the one that matters.
 *
 * The Dashboard's cards wear it too (2026-11-20): the same job, the same chip.
 */
export function AgeChip({ m, every, note }: { m: number; every?: number; note?: string | null }) {
  // A slow source is late once it has missed a read, not ten minutes after its last one.
  const warnAt = every ? Math.max(10, every * 2) : 10;
  const errAt = every ? Math.max(60, every * 6) : 60;
  const tone =
    m >= errAt ? "text-err border-err/40" : m >= warnAt ? "text-warn border-warn/40" : "text-ink-3 border-ring";
  const when = m < 1 ? "Fetched in the last minute" : `Fetched ${age(m)} ago`;
  const cadence = every ? ` · read every ${every >= 60 ? `${every / 60}h` : `${every} min`}` : "";
  return (
    <span
      className={cn(
        "fig shrink-0 rounded border px-1.5 py-px text-[9.5px] leading-[14px]",
        // Quiet: the age is a figure, not a badge — no box round it.
        "qt:border-0 qt:px-0 qt:text-[11px]",
        tone,
      )}
      title={note ? `${when}${cadence} · ${note}` : `${when}${cadence}`}
    >
      {age(m)}
    </span>
  );
}
