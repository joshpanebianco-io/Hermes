"use client";

import type { Clock } from "@/types/terminal";
import { inMin } from "@/lib/format";
import { cn } from "@/lib/cn";
import { HERMES_MARK_D } from "@/lib/hermesMark";
import { TABS, type Tab } from "@/lib/tabs";
import { useNow } from "@/lib/useNow";
import { localClock, readerClock } from "@/lib/clock";
import { useRefreshPress } from "@/lib/refresh";
import { RefreshGlyph, refreshWord } from "@/components/shell/RefreshGlyph";

/**
 * The header rail — identity on the left, the pages in the centre, state on the right.
 *
 * NO PRICES UP HERE (owner, 2026-11-10: "lets remove the" eleven instruments "from
 * the top and move them in there appropriate places else where and lets move the nav
 * bar to the centre", then "swap outright"). The strip ran the books, the index ETFs,
 * the vol pair and the macro over every page. Each now sits on the page that uses it
 * (lib/quoteTiles): the books on Futures, the macro on Macro's board, SPY, QQQ, IWM
 * and VIX in the Scanner's masthead, all eleven in one row atop the Dashboard. The
 * band is the lockup, the tabs and the clock, so the tabs can stand in its middle.
 *
 * THE TABS ARE CENTRED ON THE WINDOW, not on the room between the lockup and the
 * clock: the band is three columns, the outer two of equal width, so the tabs do not
 * slide when the clock's line lengthens. A window too narrow for that lets the outer
 * columns take what they need, and the tabs move off centre rather than overlap.
 */

/**
 * The New York clock, under the session. It names New York: under "Overlap", "closes in
 * 5h 45m" alone read as the overlap ending.
 */
export function nyClock(clock: Clock | null): { label: string; value: string; title: string } | null {
  const ny = clock?.sessions.find((x) => x.key === "newyork");
  if (!ny) return null;
  if (ny.holiday) return { label: "NYSE", value: "Holiday", title: `${ny.holiday} — US markets are closed` };
  return ny.open
    ? { label: "NY closes in", value: inMin(ny.next_min), title: "Time to the 16:00 ET close" }
    : { label: "NY opens in", value: inMin(ny.next_min), title: "Time to the next 09:30 ET open" };
}

/**
 * The session dot's three states: New York's cash session (green, the live hue), futures
 * alone (amber, the hue the Futures card marks the box trading now with), shut (grey,
 * still): the 17:00 ET maintenance hour and a holiday.
 */
type SessionTone = "cash" | "futures" | "shut";
const SESSION_DOT: Record<SessionTone, string> = { cash: "text-call", futures: "text-desk-policy", shut: "text-ink-4" };

function sessionTone(key: string): SessionTone {
  if (key === "open" || key === "midday" || key === "close") return "cash";
  if (key === "halt" || key === "holiday") return "shut";
  return "futures";
}

/**
 * The session's name in the card, in Title Case as the chips are ("US pre-market" reads
 * "Pre-Market": the US is the card's whole subject). London's last hour into the
 * pre-market is "Pre-Market" too (owner, 2026-11-20: "i like 'Pre-Market' better than
 * overlap maybe we can ahve both and one in brakcets?"): London still being in is what
 * the "(Overlap)" after it says.
 */
const SMALL_WORDS = new Set(["and", "into", "the", "of", "to"]);
const cap = (w: string) => w.charAt(0).toUpperCase() + w.slice(1);

function sessionWord(key: string, label: string): string {
  if (key === "handover") return "Pre-Market";
  return label
    .replace(/^US /, "")
    .split(" ")
    .map((w, i) => (i > 0 && SMALL_WORDS.has(w) ? w : w.split("-").map(cap).join("-")))
    .join(" ");
}

const LINK_WORD = { live: "Live", lost: "Stale", offline: "Offline" } as const;
const LINK_TITLE = {
  live: "Live · click to refresh now",
  lost: "The last refresh failed: the figures on screen are from the last one that landed. Click to try again",
  offline: "The collector is offline. Click to try again",
} as const;

