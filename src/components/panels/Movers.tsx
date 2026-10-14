"use client";

import { useState } from "react";
import type { IndexMovers } from "@/types/terminal";
import { Module } from "@/components/ui/Module";
import { Skeleton } from "@/components/ui/Skeleton";
import { TickerLogo } from "@/components/ui/TickerLogo";
import { Tick } from "@/components/ui/Tick";
import { pct } from "@/lib/format";
import { cn } from "@/lib/cn";
import { segItem } from "@/lib/seg";
import { oneOf, usePersisted } from "@/lib/usePersisted";

/**
 * The heavy names — what actually moved the index.
 *
 * RANKED BY CONTRIBUTION, NOT BY PERCENT CHANGE, and that is the whole point.
 * NQ is cap-weighted and its top nine names are about 43% of it, so on most
 * days two or three of them supply the move. A 6% move in a 0.3% weight is
 * noise; a 2% move in an 8% weight is the tape. Every figure here is weight
 * times return, in index percentage points.
 *
 * TWO VIEWS OF ONE TRUTH. The map is a weighted heatmap in the TradingView
 * idiom — tile AREA is index weight, tile COLOUR is the day's move — which
 * answers "what does the index look like right now" in one glance. The list
 * answers "what is doing it", ranked, with the arithmetic visible. Neither
 * replaces the other: a heatmap cannot show you that AMZN at −2.5% and TSLA at
 * +4.0% almost cancelled, and a list cannot show you that six of the top ten
 * are red.
 *
 * COLOUR IS THE MOVE, AREA IS THE WEIGHT — never both on one channel. Scaling
 * the tile by contribution would make a small name with a big move look heavy,
 * which is exactly the confusion the panel exists to remove.
 */

const VIEWS = [
  { key: "map", label: "Map" },
  { key: "list", label: "List" },
] as const;
type View = (typeof VIEWS)[number]["key"];

/** Beyond this the colour stops deepening — one outlier must not flatten the rest. */
const CAP_PCT = 3;

function tint(p: number | null): string {
  if (p == null) return "var(--surface-2)";
  const t = Math.min(Math.abs(p) / CAP_PCT, 1);
  // color-mix rather than opacity: a translucent tile would pick up whatever
  // is behind it and two identical moves would render differently depending
  // on where they landed in the grid.
  return `color-mix(in oklab, var(${p >= 0 ? "--call" : "--put"}) ${(
    12 + t * 62
  ).toFixed(0)}%, var(--surface-2))`;
}

export function Movers({
  indices,
  ageMin,
  error,
}: {
  indices: Record<string, IndexMovers>;
  ageMin?: number | null;
  error?: string | null;
}) {
  const keys = Object.keys(indices);
  const [sel, setSel] = usePersisted<string>("movers.index", "NQ", oneOf("NQ", "ES"));
  const [view, setView] = usePersisted<View>("movers.view", "map", oneOf("map", "list"));
  const active = indices[sel] ?? indices[keys[0]];
  const [hover, setHover] = useState<string | null>(null);

  return (
    <Module
      title="Index movers"
      sub={active ? `${active.covered_weight}% of ${active.index}` : undefined}
      ageMin={ageMin}
      error={error}
      bodyClassName="px-0 py-0"
      right={
        <div className="flex items-center gap-1.5">
          {keys.length > 1 && (
            <div className="seg">
              {keys.map((k) => (
                <button
                  key={k}
                  type="button"
                  onClick={() => setSel(k)}
                  {...segItem(k === sel, { className: "text-[10px] normal-case tracking-normal" })}
                >
                  {k}
                </button>
              ))}
            </div>
          )}
          <div className="seg">
            {VIEWS.map((v) => (
              <button
                key={v.key}
                type="button"
                onClick={() => setView(v.key)}
                {...segItem(v.key === view, { className: "text-[10px] normal-case tracking-normal" })}
              >
                {v.label}
              </button>
            ))}
          </div>
        </div>
      }
    >
      {!active || active.members.length === 0 ? (
        ageMin == null && !error ? (
          <Skeleton rows={4} label="Loading index movers" />
        ) : (
          <p className="px-3 py-5 text-center text-[11px] text-ink-3">
            No constituent data — weights come from the fund&rsquo;s own holdings file.
          </p>
        )
      ) : (
        <>
          {view === "map" ? (
            <Map m={active} hover={hover} setHover={setHover} />
          ) : (
            <List m={active} />
          )}
          <Net m={active} />
        </>
      )}
    </Module>
  );
}

