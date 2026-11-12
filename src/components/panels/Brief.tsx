"use client";

import type {
  Book,
  BriefBody,
  BriefCall,
  BriefFacts,
  BriefGamma,
  BriefLadder,
  BriefLadderRow,
  BriefRead,
  BriefSnapshotRow,
  Report,
  Tone,
} from "@/types/terminal";
import { createContext, useContext } from "react";
import { biasInk, biasLabel, convictionWord } from "@/lib/bias";
import { cn } from "@/lib/cn";
import { bp, dir, num, pct, signed } from "@/lib/format";
import { useLum, useQuiet } from "@/components/state/UiMode";
import { regimeMeans } from "@/lib/gammaRegime";
import { subLabel } from "@/lib/releases";

/**
 * The session brief — the model's read, laid out like a desk's morning note.
 *
 * TWO AUTHORS ON ONE PAGE, AND THE SPLIT IS THE POINT. Every table here — the
 * snapshot, the levels ladder, the gamma card, the catalysts, the ratio strip,
 * the headline list — is printed from `rep.facts`, which the collector computed
 * from the snapshot. The model's answer supplies only words: the thesis, the
 * calls, the regime chains and reads, and short notes joined onto table rows
 * by id. So a call wall on this page cannot be a model's transcription error,
 * and a note for a row that does not exist never arrives here: the server
 * dropped it (`sanitize_brief`).
 *
 * THE SERIF APPEARS NOWHERE ELSE IN THE PRODUCT. The terminal is an instrument
 * you operate; this tab is a document you read top to bottom before a session,
 * and the owner's own brief — the page this was modelled on — reads that way
 * because its headings are set like one.
 *
 * THE HUES ARE THE TERMINAL'S, NOT THE SOURCE BRIEF'S. That page drew the flip
 * purple and every wall amber. Here amber is the flip and teal and magenta are
 * the call and put walls, exactly as the Gamma panel and GEXYGEN draw them —
 * a wall that changed colour between two tabs of one product would be a lie
 * told by a stylesheet.
 *
 * TWO PAINTS, ONE BRIEF (owner instruction, 2026-10-13: "update the report
 * section aesthetic to match better" — the Quiet Terminal). CARDED is the
 * document above: serif headings, the call on a tinted card; it was Classic's
 * paint and, with Classic gone (2026-11-11), it is what Luminous Glass draws, a
 * theme of cards (state/UiMode `useQuiet` is true for Quiet alone). QUIET is how
 * GEXYGEN's own SessionBrief renders this same schema: no cards and no tints —
 * hairlines between sections and between the calls, condensed caps for every
 * label and section title, Plex throughout (the serif was the one exception
 * Quiet does not make), square markers, and hue only where it means a side:
 * the bias word, its pips, a driver's marker, a wall's rail. Same order, same
 * tables, same words — only the paint differs.
 */

interface Paint {
  quiet: boolean;
  /** Luminous Glass: Quiet's type and marks, each section a card of its own. */
  lum: boolean;
  /** A bias set as text: the call's word, a read's chip. */
  ink: (b: string | null | undefined) => string;
  /** Marker shape: a dot (the carded paint, Luminous) or a square (Quiet). */
  mark: string;
}

const CARDED: Paint = { quiet: false, lum: false, ink: (b) => biasInk(b), mark: "rounded-full" };

/** Quiet prints a side in the hue's figure tier, as GEXYGEN's brief does. */
const QUIET: Paint = {
  quiet: true,
  lum: false,
  ink: (b) =>
    /bull/.test(b ?? "") ? "var(--call-fig)" : /bear/.test(b ?? "") ? "var(--put-fig)" : "var(--ink-2)",
  mark: "rounded-[1px]",
};

/*
 * LUMINOUS GLASS: A BOARD OF CARDS, NOT A DOCUMENT IN ONE (owner, 2026-11-12: "improve
 * the aesthetic of the brief in the futures section, make it look more modern and
 * sleek"). Luminous drew the carded paint: a serif masthead and thesis, the call on a
 * tinted slab, then every table stretched across one 1,400px card with its figures a
 * screen-width from their labels, seven screens long. It was the one page of the
 * interface still set like the old one.
 *
 * So under Luminous the brief is what every other page there is: glass cards on the
 * ground, two across where two belong together (the levels beside the gamma they
 * come from, the catalysts beside the read). The type is the interface's sans, the
 * call is a panel with its side as a rule down its edge and not a tint, the snapshot
 * is tiles, and dealer gamma has a small map of its walls. It reuses Quiet's pieces
 * (`quiet` is true here), rounded: SAME ORDER, SAME TABLES, SAME WORDS still holds.
 * CARDED is drawn by neither interface now; it stays as the one-line way back.
 */
const LUM: Paint = { quiet: true, lum: true, ink: QUIET.ink, mark: "rounded-full" };

/** A tile inside a Luminous card: a faint lift, never a tint or a gradient. */
const TILE = "rounded-[12px] border border-white/[0.07] bg-white/[0.025]";

/** The rows of the snapshot that are the books themselves: the only ones whose move is a side. */
const BOOK_ROWS: ReadonlySet<string> = new Set(["NQ", "ES", "GC"]);

const PaintCtx = createContext<Paint>(CARDED);
const usePaint = () => useContext(PaintCtx);

// The name a reader says, not the ticker they type (owner, 2026-09-22: "Nasdaq",
// as GC was already "Gold"). The pickers and the terminal panels keep the ticker.
const BOOK_NAME: Record<Book, string> = { NQ: "Nasdaq", ES: "ES", GC: "Gold" };

const TONE_HUE: Record<Tone, string> = {
  bear: "var(--put)",
  bull: "var(--call)",
  mixed: "var(--flip)",
  neutral: "var(--ink-3)",
};

const TONE_HUE_QT: Record<Tone, string> = {
  bear: "var(--put-fig)",
  bull: "var(--call-fig)",
  mixed: "var(--flip-fig)",
  neutral: "var(--ink-3)",
};

/** Quiet's words for the four tones, as GEXYGEN's legend reads them. */
const TONE_WORD: Record<Tone, string> = {
  bull: "helps the book",
  bear: "weighs on it",
  mixed: "cuts both ways",
  neutral: "no lean",
};

const KIND_HUE: Record<BriefLadderRow["kind"], string> = {
  flip: "var(--flip)",
  call: "var(--call)",
  put: "var(--put)",
  range: "var(--ink-2)",
  em: "var(--em)",
  ref: "var(--ring-2)",
  last: "var(--spot)",
  vwap: "var(--ink)",
  open: "var(--ring-2)",
  ema: "var(--ink-2)",
};

/** Quiet's rails in the figure tier — GEXYGEN's ladder; spot is ink, not a slab. */
const KIND_HUE_QT: Record<BriefLadderRow["kind"], string> = {
  flip: "var(--flip-fig)",
  call: "var(--call-fig)",
  put: "var(--put-fig)",
  range: "var(--ink-2)",
  em: "var(--em)",
  ref: "var(--ink-4)",
  last: "var(--ink)",
  vwap: "var(--ink)",
  open: "var(--ink-4)",
  ema: "var(--ink-2)",
};

const LEGEND: [BriefLadderRow["kind"], string][] = [
  ["flip", "Gamma flip"],
  ["call", "Call wall"],
  ["put", "Put wall"],
  ["range", "Session range"],
  ["em", "Expected move"],
  ["ref", "Reference"],
];

const ARROW = { up: "↑", down: "↓", flat: "→" } as const;

function tint(hue: string, amount: number): string {
  return `color-mix(in oklab, ${hue} ${amount}%, transparent)`;
}

