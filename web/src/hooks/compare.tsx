import { createContext, useCallback, useContext, useEffect, useMemo, useState, type ReactNode } from "react";

export const MAX_COMPARE = 3;
const KEY = "footstats-compare";

interface CompareState {
  ids: number[];
  add: (id: number) => void;
  remove: (id: number) => void;
  set: (ids: number[]) => void;
  has: (id: number) => boolean;
  full: boolean;
}

const CompareContext = createContext<CompareState | null>(null);

function load(): number[] {
  try {
    const raw = JSON.parse(localStorage.getItem(KEY) ?? "[]");
    return Array.isArray(raw) ? raw.filter((n) => Number.isInteger(n) && n > 0).slice(0, MAX_COMPARE) : [];
  } catch {
    return [];
  }
}

/** The players picked for comparison (up to three), remembered in this browser. */
export function CompareProvider({ children }: { children: ReactNode }) {
  const [ids, setIds] = useState<number[]>(load);

  useEffect(() => {
    try {
      localStorage.setItem(KEY, JSON.stringify(ids));
    } catch {
      // private mode or storage blocked: the list just isn't remembered
    }
  }, [ids]);

  const add = useCallback((id: number) => {
    setIds((cur) => (cur.includes(id) || cur.length >= MAX_COMPARE ? cur : [...cur, id]));
  }, []);
  const remove = useCallback((id: number) => setIds((cur) => cur.filter((x) => x !== id)), []);
  const set = useCallback((next: number[]) => setIds([...new Set(next)].slice(0, MAX_COMPARE)), []);

  const value = useMemo<CompareState>(
    () => ({ ids, add, remove, set, has: (id) => ids.includes(id), full: ids.length >= MAX_COMPARE }),
    [ids, add, remove, set],
  );
  return <CompareContext.Provider value={value}>{children}</CompareContext.Provider>;
}

export function useCompare(): CompareState {
  const ctx = useContext(CompareContext);
  if (!ctx) throw new Error("useCompare must be used inside CompareProvider");
  return ctx;
}
