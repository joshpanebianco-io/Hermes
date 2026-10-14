"use client";

import type { GammaEtf, IndexOptions } from "@/types/market";
import { Module } from "@/components/ui/Module";
import { Skeleton } from "@/components/ui/Skeleton";
import { Tick } from "@/components/ui/Tick";
import { TickerLogo } from "@/components/ui/TickerLogo";
import { num } from "@/lib/format";
import { cn } from "@/lib/cn";
import { FlowLine, Gap } from "@/components/market/shared";

/**
 * The index ETFs as an options trader reads them: where dealer hedging pins or
 * pushes SPY and QQQ (the gamma feed's levels, translated from the futures
 * into ETF prices), and what each chain says today — how rich the vol is
 * against what the index has been doing, the put skew, the move priced into
 * the front expiry, and which way today's volume is leaning.
 */

/* -------------------------------------------------------------------------- */
/* Dealer gamma — only when the gamma feed is up                               */
/* -------------------------------------------------------------------------- */

const REGIME_TIP = {
  POS: "Positive gamma: dealers hedge against the move — ranges hold, fades work, breakouts stall at the walls",
  NEG: "Negative gamma: dealers hedge with the move — ranges break, trends extend, walls give way",
} as const;

/** Rendered only when `gamma` carries rows; a gamma feed that is off leaves no trace. */
export function DealerGamma({ gamma }: { gamma: GammaEtf[] }) {
  return (
    <Module title="Dealer gamma" sub="in ETF prices" bodyClassName="px-0 py-0">
      {gamma.map((g) => (
        <GammaEtfRow key={g.etf} g={g} />
      ))}
    </Module>
  );
}

function GammaEtfRow({ g }: { g: GammaEtf }) {
  const pos = g.regime === "POS";
  const vsFlip = g.spot != null && g.flip != null ? g.spot - g.flip : null;
  // The ladder's span: the two walls, widened to keep spot and the flip on it.
  const pts = [g.put_wall, g.flip, g.call_wall, g.spot].filter((v): v is number => v != null);
  const lo = pts.length ? Math.min(...pts) : 0;
  const hi = pts.length ? Math.max(...pts) : 1;
  const span = hi - lo || 1;
  const at = (v: number) => `${4 + ((v - lo) / span) * 92}%`;
  return (
    <div className="border-b border-ring/40 px-3 py-2 last:border-b-0" title={g.note || undefined}>
      <div className="flex items-baseline gap-2">
        <span className="text-[12px] font-semibold text-ink">{g.etf}</span>
        <span className="fig text-[9.5px] text-ink-3">from {g.book}</span>
        {g.regime && (
          <span
            className={cn("qt-cap ml-auto inline-flex items-center gap-1.5 text-[9.5px]", pos ? "text-call-fig" : "text-put-fig")}
            title={REGIME_TIP[g.regime]}
          >
            <span aria-hidden className={cn("h-[6px] w-[6px]", pos ? "bg-call-fig" : "bg-put-fig")} />
            {pos ? "Positive" : "Negative"} <span className="normal-case">γ</span>
          </span>
        )}
      </div>

      {pts.length >= 2 && (
        <div className="relative mt-2.5 mb-1 h-[14px]" aria-hidden>
          <span className="absolute inset-x-0 top-1/2 h-px bg-ring" />
          {g.put_wall != null && <Mark left={at(g.put_wall)} cls="bg-put-fig" />}
          {g.call_wall != null && <Mark left={at(g.call_wall)} cls="bg-call-fig" />}
          {g.flip != null && <Mark left={at(g.flip)} cls="bg-flip-fig" />}
          {g.spot != null && (
            <span className="absolute top-0 h-full w-[2px] -translate-x-1/2 bg-ink" style={{ left: at(g.spot) }} />
          )}
        </div>
      )}

      <div className="grid grid-cols-3 gap-x-2 text-[10px]">
        <Level k="Put wall" v={g.put_wall} cls="text-put-fig" />
        <Level k="Flip" v={g.flip} cls="text-flip-fig" />
        <Level k="Call wall" v={g.call_wall} cls="text-call-fig" />
      </div>
      <p className="mt-1 text-[10px] text-ink-3">
        spot <Tick value={num(g.spot, 2)} className="fig text-ink" />
        {vsFlip != null && (
          <>
            {" "}
            · <span className={cn("fig", vsFlip >= 0 ? "up" : "down")}>{`${vsFlip >= 0 ? "+" : ""}${vsFlip.toFixed(2)}`}</span>{" "}
            {vsFlip >= 0 ? "above" : "below"} the flip
          </>
        )}
      </p>
    </div>
  );
}

