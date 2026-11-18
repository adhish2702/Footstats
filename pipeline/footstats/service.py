"""Builds every analysis once and answers queries for the API."""
from __future__ import annotations

from functools import cached_property
from pathlib import Path

import numpy as np
import pandas as pd

from .clusters import overall_agreement, role_agreement
from .data import DEFAULT_CSV, LEAGUES, MIN_MINUTES, NOT_PER90, load_players
from .model import train_and_evaluate
from .ratings import RATING_WEIGHTS, compute_ratings
from .roles import FEATURES, ROLE_INFO, ROLES
from .similar import similar_players

# Clubs that usually do the buying rather than the selling (FBref names).
ELITE_CLUBS = {
    "Arsenal", "Chelsea", "Liverpool", "Manchester City", "Manchester Utd", "Tottenham",
    "Real Madrid", "Barcelona", "Atlético Madrid",
    "Bayern Munich", "Dortmund", "Leverkusen",
    "Inter", "Milan", "Juventus", "Napoli",
    "Paris S-G",
}


def _clean(value):
    """Make numpy/pandas scalars JSON-friendly."""
    if isinstance(value, (np.integer,)):
        return int(value)
    if isinstance(value, (np.floating, float)):
        return None if np.isnan(value) else round(float(value), 3)
    if isinstance(value, (np.bool_,)):
        return bool(value)
    return value


