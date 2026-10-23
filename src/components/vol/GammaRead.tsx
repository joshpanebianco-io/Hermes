"use client";

import type { ExpiryState, GexAsset } from "@/types/terminal";
import { Popover } from "@/components/ui/Popover";
import { num } from "@/lib/format";
import { cn } from "@/lib/cn";

/**
 * The gamma panel's click-through: the regime, spot against the flip in points
 * and in the book's own one-sigma day, the nearest walls, OpEx week — and the
 * dealer-flow rules each of those is read by.
 *
 * WHY WORDS UNDER A LADDER THAT ALREADY SHOWS THE LEVELS (owner, 2026-10-22).
 * The seven prices say where hedging turns; they do not say what to do at
 * them, and that differs by regime: in positive gamma the first wall holds
 * more often than not and the fade works, in negative gamma it gives and the
 * break runs. The one sentence the panel prints and this long form are built
 * here from the asset the collector serves, the implied day beside it and
 * the expiry block — nothing is fetched or estimated in the browser.
 */

/** What is read from the asset: regime, the flip, the first wall each side. */
function facts(a: GexAsset) {
  const spot = a.spot ?? null;
  const flip = a.levels.find((l) => l.side === "flip")?.price ?? null;
  const above = a.levels.filter((l) => l.side === "call" && spot != null && l.price > spot).sort((x, y) => x.price - y.price)[0] ?? null;
  const below = a.levels.filter((l) => l.side === "put" && spot != null && l.price < spot).sort((x, y) => y.price - x.price)[0] ?? null;
  const regime = a.regime === "POS" || a.regime === "NEG" ? a.regime : null;
  return { spot, flip, above, below, regime };
}

/** The one line the panel prints under the ladder. */
export function gammaLine(a: GexAsset, sigma: number | null | undefined, expiry?: ExpiryState | null): string | null {
  const { spot, flip, above, below, regime } = facts(a);
  if (spot == null || !regime) return null;
  const bits: string[] = [];
  if (flip != null) {
    const d = spot - flip;
    const sig = sigma ? ` (${(Math.abs(d) / sigma).toFixed(1)}σ)` : "";
    bits.push(`Spot ${num(Math.abs(d), 0)} ${d >= 0 ? "above" : "below"} the flip${sig}`);
  }
  bits.push(
    regime === "POS"
      ? "positive gamma: dealers damp moves, ranges hold, fade into the walls"
      : "negative gamma: dealers chase moves, breaks run, trade the break not the fade",
  );
  if (above && below) {
    bits.push(`walls ${num(below.price, 0)} under and ${num(above.price, 0)} over`);
  }
  if (expiry?.opex_week) bits.push("OpEx week: the walls are at their heaviest into Friday");
  const s = bits.join(" · ");
  return s.charAt(0).toUpperCase() + s.slice(1) + ".";
}

const RULES: { key: "POS" | "NEG" | "flip" | "walls" | "em" | "opex"; when: string; read: string }[] = [
  {
    key: "POS",
    when: "Positive gamma",
    read: "Dealers are long gamma: they sell rallies and buy dips to stay hedged. Ranges hold, the first wall holds more often than not, breakouts stall. Fade into the walls; targets inside the expected move.",
  },
  {
    key: "NEG",
    when: "Negative gamma",
    read: "Dealers are short gamma: they buy strength and sell weakness. Ranges extend, walls give, breaks run. Trade the break, not the fade; stops wider, size smaller.",
  },
  {
    key: "flip",
    when: "Spot against the flip",
    read: "The flip is the price where hedging turns. Crossing it changes the day's character more than any other level: above it the positive rules, below it the negative ones. A flip within half a sigma is in play today.",
  },
  {
    key: "walls",
    when: "The walls",
    read: "Three chevrons is the heaviest. A wall on a profile level or the expected-move edge is confluence; a wall the session has already traded through is spent until the map is rebuilt.",
  },
  {
    key: "em",
    when: "The expected move",
    read: "Inside the band is the base case; the edge plus a wall is where a first target lands and where a fade is taken in positive gamma. In negative gamma the edge is where a break accelerates.",
  },
  {
    key: "opex",
    when: "OpEx week",
    read: "The near book is at its largest and price pins to the walls into Friday; the Monday after, the same strikes carry almost nothing and the map is rebuilt around the next cycle.",
  },
];

