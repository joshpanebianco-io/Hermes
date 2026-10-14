"use client";

import { useCallback, useEffect, useState } from "react";
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
import { UI_COOKIE, type UiMode } from "@/lib/ui";
import { DEFAULT_ALERTS, TEST_ALERT, setAlertPrefs, useAlertPrefs, type AlertKind } from "@/lib/alerts";
import { segItem } from "@/lib/seg";
import { setOptionsPrefs, useOptionsPrefs } from "@/lib/optionsPrefs";
import type { ExpiryRule, Watchlist } from "@/types/scanner";
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
/**
 * The interface — Quiet (GEXYGEN's flat, hairline chassis) or Classic (the
 * carded neon one this terminal shipped with). Quiet is the default; Classic is
 * kept because a redesign you cannot step back from is a bet, not a choice.
 */
const UIS: { key: UiMode; label: string; hint: string }[] = [
  { key: "quiet", label: "Quiet", hint: "Flat chrome on one grey ramp, hairlines instead of cards, IBM Plex" },
  { key: "classic", label: "Classic", hint: "Carded panes, mono caps headers and the neon chrome" },
];

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
  ui,
  onUi,
}: {
  theme: ThemeChoice;
  onTheme: (t: ThemeChoice) => void;
  fx: FrameFx;
  onFx: (v: FrameFx) => void;
  ui: UiMode;
  onUi: (v: UiMode) => void;
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

  /*
   * Live, like the palette: the class goes straight onto <html> and the cookie
   * makes the server render the next load in the same interface.
   */
  const setUi = (m: UiMode) => {
    onUi(m);
    document.cookie = `${UI_COOKIE}=${m}; path=/; max-age=31536000; samesite=lax`;
    document.documentElement.classList.toggle("ui-qt", m === "quiet");
  };

  return (
    <div className="min-h-0 flex-1 overflow-y-auto p-2 qt:p-0">
      <div className="qt-stack flex min-w-0 flex-col gap-2">
        <Module title="Interface" sub="the chassis the terminal is drawn in" bodyClassName="px-0 py-0">
          {UIS.map((o) => (
            <button
              key={o.key}
              type="button"
              onClick={() => setUi(o.key)}
              className={cn(
                "hit flex w-full items-center gap-2 border-b border-ring/40 px-3 py-1.5 text-left last:border-b-0",
                ui === o.key && "bg-ink/[0.06]",
              )}
            >
              <span
                aria-hidden
                className={cn(
                  "h-[13px] w-[13px] shrink-0 rounded-[3px] border",
                  ui === o.key ? "border-ink bg-ink/20" : "border-ring-2",
                )}
              />
              <span className={cn("w-[70px] shrink-0 text-[11px] qt:text-[12.5px]", ui === o.key ? "text-ink" : "text-ink-2")}>
                {o.label}
              </span>
              <span className="min-w-0 flex-1 truncate text-[9.5px] text-ink-4 qt:text-[11.5px] qt:text-ink-3">{o.hint}</span>
            </button>
          ))}
        </Module>

        <Alerts />

        <OptionsPrefsModule />

        <Keyboard />

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

/* ---------------------------------------------------------------- alerts */

const KIND_OPTS: { key: AlertKind; label: string; hint: string }[] = [
  { key: "L", label: "(L) retest", hint: "A broken level retested with the 8 EMA wave at it" },
  { key: "E", label: "(E) trigger", hint: "The (E) candle's high or low broken in the trend's direction" },
  { key: "BO", label: "◆ Breakout", hint: "A level broken on a close — not a gap through it" },
  { key: "NEAR", label: "Near a level", hint: "90% of the way to a level; once per level per name per day" },
];

/**
 * Settings → Alerts: what the scanner announces, and how. The alerts
 * themselves run in the shell (components/shell/ScanAlerts.tsx) on every tab.
 *
 * DESKTOP NOTIFICATIONS NEED THE BROWSER'S PERMISSION, which can only be asked
 * for from a click — so they are off until "Allow" is pressed here, and the
 * row says plainly when the browser has refused, because a toggle that reads
 * "on" while the browser blocks it is the one state this must not show.
 */
function Alerts() {
  const p = useAlertPrefs();
  const [perm, setPerm] = useState<NotificationPermission | "unsupported">("default");
  useEffect(() => {
    setPerm(typeof Notification === "undefined" ? "unsupported" : Notification.permission);
  }, []);

  const allow = async () => {
    if (typeof Notification === "undefined") return;
    const r = await Notification.requestPermission();
    setPerm(r);
    if (r === "granted") setAlertPrefs({ desktop: true });
  };

  const toggleKind = (k: AlertKind) =>
    setAlertPrefs({ kinds: p.kinds.includes(k) ? p.kinds.filter((x) => x !== k) : [...p.kinds, k] });

  const row = "flex flex-wrap items-center gap-x-3 gap-y-1.5 border-b border-ring/40 px-3 py-2 last:border-b-0";
  const label = "w-[150px] shrink-0 text-[11px] text-ink-2 qt:text-[12.5px]";
  const hint = "min-w-0 flex-1 text-[9.5px] text-ink-3 qt:text-[11.5px]";

  return (
    <Module title="Alerts" sub="the scanner's signals, raised on every tab" bodyClassName="px-0 py-0">
      <div className={row}>
        <span className={label}>Alerts</span>
        <span className="seg">
          <button type="button" onClick={() => setAlertPrefs({ on: true })} {...segItem(p.on)}>
            On
          </button>
          <button type="button" onClick={() => setAlertPrefs({ on: false })} {...segItem(!p.on)}>
            Off
          </button>
        </span>
        <span className={hint}>A toast in the corner when a new signal fires on a confirmed ten-minute bar</span>
      </div>
      <div className={row}>
        <span className={label}>Desktop notifications</span>
        {perm === "granted" ? (
          <span className="seg">
            <button type="button" onClick={() => setAlertPrefs({ desktop: true })} {...segItem(p.desktop)}>
              On
            </button>
            <button type="button" onClick={() => setAlertPrefs({ desktop: false })} {...segItem(!p.desktop)}>
              Off
            </button>
          </span>
        ) : perm === "denied" ? (
          <span className="text-[11px] text-warn qt:text-[12px]">Blocked by the browser — allow notifications for localhost:3100 in its site settings</span>
        ) : perm === "unsupported" ? (
          <span className="text-[11px] text-ink-3 qt:text-[12px]">This browser has no notifications</span>
        ) : (
          <button type="button" onClick={() => void allow()} {...segItem(false, { className: "border border-ring-2" })}>
            Allow
          </button>
        )}
        <span className={hint}>Reaches you in another window or app, while this page is open in a tab</span>
      </div>
      <div className={row}>
        <span className={label}>Sound</span>
        <span className="seg">
          <button type="button" onClick={() => setAlertPrefs({ sound: true })} {...segItem(p.sound)}>
            On
          </button>
          <button type="button" onClick={() => setAlertPrefs({ sound: false })} {...segItem(!p.sound)}>
            Off
          </button>
        </span>
        <span className={hint}>Rising for a long, falling for a short</span>
      </div>
      <div className={row}>
        <span className={label}>Alert on</span>
        <span className="seg">
          {KIND_OPTS.map((k) => (
            <button key={k.key} type="button" title={k.hint} onClick={() => toggleKind(k.key)} {...segItem(p.kinds.includes(k.key))}>
              {k.label}
            </button>
          ))}
        </span>
      </div>
      <div className={row}>
        <span className={label}>Minimum score</span>
        <span className="seg">
          {([0, 40, 60] as const).map((m) => (
            <button key={m} type="button" onClick={() => setAlertPrefs({ minScore: m })} {...segItem(p.minScore === m)}>
              {m === 0 ? "Any" : `${m}+`}
            </button>
          ))}
        </span>
        <span className={hint}>Only names the scanner ranks at least this high</span>
      </div>
      <div className={row}>
        <button type="button" onClick={() => window.dispatchEvent(new Event(TEST_ALERT))} {...segItem(false, { className: "border border-ring-2" })}>
          Send a test alert
        </button>
        <button type="button" onClick={() => setAlertPrefs(DEFAULT_ALERTS)} {...segItem(false, { className: "border border-ring-2" })}>
          Reset
        </button>
        <span className={hint}>
          In a background tab Chrome checks about once a minute, so an alert can trail its bar by up to a minute
        </span>
      </div>
    </Module>
  );
}

/* ---------------------------------------------------------------- options */

/**
 * Settings → Options: the stocks desk's sizing and expiry preferences, read
 * live by the scanner's contract helper (lib/optionsPrefs.ts).
 *
 * THE BUDGET IS TYPED AS DOLLARS OF PREMIUM AT RISK, and blank means "do not
 * size" — the helper then prints the risk per contract and leaves the count
 * to you. Nothing here places an order; it is arithmetic on the screen.
 *
 * THE EXPIRY RULE IS THE COLLECTOR'S, IN ITS OWN WORDS (audit, 2026-10-14: the
 * plan, this page and the table each kept a copy, and they disagreed). It is
 * read from the watchlist route, where it rides along; offline, the line says
 * so rather than printing a copy that may be stale.
 */
function OptionsPrefsModule() {
  const p = useOptionsPrefs();
  const [draft, setDraft] = useState<string>("");
  const [rule, setRule] = useState<ExpiryRule | null>(null);
  useEffect(() => {
    let live = true;
    fetch("/api/scanner/watchlist", { cache: "no-store" })
      .then((r) => r.json() as Promise<Watchlist>)
      .then((w) => {
        if (live && w.options_rule) setRule(w.options_rule);
      })
      .catch(() => {
        /* offline: the hint says so */
      });
    return () => {
      live = false;
    };
  }, []);
  useEffect(() => {
    setDraft(p.budget != null ? String(p.budget) : "");
  }, [p.budget]);
  const commit = () => {
    const n = Number(draft.replace(/[$,\s]/g, ""));
    setOptionsPrefs({ budget: draft.trim() === "" || !Number.isFinite(n) || n <= 0 ? null : Math.round(n) });
  };
  const row = "flex flex-wrap items-center gap-x-3 gap-y-1.5 border-b border-ring/40 px-3 py-2 last:border-b-0";
  const label = "w-[150px] shrink-0 text-[11px] text-ink-2 qt:text-[12.5px]";
  const hint = "min-w-0 flex-1 text-[9.5px] text-ink-3 qt:text-[11.5px]";
  return (
    <Module title="Options" sub="the stocks desk's contract helper" bodyClassName="px-0 py-0">
      <div className={row}>
        <label htmlFor="opt-budget" className={label}>
          Risk per trade
        </label>
        <span className="flex items-center gap-1.5">
          <span className="fig text-[12px] text-ink-3">$</span>
          <input
            id="opt-budget"
            inputMode="numeric"
            value={draft}
            placeholder="not set"
            onChange={(e) => setDraft(e.target.value)}
            onBlur={commit}
            onKeyDown={(e) => {
              if (e.key === "Enter") commit();
            }}
            className="fig w-[96px] rounded-[3px] border border-ring-2 bg-bg px-2 py-[3px] text-[12px] text-ink outline-none focus:border-ink-3"
          />
        </span>
        <span className={hint}>
          Premium you are prepared to lose on one trade — the scanner then says how many contracts that buys. Blank
          prints the risk per contract only.
        </span>
      </div>
      <div className={row}>
        <span className={label}>Same-day (0DTE) contracts</span>
        <span className="seg">
          <button type="button" onClick={() => setOptionsPrefs({ zeroDte: true })} {...segItem(p.zeroDte)}>
            On
          </button>
          <button type="button" onClick={() => setOptionsPrefs({ zeroDte: false })} {...segItem(!p.zeroDte)}>
            Off
          </button>
        </span>
        <span className={hint}>
          {rule ? rule.text : "The expiry rule loads from the collector."} Off: no same-day contract on any name — the
          weekly instead.
        </span>
      </div>
    </Module>
  );
}

/* ---------------------------------------------------------------- keyboard */

const KEYS: { keys: string[]; what: string }[] = [
  { keys: ["1", "2", "3", "4"], what: "The current desk's tabs, in the order the header shows them" },
  { keys: ["D"], what: "Switch desk — Futures and Stocks & options — back to the tab you left" },
  { keys: ["↑", "↓"], what: "Scanner: walk the list, the selection and the detail pane moving together" },
  { keys: ["Enter"], what: "Scanner: open the focused row" },
];

/** The shortcuts, written down — the header's hover hints are not where anyone looks for them. */
function Keyboard() {
  return (
    <Module title="Keyboard" sub="ignored while typing in a field" bodyClassName="px-0 py-0">
      {KEYS.map((k) => (
        <div key={k.what} className="flex items-center gap-3 border-b border-ring/40 px-3 py-2 last:border-b-0">
          <span className="flex w-[150px] shrink-0 gap-1">
            {k.keys.map((x) => (
              <kbd
                key={x}
                className="fig min-w-[22px] rounded-[3px] border border-ring-2 bg-surface-2 px-1.5 py-px text-center text-[11px] text-ink-2"
              >
                {x}
              </kbd>
            ))}
          </span>
          <span className="text-[11px] text-ink-3 qt:text-[12px]">{k.what}</span>
        </div>
      ))}
    </Module>
  );
}
