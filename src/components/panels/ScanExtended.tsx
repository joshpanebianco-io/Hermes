"use client";

import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import type { ExtendedChip, ExtendedPayload, ExtendedRow } from "@/types/scanner";
import { PageLoader, PageNote } from "@/components/ui/HelmLoader";
import {
  CatalystCell,
  Chips,
  Choice,
  ExtVol,
  Glyph,
  Head,
  Menu,
  MoveBar,
  RangeBar,
  RvolWord,
  Showing,
  Spark,
  SPARK_TIP,
  TD,
  TH,
  Tag,
  TickerCell,
  capWord,
  dayName,
  delayedLine,
  isNum,
  pctText,
  rowProps,
  rowTags,
  volWord,
} from "@/components/panels/ScanWide";
import { compact } from "@/lib/format";
import { cn } from "@/lib/cn";
import { keepRead, lastRead } from "@/lib/lastRead";
import { THROUGH_DAY_TITLE } from "@/lib/outsideDay";
import { segItem } from "@/lib/seg";
import { openTicker, useTicker } from "@/lib/ticker";
import { manyOf, oneOf, usePersisted } from "@/lib/usePersisted";
import { usePinsChanged } from "@/lib/usePinsChanged";

/**
 * Extended hours — what is moving before the open and after the close.
 *
 * The plan for a day starts here: the gappers, how much has traded against what is
 * usual, what the news is, and where each sits against the day it follows and the
 * pre-market it made. With no session on, the page is the last one rather than an
 * empty table, because that is what someone opening it the night before wants to read.
 *
 * THE SCREENSHOTS' PAGE (owner, 2026-11-10): one line of counts, the chips, and the
 * table under coloured group rules, with both ranges drawn. Their Opening Range column
 * is left out: the wide read has no intraday bars to take it from, and the strategy
 * does not trade it.
 */

/*
 * SIX CHIPS, EACH A CUT NOTHING ELSE ON THE PAGE MAKES (owner, 2026-11-13: "streamline
 * the app and make it have the most useful informaiton visible without clutter and
 * noise", after asking whether the pills were redundant). Two went: "Pinned", which
 * re-listed names that are all on the Setups table already (its Gaps chip is the same
 * question asked of your own list), and "Day 2/3", which is the tab this page's own
 * "Multi-day tracker" button opens. The collector still answers both keys.
 */
const CHIPS: ReadonlyArray<{ key: ExtendedChip; label: string; title?: string }> = [
  { key: "all", label: "All" },
  { key: "news", label: "Has News", title: "A story about this name in the last day" },
  { key: "up", label: "Gap Up" },
  { key: "down", label: "Gap Down" },
  // Not "Outside day": that is through both ranges (lib/outsideDay), and in an extended
  // session this list knows the previous day's level alone.
  { key: "through", label: "Through PDH/PDL", title: THROUGH_DAY_TITLE },
  { key: "inside", label: "Inside Day", title: "The last bar sits inside the one before it" },
];
const CAPS = [0, 3e8, 2e9, 5e9, 1e10].map((value) => ({ value, label: capWord(value) }));
const VOLS = [
  { value: 0, label: "Auto" },
  ...[5e4, 1e5, 5e5, 1e6].map((value) => ({ value, label: volWord(value) })),
];
/*
 * TWO SESSIONS, AND THE PAGE PICKS ONE BY THE CLOCK. There was a third choice, "All
 * sessions", the two merged: through the whole regular session it was the pre-market
 * list again, name for name (97 and 97 when it was checked), because the after-hours
 * list is empty until 16:00. It went with the 2026-11-13 clear-out; a browser that had
 * it saved follows the clock.
 */
type Session = "pre" | "post";

const SESSION_WORD: Record<Session, string> = { pre: "Pre-market", post: "After-hours" };
const BADGE: Record<Session, string> = { pre: "PM", post: "AH" };

const COLS = ["news", "move", "volume", "levels", "chart", "float"] as const;
type Col = (typeof COLS)[number];
const COL_NAME: Record<Col, string> = { news: "News", move: "Move", volume: "Volume", levels: "Levels", chart: "Chart", float: "Float" };
const COL_DEFAULT: Col[] = ["news", "move", "volume", "levels", "chart"];

