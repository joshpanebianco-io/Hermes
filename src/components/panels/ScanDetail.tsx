"use client";

import type { ScanRow, Side } from "@/types/scanner";
import { Tick } from "@/components/ui/Tick";
import { ago, compact, dir, num, pct } from "@/lib/format";
import { cn } from "@/lib/cn";

/**
 * One name, read top to bottom in the order you would act on it: what the
 * setup is and where the entry sits, why it ranks where it does, the levels
 * around price, and then what could move it that the chart does not show —
 * earnings, filings, headlines.
 *
 * THE LADDER IS IN PRICE ORDER, with every level measured from the last print
 * in ten-minute ATRs, because "0.3 ATR above the PMH" is the sentence the
 * retest trade is made of and "$0.41 above" is not — the same forty cents is a
 * retest on one name and noise on another.
 */

export const sideHue = (s: Side) => (s === "long" ? "text-call-fig" : "text-put-fig");

export const levelGlyph = (k: "forming") => (k === "forming" ? "···" : "");

const LEVEL_FIELD = { PDH: "pdh", PDL: "pdl", PMH: "pmh", PML: "pml" } as const;

/** The setup column's words: the state, and the level or reference it is about. */
export function setupLabel(r: ScanRow): string {
  const { state, level, entry, side } = r.setup;
  switch (state) {
    case "retest":
      return `Retest ${level ?? entry?.kind ?? ""}`.trim();
    case "pullback":
      return `Pulling back to ${level ?? entry?.kind ?? "level"}`;
    case "extended":
      return entry && (entry.kind === "VWAP" || entry.kind === "EMA8")
        ? `Extended → ${entry.kind === "EMA8" ? "8 EMA" : "VWAP"}`
        : `Extended past ${level ?? "level"}`;
    case "approaching":
      return `Near ${level ?? "a level"}`;
    case "failed":
      return `Failed ${level ?? ""}`.trim();
    case "forming":
      // Pre-market: the levels are not locked yet, so the row says what the
      // open has to do — hold beyond a level it has already broken, or break
      // one it has not. Read off `broken`, never inferred from the side.
      if (!level) return "Inside · plan";
      if (r.broken[LEVEL_FIELD[level]]) return `${side === "short" ? "Below" : "Above"} ${level} · plan`;
      return `Break of ${level} · plan`;
    case "chop":
      return "Inside — chop";
  }
}

export function ScanDetail({ r, bench, now }: { r: ScanRow; bench: "SPY" | "QQQ"; now: number | null }) {
  if (!r.ok) {
    return (
      <div className="px-6 py-6">
        <p className="text-[18px] font-semibold text-ink">{r.sym}</p>
        <p className="mt-2 text-[12px] text-ink-3">{r.error ?? "No data for this name yet."}</p>
      </div>
    );
  }
  const side = r.setup.side ?? r.score.side;
  return (
    <div className="flex flex-col divide-y divide-ring">
      <Head r={r} bench={bench} side={side} />
      <Setup r={r} side={side} />
      <Score r={r} />
      <Ladder r={r} />
      <Catalysts r={r} now={now} />
    </div>
  );
}

/* -------------------------------------------------------------------------- */

