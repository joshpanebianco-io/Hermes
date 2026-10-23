"use client";

import type { PolicyMeetings, Rates } from "@/types/terminal";
import { Popover } from "@/components/ui/Popover";
import { bp } from "@/lib/format";
import { cn } from "@/lib/cn";

/**
 * The rates panel's click-through: what the FOMC path prices in words, what
 * the day's move in the 10Y does to each book, and what the curve's shape
 * says — the long form behind the figures.
 *
 * THE FIGURES WERE ALL THERE AND NONE OF THEM SAID WHAT TO DO (owner,
 * 2026-10-22). "+17bp priced for Oct 28" is a fact; "about two thirds of a
 * cut, so a hot print that takes it away is a repricing the first hour
 * trades" is the read. The thresholds quoted are the driver board's
 * (drivers.py: the 10Y's day change votes at four basis points, the hold
 * band is the policy module's), so the panel and the count agree.
 */

/** drivers.YIELD_BP — the 10Y's day change at or beyond which it votes. */
const YIELD_BP = 4;
/** policy.HOLD_BAND_BP — inside this the next meeting is read as a hold. */
const HOLD_BAND_BP = 5;

function meetingLine(pm: PolicyMeetings | undefined): string | null {
  const m = pm?.meetings?.[0];
  if (!m) return null;
  const move = m.move_bp;
  if (Math.abs(move) < HOLD_BAND_BP) {
    return `${m.label}: a hold is priced (${bp(move, 0)}). The market has nothing to unwind at the decision; the statement and the path after it are the event.`;
  }
  const share = Math.round((Math.abs(move) / 25) * 100);
  const kind = move > 0 ? "hike" : "cut";
  return `${m.label}: ${bp(move, 0)} priced, about ${share}% of a 25bp ${kind}. A print that moves this by more than ${HOLD_BAND_BP}bp is a repricing, and the first hour trades it.`;
}

function tenYearLine(rates: Rates): string | null {
  const ten = rates.curve?.find((r) => r.key === "10Y");
  const chg = ten?.chg_bp ?? null;
  if (ten == null || chg == null) return null;
  // THE CURVE IS TREASURY'S DAILY PRINT, so this is the last close's move; the
  // live 10Y is on the board and votes on the driver board at ±YIELD_BP.
  const abs = Math.abs(chg);
  const at = `The 10Y closed at ${ten.value.toFixed(2)}%, ${bp(chg, 0)} on the day of the last curve print`;
  if (abs < YIELD_BP) {
    return `${at} — inside ±${YIELD_BP}bp, no read from rates. The live 10Y is on the board and votes on the driver board.`;
  }
  return chg > 0
    ? `${at}: the discount rate rising is a headwind for NQ first and ES after it, and for gold through real yields. The live 10Y is on the board and votes on the driver board.`
    : `${at}: the discount rate falling is a tailwind for NQ and ES, and for gold through real yields — unless it is a growth scare, which sells the index first. The live 10Y is on the board and votes on the driver board.`;
}

function curveLine(rates: Rates): string | null {
  const s = rates.spreads?.find((r) => r.key === "2s10s");
  if (!s) return null;
  const v = s.value;
  if (v < 0) {
    return `2s10s at ${Math.round(v)}bp is inverted: the front end prices more tightening than the long end believes lasts. A steepening from here is usually the long end falling first — bullish duration, mixed for the index.`;
  }
  if (v < 25) {
    return `2s10s at ${Math.round(v)}bp is flat: little term premium, the curve moves on the Fed path. Bull steepening (cuts priced) supports the index; bear steepening (supply, inflation) does not.`;
  }
  return `2s10s at ${Math.round(v)}bp is steep: the long end carries a term premium of its own. Auctions and supply move it as much as the Fed does — a tailed 10s or 30s is an equity event at 13:01 ET.`;
}

export function RatesPopover({
  rates,
  pm,
  className,
  children,
}: {
  rates: Rates;
  pm: PolicyMeetings | undefined;
  className?: string;
  children: React.ReactNode;
}) {
  return (
    <Popover
      label="What the rates panel means"
      title="Click for what the path, the 10Y and the curve mean for the books"
      className={className}
      panel={<RatesRead rates={rates} pm={pm} />}
    >
      {children}
    </Popover>
  );
}

function RatesRead({ rates, pm }: { rates: Rates; pm: PolicyMeetings | undefined }) {
  const lines: { k: string; v: string | null }[] = [
    { k: "The next decision", v: meetingLine(pm) },
    { k: "The 10Y today", v: tenYearLine(rates) },
    { k: "The curve", v: curveLine(rates) },
  ];
  const real = rates.real?.find((r) => r.key === "10Y");
  return (
    <div className="w-[min(560px,calc(100vw-24px))] px-4 py-3 text-ink">
      <div className="flex flex-wrap items-baseline gap-x-2 gap-y-1">
        <span className="qt-cap text-[10.5px] text-ink-3">What the rates mean</span>
        <span className="text-[14px] font-semibold text-ink">Rates &amp; policy</span>
        {rates.as_of && <span className="fig ml-auto text-[11px] text-ink-3">curve {rates.as_of}</span>}
      </div>
      <dl className="mt-2.5 grid grid-cols-[130px_minmax(0,1fr)] gap-x-3 gap-y-2.5 text-[11.5px] leading-[1.5]">
        {lines.map((l) => (
          <div key={l.k} className="contents">
            <dt className="qt-cap text-[10px] text-ink-3">{l.k}</dt>
            <dd className={cn(l.v ? "text-ink-2" : "text-ink-3")}>{l.v ?? "No figure to read yet."}</dd>
          </div>
        ))}
        {real && (
          <div className="contents">
            <dt className="qt-cap text-[10px] text-ink-3">Real 10Y</dt>
            <dd className="text-ink-2">
              {real.value.toFixed(2)}%{real.chg_bp != null ? ` (${bp(real.chg_bp, 0)})` : ""}: gold&apos;s carrying cost, and the
              half of a nominal move that is not inflation. Treasury&apos;s daily print, so it lags the board.
            </dd>
          </div>
        )}
      </dl>
      <p className="mt-2.5 border-t border-ring pt-2 text-[11px] leading-[1.45] text-ink-3">
        Rising yields wear the down hue on this panel because for a long-duration book that is the losing
        direction. Basis points priced per meeting, never a probability: a probability needs an assumed move
        size, and this assumes none.
      </p>
    </div>
  );
}
