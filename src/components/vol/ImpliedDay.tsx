"use client";

import { Fragment } from "react";
import type { ImpliedBook } from "@/types/terminal";
import { Popover } from "@/components/ui/Popover";
import { Tick } from "@/components/ui/Tick";
import { FUEL_ROWS, PREMIUM_ROWS, fuelTone, premiumTone, type ReadRow } from "@/lib/vix";
import { dir, num, pct } from "@/lib/format";
import { cn } from "@/lib/cn";

/**
 * A book's implied day in long form — the click-through behind each row of
 * the Volatility panel's foot, built the way the VIX bands were: the figure
 * on top as the row shows it, what it is in two sentences, today's facts,
 * then the two rule tables with the row the book is in marked.
 *
 * THE WORDS ARE THE SERVER'S. `fuel` and `premium` arrive on the row from
 * volterm.py, scored with the stocks desk's own thresholds; the tables here
 * are lib/vix's copy of the same constants, so the marked row and the word on
 * the panel cannot disagree. The panel says less where less is known — no
 * realised leg until twenty closes are in, no GEXYGEN band while it is down —
 * rather than guessing.
 */

/** What each index is the implied volatility OF — the sentence needs the market, not the ticker. */
const VOL_OF: Record<string, string> = {
  VXN: "the Nasdaq-100's options",
  VIX: "the S&P 500's options",
  GVZ: "gold's options",
};

export function ImpliedPopover({
  book,
  className,
  children,
}: {
  book: ImpliedBook;
  className?: string;
  children: React.ReactNode;
}) {
  return (
    <Popover
      label={`What ${book.key}'s implied day means`}
      title="Click for what the implied day means"
      className={className}
      panel={<ImpliedDay b={book} />}
    >
      {children}
    </Popover>
  );
}

function ImpliedDay({ b }: { b: ImpliedBook }) {
  const of = VOL_OF[b.vol_key] ?? `${b.vol_key}'s options`;
  const neg = b.regime === "NEG";
  return (
    <div className="w-[min(560px,calc(100vw-24px))] px-4 py-3 text-ink">
      {/* ---- the figure, as the row shows it, so the panel opens on the thing clicked ---- */}
      <div className="flex flex-wrap items-baseline gap-x-2 gap-y-1">
        <span className="qt-cap text-[10.5px] text-ink-3">Implied day</span>
        <span className="fig text-[19px] leading-none text-ink">{b.key}</span>
        {b.sigma != null && (
          <Tick value={`±${num(b.sigma, b.dp)}`} className="fig text-[15px] leading-none text-ink" />
        )}
        <span className="fig ml-auto flex items-baseline gap-1.5 text-[11px] text-ink-3">
          {b.vol_key}
          <Tick value={num(b.vol, 1)} className="text-ink-2" />
          <Tick value={pct(b.vol_pct)} className={dir(b.vol_pct)} />
        </span>
      </div>

      <p className="mt-2 text-[12px] leading-[1.5] text-ink-2">
        The one-day, one-sigma move {of} price: {b.vol_key} ÷ √252, times price. Price closes inside it about two
        days in three, so it is a range of outcomes, not a ceiling. Levels inside it are today&apos;s; walls outside it
        need a bigger day than the market has priced.
      </p>

      {/* ---- today's facts ---- */}
      <dl className="mt-2.5 grid grid-cols-[auto_auto_minmax(0,1fr)] gap-x-3 gap-y-1 text-[11.5px] leading-[1.45]">
        <Fact
          k="Band today"
          v={b.lo != null && b.hi != null ? `${num(b.lo, b.dp)} – ${num(b.hi, b.dp)}` : "—"}
          note="round the last print"
        />
        <Fact
          k="Range used"
          v={b.used != null && b.fuel ? `${b.used.toFixed(2)}× · ${b.fuel}` : "—"}
          tone={fuelTone(b.fuel)}
          note={b.range != null ? `${num(b.range, b.dp)} pts traded since 18:00 ET` : "no range on the quote yet"}
        />
        <Fact
          k="Against realised"
          v={b.iv_rv != null && b.premium ? `${b.iv_rv.toFixed(2)} · ${b.premium}` : "—"}
          tone={premiumTone(b.premium)}
          note={
            b.rv20 != null && b.rv_day != null
              ? `RV20 ${b.rv20.toFixed(1)} · a realised day is ±${num(b.rv_day, b.dp)}`
              : "needs twenty daily closes"
          }
        />
        {b.gex_lo != null && b.gex_hi != null && (
          <Fact
            k="GEXYGEN 0DTE band"
            v={`${num(b.gex_lo, b.dp)} – ${num(b.gex_hi, b.dp)}`}
            note="the same-day book's own, narrower"
          />
        )}
        {b.regime && (
          <Fact
            k="Dealer gamma"
            v={neg ? "negative" : "positive"}
            tone={neg ? "text-put-fig" : "text-call-fig"}
            note={neg ? "trends extend in it; a stretched day can keep going" : "ranges hold in it; the band tends to contain the day"}
          />
        )}
      </dl>

      {/* ---- the two rules, the row the book is in marked ---- */}
      <RuleTable title="Used" rows={FUEL_ROWS} here={b.fuel} tone={fuelTone} />
      <RuleTable title="IV / RV" rows={PREMIUM_ROWS} here={b.premium} tone={premiumTone} />

      <p className="mt-2.5 border-t border-ring pt-2 text-[11px] leading-[1.45] text-ink-3">
        Rules of thumb for ranges, targets and stops, not a signal. A thirty-day index applied to one day: the
        nine-day tenor can price a different day.
      </p>
    </div>
  );
}