function Mark({ left, cls }: { left: string; cls: string }) {
  return <span className={cn("absolute top-1/2 h-[7px] w-[7px] -translate-x-1/2 -translate-y-1/2", cls)} style={{ left }} />;
}

function Level({ k, v, cls }: { k: string; v: number | null; cls: string }) {
  return (
    <div className="min-w-0">
      <span className="qt-cap block text-[9px] text-ink-3">{k}</span>
      <Tick value={num(v, 2)} className={cn("fig text-[11.5px]", v == null ? "text-ink-3" : cls)} />
    </div>
  );
}

/* -------------------------------------------------------------------------- */
/* Index options — the three chains a stocks desk prices its day off          */
/* -------------------------------------------------------------------------- */

export function IndexOptionsPanel({ rows }: { rows: IndexOptions[] | null }) {
  return (
    <Module title="Index options" sub="SPY · QQQ · IWM chains" bodyClassName="px-0 py-0">
      {!rows ? (
        <Skeleton rows={6} label="Loading the index chains" />
      ) : rows.length === 0 ? (
        <Gap>No index chain yet — the delayed chains load a minute or two after a restart.</Gap>
      ) : (
        <>
          <div className={cn(CHAIN_GRID, "border-b border-ring/40 pt-1.5 pb-1")}>
            <span />
            <span className="qt-cap text-[9px] text-ink-3" title="Thirty-day implied volatility, interpolated from the chain">
              IV30
            </span>
            <span className="qt-cap text-[9px] text-ink-3" title="Implied over twenty-day realised: rich favours spreads or selling premium, cheap favours owning the option outright">
              IV/RV
            </span>
            <span className="qt-cap text-right text-[9px] text-ink-3" title="25-delta put IV minus 25-delta call IV, in vol points — what the market pays for downside over upside">
              Skew
            </span>
            <span className="qt-cap text-right text-[9px] text-ink-3" title="The front expiry's at-the-money straddle, as a share of spot">
              Front EM
            </span>
          </div>
          {rows.map((r) => (
            <IndexChain key={r.sym} r={r} />
          ))}
        </>
      )}
    </Module>
  );
}

/** Symbol · IV30 · IV/RV · skew · front expected move — one grid for the head and every row. */
const CHAIN_GRID = "grid grid-cols-[56px_minmax(0,0.8fr)_minmax(0,1.3fr)_minmax(0,0.7fr)_minmax(0,0.9fr)] items-baseline gap-x-2 px-3";

function IndexChain({ r }: { r: IndexOptions }) {
  const prem = r.premium?.toLowerCase() ?? null;
  const premText = prem === "rich" ? "text-flip-fig" : prem === "cheap" ? "text-call-fig" : "text-ink-3";
  return (
    <div className="hit border-b border-ring/40 py-1.5 last:border-b-0">
      <div className={cn(CHAIN_GRID, "text-[11px]")}>
        <span className="flex items-center gap-1.5 self-center text-[12px] font-semibold text-ink">
          <TickerLogo sym={r.sym} size={14} />
          {r.sym}
        </span>
        <Tick value={r.iv30 != null ? `${r.iv30.toFixed(1)}%` : "—"} className="fig text-ink" />
        <span className="min-w-0 truncate">
          <span className={cn("fig", prem === "rich" || prem === "cheap" ? premText : "text-ink")}>
            {r.iv_rv != null ? r.iv_rv.toFixed(2) : "—"}
          </span>
          {prem && <span className={cn("qt-cap ml-1.5 text-[9px]", premText)}>{prem}</span>}
        </span>
        <span className="fig text-right text-ink-2">{r.skew != null ? `${r.skew >= 0 ? "+" : ""}${r.skew.toFixed(1)}` : "—"}</span>
        <span className="fig text-right text-ink">{r.em_front_pct != null ? `±${r.em_front_pct.toFixed(2)}%` : "—"}</span>
      </div>
      <div className="mt-1 flex flex-wrap items-baseline gap-x-2 pr-3 pl-[58px] text-[10.5px]">
        {r.flow ? (
          <>
            <FlowLine f={r.flow} />
            {r.flow.vol_oi != null && (
              <span className="text-ink-3" title="Today's volume against open interest — above about 0.5 much of the trade is fresh positioning">
                vol/OI <span className="fig text-ink-2">{r.flow.vol_oi.toFixed(2)}</span>
              </span>
            )}
          </>
        ) : (
          <span className="text-ink-3">no flow read yet</span>
        )}
      </div>
    </div>
  );
}