export function GammaPopover({
  asset,
  book,
  sigma,
  expiry,
  className,
  children,
}: {
  asset: GexAsset;
  book: string;
  sigma: number | null | undefined;
  expiry?: ExpiryState | null;
  className?: string;
  children: React.ReactNode;
}) {
  return (
    <Popover
      label={`What ${book}'s gamma levels mean`}
      title="Click for what the regime, the flip and the walls mean for the session"
      className={className}
      panel={<GammaRead asset={asset} book={book} sigma={sigma} expiry={expiry} />}
    >
      {children}
    </Popover>
  );
}

function GammaRead({
  asset: a,
  book,
  sigma,
  expiry,
}: {
  asset: GexAsset;
  book: string;
  sigma: number | null | undefined;
  expiry?: ExpiryState | null;
}) {
  const { spot, flip, above, below, regime } = facts(a);
  const line = gammaLine(a, sigma, expiry);
  const marked = new Set<string>();
  if (regime) marked.add(regime);
  if (flip != null && spot != null && sigma && Math.abs(spot - flip) / sigma <= 0.5) marked.add("flip");
  if (expiry?.opex_week) marked.add("opex");
  return (
    <div className="w-[min(620px,calc(100vw-24px))] px-4 py-3 text-ink">
      <div className="flex flex-wrap items-baseline gap-x-2 gap-y-1">
        <span className="qt-cap text-[10.5px] text-ink-3">What the gamma levels mean</span>
        <span className="fig text-[19px] leading-none text-ink">{book}</span>
        {spot != null && <span className="fig text-[13px] text-ink-2">{num(spot)}</span>}
        {regime && (
          <span className={cn("qt-cap text-[10.5px]", regime === "POS" ? "text-call-fig" : "text-put-fig")}>
            {regime === "POS" ? "positive γ" : "negative γ"}
          </span>
        )}
        <span className="fig ml-auto text-[11px] text-ink-3">0DTE book · GEXYGEN</span>
      </div>

      <p className="mt-2 text-[12px] leading-[1.5] text-ink-2">{line ?? "No regime or flip to read yet."}</p>

      <dl className="mt-2.5 grid grid-cols-[auto_auto_minmax(0,1fr)] gap-x-3 gap-y-1 text-[11.5px]">
        {flip != null && (
          <Fact k="Flip" v={num(flip, 0)} note={spot != null ? `${num(Math.abs(spot - flip), 0)} ${spot >= flip ? "below spot" : "above spot"}${sigma ? ` · ${(Math.abs(spot - flip) / sigma).toFixed(1)}σ` : ""}` : undefined} />
        )}
        {above && <Fact k="Wall over" v={num(above.price, 0)} note={`${above.label}${spot != null ? ` · ${num(above.price - spot, 0)} away` : ""}`} />}
        {below && <Fact k="Wall under" v={num(below.price, 0)} note={`${below.label}${spot != null ? ` · ${num(spot - below.price, 0)} away` : ""}`} />}
        {sigma != null && <Fact k="One-sigma day" v={`±${num(sigma, 0)}`} note="from the book's own index (Volatility panel)" />}
      </dl>

      <dl className="mt-3 grid grid-cols-[12px_150px_minmax(0,1fr)] gap-x-2.5 gap-y-2 text-[11.5px] leading-[1.45]">
        {RULES.map((r) => (
          <div key={r.key} className="contents">
            <dt className={cn("text-[10px]", marked.has(r.key) ? "text-ink" : "text-transparent")} aria-hidden>
              ▸
            </dt>
            <dd className={cn(marked.has(r.key) ? "text-ink" : "text-ink-2")}>{r.when}</dd>
            <dd className="text-ink-3">{r.read}</dd>
          </div>
        ))}
      </dl>

      <p className="mt-2.5 border-t border-ring pt-2 text-[11px] leading-[1.45] text-ink-3">
        Rules of thumb for the session, not a signal. Open interest clears once a day, so outside New York
        the map is the US close&apos;s positioning and the hedging flow behind it is lighter: decisive in New
        York, a reference elsewhere.
      </p>
    </div>
  );
}

function Fact({ k, v, note }: { k: string; v: string; note?: string }) {
  return (
    <div className="contents">
      <dt className="qt-cap text-[10px] text-ink-3">{k}</dt>
      <dd className="fig text-[12px] text-ink">{v}</dd>
      <dd className="text-[11px] text-ink-3">{note ?? ""}</dd>
    </div>
  );
}
