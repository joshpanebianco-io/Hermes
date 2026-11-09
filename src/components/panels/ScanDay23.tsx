"use client";

import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import type { Day23Chip, Day23Payload, Day23Row, Side } from "@/types/scanner";
import { HelmLoader } from "@/components/ui/HelmLoader";
import {
  CatalystCell,
  Chips,
  Choice,
  Menu,
  NameCell,
  Spark,
  StagePips,
  TD,
  TH,
  TrackButton,
  capWord,
  dayName,
  dayShort,
  delayedLine,
  isNum,
  pctText,
  rowProps,
  useWalk,
} from "@/components/panels/ScanWide";
import { num } from "@/lib/format";
import { cn } from "@/lib/cn";
import { useTicker } from "@/lib/ticker";
import { oneOf, usePersisted } from "@/lib/usePersisted";

/**
 * Day 2/3 — the big movers, and whether they are still moving (momentum.py).
 *
 * Day 1 is an outsized move on heavy volume, usually on news. Day 2 is the session
 * after, and Day 1's high is now the PDH, so it is the desk's usual break and retest
 * on the strongest names of the week. An inside day is the move resting; a break of
 * that small range is the next trigger. Day 3 and on are older and more stretched.
 *
 * Grouped by side, what is holding first. Words, not a score: a row says what the
 * name did and where it stands against its own level.
 */

const CHIPS: ReadonlyArray<{ key: Day23Chip; label: string; title?: string }> = [
  { key: "all", label: "All" },
  { key: "long", label: "Long" },
  { key: "short", label: "Short" },
  { key: "day1", label: "Day 1" },
  { key: "day2", label: "Day 2" },
  { key: "day3", label: "Day 3+" },
  { key: "inside", label: "Inside day", title: "The whole session inside the previous day's range: resting" },
  { key: "through", label: "Through PDH / PDL" },
];
const MOVES = [10, 15, 20, 30].map((value) => ({ value, label: `${value}%+` }));
const CAPS = [3e8, 2e9, 5e9, 1e10].map((value) => ({ value, label: capWord(value) }));
const KIND_HUE: Record<Day23Row["kind"], string> = {
  confirmed: "text-ink",
  inside: "text-ink-2",
  watch: "text-ink-3",
  failed: "text-ink-3 line-through decoration-ink-3/60",
};

export function ScanDay23({ onTrackChanged }: { onTrackChanged?: () => void }) {
  const [chip, setChip] = usePersisted<Day23Chip>("d23.chip", "all", oneOf("all", "long", "short", "day1", "day2", "day3", "inside", "through"));
  const [move, setMove] = usePersisted<number>("d23.move", 20, isNum);
  const [cap, setCap] = usePersisted<number>("d23.cap", 2e9, isNum);
  const [data, setData] = useState<Day23Payload | null>(null);
  const seq = useRef(0);
  const ticker = useTicker();

  const q = useMemo(() => new URLSearchParams({ chip, move: String(move), cap: String(cap) }).toString(), [chip, move, cap]);
  const load = useCallback(async () => {
    const mine = ++seq.current;
    try {
      const r = await fetch(`/api/scanner/day23?${q}`, { cache: "no-store" });
      const d = (await r.json()) as Day23Payload;
      if (mine === seq.current) setData(d);
    } catch {
      /* the last read stays on screen */
    }
  }, [q]);

  const on = data?.ok ? data.basis !== "last" : false;
  useEffect(() => {
    void load();
    const id = setInterval(load, on ? 5000 : 60_000);
    return () => clearInterval(id);
  }, [load, on]);

  const syms = useMemo(() => {
    const rows = data?.rows ?? [];
    return [...rows.filter((r) => r.side === "long"), ...rows.filter((r) => r.side === "short")].map((r) => r.sym);
  }, [data]);
  useWalk(syms);

  if (!data) return <HelmLoader label="Reading the ledger" size={48} minHeight={420} />;
  if (!data.ok) {
    return <p className="px-6 py-10 text-center text-[12px] text-ink-3">{data.offline ? `${data.offline.reason}.` : (data.error ?? "The wide read has not landed yet.")}</p>;
  }
  const c = data.chips;
  const longs = data.rows.filter((r) => r.side === "long");
  const shorts = data.rows.filter((r) => r.side === "short");
  const today = data.basis === "last" ? dayName(data.day).split(" ")[0].replace(",", "") : "Today";
  const summary = `${move}%+ · 1.5× volume · ${capWord(cap)}`;

  return (
    <div className="flex min-h-0 flex-1 flex-col">
      <div className="flex shrink-0 flex-wrap items-baseline gap-x-8 gap-y-1 border-b border-ring px-6 py-3">
        <Card value={c.day1} word="Day 1" sub={`a ${move}%+ move on 1.5× volume`} />
        <Card value={c.day2} word="Day 2" sub="first continuation day" />
        <Card value={c.day3} word="Day 3+" sub={c.day3 === 0 ? "fills in over the next sessions" : "older, more stretched"} />
        <Card value={c.inside} word="Inside days" sub="resting, not triggered" />
        <Card value={c.through} word="Through PDH / PDL" sub="" />
        <p className="fig ml-auto text-[11px] text-ink-3">
          {data.basis === "last" ? `As of ${dayName(data.day)}` : "This session"} · {delayedLine(data.read_age_min, data.delayed_min)}
        </p>
      </div>
      <div className="flex shrink-0 flex-wrap items-center gap-2 px-6 py-2.5">
        <Chips items={CHIPS} on={chip} set={setChip} counts={c} />
        <div className="ml-auto flex items-center gap-2">
          <span className="fig text-[11px] text-ink-3">{data.shown} showing</span>
          <Menu label={<>Filters · <span className="fig">{summary}</span></>}>
            <Choice label="Day 1 move" options={MOVES} value={move} set={setMove} />
            <Choice label="Market cap" options={CAPS} value={cap} set={setCap} />
          </Menu>
        </div>
      </div>
      <div className="min-h-0 flex-1 overflow-auto">
        {data.rows.length === 0 ? (
          <p className="px-6 py-10 text-center text-[12px] text-ink-3">No moves at these filters. The ledger keeps everything from 10% and $300m, so loosening them shows more straight away.</p>
        ) : (
          <table className="w-full min-w-[1160px] border-separate border-spacing-0 text-left">
            <thead className="sticky top-0 z-20">
              <tr>
                <th scope="col" className={cn(TH, "sticky left-0 z-30 w-[148px]")}>Ticker</th>
                <th scope="col" className={TH}>Day</th>
                <th scope="col" className={cn(TH, "text-right")}>Day 1 move</th>
                <th scope="col" className={cn(TH, "text-right")}>{today}</th>
                <th scope="col" className={cn(TH, "text-right")} title="Yesterday's high for a long, its low for a short, and how far price is from it">PDH / PDL</th>
                <th scope="col" className={cn(TH, "text-right")}>Volume</th>
                <th scope="col" className={TH}>State</th>
                <th scope="col" className={cn(TH, "text-right")} title="Since Day 1's close">Since</th>
                <th scope="col" className={TH}>Most important story</th>
                <th scope="col" className={TH}>Today</th>
                <th scope="col" className={TH} />
              </tr>
            </thead>
            <tbody>
              <Group side="long" rows={longs} ticker={ticker} onDone={() => { void load(); onTrackChanged?.(); }} />
              <Group side="short" rows={shorts} ticker={ticker} onDone={() => { void load(); onTrackChanged?.(); }} />
            </tbody>
          </table>
        )}
      </div>
    </div>
  );
}

