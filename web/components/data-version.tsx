"use client";

import { createContext, useCallback, useEffect, useState } from "react";
import { get } from "@/lib/api";
import type { AppState } from "@/lib/types";

interface Ctx {
  version: number;
  state: AppState | null;
  refresh: () => void;
}

/** Bumped whenever the active data changes, so every page re-fetches. */
export const DataVersion = createContext<Ctx>({ version: 0, state: null, refresh: () => {} });

export function DataProvider({ children }: { children: React.ReactNode }) {
  const [version, setVersion] = useState(0);
  const [state, setState] = useState<AppState | null>(null);
  useEffect(() => {
    get<AppState>("/api/state").then(setState).catch(() => setState(null));
  }, [version]);
  const refresh = useCallback(() => setVersion((v) => v + 1), []);
  return <DataVersion.Provider value={{ version, state, refresh }}>{children}</DataVersion.Provider>;
}
