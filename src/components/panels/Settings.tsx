"use client";

import { useCallback, useState } from "react";
import {
  DEFAULT_THEME,
  HUES,
  PRESETS,
  THEME_COOKIE,
  type HueId,
  type ThemeChoice,
  matchPreset,
  themeVars,
} from "@/lib/theme";
import { Module } from "@/components/ui/Module";
import type { FrameFx } from "@/lib/useFrameLight";
import { cn } from "@/lib/cn";

/**
 * Settings — the palette, imported wholesale from GEXYGEN.
 *
 * APPLIED TO `<html>`, LIVE, AND WRITTEN TO A COOKIE. The custom properties go
 * on the document element rather than a wrapper for the same reason GEXYGEN
 * puts them there: anything reading a token with `getComputedStyle` reads it
 * from the root, and a theme scoped to a nested node would style the DOM and
 * leave those readers on the compiled defaults. The cookie means the server
 * renders the first paint already themed instead of flashing green and pink and
 * then switching.
 *
 * WHAT IS DELIBERATELY NOT SETTABLE. The five desk hues on the wire, the
 * surfaces and the ink ramp. The desk hues are identity tags that have to stay
 * distinguishable from each other at equal value, and letting a preset move them
 * would let a headline rail collide with the up/down palette — a green rail
 * reading as "bullish" is the one confusion this palette is built to avoid.
 *
 * THE WARNING ON THIS PAGE IS REAL. Retinting calls to blue here gives a blue
 * call wall in this browser, a blue one in GEXYGEN if it is themed to match,
 * and a teal one in NinjaTrader and on the TradingView indicator — those read
 * from their own source files and cannot be reached from here.
 */

const SIDE_SLOTS: { key: keyof ThemeChoice; label: string; hint: string }[] = [
  { key: "call", label: "Calls / up", hint: "Call walls, positive gamma, and every up move" },
  { key: "put", label: "Puts / down", hint: "Put walls, negative gamma, and every down move" },
  { key: "flip", label: "Gamma flip", hint: "The regime boundary, and anything demanding attention" },
  { key: "neutral", label: "Spot", hint: "Spot and the figures that carry no side" },
];

const CHROME_SLOTS: { key: keyof ThemeChoice; label: string; hint: string }[] = [
  { key: "tabs", label: "Tab underline", hint: "The active tab marker" },
  { key: "iconA", label: "Mark ring A", hint: "The larger ring of the logo" },
  { key: "iconB", label: "Mark ring B", hint: "The smaller ring" },
  { key: "titleA", label: "Wordmark A", hint: "Left end of the HERMESX gradient" },
  { key: "titleB", label: "Wordmark B", hint: "Right end of it" },
  // These described a hairline across the top edge, which no longer exists —
  // it was deleted when the frame effects arrived, because a static light and
  // a moving one on the same chassis read as a mistake. They now colour the
  // comet and the breathing ring.
  { key: "frameA", label: "Frame light A", hint: "The comet's tail, and breathe's first hue" },
  { key: "frameB", label: "Frame light B", hint: "The comet's head, and breathe's second hue" },
];

/**
 * The chassis light.
 *
 * OFF IS A REAL CHOICE, not a disabled state — a terminal that is being read
 * for hours should be allowed to sit still. Travel is the comet; breathe is the
 * whole perimeter glowing in place. Both run on the chrome hues, so whatever
 * the palette is set to, the frame agrees with it.
 */
const FX: { key: FrameFx; label: string; hint: string }[] = [
  { key: "travel", label: "Travel", hint: "A charge running the perimeter, ten seconds a lap" },
  { key: "breathe", label: "Breathe", hint: "The whole frame glowing in place, alternating the two hues" },
  { key: "off", label: "Off", hint: "A plain chassis with no light at all" },
];

