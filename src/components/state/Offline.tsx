"use client";

import { createContext, useContext } from "react";

/**
 * Whether the collector is offline, for the few components whose honest
 * answer changes with it — a skeleton says "warming up", which is a lie when
 * nothing is coming. The Terminal provides it from the payload's `offline`.
 */
const OfflineCtx = createContext(false);

export const OfflineProvider = OfflineCtx.Provider;

export function useOffline(): boolean {
  return useContext(OfflineCtx);
}