/**
 * THE MEASURE, HELD BACK WHILE THE PAGE WIDENS.
 *
 * The brief used to be one 880px column for everything, which left most of a
 * desk monitor empty — the panel's own column runs past 1400px at 1920. The
 * article now takes that room, but width is only a gift to the things that are
 * WIDE BY NATURE: the snapshot and catalyst tables (all `w-full`), the ladders
 * and gamma cards, which go two-up and get real columns instead of cramped
 * ones.
 *
 * Running text is not one of those things. Prose has a comfortable line length
 * regardless of the glass it is displayed on, and body copy set at 13.5px was
 * already reaching ~135 characters inside the old 880px — past comfortable, not
 * short of it. So the paragraphs keep the width they have always had while
 * everything around them expands: nothing reads worse than before, and the
 * space goes where it buys something.
 */
const MEASURE = "max-w-[840px]";

export function Brief({ rep }: { rep: Report }) {
  const quiet = useQuiet();
  const lum = useLum();
  return (
    <PaintCtx.Provider value={lum ? LUM : quiet ? QUIET : CARDED}>
      <BriefBodyView rep={rep} />
    </PaintCtx.Provider>
  );
}

function BriefBodyView({ rep }: { rep: Report }) {
  const p = usePaint();
  const b = rep.report as BriefBody;
  const f = rep.facts as BriefFacts;
  const watch = new Map(b.snapshot_watch.map((w) => [w.key, w.note]));
  const callOf = new Map(b.calls.map((c) => [c.book, c]));
  /*
   * Was the session ALREADY TRADING when this note was written? Older reports
   * predate the flag and were genuinely composed as pre-open notes, so absent
   * means false and the original headings are the honest ones for them.
   */
  const live = rep.session_underway === true;

  // Luminous lays the sections out as cards, twelve columns wide: two that belong
  // together share a row when the note is about one book, and a section whose
  // neighbour is missing takes the row. Three books need the width, so they stack.
  const one = f.ladders.length <= 1 && b.reads.length <= 1;
  const hasCat = f.catalysts.length > 0 || Boolean(b.catalysts_intro);
  const hasRot = f.rotation.ratios.length > 0 || f.rotation.megacaps.length > 0;
  const hasHead = b.headlines.some((h) => f.headlines.some((x) => x.id === h.id));
  const pair = (left: boolean, other: boolean, wide: string, narrow: string) =>
    !other || !one ? "xl:col-span-12" : left ? wide : narrow;
  const SPAN = {
    all: "xl:col-span-12",
    levels: pair(true, f.gamma.length > 0, "xl:col-span-7", "xl:col-span-5"),
    gamma: pair(false, f.ladders.length > 0, "xl:col-span-7", "xl:col-span-5"),
    cat: pair(false, b.reads.length > 0, "xl:col-span-7", "xl:col-span-5"),
    read: pair(true, hasCat, "xl:col-span-7", "xl:col-span-5"),
    rot: hasHead ? "xl:col-span-6" : "xl:col-span-12",
    head: hasRot ? "xl:col-span-6" : "xl:col-span-12",
  };

  return (
    <article
      className={cn(
        p.lum
          ? "qt-noscale grid w-full grid-cols-1 gap-2 lum:gap-[var(--lum-gap)] xl:grid-cols-12"
          : cn("w-full px-5 pt-4 pb-6", p.quiet && "qt-noscale px-3 pt-2 pb-8"),
      )}
    >
      {/* Under Luminous the masthead, the thesis and the calls are the first card. */}
      <div className={cn(p.lum && "qt-card min-w-0 px-6 pt-5 pb-6 xl:col-span-12")}>
      {/*
        * THE MASTHEAD. This was a 13.5px bold sans label, and it looked wrong
        * without saying why (owner, 2026-09-22): it is the document's TITLE and
        * it was set smaller than the document's own section headings, in the
        * one face no other heading here uses — so it read as a stray caption
        * floating over the thesis. It is now what it is: the brief's serif, a
        * step above the sections, on a rule that separates the name of the
        * document from the first thing the document says. Title case stays —
        * that was chosen on purpose.
        */}
      <header
        className={cn(
          "flex flex-wrap items-baseline justify-between gap-x-3 gap-y-1 border-b pb-3",
          p.quiet ? "border-ring" : "border-ring/60",
        )}
      >
        {p.quiet ? (
          // GEXYGEN's masthead: the session in weight, the document's name
          // beside it in grey — one line, Plex, no serif.
          <h1 className="text-[21px] leading-tight font-semibold text-ink">
            {rep.session_label} <span className="font-normal text-ink-3">Session Brief</span>
          </h1>
        ) : (
          <h1 className="font-serif text-[23.5px] leading-tight font-normal text-ink">
            {rep.session_label} Session Brief
          </h1>
        )}
        <span className="fig text-[11.5px] text-ink-3">{f.as_of}</span>
      </header>

      {f.partial.length > 0 && (
        <div
          className={cn(
            "mt-3 border-l-[3px] border-warn px-3 py-2 leading-relaxed",
            p.quiet ? "bg-warn/[0.07] text-[12px] text-ink-2 [&>strong]:text-warn" : "bg-warn/10 text-[11.5px] text-warn",
          )}
        >
          <strong className="font-semibold">Partial data.</strong>
          {f.partial.map((p, i) => (
            <div key={i}>{p}</div>
          ))}
        </div>
      )}

      {/*
        * THE CHECK THE DESIGN PROMISED. Every claim is meant to quote a figure
        * from the digest; the collector now verifies that after the answer and
        * names what it could not find. Said here rather than hidden, because a
        * wrong number stated confidently is worse than no number — GEXYGEN's
        * brief carries the same banner, in the same words.
        */}
      {rep.unverified && rep.unverified.length > 0 && (
        <div
          className={cn(
            "mt-3 border-l-[3px] px-3 py-2 leading-relaxed",
            p.quiet
              ? "border-put-fig bg-put-fig/[0.07] text-[12px] text-ink-2 [&>strong]:text-put-fig"
              : "border-err bg-err/10 text-[11.5px] text-ink-2 [&>strong]:text-err",
          )}
        >
          <strong className="font-semibold">Unverified figures.</strong> The model printed{" "}
          {rep.unverified.length === 1 ? "a number" : "numbers"} the data it was given does not contain —{" "}
          <span className="fig text-ink">{rep.unverified.join(", ")}</span>. Read the sentences carrying{" "}
          {rep.unverified.length === 1 ? "it" : "them"} as unchecked; the tables beside the prose are the
          collector&apos;s and are exact.
        </div>
      )}

      {/* A clear step under the 23.5px masthead: at 22 against 25 the two read as
          one size and the title stopped looking like the title. */}
      <p
        className={cn(
          "text-ink",
          p.quiet ? "mt-5 text-[18px] leading-[1.5]" : "mt-4 font-serif text-[18.5px] leading-[1.45]",
          p.lum ? "max-w-[1040px]" : MEASURE,
        )}
      >
        {b.thesis}
      </p>

      <Calls calls={b.calls} live={live} />
      </div>

      {f.snapshot.length > 0 && (
        <Section title="Snapshot" span={SPAN.all}>
          <Snapshot rows={f.snapshot} watch={watch} />
        </Section>
      )}

      {f.ladders.length > 0 && (
        <Section title="Levels" span={SPAN.levels}>
          <Legend />
          <div className={cn("grid gap-x-8 gap-y-6", f.ladders.length > 1 && "lg:grid-cols-2", p.quiet && "gap-x-10")}>
            {f.ladders.map((l) => (
              <Ladder key={l.book} l={l} />
            ))}
          </div>
        </Section>
      )}

      {f.gamma.length > 0 && (
        <Section title="Dealer gamma" span={SPAN.gamma} right="how far a move runs, not which way">
          <div className={cn("grid gap-3", f.gamma.length > 1 && "lg:grid-cols-2", p.quiet && !p.lum && "gap-x-10 gap-y-5")}>
            {f.gamma.map((g) => (
              <GammaCard key={g.book} g={g} />
            ))}
          </div>
          {b.gamma_read && <P className="mt-3">{b.gamma_read}</P>}
        </Section>
      )}

      <Catalysts f={f} b={b} span={SPAN.cat} />

      {b.reads.length > 0 && (
        <Section title="The read" span={SPAN.read}>
          <div className={cn(p.lum && b.reads.length > 1 && "grid gap-x-10 gap-y-8 lg:grid-cols-2 2xl:grid-cols-3")}>
            {b.reads.map((r) => (
              <Read key={r.book} r={r} call={callOf.get(r.book)} live={live} tiled={p.lum && b.reads.length > 1} />
            ))}
          </div>
        </Section>
      )}

      <Rotation f={f} b={b} span={SPAN.rot} />
      <Headlines f={f} b={b} span={SPAN.head} />

      {(b.cross_asset || b.risks.length > 0) && (
        <Section title="Cross-asset" span={SPAN.all}>
          {b.cross_asset && (
            <p
              className={cn(
                "text-ink",
                p.quiet ? "text-[14px] leading-[1.6]" : "font-serif text-[16px] leading-relaxed",
                MEASURE,
              )}
            >
              {b.cross_asset}
            </p>
          )}
          {b.risks.length > 0 && (
            <>
              <Label className="mt-4">Risks</Label>
              <ul className="space-y-1">
                {b.risks.map((x, i) =>
                  p.quiet ? (
                    <li key={i} className="flex gap-2 text-[13px] leading-[1.5] text-ink-2">
                      <span aria-hidden className="mt-[7px] h-[5px] w-[5px] shrink-0 rounded-[1px] bg-ink-4" />
                      {x}
                    </li>
                  ) : (
                    <li key={i} className="text-[12.5px] leading-snug text-ink-2">
                      · {x}
                    </li>
                  ),
                )}
              </ul>
            </>
          )}
        </Section>
      )}
    </article>
  );
}

