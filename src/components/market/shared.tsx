import type { Conviction, Fuel, OptionsFlow, Print, Side } from "@/types/market";
import { compact } from "@/lib/format";
import { cn } from "@/lib/cn";

/**
 * The conviction board's small parts, shared by the Market tab and the Game
 * plan so a vote, a side and a split read the same wherever they print.
 *
 * HUE IS SPOKEN FOR. A side or a direction wears the call or put figure tier;
 * everything else — a grade, a state, a count — is carried by value (ink-1 to
 * ink-3) and by the word. A surprise in a print is amber either way, as on the
 * calendar, because a hot CPI and a hot payrolls mean opposite things.
 */

export const sideText = (s: Side | "neutral" | null | undefined) =>
  s === "long" ? "text-call-fig" : s === "short" ? "text-put-fig" : "text-ink-3";

export const sideBg = (s: Side | "neutral" | null | undefined) =>
  s === "long" ? "bg-call-fig" : s === "short" ? "bg-put-fig" : "bg-ink-4";

export const voteGlyph = (v: Side | "neutral" | null | undefined) => (v === "long" ? "▲" : v === "short" ? "▼" : "–");

export const biasWord = (b: Side | null | undefined) => (b === "long" ? "▲ Long" : b === "short" ? "▼ Short" : "No bias");

/** Every vote, one per line — the hover on any conviction summary. */
export function votesTip(c: Conviction): string {
  if (c.votes.length === 0) return "No signal has voted yet.";
  return c.votes.map((v) => `${voteGlyph(v.vote)} ${v.label}: ${v.value} — ${v.note}`).join("\n");
}

/** The grade's ink: strong carries the side's hue, weak and none step back. */
export function gradeText(c: Conviction): string {
  if (c.grade === "strong") return sideText(c.bias);
  return c.grade === "moderate" ? "text-ink-2" : "text-ink-3";
}

/**
 * A flat split bar — agree, against and neutral; sectors up and down; calls and
 * puts. Each part is its share of `total`, on the terminal's track grey, with a
 * hairline between parts. No rounded ends: Quiet's bars are flat.
 */
export function SplitBar({
  parts,
  total,
  className,
  label,
}: {
  parts: Array<{ n: number; cls: string }>;
  total: number;
  className?: string;
  label?: string;
}) {
  const t = Math.max(1, total);
  return (
    <span
      className={cn("flex h-[4px] w-full gap-px bg-[var(--qt-track,var(--surface-3))]", className)}
      role="img"
      aria-label={label}
    >
      {parts.map((p, i) =>
        p.n > 0 ? <span key={i} className={cn("h-full", p.cls)} style={{ width: `${(p.n / t) * 100}%` }} /> : null,
      )}
    </span>
  );
}

/** The agree / against / neutral split of a conviction count. */
export function ConvictionBar({ c, className }: { c: Conviction; className?: string }) {
  const agree = c.bias ? sideBg(c.bias) : "bg-ink-3";
  const against = c.bias === "long" ? "bg-put-fig" : c.bias === "short" ? "bg-call-fig" : "bg-ink-3";
  return (
    <SplitBar
      className={className}
      total={c.total}
      label={`${c.agree} agree, ${c.against} against, ${c.neutral} neutral`}
      parts={[
        { n: c.agree, cls: agree },
        { n: c.against, cls: cn(against, "opacity-60") },
        { n: c.neutral, cls: "bg-ink-4 opacity-50" },
      ]}
    />
  );
}

/** Room is the good state for a new entry; stretched is the one to respect. */
export const stateText = (s: Fuel["state"]) =>
  s === "stretched" ? "text-warn" : s === "room" ? "text-ink-2" : "text-ink-3";

/** A surprise is amber whichever way it went — the calendar's rule. */
export const readText = (r: Print["read"]) => (r === "hot" || r === "cold" ? "text-flip-fig" : "text-ink-3");

/**
 * A print's ET time read against the context's build time. The calendar
 * writes "08:30" or "Wed 08:30"; a weekday that is today's is dropped from the
 * label, and `until` (minutes) is set only for a time still ahead today. A
 * label the parser does not recognise is printed as given.
 */
