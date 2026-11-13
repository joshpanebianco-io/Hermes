"use client";

import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import type { PhaseKey, TodayPayload, TodayRow, TodayTrigger } from "@/types/today";
import { PageLoader, PageNote } from "@/components/ui/HelmLoader";
import { CatalystCell, Chips, Head, Spark, TD, TH, Tag, TickerCell, TickerFilter, rowProps } from "@/components/panels/ScanWide";
import { cn } from "@/lib/cn";
import { num } from "@/lib/format";
import { segItem } from "@/lib/seg";
import { oneOf, usePersisted } from "@/lib/usePersisted";
import { usePinsChanged } from "@/lib/usePinsChanged";
import { useTicker } from "@/lib/ticker";

/*
 * TODAY: THE STOCKS TAB'S ONE LIST (owner, 2026-11-13: "a nice consistent work flow for
 * analysing the market and making it easier to pick good stocks to trade for the day,
 * without all the confusing clutter and multiple sections"). One table all day, whose
 * ranking changes with the clock (server today.py):
 *
 *   After hours  16:00–20:00  movers after the close, and the day's big movers
 *   Overnight    20:00–04:00  the prep for the next session
 *   Pre-market   04:00–09:30  in play going into the open, updating live
 *   The open     09:30–10:00  the same names, by what the bell has done to them
 *   Session      10:00–16:00  the best trades now: the engine's setup score
 *
 * Every row says why it is there, carries its story, and its plan: both triggers before
 * a side is decided, the live setup once it is. A row opens the slide-out as everywhere.
 */

/** How often the list is read again: a phase that moves by the second, read often. */
const POLL_SEC: Record<PhaseKey, number> = { session: 10, open: 10, pre: 15, after: 30, overnight: 60 };

type SideF = "all" | "long" | "short" | "fav";
const SIDES: ReadonlyArray<{ key: SideF; label: string; title: string }> = [
  { key: "all", label: "All", title: "Every name on the list" },
  { key: "long", label: "Long", title: "Names leaning long: gapped or moving up, or a long setup" },
  { key: "short", label: "Short", title: "Names leaning short: gapped or moving down, or a short setup" },
  { key: "fav", label: "★ Favourites", title: "Your pinned names, when they are on the list" },
];

const MOVE_WORD = { pre: "pre", after: "after", day: "day" } as const;

