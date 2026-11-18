import { api } from "./helpers";
import { PLAYERS, styleValue } from "./seed";

const ids = (body: { data: { id: number }[] }) => body.data.map((p) => p.id);

describe("GET /players", () => {
  it("lists players by rating, best first, 20 a page", async () => {
    const res = await api().get("/players").expect(200);
    expect(res.body).toMatchObject({ page: 1, pageSize: 20, total: 15, totalPages: 1, sort: "-rating" });
    expect(ids(res.body)).toEqual([1, 11, 12, 2, 14, 5, 3, 13, 4, 10, 8, 9, 7, 6, 15]);
  });

  it("returns a summary with club and prediction", async () => {
    const res = await api().get("/players?search=karim").expect(200);
    expect(res.body.data).toEqual([{
      id: 11, name: "Karim López", club: { id: 3, name: "Ciudad Azul", league: "La Liga" },
      position: "STR", role: "False nine", age: 23, minutes: 2300, qualified: true, rating: 70,
      npgaP90: 0.9, prediction: { predictedP90: 0.55, actualP90: 0.9, gapP90: 0.35 },
    }]);
  });

  it("has no prediction for goalkeepers or players under 900 minutes", async () => {
    const res = await api().get("/players?sort=name").expect(200);
    const without = res.body.data.filter((p: any) => p.prediction === null).map((p: any) => p.id);
    expect(without.sort((a: number, b: number) => a - b)).toEqual([5, 6, 15]);
  });

  it("paginates", async () => {
    const page2 = await api().get("/players?pageSize=4&page=2&sort=name").expect(200);
    expect(page2.body).toMatchObject({ page: 2, pageSize: 4, total: 15, totalPages: 4 });
    expect(page2.body.data.map((p: any) => p.name)).toEqual(["Eli Ford", "Finn Grant", "Gary Hill", "Hugo Ince"]);
    const last = await api().get("/players?pageSize=4&page=4").expect(200);
    expect(last.body.data).toHaveLength(3);
    const beyond = await api().get("/players?pageSize=4&page=9").expect(200);
    expect(beyond.body).toMatchObject({ data: [], total: 15, totalPages: 4 });
  });

  it("searches names ignoring accents and case", async () => {
    for (const search of ["alvaro nunez", "ÁLVARO", "Núñez", "  nunez  "]) {
      const res = await api().get("/players").query({ search }).expect(200);
      expect(ids(res.body)).toEqual([1]);
    }
    const res = await api().get("/players").query({ search: "pena" }).expect(200);
    expect(ids(res.body)).toEqual([15]);
  });

  it("treats LIKE wildcards in a search literally", async () => {
    const res = await api().get("/players").query({ search: "%" }).expect(200);
    expect(res.body.total).toBe(0);
    const underscore = await api().get("/players").query({ search: "_" }).expect(200);
    expect(underscore.body.total).toBe(0);
  });

  it("filters by club, league and position, together", async () => {
    expect(ids((await api().get("/players?club=2").expect(200)).body).sort()).toEqual([10, 7, 8, 9]);
    const laLiga = (await api().get("/players").query({ league: "La Liga" }).expect(200)).body;
    expect(laLiga.total).toBe(5);
    const strikers = (await api().get("/players?position=STR&sort=name").expect(200)).body;
    expect(ids(strikers)).toEqual([1, 7, 11, 15]);
    const both = (await api().get("/players").query({ position: "STR", league: "Premier League", sort: "name" })).body;
    expect(ids(both)).toEqual([1, 7]);
    expect((await api().get("/players?club=999").expect(200)).body.total).toBe(0);
  });

  it("sorts by any field either way, with missing values last", async () => {
    const gapDesc = (await api().get("/players?sort=-gap").expect(200)).body;
    expect(ids(gapDesc).slice(0, 3)).toEqual([11, 1, 3]);
    expect(ids(gapDesc).slice(-3)).toEqual([5, 6, 15]);
    const gapAsc = (await api().get("/players?sort=gap").expect(200)).body;
    expect(ids(gapAsc).slice(0, 2)).toEqual([7, 2]);
    expect(ids(gapAsc).slice(-3)).toEqual([5, 6, 15]);
    const age = (await api().get("/players?sort=age").expect(200)).body;
    expect(ids(age)[0]).toBe(6);
    expect(ids(age).at(-1)).toBe(15); // age unknown
    const minutes = (await api().get("/players?sort=-minutes&pageSize=1").expect(200)).body;
    expect(ids(minutes)).toEqual([5]);
  });

  it.each([
    ["position=XX", "position"],
    ["league=Eredivisie", "league"],
    ["sort=height", "sort"],
    ["sort=--rating", "sort"],
    ["page=0", "page"],
    ["page=-1", "page"],
    ["pageSize=101", "pageSize"],
    ["pageSize=ten", "pageSize"],
    ["club=abc", "club"],
    ["club=0", "club"],
    ["position=STR&position=WNG", "position"],
    [`search=${"x".repeat(51)}`, "search"],
  ])("rejects %s", async (query, param) => {
    const res = await api().get(`/players?${query}`).expect(400);
    expect(res.body.error).toMatchObject({ status: 400, message: "Invalid query parameters" });
    expect(res.body.error.details.map((d: any) => d.param)).toContain(param);
  });

  it("rejects unknown parameters, naming them", async () => {
    const res = await api().get("/players?postion=STR").expect(400);
    expect(res.body.error.details).toEqual([{ param: "postion", message: "unknown query parameter" }]);
  });
});

