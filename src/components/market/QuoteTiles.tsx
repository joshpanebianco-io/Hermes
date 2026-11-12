"use client";

import type { ImpliedBook, Quote, VolTerm } from "@/types/terminal";
import { dir, feedNote, num, quoteChg } from "@/lib/format";
import { cn } from "@/lib/cn";
import { lagText, quoteGroups, quoteInk } from "@/lib/quoteTiles";
import { curveShape } from "@/lib/vix";
import { Tick } from "@/components/ui/Tick";
import { VixPopover, type VixFacts } from "@/components/vol/VixBands";

/**
 * A row of prices, each a name over its figure with the move beside it: the header
 * strip's full-screen form, now drawn on the page each figure belongs to (lib/quoteTiles).
 *
 * THE FIGURES DO NOT MOVE AROUND. A row is in trading order with a hairline between
 * its groups, so a figure is always in the same place on its page, which is what the
 * strip was for. `spread` sets the row across its whole width, as the Dashboard's is.
 *
 * VIX OPENS ITS BANDS here as it did in the header (owner, 2026-10-21: "include the
 * header vix too"): the curve read from the VIX3M print on the same feed, the books'
 * implied day and the month from volterm, the band off the level by lib/vix's rule.
 */
export function QuoteTiles({
  quotes,
  groups,
  implied,
  vixMonth,
  spread = false,
  pills = false,
  className,
}: {
  quotes: readonly Quote[];
  groups: readonly (readonly string[])[];
  /**
   * Each figure on one line in a capsule of its own, "SPY 759.81 +1.32%": the Sidebar
   * interface's header, where the prices stand beside the page's name (shell/SideHeader).
   */
  pills?: boolean;
  /** The books' implied day (volterm.books), for the VIX panel. */
  implied?: ImpliedBook[];
  /** The VIX against its own month (volterm.vix_month), for the same panel. */
  vixMonth?: VolTerm["vix_month"];
  spread?: boolean;
  className?: string;
}) {
  const rows = quoteGroups(quotes, groups);
  if (rows.length === 0) return null;
  const vix3m = quotes.find((q) => q.key === "VIX3M")?.last ?? null;
  const vvix = quotes.find((q) => q.key === "VVIX")?.last ?? null;
  const facts = (q: Quote): VixFacts => {
    const ratio = vix3m && vix3m > 0 ? q.last / vix3m : null;
    return { last: q.last, pct: q.pct, ratio, shape: curveShape(ratio), vvix, implied: implied ?? null, month: vixMonth ?? null };
  };
  if (pills) {
    // No rule between the groups: each capsule is its own outline already.
    return (
      <div className={cn("flex min-w-0 flex-wrap items-center gap-2", className)}>
        {rows.flat().map((q) =>
          q.key === "VIX" ? (
            <VixPopover key={q.key} facts={facts(q)} title={[feedNote(q), "Click for what the level means"].filter(Boolean).join("\n")} className="flex shrink-0">
              <Pill q={q} />
            </VixPopover>
          ) : (
            <div key={q.key} className="flex shrink-0" title={feedNote(q) ?? undefined}>
              <Pill q={q} />
            </div>
          ),
        )}
      </div>
    );
  }
  return (
    <div className={cn("flex min-w-0 flex-wrap items-center gap-y-2", spread ? "justify-between gap-x-4" : "gap-x-4", className)}>
      {rows.flatMap((g, i) => [
        ...(i > 0 ? [<span key={`rule-${i}`} aria-hidden className="h-7 w-px shrink-0 bg-ring-2" />] : []),
        ...g.map((q) =>
          q.key === "VIX" ? (
            <VixPopover
              key={q.key}
              facts={facts(q)}
              title={[feedNote(q), "Click for what the level means"].filter(Boolean).join("\n")}
              className="-mx-1.5 flex shrink-0 px-1.5"
            >
              <Figure q={q} />
            </VixPopover>
          ) : (
            <div key={q.key} className="flex shrink-0" title={feedNote(q) ?? undefined}>
              <Figure q={q} />
            </div>
          ),
        ),
      ])}
    </div>
  );
}

/** One instrument on one line, in a capsule. Phrasing content only: on VIX this sits inside a <button>. */
function Pill({ q }: { q: Quote }) {
  const chg = quoteChg(q);
  const lag = lagText(q, 5);
  return (
    <span className="qt-quote-pill flex items-baseline gap-2 rounded-full border border-ring-2 px-3 py-[5px] whitespace-nowrap">
      <span className="qt-cap text-[10.5px] text-ink-3">
        {q.key}
        {lag && <span className="text-ink-4 normal-case"> · {lag}</span>}
      </span>
      <Tick value={num(q.last)} className={cn("fig text-[13px] leading-none", quoteInk(q))} />
      <Tick value={chg.text} className={cn("fig text-[11px] leading-none", dir(chg.v))} />
    </span>
  );
}

/** One instrument. Phrasing content only: on VIX this sits inside a <button>. */
function Figure({ q }: { q: Quote }) {
  const chg = quoteChg(q);
  const lag = lagText(q);
  return (
    <span className="flex flex-col justify-center gap-1 text-left">
      {/* How late a delayed print is rides under its own label, in lower case: "NQ · 10M"
          read as ten million or a ten-minute chart. */}
      <span className="qt-cap text-[10.5px] whitespace-nowrap text-ink-3">
        {q.key}
        {lag && <span className="text-ink-4 normal-case"> · {lag}</span>}
      </span>
      <span className="flex items-baseline gap-1.5 whitespace-nowrap">
        <Tick value={num(q.last)} className={cn("fig text-[14.5px] leading-none", quoteInk(q))} />
        <Tick value={chg.text} className={cn("fig text-[11px] leading-none", dir(chg.v))} />
      </span>
    </span>
  );
}
