"use client";

import { memo, useMemo } from "react";
import type { Terminal as TerminalData } from "@/types/terminal";
import { Wire } from "@/components/panels/Wire";
import { Board } from "@/components/panels/Board";
import { Rates } from "@/components/panels/Rates";
import { Calendar } from "@/components/panels/Calendar";
import { Earnings } from "@/components/panels/Earnings";
import { Movers } from "@/components/panels/Movers";
import { Fed } from "@/components/panels/Fed";
import { CrossAsset, PrintsFed, SectorPeers } from "@/components/market/SchedulePanels";
import type { MarketFeed } from "@/lib/useMarket";
import { useWatchlistEarnings } from "@/lib/useWatchlistEarnings";
import { boardReady } from "@/lib/ready";
import { PageLoader } from "@/components/ui/HelmLoader";
import { ageStep } from "@/lib/format";

/**
 * Macro — what is happening, and what is scheduled. One tab for both desks
 * (lib/tabs.ts, 2026-10-30).
 *
 * THREE COLUMNS, AND THE MIDDLE ONE IS THE WIRE. The layout encodes what this
 * page is for: live state on the left, news in the middle where the eye
 * rests, what is scheduled on the right. The futures Macro tab and the stocks
 * Market tab used to show these same panels in two different orders; this is
 * the one order, cut by the owner's principle that importance descends down a
 * column (2026-09-16), with what is live above what is scheduled.
 *
 * LEFT — what the market is doing. The CONSEQUENCE of the macro lead first,
 * because it is short and it is the read: which names carried the index.
 * Earnings under it since 2026-11-13 (owner: "move the earnings card to the
 * left and under index movers"), with the watchlist's names marked: the names
 * that carried the index, then the ones about to report. It was the fourth
 * card down the right column, under the calendar, the prints and the Fed
 * diary, and it is the one diary on this page that is about stocks.
 * Rates next, the one panel whose data is daily, because the curve and the
 * policy path are what the books are priced off. The macro board — VIX,
 * energy, rates, the dollar, metals, the global indices, crypto, with
 * day-range bars — is last for the reason it was last before: it is a screen
 * tall, and the header strip already carries its headline rows, so above the
 * others it would bury them.
 *
 * NO SECTORS AND NO BREADTH HERE SINCE 2026-11-13 (owner: "streamline the app
 * and make it have the most useful informaiton visible without clutter and
 * noise"). The column opened with a sector rotation panel and a breadth panel,
 * and each was a second, smaller copy of something with a page or a card of
 * its own: the sectors are the Sectors tab (the heat map, the industries, the
 * stocks in each) and the Dashboard's rotation row, and breadth is the
 * Dashboard's card, the same bars off the same read. Two panels down, the
 * movers open the column. (The rates were on screen under them without
 * scrolling until earnings came between the two the same day: with 19 reports
 * listed that card ran about 870px at 2560x1440, so the rates and the macro
 * board are a scroll down the column.)
 *
 * RIGHT — what the day is scheduled to throw at it. The calendar first,
 * because it is where macro lives on this screen: the print that just landed
 * and its surprise are the most important fact on a data day, and on a quiet
 * day the calendar is what says it is quiet. Today's prints against
 * consensus and the Fed path under it (the stocks desk's read of the same
 * day), then the Fed & Treasury diary and the sector peers reporting, and
 * last the cross-asset moves the names' drivers are read from.
 *
 * THE MARKET CONTEXT (prints, the Fed path, peers, cross-asset) is the
 * collector's, polled every twenty seconds by the Terminal and handed down.
 *
 * ONE LOADER, NOT ONE PER PANEL (owner, 2026-10-30: "instead of having
 * individual loading spinners for each module, lets just make it the whole
 * page have one loading spinner until everything loads"). While the
 * collector is still warming — a cold start, or the minute after a restart —
 * the board used to be a grid of nine helms, each panel waiting on its own
 * source. Now the board waits as one: the helm in the middle until every
 * source this page reads has reported once (lib/ready.ts), then the whole
 * page at once. A source that fails AFTER that still says so in its own
 * panel, which is the right place for it.
 */

const MWire = memo(Wire);
const MBoard = memo(Board);
const MRates = memo(Rates);
const MCalendar = memo(Calendar);
const MEarnings = memo(Earnings);
const MMovers = memo(Movers);
const MFed = memo(Fed);
const MPrintsFed = memo(PrintsFed);
const MCrossAsset = memo(CrossAsset);
const MPeers = memo(SectorPeers);

const NONE: never[] = [];
const EMPTY = {} as Record<string, never>;
// Hoisted: an array literal in JSX is a new prop every render and would defeat the memo.
const MACRO_GROUPS: React.ComponentProps<typeof Board>["groups"] = ["vol", "energy", "rates", "fx", "metals", "global", "crypto"];