describe("GET /players/:id", () => {
  it("returns the full profile", async () => {
    const res = await api().get("/players/1").expect(200);
    const p = res.body;
    expect(p).toMatchObject({
      id: 1, name: "Álvaro Núñez", position: "STR", role: "Poacher", clubsPlayed: "North Bank",
      birthYear: 2000, qualified: true,
      prediction: { predictedP90: 0.6, actualP90: 0.8, gapP90: 0.2, modelVersion: "test-model-v1", inTestSet: false },
      stats: { output: { goals: 1, npgaP90: 0.8 }, goalkeeping: null },
    });
    expect(p.stats.defending).toEqual({ tacklesWonP90: 1.1, interceptionsP90: 0.9, clearancesP90: 2.5, passAccuracyPct: 81 });
  });

  it("gives each style feature a percentile within the position", async () => {
    // Qualified strikers are players 1, 7 and 11, and style values rise with the id.
    const low = (await api().get("/players/1").expect(200)).body.style;
    expect(low.comparedWith).toBe("3 STR players with 900+ minutes");
    expect(low.features).toHaveLength(19);
    expect(low.features[0]).toEqual({
      key: "shots_p90", label: "Shots", value: styleValue(1, 0), percentile: 33, lowerIsBetter: false,
    });
    expect(low.features.every((f: any) => f.percentile === 33)).toBe(true);
    expect((await api().get("/players/7")).body.style.features[0].percentile).toBe(67);
    expect((await api().get("/players/11")).body.style.features[0].percentile).toBe(100);
    // A striker under 900 minutes is placed against the qualified ones.
    expect((await api().get("/players/15")).body.style.features[0].percentile).toBe(100);
    const misc = low.features.find((f: any) => f.key === "miscontrols_p90");
    expect(misc.lowerIsBetter).toBe(true);
  });

  it("shows goalkeeping stats and no prediction for a goalkeeper", async () => {
    const res = await api().get("/players/5").expect(200);
    expect(res.body.prediction).toBeNull();
    expect(res.body.stats.goalkeeping).toEqual({ savesPct: 71.5, cleanSheets: 12, goalsConceded: 30, goalsPrevented: 3.2 });
  });

  it("returns 404 for a player that doesn't exist", async () => {
    const res = await api().get("/players/999").expect(404);
    expect(res.body.error).toEqual({ status: 404, message: "No player with id 999" });
  });

  it.each(["abc", "0", "1.5", "-3", "99999999999"])("rejects the id %s", async (bad) => {
    const res = await api().get(`/players/${bad}`).expect(400);
    expect(res.body.error.message).toBe("Invalid path parameters");
  });

  it("every seeded player can be fetched", async () => {
    for (const p of PLAYERS) {
      const res = await api().get(`/players/${p.id}`).expect(200);
      expect(res.body.name).toBe(p.name);
    }
  });
});