/* ---------------------------------------------------------------- the calls */

function Calls({ calls, live }: { calls: BriefCall[]; live?: boolean }) {
  const p = usePaint();
  if (p.lum) return <LumCalls calls={calls} live={live} />;
  if (p.quiet) return <QuietCalls calls={calls} live={live} />;
  return (
    <div
      className={cn(
        "mt-5 grid gap-2.5",
        calls.length > 1 && "sm:grid-cols-2",
        calls.length > 2 && "lg:grid-cols-3",
      )}
    >
      {calls.map((c) => {
        const ink = biasInk(c.open_bias);
        return (
          <div
            key={c.book}
            className="border-t-[3px] px-3.5 pt-3 pb-3.5"
            style={{ borderColor: ink, background: tint(ink, 10) }}
          >
            <div className="text-[16px] font-semibold text-ink-3">{BOOK_NAME[c.book]}</div>
            <div className="mt-0.5 font-serif text-[29px] leading-9" style={{ color: ink }}>
              {biasLabel(c.open_bias)}
            </div>
            <div className="mt-0.5 mb-3 flex flex-wrap items-center gap-2 text-[12.5px] text-ink-3">
              <span>
                {convictionWord(c.conviction)} conviction {live ? "from here" : "at the open"}
              </span>
              <Pips n={c.conviction} hue={ink} />
            </div>
            {/*
              * THE REASONING SITS ON THE CARD, NOT IN THE READ BELOW IT. A bias
              * and a conviction score with no "because" is a number that cannot
              * be argued with; the owner asked for the call to explain itself.
              * Each line names its layer, so a macro reason and a structure
              * reason cannot be blurred into one sentence — and a conflict
              * between them is visible as two lines that disagree.
              */}
            {c.why && c.why.length > 0 && (
              <>
                <Label>Why</Label>
                <ul className="mb-3 space-y-1">
                  {c.why.map((w, i) => (
                    <li key={i} className="flex gap-1.5 text-[12.5px] leading-snug text-ink">
                      <span aria-hidden className="text-ink-3">
                        ·
                      </span>
                      <span>{w}</span>
                    </li>
                  ))}
                </ul>
              </>
            )}
            <Label>{live ? "Rest of session" : "Rest of day"}</Label>
            <div className="mb-2.5 text-[13.5px] leading-snug text-ink">
              {c.rest_of_day || biasLabel(c.rest_of_day_bias)}
            </div>
            {c.wrong_if && (
              <>
                <Label>Wrong if</Label>
                <div className="text-[13.5px] leading-snug font-semibold text-ink">
                  {c.wrong_if}
                </div>
              </>
            )}
            {c.catalyst && (
              <>
                <Label>Catalyst</Label>
                <div className="text-[13px] leading-snug text-ink-2">{c.catalyst}</div>
              </>
            )}
          </div>
        );
      })}
    </div>
  );
}

/**
 * Quiet's calls: no card and no tint — the calls sit between two hairlines,
 * divided by hairlines, the bias word in its side's figure hue the only colour
 * (GEXYGEN's brief sets its call exactly so). Labels go above their text, not
 * beside it, which GEXYGEN learned reads as one run-on line otherwise.
 */
function QuietCalls({ calls, live }: { calls: BriefCall[]; live?: boolean }) {
  const p = usePaint();
  return (
    <div
      className={cn(
        "mt-6 grid border-t border-ring",
        calls.length > 1 && "sm:grid-cols-2 sm:divide-x sm:divide-ring",
        calls.length > 2 && "lg:grid-cols-3",
      )}
    >
      {calls.map((c) => {
        const hue = p.ink(c.open_bias);
        return (
          <div
            key={c.book}
            className={cn("min-w-0 py-4", calls.length > 1 ? "sm:px-6 sm:first:pl-0 sm:last:pr-0" : "")}
          >
            <div className="flex flex-wrap items-baseline gap-x-3 gap-y-1">
              <span className="qt-cap text-[11px] text-ink-3">{BOOK_NAME[c.book]}</span>
              <span className="text-[27px] leading-none font-semibold" style={{ color: hue }}>
                {biasLabel(c.open_bias)}
              </span>
              <span className="text-[12px] text-ink-3">{live ? "from here" : "at the open"}</span>
              <span className="ml-auto flex items-center gap-2 text-[11.5px] text-ink-3">
                {convictionWord(c.conviction)} conviction
                <Pips n={c.conviction} hue={hue} />
              </span>
            </div>
            {c.why && c.why.length > 0 && (
              <ul className="mt-3 flex flex-col gap-1.5">
                {c.why.map((w, i) => (
                  <li key={i} className="flex gap-2 text-[13px] leading-[1.5] text-ink-2">
                    <span
                      aria-hidden
                      className="mt-[7px] h-[5px] w-[5px] shrink-0 rounded-[1px]"
                      style={{ background: hue }}
                    />
                    <span>
                      <Layered text={w} />
                    </span>
                  </li>
                ))}
              </ul>
            )}
            <div className="mt-4 flex flex-col gap-3 text-[13px] leading-[1.5]">
              <div>
                <p className="qt-cap text-[10.5px] text-ink-3">{live ? "Rest of session" : "Rest of day"}</p>
                <p className="mt-1 text-ink-2">{c.rest_of_day || biasLabel(c.rest_of_day_bias)}</p>
              </div>
              {c.wrong_if && (
                <div>
                  <p className="qt-cap text-[10.5px] text-ink-3">Wrong if</p>
                  <p className="mt-1 font-semibold text-ink">{c.wrong_if}</p>
                </div>
              )}
              {c.catalyst && (
                <div>
                  <p className="qt-cap text-[10.5px] text-ink-3">Catalyst</p>
                  <p className="mt-1 text-ink-2">{c.catalyst}</p>
                </div>
              )}
            </div>
          </div>
        );
      })}
    </div>
  );
}