class FootStats:
    def __init__(self, csv_path: str | Path = DEFAULT_CSV):
        self.df = load_players(csv_path)
        ratings, self.percentiles = compute_ratings(self.df)
        self.df["Rating"] = self.df["id"].map(ratings)
        expected = self.report.expected.set_index("id")
        self.df["xGA90"] = self.df["id"].map(expected["expected"])
        # Non-penalty, to match what the model predicts.
        self.df["GA90"] = (self.df["Non-penalty goal contributions"]
                           / self.df["Minutes"].clip(lower=1) * 90)

    @cached_property
    def report(self):
        return train_and_evaluate(self.df)

    @cached_property
    def agreement(self) -> dict[str, dict]:
        return role_agreement(self.df)

    # ---- summaries -------------------------------------------------------
    def _summary(self, row: pd.Series) -> dict:
        return {
            "id": int(row["id"]), "name": row["Player Name"], "club": row["Club"],
            "clubs": row["Clubs"], "league": row["League"],
            "age": None if pd.isna(row["Age"]) else int(row["Age"]),
            "nationality": row["Nationality"], "position": row["Position"],
            "appearances": int(row["Appearances"]), "minutes": int(row["Minutes"]),
            "goals": int(row["Goals"]), "assists": int(row["Assists"]),
            "role": row["Role"], "rating": _clean(row["Rating"]),
            "qualified": bool(row["Qualified"]),
            "ga90": _clean(row["GA90"]), "xga90": _clean(row["xGA90"]),
        }

    def list_players(self, position: str | None = None, club: str | None = None,
                     q: str | None = None, qualified_only: bool = False,
                     sort: str = "rating", limit: int = 3000,
                     league: str | None = None, max_age: int | None = None,
                     role: str | None = None) -> list[dict]:
        d = self._filter(self.df, league, max_age)
        if position:
            d = d[d["Position"] == position.upper()]
        if role:
            d = d[d["Role"] == role]
        if club:
            d = d[d["Club"] == club]
        if q:
            d = d[d["Player Name"].str.contains(q, case=False, regex=False)]
        if qualified_only:
            d = d[d["Qualified"]]
        key = {"rating": "Rating", "minutes": "Minutes", "goals": "Goals",
               "assists": "Assists", "name": "Player Name", "age": "Age"}.get(sort, "Rating")
        d = d.sort_values(key, ascending=key in ("Player Name", "Age"), na_position="last")
        return [self._summary(r) for _, r in d.head(limit).iterrows()]

    def player(self, player_id: int) -> dict:
        rows = self.df[self.df["id"] == player_id]
        if rows.empty:
            raise KeyError(player_id)
        row = rows.iloc[0]
        out = self._summary(row)
        role = row["Role"]
        out["percentiles"] = [
            {"metric": m, "percentile": self.percentiles[player_id][m],
             "weight": abs(w), "lower_is_better": w < 0, "per90": m not in NOT_PER90}
            for m, w in RATING_WEIGHTS[role].items()
        ]
        out["role_plural"] = ROLE_INFO[role]["plural"]
        out["role_description"] = ROLE_INFO[role]["description"]
        out["role_rank"] = self._role_rank(row)
        out["similar"] = similar_players(self.df, player_id)
        out["min_minutes"] = MIN_MINUTES
        return out

    @staticmethod
    def _filter(d: pd.DataFrame, league: str | None, max_age: int | None) -> pd.DataFrame:
        if league:
            d = d[d["League"] == league]
        if max_age:
            d = d[d["Age"].notna() & (d["Age"] <= max_age)]
        return d

    def _role_rank(self, row) -> dict | None:
        """Standing among qualified players in the same role."""
        if not row["Qualified"]:
            return None
        pool = self.df[(self.df["Role"] == row["Role"]) & self.df["Qualified"]]
        rank = int((pool["Rating"] > row["Rating"]).sum()) + 1
        return {"rank": rank, "of": len(pool)}

    def clubs(self, league: str | None = None) -> list[str]:
        d = self.df if not league else self.df[self.df["League"] == league]
        return sorted(d["Club"].unique())

    def leagues(self) -> list[str]:
        return [lg for lg in LEAGUES if lg in set(self.df["League"])]

    # ---- scouting --------------------------------------------------------
    def scouting_targets(self, position: str | None = None, limit: int = 10,
                         league: str | None = None, max_age: int | None = None,
                         role: str | None = None) -> list[dict]:
        """Top-rated qualified players outside Europe's elite clubs: likely transfer targets."""
        d = self._filter(self.df, league, max_age)
        d = d[d["Qualified"] & ~d["Club"].isin(ELITE_CLUBS)]
        if position:
            d = d[d["Position"] == position.upper()]
        if role:
            d = d[d["Role"] == role]
        d = d.sort_values("Rating", ascending=False).head(limit)
        return [self._summary(r) for _, r in d.iterrows()]

    def performance_gaps(self, limit: int = 10, league: str | None = None) -> dict:
        """Biggest gaps between actual and model-expected non-penalty G+A per 90."""
        d = self._filter(self.df, league, None).dropna(subset=["xGA90"]).copy()
        d["gap"] = d["GA90"] - d["xGA90"]

        def fmt(frame):
            return [{**self._summary(r), "gap": round(float(r["gap"]), 3)} for _, r in frame.iterrows()]

        return {
            "underperforming": fmt(d.nsmallest(limit, "gap")),
            "overperforming": fmt(d.nlargest(limit, "gap")),
        }

    # ---- model + roles ------------------------------------------------
    def model_report(self) -> dict:
        r = self.report
        return {
            "target": "Non-penalty goals + assists per 90 (outfield players, 900+ minutes)",
            "xg_mae": r.xg_mae, "xg_r2": r.xg_r2,
            "chosen_model": r.chosen_model, "n_players": r.n_players,
            "n_train": r.n_train, "n_test": r.n_test, "cv_mae": r.cv_mae,
            "test_mae": r.test_mae, "test_r2": r.test_r2,
            "baseline_mae": r.baseline_mae, "error_reduction_pct": r.error_reduction_pct,
            "feature_importance": r.feature_importance[:10],
            "test_points": r.test_points,
        }

    def roles_report(self) -> dict:
        """Roles per position, how each is recognised and rated, and the K-Means check."""
        qualified = self.df[self.df["Qualified"]]
        positions = []
        for position, roles in ROLES.items():
            entries = []
            for role in roles:
                info = ROLE_INFO[role]
                members = qualified[qualified["Role"] == role]
                entries.append({
                    "role": role, "plural": info["plural"], "description": info["description"],
                    "size": int(len(members)),
                    "more_of": [s for s, sign in info["signals"].items() if sign > 0],
                    "less_of": [s for s, sign in info["signals"].items() if sign < 0],
                    "weights": [{"metric": m, "weight": abs(w), "lower_is_better": w < 0}
                                for m, w in RATING_WEIGHTS[role].items()],
                    "examples": members.nlargest(3, "Rating")["Player Name"].tolist(),
                })
            positions.append({"position": position, "roles": entries,
                              "check": self.agreement.get(position)})
        return {"positions": positions, "agreement": overall_agreement(self.agreement),
                "signals": len(FEATURES)}

    def overview(self) -> dict:
        d = self.df
        return {
            "players": len(d), "qualified": int(d["Qualified"].sum()),
            "clubs": d["Club"].nunique(), "season": "2024/25",
            "leagues": d["League"].value_counts().reindex(self.leagues()).to_dict(),
            "positions": d["Position"].value_counts().to_dict(),
            "roles": d["Role"].value_counts().to_dict(),
        }
