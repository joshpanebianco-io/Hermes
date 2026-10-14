"use client";

import type { Fuel, MarketCtx, Print } from "@/types/market";
import { Tick } from "@/components/ui/Tick";
import { inMin } from "@/lib/format";
import { cn } from "@/lib/cn";
import { HelmLoader } from "@/components/ui/HelmLoader";
import {
  ConvictionBar,
  SplitBar,
  biasWord,
  gradeText,
  readText,
  sideText,
  printClock,
  stateText,
  votesTip,
} from "@/components/market/shared";

/**
 * The Market tab's top line — the four answers a stocks trader wants before
 * reading anything else: which side the tape is paying and how many signals
 * agree, how far the options price the day, how much of that the index has
 * already travelled, whether the move is broad, and what is printing next.
 *
 * Every figure is the collector's; a block it could not fill prints a dash and
 * says why underneath, never a number this page made up.
 */
export function MarketStrip({ ctx, failed }: { ctx: MarketCtx | null; failed?: string | null }) {
  if (!ctx && !failed) return <StripFrame><StripSkeleton /></StripFrame>;
  if (!ctx || ctx.offline) {
    return (
      <StripFrame>
        <p className="px-4 py-2.5 text-[12px] text-err qt:px-6">
          <strong className="font-semibold">Market context unavailable.</strong>{" "}
          {ctx?.offline ? (
            <>
              {ctx.offline.reason} — expected at <code>{ctx.offline.api}</code>.
            </>
          ) : (
            `${failed}.`
          )}{" "}
          The conviction count, breadth, fuel and flow panels are left out rather than
          guessed; the panels below still read the terminal&apos;s own feeds.
        </p>
      </StripFrame>
    );
  }

  const c = ctx.conviction;
  const spy = ctx.fuel.find((f) => f.sym === "SPY") ?? null;
  const qqq = ctx.fuel.find((f) => f.sym === "QQQ") ?? null;
  const b = ctx.breadth;
  const ndx = b.indices.find((i) => i.key === "NDX") ?? null;
  const next = nextPrint(ctx.prints);
  const lastHot = [...ctx.prints].reverse().find((p) => (p.released || p.done) && p.score >= 4) ?? null;
  const clock = next ? printClock(next.et, ctx.built_utc) : null;
  const toGo = clock?.until ?? null;

  return (
    <StripFrame>
      <div className="grid grid-cols-2 divide-ring md:grid-cols-[minmax(0,1.45fr)_repeat(4,minmax(0,1fr))] md:divide-x">
        {/* ---- the count: which side, and how many signals agree ----------- */}
        <Cell label="Tape conviction" title={votesTip(c)} className="col-span-2 md:col-span-1">
          {c.total === 0 ? (
            <>
              <span className="text-[16px] leading-none text-ink-3">No votes yet</span>
              <p className="mt-1.5 text-[11px] text-ink-3">the signals have not answered</p>
            </>
          ) : (
            <>
              <div className="flex flex-wrap items-baseline gap-x-2.5 gap-y-1">
                <span className={cn("text-[18px] leading-none font-semibold", sideText(c.bias))}>{biasWord(c.bias)}</span>
                <span className="fig text-[12.5px] text-ink-2">
                  {c.agree} of {c.total} agree
                </span>
                <span className={cn("qt-cap text-[10.5px]", gradeText(c))}>{c.grade}</span>
              </div>
              <ConvictionBar c={c} className="mt-2 max-w-[260px]" />
              <p className="mt-1.5 text-[11px] text-ink-3">
                {c.agree} agree · {c.against} against · {c.neutral} neutral · plans capped at{" "}
                <span className="fig text-ink-2">{c.max_conviction}</span>
              </p>
            </>
          )}
        </Cell>

        {/* ---- the day the options price ------------------------------------ */}
        <Cell
          label="Implied SPY day"
          title="The one-day, one-standard-deviation move the index vol prices: VIX ÷ √252 for SPY, VXN ÷ √252 for QQQ"
        >
          <span className="fig text-[19px] leading-none text-ink">
            {spy?.implied_pct != null ? `±${spy.implied_pct.toFixed(2)}%` : "—"}
          </span>
          <p className="mt-1.5 text-[11px] text-ink-3">
            {qqq?.implied_pct != null ? (
              <>
                QQQ <span className="fig text-ink-2">±{qqq.implied_pct.toFixed(2)}%</span> · one-sigma
              </>
            ) : (
              "one-sigma, from VIX"
            )}
          </p>
        </Cell>

        {/* ---- how much of it is spent --------------------------------------- */}
        <Cell
          label="Fuel used"
          title="Today's range as a multiple of the implied day. Under 0.6× there is room to travel; past 1.0× the index has already done what the options priced."
        >
          <div className="flex flex-col gap-1">
            {[spy, qqq].map((f, i) => (
              <FuelLine key={f?.sym ?? i} f={f} sym={i === 0 ? "SPY" : "QQQ"} />
            ))}
          </div>
        </Cell>

        {/* ---- is the move broad --------------------------------------------- */}
        <Cell
          label="Breadth"
          title="How many of the sector SPDRs are up, equal weight (RSP) against cap weight (SPY), and how many Nasdaq-100 names are rising"
        >
          {b.sectors_total > 0 ? (
            <>
              <span className="fig text-[16px] leading-none text-ink">
                {b.sectors_up}
                <span className="text-ink-3"> / {b.sectors_total}</span>
              </span>{" "}
              <span className="text-[11.5px] text-ink-3">sectors up</span>
              <SplitBar
                className="mt-2 max-w-[180px]"
                total={b.sectors_total}
                label={`${b.sectors_up} sectors up, ${b.sectors_down} down`}
                parts={[
                  { n: b.sectors_up, cls: "bg-call-fig" },
                  { n: b.sectors_down, cls: "bg-put-fig" },
                ]}
              />
              <p className="mt-1.5 text-[11px] text-ink-3">
                RSP{" "}
                <span className={cn("fig", b.rsp_vs_spy == null ? "text-ink-3" : b.rsp_vs_spy >= 0 ? "up" : "down")}>
                  {b.rsp_vs_spy == null ? "—" : `${b.rsp_vs_spy >= 0 ? "+" : ""}${b.rsp_vs_spy.toFixed(2)}`}
                </span>{" "}
                vs SPY
                {ndx?.pct_up != null && (
                  <>
                    {" "}· NDX <span className="fig text-ink-2">{Math.round(ndx.pct_up)}%</span> up
                  </>
                )}
              </p>
            </>
          ) : (
            <>
              <span className="text-[14px] leading-none text-ink-3">—</span>
              <p className="mt-1.5 text-[11px] text-ink-3">the sector feed has not answered</p>
            </>
          )}
        </Cell>

        {/* ---- what prints next ---------------------------------------------- */}
        <Cell
          label="Next high-impact"
          title="The next US release scored 4 or more on the calendar, for the session the scanner is reading — and the one after it, before its open"
        >
          {next ? (
            <>
              <span className={cn("fig text-[17px] leading-none", toGo != null && toGo <= 30 ? "text-flip-fig" : "text-ink")}>
                {toGo != null ? `in ${inMin(toGo)}` : clock!.label}
              </span>
              <p className="mt-1.5 truncate text-[11px] text-ink-3" title={next.title}>
                <span className="fig text-ink-2">{clock!.label}</span> {next.title}
              </p>
            </>
          ) : lastHot ? (
            <>
              <span className="text-[14px] leading-none text-ink-2">All printed</span>
              <p className="mt-1.5 truncate text-[11px] text-ink-3" title={lastHot.title}>
                <span className="fig text-ink-2">{printClock(lastHot.et, ctx.built_utc).label}</span> {lastHot.title}
                {lastHot.read && <span className={cn("qt-cap ml-1.5 text-[10px]", readText(lastHot.read))}>{lastHot.read}</span>}
              </p>
            </>
          ) : (
            <>
              <span className="text-[14px] leading-none text-ink-3">Nothing scheduled</span>
              <p className="mt-1.5 text-[11px] text-ink-3">no high-impact US print today</p>
            </>
          )}
        </Cell>
      </div>
    </StripFrame>
  );
}