function Fact({ k, v, note, tone }: { k: string; v: string; note: string; tone?: string }) {
  return (
    <>
      <dt className="text-ink-3">{k}</dt>
      <dd className={cn("fig whitespace-nowrap", tone ?? "text-ink")}>{v}</dd>
      <dd className="text-ink-3">{note}</dd>
    </>
  );
}

/*
 * FOUR COLUMNS FROM 640px, STACKED BELOW IT — the VIX bands' own arrangement:
 * on a phone the read is its own line under the word and the range, and the
 * column heads go, because the figures say what they are.
 */
function RuleTable<K extends string>({
  title,
  rows,
  here,
  tone,
}: {
  title: string;
  rows: readonly ReadRow<K>[];
  here: K | null | undefined;
  tone: (k: K) => string;
}) {
  const head = "qt-cap border-b border-ring pb-1 text-[10px] text-ink-3";
  const cell = "border-b border-ring/50 py-1.5";
  return (
    <div className="mt-2.5 grid grid-cols-[14px_auto_auto_minmax(0,1fr)] gap-x-3 text-[11.5px] leading-[1.45]">
      <span className={cn(head, "max-sm:hidden")} aria-hidden />
      <span className={cn(head, "max-sm:hidden")}>{title}</span>
      <span className={cn(head, "max-sm:hidden")}>Range</span>
      <span className={cn(head, "max-sm:hidden")}>Read</span>
      {rows.map((r) => {
        const on = r.key === here;
        const lead = cn(cell, "max-sm:border-b-0 max-sm:pb-0");
        return (
          <Fragment key={r.key}>
            <span className={cn(lead, "fig", tone(r.key))} aria-label={on ? "Now" : undefined}>
              {on ? "▸" : ""}
            </span>
            <span className={cn(lead, "fig", on ? cn("font-semibold", tone(r.key)) : "text-ink-2")}>{r.label}</span>
            <span className={cn(lead, "fig whitespace-nowrap", on ? "text-ink" : "text-ink-2")}>{r.range}</span>
            <span className={cn(cell, "max-sm:col-start-2 max-sm:col-span-3 max-sm:pt-0.5", on ? "text-ink" : "text-ink-3")}>
              {r.read}
            </span>
          </Fragment>
        );
      })}
    </div>
  );
}
