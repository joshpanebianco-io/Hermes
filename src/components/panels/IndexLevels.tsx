"use client";

import type { ScanRow } from "@/types/scanner";
import { Module } from "@/components/ui/Module";
import { Skeleton } from "@/components/ui/Skeleton";
import { num, signed } from "@/lib/format";
import { useIndexLevels } from "@/lib/useIndexLevels";
import { cn } from "@/lib/cn";

/**
 * Index levels — SPY, QQQ and IWM against their own levels (owner, 2026-10-30).
 *
 * WHY THE INDEX FIRST. Every single-name trade on the stocks desk is made
 * against the tape, and "where does the index sit against its levels" is
 * that read in the strategy's own terms: above the previous day's high is a
 * different day from inside yesterday's range. The scanner already works
 * these three out exactly as it does every name — PDH, PDL, PMH, PML, VWAP,
 * and which have been taken out — so this is those rows, lifted onto
 * Structure beside the futures ladder (lib/useIndexLevels.ts).
 *
 * A LEVEL THAT HAS BEEN TAKEN OUT PRINTS IN AMBER, the session ranges'
 * convention, so the two panels read the same way: amber is a level that no
 * longer holds.
 */
const LEVELS: { key: "pmh" | "pml" | "pdh" | "pdl"; label: string; title: string }[] = [
  { key: "pdh", label: "PDH", title: "Previous day's high" },
  { key: "pdl", label: "PDL", title: "Previous day's low" },
  { key: "pmh", label: "PMH", title: "Pre-market high — final at 09:30 ET" },
  { key: "pml", label: "PML", title: "Pre-market low — final at 09:30 ET" },
];

const TREND = { 1: "▲", 0: "⚠", [-1]: "▼" } as Record<number, string>;

export function IndexLevels() {
  const { rows, failed } = useIndexLevels();
  return (
    <Module title="Index levels" sub="SPY · QQQ · IWM against their own levels" error={failed} bodyClassName="px-0 py-0">
      {!rows ? (
        <div className="px-3 py-2">
          <Skeleton rows={3} label="Loading the index levels" />
        </div>
      ) : rows.length === 0 ? (
        <p className="px-3 py-5 text-center text-[11px] text-ink-3">The scanner has not built these names yet.</p>
      ) : (
        <table className="w-full border-collapse">
          <thead>
            <tr className="text-[8.5px] tracking-[0.06em] text-ink-4 uppercase">
              <th className="px-2 py-1 text-left font-medium">Name</th>
              <th className="px-1 py-1 text-right font-medium">Last</th>
              {LEVELS.map((l) => (
                <th key={l.key} className="px-1 py-1 text-right font-medium" title={l.title}>
                  {l.label}
                </th>
              ))}
              <th className="px-1.5 py-1 text-right font-medium" title="Anchored at 09:30 ET">
                VWAP
              </th>
            </tr>
          </thead>
          <tbody>
            {rows.map((r) => (
              <Row key={r.sym} r={r} />
            ))}
          </tbody>
        </table>
      )}
    </Module>
  );
}

function Row({ r }: { r: ScanRow }) {
  const lv = r.levels;
  const chg = r.chg_pct ?? null;
  const note = r.setup?.note ?? null;
  return (
    <>
      <tr className="hit border-t border-ring/40" title={note ?? undefined}>
        <td className="px-2 py-[3px] text-[10.5px] whitespace-nowrap">
          <span className={cn("fig mr-1 text-[10px]", r.trend === 1 ? "text-call-fig" : r.trend === -1 ? "text-put-fig" : "text-ink-4")} aria-hidden>
            {TREND[r.trend ?? 0]}
          </span>
          <span className="fig font-semibold text-ink">{r.sym}</span>
        </td>
        <td className="fig px-1 py-[3px] text-right text-[10.5px] whitespace-nowrap">
          <span className="text-ink">{num(r.last, 2)}</span>{" "}
          <span className={cn("text-[9.5px]", chg === null ? "text-ink-4" : chg > 0 ? "text-call-fig" : chg < 0 ? "text-put-fig" : "text-ink-3")}>
            {chg === null ? "" : `${signed(chg, 2)}%`}
          </span>
        </td>
        {LEVELS.map((l) => {
          const v = lv?.[l.key] ?? null;
          const gone = Boolean(r.broken?.[l.key]);
          return (
            <td key={l.key} className={cn("fig px-1 py-[3px] text-right text-[10.5px] whitespace-nowrap", gone ? "text-flip" : "text-ink-2")} title={gone ? `${l.title} — taken out` : l.title}>
              {v === null ? "—" : num(v, 2)}
            </td>
          );
        })}
        <td className="fig px-1.5 py-[3px] text-right text-[10.5px] whitespace-nowrap text-ink-2">{lv?.vwap == null ? "—" : num(lv.vwap, 2)}</td>
      </tr>
      {note && (
        <tr>
          <td colSpan={7} className="px-2 pb-1.5 text-[10px] leading-snug text-ink-3">
            {note}
          </td>
        </tr>
      )}
    </>
  );
}
