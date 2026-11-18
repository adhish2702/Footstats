import type { GapStatus, Position } from "../api/types";

export const POSITION_NAMES: Record<Position, string> = {
  GKP: "Goalkeeper",
  DEF: "Defender",
  MID: "Midfielder",
  WNG: "Winger",
  STR: "Striker",
};

export const LEAGUES = ["Premier League", "La Liga", "Serie A", "Bundesliga", "Ligue 1"] as const;
export const POSITIONS: Position[] = ["GKP", "DEF", "MID", "WNG", "STR"];

/** "Martin Ødegaard" -> "MØ"; "Vitinha" -> "VI"; "Jan Paul van Hecke" -> "JH". */
export function initials(name: string): string {
  const words = name.trim().split(/\s+/).filter((w) => /\p{L}/u.test(w));
  if (words.length === 0) return "?";
  if (words.length === 1) return [...words[0]!].slice(0, 2).join("").toUpperCase();
  const first = [...words[0]!][0]!;
  const last = [...words[words.length - 1]!][0]!;
  return (first + last).toUpperCase();
}

/** 0.4567 -> "0.46". */
export function fixed(n: number | null | undefined, digits = 2): string {
  return n === null || n === undefined || !Number.isFinite(n) ? "—" : n.toFixed(digits);
}

/** 0.2 -> "+0.20", -0.1 -> "−0.10" (true minus sign). */
export function signed(n: number | null | undefined, digits = 2): string {
  if (n === null || n === undefined || !Number.isFinite(n)) return "—";
  const text = Math.abs(n).toFixed(digits);
  if (Number(text) === 0) return text;
  return n > 0 ? `+${text}` : `−${text}`;
}

/** 1 -> "1st", 22 -> "22nd", 13 -> "13th". */
export function ordinal(n: number | null | undefined): string {
  if (n === null || n === undefined || !Number.isFinite(n)) return "—";
  const r = Math.round(n);
  const teen = r % 100 >= 11 && r % 100 <= 13;
  const suffix = teen ? "th" : ({ 1: "st", 2: "nd", 3: "rd" } as Record<number, string>)[r % 10] ?? "th";
  return `${r}${suffix}`;
}

export function thousands(n: number): string {
  return n.toLocaleString("en-GB");
}

/** Whether a gap is big enough to call: smaller than the model's typical error is noise. */
export function gapVerdict(gap: number, typicalError = 0.07): "over" | "under" | "level" {
  if (gap >= typicalError) return "over";
  if (gap <= -typicalError) return "under";
  return "level";
}

export const STATUS_TEXT: Record<GapStatus, string> = {
  missing: "No qualified player",
  weak: "Weak",
  below: "Below average",
  above: "Above average",
};

/** Upper end of a gauge scale: a round number at least 0.2 above the larger value. */
export function gaugeMax(...values: number[]): number {
  const top = Math.max(0.6, ...values.filter(Number.isFinite));
  // Round before ceil: (1.3 + 0.1) * 5 is 7.000000000000001 in floating point.
  return Math.ceil(Math.round((top + 0.1) * 5 * 1e6) / 1e6) / 5;
}

/** Angle (degrees, -90 = left, +90 = right) of a value on a half-circle gauge. */
export function gaugeAngle(value: number, max: number): number {
  const t = Math.max(0, Math.min(1, value / max));
  return -90 + 180 * t;
}
