"use client";

import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import type { BreakoutChip, BreakoutsPayload } from "@/types/scanner";
import { HelmLoader } from "@/components/ui/HelmLoader";
import {
  CatalystCell,
  Chips,
  Choice,
  GroupHead,
  Menu,
  NameCell,
  RangeCell,
  Spark,
  TD,
  TH,
  TrackButton,
  VolCell,
  capWord,
  dayName,
  delayedLine,
  isNum,
  isStr,
  pctText,
  rowProps,
  useWalk,
  volWord,
} from "@/components/panels/ScanWide";
import { num } from "@/lib/format";
import { cn } from "@/lib/cn";
import { segItem } from "@/lib/seg";
import { useTicker } from "@/lib/ticker";
import { manyOf, oneOf, usePersisted } from "@/lib/usePersisted";

/**
 * Breakouts — every US stock against its levels, not forty.
 *
 * WHY (owner, 2026-11-09): "I always miss the big breakouts". The Scanner's table is
 * deep and narrow: forty names with signals, a score and options. This is wide and
 * shallow: the whole market off one screener read, asking one question, which names
 * are through the pre-market range AND the previous day's range the same way.
 *
 * FIFTEEN MINUTES BEHIND, AND IT SAYS SO, except for the few hundred best candidates
 * the live stream is watching, which move on their own trades. A name worth trading
 * goes on the list with Track, where it is read live and its signals fire.
 *
 * NEWS COMES BEFORE SIZE. Through both ranges first, then a fresh major story, then
 * relative volume: the signal log says news is what makes a move run. The Catalyst
 * column is the most important story of the last day, not the newest, which on a
 * big mover is nearly always an analyst's note written after it.
 *
 * NO SCORE. The 0-100 rank needs bars, and belongs to the tracked names.
 */

const CHIPS: ReadonlyArray<{ key: BreakoutChip; label: string; title?: string }> = [
  { key: "all", label: "All" },
  { key: "both", label: "Both ranges", title: "Through the pre-market range and the previous day's range, the same way" },
  { key: "news", label: "Has news", title: "A story about this name in the last thirty hours" },
  { key: "gaps", label: "Gaps", title: "Opened 2% or more away from the previous close" },
  { key: "through", label: "Through PDH / PDL" },
  { key: "inside", label: "Inside day", title: "The whole session inside the previous day's range" },
  { key: "day23", label: "Day 2/3", title: "Day 2 or later of a multi-day move" },
  { key: "pinned", label: "Pinned" },
];
const CAPS = [0, 3e8, 2e9, 5e9, 1e10].map((value) => ({ value, label: capWord(value) }));
const VOLS = [0, 1e5, 5e5, 1e6, 5e6].map((value) => ({ value, label: volWord(value) }));
const RVOLS = [0, 1, 1.5, 2, 5].map((value) => ({ value, label: value ? `${value}×+` : "Any" }));
const SECTORS = ["", "XLK", "XLC", "XLY", "XLP", "XLE", "XLF", "XLV", "XLI", "XLB", "XLRE", "XLU"].map((value) => ({
  value,
  label: value || "All",
}));
const COLS = ["catalyst", "move", "levels", "chart", "volume"] as const;
type Col = (typeof COLS)[number];
const COL_NAME: Record<Col, string> = { catalyst: "Catalyst", move: "Move", levels: "Levels", chart: "Chart", volume: "Volume" };
type Sort = "rank" | "rvol" | "chg" | "gap" | "vol";

const BASIS_WORD: Record<BreakoutsPayload["basis"], string> = {
  pre: "Pre-market",
  rth: "Regular session",
  post: "After hours",
  last: "Last session",
};

