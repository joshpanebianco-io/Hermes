import { useSyncExternalStore } from "react";

/**
 * Open Hermes from anywhere — the header's Ask key, the keyboard, a panel.
 *
 * A window event rather than a context: the panel is mounted once beside the
 * page, and the things that open it sit in different branches of the tree.
 */
export const OPEN_ASK_EVENT = "hermesx:ask";

export function openAsk(): void {
  window.dispatchEvent(new Event(OPEN_ASK_EVENT));
}

/**
 * Open Hermes with a question already typed. It opens, never toggles shut,
 * and waits for the reader to send: a starting point, not a model call made
 * on their behalf.
 */
export function askHermes(question: string): void {
  window.dispatchEvent(new CustomEvent(OPEN_ASK_EVENT, { detail: { question } }));
}

/*
 * THE NAME UNDER THE CURSOR. On the Scanner, "explain this setup" means the
 * selected row, and the selection is the Scanner's own state. It publishes it
 * here; the panel reads it for its suggestions and sends it with a question,
 * so the collector can hand the model that row whole.
 */
let focus: string | null = null;
const subs = new Set<() => void>();

export function setAskFocus(sym: string | null): void {
  if (focus === sym) return;
  focus = sym;
  subs.forEach((f) => f());
}

function subscribe(f: () => void): () => void {
  subs.add(f);
  return () => {
    subs.delete(f);
  };
}

export function useAskFocus(): string | null {
  return useSyncExternalStore(subscribe, () => focus, () => null);
}
