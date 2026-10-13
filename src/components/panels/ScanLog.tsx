"use client";

import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import type { ScanEvent, ScanEvents, ScanOutcome, ScanStats } from "@/types/scanner";
import { num } from "@/lib/format";
import { segItem } from "@/lib/seg";
import { cn } from "@/lib/cn";
import { oneOf, usePersisted } from "@/lib/usePersisted";

/**
 * The signal log — every (L), (E), breakout and near-break the engine saw,
 * and what each one did afterwards (owner instruction, 2026-10-13: the
 * review's "measure the edge": log every signal and its outcome so the score
 * can be calibrated on real results instead of my guesses).
 *
 * OUTCOMES ARE IN R, AND R IS THE PINE'S OWN STOP. The script's tooltip names
 * the stop idea for each signal — below the (L) bar's low, below the (E)
 * candle's low — so one R is the distance from the signal price to that stop,
 * and everything after is measured in it: how far it ran for you (MFE), how
 * far against (MAE), whether +1R came before the stop, and where it stood 30
 * and 60 minutes on and at the close.
 *
 * THE ONE CONSERVATIVE CALL, STATED. A ten-minute bar does not say whether
 * its high or its low came first, so a bar that touches both the stop and +1R
 * is counted as stopped. That understates the edge slightly; the alternative
 * would overstate it, which is worse.
 *
 * THE STATS ARE A RECORD, NOT A FORECAST, and they say so when the sample is
 * too small to read — a 3-for-4 day is an anecdote.
 */

type Filter = "signals" | "all";
const POLL_SEC = 30;
const SMALL = 5;

const KIND: Record<ScanEvent["kind"], string> = { L: "(L)", E: "(E)", BO: "◆", NEAR: "near" };

export function ScanLog({ onPick }: { onPick: (sym: string) => void }) {
  const [events, setEvents] = useState<ScanEvent[]>([]);
  const [stats, setStats] = useState<ScanStats | null>(null);
  const [err, setErr] = useState<string | null>(null);
  const [loaded, setLoaded] = useState(false);
  const [filter, setFilter] = usePersisted<Filter>("scan.log", "signals", oneOf("signals", "all"));
  const seq = useRef(0);

  const load = useCallback(async () => {
    const mine = ++seq.current;
    try {
      // Where the log ends, then the most recent 500 events before it — the
      // feed is oldest-first from a cursor, so the cursor is set back from the end.
      const head = (await (await fetch(`/api/scanner/events?since=${Number.MAX_SAFE_INTEGER}`, { cache: "no-store" })).json()) as ScanEvents;
      const [ev, st] = await Promise.all([
        fetch(`/api/scanner/events?since=${Math.max(0, head.latest - 500)}&limit=500`, { cache: "no-store" }).then(
          (r) => r.json() as Promise<ScanEvents>,
        ),
        fetch("/api/scanner/stats?days=20", { cache: "no-store" }).then((r) => r.json() as Promise<ScanStats>),
      ]);
      if (mine !== seq.current) return;
      setEvents(ev.events ?? []);
      setStats(st.offline ? null : st);
      setErr(ev.offline?.reason ?? head.offline?.reason ?? null);
      setLoaded(true);
    } catch (e) {
      if (mine === seq.current) {
        setErr(e instanceof Error ? e.message : "request failed");
        setLoaded(true);
      }
    }
  }, []);

  useEffect(() => {
    void load();
    const id = setInterval(load, POLL_SEC * 1000);
    return () => clearInterval(id);
  }, [load]);

  const days = useMemo(() => {
    const kept = filter === "all" ? events : events.filter((e) => e.kind === "L" || e.kind === "E");
    const by = new Map<string, ScanEvent[]>();
    for (const e of [...kept].reverse()) {
      const list = by.get(e.day) ?? [];
      list.push(e);
      by.set(e.day, list);
    }
    return [...by.entries()];
  }, [events, filter]);


  return (
    <div className="flex flex-col pb-6">
      {err && <p className="px-3 py-3 text-[12px] text-err">Signal log unavailable — {err}</p>}

      <Stats stats={stats} />

      <div className="flex items-center gap-3 px-3 pt-5 pb-2">
        <p className="qt-cap text-[10.5px] text-ink-3">Signals, newest first</p>
        <span className="seg ml-auto">
          <button type="button" onClick={() => setFilter("signals")} {...segItem(filter === "signals")}>
            (L) and (E)
          </button>
          <button type="button" onClick={() => setFilter("all")} {...segItem(filter === "all")}>
            Every event
          </button>
        </span>
      </div>

      {!loaded ? (
        <p className="px-3 py-8 text-center text-[12px] text-ink-3">Loading the log…</p>
      ) : days.length === 0 ? (
        <p className="px-3 py-8 text-center text-[12px] text-ink-3">
          Nothing logged yet. Signals are recorded as the engine sees them on confirmed ten-minute bars during the
          regular session.
        </p>
      ) : (
        <table className="w-full min-w-[860px] border-collapse text-left">
          <thead className="sticky top-0 z-10 bg-bg">
            <tr className="border-b border-ring">
              {["Time", "Name", "Signal", "Price", "Stop", "1R", "Best", "Worst", "+1R?", "30m", "60m", "Close", "Score"].map((h, i) => (
                <th key={h} scope="col" className={cn("qt-cap px-2.5 py-2 text-[10.5px] font-semibold text-ink-3", i >= 3 && "text-right")}>
                  {h}
                </th>
              ))}
            </tr>
          </thead>
          <tbody>
            {days.map(([day, list]) => (
              <DayRows key={day} day={day} list={list} onPick={onPick} />
            ))}
          </tbody>
        </table>
      )}
    </div>
  );
}

