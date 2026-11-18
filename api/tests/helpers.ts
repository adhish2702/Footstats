import type { Pool } from "pg";
import request from "supertest";
import { createApp } from "../src/app";
import "../src/config";
import { createPool } from "../src/db";

export const FRONTEND = "http://localhost:5173";

let pool: Pool | undefined;

/** A supertest client for the app, wired to the seeded test database. */
export function api() {
  pool ??= createPool(process.env.TEST_DATABASE_URL!);
  return request(createApp({ db: pool, corsOrigins: [FRONTEND] }));
}

afterAll(async () => {
  await pool?.end();
  pool = undefined;
});
