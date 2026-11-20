"use client";

import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import type { Day23Chip, Day23Payload, Day23Row, Side } from "@/types/scanner";
import { PageLoader, PageNote } from "@/components/ui/HelmLoader";
import {
  CatalystCell,
  Chips,
  Choice,
  Glyph,
  Head,
  Menu,
  ScoreBar,
  Showing,
  Spark,
  SPARK_TIP,
  StagePips,
  TD,
  TH,
  Tag,
  TickerCell,
  capShort,
  capWord,
  dayName,
  dayShort,
  delayedLine,
  edgeShadow,
  isNum,
  pctText,
  rowProps,
} from "@/components/panels/ScanWide";
import { compact, num } from "@/lib/format";
import { cn } from "@/lib/cn";
import { keepRead, lastRead } from "@/lib/lastRead";
import { THROUGH_DAY_TITLE } from "@/lib/outsideDay";
import { useTicker } from "@/lib/ticker";
import { oneOf, usePersisted } from "@/lib/usePersisted";
import { usePinsChanged } from "@/lib/usePinsChanged";

/**
 * Day 2/3 — the big movers, and whether they are still moving (momentum.py).
 *
 * Day 1 is an outsized move on heavy volume, usually on news. Day 2 is the session
 * after, and Day 1's high is now the PDH, so it is the desk's usual break and retest
 * on the strongest names of the week. An inside day is the move resting; a break of
 * that small range is the next trigger. Day 3 and on are older and more stretched.
 *
 * THE SCREENSHOTS' PAGE (owner, 2026-11-10): the counts in a row of cards, the table
 * under coloured group rules, grouped by side and ranked best first. A row still says
 * in words what the name did and where it stands against its own levels.
 */

const CHIPS: ReadonlyArray<{ key: Day23Chip; label: string; title?: string }> = [
  { key: "all", label: "All" },
  // Not "Outside": an outside day is through both ranges (lib/outsideDay); this is the
  // previous day's level alone.
  { key: "through", label: "Through PDH/PDL", title: THROUGH_DAY_TITLE },
  { key: "inside", label: "Inside Day", title: "The whole session inside the previous day's range: resting" },
  { key: "long", label: "Long" },
  { key: "short", label: "Short" },
  { key: "day1", label: "Day 1" },
  { key: "day2", label: "Day 2" },
  { key: "day3", label: "Day 3+" },
];
const MOVES = [10, 15, 20, 30].map((value) => ({ value, label: `${value}%+` }));
const CAPS = [3e8, 2e9, 5e9, 1e10].map((value) => ({ value, label: capWord(value) }));

/** A track's kind as the row's pill, and the colour of its left edge. */
const KIND: Record<Day23Row["kind"], { word: string; tone: "up" | "flat" | "warn" | "down"; edge: string }> = {
  confirmed: { word: "Confirmed", tone: "up", edge: "var(--call-fig)" },
  inside: { word: "Inside day", tone: "flat", edge: "var(--ink-4)" },
  watch: { word: "Watch", tone: "warn", edge: "var(--flip-fig)" },
  failed: { word: "Failed", tone: "down", edge: "var(--put-fig)" },
};