function Group({ side, rows, ticker, onDone }: { side: Side; rows: Day23Row[]; ticker: string | null; onDone: () => void }) {
  if (rows.length === 0) return null;
  return (
    <>
      <tr>
        <td colSpan={11} className="border-b border-ring/60 bg-bg px-2 pt-3 pb-1.5">
          <span className={cn("qt-cap text-[10.5px] font-semibold", side === "long" ? "text-call-fig" : "text-put-fig")}>{side === "long" ? "Long side" : "Short side"}</span>
          <span className="fig ml-2 text-[11px] text-ink-3">{rows.length} names</span>
        </td>
      </tr>
      {rows.map((r) => (
        <tr key={r.sym} {...rowProps(r.sym, ticker === r.sym)}>
          <td className={cn(TD, "sticky left-0 z-10", ticker === r.sym ? "bg-surface-2" : "bg-bg group-hover:bg-surface")}>
            <NameCell sym={r.sym} side={r.side} price={num(r.last)} cap={r.cap} sub={r.live ? <span className="qt-cap ml-1.5 text-[9px] text-call-fig">live</span> : undefined} />
          </td>
          <td className={TD}>
            <StagePips stage={r.stage} />
            <p className="fig mt-0.5 text-[10.5px] text-ink-3">moved {dayShort(r.moved)}</p>
          </td>
          <td className={cn(TD, "fig text-right leading-[1.3]")}>
            <p className={cn("text-[12px]", r.move >= 0 ? "up" : "down")}>{pctText(r.move)}</p>
            <p className="text-[10.5px] text-ink-3">{r.vx != null ? `${r.vx.toFixed(1)}× vol` : ""}</p>
          </td>
          <td className={cn(TD, "fig text-right text-[12px]", (r.chg ?? 0) >= 0 ? "up" : "down")}>{pctText(r.chg)}</td>
          <td className={cn(TD, "fig text-right leading-[1.3]")}>
            <p className="text-[12px] text-ink-2">{num(r.level)}</p>
            <p className="text-[10.5px] text-ink-3">{pctText(r.to_level, 1)}</p>
          </td>
          <td className={cn(TD, "fig text-right text-[12px]", (r.adv_pct ?? 0) >= 200 ? "text-ink" : "text-ink-2")}>{r.adv_pct != null ? `${Math.round(r.adv_pct)}% ADV` : "—"}</td>
          <td className={cn(TD, "text-[12px] whitespace-nowrap", KIND_HUE[r.kind])}>{r.state}</td>
          <td className={cn(TD, "fig text-right text-[12px]", r.stage <= 1 ? "text-ink-3" : (r.since ?? 0) >= 0 ? "up" : "down")}>{r.stage <= 1 ? "—" : pctText(r.since, 1)}</td>
          <td className={TD}>
            <CatalystCell c={r.catalyst} width={340} />
          </td>
          <td className={TD}>
            <Spark pts={r.spark} />
          </td>
          <td className={cn(TD, "text-right")}>
            <TrackButton sym={r.sym} tracked={r.tracked} onDone={onDone} />
          </td>
        </tr>
      ))}
    </>
  );
}

function Card({ value, word, sub }: { value: number; word: string; sub: string }) {
  return (
    <p className="flex items-baseline gap-2 whitespace-nowrap">
      <span className="fig text-[17px] leading-none text-ink">{value}</span>
      <span className="text-[12px] font-semibold text-ink-2">{word}</span>
      {sub && <span className="text-[11px] text-ink-3 max-[1599px]:hidden">{sub}</span>}
    </p>
  );
}
