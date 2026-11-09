"use client";

import type { Clock, ImpliedBook, Quote, VolTerm } from "@/types/terminal";
import { dir, feedNote, inMin, num, quoteChg } from "@/lib/format";
import { cn } from "@/lib/cn";
import { Tick } from "@/components/ui/Tick";
import { HERMES_MARK_D } from "@/lib/hermesMark";
import { stripTiles } from "@/lib/headerStrip";
import { TABS, type Tab } from "@/lib/tabs";
import { useNow } from "@/lib/useNow";
import { localClock, readerClock } from "@/lib/clock";
import { curveShape } from "@/lib/vix";
import { VixPopover, type VixFacts } from "@/components/vol/VixBands";
import { HeaderStrip, stripInk } from "@/components/shell/HeaderStrip";

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
 * ONE STRIP FOR BOTH DESKS (2026-10-30, with the one tab bar — lib/tabs.ts).
 * Each desk used to read its own: the futures books and the macro that moves
 * them, or the index ETFs the options trade on with the vol pair that prices
 * them. Now it is one row in trading order — the three books, the two index
 * ETFs, VIX for the level and VVIX for how fast it can move, the 10-year,
 * the dollar, crude, bitcoin (lib/headerStrip.ts) — with the New York
 * open-or-close countdown on the right, under the session.
 */

/**
 * The New York clock, beside the strip. `short` is Quiet's: under the "Overlap"
 * label "closes in 5h 45m" read as the overlap ending, so it names New York.
 */
function nyClock(clock: Clock | null): { label: string; short: string; value: string; title: string } | null {
  const ny = clock?.sessions.find((x) => x.key === "newyork");
  if (!ny) return null;
  if (ny.holiday) return { label: "NYSE", short: "NYSE", value: "Holiday", title: `${ny.holiday} — US markets are closed` };
  return ny.open
    ? { label: "NY closes in", short: "NY close", value: inMin(ny.next_min), title: "Time to the 16:00 ET close" }
    : { label: "NY opens in", short: "NY open", value: inMin(ny.next_min), title: "Time to the next 09:30 ET open" };
}

