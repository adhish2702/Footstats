import { Router } from "express";
import type { Db } from "../db";
import { HttpError } from "../errors";
import { KEEPER_PREVENTED_P90, SUMMARY_FROM, SUMMARY_SELECT, playerDetail, toSummary } from "../players";
import { escapeLike, foldName } from "../text";
import { emptyQuery, id, parse, playersQuery } from "../validation";

const SORT_COLUMNS: Record<string, string> = {
  name: "p.name",
  age: "p.age",
  minutes: "p.minutes",
  rating: "p.rating",
  npga: "s.npga_p90",
  predicted: "pr.predicted_p90",
  actual: "pr.actual_p90",
  gap: "pr.gap_p90",
  // goalkeepers only: goals prevented per 90 (everyone else sorts last)
  prevented: KEEPER_PREVENTED_P90,
};

export function playersRouter(db: Db): Router {
  const router = Router();

  /** GET /players?search=&club=&league=&position=&sort=&page=&pageSize= */
  router.get("/", async (req, res) => {
    const q = parse(playersQuery, req.query);
    const where: string[] = [];
    const params: unknown[] = [];
    const add = (sql: string, value: unknown) => {
      params.push(value);
      where.push(sql.replace("?", `$${params.length}`));
    };
    if (q.search) add(`p.search_name LIKE ? ESCAPE '\\'`, `%${escapeLike(foldName(q.search))}%`);
    if (q.club) add("c.id = ?", q.club);
    if (q.league) add("c.league = ?", q.league);
    if (q.position) add("p.position = ?", q.position);
    const whereSql = where.length ? `WHERE ${where.join(" AND ")}` : "";

    const descending = q.sort.startsWith("-");
    const field = q.sort.replace(/^-/, "");
    const order = `${SORT_COLUMNS[field]} ${descending ? "DESC" : "ASC"} NULLS LAST, p.id ASC`;

    const count = await db.query(`SELECT count(*) AS total FROM ${SUMMARY_FROM} ${whereSql}`, params);
    const total: number = count.rows[0].total;
    const { rows } = await db.query(
      `SELECT ${SUMMARY_SELECT} FROM ${SUMMARY_FROM} ${whereSql}
        ORDER BY ${order}
        LIMIT $${params.length + 1} OFFSET $${params.length + 2}`,
      [...params, q.pageSize, (q.page - 1) * q.pageSize],
    );
    res.json({
      data: rows.map(toSummary),
      page: q.page,
      pageSize: q.pageSize,
      total,
      totalPages: Math.ceil(total / q.pageSize),
      sort: q.sort,
    });
  });

  /** GET /players/:id */
  router.get("/:id", async (req, res) => {
    parse(emptyQuery, req.query);
    const playerId = parse(id, req.params.id, "path parameter");
    const player = await playerDetail(db, playerId);
    if (!player) throw new HttpError(404, `No player with id ${playerId}`);
    res.json(player);
  });

  return router;
}
