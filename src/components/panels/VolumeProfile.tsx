"use client";

import type { VPAssets } from "@/types/terminal";
import { Module } from "@/components/ui/Module";
import { Tick } from "@/components/ui/Tick";
import { num } from "@/lib/format";
import { cn } from "@/lib/cn";
import { segItem } from "@/lib/seg";
import { oneOf, usePersisted } from "@/lib/usePersisted";

/**
 * Volume profile levels — where the volume traded, beside where the dealers
 * hedge.
 *
 * THE WINDOWS FOLLOW THE OWNER'S OWN SESSION LOGIC (spec, 2026-09-01): the
 * previous RTH profile is every session's reference; the completed overnight
 * appears only once New York is trading (before that it IS the developing
 * profile, and one set of numbers should not wear two names); and the
 * developing row is anchored 18:00 ET through Asia and London, 09:30 once
 * the cash opens.
 *
 * EACH ROW KEEPS ITS OWN TRACK — the window's low to its high, the value area
 * as a filled band, the POC as the bright tick, the live price as the marker.
 * This was Session Ranges' grammar too until that panel moved to one shared
 * price axis (2026-09-22), because its read is sessions AGAINST each other.
 * This panel's read is where value sits INSIDE a window, which is the one
 * thing a private scale is good at, so it stays.
 *
 * "≈" IN THE SUB IS A CLAIM, NOT DECORATION: these are built from 5-minute
 * bars with volume spread across each bar's range. Zones, not ticks.
 */

export function VolumeProfile({
  data,
  ageMin,
  error,
}: {
  data: VPAssets;
  ageMin?: number | null;
  error?: string | null;
}) {
  const assets = data?.assets ?? {};
  const keys = Object.keys(assets);
  const [sel, setSel] = usePersisted<string>("vp.asset", "NQ", oneOf("NQ", "ES", "GC"));
  const active = assets[sel] ?? assets[keys[0]];

  return (
    <Module
      title="Volume profile"
      sub="≈ 5m bars"
      ageMin={ageMin}
      error={error}
      bodyClassName="px-0 py-0"
      right={
        keys.length > 1 && (
          <div className="seg">
            {keys.map((k) => (
              <button
                key={k}
                type="button"
                onClick={() => setSel(k)}
                {...segItem(k === sel, { className: "text-[10px] normal-case tracking-normal" })}
              >
                {k}
              </button>
            ))}
          </div>
        )
      }
    >
      {!active ? (
        <p className="px-3 py-5 text-center text-[11px] text-ink-3">No bars yet.</p>
      ) : !active.ok ? (
        <p className="px-3 py-5 text-center text-[11px] text-ink-3">
          {active.error ?? "unavailable"}
        </p>
      ) : (
        <div>
          {/* The three column names, once — the calendar's pattern. */}
          <div className="flex items-baseline gap-2 border-b border-ring/40 px-3 pt-1 pb-0.5">
            <span className="w-[72px] shrink-0 qt:w-[100px]" />
            <span className="min-w-0 flex-1" />
            <span
              className="fig w-[56px] shrink-0 text-right text-[8.5px] tracking-wide text-ink-3"
              title="Value area low — the bottom of the 70% acceptance zone"
            >
              val
            </span>
            <span
              className="fig w-[60px] shrink-0 text-right text-[8.5px] tracking-wide text-ink-3"
              title="Point of control — the price with the most traded volume; the magnet"
            >
              poc
            </span>
            <span
              className="fig w-[56px] shrink-0 text-right text-[8.5px] tracking-wide text-ink-3"
              title="Value area high — the top of the 70% acceptance zone"
            >
              vah
            </span>
          </div>
          <ul className="py-0.5">
            {active.rows.map((r) => (
              <Row key={r.key} r={r} last={active.last ?? null} />
            ))}
          </ul>
        </div>
      )}
    </Module>
  );
}

function Row({
  r,
  last,
}: {
  r: VPAssets["assets"][string]["rows"][number];
  last: number | null;
}) {
  const span = Math.max(r.high - r.low, 1e-9);
  const pos = (p: number) => Math.max(0, Math.min(100, ((p - r.low) / span) * 100));
  const live = r.kind === "live";
  // The live marker only belongs on the row whose window contains "now".
  const marker = live && last !== null ? Math.max(-2, Math.min(102, ((last - r.low) / span) * 100)) : null;

  return (
    <li
      className="hit flex items-baseline gap-2 px-3 py-[4px]"
      title={`${r.label} · ${r.date} ${r.start_et}-${r.end_et}
Track: this window's full range, ${num(r.low)}-${num(r.high)}. Shaded band: the value area (VAL-VAH), where 70% of volume traded. Amber tick: POC, the price with the most volume. White marker: live price (developing window only).
${r.bars} bars · bin ${r.bin}`}
    >
      <span
        className={cn(
          "fig w-[72px] shrink-0 text-[10px] qt:w-[100px] qt:font-sans qt:whitespace-nowrap",
          live ? "text-ink-2" : "text-ink-3",
        )}
      >
        {r.label}
      </span>
      <span className="relative h-[9px] min-w-0 flex-1 self-center rounded-sm bg-ring/40">
        {/* The 70% value area. */}
        <span
          title="Value area: VAL to VAH, where 70% of this window's volume traded"
          className="absolute inset-y-0 rounded-sm"
          style={{
            left: `${pos(r.val)}%`,
            width: `${Math.max(pos(r.vah) - pos(r.val), 1)}%`,
            background: "color-mix(in oklab, var(--em) 45%, transparent)",
          }}
        />
        {/* The POC: the magnet, bright. */}
        <span
          title="POC: the price with the most traded volume"
          className="absolute top-1/2 h-[13px] w-[2px] -translate-y-1/2 rounded-full"
          style={{ left: `calc(${pos(r.poc)}% - 1px)`, background: "var(--flip)" }}
        />
        {marker !== null && (
          <span
            className="absolute top-1/2 h-[11px] w-[2px] -translate-y-1/2 rounded-full"
            style={{ left: `calc(${marker}% - 1px)`, background: "var(--spot)" }}
            title="Live price"
          />
        )}
      </span>
      <Tick
        value={num(r.val, 0)}
        className="fig w-[56px] shrink-0 text-right text-[10.5px] text-ink-3"
      />
      <Tick
        value={num(r.poc, 0)}
        className="fig w-[60px] shrink-0 text-right text-[11px] text-ink"
      />
      <Tick
        value={num(r.vah, 0)}
        className="fig w-[56px] shrink-0 text-right text-[10.5px] text-ink-3"
      />
    </li>
  );
}
