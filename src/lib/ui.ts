/**
 * The interface — which chassis paints the terminal.
 *
 * QUIET IS THE DEFAULT (owner instruction, 2026-10-13: "update the newsterminal
 * app UI to be like the quiet terminal aesthetic in gexygens macro section").
 * GEXYGEN's Quiet Terminal, carried across by copying, never by linkage: flat
 * chrome on one neutral grey ramp, hairlines instead of cards, IBM Plex, and
 * the data hues as the only colour on the screen.
 *
 * CLASSIC STAYS ONE CLICK AWAY in Settings, as GEXYGEN kept its own previous
 * interface beside Quiet. Everything Quiet changes is scoped under `.ui-qt`
 * (and the `qt:` variant), so the classic paint is simply the absence of the
 * class — there is no second stylesheet to drift.
 *
 * THE CLASS GOES ON `<html>`, set by the server from this cookie, so the first
 * paint is already the right interface rather than classic flashing to Quiet.
 */

export type UiMode = "quiet" | "classic";

export const UI_COOKIE = "nt_ui";
export const DEFAULT_UI: UiMode = "quiet";

export function parseUi(raw: string | undefined): UiMode {
  return raw === "classic" || raw === "quiet" ? raw : DEFAULT_UI;
}

/** The class `<html>` wears for a mode; classic wears none. */
export function uiClass(m: UiMode): string {
  return m === "quiet" ? "ui-qt" : "";
}