function Head({ r, bench, side }: { r: ScanRow; bench: "SPY" | "QQQ"; side: Side | null }) {
  const rs = r.rs[bench];
  const rs1h = r.rs_1h[bench];
  return (
    <div className="px-6 pt-5 pb-4">
      <div className="flex items-baseline gap-2.5">
        <span className={cn("text-[14px]", side ? sideHue(side) : "text-ink-4")}>
          {side === "long" ? "▲" : side === "short" ? "▼" : "·"}
        </span>
        <span className="text-[21px] leading-none font-semibold text-ink">{r.sym}</span>
        {r.name && <span className="truncate text-[12.5px] text-ink-3">{r.name}</span>}
        {r.sector && (
          <span
            className="ml-auto shrink-0 text-[11.5px] text-ink-3"
            title="The name's sector SPDR against SPY today, in percentage points"
          >
            <span className="qt-cap text-[10.5px] text-ink-3">{r.sector}</span>{" "}
            <span className={cn("fig", dir(r.sector_rs))}>
              {r.sector_rs != null ? `${r.sector_rs >= 0 ? "+" : ""}${r.sector_rs.toFixed(2)}` : "—"}
            </span>{" "}
            vs SPY
          </span>
        )}
      </div>
      <div className="mt-3.5 grid grid-cols-3 gap-x-4 gap-y-3 sm:grid-cols-6">
        <Fig label="Last">
          <Tick value={num(r.last)} className="fig text-[16px] text-ink" />
        </Fig>
        <Fig label="Chg">
          <Tick value={pct(r.chg_pct)} className={cn("fig text-[14px]", dir(r.chg_pct))} />
        </Fig>
        <Fig label="Pre / post">
          <span className={cn("fig text-[14px]", r.ext_pct == null ? "text-ink-4" : dir(r.ext_pct))}>
            {r.ext_pct == null ? "—" : pct(r.ext_pct)}
          </span>
        </Fig>
        <Fig label={`RS ${bench}`} title={`Today · last hour (six ten-minute bars), each in ATRs, minus ${bench}'s`}>
          <span className={cn("fig text-[14px]", rs == null ? "text-ink-4" : dir(rs))}>
            {rs == null ? "—" : `${rs >= 0 ? "+" : ""}${rs.toFixed(2)}`}
          </span>
          <span className="fig ml-1.5 text-[11px] text-ink-4">
            1h {rs1h == null ? "—" : `${rs1h >= 0 ? "+" : ""}${rs1h.toFixed(2)}`}
          </span>
        </Fig>
        <Fig label="RVol" title={r.volume != null ? `${compact(r.volume)} shares today incl. pre/post` : undefined}>
          <span className="fig text-[14px] text-ink">{r.rvol != null ? `${r.rvol.toFixed(1)}×` : "—"}</span>
          <span className="fig ml-1.5 text-[11px] text-ink-4">{compact(r.volume)}</span>
        </Fig>
        <Fig
          label="Range used"
          title="Today's regular-session high-to-low as a share of the daily ATR. Past about 1.2 the day's fuel is mostly spent."
        >
          <span
            className={cn(
              "fig text-[14px]",
              r.range_used == null ? "text-ink-4" : r.range_used >= 1.2 ? "text-flip-fig" : "text-ink",
            )}
          >
            {r.range_used != null ? `${Math.round(r.range_used * 100)}%` : "—"}
          </span>
          <span className="fig ml-1.5 text-[11px] text-ink-4">ATR {num(r.atr_d)}</span>
        </Fig>
      </div>
    </div>
  );
}

function Fig({ label, title, children }: { label: string; title?: string; children: React.ReactNode }) {
  return (
    <div className="min-w-0" title={title}>
      <p className="qt-cap mb-1 text-[10px] text-ink-4">{label}</p>
      <div className="flex items-baseline whitespace-nowrap">{children}</div>
    </div>
  );
}

const Cap = ({ children, right }: { children: React.ReactNode; right?: React.ReactNode }) => (
  <div className="mb-2.5 flex items-baseline gap-2">
    <h3 className="text-[13.5px] font-semibold text-ink">{children}</h3>
    {right && <div className="ml-auto text-[11px] text-ink-4">{right}</div>}
  </div>
);

/* -------------------------------------------------------------------------- */

