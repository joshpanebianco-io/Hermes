"use client";

import { useEffect, useMemo, useState } from "react";
import type {
  Bias,
  Report as ReportT,
  ReportAsset,
  ReportBody,
  ReportSession,
} from "@/types/terminal";
import type { ReportController } from "@/lib/useReport";
import { DESK_REPORT, SESSION_PICKS, assetWord, covers, deskOf, subjectFor, type ReportDesk } from "@/lib/reportDesk";
import { oneOf, usePersisted } from "@/lib/usePersisted";
import { Brief } from "@/components/panels/Brief";
import { Module } from "@/components/ui/Module";
import { PastList } from "@/components/panels/PastList";
import { biasHue, biasLabel } from "@/lib/bias";
import { cn } from "@/lib/cn";
import { segItem } from "@/lib/seg";
import { HelmMark, HelmSweep, useHelmId } from "@/components/ui/HelmLoader";
import { useLum, useQuiet } from "@/components/state/UiMode";
import { NoteAge } from "@/components/ui/NoteAge";

/**
 * The session report — a model's read of the whole terminal.
 *
 * WHAT THIS PANEL IS CAREFUL ABOUT. The owner chose to have the model form the
 * view rather than narrate a deterministic one (see server/newsterminal/
 * report.py). That makes the provenance strip below load-bearing rather than
 * decorative: the model name, the moment, and a link to the exact digest it was
 * shown are the only way to tell a good call from a lucky one later. Nothing
 * here is generated locally — with no key the panel says so and shows nothing,
 * because a fabricated bias rendered in the same frame as a real one is the
 * worst thing this product could do.
 *
 * THE BIAS BAR IS A POSITION, NOT A GAUGE. Five states from bearish to bullish
 * with a mark on a track, because "leaning bearish" is a point on a line and a
 * coloured pill would lose the distance between it and "bearish".
 */

/**
 * Which session the report is for: Asia, London or New York.
 *
 * THIS DESK TRADES THREE OF THEM, so a report cannot assume New York. The row opens on
 * the session the clock says is trading or about to (there is no "Auto" pill: the lit
 * one IS the clock's, until another is picked), and the other two are for writing
 * tomorrow's Asia report this afternoon.
 *
 * The choice reaches the model as a different SYSTEM PROMPT, not as a filter on
 * the data: what leads a session, what hands over to it and how it behaves are
 * all different, and a New York framing at 20:00 ET produces a note about the
 * Fed when the reader is about to trade the Nikkei.
 */
/*
 * WHAT THE REPORT IS ABOUT, BY DESK (owner, 2026-11-16: "in both futures and stocks lets
 * add Market Report tab with the generate funcitonality next to cl and then next to
 * charts", lib/reportDesk has the rest). This panel is the Futures tab's Market Report
 * view, with a pill for each of NQ, ES, GC, SIL and CL and one for each session, and the
 * Stocks tab's, with SPY · QQQ · IWM and New York. It was one page from 2026-11-15, with
 * Indexes (NQ and ES together), Gold, Silver and Oil; a report stored then opens under
 * each book it carries.
 *
 * Picking a book narrows the ladder, the session ranges and the drivers in the digest to
 * it, and swaps the prompt's driver block: told to write about crude, a model handed the
 * equity blocks would otherwise work through technology's relative strength on the way
 * to a call that has nothing to do with it.
 *
 * THE STOCKS REPORT IS NOT THE MARKET OVERVIEW. The 09:00 ET overview (server
 * overview.py) still writes itself for the Dashboard's card; the report here is the
 * market report sheet, the Futures one's design, for the three funds (server
 * report._etf_facts).
 */

