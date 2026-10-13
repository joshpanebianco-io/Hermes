import type { CSSProperties } from "react";
import { cn } from "@/lib/cn";

/**
 * The segmented control's props — one garment for every picker and filter
 * chip on the terminal (see `.seg` in globals.css for why there is one).
 *
 * Props rather than a component because the chips differ in what they hold
 * (a count, a swatch, a tooltip, aria-pressed) and agree only on geometry and
 * state — which is exactly what a class, a data attribute and two custom
 * properties can carry. Spread it onto a <button>:
 *
 *   <button type="button" onClick={…} {...segItem(on, { hue: "var(--desk-macro)" })}>
 *
 * `hue` tints the chip to that colour when on (classic only — Quiet lifts
 * every active chip onto the same selection grey). `pct` is how strong.
 */
export function segItem(
  on: boolean,
  opts: { hue?: string; pct?: number; className?: string } = {},
): { className: string; "data-on"?: ""; style?: CSSProperties } {
  const { hue, pct = 24, className } = opts;
  return {
    className: cn("seg-item hit", className),
    ...(on ? { "data-on": "" as const } : {}),
    ...(hue ? { style: { "--seg-hue": hue, "--seg-pct": `${pct}%` } as CSSProperties } : {}),
  };
}
