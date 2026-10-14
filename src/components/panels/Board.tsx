"use client";

import type { Quote } from "@/types/terminal";
import { Module } from "@/components/ui/Module";
import { Skeleton } from "@/components/ui/Skeleton";
import { Tick } from "@/components/ui/Tick";
import { Sparkline } from "@/components/ui/Sparkline";
import { autoDp, dir, feedNote, num, quoteChg } from "@/lib/format";
import { cn } from "@/lib/cn";

/**
 * The board — one row per instrument.
 *
 * GROUPED, NOT SORTED BY MOVE. A board that reorders itself by the day's
 * biggest mover is unreadable: the row you are looking for is somewhere new
 * every twenty seconds, and muscle memory — which is most of what makes a
 * board fast — never forms. Fixed groups, fixed order inside them.
 *
 * THE RANGE BAR IS THE THIRD COLUMN WORTH HAVING. Last and change are the
 * obvious two; where the last print sits inside the day's range is the one
 * that says whether a +0.4% is holding its highs or has already given half of
 * it back, and it cannot be inferred from the other two.
 */

const GROUPS: { key: Quote["group"]; label: string }[] = [
  { key: "core", label: "The book" },
  { key: "global", label: "Global indices" },
  { key: "rates", label: "Rates" },
  { key: "vol", label: "Volatility" },
  { key: "fx", label: "FX" },
  { key: "energy", label: "Energy" },
  { key: "metals", label: "Metals & ags" },
  { key: "crypto", label: "Risk appetite" },
];

export function Board({
  quotes,
  ageMin,
  error,
  groups,
  title = "Board",
}: {
  quotes: Quote[];
  ageMin?: number | null;
  error?: string | null;
  /** Which groups this instance renders — the board is split across columns. */
  groups?: Quote["group"][];
  title?: string;
}) {
  const wanted = groups ?? GROUPS.map((g) => g.key);
  const shown = GROUPS.filter((g) => wanted.includes(g.key));

  return (
    <Module title={title} ageMin={ageMin} error={error} bodyClassName="px-0 py-0">
      {quotes.length === 0 ? (
        ageMin == null && !error ? (
          <Skeleton rows={6} label={`Loading ${title.toLowerCase()}`} />
        ) : (
          <p className="px-3 py-6 text-center text-[11px] text-ink-3">The quote feed returned nothing for these instruments.</p>
        )
      ) : (
        shown.map((g) => {
          const rows = quotes.filter((q) => q.group === g.key);
          if (!rows.length) return null;
          return (
            <div key={g.key}>
              <div className="qt-band border-y border-ring/40 bg-surface-2/50 px-3 py-1 first:border-t-0">
                <span className="eyebrow text-[9px]">{g.label}</span>
              </div>
              <ul>
                {rows.map((q) => (
                  <Row key={q.key} q={q} />
                ))}
              </ul>
            </div>
          );
        })
      )}
    </Module>
  );
}

/**
 * WHAT THE PRICE IS, ON THE ROW (audit, 2026-10-14). A delayed print carries a
 * small D, the convention on every retail screen; a closed market's last price
 * is dimmed, because it is not moving and must not read as if it were — and so
 * is one with no print for half an hour inside its hours (a lunch break, a
 * grain contract between sessions). The tooltip says which, how late and as
 * of when. A live row looks exactly as it always did.
 */
function Row({ q }: { q: Quote }) {
  const chg = quoteChg(q);
  const note = feedNote(q);
  const ink = q.feed === "closed" || q.feed === "stale" ? "text-ink-3" : "text-ink";
  return (
    <li className="hit flex items-center gap-2 px-3 py-[3px]" title={note ? `${q.name} — ${note}` : q.name}>
      <span className="fig w-[52px] shrink-0 truncate text-[11px] text-ink-2">{q.key}</span>
      <Tick
        value={num(q.last, q.last >= 1000 ? autoDp(q.last) : undefined)}
        className={cn("fig w-[74px] shrink-0 truncate text-right text-[11.5px]", ink)}
      />
      <span className="fig -ml-1 w-[7px] shrink-0 text-[8.5px] leading-none text-ink-4" aria-label={note ?? undefined}>
        {q.feed === "delayed" ? "D" : ""}
      </span>
      <Tick value={chg.text} className={cn("fig -ml-1 w-[62px] shrink-0 text-right text-[11px]", dir(chg.v))} />
      <RangeBar pos={q.range_pos} />
      <Sparkline data={q.spark} prev={q.prev} width={56} height={16} />
    </li>
  );
}

/**
 * Where the last print sits between the session's low and high.
 *
 * A MARK ON A TRACK, NOT A FILLED BAR. A fill reads as a quantity ("70% of
 * something"); this is a position, and the distinction matters because the
 * interesting states are the two ends. The track is drawn in the neutral
 * chrome hue and only the mark takes the direction colour, so a row that is
 * down but pinned at its highs still reads correctly.
 */
function RangeBar({ pos }: { pos: number | null }) {
  if (pos === null || !Number.isFinite(pos)) {
    return <span className="h-[3px] w-[44px] shrink-0" aria-hidden />;
  }
  const p = Math.max(0, Math.min(1, pos));
  const tone = p >= 0.75 ? "var(--call)" : p <= 0.25 ? "var(--put)" : "var(--ink-3)";
  return (
    <span
      className="relative h-[3px] w-[44px] shrink-0 rounded-full bg-ring"
      title={`${(p * 100).toFixed(0)}% of the day's range`}
    >
      <span
        className="absolute top-1/2 h-[7px] w-[2px] -translate-y-1/2 rounded-full"
        style={{ left: `calc(${p * 100}% - 1px)`, background: tone }}
      />
    </span>
  );
}
