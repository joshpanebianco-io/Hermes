/*
 * The panel's own words — what it shows before any model is asked. Kept apart
 * from prompt.ts so the browser bundle does not pull the whole prompt in to
 * print a greeting.
 */

/** The first message in every conversation. Never sent to the model. */
export const GREETING =
  "Hi, I'm Hermes. Ask me to explain anything on the terminal — a panel, a reading, a level, a setup or a market idea — and I'll answer from the live data on your desk.";

/**
 * The Hermes tab's line under the helm — what it reads, and the promise every
 * answer is held to. Static on purpose: a count that must be fetched is a
 * count that can be wrong on the first frame.
 */
export const HERMES_INTRO =
  "Reads the whole terminal, live: both desks' boards, every scanner name, the latest brief and the latest market overview. Every figure it quotes is checked against that data.";

/**
 * The tab's openers — three from each desk, questions a reader sits down
 * with rather than a feature tour. Shown on an empty chat.
 */
export const HERMES_SUGGESTIONS = [
  "What matters most going into New York tonight?",
  "Which scanner names are closest to a break?",
  "Run down yesterday's earnings and the reactions",
  "Does the brief agree with the market overview?",
  "Explain the vol term structure right now",
  "How should VIX shape my stops today?",
];

/**
 * Openers chosen for the tab the reader has open (and, on the Scanner, the
 * name they have selected), shown until they ask something of their own. Each
 * is a question a reader of that tab actually has before a session — not a
 * feature tour.
 */
export function suggestionsFor(tab: string, sym: string | null): string[] {
  switch (tab) {
    case "dashboard":
      return [
        "What is the plan for the next session?",
        "Which sector or theme has the broadest move?",
        "Which of the top setups has news behind it?",
        "What could change the plan before the open?",
      ];
    case "terminal":
      return [
        "What matters most going into the next session?",
        "What are rates and the Fed path telling me?",
        "Which headlines could move NQ, ES or GC?",
        "What prints today, and what did the last ones say?",
      ];
    case "structure":
      return [
        "Where does price sit in each session's range?",
        "Explain the gamma levels and the regime",
        "Which levels on the ladder matter most right now?",
        "Explain the vol term structure right now",
      ];
    case "tape":
      return [
        "Where do SPY and QQQ sit against their levels?",
        "Is the tape worth trading with right now?",
        "Explain dealer gamma in ETF prices",
        "How much of the implied day is already used?",
      ];
    case "report":
      return [
        "Summarise the latest report in three lines",
        "What would make today's calls wrong?",
        "Which factor carries the bias right now?",
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
        "Summarise the market overview",
        "Which sector has the best story behind it?",
        "What would change the read at the open?",
        "Which names on the Scanner fit the read?",
      ];
    case "hermes":
      return HERMES_SUGGESTIONS.slice(0, 4);
    default:
      return [
        "What can you explain?",
        "How do the two desks differ?",
        "What does Quiet change?",
      ];
  }
}
