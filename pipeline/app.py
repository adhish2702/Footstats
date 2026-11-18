"""FootStats REST API.

Run:  uvicorn app:app --reload --port 8000
Docs: http://localhost:8000/docs
"""
from __future__ import annotations

import os
from contextlib import asynccontextmanager
from functools import lru_cache
from typing import Literal

from fastapi import Depends, FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware

from footstats import FootStats
from footstats.roles import ROLE_INFO

Position = Literal["GKP", "DEF", "MID", "WNG", "STR"]
League = Literal["Premier League", "La Liga", "Serie A", "Bundesliga", "Ligue 1"]
Role = Literal[tuple(ROLE_INFO)]  # the 18 role names, e.g. "Poacher"

@lru_cache
def get_stats() -> FootStats:
    """Build all analyses once (about 15-20s), then serve from memory."""
    return FootStats()


@asynccontextmanager
async def lifespan(app: FastAPI):
    app.dependency_overrides.get(get_stats, get_stats)()  # warm up before serving
    yield


app = FastAPI(lifespan=lifespan, title="FootStats API", version="2.0.0",
              description="2024/25 player ratings for Europe's top five leagues: tactical roles, "
                          "similar-player search and an expected goal-contributions model.")
app.add_middleware(
    CORSMiddleware,
    allow_origins=os.getenv("FOOTSTATS_CORS", "http://localhost:5173").split(","),
    allow_methods=["GET"], allow_headers=["*"],
)


@app.get("/api/health")
def health():
    return {"status": "ok"}


@app.get("/api/overview")
def overview(fs: FootStats = Depends(get_stats)):
    return fs.overview()


@app.get("/api/leagues")
def leagues(fs: FootStats = Depends(get_stats)):
    return fs.leagues()


@app.get("/api/clubs")
def clubs(league: League | None = None, fs: FootStats = Depends(get_stats)):
    return fs.clubs(league)


@app.get("/api/players")
def players(
    position: Position | None = None,
    role: Role | None = None,
    league: League | None = None,
    max_age: int | None = Query(None, ge=15, le=45),
    club: str | None = None,
    q: str | None = Query(None, max_length=50, description="Name search"),
    qualified_only: bool = False,
    sort: Literal["rating", "minutes", "goals", "assists", "name", "age"] = "rating",
    limit: int = Query(3000, ge=1, le=3000),
    fs: FootStats = Depends(get_stats),
):
    return fs.list_players(position, club, q, qualified_only, sort, limit, league, max_age, role)


@app.get("/api/players/{player_id}")
def player(player_id: int, fs: FootStats = Depends(get_stats)):
    try:
        return fs.player(player_id)
    except KeyError:
        raise HTTPException(status_code=404, detail="Player not found")


@app.get("/api/scouting/targets")
def scouting_targets(position: Position | None = None,
                     role: Role | None = None,
                     league: League | None = None,
                     max_age: int | None = Query(None, ge=15, le=45),
                     limit: int = Query(10, ge=1, le=50),
                     fs: FootStats = Depends(get_stats)):
    return fs.scouting_targets(position, limit, league, max_age, role)


@app.get("/api/scouting/performance")
def performance(league: League | None = None,
                limit: int = Query(10, ge=1, le=50), fs: FootStats = Depends(get_stats)):
    return fs.performance_gaps(limit, league)


@app.get("/api/model")
def model(fs: FootStats = Depends(get_stats)):
    return fs.model_report()


@app.get("/api/roles")
def roles(fs: FootStats = Depends(get_stats)):
    return fs.roles_report()
