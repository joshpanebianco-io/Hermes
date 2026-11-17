"use client";

import type { Quote } from "@/types/terminal";
import { Module } from "@/components/ui/Module";
import { Skeleton } from "@/components/ui/Skeleton";
import { Tick } from "@/components/ui/Tick";
import { Sparkline } from "@/components/ui/Sparkline";
import { AssetIcon, hasAssetIcon } from "@/components/ui/AssetIcon";
import { TickerLogo } from "@/components/ui/TickerLogo";
import { autoDp, dir, feedNote, num, quoteChg } from "@/lib/format";
import { shownQuote } from "@/lib/quoteExt";
import { cn } from "@/lib/cn";

/**
 * The board — one row per instrument.
 *
 * GROUPED, NOT SORTED BY MOVE. A board that reorders itself by the day's
 * biggest mover is unreadable: the row you are looking for is somewhere new
 * every twenty seconds, and muscle memory — which is most of what makes a
 * board fast — never forms. Fixed groups, fixed order inside them.
 *
 * THE RANGE BAR IS THE THIRD COLUMN WORTH HAVING. Last and change are the
 * obvious two; where the last print sits inside the day's range is the one
 * that says whether a +0.4% is holding its highs or has already given half of
 * it back, and it cannot be inferred from the other two.
 *
 * THE MACRO BOARD DRAWS TWO UP (owner, 2026-11-14, of an audit of the Macro cards:
 * "do what you recommend"). One column of forty-three rows was 1,567px, a screen and
 * a half, and half of every row was an empty track. On a card wide enough the groups
 * flow into two columns in the order asked for, which halves it. A row that narrow
 * has no room for the range bar, so it goes there and the sparkline, whose last dot
 * sits where the print is in the day's range, carries that reading.
 *
 * A NAME WHERE THE CODE IS NOT ONE (same day). "N225", "SX5E", "HEATO…" (cut off at
 * the column) and "ZB" are a feed's codes. Those rows are named for what they are;
 * a code a desk says aloud (VIX, DXY, WTI, BTC, US10Y) stays as it is. The code is
 * on the hover either way.
 *
 * A RISE IN THE VIX, A YIELD OR THE DOLLAR IS NOT A SIDE (owner, 2026-11-12:
 * "positive doesnt mean bullish and vice versa"). Those three groups print their
 * change in ink with an arrow and draw their line in grey. An index, a commodity and
 * a coin are their own price, so they keep green and pink.
 */

const GROUPS: { key: Quote["group"]; label: string }[] = [
  { key: "core", label: "The book" },
  { key: "global", label: "Global indices" },
  { key: "rates", label: "Rates" },
  { key: "vol", label: "Volatility" },
  { key: "fx", label: "FX" },
  { key: "energy", label: "Energy" },
  { key: "metals", label: "Metals & ags" },
  { key: "crypto", label: "Risk appetite" },
];

/** Groups whose change is a move, never a side: ink and an arrow. */
const MOVES: ReadonlySet<Quote["group"]> = new Set(["vol", "rates", "fx"]);

/** The rows whose key is a feed's code, as what they are. Nine characters at most: the column's width ("Long bonds" was cut to "Long bon…"). */
const NAMES: Record<string, string> = {
  N225: "Nikkei",
  HSI: "Hang Seng",
  SHCOMP: "Shanghai",
  SX5E: "Stoxx 50",
  ZN: "10Y fut",
  ZB: "Bond fut",
  BRENT: "Brent",
  NATGAS: "Nat gas",
  RBOB: "Gasoline",
  HEATOIL: "Heat oil",
  // The gold future, which the Macro board draws at the head of the metals (MacroBoard).
  GC: "Gold",
  SILVER: "Silver",
  COPPER: "Copper",
  PLAT: "Platinum",
  WHEAT: "Wheat",
  CORN: "Corn",
  HYG: "HY credit",
  TLT: "TLT bonds",
};

