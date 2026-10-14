"use client";

import type { Breadth as BreadthData, BreadthIndex, Conviction, Fuel as FuelRow } from "@/types/market";
import { Module } from "@/components/ui/Module";
import { Skeleton } from "@/components/ui/Skeleton";
import { Tick } from "@/components/ui/Tick";
import { pct } from "@/lib/format";
import { cn } from "@/lib/cn";
import {
  ConvictionBar,
  Gap,
  SplitBar,
  biasWord,
  gradeText,
  sideText,
  stateText,
  voteGlyph,
} from "@/components/market/shared";

/**
 * The tape, read three ways: the conviction count (which side, and how many
 * independent signals agree), breadth (is the move broad or carried by a few
 * names), and fuel (how much of the day the options priced is already spent).
 * Together they answer whether a single-name setup is swimming with the
 * market or against it — the question the scanner's score cannot.
 */

/* -------------------------------------------------------------------------- */
/* Conviction — every vote, with its figure and its reason                     */
/* -------------------------------------------------------------------------- */

export function ConvictionPanel({ c }: { c: Conviction | null }) {
  return (
    <Module
      title="Tape conviction"
      sub="signals that agree"
      bodyClassName="px-0 py-0"
      right={
        c && c.total > 0 ? (
          <span className="flex items-baseline gap-2">
            <span className={cn("text-[11px] font-semibold", sideText(c.bias))}>{biasWord(c.bias)}</span>
            <span className="fig text-[10.5px] text-ink-2">
              {c.agree}/{c.total}
            </span>
            <span className={cn("qt-cap text-[9.5px]", gradeText(c))}>{c.grade}</span>
          </span>
        ) : undefined
      }
    >
      {!c ? (
        <Skeleton rows={8} label="Loading the conviction count" />
      ) : c.votes.length === 0 ? (
        <Gap>No signal has voted yet — the tape&apos;s inputs have not answered.</Gap>
      ) : (
        <>
          <ul className="py-1">
            {c.votes.map((v) => (
              <li
                key={v.key}
                className="hit grid grid-cols-[14px_minmax(0,1fr)_auto] items-baseline gap-2 px-3 py-[3px]"
                title={v.note}
              >
                <span className={cn("text-center text-[10px]", sideText(v.vote))} aria-label={v.vote}>
                  {voteGlyph(v.vote)}
                </span>
                <span className={cn("truncate text-[10.5px]", v.vote === "neutral" ? "text-ink-3" : "text-ink-2")}>
                  {v.label}
                </span>
                <Tick value={v.value} className="fig text-right text-[10.5px] text-ink" />
              </li>
            ))}
          </ul>
          <div className="border-t border-ring/40 px-3 py-2">
            <ConvictionBar c={c} />
            <p className="mt-1.5 text-[10px] leading-relaxed text-ink-3">
              {c.agree} agree · {c.against} against · {c.neutral} neutral. A plan on this tape is capped at{" "}
              <span className="fig text-ink-2">{c.max_conviction}/5</span>
              {c.bias ? "; one against the tape at 3." : "."} Strong is six or more agreeing with at most one
              against.
            </p>
          </div>
        </>
      )}
    </Module>
  );
}

/* -------------------------------------------------------------------------- */
/* Breadth — is the move broad, or carried                                     */
/* -------------------------------------------------------------------------- */

export function BreadthPanel({ b }: { b: BreadthData | null }) {
  const rsp = b?.rsp_vs_spy ?? null;
  return (
    <Module title="Breadth" sub="is the move broad" bodyClassName="px-0 py-0">
      {!b ? (
        <Skeleton rows={4} label="Loading breadth" />
      ) : b.sectors_total === 0 && b.indices.length === 0 && rsp == null ? (
        <Gap>No breadth yet — the sector and constituent feeds have not answered.</Gap>
      ) : (
        <div className="flex flex-col gap-2.5 px-3 py-2.5">
          {b.sectors_total > 0 && (
            <Row label="Sectors" right={`${b.sectors_up} up · ${b.sectors_down} down`}>
              <SplitBar
                total={b.sectors_total}
                label={`${b.sectors_up} of ${b.sectors_total} sector SPDRs up`}
                parts={[
                  { n: b.sectors_up, cls: "bg-call-fig" },
                  { n: b.sectors_down, cls: "bg-put-fig" },
                ]}
              />
            </Row>
          )}
          <div
            className="flex items-baseline gap-2 text-[10.5px]"
            title="RSP's day minus SPY's, in percentage points: equal weight beating cap weight means the average stock is taking part"
          >
            <span className="qt-cap w-[64px] shrink-0 text-[9.5px] text-ink-3">Equal wt</span>
            <span className={cn("fig text-[11.5px]", rsp == null ? "text-ink-3" : rsp >= 0 ? "up" : "down")}>
              {rsp == null ? "—" : `${rsp >= 0 ? "+" : ""}${rsp.toFixed(2)}`}
            </span>
            <span className="min-w-0 truncate text-ink-3">
              {rsp == null ? "RSP vs SPY unavailable" : rsp >= 0 ? "RSP leading SPY — broad" : "RSP lagging SPY — carried by the largest"}
            </span>
          </div>
          {b.indices.map((i) => (
            <IndexBreadth key={i.key} i={i} />
          ))}
        </div>
      )}
    </Module>
  );
}

