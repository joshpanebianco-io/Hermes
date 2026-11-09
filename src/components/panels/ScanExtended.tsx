"use client";

import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import type { ExtendedChip, ExtendedPayload, ExtendedRow } from "@/types/scanner";
import { HelmLoader } from "@/components/ui/HelmLoader";
import {
  CatalystCell,
  Chips,
  Choice,
  Menu,
  NameCell,
  Spark,
  TD,
  TH,
  TrackButton,
  VolCell,
  capShort,
  capWord,
  dayName,
  delayedLine,
  isNum,
  pctText,
  rowProps,
  useWalk,
  volWord,
} from "@/components/panels/ScanWide";
import { compact, num } from "@/lib/format";
import { cn } from "@/lib/cn";
import { segItem } from "@/lib/seg";
import { openTicker, useTicker } from "@/lib/ticker";
import { oneOf, usePersisted } from "@/lib/usePersisted";

/**
 * Extended hours — what is moving before the open and after the close.
 *
 * The plan for a day starts here: the gappers, how much has traded against an
 * average day, what the news is, and where each sits against the day it follows.
 * With no session on, the page is the last one rather than an empty table, because
 * that is what someone opening it the night before wants to read.
 */

const CHIPS: ReadonlyArray<{ key: ExtendedChip; label: string }> = [
  { key: "all", label: "All" },
  { key: "up", label: "Gap up" },
  { key: "down", label: "Gap down" },
  { key: "news", label: "Has news" },
  { key: "through", label: "Through the day's range" },
  { key: "day23", label: "Day 2/3" },
  { key: "pinned", label: "Pinned" },
];
const CAPS = [0, 3e8, 2e9, 5e9, 1e10].map((value) => ({ value, label: capWord(value) }));
const VOLS = [
  { value: 0, label: "Auto" },
  ...[5e4, 1e5, 5e5, 1e6].map((value) => ({ value, label: volWord(value) })),
];
type Session = "pre" | "post";

const SESSION_WORD: Record<Session, string> = { pre: "Pre-market", post: "After-hours" };

/** Where price sits in the day it follows: low on the left, high on the right. */
function RangeBar({ r }: { r: ExtendedRow }) {
  if (r.hi == null || r.lo == null || r.state == null) return <span className="text-ink-3">—</span>;
  const pos = r.hi > r.lo ? Math.max(0, Math.min(1, (r.last - r.lo) / (r.hi - r.lo))) : 0.5;
  const hue = r.state === "above" ? "bg-call-fig" : r.state === "below" ? "bg-put-fig" : "bg-ink-2";
  return (
    <div className="w-[150px]" title={`${r.state === "inside" ? "Inside" : r.state === "above" ? "Above" : "Below"} the day's range, ${num(r.lo)} to ${num(r.hi)}`}>
      <div className="fig flex justify-between text-[10.5px] text-ink-3">
        <span>{num(r.lo)}</span>
        <span>{num(r.hi)}</span>
      </div>
      <div className="relative mt-1 h-[3px] bg-[var(--qt-track,var(--ring))]">
        <span className={cn("absolute top-1/2 h-[9px] w-[3px] -translate-y-1/2", hue)} style={{ left: `calc(${pos * 100}% - 1px)` }} />
      </div>
    </div>
  );
}

