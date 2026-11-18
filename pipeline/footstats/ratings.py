"""Role-specific player ratings (0-99, 50 = average qualified player in the role)."""
from __future__ import annotations

import numpy as np
import pandas as pd

from .data import NOT_PER90, per90
from .roles import ROLE_INFO, ROLES

# role -> metric -> weight. A negative weight means "lower is better" (inverted).
# Counting stats are converted to per 90; rates (data.NOT_PER90) are used as-is.
# Each role is judged on what the role is for, so two players in the same
# position can be rated on quite different things.
RATING_WEIGHTS: dict[str, dict[str, float]] = {
    # ---- goalkeepers: shot-stopping first, then what the role adds ----
    "Sweeper-keeper": {
        "Goals prevented": 0.30, "Save %": 0.15, "Sweeper actions": 0.20,
        "Crosses stopped %": 0.15, "Clean sheets": 0.10, "Goals conceded": -0.10,
    },
    "Ball-playing goalkeeper": {
        "Goals prevented": 0.30, "Save %": 0.15, "Pass accuracy": 0.15,
        "Passes completed": 0.15, "Crosses stopped %": 0.05, "Clean sheets": 0.10,
        "Goals conceded": -0.10,
    },
    # ---- centre-backs ----
    "Ball-playing centre-back": {
        "Progressive passes": 0.16, "Passes into final third": 0.10, "Pass accuracy": 0.12,
        "Passes completed": 0.08, "Progressive carries": 0.10, "Interceptions": 0.10,
        "Tackles won": 0.08, "Aerial win %": 0.08, "Challenge success": 0.08,
        "Errors leading to shots": -0.10,
    },
    "Stopper": {
        "Clearances": 0.16, "Aerials won": 0.12, "Aerial win %": 0.12, "Blocks": 0.12,
        "Interceptions": 0.12, "Tackles won": 0.10, "Challenge success": 0.12,
        "Pass accuracy": 0.04, "Errors leading to shots": -0.10,
    },
    "Wide centre-back": {
        "Challenge success": 0.14, "Tackles won": 0.12, "Interceptions": 0.10,
        "Ball recoveries": 0.10, "Progressive carries": 0.12, "Progressive passes": 0.10,
        "Passes into final third": 0.08, "Aerial win %": 0.08, "xAG": 0.06,
        "Errors leading to shots": -0.10,
    },
    # ---- full-backs ----
    "Inverted full-back": {
        "Progressive passes": 0.16, "Passes into final third": 0.12, "Pass accuracy": 0.12,
        "Passes completed": 0.08, "Shot-creating actions": 0.08, "Interceptions": 0.10,
        "Tackles won": 0.10, "Ball recoveries": 0.08, "Challenge success": 0.08,
        "Errors leading to shots": -0.08,
    },
    "Wing-back": {
        "xAG": 0.16, "Crosses into box": 0.10, "Key passes": 0.10,
        "Shot-creating actions": 0.10, "Progressive carries": 0.12,
        "Progressive receptions": 0.08, "Carries into box": 0.06, "Tackles won": 0.10,
        "Interceptions": 0.08, "Challenge success": 0.10,
    },
    # ---- midfielders ----
    "Deep-lying playmaker": {
        "Progressive passes": 0.18, "Passes into final third": 0.14, "Pass accuracy": 0.12,
        "Passes completed": 0.10, "Switches": 0.06, "xAG": 0.06, "Interceptions": 0.10,
        "Ball recoveries": 0.10, "Tackles won": 0.06, "Dispossessed": -0.08,
    },
    "Ball-winning midfielder": {
        "Tackles won": 0.20, "Interceptions": 0.18, "Ball recoveries": 0.16,
        "Challenge success": 0.12, "Aerials won": 0.08, "Blocks": 0.08,
        "Pass accuracy": 0.10, "Progressive passes": 0.08,
    },
    "Box-to-box midfielder": {
        "Progressive carries": 0.14, "Progressive receptions": 0.10,
        "Non-penalty goals": 0.12, "npxG": 0.10, "Touches in box": 0.08, "Assists": 0.06,
        "xAG": 0.08, "Tackles won": 0.10, "Ball recoveries": 0.10, "Interceptions": 0.06,
        "Progressive passes": 0.06,
    },
    "Advanced playmaker": {
        "xAG": 0.18, "Assists": 0.12, "Key passes": 0.12, "Shot-creating actions": 0.12,
        "Passes into box": 0.10, "Through balls": 0.06, "Non-penalty goals": 0.10,
        "npxG": 0.06, "Progressive passes": 0.08, "Progressive carries": 0.06,
    },
    # ---- wingers ----
    "Inside forward": {
        "Non-penalty goals": 0.24, "npxG": 0.18, "Shots": 0.06, "Touches in box": 0.10,
        "Assists": 0.08, "xAG": 0.08, "Shot-creating actions": 0.08,
        "Progressive receptions": 0.10, "Progressive carries": 0.08,
    },
    "Touchline winger": {
        "Successful take-ons": 0.16, "Progressive carries": 0.14, "Carries into box": 0.10,
        "xAG": 0.14, "Assists": 0.10, "Crosses into box": 0.08, "Key passes": 0.08,
        "Non-penalty goals": 0.10, "npxG": 0.05, "Progressive receptions": 0.05,
    },
    "Wide playmaker": {
        "xAG": 0.18, "Assists": 0.12, "Key passes": 0.14, "Shot-creating actions": 0.14,
        "Passes into box": 0.10, "Through balls": 0.06, "Progressive passes": 0.08,
        "Non-penalty goals": 0.10, "npxG": 0.08,
    },
    # ---- strikers ----
    "Pressing forward": {
        "Non-penalty goals": 0.22, "npxG": 0.14, "Tackles outside own third": 0.14,
        "Ball recoveries": 0.12, "Interceptions": 0.08, "Progressive receptions": 0.10,
        "Touches in box": 0.08, "Assists": 0.06, "xAG": 0.06,
    },
    "False nine": {
        "Non-penalty goals": 0.18, "npxG": 0.10, "xAG": 0.14, "Assists": 0.12,
        "Shot-creating actions": 0.14, "Key passes": 0.10, "Progressive passes": 0.08,
        "Progressive carries": 0.08, "Passes into box": 0.06,
    },
    "Poacher": {
        "Non-penalty goals": 0.35, "npxG": 0.25, "Touches in box": 0.12,
        "Shots on target": 0.10, "Shots": 0.08, "Progressive receptions": 0.05,
        "Assists": 0.05,
    },
    "Target forward": {
        "Non-penalty goals": 0.22, "npxG": 0.14, "Aerials won": 0.16, "Aerial win %": 0.10,
        "Fouls drawn": 0.06, "Shot-creating actions": 0.10, "Touches in box": 0.08,
        "Assists": 0.08, "xAG": 0.06,
    },
}