function IndexBreadth({ i }: { i: BreadthIndex }) {
  const share = i.top3_share;
  return (
    <Row
      label={i.key}
      right={
        <>
          {i.up}/{i.total} up{i.pct_up != null && <span className="text-ink-3"> · {Math.round(i.pct_up)}%</span>}
        </>
      }
    >
      <SplitBar
        total={i.total}
        label={`${i.up} of ${i.total} ${i.key} names up`}
        parts={[
          { n: i.up, cls: "bg-call-fig" },
          { n: i.down, cls: "bg-put-fig" },
        ]}
      />
      <p className="mt-1 text-[10px] text-ink-3">
        {share != null ? (
          <span title="The three largest contributions as a share of all the shown names' contributions, by size">
            top three carry <span className={cn("fig", share >= 0.5 ? "text-warn" : "text-ink-2")}>{Math.round(share * 100)}%</span>
            {share >= 0.5 ? " — narrow" : ""}
          </span>
        ) : (
          "concentration unavailable"
        )}
        {i.contrib_pct != null && (
          <span title="The shown names' summed contribution to the index's move today">
            {" "}· shown names <span className={cn("fig", i.contrib_pct >= 0 ? "up" : "down")}>{pct(i.contrib_pct)}</span>
          </span>
        )}
      </p>
    </Row>
  );
}

function Row({ label, right, children }: { label: string; right: React.ReactNode; children: React.ReactNode }) {
  return (
    <div>
      <div className="mb-1 flex items-baseline gap-2">
        <span className="qt-cap w-[64px] shrink-0 text-[9.5px] text-ink-3">{label}</span>
        <span className="fig ml-auto text-[10.5px] text-ink-2">{right}</span>
      </div>
      {children}
    </div>
  );
}

/* -------------------------------------------------------------------------- */
/* Fuel — the range spent against the range priced                             */
/* -------------------------------------------------------------------------- */

/** The bar spans 0 to 2× the implied day; 1.0 sits at its middle. */
const FUEL_SPAN = 2;

export function FuelPanel({ fuel }: { fuel: FuelRow[] | null }) {
  return (
    <Module title="Fuel" sub="range used of the implied day" bodyClassName="px-0 py-0">
      {!fuel ? (
        <Skeleton rows={3} label="Loading index fuel" />
      ) : fuel.length === 0 ? (
        <Gap>No fuel read — the index quotes have not answered.</Gap>
      ) : (
        <>
          <ul className="py-1.5">
            {fuel.map((f) => (
              <FuelItem key={f.sym} f={f} />
            ))}
          </ul>
          <p className="border-t border-ring/40 px-3 py-1.5 text-[10px] leading-relaxed text-ink-3">
            Under 0.6× there is room left to travel; past 1.0× the index has done what the options priced, and a
            breakout entered there is paying for the second sigma.
          </p>
        </>
      )}
    </Module>
  );
}

function FuelItem({ f }: { f: FuelRow }) {
  const pre = f.range_pct == null;
  const x = pre ? (f.gap_vs_implied != null ? Math.abs(f.gap_vs_implied) : null) : f.used;
  const w = x == null ? 0 : (Math.min(x, FUEL_SPAN) / FUEL_SPAN) * 100;
  const fill = !pre && f.state === "stretched" ? "var(--warn)" : "var(--em)";
  return (
    <li className="hit px-3 py-[5px]">
      <div className="flex items-center gap-2">
        <span className="fig w-[34px] shrink-0 text-[10.5px] text-ink-2">{f.sym}</span>
        <span className="relative h-[8px] min-w-[60px] flex-1 bg-[var(--qt-track,var(--surface-3))]" aria-hidden>
          <span
            className="absolute inset-y-0 left-0"
            style={{ width: `${w}%`, background: fill, opacity: pre ? 0.45 : 0.85 }}
          />
          {/* 1.0× — the whole implied day. */}
          <span className="absolute inset-y-[-3px] left-1/2 w-px -translate-x-1/2 bg-ink-3" />
        </span>
        <Tick value={x != null ? `${x.toFixed(2)}×` : "—"} className="fig w-[46px] shrink-0 text-right text-[11px] text-ink" />
        <span className={cn("qt-cap w-[62px] shrink-0 text-right text-[9.5px]", pre ? "text-ink-3" : stateText(f.state))}>
          {pre ? "pre · gap" : (f.state ?? "—")}
        </span>
      </div>
      <p className="mt-0.5 pl-[42px] text-[10px] text-ink-3">
        {f.implied_pct == null ? (
          <>no index vol for {f.sym} — implied unknown</>
        ) : pre ? (
          <>
            gap <span className={cn("fig", f.gap_pct == null ? "" : f.gap_pct >= 0 ? "up" : "down")}>{pct(f.gap_pct)}</span> of{" "}
            <span className="fig text-ink-2">±{f.implied_pct.toFixed(2)}%</span> · range opens 09:30
          </>
        ) : (
          <>
            range <span className="fig text-ink-2">{f.range_pct!.toFixed(2)}%</span> of{" "}
            <span className="fig text-ink-2">±{f.implied_pct.toFixed(2)}%</span>
            {f.gap_pct != null && (
              <>
                {" "}· gap <span className={cn("fig", f.gap_pct >= 0 ? "up" : "down")}>{pct(f.gap_pct)}</span>
              </>
            )}
          </>
        )}
        {f.rvol != null && (
          <>
            {" "}· RVOL <span className="fig text-ink-2">{f.rvol.toFixed(1)}×</span>
          </>
        )}
      </p>
    </li>
  );
}