function FuelLine({ f, sym }: { f: Fuel | null; sym: "SPY" | "QQQ" }) {
  // Before the open there is no range yet — the gap is all that has been spent.
  const pre = f != null && f.range_pct == null;
  const x = f ? (pre ? f.gap_vs_implied : f.used) : null;
  return (
    <div className="flex items-baseline gap-2 text-[12px]">
      <span className="fig w-[32px] text-ink-2">{sym}</span>
      <Tick value={x != null ? `${Math.abs(x).toFixed(2)}×` : "—"} className="fig text-[13px] text-ink" />
      {pre ? (
        <span className="qt-cap text-[10px] text-ink-3">gap · pre</span>
      ) : (
        f?.state && <span className={cn("qt-cap text-[10px]", stateText(f.state))}>{f.state}</span>
      )}
    </div>
  );
}

/**
 * The first high-impact print still to come, in the order the collector lists
 * them. Not merely un-released: a speech never has an actual, and a 13:00 Fed
 * speaker read as "next" all afternoon (audit, 2026-10-14) — `done` is the clock.
 */
function nextPrint(prints: Print[]): Print | null {
  return prints.find((p) => !p.released && !p.done && p.score >= 4) ?? null;
}

function StripFrame({ children }: { children: React.ReactNode }) {
  return (
    <section
      aria-label="Market conviction"
      className={cn(
        "mx-2 mt-2 shrink-0 overflow-hidden rounded-lg border border-ring bg-surface",
        "qt:mx-0 qt:mt-0 qt:rounded-none qt:border-x-0 qt:border-t-0 qt:bg-transparent",
      )}
    >
      {children}
    </section>
  );
}

function Cell({
  label,
  title,
  className,
  children,
}: {
  label: string;
  title?: string;
  className?: string;
  children: React.ReactNode;
}) {
  return (
    <div className={cn("min-w-0 px-4 py-2.5 qt:px-6 qt:py-3", className)} title={title}>
      <p className="qt-cap mb-2 text-[10.5px] text-ink-3">{label}</p>
      {children}
    </div>
  );
}

function StripSkeleton() {
  return <HelmLoader label="Reading the tape" size={30} minHeight={92} className="py-3" />;
}
