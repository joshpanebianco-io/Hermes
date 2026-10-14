"use client";

import type { Clock, Quote } from "@/types/terminal";
import { dir, inMin, num, pct } from "@/lib/format";
import { cn } from "@/lib/cn";
import { Tick } from "@/components/ui/Tick";
import { HERMES_MARK_D } from "@/lib/hermesMark";
import { DESKS, tabsFor, type Desk, type Tab } from "@/lib/tabs";
import { segItem } from "@/lib/seg";
import { useNow } from "@/lib/useNow";
import { localClock, readerClock } from "@/lib/clock";

/**
 * The header rail — identity on the left, state on the right.
 *
 * THE TICKER STRIP IS NOT A CRAWL. It is a fixed row of the instruments this
 * desk actually trades, always in the same order and always in the same place.
 * A scrolling strip is the thing every finance site does and it is wrong for
 * an instrument: you cannot glance at a moving target, and the whole value of
 * a header row is that NQ is always in the same six centimetres of glass.
 */
/*
 * EACH DESK READS ITS OWN STRIP. Futures: the three books and the macro that
 * moves them. Stocks & options: the index ETFs the options trade on, the vol
 * pair that prices them (VIX for the level, VVIX for how fast it can move),
 * and the 10-year that leans on long-duration names — then how long until New
 * York opens or closes, the one clock that desk trades on.
 */
const STRIP: Record<Desk, string[]> = {
  futures: ["NQ", "ES", "GC", "VIX", "US10Y", "DXY", "WTI", "BTC"],
  stocks: ["SPY", "QQQ", "IWM", "VIX", "VVIX", "US10Y"],
};

/** "NYSE opens in 1h 20m" / "closes in 2h 05m" / a holiday — the stocks desk's clock. */
function nyClock(clock: Clock | null): { label: string; value: string; title: string } | null {
  const ny = clock?.sessions.find((x) => x.key === "newyork");
  if (!ny) return null;
  if (ny.holiday) return { label: "NYSE", value: "Holiday", title: `${ny.holiday} — US markets are closed` };
  return ny.open
    ? { label: "NY closes in", value: inMin(ny.next_min), title: "Time to the 16:00 ET close" }
    : { label: "NY opens in", value: inMin(ny.next_min), title: "Time to the next 09:30 ET open" };
}

