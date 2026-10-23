"use client";

import type { PolicyMeetings, Rates as RatesData } from "@/types/terminal";
import { Module } from "@/components/ui/Module";
import { Tick } from "@/components/ui/Tick";
import { bp, num } from "@/lib/format";
import { cn } from "@/lib/cn";
import { RatesPopover } from "@/components/vol/RatesRead";

/**
 * Rates — the curve, where policy is, and where it is priced to go.
 *
 * THE POLICY PATH IS THE HEADLINE, not the ten-year. A curve tells you what
 * happened; the fed funds strip tells you what the market has already agreed
 * will happen, which is the thing a headline can surprise. So the strip sits
 * at the top and the curve underneath it.
 *
 * NO "72% CHANCE OF A CUT". That number needs a meeting calendar, an assumed
 * move size and a convention for a meeting that falls mid-month — three
 * assumptions stacked on a primitive that is already perfectly readable. Each
 * fed funds contract settles to the average policy rate over its month, so
 * `100 − price` IS the market's expected rate for that month. This shows that,
 * and the difference between the near and far ends of it.
 *
 * THE PER-MEETING ROWS EXIST NOW, AND THE PARAGRAPH ABOVE STILL HOLDS. Two of
 * its three objections dissolved when `fedcal` landed: the meeting calendar is
 * the Board's own, and no move size is assumed anywhere because the rows show
 * BASIS POINTS PRICED, never a probability — probability is what needs a
 * quantum to divide by, and nothing here divides. The one surviving assumption
 * (the mid-month day-count) lives in `server/newsterminal/policy.py`, stated
 * and tested. "+59bp by October" and "+16bp on Sep 16" are different notes;
 * only the second tells you which meeting a speech just repriced.
 */
export function Rates({
  rates,
  pm,
  ageMin,
  error,
}: {
  rates: RatesData;
  pm: PolicyMeetings;
  ageMin?: number | null;
  error?: string | null;
}) {
  const effr = rates.policy?.EFFR;
  const path = rates.path ?? {};
  const strip = rates.strip ?? [];
  const tightening = (path.move_bp ?? 0) > 0;

  return (
    <Module
      title="Rates & policy"
      sub={rates.as_of ? `curve ${rates.as_of}` : undefined}
      ageMin={ageMin}
      error={error}
      bodyClassName="px-0 py-0"
    >
      {/* ---- where policy is, and where it is going ---------------------- */}
      <div className="border-b border-ring/40 px-3 py-2">
        <div className="flex flex-wrap items-baseline gap-x-4 gap-y-1">
          <Stat label="EFFR" value={effr ? `${effr.rate.toFixed(2)}%` : "—"} sub={effr?.as_of} />
          {path.horizon !== undefined && (
            <Stat
              label={`Priced ${path.horizon_label ?? ""}`}
              value={`${path.horizon.toFixed(2)}%`}
              tone={tightening ? "down" : "up"}
            />
          )}
          {path.move_bp !== undefined && (
            <Stat
              label={path.direction === "easing" ? "Easing priced" : "Tightening priced"}
              value={bp(path.move_bp)}
              tone={tightening ? "down" : "up"}
              sub={`${path.front_label} → ${path.horizon_label}`}
            />
          )}
        </div>
        {strip.length > 1 && <Strip strip={strip} effr={effr?.rate ?? null} />}
      </div>

      {/* ---- what each meeting has priced into it ------------------------ */}
      {(pm?.meetings?.length ?? 0) > 0 && (
        <div className="border-b border-ring/40 px-3 py-1.5">
          <div className="mb-0.5 flex items-baseline justify-between">
            {/* The eyebrow opens what the path, the 10Y and the curve mean
                (RatesRead) — the panel's one click-through, on the figure
                that is the headline. */}
            <RatesPopover rates={rates} pm={pm} className="-mx-1 px-1 py-0">
              <span className="eyebrow text-[9px]">FOMC path · what it means</span>
            </RatesPopover>
            {pm.anchor != null && (
              <span className="fig text-[9px] text-ink-3">
                from {pm.anchor.toFixed(2)}% {pm.anchor_src}
              </span>
            )}
          </div>
          {pm.meetings.slice(0, 5).map((m) => (
            <div
              key={m.date}
              className="flex items-baseline gap-2 py-[2px]"
              title={`${m.stance} · ${m.move_bp > 0 ? "+" : ""}${m.move_bp}bp priced for the ${m.label} decision (${m.method ?? ""}) · ${m.cum_bp > 0 ? "+" : ""}${m.cum_bp}bp cumulative from ${pm.anchor_src ?? "the anchor"}`}
            >
              <span className="fig w-[44px] shrink-0 text-[10.5px] text-ink-3">{m.label}</span>
              <span className="min-w-0 flex-1 border-b border-dotted border-ring/50" />
              {/* Rising yields wear the down hue everywhere in this panel:
                  for a long-duration book that is the losing direction. */}
              <Tick
                value={bp(m.move_bp, 0)}
                className={cn(
                  "fig w-[48px] shrink-0 text-right text-[10.5px]",
                  m.stance === "hike" ? "down" : m.stance === "cut" ? "up" : "text-ink-3",
                )}
              />
              <Tick
                value={`${m.implied_after.toFixed(2)}%`}
                className="fig w-[52px] shrink-0 text-right text-[10.5px] text-ink-2"
              />
            </div>
          ))}
        </div>
      )}

      {/* ---- the curve --------------------------------------------------- */}
      <div className="grid grid-cols-2 gap-x-3 px-3 py-1.5">
        {(rates.curve ?? []).map((r) => (
          <div key={r.key} className="flex items-baseline gap-2 py-[2px]">
            <span className="fig w-[30px] shrink-0 text-[10.5px] text-ink-3">{r.label}</span>
            <Tick
              value={`${r.value.toFixed(2)}%`}
              className="fig flex-1 text-right text-[11.5px] text-ink"
            />
            <span
              className={cn(
                "fig w-[46px] shrink-0 text-right text-[10px]",
                (r.chg_bp ?? 0) > 0 ? "down" : (r.chg_bp ?? 0) < 0 ? "up" : "flat",
              )}
              title="Change on the day, in basis points. Rising yields are shown in the
                     down colour because for a long-duration book that is the losing direction."
            >
              <Tick value={r.chg_bp === null || r.chg_bp === undefined ? "—" : bp(r.chg_bp, 0)} />
            </span>
          </div>
        ))}
      </div>

      {/* ---- spreads ----------------------------------------------------- */}
      {(rates.spreads ?? []).length > 0 && (
        <div className="flex flex-wrap gap-x-4 gap-y-1 border-t border-ring/40 px-3 py-1.5">
          {rates.spreads.map((s) => (
            <div key={s.key} className="flex items-baseline gap-1.5">
              <RatesPopover rates={rates} pm={pm} className="-mx-1 px-1 py-0">
                <span className="fig text-[10px] text-ink-3">{s.label}</span>
              </RatesPopover>
              <span
                className={cn(
                  "fig text-[11px]",
                  s.note === "inverted" ? "down" : "text-ink",
                )}
                title={s.note}
              >
                {s.unit === "bp" ? `${num(s.value, 0)}bp` : `${s.value.toFixed(2)}%`}
              </span>
            </div>
          ))}
        </div>
      )}
    </Module>
  );
}

