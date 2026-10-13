"use client";

import type { Clock, Quote } from "@/types/terminal";
import { dir, num, pct } from "@/lib/format";
import { cn } from "@/lib/cn";
import { Tick } from "@/components/ui/Tick";
import { HERMES_MARK_D } from "@/lib/hermesMark";
import { TABS, type Tab } from "@/lib/tabs";
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
/** Which strip figures stay in the Quiet band at which window width, by position. */
const STRIP_FIT = [
  "",
  "",
  "",
  "max-[1379px]:hidden",
  "max-[1599px]:hidden",
  "max-[1759px]:hidden",
  "max-[1759px]:hidden",
  "max-[1899px]:hidden",
];

export function Header({
  clock: rawClock,
  quotes,
  live,
  onRefresh,
  tab,
  onTab,
}: {
  clock: Clock | null;
  quotes: Quote[];
  live: boolean;
  onRefresh: () => void;
  tab: Tab;
  onTab: (t: Tab) => void;
}) {
  // The header owns its own second hand — the rest of the shell does not tick.
  const now = useNow(1000);
  const clock = localClock(rawClock, now);
  // The reader's own time beside New York's: the owner trades the NY session
  // from Australia, where 09:30 ET is past midnight. Null on New York time.
  const local = readerClock(now);
  // The strip's instruments, in trading order rather than payload order.
  const strip = ["NQ", "ES", "GC", "VIX", "US10Y", "DXY", "WTI", "BTC"]
    .map((k) => quotes.find((q) => q.key === k))
    .filter((q): q is Quote => Boolean(q));

  return (
    <header className="flex flex-col gap-0 border-b border-ring">
      <div className="flex flex-wrap items-center gap-x-3 gap-y-1 px-3 py-2 qt:h-[58px] qt:flex-nowrap qt:gap-x-6 qt:px-6 qt:py-0">
        <div className="flex shrink-0 items-center gap-2">
          <Mark />
          <span className="wordmark fig text-[16px] font-semibold tracking-[0.14em]">
            HERMESX
          </span>
        </div>

        {/*
         * THE TABS SIT BESIDE THE WORDMARK, NOT ABOVE THE PANELS. The
         * instrument, the note written off it, and the controls for both — all
         * chrome-level views of one session, so they belong in the chassis
         * beside the clock and the state light rather than in a bar that would
         * push the board down by its own height.
         */}
        <nav className="flex shrink-0 items-center gap-0.5 qt:gap-1">
          {TABS.map((t) => (
            <button
              key={t.key}
              type="button"
              onClick={() => onTab(t.key)}
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
         * The band has room for all eight only at full HD; below that the
         * strip drops from the right (BTC first, the books last) rather than
         * wrap or slide under the tabs — measured at 1280, 1440, 1600, 1920.
         */}
        {strip.length > 0 && (
          <div className="hidden min-w-0 flex-1 items-center gap-6 overflow-hidden [justify-content:safe_flex-end] qt:flex">
            {strip.map((q, i) => (
              <div key={q.key} className={cn("flex shrink-0 flex-col gap-1", STRIP_FIT[i])}>
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
          <button
            type="button"
            onClick={onRefresh}
            className="fig hit rounded border border-ring px-2 py-px text-[9.5px] text-ink-3 uppercase hover:text-ink-2 qt:ml-1 qt:rounded-[4px] qt:border-ring-2 qt:px-2.5 qt:py-0.5 qt:font-sans qt:text-[12px] qt:tracking-normal qt:normal-case"
          >
            Refresh
          </button>
        </div>
      </div>

      {strip.length > 0 && (
        <div className="flex flex-wrap items-center gap-x-4 gap-y-1 border-t border-ring/60 bg-surface/50 px-3 py-1.5 qt:hidden">
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
      width="26"
      height="26"
      viewBox="0 0 512 512"
      aria-hidden
      className="shrink-0"
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
