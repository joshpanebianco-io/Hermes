"use client";

import { useMemo } from "react";
import type { Desk, Impact, WireItem } from "@/types/terminal";
import { Module } from "@/components/ui/Module";
import { Skeleton } from "@/components/ui/Skeleton";
import { Ago } from "@/components/ui/Ago";
import { cn } from "@/lib/cn";
import { manyOf, oneOf, usePersisted } from "@/lib/usePersisted";
import { segItem } from "@/lib/seg";

/**
 * The wire — every desk's headlines on one tape.
 *
 * A LIST, NOT A CRAWL. GEXYGEN's WireTicker scrolls its headlines past because
 * it is a one-line strip inside a dashboard about something else. Here the
 * wire IS the product, it has a full column, and a moving target you cannot
 * scan or click without chasing is the wrong answer at that size. It updates
 * in place; new items slide in so an insertion above the line you are reading
 * announces itself instead of silently shifting the page.
 *
 * THE DESK RAIL CARRIES IDENTITY, THE TEXT STAYS NEUTRAL. Each item has a 3px
 * coloured rail on its left and white-ish headline text. Colouring the
 * headline itself would collide with the data palette, where green and red
 * mean up and down — a green headline must never read as "this is bullish".
 *
 * EVERY LINE NAMES ITS PUBLISHER AND LINKS BACK. That is both the decent thing
 * and what keeps a personal aggregator defensible: the title is the thinnest
 * copyright there is and the link sends the reader to the outlet that paid for
 * the reporting.
 */

const DESKS: { key: Desk | "all"; label: string; hue: string }[] = [
  { key: "all", label: "All", hue: "var(--ink-3)" },
  { key: "markets", label: "Markets", hue: "var(--desk-markets)" },
  { key: "corp", label: "Companies", hue: "var(--desk-corp)" },
  { key: "macro", label: "Macro", hue: "var(--desk-macro)" },
  { key: "policy", label: "Policy", hue: "var(--desk-policy)" },
  { key: "geo", label: "Geopolitics", hue: "var(--desk-geo)" },
  { key: "energy", label: "Energy", hue: "var(--desk-energy)" },
];

const HUE: Record<Desk, string> = {
  markets: "var(--desk-markets)",
  corp: "var(--desk-corp)",
  macro: "var(--desk-macro)",
  policy: "var(--desk-policy)",
  geo: "var(--desk-geo)",
  energy: "var(--desk-energy)",
};

/**
 * Impact, as three TOGGLES rather than a cumulative threshold.
 *
 * "HIGH" STILL MEANS ONLY HIGH. A "high and above" reading would make the top
 * filter identical to the unfiltered tape whenever nothing big is happening,
 * which is precisely when you would be checking it. Switching to HIGH either
 * leaves you with six lines or with none, and both are answers.
 *
 * BUT THE TIERS COMBINE, because you say so, not because the filter assumes it
 * (owner, 2026-09-22). They used to be one-at-a-time, and the tape most worth
 * reading — everything that matters, none of the context — is HIGH and MED
 * together, which one-at-a-time could not show. Each tier is its own switch;
 * none lit is the whole tape, which is what ALL means and what it resets to.
 * Lighting all three is the same tape, so it collapses back to ALL rather than
 * leaving two different-looking states that mean one thing.
 */
const IMPACTS: { key: Impact | "all"; label: string; hue: string; title: string }[] = [
  { key: "all", label: "All", hue: "var(--ink-3)", title: "Every headline on the tape — clears the tiers" },
  {
    key: "high",
    label: "High",
    hue: "var(--err)",
    title: "A released number or a decided event — reprices on the spot. Combines with the other tiers",
  },
  {
    key: "medium",
    label: "Med",
    hue: "var(--warn)",
    title: "Moves things over a session: officials, policy, deals, supply. Combines with the other tiers",
  },
  { key: "low", label: "Low", hue: "var(--ink-4)", title: "Context. Combines with the other tiers" },
];

/** How many tiers there are — lighting every one of them is just ALL. */
const TIERS = IMPACTS.length - 1;

