"use client";

import { useSyncExternalStore } from "react";

/**
 * The scanner alerts' preferences — one store that Settings writes and the
 * alerts read, live.
 *
 * NOT `usePersisted`, and for a reason: that hook reads storage once per
 * component, so a toggle flipped in Settings would not reach the alerts
 * running in the shell until a reload. This keeps one copy in memory, tells
 * every reader when it changes, and follows the same key across browser tabs
 * through the `storage` event.
 *
 * SSR renders the defaults, like every other stored preference here (see
 * usePersisted for the hydration reason).
 */

export type AlertKind = "L" | "E" | "BO" | "NEAR";

export interface AlertPrefs {
  /** In-app alerts at all. */
  on: boolean;
  /** Desktop notifications, once the browser has granted them. */
  desktop: boolean;
  sound: boolean;
  kinds: AlertKind[];
  /** Only names scoring at least this. */
  minScore: 0 | 40 | 60;
}

/*
 * NEAR IS OFF BY DEFAULT. "About to break" fires once per level per name per
 * day, which across a 21-name list is dozens of alerts — useful when you ask
 * for it, noise when you did not. The three signals the strategy trades are on.
 */
export const DEFAULT_ALERTS: AlertPrefs = {
  on: true,
  desktop: false,
  sound: true,
  kinds: ["L", "E", "BO"],
  minScore: 0,
};

const KEY = "nt.alerts";
const KINDS: AlertKind[] = ["L", "E", "BO", "NEAR"];
let cache: AlertPrefs | null = null;
const subs = new Set<() => void>();

function parse(raw: string | null): AlertPrefs {
  if (!raw) return DEFAULT_ALERTS;
  try {
    const v = JSON.parse(raw) as Partial<AlertPrefs>;
    return {
      on: typeof v.on === "boolean" ? v.on : DEFAULT_ALERTS.on,
      desktop: typeof v.desktop === "boolean" ? v.desktop : DEFAULT_ALERTS.desktop,
      sound: typeof v.sound === "boolean" ? v.sound : DEFAULT_ALERTS.sound,
      kinds: Array.isArray(v.kinds) ? v.kinds.filter((k): k is AlertKind => KINDS.includes(k as AlertKind)) : DEFAULT_ALERTS.kinds,
      minScore: v.minScore === 40 || v.minScore === 60 ? v.minScore : 0,
    };
  } catch {
    return DEFAULT_ALERTS;
  }
}

function read(): AlertPrefs {
  if (cache) return cache;
  try {
    cache = parse(window.localStorage.getItem(KEY));
  } catch {
    cache = DEFAULT_ALERTS;
  }
  return cache;
}

function subscribe(fn: () => void): () => void {
  subs.add(fn);
  const onStorage = (e: StorageEvent) => {
    if (e.key === KEY) {
      cache = null;
      fn();
    }
  };
  window.addEventListener("storage", onStorage);
  return () => {
    subs.delete(fn);
    window.removeEventListener("storage", onStorage);
  };
}

export function setAlertPrefs(patch: Partial<AlertPrefs>): void {
  cache = { ...read(), ...patch };
  try {
    window.localStorage.setItem(KEY, JSON.stringify(cache));
  } catch {
    /* applies to this session; it just will not persist */
  }
  for (const fn of subs) fn();
}

export function useAlertPrefs(): AlertPrefs {
  return useSyncExternalStore(subscribe, read, () => DEFAULT_ALERTS);
}

/** Settings' "send a test alert" — the alerts listen for it. */
export const TEST_ALERT = "hx:test-alert";

/*
 * THE CHIME. Two short notes from WebAudio — rising for a long, falling for a
 * short — so the side is heard before the toast is read. Synthesised rather
 * than a sound file because it is three oscillator calls and needs no asset.
 * Browsers start audio suspended until the page has been clicked once; the
 * first chime after a fresh load may therefore be silent, and every later one
 * plays.
 */
let audio: AudioContext | null = null;

export function chime(side: "long" | "short"): void {
  try {
    audio ??= new AudioContext();
    if (audio.state === "suspended") void audio.resume();
    const t = audio.currentTime;
    const notes = side === "long" ? [660, 880] : [880, 587];
    notes.forEach((f, i) => {
      const o = audio!.createOscillator();
      const g = audio!.createGain();
      o.type = "sine";
      o.frequency.value = f;
      const at = t + i * 0.14;
      g.gain.setValueAtTime(0, at);
      g.gain.linearRampToValueAtTime(0.12, at + 0.015);
      g.gain.exponentialRampToValueAtTime(0.0001, at + 0.22);
      o.connect(g).connect(audio!.destination);
      o.start(at);
      o.stop(at + 0.24);
    });
  } catch {
    /* no audio device, or a browser that refuses — the toast still shows */
  }
}
