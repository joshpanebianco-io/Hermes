"use client";

import { useCallback, useEffect, useState } from "react";

/**
 * A piece of UI state that survives a reload.
 *
 * THE DEFAULT IS WHAT RENDERS FIRST, ALWAYS. localStorage does not exist on the
 * server, so reading it during render would make the first client render
 * disagree with the server's markup and React would throw the tree away — the
 * same hydration trap the clock and the relative timestamps hit. So the hook
 * starts on the default, reads storage once after mount, and only then applies
 * the stored value. A saved filter therefore appears a frame late, which is
 * invisible and correct, rather than never or broken.
 *
 * ONLY PREFERENCES BELONG HERE. Nothing derived from market data is stored:
 * a remembered filter is a preference and stays true, a remembered price is a
 * lie the moment it is written.
 *
 * Every failure is swallowed on purpose. Storage throws in private windows and
 * when a browser is set to block site data, and a terminal that will not render
 * because it could not remember which tab you were on is worse than one that
 * forgets.
 */
export function usePersisted<T>(
  key: string,
  fallback: T,
  /** Rejects a stored value this build no longer understands. */
  isValid: (v: unknown) => v is T,
): [T, (v: T | ((prev: T) => T)) => void] {
  const [value, setValue] = useState<T>(fallback);

  useEffect(() => {
    try {
      const raw = window.localStorage.getItem(`nt.${key}`);
      if (raw === null) return;
      const parsed: unknown = JSON.parse(raw);
      if (isValid(parsed)) setValue(parsed);
    } catch {
      /* unreadable or unparseable storage is the same as no storage */
    }
    // `isValid` is a fresh closure on every render at most call sites, so it is
    // deliberately not a dependency — this must run once per key, not per
    // render, or it would fight every local change.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [key]);

  const set = useCallback(
    (v: T | ((prev: T) => T)) => {
      setValue((prev) => {
        const next = typeof v === "function" ? (v as (p: T) => T)(prev) : v;
        try {
          window.localStorage.setItem(`nt.${key}`, JSON.stringify(next));
        } catch {
          /* applies to this session; it just will not persist */
        }
        return next;
      });
    },
    [key],
  );

  return [value, set];
}

/** `isValid` for a fixed set of string options — the shape most filters take. */
export function oneOf<T extends string>(...allowed: readonly T[]) {
  const set = new Set<string>(allowed);
  return (v: unknown): v is T => typeof v === "string" && set.has(v);
}

/** `isValid` for a filter that holds SEVERAL of a fixed set — a list of them. */
export function manyOf<T extends string>(...allowed: readonly T[]) {
  const one = oneOf(...allowed);
  return (v: unknown): v is T[] => Array.isArray(v) && v.every(one);
}

export const isBool = (v: unknown): v is boolean => typeof v === "boolean";