export function ScanExtended({ onTrackChanged }: { onTrackChanged?: () => void }) {
  const [session, setSession] = usePersisted<Session | "auto">("ext.session", "auto", oneOf("auto", "pre", "post"));
  const [chip, setChip] = usePersisted<ExtendedChip>("ext.chip", "all", oneOf("all", "up", "down", "news", "through", "day23", "pinned"));
  const [cap, setCap] = usePersisted<number>("ext.cap", 2e9, isNum);
  const [vol, setVol] = usePersisted<number>("ext.vol", 0, isNum);
  const [data, setData] = useState<ExtendedPayload | null>(null);
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
      if (mine === seq.current) setData(d);
    } catch {
      /* the last read stays on screen */
    }
  }, [q]);

  const live = data?.ok ? data.active : false;
  useEffect(() => {
    void load();
    const id = setInterval(load, live ? 5000 : 60_000);
    return () => clearInterval(id);
  }, [load, live]);

  const syms = useMemo(() => data?.rows.map((r) => r.sym) ?? [], [data]);
  useWalk(syms);

  if (!data) return <HelmLoader label="Reading the extended session" size={48} minHeight={420} />;
  if (!data.ok) {
    return <p className="px-6 py-10 text-center text-[12px] text-ink-3">{data.offline ? `${data.offline.reason}.` : (data.error ?? "The wide read has not landed yet.")}</p>;
  }

  const summary = [capWord(cap), vol ? volWord(vol) : `${volWord(data.volume_floor)} auto`].join(" · ");
  const { up, down } = data.stats;

  return (
    <div className="flex min-h-0 flex-1 flex-col">
      <div className="flex shrink-0 flex-wrap items-center gap-x-8 gap-y-2 border-b border-ring px-6 py-3">
        <span className="seg">
          {(["pre", "post"] as const).map((s) => (
            <button key={s} type="button" onClick={() => setSession(s === clock ? "auto" : s)} {...segItem(shown === s)}>
              {SESSION_WORD[s]}
            </button>
          ))}
        </span>
        {up && <Biggest r={up} />}
        {down && <Biggest r={down} />}
        <p className="fig ml-auto text-[11px] text-ink-3">
          {data.active ? `${SESSION_WORD[shown]} on now` : `Last ${SESSION_WORD[shown].toLowerCase()} · ${dayName(data.day)}`} · {delayedLine(data.read_age_min, data.delayed_min)}
        </p>
      </div>

      {!data.active && (
        <div className="shrink-0 border-b border-ring px-6 py-3">
          <p className="text-[12px] text-ink-2">
            {shown === "pre" ? "The pre-market opens at 04:00 ET. These are the last session's gappers, kept for reference." : "After-hours runs 16:00 to 20:00 ET. These are the last session's gappers, kept for reference."}
          </p>
          {data.reference.length > 0 && (
            <div className="mt-2.5 grid grid-cols-1 gap-2 sm:grid-cols-2 xl:grid-cols-4">
              {data.reference.map((r) => (
                <RefCard key={r.sym} r={r} />
              ))}
            </div>
          )}
        </div>
      )}

      <div className="flex shrink-0 flex-wrap items-center gap-2 px-6 py-2.5">
        <Chips items={CHIPS} on={chip} set={setChip} counts={data.chips} />
        <div className="ml-auto flex items-center gap-2">
          <span className="fig text-[11px] text-ink-3">{data.shown === data.matched ? `${data.shown} showing` : `${data.shown} of ${data.matched}`}</span>
          <Menu label={<>Filters · <span className="fig">{summary}</span></>}>
            <Choice label="Market cap" options={CAPS} value={cap} set={setCap} />
            <Choice label={`${SESSION_WORD[shown]} volume`} options={VOLS} value={vol} set={setVol} />
          </Menu>
        </div>
      </div>

      <div className="min-h-0 flex-1 overflow-auto">
        {data.rows.length === 0 ? (
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
          <table className="w-full min-w-[1020px] border-separate border-spacing-0 text-left">
            <thead className="sticky top-0 z-20">
              <tr>
                <th scope="col" className={cn(TH, "sticky left-0 z-30 w-[148px]")}>Ticker</th>
                <th scope="col" className={TH}>Most important story</th>
                <th scope="col" className={cn(TH, "text-right")}>{shown === "pre" ? "PM %" : "AH %"}</th>
                <th scope="col" className={cn(TH, "text-right")}>Volume</th>
                <th scope="col" className={TH}>Against the day</th>
                <th scope="col" className={cn(TH, "text-right")}>Float</th>
                <th scope="col" className={TH}>Today</th>
                <th scope="col" className={TH} />
              </tr>
            </thead>
            <tbody>
              {data.rows.map((r) => (
                <tr key={r.sym} {...rowProps(r.sym, ticker === r.sym)}>
                  <td className={cn(TD, "sticky left-0 z-10", ticker === r.sym ? "bg-surface-2" : "bg-bg group-hover:bg-surface")}>
                    <NameCell
                      sym={r.sym}
                      side={r.chg >= 0 ? "long" : "short"}
                      price={num(r.last)}
                      sub={
                        <>
                          {r.live && <span className="qt-cap ml-1.5 text-[9px] text-call-fig" title="Moving on the live stream">live</span>}
                          {(r.stage ?? 0) >= 2 && <span className="qt-cap ml-1.5 text-[9px] text-ink-2">day {r.stage}</span>}
                        </>
                      }
                    />
                  </td>
                  <td className={TD}>
                    <CatalystCell c={r.catalyst} width={460} />
                  </td>
                  <td className={cn(TD, "fig text-right text-[12.5px]", r.chg >= 0 ? "up" : "down")}>{pctText(r.chg)}</td>
                  <td className={TD}>
                    <VolCell vol={r.vol} adv={r.adv_pct} />
                  </td>
                  <td className={TD}>
                    <RangeBar r={r} />
                  </td>
                  <td className={cn(TD, "fig text-right text-[12px] text-ink-3")}>{r.float != null ? compact(r.float) : "—"}</td>
                  <td className={TD}>
                    <Spark pts={r.spark} />
                  </td>
                  <td className={cn(TD, "text-right")}>
                    <TrackButton
                      sym={r.sym}
                      tracked={Boolean(r.tracked)}
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

function RefCard({ r }: { r: ExtendedRow }) {
  return (
    <button type="button" onClick={() => openTicker(r.sym)} className="hit rounded-[3px] border border-ring p-2.5 text-left">
      <p className="flex items-baseline gap-2">
        <span className="text-[13px] font-semibold text-ink">{r.sym}</span>
        <span className={cn("fig text-[15px]", r.chg >= 0 ? "up" : "down")}>{pctText(r.chg, 1)}</span>
        <span className="fig text-[11.5px] text-ink-2">{num(r.last)}</span>
        {r.catalyst && <span className="qt-cap ml-auto text-[9.5px] text-ink-2">{r.catalyst.tag}</span>}
      </p>
      <p className="mt-1 line-clamp-2 min-h-[32px] text-[11.5px] leading-[1.35] text-ink-3">{r.catalyst?.title ?? "No story held for this move."}</p>
      <p className="fig mt-1.5 text-[10.5px] text-ink-3">
        vol {r.vol != null ? compact(r.vol) : "—"} · float {r.float != null ? compact(r.float) : "—"} · {capShort(r.cap)}
      </p>
    </button>
  );
}
