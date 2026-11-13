"use client";

import { useEffect, useRef, useState } from "react";
import type { Catalyst, RangeState, ScanRow, Verdict } from "@/types/scanner";
import { TickerLogo } from "@/components/ui/TickerLogo";
import { compact, num } from "@/lib/format";
import { cn } from "@/lib/cn";
import { segItem } from "@/lib/seg";
import { closeTicker, openTicker, togglePin, trackName } from "@/lib/ticker";

/**
 * What the wide tables share: Breakouts, Extended hours and Day 2/3 read the same
 * screener and draw the same cells, so a catalyst, a sparkline and a filter look
 * and behave one way on all three.
 *
 * THE GROUP RULES CARRY THE ONLY NEW COLOUR (owner, 2026-11-10: "follow the
 * screenshots closely"), and it is the desks' own muted set, one hue a group: news
 * blue, the move amber, the levels red, the setup violet. Green and pink still mean a
 * side and nothing else, except the score's three tiers.
 */

/**
 * The gap: the open against the previous close. Before the open, and overnight,
 * there is no open yet, so it is where the extended session stands against that
 * close: the gap as it would be if the bell rang now.
 */
export function gapOf(r: ScanRow): number | null {
  const { open, pdc } = r.levels;
  if (open != null && pdc) return (open / pdc - 1) * 100;
  return r.ext_pct;
}

export const isNum = (v: unknown): v is number => typeof v === "number" && Number.isFinite(v);
export const isStr = (v: unknown): v is string => typeof v === "string";

/** "$2bn+", "$300m+", "Any". */
export function capWord(v: number): string {
  if (!v) return "Any";
  return v >= 1e9 ? `$${v / 1e9}bn+` : `$${v / 1e6}m+`;
}

export function volWord(v: number): string {
  if (!v) return "Any";
  return v >= 1e6 ? `${v / 1e6}M+` : `${v / 1e3}K+`;
}

export function capShort(v: number | null | undefined): string {
  if (v == null) return "—";
  return v >= 1e12 ? `$${(v / 1e12).toFixed(1)}T` : v >= 1e9 ? `$${Math.round(v / 1e8) / 10}B` : `$${Math.round(v / 1e6)}M`;
}

export function pctText(v: number | null | undefined, digits = 2): string {
  if (v == null) return "—";
  return `${v >= 0 ? "+" : ""}${v.toFixed(digits)}%`;
}

/** "2026-11-06" → "Nov 6". */
export function dayShort(iso: string): string {
  const d = new Date(`${iso}T12:00:00Z`);
  return Number.isNaN(d.getTime()) ? iso : d.toLocaleDateString("en-US", { month: "short", day: "numeric", timeZone: "UTC" });
}

/** "2026-11-06" → "Fri Nov 6". */
export function dayName(iso: string): string {
  const d = new Date(`${iso}T12:00:00Z`);
  return Number.isNaN(d.getTime())
    ? iso
    : d.toLocaleDateString("en-US", { weekday: "short", month: "short", day: "numeric", timeZone: "UTC" });
}

/** The day's closes as a line: hue by which way it ended, a flat rule while there are none. */
export function Spark({ pts, w = 84, h = 26 }: { pts: number[] | null | undefined; w?: number; h?: number }) {
  if (!pts || pts.length < 2) return <span className="inline-block" style={{ width: w, height: h }} aria-hidden />;
  const lo = Math.min(...pts);
  const hi = Math.max(...pts);
  const span = hi - lo || 1;
  const d = pts
    .map((v, i) => `${i ? "L" : "M"}${((i / (pts.length - 1)) * (w - 2) + 1).toFixed(1)},${(h - 2 - ((v - lo) / span) * (h - 4)).toFixed(1)}`)
    .join("");
  const up = pts[pts.length - 1] >= pts[0];
  return (
    <svg width={w} height={h} className="block" aria-hidden>
      <path d={d} fill="none" stroke={up ? "var(--call-fig)" : "var(--put-fig)"} strokeWidth={1} opacity={0.85} />
    </svg>
  );
}

function tagHue(c: Catalyst): string {
  return c.tier === 1 ? "border-ring-2 text-ink" : c.tier === 2 ? "border-ring text-ink-2" : "border-ring text-ink-3";
}