export function ScanExtended({ onTrackChanged, onDay23 }: { onTrackChanged?: () => void; onDay23?: () => void }) {
  const [session, setSession] = usePersisted<Session | "auto">("ext.session", "auto", oneOf("auto", "pre", "post"));
  const [chip, setChip] = usePersisted<ExtendedChip>("ext.chip", "all", oneOf("all", "up", "down", "news", "through", "inside"));
  const [cap, setCap] = usePersisted<number>("ext.cap", 2e9, isNum);
  const [vol, setVol] = usePersisted<number>("ext.vol", 0, isNum);
  const [cols, setCols] = usePersisted<Col[]>("ext.cols", COL_DEFAULT, manyOf(...COLS));
  // The news-led order the collector sends, or the biggest gap up or down first.
  const [sort, setSort] = usePersisted<"news" | "up" | "down">("ext.sort", "news", oneOf("news", "up", "down"));
  const [data, setData] = useState<ExtendedPayload | null>(() => lastRead<ExtendedPayload>("scan.extended"));
  const seq = useRef(0);
  const ticker = useTicker();

  // "Auto" follows the clock: after-hours from 16:00 until the next pre-market.
  const [clock, setClock] = useState<Session>("pre");
  useEffect(() => {
    const read = () => {
      const h = Number(new Intl.DateTimeFormat("en-US", { timeZone: "America/New_York", hour: "2-digit", hour12: false }).format(new Date()));
      setClock(h >= 16 && h < 20 ? "post" : "pre");
    };
    read();
    const id = setInterval(read, 60_000);
    return () => clearInterval(id);
  }, []);
  const shown: Session = session === "auto" ? clock : session;

  const q = useMemo(() => {
    const p = new URLSearchParams({ session: shown, chip, cap: String(cap) });
    if (vol) p.set("vol", String(vol));
    return p.toString();
  }, [shown, chip, cap, vol]);

  const load = useCallback(async () => {
    const mine = ++seq.current;
    try {
      const r = await fetch(`/api/scanner/extended?${q}`, { cache: "no-store" });
      const d = (await r.json()) as ExtendedPayload;
      if (mine === seq.current) setData(keepRead("scan.extended", d));
    } catch {
      /* the last read stays on screen */
    }
  }, [q]);
  // A star elsewhere, or the Undo on the unpin notice, changed the list: read it again.
  usePinsChanged(load);

  const live = data?.ok ? data.active : false;
  useEffect(() => {
    void load();
    const id = setInterval(load, live ? 5000 : 60_000);
    return () => clearInterval(id);
  }, [load, live]);

  const rows = useMemo(() => {
    const all = data?.rows ?? [];
    return sort === "news" ? all : [...all].sort((a, b) => (sort === "up" ? b.chg - a.chg : a.chg - b.chg));
  }, [data, sort]);
  // A card where the view will be, not the helm on the ground (ui/HelmLoader PageLoader).
  if (!data) return <PageLoader label="Reading the extended session" />;
  if (!data.ok) {
    return <PageNote>{data.offline ? `${data.offline.reason}.` : (data.error ?? "The wide read has not landed yet.")}</PageNote>;
  }

  const summary = [capWord(cap), vol ? volWord(vol) : `${volWord(data.volume_floor)} auto`].join(" · ");
  const s = data.stats;
  const has = (c: Col) => cols.includes(c);
  const toggle = (c: Col) => setCols((was) => (was.includes(c) ? was.filter((x) => x !== c) : [...was, c]));
  const refreshed = () => {
    void load();
    onTrackChanged?.();
  };
  const moveName = shown === "pre" ? "PM %" : "AH %";
  const volName = shown === "pre" ? "PM vol" : "AH vol";

  return (
    <div className="flex min-h-0 flex-1 flex-col">
      {/* ONE ROW, NOT TWO BARS (design pass, 2026-11-11): the session switch sat on a bar
          of its own with the status at the far end, and the counts on a second under it,
          which with the chips made four bars above the table. They are one line on a
          wide window and wrap on a narrow one; two more names fit on the screen. */}
      <div className="qt-stats flex shrink-0 flex-wrap items-center gap-x-6 gap-y-2 border-b border-ring px-4 py-2">
        <span className="seg">
          {(["pre", "post"] as const).map((v) => (
            <button key={v} type="button" onClick={() => setSession(v === clock ? "auto" : v)} {...segItem(shown === v)}>
              {SESSION_WORD[v]}
            </button>
          ))}
        </span>
        <span aria-hidden className="h-6 w-px bg-ring-2" />
        {s.up && <Biggest r={s.up} />}
        {s.down && <Biggest r={s.down} />}
        <span aria-hidden className="h-6 w-px bg-ring-2" />
        <Count label="Through PD" value={s.through ?? data.chips.through} hue="text-desk-markets" sub="over PDH or under PDL" />
        <Count label="Inside day" value={s.inside ?? data.chips.inside ?? 0} sub="consolidating" />
        <Count label="Gapping up" value={s.gap_up ?? data.chips.up} hue="text-call-fig" news={s.gap_up_news} />
        <Count label="Gapping down" value={s.gap_down ?? data.chips.down} hue="text-put-fig" news={s.gap_down_news} />
        <p className="fig ml-auto text-[11px] text-ink-3">
          {data.active ? (
            <>
              <span aria-hidden className="mr-1.5 inline-block h-[6px] w-[6px] rounded-full bg-desk-policy align-middle" />
              {SESSION_WORD[shown]} active
            </>
          ) : (
            <>
              Last {SESSION_WORD[shown].toLowerCase()} · {dayName(data.day)}
            </>
          )}{" "}
          · {delayedLine(data.read_age_min, data.delayed_min)}
        </p>
        {onDay23 && (
          <button type="button" onClick={onDay23} className="hit flex items-center gap-2 rounded-[4px] border border-ring-2 px-2.5 py-1 text-[11.5px] text-ink-2">
            <span className="qt-cap text-[9.5px] text-ink-3">Multi-day tracker</span>
            Day 2/3
            <Glyph name="arrow" size={12} className="text-ink-3" />
          </button>
        )}
      </div>

      <div className="qt-bar flex shrink-0 flex-wrap items-center gap-2 border-b border-ring px-4 py-2">
        <Chips items={CHIPS} on={chip} set={setChip} counts={data.chips} />
        <div className="ml-auto flex items-center gap-2">
          <Menu label={<>Filters · <span className="fig">{summary}</span></>}>
            <Choice label="Market cap" options={CAPS} value={cap} set={setCap} />
            <Choice label="Volume this session" options={VOLS} value={vol} set={setVol} />
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
          <Showing shown={data.shown} total={data.scanned ?? null} word="scanned" />
        </div>
      </div>

      <div className="qt-sheet min-h-0 flex-1 overflow-auto">
        {rows.length === 0 ? (
          <div className="px-6 py-10 text-center text-[12px] text-ink-3">
            <p>{data.active ? "Nothing has gapped 2% on volume yet." : "Nothing at these filters."} Extended-hours volume is thin by nature: lowering the volume floor shows more.</p>
            {data.reference.length > 0 && data.reference_is_last && (
              <div className="mx-auto mt-4 grid max-w-[1100px] grid-cols-1 gap-2 text-left sm:grid-cols-2 xl:grid-cols-4">
                {data.reference.map((r) => (
                  <RefCard key={r.sym} r={r} />
                ))}
              </div>
            )}
          </div>
        ) : (
          <table className="w-full min-w-[1180px] border-separate border-spacing-0 text-left">
            <thead className="sticky top-0 z-20">
              <tr>
                <th scope="col" className={cn(TH, "sticky left-0 z-30 w-[200px]")}><Head label="Ticker" hint="symbol · price · tags" /></th>
                {has("news") && <th scope="col" className={TH}><Head label="News" hint="most important first" /></th>}
                {has("move") && (
                  <>
                    <th scope="col" className={TH} title="Against this session's own average"><Head label="RVol" hint="vs usual session" /></th>
                    <th scope="col" className={TH}>
                      <button
                        type="button"
                        title="Click: biggest gap up first, biggest gap down first, or back to news first, then the move in ATRs on its volume"
                        onClick={() => setSort(sort === "news" ? "up" : sort === "up" ? "down" : "news")}
                        className={cn("qt-cap text-[10.5px] hover:text-ink-2", sort === "news" ? "text-ink-3" : "text-ink")}
                      >
                        <Head label={`${moveName}${sort === "up" ? " ↓" : sort === "down" ? " ↑" : ""}`} hint="vs prev close" />
                      </button>
                    </th>
                  </>
                )}
                {has("volume") && <th scope="col" className={TH}><Head label={volName} hint="this session" /></th>}
                {has("float") && <th scope="col" className={cn(TH, "text-right")}><Head label="Float" right /></th>}
                {has("levels") && (
                  <>
                    <th scope="col" className={TH}><Head label="PD range" hint="previous day low → current → high" /></th>
                    <th scope="col" className={TH}><Head label="PM range" hint="pre-market low → current → high" /></th>
                  </>
                )}
                {has("chart") && <th scope="col" className={TH} title={SPARK_TIP}><Head label="Spark" hint="from 04:00" /></th>}
              </tr>
            </thead>
            <tbody>
              {rows.map((r) => {
                const tag = BADGE[r.session ?? (shown === "post" ? "post" : "pre")];
                return (
                  <tr key={r.sym} {...rowProps(r.sym, ticker === r.sym)}>
                    <td className={cn(TD, "sticky left-0 z-10 w-[200px]", ticker === r.sym ? "bg-surface-2" : "bg-bg group-hover:bg-surface")}>
                      <TickerCell
                        sym={r.sym}
                        name={r.name}
                        price={`$${r.last.toFixed(2)}`}
                        badge={<Tag tone="warn">{tag}</Tag>}
                        tags={rowTags({ pd: r.state ?? null, inside: r.inside, news: r.catalyst != null, stage: r.stage, verdict: r.verdict })}
                        pinned={Boolean(r.pinned)}
                        onPinned={refreshed}
                        tracked={r.tracked}
                        onTrack={refreshed}
                        stack
                      />
                    </td>
                    {has("news") && (
                      <td className={TD}>
                        <CatalystCell c={r.catalyst} width={420} />
                      </td>
                    )}
                    {has("move") && (
                      <>
                        <td className={TD}>
                          <RvolWord v={r.rvol} est={r.rvol_est} />
                        </td>
                        <td className={TD}>
                          <MoveBar v={r.chg} />
                        </td>
                      </>
                    )}
                    {has("volume") && (
                      <td className={TD}>
                        <ExtVol vol={r.vol} adv={r.adv_pct} tag={tag} />
                      </td>
                    )}
                    {has("float") && <td className={cn(TD, "fig text-right text-[12px] text-ink-3")}>{r.float != null ? compact(r.float) : "—"}</td>}
                    {has("levels") && (
                      <>
                        <td className={TD}>
                          <RangeBar lo={r.lo} hi={r.hi} last={r.last} />
                        </td>
                        <td className={TD}>
                          <RangeBar lo={r.pml} hi={r.pmh} last={r.last} />
                        </td>
                      </>
                    )}
                    {has("chart") && (
                      <td className={TD}>
                        <Spark pts={r.spark} base={r.spark_ref} />
                      </td>
                    )}
                  </tr>
                );
              })}
            </tbody>
          </table>
        )}
      </div>
    </div>
  );
}