export function Header({
  clock: rawClock,
  quotes,
  live,
  onRefresh,
  tab,
  onTab,
  desk,
  onDesk,
}: {
  clock: Clock | null;
  quotes: Quote[];
  live: boolean;
  onRefresh: () => void;
  tab: Tab;
  onTab: (t: Tab) => void;
  desk: Desk;
  onDesk: (d: Desk) => void;
}) {
  // The header owns its own second hand — the rest of the shell does not tick.
  const now = useNow(1000);
  const clock = localClock(rawClock, now);
  // The reader's own time beside New York's: the owner trades the NY session
  // from Australia, where 09:30 ET is past midnight. Null on New York time.
  const local = readerClock(now);
  // The strip's instruments, in trading order rather than payload order. A key
  // the feed does not carry yet is simply not drawn.
  const strip = STRIP[desk]
    .map((k) => quotes.find((q) => q.key === k))
    .filter((q): q is Quote => Boolean(q));
  const ny = desk === "stocks" ? nyClock(clock) : null;
  const tabs = tabsFor(desk);

  return (
    <header className="flex flex-col gap-0 border-b border-ring">
      <div className="flex flex-wrap items-center gap-x-3 gap-y-1 px-3 py-2 qt:h-[64px] qt:flex-nowrap qt:gap-x-6 qt:px-6 qt:py-0">
        {/*
         * THE LOCKUP, A STEP LARGER (owner, 2026-10-13: "increase the hermesx
         * and logo slightly more") — the same mono word and the same helm, at
         * a size that reads as the head of the band rather than a caption.
         */}
        <div className="flex shrink-0 items-center gap-2 qt:gap-2.5">
          <Mark />
          <span className="wordmark fig text-[18px] font-semibold tracking-[0.14em] qt:text-[19px]">
            HERMESX
          </span>
        </div>
        {/* A hairline between the lockup and the controls, as the status group
            already has on the right — Quiet separates with rules, not space. */}
        <span aria-hidden className="hidden h-7 w-px shrink-0 bg-ring-2 qt:block" />

        {/*
         * THE TABS SIT BESIDE THE WORDMARK, NOT ABOVE THE PANELS. The
         * instrument, the note written off it, and the controls for both — all
         * chrome-level views of one session, so they belong in the chassis
         * beside the clock and the state light rather than in a bar that would
         * push the board down by its own height.
         */}
        {/*
         * THE DESK SWITCH LEADS THE TABS — the two desks are two products'
         * worth of tabs, and which one you are on is the first thing the
         * chassis should say. It goes to that desk's last tab. `D` flips it.
         */}
        <span className="seg shrink-0" role="tablist" aria-label="Desk" title="Switch desk — or press D">
          {DESKS.map((d) => (
            <button
              key={d.key}
              type="button"
              role="tab"
              aria-selected={desk === d.key}
              onClick={() => onDesk(d.key)}
              {...segItem(desk === d.key, { className: "text-[10px] tracking-[0.08em] uppercase qt:text-[12.5px]" })}
            >
              <span className="max-[1599px]:hidden">{d.label}</span>
              <span className="min-[1600px]:hidden">{d.short}</span>
            </button>
          ))}
        </span>

        <nav className="flex shrink-0 items-center gap-0.5 qt:gap-1" aria-label="Tabs">
          {tabs.map((t, i) => (
            <button
              key={t.key}
              type="button"
              onClick={() => onTab(t.key)}
              title={`${t.label} — press ${i + 1}`}
              aria-current={tab === t.key ? "page" : undefined}
              className={cn(
                "fig hit relative rounded px-2 py-1 text-[10px] tracking-[0.1em] uppercase",
                // Quiet: sentence case Plex, the active tab lifted onto the
                // selection grey — the same key GEXYGEN's rail and segments use.
                "qt:rounded-[3px] qt:px-2.5 qt:font-sans qt:text-[12.5px] qt:tracking-normal qt:normal-case",
                tab === t.key ? "text-ink qt:bg-surface-3 qt:font-semibold" : "text-ink-3 hover:text-ink-2",
              )}
            >
              {t.label}
              {tab === t.key && (
                <span
                  aria-hidden
                  className="absolute inset-x-1.5 -bottom-[3px] h-[2px] rounded-full qt:hidden"
                  style={{ background: "var(--flip)" }}
                />
              )}
            </button>
          ))}
        </nav>

        {/*
         * QUIET CARRIES THE STRIP IN THE BAND — each instrument a caps label
         * over its figure, the way GEXYGEN's Quiet header sets its walls and
         * the flip. One band instead of two rows, so the board starts higher.
         *
         * IT FITS ITSELF. The figures wrap inside a box one row high that hides
         * its overflow, so whatever does not fit falls to a second row nobody
         * sees — the strip drops from the right at any width, on either desk,
         * with no table of breakpoints to fall out of date when a figure is
         * added or the desk switch widens the tabs. A figure is shown whole or
         * not at all; it is never cut through.
         *
         * 16px between figures, not 24: at the larger type scale (2026-10-14)
         * the wider gap cost VVIX at 1920, and a figure beats air.
         */}
        {(strip.length > 0 || ny) && (
          <div className="hidden h-[36px] min-w-0 flex-1 flex-wrap content-start items-center justify-end gap-x-4 gap-y-4 overflow-hidden qt:flex">
            {ny && (
              <div className="flex h-[36px] shrink-0 flex-col justify-center gap-1 border-r border-ring pr-4" title={ny.title}>
                <span className="qt-cap text-[10.5px] text-ink-3">{ny.label}</span>
                <span className="fig text-[14.5px] leading-none text-ink">{ny.value}</span>
              </div>
            )}
            {strip.map((q) => (
              <div key={q.key} className="flex h-[36px] shrink-0 flex-col justify-center gap-1">
                <span className="qt-cap text-[10.5px] text-ink-3">{q.key}</span>
                <div className="flex items-baseline gap-1.5">
                  <Tick value={num(q.last)} className="fig text-[14.5px] leading-none text-ink" />
                  <Tick value={pct(q.pct)} className={cn("fig text-[11px] leading-none", dir(q.pct))} />
                </div>
              </div>
            ))}
          </div>
        )}

        {/* The clock rides the right-side status group (owner, 2026-09-01):
            time, session, feed state and the refresh are all "is this thing
            current" answers, and they read better as one cluster than with
            the clock orphaned beside the tabs. */}
        <div className="ml-auto flex shrink-0 items-center gap-2 qt:ml-0 qt:self-stretch qt:border-l qt:border-ring qt:pl-6">
          {clock && (
            <div className="mr-2 flex items-baseline gap-2">
              {clock.overlap && (
                <span className="fig qt-pill rounded bg-flip/15 px-1.5 py-px text-[9px] text-flip [--pill-hue:var(--flip-fig)] qt:text-[10.5px]">
                  OVERLAP
                </span>
              )}
              {/* Yields first when the band is tight: the session table carries
                  the phase, and the reader's local time is worth more here. */}
              <span className="hidden text-[10.5px] text-ink-3 sm:inline qt:text-[12px] qt:max-[1439px]:hidden">
                {clock.phase.label}
              </span>
              <span className="fig text-[13px] text-ink qt:text-[15px]">{clock.et_time}</span>
              <span className="eyebrow text-[9px]">ET</span>
              {local && (
                <span
                  className="fig ml-1 text-[11px] text-ink-3 qt:text-[12.5px]"
                  title={`Your local time (${local.zone})`}
                >
                  {local.time} <span className="eyebrow text-[9px]">{local.zone}</span>
                </span>
              )}
            </div>
          )}
          <span
            className={cn(
              "h-[7px] w-[7px] rounded-full",
              live ? "bg-call live-dot" : "bg-err",
            )}
            aria-hidden
          />
          <span className="fig text-[9.5px] text-ink-3 uppercase qt:text-[10.5px]">
            {live ? "Live" : "Offline"}
          </span>
          {/* Quiet: the same key as Generate — one button family across the chrome. */}
          <button
            type="button"
            onClick={onRefresh}
            className="fig hit rounded border border-ring px-2 py-px text-[9.5px] text-ink-3 uppercase hover:text-ink-2 qt:ml-1 qt:inline-flex qt:h-[28px] qt:items-center qt:rounded-[4px] qt:border-ring-2 qt:px-3 qt:py-0 qt:font-sans qt:text-[12.5px] qt:font-semibold qt:tracking-normal qt:normal-case qt:hover:border-ink-4 qt:hover:bg-surface-2"
          >
            Refresh
          </button>
        </div>
      </div>

      {strip.length > 0 && (
        <div className="flex flex-wrap items-center gap-x-4 gap-y-1 border-t border-ring/60 bg-surface/50 px-3 py-1.5 qt:hidden">
          {ny && (
            <div className="flex items-baseline gap-1.5" title={ny.title}>
              <span className="fig text-[9.5px] tracking-wider text-ink-3 uppercase">{ny.label}</span>
              <span className="fig text-[11.5px] text-ink">{ny.value}</span>
            </div>
          )}
          {strip.map((q) => (
            <div key={q.key} className="flex items-baseline gap-1.5">
              <span className="fig text-[9.5px] tracking-wider text-ink-3 uppercase">{q.key}</span>
              <Tick value={num(q.last)} className="fig text-[11.5px] text-ink" />
              <Tick value={pct(q.pct)} className={cn("fig text-[10px]", dir(q.pct))} />
            </div>
          ))}
        </div>
      )}
    </header>
  );
}