export function ScanBreakouts({ onTrackChanged }: { onTrackChanged?: () => void }) {
  const [chip, setChip] = usePersisted<BreakoutChip>("brk.chip", "both", oneOf("all", "both", "news", "gaps", "through", "inside", "day23", "pinned"));
  const [cap, setCap] = usePersisted<number>("brk.cap", 2e9, isNum);
  const [vol, setVol] = usePersisted<number>("brk.vol", 5e5, isNum);
  const [rvol, setRvol] = usePersisted<number>("brk.rvol", 2, isNum);
  const [sector, setSector] = usePersisted<string>("brk.sector", "", isStr);
  const [theme, setTheme] = usePersisted<string>("brk.theme", "", isStr);
  const [sort, setSort] = usePersisted<Sort>("brk.sort", "rank", oneOf("rank", "rvol", "chg", "gap", "vol"));
  const [cols, setCols] = usePersisted<Col[]>("brk.cols", [...COLS], manyOf(...COLS));
  const [data, setData] = useState<BreakoutsPayload | null>(null);
  const seq = useRef(0);
  const ticker = useTicker();

  const q = useMemo(() => {
    const p = new URLSearchParams({ chip, cap: String(cap), vol: String(vol), rvol: String(rvol), sort });
    if (sector) p.set("sector", sector);
    if (theme) p.set("theme", theme);
    return p.toString();
  }, [chip, cap, vol, rvol, sector, theme, sort]);

  const load = useCallback(async () => {
    const mine = ++seq.current;
    try {
      const r = await fetch(`/api/scanner/breakouts?${q}`, { cache: "no-store" });
      const d = (await r.json()) as BreakoutsPayload;
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

  const syms = useMemo(() => data?.rows.map((r) => r.sym) ?? [], [data]);
  useWalk(syms);

  if (!data) return <HelmLoader label="Reading the market" size={48} minHeight={420} />;
  if (!data.ok) {
    return (
      <p className="px-6 py-10 text-center text-[12px] text-ink-3">
        {data.offline ? `${data.offline.reason}.` : (data.error ?? "The wide read has not landed yet: it is one request, a few seconds after a start.")}
      </p>
    );
  }

  const has = (c: Col) => cols.includes(c);
  const toggle = (c: Col) => setCols((was) => (was.includes(c) ? was.filter((x) => x !== c) : [...was, c]));
  const summary = [capWord(cap), vol ? volWord(vol) : null, rvol ? `RVol ${rvol}×+` : null, sector || null, theme || null].filter(Boolean).join(" · ");
  const header = (k: Sort, label: string, title?: string) => (
    <button type="button" title={title} onClick={() => setSort(sort === k ? "rank" : k)} className={cn("qt-cap text-[10.5px] hover:text-ink-2", sort === k ? "text-ink" : "text-ink-3")}>
      {label}
      {sort === k ? " ↓" : ""}
    </button>
  );
  const groups: Array<{ label: string; span: number }> = [{ label: "", span: 1 }];
  if (has("catalyst")) groups.push({ label: "Catalyst", span: 1 });
  if (has("move")) groups.push({ label: "Move", span: 3 });
  if (has("levels")) groups.push({ label: "Levels", span: 2 });
  if (has("chart")) groups.push({ label: "Chart", span: 1 });
  if (has("volume")) groups.push({ label: "Volume", span: 1 });
  groups.push({ label: "", span: 1 });
  const s = data.stats;

  return (
    <div className="flex min-h-0 flex-1 flex-col">
      <div className="flex shrink-0 flex-wrap items-baseline gap-x-8 gap-y-1 border-b border-ring px-6 py-3">
        <Stat value={s.up} hue="text-call-fig" word={data.basis === "pre" ? "▲ above PDH" : "▲ above PMH and PDH"} />
        <Stat value={s.down} hue="text-put-fig" word={data.basis === "pre" ? "▼ below PDL" : "▼ below PML and PDL"} />
        <Stat value={s.top_rvol ? `${s.top_rvol.v.toFixed(1)}×` : "—"} word={s.top_rvol ? `top RVol · ${s.top_rvol.sym}` : "top RVol"} />
        <Stat value={s.top_move ? pctText(s.top_move.v, 1) : "—"} word={s.top_move ? `top mover · ${s.top_move.sym}` : "top mover"} />
        <p className="fig ml-auto text-[11px] text-ink-3" title={data.basis === "pre" ? "Before the open the pre-market range is still forming, so Both ranges reads the previous day's levels alone." : undefined}>
          {BASIS_WORD[data.basis]} · {dayName(data.day)} · {data.scanned.toLocaleString()} scanned · {delayedLine(data.read_age_min, data.delayed_min, s.live)}
        </p>
      </div>

      <div className="flex shrink-0 flex-wrap items-center gap-2 px-6 py-2.5">
        <Chips items={CHIPS} on={chip} set={setChip} counts={data.chips} />
        <div className="ml-auto flex items-center gap-2">
          <span className="fig text-[11px] text-ink-3">{data.shown === data.matched ? `${data.shown} showing` : `${data.shown} of ${data.matched}`}</span>
          <Menu label={<>Filters · <span className="fig">{summary}</span></>}>
            <Choice label="Market cap" options={CAPS} value={cap} set={setCap} />
            <Choice label="Volume" options={VOLS} value={vol} set={setVol} />
            <Choice label="Relative volume" options={RVOLS} value={rvol} set={setRvol} />
            <Choice label="Sector" options={SECTORS} value={sector} set={setSector} />
            <Choice label="Theme" options={[{ value: "", label: "All" }, ...data.themes.map((t) => ({ value: t.key, label: t.label }))]} value={theme} set={setTheme} />
            <button
              type="button"
              onClick={() => {
                setCap(2e9);
                setVol(5e5);
                setRvol(2);
                setSector("");
                setTheme("");
              }}
              {...segItem(false, { className: "self-start border border-ring-2" })}
            >
              Reset
            </button>
          </Menu>
          <Menu label="Columns" width={200}>
            <span className="seg flex-col items-stretch">
              {COLS.map((c) => (
                <button key={c} type="button" aria-pressed={has(c)} onClick={() => toggle(c)} {...segItem(has(c))}>
                  {COL_NAME[c]}
                </button>
              ))}
            </span>
          </Menu>
        </div>
      </div>

      <div className="min-h-0 flex-1 overflow-auto">
        {data.rows.length === 0 ? (
          <p className="px-6 py-10 text-center text-[12px] text-ink-3">
            Nothing here at these filters. {data.scanned.toLocaleString()} names scanned: try loosening relative volume or market cap.
          </p>
        ) : (
          <table className="w-full min-w-[1080px] border-separate border-spacing-0 text-left">
            <thead className="sticky top-0 z-20">
              <GroupHead groups={groups} />
              <tr>
                <th scope="col" className={cn(TH, "sticky left-0 z-30 w-[148px]")}>
                  Ticker
                </th>
                {has("catalyst") && <th scope="col" className={TH}>Most important story</th>}
                {has("move") && (
                  <>
                    <th scope="col" className={cn(TH, "text-right")}>{header("rvol", "RVol", "Against the 30-day average; by time of day in the session")}</th>
                    <th scope="col" className={cn(TH, "text-right")}>{header("chg", "Chg", "Against the previous close")}</th>
                    <th scope="col" className={cn(TH, "text-right")}>{header("gap", "Gap", "The open against the previous close")}</th>
                  </>
                )}
                {has("levels") && (
                  <>
                    <th scope="col" className={TH}>PM range</th>
                    <th scope="col" className={TH}>PD range</th>
                  </>
                )}
                {has("chart") && <th scope="col" className={TH}>Today</th>}
                {has("volume") && <th scope="col" className={cn(TH, "text-right")}>{header("vol", "Volume")}</th>}
                <th scope="col" className={TH} />
              </tr>
            </thead>
            <tbody>
              {data.rows.map((r) => (
                <tr key={r.sym} {...rowProps(r.sym, ticker === r.sym)}>
                  <td className={cn(TD, "sticky left-0 z-10", ticker === r.sym ? "bg-surface-2" : "bg-bg group-hover:bg-surface")}>
                    <NameCell
                      sym={r.sym}
                      side={r.both === "up" || (r.both === null && r.pd_state === "above") ? "long" : r.both === "down" || (r.both === null && r.pd_state === "below") ? "short" : null}
                      price={num(r.last)}
                      sub={
                        <>
                          {r.live && <span className="qt-cap ml-1.5 text-[9px] text-call-fig" title="Moving on the live stream">live</span>}
                          {(r.stage ?? 0) >= 2 && <span className="qt-cap ml-1.5 text-[9px] text-ink-2" title={`Day ${r.stage} of a multi-day move`}>day {r.stage}</span>}
                        </>
                      }
                    />
                  </td>
                  {has("catalyst") && (
                    <td className={TD}>
                      <CatalystCell c={r.catalyst} />
                    </td>
                  )}
                  {has("move") && (
                    <>
                      <td className={cn(TD, "fig text-right text-[12px]", (r.rvol ?? 0) >= 3 ? "text-ink" : "text-ink-2")}>{r.rvol != null ? `${r.rvol.toFixed(1)}×` : "—"}</td>
                      <td className={cn(TD, "fig text-right text-[12px]", (r.chg ?? 0) >= 0 ? "up" : "down")}>{pctText(r.chg)}</td>
                      <td className={cn(TD, "fig text-right text-[12px]", (r.gap ?? 0) >= 0 ? "up" : "down")}>{pctText(r.gap)}</td>
                    </>
                  )}
                  {has("levels") && (
                    <>
                      <td className={TD}>
                        <RangeCell state={r.pm_state} hi={r.pmh} lo={r.pml} hiName="PMH" loName="PML" />
                      </td>
                      <td className={TD}>
                        <RangeCell state={r.pd_state} hi={r.pdh} lo={r.pdl} hiName="PDH" loName="PDL" />
                      </td>
                    </>
                  )}
                  {has("chart") && (
                    <td className={TD}>
                      <Spark pts={r.spark} />
                    </td>
                  )}
                  {has("volume") && (
                    <td className={TD}>
                      <VolCell vol={r.vol} adv={r.adv_pct} />
                    </td>
                  )}
                  <td className={cn(TD, "text-right")}>
                    <TrackButton
                      sym={r.sym}
                      tracked={r.tracked}
                      onDone={() => {
                        void load();
                        onTrackChanged?.();
                      }}
                    />
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </div>
    </div>
  );
}

function Stat({ value, word, hue }: { value: number | string; word: string; hue?: string }) {
  return (
    <p className="flex items-baseline gap-2 whitespace-nowrap">
      <span className={cn("fig text-[17px] leading-none", hue ?? "text-ink")}>{value}</span>
      <span className="text-[11.5px] text-ink-3">{word}</span>
    </p>
  );
}
