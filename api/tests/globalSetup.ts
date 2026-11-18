/**
 * Runs once before the tests: rebuilds TEST_DATABASE_URL from db/schema.sql
 * and loads the fixture data. Refuses to touch anything that doesn't look like
 * a test database, so a wrong setting can never wipe the real one.
 */
import fs from "node:fs";
import path from "node:path";
import { Client } from "pg";
import "../src/config"; // loads the repo's .env
import { seed } from "./seed";

export default async function globalSetup(): Promise<void> {
  const url = process.env.TEST_DATABASE_URL;
  if (!url) throw new Error("TEST_DATABASE_URL is not set (see .env.example)");
  const dbName = new URL(url).pathname.replace(/^\//, "");
  if (url === process.env.DATABASE_URL || !/test/i.test(dbName)) {
    throw new Error(`Refusing to reset "${dbName}": TEST_DATABASE_URL must name a separate *test* database`);
  }

  const client = new Client({ connectionString: url });
  await client.connect();
  try {
    await client.query("BEGIN");
    await client.query(fs.readFileSync(path.resolve(__dirname, "../../db/schema.sql"), "utf8"));
    await seed(client);
    await client.query("COMMIT");
  } catch (err) {
    await client.query("ROLLBACK");
    throw err;
  } finally {
    await client.end();
  }
}