export function ageWord(min: number): string {
  if (min < 60) return `${Math.max(1, Math.round(min))}m`;
  if (min < 48 * 60) return `${Math.round(min / 60)}h`;
  return `${Math.round(min / 1440)}d`;
}

/** The name's most important story: its kind, the headline, how old. Two lines at most. */
export function CatalystCell({ c, width = 380 }: { c: Catalyst | null | undefined; width?: number }) {
  if (!c) return <span className="text-[12px] text-ink-3">—</span>;
  return (
    <a
      href={c.url}
      target="_blank"
      rel="noreferrer noopener"
      onClick={(e) => e.stopPropagation()}
      className="hit block"
      style={{ maxWidth: width }}
      title={`${c.title}\n${c.provider} · ${ageWord(c.age_min)} ago`}
    >
      <span className={cn("line-clamp-2 text-[12px] leading-[1.35]", c.tier === 1 ? "text-ink" : "text-ink-2")}>
        <span className={cn("qt-cap mr-1.5 inline-block rounded-[2px] border px-1 align-[1px] text-[9.5px] leading-[14px]", tagHue(c))}>{c.tag}</span>
        {c.title}
      </span>
    </a>
  );
}

/** The chips over a table: one choice, each with how many it would show. */
export function Chips<T extends string>({
  items,
  on,
  set,
  counts,
}: {
  items: ReadonlyArray<{ key: T; label: string; title?: string }>;
  /** The chip that is lit. */
  on: T;
  set: (k: T) => void;
  counts?: Partial<Record<T, number>> | null;
}) {
  return (
    <span className="seg flex-wrap">
      {items.map((x) => (
        <button key={x.key} type="button" title={x.title} onClick={() => set(x.key)} {...segItem(on === x.key)}>
          {x.label}
          {counts?.[x.key] != null && <span className="seg-n">{counts[x.key]}</span>}
        </button>
      ))}
    </span>
  );
}

/** One row of a filter menu. */
export function Choice<T extends string | number>({
  label,
  options,
  value,
  set,
}: {
  label: string;
  options: ReadonlyArray<{ value: T; label: string }>;
  value: T;
  set: (v: T) => void;
}) {
  return (
    <div>
      <p className="qt-cap mb-1 text-[10px] text-ink-3">{label}</p>
      <span className="seg flex-wrap">
        {options.map((o) => (
          <button key={String(o.value)} type="button" onClick={() => set(o.value)} {...segItem(value === o.value)}>
            {o.label}
          </button>
        ))}
      </span>
    </div>
  );
}

/**
 * A button that names what it holds and opens a panel under itself. The panel hangs
 * from the button's right edge, where the bars keep their menus; `left` hangs it from
 * the left edge, for a menu at the start of a row (the chart's).
 *
 * A menu of settings stays open while they are flipped. One that is a single pick (which
 * name a chart shows) takes its children as a function and is handed `close` to call.
 */
export function Menu({
  label,
  children,
  width = 340,
  left = false,
  title,
}: {
  label: React.ReactNode;
  children: React.ReactNode | ((close: () => void) => React.ReactNode);
  width?: number;
  left?: boolean;
  title?: string;
}) {
  const [open, setOpen] = useState(false);
  const box = useRef<HTMLSpanElement | null>(null);
  useEffect(() => {
    if (!open) return;
    const off = (e: MouseEvent) => {
      if (!box.current?.contains(e.target as Node)) setOpen(false);
    };
    window.addEventListener("mousedown", off);
    return () => window.removeEventListener("mousedown", off);
  }, [open]);
  return (
    <span ref={box} className="relative shrink-0">
      <button type="button" onClick={() => setOpen((v) => !v)} aria-expanded={open} title={title} {...segItem(open, { className: "border border-ring-2" })}>
        {label}
      </button>
      {open && (
        <div className={cn("absolute top-full z-40 mt-1 flex flex-col gap-3 rounded-[4px] border border-ring-2 bg-surface p-3 shadow-[0_12px_40px_rgba(0,0,0,.55)]", left ? "left-0" : "right-0")} style={{ width }}>
          {typeof children === "function" ? children(() => setOpen(false)) : children}
        </div>
      )}
    </span>
  );
}