export function Wire({
  items,
  ageMin,
  error,
}: {
  items: WireItem[];
  ageMin?: number | null;
  error?: string | null;
}) {
  const [desk, setDesk] = usePersisted<Desk | "all">(
    "wire.desk",
    "all",
    oneOf("all", "markets", "corp", "macro", "policy", "geo", "energy"),
  );
  // The tiers that are lit. EMPTY IS THE WHOLE TAPE — that is what ALL is. A
  // build that stored the old single string is rejected by `manyOf` and starts
  // on ALL once, which is the right place to land.
  const [impacts, setImpacts] = usePersisted<Impact[]>(
    "wire.impact",
    [],
    manyOf("high", "medium", "low"),
  );
  const toggleImpact = (k: Impact | "all") =>
    setImpacts((prev) => {
      if (k === "all") return [];
      const next = prev.includes(k) ? prev.filter((x) => x !== k) : [...prev, k];
      return next.length === TIERS ? [] : next;
    });

  // Counts are computed against the OTHER filter, so each row of chips shows
  // what you would actually get by clicking it rather than a total that goes
  // stale the moment the other filter moves.
  const deskCounts = useMemo(() => {
    const pool = impacts.length ? items.filter((i) => impacts.includes(i.impact)) : items;
    const c: Record<string, number> = { all: pool.length };
    for (const i of pool) c[i.category] = (c[i.category] ?? 0) + 1;
    return c;
  }, [items, impacts]);

  const impactCounts = useMemo(() => {
    const pool = desk === "all" ? items : items.filter((i) => i.category === desk);
    const c: Record<string, number> = { all: pool.length };
    for (const i of pool) c[i.impact] = (c[i.impact] ?? 0) + 1;
    return c;
  }, [items, desk]);

  const shown = useMemo(() => {
    let list = desk === "all" ? items : items.filter((i) => i.category === desk);
    if (impacts.length) list = list.filter((i) => impacts.includes(i.impact));
    return list.slice(0, 150);
  }, [items, desk, impacts]);

  return (
    <Module
      title="Wire"
      sub={`${items.length} stories`}
      ageMin={ageMin}
      error={error}
      className="min-h-0 flex-1"
      bodyClassName="min-h-0 overflow-y-auto"
      right={
        <div className="seg">
          {IMPACTS.map((im) => {
            const on = im.key === "all" ? impacts.length === 0 : impacts.includes(im.key);
            const n = impactCounts[im.key] ?? 0;
            return (
              <button
                key={im.key}
                type="button"
                onClick={() => toggleImpact(im.key)}
                aria-pressed={on}
                title={im.title}
                {...segItem(on, { hue: im.hue, pct: 26 })}
              >
                {im.label}
                <span className="seg-n">{n}</span>
              </button>
            );
          })}
        </div>
      }
    >
      <div className="seg seg-bare sticky top-0 z-10 -mx-px flex border-b border-ring/60 bg-surface px-3 py-1.5 qt:bg-bg qt:pb-2.5">
        {DESKS.map((d) => {
          const on = desk === d.key;
          const n = deskCounts[d.key] ?? 0;
          return (
            <button
              key={d.key}
              type="button"
              onClick={() => setDesk(d.key)}
              {...segItem(on, { hue: d.hue, pct: 22, className: "text-[10px] py-0.5" })}
            >
              {d.key !== "all" && <span className="seg-dot" />}
              {d.label}
              <span className="seg-n">{n}</span>
            </button>
          );
        })}
      </div>

      {shown.length === 0 ? (
        items.length === 0 && ageMin == null && !error ? (
          <Skeleton rows={10} label="Loading the wire" />
        ) : (
          <p className="px-3 py-6 text-center text-[11px] text-ink-3">
            {items.length === 0
              ? "No headlines — the collector polls the wire every two minutes."
              : "Nothing on this desk right now."}
          </p>
        )
      ) : (
        <ul className="divide-y divide-ring/40">
          {shown.map((h) => (
            <Item key={`${h.url}-${h.ts ?? 0}`} h={h} />
          ))}
        </ul>
      )}
    </Module>
  );
}

function Item({ h }: { h: WireItem }) {
  return (
    <li className="wire-in">
      <a
        href={h.url}
        target="_blank"
        rel="noreferrer noopener"
        className="hit relative flex min-w-0 flex-col gap-0.5 py-1.5 pr-3 pl-3.5"
      >
        <span
          aria-hidden
          className="absolute inset-y-0 left-0 w-[3px]"
          style={{ background: HUE[h.category] }}
        />
        <div className="flex min-w-0 items-baseline gap-1.5">
          {/*
           * ONLY HIGH AND MEDIUM CARRY A MARK. Low is most of the tape, and a
           * badge on every line is a badge on no line — the absence of a mark
           * is what makes the two that have one findable.
           */}
          {h.impact !== "low" && (
            <span
              className={cn(
                "fig qt-pill shrink-0 rounded-sm px-1 text-[9px] leading-[13px]",
                h.impact === "high" ? "bg-err/25 text-err" : "bg-warn/20 text-warn",
              )}
              title={h.impact === "high" ? "High impact" : "Medium impact"}
            >
              {h.impact === "high" ? "H" : "M"}
            </span>
          )}
          <span className="min-w-0 flex-1 text-[12px] leading-[1.35] text-ink">{h.title}</span>
          <Ago utc={h.utc} className="fig shrink-0 text-[9.5px] text-ink-3 tabular-nums" />
        </div>
        {h.summary && (
          <p className="line-clamp-2 pr-6 text-[10.5px] leading-[1.4] text-ink-3">{h.summary}</p>
        )}
        <div className="flex items-center gap-1.5 text-[9.5px] text-ink-3">
          <span className="text-ink-3">{h.publisher}</span>
          {h.also && h.also.length > 0 && (
            <span title={`Also filed by ${h.also.join(", ")}`}>+{h.also.length}</span>
          )}
          <span aria-hidden>·</span>
          <span className="uppercase">{h.category}</span>
        </div>
      </a>
    </li>
  );
}
