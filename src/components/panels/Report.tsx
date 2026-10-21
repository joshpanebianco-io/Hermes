"use client";

import { useEffect, useState } from "react";
import type {
  Bias,
  Report as ReportT,
  ReportAsset,
  ReportBody,
  ReportSession,
} from "@/types/terminal";
import type { ReportController } from "@/lib/useReport";
import { Brief } from "@/components/panels/Brief";
import { Module } from "@/components/ui/Module";
import { biasHue, biasLabel } from "@/lib/bias";
import { cn } from "@/lib/cn";
import { segItem } from "@/lib/seg";
import { HelmMark, HelmSweep, useHelmId } from "@/components/ui/HelmLoader";
import { useQuiet } from "@/components/state/UiMode";
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
 * Which session the note is written for.
 *
 * THIS DESK TRADES THREE OF THEM, so the note cannot assume New York. `Auto`
 * resolves from the ET clock to the session that is trading or about to — what
 * pressing Generate almost always means — and the three explicit choices are
 * for writing tomorrow's Asia note this afternoon.
 *
 * The choice reaches the model as a different SYSTEM PROMPT, not as a filter on
 * the data: what leads a session, what hands over to it and how it behaves are
 * all different, and a New York framing at 20:00 ET produces a note about the
 * Fed when the reader is about to trade the Nikkei.
 */
const SESSION_PICKS: { key: ReportSession | "auto"; label: string; title: string }[] = [
  { key: "auto", label: "Auto", title: "Whichever session is trading or about to — from the ET clock" },
  { key: "asia", label: "Asia", title: "18:00–03:00 ET · Nikkei, Hang Seng, USD/JPY" },
  { key: "london", label: "London", title: "03:00–08:00 ET · FTSE, DAX, EUR/USD, Bunds" },
  { key: "ny", label: "NY", title: "09:30–16:00 ET · NQ, ES, the curve, the dollar" },
];

/**
 * STATE LIVES IN `useReport`, ABOVE THE TAB SWITCH, and that is a fix rather
 * than a preference. This panel is unmounted when you leave the tab, so an
 * in-flight generation was being abandoned mid-request: the fetch was
 * cancelled, `busy` was lost with the component, and coming back showed the
 * previous report as though nothing had happened. A generation takes two to
 * three minutes on a free model, which is exactly long enough that switching
 * tabs while it runs is the normal thing to do.
 */
/**
 * Which book the note is about.
 *
 * `All` is the right default when you are deciding WHAT to trade; the three
 * single-asset choices are for when you have already decided and want the
 * note's whole attention on one instrument. Picking one narrows the gamma
 * ladder, the session ranges and the index movers in the digest, and swaps the
 * prompt's driver block — told to write about gold, a model handed the equity
 * blocks will otherwise work through technology's relative strength on the way
 * to a call that has nothing to do with it.
 *
 * It is still ONE request either way, so a focused note costs no more of the
 * free tier's daily allowance than the combined one.
 */
const ASSET_PICKS: { key: ReportAsset; label: string; title: string }[] = [
  { key: "all", label: "All", title: "NQ, ES and GC together — where they agree and where they do not" },
  { key: "NQ", label: "NQ", title: "NQ futures and QQQ · cap-weighted, long duration, the heavy names are the story" },
  { key: "ES", label: "ES", title: "ES futures and SPY · broader, sector rotation and breadth carry more" },
  { key: "GC", label: "GC", title: "GC futures and GLD · real yields, the dollar and geopolitics — not the equity blocks" },
];

