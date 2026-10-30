"use client";

import { memo } from "react";
import type { Terminal as TerminalData } from "@/types/terminal";
import type { Desk } from "@/lib/tabs";
import { Board } from "@/components/panels/Board";
import { Gamma } from "@/components/panels/Gamma";
import { Sessions } from "@/components/panels/Sessions";
import { SessionRanges } from "@/components/panels/SessionRanges";
import { Volatility } from "@/components/panels/Volatility";
import { VolumeProfile } from "@/components/panels/VolumeProfile";
import { Levels } from "@/components/panels/Levels";
import { IndexLevels } from "@/components/panels/IndexLevels";
import { DeskSwitch } from "@/components/panels/DeskSwitch";
import { DriverStrip } from "@/components/shell/DriverStrip";
import { MarketStrip } from "@/components/market/MarketStrip";
import { BreadthPanel, ConvictionPanel, FuelPanel } from "@/components/market/TapePanels";
import { DealerGamma, IndexOptionsPanel } from "@/components/market/OptionsPanels";
import type { MarketFeed } from "@/lib/useMarket";
import { boardReady } from "@/lib/ready";
import { HelmLoader } from "@/components/ui/HelmLoader";
import { ageStep } from "@/lib/format";

/**
 * Structure — where price is, and how it is positioned. One tab for both
 * desks (lib/tabs.ts, 2026-10-30: "a separate tab … session ranges, volume
 * profile, gamma levels etc").
 *
 * BEHIND THE DESK SWITCH (owner, 2026-10-30, after a day with both halves
 * side by side: "i reckon we should have the toggle for structure"). The
 * switch is the one Analysis wears, remembered as one choice, so flipping
 * it here flips the note there too — it is "which desk am I reading", not a
 * setting per tab. Each half gets the whole page, three columns, which is
 * what the two halves beside each other could not give either of them.
 *
 * FUTURES. The driver board leads, as it led the futures Macro: per book,
 * which way the engine's count leans and how to treat it. Then price on the
 * left — the book, where price sits in each session box, value — the levels
 * ladder (the brief's, live, with VWAP, the opening range and today's opens)
 * and the seven gamma levels in the middle, and on the right the vol curve
 * that frames them and the session clock, reference you consult rather than
 * a figure you act on.
 *
 * STOCKS & OPTIONS. The tape strip leads — the count, how the options price
 * the day, how much is spent, breadth, what prints next — the way the old
 * Market tab opened. Then the index's own levels and dealer gamma in ETF
 * prices on the left, the tape count and breadth in the middle, the index
 * chains and fuel on the right.
 *
 * ONE LOADER FOR THE BOARD, as on Macro: the helm in the middle until every
 * source this page reads has reported once — see lib/ready.ts.
 */

const MBoard = memo(Board);
const MSessionRanges = memo(SessionRanges);
const MVolumeProfile = memo(VolumeProfile);
const MGamma = memo(Gamma);
const MVolatility = memo(Volatility);
const MSessions = memo(Sessions);
const MLevels = memo(Levels);
const MStrip = memo(MarketStrip);
const MConviction = memo(ConvictionPanel);
const MBreadth = memo(BreadthPanel);
const MFuel = memo(FuelPanel);
const MDealerGamma = memo(DealerGamma);
const MIndexOptions = memo(IndexOptionsPanel);

const NONE: never[] = [];
const EMPTY = {} as Record<string, never>;
// Hoisted: an array literal in JSX is a new prop every render and would defeat the memo.
const BOOK_GROUPS: React.ComponentProps<typeof Board>["groups"] = ["core"];

/** The sources this page reads — the board waits for each to have reported once. */
const SOURCES = ["quotes", "ranges", "profiles", "gex"];

const SUB = {
  futures: "NQ · ES · GC — price, value, the levels, gamma, the vol curve.",
  stocks: "SPY · QQQ · IWM — the index's levels, dealer gamma in ETF prices, the tape.",
} as const;

const GRID = "qt-board grid min-h-0 flex-1 grid-cols-1 gap-2 p-2 xl:grid-cols-3 xl:overflow-hidden";
const COL = "qt-col flex min-h-0 min-w-0 flex-col gap-2 xl:overflow-y-auto";

export function StructureBoard({
  data,
  market: feed,
  desk,
  onDesk,
}: {
  data: TerminalData;
  market: MarketFeed;
  desk: Desk;
  onDesk: (d: Desk) => void;
}) {
  const st = data.status ?? {};
  const raw = data.age_min ?? {};
  const age = (k: string) => ageStep(raw[k]) ?? undefined;
  const { ctx: market, failed } = feed;
  const ctx = market?.offline ? null : market;
  const loading = market === null && !failed;

  if (!boardReady(data, SOURCES, feed)) {
    return (
      <main className="flex min-h-0 flex-1 items-center justify-center">
        <HelmLoader label="Loading the desk" size={64} />
      </main>
    );
  }

  return (
    <main className="flex min-h-0 flex-1 flex-col overflow-y-auto xl:overflow-hidden">
      <DeskSwitch desk={desk} onDesk={onDesk} sub={SUB} />

      {desk === "futures" ? (
        <>
          <DriverStrip drivers={data.drivers} />
          <div className={GRID}>
            {/* ---- price ---------------------------------------------------- */}
            <div className={COL}>
              <MBoard title="The book" quotes={data.quotes ?? NONE} groups={BOOK_GROUPS} ageMin={age("quotes")} error={st.quotes?.ok === false ? st.quotes.error : null} />
              <MSessionRanges assets={data.ranges?.assets ?? EMPTY} ladders={data.ladders} expiry={data.expiry} ageMin={age("ranges")} error={st.ranges?.ok === false ? st.ranges.error : null} />
              <MVolumeProfile data={data.profiles} ladders={data.ladders} ageMin={age("profiles")} error={st.profiles?.ok === false ? st.profiles.error : null} />
            </div>
            {/* ---- the levels, and positioning ------------------------------ */}
            <div className={COL}>
              <MLevels ladders={data.ladders} ageMin={age("ranges")} error={st.ranges?.ok === false ? st.ranges.error : null} />
              <MGamma
                assets={data.gex?.assets ?? EMPTY}
                enabled={data.gex?.enabled ?? false}
                ageMin={age("gex")}
                error={st.gex?.ok === false ? st.gex.error : null}
                implied={data.volterm?.books}
                expiry={data.expiry}
              />
            </div>
            {/* ---- the regime, and the clock -------------------------------- */}
            <div className={COL}>
              <MVolatility vol={data.volterm} ageMin={age("quotes")} implied putcall={data.putcall} />
              {data.clock && <MSessions clock={data.clock} />}
            </div>
          </div>
        </>
      ) : (
        <>
          <MStrip ctx={market} failed={failed} />
          <div className={GRID}>
            {/* ---- the index, and how it is positioned ---------------------- */}
            <div className={COL}>
              <IndexLevels />
              {(ctx || loading) && ctx?.gamma && ctx.gamma.length > 0 && <MDealerGamma gamma={ctx.gamma} />}
            </div>
            {/* ---- is the tape worth trading with --------------------------- */}
            <div className={COL}>
              {(ctx || loading) && (
                <>
                  <MConviction c={ctx?.conviction ?? null} />
                  <MBreadth b={ctx?.breadth ?? null} />
                </>
              )}
            </div>
            {/* ---- what the options price, and how much is spent ------------ */}
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
        </>
      )}
    </main>
  );
}
