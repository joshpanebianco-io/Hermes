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
import { UI_CLASSES, UI_COOKIE, uiClass, type UiMode } from "@/lib/ui";
import { DEFAULT_ALERTS, TEST_ALERT, setAlertPrefs, useAlertPrefs, type AlertKind } from "@/lib/alerts";
import { segItem } from "@/lib/seg";
import { oneOf, usePersisted } from "@/lib/usePersisted";
import { setLegacyViews, useLegacyViews } from "@/lib/legacyViews";
import { cn } from "@/lib/cn";
import type { PriceFeed } from "@/types/feed";

/**
 * Settings — the interface, the price feed (Data), the alerts and the colour presets.
 *
 * THE PALETTE IS GEXYGEN'S, APPLIED TO `<html>`, LIVE, AND WRITTEN TO A COOKIE.
 * The custom properties go on the document element rather than a wrapper for the
 * same reason GEXYGEN puts them there: anything reading a token with
 * `getComputedStyle` reads it from the root, and a theme scoped to a nested node
 * would style the DOM and leave those readers on the compiled defaults. The cookie
 * means the server renders the first paint already themed instead of flashing
 * green and pink and then switching.
 *
 * A PRESET IS THE WHOLE CHOICE (owner, 2026-11-13: "can we get rid of the chrome
 * customisation data hue customisation, frame light and lets remove that from the
 * app as well"). Three sections went that day. Data hues and Chrome each opened a
 * swatch picker per slot (calls, puts, the flip and spot; the tab underline, the
 * mark's rings, the wordmark and the frame's two hues), so any slot could wear any
 * of seventeen hues. Frame light chose the light that ran round the window's edge
 * (travel, breathe or off), and the light itself went with its switch
 * (lib/useFrameLight.ts and the ring's rules in globals.css are deleted). What a
 * preset sets is unchanged: every slot at once, the two frame hues included, which
 * are still the light behind Luminous Glass and the lit state of its pills.
 *
 * A HAND-MIXED PALETTE IS STILL HONOURED. A cookie written by the old pickers that
 * matches no preset keeps drawing as it was, the Presets card calls it "custom",
 * and choosing any preset (or Reset) replaces it; there is no way back to a mix
 * from here.
 *
 * WHAT WAS NEVER SETTABLE. The five desk hues on the wire, the surfaces and the
 * ink ramp. The desk hues are identity tags that have to stay distinguishable from
 * each other at equal value, and letting a preset move them would let a headline
 * rail collide with the up/down palette — a green rail reading as "bullish" is the
 * one confusion this palette is built to avoid.
 *
 * ONE SECTION AT A TIME (owner, 2026-11-05: "each section actually be it's own
 * seperate tab, just to make it cleaner"). It was one long scroll of eight
 * modules, with Presets below the fold. The open section is remembered like every
 * other choice; a remembered section that no longer exists opens Interface.
 */

const SECTIONS = [
  { key: "interface", label: "Interface" },
  { key: "data", label: "Data" },
  { key: "alerts", label: "Alerts" },
  { key: "presets", label: "Presets" },
] as const;
type Section = (typeof SECTIONS)[number]["key"];

/**
 * The interface — Quiet (GEXYGEN's flat, hairline chassis) or Luminous Glass
 * (GEXYGEN's other one: the deep ground and the glass cards, on Quiet's layout).
 * Quiet is the default. Classic, the carded neon one this terminal shipped with, sat
 * here as a third choice until the owner had it removed on 2026-11-11 (lib/ui.ts).
 */
const UIS: { key: UiMode; label: string; hint: string }[] = [
  { key: "quiet", label: "Quiet", hint: "Flat chrome on one grey ramp, hairlines instead of cards, IBM Plex" },
  { key: "lum", label: "Luminous Glass", hint: "Cards of lit glass over a soft light, pill controls, a plain sans with JetBrains Mono figures, 10% larger on a wide screen — the same pages as Quiet" },
  { key: "side", label: "Sidebar", hint: "Every page and view listed down the left; across the top the page's name, the index prices, the search and the clock; plain dark cards — the same pages as Luminous Glass" },
];