function Setup({ r, side }: { r: ScanRow; side: Side | null }) {
  const e = r.setup.entry;
  const live = r.setup.state === "retest";
  return (
    <section className="px-6 py-4">
      <Cap>The setup</Cap>
      <p
        className={cn(
          "text-[16px] leading-tight font-semibold",
          live && side ? sideHue(side) : r.setup.state === "approaching" ? "text-flip-fig" : "text-ink",
        )}
      >
        {side === "long" ? "Long · " : side === "short" ? "Short · " : ""}
        {setupLabel(r)}
      </p>
      {r.setup.note && <p className="mt-1.5 text-[12.5px] leading-[1.5] text-ink-2">{r.setup.note}</p>}
      {e && (
        <p className="mt-2.5 text-[12px] text-ink-3">
          <span className="qt-cap mr-1.5 text-[10.5px] text-ink-4">Entry reference</span>
          <span className="text-ink-2">{e.kind === "EMA8" ? "8 EMA wave" : e.kind}</span>{" "}
          <span className="fig text-ink">{num(e.price)}</span>
          <span className="fig ml-1.5 text-ink-3">
            · price {e.dist_atr >= 0 ? "+" : ""}
            {e.dist_atr.toFixed(2)} ATR from it
          </span>
        </p>
      )}

      <div className="mt-3.5">
        <p className="qt-cap mb-1.5 text-[10.5px] text-ink-4">Signals today · confirmed 10-minute bars</p>
        {r.signals.length === 0 ? (
          <p className="text-[12px] text-ink-4">None yet.</p>
        ) : (
          <ul className="flex flex-col">
            {r.signals.map((s, i) => (
              <li key={`${s.kind}-${s.at_et}-${i}`} className="flex items-baseline gap-2.5 py-[3px] text-[12px]">
                <span className="fig w-[40px] shrink-0 text-ink-3">{s.at_et}</span>
                <span
                  className={cn(
                    "fig w-[46px] shrink-0 font-semibold",
                    s.kind === "E_SETUP" || s.kind === "BO" ? "text-ink-2" : sideHue(s.side),
                  )}
                >
                  {s.kind === "E_SETUP" ? "(E)" : s.kind === "BO" ? "◆" : `(${s.kind})`}{" "}
                  {s.kind === "E_SETUP" ? "" : s.side === "long" ? "▲" : "▼"}
                </span>
                <span className="min-w-0 text-ink-2">{s.note}</span>
              </li>
            ))}
          </ul>
        )}
      </div>
    </section>
  );
}

/* -------------------------------------------------------------------------- */

function Score({ r }: { r: ScanRow }) {
  return (
    <section className="px-6 py-4">
      <Cap right={<span title="Each part is a fixed rule; together they order the list. Not a measured probability.">heuristic rank</span>}>
        Why it ranks here <span className="fig ml-1.5 text-ink-2">{r.score.total}</span>
      </Cap>
      <ul className="flex flex-col gap-2">
        {r.score.parts.map((p) => {
          const penalty = p.pts < 0;
          return (
            <li key={p.key} className="grid grid-cols-[96px_minmax(0,1fr)_46px] items-center gap-x-3 gap-y-0.5">
              <span className="text-[12px] text-ink-2">{p.label}</span>
              {penalty || p.max <= 0 ? (
                <span className="text-[11.5px] text-ink-3">{p.note}</span>
              ) : (
                <span className="relative h-[4px] bg-[var(--qt-track,var(--ring))]">
                  <span
                    className="absolute inset-y-0 left-0 bg-ink-2"
                    style={{ width: `${Math.max(0, Math.min(1, p.pts / p.max)) * 100}%` }}
                  />
                </span>
              )}
              <span
                className={cn("fig text-right text-[12px]", penalty ? "text-flip-fig" : "text-ink")}
              >
                {penalty ? Math.round(p.pts) : `${Math.round(p.pts)}/${p.max}`}
              </span>
              {!penalty && p.max > 0 && p.note && (
                <span className="col-start-2 col-end-4 text-[11px] leading-[1.4] text-ink-4">{p.note}</span>
              )}
            </li>
          );
        })}
      </ul>
    </section>
  );
}

/* -------------------------------------------------------------------------- */

interface Rung {
  key: string;
  label: string;
  price: number;
  tone: "call" | "put" | "neutral" | "spot" | "broken-hi" | "broken-lo";
  hint?: string;
}

