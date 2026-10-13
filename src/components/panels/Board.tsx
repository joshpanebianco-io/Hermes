"use client";

import type { Quote } from "@/types/terminal";
import { Module } from "@/components/ui/Module";
import { Tick } from "@/components/ui/Tick";
import { Sparkline } from "@/components/ui/Sparkline";
import { autoDp, dir, num, pct } from "@/lib/format";
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
        <p className="px-3 py-6 text-center text-[11px] text-ink-3">No quotes yet.</p>
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

function Row({ q }: { q: Quote }) {
  const d = dir(q.pct);
  return (
    <li className="hit flex items-center gap-2 px-3 py-[3px]">
      <span className="fig w-[52px] shrink-0 truncate text-[11px] text-ink-2" title={q.name}>
        {q.key}
      </span>
      <Tick
        value={num(q.last, q.last >= 1000 ? autoDp(q.last) : undefined)}
        className="fig w-[74px] shrink-0 truncate text-right text-[11.5px] text-ink"
      />
      <Tick value={pct(q.pct)} className={cn("fig w-[62px] shrink-0 text-right text-[11px]", d)} />
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
