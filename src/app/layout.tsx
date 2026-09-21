import type { Metadata, Viewport } from "next";
import { cookies } from "next/headers";
import { Tooltips } from "@/components/ui/Tooltips";
import { THEME_COOKIE, parseTheme, themeStyle } from "@/lib/theme";
import "./globals.css";

/*
 * THE TAB ICON IS THE DESKTOP ICON (owner, 2026-09-22): public/hermesx.ico,
 * the gradient helm on its chassis-black tile, so the tab and the shortcut
 * that opened it are one picture. It was an inline SVG before — first
 * theme-hued, then a plain black glyph (2026-09-01) — and the file wins over
 * re-inlining the tile for a reason: scripts/make-icon.mjs draws the mark
 * fresh at each size with a stroke fitted to that size, and a single SVG has
 * one stroke for every size. The browser picks the 16/32px entry it needs.
 * If the mark changes, `npm run icon` updates both at once; a tab that still
 * shows the old picture is the browser's favicon cache, not the file.
 */
export const metadata: Metadata = {
  title: "HERMESX — News Terminal",
  description:
    "A single-desk market terminal: the wire, the board, the curve, sector rotation, " +
    "the economic calendar and borrowed gamma levels, on one session clock.",
  icons: { icon: "/hermesx.ico" },
};

export const viewport: Viewport = {
  themeColor: "#0a0b10",
  width: "device-width",
  initialScale: 1,
};

/**
 * THE THEME GOES ON `<html>`, AND IT HAS TO.
 *
 * Anything reading a token with `getComputedStyle` reads it from the document
 * element, so custom properties written to a nested wrapper would style the DOM
 * and leave those readers on the compiled defaults — the same trap GEXYGEN
 * documents for its canvas panes. Server-side, so the first paint is already
 * themed rather than flashing the default palette and switching.
 */
export default async function RootLayout({ children }: { children: React.ReactNode }) {
  const jar = await cookies();
  const theme = parseTheme(jar.get(THEME_COOKIE)?.value);
  return (
    <html lang="en" style={themeStyle(theme)}>
      <body>
        {children}
        {/* Every `title` in the app, drawn in the app's own hand — see the file. */}
        <Tooltips />
      </body>
    </html>
  );
}
