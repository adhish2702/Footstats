/**
 * A small, made-up dataset for the API tests. Names are fictional. The numbers
 * are chosen so the expected answers can be worked out by hand (see the tests).
 */
import type { Client } from "pg";
import { STYLE_FEATURES } from "../src/players";
import { foldName } from "../src/text";

export const CLUBS = [
  { id: 1, name: "North Bank", league: "Premier League" },
  { id: 2, name: "Riverside", league: "Premier League" },
  { id: 3, name: "Ciudad Azul", league: "La Liga" },
  { id: 4, name: "Puerto Viejo", league: "La Liga" },
];

interface SeedPlayer {
  id: number; name: string; club: number; position: string; role: string;
  age: number | null; minutes: number; rating: number;
  /** [predicted, actual] non-penalty G+A per 90; only for qualified outfield players. */
  prediction?: [number, number];
  npga?: number;
}

export const PLAYERS: SeedPlayer[] = [
  { id: 1, name: "Álvaro Núñez", club: 1, position: "STR", role: "Poacher", age: 24, minutes: 2500, rating: 72, prediction: [0.6, 0.8] },
  { id: 2, name: "Ben Carter", club: 1, position: "WNG", role: "Inside forward", age: 22, minutes: 2000, rating: 65, prediction: [0.4, 0.3] },
  { id: 3, name: "Chris Doyle", club: 1, position: "MID", role: "Advanced playmaker", age: 27, minutes: 2200, rating: 58, prediction: [0.3, 0.35] },
  { id: 4, name: "Dan Evans", club: 1, position: "DEF", role: "Wing-back", age: 29, minutes: 2700, rating: 55, prediction: [0.1, 0.08] },
  { id: 5, name: "Eli Ford", club: 1, position: "GKP", role: "Sweeper-keeper", age: 31, minutes: 3000, rating: 60, npga: 0 },
  { id: 6, name: "Finn Grant", club: 1, position: "MID", role: "Box-to-box midfielder", age: 19, minutes: 400, rating: 48, npga: 0.2 },
  { id: 7, name: "Gary Hill", club: 2, position: "STR", role: "Target forward", age: 30, minutes: 2400, rating: 50, prediction: [0.5, 0.2] },
  { id: 8, name: "Hugo Ince", club: 2, position: "WNG", role: "Touchline winger", age: 25, minutes: 1800, rating: 52, prediction: [0.45, 0.5] },
  { id: 9, name: "Ian Jones", club: 2, position: "MID", role: "Ball-winning midfielder", age: 26, minutes: 2600, rating: 51, prediction: [0.15, 0.1] },
  { id: 10, name: "Jack Kerr", club: 2, position: "DEF", role: "Stopper", age: 28, minutes: 2900, rating: 54, prediction: [0.05, 0.06] },
  { id: 11, name: "Karim López", club: 3, position: "STR", role: "False nine", age: 23, minutes: 2300, rating: 70, prediction: [0.55, 0.9] },
  { id: 12, name: "Luis Martín", club: 3, position: "MID", role: "Deep-lying playmaker", age: 24, minutes: 2100, rating: 66, prediction: [0.25, 0.2] },
  { id: 13, name: "Marc Nadal", club: 3, position: "DEF", role: "Inverted full-back", age: 21, minutes: 1500, rating: 57, prediction: [0.12, 0.15] },
  { id: 14, name: "Nico Ortega", club: 4, position: "WNG", role: "Wide playmaker", age: 20, minutes: 2000, rating: 61, prediction: [0.3, 0.25] },
  { id: 15, name: "Óscar Peña", club: 4, position: "STR", role: "Poacher", age: null, minutes: 600, rating: 47, npga: 0.4 },
];

export const MODEL = {
  version: "test-model-v1", model_name: "Ridge regression", target: "Non-penalty goals + assists per 90",
  season: "2024-25", n_players: 11, n_train: 9, n_test: 2, cv_mae: 0.076, test_mae: 0.07,
  baseline_mae: 0.17, test_r2: 0.79, xg_mae: 0.065, xg_r2: 0.82,
  features: [{ feature: "Shots", importance: 0.3 }, { feature: "Touches in box", importance: 0.2 }],
  data_sha256: "0".repeat(64),
};

/** Every style feature is id x 0.1 plus a small per-feature offset, so it rises with the id. */
export function styleValue(playerId: number, featureIndex: number): number {
  return Math.round((playerId * 0.1 + featureIndex * 0.01) * 1000) / 1000;
}

async function insert(client: Client, table: string, row: Record<string, unknown>) {
  const cols = Object.keys(row);
  const values = cols.map((c) => {
    const v = row[c];
    return v !== null && typeof v === "object" ? JSON.stringify(v) : v;
  });
  await client.query(
    `INSERT INTO ${table} (${cols.join(", ")}) VALUES (${cols.map((_, i) => `$${i + 1}`).join(", ")})`,
    values,
  );
}

export async function seed(client: Client): Promise<void> {
  for (const club of CLUBS) await insert(client, "clubs", club);
  await insert(client, "model_versions", MODEL);
  for (const p of PLAYERS) {
    const isGk = p.position === "GKP";
    await insert(client, "players", {
      id: p.id, name: p.name, search_name: foldName(p.name), club_id: p.club,
      clubs_played: CLUBS.find((c) => c.id === p.club)!.name, nationality: "XYZ",
      age: p.age, birth_year: p.age === null ? null : 2024 - p.age, position: p.position, role: p.role,
      appearances: Math.round(p.minutes / 85), starts: Math.round(p.minutes / 95),
      minutes: p.minutes, qualified: p.minutes >= 900, rating: p.rating,
    });
    const npga = p.prediction ? p.prediction[1] : p.npga ?? 0;
    const stats: Record<string, unknown> = {
      player_id: p.id, goals: p.id, assists: p.id % 4, penalty_goals: p.id % 2,
      non_penalty_goals: p.id - (p.id % 2), xg: p.id * 0.9, npxg: p.id * 0.8, xag: p.id * 0.3,
      npga_p90: npga, npxg_p90: 0.3, xag_p90: 0.1,
      tackles_won_p90: 1.1, interceptions_p90: 0.9, clearances_p90: 2.5, pass_accuracy_pct: 80 + p.id,
      saves_pct: isGk ? 71.5 : null, clean_sheets: isGk ? 12 : null,
      goals_conceded: isGk ? 30 : null, goals_prevented: isGk ? 3.2 : null,
    };
    STYLE_FEATURES.forEach((f, i) => { stats[f.key] = styleValue(p.id, i); });
    await insert(client, "player_stats", stats);
    if (p.prediction) {
      await insert(client, "predictions", {
        player_id: p.id, model_version: MODEL.version,
        predicted_p90: p.prediction[0], actual_p90: p.prediction[1], in_test_set: p.id % 5 === 0,
      });
    }
  }
}
