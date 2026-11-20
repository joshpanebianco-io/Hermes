"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import type { NamePayload } from "@/types/scanner";
import { ScanChart } from "@/components/panels/ScanChart";
import { ScanDetail, emBand } from "@/components/panels/ScanDetail";
import { Glyph, TrackButton, isNum } from "@/components/panels/ScanWide";
import { TickerLogo } from "@/components/ui/TickerLogo";
import { Tick } from "@/components/ui/Tick";
import { HelmLoader } from "@/components/ui/HelmLoader";
import { setAskFocus } from "@/lib/ask/open";
import { dir, num, pct } from "@/lib/format";
import { cn } from "@/lib/cn";
import { segItem } from "@/lib/seg";
import { keepRead, lastRead } from "@/lib/lastRead";
import { closeTicker, openSearch, togglePin, useTicker } from "@/lib/ticker";
import { useNow } from "@/lib/useNow";
import { oneOf, usePersisted } from "@/lib/usePersisted";
import { usePinsChanged } from "@/lib/usePinsChanged";

/**
 * The slide-out: one name, large, from anywhere (owner, 2026-11-09).
 *
 * It replaces the fixed pane the Scanner carried beside its table. The table gets
 * the full width back, which it needed, and the chart goes from 456px to about
 * 1,180 on the owner's 2560 screen, which is what reading a retest needs.
 *
 * THE TABLE BEHIND IT STAYS LIVE. The screenshots this came from dim the page and
 * block it; here another click swaps the name without closing, because the job is
 * going through thirty names, not reading one. So it is not a dialog: no backdrop
 * and no focus trap.
 *
 * Esc closes it, the header's buttons make it full width and close it, its left
 * edge drags, and the width is remembered. It sits inside the page, between the
 * header and the status rail, and Hermes's panel floats above it. Its single-key
 * controls (F, V, the arrows walking the list) and the legend of them along its
 * foot went on 2026-11-11, at the owner's word.
 */

const isPct = (v: unknown): v is number => isNum(v) && v >= 40 && v <= 100;

