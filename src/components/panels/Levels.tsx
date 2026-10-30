"use client";

import type { BriefLadder, BriefLadderRow } from "@/types/terminal";
import { Module } from "@/components/ui/Module";
import { Skeleton } from "@/components/ui/Skeleton";
import { useQuiet } from "@/components/state/UiMode";
import { num, signed } from "@/lib/format";
import { oneOf, usePersisted } from "@/lib/usePersisted";
import { segItem } from "@/lib/seg";
import { cn } from "@/lib/cn";

/**
 * Levels — the live ladder per book: every price the session trades against,
 * in price order, measured from last (owner, 2026-10-30: the Structure tab's
 * "structure worth tracking").
 *
 * THE BRIEF'S LADDER, LIVE. The Analysis brief computes this table every time
 * a note is written and then it sits inside the note, going stale with it.
 * The collector now computes the same ladder on every terminal poll
 * (report.live_ladders) with the rows a note does not need but a desk
 * watching the tape does: VWAP from the reopen and from the cash open, the
 * opening range, today's two opens. The strategy is a levels strategy — a
 * break of a level, entered on its retest, or on VWAP when price has run —
 * and this is the futures desk's version of the scanner's levels columns.
 *
 * ONE BOOK AT A TIME, with the picker the ranges and the profile use, so the
 * three panels in this column read the same book together.
 */
const ASSETS = ["NQ", "ES", "GC"] as const;

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

export function Levels({
  ladders,
  ageMin,
  error,
}: {
  ladders: Record<string, BriefLadder | null> | undefined;
  ageMin?: number | null;
  error?: string | null;
}) {
  const quiet = useQuiet();
  const hues = quiet ? KIND_HUE_QT : KIND_HUE;
  const [sel, setSel] = usePersisted<string>("levels.asset", "NQ", oneOf(...ASSETS));
  const keys = ASSETS.filter((k) => ladders?.[k]);
  const l = ladders?.[sel] ?? ladders?.[keys[0]] ?? null;

  return (
    <Module
      title="Levels"
      sub={l ? `last ${num(l.last, l.dp)}${l.em !== null ? ` · expected move ±${num(l.em, l.dp)}` : ""}` : "what each book trades against"}
      ageMin={ageMin}
      error={error}
      bodyClassName="px-0 py-0"
      right={
        keys.length > 1 && (
          <span className="seg" role="tablist" aria-label="Book">
            {keys.map((k) => (
              <button key={k} type="button" role="tab" aria-selected={sel === k} onClick={() => setSel(k)} {...segItem(sel === k)}>
                {k}
              </button>
            ))}
          </span>
        )
      }
    >
      {!ladders ? (
        <div className="px-3 py-2">
          <Skeleton rows={8} label="Loading the levels" />
        </div>
      ) : !l ? (
        <p className="px-3 py-5 text-center text-[11px] text-ink-3">No levels for this book yet — the collector needs a price and the night&apos;s bars.</p>
      ) : (
        <>
          <table className="w-full border-collapse">
            <tbody>
              {l.rows.map((r, i) => {
                const last = r.kind === "last";
                const muted = r.kind === "em" || r.kind === "ref" || r.kind === "open";
                const ink = last ? (quiet ? "text-ink" : "text-bg") : muted ? "text-ink-3" : "text-ink";
                // A band's rows share a bracket down their left edge; its first row carries the count.
                const band = r.band != null ? l.confluence?.[r.band] : undefined;
                const bandFirst = band && (i === 0 || l.rows[i - 1].band !== r.band);
                const bandLast = band && (i === l.rows.length - 1 || l.rows[i + 1].band !== r.band);
                return (
                  <tr
                    key={i}
                    className="hit border-b border-ring/40 last:border-b-0"
                    title={
                      last
                        ? "Last — the line every level is measured from"
                        : `${r.label} · ${signed(r.dist, l.dp)} from last${r.inside_em ? " · inside the expected move" : ""}${band ? `\n${band.text}` : ""}`
                    }
                    style={{
                      background: last
                        ? quiet
                          ? "var(--surface-3)"
                          : "var(--spot)"
                        : r.inside_em
                          ? quiet
                            ? "color-mix(in oklab, var(--surface-2) 60%, transparent)"
                            : "color-mix(in oklab, var(--surface-3) 80%, transparent)"
                          : undefined,
                    }}
                  >
                    <td className="w-[3px] p-0" style={{ background: hues[r.kind] }} />
                    <td className="w-[6px] p-0">
                      {band && (
                        <span
                          className={cn("block h-full w-[4px] border-l border-flip", bandFirst && "rounded-tl-[3px] border-t", bandLast && "rounded-bl-[3px] border-b")}
                          style={{ minHeight: 18 }}
                        />
                      )}
                    </td>
                    <td className={cn("fig w-[78px] px-2 py-[3px] text-right text-[11px] whitespace-nowrap", ink, (last || r.kind === "flip") && "font-bold")}>
                      {num(r.price, l.dp)}
                    </td>
                    <td className={cn("truncate px-2 py-[3px] text-[11px]", ink, (last || r.kind === "flip") && "font-semibold", r.kind === "em" && "italic")}>
                      {r.label}
                      {bandFirst && band && (
                        <span className="fig ml-1.5 text-[9px] text-flip-fig" title={band.text}>
                          ×{band.n}
                        </span>
                      )}
                    </td>
                    <td className={cn("fig w-[62px] px-2 py-[3px] text-right text-[10.5px] whitespace-nowrap", last ? (quiet ? "text-ink-2" : "text-bg") : "text-ink-3")}>
                      {r.dist === null ? "" : signed(r.dist, l.dp)}
                    </td>
                  </tr>
                );
              })}
            </tbody>
          </table>
          {/* THE BANDS AND THE REGIME LINE (structure.py, 2026-10-30): where three
              or more rows sit inside a quarter of an ATR the level is the band,
              and the daily 200 EMA sits under the ladder as the regime rather
              than as a row thousands of points away. */}
          {l.confluence && l.confluence.length > 0 && (
            <div className="border-t border-ring/40 px-3 py-1.5">
              {l.confluence.map((b, i) => (
                <p key={i} className="text-[10.5px] leading-[1.45] text-ink-2">
                  <span className="fig text-flip-fig">
                    {num(b.lo, l.dp)}–{num(b.hi, l.dp)}
                  </span>
                  <span className="text-ink-3"> · {b.labels.map((s) => s.toLowerCase()).join(", ")} — the level is the band, not any one row.</span>
                </p>
              ))}
            </div>
          )}
          {l.regime && (
            <p className="border-t border-ring/40 px-3 py-1.5 text-[10.5px] leading-[1.45] text-ink-2" title="The daily 200 EMA — the regime line, not a level of the day">
              <span className="qt-cap mr-1.5 text-[10px] text-ink-3">Daily</span>
              <span className={l.regime.above ? "text-call-fig" : "text-put-fig"}>{l.regime.above ? "above" : "below"} the 200-day EMA</span>
              <span className="text-ink-3"> · {l.regime.text}</span>
            </p>
          )}
          {l.note && <p className="border-t border-ring/40 px-3 py-1.5 text-[10px] leading-snug text-ink-3">{l.note}</p>}
        </>
      )}
    </Module>
  );
}
