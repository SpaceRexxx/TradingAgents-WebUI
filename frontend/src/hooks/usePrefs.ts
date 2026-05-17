import { useCallback, useState } from "react";

export interface Prefs {
  selectedAnalysts: string[];
  researchDepth: number;
  lookbackDays: number;
  newsLookbackDays: number;
  hasPosition: boolean;
}

const KEY = "ta_prefs";

export const DEFAULT_PREFS: Prefs = {
  selectedAnalysts: ["market", "social", "news", "fundamentals"],
  researchDepth: 2,
  lookbackDays: 30,
  newsLookbackDays: 7,
  hasPosition: false,
};

function load(): Prefs {
  try {
    const raw = localStorage.getItem(KEY);
    if (!raw) return DEFAULT_PREFS;
    return { ...DEFAULT_PREFS, ...(JSON.parse(raw) as Partial<Prefs>) };
  } catch {
    return DEFAULT_PREFS;
  }
}

export function usePrefs(): [Prefs, (patch: Partial<Prefs>) => void] {
  const [prefs, setPrefs] = useState<Prefs>(load);

  const update = useCallback((patch: Partial<Prefs>) => {
    setPrefs((prev) => {
      const next = { ...prev, ...patch };
      try {
        localStorage.setItem(KEY, JSON.stringify(next));
      } catch {
        /* storage unavailable — keep in-memory only */
      }
      return next;
    });
  }, []);

  return [prefs, update];
}