export function StocksToday({ onPlan }: { onPlan: () => void }) {
  const [data, setData] = useState<TodayPayload | null>(null);
  const [failed, setFailed] = useState<string | null>(null);
  const [sideF, setSideF] = usePersisted<SideF>("today.side", "all", oneOf("all", "long", "short", "fav"));
  const [find, setFind] = useState("");
  const ticker = useTicker();
  const seq = useRef(0);

  const load = useCallback(async () => {
    const mine = ++seq.current;
    try {
      const r = await fetch("/api/scanner/today", { cache: "no-store" });
      const next = (await r.json()) as TodayPayload & { offline?: { reason: string } };
      if (mine !== seq.current) return;
      if (next.offline) setFailed(next.offline.reason);
      else {
        setData(next);
        setFailed(null);
      }
    } catch (e) {
      if (mine === seq.current) setFailed(e instanceof Error ? e.message : "request failed");
    }
  }, []);
  usePinsChanged(load);

  const phaseKey = data?.phase?.key ?? "overnight";
  useEffect(() => {
    void load();
    const id = setInterval(load, POLL_SEC[phaseKey] * 1000);
    return () => clearInterval(id);
  }, [load, phaseKey]);

  const counts = useMemo(() => {
    const rows = data?.rows ?? [];
    return {
      all: rows.length,
      long: rows.filter((r) => r.lean === "long").length,
      short: rows.filter((r) => r.lean === "short").length,
      fav: rows.filter((r) => r.fav).length,
    };
  }, [data?.rows]);

  const rows = useMemo(() => {
    const typed = find.trim().toUpperCase();
    return (data?.rows ?? []).filter(
      (r) =>
        (sideF === "all" || (sideF === "fav" ? r.fav : r.lean === sideF)) && (!typed || r.sym.includes(typed)),
    );
  }, [data?.rows, sideF, find]);

  if (!data) {
    return failed ? (
      <PageNote>
        <strong className="font-semibold text-err">The list is unavailable.</strong> {failed}. Nothing here is cached or invented.
      </PageNote>
    ) : (
      <PageLoader label="Reading the list" />
    );
  }

  const ph = data.phase;
  return (
    <div className="flex min-h-0 flex-1 flex-col">
      <PhaseStrip data={data} />
      <div className="flex shrink-0 flex-wrap items-center gap-2 border-b border-ring px-3 py-1.5 qt:px-4">
        <Chips items={SIDES} on={sideF} set={setSideF} counts={counts} />
        <span className="ml-auto flex items-center gap-2">
          <TickerFilter value={find} onChange={setFind} />
          <button type="button" onClick={onPlan} title="The written pre-open game plan for the list's best names" {...segItem(false, { className: "border border-ring-2" })}>
            Game plan
          </button>
        </span>
      </div>
      {failed && <p className="qt-slab border-b border-ring bg-err/10 px-4 py-1.5 text-[11.5px] text-err">Last read failed ({failed}); showing the one before.</p>}
      {rows.length === 0 ? (
        <PageNote>{data.note ?? (data.rows.length ? "No name on the list matches that filter." : EMPTY[ph.key])}</PageNote>
      ) : (
        <div className="min-h-0 flex-1 overflow-auto">
          <table className="w-full min-w-[1240px] border-separate border-spacing-0 text-left">
            <thead className="sticky top-0 z-20">
              <tr>
                <th scope="col" className={cn(TH, "w-[34px] text-right")}>#</th>
                <th scope="col" className={cn(TH, "sticky left-0 z-30 w-[210px]")}><Head label="Ticker" hint="price · lean" /></th>
                <th scope="col" className={cn(TH, "text-right")}><Head label="Move" hint={MOVE_HINT[ph.key]} right /></th>
                <th scope="col" className={TH}><Head label="Why it's here" hint={WHY_HINT[ph.key]} /></th>
                <th scope="col" className={TH}><Head label="News" hint="the story moving it" /></th>
                <th scope="col" className={TH}><Head label={ph.key === "session" || ph.key === "open" ? "Setup" : "Plan"} hint={PLAN_HINT[ph.key]} /></th>
                <th scope="col" className={TH}><Head label="Score" hint={ph.key === "session" ? "setup, of 100" : "in play"} /></th>
                <th scope="col" className={TH}><Head label="Spark" hint="today" /></th>
              </tr>
            </thead>
            <tbody>
              {rows.map((r) => (
                <Row key={r.sym} r={r} phase={ph.key} on={ticker === r.sym} onPinned={load} />
              ))}
            </tbody>
          </table>
        </div>
      )}
    </div>
  );
}

/* ---- the phase strip ------------------------------------------------------- */

function untilWord(min: number): string {
  if (min < 1) return "now";
  if (min < 90) return `in ${Math.round(min)}m`;
  const h = Math.floor(min / 60);
  const m = Math.round(min % 60);
  if (h < 24) return `in ${h}h${m ? ` ${m}m` : ""}`;
  return `in ${Math.round(h / 24)}d`;
}

function dayWord(iso: string): string {
  const d = new Date(`${iso}T12:00:00Z`);
  return d.toLocaleDateString("en-US", { weekday: "long", day: "numeric", month: "short", timeZone: "UTC" });
}

function PhaseStrip({ data }: { data: TodayPayload }) {
  const ph = data.phase;
  const forNext = ph.key === "after" || ph.key === "overnight";
  const updated = new Date(data.updated_utc).toLocaleTimeString("en-US", { hour: "2-digit", minute: "2-digit", second: "2-digit", hour12: false, timeZone: "America/New_York" });
  return (
    <div className="flex shrink-0 flex-wrap items-center gap-x-5 gap-y-1.5 border-b border-ring px-3 py-2.5 qt:px-4">
      <ol className="flex items-center gap-1.5 text-[11.5px]" aria-label="The day's phases">
        {data.phases.map((p, i) => {
          const on = p.key === ph.key;
          return (
            <li key={p.key} className="flex items-center gap-1.5">
              {i > 0 && <span aria-hidden className="text-ink-3/60">›</span>}
              <span
                aria-current={on ? "step" : undefined}
                className={cn("rounded-[3px] px-1.5 py-[2px] whitespace-nowrap", on ? "bg-surface-2 font-semibold text-ink" : "text-ink-3")}
              >
                {on && <span aria-hidden className="mr-1.5 inline-block h-[6px] w-[6px] rounded-full bg-call align-middle" />}
                {p.label}
              </span>
            </li>
          );
        })}
      </ol>
      <p className="min-w-0 flex-1 text-[12.5px] text-ink-2">
        {ph.title}
        {forNext && <span className="text-ink-3"> · for {dayWord(ph.day)}</span>}
      </p>
      <p className="fig shrink-0 text-[11px] text-ink-3" title="The list is read again on its own; prices on the live stream move with every read">
        {data.replay ? <span className="mr-2 rounded-[3px] border border-flip-fig/50 px-1 text-flip-fig">{data.replay}</span> : null}
        {ph.next_label} {untilWord(ph.ends_in_min)} · updated {updated} ET
      </p>
    </div>
  );
}

