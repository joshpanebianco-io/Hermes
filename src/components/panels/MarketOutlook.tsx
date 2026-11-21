"use client";

import { useLayoutEffect, useRef, useState } from "react";
import type { MarketOutlook, OutlookRow } from "@/types/outlook";
import type { Quote } from "@/types/terminal";
import { AssetIcon } from "@/components/ui/AssetIcon";
import { Sparkline } from "@/components/ui/Sparkline";
import { cn } from "@/lib/cn";
import { dir, pct } from "@/lib/format";

/**
 * The Market Pulse: stocks, bonds, the dollar, gold, silver, oil and bitcoin read against
 * each other (server outlook.py).
 *
 * WHY (owner, 2026-11-21: "should we add a Market Outlook card that compares Stocks/the
 * major indices, gold, silv, bitcoin, us bonds, oil, USD since theyre represent different
 * aspects ... if all drop at the same time, that is indicitive of something?"; of the mock
 * on that Friday's close: "go ahead as mocked"). The pattern the markets make together,
 * then a row a market: its move, its arrows and how big that move is in its own usual
 * day, so silver's 7% and the note's 0.7% are read on one scale.
 *
 * NAMED MARKET PULSE, AND DRAWN TO BE LOOKED AT (the same day, of the card's first build:
 * "do you think we should add a spark like we have in scanner? and also can we add the
 * appropriate icon for each item, i think icons and visuals make it appear more
 * professional and appealling and also i want to add a visual indicator ... like if it
 * shows risk on, or risk off or extreme greed or extreme fear", then "can we use the
 * appropiritate colors for the numbers and arrows depending if its down or up"; of the
 * full-size picture of all four with the new name: "i like it"). So: a fear-to-greed scale
 * across the top, and on every row the market's mark, the session's line, and its move in
 * green or pink. It was "Market Outlook" for its first hours: an outlook is a forecast,
 * and this reads what the markets are doing now. The files and keys keep the old word.
 *
 * ONE BODY, TWO PLACES (the owner: "a toggle option on the MAcro Board in MAcro", and on
 * the Dashboard "the Market Outlook card in its plac[e]", where Stock news was). The same
 * job is drawn the same way wherever it is, so both draw this; `dense` is Macro's pane.
 *
 * THE COLOUR IS EACH MARKET'S OWN WAY, AND NOTHING MORE. On the Macro board a yield and
 * the dollar are printed in ink, because there a rise in either reads as a call on the
 * book (owner, 2026-11-12: "positive doesnt mean bullish and vice versa"). Here every row
 * is one market against the others and the owner asked for up and down in colour: green
 * says that market rose, bonds and the dollar included, and what that means for stocks is
 * the pattern's line to say, not the colour's.
 */

/** The most a row of the Dashboard's card grows to, in px (the class on the row says the same). */
const ROW_MAX = 40;
/** From this much height the card has room for the scale's own line of words under it. */
const ROOMY_PX = 360;

function arrowText(n: number): string {
  return n === 0 ? "·" : (n > 0 ? "▲" : "▼").repeat(Math.min(3, Math.abs(n)));
}

/** A move that prints "+0.0%" is flat: no colour, as it has no arrow. */
const way = (r: OutlookRow): number => (Math.abs(r.pct) < 0.05 ? 0 : r.pct);

function rowTitle(r: OutlookRow): string {
  const size = `${Math.abs(r.mult).toFixed(1)} times its usual day${r.sized ? "" : " (a stated usual day: too little history to measure one)"}`;
  return [`${r.name || r.group} ${pct(r.pct, 2)}, ${size}`, r.note].filter(Boolean).join(" · ");
}

/**
 * THE SCALE: extreme fear at the left end, extreme greed at the right, neutral in the
 * middle, the bias cards' own drawing (ui/BiasScale) a size up: a bar from the middle to a
 * mark at the score, in pink toward fear and green toward greed. The four short ticks are
 * where the words change, at 20 and 60 either side.
 */