export function Header({
  clock: rawClock,
  link,
  onRefresh,
  tab,
  onTab,
}: {
  clock: Clock | null;
  /**
   * The page's own link to its data: "live" while polls land, "lost" once
   * one has failed (the figures on screen are from the last poll that did),
   * "offline" when the collector behind the server is down.
   */
  link: "live" | "lost" | "offline";
  /** Reads everything again; the button spins until the promise settles (lib/refresh). */
  onRefresh: () => void | Promise<void>;
  tab: Tab;
  onTab: (t: Tab) => void;
}) {
  // The header owns its own second hand — the rest of the shell does not tick.
  const now = useNow(1000);
  const { phase, press } = useRefreshPress(onRefresh);
  const clock = localClock(rawClock, now);
  // The reader's own time beside New York's: the owner trades the NY session
  // from Australia, where 09:30 ET is past midnight. Null on New York time.
  const local = readerClock(now);
  const ny = nyClock(clock);
  const tabs = TABS;

  return (
    <header className="flex flex-col gap-0 border-b border-ring">
      <div className="flex flex-wrap items-center gap-x-3 gap-y-1 px-3 py-2 md:grid md:grid-cols-[minmax(max-content,1fr)_auto_minmax(max-content,1fr)] qt:h-[64px] qt:gap-x-4 qt:px-5 qt:py-0 roomy:gap-x-6 roomy:px-6">
        {/*
         * THE LOCKUP, A STEP LARGER (owner, 2026-10-13: "increase the hermesx
         * and logo slightly more") — the same mono word and the same helm, at
         * a size that reads as the head of the band rather than a caption.
         */}
        <div className="flex shrink-0 items-center gap-2 md:col-start-1 md:justify-self-start qt:gap-2.5">
          <Mark />
          {/* The helm alone in a tight window: the word is the widest thing in the
              band, and the tabs and the clock are worth more than it there. */}
          <span className="wordmark fig text-[18px] font-semibold tracking-[0.14em] qt:text-[19px] qt:max-[1179px]:hidden">
            HERMES
          </span>
        </div>

        {/*
         * THE TABS SIT IN THE BAND, NOT ABOVE THE PANELS. The instrument, the note
         * written off it, and the controls for both — all chrome-level views of one
         * session, so they belong in the chassis between the lockup and the clock
         * rather than in a bar that would push the board down by its own height.
         */}
        <nav className="flex shrink-0 flex-wrap items-center gap-0.5 md:col-start-2 md:justify-self-center qt:gap-1" aria-label="Tabs">
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
                "qt:rounded-[3px] qt:px-2 qt:font-sans qt:text-[12.5px] qt:tracking-normal qt:normal-case",
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

        {/* The clock rides the right-side status group (owner, 2026-09-01):
            time, session, feed state and the refresh are all "is this thing
            current" answers, and they read better as one cluster than with
            the clock orphaned beside the tabs. */}
        {/*
          * ONE CARD, THREE PARTS (owner, 2026-11-20: "can we touch this section up a bit ... i
          * dont have anything in mind myself", then of the flip mock: "ye ai like that"). It
          * was six loose things on one line in four kinds of type, "US pre-market · NY opens
          * in 1h 36m 07:54:42 ET 22:54 AEST ● LIVE [Refresh]", with a stacked form for a
          * narrower window. Now, at every width: the session with New York's countdown under
          * it; New York's time with yours under it; the refresh, wearing the live dot. Stale
          * and Offline still say so in words, on the button.
          */}
        <div className="ml-auto flex shrink-0 items-center md:col-start-3 md:ml-0 md:justify-self-end">
          <div className="flex h-[46px] items-stretch rounded-[12px] border border-ring-2 bg-surface-2/55 shadow-[inset_0_1px_0_color-mix(in_srgb,var(--ink)_6%,transparent)]">
            {clock && (
              <>
                <div
                  className="flex flex-col justify-center gap-[5px] px-4"
                  title={[clock.phase.label, clock.phase.note, clock.overlap ? "Overlap: London and New York both open" : null, ny?.title].filter(Boolean).join(" · ")}
                >
                  <span className="flex items-center gap-[7px] text-[12.5px] leading-none font-semibold whitespace-nowrap text-ink">
                    <span
                      aria-hidden
                      className={cn("h-[7px] w-[7px] shrink-0 rounded-full bg-current", SESSION_DOT[sessionTone(clock.phase.key)], sessionTone(clock.phase.key) !== "shut" && "live-dot shadow-[0_0_8px_currentColor]")}
                    />
                    {sessionWord(clock.phase.key, clock.phase.label)}
                    {/* The session first, the overlap after it in its own hue (owner, 2026-11-20). */}
                    {clock.overlap && <span className="font-normal text-flip-fig">(Overlap)</span>}
                  </span>
                  {ny && (
                    <span className="pl-[14px] text-[11.5px] leading-none whitespace-nowrap text-ink-3">
                      {ny.label} <span className="fig text-ink-2">{ny.value}</span>
                    </span>
                  )}
                </div>
                <span aria-hidden className="my-[9px] w-px bg-ring-2" />
                <div className="flex flex-col justify-center gap-[5px] px-4">
                  <span className="flex items-baseline gap-1.5 leading-none" title="New York's time">
                    <span className="fig text-[16px] tracking-[0.01em] text-ink">
                      {clock.et_time.slice(0, 5)}
                      <span className="text-ink-3">{clock.et_time.slice(5)}</span>
                    </span>
                    <span className="eyebrow text-[9px]">ET</span>
                  </span>
                  {local && (
                    <span className="flex items-baseline gap-1.5 leading-none" title={`Your local time (${local.zone})`}>
                      <span className="fig text-[11.5px] text-ink-3">{local.time}</span>
                      <span className="eyebrow text-[9px] text-ink-4">{local.zone}</span>
                    </span>
                  )}
                </div>
                <span aria-hidden className="my-[9px] w-px bg-ring-2" />
              </>
            )}
            <button
              type="button"
              onClick={press}
              aria-busy={phase === "busy"}
              aria-label={`${refreshWord(phase, "Refresh")} · ${LINK_WORD[link]}`}
              title={refreshWord(phase, LINK_TITLE[link])}
              className={cn(
                // Pressed in on the click, lit while it reads (lib/refresh).
                "hit flex items-center justify-center gap-2 text-ink-3 transition-[transform,background-color] duration-100 hover:bg-surface-3/60 hover:text-ink-2 active:scale-90",
                phase !== "idle" && "bg-surface-3/60",
                clock ? "rounded-r-[11px]" : "rounded-[11px]",
                link === "live" ? "w-[46px]" : "px-3.5",
              )}
            >
              <RefreshGlyph phase={phase} />
              {/* Nothing while all is well: the icon alone (owner, 2026-11-20: "i dont like the
                  dot next to the refresh button icon"). In words, in their hue, the moment it
                  is not. */}
              {link !== "live" && (
                <span className={cn("fig text-[10.5px] uppercase", link === "lost" ? "text-warn" : "text-err")}>{LINK_WORD[link]}</span>
              )}
            </button>
          </div>
        </div>
      </div>
    </header>
  );
}

/**
 * The two-ring lockup. Chrome hues — decoration, never data. `gradientId` is for a
 * second copy on the same page: two SVGs sharing a gradient id read the first one's,
 * and a hidden first one paints the visible one blank.
 */
export function Mark({ gradientId = "hermes-grad" }: { gradientId?: string }) {
  return (
    <svg
      // A step larger with the word (owner, 2026-10-13); sized by class so
      // Quiet's taller band can take it up a further notch.
      className="hermes-arrive h-[30px] w-[30px] shrink-0 qt:h-[34px] qt:w-[34px]"
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
          *
          * spreadMethod="repeat" IS WHAT MAKES IT PERIODIC (owner, 2026-11-05:
          * "a bit abrupt and not smooth"). Without it a gradient pads past its
          * ends, so sliding it off the mark left one flat colour for the back
          * half of the cycle, and the wrap jumped back to the full range.
          */}
        <linearGradient
          id={gradientId}
          gradientUnits="userSpaceOnUse"
          spreadMethod="repeat"
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
          fill={`url(#${gradientId})`}
          stroke={`url(#${gradientId})`}
          strokeWidth={8}
          d={HERMES_MARK_D}
        />
      </g>
    </svg>
  );
}