const EMPTY: Record<PhaseKey, string> = {
  after: "Nothing has moved enough since the close to make the list yet.",
  overnight: "Nothing moved enough this evening to make the list.",
  pre: "Nothing is in play yet this morning. Names arrive as the pre-market trades.",
  open: "The pre-market's names arrive here at the bell.",
  session: "The engine has read no names yet.",
};
const MOVE_HINT: Record<PhaseKey, string> = {
  after: "since the prior close",
  overnight: "since the prior close",
  pre: "pre-market vs close",
  open: "since the close",
  session: "since the close",
};
const WHY_HINT: Record<PhaseKey, string> = {
  after: "move in ATRs · volume · news",
  overnight: "move in ATRs · volume · news",
  pre: "gap in ATRs · volume · news",
  open: "the pre-market's read",
  session: "the score's best parts",
};
const PLAN_HINT: Record<PhaseKey, string> = {
  after: "tomorrow's levels, both ways",
  overnight: "tomorrow's levels, both ways",
  pre: "both triggers",
  open: "what the bell has done",
  session: "the live setup",
};

/* ---- a row ------------------------------------------------------------------ */

function Row({ r, phase, on, onPinned }: { r: TodayRow; phase: PhaseKey; on: boolean; onPinned: () => void }) {
  const tags: React.ReactNode[] = [];
  if (r.lean) tags.push(<Tag key="lean" tone={r.lean === "long" ? "up" : "down"} title="Which way the move or the setup leans: a lean, not a call">{r.lean === "long" ? "▲ long" : "▼ short"}</Tag>);
  if (r.stage && r.stage >= 2) tags.push(<Tag key="day" tone="warn" title="Day 2 or later of a 20% move">Day {r.stage}</Tag>);
  if (r.gated) tags.push(<Tag key="gate" tone="flat" title="Under 1.0× RVOL: kept out of the top ten">RVOL gate</Tag>);
  return (
    <tr {...rowProps(r.sym, on)}>
      <td className={cn(TD, "text-right align-top")}>
        <p className="fig text-[12px] text-ink-3">{r.rank}</p>
        {r.new && (
          <span className="mt-1 inline-block">
            <Tag tone="news" title="Came into the top ten in the last fifteen minutes">New</Tag>
          </span>
        )}
      </td>
      <td className={cn(TD, "sticky left-0 z-10 w-[210px]", on ? "bg-surface-2" : "bg-bg group-hover:bg-surface")}>
        <TickerCell
          sym={r.sym}
          name={r.name}
          price={r.last != null ? `$${num(r.last)}` : null}
          tags={tags}
          pinned={r.fav}
          onPinned={onPinned}
          tracked={r.tracked}
          stack
        />
      </td>
      <td className={cn(TD, "fig text-right leading-[1.3]")}>
        <p className={cn("text-[13px]", (r.chg ?? 0) >= 0 ? "text-call-fig" : "text-put-fig")}>
          {r.chg == null ? "—" : `${r.chg >= 0 ? "+" : ""}${r.chg.toFixed(1)}%`}
        </p>
        <p className="text-[10.5px] text-ink-3">
          {MOVE_WORD[r.move]}
          {r.live && <span title="A live trade" className="ml-1 text-call-fig">●</span>}
          {r.gap_atr != null && <span className="ml-1">{r.gap_atr.toFixed(2)} ATR</span>}
        </p>
      </td>
      <td className={TD}>
        <ul className="flex max-w-[360px] flex-wrap gap-x-2 gap-y-0.5 text-[12px] leading-[1.35] text-ink-2">
          {r.why.map((w, i) => (
            <li key={i} className={cn(i > 0 && "before:mr-2 before:text-ink-3/60 before:content-['·']")}>{w}</li>
          ))}
        </ul>
      </td>
      <td className={TD}>
        <CatalystCell c={r.story} width={300} />
      </td>
      <td className={cn(TD, "max-w-[300px]")}>{phase === "session" || phase === "open" ? <SetupCell r={r} /> : <PlanCell r={r} />}</td>
      <td className={TD}>
        <ScoreCell r={r} />
      </td>
      <td className={TD}>
        <Spark pts={r.spark} w={76} />
      </td>
    </tr>
  );
}