export function ScanDay23({ onTrackChanged }: { onTrackChanged?: () => void }) {
  const [chip, setChip] = usePersisted<Day23Chip>("d23.chip", "all", oneOf("all", "long", "short", "day1", "day2", "day3", "inside", "through"));
  const [move, setMove] = usePersisted<number>("d23.move", 20, isNum);
  const [cap, setCap] = usePersisted<number>("d23.cap", 2e9, isNum);
  const [data, setData] = useState<Day23Payload | null>(() => lastRead<Day23Payload>("scan.day23"));
  const seq = useRef(0);
  const ticker = useTicker();

  const q = useMemo(() => new URLSearchParams({ chip, move: String(move), cap: String(cap) }).toString(), [chip, move, cap]);
  const load = useCallback(async () => {
    const mine = ++seq.current;
    try {
      const r = await fetch(`/api/scanner/day23?${q}`, { cache: "no-store" });
      const d = (await r.json()) as Day23Payload;
      if (mine === seq.current) setData(keepRead("scan.day23", d));
    } catch {
      /* the last read stays on screen */
    }
  }, [q]);
  // A star elsewhere, or the Undo on the unpin notice, changed the list: read it again.
  usePinsChanged(load);

  const on = data?.ok ? data.basis !== "last" : false;
  useEffect(() => {
    void load();
    const id = setInterval(load, on ? 5000 : 60_000);
    return () => clearInterval(id);
  }, [load, on]);

  // A card where the view will be, not the helm on the ground (ui/HelmLoader PageLoader).
  if (!data) return <PageLoader label="Reading the ledger" />;
  if (!data.ok) {
    return <PageNote>{data.offline ? `${data.offline.reason}.` : (data.error ?? "The wide read has not landed yet.")}</PageNote>;
  }
  const c = data.chips;
  const longs = data.rows.filter((r) => r.side === "long");
  const shorts = data.rows.filter((r) => r.side === "short");
  const summary = `${move}%+ · 1.5× volume · ${capWord(cap)}`;
  const refresh = () => {
    void load();
    onTrackChanged?.();
  };

  return (
    <div className="flex min-h-0 flex-1 flex-col">
      <div className="qt-stats flex shrink-0 flex-wrap items-stretch gap-x-2 gap-y-1 border-b border-ring px-2 py-2">
        <Card part glyph="check" hue="text-call-fig" value={c.day1} word="Strong Day 1" sub={`a ${move}%+ move on 1.5× volume`} />
        <Card part glyph="inside" hue="text-desk-macro" value={c.inside} word="Inside days" sub="building, not triggered" />
        <Card glyph="bolt" hue="text-flip-fig" value={c.through} word="Through PD" sub="over PDH or under PDL" />
        <div className="relative ml-auto flex items-center gap-1 rounded-[5px] border border-desk-macro/40 px-2 pt-1.5">
          <span className="qt-cap absolute -top-[6px] left-2 bg-bg px-1 text-[9px] text-desk-macro">Day stage</span>
          <Card part glyph="up" hue="text-ink" value={c.day2} word="Day 2" sub="first continuation day" />
          <Card glyph="arrow" hue="text-ink" value={c.day3} word="Day 3+" sub={c.day3 === 0 ? "fills in over the next sessions" : "extended move"} />
        </div>
      </div>
      <div className="qt-bar flex shrink-0 flex-wrap items-center gap-2 border-b border-ring px-4 py-2">
        <Chips items={CHIPS} on={chip} set={setChip} counts={c} />
        <div className="ml-auto flex items-center gap-2">
          <p className="fig text-[11px] text-ink-3">
            {data.basis === "last" ? `As of ${dayName(data.day)}` : "This session"} · {delayedLine(data.read_age_min, data.delayed_min)}
          </p>
          <Menu label={<>Filters · <span className="fig">{summary}</span></>}>
            <Choice label="Day 1 move" options={MOVES} value={move} set={setMove} />
            <Choice label="Market cap" options={CAPS} value={cap} set={setCap} />
          </Menu>
          <Showing shown={data.shown} total={data.matched !== data.shown ? data.matched : null} word="tracked" />
        </div>
      </div>
      <div className="qt-sheet min-h-0 flex-1 overflow-auto">
        {data.rows.length === 0 ? (
          <p className="px-6 py-10 text-center text-[12px] text-ink-3">No moves at these filters. The ledger keeps everything from 10% and $300m, so loosening them shows more straight away.</p>
        ) : (
          <table className="w-full min-w-[1320px] border-separate border-spacing-0 text-left">
            <thead className="sticky top-0 z-20">
              <tr>
                <th scope="col" className={cn(TH, "sticky left-0 z-30 w-[176px]")}><Head label="Ticker" hint="symbol · mkt cap" /></th>
                <th scope="col" className={TH}><Head label="Day" hint="of the move" /></th>
                <th scope="col" className={TH}><Head label="State" hint="what it has done" /></th>
                <th scope="col" className={TH} title="A rough order for this table, from where price stands against its level, the volume and the news. Not the Setups score: there is no record behind it."><Head label="Score ↓" hint="levels · volume · news" /></th>
                <th scope="col" className={TH}><Head label="Volume" hint="vs an average day" /></th>
                <th scope="col" className={TH}><Head label="Support" hint="vs yesterday's low · PDL" /></th>
                <th scope="col" className={TH}><Head label="Resistance" hint="vs yesterday's high · PDH" /></th>
                <th scope="col" className={TH}><Head label="News" hint="most important first" /></th>
                <th scope="col" className={cn(TH, "text-right")} title="Since Day 1's close"><Head label="Since" hint="cumulative · Day 1" right /></th>
                <th scope="col" className={TH} title={SPARK_TIP}><Head label="Spark" hint="from 04:00" /></th>
              </tr>
            </thead>
            <tbody>
              <Group side="long" rows={longs} ticker={ticker} onDone={refresh} />
              <Group side="short" rows={shorts} ticker={ticker} onDone={refresh} />
            </tbody>
          </table>
        )}
      </div>
    </div>
  );
}

