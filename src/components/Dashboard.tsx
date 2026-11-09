"use client";

import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { setAskFocus } from "@/lib/ask/open";
import type { CalendarRow } from "@/types/terminal";
import type { DashRow, DashStory, DashboardPayload } from "@/types/dashboard";
import { BreadthBars } from "@/components/panels/Breadth";
import { setupLabel } from "@/components/panels/ScanDetail";
import { CARD, CatalystCell, Chips, Spark, TD, TH, ageWord, dayName, pctText, rowProps, useWalk } from "@/components/panels/ScanWide";
import { HelmLoader } from "@/components/ui/HelmLoader";
import { TickerLogo } from "@/components/ui/TickerLogo";
import { scoreText } from "@/lib/bias";
import { cn } from "@/lib/cn";
import { dir, inMin, num, pct } from "@/lib/format";
import { heatMax, heatStyle } from "@/lib/heat";
import { etDay, useNextPrint } from "@/lib/nextPrint";
import type { Tab } from "@/lib/tabs";
import { openTicker, useTicker } from "@/lib/ticker";
import { useNow } from "@/lib/useNow";
import { oneOf, persist, usePersisted } from "@/lib/usePersisted";

/**
 * The Dashboard: the session on one page.
 *
 * WHY (owner, 2026-11-09: "can we also have a dashboard section like the shown in some
 * of the screen shots", then "can we follow the layout a bit closer"). Three rows, as
 * in those screenshots: the read beside the game plan; the top setups, the list and
 * the news; the eleven sectors. Macro stays as it was.
 *
 * NOTHING HERE IS NEW INFORMATION, and every part opens where it came from. The read is
 * a fixed rule over the tape count, the VIX band and breadth (server dashboard.py), and
 * the top setups are the scanner's own rank, because this terminal has nobody picking
 * names by hand.
 */

const POLL_SEC = 30;
const LIVE_POLL_SEC = 10;

const WHEN_WORD = { pre: "before the open", after: "after the close", unspecified: "time not set" } as const;

type TopChip = "all" | "long" | "short" | "news";
type ListChip = "pinned" | "adds";

const TOP_CHIPS: ReadonlyArray<{ key: TopChip; label: string }> = [
  { key: "all", label: "All" },
  { key: "long", label: "Long" },
  { key: "short", label: "Short" },
  { key: "news", label: "Has news" },
];
const TOP_TEST: Record<TopChip, (r: DashRow) => boolean> = {
  all: () => true,
  long: (r) => r.score.side === "long",
  short: (r) => r.score.side === "short",
  news: (r) => r.catalyst != null,
};

export function Dashboard({ calendar, onOpen }: { calendar: CalendarRow[]; onOpen: (t: Tab) => void }) {
  const now = useNow(30_000);
  const later = useNextPrint(calendar, now);
  const [data, setData] = useState<DashboardPayload | null>(null);
  const seq = useRef(0);

  const load = useCallback(async () => {
    const mine = ++seq.current;
    try {
      const r = await fetch("/api/dashboard", { cache: "no-store" });
      const d = (await r.json()) as DashboardPayload;
      if (mine === seq.current) setData(d);
    } catch {
      /* the last read stays on screen */
    }
  }, []);

  const live = data?.session === "rth";
  useEffect(() => {
    void load();
    const id = setInterval(load, (live ? LIVE_POLL_SEC : POLL_SEC) * 1000);
    return () => clearInterval(id);
  }, [load, live]);

  // The Scanner reads its view, and the Sectors view its card, from storage as it mounts.
  const toScanner = useCallback(
    (view: string, also: Record<string, unknown> = {}) => {
      persist("scan.view", view);
      for (const [k, v] of Object.entries(also)) persist(k, v);
      onOpen("scanner");
    },
    [onOpen],
  );

  const syms = useMemo(() => [...new Set([...(data?.top ?? []), ...(data?.list ?? [])].map((r) => r.sym))], [data]);
  useWalk(syms);

  // Hermes reads the name open in the slide-out: "explain this setup" means it.
  const ticker = useTicker();
  useEffect(() => {
    setAskFocus(ticker);
    return () => setAskFocus(null);
  }, [ticker]);

  if (!data) return <HelmLoader label="Reading the session" size={48} minHeight={420} />;
  if (!data.ok || data.offline) {
    return (
      <p className="px-6 py-10 text-center text-[12px] text-ink-3">
        {data.offline ? `${data.offline.reason}.` : "The scanner has not built yet: the first pass takes about a minute and a half after a start."}
      </p>
    );
  }

  return (
    <main className="flex min-h-0 flex-1 flex-col gap-3 overflow-y-auto p-3">
      <div className="grid shrink-0 gap-3 xl:grid-cols-[minmax(0,1fr)_minmax(0,2.15fr)]">
        <ReadCard d={data} later={later} now={now} />
        <PlanCard d={data} onWire={() => onOpen("terminal")} toScanner={toScanner} />
      </div>
      <div className="grid gap-3 xl:min-h-[320px] xl:flex-1 xl:grid-cols-[minmax(0,5fr)_minmax(0,3.7fr)_minmax(0,3.6fr)] xl:grid-rows-[minmax(0,1fr)]">
        <TopSetups rows={data.top} onAll={() => toScanner("setups", { "scan.side": "all" })} />
        <MyList list={data.list} adds={data.adds} onAll={() => toScanner("setups", { "scan.side": "pinned" })} />
        <StockNews stories={data.stories} live={data.news_live} />
      </div>
      <Rotation d={data} onHeat={() => toScanner("sectors")} onSector={(k) => toScanner("sectors", { "sec.mode": "cards", "sec.sel": k })} />
    </main>
  );
}