/*
 * NO BAND OF GROUP NAMES OVER A TABLE'S HEADER (owner, 2026-11-11: "can we remove the
 * 'news move levels chart volume' bars that go around the colum filters"). GroupHead
 * drew one over Setups, Breakouts, Extended hours, Day 2/3 and the Sectors list: a
 * word over each run of columns with a coloured rule under it. Each column's own name
 * and the line under it say the same, so the header is one row.
 */

/** A column's name, and what it is measured against under it. */
export function Head({ label, hint, right }: { label: React.ReactNode; hint?: string; right?: boolean }) {
  return (
    <span className={cn("inline-flex flex-col gap-[3px] leading-none", right && "items-end")}>
      <span>{label}</span>
      {hint && <span className="text-[9.5px] font-normal tracking-normal text-ink-3 normal-case">{hint}</span>}
    </span>
  );
}

/* ---- the small marks ---------------------------------------------------- */

const GLYPHS: Record<string, React.ReactNode> = {
  up: <path d="M3 17l6-6 4 4 8-9M15 6h6v6" />,
  down: <path d="M3 7l6 6 4-4 8 9M15 18h6v-6" />,
  pulse: <path d="M2 12h5l3-8 4 16 3-8h5" />,
  star: <path d="M12 3.5l2.6 5.4 5.9.8-4.3 4.1 1 5.9-5.2-2.8-5.2 2.8 1-5.9-4.3-4.1 5.9-.8z" />,
  inside: <rect x="5" y="5" width="14" height="14" rx="2" />,
  bolt: <path d="M13 2L4 14h7l-1 8 9-12h-7z" />,
  clock: (
    <>
      <circle cx="12" cy="12" r="8.5" />
      <path d="M12 7v5l3.5 2" />
    </>
  ),
  check: <path d="M5 12.5l4.5 4.5L19 7" />,
  arrow: <path d="M7 17L17 7M9 7h8v8" />,
  search: (
    <>
      <circle cx="11" cy="11" r="7" />
      <path d="M20 20l-3.5-3.5" />
    </>
  ),
  tape: <path d="M3 12h18M3 6h18M3 18h12" />,
  // Several charts side by side.
  grid: (
    <>
      <rect x="3.5" y="3.5" width="7" height="7" rx="1.5" />
      <rect x="13.5" y="3.5" width="7" height="7" rx="1.5" />
      <rect x="3.5" y="13.5" width="7" height="7" rx="1.5" />
      <rect x="13.5" y="13.5" width="7" height="7" rx="1.5" />
    </>
  ),
};

export function Glyph({ name, size = 14, className }: { name: keyof typeof GLYPHS | string; size?: number; className?: string }) {
  return (
    <svg aria-hidden width={size} height={size} viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" className={cn("shrink-0", className)}>
      {GLYPHS[name]}
    </svg>
  );
}

export type TagTone = "up" | "down" | "news" | "flat" | "warn";

const TAG_TONE: Record<TagTone, string> = {
  up: "border-call-fig/35 bg-call-fig/10 text-call-fig",
  down: "border-put-fig/35 bg-put-fig/10 text-put-fig",
  news: "border-desk-markets/50 bg-desk-markets/10 text-desk-markets",
  flat: "border-ring-2 text-ink-3",
  warn: "border-flip-fig/35 bg-flip-fig/10 text-flip-fig",
};

/** One small word on a row: where it stands, that it has news, what day of a move. */
export function Tag({ tone, title, children }: { tone: TagTone; title?: string; children: React.ReactNode }) {
  return (
    <span title={title} className={cn("qt-cap inline-block rounded-[3px] border px-[5px] text-[9.5px] leading-[14px]", TAG_TONE[tone])}>
      {children}
    </span>
  );
}

