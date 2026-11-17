"use client";

import type { PolicyMeetings, Rates as RatesData } from "@/types/terminal";
import { Module } from "@/components/ui/Module";
import { Tick } from "@/components/ui/Tick";
import { bp, num } from "@/lib/format";
import { cn } from "@/lib/cn";
import { RatesPopover } from "@/components/vol/RatesRead";
import {
  dayLabel,
  decisionLine,
  isoDate,
  meetingSize,
  monthLabel,
  monthsApart,
  moveText,
  pathSize,
  slope,
  slopeMove,
  tenYearRead,
} from "@/lib/ratesRead";

/**
 * Rates — where policy is, where it is priced to go, and the curve.
 *
 * THE POLICY PATH IS THE HEADLINE, not the ten-year. A curve tells you what
 * happened; the fed funds strip tells you what the market has already agreed
 * will happen, which is the thing a headline can surprise. So the path sits
 * at the top and the curve underneath it.
 *
 * THE CARD SAYS IT IN WORDS FIRST (owner, 2026-11-14: "is the rates and policy
 * card in macro as inutiive and easy to read as it could be", then "do what you
 * think best"). It had every figure and made the reader assemble them: three
 * same-weight figures of which two were one fact, the next meeting as a grey row
 * of two unnamed numbers, the read behind a label that looked like a heading.
 * Now, top to bottom: one sentence (what the next meeting has priced, and what
 * the 10Y is doing to the index books), two figures (the rate now and the far
 * end of the strip), the path meeting by meeting with its columns named, the
 * Treasury's yields, the curve's shape. Each fact is on the card once.
 *
 * BASIS POINTS PRICED, AND THE SAME IN QUARTER POINTS. Never "a 72% chance of a
 * cut": a probability needs an assumed move size and a convention for a meeting
 * that falls mid-month, and nothing here assumes either. Each fed funds contract
 * settles to the average policy rate over its month, so `100 − price` IS the
 * expected rate for that month, and `policy.py` un-mixes it at each decision
 * date into what that meeting has priced. "+27bp" is then also said as "a full
 * hike" (lib/ratesRead), which is the same figure in the unit it is talked about
 * in, not a likelihood.
 *
 * A YIELD IS A MOVE, NOT A SIDE (owner, 2026-11-12: "positive doesnt mean bullish
 * and vice versa"). This card painted a rising yield pink while the Macro board
 * beside it painted the same move green. Every figure here is now ink with an
 * arrow, and the one coloured word on the card is the effect on the index books:
 * headwind or tailwind.
 *
 * THE STEP CHART WENT. It had no scale and both its end labels stacked at one
 * end; the path table's Total column is the same shape with the numbers on it.
 * Three of the four spreads left the face (10Y over 3M, 30Y over 5Y, the
 * breakeven): they are a line in the click-through, the collector still sends
 * them and Hermes still reads them. What stays is the one that names the curve's
 * shape, with its change on the day, and the real 10Y.
 *
 * IT HAS TO FIT UNDER EARNINGS. The card is the last in Macro's left column and on
 * the 1440 screen had about ninety pixels to grow before that column scrolled, so
 * the yields run across in two rows and the curve is one line.
 */

/** The live 10Y as the driver board reads it: MacroBoard passes it while the cash 10Y is trading. */
export interface TenLive {
  last: number;
  chgBp: number;
  vote: "long" | "short" | "neutral";
}

/** How many meetings the path lists. */
const PATH_ROWS = 5;

