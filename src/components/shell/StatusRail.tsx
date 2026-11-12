"use client";

import type { SourceStatus } from "@/types/terminal";
import { AskGlyph } from "@/components/ask/AskPanel";
import { Popover } from "@/components/ui/Popover";
import { openAsk } from "@/lib/ask/open";
import { age } from "@/lib/format";
import { cn } from "@/lib/cn";

/**
 * The status rail — where a terminal puts its state.
 *
 * EVERY SOURCE, ALWAYS VISIBLE, WHETHER OR NOT IT IS HEALTHY. The temptation
 * is to show only the failures and keep the rail quiet; the problem is that an
 * empty rail then means both "everything is fine" and "the status block itself
 * is broken". A row per source, green when it is fine, is the only version
 * where absence of an alarm is evidence rather than an assumption.
 *
 * The wire's row carries its own sub-count — 28 feeds behind one name — so a
 * tape running on nineteen of twenty-eight publishers says so rather than
 * looking identical to a healthy one.
 *
 * EVERY SOURCE MEANS EVERY SOURCE (review, 2026-10-13). The rail named six of
 * the sixteen, so when iShares changed its download URL the Index movers feed
 * died without the rail ever mentioning it — the exact failure this rail
 * exists to make impossible. It now lists whatever the collector reports, in
 * reading order, and stays one line by being compact about health: a healthy
 * source is a dot and its name (the detail is in its hover), and anything
 * down or serving STALE bytes — a cached copy shown because the upstream
 * failed — opens up with its age and its reason, red for down, amber for
 * stale. A dead feed can no longer look like a quiet one.
 *
 * ONE LINE AT EVERY WIDTH. Eighteen names needed about 1,600px, so below that
 * the healthy ones folded into a single "17 live". There are twenty-four now and
 * the fold never fired at 1920, where the rail wrapped to two lines of green on
 * every tab (2026-11-05). So it folds at every width: the count is a button, the
 * whole list with each source's age opens from it, and only what is down, stale
 * or missing feeds keeps its own entry. A problem is never folded away, and the
 * count is still evidence: "24 of 24" cannot be mistaken for an empty rail.
 *
 * THE WIRE'S COUNT OPENS ITS FEEDS (owner, 2026-11-06: "can we make it clickable
 * like the sources live next to it"). "38/39" said one publisher was missing and
 * not which, or why; its row in the list above cannot either, being one name for
 * forty feeds.
 */

/** Reading order; anything the collector adds later lands after these. */
const ORDER = [
  "quotes", "wire", "gex", "ranges", "profiles", "sectors", "constituents", "calendar",
  "earnings", "fed", "auctions", "rates", "context", "scanner", "scan_live", "scan_news", "scan_sec",
  "pool", "options",
];