function DayRows({ day, list, onPick }: { day: string; list: ScanEvent[]; onPick: (sym: string) => void }) {
  return (
    <>
      <tr>
        <td colSpan={13} className="qt-cap px-2.5 pt-4 pb-1.5 text-[10.5px] text-ink-3">
          {dayName(day)}
        </td>
      </tr>
      {list.map((e) => (
        <tr key={e.id} className="border-b border-ring/60 text-[12px]">
          <td className="fig px-2.5 py-1.5 text-ink-3">
            {e.at_et}
            {!e.live && (
              <span className="qt-cap ml-1.5 text-[9px] text-ink-3" title="Found by a replay after a restart — never alerted">
                replay
              </span>
            )}
          </td>
          <td className="px-2.5 py-1.5">
            <button type="button" onClick={() => onPick(e.sym)} className="hit font-semibold text-ink hover:underline">
              {e.sym}
            </button>
          </td>
          <td className={cn("px-2.5 py-1.5 whitespace-nowrap", e.side === "long" ? "text-call-fig" : "text-put-fig")}>
            <span className="fig">{KIND[e.kind]}</span> {e.side === "long" ? "▲" : "▼"}
            {e.level && <span className="ml-1.5 text-ink-3">{e.level}</span>}
          </td>
          <td className="fig px-2.5 py-1.5 text-right text-ink">{num(e.price)}</td>
          <td className="fig px-2.5 py-1.5 text-right text-ink-3">{e.stop != null ? num(e.stop) : "—"}</td>
          <Outcome o={e.outcome} />
          <td className="fig px-2.5 py-1.5 text-right text-ink-3">{e.score ?? "—"}</td>
        </tr>
      ))}
    </>
  );
}

const rTxt = (v: number | null | undefined) => (v == null ? "—" : `${v >= 0 ? "+" : ""}${v.toFixed(1)}R`);
const rHue = (v: number | null | undefined) => (v == null ? "text-ink-3" : v > 0 ? "up" : v < 0 ? "down" : "text-ink-2");