/**
 * STATE LIVES IN `useReport`, ABOVE THE TAB SWITCH, and that is a fix rather
 * than a preference. This panel is unmounted when you leave the tab, so an
 * in-flight generation was being abandoned mid-request: the fetch was
 * cancelled, `busy` was lost with the component, and coming back showed the
 * previous report as though nothing had happened. A generation takes two to
 * three minutes on a free model, which is exactly long enough that switching
 * tabs while it runs is the normal thing to do.
 *
 * THE PILLS CHOOSE WHAT IS READ, NOT ONLY WHAT IS WRITTEN. The page shows the newest
 * stored report for the pair that is lit, opening it from the list if the one in hand
 * is another pair's; a pair with none says so and offers Generate. A report picked from
 * Past reports lights its own pair and stays up until the pills move or a new one is
 * written. A generation that failed is not stored, so it is shown where it happened
 * and goes when the pills move.
 */
export function Report({
  feed,
  busy,
  writing,
  viewing,
  generate,
  open,
  discard,
  discardMany,
  discardAll,
  retry,
  startedAt,
  clockSession,
  desk,
}: ReportController & {
  /** The session the clock says is trading or about to: the pill lit until one is picked. */
  clockSession: ReportSession;
  /** Which tab this is: the Futures desk's report or the Stocks desk's (lib/reportDesk). */
  desk: ReportDesk;
}) {
  const quiet = useQuiet();
  const [showDigest, setShowDigest] = useState(false);
  const enabled = feed?.config?.enabled ?? false;
  const cfg = DESK_REPORT[desk];
  // One report is written at a time, for either desk: this view waits on its own and
  // says so of the other's.
  const mine = busy && (writing == null || deskOf(writing) === desk);
  const theirs = busy && !mine;
  /** The loader is what the card holds: the one state that is stood in the middle of it. */
  const waiting = enabled && mine;

  // What it is about, remembered per desk; the session is not remembered (2026-11-15: a
  // session kept from last night left a page opened in the New York morning on Asia).
  const [subject, setSubject] = usePersisted<ReportAsset>(
    `report.${desk}.asset`,
    cfg.subjects[0].key,
    oneOf(...cfg.subjects.map((s) => s.key)),
  );
  const [pick, setPick] = useState<ReportSession | "auto">("auto");
  const session: ReportSession =
    cfg.sessions.length === 1
      ? cfg.sessions[0]
      : pick !== "auto"
        ? pick
        : cfg.sessions.includes(clockSession)
          ? clockSession
          : cfg.sessions[0];
  const all = useMemo(() => feed?.history ?? [], [feed?.history]);
  // Each desk's Past reports are its own.
  const history = useMemo(() => all.filter((h) => deskOf(h.asset) === desk), [all, desk]);
  /** A past report the reader opened by hand, while it is still kept. */
  const [chosen, setChosen] = useState<string | null>(null);
  /** A failed generation the reader has moved on from. */
  const [dismissed, setDismissed] = useState<string | null>(null);
  const kept = chosen && history.some((h) => h.id === chosen) ? chosen : null;
  const pair = history.find((h) => covers(h.asset, subject) && h.session === session) ?? null;
  const wantId = kept ?? pair?.id ?? null;
  const latest = feed?.latest ?? null;
  // Not stored, so not in the list: the envelope of a generation that failed, on its own desk.
  const failed =
    latest && latest.error && deskOf(latest.asset) === desk && !all.some((h) => h.id === latest.id) && latest.id !== dismissed
      ? latest
      : null;
  const rep = failed ?? (wantId && latest?.id === wantId ? latest : null);
  /** The pair has a stored report and it is not the one in hand yet. */
  const opening = !failed && wantId !== null && latest?.id !== wantId;
  useEffect(() => {
    if (!failed && !mine && wantId && latest?.id !== wantId && viewing !== wantId) open(wantId);
  }, [failed, mine, wantId, latest?.id, viewing, open]);

  const move = () => {
    setChosen(null);
    if (failed) setDismissed(failed.id);
  };
  const write = () => {
    move();
    generate(session, subject);
  };
  const openPast = (id: string) => {
    const h = history.find((x) => x.id === id);
    if (h) {
      setSubject(subjectFor(h.asset, subject, desk));
      if (h.session && cfg.sessions.includes(h.session)) setPick(h.session);
    }
    if (failed) setDismissed(failed.id);
    setChosen(id);
  };
  const subjectLabel = cfg.subjects.find((s) => s.key === subject)?.label ?? subject;
  const what = `${subjectLabel} · ${SESSION_PICKS.find((x) => x.key === session)?.label ?? ""}`;

  /*
   * LUMINOUS DRAWS A BRIEF AS A BOARD OF CARDS (panels/Brief, LUM): the report's card is
   * then only its bar (the title, what it is about, which session, Generate), which stays
   * put, and the brief's own cards scroll under it. Every other state (the loader, a
   * failure, no key, an old note) is still one card that fills the column.
   */
  const lum = useLum();
  const board = lum && enabled && !mine && Boolean(rep && !rep.error && rep.report && rep.format === "brief" && rep.facts);

  return (
    <div className="qt-board grid min-h-0 flex-1 grid-cols-1 gap-2 overflow-y-auto p-2 xl:grid-cols-[minmax(0,3fr)_minmax(260px,1fr)] xl:overflow-hidden">
      {/* Shrinkable only side by side: stacked, a column that shrinks spills into the next
          one (the report was drawn under Past calls on a window narrower than xl). */}
      <div className={cn("flex min-w-0 flex-col gap-2 lum:gap-[var(--lum-gap)] xl:min-h-0", board ? "xl:overflow-hidden" : "xl:overflow-y-auto")}>
        <Module
          title="Market report"
          large
          /*
           * THE CARD RUNS TO THE FOOT OF ITS COLUMN WHATEVER IT HOLDS (owner, 2026-11-12:
           * "when we generate brief on the futures tab, the card doesnt go all the way to
           * the bottom"). It was as tall as its contents, so the loader, a failure or "no
           * report yet" left a 430px card beside Past calls, which runs the full height.
           * `grow` and not `flex-1`: a brief longer than the column must keep its height
           * and scroll the column, not be cut to it.
           */
          className={board ? "shrink-0" : "xl:grow"}
          sub={rep ? [assetWord(rep.asset), rep.session_label, rep.et_label].filter(Boolean).join(" · ") : what}
          bodyClassName={board ? "hidden" : cn("px-0 py-0", waiting && "flex flex-col justify-center")}
          /*
           * A FAILED TRIP IS STATED, NOT DRESSED AS SOMETHING ELSE. It used to
           * fall through to the no-key screen. With a report already on the
           * page, the reason rides above it and the report stays readable.
           */
          error={
            feed?.offline && enabled
              ? `Collector unreachable — ${feed.offline.reason}. Showing the report this page already holds.`
              : null
          }
          right={
            <div className="flex flex-wrap items-center justify-end gap-1.5">
              <div className="seg" role="group" aria-label="What the report is about">
                {cfg.subjects.map((ap) => (
                  <button
                    key={ap.key}
                    type="button"
                    onClick={() => {
                      move();
                      setSubject(ap.key);
                    }}
                    title={ap.title}
                    {...segItem(subject === ap.key, { className: "text-[11px] leading-[17px]" })}
                  >
                    {ap.label}
                  </button>
                ))}
              </div>
              <span aria-hidden className="h-3.5 w-px bg-ring qt:hidden" />
              <div className="seg" role="group" aria-label="Which session the report is for">
                {SESSION_PICKS.filter((sp) => cfg.sessions.includes(sp.key)).map((sp) => (
                  <button
                    key={sp.key}
                    type="button"
                    onClick={() => {
                      move();
                      setPick(sp.key);
                    }}
                    title={pick === "auto" && sp.key === clockSession ? `${sp.title} · the session the clock says is next` : sp.title}
                    {...segItem(session === sp.key, { className: "text-[11px] leading-[17px]" })}
                  >
                    {sp.label}
                  </button>
                ))}
              </div>
              {/*
                * The model's name used to sit here. It is not a control and it
                * does not change between presses, so it was noise beside the
                * one button that matters; it is still stated where it is
                * evidence — under the note it wrote, and on the loader.
                *
                * `.generate` (globals.css) is the button's whole look. It stays
                * `disabled` while busy so a second press cannot queue a second
                * report, and `data-busy` is what stops that reading as dead.
                */}
              <GenerateButton
                onClick={write}
                busy={busy}
                enabled={enabled}
                busyTitle={
                  theirs
                    ? `The ${desk === "futures" ? "Stocks" : "Futures"} tab's report is being written: one report at a time`
                    : "Reading the terminal and generating the report — usually one to three minutes"
                }
                idleTitle={`Read the terminal as it stands now and write the ${what} report`}
              />
            </div>
          }
        >
          {board ? null : feed?.offline && !enabled ? (
            <Offline reason={feed.offline.reason} api={feed.offline.api} onRetry={retry} />
          ) : !enabled ? (
            <NoKey model={feed?.config?.model} />
          ) : mine ? (
            <Working startedAt={startedAt} model={feed?.config?.model} />
          ) : opening ? (
            <p className="px-4 py-8 text-center text-[11.5px] text-ink-3">Opening the {what} report…</p>
          ) : !rep ? (
            <Empty what={what} />
          ) : rep.error ? (
            <Failed error={rep.error} raw={rep.raw} />
          ) : rep.report ? (
            <>
              <NoteAge createdUtc={rep.created_utc} what="brief" />
              {rep.format === "brief" && rep.facts ? <Brief rep={rep} /> : <Body rep={rep} />}
              <Provenance
                rep={rep}
                showDigest={showDigest}
                onDigest={() => setShowDigest((v) => !v)}
              />
            </>
          ) : (
            <Empty what={what} />
          )}
        </Module>
        {board && rep && (
          <div className="flex min-w-0 flex-col gap-2 lum:gap-[var(--lum-gap)] xl:min-h-0 xl:flex-1 xl:overflow-y-auto">
            {/* The age banner keeps its tint and takes the cards' corners. */}
            <div className="shrink-0 overflow-hidden rounded-[12px] empty:hidden">
              <NoteAge createdUtc={rep.created_utc} what="brief" />
            </div>
            <Brief rep={rep} />
            <div className="qt-card shrink-0 px-2 py-1 [&>div:first-child]:border-t-0 [&>div:first-child]:bg-transparent [&>div:first-child]:pt-2 [&>div:first-child]:text-[11px]">
              <Provenance rep={rep} showDigest={showDigest} onDigest={() => setShowDigest((v) => !v)} />
            </div>
          </div>
        )}
      </div>

      <div className="flex min-w-0 flex-col gap-2 xl:min-h-0 xl:overflow-y-auto">
        {/* Runs to the foot of the column so it ends level with the report
            beside it, and the list scrolls INSIDE it — the wire's arrangement.
            Only at xl, where the two sit side by side; stacked, it is as tall
            as its rows. */}
        <PastList
          title="Past reports"
          noun="report"
          items={history}
          current={rep?.id ?? wantId}
          empty="Nothing yet. Reports are kept so you can check the calls against how the session actually went."
          onOpen={openPast}
          onDiscard={discard}
          onDiscardMany={discardMany}
          onDiscardAll={discardAll}
          row={(h) => (
            <>
              <span className="flex w-full items-baseline gap-2">
                <span className="fig shrink-0 text-[11px] text-ink-3">{h.et_label}</span>
                {/* What it is about, as the pill says it; one stored before the pills keeps
                    its own label beside that when it was about a single index. */}
                <span className="fig shrink-0 rounded bg-ink/10 px-1 text-[10px] text-ink-3 qt:border qt:border-ring-2 qt:bg-transparent">
                  {assetWord(h.asset)}
                </span>
                {/* The one part of this line that may give way: on a narrow
                    column the date, the book and the call all matter more
                    than which session it was, so this is what truncates. */}
                {h.session_label && (
                  <span className="fig min-w-0 truncate text-[10px] text-ink-3">{h.session_label}</span>
                )}
                {h.bias &&
                  (quiet ? (
                    // Quiet: no tinted pill — a square marker and caps in the
                    // side's figure hue, the call's word as the brief prints it.
                    <span
                      className="qt-cap ml-auto inline-flex shrink-0 items-center gap-1 text-[10px]"
                      style={{ color: quietBias(h.bias) }}
                    >
                      <span aria-hidden className="h-[5px] w-[5px] bg-current" />
                      {biasLabel(h.bias)}
                    </span>
                  ) : (
                    <span
                      className="fig ml-auto shrink-0 rounded px-1 text-[10px]"
                      style={{
                        color: biasHue(h.bias),
                        background: `color-mix(in oklab, ${biasHue(h.bias)} 18%, transparent)`,
                      }}
                    >
                      {h.bias}
                    </span>
                  ))}
              </span>
              {h.headline && (
                <span className="line-clamp-2 text-[11.5px] leading-snug text-ink-2">{h.headline}</span>
              )}
            </>
          )}
        />
      </div>
    </div>
  );
}