function trigger(t: TodayTrigger | null, side: "long" | "short"): React.ReactNode {
  if (!t) return null;
  const arrow = side === "long" ? "▲" : "▼";
  const word = t.held ? `retest of ${t.level}` : `${side === "long" ? "above" : "below"} ${t.level}`;
  return (
    <p className="fig text-[12px] leading-[1.45] whitespace-nowrap">
      <span className={side === "long" ? "text-call-fig" : "text-put-fig"}>{arrow}</span>{" "}
      <span className="text-ink-2">{word}</span> <span className="text-ink">{num(t.price)}</span>
    </p>
  );
}

function PlanCell({ r }: { r: TodayRow }) {
  if (!r.plan || (!r.plan.long && !r.plan.short)) return <span className="text-[12px] text-ink-3">—</span>;
  // The lean's trigger first.
  const order: Array<"long" | "short"> = r.lean === "short" ? ["short", "long"] : ["long", "short"];
  return <div>{order.map((s) => <div key={s}>{trigger(r.plan?.[s] ?? null, s)}</div>)}</div>;
}

const STATE_HUE: Record<string, string> = {
  retest: "text-ink font-semibold",
  pullback: "text-ink",
  extended: "text-ink-2",
  approaching: "text-flip-fig",
  failed: "text-ink-3 line-through",
  chop: "text-ink-3",
  forming: "text-ink-3",
};

function SetupCell({ r }: { r: TodayRow }) {
  const s = r.setup;
  if (!s) {
    return (
      <div>
        {r.status && <p className="qt-cap text-[10px] text-ink-3">{r.status}</p>}
        <PlanCell r={r} />
      </div>
    );
  }
  return (
    <div title={s.note ?? undefined}>
      {r.status && <p className="qt-cap text-[10px] text-ink-3">{r.status}</p>}
      <p className={cn("line-clamp-2 text-[12px] leading-[1.35]", STATE_HUE[s.state ?? ""] ?? "text-ink-2")}>
        {s.side && <span className={cn("mr-1 text-[10px]", s.side === "long" ? "text-call-fig" : "text-put-fig")}>{s.side === "long" ? "▲" : "▼"}</span>}
        {s.note ?? s.state}
      </p>
    </div>
  );
}

function ScoreCell({ r }: { r: TodayRow }) {
  if (r.score == null) return <span className="text-[12px] text-ink-3">—</span>;
  const frac = Math.max(0, Math.min(1, r.score / (r.score_max || 100)));
  const hue = frac >= 0.65 ? "call" : frac >= 0.45 ? "flip" : "ink";
  const fig = { call: "text-call-fig", flip: "text-flip-fig", ink: "text-ink-2" }[hue];
  const bar = { call: "bg-call-fig", flip: "bg-flip-fig", ink: "bg-ink-3" }[hue];
  const title =
    r.score_kind === "setup"
      ? `Setup score ${r.score} of 100${r.raw != null && r.raw !== r.score ? ` (${r.raw} before the cap: the list is ranked on it)` : ""}`
      : `In play ${r.score.toFixed(1)} of ${r.score_max}: the move in daily ATRs, volume against normal, a report or a story, a level already through, a Day 2 or 3`;
  return (
    <div className="min-w-[78px]" title={title}>
      <p className={cn("fig text-[12.5px] leading-none", fig)}>
        {r.score_kind === "setup" ? r.score : r.score.toFixed(1)}
        <span className="text-[10px] text-ink-3"> {r.score_kind === "setup" ? "/100" : "in play"}</span>
      </p>
      <div className="relative mt-[6px] h-[3px] bg-[var(--qt-track,var(--ring))]">
        <span className={cn("absolute inset-y-0 left-0", bar)} style={{ width: `${frac * 100}%` }} />
      </div>
    </div>
  );
}
