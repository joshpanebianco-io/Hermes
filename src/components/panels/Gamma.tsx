"use client";

import type { ExpiryState, GexAsset, ImpliedBook } from "@/types/terminal";
import { Module } from "@/components/ui/Module";
import { GammaPopover, gammaLine } from "@/components/vol/GammaRead";
import { Tick } from "@/components/ui/Tick";
import { num, pct, signed } from "@/lib/format";
import { cn } from "@/lib/cn";
import { segItem } from "@/lib/seg";
import { oneOf, usePersisted } from "@/lib/usePersisted";

/**
 * Gamma levels, borrowed from GEXYGEN.
 *
 * SEVEN NUMBERS PER ASSET AND NOT ONE MORE — three call walls, three put
 * walls, the gamma flip. GEXYGEN is where a gamma map is read, with its strike
 * profile and its greeks; what belongs on a news terminal is the handful of
 * prices that say where dealer hedging turns, so a headline can be judged
 * against them.
 *
 * DRAWN AS A LADDER, IN PRICE ORDER, WITH SPOT IN IT. A table sorted by
 * "call wall, call wall 2, call wall 3, put wall…" is the file's order, not
 * the market's — and on a real chart the third call wall can sit BELOW the
 * first put wall, which a grouped table hides completely. Price order with
 * spot's own row in the stack is the only arrangement where "where are we"
 * and "what is above us" are answered by looking rather than by arithmetic.
 *
 * THE COLOURS ARE GEXYGEN'S, byte-identical, so a wall is the same teal here,
 * there, on the TradingView indicator and in NinjaTrader.
 *
 * RANK IS CHEVRONS, NOT A TRAILING DIGIT — the same ordinal GEXYGEN's Major
 * Walls card draws. "Call wall 2" and "Call wall 3" put the WEAKEST claim in
 * the most prominent position: the ladder is sorted by price, so the numbers
 * ran 2, 3, 1 down the column and the heaviest wall on the side was the one
 * with no number at all. Three chevrons is the heaviest, one is the third, and
 * because it is a mark rather than a digit it reads at a glance without being
 * compared to its neighbours.
 */

export function Gamma({
  assets,
  enabled,
  ageMin,
  error,
  implied,
  expiry,
}: {
  assets: Record<string, GexAsset>;
  enabled: boolean;
  ageMin?: number | null;
  error?: string | null;
  /** Each book's one-sigma day (the Volatility panel's rows), so the flip's distance reads in sigma. */
  implied?: ImpliedBook[] | null;
  /** The expiry block, for the OpEx-week note on the read. */
  expiry?: ExpiryState | null;
}) {
  const keys = Object.keys(assets);
  const [sel, setSel] = usePersisted<string>("gex.asset", "NQ", oneOf("NQ", "ES", "GC"));
  const active = assets[sel] ?? assets[keys[0]];
  const book = assets[sel] ? sel : keys[0];
  const sigma = implied?.find((b) => b.key === book)?.sigma ?? null;

  return (
    <Module
      title="Gamma levels"
      // "0DTE", not "book front": the served window is the front expiry
      // alone (engine: "whatever its DTE"), which is today's expiry during
      // the NY session and the next session's overnight — 0DTE in the sense
      // a trader means it. "front" is engine vocabulary nobody trades.
      sub={active?.book ? (active.book === "front" ? "0DTE" : `book ${active.book}`) : undefined}
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
      {!enabled ? (
        <Note>
          Disabled by configuration — <code className="text-ink-3">NT_GEXYGEN_API</code> is empty.
        </Note>
      ) : !active ? (
        <Note>No assets configured.</Note>
      ) : !active.ok ? (
        <Note>
          {active.error ?? "unavailable"}
          <span className="mt-1 block text-ink-3">
            These come from GEXYGEN&rsquo;s compute service. Start it and this fills in.
          </span>
        </Note>
      ) : (
        <Ladder a={active} book={book} sigma={sigma} expiry={expiry} />
      )}
    </Module>
  );
}

function Note({ children }: { children: React.ReactNode }) {
  return <p className="px-3 py-5 text-center text-[11px] leading-relaxed text-ink-3">{children}</p>;
}

const SIDE_HUE = {
  call: "var(--call)",
  put: "var(--put)",
  flip: "var(--flip)",
} as const;

