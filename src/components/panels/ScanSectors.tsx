"use client";

import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import type { BreakoutChip, BreakoutsPayload } from "@/types/scanner";
import type { HeatCard, HeatIndustry, HeatSpan, HeatmapPayload } from "@/types/dashboard";
import { HelmLoader, PageLoader, PageNote } from "@/components/ui/HelmLoader";
import { TickerLogo } from "@/components/ui/TickerLogo";
import { SectorGlyph } from "@/components/ui/SectorGlyph";
import {
  CatalystCell,
  Chips,
  Choice,
  Menu,
  RangeCell,
  Spark,
  TD,
  TH,
  TrackButton,
  capWord,
  dayName,
  delayedLine,
  isNum,
  isStr,
  pctText,
  rowProps,
  volWord,
} from "@/components/panels/ScanWide";
import { cn } from "@/lib/cn";
import { OUTSIDE_DAY_TITLE } from "@/lib/outsideDay";
import { compact, dir, num, pct } from "@/lib/format";
import { heatMax, heatStyle } from "@/lib/heat";
import { segItem } from "@/lib/seg";
import { useTicker } from "@/lib/ticker";
import { manyOf, oneOf, usePersisted } from "@/lib/usePersisted";
import { usePinsChanged } from "@/lib/usePinsChanged";

/**
 * Sectors: where the money is, and the stocks in it.
 *
 * WHY (owner, 2026-11-09: "a Sector heatmeap area", "way more sectors", "follow the
 * layout a bit closer"). The screenshots' page, top to bottom: the top mover beside the
 * ranked cards, the themes under them, how many names are through the day's levels,
 * the sector and theme strips, and the stocks.
 *
 * NO ROTATION SCORE. The screenshots' bar is a score whose recipe nobody here can
 * read. This bar is the distance from SPY, the same excess return Macro's table ranks.
 *
 * UP AND DOWN COUNT THE STOCKS, because an ETF can hide them: XLV closed -0.06% on
 * 2026-11-06 with 157 of its names up and 83 down. They come off the 15-minute screener,
 * and until the open the cards read the last session, as the ETFs do.
 *
 * INDUSTRIES are the owner's "way more": TradingView's groups with five or more names
 * at $2bn+, ninety-odd of them, ranked by the median stock so that one 40% name cannot
 * carry a group the way it carries an average.
 *
 * THE TABLE LISTS A GROUP AT ANY HOUR, as the screenshots' does. Its volume filter reads
 * the last whole session (universe.last_session_volume): on the pre-market's own volume,
 * Technology showed 3 of its 321 names at 06:19 ET.
 */

const SECTORS: ReadonlySet<string> = new Set(["XLK", "XLC", "XLY", "XLP", "XLE", "XLF", "XLV", "XLI", "XLB", "XLRE", "XLU"]);
const SPANS: ReadonlyArray<{ key: HeatSpan; label: string; word: string }> = [
  { key: "day", label: "1D", word: "the day" },
  { key: "week", label: "1W", word: "the week" },
  { key: "month", label: "1M", word: "the month" },
];
const CHIPS: ReadonlyArray<{ key: BreakoutChip; label: string; title?: string }> = [
  { key: "all", label: "All" },
  // The collector's `both`: an outside day, as on Breakouts (lib/outsideDay).
  { key: "both", label: "Outside day", title: OUTSIDE_DAY_TITLE },
  { key: "news", label: "Has news", title: "A story about this name in the last thirty hours" },
  { key: "gaps", label: "Gaps", title: "Opened 2% or more away from the previous close" },
  { key: "inside", label: "Inside day", title: "The whole session inside the previous day's range" },
  { key: "day23", label: "Day 2/3", title: "Day 2 or later of a multi-day move" },
];
const CAPS = [0, 3e8, 2e9, 5e9, 1e10].map((value) => ({ value, label: capWord(value) }));
const VOLS = [0, 1e5, 5e5, 1e6, 5e6].map((value) => ({ value, label: volWord(value) }));
const COLS = ["themes", "momentum", "volume", "levels", "news", "chart"] as const;
type Col = (typeof COLS)[number];
const COL_NAME: Record<Col, string> = { themes: "Themes", momentum: "Momentum", volume: "Volume", levels: "Levels", news: "News", chart: "Chart" };
type Sort = "rank" | "rvol" | "chg" | "gap" | "vol";

