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
          {ageMin !== undefined && ageMin !== null && <AgeChip m={ageMin} />}
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
 */
function AgeChip({ m }: { m: number }) {
  const tone =
    m >= 60 ? "text-err border-err/40" : m >= 10 ? "text-warn border-warn/40" : "text-ink-3 border-ring";
  return (
    <span
      className={cn(
        "fig shrink-0 rounded border px-1.5 py-px text-[9.5px] leading-[14px]",
        // Quiet: the age is a figure, not a badge — no box round it.
        "qt:border-0 qt:px-0 qt:text-[11px]",
        tone,
      )}
      title={m < 1 ? "Fetched in the last minute" : `Fetched ${age(m)} ago`}
    >
      {age(m)}
    </span>
  );
}
