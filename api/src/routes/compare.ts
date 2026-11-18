import { Router } from "express";
import type { Db } from "../db";
import { HttpError } from "../errors";
import { playerDetail } from "../players";
import { compareQuery, parse } from "../validation";

export function compareRouter(db: Db): Router {
  const router = Router();

  /** GET /compare?ids=1,2,3 : up to three full player profiles, in the order asked for. */
  router.get("/", async (req, res) => {
    const { ids } = parse(compareQuery, req.query);
    const players = await Promise.all(ids.map((playerId) => playerDetail(db, playerId)));
    const missing = ids.filter((_, i) => players[i] === null);
    if (missing.length) throw new HttpError(404, `No player with id ${missing.join(", ")}`);
    res.json({
      note: "Style percentiles are within each player's own position.",
      players,
    });
  });

  return router;
}