export function Board({
  quotes,
  ageMin,
  error,
  groups,
  title = "Board",
  twoUp = false,
}: {
  quotes: Quote[];
  ageMin?: number | null;
  error?: string | null;
  /** Which groups this instance renders — the board is split across columns. */
  groups?: Quote["group"][];
  title?: string;
  /** The Macro board: two columns on a wide card, and plain names for coded rows. */
  twoUp?: boolean;
}) {
  // In the order asked for: the Macro page puts volatility and rates first (owner,
  // 2026-11-14: "yes put vix and rates first"). With none asked, GROUPS' own order.
  const wanted = groups ?? GROUPS.map((g) => g.key);
  const shown = wanted.flatMap((k) => GROUPS.filter((g) => g.key === k));

  return (
    <Module title={title} ageMin={ageMin} error={error} bodyClassName="px-0 py-0">
      {quotes.length === 0 ? (
        ageMin == null && !error ? (
          <Skeleton rows={6} label={`Loading ${title.toLowerCase()}`} />
        ) : (
          <p className="px-3 py-6 text-center text-[11px] text-ink-3">The quote feed returned nothing for these instruments.</p>
        )
      ) : (
        // The columns balance themselves and a group never splits across them, so with
        // seven groups the first three (volatility, rates, global indices) are the left.
        <div className="@container">
          {/* Two columns from 32rem of card (`@lg`; it was `@xl`, 36rem): the board sits in
              Macro's left column since 2026-11-15, which on the Sidebar interface is 597px
              of card, and under the old mark it fell to one column 1,160px tall. */}
          <div className={cn(twoUp && "@lg:columns-2 @lg:gap-0 @lg:[column-rule:1px_solid_color-mix(in_oklab,var(--ring)_45%,transparent)]")}>
            {shown.map((g) => {
              const rows = quotes.filter((q) => q.group === g.key);
              if (!rows.length) return null;
              return (
                <div key={g.key} className="break-inside-avoid">
                  <div className={cn("qt-band border-y border-ring/40 bg-surface-2/50 px-3 py-1 first:border-t-0", twoUp && "qt-band-tight")}>
                    <span className="eyebrow text-[9px]">{g.label}</span>
                  </div>
                  <ul>
                    {rows.map((q) => (
                      <Row key={q.key} q={q} mark={g.key === "core"} move={MOVES.has(g.key)} named={twoUp} />
                    ))}
                  </ul>
                </div>
              );
            })}
          </div>
        </div>
      )}
    </Module>
  );
}

/** A move's change as the row prints it: "↑ 3.21%", "↓ 0.6bp", and a flat one with no arrow. */
function moveText(text: string, v: number | null): string {
  if (v === null || !Number.isFinite(v)) return text;
  const bare = text.replace(/^[+\-−]/, "");
  return v === 0 ? bare : `${v > 0 ? "↑" : "↓"} ${bare}`;
}

/**
 * WHAT THE PRICE IS, ON THE ROW (audit, 2026-10-14). A delayed print carries a
 * small D, the convention on every retail screen; a closed market's last price
 * is dimmed, because it is not moving and must not read as if it were — and so
 * is one with no print for half an hour inside its hours (a lunch break, a
 * grain contract between sessions). The tooltip says which, how late and as
 * of when. A live row looks exactly as it always did.
 */