/** The tags a row wears, in the same order on every table. */
export function rowTags(o: {
  pd?: RangeState | null;
  pm?: RangeState | "forming" | null;
  inside?: boolean;
  news?: boolean;
  stage?: number | null;
  /** The engine's verdict on the name today (the wide tables); pinned and tracked show their star and dot instead. */
  verdict?: Verdict | null;
  /** The month's newest insider trade worth a line (Form 4s), and how many there were. */
  insider?: { side: "buy" | "sell"; text: string; n: number } | null;
}): React.ReactNode[] {
  const out: React.ReactNode[] = [];
  if (o.pd === "above") out.push(<Tag key="pd" tone="up">Above PDH</Tag>);
  if (o.pd === "below") out.push(<Tag key="pd" tone="down">Below PDL</Tag>);
  if (o.pm === "above") out.push(<Tag key="pm" tone="up">Above PMH</Tag>);
  if (o.pm === "below") out.push(<Tag key="pm" tone="down">Below PML</Tag>);
  if (o.inside) out.push(<Tag key="in" tone="flat" title="The day's range sits inside the previous day's">Inside day</Tag>);
  if (o.news) out.push(<Tag key="news" tone="news">News</Tag>);
  if ((o.stage ?? 0) >= 2) out.push(<Tag key="day" tone="flat" title={`Day ${o.stage} of a multi-day move`}>Day {o.stage}</Tag>);
  if (o.insider) {
    out.push(
      <Tag
        key="insider"
        tone={o.insider.side === "buy" ? "up" : "down"}
        title={`${o.insider.text}${o.insider.n > 1 ? `\n+${o.insider.n - 1} more this month` : ""}\nFrom the SEC's Form 4s: open-market buys of $100k+, sales of $1M+ outside a 10b5-1 plan. Context, not part of the score.`}
      >
        {o.insider.side === "buy" ? "Insider buy" : "Insider sale"}
      </Tag>,
    );
  }
  // NO POOL TAG (owner, 2026-11-13: "what does the POOL tag even mean?" → removed). It
  // said the app had put the name on the list by itself at a mark; with the favourites
  // cleared that was nearly every row, so it told the reader nothing.
  const v = o.verdict;
  if (v?.state === "inplay") {
    out.push(
      <Tag key="verdict" tone="flat" title={`${v.reason ?? ""} — in play (${v.score}) but not on today's list: track it to have the engine score it at the open`}>
        In play {v.score != null ? Math.round(v.score) : ""}
      </Tag>,
    );
  }
  return out;
}

/** The row's star: on the pinned list for good. Lit at once, then the list catches up. */
export function Star({ sym, pinned, onDone }: { sym: string; pinned: boolean; onDone?: () => void }) {
  const [wish, setWish] = useState<boolean | null>(null);
  const [why, setWhy] = useState<string | null>(null);
  useEffect(() => setWish(null), [pinned]);
  const on = wish ?? pinned;
  return (
    <button
      type="button"
      aria-pressed={on}
      title={why ?? (on ? "A favourite. Click to take it off your favourites." : "Add to your favourites")}
      onClick={(e) => {
        e.stopPropagation();
        setWish(!on);
        void togglePin(sym).then((err) => {
          // Refused (the list is full, say): the star goes back and its hover says why.
          setWhy(err);
          if (err) setWish(null);
          onDone?.();
        });
      }}
      className={cn("text-[13px] leading-none", on ? "text-flip-fig" : "text-ink-4 hover:text-ink-2")}
    >
      {on ? "★" : "☆"}
    </button>
  );
}

/**
 * The name, as the screenshots set it: the symbol and price, the tags under them, the
 * star at the far end. `stack` puts the price on a line of its own for the tall rows
 * of Extended hours. Track, which most rows do not need, waits for the hover.
 */