export function printClock(et: string, builtUtc: string): { label: string; until: number | null } {
  const m = et.trim().match(/^(?:([A-Za-z]{3})\s+)?(\d{1,2}):(\d{2})\s*(AM|PM)?$/i);
  const t = Date.parse(builtUtc);
  if (!m || Number.isNaN(t)) return { label: et, until: null };
  const parts = new Intl.DateTimeFormat("en-US", {
    timeZone: "America/New_York",
    weekday: "short",
    hour: "2-digit",
    minute: "2-digit",
    hourCycle: "h23",
  }).formatToParts(new Date(t));
  const get = (k: string) => parts.find((p) => p.type === k)?.value ?? "";
  const today = !m[1] || m[1].toLowerCase() === get("weekday").toLowerCase();
  const time = `${m[2].padStart(2, "0")}:${m[3]}${m[4] ? ` ${m[4].toUpperCase()}` : ""}`;
  if (!today) return { label: `${m[1]} ${time}`, until: null };
  let h = Number(m[2]);
  const ap = m[4]?.toUpperCase();
  if (ap === "PM" && h < 12) h += 12;
  if (ap === "AM" && h === 12) h = 0;
  const now = Number(get("hour")) * 60 + Number(get("minute"));
  const d = h * 60 + Number(m[3]) - now;
  return { label: time, until: Number.isFinite(d) && d > 0 ? d : null };
}

/** A strike as the chain prints it: 580, 347.5 — never 580.00. */
export function strike(x: number): string {
  return Number.isInteger(x) ? String(x) : String(Number(x.toFixed(2)));
}

/** "2026-10-17" → "10-17", the way the chain's expiries print. */
export const shortExpiry = (iso: string) => (/^\d{4}-\d{2}-\d{2}$/.test(iso) ? iso.slice(5) : iso);

/** Which way today's option volume leans, in the hue of the side it favours. */
export function leanText(l: OptionsFlow["lean"]): string {
  return l === "calls" ? "text-call-fig" : l === "puts" ? "text-put-fig" : "text-ink-3";
}

/** "P/C 0.84 · calls", for a one-line read of a chain's flow. */
export function FlowLine({ f, className }: { f: OptionsFlow; className?: string }) {
  const top = f.top[0];
  return (
    <span className={cn("inline-flex min-w-0 flex-wrap items-baseline gap-x-1.5", className)}>
      <span className="text-ink-3">P/C</span>
      <span className="fig text-ink">{f.pc_vol != null ? f.pc_vol.toFixed(2) : "—"}</span>
      {f.lean && <span className={cn("qt-cap text-[10px]", leanText(f.lean))}>{f.lean}</span>}
      {top && (
        <>
          <span className="text-ink-4">·</span>
          <span
            className="fig text-ink-2"
            title={`Most traded strike today: ${strike(top.strike)}${top.right} expiring ${top.expiry} — ${top.volume.toLocaleString("en-US")} contracts against ${top.oi.toLocaleString("en-US")} open`}
          >
            <span className={top.right === "C" ? "text-call-fig" : "text-put-fig"}>
              {strike(top.strike)}
              {top.right}
            </span>{" "}
            {shortExpiry(top.expiry)} <span className="text-ink-3">{compact(top.volume)}</span>
          </span>
        </>
      )}
    </span>
  );
}

/** What a panel says when its block is empty — never a blank, never a guess. */
export function Gap({ children }: { children: React.ReactNode }) {
  return <p className="px-3 py-4 text-center text-[11px] leading-relaxed text-ink-3">{children}</p>;
}

/** A small caps label over a figure, for the panels' summary rows. */
export function Stat({
  label,
  children,
  title,
  className,
}: {
  label: string;
  children: React.ReactNode;
  title?: string;
  className?: string;
}) {
  return (
    <div className={cn("min-w-0", className)} title={title}>
      <p className="qt-cap mb-1 text-[10px] text-ink-3">{label}</p>
      {children}
    </div>
  );
}