/** A bias in Quiet's figure tier — the same hues the brief's call wears. */
function quietBias(b: string): string {
  return /bull/.test(b) ? "var(--call-fig)" : /bear/.test(b) ? "var(--put-fig)" : "var(--ink-3)";
}

/* ---------------------------------------------------------------- states */

/**
 * The collector could not be reached and the page holds nothing to show. Not
 * the no-key screen — a key may well be set — and not an empty report: the
 * reason, where it was looked for, and a way to ask again.
 */
export function Offline({
  reason,
  api,
  onRetry,
  what = "Reports",
  title = "Collector unreachable.",
}: {
  reason: string;
  api: string;
  onRetry: () => void;
  /** What is read from the collector — "Reports", "Plans". */
  what?: string;
  /** The state's name — "Collector unreachable." unless the reason says otherwise. */
  title?: string;
}) {
  return (
    <div className="space-y-3 px-4 py-5 text-[11.5px] leading-relaxed text-ink-3">
      <p className="text-err">
        <strong className="font-semibold">{title}</strong> {reason} — expected at{" "}
        <code>{api}</code>.
      </p>
      <p>
        {what} are read from the collector, so there is nothing to show until it answers. Nothing
        here is cached or invented. Start it with <code className="text-ink-2">.\dev.ps1</code>.
      </p>
      <button type="button" onClick={onRetry} {...segItem(false, { className: "border border-ring-2" })}>
        Retry
      </button>
    </div>
  );
}

