"use client";

import { useEffect, useRef, useState, type ReactNode } from "react";
import type { BriefContextPulse, BriefContextRotation, BriefContextWords, BriefGammaMap, BriefMarketContext } from "@/types/terminal";
import { AssetIcon } from "@/components/ui/AssetIcon";
import { SectorGlyph } from "@/components/ui/SectorGlyph";
import { TickerLogo } from "@/components/ui/TickerLogo";
import { SENTIMENT_WORDS, SentimentBar, sentimentSide } from "@/components/panels/MarketOutlook";
import { cn } from "@/lib/cn";
import { dir, pct } from "@/lib/format";
import { gammaPrice, layoutGamma, type GammaKind } from "@/lib/gammaMap";

/**
 * THE MARKET REPORT'S MARKET CONTEXT: the day's backdrop, charted, with what it means.
 *
 * WHY (owner, 2026-11-21: "in our market reports in both stocks and futures sectionsm, we
 * should summaries the market pulse, sector rotations and gex context. for the stocks
 * section report maybe just have the SPY gex levels"). Its first build was three lines of
 * text the engine wrote, and the owner's word on it: "it needs to have nisce visuals and it
 * is way too bland. use the ai model to summarise and tlak about it and how it affects the
 * market. i want it to look like aprofessional market report". Of the full-size picture of
 * this layout over their own two reports: "go ahead".
 *
 * So: a lead paragraph, then three panels side by side, each a chart of the engine's
 * figures with the model's paragraph under it.
 *   - Market Pulse: the fear-to-greed scale the card draws (the same bar), then a bar a
 *     market: its move measured in its own usual day, so silver's 7% and the note's 0.9%
 *     are read on one scale.
 *   - Sector Rotation: the eleven sectors best to worst about a zero line, then the index
 *     against its equal-weight twin, which says whether the largest names made the day.
 *   - Dealer Gamma: a map. The line is price; the flip splits it into the zone where
 *     hedging adds to moves and the zone where it damps them; the walls are ticks, the
 *     expected move a bracket, the price a dot. SPY alone on the Stocks report, the
 *     report's own contract on a futures one.
 *
 * WHO WROTE WHAT. Every figure and chart is the engine's, stored with the report (server
 * briefctx.py), so the section reads as it was written. The lead and the three paragraphs
 * are the model's (`body.context`), checked by the report's numeral guard. Where the model
 * wrote nothing for a panel the engine's own line stands under the chart.
 *
 * GAMMA IS NOT A SIDE, SO IT IS NOT A SIDE'S COLOUR (owner, 2026-11-12: "positive doesnt
 * mean bullish and vice versa"). The regime's word is in ink and the zones are the flip's
 * amber and a grey. A wall wears the hue the gamma card gives its kind (panels/Gamma), a
 * move in the other two panels the green and pink every move wears.
 *
 * A REPORT WRITTEN BEFORE THE CHARTS (the morning of 2026-11-21) has the three lines and
 * no figures: it prints its lines, as it did.
 */

const CAP = "qt-cap text-[10.5px] tracking-[0.09em] text-ink-3";
/*
 * THE CHARTS' OWN SMALL CAPS (the scale's five words, a tick's "Put wall", "Expected
 * move"): the caps label's face at the size the approved picture drew them, 9px. Not
 * `qt-cap`: Luminous sets every `qt-cap` to 11.5px (globals.css), and at that size the
 * scale's five words ran past the bar's end on a 1920 screen, where a panel is 445px wide.
 */
const MICRO = "font-[family-name:var(--font-cond)] leading-none font-semibold whitespace-nowrap uppercase";

function fill(v: number): string {
  return v > 0 ? "bg-call-fig" : v < 0 ? "bg-put-fig" : "bg-ink-3";
}

/** A move that prints "+0.0%" is flat: no colour, as on the card. */
const flat = (v: number, dp: number): number => (Math.abs(v) < 0.5 / 10 ** dp ? 0 : v);