export const SENTIMENT_WORDS = ["Extreme fear", "Fear", "Neutral", "Greed", "Extreme greed"] as const;
const WORDS = SENTIMENT_WORDS;
const LEG_WORD: Record<string, string> = { stocks: "stocks", vix: "the VIX", credit: "high-yield credit", bitcoin: "bitcoin" };

/** Which end of the scale a score is at: the words change at 20 either side of the middle. */
export function sentimentSide(score: number): "fear" | "greed" | "none" {
  return score <= -20 ? "fear" : score >= 20 ? "greed" : "none";
}

/**
 * The scale's bar alone, for wherever the reading is drawn: this card, and the Market
 * Report's Market Context (panels/BriefContext), which prints the same reading and so
 * draws the same bar.
 */
export function SentimentBar({ score, roomy }: { score: number; roomy: boolean }) {
  const pos = 50 + Math.max(-100, Math.min(100, score)) / 2;
  const side = sentimentSide(score);
  const fill = side === "fear" ? "bg-put-fig" : side === "greed" ? "bg-call-fig" : "bg-ink-3";
  return (
    <span className={cn("relative block min-w-[60px] flex-1", roomy ? "h-[16px]" : "h-[13px]")}>
      <span className={cn("absolute inset-x-0 top-1/2 -translate-y-1/2 rounded-[3px] bg-[color-mix(in_oklab,var(--ink-3)_34%,transparent)]", roomy ? "h-[7px]" : "h-[5px]")} />
      {pos !== 50 && (
        <span
          className={cn("absolute top-1/2 -translate-y-1/2 rounded-[3px] opacity-90", fill, roomy ? "h-[7px]" : "h-[5px]")}
          style={{ left: `${Math.min(50, pos)}%`, width: `${Math.abs(pos - 50)}%` }}
        />
      )}
      {[20, 40, 60, 80].map((at) => (
        <span key={at} className={cn("absolute top-1/2 w-px -translate-x-1/2 -translate-y-1/2 bg-ink-3", roomy ? "h-[11px]" : "h-[9px]")} style={{ left: `${at}%` }} />
      ))}
      <span className={cn("absolute top-1/2 left-1/2 w-[2px] -translate-x-1/2 -translate-y-1/2 rounded-[1px] bg-ink-2", roomy ? "h-[16px]" : "h-[13px]")} />
      <span
        className={cn("absolute top-1/2 -translate-x-1/2 -translate-y-1/2 rounded-full shadow-[0_0_0_2px_var(--bg)]", fill, roomy ? "h-[14px] w-[14px]" : "h-[11px] w-[11px]")}
        // Held inside the track: at an extreme the mark sits on the end, not past it.
        style={{ left: `clamp(7px, ${pos}%, calc(100% - 7px))` }}
      />
    </span>
  );
}