function Ladder({ r }: { r: ScanRow }) {
  const L = r.levels;
  const rungs: Rung[] = [];
  const add = (key: string, label: string, price: number | null, tone: Rung["tone"], hint?: string) => {
    if (price != null && Number.isFinite(price)) rungs.push({ key, label, price, tone, hint });
  };
  add("pdh", "PDH", L.pdh, r.broken.pdh ? "broken-hi" : "call", "previous regular-session high");
  add("pmh", "PMH", L.pm_done ? L.pmh : null, r.broken.pmh ? "broken-hi" : "call", "pre-market high");
  add("pml", "PML", L.pm_done ? L.pml : null, r.broken.pml ? "broken-lo" : "put", "pre-market low");
  add("pdl", "PDL", L.pdl, r.broken.pdl ? "broken-lo" : "put", "previous regular-session low");
  add("vwap", "VWAP", L.vwap, "neutral", "volume-weighted average price for the session");
  add("ema8", "8 EMA", L.ema8, "neutral", "the 8 EMA on ten-minute bars");
  add("pdc", "Prev close", L.pdc, "neutral");
  add("dhi", "Day high", L.day_hi, "neutral", "today's regular-session high so far");
  add("dlo", "Day low", L.day_lo, "neutral", "today's regular-session low so far");
  if (!L.pm_done) {
    add("pmh_f", "PMH forming", L.pmh, "neutral", "pre-market high so far — locks at 09:30");
    add("pml_f", "PML forming", L.pml, "neutral", "pre-market low so far — locks at 09:30");
  }
  if (r.last != null) rungs.push({ key: "last", label: "Last", price: r.last, tone: "spot" });
  rungs.sort((a, b) => b.price - a.price);

  const atr = r.atr_b;
  return (
    <section className="px-6 py-4">
      <Cap right={atr != null ? <span className="fig">10m ATR {num(atr)}</span> : undefined}>Levels</Cap>
      {L.wave_hi != null && L.wave_lo != null && (
        <p className="mb-2 text-[11.5px] text-ink-3">
          8 EMA wave <span className="fig text-ink-2">{num(L.wave_lo)}</span>–
          <span className="fig text-ink-2">{num(L.wave_hi)}</span>
        </p>
      )}
      <ul className="flex flex-col">
        {rungs.map((g) => {
          const d = r.last != null && atr ? (g.price - r.last) / atr : null;
          const spot = g.tone === "spot";
          return (
            <li
              key={g.key}
              title={g.hint}
              className={cn(
                "grid grid-cols-[minmax(0,1fr)_88px_70px] items-baseline gap-2 py-[3px]",
                spot && "my-0.5 border-y border-ring bg-surface-2 py-[5px]",
              )}
            >
              <span
                className={cn(
                  "text-[12px]",
                  spot && "font-semibold text-ink",
                  g.tone === "call" && "text-call-fig",
                  g.tone === "put" && "text-put-fig",
                  g.tone === "neutral" && "text-ink-2",
                  (g.tone === "broken-hi" || g.tone === "broken-lo") && "text-ink-3",
                )}
              >
                {(g.tone === "broken-hi" || g.tone === "broken-lo") && (
                  <span
                    aria-hidden
                    className={cn(
                      "mr-1.5 inline-block h-[7px] w-[7px] rounded-[1px] align-middle",
                      g.tone === "broken-hi" ? "bg-call-fig" : "bg-put-fig",
                    )}
                  />
                )}
                {g.label}
                {(g.tone === "broken-hi" || g.tone === "broken-lo") && (
                  <span className="qt-cap ml-1.5 text-[9.5px] text-ink-4">broken</span>
                )}
              </span>
              <span className={cn("fig text-right text-[12.5px]", spot ? "text-ink" : "text-ink-2")}>
                {num(g.price)}
              </span>
              <span className="fig text-right text-[11px] text-ink-4">
                {spot || d == null ? "" : `${d >= 0 ? "+" : ""}${d.toFixed(1)} ATR`}
              </span>
            </li>
          );
        })}
      </ul>
    </section>
  );
}

/* -------------------------------------------------------------------------- */

const KIND_LABEL: Record<ScanRow["news"][number]["kind"], string> = {
  rating: "Rating",
  earnings: "Earnings",
  filing: "Filing",
  news: "News",
};

