"use client";

import { Fragment } from "react";
import type { DriverBook, DriverVote } from "@/types/terminal";
import { Popover } from "@/components/ui/Popover";
import { num } from "@/lib/format";
import { cn } from "@/lib/cn";

/**
 * The driver board's long form — every vote behind a book's count, by layer,
 * with its figure and its reason, then the context rows that never vote and
 * one line on how to treat it.
 *
 * THE FUTURES DESK'S TAPE COUNT (owner, 2026-10-22: "do everything you
 * recommend"). The stocks desk has shown its eleven votes since October; the
 * futures Terminal showed the 10Y up six basis points and said nothing about
 * what that did to NQ. This panel is the server's board (drivers.py) printed:
 * the words are the engine's, the thresholds the stocks desk's own where one
 * exists, and the panel adds nothing — it opens from the strip the way every
 * VIX figure opens the bands.
 */

const LAYERS: { key: DriverVote["layer"]; label: string; what: string }[] = [
  { key: "macro", label: "Macro", what: "sets the direction" },
  { key: "positioning", label: "Positioning", what: "says how far a move runs" },
  { key: "structure", label: "Structure", what: "says whether the tape accepts it" },
];

export const voteTone = (v: DriverVote["vote"] | DriverBook["bias"]) =>
  v === "long" ? "text-call-fig" : v === "short" ? "text-put-fig" : "text-ink-3";
export const voteGlyph = (v: DriverVote["vote"]) => (v === "long" ? "▲" : v === "short" ? "▼" : "–");
export const biasWord = (b: DriverBook["bias"]) => (b === "long" ? "▲ Long" : b === "short" ? "▼ Short" : "No lean");
/** Strong carries the side's hue; weak and none step back — the stocks desk's rule. */
export const gradeTone = (b: DriverBook) =>
  b.grade === "strong" ? voteTone(b.bias) : b.grade === "moderate" ? "text-ink-2" : "text-ink-3";

export function DriverPopover({
  book,
  className,
  children,
}: {
  book: DriverBook;
  className?: string;
  children: React.ReactNode;
}) {
  return (
    <Popover
      label={`What drives ${book.key} today`}
      title="Click for every driver and how to treat the count"
      className={className}
      panel={<DriverBoard book={book} />}
    >
      {children}
    </Popover>
  );
}

export function DriverBoard({ book: b }: { book: DriverBook }) {
  return (
    <div className="w-[min(660px,calc(100vw-24px))] px-4 py-3 text-ink">
      {/* ---- the count, as the strip shows it ---- */}
      <div className="flex flex-wrap items-baseline gap-x-2 gap-y-1">
        <span className="qt-cap text-[10.5px] text-ink-3">Driver board</span>
        <span className="fig text-[19px] leading-none text-ink">{b.key}</span>
        {b.last != null && <span className="fig text-[13px] text-ink-2">{num(b.last)}</span>}
        <span className={cn("text-[13px] font-semibold", voteTone(b.bias))}>{biasWord(b.bias)}</span>
        <span className="fig text-[12px] text-ink-2">
          {b.agree} of {b.total} agree
        </span>
        <span className={cn("qt-cap text-[10.5px]", gradeTone(b))}>{b.grade}</span>
        <span className="fig ml-auto text-[11px] text-ink-3">
          {b.against} against · {b.neutral} neutral · brief capped at {b.max_conviction}/5
        </span>
      </div>

      <p className="mt-2 text-[12px] leading-[1.5] text-ink-2">{b.treatment}</p>
      {b.conflict && (
        <p className="mt-1.5 text-[11.5px] leading-[1.5] text-flip-fig">
          Macro leans {b.macro_lean}, structure accepts {b.structure_lean}: a conflict lowers conviction rather
          than picking a side. Trade the levels.
        </p>
      )}

      {/* ---- every vote, by layer ---- */}
      <dl className="mt-3 grid grid-cols-[14px_172px_minmax(0,1fr)] gap-x-2.5 gap-y-1.5 text-[11.5px] leading-[1.45]">
        {LAYERS.map((layer) => {
          const votes = b.votes.filter((v) => v.layer === layer.key);
          if (votes.length === 0) return null;
          return (
            <Fragment key={layer.key}>
              <dt className="col-span-3 mt-1.5 flex items-baseline gap-2 border-t border-ring/40 pt-1.5 first:mt-0 first:border-t-0 first:pt-0">
                <span className="eyebrow text-[9px]">{layer.label}</span>
                <span className="text-[10px] text-ink-3">{layer.what}</span>
              </dt>
              {votes.map((v) => (
                <Fragment key={v.key}>
                  <dd className={cn("text-center text-[10px]", voteTone(v.vote))} aria-label={v.vote}>
                    {voteGlyph(v.vote)}
                  </dd>
                  <dd className="min-w-0">
                    <span className={cn("block truncate", v.vote === "neutral" ? "text-ink-3" : "text-ink-2")}>
                      {v.label}
                    </span>
                    <span className="fig block text-[11px] leading-[1.35] text-ink" title={v.value}>
                      {v.value}
                    </span>
                  </dd>
                  <dd className="text-ink-3">{v.note}</dd>
                </Fragment>
              ))}
            </Fragment>
          );
        })}
        {b.context.length > 0 && (
          <>
            <dt className="col-span-3 mt-1.5 flex items-baseline gap-2 border-t border-ring/40 pt-1.5">
              <span className="eyebrow text-[9px]">Context</span>
              <span className="text-[10px] text-ink-3">what a move will find — never a vote</span>
            </dt>
            {b.context.map((c) => (
              <Fragment key={c.key}>
                <dd className="text-center text-[10px] text-ink-4">·</dd>
                <dd className="min-w-0">
                  <span className="block text-ink-2">{c.label}</span>
                  <span className="fig block text-[11px] leading-[1.35] text-ink" title={c.value}>
                    {c.value}
                  </span>
                </dd>
                <dd className="text-ink-3">{c.note}</dd>
              </Fragment>
            ))}
          </>
        )}
      </dl>

      <p className="mt-2.5 border-t border-ring pt-2 text-[11px] leading-[1.45] text-ink-3">
        Each read is a vote with its threshold stated — the stocks desk&apos;s own where one exists. Strong is six
        or more agreeing with at most one against; moderate four or more. A cash-market read votes from 09:30 ET
        and says so until then; gamma counts in New York and is a reference elsewhere. The Analysis brief is
        handed this count and may not be more confident than it.
      </p>
    </div>
  );
}