export function NoKey({ model, what = "report" }: { model?: string; what?: string }) {
  return (
    <div className="space-y-3 px-4 py-5 text-[11.5px] leading-relaxed text-ink-3">
      <p className="text-ink-2">
        The {what} is written by a model, and no key is set — so there is nothing to show.
      </p>
      <p>
        There is deliberately no local fallback. A bias invented by this app and rendered in
        the same frame as a real one would be indistinguishable from it, which is exactly the
        failure the rest of this terminal is built to avoid.
      </p>
      <ol className="ml-4 list-decimal space-y-1">
        <li>
          Get a free key at{" "}
          <a
            href="https://openrouter.ai/keys"
            target="_blank"
            rel="noreferrer noopener"
            className="text-call underline underline-offset-2"
          >
            openrouter.ai/keys
          </a>
          .
        </li>
        <li>
          Put <code className="text-ink-2">OPENROUTER_API_KEY=sk-or-…</code> in{" "}
          <code className="text-ink-2">.env.local</code>.
        </li>
        <li>
          Restart the collector — <code className="text-ink-2">.\dev.ps1</code>.
        </li>
      </ol>
      <p className="text-ink-3">
        Model: <span className="fig">{model ?? "nvidia/nemotron-3.5-super-vl:free"}</span> — free tier, no card.
        Override with <code>NT_REPORT_MODEL</code>. The free tier allows 50 requests a day, or
        1000 once $10 of credit has ever been bought.
      </p>
    </div>
  );
}

