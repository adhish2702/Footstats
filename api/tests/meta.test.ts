import { FRONTEND, api } from "./helpers";
import { MODEL } from "./seed";

describe("GET /health", () => {
  it("reports the database as reachable", async () => {
    const res = await api().get("/health").expect(200);
    expect(res.body).toEqual({ status: "ok", database: "ok" });
  });
});

describe("GET /model", () => {
  it("returns the model version and its stored metrics", async () => {
    const res = await api().get("/model").expect(200);
    expect(res.body).toMatchObject({
      version: MODEL.version,
      modelName: "Ridge regression",
      players: 11,
      testPlayers: 2,
      metrics: { testMae: 0.07, baselineMae: 0.17, testR2: 0.79, cvMae: 0.076, errorReductionPct: 58.8 },
    });
    expect(res.body.featureImportance[0]).toEqual({ feature: "Shots", importance: 0.3 });
  });

  it("rejects unknown query parameters", async () => {
    const res = await api().get("/model?verbose=1").expect(400);
    expect(res.body.error.details).toEqual([{ param: "verbose", message: "unknown query parameter" }]);
  });
});

describe("database access", () => {
  it("uses read-only sessions", async () => {
    const { createPool } = await import("../src/db");
    const pool = createPool(process.env.TEST_DATABASE_URL!);
    try {
      const { rows } = await pool.query("SHOW default_transaction_read_only");
      expect(rows[0].default_transaction_read_only).toBe("on");
      await expect(pool.query("DELETE FROM players")).rejects.toThrow(/read-only transaction/);
    } finally {
      await pool.end();
    }
  });
});

describe("errors and headers", () => {
  it("returns a JSON 404 for unknown routes", async () => {
    const res = await api().get("/nope").expect(404);
    expect(res.body).toEqual({ error: { status: 404, message: "Not found: GET /nope" } });
  });

  it("is read-only", async () => {
    const res = await api().post("/players").send({ name: "x" }).expect(405);
    expect(res.body.error.message).toMatch(/read-only/);
    await api().delete("/players/1").expect(405);
  });

  it("allows the configured front end and no other origin", async () => {
    const allowed = await api().get("/health").set("Origin", FRONTEND).expect(200);
    expect(allowed.headers["access-control-allow-origin"]).toBe(FRONTEND);
    const other = await api().get("/health").set("Origin", "https://evil.example").expect(200);
    expect(other.headers["access-control-allow-origin"]).toBeUndefined();
  });

  it("answers CORS preflight for GET only", async () => {
    const res = await api().options("/players").set("Origin", FRONTEND)
      .set("Access-Control-Request-Method", "GET").expect(204);
    expect(res.headers["access-control-allow-methods"]).toBe("GET");
  });

  it("marks responses as cacheable and hides the framework", async () => {
    const res = await api().get("/health");
    expect(res.headers["cache-control"]).toBe("public, max-age=300");
    expect(res.headers["x-powered-by"]).toBeUndefined();
  });
});
