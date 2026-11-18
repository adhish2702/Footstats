import { api } from "./helpers";

describe("GET /clubs", () => {
  it("lists every club by league, with squad counts", async () => {
    const res = await api().get("/clubs").expect(200);
    expect(res.body.data).toEqual([
      { id: 3, name: "Ciudad Azul", league: "La Liga", players: 3, playersWithPrediction: 3 },
      { id: 4, name: "Puerto Viejo", league: "La Liga", players: 2, playersWithPrediction: 1 },
      { id: 1, name: "North Bank", league: "Premier League", players: 6, playersWithPrediction: 4 },
      { id: 2, name: "Riverside", league: "Premier League", players: 4, playersWithPrediction: 4 },
    ]);
  });

  it("filters by league", async () => {
    const res = await api().get("/clubs").query({ league: "Premier League" }).expect(200);
    expect(res.body.data.map((c: any) => c.id)).toEqual([1, 2]);
  });

  it("rejects an unknown league", async () => {
    const res = await api().get("/clubs?league=MLS").expect(400);
    expect(res.body.error.details[0].param).toBe("league");
  });
});

describe("GET /clubs/:id/gaps", () => {
  // Premier League, minutes-weighted predicted npG+A per 90 by position:
  //   STR (2500 x 0.60 + 2400 x 0.50) / 4900 = 0.551
  //   WNG (2000 x 0.40 + 1800 x 0.45) / 3800 = 0.424
  //   MID (2200 x 0.30 + 2600 x 0.15) / 4800 = 0.219
  //   DEF (2700 x 0.10 + 2900 x 0.05) / 5600 = 0.074
  it("compares each position with the league, weakest first", async () => {
    const res = await api().get("/clubs/1/gaps").expect(200);
    expect(res.body.club).toEqual({ id: 1, name: "North Bank", league: "Premier League" });
    expect(res.body.weakest).toBe("WNG");
    expect(res.body.positions.map((p: any) => [p.position, p.vsLeaguePct, p.status])).toEqual([
      ["WNG", -5.6, "below"],
      ["STR", 8.9, "above"],
      ["DEF", 34.9, "above"],
      ["MID", 37.1, "above"],
    ]);
    expect(res.body.positions[0]).toMatchObject({
      squadPlayers: 1, squadMinutes: 2000, squadPredictedP90: 0.4, squadActualP90: 0.3,
      leaguePredictedP90: 0.424, differenceP90: -0.024,
      players: [{ id: 2, name: "Ben Carter", minutes: 2000, predictedP90: 0.4, actualP90: 0.3 }],
    });
    expect(res.body.method).toMatch(/minutes-weighted/i);
  });

  it("marks positions 10% or more below the league as weak", async () => {
    const res = await api().get("/clubs/2/gaps").expect(200);
    expect(res.body.weakest).toBe("DEF");
    expect(res.body.positions.map((p: any) => [p.position, p.vsLeaguePct, p.status])).toEqual([
      ["DEF", -32.5, "weak"],
      ["MID", -31.4, "weak"],
      ["STR", -9.3, "below"],
      ["WNG", 6.2, "above"],
    ]);
  });

  it("lists a position with no qualified player as missing, first", async () => {
    const res = await api().get("/clubs/3/gaps").expect(200);
    expect(res.body.weakest).toBe("WNG");
    expect(res.body.positions[0]).toMatchObject({
      position: "WNG", status: "missing", squadPlayers: 0, squadMinutes: 0,
      squadPredictedP90: null, vsLeaguePct: null, players: [],
    });
    // Ciudad Azul is the league's only club with a striker, midfielder and defender.
    expect(res.body.positions.slice(1).map((p: any) => p.vsLeaguePct)).toEqual([0, 0, 0]);
  });

  it("ignores players the model doesn't cover", async () => {
    // Puerto Viejo's striker has 600 minutes, so the club has no qualified striker.
    const res = await api().get("/clubs/4/gaps").expect(200);
    const status = Object.fromEntries(res.body.positions.map((p: any) => [p.position, p.status]));
    expect(status).toEqual({ DEF: "missing", MID: "missing", STR: "missing", WNG: "above" });
  });

  it("returns 404 for a club that doesn't exist", async () => {
    const res = await api().get("/clubs/99/gaps").expect(404);
    expect(res.body.error.message).toBe("No club with id 99");
  });

  it("rejects a bad club id", async () => {
    await api().get("/clubs/north-bank/gaps").expect(400);
  });
});
