"use client";

import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import type { BreakoutChip, BreakoutsPayload } from "@/types/scanner";
import { PageLoader, PageNote } from "@/components/ui/HelmLoader";
import {
  CatalystCell,
  Chips,
  Choice,
  Head,
  Menu,
  RangeCell,
  RvolBar,
  Showing,
  Spark,
  StatCard,
  TD,
  TH,
  TickerCell,
  TickerFilter,
  VolPct,
  capWord,
  dayName,
  delayedLine,
  isNum,
  isStr,
  pctText,
  rowProps,
  rowTags,
  volWord,
} from "@/components/panels/ScanWide";
import { num } from "@/lib/format";
import { cn } from "@/lib/cn";
import { OUTSIDE_DAY_TITLE, THROUGH_DAY_TITLE } from "@/lib/outsideDay";
import { segItem } from "@/lib/seg";
import { useTicker } from "@/lib/ticker";
import { manyOf, oneOf, usePersisted } from "@/lib/usePersisted";
import { usePinsChanged } from "@/lib/usePinsChanged";

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
 * relative volume: the signal log says news is what makes a move run. The News
 * column is the most important story of the last day, not the newest, which on a
 * big mover is nearly always an analyst's note written after it.
 *
 * NO SCORE. The 0-100 rank needs bars, and belongs to the tracked names.
 */

/*
 * SIX CHIPS (owner, 2026-11-13: "streamline the app and make it have the most useful
 * informaiton visible without clutter and noise", after asking whether the pills were
 * redundant). Two went. "Pinned" listed the names already on the Setups table, where
 * they are read live with a score, on the one page built to find names that are NOT on
 * it (6 of 36 rows when it was counted). "Day 2/3" is the tab beside this one. The
 * collector still answers both keys, and the Sectors tab still offers them.
 */