export function TickerCell({
  sym,
  name,
  price,
  sub,
  badge,
  tags,
  pinned,
  onPinned,
  tracked,
  onTrack,
  stack,
}: {
  sym: string;
  name?: string | null;
  price?: string | null;
  sub?: React.ReactNode;
  badge?: React.ReactNode;
  tags?: React.ReactNode[];
  pinned: boolean;
  onPinned?: () => void;
  tracked?: boolean;
  onTrack?: () => void;
  stack?: boolean;
}) {
  return (
    <div className="flex items-center gap-2">
      <TickerLogo sym={sym} size={stack ? 22 : 20} />
      <div className="min-w-0 flex-1">
        <p className="flex items-baseline gap-1.5 leading-[1.25] whitespace-nowrap">
          <span className="text-[13px] font-semibold text-ink" title={name ?? undefined}>{sym}</span>
          {!stack && price && <span className="fig text-[12.5px] text-ink-2">{price}</span>}
          {sub && !stack && <span className="fig text-[11px] text-ink-3">{sub}</span>}
          {badge}
          {tracked && <span aria-hidden title="On the list: read live, with signals" className="h-[5px] w-[5px] self-center rounded-full bg-desk-markets" />}
        </p>
        {stack && price && <p className="fig text-[13px] leading-[1.35] text-ink-2">{price}</p>}
        {stack && sub && <p className="fig text-[11px] text-ink-3">{sub}</p>}
        {tags && tags.length > 0 && <p className="mt-1 flex gap-1 whitespace-nowrap">{tags}</p>}
      </div>
      <div className="flex shrink-0 flex-col items-end gap-1 self-start">
        <Star sym={sym} pinned={pinned} onDone={onPinned} />
        {onTrack && !tracked && (
          <span className="opacity-0 group-hover:opacity-100 focus-within:opacity-100">
            <TrackButton sym={sym} tracked={false} onDone={onTrack} />
          </span>
        )}
      </div>
    </div>
  );
}

/* ---- the figures --------------------------------------------------------- */

const rvolHue = (v: number) => (v >= 3 ? "call" : v >= 1.5 ? "flip" : "ink");
const FIG_INK = { call: "text-call-fig", flip: "text-flip-fig", ink: "text-ink-2" } as const;
const BAR_INK = { call: "bg-call-fig", flip: "bg-flip-fig", ink: "bg-ink-3" } as const;

/** Relative volume over a bar, full at 5×. */
export function RvolBar({ v }: { v: number | null | undefined }) {
  if (v == null) return <span className="text-[12px] text-ink-3">—</span>;
  const h = rvolHue(v);
  return (
    <div className="min-w-[84px]">
      <p className={cn("fig text-[12.5px] leading-none", FIG_INK[h])}>{v.toFixed(1)}×</p>
      <div className="relative mt-[6px] h-[3px] bg-[var(--qt-track,var(--ring))]">
        <span className={cn("absolute inset-y-0 left-0", BAR_INK[h])} style={{ width: `${Math.min(v / 5, 1) * 100}%` }} />
      </div>
    </div>
  );
}

/** Relative volume in a word. `~` while the figure is still an estimate. */
export function RvolWord({ v, est }: { v: number | null | undefined; est?: boolean }) {
  if (v == null) return <span className="text-[12px] text-ink-3">—</span>;
  const hot = v >= 3;
  return (
    <div className="leading-[1.3]" title={est ? "Estimated from the share of an average day, until five sessions of this session's volume are on file" : "Against this session's own average"}>
      <p className={cn("fig text-[13px]", hot ? "text-flip-fig" : "text-ink")}>
        {est ? "~" : ""}
        {v >= 100 ? v.toFixed(0) : v.toFixed(1)}×
      </p>
      <p className={cn("qt-cap text-[9px]", hot ? "text-flip-fig" : "text-ink-3")}>{hot ? "Hot" : v >= 1 ? "Active" : "Low"}</p>
    </div>
  );
}

/** A move and a bar for its size, full at 6%. */
export function MoveBar({ v }: { v: number }) {
  const up = v >= 0;
  return (
    <div className="flex items-center gap-2">
      <span className={cn("fig w-[72px] text-right text-[13px]", up ? "up" : "down")}>{pctText(v)}</span>
      <span className="relative h-[2px] w-[56px] bg-[var(--qt-track,var(--ring))]">
        <span className={cn("absolute inset-y-0 left-0", up ? "bg-call-fig" : "bg-put-fig")} style={{ width: `${Math.min(Math.abs(v) / 6, 1) * 100}%` }} />
      </span>
    </div>
  );
}

/** Extended-hours volume over its share of an average day. */
export function ExtVol({ vol, adv, tag, hot = 20 }: { vol: number | null; adv: number | null; tag: string; hot?: number }) {
  return (
    <div className="fig leading-[1.3]">
      <p className="text-[13px] text-ink">
        {vol != null ? compact(vol) : "—"} <span className="qt-cap text-[9px] text-ink-3">{tag}</span>
      </p>
      <p className={cn("text-[11.5px]", (adv ?? 0) >= hot ? "text-flip-fig" : "text-ink-3")}>{adv != null ? `${Math.round(adv)}% ADV` : ""}</p>
    </div>
  );
}

