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

  /*
   * THE THEMES (owner, 2026-11-10: "for the sectors and themes, we can make our
   * own similar to how we did for the first set"). Drawn here on the same grid and
   * stroke, one subject each, never the fund issuer's mark: VanEck's or Global X's
   * logo would say nothing about semis or uranium. Where a theme sits close to its
   * sector, the picture is the narrower thing: a wafer, not the chip; a crane, not
   * the house; a pin on the bank, not the bank.
   */
  // Semis — a silicon wafer, notch and dies.
  SMH: (
    <>
      <path d="M9 19.4A8 8 0 1 1 15 19.4z" />
      <path d="M8.5 9h7v6h-7zM12 9v6M8.5 12h7" />
    </>
  ),
  // Memory — a memory stick and its pins.
  DRAM: <path d="M3 8h18v7.5H3zM6.5 15.5V18M9.5 15.5V18M12.5 15.5V18M15.5 15.5V18M18.5 15.5V18M6.5 11.75h2.5M10.75 11.75h2.5M15 11.75h2.5" />,
  // Software — code brackets.
  IGV: <path d="M8.5 7.5L4 12l4.5 4.5M15.5 7.5L20 12l-4.5 4.5M13.6 5l-3.2 14" />,
  // Cybersecurity — a shield with a keyhole.
  CIBR: (
    <>
      <path d="M12 3.5l7 2.6v5.4c0 4.3-2.9 7.7-7 9-4.1-1.3-7-4.7-7-9V6.1z" />
      <circle cx="12" cy="10.8" r="1.7" />
      <path d="M12 12.5v3" />
    </>
  ),
  // Cloud — a cloud.
  SKYY: <path d="M7.5 18.5a4.5 4.5 0 0 1-.7-8.95A5.6 5.6 0 0 1 17.6 10.9h.15a3.8 3.8 0 0 1 0 7.6z" />,
  // Quantum — an atom's three orbits.
  QTUM: (
    <>
      <circle cx="12" cy="12" r="1.3" />
      <ellipse cx="12" cy="12" rx="9" ry="3.6" />
      <ellipse cx="12" cy="12" rx="9" ry="3.6" transform="rotate(60 12 12)" />
      <ellipse cx="12" cy="12" rx="9" ry="3.6" transform="rotate(-60 12 12)" />
    </>
  ),
  // Robotics and AI — a robot's head.
  BOTZ: (
    <>
      <rect x="5" y="8" width="14" height="10.5" rx="2.2" />
      <path d="M12 8V5.2M9.8 15.3h4.4M3 12v3M21 12v3" />
      <circle cx="12" cy="4.3" r="0.9" />
      <circle cx="9.3" cy="12.2" r="1.1" />
      <circle cx="14.7" cy="12.2" r="1.1" />
    </>
  ),
  // Innovation — a light bulb.
  ARKK: <path d="M9.5 17.5h5M10.3 20.3h3.4M12 3.5a5.6 5.6 0 0 0-3.3 10.1c.7.5 1.1 1.3 1.1 2.1v1.8h4.4v-1.8c0-.8.4-1.6 1.1-2.1A5.6 5.6 0 0 0 12 3.5z" />,
  // Bitcoin miners — the coin.
  WGMI: (
    <>
      <circle cx="12" cy="12" r="8.6" />
      <path d="M10 7.6v8.8M10 7.6h2.6a2 2 0 0 1 0 4H10M10 11.6h3a2.4 2.4 0 0 1 0 4.8h-3M11 6.2v1.4M13 6.2v1.4M11 16.4v1.4M13 16.4v1.4" />
    </>
  ),
  // Biotech — the double helix.
  XBI: <path d="M8 3.5c0 4.3 8 4.2 8 8.5s-8 4.2-8 8.5M16 3.5c0 4.3-8 4.2-8 8.5s8 4.2 8 8.5M9.2 6h5.6M9.2 18h5.6M10.4 12h3.2" />,
  // Aerospace and defense — a sight.
  ITA: (
    <>
      <circle cx="12" cy="12" r="7" />
      <circle cx="12" cy="12" r="2.2" />
      <path d="M12 2.8v4.4M12 16.8v4.4M2.8 12h4.4M16.8 12h4.4" />
    </>
  ),
  // Space — a rocket.
  NASA: (
    <>
      <path d="M12 3c2.9 2.1 4.2 5.4 4.2 8.8V16H7.8v-4.2C7.8 8.4 9.1 5.1 12 3zM7.8 12.8L5 15.2V18h2.8M16.2 12.8l2.8 2.4V18h-2.8M10.4 18.6c.2 1.1.8 1.9 1.6 2.4.8-.5 1.4-1.3 1.6-2.4" />
      <circle cx="12" cy="9.6" r="1.5" />
    </>
  ),
  // Regional banks — money on a map pin.
  KRE: (
    <>
      <path d="M12 21s-6.6-5.7-6.6-11.1a6.6 6.6 0 0 1 13.2 0C18.6 15.3 12 21 12 21z" />
      <path d="M13.7 7.9c-.3-.6-.9-.9-1.7-.9-1 0-1.7.5-1.7 1.3 0 1.9 3.5 1 3.5 3 0 .8-.7 1.4-1.8 1.4-.8 0-1.5-.4-1.9-1M12 5.9v1.1M12 12.7v1.1" />
    </>
  ),
  // Homebuilders — a crane and its load.
  XHB: <path d="M6 20.5V4.5l12.5 3M6 7.8l12.5-.3M15.5 7.5v4.2M13.7 11.7h3.6v2.6h-3.6zM3.5 20.5h6M6 11h3M6 15h3" />,
  // Airlines — an airliner from above.
  JETS: <path d="M12 3.2c.8 0 1.4.8 1.4 2v4.6l6.8 4v1.9l-6.8-2.1v3.7l2.1 1.6v1.5L12 19.3l-3.5 1.1v-1.5l2.1-1.6v-3.7l-6.8 2.1v-1.9l6.8-4V5.2c0-1.2.6-2 1.4-2z" />,
  // Infrastructure — an arch bridge.
  PAVE: <path d="M2.5 15h19M4 15v4.5M20 15v4.5M4 15c3.2-6.2 12.8-6.2 16 0M8 11.3V15M12 10.4V15M16 11.3V15" />,
  // Smart grid — a transmission pylon.
  GRID: <path d="M12 3L8 21M12 3l4 18M8.9 17h6.2M9.8 13h4.4M10.6 9.2h2.8M4.5 8.5h15M6.5 12h11M4.5 8.5v1.8M19.5 8.5v1.8" />,
  // Solar — a panel on its stand.
  TAN: <path d="M4.5 15.5h15l-2-7h-11zM9.2 8.5l-.6 7M12 8.5v7M14.8 8.5l.6 7M5.5 12h13M12 15.5v3.5M9 19h6" />,
  // Uranium — the trefoil.
  URA: (
    <>
      <path d="M10.5 9.4L7.7 4.55A8.6 8.6 0 0 1 16.3 4.55L13.5 9.4A3 3 0 0 0 10.5 9.4zM15 12L20.6 12A8.6 8.6 0 0 1 16.3 19.45L13.5 14.6A3 3 0 0 0 15 12zM10.5 14.6L7.7 19.45A8.6 8.6 0 0 1 3.4 12L9 12A3 3 0 0 0 10.5 14.6z" />
      <circle cx="12" cy="12" r="1.2" />
    </>
  ),
  // Oil and gas E&P — a drop of crude, where Energy is the flame.
  XOP: <path d="M12 3.5c3.2 4.2 6.2 7.3 6.2 10.9a6.2 6.2 0 0 1-12.4 0c0-3.6 3-6.7 6.2-10.9zM9.3 14.6a2.8 2.8 0 0 0 2.4 2.7" />,
  // Gold miners — stacked bars.
  GDX: <path d="M3 19.5h8l-1.5-4.2h-5zM13 19.5h8l-1.5-4.2h-5zM8 15.3h8l-1.5-4.2h-5z" />,
  // Copper miners — copper's square on the periodic table.
  COPX: (
    <>
      <rect x="3.5" y="3.5" width="17" height="17" rx="2.5" />
      <path d="M11.2 10a2.6 2.6 0 1 0 0 4M13.4 9.6v2.6a1.6 1.6 0 0 0 3.2 0V9.6M16.6 12.2v2.2" />
    </>
  ),
  // Metals and mining — a pickaxe.
  XME: <path d="M4.5 19.5L16 8M9 5Q18 6 19 15" />,
  // China internet — the web's globe.
  KWEB: (
    <>
      <circle cx="12" cy="12" r="8.6" />
      <path d="M3.4 12h17.2M12 3.4c2.4 2.5 3.6 5.4 3.6 8.6s-1.2 6.1-3.6 8.6c-2.4-2.5-3.6-5.4-3.6-8.6S9.6 5.9 12 3.4z" />
    </>
  ),
  // China large cap — a pagoda.
  FXI: <path d="M12 3v2.2M5 9.6c2.3-.4 4.6-1.9 7-4.1 2.4 2.2 4.7 3.7 7 4.1M7.6 9.6v3.2M16.4 9.6v3.2M4 15.6c2.6-.4 5.3-1.6 8-3.4 2.7 1.8 5.4 3 8 3.4M6.6 15.6v4.9M17.4 15.6v4.9M4.5 20.5h15" />,
};

const strokes = { fill: "none", stroke: "currentColor", strokeWidth: 1.6, strokeLinecap: "round", strokeLinejoin: "round" } as const;

/** A sector or theme fund's glyph, or nothing for a ticker that is not one. */
export function SectorGlyph({ fund, size = 15, className }: { fund: string; size?: number; className?: string }) {
  const g = GLYPH[fund];
  if (!g) return null;
  return (
    <svg viewBox="0 0 24 24" width={size} height={size} aria-hidden className={className ?? "block shrink-0"} {...strokes}>
      {g}
    </svg>
  );
}
