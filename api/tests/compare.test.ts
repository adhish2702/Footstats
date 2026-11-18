import { api } from "./helpers";

describe("GET /compare", () => {
  it("returns up to three full profiles in the order asked for", async () => {
    const res = await api().get("/compare?ids=11,1,7").expect(200);
    expect(res.body.players.map((p: any) => p.id)).toEqual([11, 1, 7]);
    expect(res.body.players[0].style.features).toHaveLength(19);
    expect(res.body.players[1].prediction.gapP90).toBe(0.2);
    expect(res.body.note).toMatch(/own position/);
  });

  it("works for one or two players, and across positions", async () => {
    expect((await api().get("/compare?ids=5").expect(200)).body.players).toHaveLength(1);
    const mixed = (await api().get("/compare?ids=5,2").expect(200)).body.players;
    expect(mixed.map((p: any) => p.position)).toEqual(["GKP", "WNG"]);
  });

  it("returns 404 naming every id that doesn't exist", async () => {
    const res = await api().get("/compare?ids=1,98,99").expect(404);
    expect(res.body.error.message).toBe("No player with id 98, 99");
  });

  it.each([
    ["", "ids"],
    ["ids=", "ids"],
    ["ids=1,2,3,4", "ids"],
    ["ids=1,1", "ids"],
    ["ids=1,abc", "ids"],
    ["ids=1,,2", "ids"],
    ["ids=0", "ids"],
    ["ids=1&extra=2", "extra"],
  ])("rejects ?%s", async (query, param) => {
    const res = await api().get(`/compare?${query}`).expect(400);
    expect(res.body.error.details.map((d: any) => d.param)).toContain(param);
  });
});
