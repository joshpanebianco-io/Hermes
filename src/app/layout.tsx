import type { Metadata, Viewport } from "next";
import { IBM_Plex_Mono, IBM_Plex_Sans, IBM_Plex_Sans_Condensed } from "next/font/google";
import { cookies } from "next/headers";
import { Tooltips } from "@/components/ui/Tooltips";
import { THEME_COOKIE, parseTheme, themeStyle } from "@/lib/theme";
import { UI_COOKIE, parseUi, uiClass } from "@/lib/ui";
import { cn } from "@/lib/cn";
import "./globals.css";

/*
 * QUIET TERMINAL'S TYPEFACES — IBM Plex Sans, Sans Condensed and Mono, as
 * GEXYGEN's Quiet sets them. Self-hosted by next/font, so no browser request
 * ever leaves for Google. Exposed as variables only: `.ui-qt` in globals.css is
 * what points --font-sans / --font-cond / --font-mono at them, so the classic
 * interface keeps its system faces untouched.
 */
const plex = IBM_Plex_Sans({
  subsets: ["latin"],
  weight: ["400", "500", "600"],
  variable: "--font-plex",
  display: "swap",
});
const plexCond = IBM_Plex_Sans_Condensed({
  subsets: ["latin"],
  weight: ["500", "600"],
  variable: "--font-plex-cond",
  display: "swap",
});
const plexMono = IBM_Plex_Mono({
  subsets: ["latin"],
  weight: ["400", "500", "600"],
  variable: "--font-plex-mono",
  display: "swap",
});

/*
 * THE TAB ICON IS THE DESKTOP ICON (owner, 2026-09-22): public/hermes.ico,
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
  title: "Hermes — News Terminal",
  description:
    "A single-desk market terminal: the wire, the board, the curve, sector rotation, " +
    "the economic calendar and borrowed gamma levels, on one session clock.",
  icons: { icon: "/hermes.ico" },
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
  const ui = parseUi(jar.get(UI_COOKIE)?.value);
  return (
    <html
      lang="en"
      style={themeStyle(theme)}
      className={cn(plex.variable, plexCond.variable, plexMono.variable, uiClass(ui))}
    >
      <body>
        {children}
        {/* Every `title` in the app, drawn in the app's own hand — see the file. */}
        <Tooltips />
      </body>
    </html>
  );
}
