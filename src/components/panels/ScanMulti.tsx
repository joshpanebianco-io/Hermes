"use client";

import { useEffect, useMemo } from "react";
import type { ScanRow, ScanSession } from "@/types/scanner";
import { ScanChart, type ChartPrefs } from "@/components/panels/ScanChart";
import { emBand, setupLabel, sideHue } from "@/components/panels/ScanDetail";
import { Menu } from "@/components/panels/ScanWide";
import { TickerLogo } from "@/components/ui/TickerLogo";
import { Tick } from "@/components/ui/Tick";
import { cn } from "@/lib/cn";
import { dir, num, pct } from "@/lib/format";
import { CHART_SLOTS, fillSlots, placeIn, sameSlots, type HeldSlots } from "@/lib/multiChart";
import { segItem } from "@/lib/seg";
import { openTicker } from "@/lib/ticker";

/**
 * Multicharts — six of the list's first ten names as live charts, three across and two
 * down (owner, 2026-11-12: "displays multiple charts from the top 10 ... maybe start with
 * 6 - lay it out so its 3 columns 2 rows etc and then have the options to change what is
 * displayed in those 6 charts from the top 10"). One of the Stocks tab's views since
 * 2026-11-13, the tab after Game plan (lib/tabs.ts); it began as a button on the Setups
 * chip bar. The ten are the Scanner list's first ten (Scanner.tsx `pool`): most of them
 * are names the engine does not track until the pool promotes them, and such a chart is
 * read on the request (collector `ensure_adhoc`: about half a second the first time,
 * then the held bars, read again at most once a minute).
 *
 * SIX, BECAUSE THAT IS WHAT STILL READS. Measured the day it was built, the candles of
 * each chart get 772 by 512 pixels on the 2560 screen and 566 by 348 on a 1920 one: room
 * for the levels, the wave and a retest. Nine on the 1920 screen would be about 566 by
 * 210, which is a sparkline. The other four of the ten are one click away, in each
 * chart's Change menu.
 *
 * THE CHARTS HAVE THE PAGE. The Setups stat row is not drawn over them (Scanner.tsx) and
 * the bar over them is one line, the charts' own toolbar: on a 1920 screen a stat row and
 * a second bar took 58 pixels off every chart's height.
 *
 * EACH CHART IS THE SLIDE-OUT'S OWN (ScanChart): the same bars, levels, wave, VWAP and
 * signals, the last candle moving on the stream. What it gives up is its toolbar: the
 * timeframe and the indicators are set once for all six, from the bar over the page
 * (ChartControls, compact), so a chart's head has room to say what it is: its rank among
 * the ten, the name, the price and the day's move, the side and score, the setup in a
 * few words.
 *
 * THE NAME OPENS THE SLIDE-OUT, as a name does everywhere else on the terminal; Change
 * picks another of the ten for that chart. Which name holds which chart, and why a chart
 * does not follow the rank, is lib/multiChart.ts.
 *
 * WHAT IT COSTS THE COLLECTOR, measured 2026-11-12 with the market shut: a chart's bars
 * are 30 ms to build and are asked for every fifteen seconds in the session, its tick is
 * 1.5 ms every second. Six of them are about two per cent of one core. The one-minute
 * views are the exception: each is a download made on the request (300 to 600 ms).
 */

const CELL = "qt-card flex min-h-0 min-w-0 flex-col overflow-hidden bg-bg";

export function ScanMulti({
  pool,
  listKey,
  what,
  held,
  onHeld,
  prefs,
  session,
  open,
}: {
  /** The list's first ten, in its own order: what the six are drawn from. */
  pool: ScanRow[];
  /** Which list that is (the trading day): held names apply to it alone. */
  listKey: string;
  /** The ten in words, for the Change menu: "the top 10". */
  what: string;
  held: HeldSlots;
  onHeld: (h: HeldSlots) => void;
  /** The one set of chart choices all six follow. */
  prefs: ChartPrefs;
  session: ScanSession;
  /** The name open in the slide-out, lit on its chart. */
  open: string | null;
}) {
  const names = useMemo(() => pool.map((r) => r.sym), [pool]);
  const slots = useMemo(() => fillSlots(held.key === listKey ? held.slots : [], names), [held, listKey, names]);

  // Written down as it changes, so a chart that was given to another name keeps it
  // when the first one comes back into the ten.
  useEffect(() => {
    if (slots.length === 0) return;
    if (held.key !== listKey || !sameSlots(held.slots, slots)) onHeld({ key: listKey, slots });
  }, [held, listKey, slots, onHeld]);

  if (pool.length === 0) {
    return (
      <div className={cn(CELL, "flex-1 items-center justify-center")}>
        <p className="max-w-[520px] px-6 py-8 text-center text-[12px] leading-[1.5] text-ink-3">No name on the list has a score to chart yet.</p>
      </div>
    );
  }

  const at = new Map(pool.map((r, i) => [r.sym, { r, rank: i + 1 }]));
  return (
    // Two rows of three where there is room, each at least tall enough for its Change
    // menu to open inside it; narrower, two across and then one, and the page scrolls.
    <div className="qt-multi grid min-h-0 flex-1 auto-rows-[minmax(320px,1fr)] grid-cols-1 gap-px overflow-y-auto bg-ring md:grid-cols-2 xl:grid-cols-3 lum:gap-[var(--lum-gap)] lum:bg-transparent">
      {Array.from({ length: CHART_SLOTS }, (_, i) => {
        const sym = slots[i];
        const e = sym ? at.get(sym) : undefined;
        if (!sym || !e) {
          return (
            <div key={`none-${i}`} className={cn(CELL, "items-center justify-center")}>
              {i === slots.length && <p className="px-6 text-center text-[12px] text-ink-3">Only {slots.length} on the list.</p>}
            </div>
          );
        }
        // Keyed by the name, not the place: two charts that trade places are moved, not
        // drawn again from nothing.
        return (
          <section key={sym} aria-label={`Chart ${i + 1}, ${sym}`} className={CELL}>
            <ScanChart
              sym={sym}
              state={e.r.lvl_state}
              em={emBand(e.r)}
              prefs={prefs}
              head={
                <Head
                  r={e.r}
                  rank={e.rank}
                  index={i}
                  pool={pool}
                  slots={slots}
                  what={what}
                  session={session}
                  on={open === sym}
                  onPlace={(s) => onHeld({ key: listKey, slots: placeIn(slots, i, s) })}
                />
              }
            />
          </section>
        );
      })}
    </div>
  );
}

