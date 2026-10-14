"use client";

import { LOGO_TICKERS } from "@/lib/logos.generated";
import { cn } from "@/lib/cn";

/**
 * A company's logo beside its ticker (owner, 2026-10-14: "icons for every
 * ticker") — the company's own site icon, downloaded once by
 * scripts/fetch-logos.mjs and served from public/logos, so nothing is fetched
 * from anyone else at runtime and no lookup service can pin the wrong
 * company's mark on a symbol (the first cut did exactly that to SPCX).
 *
 * A ticker with no file — Berkshire's site has no icon at all; a name added
 * to the watchlist before the script is re-run — gets a letter tile the same
 * size, so the rows never shift. Square-ish under Quiet, rounded otherwise.
 */

/** Share classes are filed with a hyphen (BRK-B), whichever way the row spells them. */
const fileKey = (sym: string) => sym.toUpperCase().replace(/\./g, "-");

export const logoSrc = (sym: string): string | null => {
  const k = fileKey(sym);
  return LOGO_TICKERS.has(k) ? `/logos/${k}.webp` : null;
};

export function TickerLogo({ sym, size = 16, className }: { sym: string; size?: number; className?: string }) {
  const src = logoSrc(sym);
  return src ? (
    // eslint-disable-next-line @next/next/no-img-element -- a 1 KB static file; the image optimiser would only add a round trip
    <img
      src={src}
      alt=""
      aria-hidden
      width={size}
      height={size}
      loading="lazy"
      decoding="async"
      draggable={false}
      className={cn("shrink-0 rounded-[4px] qt:rounded-[2px]", className)}
      style={{ width: size, height: size }}
    />
  ) : (
    <span
      aria-hidden
      className={cn(
        "inline-flex shrink-0 items-center justify-center rounded-[4px] bg-surface-3 leading-none font-semibold text-ink-3 select-none qt:rounded-[2px]",
        className,
      )}
      style={{ width: size, height: size, fontSize: Math.round(size * 0.56) }}
    >
      {sym.charAt(0)}
    </span>
  );
}
