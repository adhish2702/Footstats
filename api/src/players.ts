/** Player queries shared by /players, /compare and /insights. */
import type { Db } from "./db";

/** The model's 19 playing-style inputs (player_stats columns), in the model's order. */
export const STYLE_FEATURES = [
  { key: "shots_p90", label: "Shots" },
  { key: "shots_on_target_p90", label: "Shots on target" },
  { key: "touches_p90", label: "Touches" },
  { key: "touches_in_box_p90", label: "Touches in box" },
  { key: "key_passes_p90", label: "Key passes" },
  { key: "passes_into_box_p90", label: "Passes into box" },
  { key: "passes_into_final_third_p90", label: "Passes into final third" },
  { key: "progressive_passes_p90", label: "Progressive passes" },
  { key: "progressive_carries_p90", label: "Progressive carries" },
  { key: "progressive_receptions_p90", label: "Progressive receptions" },
  { key: "carries_into_box_p90", label: "Carries into box" },
  { key: "successful_take_ons_p90", label: "Successful take-ons" },
  { key: "shot_creating_actions_p90", label: "Shot-creating actions" },
  { key: "crosses_p90", label: "Crosses" },
  { key: "through_balls_p90", label: "Through balls" },
  { key: "miscontrols_p90", label: "Miscontrols", lowerIsBetter: true },
  { key: "dispossessed_p90", label: "Dispossessed", lowerIsBetter: true },
  { key: "ball_recoveries_p90", label: "Ball recoveries" },
  { key: "aerials_won_p90", label: "Aerials won" },
] as const;

/** The model whose predictions are served: the most recently trained one. */
export const CURRENT_MODEL = `(SELECT version FROM model_versions ORDER BY trained_at DESC, version LIMIT 1)`;

/** Columns for a player summary. Joins: p = players, c = clubs, s = player_stats, pr = predictions. */
export const SUMMARY_SELECT = `
  p.id, p.name, p.position, p.role, p.age, p.minutes, p.qualified, p.rating,
  c.id AS club_id, c.name AS club_name, c.league,
  s.npga_p90, pr.predicted_p90, pr.actual_p90, pr.gap_p90`;

export const SUMMARY_FROM = `
  players p
  JOIN clubs c ON c.id = p.club_id
  JOIN player_stats s ON s.player_id = p.id
  LEFT JOIN predictions pr ON pr.player_id = p.id AND pr.model_version = ${CURRENT_MODEL}`;

type Row = Record<string, any>;

export interface Prediction {
  predictedP90: number;
  actualP90: number;
  gapP90: number;
}

export interface PlayerSummary {
  id: number;
  name: string;
  club: { id: number; name: string; league: string };
  position: string;
  role: string;
  age: number | null;
  minutes: number;
  qualified: boolean;
  rating: number;
  npgaP90: number;
  /** Null for goalkeepers and players under 900 minutes: the model doesn't cover them. */
  prediction: Prediction | null;
}

export function toSummary(r: Row): PlayerSummary {
  return {
    id: r.id,
    name: r.name,
    club: { id: r.club_id, name: r.club_name, league: r.league },
    position: r.position,
    role: r.role,
    age: r.age,
    minutes: r.minutes,
    qualified: r.qualified,
    rating: r.rating,
    npgaP90: r.npga_p90,
    prediction:
      r.predicted_p90 === null || r.predicted_p90 === undefined
        ? null
        : { predictedP90: r.predicted_p90, actualP90: r.actual_p90, gapP90: r.gap_p90 },
  };
}

/** The full profile of one player, or null if there is no such player. */
export async function playerDetail(db: Db, id: number) {
  const { rows } = await db.query(
    `SELECT ${SUMMARY_SELECT},
            p.clubs_played, p.nationality, p.birth_year, p.appearances, p.starts,
            pr.in_test_set, pr.model_version, s.*
       FROM ${SUMMARY_FROM}
      WHERE p.id = $1`,
    [id],
  );
  const r = rows[0];
  if (!r) return null;

  // Percentile of each style feature: the share of qualified players in the same
  // position (900+ minutes) whose value is at or below this player's.
  const shares = STYLE_FEATURES.map(
    ({ key }) => `round(100.0 * avg((q.${key} <= t.${key})::int)) AS ${key}`,
  ).join(",\n       ");
  const pct = await db.query(
    `WITH t AS (SELECT s.*, p.position FROM player_stats s JOIN players p ON p.id = s.player_id WHERE p.id = $1),
          q AS (SELECT s.* FROM player_stats s JOIN players p ON p.id = s.player_id, t
                 WHERE p.position = t.position AND p.qualified)
     SELECT count(*) AS pool_size,
       ${shares}
       FROM q, t`,
    [id],
  );
  const percentiles = pct.rows[0] as Row;

  const summary = toSummary(r);
  return {
    ...summary,
    clubsPlayed: r.clubs_played,
    nationality: r.nationality,
    birthYear: r.birth_year,
    appearances: r.appearances,
    starts: r.starts,
    prediction: summary.prediction && {
      ...summary.prediction,
      modelVersion: r.model_version,
      inTestSet: r.in_test_set,
    },
    stats: {
      output: {
        goals: r.goals,
        assists: r.assists,
        penaltyGoals: r.penalty_goals,
        nonPenaltyGoals: r.non_penalty_goals,
        xg: r.xg,
        npxg: r.npxg,
        xag: r.xag,
        npgaP90: r.npga_p90,
        npxgP90: r.npxg_p90,
        xagP90: r.xag_p90,
      },
      defending: {
        tacklesWonP90: r.tackles_won_p90,
        interceptionsP90: r.interceptions_p90,
        clearancesP90: r.clearances_p90,
        passAccuracyPct: r.pass_accuracy_pct,
      },
      goalkeeping:
        r.position === "GKP"
          ? {
              savesPct: r.saves_pct,
              cleanSheets: r.clean_sheets,
              goalsConceded: r.goals_conceded,
              goalsPrevented: r.goals_prevented,
            }
          : null,
    },
    /** Per 90, with the percentile among qualified players in the same position. */
    style: {
      comparedWith: `${percentiles.pool_size} ${r.position} players with 900+ minutes`,
      features: STYLE_FEATURES.map((f) => ({
        key: f.key,
        label: f.label,
        value: r[f.key],
        percentile: percentiles.pool_size > 0 ? percentiles[f.key] : null,
        lowerIsBetter: "lowerIsBetter" in f,
      })),
    },
  };
}

export type PlayerDetail = NonNullable<Awaited<ReturnType<typeof playerDetail>>>;