function Sentiment({ s, roomy, dense }: { s: NonNullable<MarketOutlook["sentiment"]>; roomy: boolean; dense: boolean }) {
  const side = sentimentSide(s.score);
  const ink = side === "fear" ? "text-put-fig" : side === "greed" ? "text-call-fig" : "text-ink-2";
  const legs = s.legs.map((l) => `${LEG_WORD[l.key] ?? l.key} ${l.mult > 0 ? "+" : ""}${l.mult.toFixed(1)}× (${l.weight}%)`).join(", ");
  const title = `Risk appetite today, −100 to +100: ${legs}. Each is its move in its own usual day, the VIX turned over (a rising VIX is fear), capped at three. Gold, bonds and the dollar are not in it: they are the pattern's.`;
  const bar = <SentimentBar score={s.score} roomy={roomy} />;
  const score = `${s.score > 0 ? "+" : ""}${s.score}`;
  if (!roomy) {
    // One line: the word, the figure, and the scale between its two ends.
    return (
      <div className="flex shrink-0 items-center gap-2.5" role="img" aria-label={`${s.label}, ${score} on the fear to greed scale`} title={title}>
        <span className={cn("shrink-0 font-semibold whitespace-nowrap", ink, dense ? "text-[13px]" : "text-[14.5px]")}>{s.label}</span>
        <span className={cn("fig shrink-0 text-ink", dense ? "text-[12px]" : "text-[13px]")}>{score}</span>
        <span className="qt-cap shrink-0 text-[8.5px] leading-none text-ink-3">Fear</span>
        {bar}
        <span className="qt-cap shrink-0 text-[8.5px] leading-none text-ink-3">Greed</span>
      </div>
    );
  }
  return (
    <div className="shrink-0" role="img" aria-label={`${s.label}, ${score} on the fear to greed scale`} title={title}>
      <p className="flex items-baseline gap-2.5">
        <span className={cn("text-[20px] leading-none font-semibold tracking-[-0.01em]", ink)}>{s.label}</span>
        <span className="fig text-[16px] leading-none text-ink">{score}</span>
        <span className="truncate text-[11.5px] text-ink-3">risk appetite today, from stocks, the VIX, credit and bitcoin</span>
      </p>
      <span className="mt-[9px] flex">{bar}</span>
      <p className="qt-cap mt-[5px] grid grid-cols-5 text-[9px] leading-none text-ink-3">
        {WORDS.map((w, i) => (
          <span key={w} className={cn(i === 0 ? "text-left" : i === 4 ? "text-right" : "text-center", w === s.label && "text-ink")}>
            {w}
          </span>
        ))}
      </p>
    </div>
  );
}