export function ContextSection({
  head,
  ctx,
  words,
  who,
  rule,
  className,
}: {
  /** The sheet's own section heading, drawn by the report (panels/Brief SheetHead). */
  head: ReactNode;
  ctx: BriefMarketContext;
  /** The model's lead and paragraphs. */
  words?: BriefContextWords;
  /** Whom the paragraphs are about: "stocks", or the report's contract. */
  who: string;
  /** The sheet's rule colour for the paint it is drawn in. */
  rule: string;
  className?: string;
}) {
  const rows = ctx.rows ?? [];
  const line = (key: string) => rows.find((r) => r.key === key)?.text;
  const panels: { key: "pulse" | "rotation" | "gamma"; body: ReactNode }[] = [];
  if (ctx.pulse) panels.push({ key: "pulse", body: <PulsePanel p={ctx.pulse} /> });
  if (ctx.rotation) panels.push({ key: "rotation", body: <RotationPanel r={ctx.rotation} rule={rule} /> });
  if (ctx.gamma?.length) panels.push({ key: "gamma", body: <GammaPanel maps={ctx.gamma} rule={rule} /> });
  if (!rows.length && !panels.length) return null;
  return (
    <section className={cn("border-t py-6", className)} aria-label="Market context">
      {head}
      {words?.lead && <p className="max-w-[1180px] text-[16px] leading-[1.5] tracking-[-0.003em] text-ink">{words.lead}</p>}
      {panels.length > 0 ? (
        <div
          className={cn(
            "grid border-t pt-4",
            rule,
            words?.lead ? "mt-5" : "mt-1",
            panels.length >= 3 ? "xl:grid-cols-3" : panels.length === 2 ? "xl:grid-cols-2" : "",
          )}
        >
          {panels.map((p, i) => {
            const said = words?.[p.key];
            const text = said ?? line(p.key);
            return (
              // TWO ROWS SHARED BY THE THREE PANELS (subgrid): the charts are the first and
              // the paragraphs the second, so the three "What it means" start on one line
              // however tall each chart is and however long each paragraph runs. Pinned to
              // the foot of its own column instead, a three-line paragraph began a line
              // lower than the four-line one beside it.
              <div
                key={p.key}
                className={cn(
                  "min-w-0 pt-1 xl:row-span-2 xl:grid xl:grid-rows-subgrid",
                  rule,
                  i > 0 && "max-xl:mt-6 max-xl:border-t max-xl:pt-5 xl:border-l xl:pl-7",
                  i < panels.length - 1 && "xl:pr-7",
                )}
              >
                <div className="min-w-0">{p.body}</div>
                <div className="min-w-0">
                  {text && (
                    <div className={cn("mt-4 border-t pt-[11px]", rule)}>
                      <p className={CAP}>{said ? `What it means for ${who}` : "In short"}</p>
                      <p className="mt-1.5 text-[13.5px] leading-[1.55] text-ink-2">{text}</p>
                    </div>
                  )}
                </div>
              </div>
            );
          })}
        </div>
      ) : (
        <dl className={cn("border-t", rule)}>
          {rows.map((r, i) => (
            <div key={`${r.key}-${i}`} className={cn("grid gap-x-4 gap-y-1 border-b py-2.5 md:grid-cols-[150px_minmax(0,1fr)]", rule)}>
              <dt className="text-[12.5px] leading-[1.5] font-semibold text-ink">{r.label}</dt>
              <dd className="text-[13.5px] leading-[1.5] text-ink-2">{r.text}</dd>
            </div>
          ))}
        </dl>
      )}
    </section>
  );
}

// ---- Market Pulse --------------------------------------------------------------------------------

