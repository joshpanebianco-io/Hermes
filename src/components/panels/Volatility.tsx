"use client";

import type { VolTerm } from "@/types/terminal";
import { Module } from "@/components/ui/Module";
import { Tick } from "@/components/ui/Tick";
import { num, pct } from "@/lib/format";
import { cn } from "@/lib/cn";

/**
 * The volatility term structure.
 *
 * WHY THE CURVE AND NOT THE LEVEL. VIX on the board says how much movement is
 * priced for the next month. It does not say whether that is normal. The SHAPE
 * does: in calm conditions each further tenor prices more vol than the one
 * before it, and when something is actually wrong the near tenor overtakes the
 * far one. That crossover usually leads the equity move rather than following
 * it, which is the whole reason it is worth a panel of its own.
 *
 * IT SITS UNDER THE GAMMA LADDER BECAUSE IT ANSWERS THE OTHER HALF. Gamma says
 * how dealers are forced to hedge; this says what the options market expects.
 * Positive gamma into a curve tipping toward backwardation is a different
 * session from positive gamma with the curve in healthy contango, and nothing
 * else here separates those two.
 *
 * THE RATIO IS THE HEADLINE, not the four levels. 1.00 is the boundary and the
 * distance from it is the signal, so the bar below is drawn around 1.00 rather
 * than around zero — the reader's question is "how close are we to flipping",
 * not "what is the number".
 */

/** How far either side of 1.00 the bar spans before it clamps. */
const SPAN = 0.25;

export function Volatility({
  vol,
  ageMin,
}: {
  vol: VolTerm | undefined;
  ageMin?: number | null;
}) {
  if (!vol || vol.points.length === 0) {
    return (
      <Module title="Vol term structure" ageMin={ageMin} bodyClassName="px-0 py-0">
        <p className="px-3 py-5 text-center text-[11px] text-ink-3">
          No volatility quotes yet.
        </p>
      </Module>
    );
  }

  const stressed = vol.shape === "backwardation";
  const hue = stressed ? "var(--put)" : vol.shape === "flat" ? "var(--flip)" : "var(--call)";
  const max = Math.max(...vol.points.map((p) => p.value), 1);

  // 0 at 1 - SPAN, 1 at 1 + SPAN. Clamped, because a genuine panic prints
  // ratios well past the span and the marker must stay on its track.
  const pos =
    vol.ratio == null
      ? null
      : Math.max(0, Math.min(1, (vol.ratio - (1 - SPAN)) / (2 * SPAN)));

  return (
    <Module
      title="Vol term structure"
      sub={vol.ratio_label}
      ageMin={ageMin}
      bodyClassName="px-0 py-0"
      right={
        <span
          className="fig qt-pill rounded px-1.5 py-px text-[9.5px] uppercase"
          style={
            {
              color: hue,
              background: `color-mix(in oklab, ${hue} 18%, transparent)`,
              "--pill-hue": stressed ? "var(--put-fig)" : vol.shape === "flat" ? "var(--flip-fig)" : "var(--call-fig)",
            } as React.CSSProperties
          }
        >
          {vol.shape}
        </span>
      }
    >
      {/* ---- the four tenors, as a curve you can read left to right ------- */}
      <ul className="py-1">
        {vol.points.map((p) => (
          <li key={p.key} className="hit flex items-center gap-2 px-3 py-[3px]">
            <span className="fig w-[54px] shrink-0 text-[10.5px] text-ink-2">{p.label}</span>
            <span className="relative h-[8px] flex-1 rounded-sm bg-ring/50">
              <span
                className="absolute inset-y-0 left-0 rounded-sm"
                style={{
                  width: `${(p.value / max) * 100}%`,
                  background: "var(--em)",
                  opacity: 0.75,
                }}
              />
            </span>
            <Tick
              value={num(p.value, 2)}
              className="fig w-[46px] shrink-0 text-right text-[11px] text-ink"
            />
            <Tick
              value={pct(p.pct)}
              className={cn(
                "fig w-[50px] shrink-0 text-right text-[10px]",
                (p.pct ?? 0) > 0 ? "up" : (p.pct ?? 0) < 0 ? "down" : "flat",
              )}
            />
          </li>
        ))}
      </ul>

      {/* ---- the ratio, drawn around 1.00 -------------------------------- */}
      {pos !== null && (
        <div className="border-t border-ring/40 px-3 py-2">
          <div className="flex items-baseline gap-2">
            <Tick
              value={vol.ratio?.toFixed(3)}
              className="fig text-[15px]"
              style={{ color: hue }}
            />
            <span className="eyebrow text-[9px]">{vol.ratio_label}</span>
            {vol.skew != null && (
              <Tick
                value={num(vol.skew, 1)}
                className="fig ml-auto text-[10px] text-ink-3"
                title="Cost of far out-of-the-money puts against at-the-money — what the market pays for a crash rather than for movement"
              >
                SKEW {num(vol.skew, 1)}
              </Tick>
            )}
          </div>

          <div className="relative mt-2 mb-1 h-[9px] rounded-sm bg-ring/50">
            {/* 1.00 — the boundary, not the middle of a range. */}
            <span
              aria-hidden
              className="absolute inset-y-[-3px] left-1/2 w-px -translate-x-1/2 bg-ink-3"
            />
            <span
              className="absolute top-1/2 h-[13px] w-[2px] -translate-y-1/2 rounded-full"
              style={{ left: `calc(${pos * 100}% - 1px)`, background: hue }}
            />
          </div>
          <div className="flex justify-between text-[8.5px] text-ink-3">
            <span>calm</span>
            <span className="fig">1.00</span>
            <span>stressed</span>
          </div>

          {vol.note && (
            <p className="mt-1.5 text-[10px] leading-relaxed text-ink-3">{vol.note}</p>
          )}
        </div>
      )}
    </Module>
  );
}
