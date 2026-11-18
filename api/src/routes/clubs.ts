import { Router } from "express";
import type { Db } from "../db";
import { HttpError } from "../errors";
import { CURRENT_MODEL } from "../players";
import { OUTFIELD, clubsQuery, emptyQuery, id, parse } from "../validation";

/** A position is "weak" when the squad's expected output is this far below the league's. */
export const WEAK_BELOW = 0.1;

export function clubsRouter(db: Db): Router {
  const router = Router();

  /** GET /clubs?league= */
  router.get("/", async (req, res) => {
    const q = parse(clubsQuery, req.query);
    const { rows } = await db.query(
      `SELECT c.id, c.name, c.league,
              count(p.id) AS players,
              count(pr.player_id) AS players_with_prediction
         FROM clubs c
         LEFT JOIN players p ON p.club_id = c.id
         LEFT JOIN predictions pr ON pr.player_id = p.id AND pr.model_version = ${CURRENT_MODEL}
        WHERE ($1::text IS NULL OR c.league = $1)
        GROUP BY c.id
        ORDER BY c.league, c.name`,
      [q.league ?? null],
    );
    res.json({
      data: rows.map((r) => ({
        id: r.id,
        name: r.name,
        league: r.league,
        players: r.players,
        playersWithPrediction: r.players_with_prediction,
      })),
    });
  });

  /**
   * GET /clubs/:id/gaps
   *
   * For each outfield position: the squad's expected non-penalty G+A per 90
   * against the league average for that position. Both are averages of the
   * model's predictions over players with 900+ minutes, weighted by minutes,
   * so regulars count for more than squad players. Weakest position first.
   */
  router.get("/:id/gaps", async (req, res) => {
    parse(emptyQuery, req.query);
    const clubId = parse(id, req.params.id, "path parameter");
    const club = (await db.query("SELECT id, name, league FROM clubs WHERE id = $1", [clubId])).rows[0];
    if (!club) throw new HttpError(404, `No club with id ${clubId}`);

    const { rows } = await db.query(
      `WITH r AS (
         SELECT p.club_id, c.league, p.position, p.minutes, pr.predicted_p90, pr.actual_p90
           FROM predictions pr
           JOIN players p ON p.id = pr.player_id
           JOIN clubs c ON c.id = p.club_id
          WHERE pr.model_version = ${CURRENT_MODEL} AND c.league = $2
       )
       SELECT position,
              sum(predicted_p90 * minutes) / sum(minutes) AS league_predicted,
              count(*) FILTER (WHERE club_id = $1) AS squad_players,
              sum(minutes) FILTER (WHERE club_id = $1) AS squad_minutes,
              sum(predicted_p90 * minutes) FILTER (WHERE club_id = $1)
                / nullif(sum(minutes) FILTER (WHERE club_id = $1), 0) AS squad_predicted,
              sum(actual_p90 * minutes) FILTER (WHERE club_id = $1)
                / nullif(sum(minutes) FILTER (WHERE club_id = $1), 0) AS squad_actual
         FROM r
        GROUP BY position`,
      [clubId, club.league],
    );
    const players = await db.query(
      `SELECT p.id, p.name, p.position, p.minutes, pr.predicted_p90, pr.actual_p90
         FROM players p
         JOIN predictions pr ON pr.player_id = p.id AND pr.model_version = ${CURRENT_MODEL}
        WHERE p.club_id = $1
        ORDER BY p.minutes DESC, p.id`,
      [clubId],
    );

    const round = (n: number | null) => (n === null ? null : Math.round(n * 1000) / 1000);
    const positions = OUTFIELD.flatMap((position) => {
      const r = rows.find((row) => row.position === position);
      if (!r) return [];
      const squad = r.squad_players > 0 ? r.squad_predicted : null;
      const vsLeague = squad === null || r.league_predicted === 0 ? null : squad / r.league_predicted - 1;
      const status = squad === null ? "missing" : vsLeague! <= -WEAK_BELOW ? "weak" : vsLeague! < 0 ? "below" : "above";
      return [{
        position,
        status,
        squadPlayers: r.squad_players,
        squadMinutes: r.squad_minutes ?? 0,
        squadPredictedP90: round(squad),
        squadActualP90: round(r.squad_players > 0 ? r.squad_actual : null),
        leaguePredictedP90: round(r.league_predicted),
        differenceP90: squad === null ? null : round(squad - r.league_predicted),
        vsLeaguePct: vsLeague === null ? null : Math.round(vsLeague * 1000) / 10,
        players: players.rows
          .filter((p) => p.position === position)
          .map((p) => ({ id: p.id, name: p.name, minutes: p.minutes, predictedP90: p.predicted_p90, actualP90: p.actual_p90 })),
      }];
    });
    // Missing positions first, then the furthest below the league average.
    positions.sort((a, b) => (a.vsLeaguePct ?? -Infinity) - (b.vsLeaguePct ?? -Infinity));

    res.json({
      club: { id: club.id, name: club.name, league: club.league },
      method:
        "Minutes-weighted average of predicted non-penalty goals + assists per 90, over players with 900+ minutes. " +
        `A position is weak when the squad is ${WEAK_BELOW * 100}% or more below the league average, ` +
        "and missing when the squad has no qualified player there. Goalkeepers are not modelled.",
      weakest: positions[0]?.position ?? null,
      positions,
    });
  });

  return router;
}