function Group({ side, rows, ticker, onDone }: { side: Side; rows: Day23Row[]; ticker: string | null; onDone: () => void }) {
  if (rows.length === 0) return null;
  const inside = rows.filter((r) => r.kind === "inside").length;
  return (
    <>
      <tr>
        <td colSpan={10} className="border-b border-ring/60 bg-bg px-3 pt-3 pb-1.5">
          <span className={cn("qt-cap text-[10.5px] font-semibold", side === "long" ? "text-call-fig" : "text-put-fig")}>{side === "long" ? "Long side" : "Short side"}</span>
          <span className="fig ml-2 text-[11px] text-ink-3">{rows.length} names</span>
          {inside > 0 && (
            <span className="ml-2">
              <Tag tone="flat">{inside} inside day</Tag>
            </span>
          )}
        </td>
      </tr>
      {rows.map((r) => {
        const k = KIND[r.kind];
        const span = r.pdh - r.pdl;
        const pos = span > 0 ? Math.max(0, Math.min(1, (r.last - r.pdl) / span)) : 0.5;
        const toHigh = r.pdh ? (r.last / r.pdh - 1) * 100 : null;
        const toLow = r.pdl ? (r.last / r.pdl - 1) * 100 : null;
        const lean = pos >= 0.66 ? "Bullish" : pos <= 0.33 ? "Bearish" : "Neutral";
        return (
          <tr key={r.sym} {...rowProps(r.sym, ticker === r.sym)}>
            <td className={cn(TD, "sticky left-0 z-10 w-[176px]", ticker === r.sym ? "bg-surface-2" : "bg-bg group-hover:bg-surface")} style={edgeShadow(k.edge)}>
              <TickerCell
                sym={r.sym}
                name={r.name}
                price={`$${num(r.last)}`}
                sub={capShort(r.cap)}
                pinned={r.pinned}
                onPinned={onDone}
                tracked={r.tracked}
                onTrack={onDone}
              />
            </td>
            <td className={TD}>
              <StagePips stage={r.stage} />
              <p className="fig mt-1 flex items-center gap-1.5 text-[10.5px] text-ink-3">
                moved {dayShort(r.moved)} <span className={r.move >= 0 ? "up" : "down"}>{pctText(r.move, 1)}</span>
                {r.vx != null && <span>{r.vx.toFixed(1)}×</span>}
              </p>
            </td>
            <td className={cn(TD, "whitespace-nowrap")}>
              {r.stage <= 1 ? <Tag tone="news">Day 1</Tag> : <Tag tone={k.tone}>{k.word}</Tag>}
              <p className="mt-1 text-[11px] text-ink-3">{r.state}</p>
            </td>
            <td className={TD}>
              {r.score != null ? <ScoreBar v={r.score} of strong={80} fair={60} /> : <span className="text-ink-3">—</span>}
            </td>
            <td className={cn(TD, "fig leading-[1.3]")}>
              <p className="text-[12.5px] text-ink">{r.vol != null ? compact(r.vol) : "—"}</p>
              <p className={cn("text-[11px]", (r.adv_pct ?? 0) >= 100 ? "text-flip-fig" : "text-ink-3")}>{r.adv_pct != null ? `${Math.round(r.adv_pct)}% ADV` : ""}</p>
            </td>
            <td className={cn(TD, "fig leading-[1.3]")}>
              <p className="text-[12.5px] text-ink-2">${num(r.pdl)}</p>
              <p className="text-[11px] text-ink-3">{pctText(toLow, 1)}</p>
            </td>
            <td className={cn(TD, "fig min-w-[170px]")}>
              <p className="text-[12.5px] leading-none">
                <span className="text-ink-2">${num(r.pdh)}</span> <span className="text-[11px] text-ink-3">{pctText(toHigh, 1)}</span>
              </p>
              <div className="relative mt-[7px] h-[3px] rounded-full bg-[var(--qt-track,var(--ring))]">
                <span className="absolute inset-y-0 left-0 rounded-full bg-call-fig/70" style={{ width: `${pos * 100}%` }} />
                <span className="absolute top-1/2 h-[7px] w-[7px] -translate-x-1/2 -translate-y-1/2 rounded-full bg-call-fig" style={{ left: `${pos * 100}%` }} />
              </div>
              <p className={cn("mt-[5px] text-[10.5px]", lean === "Bullish" ? "text-call-fig" : lean === "Bearish" ? "text-put-fig" : "text-ink-3")}>
                {lean} <span className="text-ink-2">{Math.round(pos * 100)}%</span>
              </p>
            </td>
            <td className={TD}>
              <CatalystCell c={r.catalyst} width={360} />
            </td>
            <td className={cn(TD, "fig text-right text-[12.5px]", r.stage <= 1 ? "text-ink-3" : (r.since ?? 0) >= 0 ? "up" : "down")}>{r.stage <= 1 ? "—" : pctText(r.since)}</td>
            <td className={TD}>
              <Spark pts={r.spark} base={r.spark_ref} w={76} />
            </td>
          </tr>
        );
      })}
    </>
  );
}

/**
 * One count at the head of the page. `part` draws the short rule after it that parts
 * two figures on one card (`qt-part`, Luminous; globals.css), as a stat row's cells are
 * parted on the other pages; the extra padding puts the rule midway to the next figure.
 */
function Card({ glyph, hue, value, word, sub, part }: { glyph: string; hue: string; value: number; word: string; sub: string; part?: boolean }) {
  return (
    <div className={cn("flex items-center gap-2.5 px-2.5 py-1", part && "qt-part lum:pr-[18px]")}>
      <span className={cn("flex h-[28px] w-[28px] shrink-0 items-center justify-center rounded-[5px] border border-ring-2 bg-surface-2", hue)}>
        <Glyph name={glyph} size={13} />
      </span>
      <div className="min-w-0">
        <p className={cn("fig text-[15px] leading-none", hue)}>{value}</p>
        <p className="mt-[3px] text-[12px] leading-none font-semibold text-ink">{word}</p>
        <p className="mt-[3px] text-[10.5px] leading-none whitespace-nowrap text-ink-3 max-[1599px]:hidden">{sub}</p>
      </div>
    </div>
  );
}
