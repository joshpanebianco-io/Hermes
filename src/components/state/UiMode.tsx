"use client";

import { createContext, useContext } from "react";
import { DEFAULT_UI, type UiMode } from "@/lib/ui";

/**
 * The interface, for the components that have to KNOW it rather than paint
 * with it.
 *
 * Most of Quiet is CSS: `.ui-qt` and the `qt:` variant restyle a pane without
 * the pane asking. A few things cannot be reached that way — a section whose
 * STRUCTURE changes (the brief's call cards become hairline columns), or a hue
 * set inline from data. Those read this. Held by the Terminal, which owns the
 * interface state and seeds it from the cookie the server read, so the first
 * render on both sides agrees.
 */
const UiCtx = createContext<UiMode>(DEFAULT_UI);

export const UiProvider = UiCtx.Provider;

export function useQuiet(): boolean {
  return useContext(UiCtx) === "quiet";
}

/**
 * Luminous Glass, and Sidebar, which rides on it (lib/ui.ts): the pages that lay
 * themselves out as cards there (the brief) ask this, and are the same cards in both.
 */
export function useLum(): boolean {
  const ui = useContext(UiCtx);
  return ui === "lum" || ui === "side";
}

/**
 * The Sidebar interface: the pages are listed down the left and the shell's header
 * carries the page's name, the prices and the search, so a page asks this before it
 * draws a band of its own for any of those.
 */
export function useSide(): boolean {
  return useContext(UiCtx) === "side";
}
