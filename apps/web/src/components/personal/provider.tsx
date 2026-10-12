"use client";

import { createContext, useCallback, useContext, useEffect, useState, type ReactNode } from "react";

import { api, type StateView } from "@/lib/personal/client";

type Ctx = {
  state: StateView | null;
  error: string | null;
  refresh: () => Promise<void>;
  setState: (s: StateView) => void;
};

const PersonalContext = createContext<Ctx | null>(null);

/** Loads this browser session's personal-finance state once and shares it across pages. */
export function PersonalProvider({ children }: { children: ReactNode }) {
  const [state, setState] = useState<StateView | null>(null);
  const [error, setError] = useState<string | null>(null);
  const refresh = useCallback(async () => {
    try {
      setState(await api.state());
      setError(null);
    } catch (e) {
      setError(e instanceof Error ? e.message : "Could not load your data");
    }
  }, []);
  useEffect(() => {
    // Initial load; the effect only kicks off the request, state is set when it resolves.
    // eslint-disable-next-line react-hooks/set-state-in-effect
    void refresh();
  }, [refresh]);
  return <PersonalContext.Provider value={{ state, error, refresh, setState }}>{children}</PersonalContext.Provider>;
}

export function usePersonal(): Ctx {
  const ctx = useContext(PersonalContext);
  if (!ctx) throw new Error("usePersonal must be used inside PersonalProvider");
  return ctx;
}