function Outcome({ o }: { o: ScanOutcome | null }) {
  if (!o) {
    return <td colSpan={7} className="px-2.5 py-1.5 text-right text-ink-3" />;
  }
  const verdict =
    o.hit_1r === true ? (
      <span className="text-call-fig">yes{o.hit_2r ? " · 2R" : ""}</span>
    ) : o.stopped === true ? (
      <span className="text-put-fig">stopped</span>
    ) : o.final ? (
      <span className="text-ink-3">neither</span>
    ) : (
      <span className="text-ink-3">open</span>
    );
  return (
    <>
      <td className="fig px-2.5 py-1.5 text-right text-ink-3">{o.r != null ? num(o.r) : "—"}</td>
      <td className="fig px-2.5 py-1.5 text-right up">{rTxt(o.mfe_r)}</td>
      <td className="fig px-2.5 py-1.5 text-right down">{o.mae_r == null ? "—" : `−${o.mae_r.toFixed(1)}R`}</td>
      <td className="px-2.5 py-1.5 text-right text-[11.5px]">{verdict}</td>
      <td className={cn("fig px-2.5 py-1.5 text-right", rHue(o.ret_30m_r))}>{rTxt(o.ret_30m_r)}</td>
      <td className={cn("fig px-2.5 py-1.5 text-right", rHue(o.ret_60m_r))}>{rTxt(o.ret_60m_r)}</td>
      <td className={cn("fig px-2.5 py-1.5 text-right", rHue(o.ret_close_r))}>{rTxt(o.ret_close_r)}</td>
    </>
  );
}

function Stats({ stats }: { stats: ScanStats | null }) {
  if (!stats) return null;
  return (
    <section className="px-3 pt-2" aria-label="Signal record">
      <div className="flex items-baseline gap-3">
        <p className="qt-cap text-[10.5px] text-ink-3">Record · last {stats.days} sessions</p>
        <p className="text-[11.5px] text-ink-3">
          {stats.total} settled (L)/(E) signals{stats.from && stats.to ? ` · ${stats.from} to ${stats.to}` : ""} · +1R
          before the Pine&apos;s stop idea, conservative on a bar that touched both
        </p>
      </div>
      {stats.total === 0 || stats.groups.length === 0 ? (
        <p className="mt-2 text-[12px] text-ink-3">
          No settled signals yet — the record fills as sessions close. It takes a few weeks before these numbers mean
          anything.
        </p>
      ) : (
        <table className="mt-2 w-full max-w-[760px] border-collapse text-left text-[12px]">
          <thead>
            <tr className="border-b border-ring">
              {["Group", "Signals", "Reached +1R", "Avg at close", "Avg best", "Avg worst"].map((h, i) => (
                <th key={h} scope="col" className={cn("qt-cap px-2.5 py-1.5 text-[10.5px] font-semibold text-ink-3", i > 0 && "text-right")}>
                  {h}
                </th>
              ))}
            </tr>
          </thead>
          <tbody>
            {stats.groups.map((g) => (
              <tr key={g.key} className="border-b border-ring/60">
                <td className="px-2.5 py-1.5 text-ink-2">{g.key}</td>
                <td className="fig px-2.5 py-1.5 text-right text-ink">
                  {g.n}
                  {g.n < SMALL && <span className="qt-cap ml-1.5 text-[9px] text-ink-3">too few</span>}
                </td>
                <td className={cn("fig px-2.5 py-1.5 text-right", g.n < SMALL ? "text-ink-3" : "text-ink")}>
                  {g.win_1r == null ? "—" : `${Math.round(g.win_1r * 100)}%`}
                </td>
                <td className={cn("fig px-2.5 py-1.5 text-right", rHue(g.avg_close_r))}>{rTxt(g.avg_close_r)}</td>
                <td className="fig px-2.5 py-1.5 text-right up">{rTxt(g.avg_mfe_r)}</td>
                <td className="fig px-2.5 py-1.5 text-right down">
                  {g.avg_mae_r == null ? "—" : `−${g.avg_mae_r.toFixed(1)}R`}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      )}
    </section>
  );
}

function dayName(iso: string): string {
  const d = new Date(`${iso}T12:00:00Z`);
  return Number.isNaN(d.getTime())
    ? iso
    : d.toLocaleDateString("en-US", { weekday: "short", month: "short", day: "numeric", timeZone: "UTC" });
}
