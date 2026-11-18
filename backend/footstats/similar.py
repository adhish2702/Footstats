"""Find statistically similar players (useful for replacement scouting)."""
from __future__ import annotations

import numpy as np
import pandas as pd
from sklearn.preprocessing import StandardScaler

from .ratings import PROFILE_METRICS, metric_values


def similar_players(df: pd.DataFrame, player_id: int, n: int = 5) -> list[dict]:
    """Return the n most similar qualified players in the same position.

    Similarity is cosine similarity of standardised per-90 rating metrics,
    reported on a 0-100 scale.
    """
    player = df.loc[df["id"] == player_id]
    if player.empty:
        raise KeyError(player_id)
    position = player["Position"].iloc[0]

    pool = df[(df["Position"] == position) & (df["Qualified"] | (df["id"] == player_id))]
    X = StandardScaler().fit_transform(metric_values(pool, PROFILE_METRICS[position]))
    X = X / np.clip(np.linalg.norm(X, axis=1, keepdims=True), 1e-9, None)

    target = X[pool["id"].to_numpy() == player_id][0]
    sims = X @ target
    ranked = pd.DataFrame({"id": pool["id"].to_numpy(), "sim": sims})
    ranked = ranked[ranked["id"] != player_id].nlargest(n, "sim")

    lookup = df.set_index("id")
    return [
        {
            "id": int(r.id),
            "name": lookup.at[r.id, "Player Name"],
            "club": lookup.at[r.id, "Club"],
            "league": lookup.at[r.id, "League"],
            "similarity": round(float((r.sim + 1) * 50), 1),
        }
        for r in ranked.itertuples()
    ]
