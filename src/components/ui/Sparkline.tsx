import { cn } from "@/lib/cn";

/**
 * A sparkline — the session's shape in 60 pixels.
 *
 * WHY IT EARNS THE SPACE ON A DENSE BOARD. A percentage change says where a
 * price ended up relative to yesterday and nothing about how it got there. Up
 * 0.4% having fallen all morning and reversed is a different market from up
 * 0.4% in a straight line at the open, and on a board of forty instruments
 * that difference is the whole reason to look at more than one of them.
 *
 * NO AXES, NO LABELS, NO TOOLTIP. It is a glyph, not a chart — the figures
 * beside it carry every number a reader needs, and axis furniture at this size
 * would cost more pixels than the line.
 *
 * THE BASELINE IS THE PRIOR CLOSE, not the series minimum. Drawn against its
 * own low, every sparkline starts at the bottom-left and looks like a rally;
 * against the prior close, a line that spends the session under water sits
 * visibly under the rule, which is the thing worth seeing at a glance.
 */
export function Sparkline({
  data,
  prev,
  className,
  width = 64,
  height = 18,
  tone = "side",
  fluid = false,
}: {
  data: number[];
  /** Yesterday's close. Draws the reference rule when it is inside the range. */
  prev?: number | null;
  className?: string;
  width?: number;
  height?: number;
  /**
   * "ink" draws the line in a neutral grey: for a series whose rise is not a side
   * (the VIX, a yield, the dollar), where green for up would say the wrong thing.
   */
  tone?: "side" | "ink";
  /**
   * `width` is the most it draws at: in a row short of room it gives way, down to 24px,
   * instead of running past the row's edge (the Macro board's two columns on the Sidebar
   * interface, 2026-11-15: the line ran 21px into the next column). The line is squeezed
   * sideways only; its stroke and the dot on its last print keep their size.
   */
  fluid?: boolean;
}) {
  const give = fluid ? "min-w-[24px] shrink" : "shrink-0";
  if (!data || data.length < 2) {
    return <div style={{ width, height }} className={cn(give, className)} aria-hidden />;
  }

  const lo = Math.min(...data, prev ?? Infinity);
  const hi = Math.max(...data, prev ?? -Infinity);
  const span = hi - lo || 1;
  const pad = 1.5;
  const h = height - pad * 2;

  const x = (i: number) => (i / (data.length - 1)) * width;
  const y = (v: number) => pad + (1 - (v - lo) / span) * h;

  const d = data.map((v, i) => `${i ? "L" : "M"}${x(i).toFixed(1)},${y(v).toFixed(1)}`).join("");

  // The colour is the SESSION's direction — last against the prior close —
  // not the direction of the final tick, which flickers.
  const base = prev ?? data[0];
  const up = data[data.length - 1] >= base;
  const stroke = tone === "ink" ? "var(--ink-3)" : up ? "var(--call)" : "var(--put)";

  const ry = prev !== null && prev !== undefined && prev >= lo && prev <= hi ? y(prev) : null;

  return (
    <svg
      width={width}
      height={height}
      viewBox={`0 0 ${width} ${height}`}
      preserveAspectRatio={fluid ? "none" : undefined}
      className={cn("overflow-visible", give, className)}
      aria-hidden
    >
      {ry !== null && (
        <line
          x1={0}
          x2={width}
          y1={ry}
          y2={ry}
          stroke="var(--ink-4)"
          strokeWidth={0.5}
          strokeDasharray="2 2"
          opacity={0.6}
          vectorEffect={fluid ? "non-scaling-stroke" : undefined}
        />
      )}
      <path d={d} fill="none" stroke={stroke} strokeWidth={1.2} strokeLinejoin="round" vectorEffect={fluid ? "non-scaling-stroke" : undefined} />
      {fluid ? (
        // A point with a round cap: a circle would be squeezed to an oval with the line.
        <path
          d={`M${x(data.length - 1).toFixed(1)},${y(data[data.length - 1]).toFixed(1)}h0`}
          stroke={stroke}
          strokeWidth={3}
          strokeLinecap="round"
          vectorEffect="non-scaling-stroke"
        />
      ) : (
        <circle cx={x(data.length - 1)} cy={y(data[data.length - 1])} r={1.5} fill={stroke} />
      )}
    </svg>
  );
}
