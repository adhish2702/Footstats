import { createApp } from "./app";
import { loadConfig } from "./config";
import { createPool } from "./db";

const config = loadConfig();
const pool = createPool(config.databaseUrl);
const app = createApp({ db: pool, corsOrigins: config.corsOrigins });

const server = app.listen(config.port, () => {
  console.log(`FootStats API on http://localhost:${config.port} (CORS: ${config.corsOrigins.join(", ")})`);
});

function shutdown() {
  server.close(() => pool.end().finally(() => process.exit(0)));
}
process.on("SIGTERM", shutdown);
process.on("SIGINT", shutdown);