/**
 * Luminous's calls: one panel a book. The side is the big word and a rule down the
 * panel's edge, never a tint over it; the reasons sit beside the call when the note is
 * about one book, each led by its layer, and what is left of the day, what makes it
 * wrong and the catalyst run along the foot as three labelled columns.
 */
function LumCalls({ calls, live }: { calls: BriefCall[]; live?: boolean }) {
  const p = usePaint();
  const one = calls.length === 1;
  return (
    <div className={cn("mt-6 grid gap-3", calls.length > 1 && "lg:grid-cols-2", calls.length > 2 && "2xl:grid-cols-3")}>
      {calls.map((c) => {
        const hue = p.ink(c.open_bias);
        return (
          <div key={c.book} className={cn(TILE, "relative min-w-0 overflow-hidden py-5 pr-6 pl-7")}>
            <span aria-hidden className="absolute inset-y-4 left-[10px] w-[3px] rounded-full" style={{ background: hue }} />
            <div className={cn("grid gap-x-10 gap-y-4", one && "lg:grid-cols-[minmax(230px,280px)_minmax(0,1fr)]")}>
              <div className="min-w-0">
                <p className="qt-cap text-[11px] text-ink-3">{BOOK_NAME[c.book]}</p>
                <p className="mt-2 text-[32px] leading-none font-semibold tracking-[-0.01em]" style={{ color: hue }}>
                  {biasLabel(c.open_bias)}
                </p>
                <p className="mt-3 flex flex-wrap items-center gap-x-2 gap-y-1 text-[12px] text-ink-3">
                  <Pips n={c.conviction} hue={hue} />
                  <span>
                    {convictionWord(c.conviction)} conviction {live ? "from here" : "at the open"}
                  </span>
                </p>
              </div>
              {c.why && c.why.length > 0 && (
                <ul className="flex min-w-0 flex-col gap-2">
                  {c.why.map((w, i) => (
                    <li key={i} className="text-[13px] leading-[1.55] text-ink-2">
                      <Layered text={w} />
                    </li>
                  ))}
                </ul>
              )}
            </div>
            <div className={cn("mt-5 grid gap-x-10 gap-y-3 border-t border-white/[0.07] pt-4 text-[13px] leading-[1.5]", one && "md:grid-cols-3")}>
              <div className="min-w-0">
                <p className="qt-cap text-[10.5px] text-ink-3">{live ? "Rest of session" : "Rest of day"}</p>
                <p className="mt-1 text-ink-2">{c.rest_of_day || biasLabel(c.rest_of_day_bias)}</p>
              </div>
              {c.wrong_if && (
                <div className="min-w-0">
                  <p className="qt-cap text-[10.5px] text-ink-3">Wrong if</p>
                  <p className="mt-1 font-semibold text-ink">{c.wrong_if}</p>
                </div>
              )}
              {c.catalyst && (
                <div className="min-w-0">
                  <p className="qt-cap text-[10.5px] text-ink-3">Catalyst</p>
                  <p className="mt-1 text-ink-2">{c.catalyst}</p>
                </div>
              )}
            </div>
          </div>
        );
      })}
    </div>
  );
}

/** A "Macro: …" bullet with its layer set in caps (a pill under Luminous), so the layers read as layers. */
function Layered({ text }: { text: string }) {
  const p = usePaint();
  const m = text.match(/^(Macro|Structure|Tape|Flow|Session|Positioning|Rates|Dollar|Breadth):\s*(.*)$/i);
  return m ? (
    <>
      <span
        className={
          p.lum
            ? "qt-cap mr-2 inline-block rounded-full border border-white/10 bg-white/[0.04] px-2 py-px align-[1px] text-[9.5px] text-ink-2"
            : "qt-cap mr-1.5 text-[10.5px] text-ink-3"
        }
      >
        {m[1]}
      </span>
      {m[2]}
    </>
  ) : (
    <>{text}</>
  );
}

function Pips({ n, hue }: { n: number; hue: string }) {
  const p = usePaint();
  return (
    <span
      className="flex items-center gap-[3px]"
      title={`Conviction ${n}/5 — the model's own confidence, not a probability`}
    >
      {[1, 2, 3, 4, 5].map((i) => (
        <span
          key={i}
          className={cn(p.quiet ? "h-[7px] w-[7px]" : "h-[8px] w-[8px]", p.mark)}
          style={{ background: i <= n ? hue : p.quiet ? "var(--qt-track, var(--surface-3))" : "var(--ring-2)" }}
        />
      ))}
    </span>
  );
}

/* ---------------------------------------------------------------- snapshot */

/**
 * Luminous's snapshot: a tile an instrument, three across. The figure and its move are
 * the tile's head; what it is measured against and why it is flagged sit under them, so
 * a figure is never a screen's width from its name.
 */
function LumSnapshot({ rows, watch }: { rows: BriefSnapshotRow[]; watch: Map<string, string> }) {
  return (
    <>
      <ul className="grid gap-2 sm:grid-cols-2 lg:grid-cols-3">
        {rows.map((row) => {
          const note = watch.get(row.key);
          const value =
            row.last2 !== null && row.last2 !== undefined
              ? `${num(row.last, row.dp)} / ${num(row.last2, row.dp)}`
              : `${num(row.last, row.dp)}${row.last !== null ? row.suffix : ""}`;
          return (
            <li key={row.key} className={cn(TILE, "min-w-0 px-4 py-3")}>
              <p className="flex items-center gap-1.5 text-[12px] font-semibold text-ink-2">
                {note !== undefined && <span aria-hidden className="h-[6px] w-[6px] shrink-0 rounded-full bg-flip-fig" title="Flagged to watch" />}
                {row.label}
              </p>
              <p className="mt-1.5 flex flex-wrap items-baseline gap-x-2.5">
                <span className="fig text-[19px] leading-none text-ink">{value}</span>
                <span className="fig text-[12px] whitespace-nowrap">
                  <Change row={row} />
                </span>
              </p>
              {row.sub && <p className="mt-2 text-[11px] leading-snug text-ink-3">{row.sub}</p>}
              {note && <p className="mt-1 text-[12px] leading-[1.45] text-ink-2">{note}</p>}
            </li>
          );
        })}
      </ul>
      {watch.size > 0 && (
        <div className="mt-2.5 flex items-center gap-1.5 text-[11px] text-ink-3">
          <span aria-hidden className="h-[6px] w-[6px] rounded-full bg-flip-fig" /> flagged to watch
        </div>
      )}
    </>
  );
}

function Snapshot({ rows, watch }: { rows: BriefSnapshotRow[]; watch: Map<string, string> }) {
  const p = usePaint();
  if (p.lum) return <LumSnapshot rows={rows} watch={watch} />;
  if (p.quiet) return <QuietSnapshot rows={rows} watch={watch} />;
  return (
    <>
      <table className="w-full border-collapse">
        <tbody>
          {rows.map((row) => {
            const note = watch.get(row.key);
            const value =
              row.last2 !== null && row.last2 !== undefined
                ? `${num(row.last, row.dp)} / ${num(row.last2, row.dp)}`
                : `${num(row.last, row.dp)}${row.last !== null ? row.suffix : ""}`;
            return (
              <tr key={row.key} className="border-b border-ring/60 align-top">
                <td className="py-2 pr-2">
                  <div className="text-[13px] font-semibold text-ink">
                    {row.label}
                    {note !== undefined && (
                      <span className="ml-1.5 align-[2px] text-[9px] text-flip" title="Flagged to watch">
                        ●
                      </span>
                    )}
                  </div>
                  {row.sub && <div className="text-[11px] leading-snug text-ink-3">{row.sub}</div>}
                  {note && <div className="text-[11.5px] leading-snug text-ink-2">{note}</div>}
                </td>
                <td className="fig px-2 py-2 text-right text-[13px] whitespace-nowrap text-ink">
                  {value}
                </td>
                <td className="fig py-2 text-right text-[12px] whitespace-nowrap">
                  <Change row={row} />
                </td>
              </tr>
            );
          })}
        </tbody>
      </table>
      {watch.size > 0 && (
        <div className="mt-2 text-[11px] text-ink-3">
          <span className="text-[9px] text-flip">●</span> flagged to watch
        </div>
      )}
    </>
  );
}