export function Settings({
  theme,
  onTheme,
  ui,
  onUi,
}: {
  theme: ThemeChoice;
  onTheme: (t: ThemeChoice) => void;
  ui: UiMode;
  onUi: (v: UiMode) => void;
}) {
  const [section, setSection] = usePersisted<Section>(
    "settings.section",
    "interface",
    oneOf(...SECTIONS.map((s) => s.key)),
  );
  const active = matchPreset(theme);
  const legacyViews = useLegacyViews();

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
    // Luminous rides on Quiet and Sidebar on Luminous (lib/ui.ts): a mode wears its own
    // class and those it rides on, and Quiet's is never off.
    const wears = uiClass(m).split(" ");
    for (const c of UI_CLASSES) document.documentElement.classList.toggle(c, wears.includes(c));
  };

  return (
    <main className="flex min-h-0 flex-1 flex-col">
      {/* The tabs and what they open share one centred column (owner, 2026-11-06), or
          on a wide screen the tabs sit far to the left of the page they control.
          `qt-mast`: under Luminous the strip is a band like the one over the Scanner,
          Futures and Sectors; it was the one row of tabs lying on the bare ground. */}
      <div className="qt-mast flex shrink-0 flex-wrap items-center justify-center gap-x-3 gap-y-1 border-b border-ring px-3 py-1.5 qt:px-6">
        {/* `seg-tabs`: the same tabs as the Stocks and Futures views (globals.css). */}
        <span className="seg seg-tabs max-w-full justify-center" role="tablist" aria-label="Settings">
          {SECTIONS.map((s) => (
            <button
              key={s.key}
              type="button"
              role="tab"
              aria-selected={section === s.key}
              onClick={() => setSection(s.key)}
              {...segItem(section === s.key)}
            >
              {s.label}
            </button>
          ))}
        </span>
      </div>
      {/*
        * ONE CARD UNDER THE BAND, TO THE FOOT OF THE PAGE (owner, 2026-11-13: "for settings
        * can we make it one whole card that takes up the res tof the area in the middle?
        * looks yuck right now"). It was two or three narrow cards stacked in a 1040px
        * column with bare ground under them and either side. The frame and the sheet are
        * the Scanner's and the Sectors page's: under Luminous the band and the sheet join
        * into one card (globals.css, "the band under the header is the top of the card
        * below it"), and the sections are parts of it, parted by a rule, not cards of their own.
        */}
      <div className="qt-frame mx-3 mb-3 flex min-h-0 flex-1 flex-col overflow-hidden rounded-[6px] border border-ring">
      <div className="qt-sheet min-h-0 flex-1 overflow-y-auto">
      <div className="mx-auto flex w-full max-w-[1160px] min-w-0 flex-col px-4 py-2 qt:px-8 qt:py-3">
        {section === "interface" && (
          <Part title="Interface" sub="the chassis the terminal is drawn in">
            {UIS.map((o) => (
              <Choice key={o.key} label={o.label} hint={o.hint} on={ui === o.key} onPick={() => setUi(o.key)} />
            ))}
          </Part>
        )}
        {/* The Stocks tab's old views, for a week while Today settles (lib/legacyViews.ts). */}
        {section === "interface" && (
          <Part title="Stocks views" sub="Today replaced Setups, Breakouts, Extended hours and Day 2/3 on 13 Nov">
            <Choice
              label="Scanner, Charts and Record"
              hint="One list that changes with the time of day: the evening's movers, then what is in play into the open, then the open's triggers, then the session's setups"
              on={!legacyViews}
              onPick={() => setLegacyViews(false)}
            />
            <Choice
              label="Also the old four"
              hint="Setups, Breakouts, Extended hours and Day 2/3 back in the strip beside the Scanner, for this week only"
              on={legacyViews}
              onPick={() => setLegacyViews(true)}
            />
          </Part>
        )}

        {section === "data" && <PriceFeedPart />}

        {section === "alerts" && <Alerts />}

        {section === "presets" && (
        <Part
          title="Presets"
          sub={active ? active.name : "custom"}
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
          <div className="grid grid-cols-2 gap-px overflow-hidden rounded-[6px] border border-ring/60 bg-ring/40 sm:grid-cols-3">
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
        </Part>
        )}
      </div>
      </div>
      </div>
    </main>
  );
}

