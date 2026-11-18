import { api } from "./helpers";

const ids = (players: { id: number }[]) => players.map((p) => p.id);

describe("GET /insights/over-under", () => {
  it("lists the biggest over- and under-performers against the model", async () => {
    const res = await api().get("/insights/over-under").expect(200);
    // gap = actual - predicted; ties are broken by id
    expect(ids(res.body.overperformers)).toEqual([11, 1, 3, 8, 13, 10]);
    expect(ids(res.body.underperformers)).toEqual([7, 2, 9, 12, 14, 4]);
    expect(res.body.overperformers[0].prediction).toEqual({ predictedP90: 0.55, actualP90: 0.9, gapP90: 0.35 });
    expect(res.body.underperformers[0].prediction.gapP90).toBe(-0.3);
    expect(res.body.model).toEqual({ version: "test-model-v1", testMae: 0.07 });
  });

  it("never lists a player without a prediction", async () => {
    const res = await api().get("/insights/over-under?limit=50").expect(200);
    const all = [...res.body.overperformers, ...res.body.underperformers];
    expect(all).toHaveLength(12);
    expect(all.every((p: any) => p.prediction !== null)).toBe(true);
  });

  it("limits each list", async () => {
    const res = await api().get("/insights/over-under?limit=2").expect(200);
    expect(ids(res.body.overperformers)).toEqual([11, 1]);
    expect(ids(res.body.underperformers)).toEqual([7, 2]);
  });

  it("filters by position and league", async () => {
    const strikers = (await api().get("/insights/over-under?position=STR").expect(200)).body;
    expect(ids(strikers.overperformers)).toEqual([11, 1]);
    expect(ids(strikers.underperformers)).toEqual([7]);
    const laLiga = (await api().get("/insights/over-under").query({ league: "La Liga" }).expect(200)).body;
    expect(ids(laLiga.overperformers)).toEqual([11, 13]);
    expect(ids(laLiga.underperformers)).toEqual([12, 14]);
  });

  it.each(["limit=0", "limit=51", "limit=x", "position=GKP", "league=MLS", "min=1"])(
    "rejects ?%s", async (query) => {
      await api().get(`/insights/over-under?${query}`).expect(400);
    },
  );

  it("returns 404 for an unknown insight", async () => {
    await api().get("/insights/top-scorers").expect(404);
  });
});