/** "2.9M · 31%": the day's volume and its share of an average day, on one line. */
export function VolPct({ vol, adv }: { vol: number | null; adv: number | null }) {
  if (vol == null) return <span className="text-[12px] text-ink-3">—</span>;
  return (
    <span className="fig text-[12.5px] whitespace-nowrap">
      <span className="text-ink">{compact(vol)}</span>
      {adv != null && <span className={(adv ?? 0) >= 100 ? "text-flip-fig" : "text-ink-3"}> · {Math.round(adv)}%</span>}
    </span>
  );
}

const money = (v: number) => `$${num(v)}`;

/** A range drawn: its low and high, where price is along it, and what that makes it. */
export function RangeBar({ lo, hi, last }: { lo: number | null | undefined; hi: number | null | undefined; last: number }) {
  if (lo == null || hi == null) return <span className="text-[12px] text-ink-3">—</span>;
  const span = hi - lo;
  const raw = span > 0 ? (last - lo) / span : 0.5;
  const pos = Math.max(0, Math.min(1, raw));
  const above = last > hi;
  const below = last < lo;
  const word = above || raw >= 0.66 ? "Bullish" : below || raw <= 0.33 ? "Bearish" : null;
  const fill = above ? "var(--call-fig)" : below ? "var(--put-fig)" : "linear-gradient(90deg, var(--put-fig), var(--call-fig))";
  const dot = above ? "var(--call-fig)" : below ? "var(--put-fig)" : "var(--flip-fig)";
  return (
    <div className="w-full max-w-[280px] min-w-[150px]">
      <div className="fig flex justify-between text-[12px] leading-none">
        <span className="text-put-fig">{money(lo)}</span>
        <span className="text-call-fig">{money(hi)}</span>
      </div>
      <div className="relative mt-[7px] h-[3px] rounded-full bg-[var(--qt-track,var(--ring))]">
        <span className="absolute inset-y-0 left-0 rounded-full opacity-85" style={{ width: `${(below ? 1 : pos) * 100}%`, background: fill }} />
        <span className="absolute top-1/2 h-[9px] w-[9px] -translate-x-1/2 -translate-y-1/2 rounded-full border-2 border-bg" style={{ left: `${pos * 100}%`, background: dot }} />
      </div>
      <p className={cn("qt-cap mt-[6px] h-[10px] text-[9px]", word === "Bullish" ? "text-call-fig" : "text-put-fig")}>
        {word}
        {above ? ` ↑ ${money(last)}` : below ? ` ↓ ${money(last)}` : ""}
      </p>
    </div>
  );
}

/** A score over a bar: green, amber or grey by tier. */
export function ScoreBar({ v, of, strong = 65, fair = 50, title }: { v: number; of?: boolean; strong?: number; fair?: number; title?: string }) {
  const h = v >= strong ? "call" : v >= fair ? "flip" : "ink";
  return (
    <div className="min-w-[86px]" title={title}>
      <p className={cn("fig text-[12.5px] leading-none", FIG_INK[h])}>
        {v}
        {of && <span className="text-[10.5px] text-ink-3"> /100</span>}
      </p>
      <div className="relative mt-[6px] h-[3px] bg-[var(--qt-track,var(--ring))]">
        <span className={cn("absolute inset-y-0 left-0", BAR_INK[h])} style={{ width: `${Math.max(0, Math.min(100, v))}%` }} />
      </div>
    </div>
  );
}

/* ---- the strip above a table --------------------------------------------- */

const CARD_TINT = { up: "text-call-fig", down: "text-put-fig", move: "text-desk-policy", news: "text-desk-markets", setup: "text-desk-macro", plain: "text-ink-3" } as const;