/** The sources this page reads — the board waits for each to have reported once. */
const SOURCES = ["quotes", "wire", "calendar", "constituents", "rates", "fed", "auctions", "earnings"];

export function MacroBoard({ data, market: feed }: { data: TerminalData; market: MarketFeed }) {
  const st = data.status ?? {};
  const raw = data.age_min ?? {};
  const age = (k: string) => ageStep(raw[k]) ?? undefined;
  const { watch, extra } = useWatchlistEarnings();
  const { ctx: market, failed } = feed;
  // The context's panels show only when it answered.
  const ctx = market?.offline ? null : market;
  const loading = market === null && !failed;

  // The index-minded block plus the watchlist's own reports, once each.
  const earnings = useMemo(() => {
    const base = data.earnings ?? NONE;
    if (extra.length === 0) return base;
    const have = new Set(base.map((r) => `${r.date}:${r.symbol}`));
    const add = extra.filter((r) => !have.has(`${r.date}:${r.symbol}`));
    return [...base, ...add].sort((a, b) => a.date.localeCompare(b.date) || (b.market_cap ?? 0) - (a.market_cap ?? 0));
  }, [data.earnings, extra]);

  // Waiting is a card where the board will be (ui/HelmLoader PageLoader), inset as the
  // board's cards are under Luminous; Quiet gives the wait no paint or inset.
  if (!boardReady(data, SOURCES, feed)) {
    return (
      <main className="flex min-h-0 flex-1 flex-col lum:p-[var(--lum-gap)]">
        <PageLoader label="Loading the desk" size={64} />
      </main>
    );
  }

  // New York's box: the cash figures on this page are the last session's outside it.
  const cashOpen = data.clock?.boxes?.some((b) => b.key === "ny" && b.open) ?? true;

  return (
    <main className="qt-board grid min-h-0 flex-1 grid-cols-1 gap-2 overflow-y-auto p-2 xl:grid-cols-[minmax(300px,1fr)_minmax(420px,1.35fr)_minmax(320px,1.1fr)] xl:overflow-hidden">
      {/* ---- left: what the market is doing ------------------------------ */}
      <div className="qt-col flex min-h-0 min-w-0 flex-col gap-2 xl:overflow-y-auto">
        <MMovers indices={data.constituents?.indices ?? EMPTY} cashOpen={cashOpen} ageMin={age("constituents")} error={st.constituents?.ok === false ? st.constituents.error : null} />
        <MEarnings rows={earnings} watch={watch} today={data.expiry?.today ?? ""} ageMin={age("earnings")} error={st.earnings?.ok === false ? st.earnings.error : null} />
        <MRates rates={data.rates} pm={data.policy_meetings} ageMin={age("rates")} error={st.rates?.ok === false ? st.rates.error : null} />
        <MBoard title="Macro board" quotes={data.quotes ?? NONE} groups={MACRO_GROUPS} ageMin={age("quotes")} error={st.quotes?.ok === false ? st.quotes.error : null} />
      </div>

      {/* ---- middle: the wire -------------------------------------------- */}
      <div className="qt-col flex min-h-0 min-w-0 flex-col gap-2">
        <MWire items={data.wire ?? NONE} ageMin={age("wire")} error={st.wire?.ok === false ? st.wire.error : null} />
      </div>

      {/* ---- right: what is scheduled ------------------------------------ */}
      <div className="qt-col flex min-h-0 min-w-0 flex-col gap-2 xl:overflow-y-auto">
        <MCalendar rows={data.calendar ?? NONE} holidays={data.holidays ?? NONE} ageMin={age("calendar")} error={st.calendar?.ok === false ? st.calendar.error : null} />
        {(ctx || loading) && <MPrintsFed prints={ctx?.prints ?? NONE} fed={ctx?.fed ?? null} builtUtc={ctx?.built_utc ?? ""} loading={loading} />}
        <MFed
          rows={data.fed ?? NONE}
          auctions={data.auctions ?? NONE}
          today={data.expiry?.today ?? ""}
          ageMin={raw.fed == null ? age("auctions") : raw.auctions == null ? age("fed") : (ageStep(Math.max(raw.fed, raw.auctions)) ?? undefined)}
          error={st.fed?.ok === false ? st.fed.error : st.auctions?.ok === false ? st.auctions.error : null}
        />
        {(ctx || loading) && (
          <>
            <MPeers peers={ctx?.peers ?? null} />
            <MCrossAsset rows={ctx?.macro ?? null} />
          </>
        )}
      </div>
    </main>
  );
}
