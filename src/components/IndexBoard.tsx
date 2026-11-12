"use client";

import { memo } from "react";
import type { Terminal as TerminalData } from "@/types/terminal";
import { Volatility } from "@/components/panels/Volatility";
import { IndexLevels } from "@/components/panels/IndexLevels";
import { MarketStrip } from "@/components/market/MarketStrip";
import { BreadthPanel, ConvictionPanel, FuelPanel } from "@/components/market/TapePanels";
import { DealerGamma, IndexOptionsPanel } from "@/components/market/OptionsPanels";
import type { MarketFeed } from "@/lib/useMarket";
import { ageStep } from "@/lib/format";

/**
 * Index — SPY, QQQ and IWM against their own levels, how they are positioned, and
 * whether the tape is worth trading with. The Scanner's view since 2026-11-10, when
 * Structure's futures half became the Futures section (owner: "a seperate futures
 * section"): this half is the stocks desk's, so it sits with the stocks desk's pages.
 *
 * Three columns, as on Structure: the index and its gamma in ETF prices; the tape's
 * conviction and breadth; what the options price and how much of it is spent.
 */

const MStrip = memo(MarketStrip);
const MConviction = memo(ConvictionPanel);
const MBreadth = memo(BreadthPanel);
const MFuel = memo(FuelPanel);
const MDealerGamma = memo(DealerGamma);
const MIndexOptions = memo(IndexOptionsPanel);
const MVolatility = memo(Volatility);

const GRID = "qt-board grid flex-1 grid-cols-1 gap-2 p-2 xl:min-h-0 xl:grid-cols-3 xl:overflow-hidden";
// Shrinkable only side by side: stacked, a column that shrinks spills into the next one.
const COL = "qt-col flex min-w-0 flex-col gap-2 xl:min-h-0 xl:overflow-y-auto";

export function IndexBoard({ data, market: feed }: { data: TerminalData; market: MarketFeed }) {
  const raw = data.age_min ?? {};
  const age = (k: string) => ageStep(raw[k]) ?? undefined;
  const { ctx: market, failed } = feed;
  const ctx = market?.offline ? null : market;
  const loading = market === null && !failed;
  return (
    <div className="flex min-h-0 flex-1 flex-col overflow-y-auto xl:overflow-hidden">
      <MStrip ctx={market} failed={failed} />
      <div className={GRID}>
        <div className={COL}>
          <IndexLevels />
          {(ctx || loading) && ctx?.gamma && ctx.gamma.length > 0 && <MDealerGamma gamma={ctx.gamma} />}
        </div>
        <div className={COL}>
          {(ctx || loading) && (
            <>
              <MConviction c={ctx?.conviction ?? null} />
              <MBreadth b={ctx?.breadth ?? null} />
            </>
          )}
        </div>
        <div className={COL}>
          {(ctx || loading) && (
            <>
              <MIndexOptions rows={ctx?.index_options ?? null} />
              <MFuel fuel={ctx?.fuel ?? null} />
            </>
          )}
          <MVolatility vol={data.volterm} ageMin={age("quotes")} putcall={data.putcall} />
        </div>
      </div>
    </div>
  );
}