export function StatusRail({
  status,
  ages,
  feeds,
  pollSec,
  lastPoll,
}: {
  status: Record<string, SourceStatus>;
  ages: Record<string, number>;
  /** The wire's publishers, one row each. */
  feeds?: SourceStatus[];
  pollSec: number;
  lastPoll: Date | null;
}) {
  const names = [
    ...ORDER.filter((n) => n in status),
    ...Object.keys(status).filter((n) => !ORDER.includes(n)).sort(),
  ];

  const healthy = names.filter((n) => status[n].ok && status[n].source !== "stale");
  const trouble = names.filter((n) => !healthy.includes(n));
  // The wire is forty feeds behind one name. Always on the rail, since it is the way
  // into the list: a healthy "39/39" is as much evidence as "24 of 24" beside it.
  const wireCount = /^(\d+)\/(\d+)/.exec(status.wire?.notes?.[0] ?? "");
  const wireShort = wireCount != null && wireCount[1] !== wireCount[2];

  return (
    <footer className="flex items-center gap-x-3 border-t border-ring bg-surface/40 px-3 py-1.5 whitespace-nowrap qt:gap-x-4 qt:bg-transparent qt:px-6 qt:py-1.5">
      <Popover
        label="Data sources"
        title="Every source the terminal reads — click for the list"
        className="hit flex shrink-0 items-center gap-1.5 rounded-[3px] px-1 py-0.5 -ml-1"
        panel={<SourceList names={names} status={status} ages={ages} />}
      >
        <span className={cn("h-[6px] w-[6px] rounded-full", trouble.length ? "bg-warn" : "bg-call")} aria-hidden />
        <span className="fig text-[9.5px] tracking-wide text-ink-3 uppercase qt:text-[10.5px]">
          {healthy.length} of {names.length} sources live
        </span>
      </Popover>
      {wireCount && (
        <Popover
          label="Wire feeds"
          title={[status.wire.error, "Click for every feed"].filter(Boolean).join(" — ")}
          className="hit flex shrink-0 items-center gap-1.5 rounded-[3px] px-1 py-0.5"
          panel={<FeedList feeds={feeds ?? []} />}
        >
          <span className={cn("h-[6px] w-[6px] rounded-full", wireShort ? "bg-warn" : "bg-call")} aria-hidden />
          <span className="fig text-[9.5px] tracking-wide text-ink-3 uppercase qt:text-[10.5px]">
            wire {status.wire.notes?.[0]}
          </span>
        </Popover>
      )}
      <div className="flex min-w-0 items-center gap-x-3 overflow-hidden">
        {trouble.map((n) => {
          const s = status[n];
          const a = ages[n];
          const stale = s.ok && s.source === "stale";
          return (
            <div key={n} className="flex min-w-0 items-center gap-1.5" title={s.error ?? undefined}>
              <span className={cn("h-[6px] w-[6px] shrink-0 rounded-full", stale ? "bg-warn" : "bg-err")} aria-hidden />
              <span className={cn("fig text-[9.5px] tracking-wide uppercase qt:text-[10.5px]", stale ? "text-warn" : "text-err")}>
                {n.replace(/_/g, " ")}
              </span>
              <span className={cn("fig text-[9.5px] qt:text-[10.5px]", stale ? "text-warn" : "text-err")}>
                {stale ? `stale${s.age_min != null ? ` ${age(s.age_min)}` : ""}` : a !== undefined ? age(a) : "never"}
              </span>
              {s.error && (
                <span className={cn("fig max-w-[240px] truncate text-[9.5px] qt:text-[10.5px]", stale ? "text-warn" : "text-err")}>
                  {s.error}
                </span>
              )}
            </div>
          );
        })}
      </div>

      <div className="ml-auto flex items-center gap-3">
        <span className="fig text-[9px] text-ink-3 qt:text-[10px]">
          poll {pollSec}s
          {lastPoll ? ` · ${lastPoll.toLocaleTimeString("en-US", { hour12: false })}` : ""}
        </span>
        <span className="fig text-[9px] text-ink-3 qt:text-[10px]" title="This terminal is for one desk only. Yahoo quotes and publisher RSS are personal-use; neither may be redistributed.">
          PERSONAL USE
        </span>
        {/* The assistant's door — on the rail rather than in the header,
            whose strip already gives up instruments for want of width. */}
        <button
          type="button"
          onClick={openAsk}
          title="Ask Hermes to explain anything on the terminal"
          className="hit flex items-center gap-1.5 rounded-[4px] border border-ring-2 bg-surface-2 px-2.5 py-1 text-ink-2 hover:border-ink-4 hover:bg-surface-3 hover:text-ink"
        >
          <AskGlyph />
          <span className="text-[11px] leading-none font-semibold">Ask Hermes</span>
        </button>
      </div>
    </footer>
  );
}