/**
 * One section of the Settings card: its title and what it is for, then its rows. Not a
 * card of its own (a Module is): the sections are parts of the one card, parted by a rule.
 */
function Part({
  title,
  sub,
  right,
  children,
}: {
  title: string;
  sub?: string;
  right?: React.ReactNode;
  children: React.ReactNode;
}) {
  return (
    <section className="border-b border-ring/60 py-4 last:border-b-0" aria-label={title}>
      <div className="mb-2 flex items-baseline gap-2 px-1">
        <h2 className="module-title">{title}</h2>
        {sub && <span className="truncate text-[11.5px] text-ink-3 qt:text-[12.5px]">{sub}</span>}
        {right && <div className="ml-auto flex items-center gap-2">{right}</div>}
      </div>
      {children}
    </section>
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

/* ---------------------------------------------------------------- alerts */

const KIND_OPTS: { key: AlertKind; label: string; hint: string }[] = [
  { key: "L", label: "(L) retest", hint: "A broken level retested with the 8 EMA wave at it" },
  { key: "E", label: "(E) trigger", hint: "After an extended run: a pullback into the 8 EMA wave, then its candle's high or low broken" },
  { key: "V", label: "(V) VWAP retest", hint: "After an extended run: VWAP retested and held, like the (L) at a level" },
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
    <Part title="Alerts" sub="the scanner's signals, raised on every tab">
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
    </Part>
  );
}

/**
 * Where live prices come from (server sources/webull.py `feed_mode`). WEBULL BESIDE YAHOO,
 * OR YAHOO ALONE (owner, 2026-11-18: "make sure our current implementation is kept as a
 * fallback so it's easy to revert and switch between"): Webull's trades go into the same
 * books as Yahoo's stream and the newer trade wins, so Webull on is Yahoo plus Webull, and
 * Yahoo only is the app exactly as it was. The choice is the collector's, kept across
 * restarts, and applies within seconds; the line under it is each feed's health, read
 * again every ten seconds while the tab is open. Since 2026-11-19 Webull is two parts: the
 * live connection's hundred names, and snapshots of every other name the app watches.
 */
function PriceFeedPart() {
  const [f, setF] = useState<PriceFeed | null>(null);
  const [err, setErr] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  const take = (r: Response, d: (PriceFeed & { error?: string }) | null) => {
    if (!r.ok || !d || d.error) setErr(d?.error ?? `HTTP ${r.status}`);
    else {
      setF(d);
      setErr(null);
    }
  };
  const load = useCallback(async () => {
    try {
      const r = await fetch("/api/feed", { cache: "no-store" });
      take(r, (await r.json().catch(() => null)) as (PriceFeed & { error?: string }) | null);
    } catch (e) {
      setErr(String(e));
    }
  }, []);
  useEffect(() => {
    void load();
    const id = window.setInterval(() => void load(), 10_000);
    return () => window.clearInterval(id);
  }, [load]);

  const pick = async (feed: "webull" | "yahoo") => {
    setBusy(true);
    try {
      const r = await fetch("/api/feed", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ feed }),
      });
      take(r, (await r.json().catch(() => null)) as (PriceFeed & { error?: string }) | null);
    } catch (e) {
      setErr(String(e));
    } finally {
      setBusy(false);
    }
  };

  const w = f?.webull;
  const s = f?.feed === "webull" ? f.snapshots : null;
  const snaps = !s?.on
    ? null
    : s.error
      ? `Snapshots: ${s.error}`
      : s.idle
        ? "Snapshots wait for the pre-market"
        : s.every_sec
          ? `Snapshots ${s.names} more every ${Math.round(s.every_sec)}s`
          : null;
  const health = err
    ? `Collector not answering: ${err}`
    : !f
      ? "Reading…"
      : [
          f.feed === "webull"
            ? w?.ok
              ? `Webull live, ${w.items} names`
              : `Webull not live yet${w?.notes?.[0] || w?.error ? `: ${w?.notes?.[0] ?? w?.error}` : ""}`
            : "Webull off",
          snaps,
          `Yahoo stream ${f.yahoo.ok ? "live" : "down"}, ${f.yahoo.items} names`,
          f.why.charAt(0).toUpperCase() + f.why.slice(1),
        ]
          .filter(Boolean)
          .join(" · ");

  return (
    <Part title="Price feed" sub="where live prices come from; a switch applies within seconds">
      <Choice
        label="Webull"
        hint={
          f && !f.webull_keys
            ? "Needs WEBULL_APP_KEY and WEBULL_APP_SECRET in .env.local"
            : "Your Webull account's real-time trades (Nasdaq Basic), about half a second behind the market, for the 100 names that matter most (open charts, tracked names, the Scanner list; Webull's limit), and a Webull snapshot of every other name the app watches every 10 seconds (20 outside the session); Yahoo's stream runs beside both, and the newer trade wins"
        }
        on={f?.feed === "webull"}
        onPick={() => void pick("webull")}
        disabled={busy || !f || !f.webull_keys}
      />
      <Choice
        label="Yahoo only"
        hint="The app as it was before Webull: Yahoo's free stream and five-second quotes, which have run minutes late on busy days"
        on={f?.feed === "yahoo"}
        onPick={() => void pick("yahoo")}
        disabled={busy || !f}
      />
      <p className={cn("px-3 pt-2 text-[9.5px] qt:text-[11.5px]", err ? "text-warn" : "text-ink-3")}>{health}</p>
    </Part>
  );
}