function PulsePanel({ p }: { p: BriefContextPulse }) {
  const side = p.score == null ? "none" : sentimentSide(p.score);
  const ink = side === "fear" ? "text-put-fig" : side === "greed" ? "text-call-fig" : "text-ink";
  const what = p.what ? `${p.what.charAt(0).toUpperCase()}${p.what.slice(1)}.` : "";
  return (
    <>
      <p className={CAP}>Market Pulse</p>
      <p className="mt-2 flex flex-wrap items-baseline gap-x-2.5 gap-y-1">
        {p.label && p.score != null ? (
          <>
            <span className={cn("text-[22px] leading-none font-semibold tracking-[-0.01em]", ink)}>{p.label}</span>
            <span className="fig text-[17px] leading-none text-ink">
              {p.score > 0 ? "+" : ""}
              {p.score}
            </span>
            <span className="text-[12.5px] font-semibold text-ink">{p.name}</span>
          </>
        ) : (
          <span className="text-[22px] leading-none font-semibold tracking-[-0.01em] text-ink">{p.name}</span>
        )}
      </p>
      {p.score != null && (
        <div role="img" aria-label={`${p.label ?? ""}, ${p.score} on the fear to greed scale`}>
          <span className="mt-3 flex">
            <SentimentBar score={p.score} roomy />
          </span>
          <p className={cn(MICRO, "mt-[5px] grid grid-cols-5 text-[9px] tracking-[0.08em] text-ink-3")}>
            {SENTIMENT_WORDS.map((w, i) => (
              <span key={w} className={cn(i === 0 ? "text-left" : i === 4 ? "text-right" : "text-center", w === p.label && "text-ink")}>
                {w}
              </span>
            ))}
          </p>
        </div>
      )}
      {what && <p className="mt-3 text-[12.5px] leading-[1.4] text-ink-2">{what}</p>}
      <ul className="mt-2">
        {p.rows.map((r) => {
          const v = flat(r.pct, 1);
          // A full bar is three of the market's usual days: the scale the card's arrows use.
          const w = (Math.min(3, Math.abs(r.mult)) / 3) * 50;
          const name = r.group === "Stocks" ? r.name : r.group;
          return (
            <li
              key={r.key}
              title={`${name} ${pct(r.pct, 2)}, ${Math.abs(r.mult).toFixed(1)} times its usual day${r.sized ? "" : " (a stated usual day: too little history to measure one)"}`}
              className="grid h-[27px] grid-cols-[22px_96px_minmax(0,1fr)_56px_44px] items-center gap-x-2.5"
            >
              <AssetIcon id={r.key} size={18} className="block shrink-0 text-ink-2" />
              <span className="truncate text-[12.5px] font-semibold text-ink">{name}</span>
              <span aria-hidden className="relative block h-3">
                <span className="absolute inset-x-0 inset-y-[2px] rounded-[2px] bg-[color-mix(in_oklab,var(--ink-3)_13%,transparent)]" />
                {v !== 0 && (
                  <span
                    className={cn("absolute top-[2px] h-2 rounded-[2px] opacity-90", fill(v))}
                    style={{ left: `${v < 0 ? 50 - w : 50}%`, width: `${w}%` }}
                  />
                )}
                <span className="absolute -inset-y-[2px] left-1/2 w-px bg-ink-3" />
              </span>
              <span className={cn("fig text-right text-[12.5px]", dir(v))}>{pct(r.pct, 1)}</span>
              <span className="fig text-right text-[11px] whitespace-nowrap text-ink-3">
                {r.sized ? "" : "~"}
                {Math.abs(r.mult).toFixed(1)}×
              </span>
            </li>
          );
        })}
      </ul>
      <p className="mt-1.5 text-[11px] leading-[1.4] text-ink-3">
        Each bar is that market&apos;s move measured in its own usual day; a full bar is three times usual. {p.tell}
      </p>
    </>
  );
}

// ---- Sector Rotation -----------------------------------------------------------------------------

const SECTOR_ROW = "grid h-[22px] grid-cols-[18px_138px_minmax(0,1fr)_62px] items-center gap-x-2.5";