export function Header({
  clock: rawClock,
  quotes,
  implied,
  vixMonth,
  link,
  onRefresh,
  tab,
  onTab,
}: {
  clock: Clock | null;
  quotes: Quote[];
  /** The books' implied day (the terminal snapshot's volterm.books) for the VIX panel; the stocks desk passes none. */
  implied?: ImpliedBook[];
  /** The VIX against its own month (volterm.vix_month), for the same panel. */
  vixMonth?: VolTerm["vix_month"];
  /**
   * The page's own link to its data: "live" while polls land, "lost" once
   * one has failed (the figures on screen are from the last poll that did),
   * "offline" when the collector behind the server is down.
   */
  link: "live" | "lost" | "offline";
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
  // Classic's second row. Quiet's strip draws itself in the band (HeaderStrip).
  const strip = stripTiles(quotes).map((x) => x.quote);
  const ny = nyClock(clock);
  const tabs = TABS;
  /*
   * THE VIX FIGURE OPENS THE BANDS, ON BOTH DESKS (owner, 2026-10-21: "include
   * the header vix too"). The header has quotes, not the scanner's regime, so
   * the curve is read here from the VIX3M print on the same feed, with
   * volterm's own flat band — and the band off the level, with lib/vix's copy
   * of scanscore's rule. Same answer, same thresholds, no second opinion.
   */
  const vix3m = quotes.find((q) => q.key === "VIX3M")?.last ?? null;
  const vvix = quotes.find((q) => q.key === "VVIX")?.last ?? null;
  const vixFacts = (q: Quote): VixFacts => {
    const ratio = vix3m && vix3m > 0 ? q.last / vix3m : null;
    return {
      last: q.last,
      pct: q.pct,
      ratio,
      shape: curveShape(ratio),
      vvix,
      implied: implied ?? null,
      month: vixMonth ?? null,
    };
  };
  const vixTitle = (note: string | null) => [note, "Click for what the level means"].filter(Boolean).join("\n");

  return (
    <header className="flex flex-col gap-0 border-b border-ring">
      <div className="flex flex-wrap items-center gap-x-3 gap-y-1 px-3 py-2 qt:h-[64px] qt:flex-nowrap qt:gap-x-4 qt:px-5 qt:py-0 roomy:gap-x-6 roomy:px-6">
        {/*
         * THE LOCKUP, A STEP LARGER (owner, 2026-10-13: "increase the hermesx
         * and logo slightly more") — the same mono word and the same helm, at
         * a size that reads as the head of the band rather than a caption.
         */}
        <div className="flex shrink-0 items-center gap-2 qt:gap-2.5">
          <Mark />
          {/* The helm alone in a tight window: the word is the widest thing in the
              band, and the strip and the clock are worth more than it there. */}
          <span className="wordmark fig text-[18px] font-semibold tracking-[0.14em] qt:text-[19px] qt:max-[1179px]:hidden">
            HERMES
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

        {/* Quiet carries the strip in the band, so the board starts higher than a
            second row would let it. */}
        <HeaderStrip quotes={quotes} ny={ny} vixFacts={vixFacts} vixTitle={vixTitle} />

        {/* The clock rides the right-side status group (owner, 2026-09-01):
            time, session, feed state and the refresh are all "is this thing
            current" answers, and they read better as one cluster than with
            the clock orphaned beside the tabs. */}
        <div className="ml-auto flex shrink-0 items-center gap-2 qt:ml-0 qt:gap-3 qt:self-stretch qt:border-l qt:border-ring qt:pl-5 roomy:gap-2 roomy:pl-6">
          {/* Compact Quiet stacks it, about 200px narrower than the one line: the
              session over the New York countdown, New York's time over the reader's.
              In the overlap "Overlap" takes the session's line, and the phase it
              replaces is on the hover. Full screen and Classic keep the one line. */}
          {clock && (
            <>
              <div
                className="hidden shrink-0 flex-col justify-center gap-1 qt:flex roomy:hidden"
                title={[clock.phase.label, ny?.title].filter(Boolean).join(" · ")}
              >
                <span className={cn("qt-cap text-[10.5px]", clock.overlap ? "text-flip-fig" : "text-ink-3")}>
                  {clock.overlap ? "Overlap" : clock.phase.label}
                </span>
                {ny && (
                  <span className="fig text-[12.5px] leading-none text-ink-2">
                    {ny.short} <span className="text-ink">{ny.value}</span>
                  </span>
                )}
              </div>
              <div className="hidden shrink-0 flex-col justify-center gap-1 qt:flex roomy:hidden">
                <span className="flex items-baseline gap-1">
                  <span className="fig text-[14.5px] leading-none text-ink">{clock.et_time}</span>
                  <span className="eyebrow text-[9px]">ET</span>
                </span>
                {local && (
                  <span className="flex items-baseline gap-1" title={`Your local time (${local.zone})`}>
                    <span className="fig text-[11px] leading-none text-ink-3">{local.time}</span>
                    <span className="eyebrow text-[9px]">{local.zone}</span>
                  </span>
                )}
              </div>
              <div className="mr-2 flex items-baseline gap-2 qt:hidden roomy:flex">
                {clock.overlap && (
                  <span className="fig qt-pill rounded bg-flip/15 px-1.5 py-px text-[9px] text-flip [--pill-hue:var(--flip-fig)] qt:text-[10.5px]">
                    OVERLAP
                  </span>
                )}
                <span className="hidden text-[10.5px] text-ink-3 sm:inline qt:text-[12px]">{clock.phase.label}</span>
                <span className="fig text-[13px] text-ink qt:text-[15px]">{clock.et_time}</span>
                <span className="eyebrow text-[9px]">ET</span>
                {local && (
                  <span className="fig ml-1 text-[11px] text-ink-3 qt:text-[12.5px]" title={`Your local time (${local.zone})`}>
                    {local.time} <span className="eyebrow text-[9px]">{local.zone}</span>
                  </span>
                )}
              </div>
            </>
          )}
          <span
            className={cn(
              "h-[7px] w-[7px] rounded-full",
              link === "live" ? "bg-call live-dot" : link === "lost" ? "bg-warn" : "bg-err",
            )}
            title={link === "live" ? "Live" : undefined}
            aria-hidden
          />
          {/* Compact: quiet when all is well, loud when it is not, on the dot alone
              while the feed is live, in words the moment it is stale or offline. */}
          <span
            className={cn(
              "fig text-[9.5px] uppercase qt:text-[10.5px]",
              link === "lost" ? "text-warn" : "text-ink-3",
              link === "live" && "qt:sr-only roomy:not-sr-only",
            )}
            title={link === "lost" ? "The last refresh failed — the figures on screen are from the last one that landed" : undefined}
          >
            {link === "live" ? "Live" : link === "lost" ? "Stale" : "Offline"}
          </span>
          {/* Compact: an icon. Quiet's button is in the same key as Generate — one
              button family across the chrome. */}
          <button
            type="button"
            onClick={onRefresh}
            aria-label="Refresh"
            title="Refresh"
            className="fig hit rounded border border-ring px-2 py-px text-[9.5px] text-ink-3 uppercase hover:text-ink-2 qt:inline-flex qt:h-[28px] qt:w-[28px] qt:items-center qt:justify-center qt:rounded-[4px] qt:border-ring-2 qt:p-0 qt:hover:border-ink-4 qt:hover:bg-surface-2 roomy:ml-1 roomy:w-auto roomy:px-3 roomy:font-sans roomy:text-[12.5px] roomy:font-semibold roomy:tracking-normal roomy:normal-case"
          >
            <span className="qt:hidden roomy:inline">Refresh</span>
            <svg
              aria-hidden
              className="hidden qt:block roomy:hidden"
              width="14"
              height="14"
              viewBox="0 0 24 24"
              fill="none"
              stroke="currentColor"
              strokeWidth="2"
              strokeLinecap="round"
              strokeLinejoin="round"
            >
              <path d="M21 12a9 9 0 1 1-2.6-6.4L21 8" />
              <path d="M21 3v5h-5" />
            </svg>
          </button>
        </div>
      </div>

      {strip.length > 0 && (
        <div className="flex flex-wrap items-center gap-x-4 gap-y-1 border-t border-ring/60 bg-surface/50 px-3 py-1.5 qt:hidden">
          {strip.map((q) => {
            const chg = quoteChg(q);
            const figure = (
              <>
                <span className="fig text-[9.5px] tracking-wider text-ink-3 uppercase">{q.key}</span>
                <Tick value={num(q.last)} className={cn("fig text-[11.5px]", stripInk(q))} />
                <Tick value={chg.text} className={cn("fig text-[10px]", dir(chg.v))} />
              </>
            );
            return q.key === "VIX" ? (
              <VixPopover key={q.key} facts={vixFacts(q)} title={vixTitle(feedNote(q))} className="-mx-1 flex items-baseline gap-1.5 px-1">
                {figure}
              </VixPopover>
            ) : (
              <div key={q.key} className="flex items-baseline gap-1.5" title={feedNote(q) ?? undefined}>
                {figure}
              </div>
            );
          })}
          {ny && (
            <div className="flex items-baseline gap-1.5" title={ny.title}>
              <span className="fig text-[9.5px] tracking-wider text-ink-3 uppercase">{ny.label}</span>
              <span className="fig text-[11.5px] text-ink">{ny.value}</span>
            </div>
          )}
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
          id="hermes-grad"
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
          fill="url(#hermes-grad)"
          stroke="url(#hermes-grad)"
          strokeWidth={8}
          d={HERMES_MARK_D}
        />
      </g>
    </svg>
  );
}