/**
 * Quiet's snapshot: two balanced columns across the full width, as GEXYGEN
 * sets its own — one tall table down the left of a wide column leaves a
 * screen of empty space beside it. A flagged row wears a square in the flip's
 * hue, which is what "look here" means everywhere on this terminal.
 */
function QuietSnapshot({ rows, watch }: { rows: BriefSnapshotRow[]; watch: Map<string, string> }) {
  return (
    <>
      <ul className="grid gap-x-10 lg:grid-cols-2">
        {rows.map((row) => {
          const note = watch.get(row.key);
          const value =
            row.last2 !== null && row.last2 !== undefined
              ? `${num(row.last, row.dp)} / ${num(row.last2, row.dp)}`
              : `${num(row.last, row.dp)}${row.last !== null ? row.suffix : ""}`;
          return (
            <li
              key={row.key}
              className="grid grid-cols-[minmax(0,1fr)_auto_104px] items-baseline gap-x-3 border-b border-ring/70 py-[7px]"
            >
              <span className="min-w-0">
                <span className="flex items-center gap-1.5 text-[13px] font-semibold text-ink">
                  {note !== undefined && (
                    <span aria-hidden className="h-[6px] w-[6px] shrink-0 rounded-[1px] bg-flip-fig" title="Flagged to watch" />
                  )}
                  {row.label}
                </span>
                {row.sub && <span className="block text-[11px] leading-snug text-ink-3">{row.sub}</span>}
                {note && <span className="mt-0.5 block text-[12px] leading-[1.45] text-ink-2">{note}</span>}
              </span>
              <span className="fig text-right text-[13px] whitespace-nowrap text-ink">{value}</span>
              <span className="fig text-right text-[12px] whitespace-nowrap">
                <Change row={row} />
              </span>
            </li>
          );
        })}
      </ul>
      {watch.size > 0 && (
        <div className="mt-2 flex items-center gap-1.5 text-[11px] text-ink-3">
          <span aria-hidden className="h-[6px] w-[6px] rounded-[1px] bg-flip-fig" /> flagged to watch
        </div>
      )}
    </>
  );
}

function Change({ row }: { row: BriefSnapshotRow }) {
  if (row.chg === null || row.chg === undefined) {
    return <span className="text-ink-3">{row.tag ?? ""}</span>;
  }
  const d = dir(row.chg);
  const text =
    row.chg_unit === "bp" ? bp(row.chg) : row.chg_unit === "pts" ? signed(row.chg, row.dp) : pct(row.chg);
  /*
   * GREEN AND PINK ONLY ON THE BOOKS (owner, 2026-11-12: "10y yield etc ... incorrect
   * bias - positive doesnt mean bullish and vice versa"). Every row's move was coloured
   * by its sign, so under a call that said Lean Bear the 10-year's rise was a green
   * arrow and the dollar's fall a pink one: each the opposite of what it does to the
   * book. A book's own move is a side. A yield's, the dollar's, the VIX's or oil's is a
   * move, drawn in ink with its arrow; what it does to the book is said in The read's
   * drivers, where each has a tone.
   */
  const side = BOOK_ROWS.has(row.key);
  return (
    <span className={side ? d : "text-ink-2"} title={side ? undefined : "The move itself, not a side: what it does to the book is in The read"}>
      <span className="mr-1 align-[1px] text-[8px]">{d === "up" ? "▲" : d === "down" ? "▼" : "–"}</span>
      {text}
      {row.tag ? ` · ${row.tag}` : ""}
    </span>
  );
}

/* ---------------------------------------------------------------- levels */

function Legend() {
  const p = usePaint();
  const hues = p.quiet ? KIND_HUE_QT : KIND_HUE;
  return (
    <div className="-mt-1 mb-4 flex flex-wrap gap-x-4 gap-y-1 text-[11px] text-ink-3">
      {LEGEND.map(([k, label]) => (
        <span key={k} className="inline-flex items-center gap-1.5 whitespace-nowrap">
          <span className="inline-block h-2 w-2" style={{ background: hues[k] }} />
          {label}
        </span>
      ))}
      <span className="inline-flex items-center gap-1.5 whitespace-nowrap">
        <span className="inline-block h-2 w-3 bg-surface-3" />
        Inside the expected move
      </span>
    </div>
  );
}

function Ladder({ l }: { l: BriefLadder }) {
  const p = usePaint();
  const hues = p.quiet ? KIND_HUE_QT : KIND_HUE;
  return (
    <div className="min-w-0">
      <div className="mb-1.5 flex flex-wrap items-baseline justify-between gap-x-2">
        <span className={cn("text-ink", p.quiet ? "text-[13.5px] font-semibold" : "text-[14px] font-bold")}>
          {l.label}
        </span>
        <span className="text-[11px] text-ink-3">
          Last <span className="fig">{num(l.last, l.dp)}</span>
          {l.em !== null && (
            <>
              {" "}
              · expected move <span className="fig">±{num(l.em, l.dp)}</span>
              {l.em_basis && l.em_basis !== "GEXYGEN" && ` (${l.em_basis})`}
            </>
          )}
        </span>
      </div>
      <table className="w-full border-collapse border-t border-ring/60">
        <tbody>
          {l.rows.map((r, i) => {
            const last = r.kind === "last";
            const muted = r.kind === "em" || r.kind === "ref";
            // The carded paint inverts the spot row onto a white slab; Quiet lifts it onto
            // the selection grey instead — a slab of white is a glow by another name.
            const ink = last ? (p.quiet ? "text-ink" : "text-bg") : muted ? "text-ink-3" : "text-ink";
            return (
              <tr
                key={i}
                className="border-b border-ring/60"
                style={{
                  background: last
                    ? p.quiet
                      ? "var(--surface-3)"
                      : "var(--spot)"
                    : r.inside_em
                      ? p.quiet
                        ? "color-mix(in oklab, var(--surface-2) 60%, transparent)"
                        : "color-mix(in oklab, var(--surface-3) 80%, transparent)"
                      : undefined,
                }}
              >
                <td className="w-[4px] p-0" style={{ background: hues[r.kind] }} />
                <td
                  className={cn(
                    "fig w-[88px] px-2.5 py-1.5 text-right text-[12.5px] whitespace-nowrap",
                    ink,
                    (last || r.kind === "flip") && "font-bold",
                  )}
                >
                  {num(r.price, l.dp)}
                </td>
                <td
                  className={cn(
                    "px-2.5 py-1.5 text-[12.5px]",
                    ink,
                    (last || r.kind === "flip") && "font-bold",
                    r.kind === "em" && "italic",
                  )}
                >
                  {r.label}
                </td>
                <td
                  className={cn(
                    "fig px-2.5 py-1.5 text-right text-[12px] whitespace-nowrap",
                    last ? (p.quiet ? "text-ink-2" : "text-bg") : "text-ink-3",
                  )}
                >
                  {r.dist === null ? "" : signed(r.dist, l.dp)}
                </td>
              </tr>
            );
          })}
        </tbody>
      </table>
      {l.note && <p className="mt-1.5 text-[11px] leading-relaxed text-ink-3">{l.note}</p>}
    </div>
  );
}

/* ---------------------------------------------------------------- gamma */