function Biggest({ r }: { r: ExtendedRow }) {
  return (
    <button type="button" onClick={() => openTicker(r.sym)} className="hit flex items-baseline gap-2 whitespace-nowrap">
      <span className={cn("text-[11px]", r.chg >= 0 ? "text-call-fig" : "text-put-fig")}>{r.chg >= 0 ? "▲" : "▼"}</span>
      <span className="text-[13px] font-semibold text-ink">{r.sym}</span>
      <span className={cn("fig text-[14px]", r.chg >= 0 ? "up" : "down")}>{pctText(r.chg, 1)}</span>
      <span className="fig text-[11px] text-ink-3">{r.vol != null ? `${compact(r.vol)} vol` : ""}</span>
    </button>
  );
}

function Count({ label, value, hue, sub, news }: { label: string; value: number; hue?: string; sub?: string; news?: number }) {
  return (
    <p className="flex items-baseline gap-2 whitespace-nowrap">
      <span className="qt-cap text-[9.5px] text-ink-3">{label}</span>
      <span className={cn("fig text-[15px] leading-none", hue ?? "text-ink")}>{value}</span>
      {sub && <span className="text-[11px] text-ink-3">{sub}</span>}
      {news != null && <Tag tone="news">{news} news</Tag>}
    </p>
  );
}

function RefCard({ r }: { r: ExtendedRow }) {
  return (
    <button type="button" onClick={() => openTicker(r.sym)} className="hit rounded-[3px] border border-ring p-2.5 text-left">
      <p className="flex items-baseline gap-2">
        <span className="text-[13px] font-semibold text-ink">{r.sym}</span>
        <span className={cn("fig text-[15px]", r.chg >= 0 ? "up" : "down")}>{pctText(r.chg, 1)}</span>
        {r.catalyst && <span className="qt-cap ml-auto text-[9.5px] text-ink-2">{r.catalyst.tag}</span>}
      </p>
      <p className="mt-1 line-clamp-2 min-h-[32px] text-[11.5px] leading-[1.35] text-ink-3">{r.catalyst?.title ?? "No story held for this move."}</p>
    </button>
  );
}
