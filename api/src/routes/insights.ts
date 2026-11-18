import { Router } from "express";
import type { Db } from "../db";
import { SUMMARY_FROM, SUMMARY_SELECT, toSummary } from "../players";
import { overUnderQuery, parse } from "../validation";

export function insightsRouter(db: Db): Router {
  const router = Router();

  /**
   * GET /insights/over-under?limit=&position=&league=
   * The biggest gaps between actual and predicted non-penalty G+A per 90.
   */
  router.get("/over-under", async (req, res) => {
    const q = parse(overUnderQuery, req.query);
    const filters = `pr.player_id IS NOT NULL
      AND ($2::text IS NULL OR p.position = $2)
      AND ($3::text IS NULL OR c.league = $3)`;
    const params = [q.limit, q.position ?? null, q.league ?? null];
    const [over, under, model] = await Promise.all([
      db.query(`SELECT ${SUMMARY_SELECT} FROM ${SUMMARY_FROM}
                 WHERE ${filters} AND pr.gap_p90 > 0
                 ORDER BY pr.gap_p90 DESC, p.id LIMIT $1`, params),
      db.query(`SELECT ${SUMMARY_SELECT} FROM ${SUMMARY_FROM}
                 WHERE ${filters} AND pr.gap_p90 < 0
                 ORDER BY pr.gap_p90 ASC, p.id LIMIT $1`, params),
      db.query(`SELECT version, test_mae FROM model_versions ORDER BY trained_at DESC, version LIMIT 1`),
    ]);
    res.json({
      model: model.rows[0] ? { version: model.rows[0].version, testMae: model.rows[0].test_mae } : null,
      // A gap smaller than the model's typical error is not much of a signal.
      note: "Gap = actual minus predicted non-penalty goals + assists per 90. " +
        "Each prediction comes from a model trained without that player.",
      overperformers: over.rows.map(toSummary),
      underperformers: under.rows.map(toSummary),
    });
  });

  return router;
}