# Every metric any role in a position is rated on. Used to compare players
# across roles within a position (similar-player search).
PROFILE_METRICS: dict[str, list[str]] = {
    position: list(dict.fromkeys(m for role in roles for m in RATING_WEIGHTS[role]))
    for position, roles in ROLES.items()
}

MIN_ROLE_POOL = 15  # below this, a role is compared with the whole position instead
SHRINK_MINUTES = 1000  # ratings are pulled toward average for players with few minutes


def metric_values(df: pd.DataFrame, metrics: list[str]) -> pd.DataFrame:
    """Values used for rating: per-90 for counts, raw for rates."""
    counts = [m for m in metrics if m not in NOT_PER90]
    out = df[metrics].astype(float).copy()
    out[counts] = per90(df, counts)
    return out


def _percentile_against(pool: np.ndarray, values: np.ndarray) -> np.ndarray:
    """Percentile (0-100) of each value within a reference pool."""
    pool = np.sort(pool)
    below = np.searchsorted(pool, values, side="left")
    at_or_below = np.searchsorted(pool, values, side="right")
    return 100 * (below + at_or_below) / (2 * len(pool))


def compute_ratings(df: pd.DataFrame) -> tuple[pd.Series, dict[int, dict[str, float]]]:
    """Return (rating per player id, per-metric percentiles per player id).

    Rating: weighted average of z-scores (capped at -3..+4) on the role's
    metrics against qualified players (900+ min) in the same role, shrunk
    toward the average by minutes / (minutes + 1000), then mapped so 50 =
    average qualified player in that role. z-scores let exceptional output
    (e.g. a 29-goal season) count fully, which percentiles would cap at 100.

    Percentiles: per-metric standing within the same pool, for display.
    "Lower is better" metrics are inverted in both.
    """
    ratings = pd.Series(np.nan, index=df["id"], name="Rating")
    percentiles: dict[int, dict[str, float]] = {}

    for role, weights in RATING_WEIGHTS.items():
        group = df[df["Role"] == role]
        if group.empty:
            continue
        metrics = list(weights)
        values = metric_values(group, metrics)
        pool = values[group["Qualified"].to_numpy()]
        if len(pool) < MIN_ROLE_POOL:
            position = df[(df["Position"] == ROLE_INFO[role]["position"]) & df["Qualified"]]
            pool = metric_values(position, metrics) if len(position) >= 2 else values

        mean, std = pool.mean(), pool.std(ddof=0).replace(0, 1)
        pct = pd.DataFrame(index=group.index)
        z = (values - mean) / std
        for metric, weight in weights.items():
            p = _percentile_against(pool[metric].to_numpy(), values[metric].to_numpy())
            pct[metric] = 100 - p if weight < 0 else p
            if weight < 0:
                z[metric] = -z[metric]

        total = sum(abs(w) for w in weights.values())
        composite = sum(z[m].clip(-3, 4) * abs(w) for m, w in weights.items()) / total
        reliability = group["Minutes"] / (group["Minutes"] + SHRINK_MINUTES)
        score = (50 + 25 * composite * reliability).clip(0, 99)
        ratings.loc[group["id"].to_numpy()] = score.round(1).to_numpy()
        for row_idx, pid in zip(group.index, group["id"]):
            percentiles[int(pid)] = {m: round(float(pct.at[row_idx, m]), 1) for m in weights}

    return ratings, percentiles