export function TickerDrawer() {
  const sym = useTicker();
  const [data, setData] = useState<NamePayload | null>(null);
  const [failed, setFailed] = useState<string | null>(null);
  // This opening's own read has landed (a held last read does not count: see the star).
  const [fresh, setFresh] = useState(false);
  const [width, setWidth] = usePersisted<number>("drawer.pct", 62, isPct);
  const [full, setFull] = useState(false);
  const [bench] = usePersisted<"SPY" | "QQQ">("scan.bench", "SPY", oneOf("SPY", "QQQ"));
  const now = useNow(30_000);
  const seq = useRef(0);
  const panel = useRef<HTMLElement | null>(null);

  const load = useCallback(async (name: string) => {
    const mine = ++seq.current;
    try {
      const r = await fetch(`/api/scanner/name/${encodeURIComponent(name)}`, { cache: "no-store" });
      const d = (await r.json()) as NamePayload;
      if (mine === seq.current) {
        setData(keepRead(`name:${name}`, d));
        setFresh(true);
        setFailed(null);
      }
    } catch (e) {
      if (mine === seq.current) setFailed(e instanceof Error ? e.message : "request failed");
    }
  }, []);

  const session = data?.session;
  useEffect(() => {
    if (!sym) return;
    void load(sym);
    const open = session && session !== "closed";
    const id = setInterval(() => void load(sym), open ? 5000 : 20_000);
    return () => clearInterval(id);
  }, [sym, session, load]);

  // A star in a table, or the Undo on the unpin notice, changed the list: the header's
  // own star reads the name again so it shows the truth.
  const reload = useCallback(() => {
    if (sym) void load(sym);
  }, [sym, load]);
  usePinsChanged(reload);

  // A new name starts blank rather than showing the last one's row under its ticker, or on
  // its own last read if it was open earlier this session (lib/lastRead): its poll then
  // replaces it, as it would have had the slide-out stayed open.
  useEffect(() => {
    setData(sym ? lastRead<NamePayload>(`name:${sym}`) : null);
    setFresh(false);
    setFailed(null);
  }, [sym]);

  // Hermes reads the name on screen: "explain this setup" means it.
  useEffect(() => {
    if (!sym) return;
    setAskFocus(sym);
    return () => setAskFocus(null);
  }, [sym]);

  useEffect(() => {
    if (!sym) return;
    const onKey = (e: KeyboardEvent) => {
      if (e.defaultPrevented || e.ctrlKey || e.metaKey || e.altKey) return;
      const el = e.target as HTMLElement | null;
      if (el && (el.isContentEditable || /^(INPUT|TEXTAREA|SELECT)$/.test(el.tagName))) return;
      // Esc closes it, as it closes a menu or the search. F for full width went with the
      // other single-key controls (owner, 2026-11-11); the button in the header does it.
      if (e.key === "Escape") {
        e.preventDefault();
        closeTicker();
      }
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [sym]);

  const startDrag = (e: React.PointerEvent<HTMLDivElement>) => {
    const parent = panel.current?.parentElement;
    if (!parent) return;
    e.preventDefault();
    const box = parent.getBoundingClientRect();
    const move = (ev: PointerEvent) => {
      const pct = ((box.right - ev.clientX) / box.width) * 100;
      setFull(false);
      setWidth(Math.max(40, Math.min(100, Math.round(pct))));
    };
    const up = () => {
      window.removeEventListener("pointermove", move);
      window.removeEventListener("pointerup", up);
    };
    window.addEventListener("pointermove", move);
    window.addEventListener("pointerup", up);
  };

  if (!sym) return null;
  const r = data?.row ?? null;
  // THE MOVE IN DOLLARS, FROM THE SAME TWO PRICES AS THE PERCENT BESIDE IT. The percent is
  // the regular session's (before the open, the last session's own). The dollars used to be
  // the last trade less the previous close, which outside the session is a different move:
  // GEV read "+9.96 (-3.90%)" on the evening of 10 Nov 2026, the after-hours gain beside
  // the day's loss. So they are worked back from the percent and the price it ends at: the
  // last trade in the session, the close after it, the previous close before the open.
  const move = (() => {
    if (!r || r.chg_pct == null || r.chg_pct <= -100) return null;
    const session = data?.session;
    const end =
      session === "pre" || session === "closed"
        ? r.levels.pdc
        : session === "post" && r.ext_pct != null && r.last != null
          ? r.last / (1 + r.ext_pct / 100)
          : r.last;
    return end != null ? end - end / (1 + r.chg_pct / 100) : null;
  })();

  return (
    <aside
      ref={panel}
      aria-label={`${sym}, detail`}
      className="qt-drawer absolute inset-y-0 right-0 z-40 flex min-w-0 flex-col border-l border-ring-2 bg-bg shadow-[-18px_0_60px_rgba(0,0,0,.45)]"
      style={{ width: full ? "100%" : `min(100%, max(860px, ${width}%))` }}
    >
      {!full && <div onPointerDown={startDrag} className="absolute inset-y-0 -left-[3px] z-10 w-[6px] cursor-col-resize" aria-hidden title="Drag to resize" />}

      <header className="flex shrink-0 flex-wrap items-center gap-x-3 gap-y-1 border-b border-ring px-4 py-2">
        <TickerLogo sym={sym} size={22} />
        <span className="text-[18px] leading-none font-semibold text-ink">{sym}</span>
        {r?.name && <span className="max-w-[220px] truncate text-[12.5px] text-ink-3">{r.name}</span>}
        {r && (
          <>
            <Tick value={`$${num(r.last)}`} className="fig text-[15px] text-ink" />
            <span className={cn("fig text-[13px]", dir(r.chg_pct))}>
              {move != null && `${move >= 0 ? "+" : ""}${move.toFixed(r.last != null && r.last < 1 ? 4 : 2)} `}
              (<Tick value={pct(r.chg_pct)} />)
            </span>
            {r.ext_pct != null && (
              <span className="fig text-[12px] text-ink-3">
                {data?.session === "pre" ? "pre" : "post"} <span className={dir(r.ext_pct)}>{pct(r.ext_pct)}</span>
              </span>
            )}
          </>
        )}
        {data?.stage != null && <span className="qt-cap text-[10px] text-ink-2" title="Which day of a multi-day move this is">Day {data.stage}</span>}

        <button
          type="button"
          onClick={openSearch}
          title="Find any ticker or company (Ctrl+K)"
          className="hit mx-auto flex h-[26px] w-[clamp(150px,16%,220px)] items-center gap-2 rounded-[4px] border border-ring-2 px-2.5 text-[12px] whitespace-nowrap text-ink-3"
        >
          <Glyph name="search" size={12} />
          <span className="min-w-0 flex-1 truncate text-left">Search ticker or company…</span>
        </button>

        <div className="flex items-center gap-2">
          {data && fresh && !data.tracked && <TrackButton sym={sym} tracked={false} onDone={() => void load(sym)} />}
          <button
            type="button"
            onClick={() => void togglePin(sym).then(() => load(sym))}
            // Not until the name has been read: the star showed ☆ for every name while
            // it loaded, and a click in that half second on a pinned one unpinned it. A
            // last read held from earlier (lib/lastRead) is not enough: the star may have
            // changed since, so it waits for this opening's own read.
            disabled={!data || !fresh}
            title={!data || !fresh ? "Reading the name…" : data.pinned ? "A favourite. Click to take it off your favourites." : "Add to your favourites"}
            aria-pressed={data?.pinned ?? false}
            {...segItem(data?.pinned ?? false, { className: "border border-ring-2 disabled:opacity-40" })}
          >
            {data?.pinned ? "★" : "☆"}
          </button>
          <a
            href={`https://www.tradingview.com/chart/?symbol=${encodeURIComponent(sym)}`}
            target="_blank"
            rel="noreferrer noopener"
            className="hit rounded-[3px] border border-ring-2 px-2 py-[3px] text-[11.5px] text-ink-3 hover:text-ink"
            title="Open this name on TradingView"
          >
            TradingView ↗
          </a>
          <button type="button" onClick={() => setFull((v) => !v)} title={full ? "Back to its own width" : "Full width"} {...segItem(full, { className: "border border-ring-2" })}>
            ⤢
          </button>
          <button type="button" onClick={closeTicker} title="Close" {...segItem(false, { className: "border border-ring-2" })}>
            ✕
          </button>
        </div>
      </header>

      <div className="@container min-h-0 flex-1">
        <div className="grid h-full min-h-0 grid-rows-[minmax(320px,52%)_minmax(0,1fr)] @min-[900px]:grid-cols-[minmax(0,1fr)_360px] @min-[900px]:grid-rows-1">
          <section aria-label={`${sym} chart`} className="min-h-0 min-w-0">
            <ScanChart key={sym} sym={sym} state={r?.lvl_state ?? 0} em={r ? emBand(r) : null} />
          </section>
          <section aria-label={`${sym} detail`} className="min-h-0 min-w-0 overflow-y-auto border-t border-ring @min-[900px]:border-t-0 @min-[900px]:border-l">
            {r ? (
              <ScanDetail r={r} bench={bench} now={now} tracked={Boolean(data?.tracked)} stage={data?.stage ?? null} />
            ) : data ? (
              <p className="px-5 py-8 text-center text-[12px] text-ink-3">{data.offline ? `${data.offline.reason}.` : (data.error ?? "No data for this name yet.")}</p>
            ) : failed ? (
              <p className="px-5 py-8 text-center text-[12px] text-ink-3">{failed}</p>
            ) : (
              <HelmLoader label={`Reading ${sym}`} size={40} minHeight={240} />
            )}
          </section>
        </div>
      </div>

    </aside>
  );
}