/**
 * The generation screen.
 *
 * WHAT IT USED TO BE: "Reading the terminal…" over two paragraphs of caveats
 * about free-tier pools. Read once, that is context; read on every generation,
 * for two to three minutes, it is noise in the one place the eye has nothing
 * else to do. The owner called it useless (2026-09-16), and it was.
 *
 * WHAT IT IS NOW: the helm, breathing on the same wash the header runs; a
 * sweep that says "still working" without pretending to know how far; a clock
 * that says how long it has actually been — the one figure that stops a slow
 * model reading as a hung one; and a single line of what is happening, cycled
 * off the elapsed time rather than off any real signal, because the request is
 * one round trip and there is no real signal to show. The model name is the
 * honest attribution and "usually 1–3 min" the honest expectation.
 *
 * THE SWEEP IS INDETERMINATE ON PURPOSE. A bar that fills to 90% and waits is
 * the most common lie in software; this one only ever says "still going".
 */
const STAGES = [
  "Reading the wire",
  "Placing spot against the walls",
  "Reading the session ranges",
  "Reading the profile against prior value",
  "Weighing the calendar",
  "Forming the call",
  "Writing the read",
];

export function Working({
  startedAt,
  model,
  stages = STAGES,
  noun = "report",
}: {
  startedAt: number | null;
  model?: string;
  /** The lines cycled under the clock — what this kind of writing reads first. */
  stages?: readonly string[];
  /** What is being written, for the attribution line. */
  noun?: string;
}) {
  const [now, setNow] = useState(() => Date.now());
  useEffect(() => {
    const id = window.setInterval(() => setNow(Date.now()), 1000);
    return () => window.clearInterval(id);
  }, []);
  const elapsed = Math.max(0, Math.floor((now - (startedAt ?? now)) / 1000));
  const mm = Math.floor(elapsed / 60);
  const ss = String(elapsed % 60).padStart(2, "0");
  const stage = stages[Math.floor(elapsed / 8) % stages.length];
  const gradId = useHelmId();

  return (
    <div
      className="report-loader flex flex-col items-center px-4 py-14 text-center"
      role="status"
      aria-live="polite"
    >
      {/*
        * The same lockup as the header — same trace, same mirror on a parent
        * group (the glitch animates CSS transform, which would override a
        * transform attribute on the path itself), same 5.6s wash. It is
        * `hermes-mark` so it breathes and glitches on the header's timeline
        * and stands down under prefers-reduced-motion with it.
        */}
      <HelmMark size={88} gradId={gradId} />
      <HelmSweep width={220} gradId={gradId} className="mt-6" />

      <div className="fig mt-5 text-[22px] leading-none text-ink tabular-nums">
        {mm}:{ss}
      </div>
      <div className="mt-2 text-[12px] text-ink-2">{stage}…</div>
      <div className="fig mt-4 text-[10px] text-ink-3">
        {model ? `${model} · ` : ""}usually 1–3 min on the free tier · the {noun} names the
        model that answered
      </div>
    </div>
  );
}