export function OutlookBody({
  d,
  quotes,
  dense = false,
}: {
  d: MarketOutlook | null | undefined;
  /** The board's quotes, for each row's line: the same session path the Macro board draws. */
  quotes?: Quote[];
  dense?: boolean;
}) {
  // HOW MUCH ROOM THE CARD HAS, MEASURED (2026-11-21). The Dashboard's second row is 320px
  // on a 1920 screen and 614px on the owner's 2560. With room, the scale has its line of
  // five words and the rows grow; without, it is one line and the rows are 21px, at which
  // the scale, the pattern, all eight rows and the sentence fit the small card. Read before
  // the first paint, so the card never draws one form and then the other.
  const box = useRef<HTMLDivElement>(null);
  const [height, setHeight] = useState(0);
  useLayoutEffect(() => {
    const el = box.current;
    if (!el || dense) return;
    setHeight(el.clientHeight);
    if (typeof ResizeObserver === "undefined") return;
    const ro = new ResizeObserver(([e]) => setHeight(Math.round(e.contentRect.height)));
    ro.observe(el);
    return () => ro.disconnect();
  }, [dense]);

  if (!d || !d.ok) {
    return (
      <div ref={box} className={cn(!dense && "h-full")}>
        <p className={cn("text-center text-ink-3", dense ? "px-3 py-5 text-[11px]" : "py-8 text-[12px]")}>{d?.why ?? "Reading the markets…"}</p>
      </div>
    );
  }
  const rows = d.rows ?? [];
  const roomy = !dense && height >= ROOMY_PX;
  const seen = d.seen && d.seen.of > 0 ? `${d.seen.n} of the last ${d.seen.of} sessions.` : "";
  const byKey = new Map((quotes ?? []).map((q) => [q.key, q]));
  // A row's line is its quote's session path, which is the row's own figure only while the
  // card is read off the live quotes: not under a close kept from the record, and never
  // bitcoin's on a shut market, whose line by then is another day's.
  const lineOf = (r: OutlookRow): Quote | null => {
    if (d.from !== "live" || (r.key === "BTC" && d.state === "close")) return null;
    const q = byKey.get(r.key);
    return q && q.spark?.length > 1 ? q : null;
  };
  return (
    <div ref={box} className={cn(dense ? "px-3 py-2" : "flex h-full min-h-0 flex-col")}>
      {d.sentiment && <Sentiment s={d.sentiment} roomy={roomy} dense={dense} />}
      <p className={cn("leading-[1.35] text-ink", dense ? "mt-1.5 text-[12px]" : "shrink-0 text-[13px]", !dense && (roomy ? "mt-3" : "mt-1.5"), !d.sentiment && "mt-0")}>
        <span className="font-semibold">{d.name}</span>
        {d.what && <span className="text-ink-2">: {d.what}</span>}
      </p>
      {/* The rows share the card's height, each between 21px and ROW_MAX; the list stops at
          its rows' most, so the sentence sits under the last row and not at the card's foot. */}
      <ul className={dense ? "mt-1" : cn("flex min-h-0 flex-1 flex-col", roomy ? "mt-1.5" : "mt-1")} style={dense ? undefined : { maxHeight: rows.length * ROW_MAX }}>
        {rows.map((r, i) => {
          const q = lineOf(r);
          const v = way(r);
          // Stocks' two rows are named for their index; the rest for the market, then the instrument.
          const lead = r.group === "Stocks" ? r.name : r.group;
          const rest = r.group === "Stocks" ? "" : r.name;
          return (
            <li
              key={r.key}
              title={rowTitle(r)}
              className={cn(
                "grid items-center gap-x-2",
                // Macro's rows are 19px: at 24 the card ran 20px past the foot of its column
                // on a 1920 screen, where Earnings above it is already at its least.
                dense
                  ? "grid-cols-[18px_minmax(0,1fr)_60px_52px_50px_70px] py-[1.5px] leading-[16px]"
                  : "max-h-[40px] min-h-[21px] flex-1 basis-0 grid-cols-[22px_minmax(0,1fr)_100px_58px_50px_76px] border-b border-ring/60 leading-[17px] last:border-b-0",
              )}
            >
              <AssetIcon id={r.key} size={dense ? 15 : roomy ? 20 : 17} className="block shrink-0 text-ink-2" />
              <span className={cn("truncate text-ink", dense ? "text-[11.5px]" : "text-[12.5px]")}>
                <span className="font-semibold">{lead}</span>
                {rest && <span className="text-ink-3"> · {rest}</span>}
                {/* The bond row's move is the note's price, so that green is bonds bought;
                    the yield is the figure a desk quotes, so it rides beside the name
                    (owner, 2026-11-21: "as accurate and relevant as possible"). */}
                {r.yield_bp != null && (
                  <span className="text-ink-3">
                    {" · yield "}
                    <span className="fig">
                      {r.yield_bp > 0 ? "+" : ""}
                      {r.yield_bp.toFixed(0)}bp
                    </span>
                  </span>
                )}
              </span>
              {q ? (
                <Sparkline data={q.spark} prev={q.prev} width={dense ? 60 : 100} height={dense ? 13 : roomy ? 24 : 16} tone={v === 0 ? "ink" : "side"} />
              ) : (
                <span aria-hidden />
              )}
              <span className={cn("fig text-right", dir(v), dense ? "text-[11.5px]" : "text-[12.5px]")}>{pct(r.pct, 1)}</span>
              <span aria-hidden className={cn("fig text-[9.5px] tracking-[0.02em]", r.arrows === 0 ? "text-ink-4" : dir(r.arrows))}>
                {arrowText(r.arrows)}
              </span>
              <span className={cn("fig whitespace-nowrap text-ink-3", dense ? "text-[11px]" : "text-[11.5px]")}>
                {r.sized ? "" : "~"}
                {Math.abs(r.mult).toFixed(1)}×{i === 0 && <span className="text-ink-4"> usual</span>}
              </span>
            </li>
          );
        })}
      </ul>
      <p className={cn("leading-[1.4] text-ink-3", dense ? "mt-1.5 text-[11px]" : cn("shrink-0 text-[11.5px]", roomy ? "mt-2" : "mt-1.5"))}>
        {d.tell} {seen}
      </p>
      {d.overnight && (
        <p className={cn("leading-[1.4] text-ink-3", dense ? "mt-0.5 text-[11px]" : "mt-1 shrink-0 text-[11.5px]")}>
          Overnight so far: <span className="text-ink-2">{d.overnight.name}</span>
          {d.overnight.what && `: ${d.overnight.what}`}
        </p>
      )}
    </div>
  );
}