function RotationPanel({ r, rule }: { r: BriefContextRotation; rule: string }) {
  const pair = r.spy != null && r.rsp != null ? [r.spy, r.rsp] : [];
  const all = [...r.sectors.map((s) => s.pct), ...pair];
  const lo = Math.min(0, ...all);
  const hi = Math.max(0, ...all);
  const at = (v: number) => ((v - lo) / (hi - lo || 1)) * 100;
  const zero = at(0);
  const bar = (v: number, thin = false) => (
    <span aria-hidden className="relative block h-3">
      <span
        className={cn("absolute rounded-[2px] opacity-90", fill(v), thin ? "top-[3.5px] h-[5px]" : "top-[2px] h-2")}
        // A sector flat on the day still has a mark at the line, so its row is not empty.
        style={{ left: `${Math.min(zero, at(v))}%`, width: `${Math.max(0.6, Math.abs(at(v) - zero))}%` }}
      />
      <span className="absolute -inset-y-[2px] w-px bg-ink-3" style={{ left: `${zero}%` }} />
    </span>
  );
  return (
    <>
      <p className={CAP}>Sector Rotation</p>
      <p className="mt-2 flex items-baseline gap-2">
        <span className="fig text-[22px] leading-none font-semibold text-ink">
          {r.up} of {r.n}
        </span>
        <span className="text-[14px] text-ink-2">sectors up{r.pre ? " before the bell" : ""}</span>
        <span className="ml-auto text-[11.5px] whitespace-nowrap text-ink-3">best to worst</span>
      </p>
      <ul className="mt-3">
        {r.sectors.map((s) => (
          <li key={s.key} className={SECTOR_ROW} title={`${s.label} (${s.key}) ${pct(s.pct)}`}>
            <SectorGlyph fund={s.key} size={15} className="block shrink-0 text-ink-3" />
            <span className="truncate text-[12.5px] font-semibold text-ink">{s.label}</span>
            {bar(s.pct)}
            <span className={cn("fig text-right text-[12.5px]", dir(flat(s.pct, 2)))}>{pct(s.pct)}</span>
          </li>
        ))}
      </ul>
      {r.spy != null && r.rsp != null && (
        <div className={cn("mt-[9px] border-t pt-[9px]", rule)}>
          <ul>
            {(
              [
                ["S&P 500", r.spy, "Every stock weighted by its size"],
                ["Equal weight", r.rsp, "The same stocks, each counted the same"],
              ] as const
            ).map(([name, v, title]) => (
              <li key={name} className={SECTOR_ROW} title={title}>
                <span />
                <span className="truncate text-[12.5px] font-semibold text-ink">{name}</span>
                {bar(v, true)}
                <span className={cn("fig text-right text-[12.5px]", dir(flat(v, 2)))}>{pct(v)}</span>
              </li>
            ))}
          </ul>
          {r.breadth && <p className="mt-1 text-[11px] leading-[1.4] text-ink-3">{r.breadth}</p>}
        </div>
      )}
    </>
  );
}

// ---- Dealer Gamma --------------------------------------------------------------------------------

const KIND_WORD: Record<GammaKind, string> = { put: "Put wall", call: "Call wall", flip: "Flip" };
const KIND_INK: Record<GammaKind, string> = { put: "text-put-fig", call: "text-call-fig", flip: "text-flip-fig" };
const KIND_FILL: Record<GammaKind, string> = { put: "bg-put-fig", call: "bg-call-fig", flip: "bg-flip-fig" };
const ZONE_BELOW = "bg-[color-mix(in_oklab,var(--flip-fig)_24%,transparent)]";
const ZONE_ABOVE = "bg-[color-mix(in_oklab,var(--ink-3)_17%,transparent)]";

function GammaPanel({ maps, rule }: { maps: BriefGammaMap[]; rule: string }) {
  return (
    <>
      {maps.map((g, i) => (
        <div key={g.name} className={cn(i > 0 && "mt-6")}>
          <GammaOne g={g} rule={rule} />
        </div>
      ))}
    </>
  );
}