function Empty({ what }: { what: string }) {
  return (
    <p className="px-4 py-8 text-center text-[11.5px] text-ink-3">
      No {what} report yet — press <span className="fig text-flip">Generate</span>.
    </p>
  );
}

export function Failed({ error, raw, noun = "report" }: { error: string; raw?: string | null; noun?: string }) {
  return (
    <div className="space-y-2 px-4 py-4 text-[11.5px] leading-relaxed">
      <p className="text-err">{error}</p>
      {raw && (
        <details className="text-[10.5px] text-ink-3">
          <summary className="cursor-pointer text-ink-3">What the model said instead</summary>
          <pre className="mt-1 max-h-48 overflow-auto whitespace-pre-wrap">{raw}</pre>
        </details>
      )}
      <p className="text-ink-3">
        Nothing is shown above because there is no valid {noun} to show — not because the panel
        is empty.
      </p>
    </div>
  );
}

/**
 * GENERATE — the one control on a writing tab that makes something, so the one
 * that is lit (`.generate` in globals.css). Shared by the Report and the Game
 * plan so the two desks' briefs are summoned by the same key.
 */
export function GenerateButton({
  onClick,
  busy,
  enabled,
  busyTitle,
  idleTitle,
  label = "Generate",
}: {
  onClick: () => void;
  busy: boolean;
  enabled: boolean;
  busyTitle: string;
  idleTitle: string;
  /** The word at rest: the Market view says "Write again" over a note it already holds. */
  label?: string;
}) {
  return (
    <button
      type="button"
      onClick={onClick}
      disabled={busy || !enabled}
      data-busy={busy || undefined}
      className="generate ml-1"
      title={!enabled ? "Needs OPENROUTER_API_KEY" : busy ? busyTitle : idleTitle}
    >
      <svg className="generate-spark" width="11" height="11" viewBox="0 0 11 11" fill="currentColor" aria-hidden>
        {/* Odd-sized, so the star's centre is a whole pixel. */}
        <path d="M5.5 0l1.3 4.2L11 5.5 6.8 6.8 5.5 11 4.2 6.8 0 5.5l4.2-1.3z" />
      </svg>
      {busy ? "Reading…" : label}
    </button>
  );
}

