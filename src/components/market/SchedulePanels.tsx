"use client";

import type { FedPath, MacroMove, PeerSector, Print } from "@/types/market";
import { Module } from "@/components/ui/Module";
import { SectorGlyph } from "@/components/ui/SectorGlyph";
import { Skeleton } from "@/components/ui/Skeleton";
import { Tick } from "@/components/ui/Tick";
import { bp } from "@/lib/format";
import { cn } from "@/lib/cn";
import { Gap, printClock, readText } from "@/components/market/shared";

/**
 * What the day is scheduled to throw at a position, and what it leans on:
 * today's US prints read against consensus and where the Fed is priced, the
 * cross-asset moves equities answer to, and the sector peers whose reports
 * move a watchlist name before its own.
 */

/* -------------------------------------------------------------------------- */
/* Prints & the Fed                                                            */
/* -------------------------------------------------------------------------- */

export function PrintsFed({
  prints,
  fed,
  builtUtc,
  loading,
}: {
  prints: Print[];
  fed: FedPath | null;
  builtUtc: string;
  loading: boolean;
}) {
  return (
    <Module title="Prints & the Fed" sub="today, against consensus" bodyClassName="px-0 py-0">
      {loading ? (
        <Skeleton rows={5} label="Loading today's prints" />
      ) : (
        <>
          {prints.length === 0 ? (
            <Gap>No US print scored 3 or more today.</Gap>
          ) : (
            <ul className="py-1">
              {prints.map((p) => (
                <PrintRow key={`${p.et}-${p.title}-${p.consensus ?? ""}-${p.previous ?? ""}`} p={p} builtUtc={builtUtc} />
              ))}
            </ul>
          )}
          <FedBlock fed={fed} />
        </>
      )}
    </Module>
  );
}

function PrintRow({ p, builtUtc }: { p: Print; builtUtc: string }) {
  const surprised = p.read === "hot" || p.read === "cold";
  const clock = printClock(p.et, builtUtc);
  return (
    <li className="hit px-3 py-[4px]" title={p.themes.length ? p.themes.join(" · ") : undefined}>
      <div className="flex items-baseline gap-2">
        <span className="fig w-[58px] shrink-0 text-[10.5px] text-ink-2 qt:w-[66px] qt:text-[12px]">
          {clock.label}
        </span>
        <span className="min-w-0 truncate text-[11px] text-ink">{p.title}</span>
        {p.score >= 4 && (
          <span aria-label="High impact" title="High impact" className="h-[5px] w-[5px] shrink-0 -translate-y-[2px] bg-warn" />
        )}
        <span className={cn("qt-cap ml-auto w-[44px] shrink-0 text-right text-[9.5px]", p.released ? readText(p.read) : "text-ink-3")}>
          {!p.released ? "due" : p.read ?? "out"}
        </span>
      </div>
      <p className="fig mt-0.5 pl-[66px] text-[10px] text-ink-3 qt:pl-[74px]">
        {p.released && (
          <>
            act <span className={surprised ? "text-flip-fig" : "text-ink"}>{p.actual ?? "—"}</span> ·{" "}
          </>
        )}
        cons <span className="text-ink-2">{p.consensus ?? "—"}</span> · prev <span className="text-ink-2">{p.previous ?? "—"}</span>
      </p>
    </li>
  );
}

function FedBlock({ fed }: { fed: FedPath | null }) {
  if (!fed || (!fed.next && fed.path.length === 0)) {
    return <p className="border-t border-ring/40 px-3 py-2 text-[10.5px] text-ink-3">Fed path unavailable — the funds futures have not answered.</p>;
  }
  // Cuts wear the up hue, hikes the down hue — the Rates panel's convention.
  const tone = (v: number | null) => (v == null || v === 0 ? "text-ink-3" : v < 0 ? "up" : "down");
  return (
    <div className="border-t border-ring/40 px-3 py-2">
      <div className="flex flex-wrap items-baseline gap-x-2.5 gap-y-1">
        <span className="qt-cap text-[9.5px] text-ink-3">Next FOMC</span>
        <span className="fig text-[11.5px] text-ink">{fed.next ? meetingDay(fed.next) : "—"}</span>
        <Tick value={bp(fed.next_bp)} className={cn("fig text-[11.5px]", tone(fed.next_bp))} />
        <span className="text-[10px] text-ink-3">priced</span>
        {fed.next_rate != null && <span className="fig text-[10.5px] text-ink-2">→ {fed.next_rate.toFixed(2)}%</span>}
        {fed.change_bp != null && (
          <span className="ml-auto text-[10px] text-ink-3" title="How much what the next meeting prices has moved today">
            today <Tick value={bp(fed.change_bp)} className={cn("fig", tone(fed.change_bp))} />
          </span>
        )}
      </div>
      {fed.path.length > 1 && (
        <ul className="mt-1.5">
          {fed.path.map((m) => (
            <li key={m.date} className="flex items-baseline gap-2 py-[1px]">
              <span className="fig w-[52px] shrink-0 text-[10px] text-ink-3">{meetingDay(m.date)}</span>
              <span className="min-w-0 flex-1 border-b border-dotted border-ring/50" />
              <span className={cn("fig w-[44px] shrink-0 text-right text-[10px]", tone(m.bp))}>{bp(m.bp)}</span>
              <span className="fig w-[46px] shrink-0 text-right text-[10px] text-ink-2">
                {m.rate != null ? `${m.rate.toFixed(2)}%` : "—"}
              </span>
            </li>
          ))}
        </ul>
      )}
      {fed.note && <p className="mt-1.5 text-[10px] leading-relaxed text-ink-3">{fed.note}</p>}
    </div>
  );
}

