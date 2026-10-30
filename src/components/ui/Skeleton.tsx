"use client";

import { PaneLoader } from "@/components/ui/HelmLoader";

/**
 * A pane's first-load state. It was a shimmer of grey rows; it is now the
 * HERMES helm with its animation (owner, 2026-10-14: "everywhere there is a
 * loading, it should be the hermex helmet logo"), centred in about the height
 * the rows took so the pane does not jump when the answer lands. The name and
 * props stay, so every panel that used it changed with this one file.
 */
export function Skeleton({
  rows = 4,
  className,
  label = "Loading",
}: {
  rows?: number;
  className?: string;
  /** What is loading — the caption, and what a screen reader hears. */
  label?: string;
}) {
  return <PaneLoader label={label} rows={rows} className={className} />;
}