/* ---------------------------------------------------------------- the note */

/**
 * The note as it was before the brief (2026-09-16). Kept so the reports stored
 * before then still render in Past calls — they carry no facts to build a
 * brief from, and redrawing them as one would invent the tables.
 */
function Body({ rep }: { rep: ReportT }) {
  const r = rep.report as ReportBody;
  const hue = biasHue(r.bias);

  return (
    <div>
      {/* ---- the call ------------------------------------------------- */}
      <div className="border-b border-ring/50 px-4 py-3">
        <div className="flex flex-wrap items-baseline gap-x-3 gap-y-1">
          <span className="fig text-[19px] tracking-tight uppercase" style={{ color: hue }}>
            {r.bias}
          </span>
          <span
            className="flex items-center gap-[3px]"
            title="Conviction 1-5 — how strongly the data supports the call. The model's own confidence, not a probability."
          >
            {[1, 2, 3, 4, 5].map((i) => (
              <span
                key={i}
                className="h-[7px] w-[7px] rounded-full"
                style={{ background: i <= r.conviction ? hue : "var(--ring)" }}
              />
            ))}
            <span className="fig ml-1 text-[10px] text-ink-3">
              {r.conviction}/5 conviction
            </span>
          </span>
        </div>

        {/*
         * NO DIRECTIONAL METER, ON PURPOSE — this line replaced two of them
         * in one day. A five-step bias spectrum drew "what do the 5 bars
         * mean?"; a centre-diverging conviction bar drew "why is only a
         * section colored?". Both times the reader had already understood
         * the WORD (direction, in its hue) and the DOTS (strength, in
         * rating grammar) instantly. The meters were decoration explaining
         * things that were not confusing, at the cost of becoming the
         * confusing thing themselves. If a future hand feels this row needs
         * a gauge, read those two quotes first.
         */}

        <p className="text-[13px] leading-snug text-ink">{r.headline}</p>
        <p className="mt-1 text-[11.5px] leading-relaxed text-ink-3">{r.summary}</p>
      </div>

      {/* ---- why ------------------------------------------------------ */}
      <Section title="Why">
        <ul className="space-y-1.5">
          {r.drivers.map((d, i) => (
            <li key={i} className="relative pl-3">
              <span
                aria-hidden
                className="absolute top-[6px] left-0 h-[6px] w-[6px] rounded-full"
                style={{
                  background:
                    d.direction === "bullish"
                      ? "var(--call)"
                      : d.direction === "bearish"
                        ? "var(--put)"
                        : "var(--ink-4)",
                }}
              />
              <span className="text-[11.5px] leading-snug text-ink-2">{d.point}</span>
              <span className="fig ml-1.5 text-[10.5px] text-ink-3">{d.evidence}</span>
            </li>
          ))}
        </ul>
      </Section>

      {/* ---- expected session ----------------------------------------- */}
      <Section title="How the session should behave">
        <p className="text-[11.5px] leading-relaxed text-ink-2">{r.session_expectation}</p>
      </Section>

      {/* ---- levels ---------------------------------------------------- */}
      <Section title="Levels to watch">
        <ul className="space-y-1">
          {r.levels_to_watch.map((l, i) => (
            <li key={i} className="flex flex-wrap items-baseline gap-x-2">
              <span className="fig w-[34px] shrink-0 text-[10.5px] text-ink-3">{l.instrument}</span>
              <span className="fig text-[11.5px] text-ink">{l.level}</span>
              <span className="min-w-0 flex-1 text-[10.5px] text-ink-3">{l.why}</span>
            </li>
          ))}
        </ul>
      </Section>

      {/* ---- what breaks it -------------------------------------------- */}
      <Section title="What would change it">
        <ul className="space-y-1">
          {r.invalidation.map((v, i) => (
            <li key={i} className="text-[11.5px] leading-snug">
              <span className="text-ink-2">{v.condition}</span>
              <span className="text-ink-4"> → </span>
              <span style={{ color: biasHue(v.flips_to as Bias) }}>{v.flips_to}</span>
            </li>
          ))}
        </ul>
      </Section>

      {r.risks?.length > 0 && (
        <Section title="Risks">
          <ul className="space-y-0.5">
            {r.risks.map((x, i) => (
              <li key={i} className="text-[11px] leading-snug text-ink-3">
                · {x}
              </li>
            ))}
          </ul>
        </Section>
      )}

    </div>
  );
}