/* -------------------------------------------------------------------------- */
/* The pieces                                                                  */
/* -------------------------------------------------------------------------- */

function Head({ title, sub, right }: { title: React.ReactNode; sub?: string; right?: React.ReactNode }) {
  return (
    <div className="flex shrink-0 items-start justify-between gap-3">
      <div className="min-w-0">
        <h2 className="text-[13.5px] font-semibold text-ink">{title}</h2>
        {sub && <p className="mt-0.5 text-[11.5px] text-ink-3">{sub}</p>}
      </div>
      {right}
    </div>
  );
}

function Go({ onClick, children }: { onClick: () => void; children: React.ReactNode }) {
  return (
    <button type="button" onClick={onClick} className="hit shrink-0 text-[11.5px] whitespace-nowrap text-ink-2 hover:text-ink">
      {children} →
    </button>
  );
}

function Field({ label, children }: { label: string; children: React.ReactNode }) {
  return (
    <div>
      <p className="qt-cap mb-1 text-[10px] text-ink-3">{label}</p>
      {children}
    </div>
  );
}

function ReadCard({ d, later, now }: { d: DashboardPayload; later: CalendarRow | null; now: number | null }) {
  const by = (w: "pre" | "after" | "unspecified") => d.read.reports.filter((r) => r.when === w).map((r) => r.sym);
  const reports = (["pre", "after", "unspecified"] as const)
    .filter((w) => by(w).length)
    .map((w) => `${by(w).join(", ")} ${WHEN_WORD[w]}`)
    .join(" · ");
  const ev = d.plan.event;
  const next = ev
    ? `${ev.title} · ${ev.et} ET · ${ev.in_min < 0 ? "just printed" : `in ${inMin(ev.in_min)}`}`
    : later && later.ts !== null && now !== null
      ? `${etDay(later.ts, now)}${later.event}${later.et ? ` · ${later.et} ET` : ""} · in ${inMin((later.ts - now / 1000) / 60)}`
      : "None scheduled";
  return (
    <section className={cn(CARD, "flex flex-col gap-2.5")}>
      <Head title={d.read.title} sub={`Levels for ${dayName(d.trading_day)}`} />
      <div className="space-y-1.5 text-[13px] leading-[1.45] text-ink-2">
        {d.read.lines.map((l) => (
          <p key={l}>{l}</p>
        ))}
      </div>
      <p className="fig text-[11px] text-ink-3">{d.read.foot}</p>
      <dl className="mt-auto space-y-1 border-t border-ring/60 pt-2 text-[12px]">
        <div className="flex gap-3">
          <dt className="qt-cap w-[54px] shrink-0 pt-px text-[10px] text-ink-3">Reports</dt>
          <dd className="min-w-0 text-ink-2">{reports || "None on the calendar"}</dd>
        </div>
        <div className="flex gap-3">
          <dt className="qt-cap w-[54px] shrink-0 pt-px text-[10px] text-ink-3">Next</dt>
          <dd className="min-w-0 text-ink-2">{next}</dd>
        </div>
      </dl>
    </section>
  );
}

