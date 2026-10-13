import { Terminal } from "@/components/Terminal";
import type { ReportFeed, Terminal as TerminalData } from "@/types/terminal";
import { failureReason, offlineTerminal } from "@/lib/offline";
import { cookies } from "next/headers";
import { THEME_COOKIE, parseTheme } from "@/lib/theme";
import { UI_COOKIE, parseUi } from "@/lib/ui";

/**
 * The terminal, server-rendered once and then polled by the client.
 *
 * THE FIRST PAINT IS REAL DATA. The collector holds a warm snapshot, so
 * fetching it here costs one localhost round trip and the page arrives
 * complete rather than as a grid of skeletons that fill in a second later.
 * That is the whole reason the collector is a separate always-running process
 * rather than something the request path does.
 *
 * `no-store` and `force-dynamic` together: this is a live instrument and there
 * is no version of it that should ever be served from a cache, including
 * Next's own full-route cache during a production build.
 */

export const dynamic = "force-dynamic";
export const revalidate = 0;

const API = process.env.NT_API ?? "http://127.0.0.1:8100";

async function getInitial(): Promise<TerminalData> {
  try {
    const r = await fetch(`${API.replace(/\/$/, "")}/api/terminal`, {
      cache: "no-store",
      signal: AbortSignal.timeout(8000),
    });
    if (!r.ok) throw new Error(`collector returned HTTP ${r.status}`);
    return (await r.json()) as TerminalData;
  } catch (e) {
    return offlineTerminal(failureReason(e), API);
  }
}

/**
 * The last report, so the Report tab is populated the moment it is opened.
 *
 * Fetched in parallel with the terminal and returns null on any failure: a
 * report is context beside the instrument, and a slow or dead report store must
 * never be able to delay or break the board. Same rule GEXYGEN applies to its
 * reference data.
 */
async function getReport(): Promise<ReportFeed | null> {
  try {
    const r = await fetch(`${API.replace(/\/$/, "")}/api/report`, {
      cache: "no-store",
      signal: AbortSignal.timeout(6000),
    });
    if (!r.ok) return null;
    return (await r.json()) as ReportFeed;
  } catch {
    return null;
  }
}

/**
 * `?tab=report` opens straight into the note.
 *
 * READ ON THE SERVER, not from `location` in an effect. Reading it after mount
 * would render the terminal tab first and flip to the report a frame later,
 * which is a visible flash on every deep link; reading it here means the first
 * paint is already the right tab. The client rewrites the URL with
 * `replaceState` when you switch, so the address bar stays shareable without
 * either half re-fetching.
 */
export default async function Page({
  searchParams,
}: {
  searchParams: Promise<Record<string, string | string[] | undefined>>;
}) {
  const sp = await searchParams;
  const initialTab =
    sp.tab === "report" || sp.tab === "settings" || sp.tab === "scanner" ? sp.tab : "terminal";
  /*
   * WHETHER THE URL ASKED AT ALL, which is not the same question as which tab
   * it asked for. `?tab=terminal` and a bare `/` both resolve to "terminal"
   * above, and for a while both were also treated as saying NOTHING — so the
   * remembered tab won, and the desktop shortcut opened on whatever you last
   * looked at. Landing on the report after a double-click is the wrong first
   * frame: the shortcut says "show me the terminal", and the note is a place
   * you go, not a place you arrive.
   */
  const initialTabPinned =
    sp.tab === "terminal" || sp.tab === "scanner" || sp.tab === "report" || sp.tab === "settings";
  const jar = await cookies();
  const theme = parseTheme(jar.get(THEME_COOKIE)?.value);
  const ui = parseUi(jar.get(UI_COOKIE)?.value);
  const [initial, initialReport] = await Promise.all([getInitial(), getReport()]);
  return (
    <Terminal
      initial={initial}
      initialReport={initialReport}
      initialTab={initialTab}
      initialTabPinned={initialTabPinned}
      initialTheme={theme}
      initialUi={ui}
    />
  );
}
