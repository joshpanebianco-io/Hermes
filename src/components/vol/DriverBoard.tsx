"use client";

import { Fragment } from "react";
import type { DriverBook, DriverVote } from "@/types/terminal";
import { Popover } from "@/components/ui/Popover";
import { liveLine, scoreText } from "@/lib/bias";
import { num } from "@/lib/format";
import { cn } from "@/lib/cn";

/**
 * The driver board's long form — every read behind a book's score, by family,
 * with its figure and its reason, then the context rows that never vote and
 * one line on how to treat it.
 *
 * THE FUTURES DESK'S TAPE COUNT (owner, 2026-10-22: "do everything you
 * recommend"), WEIGHED (owner, 2026-11-05: "do what you recommend"). This panel
 * is the server's board (drivers.py, bias.py) printed: the words are the engine's,
 * the thresholds the stocks desk's own where one exists, and the panel adds
 * nothing — it opens from the strip the way every VIX figure opens the bands.
 * A read that cannot vote at this hour is dimmed and marked, because it is not the
 * same thing as a flat one.
 */

export const voteTone = (v: DriverVote["vote"] | DriverBook["bias"]) =>
  v === "long" ? "text-call-fig" : v === "short" ? "text-put-fig" : "text-ink-3";
export const voteGlyph = (v: DriverVote["vote"]) => (v === "long" ? "▲" : v === "short" ? "▼" : "–");

/** One read in the long form: its side, or a dot when it cannot vote at this hour. */
function Read({ v }: { v: DriverVote }) {
  const off = v.live === false;
  return (
    <>
      <dd className={cn("text-center text-[10px]", off ? "text-ink-4" : voteTone(v.vote))} aria-label={off ? "cannot vote" : v.vote}>
        {off ? "·" : voteGlyph(v.vote)}
      </dd>
      <dd className="min-w-0">
        <span className={cn("block truncate", off ? "text-ink-4" : v.vote === "neutral" ? "text-ink-3" : "text-ink-2")}>{v.label}</span>
        <span className={cn("fig block text-[11px] leading-[1.35]", off ? "text-ink-3" : "text-ink")} title={v.value}>
          {v.value}
        </span>
      </dd>
      <dd className={off ? "text-ink-4" : "text-ink-3"}>{v.note}</dd>
    </>
  );
}

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
      title="Click for every read behind the score and how to treat it"
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
        <span className={cn("fig text-[13px] font-semibold", voteTone(b.bias))}>{scoreText(b.score)}</span>
        <span className={cn("qt-cap text-[10.5px]", gradeTone(b))}>{b.grade}</span>
        {b.conflict && <span className="qt-cap text-[10.5px] text-flip-fig">conflict</span>}
        <span className="fig ml-auto text-[11px] text-ink-3">brief capped at {b.max_conviction}/5</span>
      </div>
      <p className="fig mt-1.5 text-[11px] text-ink-3">
        {liveLine(b)} · {b.agree} agree · {b.against} against · {b.neutral} flat · {b.cannot_vote} cannot vote yet
      </p>

      <p className="mt-2 text-[12px] leading-[1.5] text-ink-2">{b.treatment}</p>

      {/* ---- every read, by family, heaviest first ---- */}
      <dl className="mt-3 grid grid-cols-[14px_172px_minmax(0,1fr)] gap-x-2.5 gap-y-1.5 text-[11.5px] leading-[1.45]">
        {b.families.map((f) => {
          const votes = b.votes.filter((v) => v.family === f.key);
          if (votes.length === 0) return null;
          return (
            <Fragment key={f.key}>
              <dt className="col-span-3 mt-1.5 flex items-baseline gap-2 border-t border-ring/40 pt-1.5 first:mt-0 first:border-t-0 first:pt-0">
                <span className="eyebrow text-[9px]">{f.label}</span>
                <span className="text-[10px] text-ink-3">{f.weight > 0 ? `weight ${f.weight}` : "no weight this session"}</span>
                <span className={cn("fig ml-auto text-[11px]", f.score == null ? "text-ink-4" : f.score > 0 ? "text-call-fig" : f.score < 0 ? "text-put-fig" : "text-ink-3")}>
                  {f.score == null ? "cannot vote yet" : scoreText(f.score)}
                </span>
              </dt>
              {votes.map((v) => (
                <Fragment key={v.key}>
                  <Read v={v} />
                </Fragment>
              ))}
            </Fragment>
          );
        })}
        {b.votes
          .filter((v) => !v.family)
          .map((v) => (
            <Fragment key={v.key}>
              <dt className="col-span-3 mt-1.5 flex items-baseline gap-2 border-t border-ring/40 pt-1.5">
                <span className="eyebrow text-[9px]">{v.label}</span>
                {/* Each says why it is not a side: event risk lowers the ceiling, dealer gamma
                    says how far a move runs (it voted long above the flip until 2026-11-12). */}
                <span className="text-[10px] text-ink-3">{v.aside ?? "never a side: on the tape, it lowers the ceiling a notch"}</span>
              </dt>
              <dd className="text-center text-[10px] text-ink-4">·</dd>
              <dd className="min-w-0">
                <span className="fig block text-[11px] leading-[1.35] text-ink" title={v.value}>
                  {v.value}
                </span>
              </dd>
              <dd className="text-ink-3">{v.note}</dd>
            </Fragment>
          ))}
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
        The score runs from -100 to +100: each family&apos;s net read, weighed for the session, over the reads
        that can vote now. Strong is 50 or more with at least 60% of the weight live, moderate 30, weak 10; a
        conflict between macro and structure takes a notch off. The weights are a judgement, not a fit to
        outcomes. A read marked with a dot cannot vote at this hour, which is not the same as a flat one. The
        written brief is handed this score and may not be more confident than it.
      </p>
    </div>
  );
}