/*
 * NO OPTIONS SECTION (owner, 2026-11-13: "can we remove the options tab too in
 * settings? what does that even do?"). It held two things for the Stocks tab's
 * contract helper: a risk per trade in dollars, which added a contract count beside
 * each suggested contract (a Size column on the Options columns, "N for a $X budget"
 * in the slide-out), and a switch that turned same-day contracts off so every name
 * got the weekly. Both went with it (lib/optionsPrefs.ts is deleted): the helper
 * gives the premium at risk per contract and no count, and the contract is always
 * the collector's expiry rule's pick.
 */

/*
 * NO KEYBOARD SECTION (owner, 2026-11-11: "can we remove the key board controls and
 * from the settings too"). It listed the single-key controls (1 to 7 for the tabs, A
 * for Hermes, F, V, the arrows), and they went with it. A remembered section of
 * "keyboard" falls back to Interface.
 */

/** One option of a Settings choice: a square marker, its name, and what it does. */
function Choice({
  label,
  hint,
  on,
  onPick,
  disabled,
}: {
  label: string;
  hint: string;
  on: boolean;
  onPick: () => void;
  disabled?: boolean;
}) {
  return (
    <button
      type="button"
      onClick={onPick}
      disabled={disabled}
      aria-pressed={on}
      // NO LIT BOX ON THE CHOSEN ROW (owner, 2026-11-13: "remove the hihglighted box from
      // the setting selected in interface"): the filled mark with its tick says which.
      className="hit flex w-full items-center gap-3 border-b border-ring/40 px-3 py-2 text-left last:border-b-0 disabled:pointer-events-none disabled:opacity-50"
    >
      {/* A FILLED MARK WITH A TICK, NOT A BRIGHTER OUTLINE (design review, 2026-11-11):
          the chosen row's box was the same empty square with a lighter edge, and read
          as unticked beside a row that was lit. */}
      <span
        aria-hidden
        className={cn(
          "grid h-[14px] w-[14px] shrink-0 place-items-center rounded-full border",
          on ? "border-ink bg-ink" : "border-ring-2",
        )}
      >
        {on && (
          <svg viewBox="0 0 12 12" className="h-[9px] w-[9px]" style={{ color: "var(--bg)" }}>
            <path d="M2.6 6.3 5 8.6 9.4 3.7" fill="none" stroke="currentColor" strokeWidth="1.9" strokeLinecap="round" strokeLinejoin="round" />
          </svg>
        )}
      </span>
      {/* 170px: "Luminous Glass" and "Today, Charts and Record" broke over two and three
          lines in the 70px the column was. The hint wraps rather than ending in "Lu…". */}
      <span className={cn("w-[170px] shrink-0 text-[11px] qt:text-[12.5px]", on ? "text-ink" : "text-ink-2")}>{label}</span>
      <span className="min-w-0 flex-1 text-[9.5px] text-ink-4 qt:text-[11.5px] qt:text-ink-3">{hint}</span>
    </button>
  );
}

