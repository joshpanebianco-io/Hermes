"use client";

import type { SectorRow } from "@/types/terminal";
import { Module } from "@/components/ui/Module";
import { Tick } from "@/components/ui/Tick";
import { pct } from "@/lib/format";
import { cn } from "@/lib/cn";
import { segItem } from "@/lib/seg";
import { oneOf, usePersisted } from "@/lib/usePersisted";

/**
 * Sector rotation — who is being bought, measured against the index.
 *
 * RELATIVE STRENGTH, NOT RETURN. On a day the whole market is up 1%, a sector
 * up 0.8% is being SOLD relative to it, and an absolute-return table shows
 * that as green. Every bar here is excess return over SPY, which is the only
 * form of the number that answers "is money rotating in".
 *
 * THE SPAN IS A REAL TENSION, and the default sits on the near side of it.
 * Rotation is properly a claim about weeks — one session's move is noise
 * against it, and a leadership table built on a single day reshuffles every
 * morning. But this terminal is read at the open to judge the day ahead, and
 * for that question the month is answering something else. So it opens on 1D
 * with 1W and 1M one click away; see the note on SPANS.
 *
 * SPY AND RSP ARE ON THE LIST BUT NOT IN THE RANKING. SPY is the benchmark and
 * would always read exactly zero; RSP against SPY is the breadth trade — equal
 * weight beating cap weight means the rally is broadening — which is a
 * different claim from a sector's and is stated separately underneath.
 */

/*
 * 1D FIRST AND 1D BY DEFAULT (owner instruction, 2026-08-31).
 *
 * The panel opened on a month because rotation is a claim about weeks and one
 * session is noise against it — that argument still holds and is why 1W and 1M
 * are one click away. But this terminal is read at the open to judge the day
 * ahead, and for that question the honest span is the one the session is
 * actually trading. The button order follows the default: the first chip is
 * the one you land on.
 */
const SPANS = [
  { key: "day", label: "1D" },
  { key: "week", label: "1W" },
  { key: "month", label: "1M" },
] as const;

type Span = (typeof SPANS)[number]["key"];

export function Rotation({
  rows,
  ageMin,
  error,
}: {
  rows: SectorRow[];
  ageMin?: number | null;
  error?: string | null;
}) {
  const [span, setSpan] = usePersisted<Span>("rot.span", "day", oneOf("day", "week", "month"));

  const sectors = rows.filter((r) => r.key !== "SPY" && r.key !== "RSP");
  const spy = rows.find((r) => r.key === "SPY");
  const rsp = rows.find((r) => r.key === "RSP");

  const rsKey = `rs_${span}` as const;
  const ranked = [...sectors].sort(
    (a, b) => (b[rsKey] ?? -Infinity) - (a[rsKey] ?? -Infinity),
  );
  const max = Math.max(1, ...ranked.map((r) => Math.abs(r[rsKey] ?? 0)));

  const breadth = rsp ? (rsp[rsKey] ?? null) : null;

  return (
    <Module
      title="Sector rotation"
      sub="vs SPY"
      ageMin={ageMin}
      error={error}
      bodyClassName="px-0 py-0"
      right={
        <div className="seg">
          {SPANS.map((s) => (
            <button
              key={s.key}
              type="button"
              onClick={() => setSpan(s.key)}
              {...segItem(s.key === span, { className: "text-[10px] normal-case tracking-normal" })}
            >
              {s.label}
            </button>
          ))}
        </div>
      }
    >
      {ranked.length === 0 ? (
        <p className="px-3 py-6 text-center text-[11px] text-ink-4">No sector data yet.</p>
      ) : (
        <>
          <ul className="py-1">
            {ranked.map((r) => {
              const v = r[rsKey];
              const abs = r[`${span}_pct` as const];
              return (
                <li key={r.key} className="hit flex items-center gap-2 px-3 py-[3px]">
                  <span className="fig w-[38px] shrink-0 text-[10.5px] text-ink-2">{r.key}</span>
                  <span className="hidden w-[104px] shrink-0 truncate text-[10px] text-ink-4 sm:block">
                    {r.label}
                  </span>
                  <Bar v={v} max={max} />
                  <span
                    className={cn(
                      "fig w-[52px] shrink-0 text-right text-[11px]",
                      (v ?? 0) > 0 ? "up" : (v ?? 0) < 0 ? "down" : "flat",
                    )}
                    title="Excess return over SPY"
                  >
                    <Tick value={pct(v)} />
                  </span>
                  <Tick
                    value={pct(abs)}
                    className="fig w-[52px] shrink-0 text-right text-[10px] text-ink-4"
                  />
                </li>
              );
            })}
          </ul>
          <div className="border-t border-ring/40 px-3 py-1.5 text-[10px] leading-relaxed text-ink-3">
            {breadth === null ? (
              <span className="text-ink-4">Breadth unavailable.</span>
            ) : (
              <>
                <span className="text-ink-4">Breadth </span>
                <span className={breadth >= 0 ? "up" : "down"}>{pct(breadth)}</span>
                <span className="text-ink-4">
                  {" "}
                  — equal weight {breadth >= 0 ? "beating" : "lagging"} cap weight, so the move is{" "}
                  {breadth >= 0 ? "broad" : "carried by the largest names"}.
                </span>
              </>
            )}
            {spy && (
              <span className="text-ink-4">
                {" "}
                SPY {pct(spy[`${span}_pct` as const])} over the same span.
              </span>
            )}
          </div>
        </>
      )}
    </Module>
  );
}

/** A centred divergent bar: right of the rule is leading, left is lagging. */
function Bar({ v, max }: { v: number | null; max: number }) {
  const w = v === null ? 0 : (Math.abs(v) / max) * 50;
  const pos = (v ?? 0) >= 0;
  return (
    <span className="relative h-[8px] flex-1 min-w-[40px]">
      <span className="absolute inset-y-0 left-1/2 w-px -translate-x-1/2 bg-ring" aria-hidden />
      {v !== null && (
        <span
          className="absolute top-1/2 h-[5px] -translate-y-1/2 rounded-sm"
          style={{
            left: pos ? "50%" : `calc(50% - ${w}%)`,
            width: `${w}%`,
            background: pos ? "var(--call)" : "var(--put)",
            opacity: 0.85,
          }}
        />
      )}
    </span>
  );
}