/** "2026-10-28" → "Oct 28". */
function meetingDay(iso: string): string {
  const d = new Date(`${iso}T12:00:00Z`);
  return Number.isNaN(d.getTime()) ? iso : d.toLocaleDateString("en-US", { month: "short", day: "numeric", timeZone: "UTC" });
}

/* -------------------------------------------------------------------------- */
/* Cross-asset                                                                 */
/* -------------------------------------------------------------------------- */

/**
 * A yield's rise wears the down hue, as on the Rates panel — for an equity
 * book that is the losing direction. A curve spread has no good direction, so
 * it prints in ink; every price prints in the hue of its own move.
 */
function macroTone(m: MacroMove): string {
  if (m.move == null || m.move === 0) return "text-ink-3";
  if (/s\d+s|curve|spread/i.test(`${m.key} ${m.label}`)) return "text-ink";
  if (/bp\s*$/i.test(m.text)) return m.move > 0 ? "down" : "up";
  return m.move > 0 ? "up" : "down";
}

export function CrossAsset({ rows }: { rows: MacroMove[] | null }) {
  return (
    <Module title="Cross-asset" sub="what stocks lean on today" bodyClassName="px-0 py-0">
      {!rows ? (
        <Skeleton rows={5} label="Loading the cross-asset moves" />
      ) : rows.length === 0 ? (
        <Gap>No cross-asset moves yet — the quote feed has not answered.</Gap>
      ) : (
        <div className="grid grid-cols-2 gap-x-4 px-3 py-1.5">
          {rows.map((m) => (
            <div key={m.key} className="hit flex items-baseline gap-2 py-[3px]">
              <span className="min-w-0 flex-1 truncate text-[10.5px] text-ink-3">{m.label}</span>
              <Tick value={m.text} className={cn("fig shrink-0 text-right text-[11px]", macroTone(m))} />
            </div>
          ))}
        </div>
      )}
    </Module>
  );
}

/* -------------------------------------------------------------------------- */
/* Sector peers reporting                                                      */
/* -------------------------------------------------------------------------- */

const WHEN: Record<string, string> = { pre: "BMO", after: "AMC" };

function reportDay(r: { date: string; days: number }): string {
  if (r.days === 0) return "today";
  if (r.days === 1) return "tmrw";
  const d = new Date(`${r.date}T12:00:00Z`);
  return Number.isNaN(d.getTime()) ? r.date : d.toLocaleDateString("en-US", { weekday: "short", timeZone: "UTC" });
}

export function SectorPeers({ peers }: { peers: PeerSector[] | null }) {
  const live = peers?.filter((p) => p.reports.length > 0) ?? null;
  return (
    <Module title="Sector peers reporting" sub="big caps, next three sessions" bodyClassName="px-0 py-0">
      {!live ? (
        <Skeleton rows={3} label="Loading sector peers" />
      ) : live.length === 0 ? (
        <Gap>No big cap in the watchlist&apos;s sectors reports in the next three sessions.</Gap>
      ) : (
        <ul className="py-1">
          {live.map((p) => (
            <li key={p.sector} className="hit border-b border-ring/40 px-3 py-[5px] last:border-b-0">
              <div className="flex items-baseline gap-2">
                <SectorGlyph fund={p.sector} className="block shrink-0 self-center text-ink-3" />
                <span className="fig w-[38px] shrink-0 text-[10.5px] text-ink-2">{p.sector}</span>
                <span className="min-w-0 truncate text-[10px] text-ink-3">{p.label ?? ""}</span>
                {p.watch.length > 0 && (
                  <span className="ml-auto shrink-0 truncate text-[10px] text-ink-3" title="The watchlist names in this sector — a peer's report moves them first">
                    moves <span className="fig text-ink-2">{p.watch.join(" ")}</span>
                  </span>
                )}
              </div>
              <div className="mt-0.5 flex flex-wrap gap-x-3 gap-y-0.5 pl-[69px]">
                {p.reports.map((r) => (
                  <span key={`${r.sym}-${r.date}`} className="text-[10.5px]">
                    <span className="font-semibold text-ink">{r.sym}</span>{" "}
                    <span className={cn("fig", r.days === 0 ? "text-warn" : "text-ink-3")}>
                      {reportDay(r)}
                      {WHEN[r.when] ? ` ${WHEN[r.when]}` : ""}
                    </span>
                  </span>
                ))}
              </div>
            </li>
          ))}
        </ul>
      )}
    </Module>
  );
}
