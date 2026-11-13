"use client";

import { Mark } from "@/components/shell/Header";
import { AssetIcon } from "@/components/ui/AssetIcon";
import { cn } from "@/lib/cn";
import { FUT_NAME, FUT_VIEWS, isFutBook, type FutView } from "@/lib/futures";
import { SCAN_VIEWS, type ScanView, type Tab } from "@/lib/tabs";
import { isBool, usePersisted } from "@/lib/usePersisted";

/**
 * The Sidebar interface's navigation: every page, and every view of a page, down the
 * left in groups.
 *
 * WHY THE VIEWS ARE HERE AND NOT ON THE PAGE (owner, 2026-11-12, of the reference
 * screenshots in Desktop\Scanner: "follow this layout closely - keeping our stuff we
 * have but following that layout"). In that layout the scanner's views are items of
 * the sidebar, beside the pages, under small group names; a page then opens straight
 * onto its content with no row of tabs over it. So here the Stocks tab's seven views
 * and the Futures tab's seven are listed, one click from anywhere, and those pages do
 * not draw their band in this interface (they ask `useSide`).
 *
 * THE GROUPS ARE HERMES'S OWN DESKS: the Dashboard; Stocks; Market (Sectors, and Macro
 * with its wire and calendar); Futures; Hermes AI. Settings is at the foot, where the
 * reference keeps it. A sidebar existed once before (2026-11-09 to 2026-11-11) as a
 * switch on the old interfaces and went when the owner kept the top bar; this one is
 * part of an interface of its own.
 *
 * IT FOLDS TO ITS ICONS, from the button beside the mark, and remembers that: on a
 * 1920 screen the folded rail gives the page 148px back.
 */

type Item = {
  key: string;
  label: string;
  title?: string;
  icon: React.ReactNode;
  on: boolean;
  go: () => void;
};

/** One stroke icon on a 24px grid. */
function Icon({ children }: { children: React.ReactNode }) {
  return (
    <svg aria-hidden width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round" className="shrink-0">
      {children}
    </svg>
  );
}

const ICON = {
  dashboard: (
    <Icon>
      <rect x="3" y="3" width="7" height="7" rx="1.5" />
      <rect x="14" y="3" width="7" height="7" rx="1.5" />
      <rect x="3" y="14" width="7" height="7" rx="1.5" />
      <rect x="14" y="14" width="7" height="7" rx="1.5" />
    </Icon>
  ),
  setups: (
    <Icon>
      <path d="M4 8V6a2 2 0 0 1 2-2h2M16 4h2a2 2 0 0 1 2 2v2M20 16v2a2 2 0 0 1-2 2h-2M8 20H6a2 2 0 0 1-2-2v-2M7 12h10" />
    </Icon>
  ),
  breakouts: (
    <Icon>
      <path d="M3 17l6-6 4 4 8-8M15 7h6v6" />
    </Icon>
  ),
  extended: (
    <Icon>
      <path d="M20 14.5A8 8 0 1 1 9.5 4a6.5 6.5 0 0 0 10.5 10.5z" />
    </Icon>
  ),
  day23: (
    <Icon>
      <path d="M4 11a8 8 0 0 1 14-4l2 2M20 4v5h-5M20 13a8 8 0 0 1-14 4l-2-2M4 20v-5h5" />
    </Icon>
  ),
  log: (
    <Icon>
      <path d="M8 6h12M8 12h12M8 18h12M4 6h.01M4 12h.01M4 18h.01" />
    </Icon>
  ),
  note: (
    <Icon>
      <path d="M7 3h7l5 5v13H7zM14 3v5h5M10 13h6M10 17h6" />
    </Icon>
  ),
  // Three across and two down, as the charts are.
  multi: (
    <Icon>
      <rect x="3" y="5" width="18" height="14" rx="2" />
      <path d="M9 5v14M15 5v14M3 12h18" />
    </Icon>
  ),
  sectors: (
    <Icon>
      <rect x="3" y="3" width="18" height="18" rx="2" />
      <path d="M3 12h18M12 3v18" />
    </Icon>
  ),
  macro: (
    <Icon>
      <circle cx="12" cy="12" r="9" />
      <path d="M3 12h18M12 3c3 3.5 3 14.5 0 18M12 3c-3 3.5-3 14.5 0 18" />
    </Icon>
  ),
  layers: (
    <Icon>
      <path d="M12 3l9 5-9 5-9-5 9-5zM3 13l9 5 9-5" />
    </Icon>
  ),
  hermes: (
    <Icon>
      <path d="M4 5h16v11H9l-5 4z" />
    </Icon>
  ),
  settings: (
    <Icon>
      <circle cx="12" cy="12" r="3" />
      <path d="M12 2v3M12 19v3M4.9 4.9l2.1 2.1M17 17l2.1 2.1M2 12h3M19 12h3M4.9 19.1L7 17M17 7l2.1-2.1" />
    </Icon>
  ),
  fold: (
    <Icon>
      <rect x="3" y="4" width="18" height="16" rx="2" />
      <path d="M9 4v16" />
    </Icon>
  ),
} as const;

