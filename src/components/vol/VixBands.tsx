"use client";

import { Fragment } from "react";
import { Popover } from "@/components/ui/Popover";
import { Tick } from "@/components/ui/Tick";
import { BAND_LABEL, BANDS, impliedDayPct, vixBand, type VixBand } from "@/lib/vix";
import { dir, num, pct } from "@/lib/format";
import { cn } from "@/lib/cn";

/**
 * The VIX card's click-through: the four bands and what each means.
 *
 * ONE PANEL FOR EVERY VIX ON SCREEN (owner, 2026-10-21: "if we click on the
 * vix card it shows the ranges and what they mean ... include the header vix
 * too"). The Scanner card, the Game plan card and the header figure on both
 * desks all open this, handed whatever travels with their number — the band
 * the server scored with, the curve, VVIX — and the panel says less where
 * less is known rather than guessing.
 *
 * THE BAND WORD IS THE SERVER'S WHEN THE PAYLOAD CARRIES ONE, and only read
 * off the level (lib/vix, the same rule) where it does not — the header has a
 * quote, not a regime. Either way the marked row is the row the scanner is
 * in, not a second opinion.
 */

/** What the panel reads: the VIX print and what travels with it, any of it missing. */
export interface VixFacts {
  last: number | null;
  pct: number | null;
  /** VIX ÷ VIX3M. */
  ratio: number | null;
  shape: string | null;
  vvix: number | null;
  /** The band the server scored with, when the payload carries one. */
  band?: string | null;
}

/** The band's ink — the Scanner card's own mapping, so the panel and the card agree. */
export function bandTone(band: VixBand | null): string {
  return band === "stressed"
    ? "text-put-fig"
    : band === "elevated"
      ? "text-flip-fig"
      : band === "grind"
        ? "text-ink-3"
        : "text-ink";
}

const isBand = (b: unknown): b is VixBand =>
  b === "grind" || b === "normal" || b === "elevated" || b === "stressed";

export function VixPopover({
  facts,
  title,
  className,
  children,
}: {
  facts: VixFacts;
  title?: string;
  className?: string;
  children: React.ReactNode;
}) {
  const band = isBand(facts.band) ? facts.band : vixBand(facts.last, facts.shape);
  return (
    <Popover label="What the VIX level means" title={title} className={className} panel={<VixBands facts={facts} band={band} />}>
      {children}
    </Popover>
  );
}

function VixBands({ facts, band }: { facts: VixFacts; band: VixBand | null }) {
  const em = facts.last != null && Number.isFinite(facts.last) ? impliedDayPct(facts.last) : null;
  const shape = facts.shape && facts.shape !== "unknown" ? facts.shape : null;
  const head = "qt-cap border-b border-ring pb-1 text-[10px] text-ink-3";
  const cell = "border-b border-ring/50 py-1.5";
  return (
    <div className="w-[min(560px,calc(100vw-24px))] px-4 py-3 text-ink">
      {/* ---- the figure, as the card shows it, so the panel opens on the thing clicked ---- */}
      <div className="flex flex-wrap items-baseline gap-x-2 gap-y-1">
        <span className="qt-cap text-[10.5px] text-ink-3">VIX</span>
        <Tick value={num(facts.last, 2)} className="fig text-[19px] leading-none text-ink" />
        <Tick value={pct(facts.pct)} className={cn("fig text-[11.5px]", dir(facts.pct))} />
        {band && <span className={cn("qt-cap text-[10.5px]", bandTone(band))}>{BAND_LABEL[band]}</span>}
        {em != null && (
          <span className="fig ml-auto text-[11px] text-ink-3">
            SPY day <span className="text-ink-2">±{em.toFixed(2)}%</span>
          </span>
        )}
      </div>

      <p className="mt-2 text-[12px] leading-[1.5] text-ink-2">
        The 30-day S&amp;P 500 move the options market is pricing, annualised. Divided by √252 (about 15.9) it is the
        one-day move it implies for SPY. The bands are the scanner&apos;s own: the band word on the card is the one every
        row is scored in.
      </p>

      {/* ---- the four bands, the one the tape is in marked ----
          FIVE COLUMNS FROM 640px, STACKED BELOW IT: on a phone the three
          figure columns left the read a word per line and the heading cut
          off at the edge. There each band is its figures on one line and
          its read under them, and the column heads go — the figures say
          what they are. */}
      <div className="mt-2.5 grid grid-cols-[14px_auto_auto_minmax(0,1fr)] gap-x-3 text-[11.5px] leading-[1.45] sm:grid-cols-[14px_auto_auto_auto_minmax(0,1fr)]">
        <span className={cn(head, "max-sm:hidden")} aria-hidden />
        <span className={cn(head, "max-sm:hidden")}>Band</span>
        <span className={cn(head, "max-sm:hidden")}>VIX</span>
        <span className={cn(head, "max-sm:hidden")}>SPY day</span>
        <span className={cn(head, "max-sm:hidden")}>What the tape does</span>
        {BANDS.map((b) => {
          const here = b.key === band;
          const lead = cn(cell, "max-sm:border-b-0 max-sm:pb-0");
          return (
            <Fragment key={b.key}>
              <span className={cn(lead, "fig", bandTone(b.key))} aria-label={here ? "Now" : undefined}>
                {here ? "▸" : ""}
              </span>
              <span className={cn(lead, "fig", here ? cn("font-semibold", bandTone(b.key)) : "text-ink-2")}>{b.label}</span>
              <span className={cn(lead, "fig whitespace-nowrap", here ? "text-ink" : "text-ink-2")}>{b.range}</span>
              <span className={cn(lead, "fig whitespace-nowrap", here ? "text-ink" : "text-ink-3")}>{b.move}</span>
              <span className={cn(cell, "max-sm:col-start-2 max-sm:col-span-3 max-sm:pt-0.5", here ? "text-ink" : "text-ink-3")}>
                {b.read}
              </span>
            </Fragment>
          );
        })}
      </div>

      <p className="mt-2.5 text-[11.5px] leading-[1.5] text-ink-3">
        <span className="text-ink-2">The curve overrides the level.</span> VIX ÷ VIX3M above 1.00 (backwardation) reads
        Stressed at any number, because near-term fear has overtaken the three-month view.
        {facts.ratio != null ? (
          <>
            {" "}
            Today <span className="fig text-ink">{facts.ratio.toFixed(2)}</span>
            {shape && <>, {shape}</>}.
          </>
        ) : shape ? (
          <> Today: {shape}.</>
        ) : null}
      </p>

      {facts.vvix != null && (
        <p className="mt-1.5 text-[11.5px] leading-[1.5] text-ink-3">
          <span className="text-ink-2">
            VVIX <span className="fig text-ink">{num(facts.vvix, 1)}</span>
          </span>{" "}
          — how fast VIX itself can move. Under 90 is quiet; 100 and up is positioning for a vol shock.
        </p>
      )}

      <p className="mt-2.5 border-t border-ring pt-2 text-[11px] leading-[1.45] text-ink-3">
        Rules of thumb for sizing and stops, not a signal. VIX never picks a name.
      </p>
    </div>
  );
}
