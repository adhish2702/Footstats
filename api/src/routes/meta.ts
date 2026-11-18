import { Router } from "express";
import type { Db } from "../db";
import { HttpError } from "../errors";
import { emptyQuery, parse } from "../validation";

export function metaRouter(db: Db): Router {
  const router = Router();

  /** GET /health : for the host's health check. */
  router.get("/health", async (_req, res) => {
    try {
      await db.query("SELECT 1");
      res.json({ status: "ok", database: "ok" });
    } catch {
      res.status(503).json({ status: "error", database: "unreachable" });
    }
  });

  /** GET /model : the model behind the predictions, and the metrics it scored. */
  router.get("/model", async (req, res) => {
    parse(emptyQuery, req.query);
    const { rows } = await db.query(
      `SELECT * FROM model_versions ORDER BY trained_at DESC, version LIMIT 1`,
    );
    const m = rows[0];
    if (!m) throw new HttpError(503, "No model loaded yet: run the pipeline (pipeline/load_db.py)");
    res.json({
      version: m.version,
      modelName: m.model_name,
      target: m.target,
      season: m.season,
      trainedAt: m.trained_at,
      players: m.n_players,
      trainPlayers: m.n_train,
      testPlayers: m.n_test,
      metrics: {
        testMae: m.test_mae,
        baselineMae: m.baseline_mae,
        errorReductionPct: Math.round(1000 * (1 - m.test_mae / m.baseline_mae)) / 10,
        testR2: m.test_r2,
        cvMae: m.cv_mae,
        xgMae: m.xg_mae,
        xgR2: m.xg_r2,
      },
      featureImportance: m.features,
    });
  });

  return router;
}