function Stat({
  label,
  value,
  sub,
  tone,
}: {
  label: string;
  value: string;
  sub?: string | null;
  tone?: "up" | "down";
}) {
  return (
    <div className="min-w-0">
      <div className="eyebrow text-[9px]">{label}</div>
      <div className={cn("fig text-[15px] leading-tight", tone ?? "text-ink")}>{value}</div>
      {sub && <div className="fig text-[9px] text-ink-3">{sub}</div>}
    </div>
  );
}

/**
 * The strip as a small step chart.
 *
 * A SHAPE, NOT FIFTEEN NUMBERS. The question the strip answers is "which way
 * and how steeply", and fifteen rows of four decimals answers it far worse
 * than a line does. The current policy rate is drawn as a dashed rule across
 * it, so "priced above where we are" reads without comparing two figures.
 */
function Strip({
  strip,
  effr,
}: {
  strip: RatesData["strip"];
  effr: number | null;
}) {
  const vals = strip.map((s) => s.implied);
  const lo = Math.min(...vals, effr ?? Infinity);
  const hi = Math.max(...vals, effr ?? -Infinity);
  const span = hi - lo || 0.25;
  const W = 100;
  const H = 30;
  const x = (i: number) => (i / (strip.length - 1)) * W;
  const y = (v: number) => 3 + (1 - (v - lo) / span) * (H - 6);
  const d = strip.map((s, i) => `${i ? "L" : "M"}${x(i).toFixed(2)},${y(s.implied).toFixed(2)}`).join("");
  const up = vals[vals.length - 1] >= vals[0];

  return (
    <div className="mt-1.5 flex items-center gap-2">
      <svg viewBox={`0 0 ${W} ${H}`} className="h-[34px] w-full" preserveAspectRatio="none">
        {effr !== null && effr >= lo && effr <= hi && (
          <line
            x1={0}
            x2={W}
            y1={y(effr)}
            y2={y(effr)}
            stroke="var(--ink-4)"
            strokeWidth={0.4}
            strokeDasharray="2 2"
          />
        )}
        <path
          d={d}
          fill="none"
          stroke={up ? "var(--put)" : "var(--call)"}
          strokeWidth={1}
          vectorEffect="non-scaling-stroke"
        />
      </svg>
      <div className="fig shrink-0 text-right text-[9px] leading-tight text-ink-3">
        <div>{strip[0]?.label}</div>
        <div>{strip[strip.length - 1]?.label}</div>
      </div>
    </div>
  );
}
