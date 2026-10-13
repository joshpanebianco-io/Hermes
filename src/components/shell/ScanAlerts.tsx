"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import type { ScanEvent, ScanEvents } from "@/types/scanner";
import { TEST_ALERT, chime, useAlertPrefs } from "@/lib/alerts";
import { num } from "@/lib/format";
import { cn } from "@/lib/cn";

/**
 * Scanner alerts — the Pine's alerts, raised by the terminal (owner
 * instruction, 2026-10-13: the review's "you wouldn't need to watch the tab at
 * 00:30 AEDT").
 *
 * MOUNTED ONCE IN THE SHELL, so it runs on every tab: the point is to be told
 * while reading the wire or the brief. It polls the scanner's event feed, and
 * for each NEW event — an (L) retest, an (E) trigger, a ◆ breakout, or a name
 * 90% of the way to a level — raises an in-app toast, a chime, and (once the
 * browser has granted it) a desktop notification. What fires, and how, is
 * Settings → Alerts.
 *
 * ONLY LIVE EVENTS ALERT. The page starts at the feed's current end, so a
 * reload never replays the morning; and an event the collector found by
 * replaying bars after a restart is marked not-live by the engine and is
 * logged but never announced — an alert for a signal from two hours ago is a
 * false alarm with a timestamp.
 *
 * A BACKGROUND TAB IS SLOWER. Chrome throttles timers in a tab hidden for five
 * minutes to about once a minute, so an alert can arrive up to a minute after
 * the bar; on ten-minute bars that is still inside the retest.
 */

const POLL_SEC = 15;
const TOAST_SEC = 25;
const MAX_TOASTS = 4;

const GLYPH: Record<ScanEvent["kind"], string> = { L: "(L)", E: "(E)", BO: "◆", NEAR: "Near" };

const openUrl = (sym: string) => `/?tab=scanner&sym=${encodeURIComponent(sym)}`;

export function ScanAlerts() {
  const prefs = useAlertPrefs();
  // Read through a ref so the poll keeps one identity and still sees a toggle
  // flipped in Settings a moment ago.
  const prefsRef = useRef(prefs);
  useEffect(() => {
    prefsRef.current = prefs;
  }, [prefs]);
  const cursor = useRef<number | null>(null);
  const [toasts, setToasts] = useState<ScanEvent[]>([]);

  const raise = useCallback((e: ScanEvent) => {
    const p = prefsRef.current;
    setToasts((t) => [...t.filter((x) => x.id !== e.id), e].slice(-MAX_TOASTS));
    if (p.sound) chime(e.side);
    if (p.desktop && typeof Notification !== "undefined" && Notification.permission === "granted") {
      try {
        const n = new Notification(`${GLYPH[e.kind]} ${e.side === "long" ? "▲" : "▼"} ${e.sym} · ${e.at_et} ET`, {
          body: e.note,
          tag: `hx-${e.id}`,
          silent: true,
        });
        n.onclick = () => {
          window.focus();
          window.location.assign(openUrl(e.sym));
        };
      } catch {
        /* some browsers only allow notifications from a service worker */
      }
    }
  }, []);

  const poll = useCallback(async () => {
    try {
      const since = cursor.current ?? Number.MAX_SAFE_INTEGER;
      const r = await fetch(`/api/scanner/events?since=${since}&limit=100`, { cache: "no-store" });
      const d = (await r.json()) as ScanEvents;
      if (d.offline) return;
      // First answer, or a log that was reset under us: start at the end.
      if (cursor.current === null || d.latest < cursor.current) {
        cursor.current = d.latest;
        return;
      }
      const p = prefsRef.current;
      for (const e of d.events) {
        cursor.current = Math.max(cursor.current ?? 0, e.id);
        if (!p.on || !e.live || !p.kinds.includes(e.kind)) continue;
        if ((e.score ?? 0) < p.minScore) continue;
        raise(e);
      }
    } catch {
      /* the collector is down or restarting — the next poll tries again */
    }
  }, [raise]);

  useEffect(() => {
    void poll();
    const id = setInterval(poll, POLL_SEC * 1000);
    return () => clearInterval(id);
  }, [poll]);

  // Settings' test button.
  useEffect(() => {
    const onTest = () =>
      raise({
        id: -Date.now(),
        ts: new Date().toISOString(),
        bar_ts: new Date().toISOString(),
        at_et: new Date().toLocaleTimeString("en-US", { hour: "2-digit", minute: "2-digit", hour12: false, timeZone: "America/New_York" }),
        day: "",
        sym: "TEST",
        kind: "L",
        side: "long",
        level: "PMH",
        price: 100,
        stop: 99.5,
        score: 72,
        note: "(L) long — retest of PMH 100.00 · a test alert from Settings",
        live: true,
        outcome: null,
      });
    window.addEventListener(TEST_ALERT, onTest);
    return () => window.removeEventListener(TEST_ALERT, onTest);
  }, [raise]);

  // Each toast leaves on its own after a while.
  useEffect(() => {
    if (toasts.length === 0) return;
    const id = setTimeout(() => setToasts((t) => t.slice(1)), TOAST_SEC * 1000);
    return () => clearTimeout(id);
  }, [toasts]);

  if (toasts.length === 0) return null;
  return (
    <div className="pointer-events-none fixed right-4 bottom-12 z-[900] flex w-[340px] flex-col gap-2" aria-live="polite" role="status">
      {toasts.map((e) => (
        <div
          key={e.id}
          className="pointer-events-auto flex flex-col gap-1 rounded-[4px] border border-ring-2 border-l-2 bg-surface-2 px-3 py-2.5 shadow-[0_8px_24px_-12px_rgb(0_0_0/0.9)]"
          style={{ borderLeftColor: e.side === "long" ? "var(--call-fig)" : "var(--put-fig)" }}
        >
          <div className="flex items-baseline gap-2">
            <span className={cn("fig text-[12px] font-semibold", e.side === "long" ? "text-call-fig" : "text-put-fig")}>
              {GLYPH[e.kind]} {e.side === "long" ? "▲" : "▼"}
            </span>
            <span className="text-[13.5px] font-semibold text-ink">{e.sym}</span>
            {e.level && <span className="qt-cap text-[10.5px] text-ink-3">{e.level}</span>}
            <span className="fig ml-auto text-[11px] text-ink-3">{e.at_et} ET</span>
            <button
              type="button"
              aria-label="Dismiss"
              onClick={() => setToasts((t) => t.filter((x) => x.id !== e.id))}
              className="hit -mr-1 px-1 text-[13px] leading-none text-ink-3 hover:text-ink"
            >
              ×
            </button>
          </div>
          <p className="text-[12px] leading-snug text-ink-2">{e.note}</p>
          <div className="flex items-baseline gap-3 text-[11px] text-ink-3">
            <span className="fig">
              {num(e.price)}
              {e.stop != null && ` · stop ${num(e.stop)}`}
              {e.score != null && ` · score ${e.score}`}
            </span>
            {e.sym !== "TEST" && (
              <a href={openUrl(e.sym)} className="ml-auto text-ink-2 underline-offset-2 hover:underline">
                Open in the scanner
              </a>
            )}
          </div>
        </div>
      ))}
    </div>
  );
}
