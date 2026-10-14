"use client";

import { memo, useEffect, useMemo, useState } from "react";
import type { EarningsRow, Terminal as TerminalData } from "@/types/terminal";
import type { ScannerPayload } from "@/types/scanner";
import { Wire } from "@/components/panels/Wire";
import { Rates } from "@/components/panels/Rates";
import { Rotation } from "@/components/panels/Rotation";
import { Calendar } from "@/components/panels/Calendar";
import { Earnings } from "@/components/panels/Earnings";
import { Movers } from "@/components/panels/Movers";
import { Volatility } from "@/components/panels/Volatility";
import { MarketStrip } from "@/components/market/MarketStrip";
import { BreadthPanel, ConvictionPanel, FuelPanel } from "@/components/market/TapePanels";
import { DealerGamma, IndexOptionsPanel } from "@/components/market/OptionsPanels";
import { CrossAsset, PrintsFed, SectorPeers } from "@/components/market/SchedulePanels";
import { useMarket } from "@/lib/useMarket";
import { ageStep } from "@/lib/format";

/**
 * The stocks desk's Market tab — the shared macro panels, composed for
 * someone trading single names and index ETFs in New York (owner instruction,
 * 2026-10-13: the review's desk split, "shared by both: the wire, the economic
 * calendar, VIX / rates / dollar, sector rotation").
 *
 * THE SAME PANELS, A DIFFERENT READING ORDER. Left is the weather an options
 * trade is priced in — the vol curve, which sectors are being bought, which
 * names carried the index; the wire stays in the middle where the eye rests;
 * right is what is scheduled — the US calendar that moves stocks, the
 * earnings that touch the watchlist, and the curve that leans on growth.
 * Nothing here is computed differently from the futures Terminal; only what
 * leads, and what the calendar and earnings filter for.
 *
 * THE WATCHLIST COMES FROM THE SCANNER, fetched only while this tab is open:
 * its names mark the earnings panel, and its smaller names' reports — which the
 * collector keeps out of the index-minded earnings block — are added back here.
 *
 * THE CONVICTION BOARD (owner instruction, 2026-10-14: "make sure in the market
 * tab we have everything that is worth having that helps add more context and
 * confidence to stock and options"). The collector's market context — polled
 * every twenty seconds, and only while this tab is mounted — puts the tape's
 * count on top: which side, how many of the signals agree, how far the options
 * price the day and how much of it is spent, how broad the move is and what
 * prints next. Under it, the left column says whether the tape is worth
 * trading with (the votes, breadth, fuel, dealer gamma, the index chains, then
 * the vol curve, rotation and the names carrying the index); the right says
 * what the day is scheduled to throw at it (the prints against consensus and
 * the Fed, the cross-asset moves, the calendar, earnings and the sector peers
 * reporting, the curve). A collector without the context leaves those panels
 * out and says so in the strip; the terminal's own panels carry on.
 */

const MVolatility = memo(Volatility);
const MRotation = memo(Rotation);
const MMovers = memo(Movers);
const MWire = memo(Wire);
const MCalendar = memo(Calendar);
const MEarnings = memo(Earnings);
const MRates = memo(Rates);
const MStrip = memo(MarketStrip);
const MConviction = memo(ConvictionPanel);
const MBreadth = memo(BreadthPanel);
const MFuel = memo(FuelPanel);
const MGamma = memo(DealerGamma);
const MIndexOptions = memo(IndexOptionsPanel);
const MPrintsFed = memo(PrintsFed);
const MCrossAsset = memo(CrossAsset);
const MPeers = memo(SectorPeers);

const NONE: never[] = [];
const EMPTY = {} as Record<string, never>;
const WATCH_POLL_SEC = 60;