function PlanCard({ d, onWire, toScanner }: { d: DashboardPayload; onWire: () => void; toScanner: (view: string, also?: Record<string, unknown>) => void }) {
  const b = d.plan.bias;
  const hue = b.side === "long" ? "text-call-fig" : b.side === "short" ? "text-put-fig" : "text-ink-3";
  const tip = b.live != null && b.total != null ? `${b.live} of ${b.total} reads live${b.cap != null ? ` · plans capped at ${b.cap}` : ""}` : undefined;
  return (
    <section className={cn(CARD, "flex flex-col gap-3")}>
      <Head title="Today's game plan" sub="Playbook for the session" right={<Go onClick={onWire}>Open the wire</Go>} />
      <div className="grid flex-1 gap-x-10 gap-y-4 lg:grid-cols-[minmax(0,1fr)_minmax(0,1.3fr)]">
        <div className="space-y-2.5">
          <Field label="Market bias">
            <span title={tip} className={cn("inline-flex items-baseline gap-1.5 rounded-[3px] border border-ring-2 px-2 py-0.5 text-[13px] font-semibold", hue)}>
              {b.side === "long" ? "▲ Long" : b.side === "short" ? "▼ Short" : "– No lean"}
              {b.score != null && <span className="fig">{scoreText(b.score)}</span>}
              {b.grade && b.grade !== "none" && <span className="qt-cap text-[10px] font-normal text-ink-3">{b.grade}</span>}
            </span>
          </Field>
          <Field label="Focus sectors">
            <FocusLine rows={d.plan.focus} none="No sector ahead of SPY" />
          </Field>
          <Field label="Focus themes">
            <FocusLine rows={d.plan.themes} none="No theme ahead of SPY" />
          </Field>
          <Field label="Best setups today">
            <ul className="space-y-0.5">
              {d.plan.setups.map((s) => (
                <li key={s.key}>
                  <button
                    type="button"
                    // Breakouts' own default filters, the ones this count was made with.
                    onClick={() => toScanner(s.view, s.chip ? { "brk.chip": s.chip, "brk.cap": 2e9, "brk.vol": 5e5, "brk.rvol": 2, "brk.sector": "", "brk.theme": "" } : {})}
                    className="hit flex items-baseline gap-2 text-left text-[12.5px] text-ink-2 hover:text-ink"
                  >
                    <span aria-hidden className="text-ink-3">✓</span>
                    {s.word}
                    <span className="fig text-ink">{s.n ?? "—"}</span>
                  </button>
                </li>
              ))}
            </ul>
          </Field>
        </div>
        <div className="flex min-w-0 flex-col">
          <p className="mb-2 flex items-baseline justify-between text-[12px] text-ink-2">
            <span>Breadth · advancers vs decliners</span>
            <span className="fig text-[11px] text-ink-3">{d.breadth ? `${d.breadth.names.toLocaleString()} stocks at $2bn+` : ""}</span>
          </p>
          {d.breadth ? <BreadthBars data={d.breadth} /> : <p className="py-6 text-center text-[11.5px] text-ink-3">The wide read has not landed yet.</p>}
        </div>
      </div>
    </section>
  );
}

function FocusLine({ rows, none }: { rows: DashboardPayload["plan"]["focus"]; none: string }) {
  if (!rows.length) return <p className="text-[12.5px] text-ink-3">{none}</p>;
  return (
    <p className="flex flex-wrap gap-x-4 gap-y-0.5 text-[12.5px] text-ink-2">
      {rows.map((f) => (
        <span key={f.key} className="whitespace-nowrap" title={`${f.key}: ${pct(f.rs)} against SPY`}>
          {f.label} <span className={cn("fig", dir(f.pct))}>{pct(f.pct)}</span>
        </span>
      ))}
    </p>
  );
}

type Place = "above" | "below" | "inside" | null;

function pdPlace(r: DashRow): Place {
  const { pdh, pdl } = r.levels;
  if (r.last == null || pdh == null || pdl == null) return null;
  return r.last > pdh ? "above" : r.last < pdl ? "below" : "inside";
}

function pmPlace(r: DashRow): Place {
  const { pmh, pml } = r.levels;
  if (r.last == null || pmh == null || pml == null) return null;
  return r.last > pmh ? "above" : r.last < pml ? "below" : "inside";
}

const PLACE_WORD: Record<NonNullable<Place>, string> = { above: "above its high", below: "below its low", inside: "inside" };

function Dot({ at, range }: { at: Place; range: string }) {
  const say = at ? `${range}: ${PLACE_WORD[at]}` : `${range}: no range yet`;
  return <span title={say} aria-label={say} className={cn("inline-block h-[7px] w-[7px] rounded-full", at === "above" ? "bg-call-fig" : at === "below" ? "bg-put-fig" : at === "inside" ? "bg-ink-4" : "border border-ring-2")} />;
}

function Name({ r }: { r: DashRow }) {
  return (
    <div className="flex items-center gap-1.5 whitespace-nowrap">
      <TickerLogo sym={r.sym} size={16} />
      <div className="leading-[1.25]">
        <p className="text-[12.5px] font-semibold text-ink">{r.sym}</p>
        <p className="fig text-[10.5px] text-ink-3">{num(r.last)}</p>
      </div>
    </div>
  );
}

