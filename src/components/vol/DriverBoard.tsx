"use client";

import type { DriverBook, DriverVote } from "@/types/terminal";
import { Popover } from "@/components/ui/Popover";
import { liveLine, scoreText } from "@/lib/bias";
import { wholeScore } from "@/lib/biasScale";
import { BiasScale } from "@/components/ui/BiasScale";
import { num } from "@/lib/format";
import { cn } from "@/lib/cn";
import { FUT_NAME, type FutBook } from "@/lib/futures";
import { sheetOf, type Lean, type SheetFactor, type SheetRead } from "@/lib/driverSheet";
import { useLum } from "@/components/state/UiMode";
import { segItem } from "@/lib/seg";
import { toggleBias, useBias } from "@/lib/biasDrawer";

/**
 * The driver board's long form: every read behind a book's score, by factor, with its
 * figure and its reason, then the context that never votes, and how to treat it. It
 * opens from a futures contract's Bias card.
 *
 * THE FUTURES DESK'S TAPE COUNT (owner, 2026-10-22: "do everything you recommend"),
 * WEIGHED (owner, 2026-11-05: "do what you recommend"). This panel is the server's board
 * (drivers.py, bias.py) printed: the words are the engine's, and the panel adds nothing.
 *
 * SET AS A REPORT SINCE 2026-11-16 (owner: "make the pop out card a bit wider and format
 * it more like a professional report etc.", the day the Market Report page left the
 * navigation and this pop-up became where a contract's read is written out). It is laid
 * out as the market report's sheet is (panels/Brief MarketReportView): a masthead over a
 * rule, the call with the scale, a strip of four key figures, the summary, a table of
 * what is driving the bias with the report's names and tags for each factor
 * (lib/driverSheet), the context, and the method at its foot. 880px where it was 660.
 * Unlike a report it is never stale: it is the board of the last refresh, and says when
 * that was.
 *
 * FROM THE RIGHT SINCE THE SAME DAY (owner: "can we make it so when you click on the bias
 * the pop up card comes from the right similar to when you click on a stock and the
 * charts appears"): the Bias card is a `BiasOpener`, and the sheet is drawn in the
 * slide-out (vol/BiasDrawer) with `onClose`, its masthead pinned at the top.
 *
 * A read that cannot vote at this hour is dimmed and marked with a dot, because it is
 * not the same thing as a flat one.
 */

export const voteTone = (v: DriverVote["vote"] | DriverBook["bias"]) =>
  v === "long" ? "text-call-fig" : v === "short" ? "text-put-fig" : "text-ink-3";
export const voteGlyph = (v: DriverVote["vote"]) => (v === "long" ? "▲" : v === "short" ? "▼" : "–");

export const biasWord = (b: DriverBook["bias"]) => (b === "long" ? "▲ Long" : b === "short" ? "▼ Short" : "No lean");
/** Strong carries the side's hue; weak and none step back — the stocks desk's rule. */
export const gradeTone = (b: DriverBook) =>
  b.grade === "strong" ? voteTone(b.bias) : b.grade === "moderate" ? "text-ink-2" : "text-ink-3";

export function DriverPopover({
  book,
  asOf,
  className,
  children,
}: {
  book: DriverBook;
  /** When the board was built (`drivers.built_utc`), for the masthead. */
  asOf?: string;
  className?: string;
  children: React.ReactNode;
}) {
  return (
    <Popover
      label={`What drives ${book.key} today`}
      title="Click for every read behind the score and how to treat it"
      className={className}
      panel={<DriverBoard book={book} asOf={asOf} />}
    >
      {children}
    </Popover>
  );
}

/**
 * A futures contract's Bias card as the button that slides its board out from the right
 * (vol/BiasDrawer), as a stock's row slides out its chart. A second click puts it away.
 * It took the pop-up's place on 2026-11-16; `DriverPopover` above is kept for a figure
 * that wants the board in place.
 */
export function BiasOpener({ book, className, children }: { book: string; className?: string; children: React.ReactNode }) {
  const on = useBias() === book;
  return (
    <button
      type="button"
      onClick={() => toggleBias(book)}
      aria-expanded={on}
      title={on ? "Put the bias away" : "Every read behind the score and how to treat it"}
      className={cn("hit cursor-pointer rounded-[4px] text-left hover:bg-surface-2/70 aria-expanded:bg-surface-2", className)}
    >
      {children}
    </button>
  );
}