function Catalysts({ r, now }: { r: ScanRow; now: number | null }) {
  const e = r.earnings;
  return (
    <section className="px-6 py-4">
      <Cap>Catalysts</Cap>

      <div className="flex flex-col gap-1.5">
        <p className="text-[12px] text-ink-2">
          <span className="qt-cap mr-2 text-[10.5px] text-ink-4">Earnings</span>
          {e ? (
            <>
              <span className="text-ink">{earnDay(e.date, e.days)}</span>{" "}
              <span className="text-ink-3">
                {e.when === "pre" ? "before the open" : e.when === "after" ? "after the close" : "time unconfirmed"}
              </span>
              {e.eps_actual ? (
                <span className="fig ml-2">
                  EPS {e.eps_actual} vs {e.eps_forecast ?? "—"}e
                  {e.surprise_pct != null && (
                    <span className={cn("ml-1", dir(e.surprise_pct))}>
                      ({e.surprise_pct >= 0 ? "+" : ""}
                      {e.surprise_pct.toFixed(1)}%)
                    </span>
                  )}
                </span>
              ) : e.eps_forecast ? (
                <span className="fig ml-2 text-ink-3">est {e.eps_forecast}</span>
              ) : null}
            </>
          ) : (
            <span className="text-ink-4">none in the window the calendar covers</span>
          )}
        </p>
        {r.flags.length > 0 && (
          <ul className="flex flex-col gap-1">
            {r.flags.map((f) => (
              <li key={`${f.kind}-${f.text}`} className="flex items-baseline gap-2 text-[12px]">
                <span
                  aria-hidden
                  className={cn(
                    "mt-[5px] h-[6px] w-[6px] shrink-0 rounded-[1px]",
                    f.tone === "warn" ? "bg-flip-fig" : f.tone === "good" ? "bg-call-fig" : "bg-ink-4",
                  )}
                />
                <span className="text-ink-2">{f.text}</span>
              </li>
            ))}
          </ul>
        )}
      </div>

      {r.filings.length > 0 && (
        <div className="mt-3.5">
          <p className="qt-cap mb-1.5 text-[10.5px] text-ink-4">SEC filings · last 3 days</p>
          <ul className="flex flex-col">
            {r.filings.map((f) => (
              <li key={`${f.form}-${f.filed}-${f.url}`}>
                <a
                  href={f.url}
                  target="_blank"
                  rel="noreferrer noopener"
                  className="hit grid grid-cols-[56px_92px_minmax(0,1fr)] items-baseline gap-2 py-[3px] text-[12px]"
                >
                  <span className="fig font-semibold text-ink">{f.form}</span>
                  <span className="fig text-ink-3">{filedAt(f.filed)}</span>
                  <span className="truncate text-ink-2">{f.desc}</span>
                </a>
              </li>
            ))}
          </ul>
        </div>
      )}

      <div className="mt-3.5">
        <p className="qt-cap mb-1.5 text-[10.5px] text-ink-4">Headlines · last 3 days</p>
        {r.news.length === 0 ? (
          <p className="text-[12px] text-ink-4">No headlines found for this name.</p>
        ) : (
          <ul className="flex flex-col divide-y divide-ring/60">
            {r.news.map((n) => (
              <li key={n.url}>
                <a href={n.url} target="_blank" rel="noreferrer noopener" className="hit flex flex-col gap-0.5 py-2">
                  <span className="text-[12.5px] leading-[1.4] text-ink">{n.title}</span>
                  <span className="flex items-baseline gap-2 text-[11px] text-ink-4">
                    {n.kind !== "news" && (
                      <span className={cn("qt-cap text-[9.5px]", n.kind === "rating" ? "text-flip-fig" : "text-ink-3")}>
                        {KIND_LABEL[n.kind]}
                      </span>
                    )}
                    <span className="text-ink-3">{n.publisher}</span>
                    <span className="fig">{ago(n.utc, now)}</span>
                  </span>
                </a>
              </li>
            ))}
          </ul>
        )}
      </div>
    </section>
  );
}

/** EDGAR's acceptance time → "Oct 12 16:05", in New York time like everything else here. */
function filedAt(iso: string): string {
  const d = new Date(iso);
  if (Number.isNaN(d.getTime())) return iso;
  const day = d.toLocaleDateString("en-US", { month: "short", day: "numeric", timeZone: "America/New_York" });
  const t = d.toLocaleTimeString("en-US", { hour: "2-digit", minute: "2-digit", hour12: false, timeZone: "America/New_York" });
  return `${day} ${t}`;
}

/** "Today", "Tomorrow", "Thu Oct 16 · in 3d", "Mon Oct 12 · 1d ago". */
function earnDay(iso: string, days: number): string {
  if (days === 0) return "Today";
  if (days === 1) return "Tomorrow";
  if (days === -1) return "Yesterday";
  const d = new Date(`${iso}T12:00:00Z`);
  const name = Number.isNaN(d.getTime())
    ? iso
    : d.toLocaleDateString("en-US", { weekday: "short", month: "short", day: "numeric", timeZone: "UTC" });
  return days > 0 ? `${name} · in ${days}d` : `${name} · ${-days}d ago`;
}
