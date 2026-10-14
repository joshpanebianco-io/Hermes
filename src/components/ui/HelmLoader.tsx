"use client";

import { useId } from "react";
import { HERMES_MARK_D } from "@/lib/hermesMark";
import { useOffline } from "@/components/state/Offline";
import { cn } from "@/lib/cn";

/**
 * THE TERMINAL'S ONE LOADING STATE (owner, 2026-10-14: "everywhere there is a
 * loading, it should be the hermex helmet logo with its animation").
 *
 * The header's winged helm, alive the way the lockup is: the colour washes
 * along the line work (SMIL on the gradient, 5.6s, the wordmark's period),
 * the glow breathes on the same cycle, and it glitches — every ten seconds
 * here rather than the header's once a minute, the cadence the report's
 * writing state already used, because a loader is stared at and a header is
 * glanced at. Under it, a thin sweep in the same gradient says "working"
 * where a still mark would read as a logo.
 *
 * Same trace, same mirror on a PARENT group (the glitch animates CSS
 * `transform`, which would override a transform attribute on the path
 * itself), same `hermes-mark` class — so it stands down under
 * prefers-reduced-motion with everything else.
 */

/** The helm alone, at `size` px — for the loaders below and the report's writing state. */
export function HelmMark({ size, gradId }: { size: number; gradId: string }) {
  // Hairline line art: fatter strokes at small sizes, or the trace vanishes.
  const stroke = size < 32 ? 12 : size < 60 ? 8 : 6;
  return (
    <svg width={size} height={size} viewBox="0 0 512 512" aria-hidden style={{ overflow: "visible" }}>
      <defs>
        <linearGradient id={gradId} gradientUnits="userSpaceOnUse" x1="0" y1="0" x2="1024" y2="0">
          <stop offset="0" stopColor="var(--icon-a)" />
          <stop offset="0.25" stopColor="var(--title-sheen)" />
          <stop offset="0.5" stopColor="var(--icon-b)" />
          <stop offset="0.75" stopColor="var(--title-sheen)" />
          <stop offset="1" stopColor="var(--icon-a)" />
          {/* 0 → −1024 runs the colour left to right on screen through the mirror. */}
          <animateTransform
            attributeName="gradientTransform"
            type="translate"
            from="0 0"
            to="-1024 0"
            dur="5.6s"
            repeatCount="indefinite"
          />
        </linearGradient>
      </defs>
      <g transform="rotate(-10 256 256) translate(512 0) scale(-1 1)">
        <path className="hermes-mark" fill={`url(#${gradId})`} stroke={`url(#${gradId})`} strokeWidth={stroke} d={HERMES_MARK_D} />
      </g>
    </svg>
  );
}

/** The sweep under the helm, in the helm's own gradient. */
export function HelmSweep({ width, gradId, className }: { width: number; gradId: string; className?: string }) {
  const run = Math.round(width / 3);
  return (
    <svg className={className} width={width} height={2} viewBox={`0 0 ${width} 2`} preserveAspectRatio="none" aria-hidden>
      <rect width={width} height="2" fill="var(--ring)" />
      <rect width={run} height="2" fill={`url(#${gradId})`}>
        <animate attributeName="x" from={-run} to={width} dur="1.8s" repeatCount="indefinite" />
      </rect>
    </svg>
  );
}

/** A gradient id that is unique per loader and valid inside `url(#…)`. */
export function useHelmId(): string {
  return `helm${useId().replace(/[^A-Za-z0-9_-]/g, "")}`;
}

/**
 * A pane, a table or a chart waiting for its first answer: the helm centred
 * in the space the content will take (`minHeight`), a sweep and a caption.
 */
export function HelmLoader({
  label,
  size = 40,
  minHeight,
  className,
  caption = true,
}: {
  /** What is loading — the caption, and what a screen reader hears. */
  label: string;
  size?: number;
  /** Reserve the content's height so nothing jumps when it lands. */
  minHeight?: number;
  className?: string;
  /** False for the tightest spots, where the helm and sweep say enough. */
  caption?: boolean;
}) {
  const id = useHelmId();
  return (
    <div
      className={cn("helm-loader flex flex-col items-center justify-center gap-3 px-3 py-5 text-center", className)}
      style={minHeight ? { minHeight } : undefined}
      role="status"
      aria-live="polite"
      aria-label={label}
    >
      <HelmMark size={size} gradId={id} />
      <HelmSweep width={Math.max(64, Math.round(size * 2.4))} gradId={id} />
      {caption && <span className="text-[11px] text-ink-3">{label}…</span>}
    </div>
  );
}

/** The helm at text size, beside a few words — for a table cell or a line of copy. */
export function HelmInline({ label, size = 14, className }: { label: string; size?: number; className?: string }) {
  const id = useHelmId();
  return (
    <span className={cn("helm-loader inline-flex items-center gap-1.5", className)} role="status" aria-label={label}>
      <HelmMark size={size} gradId={id} />
      <span>{label}…</span>
    </span>
  );
}

/** A loader that knows the collector may be down — then it says so instead of spinning forever. */
export function PaneLoader({ label, rows = 4, className }: { label: string; rows?: number; className?: string }) {
  const offline = useOffline();
  if (offline) {
    return <p className="px-3 py-5 text-center text-[11px] text-ink-3">No data — the collector is offline.</p>;
  }
  return (
    <HelmLoader
      label={label}
      size={rows <= 3 ? 28 : 36}
      // About the height of the rows it stands in for, so the pane does not jump.
      minHeight={Math.max(96, rows * 22 + 24)}
      className={className}
    />
  );
}
