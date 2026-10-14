import type { Tab } from "@/lib/tabs";

/*
 * The panel's own words — what it shows before any model is asked. Kept apart
 * from prompt.ts so the browser bundle does not pull the whole prompt in to
 * print a greeting.
 */

/** The first message in every conversation. Never sent to the model. */
export const GREETING =
  "Hi, I'm Hermes. Ask me to explain anything on the terminal — a panel, a reading, a level, a setup or a market idea — and I'll answer from the live data on your desk.";

/**
 * Openers chosen for the tab the reader has open (and, on the Scanner, the
 * name they have selected), shown until they ask something of their own. Each
 * is a question a reader of that tab actually has before a session — not a
 * feature tour.
 */
export function suggestionsFor(tab: Tab, sym: string | null): string[] {
  switch (tab) {
    case "terminal":
      return [
        "What matters most going into the next session?",
        "Explain the vol term structure right now",
        "What are rates and the Fed path telling me?",
        "Which headlines could move NQ, ES or GC?",
      ];
    case "report":
      return [
        "Summarise the latest brief in three lines",
        "What would make today's calls wrong?",
        "Explain the gamma read in plain words",
        "Which catalyst is the biggest risk this session?",
      ];
    case "market":
      return [
        "What is the tape count saying, and why?",
        "Is breadth confirming the move?",
        "What could move stocks during the session?",
        "How should VIX shape my stops today?",
      ];
    case "scanner":
      return sym
        ? [
            `Explain ${sym}'s setup`,
            `What would trigger and invalidate ${sym}?`,
            `Which contract fits ${sym} and why?`,
            `Why does ${sym} rank where it does?`,
          ]
        : [
            "Why do the top names rank where they do?",
            "Which names are closest to a break?",
            "How does the scanner's score work?",
            "What are cheap and rich options telling me?",
          ];
    case "plan":
      return [
        "Summarise the game plan",
        "Which name has the best context behind it?",
        "What would change the plan at the open?",
        "Explain the conviction cap",
      ];
    default:
      return [
        "What can you explain?",
        "How do the two desks differ?",
        "What does Quiet change?",
      ];
  }
}
