import fs from "node:fs";
import path from "node:path";
import dotenv from "dotenv";

// Locally, settings come from the repo's .env (git-ignored). In production
// (Render) they are real environment variables and there is no .env file.
const envFile = path.resolve(__dirname, "../../.env");
if (fs.existsSync(envFile)) dotenv.config({ path: envFile, quiet: true });

export interface Config {
  databaseUrl: string;
  port: number;
  corsOrigins: string[];
}

export function loadConfig(env: NodeJS.ProcessEnv = process.env): Config {
  const databaseUrl = env.DATABASE_URL;
  if (!databaseUrl) throw new Error("DATABASE_URL is not set (see .env.example)");
  const port = Number(env.PORT ?? 4000);
  if (!Number.isInteger(port) || port <= 0) throw new Error(`PORT must be a number, got ${env.PORT}`);
  // Comma-separated list of front-end origins allowed to call the API.
  const corsOrigins = (env.CORS_ORIGIN ?? "http://localhost:5173")
    .split(",").map((o) => o.trim().replace(/\/$/, "")).filter(Boolean);
  return { databaseUrl, port, corsOrigins };
}
