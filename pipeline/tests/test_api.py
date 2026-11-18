def test_health(client):
    assert client.get("/api/health").json() == {"status": "ok"}


def test_overview(client):
    body = client.get("/api/overview").json()
    assert body["clubs"] == 96 and len(body["leagues"]) == 5


def test_players_filter_and_sort(client):
    rows = client.get("/api/players", params={"position": "STR", "qualified_only": True}).json()
    assert rows and all(r["position"] == "STR" and r["qualified"] for r in rows)
    ratings = [r["rating"] for r in rows]
    assert ratings == sorted(ratings, reverse=True)


def test_players_filter_by_role(client):
    rows = client.get("/api/players", params={"role": "Poacher", "qualified_only": True}).json()
    assert len(rows) >= 25 and all(r["role"] == "Poacher" and r["position"] == "STR" for r in rows)
    # A role from another position is a valid filter that matches nobody.
    mismatch = client.get("/api/players", params={"position": "MID", "role": "Poacher"})
    assert mismatch.status_code == 200 and mismatch.json() == []
    assert client.get("/api/players", params={"role": "Libero"}).status_code == 422


def test_players_filter_by_league_and_age(client):
    rows = client.get("/api/players", params={"league": "La Liga", "max_age": 21}).json()
    assert rows and all(r["league"] == "La Liga" and r["age"] <= 21 for r in rows)
    assert client.get("/api/players", params={"league": "MLS"}).status_code == 422


def test_leagues_and_clubs(client):
    assert client.get("/api/leagues").json()[0] == "Premier League"
    assert len(client.get("/api/clubs", params={"league": "Bundesliga"}).json()) == 18


def test_players_search(client):
    rows = client.get("/api/players", params={"q": "yamal"}).json()
    assert [r["name"] for r in rows] == ["Lamine Yamal"]


def test_invalid_position_rejected(client):
    assert client.get("/api/players", params={"position": "XYZ"}).status_code == 422
    # "FWD" was replaced by the striker / winger split.
    assert client.get("/api/players", params={"position": "FWD"}).status_code == 422


def test_player_detail(client):
    pid = client.get("/api/players", params={"q": "Haaland"}).json()[0]["id"]
    body = client.get(f"/api/players/{pid}").json()
    assert body["name"] == "Erling Haaland"
    assert {"percentiles", "similar", "role_rank", "role_description", "xga90"} <= body.keys()
    assert body["role"] == "Poacher" and body["role_plural"] == "poachers"
    assert body["role_rank"]["of"] >= 25
    assert all("per90" in m for m in body["percentiles"])


def test_player_not_found(client):
    assert client.get("/api/players/99999").status_code == 404


def test_model_endpoint(client):
    body = client.get("/api/model").json()
    assert body["test_mae"] < body["baseline_mae"]
    assert body["xg_mae"] > 0


def test_scouting_and_roles(client):
    assert len(client.get("/api/scouting/targets", params={"position": "MID", "limit": 5}).json()) == 5
    perf = client.get("/api/scouting/performance").json()
    assert perf["underperforming"][0]["gap"] < 0 < perf["overperforming"][0]["gap"]
    targets = client.get("/api/scouting/targets", params={"role": "Wing-back", "limit": 5}).json()
    assert len(targets) == 5 and all(t["role"] == "Wing-back" for t in targets)
    roles = client.get("/api/roles").json()
    assert [p["position"] for p in roles["positions"]] == ["GKP", "DEF", "MID", "WNG", "STR"]
    assert sum(len(p["roles"]) for p in roles["positions"]) == 18
    assert client.get("/api/clusters").status_code == 404