const CHIPS: ReadonlyArray<{ key: BreakoutChip; label: string; title?: string }> = [
  { key: "all", label: "All" },
  { key: "news", label: "Has News", title: "A story about this name in the last thirty hours" },
  { key: "gaps", label: "Gaps", title: "Opened 2% or more away from the previous close" },
  // `both` is an OUTSIDE DAY (owner, 2026-11-13: above both highs or below both lows).
  // It read "Both ranges" and the chip after it, the previous day's level alone, was
  // the one called "Outside day". The keys are what the collector knows them by.
  { key: "both", label: "Outside Day", title: OUTSIDE_DAY_TITLE },
  { key: "through", label: "Through PDH/PDL", title: THROUGH_DAY_TITLE },
  { key: "inside", label: "Inside Day", title: "The whole session inside the previous day's range" },
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
const COL_NAME: Record<Col, string> = { catalyst: "News", move: "Move", levels: "Levels", chart: "Chart", volume: "Volume" };
type Sort = "rank" | "rvol" | "chg" | "gap" | "vol";

const BASIS_WORD: Record<BreakoutsPayload["basis"], string> = {
  pre: "Pre-market",
  rth: "Regular session",
  post: "After hours",
  last: "Last session",
};

export function ScanBreakouts({ onTrackChanged }: { onTrackChanged?: () => void }) {
  const [chip, setChip] = usePersisted<BreakoutChip>("brk.chip", "both", oneOf("all", "both", "news", "gaps", "through", "inside"));
  const [cap, setCap] = usePersisted<number>("brk.cap", 2e9, isNum);
  const [vol, setVol] = usePersisted<number>("brk.vol", 5e5, isNum);
  const [rvol, setRvol] = usePersisted<number>("brk.rvol", 2, isNum);
  const [sector, setSector] = usePersisted<string>("brk.sector", "", isStr);
  const [theme, setTheme] = usePersisted<string>("brk.theme", "", isStr);
  const [sort, setSort] = usePersisted<Sort>("brk.sort", "rank", oneOf("rank", "rvol", "chg", "gap", "vol"));
  const [cols, setCols] = usePersisted<Col[]>("brk.cols", [...COLS], manyOf(...COLS));
  const [find, setFind] = useState("");
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
  // A star elsewhere, or the Undo on the unpin notice, changed the list: read it again.
  usePinsChanged(load);

  const on = data?.ok ? data.basis !== "last" : false;
  useEffect(() => {
    void load();
    const id = setInterval(load, on ? 5000 : 60_000);
    return () => clearInterval(id);
  }, [load, on]);

  const typed = find.trim().toUpperCase();
  const rows = useMemo(() => (data?.rows ?? []).filter((r) => !typed || r.sym.includes(typed)), [data, typed]);
  // A card where the view will be, not the helm on the ground (ui/HelmLoader PageLoader).
  if (!data) return <PageLoader label="Reading the market" />;
  if (!data.ok) {
    return (
      <PageNote>
        {data.offline ? `${data.offline.reason}.` : (data.error ?? "The wide read has not landed yet: it is one request, a few seconds after a start.")}
      </PageNote>
    );
  }

  const has = (c: Col) => cols.includes(c);
  const toggle = (c: Col) => setCols((was) => (was.includes(c) ? was.filter((x) => x !== c) : [...was, c]));
  const summary = [capWord(cap), vol ? volWord(vol) : null, rvol ? `RVol ${rvol}×+` : null, sector || null, theme || null].filter(Boolean).join(" · ");
  const header = (k: Sort, label: string, hint: string, title?: string, right?: boolean) => (
    <button type="button" title={title} onClick={() => setSort(sort === k ? "rank" : k)} className={cn("qt-cap text-[10.5px] hover:text-ink-2", sort === k ? "text-ink" : "text-ink-3")}>
      <Head label={`${label}${sort === k ? " ↓" : ""}`} hint={hint} right={right} />
    </button>
  );
  const s = data.stats;
  const refreshed = () => {
    void load();
    onTrackChanged?.();
  };

  return (
    <div className="flex min-h-0 flex-1 flex-col">
      <div className="qt-stats flex shrink-0 flex-wrap items-stretch border-b border-ring">
        <StatCard glyph="up" tint="up" value={s.up} hue="text-call-fig" label="Bullish" sub={data.basis === "pre" ? "above PDH" : `above PMH and PDH · ${s.pdh} above PDH`} />
        <StatCard glyph="down" tint="down" value={s.down} hue="text-put-fig" label="Bearish" sub={data.basis === "pre" ? "below PDL" : `below PML and PDL · ${s.pdl} below PDL`} />
        <StatCard glyph="pulse" tint="news" value={s.top_rvol ? `${s.top_rvol.v.toFixed(1)}×` : "—"} hue="text-desk-markets" label="Top RVol" sub={s.top_rvol?.sym} />
        <StatCard glyph="star" tint="move" value={s.top_move ? pctText(s.top_move.v, 2) : "—"} hue="text-desk-policy" label="Top mover" sub={s.top_move?.sym} />
      </div>

      <div className="qt-bar flex shrink-0 flex-wrap items-center gap-2 border-b border-ring px-4 py-2">
        <Chips items={CHIPS} on={chip} set={setChip} counts={data.chips} />
        <div className="ml-auto flex items-center gap-2">
          {/* What the read is and how old, in the bar with the table's other facts, where
              Day 2/3 has it (owner, 2026-11-11: it was a loose line at the end of the
              stat tiles, and "sticks out"). */}
          <p className="fig text-[11px] whitespace-nowrap text-ink-3" title={data.basis === "pre" ? "Before the open the pre-market range is still forming, so Outside day reads the previous day's levels alone." : undefined}>
            {BASIS_WORD[data.basis]} · {dayName(data.day)} · {delayedLine(data.read_age_min, data.delayed_min, s.live)}
          </p>
          <TickerFilter value={find} onChange={setFind} />
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
          <Showing shown={rows.length} total={data.scanned} word="scanned" />
        </div>
      </div>

      <div className="qt-sheet min-h-0 flex-1 overflow-auto">
        {rows.length === 0 ? (
          <p className="px-6 py-10 text-center text-[12px] text-ink-3">
            Nothing here at these filters. {data.scanned.toLocaleString()} names scanned: try loosening relative volume or market cap.
          </p>
        ) : (
          <table className="w-full min-w-[1180px] border-separate border-spacing-0 text-left">
            <thead className="sticky top-0 z-20">
              <tr>
                <th scope="col" className={cn(TH, "sticky left-0 z-30 w-[226px]")}>
                  <Head label="Ticker" hint="symbol · price" />
                </th>
                {has("catalyst") && <th scope="col" className={TH}><Head label="News" hint="most important first" /></th>}
                {has("move") && (
                  <>
                    <th scope="col" className={TH}>
                      {data.basis === "rth"
                        ? header("rvol", "RVol", "vs usual by now", "Volume so far against the same time of day on recent sessions: for a name on the Stocks list its own figure, so it reads the same on every page; for the rest TradingView's, fifteen minutes behind")
                        : data.basis === "pre"
                          ? header("rvol", "RVol", "pre-mkt vs usual", "The pre-market's volume against this name's usual pre-market: the Extended hours figure (until five mornings are kept, a fifth of its share of an average day). A day's RVol starts at the open.")
                          : header("rvol", "RVol", "day vs 30-day avg", "The session's whole volume against the 30-day average day: the same figure as the Volume column's share of an average day. In the session it is read by time of day instead.")}
                    </th>
                    <th scope="col" className={cn(TH, "text-right")}>{header("chg", "Chg", "vs prev close", "Against the previous close", true)}</th>
                    <th scope="col" className={cn(TH, "text-right")}>{header("gap", "Gap", "open vs prev close", "The open against the previous close", true)}</th>
                  </>
                )}
                {has("levels") && (
                  <>
                    <th scope="col" className={TH}><Head label="PM range" hint="locks at 09:30" /></th>
                    <th scope="col" className={TH}><Head label="PD range" hint="vs PDH / PDL" /></th>
                  </>
                )}
                {has("chart") && <th scope="col" className={TH}><Head label="Spark" hint="today" /></th>}
                {has("volume") && <th scope="col" className={TH}>{header("vol", "Volume", "vs ADV")}</th>}
              </tr>
            </thead>
            <tbody>
              {rows.map((r) => (
                <tr key={r.sym} {...rowProps(r.sym, ticker === r.sym)}>
                  <td className={cn(TD, "sticky left-0 z-10 w-[226px]", ticker === r.sym ? "bg-surface-2" : "bg-bg group-hover:bg-surface")}>
                    <TickerCell
                      sym={r.sym}
                      name={r.name}
                      price={`$${num(r.last)}`}
                      tags={rowTags({ pd: r.pd_state, pm: r.pm_state, inside: r.inside, news: r.catalyst != null, stage: r.stage, verdict: r.verdict })}
                      pinned={r.pinned}
                      onPinned={refreshed}
                      tracked={r.tracked}
                      onTrack={refreshed}
                    />
                  </td>
                  {has("catalyst") && (
                    <td className={TD}>
                      <CatalystCell c={r.catalyst} />
                    </td>
                  )}
                  {has("move") && (
                    <>
                      <td className={TD}>
                        <RvolBar v={r.rvol} />
                      </td>
                      <td className={cn(TD, "fig text-right text-[12.5px]", (r.chg ?? 0) >= 0 ? "up" : "down")}>{pctText(r.chg)}</td>
                      <td className={cn(TD, "fig text-right text-[12.5px]", (r.gap ?? 0) >= 0 ? "up" : "down")}>{pctText(r.gap)}</td>
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
                      <VolPct vol={r.vol} adv={r.adv_pct} />
                    </td>
                  )}
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </div>
    </div>
  );
}
