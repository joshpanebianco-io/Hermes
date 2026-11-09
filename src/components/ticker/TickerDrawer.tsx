"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import type { NamePayload, Side } from "@/types/scanner";
import { ScanChart } from "@/components/panels/ScanChart";
import { ScanDetail, emBand, sideHue } from "@/components/panels/ScanDetail";
import { TrackButton, capShort, isNum } from "@/components/panels/ScanWide";
import { TickerLogo } from "@/components/ui/TickerLogo";
import { Tick } from "@/components/ui/Tick";
import { HelmLoader } from "@/components/ui/HelmLoader";
import { setAskFocus } from "@/lib/ask/open";
import { dir, num, pct } from "@/lib/format";
import { cn } from "@/lib/cn";
import { segItem } from "@/lib/seg";
import { closeTicker, togglePin, useTicker } from "@/lib/ticker";
import { useNow } from "@/lib/useNow";
import { oneOf, usePersisted } from "@/lib/usePersisted";

/**
 * The slide-out: one name, large, from anywhere (owner, 2026-11-09).
 *
 * It replaces the fixed pane the Scanner carried beside its table. The table gets
 * the full width back, which it needed, and the chart goes from 456px to about
 * 1,180 on the owner's 2560 screen, which is what reading a retest needs.
 *
 * THE TABLE BEHIND IT STAYS LIVE. The screenshots this came from dim the page and
 * block it; here another click swaps the name without closing, and ↑ ↓ walk the
 * list, because the job is going through thirty names, not reading one. So it is
 * not a dialog: no backdrop and no focus trap.
 *
 * Esc closes it, F makes it full width, its left edge drags, and the width is
 * remembered. It sits inside the page, between the header and the status rail,
 * and Hermes's panel floats above it.
 */

const isPct = (v: unknown): v is number => isNum(v) && v >= 40 && v <= 100;

export function TickerDrawer() {
  const sym = useTicker();
  const [data, setData] = useState<NamePayload | null>(null);
  const [failed, setFailed] = useState<string | null>(null);
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
        setData(d);
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

  // A new name starts blank rather than showing the last one's row under its ticker.
  useEffect(() => {
    setData(null);
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
      if (e.key === "Escape") {
        e.preventDefault();
        closeTicker();
      } else if (e.key === "f" || e.key === "F") {
        e.preventDefault();
        setFull((v) => !v);
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
  const side: Side | null = r ? (r.setup.side ?? r.score.side) : null;

  return (
    <aside
      ref={panel}
      aria-label={`${sym}, detail`}
      className="absolute inset-y-0 right-0 z-40 flex min-w-0 flex-col border-l border-ring-2 bg-bg shadow-[-18px_0_60px_rgba(0,0,0,.45)]"
      style={{ width: full ? "100%" : `min(100%, max(860px, ${width}%))` }}
    >
      {!full && <div onPointerDown={startDrag} className="absolute inset-y-0 -left-[3px] z-10 w-[6px] cursor-col-resize" aria-hidden title="Drag to resize" />}

      <header className="flex shrink-0 flex-wrap items-baseline gap-x-3 gap-y-1 border-b border-ring px-4 py-2.5">
        <span className={cn("text-[14px]", side ? sideHue(side) : "text-ink-3")}>{side === "long" ? "▲" : side === "short" ? "▼" : "·"}</span>
        <TickerLogo sym={sym} size={22} className="self-center" />
        <span className="text-[21px] leading-none font-semibold text-ink">{sym}</span>
        {r?.name && <span className="max-w-[240px] truncate text-[12.5px] text-ink-3">{r.name}</span>}
        {r && (
          <>
            <Tick value={num(r.last)} className="fig text-[17px] text-ink" />
            <Tick value={pct(r.chg_pct)} className={cn("fig text-[13px]", dir(r.chg_pct))} />
            {r.ext_pct != null && (
              <span className="fig text-[12px] text-ink-3">
                {data?.session === "pre" ? "pre" : "post"} <span className={dir(r.ext_pct)}>{pct(r.ext_pct)}</span>
              </span>
            )}
          </>
        )}
        {data?.stage != null && <span className="qt-cap text-[10px] text-ink-2" title="Which day of a multi-day move this is">Day {data.stage}</span>}
        {r?.market_cap != null && <span className="fig text-[11.5px] text-ink-3">{capShort(r.market_cap)}</span>}

        <div className="ml-auto flex items-center gap-2 self-center">
          {data && !data.tracked && <TrackButton sym={sym} tracked={false} onDone={() => void load(sym)} />}
          <button
            type="button"
            onClick={() => void togglePin(sym).then(() => load(sym))}
            title={data?.pinned ? "Pinned: always on the list. Click to unpin." : "Pin: keep this name on the list for good"}
            aria-pressed={data?.pinned ?? false}
            {...segItem(data?.pinned ?? false, { className: "border border-ring-2" })}
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
          <button type="button" onClick={() => setFull((v) => !v)} title="Full width (F)" {...segItem(full, { className: "border border-ring-2" })}>
            ⤢
          </button>
          <button type="button" onClick={closeTicker} title="Close (Esc)" {...segItem(false, { className: "border border-ring-2" })}>
            ✕
          </button>
        </div>
      </header>

      <div className="@container min-h-0 flex-1">
        <div className="grid h-full min-h-0 grid-rows-[minmax(320px,52%)_minmax(0,1fr)] @min-[900px]:grid-cols-[minmax(0,1fr)_400px] @min-[900px]:grid-rows-1">
          <section aria-label={`${sym} chart`} className="min-h-0 min-w-0">
            <ScanChart key={sym} sym={sym} state={r?.lvl_state ?? 0} em={r ? emBand(r) : null} />
          </section>
          <section aria-label={`${sym} detail`} className="min-h-0 min-w-0 overflow-y-auto border-t border-ring @min-[900px]:border-t-0 @min-[900px]:border-l">
            {r ? (
              <ScanDetail r={r} bench={bench} now={now} tracked={Boolean(data?.tracked)} />
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