/** "13:45:07" in New York, from the board's build time. */
function etTime(iso: string): string | null {
  const t = Date.parse(iso);
  if (!Number.isFinite(t)) return null;
  return new Date(t).toLocaleTimeString("en-US", { timeZone: "America/New_York", hour12: false, hour: "2-digit", minute: "2-digit", second: "2-digit" });
}

const GRADE: Record<DriverBook["grade"], string> = { strong: "Strong", moderate: "Moderate", weak: "Weak", none: "None" };

export function DriverBoard({
  book: b,
  asOf,
  onClose,
}: {
  book: DriverBook & { session_key?: string };
  asOf?: string;
  /** In the slide-out (vol/BiasDrawer): the sheet fills it, and its masthead stays at the top with a close button. */
  onClose?: () => void;
}) {
  const lum = useLum();
  const rule = lum ? "border-white/[0.07]" : "border-ring/60";
  const s = sheetOf(b);
  const score = wholeScore(b) ?? b.score;
  const at = asOf ? etTime(asOf) : null;
  const top = Math.max(1, ...s.factors.map((f) => f.weight ?? 0));
  const pad = "px-7";
  const drawer = onClose != null;
  return (
    <article
      className={cn(
        "flex flex-col text-ink",
        drawer
          ? "h-full min-h-0 w-full overflow-y-auto"
          : // At most the window's height, in the panel's own pixels: Luminous zooms a pop-up 1.1
            // on a wide window (globals.css --ui-unzoom), and 100vh unscaled ran 120px off a 1440 screen.
            "max-h-[calc((100vh-24px)*var(--ui-unzoom,1))] w-[min(880px,calc((100vw-24px)*var(--ui-unzoom,1)))] overflow-y-auto",
      )}
    >
      {/* ---- the masthead: pinned in the slide-out, so the close button never scrolls away ---- */}
      <header className={cn(pad, "pt-6", drawer && "sticky top-0 z-10 bg-bg pb-2")}>
        <div className="flex flex-wrap items-end justify-between gap-x-8 gap-y-2">
          <div className="min-w-0">
            <p className="qt-cap text-[10.5px] tracking-[0.16em] text-ink-3">Hermes · Bias</p>
            <h2 className="mt-2 text-[26px] leading-none font-semibold tracking-[-0.015em] text-ink">
              {FUT_NAME[b.key as FutBook] ?? b.key}
              <span className="font-normal text-ink-3"> · {b.key}</span>
            </h2>
          </div>
          <div className="flex items-end gap-4">
            <div className="text-right">
              <p className="fig text-[15px] leading-none text-ink">{num(b.last)}</p>
              <p className="mt-1.5 text-[11.5px] leading-none text-ink-3">
                {s.session} weights{at ? ` · as of ${at} ET` : ""}
              </p>
            </div>
            {drawer && (
              <button type="button" onClick={onClose} title="Close (Esc)" {...segItem(false, { className: "border border-ring-2 self-start" })}>
                ✕
              </button>
            )}
          </div>
        </div>
        <div aria-hidden className="mt-5 h-[2px] rounded-full bg-ink opacity-80" />
      </header>

      {/* ---- the call ---- */}
      <section className={cn(pad, "pt-5")}>
        <div className="flex flex-wrap items-center justify-between gap-x-8 gap-y-3">
          <p className={cn("flex items-baseline gap-3 text-[30px] leading-none font-semibold tracking-[-0.01em]", voteTone(b.bias))}>
            <span>{biasWord(b.bias)}</span>
            <span className="fig">{scoreText(score)}</span>
          </p>
          <BiasScale score={wholeScore(b)} side={b.bias} ends className="w-[300px] max-w-full" title={liveLine(b)} />
        </div>
        <dl className={cn("mt-5 grid grid-cols-2 border-y sm:grid-cols-4", rule)}>
          <KeyFigure
            label="Grade"
            value={GRADE[b.grade]}
            tone={gradeTone(b)}
            sub={b.conflict ? "macro and structure disagree" : "strong 50 · moderate 30 · weak 10"}
            subTone={b.conflict ? "text-flip-fig" : undefined}
            rule={rule}
          />
          <KeyFigure label="Conviction ceiling" value={`${b.max_conviction} of 5`} sub="the most a call may claim" rule={rule} />
          <KeyFigure label="Reads live" value={`${b.live} of ${b.total}`} sub={`${b.agree} agree · ${b.against} against · ${b.neutral} flat`} rule={rule} />
          <KeyFigure label="Weight live" value={`${b.coverage}%`} sub={`of ${b.weight_label}`} rule={rule} last />
        </dl>
      </section>

      {/* ---- the summary ---- */}
      <section className={cn(pad, "pt-5 pb-5")}>
        <p className="qt-cap text-[10.5px] text-ink-3">Summary</p>
        <p className="mt-2 text-[15.5px] leading-[1.55] text-ink">{b.treatment}</p>
      </section>

      {/* ---- what is driving it ---- */}
      <section className={cn(pad, "border-t py-5", rule)} aria-label="What is driving the bias">
        <SheetHead title="What is driving the bias" right="each factor's read and share of the score, heaviest first" />
        <div className={cn("grid grid-cols-[minmax(0,1fr)_120px_92px_56px] gap-x-4 border-b pb-1.5", rule)}>
          <span className={TH}>Factor</span>
          <span className={TH}>Read</span>
          <span className={cn(TH, "text-right")} title="The factor's share of the bias score in this session">
            Weight
          </span>
          <span className={cn(TH, "text-right")} title="The factor's own net read, -100 to +100">
            Net
          </span>
        </div>
        {s.factors.map((f) => (
          <FactorRows key={f.key} f={f} top={top} rule={rule} />
        ))}
      </section>

      {/* ---- context ---- */}
      {s.context.length > 0 && (
        <section className={cn(pad, "border-t py-5", rule)} aria-label="Context">
          <SheetHead title="Context" right="what a move will find, never a vote" />
          <dl className={cn("border-t", rule)}>
            {s.context.map((c) => (
              <div key={c.key} className={cn("grid grid-cols-[170px_220px_minmax(0,1fr)] gap-x-4 border-b py-2.5 text-[12.5px] leading-[1.5] last:border-b-0", rule)}>
                <dt className="font-semibold text-ink">{c.label}</dt>
                <dd className="fig text-ink">{c.value}</dd>
                <dd className="text-ink-3">{c.note}</dd>
              </div>
            ))}
          </dl>
        </section>
      )}

      {/* ---- the method ---- */}
      <footer className={cn(pad, "border-t py-3.5 text-[11px] leading-[1.55] text-ink-3", rule)}>
        The score runs from -100 to +100: each factor&apos;s net read, weighed for the session, over the whole of its
        weight. A factor that cannot vote at this hour counts as no lean, so the less of the board is live the nearer
        the score sits to zero. Strong is 50 or more with at least 60% of the weight live, moderate 30, weak 10; a
        conflict between macro and structure takes a notch off. A read marked with a dot cannot vote at this hour.
        Dealer gamma and the context rows are never a side. The weights are a judgement and have not been tested
        against outcomes.
      </footer>
    </article>
  );
}