/** Every feed on the wire, what is wrong at the top, with how many stories each is carrying. */
function FeedList({ feeds }: { feeds: SourceStatus[] }) {
  const rank = (f: SourceStatus) => (!f.ok ? 0 : f.source === "stale" ? 1 : 2);
  const rows = [...feeds].sort((a, b) => rank(a) - rank(b) || a.name.localeCompare(b.name));
  const live = feeds.filter((f) => rank(f) === 2).length;
  return (
    <div className="max-h-[70vh] w-[560px] max-w-[calc(100vw-16px)] overflow-y-auto rounded-[4px] border border-ring-2 bg-surface p-3 shadow-[0_8px_30px_rgba(0,0,0,0.5)]">
      <p className="qt-cap mb-2 text-[10px] text-ink-3">
        Wire feeds · {live} of {feeds.length} live
      </p>
      {rows.length === 0 ? (
        <p className="py-1 text-[11px] text-ink-3">The feed list has not loaded yet.</p>
      ) : (
        <ul className="flex flex-col">
          {rows.map((f) => {
            const stale = f.ok && f.source === "stale";
            return (
              <li key={f.name} className="border-b border-ring/40 py-1 last:border-b-0">
                <div className="flex items-baseline gap-2">
                  <span
                    className={cn("h-[6px] w-[6px] shrink-0 -translate-y-[1px] rounded-full", !f.ok ? "bg-err" : stale ? "bg-warn" : "bg-call")}
                    aria-hidden
                  />
                  <span className="w-[230px] shrink-0 truncate text-[11px] text-ink-2">{f.name}</span>
                  <span className={cn("fig w-[44px] shrink-0 text-[10.5px]", !f.ok ? "text-err" : stale ? "text-warn" : "text-ink-3")}>
                    {!f.ok ? "down" : stale ? "stale" : "ok"}
                  </span>
                  <span className="fig w-[72px] shrink-0 text-right text-[10.5px] whitespace-nowrap text-ink-3">
                    {f.ok ? `${f.items} ${f.items === 1 ? "story" : "stories"}` : ""}
                  </span>
                  {/* Wrapped, not truncated: the reason is why the list was opened. */}
                  {f.error && <span className="min-w-0 flex-1 text-[10.5px] text-ink-3">{f.error}</span>}
                </div>
              </li>
            );
          })}
        </ul>
      )}
    </div>
  );
}

/** Every source, in reading order, with its state, its age and what it holds. */
function SourceList({
  names,
  status,
  ages,
}: {
  names: string[];
  status: Record<string, SourceStatus>;
  ages: Record<string, number>;
}) {
  return (
    <div className="max-h-[70vh] w-[520px] max-w-[calc(100vw-16px)] overflow-y-auto rounded-[4px] border border-ring-2 bg-surface p-3 shadow-[0_8px_30px_rgba(0,0,0,0.5)]">
      <p className="qt-cap mb-2 text-[10px] text-ink-3">Data sources</p>
      <ul className="flex flex-col">
        {names.map((n) => {
          const s = status[n];
          const stale = s.ok && s.source === "stale";
          const a = ages[n];
          const note = s.error ?? s.notes?.[0] ?? null;
          return (
            <li key={n} className="border-b border-ring/40 py-1 last:border-b-0">
              <div className="flex items-baseline gap-2">
                <span
                  className={cn("h-[6px] w-[6px] shrink-0 -translate-y-[1px] rounded-full", !s.ok ? "bg-err" : stale ? "bg-warn" : "bg-call")}
                  aria-hidden
                />
                <span className="fig w-[120px] shrink-0 text-[11px] text-ink-2 uppercase">{n.replace(/_/g, " ")}</span>
                <span className={cn("fig w-[64px] shrink-0 text-[10.5px]", !s.ok ? "text-err" : stale ? "text-warn" : "text-ink-3")}>
                  {!s.ok ? "down" : stale ? "stale" : "ok"}
                </span>
                <span className="fig w-[44px] shrink-0 text-right text-[10.5px] text-ink-3">{a !== undefined ? age(a) : "never"}</span>
                {note && <span className="min-w-0 flex-1 truncate text-[10.5px] text-ink-3">{note}</span>}
              </div>
            </li>
          );
        })}
      </ul>
    </div>
  );
}
