"use client";

import type { VPAssets } from "@/types/terminal";
import { Popover } from "@/components/ui/Popover";
import { num } from "@/lib/format";
import { cn } from "@/lib/cn";

/**
 * The volume profile's click-through: what the session's position against
 * prior value means, and the market-profile rules the sentence is read by.
 *
 * THE FACTS WERE ALREADY COMPUTED FOR THE BRIEF — the shape, where the session
 * opened against prior value, where price trades now — and the panel drew
 * three bars and said nothing (owner, 2026-10-22). The sentence is the
 * collector's (profile.reads); this panel prints it and lays the rules
 * beside it, with the row the session is in marked.
 */

type Asset = VPAssets["assets"][string];

const RULES: { key: string; when: string; read: string }[] = [
  {
    key: "open_out_hold",
    when: "Opened outside prior value and holds there",
    read: "Acceptance beyond value: the trend-day odds rise. Trade with it; the prior POC is the first pullback target.",
  },
  {
    key: "open_out_back",
    when: "Opened outside prior value and came back in",
    read: "The move failed to hold. The 80% rule: a session that re-enters value and spends two periods there tends to traverse it to the other side.",
  },
  {
    key: "inside",
    when: "Opened inside prior value and trades inside it",
    read: "A rotation day. VAH and VAL are the edges to fade; the POC is the magnet between them. Breakouts need acceptance before they are trusted.",
  },
  {
    key: "inside_left",
    when: "Opened inside and has left value",
    read: "Wait for acceptance — two closes outside — before trusting the break; a single poke is a look above or below.",
  },
  {
    key: "shape",
    when: "The shape: P, b, D, two distributions",
    read: "P is acceptance near the highs (short covering), b near the lows (long liquidation), D balance. Two distributions make the valley between them the day's reference.",
  },
];

/** Which rule the sentence falls under, from the keyed facts. */
function here(a: Asset): string | null {
  const reads = a.reads;
  if (!reads) return null;
  const opened = reads.developing_profile_open?.vs_prev_rth_value ?? null;
  const now = reads.price_now?.vs_prev_rth_value ?? null;
  if (!opened || !now) return null;
  if (opened !== "inside_value" && now === opened) return "open_out_hold";
  if (opened !== "inside_value" && now === "inside_value") return "open_out_back";
  if (opened === "inside_value" && now === "inside_value") return "inside";
  if (opened === "inside_value") return "inside_left";
  return null;
}

export function ProfilePopover({
  asset,
  book,
  className,
  children,
}: {
  asset: Asset;
  book: string;
  className?: string;
  children: React.ReactNode;
}) {
  return (
    <Popover
      label={`What ${book}'s volume profile means`}
      title="Click for what the profile says and the rules it is read by"
      className={className}
      panel={<ProfileRead asset={asset} book={book} />}
    >
      {children}
    </Popover>
  );
}

function ProfileRead({ asset: a, book }: { asset: Asset; book: string }) {
  const rows = a.rows ?? [];
  const prev = rows.find((r) => r.key === "prev_rth");
  const mark = here(a);
  return (
    <div className="w-[min(600px,calc(100vw-24px))] px-4 py-3 text-ink">
      <div className="flex flex-wrap items-baseline gap-x-2 gap-y-1">
        <span className="qt-cap text-[10.5px] text-ink-3">What the profile means</span>
        <span className="fig text-[19px] leading-none text-ink">{book}</span>
        {a.last != null && <span className="fig text-[13px] text-ink-2">{num(a.last)}</span>}
        {prev && (
          <span className="fig ml-auto text-[11px] text-ink-3">
            prior RTH · VAL {num(prev.val, 0)} · POC {num(prev.poc, 0)} · VAH {num(prev.vah, 0)}
            {prev.shape ? ` · ${prev.shape}` : ""}
          </span>
        )}
      </div>

      <p className="mt-2 text-[12px] leading-[1.5] text-ink-2">
        {a.reads?.text ?? "No read yet: the profile needs the prior session and an opening print."}
      </p>

      <dl className="mt-3 grid grid-cols-[12px_190px_minmax(0,1fr)] gap-x-2.5 gap-y-2 text-[11.5px] leading-[1.45]">
        {RULES.map((r) => (
          <div key={r.key} className="contents">
            <dt className={cn("text-[10px]", mark === r.key ? "text-ink" : "text-transparent")} aria-hidden>
              ▸
            </dt>
            <dd className={cn(mark === r.key ? "text-ink" : "text-ink-2")}>{r.when}</dd>
            <dd className="text-ink-3">{r.read}</dd>
          </div>
        ))}
      </dl>

      <p className="mt-2.5 border-t border-ring pt-2 text-[11px] leading-[1.45] text-ink-3">
        Approximate by construction: five-minute bars with each bar&apos;s volume spread across its range, so
        zones rather than ticks. The POC is the price with the most volume, the value area where seventy
        percent of it traded. Read beside the gamma walls: a wall on yesterday&apos;s VAL is confluence.
      </p>
    </div>
  );
}