function Ladder({
  a,
  book,
  sigma,
  expiry,
}: {
  a: GexAsset;
  book: string;
  sigma: number | null;
  expiry?: ExpiryState | null;
}) {
  const spot = a.spot ?? 0;
  const line = gammaLine(a, sigma, expiry);
  // Spot is spliced into the level list so the ladder has a "you are here"
  // rung rather than a colour the reader has to locate.
  const rungs: {
    kind: "level" | "spot";
    price: number;
    label: string;
    side: "call" | "put" | "flip" | "spot";
    dist: number | null;
    distPct: number | null;
    rank: number;
  }[] = [
    ...a.levels.map((l) => ({
      kind: "level" as const,
      price: l.price,
      label: l.label,
      side: l.side,
      dist: l.dist,
      distPct: l.dist_pct,
      rank: l.rank,
    })),
    {
      kind: "spot" as const,
      price: spot,
      label: "Spot",
      side: "spot" as const,
      dist: 0,
      distPct: 0,
      rank: 0,
    },
  ].sort((x, y) => y.price - x.price);

  return (
    <div>
      <div className="flex items-baseline gap-2 border-b border-ring/40 px-3 py-1.5">
        <Tick value={num(spot)} className="fig text-[14px] text-ink" />
        {a.regime && (
          <span
            className="fig qt-pill rounded px-1.5 py-px text-[9.5px]"
            style={
              {
                background:
                  a.regime === "POS"
                    ? "color-mix(in oklab, var(--call) 20%, transparent)"
                    : "color-mix(in oklab, var(--put) 20%, transparent)",
                color: a.regime === "POS" ? "var(--call)" : "var(--put)",
                "--pill-hue": a.regime === "POS" ? "var(--call-fig)" : "var(--put-fig)",
              } as React.CSSProperties
            }
            title={
              a.regime === "POS"
                ? "Positive gamma: dealer hedging dampens moves"
                : "Negative gamma: dealer hedging amplifies moves"
            }
          >
            {a.regime === "POS" ? "POSITIVE γ" : "NEGATIVE γ"}
          </span>
        )}
      </div>
      {/* THE READ (owner, 2026-10-22): spot against the flip in points and in
          the book's own sigma, the regime's rule, the walls either side, OpEx
          week — one sentence, and the trigger for the rules behind it. */}
      {line && (
        <GammaPopover
          asset={a}
          book={book}
          sigma={sigma}
          expiry={expiry}
          className="block w-full border-b border-ring/40 px-3 py-1.5 text-left"
        >
          <span className="block text-[10.5px] leading-[1.45] text-ink-2">{line}</span>
        </GammaPopover>
      )}
      <ul>
        {rungs.map((r) => {
          const isSpot = r.kind === "spot";
          const hue = isSpot ? "var(--spot)" : SIDE_HUE[r.side as keyof typeof SIDE_HUE];
          return (
            <li
              /*
               * KEYED BY THE RUNG'S IDENTITY, NOT BY ITS PRICE. This was
               * `${r.label}-${r.price}`, so the moment a wall moved to a
               * different strike React unmounted the row and mounted a fresh
               * one. That is correct React and it silently defeats the change
               * flash, because a remounted `Tick` has no memory of a previous
               * value -- the one figure most worth flashing, a wall RELOCATING,
               * would be the only one that never could. GEXYGEN hit this exact
               * bug in Major Walls. The label is the stable identity: "the
               * second call wall" is the same rung whichever strike holds it.
               */
              key={r.label}
              className={cn(
                "hit relative flex items-center gap-2 px-3 py-[3px]",
                isSpot && "bg-ink/[0.06]",
              )}
            >
              <span
                aria-hidden
                className="absolute inset-y-0 left-0 w-[2px]"
                style={{ background: hue, opacity: isSpot ? 1 : 1 / Math.max(1, r.rank) }}
              />
              {r.side === "call" || r.side === "put" ? (
                <span
                  className="flex w-[74px] shrink-0 items-baseline gap-1"
                  style={{ color: hue }}
                  title={`${r.label} — ${["", "heaviest", "second", "third"][r.rank] ?? ""} on the side`}
                >
                  <span className="fig text-[10.5px]">
                    {r.side === "call" ? "Call" : "Put"}
                  </span>
                  <span
                    aria-label={`rank ${r.rank} of 3`}
                    className="text-[9px] leading-none tracking-[-0.15em]"
                  >
                    {(r.side === "call" ? "▲" : "▼").repeat(Math.max(1, 4 - r.rank))}
                  </span>
                </span>
              ) : (
                <span
                  className="fig w-[74px] shrink-0 truncate text-[10.5px]"
                  style={{ color: hue }}
                >
                  {r.label}
                </span>
              )}
              <Tick value={num(r.price)} className="fig flex-1 text-right text-[11.5px] text-ink" />
              <Tick
                value={isSpot ? "—" : signed(r.dist, 0)}
                className="fig w-[62px] shrink-0 text-right text-[10.5px] text-ink-3"
              />
              <Tick
                value={isSpot ? "" : pct(r.distPct)}
                className={cn(
                  "fig w-[54px] shrink-0 text-right text-[10.5px]",
                  isSpot ? "text-ink-4" : (r.distPct ?? 0) >= 0 ? "up" : "down",
                )}
              />
            </li>
          );
        })}
      </ul>
    </div>
  );
}