export function Rates({
  rates,
  pm,
  ten,
  ageMin,
  error,
}: {
  rates: RatesData;
  pm: PolicyMeetings;
  ten?: TenLive | null;
  ageMin?: number | null;
  error?: string | null;
}) {
  const effr = rates.policy?.EFFR;
  const effrDay = isoDate(effr?.as_of);
  const path = rates.path ?? {};
  const strip = rates.strip ?? [];
  const meetings = pm?.meetings ?? [];
  const next = meetings[0];
  const closeDay = isoDate(rates.as_of);

  const curve = rates.curve ?? [];
  const tenRow = curve.find((r) => r.key === "10Y");
  const twoRow = curve.find((r) => r.key === "2Y");
  const read10 = tenYearRead({
    live: ten ?? null,
    close: tenRow ? { value: tenRow.value, chgBp: tenRow.chg_bp ?? null, day: closeDay } : null,
  });

  const last = strip[strip.length - 1];
  const horizon = last ? monthLabel(last.month) : path.horizon_label;
  const months = strip.length > 1 && last ? monthsApart(strip[0].month, last.month) : null;
  // From today's rate where there is one, so "now", "by" and the move are one sum.
  const pathBp = path.vs_effr_bp ?? path.move_bp;

  const s2s10 = rates.spreads?.find((s) => s.key === "2s10s");
  const real10 = rates.real?.find((r) => r.key === "10Y real");
  const steeper = slopeMove(tenRow?.chg_bp, twoRow?.chg_bp);

  return (
    <Module
      title="Rates & policy"
      sub={closeDay ? `Treasury close ${dayLabel(closeDay)}` : undefined}
      ageMin={ageMin}
      every={30}
      error={error}
      bodyClassName="px-0 py-0"
    >
      {/* ---- the read: one sentence, and the long form one click away ------ */}
      {(next || read10) && (
        <div className="border-b border-ring/40 px-1 pt-1 pb-0.5">
          <RatesPopover rates={rates} pm={pm} className="block w-full px-2 py-1">
            <span className="block text-[12px] leading-[1.5] text-ink">
              {next && decisionLine(next)}
              {next && read10 && " "}
              {read10 && (
                <>
                  {read10.text}
                  {read10.wind && (
                    <>
                      {" a "}
                      <span className={read10.wind === "headwind" ? "down" : "up"}>{read10.wind}</span>
                      {" for NQ and ES."}
                    </>
                  )}
                </>
              )}
              <span className="whitespace-nowrap text-ink-3"> More ›</span>
            </span>
          </RatesPopover>
        </div>
      )}

      {/* ---- the two ends of the path: now, and the far end of the strip. The
               next meeting is not a third figure here: the sentence above says it
               and the first row below has its numbers. ------------------------- */}
      <div className="flex flex-wrap items-start gap-x-8 gap-y-2 border-b border-ring/40 px-3 py-1.5">
        <Stat
          label="Fed funds now"
          value={effr ? `${effr.rate.toFixed(2)}%` : "—"}
          sub={effrDay ? `effective, ${dayLabel(effrDay)}` : undefined}
          title="The effective federal funds rate (EFFR): what overnight money actually traded at, from the New York Fed."
        />
        {path.horizon !== undefined && (
          <Stat
            label={`Priced by ${horizon ?? "the far end"}`}
            value={`${path.horizon.toFixed(2)}%`}
            aside={pathBp !== undefined ? `(${bp(pathBp, 0)})` : undefined}
            sub={pathSize(pathBp, months)}
            title="The rate the last fed funds contract on the strip implies, and how far that is from today's."
          />
        )}
      </div>

      {/* ---- the path, meeting by meeting --------------------------------- */}
      {meetings.length > 0 && (
        <div>
          <div className="qt-band flex items-baseline gap-2 border-b border-ring/40 bg-surface-2/50 px-3 py-1">
            <span className="eyebrow text-[9px]">Fed path</span>
            <span className="fig ml-auto w-[52px] shrink-0 text-right text-[8.5px] tracking-wide text-ink-3" title="Basis points this one decision has priced into it.">
              priced
            </span>
            <span className="fig w-[70px] shrink-0 text-right text-[8.5px] tracking-wide whitespace-nowrap text-ink-3" title="The policy rate the futures imply once this decision is in.">
              rate after
            </span>
            <span
              className="fig w-[52px] shrink-0 text-right text-[8.5px] tracking-wide text-ink-3"
              title={`Everything priced up to and including this meeting, from ${pm.anchor != null ? `${pm.anchor.toFixed(2)}% ` : ""}${pm.anchor_src ?? "today's rate"}.`}
            >
              total
            </span>
          </div>
          <ul>
            {meetings.slice(0, PATH_ROWS).map((m) => (
              <li
                key={m.date}
                className="hit flex items-baseline gap-2 px-3 py-[2px]"
                title={`${dayLabel(m.date)}: ${bp(m.move_bp, 1)} priced for this decision (${m.method ?? "the strip"}), ${bp(m.cum_bp, 1)} in total from ${pm.anchor_src ?? "today's rate"}.`}
              >
                <span className={cn("fig w-[78px] shrink-0 text-[10.5px] whitespace-nowrap", m === next ? "text-ink" : "text-ink-2")}>
                  {dayLabel(m.date)}
                </span>
                <span className="min-w-0 flex-1 truncate text-[10.5px] text-ink-3">{meetingSize(m)}</span>
                <Tick
                  value={bp(m.move_bp, 0)}
                  className={cn("fig w-[52px] shrink-0 text-right text-[10.5px]", m.stance === "hold" ? "text-ink-3" : "text-ink")}
                />
                <Tick value={`${m.implied_after.toFixed(2)}%`} className="fig w-[70px] shrink-0 text-right text-[10.5px] text-ink-2" />
                <Tick value={bp(m.cum_bp, 0)} className="fig w-[52px] shrink-0 text-right text-[10.5px] text-ink-3" />
              </li>
            ))}
          </ul>
        </div>
      )}

      {/* ---- the Treasury's yields, in tenor order: bills, then notes and bonds.
               Across in two rows where the card is wide enough; on a narrow one,
               down two columns. Never the zigzag (1M, 3M / 6M, 1Y) it was. ------ */}
      {curve.length > 0 && (
        <div className="@container">
          <div className="qt-band flex items-baseline gap-2 border-y border-ring/40 bg-surface-2/50 px-3 py-1">
            <span className="eyebrow text-[9px]">Treasury yields</span>
            <span
              className="fig ml-auto text-[8.5px] tracking-wide text-ink-3"
              title="Each yield at the Treasury's last close, and its move on that day in basis points. An arrow, not a colour: a yield rising is not a side."
            >
              close · day&apos;s move
            </span>
          </div>
          <div className="grid grid-flow-col grid-cols-2 grid-rows-4 gap-x-4 px-3 py-0.5 @lg:grid-flow-row @lg:grid-cols-4 @lg:grid-rows-none">
            {curve.map((r) => {
              const move = moveText(r.chg_bp);
              return (
                <div key={r.key} className="flex items-baseline gap-2 py-[2px]">
                  <span className="fig w-[26px] shrink-0 text-[10.5px] text-ink-3">{r.label}</span>
                  <Tick value={`${r.value.toFixed(2)}%`} className="fig shrink-0 text-right text-[11.5px] text-ink" />
                  <Tick value={move} className={cn("fig text-[10.5px] whitespace-nowrap", move === "unch" || move === "—" ? "text-ink-4" : "text-ink-2")} />
                </div>
              );
            })}
          </div>
        </div>
      )}

      {/* ---- the curve's shape, and the real 10Y. The other spreads (10Y over 3M,
               30Y over 5Y, the breakeven) are in the click-through. ------------- */}
      {(s2s10 || real10) && (
        <div className="flex flex-wrap items-baseline gap-x-5 gap-y-1 border-t border-ring/40 px-3 py-1.5">
          {s2s10 && (
            <Fact
              label="10Y over 2Y"
              value={`${num(s2s10.value, 0)}bp`}
              note={`${slope(s2s10.value)}${steeper ? `, ${steeper} on the day` : ""}`}
              title="2s10s: the 10-year yield minus the 2-year. Below zero the curve is inverted."
            />
          )}
          {real10 && (
            <Fact
              className="ml-auto"
              label="Real 10Y"
              value={`${real10.value.toFixed(2)}%`}
              note={real10.chg_bp != null ? moveText(real10.chg_bp) : undefined}
              title="The 10-year inflation-protected yield: the part of the 10Y that is not inflation, and gold's carrying cost."
            />
          )}
        </div>
      )}
    </Module>
  );
}

function Stat({
  label,
  value,
  aside,
  sub,
  title,
}: {
  label: string;
  value: string;
  /** A second, smaller figure beside the first. */
  aside?: string;
  sub?: string | null;
  title?: string;
}) {
  return (
    <div className="min-w-0" title={title}>
      <div className="eyebrow text-[9px]">{label}</div>
      <div className="fig text-[15px] leading-tight text-ink">
        <Tick value={value} />
        {aside && <span className="ml-1.5 text-[11px] text-ink-2">{aside}</span>}
      </div>
      {sub && <div className="text-[10px] text-ink-3">{sub}</div>}
    </div>
  );
}

/** One named figure on the curve line, with what it says in a few words. */
function Fact({ label, value, note, title, className }: { label: string; value: string; note?: string; title?: string; className?: string }) {
  return (
    <span className={cn("flex items-baseline gap-1.5", className)} title={title}>
      <span className="text-[10px] text-ink-3">{label}</span>
      <Tick value={value} className="fig text-[11px] text-ink" />
      {note && <span className="text-[10px] text-ink-3">{note}</span>}
    </span>
  );
}