function TopSetups({ rows, onAll }: { rows: DashRow[]; onAll: () => void }) {
  const [chip, setChip] = usePersisted<TopChip>("dash.top", "all", oneOf("all", "long", "short", "news"));
  const ticker = useTicker();
  const shown = rows.filter(TOP_TEST[chip]);
  const counts = { all: rows.length, long: rows.filter(TOP_TEST.long).length, short: rows.filter(TOP_TEST.short).length, news: rows.filter(TOP_TEST.news).length };
  return (
    <section className={cn(CARD, "flex min-h-[260px] min-w-0 flex-col gap-2.5 xl:min-h-0")}>
      <Head title="Top setups" sub="The scanner's own rank" right={<Go onClick={onAll}>View all setups</Go>} />
      <div className="shrink-0">
        <Chips items={TOP_CHIPS} on={chip} set={setChip} counts={counts} />
      </div>
      <div className="min-h-0 flex-1 overflow-auto">
        {shown.length === 0 ? (
          <p className="py-8 text-center text-[12px] text-ink-3">Nothing scored here right now.</p>
        ) : (
          <table className="w-full border-separate border-spacing-0 text-left">
            <thead className="sticky top-0 z-10">
              <tr>
                <th scope="col" className={TH}>Ticker</th>
                <th scope="col" className={TH}>Side</th>
                <th scope="col" className={cn(TH, "text-center")} title="Against the previous day's range">PD</th>
                <th scope="col" className={cn(TH, "text-center")} title="Against the pre-market range">PM</th>
                <th scope="col" className={TH}>Setup</th>
                <th scope="col" className={TH}>Most important story</th>
                <th scope="col" className={TH}>Chart</th>
                <th scope="col" className={cn(TH, "text-right")}>Score</th>
              </tr>
            </thead>
            <tbody>
              {shown.map((r) => (
                <tr key={r.sym} {...rowProps(r.sym, ticker === r.sym)}>
                  <td className={TD}><Name r={r} /></td>
                  <td className={TD}>
                    <span className={cn("rounded-[3px] border border-ring px-1.5 py-px text-[11px] whitespace-nowrap", r.score.side === "long" ? "text-call-fig" : r.score.side === "short" ? "text-put-fig" : "text-ink-3")}>
                      {r.score.side === "long" ? "▲ Long" : r.score.side === "short" ? "▼ Short" : "None"}
                    </span>
                  </td>
                  <td className={cn(TD, "text-center")}><Dot at={pdPlace(r)} range="Previous day" /></td>
                  <td className={cn(TD, "text-center")}><Dot at={pmPlace(r)} range="Pre-market" /></td>
                  <td className={cn(TD, "text-[12px] whitespace-nowrap text-ink-2")}>{setupLabel(r)}</td>
                  <td className={TD}><CatalystCell c={r.catalyst} width={360} /></td>
                  <td className={TD}><Spark pts={r.spark} w={72} h={24} /></td>
                  <td className={cn(TD, "fig text-right text-[12.5px] text-ink")}>{r.score.total}</td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </div>
    </section>
  );
}

function MyList({ list, adds, onAll }: { list: DashRow[]; adds: DashRow[]; onAll: () => void }) {
  const [chip, setChip] = usePersisted<ListChip>("dash.list", "pinned", oneOf("pinned", "adds"));
  const ticker = useTicker();
  const rows = chip === "adds" ? adds : list;
  const items: ReadonlyArray<{ key: ListChip; label: string; title?: string }> = [
    { key: "pinned", label: "Pinned", title: "The names you starred" },
    { key: "adds", label: "Today's adds", title: "Names the pool or Track put on today's list; they roll off with the day" },
  ];
  return (
    <section className={cn(CARD, "flex min-h-[260px] min-w-0 flex-col gap-2.5 xl:min-h-0")}>
      <Head title="My list" right={<Go onClick={onAll}>View full list</Go>} />
      <div className="shrink-0">
        <Chips items={items} on={chip} set={setChip} counts={{ pinned: list.length, adds: adds.length }} />
      </div>
      <div className="min-h-0 flex-1 overflow-auto">
        {rows.length === 0 ? (
          <p className="py-8 text-center text-[12px] text-ink-3">{chip === "adds" ? "Nothing added today yet." : "No pinned names yet."}</p>
        ) : (
          <table className="w-full border-separate border-spacing-0 text-left">
            <thead className="sticky top-0 z-10">
              <tr>
                <th scope="col" className={TH}>Ticker</th>
                <th scope="col" className={cn(TH, "text-right")} title="Pre-market or after hours">Ext hrs</th>
                <th scope="col" className={cn(TH, "text-right")}>Day</th>
                <th scope="col" className={cn(TH, "text-center")}>PD</th>
                <th scope="col" className={cn(TH, "text-center")}>PM</th>
                <th scope="col" className={TH}>Chart</th>
              </tr>
            </thead>
            <tbody>
              {rows.map((r) => (
                <tr key={r.sym} {...rowProps(r.sym, ticker === r.sym)}>
                  <td className={TD}><Name r={r} /></td>
                  <td className={cn(TD, "fig text-right text-[12px]", dir(r.ext_pct))}>{pctText(r.ext_pct)}</td>
                  <td className={cn(TD, "fig text-right text-[12px]", dir(r.chg_pct))}>{pctText(r.chg_pct)}</td>
                  <td className={cn(TD, "text-center")}><Dot at={pdPlace(r)} range="Previous day" /></td>
                  <td className={cn(TD, "text-center")}><Dot at={pmPlace(r)} range="Pre-market" /></td>
                  <td className={TD}><Spark pts={r.spark} w={72} h={24} /></td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </div>
    </section>
  );
}

function StockNews({ stories, live }: { stories: DashStory[]; live: boolean }) {
  return (
    <section className={cn(CARD, "flex min-h-[260px] min-w-0 flex-col gap-2 xl:min-h-0")}>
      <Head
        title={
          <span className="flex items-center gap-2">
            Stock news
            {live && (
              <span className="qt-cap flex items-center gap-1 text-[9.5px] font-normal text-ink-3">
                <span aria-hidden className="h-[5px] w-[5px] rounded-full bg-call" />
                live
              </span>
            )}
          </span>
        }
        sub="Major stories, newest first"
      />
      <ul className="min-h-0 flex-1 overflow-auto pr-1">
        {stories.length === 0 && <li className="py-8 text-center text-[12px] text-ink-3">No major stories in the last thirty hours.</li>}
        {stories.map((s) => (
          <li key={`${s.syms.join()}-${s.title}`} className="border-b border-ring/60 py-2 last:border-b-0">
            <p className="text-[11.5px]">
              {s.syms.map((x, i) => (
                <span key={x}>
                  {i > 0 && <span className="text-ink-3">, </span>}
                  <button type="button" onClick={() => openTicker(x)} className="hit fig font-semibold text-ink">
                    {x}
                  </button>
                </span>
              ))}
              <span className="text-ink-3"> · {s.tag}</span>
            </p>
            <a href={s.url} target="_blank" rel="noreferrer noopener" className="hit mt-0.5 line-clamp-2 text-[12px] leading-[1.35] text-ink-2 hover:text-ink">
              {s.title}
            </a>
            <p className="fig mt-0.5 text-[10.5px] text-ink-3">
              {ageWord(s.age_min)} ago · {s.provider}
            </p>
          </li>
        ))}
      </ul>
    </section>
  );
}

function Rotation({ d, onHeat, onSector }: { d: DashboardPayload; onHeat: () => void; onSector: (key: string) => void }) {
  const max = heatMax(d.rotation.map((s) => s.day_pct));
  return (
    <section className={cn(CARD, "shrink-0")}>
      <Head title="Sector rotation" sub="Where money is moving, and the stocks pushing each sector" right={<Go onClick={onHeat}>View heat map</Go>} />
      <div className="mt-2.5 grid grid-cols-2 gap-2 sm:grid-cols-4 lg:grid-cols-6 min-[106.25rem]:grid-cols-11">
        {d.rotation.map((s) => (
          <button key={s.key} type="button" onClick={() => onSector(s.key)} title={`Open ${s.label} on the heat map`} style={heatStyle(s.day_pct, max)} className="hit min-w-0 rounded-[4px] border border-ring px-2.5 py-2 text-left">
            <p className="truncate text-[12px] font-semibold text-ink">{s.label}</p>
            <p className="flex items-baseline justify-between gap-1">
              <span className="fig text-[10.5px] text-ink-3">{s.key}</span>
              <span className={cn("fig text-[12px]", dir(s.day_pct))}>{pct(s.day_pct)}</span>
            </p>
            <p className="qt-cap mt-1.5 text-[9px] text-ink-3">Leaders</p>
            <p className="fig truncate text-[11px] text-ink-2">{s.leaders.length ? s.leaders.join(" · ") : "—"}</p>
          </button>
        ))}
      </div>
    </section>
  );
}