const TH = "qt-cap text-[10px] font-medium text-ink-3";

/** A section's title on the sheet, with a few quiet words at the end of its line (the report's SheetHead). */
function SheetHead({ title, right }: { title: string; right?: string }) {
  return (
    <h3 className="mb-3 flex items-baseline justify-between gap-3">
      <span className="text-[14.5px] font-semibold text-ink">{title}</span>
      {right && <span className="truncate text-[11px] text-ink-3">{right}</span>}
    </h3>
  );
}

/** One of the four figures under the call. */
function KeyFigure({
  label,
  value,
  sub,
  tone = "text-ink",
  subTone,
  rule,
  last,
}: {
  label: string;
  value: string;
  sub: string;
  tone?: string;
  subTone?: string;
  rule: string;
  last?: boolean;
}) {
  return (
    <div className={cn("min-w-0 py-3 pr-4 sm:border-r sm:pl-4 sm:first:pl-0", !last && rule, last && "sm:border-r-0")}>
      <dt className="qt-cap text-[10px] text-ink-3">{label}</dt>
      <dd className={cn("fig mt-1.5 text-[17px] leading-none", tone)}>{value}</dd>
      <dd className={cn("mt-1.5 truncate text-[11px] leading-none", subTone ?? "text-ink-3")} title={sub}>
        {sub}
      </dd>
    </div>
  );
}

