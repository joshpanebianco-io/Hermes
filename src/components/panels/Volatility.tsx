"use client";

import type { PutCall, VolTerm } from "@/types/terminal";
import { Module } from "@/components/ui/Module";
import { Skeleton } from "@/components/ui/Skeleton";
import { Tick } from "@/components/ui/Tick";
import { ImpliedPopover } from "@/components/vol/ImpliedDay";
import { fuelTone, premiumTone } from "@/lib/vix";
import { num, pct } from "@/lib/format";
import { cn } from "@/lib/cn";

/**
 * Volatility — the term structure, and under it the implied day per book.
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
 *
 * THE FOOT IS THE SAME QUESTION IN THE BOOKS' OWN UNITS (owner, 2026-10-22:
 * "should we also include implied volatility?"). The curve is the S&P 500's
 * and says what the options market expects in percent; the desk trades NQ, ES
 * and GC in points. Each row is a book's one-sigma day from its own index —
 * VXN, VIX, GVZ — with how much of it today's Globex range has used and
 * implied against realised, every word the server's (volterm.implied_day),
 * scored with the stocks desk's own thresholds so the two desks never disagree
 * about a number. A row opens the bands behind it, the way every VIX figure
 * opens the VIX bands. ON THE FUTURES TERMINAL ONLY: the stocks desk's Market
 * tab draws this panel without the foot, because its weather strip already
 * carries SPY's and QQQ's implied day and fuel.
 */

/** How far either side of 1.00 the bar spans before it clamps. */
const SPAN = 0.25;

export function Volatility({
  vol,
  ageMin,
  implied = false,
  putcall,
}: {
  vol: VolTerm | undefined;
  ageMin?: number | null;
  /** Draw the implied-day foot — the futures Terminal; the Market tab leaves it off. */
  implied?: boolean;
  /** Cboe's daily put/call ratios (sources/cboepc) — both desks. */
  putcall?: PutCall | null;
}) {
  const sub = implied ? "VIX curve · implied day" : "VIX curve";
  if (!vol || vol.points.length === 0) {
    return (
      <Module title="Volatility" sub={sub} ageMin={ageMin} bodyClassName="px-0 py-0">
        {ageMin == null ? (
          <Skeleton rows={4} label="Loading the vol curve" />
        ) : (
          <p className="px-3 py-5 text-center text-[11px] text-ink-3">
            The quote feed carries none of the VIX tenors right now.
          </p>
        )}
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

  const books = implied ? (vol.books ?? []) : [];

  return (
    <Module
      title="Volatility"
      sub={sub}
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

      {/* ---- Cboe's daily put/call: the market-wide options positioning ----
          The equity ratio is the sentiment gauge the tape quotes — contrarian
          and slow, a read for the week and never a timing tool for the open,
          which the hover says. The figures and the reads are the collector's
          (sources/cboepc), with the log's twenty-day average beside each. */}
      {putcall?.ratios && (
        <div
          className="flex flex-wrap items-baseline gap-x-3 gap-y-0.5 border-t border-ring/40 px-3 py-1.5 text-[10px] text-ink-3"
          title={[
            `Cboe's daily put/call ratios for ${putcall.date} (${putcall.days} days held)`,
            putcall.read.equity ? `Equity ${putcall.read.equity}` : null,
            putcall.read.total ? `Total ${putcall.read.total}` : null,
            "Contrarian and slow: a read for the week, not the open.",
          ]
            .filter(Boolean)
            .join("\n")}
        >
          <span className="eyebrow text-[9px]">Cboe put/call</span>
          {(["equity", "total", "index"] as const).map((k) => {
            const v = putcall.ratios[k];
            const a = putcall.avg20?.[k];
            return v == null ? null : (
              <span key={k} className="fig">
                {k} <span className="text-ink">{v.toFixed(2)}</span>
                {a != null && <span className="text-ink-4"> · 20d {a.toFixed(2)}</span>}
              </span>
            );
          })}
          <span className="fig ml-auto text-ink-4">{putcall.date.slice(5)}</span>
        </div>
      )}

      {/* ---- the implied day, per book: the curve in the books' own points --
          Each row is the trigger for its long form (ImpliedDay). NOTHING
          WRAPS: a figure that breaks across two lines in a 3px row is noise,
          so every cell is sized to its widest print (ES's band is 19 figures
          at two decimals, "1.25× stretched" is 15) and the band column, the
          sigma written out twice, gives way first when the column is narrow —
          the sigma, the index and the two words are the read. */}
      {books.length > 0 && (
        <div className="@container border-t border-ring/40 pt-1.5 pb-1">
          <div className="flex items-baseline gap-2 px-3 pb-1">
            <span className="eyebrow text-[9px]">Implied day</span>
            <span className="text-[9.5px] text-ink-3">1σ · used since 18:00 ET · implied / realised</span>
          </div>
          <ul>
            {books.map((b) => (
              <li key={b.key}>
                <ImpliedPopover book={b} className="flex w-full items-center gap-1.5 px-3 py-[3px] whitespace-nowrap">
                  <span className="fig w-[22px] shrink-0 text-[10.5px] text-ink-2">{b.key}</span>
                  <Tick
                    value={b.sigma != null ? `±${num(b.sigma, b.dp)}` : "—"}
                    className="fig w-[56px] shrink-0 text-[11px] text-ink"
                  />
                  <span className="fig hidden w-[144px] shrink-0 text-[10px] text-ink-3 @min-[530px]:inline">
                    {b.lo != null && b.hi != null ? `${num(b.lo, b.dp)} – ${num(b.hi, b.dp)}` : ""}
                  </span>
                  <span className="fig w-[62px] shrink-0 text-[10px] text-ink-3">
                    {b.vol_key} {num(b.vol, 1)}
                  </span>
                  <Tick
                    value={b.used != null && b.fuel ? `${b.used.toFixed(2)}× ${b.fuel}` : "—"}
                    className={cn("fig ml-auto w-[118px] shrink-0 text-right text-[10.5px]", fuelTone(b.fuel))}
                  />
                  <Tick
                    value={b.iv_rv != null && b.premium ? `${b.iv_rv.toFixed(2)} ${b.premium}` : "—"}
                    className={cn("fig w-[72px] shrink-0 text-right text-[10.5px]", premiumTone(b.premium))}
                  />
                </ImpliedPopover>
              </li>
            ))}
          </ul>
        </div>
      )}
    </Module>
  );
}