/**
 * The weighted map.
 *
 * A FLEX WRAP WITH PROPORTIONAL WIDTHS, not a real squarified treemap. At this
 * size a proper treemap's virtue — exact area — buys nothing a reader can
 * measure, and it costs a layout pass that fights the column's own resizing.
 * Widths scale with the square root of weight so the ratio between NVDA and a
 * 0.4% name stays legible instead of making the tail invisible.
 */
function Map({
  m,
  hover,
  setHover,
}: {
  m: IndexMovers;
  hover: string | null;
  setHover: (s: string | null) => void;
}) {
  const shown = m.members.slice(0, 28);
  const total = shown.reduce((a, x) => a + Math.sqrt(x.weight), 0) || 1;

  return (
    <div className="flex flex-wrap gap-[2px] p-2">
      {shown.map((x) => {
        const w = (Math.sqrt(x.weight) / total) * 100;
        return (
          <div
            key={x.symbol}
            onMouseEnter={() => setHover(x.symbol)}
            onMouseLeave={() => setHover(null)}
            className={cn(
              "flex min-w-[46px] flex-col justify-center rounded-[3px] px-1 py-1.5 transition-transform",
              hover === x.symbol && "scale-[1.04]",
            )}
            style={{ width: `calc(${w.toFixed(2)}% - 2px)`, background: tint(x.pct) }}
            title={`${x.name} · ${x.weight}% of the index · ${pct(x.pct)} · contributed ${pct(
              x.contribution,
              3,
            )} to the index`}
          >
            <span className="fig truncate text-center text-[9.5px] leading-tight font-semibold text-ink">
              {x.symbol}
            </span>
            <Tick
              value={pct(x.pct, 1)}
              className="fig truncate text-center text-[9px] leading-tight text-ink/70"
            />
          </div>
        );
      })}
    </div>
  );
}

/** The same names, ranked by what they put into the index. */
function List({ m }: { m: IndexMovers }) {
  const shown = m.members.slice(0, 14);
  const max = Math.max(...shown.map((x) => Math.abs(x.contribution)), 0.01);
  return (
    <ul className="py-1">
      {shown.map((x) => {
        const w = (Math.abs(x.contribution) / max) * 50;
        const up = x.contribution >= 0;
        return (
          <li key={x.symbol} className="hit flex items-center gap-2 px-3 py-[3px]">
            <span className="fig flex w-[62px] shrink-0 items-center gap-1.5 text-[10.5px] text-ink-2">
              <TickerLogo sym={x.symbol} size={13} />
              {x.symbol}
            </span>
            <span className="fig w-[38px] shrink-0 text-right text-[9.5px] text-ink-3"
              title="Index weight">
              {x.weight.toFixed(1)}%
            </span>
            <span className="relative h-[8px] min-w-[40px] flex-1">
              <span
                className="absolute inset-y-0 left-1/2 w-px -translate-x-1/2 bg-ring"
                aria-hidden
              />
              <span
                className="absolute top-1/2 h-[5px] -translate-y-1/2 rounded-sm"
                style={{
                  left: up ? "50%" : `calc(50% - ${w}%)`,
                  width: `${w}%`,
                  background: up ? "var(--call)" : "var(--put)",
                  opacity: 0.85,
                }}
              />
            </span>
            <Tick
              value={pct(x.pct)}
              className={cn("fig w-[52px] shrink-0 text-right text-[10.5px]", up ? "up" : "down")}
            />
            <Tick
              value={pct(x.contribution, 3)}
              className="fig w-[54px] shrink-0 text-right text-[10px] text-ink-3"
              title="Weight × return — what this name put into the index"
            />
          </li>
        );
      })}
    </ul>
  );
}

/**
 * What the shown names add up to.
 *
 * Read beside the index's own change it answers the question the panel is
 * really for: how much of today is these names, and how much is everything
 * else.
 */
function Net({ m }: { m: IndexMovers }) {
  const up = m.net_contribution >= 0;
  return (
    <div className="border-t border-ring/40 px-3 py-1.5 text-[10px] leading-relaxed text-ink-3">
      <span>Top {m.members.length} names are </span>
      <span className="fig text-ink-3">{m.covered_weight}%</span>
      <span> of {m.index} and contributed </span>
      <Tick value={pct(m.net_contribution, 2)} className={cn("fig", up ? "up" : "down")} />
      <span> to it today.</span>
      {m.as_of && <span className="text-ink-3"> Weights as of {m.as_of}.</span>}
    </div>
  );
}
