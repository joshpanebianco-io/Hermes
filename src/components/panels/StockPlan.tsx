"use client";

import { useState } from "react";
import type { Plan, PlanDriver, PlanFacts, PlanFlow, PlanFlowStrike, PlanItem, PlanMacro, PlanName, PlanRegime } from "@/types/plan";
import type { Conviction, Print } from "@/types/market";
import { PLAN_TOPS } from "@/types/plan";
import type { PlanController } from "@/lib/useStockPlan";
import { Module } from "@/components/ui/Module";
import { HelmLoader } from "@/components/ui/HelmLoader";
import { TickerLogo } from "@/components/ui/TickerLogo";
import { Failed, GenerateButton, NoKey, Offline, Working } from "@/components/panels/Report";
import { useQuiet } from "@/components/state/UiMode";
import { ConvictionBar, SplitBar, biasWord, gradeText, leanText, readText, sideText, stateText, voteGlyph, votesTip } from "@/components/market/shared";
import { bp, compact, dir, num, pct } from "@/lib/format";
import { segItem } from "@/lib/seg";
import { cn } from "@/lib/cn";
import { NoteAge } from "@/components/ui/NoteAge";

/** The engine's setup state in the words the Scanner prints — never the raw key. */
const STATE_WORD: Record<string, string> = {
  retest: "Retest",
  pullback: "Pulling back",
  extended: "Extended",
  approaching: "Near a level",
  chop: "Inside — chop",
  failed: "Failed break",
  forming: "Pre-market plan",
};
const stateWord = (s: string) => STATE_WORD[s] ?? s;

/**
 * The Game plan — the stocks desk's pre-open brief (owner instruction,
 * 2026-10-13: "do everything you recommend" — the review's NY game plan built
 * from the scanner's top names).
 *
 * THE FUTURES REPORT'S CONTRACT, KEPT. The collector reads the live scanner —
 * levels, relative strength, the setup, each name's option chain, the weather
 * and today's prints — into `facts`, and the model writes only words: the
 * plan, the trigger, the invalidation, the target, how to express it in
 * options. Every figure on this page beside the prose is printed from `facts`,
 * never from the model's sentences; a number the model wrote that the facts do
 * not carry is listed in the Unverified banner.
 *
 * A PLAN, NOT A SIGNAL. It is written before the open from the scanner's
 * ranking, which is a heuristic; the scanner's live (L) / (E) signals and its
 * alerts are what say a setup actually triggered.
 */

const STAGES = [
  "Reading the scanner's top names",
  "Placing price against PDH and PMH",
  "Reading the option chains",
  "Weighing the prints and the tape",
  "Writing the plans",
] as const;

const sideHue = (s: "long" | "short" | null) =>
  s === "long" ? "var(--call-fig)" : s === "short" ? "var(--put-fig)" : "var(--ink-3)";

const SESSION: Record<PlanFacts["session"], string> = {
  pre: "pre-market",
  rth: "written in the session",
  post: "post-market",
  closed: "market closed",
};

