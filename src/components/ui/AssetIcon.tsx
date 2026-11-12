/**
 * A mark for each futures book (owner, 2026-11-10: "futures we can use the icons
 * we made like in gexygen"). Copied from GEXYGEN's asset marks, path for path,
 * never imported: the two screens sit side by side and a market should wear the
 * same mark on both, but this terminal runs without GEXYGEN on the disk.
 *
 * DRAWN, NOT DOWNLOADED. The funds carry their issuers' logos, SPY and DIA the
 * same State Street stripes, so a fetched icon would not tell NQ from ES.
 *
 *   the indices   a badge with the index's member count: the Nasdaq-100, the
 *                 S&P 500, the Dow 30, and here the Russell 2000 as well
 *   the metals    an ingot in its own metal's colour, gold and silver; GLD,
 *                 a fund of gold bars, wears the gold one
 *   crude         a drop of oil, WTI and Brent alike
 *
 * The metals' colours are their identity, the one use of colour outside the
 * data hues; everything else takes the row's ink. A key with no mark draws
 * nothing, so it is safe to ask for any.
 */

const COUNT: Record<string, string> = { NQ: "100", ES: "500", YM: "30", RTY: "2000" };
const METAL: Record<string, { fill: string; shine: string }> = {
  GC: { fill: "#d6a83a", shine: "#f3d680" },
  GLD: { fill: "#d6a83a", shine: "#f3d680" },
  SILVER: { fill: "#aeb6c1", shine: "#e4e9ef" },
  SIL: { fill: "#aeb6c1", shine: "#e4e9ef" },
  SI: { fill: "#aeb6c1", shine: "#e4e9ef" },
};
const CRUDE: ReadonlySet<string> = new Set(["WTI", "BRENT", "CL"]);

/** Whether a key has a drawn mark. */
export const hasAssetIcon = (id: string): boolean => id in COUNT || id in METAL || CRUDE.has(id);

export function AssetIcon({ id, size = 18, className }: { id: string; size?: number; className?: string }) {
  const count = COUNT[id];
  const metal = METAL[id];
  if (!count && !metal && !CRUDE.has(id)) return null;
  return (
    <svg viewBox="0 0 24 24" width={size} height={size} aria-hidden className={className ?? "block shrink-0"}>
      {count ? (
        <>
          <rect x="1.8" y="4.5" width="20.4" height="15" rx="3.2" fill="currentColor" opacity={0.12} />
          <rect x="1.8" y="4.5" width="20.4" height="15" rx="3.2" fill="none" stroke="currentColor" strokeWidth={1.3} opacity={0.7} />
          <text
            x="12"
            y={count.length > 3 ? 15.2 : 15.6}
            textAnchor="middle"
            fontSize={count.length > 3 ? 8.8 : count.length > 2 ? 10.5 : 11.5}
            fontWeight={700}
            fill="currentColor"
            style={{ fontFamily: "var(--font-cond, ui-sans-serif)", letterSpacing: "-0.02em" }}
          >
            {count}
          </text>
        </>
      ) : metal ? (
        <>
          {/* An ingot: the top face, then the body. */}
          <path d="M3 17.5h18l-3-8.5H6z" fill={metal.fill} />
          <path d="M6 9h12l-1.1-3.1H7.1z" fill={metal.shine} />
          <path d="M3 17.5h18" stroke={metal.shine} strokeWidth={1} opacity={0.6} />
        </>
      ) : (
        // Crude: a drop of oil, dark with a lit edge.
        <>
          <path d="M12 3.2c3.5 4.4 6.2 7.8 6.2 11a6.2 6.2 0 0 1-12.4 0c0-3.2 2.7-6.6 6.2-11z" fill="#1c1f24" stroke="currentColor" strokeWidth={1.4} />
          <path d="M9.4 14.6a2.8 2.8 0 0 0 2.2 2.6" fill="none" stroke="currentColor" strokeWidth={1.2} strokeLinecap="round" opacity={0.7} />
        </>
      )}
    </svg>
  );
}