/** The stocks of a sector or theme: which request lists them. */
function groupParam(sel: string): [string, string] | null {
  if (!sel) return null;
  if (sel.startsWith("i:")) return ["industry", sel.slice(2)];
  return [SECTORS.has(sel) ? "sector" : "theme", sel];
}

export function ScanSectors({ onTrackChanged }: { onTrackChanged?: () => void }) {
  const [mode, setMode] = usePersisted<"cards" | "industries">("sec.mode", "cards", oneOf("cards", "industries"));
  const [span, setSpan] = usePersisted<HeatSpan>("sec.span", "day", oneOf("day", "week", "month"));
  /** "" is everything; an ETF's key; "i:" and an industry's name. */
  const [sel, setSel] = usePersisted<string>("sec.sel", "", isStr);
  const [chip, setChip] = usePersisted<BreakoutChip>("sec.chip", "all", oneOf("all", "both", "news", "gaps", "through", "inside", "day23", "pinned"));
  const [cap, setCap] = usePersisted<number>("sec.cap", 2e9, isNum);
  const [vol, setVol] = usePersisted<number>("sec.vol", 5e5, isNum);
  const [sort, setSort] = usePersisted<Sort>("sec.sort", "chg", oneOf("rank", "rvol", "chg", "gap", "vol"));
  const [cols, setCols] = usePersisted<Col[]>("sec.cols", [...COLS], manyOf(...COLS));
  const [heat, setHeat] = useState<HeatmapPayload | null>(null);
  const [table, setTable] = useState<BreakoutsPayload | null>(null);
  const seq = useRef(0);
  const ticker = useTicker();

  const loadHeat = useCallback(async () => {
    try {
      const r = await fetch("/api/scanner/sectors", { cache: "no-store" });
      setHeat((await r.json()) as HeatmapPayload);
    } catch {
      /* the last read stays on screen */
    }
  }, []);

  const q = useMemo(() => {
    const p = new URLSearchParams({ chip, cap: String(cap), vol: String(vol), rvol: "0", sort, listing: "1" });
    const g = groupParam(sel);
    if (g) p.set(g[0], g[1]);
    return p.toString();
  }, [chip, cap, vol, sort, sel]);

  const loadTable = useCallback(async () => {
    const mine = ++seq.current;
    try {
      const r = await fetch(`/api/scanner/breakouts?${q}`, { cache: "no-store" });
      const d = (await r.json()) as BreakoutsPayload;
      if (mine === seq.current) setTable(d);
    } catch {
      /* the last read stays on screen */
    }
  }, [q]);
  // A star elsewhere, or the Undo on the unpin notice, changed the list: read it again.
  usePinsChanged(loadTable);

  const on = heat?.ok ? heat.basis !== "last" : false;
  useEffect(() => {
    void loadHeat();
    const id = setInterval(loadHeat, on ? 20_000 : 60_000);
    return () => clearInterval(id);
  }, [loadHeat, on]);
  useEffect(() => {
    void loadTable();
    const id = setInterval(loadTable, on ? 5000 : 60_000);
    return () => clearInterval(id);
  }, [loadTable, on]);

  const pctOf = useCallback((c: HeatCard) => c[`${span}_pct` as const], [span]);
  const rsOf = useCallback((c: HeatCard) => c[`rs_${span}` as const], [span]);
  const { top, themes, tint, barMax } = useMemo(() => {
    const cards = heat?.cards ?? [];
    const best = (a: HeatCard, b: HeatCard) => (pctOf(b) ?? -Infinity) - (pctOf(a) ?? -Infinity);
    return {
      top: cards.filter((c) => c.top).sort(best),
      themes: cards.filter((c) => !c.top).sort(best),
      tint: heatMax(cards.map(pctOf)),
      barMax: heatMax(cards.map(rsOf)),
    };
  }, [heat, pctOf, rsOf]);

  // A card where the page will be, not the helm on the ground (ui/HelmLoader PageLoader).
  if (!heat) return <PageLoader label="Reading the sectors" />;
  if (!heat.ok) {
    return (
      <PageNote>
        {heat.offline ? `${heat.offline.reason}.` : (heat.error ?? "The wide read has not landed yet: it is one request, a few seconds after a start.")}
      </PageNote>
    );
  }

  const spy = heat.spy[span];
  const spanWord = SPANS.find((s) => s.key === span)?.word ?? "the day";
  const pick = (k: string) => setSel(sel === k ? "" : k);
  const cardOf = (k: string) => heat.cards.find((c) => c.key === k) ?? null;
  const selCard = sel && !sel.startsWith("i:") ? cardOf(sel) : null;
  const parent = selCard ? (selCard.kind === "sector" ? selCard.key : selCard.parent) : null;
  const parentCard = parent ? cardOf(parent) : null;
  // Regional banks rank with the sectors but are still a theme under Financials.
  const kids = parent ? [...top, ...themes].filter((c) => c.kind === "theme" && c.parent === parent) : [];
  const global = themes.filter((t) => t.parent === null);
  const sectorStrip = top.filter((c) => c.kind === "sector");
  const leader = top[0];
  const listNote =
    selCard?.list === "fund"
      ? `A partial list: Yahoo publishes only ${selCard.key}'s top ten holdings.`
      : selCard?.list === "hand"
        ? `A hand-written list of US-listed names that trade with ${selCard.label}, not ${selCard.key}'s own holdings.`
        : null;

  const has = (c: Col) => cols.includes(c);
  const toggle = (c: Col) => setCols((was) => (was.includes(c) ? was.filter((x) => x !== c) : [...was, c]));
  const header = (k: Sort, label: string, title?: string) => (
    <button type="button" title={title} onClick={() => setSort(sort === k ? "rank" : k)} className={cn("qt-cap text-[10.5px] hover:text-ink-2", sort === k ? "text-ink" : "text-ink-3")}>
      {label}
      {sort === k ? " ↓" : ""}
    </button>
  );
  const summary = [capWord(cap), vol ? volWord(vol) : null].filter(Boolean).join(" · ");
  const inds = [...heat.industries].sort((a, b) => (b[span].median ?? -Infinity) - (a[span].median ?? -Infinity));

  return (
    <div className="qt-sheet min-h-0 flex-1 overflow-auto">
      <div className="flex flex-wrap items-center gap-3 px-4 pt-3 pb-2">
        <span className="seg">
          <button type="button" onClick={() => setMode("cards")} {...segItem(mode === "cards")}>
            Sectors &amp; themes<span className="seg-n">{heat.cards.length}</span>
          </button>
          <button type="button" onClick={() => setMode("industries")} {...segItem(mode === "industries")}>
            Industries<span className="seg-n">{heat.industries.length}</span>
          </button>
        </span>
        <span className="seg">
          {SPANS.map((s) => (
            <button key={s.key} type="button" onClick={() => setSpan(s.key)} {...segItem(span === s.key)}>
              {s.label}
            </button>
          ))}
        </span>
        <p className="fig ml-auto text-[11px] text-ink-3" title="Until the open, the cards read the last regular session, as the ETFs do; the table below reads the pre-market">
          Cards read {dayName(heat.cards_day)} · {delayedLine(heat.read_age_min, heat.delayed_min)}
        </p>
      </div>

      <div className="px-4">
        {mode === "cards" ? (
          <div className={GRID}>
            {leader && <TopMover c={leader} span={span} word={spanWord} pctOf={pctOf} rsOf={rsOf} tint={tint} on={sel === leader.key} onPick={pick} />}
            {top.slice(1).map((c, i) => (
              <Card key={c.key} c={c} rank={i + 2} span={span} pctOf={pctOf} rsOf={rsOf} tint={tint} barMax={barMax} on={sel === c.key} onPick={pick} />
            ))}
            {themes.map((c) => (
              <Card key={c.key} c={c} span={span} pctOf={pctOf} rsOf={rsOf} tint={tint} barMax={barMax} on={sel === c.key} onPick={pick} />
            ))}
          </div>
        ) : (
          <div className={GRID}>
            {inds.map((g) => (
              <IndustryCard key={g.key} g={g} span={span} spy={spy} tint={heatMax(inds.map((i) => i[span].median))} barMax={heatMax(inds.map((i) => (i[span].median == null || spy == null ? null : (i[span].median as number) - spy)))} on={sel === `i:${g.key}`} onPick={() => pick(`i:${g.key}`)} />
            ))}
          </div>
        )}
        <p className="fig mt-2 text-right text-[10.5px] text-ink-3">
          {mode === "cards" ? `Ranked by ${spanWord}'s change. ` : `Ranked by the median stock over ${spanWord}. `}
          The bar under each card is its distance from SPY ({pct(spy)}); up and down count its stocks at {capWord(heat.floor).replace("+", "")} and over. Click a card to filter.
        </p>
      </div>

      {table?.ok && (
        <div className="qt-tally mx-4 mt-2 grid grid-cols-2 divide-x divide-ring rounded-[6px] border border-ring bg-surface/40 qt:rounded-[4px]">
          <Tally value={table.stats.pdh} hue="text-call-fig" glyph="▲" word="Advancing" sub="Above PDH" />
          <Tally value={table.stats.pdl} hue="text-put-fig" glyph="▼" word="Declining" sub="Below PDL" />
        </div>
      )}

      <div className="flex flex-wrap items-center gap-2 px-4 pt-3">
        <span className="seg flex-wrap">
          <button type="button" onClick={() => setSel("")} {...segItem(sel === "")}>
            All <span className={cn("fig ml-1", dir(spy))}>{pct(spy)}</span>
          </button>
          {sectorStrip.map((c) => (
            <button key={c.key} type="button" title={c.label} onClick={() => setSel(c.key)} {...segItem(parent === c.key)}>
              {c.key} <span className={cn("fig ml-1", dir(pctOf(c)))}>{pct(pctOf(c))}</span>
            </button>
          ))}
        </span>
        {global.length > 0 && (
          <Menu label={<>Global{selCard && selCard.parent === null && selCard.kind === "theme" ? ` · ${selCard.key}` : ""} ▾</>} width={240}>
            <span className="seg flex-col items-stretch">
              {global.map((c) => (
                <button key={c.key} type="button" onClick={() => setSel(c.key)} {...segItem(sel === c.key)}>
                  {c.key} · {c.label} <span className={cn("fig ml-1", dir(pctOf(c)))}>{pct(pctOf(c))}</span>
                </button>
              ))}
            </span>
          </Menu>
        )}
        <div className="ml-auto flex items-center gap-2">
          {table?.ok && <span className="fig text-[11px] text-ink-3">{table.shown === table.matched ? table.shown : `${table.shown} of ${table.matched}`} showing · {table.scanned.toLocaleString()} scanned</span>}
          <Menu label={<>Filters · <span className="fig">{summary}</span></>}>
            <Choice label="Market cap" options={CAPS} value={cap} set={setCap} />
            <Choice label="Last session's volume" options={VOLS} value={vol} set={setVol} />
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

      <div className="flex flex-wrap items-center gap-2 px-4 pt-2 pb-2">
        {parentCard && kids.length > 0 && (
          <>
            <span className="qt-cap text-[10px] text-ink-3">Themes</span>
            <span className="seg flex-wrap">
              <button type="button" onClick={() => setSel(parentCard.key)} {...segItem(sel === parentCard.key)}>
                All {parentCard.label} <span className={cn("fig ml-1", dir(pctOf(parentCard)))}>{pct(pctOf(parentCard))}</span>
              </button>
              {kids.map((t) => (
                <button key={t.key} type="button" onClick={() => setSel(t.key)} {...segItem(sel === t.key)}>
                  {t.key} · {t.label} <span className={cn("fig ml-1", dir(pctOf(t)))}>{pct(pctOf(t))}</span>
                </button>
              ))}
            </span>
          </>
        )}
        {sel.startsWith("i:") && (
          <span className="flex items-center gap-2 text-[12px] text-ink-2">
            <span className="qt-cap text-[10px] text-ink-3">Industry</span>
            {sel.slice(2)}
          </span>
        )}
        {table?.ok && (
          <span className="ml-auto">
            <Chips items={CHIPS} on={chip} set={setChip} counts={table.chips} />
          </span>
        )}
      </div>

      {listNote && <p className="px-4 pb-2 text-[11.5px] text-ink-3">{listNote}</p>}

      {!table ? (
        <HelmLoader label="Listing the stocks" size={36} minHeight={200} />
      ) : !table.ok ? (
        <p className="px-6 py-10 text-center text-[12px] text-ink-3">{table.offline ? `${table.offline.reason}.` : table.error}</p>
      ) : table.rows.length === 0 ? (
        <p className="px-6 py-10 text-center text-[12px] text-ink-3">No stocks here at these filters. Try loosening volume or market cap.</p>
      ) : (
        <table className="w-full min-w-[1360px] border-separate border-spacing-0 text-left">
          <thead className="sticky top-0 z-20">
            <tr>
              <th scope="col" className={cn(TH, "sticky left-0 z-30 w-[220px]")}>Ticker</th>
              {has("themes") && <th scope="col" className={TH}>Themes</th>}
              {has("momentum") && (
                <>
                  <th scope="col" className={cn(TH, "text-right")}>{header("rvol", "RVol", "Against the 30-day average; by time of day in the session; before the bell, the pre-market against its usual pre-market")}</th>
                  <th scope="col" className={cn(TH, "text-right")}>{header("chg", "% Chg", "Against the previous close")}</th>
                  <th scope="col" className={cn(TH, "text-right")}>{header("gap", "Gap", "The open against the previous close")}</th>
                  <th scope="col" className={cn(TH, "text-right")} title="The past week, as TradingView's screener counts it">1W</th>
                </>
              )}
              {has("volume") && (
                <>
                  <th scope="col" className={cn(TH, "text-right")}>{header("vol", "Vol")}</th>
                  <th scope="col" className={cn(TH, "text-right")} title="Against the 30-day average day">% ADV</th>
                </>
              )}
              {has("levels") && (
                <>
                  <th scope="col" className={TH}>PM range</th>
                  <th scope="col" className={TH}>PD range</th>
                </>
              )}
              {has("news") && <th scope="col" className={TH}>Headline</th>}
              {has("chart") && <th scope="col" className={TH}>Spark</th>}
              <th scope="col" className={TH} />
            </tr>
          </thead>
          <tbody>
            {table.rows.map((r) => (
              <tr key={r.sym} {...rowProps(r.sym, ticker === r.sym)}>
                <td className={cn(TD, "sticky left-0 z-10", ticker === r.sym ? "bg-surface-2" : "bg-bg group-hover:bg-surface")}>
                  <div className="flex items-center gap-1.5 whitespace-nowrap">
                    <span className={cn("w-[10px] text-[11px]", r.pd_state === "above" ? "text-call-fig" : r.pd_state === "below" ? "text-put-fig" : "text-ink-3")}>
                      {r.pd_state === "above" ? "▲" : r.pd_state === "below" ? "▼" : "·"}
                    </span>
                    <TickerLogo sym={r.sym} size={18} />
                    <div className="min-w-0 leading-[1.25]">
                      <p className="text-[13px]">
                        <span className="font-semibold text-ink">{r.sym}</span>
                        <span className="fig ml-1.5 text-[12px] text-ink-2">{num(r.last)}</span>
                        <span className={cn("fig ml-1.5 text-[12px]", dir(r.chg))}>{pctText(r.chg)}</span>
                      </p>
                      <p className="text-[10px] text-ink-3">
                        {[r.inside ? "Inside day" : null, r.catalyst ? "News" : null, (r.stage ?? 0) >= 2 ? `Day ${r.stage}` : null, r.live ? "Live" : null].filter(Boolean).join(" · ") || " "}
                      </p>
                    </div>
                  </div>
                </td>
                {has("themes") && (
                  <td className={TD}>
                    <ThemeChips keys={r.themes} />
                  </td>
                )}
                {has("momentum") && (
                  <>
                    <td className={cn(TD, "fig text-right text-[12px]", (r.rvol ?? 0) >= 3 ? "text-ink" : "text-ink-2")}>{r.rvol != null ? `${r.rvol.toFixed(1)}×` : "—"}</td>
                    <td className={cn(TD, "fig text-right text-[12px]", dir(r.chg))}>{pctText(r.chg)}</td>
                    <td className={cn(TD, "fig text-right text-[12px]", dir(r.gap))}>{pctText(r.gap)}</td>
                    <td className={cn(TD, "fig text-right text-[12px]", dir(r.week))}>{pctText(r.week, 1)}</td>
                  </>
                )}
                {has("volume") && (
                  <>
                    <td className={cn(TD, "fig text-right text-[12px] text-ink-2")}>{r.vol != null ? compact(r.vol) : "—"}</td>
                    <td className={cn(TD, "fig text-right text-[12px]", (r.adv_pct ?? 0) >= 200 ? "text-ink" : "text-ink-3")}>{r.adv_pct != null ? `${Math.round(r.adv_pct)}%` : "—"}</td>
                  </>
                )}
                {has("levels") && (
                  <>
                    <td className={TD}><RangeCell state={r.pm_state} hi={r.pmh} lo={r.pml} hiName="PMH" loName="PML" /></td>
                    <td className={TD}><RangeCell state={r.pd_state} hi={r.pdh} lo={r.pdl} hiName="PDH" loName="PDL" /></td>
                  </>
                )}
                {has("news") && (
                  <td className={TD}>{r.catalyst ? <CatalystCell c={r.catalyst} width={380} /> : <span className="text-[11.5px] text-ink-3">No news</span>}</td>
                )}
                {has("chart") && <td className={TD}><Spark pts={r.spark} /></td>}
                <td className={cn(TD, "text-right")}>
                  <TrackButton
                    sym={r.sym}
                    tracked={r.tracked}
                    onDone={() => {
                      void loadTable();
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
  );
}

/* -------------------------------------------------------------------------- */
/* The cards                                                                   */
/* -------------------------------------------------------------------------- */

/*
 * 137.5rem is 2200px. In rem because Tailwind sorts a breakpoint by its unit first: a
 * px one lands before every named (rem) one, and xl: would beat it at any width.
 */
const GRID = "grid grid-cols-2 gap-2 md:grid-cols-3 xl:grid-cols-5 min-[137.5rem]:grid-cols-7";
const CARD_BOX = "hit min-w-0 rounded-[6px] border px-3 py-2.5 text-left qt:rounded-[4px]";

interface CardBase {
  span: HeatSpan;
  pctOf: (c: HeatCard) => number | null;
  rsOf: (c: HeatCard) => number | null;
  tint: number;
  on: boolean;
  onPick: (key: string) => void;
}

function Counts({ up, down }: { up: number; down: number }) {
  return (
    <span className="fig text-[10.5px] whitespace-nowrap" title="Its stocks at $2bn+ that rose and fell">
      <span className="up">{up}↑</span> <span className="down">{down}↓</span>
    </span>
  );
}

function SpyBar({ v, max }: { v: number | null; max: number }) {
  const w = v == null ? 0 : Math.min(100, (Math.abs(v) / max) * 100);
  return (
    <div className="mt-1.5 flex items-center gap-2" title="Its distance from SPY over this span">
      <span className="relative h-[3px] flex-1 rounded-full bg-[var(--qt-track,var(--ring))]">
        <span className="absolute inset-y-0 left-0 rounded-full" style={{ width: `${w}%`, background: (v ?? 0) >= 0 ? "var(--call)" : "var(--put)" }} />
      </span>
      <span className={cn("fig w-[50px] text-right text-[10.5px]", dir(v))}>{pct(v)}</span>
    </div>
  );
}

function Card({ c, rank, span, pctOf, rsOf, tint, barMax, on, onPick }: CardBase & { c: HeatCard; rank?: number; barMax: number }) {
  const p = pctOf(c);
  return (
    <button type="button" aria-pressed={on} onClick={() => onPick(c.key)} style={heatStyle(p, tint)} className={cn(CARD_BOX, on ? "border-ink-3" : "border-ring")}>
      <p className="flex items-center gap-2">
        <SectorGlyph fund={c.key} size={15} className="block shrink-0 text-ink-2" />
        <span className="fig text-[13px] font-semibold text-ink">{c.key}</span>
        <span className={cn("fig text-[13px]", dir(p))}>{pct(p)}</span>
        {rank != null && <span className="fig ml-auto text-[10.5px] text-ink-3">#{rank}</span>}
      </p>
      <p className="mt-0.5 flex items-baseline justify-between gap-2">
        <span className="truncate text-[11.5px] text-ink-3">{c.label}</span>
        {c.names > 0 && <Counts up={c[span].up} down={c[span].down} />}
      </p>
      <SpyBar v={rsOf(c)} max={barMax} />
    </button>
  );
}

function TopMover({ c, span, word, pctOf, rsOf, tint, on, onPick }: CardBase & { c: HeatCard; word: string }) {
  const p = pctOf(c);
  const read = c[span];
  const led = read.leaders.map((x) => `${x.sym} ${x.chg >= 0 ? "+" : ""}${x.chg.toFixed(1)}%`).join(", ");
  return (
    <button type="button" aria-pressed={on} onClick={() => onPick(c.key)} style={heatStyle(p, tint)} className={cn(CARD_BOX, "col-span-2 row-span-2 flex flex-col justify-between px-4 py-3", on ? "border-ink-3" : "border-ring")}>
      <div>
        <p className="qt-cap text-[10px] text-ink-3">Top mover</p>
        <p className="mt-1 flex items-center justify-between gap-3">
          <span className="flex items-center gap-2.5">
            <SectorGlyph fund={c.key} size={22} className="block shrink-0 text-ink-2" />
            <span className="fig text-[22px] leading-none font-semibold text-ink">{c.key}</span>
          </span>
          <span className={cn("fig text-[22px] leading-none", dir(p))}>{pct(p)}</span>
        </p>
        <p className="mt-1 flex items-baseline justify-between gap-3 text-[12.5px]">
          <span className="text-ink-2">{c.label}</span>
          <span className={cn("fig text-[12px]", dir(rsOf(c)))}>{pct(rsOf(c))} vs SPY</span>
        </p>
      </div>
      <p className="mt-2 text-[12px] leading-[1.4] text-ink-3">
        Leads the board over {word}
        {c.names > 0 ? `: ${read.up} of its ${c.names} stocks at $2bn+ rose, ${read.down} fell.` : "."}
        {led ? ` Led by ${led}.` : ""}
      </p>
    </button>
  );
}

function IndustryCard({ g, span, spy, tint, barMax, on, onPick }: { g: HeatIndustry; span: HeatSpan; spy: number | null; tint: number; barMax: number; on: boolean; onPick: () => void }) {
  const read = g[span];
  const lead = read.leaders[0];
  return (
    <button type="button" aria-pressed={on} onClick={onPick} style={heatStyle(read.median, tint)} className={cn(CARD_BOX, on ? "border-ink-3" : "border-ring")} title={`${g.names} stocks at $2bn+${g.sector ? ` · ${g.sector}` : ""}`}>
      <p className="truncate text-[12.5px] font-semibold text-ink">{g.label}</p>
      <p className="mt-0.5 flex items-baseline justify-between gap-2">
        <span className={cn("fig text-[13px]", dir(read.median))}>{pct(read.median)}</span>
        <Counts up={read.up} down={read.down} />
      </p>
      <p className="fig mt-0.5 truncate text-[10.5px] text-ink-3">{lead ? `${lead.sym} ${lead.chg >= 0 ? "+" : ""}${lead.chg.toFixed(1)}%` : " "}</p>
      <SpyBar v={read.median == null || spy == null ? null : read.median - spy} max={barMax} />
    </button>
  );
}

function Tally({ value, hue, glyph, word, sub }: { value: number; hue: string; glyph: string; word: string; sub: string }) {
  return (
    <div className="flex items-center gap-3 px-4 py-2">
      <span className={cn("text-[12px]", hue)}>{glyph}</span>
      <div className="leading-[1.2]">
        <p className={cn("fig text-[16px]", hue)}>{value}</p>
        <p className="text-[11px] text-ink-3">
          <span className="qt-cap text-[10px]">{word}</span> · {sub}
        </p>
      </div>
    </div>
  );
}

function ThemeChips({ keys }: { keys: string[] }) {
  if (!keys.length) return <span className="text-[11.5px] text-ink-3">—</span>;
  // Always the same order, as in the screenshots, whichever card opened the table.
  const shown = keys.slice(0, 3);
  return (
    <span className="flex items-center gap-1 whitespace-nowrap" title={keys.join(", ")}>
      {shown.map((k) => (
        <span key={k} className="fig rounded-[3px] border border-ring px-1 text-[10px] leading-[15px] text-ink-2">
          {k}
        </span>
      ))}
      {keys.length > shown.length && <span className="fig text-[10px] text-ink-3">+{keys.length - shown.length}</span>}
    </span>
  );
}