function GammaOne({ g, rule }: { g: BriefGammaMap; rule: string }) {
  const P = (v: number) => gammaPrice(v, g.dp);
  const near = (n: BriefGammaMap["above"]) =>
    n && (
      <>
        {KIND_WORD[n.kind]} {P(n.price)} <span className="text-ink-3">· {P(n.away)} away</span>
      </>
    );
  const facts: { name: string; swatch: string; value: ReactNode }[] = [];
  if (g.flip != null) facts.push({ name: "Flip", swatch: KIND_FILL.flip, value: P(g.flip) });
  if (g.above) facts.push({ name: "Nearest above", swatch: "bg-ink-3", value: near(g.above) });
  if (g.below) facts.push({ name: "Nearest below", swatch: "bg-ink-3", value: near(g.below) });
  if (g.calls.length) facts.push({ name: g.calls.length > 1 ? "Call walls" : "Call wall", swatch: KIND_FILL.call, value: g.calls.map(P).join(" · ") });
  if (g.puts.length) facts.push({ name: g.puts.length > 1 ? "Put walls" : "Put wall", swatch: KIND_FILL.put, value: g.puts.map(P).join(" · ") });
  if (g.em) facts.push({ name: "Expected move", swatch: "bg-ink-2", value: `${P(g.em[0])} – ${P(g.em[1])}` });
  return (
    <>
      <p className={cn(CAP, "flex items-center gap-1.5")}>
        Dealer Gamma ·
        {g.name === "SPY" ? <TickerLogo sym="SPY" size={13} /> : <AssetIcon id={g.name} size={13} className="block shrink-0" />}
        {g.name}
      </p>
      <p className="mt-2 flex flex-wrap items-baseline gap-x-2.5 gap-y-1">
        <span className="text-[22px] leading-none font-semibold tracking-[-0.01em] text-ink">
          {g.regime === "NEG" ? "Negative gamma" : g.regime === "POS" ? "Positive gamma" : "Gamma levels"}
        </span>
        {g.to_flip != null && (
          <span className="text-[12.5px] text-ink-2">
            <span className="fig text-ink">{P(g.to_flip)}</span> {g.below_flip ? "below" : "above"} the flip
          </span>
        )}
      </p>
      {g.regime && (
        <p className="mt-[7px] text-[12.5px] leading-[1.4] text-ink-2">
          {g.regime === "NEG" ? "Dealers hedge with the move: breaks run and ranges widen." : "Dealers hedge against the move: ranges tend to hold."}
        </p>
      )}
      <GammaMap g={g} />
      {g.flip != null && (
        <p className="mt-2 flex flex-wrap gap-x-[18px] gap-y-1 text-[11px] leading-[1.3]">
          <span className={cn("inline-flex items-center gap-1.5", g.below_flip ? "text-ink-2" : "text-ink-3")}>
            <span aria-hidden className={cn("h-[9px] w-[14px] rounded-[2px]", ZONE_BELOW)} />
            Below the flip: negative gamma, moves run
          </span>
          <span className={cn("inline-flex items-center gap-1.5", g.below_flip ? "text-ink-3" : "text-ink-2")}>
            <span aria-hidden className={cn("h-[9px] w-[14px] rounded-[2px]", ZONE_ABOVE)} />
            Above it: positive gamma, moves fade
          </span>
        </p>
      )}
      <ul className={cn("mt-3 border-t", rule)}>
        {facts.map((f) => (
          <li key={f.name} className={cn("grid grid-cols-[10px_104px_minmax(0,1fr)] items-baseline gap-x-[9px] border-b py-[5px]", rule)}>
            <span aria-hidden className={cn("h-2 w-2 self-center rounded-[2px]", f.swatch)} />
            <span className="text-[12.5px] font-semibold text-ink">{f.name}</span>
            <span className="fig text-right text-[12.5px] text-ink">{f.value}</span>
          </li>
        ))}
      </ul>
    </>
  );
}

const TRACK = 20;
const LANE = 31;

/**
 * The map: price left to right, the flip splitting it into its two zones, the walls as
 * ticks with their prices under the line, the expected move as a bracket over it, the
 * price as a dot with its figure above. Laid out once the panel has a width
 * (lib/gammaMap), so two walls that are close take two rows.
 */
