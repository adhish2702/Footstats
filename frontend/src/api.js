import { useEffect, useState } from "react";

const BASE = import.meta.env.VITE_API_URL ?? "";

export async function getJSON(path, params = {}) {
  const qs = new URLSearchParams(
    Object.entries(params).filter(([, v]) => v !== undefined && v !== null && v !== "")
  ).toString();
  const res = await fetch(`${BASE}/api${path}${qs ? `?${qs}` : ""}`);
  if (!res.ok) throw new Error(`The server returned ${res.status} for ${path}.`);
  return res.json();
}

/** Fetch JSON whenever `deps` change. Returns { data, error, loading }. */
export function useApi(path, params = {}, deps = []) {
  const [state, setState] = useState({ data: null, error: null, loading: true });
  useEffect(() => {
    let live = true;
    setState((s) => ({ ...s, loading: true }));
    getJSON(path, params)
      .then((data) => live && setState({ data, error: null, loading: false }))
      .catch((error) => live && setState({ data: null, error, loading: false }));
    return () => {
      live = false;
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [path, ...deps]);
  return state;
}

export const POSITION_NAMES = {
  GKP: "Goalkeeper",
  DEF: "Defender",
  MID: "Midfielder",
  WNG: "Winger",
  STR: "Striker",
};

/** Roles for one position, or every role when no position is chosen. */
export function rolesFor(report, position) {
  return (report?.positions ?? [])
    .filter((p) => !position || p.position === position)
    .flatMap((p) => p.roles.map((r) => r.role));
}

export const fmt = (n, d = 2) => (n === null || n === undefined ? "–" : Number(n).toFixed(d));

export function ordinal(n) {
  const s = ["th", "st", "nd", "rd"];
  const v = n % 100;
  return n + (s[(v - 20) % 10] || s[v] || s[0]);
}

export const sentence = (s) => s.charAt(0) + s.slice(1).toLowerCase();

export const AGE_OPTIONS = [
  { value: "", label: "Any age" },
  { value: "21", label: "21 or under" },
  { value: "23", label: "23 or under" },
  { value: "25", label: "25 or under" },
];
