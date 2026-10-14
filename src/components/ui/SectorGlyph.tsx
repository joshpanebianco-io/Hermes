/**
 * The eleven sector funds' glyphs (owner, 2026-10-14: "the same icons we did
 * in gexygen"). Copied from GEXYGEN's set, path for path, never imported:
 * the two screens sit side by side and a sector should wear the same mark on
 * both, but this terminal runs without GEXYGEN on the disk.
 *
 * DRAWN, NOT DOWNLOADED. Every Select Sector SPDR carries the same State
 * Street mark — scripts/fetch-logos.mjs gives all eleven that one icon — so a
 * fetched logo says nothing about the sector. A chip, a bank or a flame does.
 *
 * A 24-grid of 1.6px round strokes in currentColor, so a glyph takes its
 * row's ink and brightens with it.
 */

const GLYPH: Record<string, React.ReactNode> = {
  // Technology — a chip and its pins.
  XLK: (
    <>
      <rect x="6.5" y="6.5" width="11" height="11" rx="1.5" />
      <path d="M10 10h4v4h-4zM10 4v2.5M14 4v2.5M10 17.5V20M14 17.5V20M4 10h2.5M4 14h2.5M17.5 10H20M17.5 14H20" />
    </>
  ),
  // Communication services — a mast broadcasting.
  XLC: (
    <>
      <circle cx="12" cy="10" r="1.6" />
      <path d="M12 11.6V20M8.4 6.8a5 5 0 0 0 0 6.4M15.6 6.8a5 5 0 0 1 0 6.4M5.6 4.2a9 9 0 0 0 0 11.6M18.4 4.2a9 9 0 0 1 0 11.6" />
    </>
  ),
  // Consumer discretionary — a shopping bag.
  XLY: <path d="M5.5 8h13l-1 12h-11zM9 8V6.5a3 3 0 0 1 6 0V8" />,
  // Consumer staples — a cart.
  XLP: (
    <>
      <path d="M3.5 5h2.2l2.1 9.5h9.8l2-7H6.9" />
      <circle cx="9" cy="18.5" r="1.3" />
      <circle cx="16.2" cy="18.5" r="1.3" />
    </>
  ),
  // Financials — a bank's pediment and columns.
  XLF: <path d="M3.5 9L12 4.5 20.5 9zM6 11.5v5.5M10 11.5v5.5M14 11.5v5.5M18 11.5v5.5M3.5 19.5h17" />,
  // Health care — the medical cross.
  XLV: <path d="M9.5 4.5h5v5h5v5h-5v5h-5v-5h-5v-5h5z" />,
  // Industrials — a gear.
  XLI: (
    <>
      <circle cx="12" cy="12" r="3" />
      <circle cx="12" cy="12" r="6.2" />
      <path d="M12 3.2v2.6M12 18.2v2.6M3.2 12h2.6M18.2 12h2.6M5.8 5.8l1.8 1.8M16.4 16.4l1.8 1.8M5.8 18.2l1.8-1.8M16.4 7.6l1.8-1.8" />
    </>
  ),
  // Energy — a flame.
  XLE: <path d="M12 3.5c1 3.2 4.6 5 4.6 9.6a4.6 4.6 0 0 1-9.2 0c0-2 1-3.4 2.3-4.5.3 1.6 1 2.6 2 3-.4-2.9.3-5.4.3-8.1z" />,
  // Materials — a molecule.
  XLB: (
    <>
      <circle cx="7" cy="7.5" r="2.2" />
      <circle cx="17" cy="7.5" r="2.2" />
      <circle cx="12" cy="17" r="2.2" />
      <path d="M9.2 7.5h5.6M8.1 9.4l2.8 5.7M15.9 9.4l-2.8 5.7" />
    </>
  ),
  // Utilities — a bolt.
  XLU: <path d="M13 3.5L6 13.5h5.5L10.5 20.5 18 10h-5.5z" />,
  // Real estate — a house.
  XLRE: <path d="M4.5 11L12 4.5 19.5 11M6.5 9.5v10h11v-10M10 19.5v-5h4v5" />,
};

const strokes = { fill: "none", stroke: "currentColor", strokeWidth: 1.6, strokeLinecap: "round", strokeLinejoin: "round" } as const;

/** A sector fund's glyph, or nothing for a ticker that is not one. */
export function SectorGlyph({ fund, size = 15, className }: { fund: string; size?: number; className?: string }) {
  const g = GLYPH[fund];
  if (!g) return null;
  return (
    <svg viewBox="0 0 24 24" width={size} height={size} aria-hidden className={className ?? "block shrink-0"} {...strokes}>
      {g}
    </svg>
  );
}