function GammaMap({ g }: { g: BriefGammaMap }) {
  const ref = useRef<HTMLDivElement>(null);
  const [width, setWidth] = useState(0);
  useEffect(() => {
    const el = ref.current;
    if (!el) return;
    const measure = () => setWidth(el.clientWidth);
    measure();
    const ro = new ResizeObserver(measure);
    ro.observe(el);
    return () => ro.disconnect();
  }, []);
  const r = width > 0 ? layoutGamma(g, width) : null;
  const P = (v: number) => gammaPrice(v, g.dp);
  // Room over the line for the price's figure, and for the bracket and its word when there
  // is one: the word's own line, a gap, then the bracket.
  const top = g.em ? 50 : 30;
  const BRACKET = 32;
  const height = top + TRACK + 8 + (r ? r.lanes : 1) * LANE;
  const said = [
    `${g.name} ${P(g.last)}`,
    g.flip != null ? `flip ${P(g.flip)}` : "",
    g.puts.length ? `put walls ${g.puts.map(P).join(", ")}` : "",
    g.calls.length ? `call walls ${g.calls.map(P).join(", ")}` : "",
    g.em ? `expected move ${P(g.em[0])} to ${P(g.em[1])}` : "",
  ]
    .filter(Boolean)
    .join("; ");
  return (
    <div ref={ref} role="img" aria-label={`Gamma map: ${said}`} className="relative mt-3.5 w-full" style={{ height }}>
      {r && (
        <>
          {r.em && (
            <>
              <span
                aria-hidden
                className="absolute h-[7px] rounded-t-[2px] border border-b-0 border-ink-3"
                style={{ top: BRACKET, left: r.em[0], width: r.em[1] - r.em[0] }}
              />
              {/* The word sits at whichever end of the bracket the price is not under. */}
              <span
                className={cn(MICRO, "absolute text-[9px] tracking-[0.08em] text-ink-3")}
                style={r.last > (r.em[0] + r.em[1]) / 2 ? { top: 19, left: r.em[0] } : { top: 19, left: r.em[1], transform: "translateX(-100%)" }}
              >
                Expected move
              </span>
            </>
          )}
          {r.flip != null ? (
            <>
              <span aria-hidden className={cn("absolute left-0 rounded-l-[3px]", ZONE_BELOW)} style={{ top, height: TRACK, width: r.flip }} />
              <span aria-hidden className={cn("absolute rounded-r-[3px]", ZONE_ABOVE)} style={{ top, height: TRACK, left: r.flip, width: Math.max(0, width - r.flip) }} />
            </>
          ) : (
            <span aria-hidden className={cn("absolute inset-x-0 rounded-[3px]", ZONE_ABOVE)} style={{ top, height: TRACK }} />
          )}
          {r.marks.map((m) => (
            <span key={`${m.kind}-${m.price}`}>
              <span
                aria-hidden
                className={cn("absolute w-[2px] -translate-x-1/2", KIND_FILL[m.kind], m.lane > 0 && "opacity-55")}
                style={{ top: top - 3, left: m.x, height: TRACK + 6 + m.lane * LANE }}
              />
              <span className="absolute -translate-x-1/2 text-center leading-[1.15] whitespace-nowrap" style={{ top: top + TRACK + 6 + m.lane * LANE, left: m.x }}>
                <span className={cn(MICRO, "block text-[8.5px] tracking-[0.07em] text-ink-3")}>{KIND_WORD[m.kind]}</span>
                <span className={cn("fig block text-[11.5px]", KIND_INK[m.kind])}>{P(m.price)}</span>
              </span>
            </span>
          ))}
          <span aria-hidden className="absolute w-px bg-ink-3" style={{ top: 17, left: r.last, height: top - 17 }} />
          <span
            aria-hidden
            className="absolute h-[13px] w-[13px] -translate-x-1/2 -translate-y-1/2 rounded-full shadow-[0_0_0_3px_var(--bg)]"
            style={{ top: top + TRACK / 2, left: r.last, background: "var(--spot)" }}
          />
          {/* Held inside the line's ends, so a price at an edge keeps its whole figure. */}
          <span
            className="absolute -translate-x-1/2 text-[12px] leading-[1.2] whitespace-nowrap text-ink"
            style={{ top: 2, left: Math.max(34, Math.min(width - 34, r.last)) }}
          >
            <span className="font-semibold">{g.name}</span> <span className="fig">{P(g.last)}</span>
          </span>
        </>
      )}
    </div>
  );
}
