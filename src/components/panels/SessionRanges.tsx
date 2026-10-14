"use client";

import type { ExpiryState, SessionRange } from "@/types/terminal";
import { Module } from "@/components/ui/Module";
import { Skeleton } from "@/components/ui/Skeleton";
import { Tick } from "@/components/ui/Tick";
import { num, pct } from "@/lib/format";
import { cn } from "@/lib/cn";
import { segItem } from "@/lib/seg";
import { oneOf, usePersisted } from "@/lib/usePersisted";

/**
 * What each session actually traded.
 *
 * THE PANEL THAT WAS MISSING. A day high and low says the range was 240 points
 * and nothing about who set it — and this desk trades Asia, London and New York,
 * so "which session" is not a detail, it is the question. "London has already
 * taken out the Asia high and failed there" and "Asia set the high at 20:00 and
 * we have bled since" are the same two numbers and opposite setups.
 *
 * EVERY BAR IS DRAWN ON ONE SHARED PRICE AXIS, left is lower and right is
 * higher, and the current price is ONE line through all of them. It used to be
 * the opposite — each bar stretched to fill its own scale so a small session's
 * bar stayed readable — and the owner could not read it (2026-09-22): with five
 * private rulers no bar says anything about the one above it, and on any trend
 * day the marker sat pinned to the end of four bars looking like part of them,
 * with "↑ out" as the only clue. The relationship BETWEEN sessions is the read
 * this panel exists for, so it is now the thing that is drawn: a staircase is a
 * trend, a stack is a range, and "London took out the Asia high" is a bar
 * poking out past the one above it.
 *
 * WHAT THAT COSTS is resolution inside a small session: pre-NY is often a
 * quarter of Asia and its bar is short. It keeps a minimum width so it never
 * vanishes, and its size is printed in points beside it as it always was.
 *
 * A HIGH OR LOW PRINTED IN AMBER HAS BEEN TAKEN OUT — price is beyond it now.
 * The line already shows that; the amber is the same fact where the number is.
 *
 * YESTERDAY'S ROWS ARE DIMMED. Each row is the most recent run of its window,
 * so during Asia the four rows beneath it are the previous day's. One axis
 * invites reading top to bottom as a timeline, and they would break it
 * silently; `prior_day` is worked out by the collector, where the clock is.
 */

const ASSETS = ["NQ", "ES", "GC"];

const HEAD = "fig shrink-0 text-right text-[8.5px] tracking-wide text-ink-3";

// Wide enough for "Europe midday" on one line when the panel has the room; the
// wrapping 52px it always was when it does not, so the track keeps its width.
// One line always: a label that wrapped ("London / open") doubled its row's
// height and broke the shared axis's rhythm in a narrow column. Narrow, it
// truncates and the full name is on hover.
const LABEL =
  "w-[60px] shrink-0 truncate whitespace-nowrap @min-[400px]:w-[84px] qt:w-[72px] qt:@min-[400px]:w-[104px]";

/** The one scale every row shares: all five ranges and the current price. */
function scaleOf(sessions: SessionRange[], last: number | null) {
  const prices: number[] = [];
  for (const s of sessions) {
    if (s.ok && s.low !== null && s.high !== null) prices.push(s.low, s.high);
  }
  if (last !== null) prices.push(last);
  if (!prices.length) return null;
  const lo = Math.min(...prices);
  const hi = Math.max(...prices);
  // A little air at both ends, so the extreme bar and a price line sitting at
  // the extreme are not drawn flush against the edge of the track.
  const pad = Math.max((hi - lo) * 0.04, 1e-9);
  const span = hi - lo + pad * 2;
  return (p: number) => ((p - (lo - pad)) / span) * 100;
}

export function SessionRanges({
  assets,
  expiry,
  ageMin,
  error,
}: {
  assets: Record<string, { last: number | null; sessions: SessionRange[] }>;
  expiry?: ExpiryState;
  ageMin?: number | null;
  error?: string | null;
}) {
  const keys = ASSETS.filter((k) => assets[k]);
  const [sel, setSel] = usePersisted<string>("ranges.asset", "NQ", oneOf("NQ", "ES", "GC"));
  const active = assets[sel] ?? assets[keys[0]];
  const x = active ? scaleOf(active.sessions, active.last) : null;
  const nowX = x && active && active.last !== null ? x(active.last) : null;

  return (
    <Module
      title="Session ranges"
      sub={expiry?.opex_week ? "OpEx week" : undefined}
      ageMin={ageMin}
      error={error}
      bodyClassName="px-0 py-0"
      right={
        keys.length > 1 && (
          <div className="seg">
            {keys.map((k) => (
              <button
                key={k}
                type="button"
                onClick={() => setSel(k)}
                {...segItem(k === sel, { className: "text-[10px] normal-case tracking-normal" })}
              >
                {k}
              </button>
            ))}
          </div>
        )
      }
    >
      {!active || !x ? (
        ageMin == null && !error ? (
          <Skeleton rows={5} label="Loading session ranges" />
        ) : (
          <p className="px-3 py-5 text-center text-[11px] text-ink-3">
            No session data for this book — the collector segments the last two days of bars.
          </p>
        )
      ) : (
        <div className="@container">
          {/* The column names once, and the price the line stands for, riding
              above the line itself. It flips sides at the midpoint so it is
              never pushed out of the track. */}
          <div className="flex items-end gap-2 border-b border-ring/40 px-3 pt-1 pb-0.5">
            <span className={LABEL} />
            <span className="relative h-[11px] min-w-0 flex-1">
              {nowX !== null && (
                <Tick
                  value={num(active.last)}
                  className="fig absolute bottom-0 px-1 text-[9.5px] leading-none text-spot"
                  style={nowX > 50 ? { right: `${100 - nowX}%` } : { left: `${nowX}%` }}
                  title="Current price — the line through every row"
                />
              )}
            </span>
            <span className={cn(HEAD, "w-[44px]")}>low</span>
            <span className={cn(HEAD, "w-[44px]")}>high</span>
            <span className={cn(HEAD, "w-[44px]")} title="Change across that session">
              chg
            </span>
            <span className={cn(HEAD, "hidden w-[28px] sm:block")} title="High minus low, in points">
              rng
            </span>
          </div>
          <ul className="pb-1">
            {active.sessions.map((s) => (
              <Row key={s.key} s={s} last={active.last} x={x} nowX={nowX} />
            ))}
          </ul>
          {expiry && <ExpiryLine e={expiry} />}
        </div>
      )}
    </Module>
  );
}