function GammaCard({ g }: { g: BriefGamma }) {
  const p = usePaint();
  const regime = g.regime === "NEG" ? "Negative gamma" : g.regime === "POS" ? "Positive gamma" : "Gamma";
  // IN INK, WHICHEVER REGIME (lib/gammaRegime): it was the bull's green for positive and
  // the bear's pink for negative, and the regime is not a side.
  const hue = "var(--ink)";
  // flip_dist is flip minus last: positive means the flip sits overhead.
  const side = g.flip_dist === null ? null : g.flip_dist > 0 ? "above" : "below";
  const flipSub =
    g.flip_dist_pct === null
      ? undefined
      : `${pct(g.flip_dist_pct, 1)}${g.flip_em !== null && side ? `, ${g.flip_em} EM ${side}` : ""}`;
  if (p.lum) {
    const means = regimeMeans(g.regime);
    return (
      <div className={cn(TILE, "min-w-0 px-5 pt-4 pb-2")}>
        <div className="flex items-baseline justify-between gap-2">
          <span className="text-[19px] leading-none font-semibold text-ink">{regime}</span>
          <span className="qt-cap text-[11px] text-ink-3">{g.label}</span>
        </div>
        {means && (
          <p className="mt-2 text-[12px] leading-[1.45] text-ink-3">
            <span className="text-ink-2">{means[0].toUpperCase() + means.slice(1)}</span>, up or down:{" "}
            {g.regime === "POS" ? "dealers hedge against a move, so ranges tend to hold." : "dealers hedge with a move, so breaks tend to run."}
          </p>
        )}
        <GammaMap g={g} />
        <div className="grid grid-cols-2 gap-x-6">
          <Stat k="Flip" v={num(g.flip, g.dp)} sub={flipSub} />
          <Stat
            k="Spot"
            v={num(g.last, g.dp)}
            sub={side === "above" ? "below the flip" : side === "below" ? "above the flip" : undefined}
          />
          <Stat k="Walls (call / put)" v={`${num(g.call_wall, g.dp)} / ${num(g.put_wall, g.dp)}`} />
          <Stat
            k="Expected move"
            v={g.em !== null ? `±${num(g.em, g.dp)}` : "—"}
            sub={g.em_basis && g.em_basis !== "GEXYGEN" ? g.em_basis : undefined}
          />
        </div>
      </div>
    );
  }
  return (
    <div
      className={cn("border-l-[3px]", p.quiet ? "border-flip-fig/70 py-1 pl-4" : "px-4 pt-3 pb-1")}
      style={p.quiet ? undefined : { borderColor: "var(--flip)", background: tint("var(--flip)", 7) }}
    >
      <div className="mb-2 flex items-baseline justify-between gap-2">
        <span
          className={p.quiet ? "text-[19px] font-semibold" : "font-serif text-[20px]"}
          style={{ color: hue }}
        >
          {regime}
        </span>
        <span className={p.quiet ? "qt-cap text-[11px] text-ink-3" : "text-[12px] font-semibold text-ink-3"}>
          {g.label}
        </span>
      </div>
      <div className="grid grid-cols-2 gap-x-4">
        <Stat k="Flip" v={num(g.flip, g.dp)} sub={flipSub} />
        <Stat
          k="Expected move"
          v={g.em !== null ? `±${num(g.em, g.dp)}` : "—"}
          sub={g.em_basis && g.em_basis !== "GEXYGEN" ? g.em_basis : undefined}
        />
        <Stat k="Walls (call / put)" v={`${num(g.call_wall, g.dp)} / ${num(g.put_wall, g.dp)}`} />
        <Stat
          k="Spot"
          v={num(g.last, g.dp)}
          sub={side === "above" ? "below the flip" : side === "below" ? "above the flip" : undefined}
        />
      </div>
    </div>
  );
}

/**
 * The gamma levels on one line, for Luminous's card: the put wall, the flip and the call
 * wall where they sit against each other, and spot among them. The walls and the flip
 * keep the hues they have on every chart and ladder; spot is ink. Labels that would
 * collide step down a line.
 */
function GammaMap({ g }: { g: BriefGamma }) {
  const marks = (
    [
      { v: g.put_wall, hue: "var(--put-fig)", word: "put wall" },
      { v: g.flip, hue: "var(--flip-fig)", word: "flip" },
      { v: g.call_wall, hue: "var(--call-fig)", word: "call wall" },
    ] as Array<{ v: number | null; hue: string; word: string }>
  )
    .filter((m): m is { v: number; hue: string; word: string } => m.v != null)
    .sort((a, b) => a.v - b.v);
  const pts = [...marks.map((m) => m.v), ...(g.last != null ? [g.last] : [])];
  if (marks.length < 2 || pts.length < 3) return <div className="h-3" />;
  const lo = Math.min(...pts);
  const span = Math.max(...pts) - lo || 1;
  // Ten per cent in from each end, so the outermost labels stay inside the card.
  const at = (v: number) => 10 + ((v - lo) / span) * 80;
  // A label within a fifth of the track of the one before it goes on the second line.
  let lastAt = -100;
  let lastRow = 1;
  const placed = marks.map((m) => {
    const x = at(m.v);
    const row = x - lastAt < 20 && lastRow === 0 ? 1 : 0;
    lastAt = x;
    lastRow = row;
    return { ...m, x, row };
  });
  return (
    <div className="relative mt-5 mb-3 h-[62px]" role="img" aria-label={`Put wall ${num(g.put_wall, g.dp)}, flip ${num(g.flip, g.dp)}, call wall ${num(g.call_wall, g.dp)}, spot ${num(g.last, g.dp)}`}>
      <span aria-hidden className="absolute top-[7px] right-0 left-0 h-[2px] rounded-full bg-white/10" />
      {placed.map((m) => (
        <span key={m.word} aria-hidden className="absolute top-0 flex -translate-x-1/2 flex-col items-center" style={{ left: `${m.x}%` }}>
          <span className="h-[16px] w-[2px] rounded-full" style={{ background: m.hue }} />
          <span className="fig text-[10px] leading-[1.35] whitespace-nowrap text-ink-3" style={{ marginTop: m.row ? 22 : 5 }}>
            <span style={{ color: m.hue }}>{m.word}</span> {num(m.v, g.dp)}
          </span>
        </span>
      ))}
      {g.last != null && (
        <span
          aria-hidden
          title={`Spot ${num(g.last, g.dp)}`}
          className="absolute top-[2px] h-[12px] w-[12px] -translate-x-1/2 rounded-full border-2 border-[var(--lum-sheet,#121822)] bg-ink"
          style={{ left: `${at(g.last)}%` }}
        />
      )}
    </div>
  );
}

function Stat({ k, v, sub }: { k: string; v: string; sub?: string }) {
  const p = usePaint();
  return (
    <div className="pb-3">
      <div className={p.quiet ? "qt-cap mb-0.5 text-[10.5px] text-ink-3" : "text-[11px] text-ink-3"}>{k}</div>
      <div className={cn("fig text-ink", p.quiet ? "text-[14px]" : "text-[15px] font-semibold")}>{v}</div>
      {sub && <div className="text-[11px] text-ink-3">{sub}</div>}
    </div>
  );
}

/* ---------------------------------------------------------------- catalysts */