export function MarketBoard({ data }: { data: TerminalData }) {
  const st = data.status ?? {};
  const raw = data.age_min ?? {};
  const age = (k: string) => ageStep(raw[k]) ?? undefined;
  const { watch, extra } = useWatchlistEarnings();
  const { ctx: market, failed } = useMarket();
  // The context's panels show only when it answered; offline, the strip says why.
  const ctx = market?.offline ? null : market;
  const loading = market === null && !failed;

  // The index-minded block plus the watchlist's own reports, once each.
  const earnings = useMemo(() => {
    const base = data.earnings ?? NONE;
    if (extra.length === 0) return base;
    const have = new Set(base.map((r) => `${r.date}:${r.symbol}`));
    const add = extra.filter((r) => !have.has(`${r.date}:${r.symbol}`));
    return [...base, ...add].sort(
      (a, b) => a.date.localeCompare(b.date) || (b.market_cap ?? 0) - (a.market_cap ?? 0),
    );
  }, [data.earnings, extra]);

  return (
    <main className="flex min-h-0 flex-1 flex-col overflow-y-auto xl:overflow-hidden">
      <MStrip ctx={market} failed={failed} />

      <div className="qt-board grid min-h-0 flex-1 grid-cols-1 gap-2 p-2 xl:grid-cols-[minmax(300px,1fr)_minmax(420px,1.35fr)_minmax(320px,1.1fr)] xl:overflow-hidden">
        {/* ---- left: is the tape worth trading with ------------------------- */}
        <div className="qt-col flex min-h-0 min-w-0 flex-col gap-2 xl:overflow-y-auto">
          {(ctx || loading) && (
            <>
              <MConviction c={ctx?.conviction ?? null} />
              <MBreadth b={ctx?.breadth ?? null} />
              <MFuel fuel={ctx?.fuel ?? null} />
              {ctx?.gamma && ctx.gamma.length > 0 && <MGamma gamma={ctx.gamma} />}
              <MIndexOptions rows={ctx?.index_options ?? null} />
            </>
          )}
          <MVolatility vol={data.volterm} ageMin={age("quotes")} />
          <MRotation
            rows={data.sectors ?? NONE}
            ageMin={age("sectors")}
            error={st.sectors?.ok === false ? st.sectors.error : null}
          />
          <MMovers
            indices={data.constituents?.indices ?? EMPTY}
            ageMin={age("constituents")}
            error={st.constituents?.ok === false ? st.constituents.error : null}
          />
        </div>

        {/* ---- middle: the wire ---------------------------------------------- */}
        <div className="qt-col flex min-h-0 min-w-0 flex-col gap-2">
          <MWire items={data.wire ?? NONE} ageMin={age("wire")} error={st.wire?.ok === false ? st.wire.error : null} />
        </div>

        {/* ---- right: what is scheduled, and what it leans on ---------------- */}
        <div className="qt-col flex min-h-0 min-w-0 flex-col gap-2 xl:overflow-y-auto">
          {(ctx || loading) && (
            <>
              <MPrintsFed prints={ctx?.prints ?? NONE} fed={ctx?.fed ?? null} builtUtc={ctx?.built_utc ?? ""} loading={loading} />
              <MCrossAsset rows={ctx?.macro ?? null} />
            </>
          )}
          <MCalendar
            rows={data.calendar ?? NONE}
            scope="stocks"
            ageMin={age("calendar")}
            error={st.calendar?.ok === false ? st.calendar.error : null}
          />
          <MEarnings
            rows={earnings}
            watch={watch}
            today={data.expiry?.today ?? ""}
            ageMin={age("earnings")}
            error={st.earnings?.ok === false ? st.earnings.error : null}
          />
          {(ctx || loading) && <MPeers peers={ctx?.peers ?? null} />}
          <MRates
            rates={data.rates}
            pm={data.policy_meetings}
            ageMin={age("rates")}
            error={st.rates?.ok === false ? st.rates.error : null}
          />
        </div>
      </div>
    </main>
  );
}

const NO_WATCH: ReadonlySet<string> = new Set();

/**
 * The scanner's watchlist, and the earnings its names carry — the smaller
 * names' reports are not in the terminal's earnings block, which is about what
 * moves an index. Polled once a minute while the Market tab is mounted; a dead
 * collector simply leaves the last answer (or nothing) in place.
 */
function useWatchlistEarnings(): { watch: ReadonlySet<string>; extra: EarningsRow[] } {
  const [state, setState] = useState<{ watch: ReadonlySet<string>; extra: EarningsRow[] }>({
    watch: NO_WATCH,
    extra: NONE,
  });
  useEffect(() => {
    let live = true;
    const load = async () => {
      try {
        const r = await fetch("/api/scanner", { cache: "no-store" });
        const d = (await r.json()) as ScannerPayload;
        if (!live || d.offline) return;
        const extra: EarningsRow[] = d.rows
          .filter((x) => x.ok && x.earnings)
          .map((x) => ({
            symbol: x.sym,
            name: x.name ?? x.sym,
            date: x.earnings!.date,
            when: x.earnings!.when,
            eps_forecast: x.earnings!.eps_forecast,
            eps_actual: x.earnings!.eps_actual,
            surprise_pct: x.earnings!.surprise_pct,
            market_cap: null,
            bellwether: false,
          }));
        setState({ watch: new Set(d.watchlist), extra });
      } catch {
        /* keep what we have */
      }
    };
    void load();
    const id = setInterval(load, WATCH_POLL_SEC * 1000);
    return () => {
      live = false;
      clearInterval(id);
    };
  }, []);
  return state;
}