function Row({
  s,
  last,
  x,
  nowX,
}: {
  s: SessionRange;
  last: number | null;
  x: (p: number) => number;
  nowX: number | null;
}) {
  if (!s.ok || s.low === null || s.high === null) {
    return (
      <li className="flex items-center gap-2 px-3 py-[3px] opacity-45">
        <span className={cn("fig text-[10.5px] text-ink-3", LABEL)}>{s.label}</span>
        <span className="flex-1 text-[10px] text-ink-3">not traded yet</span>
      </li>
    );
  }

  const beyond = last === null ? null : last > s.high ? "above" : last < s.low ? "below" : null;
  const live = s.status === "live" && !s.prior_day;
  // Dims the row's own ink but never the price line, which has to run
  // unbroken through every row to read as one line.
  const dim = s.prior_day && "opacity-45";

  const where =
    last === null
      ? "No current price"
      : beyond === "above"
        ? `Price is ${num(last - s.high, 1)} above everything ${s.label} traded — its high is taken out`
        : beyond === "below"
          ? `Price is ${num(s.low - last, 1)} below everything ${s.label} traded — its low is taken out`
          : `Price is inside this range, ${Math.round((s.pos ?? 0) * 100)}% of the way up it`;

  return (
    <li
      className="hit flex items-center gap-2 px-3"
      title={`${s.label} · ${s.date ?? ""} ${s.start_et ?? ""}–${s.end_et ?? ""} ET${
        live ? " · still trading" : ""
      }${s.prior_day ? " · the PREVIOUS day's — this window has not come round again yet" : ""}
${num(s.low)}–${num(s.high)} · range ${num(s.range, 1)}
${where}`}
    >
      <span className={cn("fig py-[3px] text-[10.5px] text-ink-2", LABEL, dim)} title={s.label}>
        {s.label}
      </span>
      <span className="relative min-w-0 flex-1 self-stretch">
        <span className="absolute inset-x-0 top-1/2 h-px bg-ring/50" />
        {/* Square ends, because the ends of this bar ARE the low and the high. */}
        <span
          className={cn("absolute top-1/2 h-[9px] min-w-[3px] -translate-y-1/2 rounded-[2px]", dim)}
          style={{
            left: `${x(s.low)}%`,
            width: `${x(s.high) - x(s.low)}%`,
            // The session still being built is the bright one.
            background: live ? "var(--em)" : "color-mix(in oklab, var(--em) 50%, transparent)",
          }}
        />
        {nowX !== null && (
          <span
            className="absolute inset-y-0 w-px"
            style={{ left: `calc(${nowX}% - 0.5px)`, background: "var(--spot)" }}
          />
        )}
      </span>
      <Tick
        value={num(s.low, 0)}
        className={cn(
          "fig w-[44px] shrink-0 text-right text-[10px]",
          beyond === "below" ? "text-flip" : "text-ink-3",
          dim,
        )}
      />
      <Tick
        value={num(s.high, 0)}
        className={cn(
          "fig w-[44px] shrink-0 text-right text-[10px]",
          beyond === "above" ? "text-flip" : "text-ink-3",
          dim,
        )}
      />
      <Tick
        value={pct(s.chg_pct)}
        className={cn(
          "fig w-[44px] shrink-0 text-right text-[10px]",
          (s.chg_pct ?? 0) >= 0 ? "up" : "down",
          dim,
        )}
      />
      <span className={cn("fig hidden w-[28px] shrink-0 text-right text-[10px] text-ink-3 sm:block", dim)}>
        {num(s.range, 0)}
      </span>
    </li>
  );
}

/**
 * The expiry line. One sentence, and only when it says something.
 *
 * It matters more here than on an ordinary terminal because the walls this
 * app borrows are open-interest structures with a maturity: in OpEx week the
 * near book is at its largest and price pins to it, and the Monday after, the
 * same strikes carry almost nothing.
 */
function ExpiryLine({ e }: { e: ExpiryState }) {
  const next = e.next?.[0];
  return (
    <div className="flex flex-wrap items-baseline gap-x-2 border-t border-ring/40 px-3 py-1.5 text-[10px]">
      {e.opex_week ? (
        <span className="fig qt-pill rounded bg-flip/20 px-1.5 py-px text-[9px] text-flip [--pill-hue:var(--flip-fig)]">
          OPEX WEEK
        </span>
      ) : (
        <span className="eyebrow text-[9px]">Next</span>
      )}
      {next && (
        <>
          <span className="text-ink-2">{next.label}</span>
          <span className="fig text-ink-3">
            {next.days === 0 ? "today" : `in ${next.days}d`}
          </span>
        </>
      )}
      {e.opex_week && <span className="text-ink-3">{e.note}</span>}
    </div>
  );
}
