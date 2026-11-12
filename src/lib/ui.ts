/**
 * The interface — which chassis paints the terminal.
 *
 * QUIET IS THE DEFAULT (owner instruction, 2026-10-13: "update the newsterminal
 * app UI to be like the quiet terminal aesthetic in gexygens macro section").
 * GEXYGEN's Quiet Terminal, carried across by copying, never by linkage: flat
 * chrome on one neutral grey ramp, hairlines instead of cards, IBM Plex, and
 * the data hues as the only colour on the screen.
 *
 * CLASSIC IS GONE (owner, 2026-11-11: "lets also completely remove the 'classic' theme
 * compleley"). It was the carded, neon, mono-caps chassis the terminal shipped with,
 * kept one click away in Settings for a month. It can no longer be chosen or drawn:
 * there are two interfaces, `<html>` always wears `ui-qt`, and a cookie that still
 * says "classic" opens Quiet. What is left of it is not a theme: the stylesheet's
 * unscoped rules are the base that `.ui-qt` and the `qt:` variant paint over, so they
 * stay as the foundation of both interfaces, never seen bare.
 *
 * THE CLASS GOES ON `<html>`, set by the server from this cookie, so the first
 * paint is already the right interface rather than one flashing to the other.
 */

/*
 * LUMINOUS GLASS RIDES ON QUIET (owner, 2026-11-10: "can we add a theme similar to
 * the other gexygen one that has the glass looking cards"). GEXYGEN's second
 * interface — the blue-black ground, cards of lit glass, Saira and JetBrains Mono —
 * copied across as tokens and card rules under `.ui-lum`, which `<html>` wears
 * TOGETHER with `.ui-qt`: every page keeps Quiet's layout, strips and type
 * scale, and Luminous only repaints the chassis. So `lum` is a Quiet, not a third
 * structure, and anything that asks "is this Quiet?" is right to say yes. (Since
 * 2026-11-11 its text is the system's sans, not Saira, and a wide window is drawn
 * 10% larger: "Luminous, turned up" at the end of globals.css.)
 */
/*
 * SIDEBAR RIDES ON LUMINOUS (owner, 2026-11-12, of the reference screenshots in
 * Desktop\Scanner: "can we create a new interface in the settings ... and follow this
 * layout closely - keeping our stuff we have but following that layout"). That layout
 * is a different SHELL, not a different paint: the pages down the left in groups, and
 * across the top one card with the page's name, the index prices, the search, the
 * session and the clock. Under it every page is the cards Luminous already draws. So
 * `<html>` wears `.ui-side` WITH `.ui-lum` and `.ui-qt`: the pages, the cards, the
 * pills and the wide-window zoom are Luminous's, and `.ui-side` (the last block of
 * globals.css) flattens the glass to the screenshots' plain dark cards and lays the
 * shell out. The Terminal draws the shell (shell/Sidebar, shell/SideHeader); a page's
 * own band of views is not drawn there, because the sidebar lists the views.
 *
 * The layout is theirs; the names, the mark, the hues and everything on the pages are
 * Hermes's. A sidebar was built once before (2026-11-09) as a switch on the old
 * interfaces and taken out two days later when the owner kept the top bar; this is a
 * whole interface of its own, chosen in Settings like the other two.
 */
export type UiMode = "quiet" | "lum" | "side";

export const UI_COOKIE = "nt_ui";
export const DEFAULT_UI: UiMode = "quiet";

/** The cookie as a mode: anything this build does not know, a remembered "classic" included, is Quiet. */
export function parseUi(raw: string | undefined): UiMode {
  return raw === "lum" || raw === "side" ? raw : DEFAULT_UI;
}

/** The classes `<html>` wears for a mode: always Quiet's; Luminous's with it; and Sidebar's on top of both. */
export function uiClass(m: UiMode): string {
  return m === "side" ? "ui-qt ui-lum ui-side" : m === "lum" ? "ui-qt ui-lum" : "ui-qt";
}

/** Each interface's own class, for a live switch: the ones a mode does not wear come off. */
export const UI_CLASSES = ["ui-qt", "ui-lum", "ui-side"] as const;