const arrow = (side: ScanRow["score"]["side"]) => (side === "long" ? "▲" : side === "short" ? "▼" : "·");

/** One chart's head: what it is on the left (a click opens the slide-out), Change on the right. */
function Head({
  r,
  rank,
  index,
  pool,
  slots,
  what,
  session,
  on,
  onPlace,
}: {
  r: ScanRow;
  rank: number;
  index: number;
  pool: ScanRow[];
  slots: string[];
  what: string;
  session: ScanSession;
  on: boolean;
  onPlace: (sym: string) => void;
}) {
  const side = r.score.side;
  return (
    <>
      <button
        type="button"
        onClick={() => openTicker(r.sym)}
        title={`Open ${r.sym}${r.name ? ` (${r.name})` : ""}: the full chart, the setup, the options and the news`}
        className={cn("hit -ml-1.5 flex min-w-0 flex-1 items-center gap-2 rounded-[4px] px-1.5 py-[3px] text-left", on && "bg-surface-2")}
      >
        <span className="fig w-[14px] shrink-0 text-right text-[10.5px] text-ink-3" title={`Number ${rank} of ${what}`}>
          {rank}
        </span>
        <TickerLogo sym={r.sym} size={18} className="shrink-0" />
        <span className="shrink-0 text-[14px] leading-none font-semibold text-ink">{r.sym}</span>
        <Tick value={num(r.last)} className="fig shrink-0 text-[12.5px] text-ink-2" />
        <Tick value={pct(r.chg_pct)} className={cn("fig shrink-0 text-[12px]", dir(r.chg_pct))} />
        {r.ext_pct != null && (
          <span className="fig shrink-0 text-[11px] text-ink-3" title={session === "pre" ? "Pre-market, against the previous close" : "After hours, against the close"}>
            {session === "pre" ? "pre" : "post"} <span className={dir(r.ext_pct)}>{pct(r.ext_pct)}</span>
          </span>
        )}
        <span className={cn("fig flex shrink-0 items-center gap-1 text-[12px]", side ? sideHue(side) : "text-ink-3")} title={`${side ?? "No side"} · score ${r.score.total} of 100, a heuristic rank and not a probability`}>
          <span className="text-[9px]">{arrow(side)}</span>
          {r.score.total}
        </span>
        <span className="min-w-0 truncate text-[11.5px] text-ink-3" title={r.setup.note || undefined}>
          {setupLabel(r, true)}
        </span>
      </button>
      <Menu
        width={272}
        label={<span className="text-[10.5px]">Change</span>}
        title={`Show another of ${what} on this chart. A chart keeps its name until you change it or the name leaves the ten; then the best one not on screen takes its place.`}
      >
        {(close) => (
          <div>
            <p className="qt-cap mb-1 text-[10px] text-ink-3">
              Chart {index + 1} · from {what}
            </p>
            <span className="seg flex-col items-stretch" role="group" aria-label={`The name on chart ${index + 1}`}>
              {pool.map((p, k) => {
                const shown = slots.indexOf(p.sym);
                const here = p.sym === r.sym;
                return (
                  <button
                    key={p.sym}
                    type="button"
                    aria-pressed={here}
                    onClick={() => {
                      onPlace(p.sym);
                      close();
                    }}
                    {...segItem(here, { className: "justify-between gap-3" })}
                  >
                    <span className="flex items-center gap-2">
                      <span className="fig w-[14px] text-right text-[10.5px] text-ink-3">{k + 1}</span>
                      <span className={cn("w-[10px] text-[10px]", p.score.side ? sideHue(p.score.side) : "text-ink-3")}>{arrow(p.score.side)}</span>
                      <span>{p.sym}</span>
                      <span className="fig text-[10.5px] text-ink-3">{p.score.total}</span>
                    </span>
                    <span className="text-[10.5px] text-ink-3">{here ? "on this chart" : shown >= 0 ? `swap with chart ${shown + 1}` : ""}</span>
                  </button>
                );
              })}
            </span>
          </div>
        )}
      </Menu>
    </>
  );
}