/* ---------------------------------------------------------------- provenance */

/**
 * Who wrote it, when, and exactly what it was shown. Under the brief and the
 * old note alike, because provenance is what makes either one checkable later.
 */
function Provenance({
  rep,
  showDigest,
  onDigest,
}: {
  rep: ReportT;
  showDigest: boolean;
  onDigest: () => void;
}) {
  return (
    <>
      <div className="flex flex-wrap items-center gap-x-3 gap-y-1 border-t border-ring/50 bg-surface-2/30 px-4 py-2 text-[9.5px] text-ink-3 qt:mx-3 qt:border-ring qt:bg-transparent qt:px-0 qt:pt-3">
        <span className="fig">{rep.model}</span>
        <span aria-hidden>·</span>
        <span className="fig">{rep.asset_label}</span>
        <span aria-hidden>·</span>
        <span className="fig">{rep.session_label} session</span>
        <span aria-hidden>·</span>
        <span className="fig">{rep.et_label}</span>
        {rep.usage?.total_tokens && (
          <>
            <span aria-hidden>·</span>
            <span className="fig">{rep.usage.total_tokens} tok</span>
          </>
        )}
        {/* What the model wrote, counted by the collector (a short brief's limit is in
            words): the page's tables are not in it. */}
        {typeof rep.words === "number" && (
          <>
            <span aria-hidden>·</span>
            <span className="fig">{rep.words} words written</span>
          </>
        )}
        <button
          type="button"
          onClick={onDigest}
          className="fig ml-auto rounded border border-ring px-1.5 py-px text-[9px] hover:text-ink-2 qt:rounded-[3px] qt:border-ring-2 qt:px-2 qt:py-[3px] qt:font-sans qt:text-[11.5px] qt:text-ink-3"
        >
          {showDigest ? "Hide" : "Show"} the data it saw
        </button>
      </div>

      {showDigest && (
        <pre className="max-h-[420px] overflow-auto border-t border-ring/50 bg-void/50 px-4 py-2 text-[9.5px] leading-relaxed text-ink-3 qt:mx-3 qt:mt-2 qt:rounded-[4px] qt:border qt:border-ring qt:bg-surface-2/60 qt:px-3">
          {JSON.stringify(rep.digest, null, 1)}
        </pre>
      )}
    </>
  );
}

function Section({ title, children }: { title: string; children: React.ReactNode }) {
  return (
    <div className="border-b border-ring/40 px-4 py-2.5 last:border-b-0">
      <div className="eyebrow mb-1.5 text-[9px]">{title}</div>
      {children}
    </div>
  );
}

/** Five pips. The model's own confidence, which is not a probability. */