/** A factor's line, then each read it is made of under it. */
function FactorRows({ f, top, rule }: { f: SheetFactor; top: number; rule: string }) {
  const idle = f.weight === 0;
  return (
    <div className={cn("border-b py-3 last:border-b-0", rule)}>
      <div className="grid grid-cols-[minmax(0,1fr)_120px_92px_56px] items-start gap-x-4">
        <div className="min-w-0">
          <div className={cn("text-[14px] leading-snug font-semibold", idle ? "text-ink-3" : "text-ink")}>{f.name}</div>
          {f.sub && <div className="mt-0.5 text-[11px] leading-snug text-ink-3">{f.sub}</div>}
        </div>
        <div>
          <Tag lean={f.lean} tag={f.tag} />
        </div>
        <div className="text-right">
          {f.weight != null && f.weight > 0 ? (
            <>
              <span className="fig text-[12.5px] leading-[20px] text-ink-2">{f.weight}%</span>
              <span aria-hidden className="mt-1 ml-auto block h-[3px] w-[46px] overflow-hidden rounded-full bg-[color-mix(in_oklab,var(--ink-3)_26%,transparent)]">
                <span className="block h-full rounded-full bg-ink-3" style={{ width: `${(f.weight / top) * 100}%` }} />
              </span>
            </>
          ) : (
            <span
              className="text-[12.5px] leading-[20px] text-ink-3"
              title={f.weight == null ? "Not a side: it lowers the ceiling on conviction" : "No weight in this session"}
            >
              —
            </span>
          )}
        </div>
        <div className={cn("fig text-right text-[12.5px] leading-[20px]", f.score == null ? "text-ink-4" : f.score > 0 ? "text-call-fig" : f.score < 0 ? "text-put-fig" : "text-ink-3")}>
          {f.score == null ? "—" : scoreText(f.score)}
        </div>
      </div>
      <ul className="mt-1.5 space-y-1">
        {f.reads.map((r) => (
          <ReadLine key={r.key} r={r} plain={f.key === "event"} />
        ))}
      </ul>
    </div>
  );
}

/** One read: its side (or a dot when it cannot vote now), its name, its figure, why. */
function ReadLine({ r, plain }: { r: SheetRead; plain?: boolean }) {
  const off = !r.live;
  return (
    <li className="grid grid-cols-[14px_150px_190px_minmax(0,1fr)] gap-x-3 text-[12px] leading-[1.45]">
      <span className={cn("text-center text-[10px] leading-[17px]", off || plain ? "text-ink-4" : voteTone(r.vote))} aria-label={off ? "cannot vote now" : plain ? "not a side" : r.vote}>
        {off || plain ? "·" : voteGlyph(r.vote)}
      </span>
      <span className={cn("min-w-0", off ? "text-ink-4" : "text-ink-2")}>{r.label}</span>
      <span className={cn("fig min-w-0 break-words", off ? "text-ink-3" : "text-ink")}>{r.value}</span>
      <span className={off ? "text-ink-4" : "text-ink-3"}>{r.note}</span>
    </li>
  );
}

/** A factor's tag, as the report draws one: green and pink are the book's side, amber the damper, the rest ink. */
function Tag({ lean, tag }: { lean: Lean; tag: string }) {
  const lum = useLum();
  const hue =
    lean === "bull" ? "var(--call-fig)" : lean === "bear" ? "var(--put-fig)" : lean === "damp" ? "var(--warn)" : lean === "mixed" ? "var(--ink-2)" : null;
  if (lum) {
    return (
      <span
        className="inline-flex items-center rounded-full border px-2 py-px text-[11px] leading-[18px] font-medium whitespace-nowrap"
        style={{
          color: hue ?? "var(--ink-3)",
          borderColor: hue ? `color-mix(in oklab, ${hue} 38%, transparent)` : "rgba(255,255,255,0.1)",
          background: hue ? `color-mix(in oklab, ${hue} 10%, transparent)` : "transparent",
        }}
      >
        {tag}
      </span>
    );
  }
  // Quiet drops the box: a toned tag is a square marker and caps in its hue (the report's Chip).
  return (
    <span className="qt-cap inline-flex items-center gap-1 text-[10px] leading-[20px] whitespace-nowrap" style={{ color: hue ?? "var(--ink-3)" }}>
      {hue && <span aria-hidden className="h-[5px] w-[5px] shrink-0 bg-current" />}
      {tag}
    </span>
  );
}