export function StockPlan({ top, setTop, feed, busy, viewing, generate, open, discard, retry, startedAt }: PlanController) {
  const [showDigest, setShowDigest] = useState(false);
  const [confirming, setConfirming] = useState<string | null>(null);
  const plan = feed?.latest ?? null;
  const enabled = feed?.config?.enabled ?? false;

  return (
    <div className="qt-board grid min-h-0 flex-1 grid-cols-1 gap-2 overflow-y-auto p-2 xl:grid-cols-[minmax(0,3fr)_minmax(260px,1fr)] xl:overflow-hidden">
      <div className="flex min-h-0 min-w-0 flex-col gap-2 xl:overflow-y-auto">
        <Module
          title="Game plan"
          large
          sub={plan ? [plan.et_label, plan.facts ? SESSION[plan.facts.session] : null].filter(Boolean).join(" · ") : "the New York session, from the scanner"}
          bodyClassName="px-0 py-0"
          error={
            feed?.offline && enabled
              ? `Collector unreachable — ${feed.offline.reason}. Showing the plan this page already holds.`
              : null
          }
          right={
            <div className="flex items-center gap-1.5">
              <span className="text-[10.5px] text-ink-3 qt:text-[11.5px]">Names</span>
              <div className="seg" title="How many of the scanner's top-ranked names the plan covers, both sides">
                {PLAN_TOPS.map((n) => (
                  <button key={n} type="button" onClick={() => setTop(n)} {...segItem(top === n, { className: "text-[11px] leading-[17px]" })}>
                    {n}
                  </button>
                ))}
              </div>
              <GenerateButton
                onClick={generate}
                busy={busy}
                enabled={enabled}
                busyTitle="Reading the scanner and writing the plan — usually one to three minutes"
                idleTitle={`Write a plan for the scanner's top ${top} names as they stand now`}
              />
            </div>
          }
        >
          {feed?.offline && !enabled ? (
            <Offline
              reason={feed.offline.reason}
              api={feed.offline.api}
              onRetry={retry}
              what="Plans"
              title={/predates/.test(feed.offline.reason) ? "Collector needs a restart." : undefined}
            />
          ) : !feed ? (
            <PlanSkeleton />
          ) : !enabled ? (
            <NoKey model={feed.config?.model} what="game plan" />
          ) : busy ? (
            <Working startedAt={startedAt} model={feed.config?.model} stages={STAGES} noun="plan" />
          ) : !plan ? (
            <p className="px-4 py-10 text-center text-[11.5px] leading-relaxed text-ink-3">
              No game plan yet — press <span className="fig text-flip">Generate</span>. It reads the scanner&apos;s
              top {top} names, their levels and option chains, the tape and today&apos;s prints, and writes a plan
              for each.
            </p>
          ) : plan.error ? (
            <Failed error={plan.error} raw={plan.raw} noun="plan" />
          ) : plan.plan && plan.facts ? (
            <>
              <NoteAge createdUtc={plan.created_utc} what="plan" />
              <PlanView p={plan} />
              <Provenance p={plan} showDigest={showDigest} onDigest={() => setShowDigest((v) => !v)} />
            </>
          ) : (
            <Failed error="The stored plan has no body." raw={plan.raw} noun="plan" />
          )}
        </Module>
      </div>

      <div className="flex min-h-0 min-w-0 flex-col gap-2 xl:overflow-y-auto">
        <Module
          title="Past plans"
          large
          sub={`${feed?.history?.length ?? 0} kept`}
          className="xl:min-h-0 xl:flex-1"
          bodyClassName="px-0 py-0 xl:min-h-0 xl:overflow-y-auto"
        >
          {!feed ? (
            <ListSkeleton />
          ) : !feed.history?.length ? (
            <p className="px-3 py-5 text-center text-[11px] text-ink-3">
              Nothing yet. Plans are kept so each one can be read against how the session went.
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
                      (viewing ?? plan?.id) === h.id && "bg-ink/[0.06] qt:bg-surface-2",
                    )}
                  >
                    <div className="flex w-full items-baseline gap-2">
                      <span className="fig shrink-0 text-[11px] text-ink-3">{h.et_label}</span>
                      <span className="fig ml-auto shrink-0 text-[10px] text-ink-3">
                        {h.n} {h.n === 1 ? "name" : "names"}
                      </span>
                    </div>
                    {h.headline && <span className="line-clamp-2 text-[11.5px] leading-snug text-ink-2">{h.headline}</span>}
                  </button>
                  {confirming === h.id ? (
                    <div className="absolute inset-0 flex items-center gap-1.5 bg-surface-2 px-3">
                      <span className="mr-auto text-[10px] text-ink-3">Delete this plan?</span>
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
                      <button type="button" onClick={() => setConfirming(null)} className="hit rounded px-1.5 py-0.5 text-[10px] text-ink-3">
                        Keep
                      </button>
                    </div>
                  ) : (
                    <button
                      type="button"
                      onClick={() => setConfirming(h.id)}
                      title="Delete this plan"
                      aria-label={`Delete the plan from ${h.et_label}`}
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

/* ---------------------------------------------------------------- the plan */

function PlanView({ p }: { p: Plan }) {
  const quiet = useQuiet();
  const f = p.facts;
  const b = p.plan!;
  const byName = new Map(f.names.map((n) => [n.sym, n]));
  const planned = new Set(b.plans.map((x) => x.sym));
  const avoided = new Set(b.avoid.map((x) => x.sym));
  const rest = f.names.filter((n) => !planned.has(n.sym) && !avoided.has(n.sym) && n.sym !== "SPY" && n.sym !== "QQQ");

  return (
    <article className={cn("qt-noscale w-full px-5 pt-4 pb-6", quiet && "px-3 pt-2 pb-8")}>
      <header className="flex flex-wrap items-baseline justify-between gap-x-3 gap-y-1 border-b border-ring pb-3">
        <h1 className="text-[21px] leading-tight font-semibold text-ink">
          {dayName(f.trading_day)} <span className="font-normal text-ink-3">New York game plan</span>
        </h1>
        <span className="fig text-[11.5px] text-ink-3">{f.as_of}</span>
      </header>

      {f.partial.length > 0 && (
        <div className="mt-3 border-l-[3px] border-warn bg-warn/[0.07] px-3 py-2 text-[12px] leading-relaxed text-ink-2">
          <strong className="font-semibold text-warn">Partial data.</strong>
          {f.partial.map((x) => (
            <span key={x} className="block">
              {x}
            </span>
          ))}
        </div>
      )}
      {p.unverified && p.unverified.length > 0 && (
        <div className="mt-3 border-l-[3px] border-put-fig bg-put-fig/[0.07] px-3 py-2 text-[12px] leading-relaxed text-ink-2">
          <strong className="font-semibold text-put-fig">Unverified figures.</strong> The model printed{" "}
          {p.unverified.length === 1 ? "a number" : "numbers"} the scanner&apos;s facts do not contain —{" "}
          <span className="fig text-ink">{p.unverified.join(", ")}</span>. Read the sentences carrying{" "}
          {p.unverified.length === 1 ? "it" : "them"} as unchecked; the tables beside each plan are the
          collector&apos;s and are exact.
        </div>
      )}

      <p className="mt-5 max-w-[840px] text-[18px] leading-[1.5] text-ink">{b.headline}</p>
      {b.market && <p className="mt-2 max-w-[840px] text-[13.5px] leading-[1.6] text-ink-2">{b.market}</p>}

      <Regime r={f.regime} />
      <RegimeContext f={f} />

      {f.macro && (f.macro.moves.length > 0 || f.macro.headlines.length > 0) && <MacroToday m={f.macro} />}

      {f.prints && f.prints.length > 0 ? (
        <Section title="Prints that matter">
          <ul className="grid gap-x-10 lg:grid-cols-2">
            {f.prints.map((c) => (
              <PrintItem key={`${c.et}-${c.title}`} c={c} />
            ))}
          </ul>
        </Section>
      ) : f.calendar.length > 0 && (
        <Section title="Prints that matter">
          <ul className="grid gap-x-10 lg:grid-cols-2">
            {f.calendar.map((c) => (
              <li
                key={`${c.et}-${c.title}`}
                className={cn("grid grid-cols-[86px_minmax(0,1fr)] items-baseline gap-3 border-b border-ring/60 py-[6px] text-[12.5px]", c.released && "opacity-70")}
              >
                <span className="fig text-ink-2">{c.et}</span>
                <span className="flex min-w-0 items-baseline gap-2 text-ink">
                  <span className="truncate">{c.title}</span>
                  {c.score >= 4 && (
                    <span className="qt-cap inline-flex shrink-0 items-center gap-1 text-[9.5px] text-warn">
                      <span aria-hidden className="h-[5px] w-[5px] bg-warn" />
                      High impact
                    </span>
                  )}
                  {c.released && <span className="qt-cap shrink-0 text-[9.5px] text-ink-3">Released</span>}
                </span>
              </li>
            ))}
          </ul>
        </Section>
      )}

      <Section title={`The plans · ${b.plans.length}`}>
        {f.conviction && f.conviction.total > 0 && <TapeCount c={f.conviction} />}
        {b.plans.length === 0 ? (
          <p className="text-[12.5px] text-ink-3">No name earned a plan from what the scanner shows.</p>
        ) : (
          <div className="flex flex-col">
            {b.plans.map((x) => (
              <PlanCard key={x.sym} x={x} n={byName.get(x.sym) ?? null} />
            ))}
          </div>
        )}
      </Section>

      {b.avoid.length > 0 && (
        <Section title="Leave alone">
          <ul className="flex flex-col">
            {b.avoid.map((a) => (
              <li key={a.sym} className="grid grid-cols-[72px_minmax(0,1fr)] items-baseline gap-3 border-b border-ring/60 py-[6px] text-[12.5px] last:border-b-0">
                <span className="flex items-center gap-1.5 self-center font-semibold text-ink">
                  <TickerLogo sym={a.sym} size={14} />
                  {a.sym}
                </span>
                <span className="text-ink-2">{a.why}</span>
              </li>
            ))}
          </ul>
        </Section>
      )}

      {rest.length > 0 && (
        <Section title="Also scanned">
          <p className="text-[12px] leading-[1.6] text-ink-3">
            {rest.map((n, i) => (
              <span key={n.sym}>
                {i > 0 && " · "}
                <span className="font-semibold text-ink-2">{n.sym}</span>{" "}
                <span className="fig">{n.score}</span> {stateWord(n.state)}
              </span>
            ))}
          </p>
        </Section>
      )}

      {b.timing.length > 0 && (
        <Section title="The clock">
          <Bullets items={b.timing} />
        </Section>
      )}
      {b.risks.length > 0 && (
        <Section title="Risks">
          <Bullets items={b.risks} />
        </Section>
      )}
    </article>
  );
}

function Regime({ r }: { r: PlanRegime }) {
  return (
    <div className="mt-6 grid grid-cols-2 border-y border-ring md:grid-cols-4 md:divide-x md:divide-ring">
      <Cell label="VIX">
        <span className="fig text-[17px] text-ink">{num(r.vix, 2)}</span>{" "}
        <span className={cn("fig text-[11.5px]", dir(r.vix_pct))}>{pct(r.vix_pct)}</span>
        <p className="mt-1 text-[11.5px] text-ink-3">
          {[r.band, r.shape].filter(Boolean).join(" · ") || "—"}
        </p>
      </Cell>
      <Cell label="Implied SPY day">
        <span className="fig text-[17px] text-ink">{r.spy_em_pct != null ? `±${r.spy_em_pct.toFixed(2)}%` : "—"}</span>
        <p className="mt-1 text-[11.5px] text-ink-3">one-sigma, from VIX</p>
      </Cell>
      <Cell label="Bias">
        <span className="text-[16px] font-semibold" style={{ color: sideHue(r.bias) }}>
          {r.bias === "long" ? "▲ Long" : r.bias === "short" ? "▼ Short" : "Neutral"}
        </span>
        <p className="mt-1 text-[11.5px] text-ink-3">{r.confirm ? r.confirm.replace(/_/g, "-") : "no read from VIX"}</p>
      </Cell>
      <Cell label="Tape">
        <ul className="flex flex-col gap-0.5">
          {r.tape.map((t) => {
            const mv = t.ext_pct ?? t.chg_pct;
            return (
              <li key={t.sym} className="flex items-baseline gap-2 text-[12px]">
                <span className="fig w-[34px] text-ink-2">{t.sym}</span>
                <span style={{ color: t.trend === 1 ? "var(--call-fig)" : t.trend === -1 ? "var(--put-fig)" : "var(--flip-fig)" }}>
                  {t.trend === 1 ? "▲" : t.trend === -1 ? "▼" : "–"}
                </span>
                <span className={cn("fig", dir(mv))}>{pct(mv)}</span>
                {t.ext_pct != null && <span className="qt-cap text-[9px] text-ink-3">ext</span>}
              </li>
            );
          })}
        </ul>
      </Cell>
    </div>
  );
}

function Cell({ label, title, children }: { label: string; title?: string; children: React.ReactNode }) {
  return (
    <div className="min-w-0 px-4 py-3 first:pl-0" title={title}>
      <p className="qt-cap mb-1.5 text-[10.5px] text-ink-3">{label}</p>
      {children}
    </div>
  );
}

/**
 * The tape's context under the weather — breadth, the fuel spent of the
 * implied day, dealer gamma in ETF prices and the next Fed meeting, as the
 * collector stood them when the plan was written. Each cell shows only when
 * the plan carries it; a plan from before 2026-10-14 shows none of them.
 */
function RegimeContext({ f }: { f: PlanFacts }) {
  const b = f.breadth;
  const fuel = (f.fuel ?? []).filter((x) => x.sym === "SPY" || x.sym === "QQQ");
  const gamma = f.gamma ?? [];
  const fed = f.fed;
  const cells: React.ReactNode[] = [];
  if (b && b.sectors_total > 0) {
    const ndx = b.indices.find((i) => i.key === "NDX");
    cells.push(
      <Cell key="breadth" label="Breadth" title="Sector SPDRs up, equal weight against cap weight, and how many Nasdaq-100 names are rising">
        <span className="fig text-[15px] text-ink">
          {b.sectors_up}
          <span className="text-ink-3">/{b.sectors_total}</span>
        </span>{" "}
        <span className="text-[11.5px] text-ink-3">sectors up</span>
        <SplitBar
          className="mt-1.5 max-w-[160px]"
          total={b.sectors_total}
          parts={[
            { n: b.sectors_up, cls: "bg-call-fig" },
            { n: b.sectors_down, cls: "bg-put-fig" },
          ]}
        />
        <p className="mt-1 text-[11.5px] text-ink-3">
          RSP{" "}
          <span className={cn("fig", dir(b.rsp_vs_spy))}>
            {b.rsp_vs_spy == null ? "—" : `${b.rsp_vs_spy >= 0 ? "+" : ""}${b.rsp_vs_spy.toFixed(2)}`}
          </span>{" "}
          vs SPY{ndx?.pct_up != null && <> · NDX {Math.round(ndx.pct_up)}% up</>}
        </p>
      </Cell>,
    );
  }
  if (fuel.length > 0) {
    cells.push(
      <Cell key="fuel" label="Fuel used" title="The index's range as a multiple of the implied day — before the open, the gap's">
        <ul className="flex flex-col gap-0.5">
          {fuel.map((x) => {
            const pre = x.range_pct == null;
            const v = pre ? (x.gap_vs_implied != null ? Math.abs(x.gap_vs_implied) : null) : x.used;
            return (
              <li key={x.sym} className="flex items-baseline gap-2 text-[12px]">
                <span className="fig w-[34px] text-ink-2">{x.sym}</span>
                <span className="fig text-ink">{v != null ? `${v.toFixed(2)}×` : "—"}</span>
                <span className={cn("qt-cap text-[9.5px]", pre ? "text-ink-3" : stateText(x.state))}>
                  {pre ? "gap · pre" : (x.state ?? "")}
                </span>
              </li>
            );
          })}
        </ul>
      </Cell>,
    );
  }
  if (gamma.length > 0) {
    cells.push(
      <Cell
        key="gamma"
        label="Gamma · flip"
        title={gamma.map((g) => g.note).filter(Boolean).join("\n") || "Dealer gamma's regime, the flip in ETF prices, and spot's distance from it"}
      >
        <ul className="flex flex-col gap-0.5">
          {gamma.map((g) => {
            const vs = g.spot != null && g.flip != null ? g.spot - g.flip : null;
            return (
              <li key={g.etf} className="flex items-baseline gap-2 text-[12px]">
                <span className="fig w-[34px] text-ink-2">{g.etf}</span>
                {g.regime && (
                  <span className={cn("qt-cap text-[9.5px]", g.regime === "POS" ? "text-call-fig" : "text-put-fig")}>
                    {g.regime === "POS" ? "pos" : "neg"} <span className="normal-case">γ</span>
                  </span>
                )}
                <span className="fig text-flip-fig">{num(g.flip, 2)}</span>
                {vs != null && <span className={cn("fig text-[11px]", vs >= 0 ? "up" : "down")}>{`${vs >= 0 ? "+" : ""}${vs.toFixed(2)}`}</span>}
              </li>
            );
          })}
        </ul>
      </Cell>,
    );
  }
  if (fed && fed.next) {
    cells.push(
      <Cell key="fed" label="Next FOMC" title={fed.note ?? undefined}>
        <span className="fig text-[15px] text-ink">{shortDay(fed.next)}</span>{" "}
        <span className={cn("fig text-[12.5px]", fed.next_bp == null || fed.next_bp === 0 ? "text-ink-3" : fed.next_bp < 0 ? "up" : "down")}>
          {bp(fed.next_bp)}
        </span>{" "}
        <span className="text-[11.5px] text-ink-3">priced</span>
        <p className="mt-1 text-[11.5px] text-ink-3">
          {fed.next_rate != null ? <>to {fed.next_rate.toFixed(2)}%</> : "rate after unavailable"}
          {fed.change_bp != null && <> · {bp(fed.change_bp)} today</>}
        </p>
      </Cell>,
    );
  }
  if (cells.length === 0) return null;
  return <div className="grid grid-cols-2 border-b border-ring md:grid-cols-4 md:divide-x md:divide-ring">{cells}</div>;
}

/** One of today's prints, read against consensus — amber when it surprised, either way. */
function PrintItem({ c }: { c: Print }) {
  return (
    <li className="grid grid-cols-[86px_minmax(0,1fr)] items-baseline gap-3 border-b border-ring/60 py-[6px] text-[12.5px]">
      <span className="fig text-ink-2">{c.et}</span>
      <span className="min-w-0">
        <span className="flex min-w-0 items-baseline gap-2 text-ink">
          <span className="truncate">{c.title}</span>
          {c.score >= 4 && (
            <span className="qt-cap inline-flex shrink-0 items-center gap-1 text-[9.5px] text-warn">
              <span aria-hidden className="h-[5px] w-[5px] bg-warn" />
              High impact
            </span>
          )}
          <span className={cn("qt-cap ml-auto shrink-0 text-[9.5px]", c.released ? readText(c.read) : "text-ink-3")}>
            {!c.released ? "due" : c.read ?? "released"}
          </span>
        </span>
        <span className="fig mt-0.5 block text-[11px] text-ink-3">
          {c.released && (
            <>
              act <span className={c.read === "hot" || c.read === "cold" ? "text-flip-fig" : "text-ink"}>{c.actual ?? "—"}</span> ·{" "}
            </>
          )}
          cons <span className="text-ink-2">{c.consensus ?? "—"}</span> · prev <span className="text-ink-2">{c.previous ?? "—"}</span>
        </span>
      </span>
    </li>
  );
}

/**
 * The tape's count over the plans — which side, how many of the signals agree,
 * and the cap it sets on every plan below. Each vote is listed with its
 * reason on the hover, so a capped plan can be traced to the votes that capped
 * it.
 */
function TapeCount({ c }: { c: Conviction }) {
  return (
    <div className="mb-4 border-b border-ring/60 pb-3.5" title={votesTip(c)}>
      <div className="flex flex-wrap items-baseline gap-x-3 gap-y-1">
        <span className="qt-cap text-[10.5px] text-ink-3">Tape</span>
        <span className={cn("text-[14px] font-semibold", sideText(c.bias))}>{biasWord(c.bias)}</span>
        <span className="fig text-[12.5px] text-ink-2">
          {c.agree} of {c.total} agree
        </span>
        <span className={cn("qt-cap text-[10.5px]", gradeText(c))}>{c.grade}</span>
        <ConvictionBar c={c} className="w-[160px] self-center" />
        <span className="ml-auto text-[12px] text-ink-3">
          every plan capped at <span className="fig text-ink-2">{c.max_conviction}</span>
          {c.bias && <>, one against the tape at <span className="fig text-ink-2">3</span></>}
        </span>
      </div>
      <ul className="mt-2 flex flex-wrap gap-x-4 gap-y-1">
        {c.votes.map((v) => (
          <li key={v.key} className="flex items-baseline gap-1.5 text-[11.5px]" title={`${v.value} — ${v.note}`}>
            <span className={cn("text-[10px]", sideText(v.vote))}>{voteGlyph(v.vote)}</span>
            <span className={v.vote === "neutral" ? "text-ink-3" : "text-ink-2"}>{v.label}</span>
          </li>
        ))}
      </ul>
    </div>
  );
}

/** One name's plan: the model's words on the left, the collector's facts on the right. */
function PlanCard({ x, n }: { x: PlanItem; n: PlanName | null }) {
  const hue = sideHue(x.side);
  return (
    <section className="grid gap-x-10 gap-y-4 border-b border-ring/60 py-5 first:pt-1 last:border-b-0 lg:grid-cols-[minmax(0,1.45fr)_minmax(300px,1fr)]" aria-label={`${x.sym} plan`}>
      <div className="min-w-0">
        <div className="flex flex-wrap items-baseline gap-x-3 gap-y-1">
          <span className="text-[13px]" style={{ color: hue }}>
            {x.side === "long" ? "▲" : "▼"}
          </span>
          <TickerLogo sym={x.sym} size={20} className="self-center" />
          <span className="text-[19px] leading-none font-semibold text-ink">{x.sym}</span>
          {n?.name && <span className="min-w-0 truncate text-[12px] text-ink-3">{n.name}</span>}
          <span className="qt-cap text-[10.5px]" style={{ color: hue }}>
            {x.side === "long" ? "Long" : "Short"}
          </span>
          <span
            className="ml-auto flex items-center gap-2 text-[11.5px] text-ink-3"
            title={
              x.capped
                ? `Conviction 1–5 after the collector's cap: ${x.capped}${x.conviction_model != null ? `. The model said ${x.conviction_model}.` : "."}`
                : "The model's own conviction, 1–5 — not a probability"
            }
          >
            {x.conviction >= 4 ? "high" : x.conviction === 3 ? "moderate" : "low"} conviction
            <Pips n={x.conviction} hue={hue} />
          </span>
        </div>
        {x.capped && (
          <p className="mt-1.5 flex items-baseline justify-end gap-1.5 text-[11.5px] text-ink-3">
            <span aria-hidden className="h-[5px] w-[5px] shrink-0 -translate-y-px bg-warn" />
            {cappedText(x)}
          </p>
        )}
        <p className="mt-3 text-[14px] leading-[1.5] font-semibold text-ink">{x.plan}</p>
        <dl className="mt-3 grid gap-x-6 gap-y-3 text-[13px] leading-[1.5] sm:grid-cols-2">
          <Term k="Trigger" v={x.trigger} />
          <Term k="Invalidation" v={x.invalidation} strong />
          <Term k="Target" v={x.target} />
          <Term k="Options" v={x.options} />
        </dl>
        {x.why.length > 0 && (
          <ul className="mt-3.5 flex flex-col gap-1.5">
            {x.why.map((w) => (
              <li key={w} className="flex gap-2 text-[12.5px] leading-[1.5] text-ink-2">
                <span aria-hidden className="mt-[7px] h-[5px] w-[5px] shrink-0 rounded-[1px]" style={{ background: hue }} />
                <span>
                  <Layered text={w} />
                </span>
              </li>
            ))}
          </ul>
        )}
      </div>
      {n ? <Facts n={n} /> : <p className="text-[12px] text-ink-3">No scanner facts for {x.sym}.</p>}
    </section>
  );
}

/**
 * A capped conviction, said plainly: "capped at 3 — tape weak; model said 4".
 * The collector's reason ends "— at most N", which the cap figure already says.
 */
function cappedText(x: PlanItem): string {
  const why = (x.capped ?? "").replace(/\s*[—–-]\s*at most \d\s*$/i, "").trim();
  const model = x.conviction_model != null && x.conviction_model !== x.conviction ? `; model said ${x.conviction_model}` : "";
  return `capped at ${x.conviction}${why ? ` — ${why}` : ""}${model}`;
}

function Term({ k, v, strong }: { k: string; v: string; strong?: boolean }) {
  if (!v) return null;
  return (
    <div>
      <dt className="qt-cap text-[10.5px] text-ink-3">{k}</dt>
      <dd className={cn("mt-1", strong ? "font-semibold text-ink" : "text-ink-2")}>{v}</dd>
    </div>
  );
}

/** The collector's facts for a name, in the scanner's own vocabulary. */
function Facts({ n }: { n: PlanName }) {
  const L = n.levels;
  const o = n.options;
  const rows: Array<[string, React.ReactNode, string?]> = [
    [
      "Last",
      <>
        <span className="text-ink">{num(n.last)}</span> <span className={dir(n.chg_pct)}>{pct(n.chg_pct)}</span>
        {n.ext_pct != null && (
          <>
            {" "}
            · <span className={dir(n.ext_pct)}>{pct(n.ext_pct)}</span> <span className="qt-cap text-[9px] text-ink-3">ext</span>
          </>
        )}
      </>,
    ],
    [
      "Setup",
      <>
        <span className="text-ink">{stateWord(n.state)}</span>
        {n.level ? ` · ${n.level}` : ""} <span className="text-ink-3">· score {n.score}</span>
      </>,
    ],
    [
      "Entry",
      n.entry ? (
        <>
          <span className="text-ink-3">{n.entry.kind === "EMA8" ? "8 EMA" : n.entry.kind}</span> <span className="text-ink">{num(n.entry.price)}</span>{" "}
          <span className="text-ink-3">
            {n.entry.dist_atr >= 0 ? "+" : ""}
            {n.entry.dist_atr.toFixed(1)} ATR
          </span>
        </>
      ) : (
        "—"
      ),
    ],
    [
      "PDH · PDL",
      <>
        <span style={{ color: "var(--call-fig)" }}>{num(L.pdh)}</span> · <span style={{ color: "var(--put-fig)" }}>{num(L.pdl)}</span>
      </>,
    ],
    [
      "PMH · PML",
      <>
        <span style={{ color: "var(--call-fig)" }}>{num(L.pmh)}</span> · <span style={{ color: "var(--put-fig)" }}>{num(L.pml)}</span>
      </>,
    ],
    [
      "RS SPY · RVol",
      <>
        <span className={dir(n.rs_spy)}>{n.rs_spy == null ? "—" : `${n.rs_spy >= 0 ? "+" : ""}${n.rs_spy.toFixed(2)}`}</span> ·{" "}
        <span className="text-ink">{n.rvol != null ? `${n.rvol.toFixed(1)}×` : "—"}</span>
      </>,
      "Relative strength in ATRs against SPY's; relative volume against the same time of day",
    ],
    ["ATR day · 10m", <>{num(n.atr_d, 2)} · {num(n.atr_b, 2)}</>],
  ];
  if (n.premkt && (n.premkt.volume != null || n.premkt.pct_adv != null)) {
    const p = n.premkt.pct_adv;
    rows.push([
      "Pre-market",
      <>
        <span className="text-ink">{compact(n.premkt.volume)}</span> shares
        {p != null && (
          <>
            {" "}· <span className={p >= 5 ? "text-ink" : "text-ink-2"}>{p < 1 ? p.toFixed(1) : Math.round(p)}%</span>{" "}
            <span className="text-ink-3">of an average day</span>
          </>
        )}
      </>,
      `Volume traded before the open, against the twenty-session average day${n.adv20 != null ? ` (${compact(n.adv20)})` : ""} — heavy pre-market volume is real interest, thin is a quote that can be pushed around`,
    ]);
  }
  if (n.sector) {
    rows.push([
      "Sector",
      <>
        <span className="text-ink">{n.sector.key}</span>
        {n.sector.label && <span className="text-ink-3"> {n.sector.label}</span>}{" "}
        <span className={dir(n.sector.rs_day)}>
          {n.sector.rs_day == null ? "—" : `${n.sector.rs_day >= 0 ? "+" : ""}${n.sector.rs_day.toFixed(2)}`}
        </span>{" "}
        <span className="text-ink-3">vs SPY</span>
      </>,
      "The sector SPDR's move today minus SPY's, in percentage points",
    ]);
  }
  if (n.peers && n.peers.length > 0) {
    rows.push([
      "Peers report",
      <span key="peers" className="flex flex-wrap gap-x-2.5">
        {n.peers.map((r) => (
          <span key={`${r.sym}-${r.date}`}>
            <span className="text-ink">{r.sym}</span>{" "}
            <span className={r.days === 0 ? "text-warn" : "text-ink-3"}>
              {peerDay(r)}
              {r.when === "pre" ? " BMO" : r.when === "after" ? " AMC" : ""}
            </span>
          </span>
        ))}
      </span>,
      "Big caps in the same sector reporting in the next three sessions — a peer's report moves this name before its own",
    ]);
  }
  if (n.macro && n.macro.length > 0) {
    rows.push([
      "Macro",
      <span key="macro" className="flex flex-col gap-0.5">
        {n.macro.map((d) => (
          <Driver key={d.driver} d={d} />
        ))}
      </span>,
      "The macro moves this name answers to, and whether today's move helps or hurts the stock",
    ]);
  }
  if (o) {
    rows.push(
      [
        "IV30 · IV/RV",
        <>
          <span className="text-ink">{o.iv30 != null ? `${o.iv30.toFixed(1)}%` : "—"}</span> ·{" "}
          <span className={o.premium === "rich" ? "text-flip-fig" : o.premium === "cheap" ? "text-call-fig" : "text-ink"}>
            {o.iv_rv != null ? o.iv_rv.toFixed(2) : "—"}
            {o.premium ? ` ${o.premium}` : ""}
          </span>
          {o.iv_rank != null && <span className="text-ink-3"> · rank {Math.round(o.iv_rank)}</span>}
        </>,
        "Implied volatility over realised: rich premium favours spreads, cheap favours buying the option outright",
      ],
      [
        "Expected move",
        <>
          {o.em_front_pct != null ? `±${o.em_front_pct.toFixed(2)}%` : "—"} <span className="text-ink-3">front</span> ·{" "}
          {o.em_weekly_pct != null ? `±${o.em_weekly_pct.toFixed(2)}%` : "—"} <span className="text-ink-3">weekly</span>
        </>,
        "The options market's priced move, from the at-the-money straddle",
      ],
      [
        "Liquidity",
        <span key="liq" className={o.liquidity === "poor" ? "text-warn" : "text-ink"}>{o.liquidity ?? "—"}</span>,
        "The at-the-money spread as a share of its price",
      ],
    );
    if (o.long) {
      rows.push([
        "Long",
        <>
          <span className="text-ink">
            {o.long.expiry.slice(5)} {strike(o.long.strike)}
            {o.long.right}
          </span>{" "}
          @ {num(o.long.mid)} <span className="text-ink-3">· {o.long.delta.toFixed(2)}Δ</span>
        </>,
      ]);
    }
    if (o.spread) {
      rows.push([
        "Spread",
        <>
          <span className="text-ink">
            {o.spread.expiry.slice(5)} {strike(o.spread.strike)}/{strike(o.spread.short_strike)}
          </span>{" "}
          @ {num(o.spread.mid)}
        </>,
      ]);
    }
  }
  if (n.flow) {
    rows.push([
      "Flow",
      <FlowFacts key="flow" f={n.flow} />,
      "Today's option volume: puts over calls, which way it leans (under 0.7 calls, over 1.3 puts), and the busiest strike",
    ]);
  }
  return (
    <div className="min-w-0">
      <table className="w-full border-collapse text-[12px]">
        <tbody>
          {rows.map(([k, v, tip]) => (
            <tr key={k} className="border-b border-ring/60 last:border-b-0" title={tip}>
              <td className="qt-cap w-[112px] py-[5px] pr-3 align-baseline text-[10px] text-ink-3">{k}</td>
              <td className="fig py-[5px] align-baseline text-ink-2">{v}</td>
            </tr>
          ))}
        </tbody>
      </table>
      {(n.earnings || o?.earnings_in) && (
        <p className="mt-2 flex items-baseline gap-2 text-[12px] text-ink-2">
          <span aria-hidden className="h-[6px] w-[6px] shrink-0 bg-warn" />
          {n.earnings && (
            <span>
              Earnings {n.earnings.days === 0 ? "today" : n.earnings.days === 1 ? "tomorrow" : `in ${n.earnings.days}d`}
              {n.earnings.when === "pre" ? " before the open" : n.earnings.when === "after" ? " after the close" : ""}
            </span>
          )}
          {o?.earnings_in && <span className="text-warn">· the {o.earnings_in.slice(5)} expiry spans it — IV crush</span>}
        </p>
      )}
      {n.headlines.length > 0 && (
        <div className="mt-3">
          <p className="qt-cap mb-1 text-[10px] text-ink-3">News · last three days</p>
          <ul className="flex flex-col gap-1">
            {n.headlines.map((h) => (
              <li key={h.id} className="text-[11.5px] leading-snug text-ink-2">
                {h.kind && h.kind !== "news" && (
                  <span className={cn("qt-cap mr-1.5 text-[9px]", h.kind === "rating" ? "text-flip-fig" : "text-ink-3")}>{h.kind}</span>
                )}
                {h.url ? (
                  <a href={h.url} target="_blank" rel="noreferrer noopener" className="hover:text-ink hover:underline">
                    {h.title}
                  </a>
                ) : (
                  h.title
                )}{" "}
                <span className="qt-cap text-[9px] text-ink-3">{h.publisher}</span>
                {h.age_min != null && <span className="fig ml-1 text-[10px] text-ink-3">{ageText(h.age_min)}</span>}
              </li>
            ))}
          </ul>
        </div>
      )}
      {n.headlines.length === 0 && n.news_loaded === false && (
        <p className="mt-3 text-[11.5px] text-ink-3">News · headlines were still loading when this plan was written.</p>
      )}
      {n.filings && n.filings.length > 0 && (
        <div className="mt-2.5">
          <p className="qt-cap mb-1 text-[10px] text-ink-3">SEC filings</p>
          <ul className="flex flex-col gap-0.5">
            {n.filings.map((fl) => (
              <li key={`${fl.form}-${fl.filed}`} className="text-[11.5px] text-ink-2">
                <span className="fig font-semibold text-ink">{fl.form}</span> <span className="text-ink-3">{fl.desc}</span>
              </li>
            ))}
          </ul>
        </div>
      )}
    </div>
  );
}

/** A name's option flow in one line: "0.62 calls · 140C 10-17 12.4K". */
function FlowFacts({ f }: { f: PlanFlow }) {
  const top: PlanFlowStrike | null = Array.isArray(f.top) ? (f.top[0] ?? null) : (f.top ?? null);
  return (
    <>
      <span className="text-ink-3">P/C</span> <span className="text-ink">{f.pc_vol != null ? f.pc_vol.toFixed(2) : "—"}</span>
      {f.lean && <span className={cn("qt-cap ml-1.5 text-[9.5px]", leanText(f.lean))}>{f.lean}</span>}
      {top && (
        <>
          {" "}·{" "}
          <span className={top.right === "C" ? "text-call-fig" : "text-put-fig"}>
            {strike(top.strike)}
            {top.right}
          </span>{" "}
          <span className="text-ink-2">{top.expiry.slice(5)}</span> <span className="text-ink-3">{compact(top.volume)}</span>
        </>
      )}
    </>
  );
}

/** A peer's report day: "today", "tmrw", or the weekday. */
function peerDay(r: { date: string; days: number }): string {
  if (r.days === 0) return "today";
  if (r.days === 1) return "tmrw";
  const d = new Date(`${r.date}T12:00:00Z`);
  return Number.isNaN(d.getTime()) ? r.date : d.toLocaleDateString("en-GB", { weekday: "short", timeZone: "UTC" });
}

/** One macro driver: its move, and what that move does to the stock today. */
function Driver({ d }: { d: PlanDriver }) {
  const hue = d.effect === "tailwind" ? "text-call-fig" : d.effect === "headwind" ? "text-put-fig" : "text-ink-3";
  return (
    <span title={d.why}>
      <span className="text-ink-2">{d.label}</span> <span className="text-ink">{d.move}</span>{" "}
      <span className={cn("qt-cap text-[9.5px]", hue)}>{d.effect}</span>
    </span>
  );
}

/**
 * The day's macro, once for the whole plan: the moves each name's drivers are
 * read from, and the market's high-impact headlines — so a plan's "Macro:"
 * line can be checked against the tape it cites.
 */
function MacroToday({ m }: { m: PlanMacro }) {
  return (
    <section className="mt-7 border-t border-ring pt-5" aria-label="Macro today">
      <h3 className="qt-cap mb-3 text-[11.5px] text-ink-3">Macro today</h3>
      {m.moves.length > 0 && (
        <div className="flex flex-wrap gap-x-7 gap-y-2">
          {m.moves.map((x) => (
            <div key={x.key} className="flex items-baseline gap-2">
              <span className="qt-cap text-[10.5px] text-ink-3">{x.label}</span>
              <span className={cn("fig text-[13px]", x.move > 0 ? "up" : x.move < 0 ? "down" : "text-ink-2")}>{x.text}</span>
            </div>
          ))}
        </div>
      )}
      {m.headlines.length > 0 && (
        <ul className="mt-3 flex flex-col">
          {m.headlines.map((h) => (
            <li key={h.id} className="flex items-baseline gap-2.5 border-b border-ring/60 py-[6px] text-[12.5px] last:border-b-0">
              <span aria-hidden className="h-[5px] w-[5px] shrink-0 translate-y-[-2px] bg-err" />
              <span className="min-w-0 flex-1 text-ink">{h.title}</span>
              <span className="qt-cap shrink-0 text-[9.5px] text-ink-3">
                {h.publisher}
                {h.desk ? ` · ${h.desk}` : ""}
              </span>
              {h.age_min != null && <span className="fig shrink-0 text-[10.5px] text-ink-3">{ageText(h.age_min)}</span>}
            </li>
          ))}
        </ul>
      )}
    </section>
  );
}

/** Minutes as the wire prints an age: "14m", "3h", "2d". */
function ageText(m: number): string {
  if (m < 60) return `${Math.max(0, Math.round(m))}m`;
  if (m < 1440) return `${Math.round(m / 60)}h`;
  return `${Math.round(m / 1440)}d`;
}

/** A "Structure: …" line with its layer set in caps — the futures brief's grammar. */
function Layered({ text: raw }: { text: string }) {
  // A plan stored before the server collapsed it can still say "News: News: …".
  const text = raw.replace(/^\s*([A-Za-z][A-Za-z ]{0,20}):\s*\1:\s*/i, "$1: ");
  const m = text.match(
    /^(Structure|RS|Relative strength|Options|Tape|Macro|News|Catalyst|Sector|Rates|Rating|Filing|Volume|Levels|Flow|Earnings|Breadth|Fuel|Gamma|Peers|Pre-market|Premarket|Fed|Prints):\s*(.*)$/i,
  );
  return m ? (
    <>
      <span className="qt-cap mr-1.5 text-[10.5px] text-ink-3">{m[1]}</span>
      {m[2]}
    </>
  ) : (
    <>{text}</>
  );
}

function Pips({ n, hue }: { n: number; hue: string }) {
  return (
    <span className="inline-flex gap-[3px]" aria-label={`conviction ${n} of 5`}>
      {[1, 2, 3, 4, 5].map((i) => (
        <span key={i} className="h-[7px] w-[7px] rounded-[1px]" style={{ background: i <= n ? hue : "var(--qt-track, var(--surface-3))" }} />
      ))}
    </span>
  );
}

function Bullets({ items }: { items: string[] }) {
  return (
    <ul className="flex flex-col gap-1">
      {items.map((x) => (
        <li key={x} className="flex gap-2 text-[13px] leading-[1.5] text-ink-2">
          <span aria-hidden className="mt-[7px] h-[5px] w-[5px] shrink-0 rounded-[1px] bg-ink-4" />
          {x}
        </li>
      ))}
    </ul>
  );
}

function Section({ title, children }: { title: string; children: React.ReactNode }) {
  return (
    <section className="mt-7 border-t border-ring pt-5" aria-label={title}>
      <h3 className="qt-cap mb-3.5 text-[11.5px] text-ink-3">{title}</h3>
      {children}
    </section>
  );
}

function Provenance({ p, showDigest, onDigest }: { p: Plan; showDigest: boolean; onDigest: () => void }) {
  return (
    <>
      <div className="mx-3 flex flex-wrap items-center gap-x-3 gap-y-1 border-t border-ring pt-3 pb-3 text-[11px] text-ink-3">
        <span className="fig">{p.model}</span>
        <span aria-hidden>·</span>
        <span className="fig">{p.et_label}</span>
        <span aria-hidden>·</span>
        <span className="fig">{p.facts.names.length} names</span>
        {p.usage?.total_tokens && (
          <>
            <span aria-hidden>·</span>
            <span className="fig">{p.usage.total_tokens.toLocaleString("en-US")} tok</span>
          </>
        )}
        <button
          type="button"
          onClick={onDigest}
          className="hit ml-auto rounded-[3px] border border-ring-2 px-2 py-[3px] text-[11.5px] text-ink-3 hover:text-ink"
        >
          {showDigest ? "Hide" : "Show"} the data it saw
        </button>
      </div>
      {showDigest && (
        <pre className="fig mx-3 mb-3 max-h-[420px] overflow-auto rounded-[4px] border border-ring bg-surface-2/60 px-3 py-2 text-[10.5px] leading-relaxed text-ink-3">
          {JSON.stringify(p.digest, null, 1)}
        </pre>
      )}
    </>
  );
}

/* ---------------------------------------------------------------- skeletons */

/** While the last plan is fetched: the helm, in the space the plan takes. */
function PlanSkeleton() {
  return <HelmLoader label="Loading the game plan" size={48} minHeight={320} />;
}

function ListSkeleton() {
  return <HelmLoader label="Loading past plans" size={28} minHeight={160} />;
}

/** A strike as the chain prints it: 340, 347.5 — not 340.00. */
function strike(x: number): string {
  return Number.isInteger(x) ? String(x) : String(Number(x.toFixed(2)));
}

/** "2026-10-28" → "28 Oct". */
function shortDay(iso: string): string {
  const d = new Date(`${iso}T12:00:00Z`);
  return Number.isNaN(d.getTime()) ? iso : d.toLocaleDateString("en-GB", { day: "numeric", month: "short", timeZone: "UTC" });
}

/** "2026-10-13" → "Tue 13 Oct". */
function dayName(iso: string): string {
  const d = new Date(`${iso}T12:00:00Z`);
  return Number.isNaN(d.getTime())
    ? iso
    : d.toLocaleDateString("en-GB", { weekday: "short", day: "numeric", month: "short", timeZone: "UTC" });
}