function Catalysts({ f, b, span }: { f: BriefFacts; b: BriefBody; span?: string }) {
  if (f.catalysts.length === 0 && !b.catalysts_intro) return null;
  const notes = new Map(b.catalyst_notes.map((n) => [n.id, n.note]));
  return (
    <Section title="Catalysts" span={span}>
      {b.catalysts_intro && <P muted>{b.catalysts_intro}</P>}
      {f.catalysts.length > 0 && (
        <table className="w-full border-collapse border-t border-ring/60">
          <tbody>
            {f.catalysts.map((c) => {
              const note = notes.get(c.id);
              const detail = [
                c.actual && `actual ${c.actual}`,
                c.consensus && `${c.kind === "earnings" ? "EPS est." : "consensus"} ${c.consensus}`,
                c.previous && `prior ${c.previous}`,
                c.note,
              ]
                .filter(Boolean)
                .join(" · ");
              return (
                <tr key={c.id} className="border-b border-ring/60 align-top">
                  <td
                    className={cn(
                      "fig w-[136px] py-2 pr-3 text-[11.5px] font-semibold whitespace-nowrap qt:w-[150px] qt:text-[12px]",
                      c.released ? "text-ink-3" : "text-ink",
                    )}
                  >
                    {c.when}
                  </td>
                  <td className="py-2">
                    <div className={cn("text-[13px] leading-snug", c.released ? "text-ink-2" : "text-ink")}>
                      {c.title}
                      {c.country && c.kind === "data" && (
                        <span className="ml-1.5 text-[11px] text-ink-3">{c.country}</span>
                      )}
                      {c.released && c.kind !== "fed" && <Chip>Released</Chip>}
                      {/* A day a market is shut or shuts early (holidays.py): it changes what
                          the rows around it mean, so it is marked as what it is. */}
                      {c.kind === "holiday" && <Chip hue="var(--flip)" quietHue="var(--warn)">Holiday</Chip>}
                      {c.high && <Chip hue="var(--flip)" quietHue="var(--warn)">High impact</Chip>}
                    </div>
                    {detail && (
                      <div className="mt-0.5 text-[11.5px] leading-snug text-ink-3">
                        {detail.charAt(0).toUpperCase() + detail.slice(1)}
                      </div>
                    )}
                    {/* The release's other series, one line each (releases.py). */}
                    {c.also?.map((a, i) => (
                      <div key={`${a.title}-${i}`} className="text-[11.5px] leading-snug text-ink-3">
                        <span className="text-ink-2">{subLabel(a.title, c.title)}</span>{" "}
                        {[a.actual && `actual ${a.actual}`, a.consensus && `consensus ${a.consensus}`, a.previous && `prior ${a.previous}`]
                          .filter(Boolean)
                          .join(" · ")}
                      </div>
                    ))}
                    {note && <div className="mt-0.5 text-[12.5px] leading-snug text-ink-2">{note}</div>}
                  </td>
                </tr>
              );
            })}
          </tbody>
        </table>
      )}
    </Section>
  );
}

/* ---------------------------------------------------------------- the read */

function Read({ r, call, live, tiled }: { r: BriefRead; call?: BriefCall; live?: boolean; tiled?: boolean }) {
  const p = usePaint();
  const ink = p.ink(call?.open_bias);
  const tones = p.quiet ? TONE_HUE_QT : TONE_HUE;
  return (
    // `tiled`: Luminous sets several books' reads side by side, so the rule between them goes.
    <div className={cn(tiled ? "min-w-0" : "mb-8 last:mb-0", p.quiet && !tiled && "mb-10 border-b border-ring/60 pb-8 last:border-b-0 last:pb-0")}>
      <div className="mb-3 flex flex-wrap items-baseline justify-between gap-2">
        <span className={p.quiet ? "text-[17px] font-semibold text-ink" : "font-serif text-[21px] text-ink"}>
          {BOOK_NAME[r.book]}
        </span>
        {call && (
          <Chip hue={ink}>
            {biasLabel(call.open_bias)} {live ? "from here" : "at the open"}
          </Chip>
        )}
      </div>

      {r.regime && <Label>Regime: {r.regime}</Label>}
      {r.chain.length > 0 && (
        <div className={cn("mb-4 flex flex-wrap items-center gap-x-1.5 gap-y-1.5 text-[12px]", p.quiet && "gap-x-2 gap-y-2")}>
          {(p.quiet ? chainLinks(r.chain) : r.chain).map((link, i) => (
            <span key={i} className="contents">
              {i > 0 && (
                <span aria-hidden className={p.quiet ? "text-ink-4" : "text-ink-3"}>
                  →
                </span>
              )}
              <span
                className={
                  p.lum
                    ? "rounded-full border border-white/10 bg-white/[0.03] px-2.5 py-1 text-ink-2"
                    : p.quiet
                      ? "rounded-[3px] border border-ring-2 px-2 py-1 text-ink-2"
                      : "border border-ring bg-surface-2 px-2 py-0.5 text-ink"
                }
              >
                {link}
              </span>
            </span>
          ))}
        </div>
      )}

      {r.at_open && (
        <>
          <Label>{live ? "Where we are" : "At the open"}</Label>
          <P>{r.at_open}</P>
        </>
      )}

      {r.wrong_if &&
        (p.quiet ? (
          <>
            <Label>Wrong if</Label>
            <p
              className="mb-4 border-l-[3px] pl-3 text-[13.5px] leading-[1.6] font-semibold text-ink"
              style={{ borderColor: ink }}
            >
              {r.wrong_if}
            </p>
          </>
        ) : (
          <div className="mb-4 border-l-[3px] bg-surface-2 px-3 py-2" style={{ borderColor: ink }}>
            <Label>Wrong if</Label>
            <div className="text-[13px] leading-snug text-ink">{r.wrong_if}</div>
          </div>
        ))}

      <Label>Rest of day</Label>
      {call?.rest_of_day && (
        <div className="mb-1.5">
          <Chip hue={p.ink(call.rest_of_day_bias)} className="ml-0">
            {call.rest_of_day}
          </Chip>
        </div>
      )}
      {r.rest_of_day && <P>{r.rest_of_day}</P>}

      {r.flips.length > 0 && (
        <>
          <Label>What flips it</Label>
          <ul className="mb-4 space-y-1">
            {r.flips.map((x, i) => (
              <li key={i} className="flex gap-2 text-[13px] leading-snug text-ink">
                <span aria-hidden className="text-ink-3">
                  ↺
                </span>
                {x}
              </li>
            ))}
          </ul>
        </>
      )}

      {r.drivers.length > 0 && (
        <>
          <Label>Drivers</Label>
          <ul className="border-t border-ring/60">
            {r.drivers.map((d, i) => (
              <li key={i} className="flex gap-2.5 border-b border-ring/60 py-1.5 text-[12.5px] leading-snug">
                <span
                  className={cn("mt-[6px] h-[7px] w-[7px] shrink-0", p.mark)}
                  style={{ background: tones[d.tone] }}
                  title={d.tone}
                />
                <span>
                  <strong className="font-semibold text-ink">{d.label}</strong>{" "}
                  <span className="text-ink-2">{d.text}</span>
                </span>
              </li>
            ))}
          </ul>
          <div className="mt-2 flex flex-wrap gap-x-3 text-[11px] text-ink-3">
            {(Object.keys(TONE_HUE) as Tone[]).map((t) => (
              <span key={t} className={cn("inline-flex items-center gap-1", p.quiet && "gap-1.5")}>
                <span className={cn("h-[7px] w-[7px]", p.mark)} style={{ background: tones[t] }} />
                {p.quiet ? TONE_WORD[t] : t}
              </span>
            ))}
          </div>
        </>
      )}
    </div>
  );
}

/* ---------------------------------------------------------------- rotation */