/** One figure at the head of a page: a mark, the figure, what it is, and whose. */
export function StatCard({
  glyph,
  tint = "plain",
  value,
  hue,
  label,
  sub,
  title,
}: {
  glyph: string;
  tint?: keyof typeof CARD_TINT;
  value: React.ReactNode;
  hue?: string;
  label: string;
  sub?: React.ReactNode;
  title?: string;
}) {
  return (
    <div className="qt-stat flex min-w-[170px] flex-1 items-center gap-3 border-r border-ring px-4 py-[7px] last:border-r-0" title={title}>
      <span className={cn("flex h-[30px] w-[30px] shrink-0 items-center justify-center rounded-[5px] border border-ring-2 bg-surface-2", CARD_TINT[tint])}>
        <Glyph name={glyph} />
      </span>
      <div className="min-w-0">
        <p className={cn("fig text-[16px] leading-none whitespace-nowrap", hue ?? "text-ink")}>{value}</p>
        <p className="qt-cap mt-[5px] text-[9.5px] leading-none text-ink-2">{label}</p>
        {sub != null && sub !== "" && <p className="mt-[3px] truncate text-[11px] leading-[1.2] text-ink-3">{sub}</p>}
      </div>
    </div>
  );
}

/** How many rows, out of how many looked at. */
export function Showing({ shown, total, word }: { shown: number; total?: number | null; word: string }) {
  return (
    <p className="fig shrink-0 text-right text-[10.5px] leading-[1.25] text-ink-3">
      <span className="text-ink-2">{shown}</span> showing
      {total != null && (
        <>
          <br />
          {total.toLocaleString()} {word}
        </>
      )}
    </p>
  );
}

/** A box that narrows the table to the tickers typed in it. */
export function TickerFilter({ value, onChange }: { value: string; onChange: (v: string) => void }) {
  return (
    <label className="flex h-[26px] w-[116px] shrink-0 items-center gap-1.5 rounded-[4px] border border-ring-2 px-2 text-ink-3">
      <Glyph name="search" size={12} />
      <input
        value={value}
        onChange={(e) => onChange(e.target.value)}
        placeholder="Ticker…"
        aria-label="Filter the table by ticker"
        spellCheck={false}
        className="fig min-w-0 flex-1 bg-transparent text-[11.5px] text-ink uppercase outline-none placeholder:text-ink-3 placeholder:normal-case"
      />
    </label>
  );
}

/** A row's left edge in the colour of its state. */
export const edgeShadow = (hue: string): React.CSSProperties => ({ boxShadow: `inset 2px 0 0 ${hue}` });

/** A panel of the slide-out: one idea, one box. */
/** `qt-card` is the hook Luminous Glass paints these as glass (globals.css `.ui-lum .qt-card`). */
export const CARD = "qt-card rounded-[6px] border border-ring bg-surface/40 px-4 py-3 qt:rounded-[4px]";

export const TH = "qt-cap border-b border-ring bg-bg px-2 py-1.5 align-bottom text-[10.5px] font-semibold whitespace-nowrap text-ink-3";
export const TD = "border-b border-ring/60 px-2 py-2 align-middle";

/** The table's row behaviour: click opens the slide-out, and Enter on a row that has the focus. */
export function rowProps(sym: string, on: boolean): React.HTMLAttributes<HTMLTableRowElement> & { "data-sym": string } {
  return {
    "data-sym": sym,
    tabIndex: 0,
    "aria-selected": on,
    onClick: () => openTicker(sym),
    onKeyDown: (e: React.KeyboardEvent) => {
      if (e.key === "Enter" || e.key === " ") {
        e.preventDefault();
        openTicker(sym);
      }
    },
    className: cn("group hit cursor-pointer outline-none focus-visible:bg-surface-2", on && "bg-surface-2"),
  };
}

/** The ticker cell of a wide table: the side, the logo, the symbol and price under it. */
export function NameCell({
  sym,
  side,
  price,
  cap,
  sub,
}: {
  sym: string;
  side: "long" | "short" | null;
  price?: string;
  cap?: number | null;
  sub?: React.ReactNode;
}) {
  return (
    <div className="flex items-center gap-1.5 whitespace-nowrap">
      <span className={cn("w-[10px] text-[11px]", side === "long" ? "text-call-fig" : side === "short" ? "text-put-fig" : "text-ink-3")}>
        {side === "long" ? "▲" : side === "short" ? "▼" : "·"}
      </span>
      <TickerLogo sym={sym} size={18} />
      <div className="min-w-0 leading-[1.25]">
        <p className="text-[13px] font-semibold text-ink">{sym}</p>
        <p className="fig text-[11px] text-ink-3">
          {price}
          {cap !== undefined && <span>{price ? " · " : ""}{capShort(cap)}</span>}
          {sub}
        </p>
      </div>
    </div>
  );
}