export function Settings({
  theme,
  onTheme,
  fx,
  onFx,
}: {
  theme: ThemeChoice;
  onTheme: (t: ThemeChoice) => void;
  fx: FrameFx;
  onFx: (v: FrameFx) => void;
}) {
  const [open, setOpen] = useState<keyof ThemeChoice | null>(null);
  const active = matchPreset(theme);

  const set = useCallback(
    (next: ThemeChoice) => {
      onTheme(next);
      // A year, path-scoped to the app. Nothing here is sensitive — it is a
      // list of hue names — so there is no reason for it to be httpOnly, and
      // the client has to be able to write it without a round trip.
      document.cookie = `${THEME_COOKIE}=${encodeURIComponent(
        JSON.stringify(next),
      )}; path=/; max-age=31536000; samesite=lax`;
      const vars = themeVars(next);
      for (const [k, v] of Object.entries(vars)) {
        document.documentElement.style.setProperty(k, v);
      }
    },
    [onTheme],
  );

  return (
    <div className="min-h-0 flex-1 overflow-y-auto p-2">
      <div className="flex min-w-0 flex-col gap-2">
        <Module
          title="Presets"
          sub={active ? active.name : "custom"}
          bodyClassName="px-0 py-0"
          right={
            <button
              type="button"
              onClick={() => set(DEFAULT_THEME)}
              className="fig hit rounded border border-ring px-2 py-px text-[9.5px] leading-[15px] text-ink-4 hover:text-ink-2"
            >
              RESET
            </button>
          }
        >
          <div className="grid grid-cols-2 gap-px bg-ring/40 sm:grid-cols-3">
            {PRESETS.map((p) => {
              const on = active?.id === p.id;
              return (
                <button
                  key={p.id}
                  type="button"
                  onClick={() => set(p.theme)}
                  className={cn(
                    "hit flex flex-col gap-1.5 bg-surface px-3 py-2 text-left",
                    on && "bg-ink/[0.07]",
                  )}
                >
                  <div className="flex items-center gap-1.5">
                    <Swatches t={p.theme} />
                    <span className={cn("text-[11px]", on ? "text-ink" : "text-ink-2")}>
                      {p.name}
                    </span>
                    {p.isDefault && (
                      <span className="fig text-[8.5px] text-ink-4 uppercase">default</span>
                    )}
                  </div>
                </button>
              );
            })}
          </div>
        </Module>

        <Module title="Frame light" sub="the chassis effect" bodyClassName="px-0 py-0">
          {FX.map((o) => (
            <button
              key={o.key}
              type="button"
              onClick={() => onFx(o.key)}
              className={cn(
                "hit flex w-full items-center gap-2 border-b border-ring/40 px-3 py-1.5 text-left last:border-b-0",
                fx === o.key && "bg-ink/[0.06]",
              )}
            >
              <span
                aria-hidden
                className="h-[13px] w-[13px] shrink-0 rounded-[3px] border"
                style={{
                  borderColor: fx === o.key ? "var(--frame-a)" : "var(--ring-2)",
                  background:
                    fx === o.key
                      ? "color-mix(in oklab, var(--frame-a) 22%, transparent)"
                      : "transparent",
                }}
              />
              <span className={cn("w-[70px] shrink-0 text-[11px]", fx === o.key ? "text-ink" : "text-ink-2")}>
                {o.label}
              </span>
              <span className="min-w-0 flex-1 truncate text-[9.5px] text-ink-4">{o.hint}</span>
            </button>
          ))}
        </Module>

        <Module title="Data hues" sub="these mean something" bodyClassName="px-0 py-0">
          <p className="border-b border-ring/40 px-3 py-2 text-[10.5px] leading-relaxed text-ink-3">
            One hue per side, and hierarchy inside a hue carried by value rather than by a second
            colour. Retinting these changes what a wall looks like <em>in this browser only</em> —
            NinjaTrader and the TradingView indicator read their own files and cannot be reached
            from here, so the cross-surface promise is what you are trading away.
          </p>
          {SIDE_SLOTS.map((s) => (
            <Slot
              key={s.key}
              slot={s}
              theme={theme}
              open={open === s.key}
              onOpen={() => setOpen(open === s.key ? null : s.key)}
              onPick={(id) => set({ ...theme, [s.key]: id })}
            />
          ))}
        </Module>

        <Module title="Chrome" sub="decoration — free to be anything" bodyClassName="px-0 py-0">
          {CHROME_SLOTS.map((s) => (
            <Slot
              key={s.key}
              slot={s}
              theme={theme}
              open={open === s.key}
              onOpen={() => setOpen(open === s.key ? null : s.key)}
              onPick={(id) => set({ ...theme, [s.key]: id })}
            />
          ))}
        </Module>
      </div>
    </div>
  );
}

/** The four data hues as a row of chips — a preset's identity at a glance. */
function Swatches({ t }: { t: ThemeChoice }) {
  const ids: HueId[] = [t.call, t.put, t.flip, t.neutral];
  return (
    <span className="flex shrink-0 gap-[2px]">
      {ids.map((id, i) => {
        const h = HUES.find((x) => x.id === id);
        return (
          <span
            key={`${id}-${i}`}
            className="h-[11px] w-[11px] rounded-[2px]"
            style={{ background: h?.mark ?? "transparent" }}
          />
        );
      })}
    </span>
  );
}

function Slot({
  slot,
  theme,
  open,
  onOpen,
  onPick,
}: {
  slot: { key: keyof ThemeChoice; label: string; hint: string };
  theme: ThemeChoice;
  open: boolean;
  onOpen: () => void;
  onPick: (id: HueId) => void;
}) {
  const current = theme[slot.key] as HueId;
  const h = HUES.find((x) => x.id === current);
  return (
    <div className="border-b border-ring/40 last:border-b-0">
      <button
        type="button"
        onClick={onOpen}
        className="hit flex w-full items-center gap-2 px-3 py-1.5 text-left"
      >
        <span
          className="h-[13px] w-[13px] shrink-0 rounded-[3px]"
          style={{ background: h?.mark }}
        />
        <span className="w-[92px] shrink-0 text-[11px] text-ink-2">{slot.label}</span>
        <span className="fig text-[10px] text-ink-3">{h?.name}</span>
        <span className="min-w-0 flex-1 truncate text-[9.5px] text-ink-4">{slot.hint}</span>
        <span className="fig shrink-0 text-[9px] text-ink-4">{open ? "▲" : "▼"}</span>
      </button>
      {open && (
        <div className="flex flex-wrap gap-1 px-3 pb-2">
          {HUES.map((x) => (
            <button
              key={x.id}
              type="button"
              onClick={() => onPick(x.id)}
              title={x.name}
              className={cn(
                "h-[20px] w-[20px] rounded-[3px] border transition-transform hover:scale-110",
                x.id === current ? "border-ink" : "border-transparent",
              )}
              style={{ background: x.mark }}
            >
              <span className="sr-only">{x.name}</span>
            </button>
          ))}
        </div>
      )}
    </div>
  );
}