function Rotation({ f, b, span }: { f: BriefFacts; b: BriefBody; span?: string }) {
  const p = usePaint();
  const { ratios, megacaps, megacap_index, index_pct } = f.rotation;
  if (ratios.length === 0 && megacaps.length === 0) return null;
  const reads = new Map(b.ratio_reads.map((r) => [r.id, r.read]));
  return (
    <Section title="Rotation" span={span}>
      {b.rotation_read && <P>{b.rotation_read}</P>}
      {ratios.length > 0 && (
        <table className="mb-4 w-full border-collapse border-t border-ring/60">
          <tbody>
            {ratios.map((r) => (
              <tr key={r.id} className="border-b border-ring/60 align-top">
                <td className="fig w-[104px] py-1.5 pr-2 text-[12px] font-semibold whitespace-nowrap text-ink">
                  {r.id}
                </td>
                <td className="fig w-[96px] py-1.5 pr-3 text-right text-[12px] whitespace-nowrap text-ink">
                  {num(r.level, r.level < 10 ? 3 : 2)} <span className={r.dir}>{ARROW[r.dir]}</span>
                </td>
                <td className="py-1.5 text-[12.5px] leading-snug text-ink-2">
                  {reads.get(r.id) ??
                    (r.chg_5d !== null && (
                      <span className="text-ink-3">{pct(r.chg_5d)} over 5 sessions</span>
                    ))}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      )}
      {megacaps.length > 0 && (
        <div className="mb-3">
          <Label>
            Megacaps
            {megacap_index && index_pct !== null ? ` (${megacap_index} ${pct(index_pct, 1)})` : ""}
          </Label>
          <div className="flex flex-wrap gap-1.5">
            {megacaps.map((m) => {
              const hue = m.pct === null ? "var(--ink-3)" : m.pct >= 0 ? "var(--call)" : "var(--put)";
              if (p.quiet) {
                // A hairline chip with the move in its hue — no tinted fill.
                return (
                  <span
                    key={m.symbol}
                    className={cn("fig border px-2 py-[3px] text-[11.5px]", p.lum ? "rounded-full border-white/10 bg-white/[0.03] px-2.5" : "rounded-[3px] border-ring-2")}
                  >
                    <span className="text-ink">{m.symbol}</span>{" "}
                    <span className={dir(m.pct)}>{pct(m.pct, 1)}</span>
                  </span>
                );
              }
              return (
                <span
                  key={m.symbol}
                  className="fig rounded-[3px] px-1.5 py-0.5 text-[11px] text-ink"
                  style={{ background: tint(hue, 22) }}
                >
                  {m.symbol} {pct(m.pct, 1)}
                </span>
              );
            })}
          </div>
        </div>
      )}
      {b.rotation_notes.map((n, i) => (
        <P key={i} muted>
          {n}
        </P>
      ))}
    </Section>
  );
}

/* ---------------------------------------------------------------- headlines */

function Headlines({ f, b, span }: { f: BriefFacts; b: BriefBody; span?: string }) {
  const byId = new Map(f.headlines.map((h) => [h.id, h]));
  const picks = b.headlines.filter((p) => byId.has(p.id));
  if (picks.length === 0) return null;
  return (
    <Section title="Headlines that move price" span={span}>
      <ul className="border-t border-ring/60">
        {picks.map((p) => {
          const h = byId.get(p.id)!;
          return (
            <li key={p.id} className="border-b border-ring/60 py-2.5">
              <div className="flex flex-wrap items-center text-[11px] text-ink-3">
                <span className="qt:hidden">{[h.publisher, h.time_et].filter(Boolean).join(", ")}</span>
                <span className="hidden text-ink-3 qt:inline">
                  <span className="qt-cap text-[10px] text-ink-3">{h.publisher}</span>
                  {h.time_et ? ` · ${h.time_et}` : ""}
                </span>
                {p.books.length > 0 && <Chip>{p.books.map((bk) => BOOK_NAME[bk]).join(" + ")}</Chip>}
              </div>
              {h.url ? (
                <a
                  href={h.url}
                  target="_blank"
                  rel="noreferrer noopener"
                  className="mt-0.5 block text-[13.5px] leading-snug text-ink hover:underline"
                >
                  {h.title}
                </a>
              ) : (
                <div className="mt-0.5 text-[13.5px] leading-snug text-ink">{h.title}</div>
              )}
              {p.note && <div className="mt-0.5 text-[12px] leading-snug text-ink-3">{p.note}</div>}
            </li>
          );
        })}
      </ul>
    </Section>
  );
}

/* ---------------------------------------------------------------- type */

function Section({
  title,
  children,
  span,
  right,
}: {
  title: string;
  children: React.ReactNode;
  /** Luminous: how much of the twelve-column row this card takes. */
  span?: string;
  /** Luminous: a few quiet words at the end of the card's title line. */
  right?: string;
}) {
  const p = usePaint();
  if (p.lum) {
    return (
      <section className={cn("qt-card min-w-0 px-5 pt-4 pb-5", span)} aria-label={title}>
        <h3 className="mb-3.5 flex items-baseline justify-between gap-3">
          <span className="text-[14.5px] font-semibold text-ink">{title}</span>
          {right && <span className="truncate text-[11px] text-ink-3">{right}</span>}
        </h3>
        {children}
      </section>
    );
  }
  return (
    <section className={cn("mt-6 border-t pt-5", p.quiet ? "mt-7 border-ring" : "border-ring/60")}>
      <h3
        className={
          p.quiet ? "qt-cap mb-3.5 text-[11.5px] text-ink-3" : "mb-3 font-serif text-[19px] font-normal text-ink"
        }
      >
        {title}
      </h3>
      {children}
    </section>
  );
}

function Label({ children, className }: { children: React.ReactNode; className?: string }) {
  const p = usePaint();
  return (
    <div
      className={cn(
        p.quiet ? "qt-cap mt-3 mb-1.5 block text-[10.5px] text-ink-3 first:mt-0" : "mb-1 text-[12px] text-ink-3",
        className,
      )}
    >
      {children}
    </div>
  );
}

/** A chain whose model wrote "A → B" inside one link gets it split — the page draws the arrows. */
function chainLinks(chain: string[]): string[] {
  return chain
    .flatMap((l) => l.split(/\s*(?:→|->)\s*/))
    .map((l) => l.trim())
    .filter(Boolean);
}

function P({
  children,
  muted,
  className,
}: {
  children: React.ReactNode;
  muted?: boolean;
  className?: string;
}) {
  return (
    <p
      className={cn(
        "mb-3 text-[13.5px] leading-[1.6]",
        MEASURE,
        muted ? "text-ink-3" : "text-ink-2",
        className,
      )}
    >
      {children}
    </p>
  );
}

function Chip({
  hue,
  quietHue,
  className,
  children,
}: {
  hue?: string;
  /** The hue in Quiet, when it differs — "high impact" is a warning there, not the flip. */
  quietHue?: string;
  className?: string;
  children: React.ReactNode;
}) {
  const p = usePaint();
  const h = hue ?? "var(--ink-2)";
  if (p.lum) {
    // Luminous: a pill, as every chip there is. A toned one carries its hue faintly.
    const q = quietHue ?? hue;
    return (
      <span
        className={cn("ml-2 inline-flex items-center rounded-full border px-2 py-px align-[1px] text-[10.5px] leading-[15px] font-medium whitespace-nowrap", className)}
        style={{
          color: q ?? "var(--ink-3)",
          borderColor: q ? `color-mix(in oklab, ${q} 38%, transparent)` : "rgba(255,255,255,0.1)",
          background: q ? `color-mix(in oklab, ${q} 10%, transparent)` : "transparent",
        }}
      >
        {children}
      </span>
    );
  }
  if (p.quiet) {
    // Quiet drops the box: a toned chip is a square marker and caps in its hue,
    // a neutral one plain caps (GEXYGEN's LumChip under .ui-qt).
    const q = quietHue ?? hue;
    return (
      <span
        className={cn("qt-cap ml-2 inline-flex items-center gap-1 align-[1px] text-[9.5px]", className)}
        style={{ color: q ?? "var(--ink-3)" }}
      >
        {q && <span aria-hidden className="h-[5px] w-[5px] shrink-0 bg-current" />}
        {children}
      </span>
    );
  }
  return (
    <span
      className={cn(
        "ml-1.5 inline-block rounded-[3px] px-1.5 py-px align-[1px] text-[10.5px] leading-[16px] font-semibold",
        className,
      )}
      style={{ color: h, background: tint(h, 16) }}
    >
      {children}
    </span>
  );
}