/** Track: onto today's list, where it is read live and signals fire. Rolls off with the day. */
export function TrackButton({ sym, tracked, onDone }: { sym: string; tracked: boolean; onDone?: () => void }) {
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState<string | null>(null);
  if (tracked) {
    return (
      <span className="qt-cap text-[9.5px] text-ink-3" title="On the list: read live, with signals">
        tracking
      </span>
    );
  }
  return (
    <button
      type="button"
      disabled={busy}
      title={err ?? "Put this name on today's list: read live, with signals and options. It rolls off with the day; the star keeps it."}
      onClick={(e) => {
        e.stopPropagation();
        setBusy(true);
        void trackName(sym).then((why) => {
          setBusy(false);
          setErr(why);
          onDone?.();
        });
      }}
      {...segItem(false, { className: cn("border border-ring-2 text-[10.5px] disabled:opacity-40", err && "text-err") })}
    >
      {err ? "Full" : "Track"}
    </button>
  );
}

export function RangeCell({
  state,
  hi,
  lo,
  hiName,
  loName,
  none = "No pre-market",
}: {
  state: RangeState | "forming" | null;
  hi: number | null;
  lo: number | null;
  hiName: string;
  loName: string;
  /** What to say when the range does not exist. */
  none?: string;
}) {
  if (state === null || hi === null || lo === null) return <span className="text-[11.5px] text-ink-3">{none}</span>;
  if (state === "forming") {
    return (
      <div className="leading-[1.3]">
        <p className="text-[11.5px] text-ink-2">Forming</p>
        <p className="fig text-[10.5px] text-ink-3">
          {num(lo)} – {num(hi)}
        </p>
      </div>
    );
  }
  if (state === "inside") {
    return (
      <div className="leading-[1.3]">
        <p className="text-[11.5px] text-ink-2"><span aria-hidden className="text-ink-3">↔</span> Inside range</p>
        <p className="fig text-[10.5px] text-ink-3">
          ${num(lo)} – ${num(hi)}
        </p>
      </div>
    );
  }
  const up = state === "above";
  return (
    <div className="leading-[1.3]">
      <p className={cn("text-[11.5px]", up ? "text-call-fig" : "text-put-fig")}>
        {up ? "▲ Bullish" : "▼ Bearish"}
      </p>
      <p className="fig text-[10.5px] text-ink-3">
        {up ? "Above" : "Below"} {up ? hiName : loName} ${num(up ? hi : lo)}
      </p>
    </div>
  );
}

/** Which day of the move, as pips: ●●○○ 2. */
export function StagePips({ stage }: { stage: number }) {
  const n = Math.min(stage, 4);
  return (
    <span className="inline-flex items-center gap-[3px]" aria-label={`Day ${stage}`}>
      {[0, 1, 2, 3].map((i) => (
        <span key={i} className={cn("h-[6px] w-[6px] rounded-[1px]", i < n ? "bg-ink-2" : "bg-[var(--qt-track,var(--ring))]")} />
      ))}
      <span className="fig ml-1 text-[12px] text-ink">{stage}</span>
    </span>
  );
}

/** The volume cell's two lines. */
export function VolCell({ vol, adv }: { vol: number | null; adv: number | null }) {
  return (
    <div className="fig text-right leading-[1.3]">
      <p className="text-[12px] text-ink-2">{vol != null ? compact(vol) : "—"}</p>
      <p className={cn("text-[10.5px]", (adv ?? 0) >= 200 ? "text-ink" : "text-ink-3")}>{adv != null ? `${Math.round(adv)}% ADV` : ""}</p>
    </div>
  );
}

/** How old the read is and that it is delayed, said once per page. */
export function delayedLine(ageMin: number | null, delayed: number, liveCount?: number): string {
  const age = ageMin == null ? "" : ageMin < 1 ? " · read just now" : ` · read ${Math.round(ageMin)}m ago`;
  return `${delayed} min delayed${liveCount ? ` · ${liveCount} on the live stream` : ""}${age}`;
}

export { closeTicker };
