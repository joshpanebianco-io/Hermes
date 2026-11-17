"use client";

import type { PolicyMeetings, Rates } from "@/types/terminal";
import { Popover } from "@/components/ui/Popover";
import { bp } from "@/lib/format";
import { cn } from "@/lib/cn";
import { YIELD_BP, dayLabel, isoDate, meetingSize, slope } from "@/lib/ratesRead";

/**
 * The rates panel's click-through: what the FOMC path prices in words, what
 * the day's move in the 10Y does to each book, and what the curve's shape
 * says — the long form behind the figures.
 *
 * THE FIGURES WERE ALL THERE AND NONE OF THEM SAID WHAT TO DO (owner,
 * 2026-10-22). "+17bp priced for Oct 28" is a fact; "about two thirds of a
 * cut, so a hot print that takes it away is a repricing the first hour
 * trades" is the read. The thresholds quoted are the driver board's
 * (drivers.py: the 10Y's day change votes at four basis points), so the panel
 * and the count agree.
 *
 * THE SHORT FORM IS ON THE CARD NOW (2026-11-14): its first line says what the
 * next meeting has priced and what the 10Y is doing, and that line is this
 * panel's trigger. Four things here were wrong and are fixed: the real 10Y line
 * looked for a row keyed "10Y" (the collector's is "10Y real") and never showed;
 * a hold was anything inside 5bp here and inside 3bp on the row, so +4bp read
 * both ways (the stance is the collector's now); "about 107% of a 25bp hike" is
 * "a full hike"; and 27bp of 2s10s was called steep.
 */

/** A change this large in what one meeting has priced is a repricing the first hour trades. */
const REPRICE_BP = 5;

function meetingLine(pm: PolicyMeetings | undefined): string | null {
  const m = pm?.meetings?.[0];
  if (!m) return null;
  const when = dayLabel(m.date);
  if (m.stance === "hold") {
    return `${when}: a hold is priced (${bp(m.move_bp, 0)}). The market has nothing to unwind at the decision; the statement and the path after it are the event.`;
  }
  return `${when}: ${bp(m.move_bp, 0)} priced, ${meetingSize(m)}. A print that moves this by more than ${REPRICE_BP}bp is a repricing, and the first hour trades it.`;
}

function tenYearLine(rates: Rates): string | null {
  const ten = rates.curve?.find((r) => r.key === "10Y");
  const chg = ten?.chg_bp ?? null;
  if (ten == null || chg == null) return null;
  // THE CURVE IS TREASURY'S DAILY PRINT, so this is the last close's move; the
  // live 10Y is on the board and votes on the driver board at ±YIELD_BP.
  const day = isoDate(rates.as_of);
  const abs = Math.abs(chg);
  const at = `The 10Y closed at ${ten.value.toFixed(2)}%${day ? ` on ${dayLabel(day)}` : ""}, ${bp(chg, 0)} on the day`;
  if (abs < YIELD_BP) {
    return `${at}: inside ±${YIELD_BP}bp, no read from rates. In the session the card's first line follows the live 10Y, which votes on the driver board.`;
  }
  return chg > 0
    ? `${at}: the discount rate rising is a headwind for NQ first and ES after it, and for gold through real yields. In the session the card's first line follows the live 10Y, which votes on the driver board.`
    : `${at}: the discount rate falling is a tailwind for NQ and ES, and for gold through real yields, unless it is a growth scare, which sells the index first. In the session the card's first line follows the live 10Y, which votes on the driver board.`;
}

function curveLine(rates: Rates): string | null {
  const s = rates.spreads?.find((r) => r.key === "2s10s");
  if (!s) return null;
  const v = s.value;
  const at = `10Y over 2Y (2s10s) at ${Math.round(v)}bp is`;
  switch (slope(v)) {
    case "inverted":
      return `${at} inverted: the front end prices more tightening than the long end believes lasts. A steepening from here is usually the long end falling first, which is bullish duration and mixed for the index.`;
    case "nearly flat":
      return `${at} nearly flat: little term premium, the curve moves on the Fed path. Bull steepening (cuts priced) supports the index; bear steepening (supply, inflation) does not.`;
    case "moderate":
      return `${at} a moderate slope, around its long-run norm: neither end leads. Watch which one moves: the front end on Fed pricing, the long end on supply and inflation.`;
    default:
      return `${at} steep: the long end carries a term premium of its own. Auctions and supply move it as much as the Fed does, and a tailed 10s or 30s is an equity event at 13:01 ET.`;
  }
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
    { k: "The 10Y", v: tenYearLine(rates) },
    { k: "The curve", v: curveLine(rates) },
  ];
  const real = rates.real?.find((r) => r.key === "10Y real");
  const day = isoDate(rates.as_of);
  // The spreads the card's face no longer carries: named for what they are.
  const spread = (key: string) => rates.spreads?.find((s) => s.key === key);
  const also = [
    spread("3m10y") && `10Y over 3M ${Math.round(spread("3m10y")!.value)}bp`,
    spread("5s30s") && `30Y over 5Y ${Math.round(spread("5s30s")!.value)}bp`,
    spread("be10") && `inflation priced over ten years (the 10Y breakeven) ${spread("be10")!.value.toFixed(2)}%`,
  ].filter(Boolean);
  return (
    <div className="w-[min(560px,calc(100vw-24px))] px-4 py-3 text-ink">
      <div className="flex flex-wrap items-baseline gap-x-2 gap-y-1">
        <span className="qt-cap text-[10.5px] text-ink-3">What the rates mean</span>
        <span className="text-[14px] font-semibold text-ink">Rates &amp; policy</span>
        {day && <span className="fig ml-auto text-[11px] text-ink-3">Treasury close {dayLabel(day)}</span>}
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
        {also.length > 0 && (
          <div className="contents">
            <dt className="qt-cap text-[10px] text-ink-3">Also on the curve</dt>
            <dd className="fig text-ink-2">{also.join(" · ")}</dd>
          </div>
        )}
      </dl>
      <p className="mt-2.5 border-t border-ring pt-2 text-[11px] leading-[1.45] text-ink-3">
        A yield is printed as a move with an arrow, not in green or pink: rising is not a side, and what it does to
        the index books is said in words. A meeting&apos;s pricing is given in basis points and in quarter points
        (&quot;a full hike&quot;); neither is a probability.
      </p>
    </div>
  );
}