const SCAN_ICON: Record<ScanView, React.ReactNode> = {
  setups: ICON.setups,
  breakouts: ICON.breakouts,
  extended: ICON.extended,
  day23: ICON.day23,
  log: ICON.log,
  plan: ICON.note,
  multi: ICON.multi,
};

export function Sidebar({
  tab,
  scanView,
  futView,
  onTab,
  onScan,
  onFut,
}: {
  tab: Tab;
  scanView: ScanView;
  futView: FutView;
  onTab: (t: Tab) => void;
  /** Open a view of the Stocks tab. */
  onScan: (v: ScanView) => void;
  /** Open a view of the Futures tab. */
  onFut: (v: FutView) => void;
}) {
  const [folded, setFolded] = usePersisted<boolean>("side.folded", false, isBool);

  const groups: Array<{ label: string; items: Item[] }> = [
    {
      label: "Main",
      items: [{ key: "dashboard", label: "Dashboard", title: "The session on one page", icon: ICON.dashboard, on: tab === "dashboard", go: () => onTab("dashboard") }],
    },
    {
      label: "Stocks",
      items: SCAN_VIEWS.map((v) => ({ key: `scan-${v.key}`, label: v.label, title: v.title, icon: SCAN_ICON[v.key], on: tab === "scanner" && scanView === v.key, go: () => onScan(v.key) })),
    },
    {
      label: "Market",
      items: [
        { key: "sectors", label: "Sectors", title: "Where the money is, and the stocks in it", icon: ICON.sectors, on: tab === "sectors", go: () => onTab("sectors") },
        { key: "terminal", label: "Macro", title: "The wire, the calendar, rates and the macro board", icon: ICON.macro, on: tab === "terminal", go: () => onTab("terminal") },
      ],
    },
    {
      label: "Futures",
      items: FUT_VIEWS.map((v) => ({
        key: `fut-${v.key}`,
        label: isFutBook(v.key) ? `${v.label} · ${FUT_NAME[v.key]}` : v.label,
        title: v.title,
        icon: isFutBook(v.key) ? <AssetIcon id={v.key} size={15} className="block shrink-0" /> : v.key === "brief" ? ICON.note : ICON.layers,
        on: tab === "futures" && futView === v.key,
        go: () => onFut(v.key),
      })),
    },
    {
      label: "Assistant",
      items: [{ key: "hermes", label: "Hermes AI", title: "Ask about anything on the terminal", icon: ICON.hermes, on: tab === "hermes", go: () => onTab("hermes") }],
    },
  ];
  const settings: Item = { key: "settings", label: "Settings", title: "The interface, alerts, options, colours", icon: ICON.settings, on: tab === "settings", go: () => onTab("settings") };

  const row = (it: Item) => (
    <button
      key={it.key}
      type="button"
      onClick={it.go}
      // Folded, the name is the hover; open, the hover says what the page is for.
      title={folded ? it.label : it.title}
      aria-label={it.label}
      aria-current={it.on ? "page" : undefined}
      data-on={it.on ? "" : undefined}
      className={cn("side-item hit", folded && "justify-center px-0")}
    >
      {it.icon}
      {!folded && <span className="min-w-0 truncate">{it.label}</span>}
    </button>
  );

  return (
    <aside className={cn("qt-side flex shrink-0 flex-col", folded ? "w-[60px]" : "w-[216px]")} aria-label="Pages">
      {/* 58px, the header card's own height, so the wordmark and the page's name share a line. */}
      <div className={cn("flex shrink-0 items-center gap-2.5", folded ? "flex-col px-0 pt-4 pb-2" : "h-[58px] px-4")}>
        <Mark gradientId="hermes-grad-side" />
        {!folded && <span className="wordmark fig text-[17px] font-semibold tracking-[0.14em]">HERMES</span>}
        <button
          type="button"
          onClick={() => setFolded((v) => !v)}
          aria-pressed={folded}
          aria-label={folded ? "Open the sidebar" : "Fold the sidebar to its icons"}
          title={folded ? "Open the sidebar" : "Fold the sidebar to its icons"}
          className={cn("hit inline-flex h-[26px] w-[26px] shrink-0 items-center justify-center rounded-[6px] text-ink-4 hover:text-ink-2", !folded && "ml-auto")}
        >
          {ICON.fold}
        </button>
      </div>

      <nav className={cn("min-h-0 flex-1 overflow-y-auto pb-3", folded ? "px-2" : "px-2.5")} aria-label="Pages and views">
        {groups.map((g, i) => (
          <div key={g.label} role="group" aria-label={g.label}>
            {/* A group's name has air over it, so the five read as five; the first sits
                close under the mark. Folded, a rule stands where the name was. */}
            {folded ? (
              i > 0 && <span aria-hidden className="mx-2 mt-2 mb-2.5 block h-px bg-ring" />
            ) : (
              <p className={cn("qt-cap px-3 pb-2 text-[10px] text-ink-4", i === 0 ? "pt-3" : "pt-5")}>{g.label}</p>
            )}
            {g.items.map(row)}
          </div>
        ))}
      </nav>

      <div className={cn("shrink-0 border-t border-ring pt-2.5 pb-2", folded ? "px-2" : "px-2.5")}>{row(settings)}</div>
    </aside>
  );
}
