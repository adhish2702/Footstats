import cors from "cors";
import express from "express";
import type { Db } from "./db";
import { HttpError, errorHandler, notFound } from "./errors";
import { clubsRouter } from "./routes/clubs";
import { compareRouter } from "./routes/compare";
import { insightsRouter } from "./routes/insights";
import { metaRouter } from "./routes/meta";
import { playersRouter } from "./routes/players";

export interface AppOptions {
  db: Db;
  /** Front-end origins allowed to call the API from a browser. */
  corsOrigins: string[];
}

export function createApp({ db, corsOrigins }: AppOptions) {
  const app = express();
  app.disable("x-powered-by");
  app.set("query parser", "simple");

  app.use(cors({ origin: corsOrigins, methods: ["GET"] }));
  app.use((req, res, next) => {
    if (req.method !== "GET" && req.method !== "HEAD" && req.method !== "OPTIONS") {
      next(new HttpError(405, "Method not allowed: this API is read-only"));
      return;
    }
    // The data changes only when the pipeline runs, so responses can be cached briefly.
    res.set("Cache-Control", "public, max-age=300");
    next();
  });

  app.use(metaRouter(db));
  app.use("/players", playersRouter(db));
  app.use("/clubs", clubsRouter(db));
  app.use("/compare", compareRouter(db));
  app.use("/insights", insightsRouter(db));

  app.use(notFound);
  app.use(errorHandler);
  return app;
}