export function Report({
  pick,
  setPick,
  book,
  setBook,
  feed,
  busy,
  viewing,
  generate,
  open,
  discard,
  retry,
  startedAt,
}: ReportController) {
  const quiet = useQuiet();
  const [showDigest, setShowDigest] = useState(false);
  /** Which row is asking "Delete this report?" — one at a time. */
  const [confirming, setConfirming] = useState<string | null>(null);
  const rep = feed?.latest ?? null;
  const enabled = feed?.config?.enabled ?? false;

  return (
    <div className="qt-board grid min-h-0 flex-1 grid-cols-1 gap-2 overflow-y-auto p-2 xl:grid-cols-[minmax(0,3fr)_minmax(260px,1fr)] xl:overflow-hidden">
      <div className="flex min-h-0 min-w-0 flex-col gap-2 xl:overflow-y-auto">
        <Module
          title="Session report"
          large
          sub={
            rep
              ? [rep.asset_label, rep.session_label, rep.et_label]
                  .filter(Boolean)
                  .join(" · ")
              : undefined
          }
          bodyClassName="px-0 py-0"
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
            <div className="flex items-center gap-1.5">
              <div className="seg">
                {ASSET_PICKS.map((ap) => (
                  <button
                    key={ap.key}
                    type="button"
                    onClick={() => setBook(ap.key)}
                    title={ap.title}
                    {...segItem(book === ap.key, { className: "text-[11px] leading-[17px]" })}
                  >
                    {ap.label}
                  </button>
                ))}
              </div>
              <span aria-hidden className="h-3.5 w-px bg-ring qt:hidden" />
              <div className="seg">
                {SESSION_PICKS.map((sp) => (
                  <button
                    key={sp.key}
                    type="button"
                    onClick={() => setPick(sp.key)}
                    title={sp.title}
                    {...segItem(pick === sp.key, { className: "text-[11px] leading-[17px]" })}
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
                onClick={generate}
                busy={busy}
                enabled={enabled}
                busyTitle="Reading the terminal and generating the report — usually one to three minutes"
                idleTitle="Read the terminal as it stands now and generate a fresh report"
              />
            </div>
          }
        >
          {feed?.offline && !enabled ? (
            <Offline reason={feed.offline.reason} api={feed.offline.api} onRetry={retry} />
          ) : !enabled ? (
            <NoKey model={feed?.config?.model} />
          ) : busy ? (
            <Working startedAt={startedAt} model={feed?.config?.model} />
          ) : !rep ? (
            <Empty />
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
            <Empty />
          )}
        </Module>
      </div>

      <div className="flex min-h-0 min-w-0 flex-col gap-2 xl:overflow-y-auto">
        {/* Runs to the foot of the column so it ends level with the report
            beside it, and the list scrolls INSIDE it — the wire's arrangement.
            Only at xl, where the two sit side by side; stacked, it is as tall
            as its rows. */}
        <Module
          title="Past calls"
          large
          sub={`${feed?.history?.length ?? 0} kept`}
          className="xl:min-h-0 xl:flex-1"
          bodyClassName="px-0 py-0 xl:min-h-0 xl:overflow-y-auto"
        >
          {!feed?.history?.length ? (
            <p className="px-3 py-5 text-center text-[11px] text-ink-3">
              Nothing yet. Reports are kept so you can check the calls against how the
              session actually went.
            </p>
          ) : (
            <ul>
              {feed.history.map((h) => (
                <li key={h.id} className="group relative">
                  <button
                    type="button"
                    onClick={() => open(h.id)}
                    className={cn(
                      "hit flex w-full flex-col items-start gap-0.5 py-1.5 pr-7 pl-3 text-left",
                      "qt:gap-1 qt:border-b qt:border-ring/60 qt:py-2.5",
                      (viewing ?? rep?.id) === h.id && "bg-ink/[0.06] qt:bg-surface-2",
                    )}
                  >
                    <div className="flex w-full items-baseline gap-2">
                      <span className="fig shrink-0 text-[11px] text-ink-3">{h.et_label}</span>
                      {h.asset_label && h.asset !== "all" && h.asset_label !== "All three books" && (
                        <span className="fig shrink-0 rounded bg-ink/10 px-1 text-[10px] text-ink-3 qt:border qt:border-ring-2 qt:bg-transparent">
                          {h.asset_label}
                        </span>
                      )}
                      {/* The one part of this line that may give way: on a narrow
                          column the date, the book and the call all matter more
                          than which session it was, so this is what truncates. */}
                      {h.session_label && (
                        <span className="fig min-w-0 truncate text-[10px] text-ink-3">
                          {h.session_label}
                        </span>
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
                    </div>
                    {h.headline && (
                      <span className="line-clamp-2 text-[11.5px] leading-snug text-ink-2">
                        {h.headline}
                      </span>
                    )}
                  </button>
                  {/*
                    * DELETE IS A SIBLING OF THE ROW BUTTON, NOT A CHILD OF IT.
                    * A button inside a button is invalid HTML and browsers
                    * resolve it by dropping one of them, so the row reserves
                    * `pr-7` and this sits in the gutter it leaves.
                    *
                    * IT ASKS FIRST, INLINE. `window.confirm` would do the job
                    * and is the wrong tool twice over: a modal dialog blocks
                    * the whole page, and the thing being confirmed is a row you
                    * can no longer see behind it. This keeps the row on screen
                    * and puts the question over it. Deleting is permanent —
                    * there is no trash folder on the collector.
                    */}
                  {confirming === h.id ? (
                    <div className="absolute inset-0 flex items-center gap-1.5 bg-surface-2 px-3">
                      <span className="mr-auto text-[10px] text-ink-3">Delete this report?</span>
                      <button
                        type="button"
                        onClick={() => {
                          discard(h.id);
                          setConfirming(null);
                        }}
                        className="hit rounded px-1.5 py-0.5 text-[10px] font-semibold text-warn"
                      >
                        Delete
                      </button>
                      <button
                        type="button"
                        onClick={() => setConfirming(null)}
                        className="hit rounded px-1.5 py-0.5 text-[10px] text-ink-3"
                      >
                        Keep
                      </button>
                    </div>
                  ) : (
                    <button
                      type="button"
                      onClick={() => setConfirming(h.id)}
                      title="Delete this report"
                      aria-label={`Delete the report from ${h.et_label}`}
                      /*
                       * Revealed on hover, but focus-visible brings it back for
                       * the keyboard — an opacity-0 control that only a mouse
                       * can summon is one a keyboard can tab to and not see.
                       */
                      className="hit absolute top-1.5 right-1 rounded px-1 text-[12px] leading-none text-ink-4 opacity-0 group-hover:opacity-100 hover:text-warn focus-visible:opacity-100"
                    >
                      ×
                    </button>
                  )}
                </li>
              ))}
            </ul>
          )}
        </Module>
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

function Empty() {
  return (
    <p className="px-4 py-8 text-center text-[11.5px] text-ink-3">
      No report yet — press <span className="fig text-flip">Generate</span>.
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
}: {
  onClick: () => void;
  busy: boolean;
  enabled: boolean;
  busyTitle: string;
  idleTitle: string;
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
      {busy ? "Reading…" : "Generate"}
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
