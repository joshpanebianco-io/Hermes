"use client";

import { useEffect, useRef, useState } from "react";
import type { Catalyst, RangeState, ScanRow } from "@/types/scanner";
import { TickerLogo } from "@/components/ui/TickerLogo";
import { compact, num } from "@/lib/format";
import { cn } from "@/lib/cn";
import { segItem } from "@/lib/seg";
import { closeTicker, openTicker, trackName, useTicker } from "@/lib/ticker";

/**
 * What the wide tables share: Breakouts, Extended hours and Day 2/3 read the same
 * screener and draw the same cells, so a catalyst, a sparkline and a filter look
 * and behave one way on all three.
 *
 * No new hues. The screenshots these came from band their headers in five colours;
 * on this terminal a hue means one thing, so the bands are rules and small caps,
 * and only what carries a side is green or pink.
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

/** A button that names what it holds and opens a panel under itself. */
export function Menu({ label, children, width = 340 }: { label: React.ReactNode; children: React.ReactNode; width?: number }) {
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
      <button type="button" onClick={() => setOpen((v) => !v)} aria-expanded={open} {...segItem(open, { className: "border border-ring-2" })}>
        {label}
      </button>
      {open && (
        <div className="absolute top-full right-0 z-40 mt-1 flex flex-col gap-3 rounded-[4px] border border-ring-2 bg-surface p-3 shadow-[0_12px_40px_rgba(0,0,0,.55)]" style={{ width }}>
          {children}
        </div>
      )}
    </span>
  );
}

/** A band of column-group names over a table's header. */
export function GroupHead({ groups }: { groups: ReadonlyArray<{ label: string; span: number }> }) {
  return (
    <tr>
      {groups.map((g, i) => (
        <th key={`${g.label}-${i}`} colSpan={g.span} scope="colgroup" className="qt-cap border-b border-ring-2 bg-bg px-2 pt-2 pb-1 text-left text-[9.5px] font-semibold text-ink-3">
          {g.label}
        </th>
      ))}
    </tr>
  );
}

/** A panel of the slide-out: one idea, one box. */
export const CARD = "rounded-[6px] border border-ring bg-surface/40 px-4 py-3 qt:rounded-[4px]";

export const TH = "qt-cap border-b border-ring bg-bg px-2 py-1.5 align-bottom text-[10.5px] font-semibold whitespace-nowrap text-ink-3";
export const TD = "border-b border-ring/60 px-2 py-2 align-middle";

/** The table's row behaviour: click opens the slide-out; Enter too; the arrows walk. */
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

/**
 * ↑ AND ↓ WALK THE LIST WHILE THE SLIDE-OUT IS OPEN, wherever the focus is: the
 * table behind it stays live, and reading thirty names is a walk down a column.
 */
export function useWalk(syms: readonly string[]): void {
  const ticker = useTicker();
  useEffect(() => {
    if (!ticker) return;
    const onKey = (e: KeyboardEvent) => {
      if (e.defaultPrevented || e.ctrlKey || e.metaKey || e.altKey) return;
      if (e.key !== "ArrowDown" && e.key !== "ArrowUp") return;
      const el = e.target as HTMLElement | null;
      if (el && (el.isContentEditable || /^(INPUT|TEXTAREA|SELECT)$/.test(el.tagName))) return;
      const i = syms.indexOf(ticker);
      const next = i < 0 ? undefined : syms[i + (e.key === "ArrowDown" ? 1 : -1)];
      if (!next) return;
      e.preventDefault();
      openTicker(next);
      document.querySelector(`tr[data-sym="${next}"]`)?.scrollIntoView({ block: "nearest" });
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [ticker, syms]);
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
        <p className="text-[11.5px] text-ink-3">Inside</p>
        <p className="fig text-[10.5px] text-ink-3">
          {num(lo)} – {num(hi)}
        </p>
      </div>
    );
  }
  const up = state === "above";
  return (
    <div className="leading-[1.3]">
      <p className={cn("text-[11.5px]", up ? "text-call-fig" : "text-put-fig")}>
        {up ? "▲ Above" : "▼ Below"} {up ? hiName : loName}
      </p>
      <p className="fig text-[10.5px] text-ink-3">{num(up ? hi : lo)}</p>
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