/** The two-ring lockup. Chrome hues — decoration, never data. */
function Mark() {
  return (
    <svg
      // A step larger with the word (owner, 2026-10-13); sized by class so
      // Quiet's taller band can take it up a further notch.
      className="h-[30px] w-[30px] shrink-0 qt:h-[34px] qt:w-[34px]"
      viewBox="0 0 512 512"
      aria-hidden
      // The mark glows past the viewBox on the breath; without this the SVG
      // clips its own drop-shadow at the edge.
      style={{ overflow: "visible" }}
    >
      {/*
       * The owner's own winged helm — see lib/hermesMark.ts for provenance.
       * Line art, so the chrome pair rides a gradient along it: the wing takes
       * the first hue, the helm face the second, the same wash the wordmark
       * runs. The path is also STROKED with its own gradient: at 22px the
       * traced lines are barely a pixel wide, and the stroke fattens them
       * enough to survive; at 128px it is invisible.
       */}
      <defs>
        {/*
          * THE MARK WASHES LIKE THE WORD ("it doesnt feel lively" — owner,
          * 2026-09-01: the static gradient read as dead beside a wordmark in
          * constant motion). Same trick as `.wordmark-wash`, in SVG terms: a
          * PERIODIC palindromic gradient (a → sheen → b → sheen → a) in user
          * space, twice the viewBox wide, slid one full period per cycle by
          * SMIL — so the loop is seamless and the browser owns the clock, no
          * JS. Same 5.6s as the word: one lockup, one period.
          */}
        <linearGradient
          id="hermes-grad"
          gradientUnits="userSpaceOnUse"
          x1="0"
          y1="0"
          x2="1024"
          y2="0"
        >
          <stop offset="0" stopColor="var(--icon-a)" />
          <stop offset="0.25" stopColor="var(--title-sheen)" />
          <stop offset="0.5" stopColor="var(--icon-b)" />
          <stop offset="0.75" stopColor="var(--title-sheen)" />
          <stop offset="1" stopColor="var(--icon-a)" />
          {/*
            * FROM 0 TO -1024, WHICH RUNS THE COLOUR LEFT TO RIGHT ON SCREEN —
            * the same direction as the wordmark wash. It reads backwards
            * because it is: a userSpaceOnUse gradient resolves in the
            * REFERENCING element's space, and the mirror wrapper flips that
            * space's x-axis, so screen-right is negative x in here. The
            * unmirrored-looking version shipped first and washed against the
            * word ("the effect on the logo is going the wrong way").
            */}
          <animateTransform
            attributeName="gradientTransform"
            type="translate"
            from="0 0"
            to="-1024 0"
            dur="5.6s"
            repeatCount="indefinite"
          />
        </linearGradient>
      </defs>
      {/*
        * FLIPPED BY OWNER'S CALL (2026-09-01) — and the mirror lives on THIS
        * WRAPPER GROUP, not on the animated path, after it silently came
        * undone once: the glitch animates the CSS `transform` property, and a
        * CSS transform OVERRIDES the SVG transform attribute outright for as
        * long as the animation exists — which is always, for an infinite one.
        * The flip shipped in the attribute, the glitch shipped an hour later,
        * and the helm quietly turned back around ("bro you flipped it back").
        * On a parent group the CSS on the path composes with the mirror
        * instead of replacing it.
        */}
      {/* rotate SITS LEFTMOST so it applies in screen space, after the
          mirror — inside the mirror its direction would flip, the same trap
          the wash fell into. -10 degrees dips the face — asked at -6
          first, then "slightly more" (owner, 2026-09-01). */}
      <g transform="rotate(-10 256 256) translate(512 0) scale(-1 1)">
        <path
          className="hermes-mark"
          fill="url(#hermes-grad)"
          stroke="url(#hermes-grad)"
          strokeWidth={8}
          d={HERMES_MARK_D}
        />
      </g>
    </svg>
  );
}