function Row({ q: raw, mark, move, named }: { q: Quote; mark?: boolean; move?: boolean; named?: boolean }) {
  // Outside the session a US-listed fund shows its pre-market or after-hours trade, tagged
  // beside its name (lib/quoteExt, the audit of 2026-11-16).
  const { q, tag, note: extNote } = shownQuote(raw);
  const chg = quoteChg(q);
  const note = extNote ?? feedNote(q);
  const ink = q.feed === "closed" || q.feed === "stale" ? "text-ink-3" : "text-ink";
  const name = named ? (NAMES[q.key] ?? q.key) : q.key;
  const what = name === q.key ? q.name : `${q.key} · ${q.name}`;
  return (
    // A container, so the range bar answers to the ROW's width: in two columns a row
    // is half the card and the bar is what gives way.
    // TIGHTER ON THE MACRO BOARD (owner, 2026-11-14: "can we reduce the size of the macro
    // board a bit and increase the calender"). The calendar above takes whatever this
    // card leaves, so every pixel off a row here is a pixel of schedule: the line is
    // 17px, not the page's 20, and the row is 21px on screen where it was 27 (23 at
    // first; then "a want a bit more room for the calendar", and the padding went to 1px).
    // TIGHTER AGAIN, FOR THE EARNINGS CARD (owner, 2026-11-15: "lets decrease the macro
    // board a bit and increase the earnings card"). The board sits under Earnings now and
    // Earnings takes what it leaves: the line is 14px and the sparkline 13 (it was 16 and
    // set the row's height), so a row is 17.6px on the owner's screen where it was 20.9.
    // And once more the same day ("can we reduce the macro board and increase the earnings
    // card slightly again"): a 13px line and a 12px sparkline, 16.5px on screen.
    <li className={cn("hit @container flex items-center gap-2 px-3", named ? "py-[1px] leading-[13px]" : "py-[3px]")} title={note ? `${what} — ${note}` : what}>
      {/* The book's own rows wear their marks: a future its badge or ingot, a fund its logo. */}
      {mark && (hasAssetIcon(q.key) ? <AssetIcon id={q.key} size={16} className="block shrink-0 text-ink-2" /> : <TickerLogo sym={q.key} size={16} />)}
      <span className={cn("fig shrink-0 truncate text-[11px] text-ink-2", named ? "w-[76px]" : "w-[52px]")}>
        {name}
        {tag && <span className="ml-1 text-[8.5px] text-ink-3">{tag}</span>}
      </span>
      <Tick
        value={num(q.last, q.last >= 1000 ? autoDp(q.last) : undefined)}
        className={cn("fig shrink-0 truncate text-right text-[11.5px]", named ? "w-[62px]" : "w-[74px]", ink)}
      />
      <span className="fig -ml-1 w-[7px] shrink-0 text-[8.5px] leading-none text-ink-4" aria-label={note ?? undefined}>
        {q.feed === "delayed" ? "D" : ""}
      </span>
      {move ? (
        <Tick
          value={moveText(chg.text, chg.v)}
          className={cn("fig -ml-1 shrink-0 text-right text-[11px] whitespace-nowrap", named ? "w-[60px]" : "w-[62px]", chg.v ? "text-ink-2" : "text-ink-3")}
        />
      ) : (
        <Tick value={chg.text} className={cn("fig -ml-1 shrink-0 text-right text-[11px]", named ? "w-[60px]" : "w-[62px]", dir(chg.v))} />
      )}
      <RangeBar pos={q.range_pos} plain={move} className={cn(named && "@max-[330px]:hidden")} />
      {/* Right-aligned, with the range bar taking up the slack: the rows stopped
          two-thirds of the way across a wide pane and left the rest blank. */}
      {/* IN TWO COLUMNS THE LINE GIVES WAY (2026-11-15). The name, the price and the change
          take 229px of a row and cannot be cut; the line is 52px where there is room for
          it, narrower where there is less, and is not drawn in a row with under 24px to
          give it (a 1920 screen), where it used to run into the next column. */}
      <Sparkline className={cn("ml-auto", named ? "@max-[252px]:hidden" : "shrink-0")} fluid={named} data={q.spark} prev={q.prev} width={named ? 52 : 72} height={named ? 12 : 16} tone={move ? "ink" : "side"} />
    </li>
  );
}

/**
 * Where the last print sits between the session's low and high.
 *
 * A MARK ON A TRACK, NOT A FILLED BAR. A fill reads as a quantity ("70% of
 * something"); this is a position, and the distinction matters because the
 * interesting states are the two ends. The track is drawn in the neutral
 * chrome hue and only the mark takes the direction colour, so a row that is
 * down but pinned at its highs still reads correctly. `plain` keeps the mark
 * grey too: at the top of its range is not a side for the VIX or a yield.
 */
function RangeBar({ pos, plain, className }: { pos: number | null; plain?: boolean; className?: string }) {
  if (pos === null || !Number.isFinite(pos)) {
    return <span className={cn("h-[3px] max-w-[220px] min-w-[44px] flex-1", className)} aria-hidden />;
  }
  const p = Math.max(0, Math.min(1, pos));
  const tone = plain ? "var(--ink-2)" : p >= 0.75 ? "var(--call)" : p <= 0.25 ? "var(--put)" : "var(--ink-3)";
  return (
    <span
      className={cn("relative h-[3px] max-w-[220px] min-w-[44px] flex-1 rounded-full bg-ring", className)}
      title={`${(p * 100).toFixed(0)}% of the day's range`}
    >
      <span
        className="absolute top-1/2 h-[7px] w-[2px] -translate-y-1/2 rounded-full"
        style={{ left: `calc(${p * 100}% - 1px)`, background: tone }}
      />
    </span>
  );
}
