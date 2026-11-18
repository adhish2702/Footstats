"""Expected goal contributions model.

Predicts an outfield player's non-penalty goals + assists per 90 from how they
play (shots, touches, passes into the final third, carries, ...) without using
the goals or assists themselves. The gap between expected and actual output
flags players who are over- or under-performing their underlying numbers.

Penalty goals are excluded from the target: none of the inputs can tell who
takes penalties (FBref shot counts exclude them), so counting them would make
every penalty taker look like an over-performer.
"""
from __future__ import annotations

from dataclasses import dataclass

import numpy as np
import pandas as pd
from sklearn.base import clone
from sklearn.dummy import DummyRegressor
from sklearn.ensemble import RandomForestRegressor
from sklearn.linear_model import RidgeCV
from sklearn.metrics import mean_absolute_error, r2_score
from sklearn.model_selection import KFold, cross_val_predict, cross_val_score, train_test_split
from sklearn.pipeline import make_pipeline
from sklearn.preprocessing import StandardScaler

from .data import FORWARD_POSITIONS, LEAGUES, per90

# Process stats only: nothing that counts or estimates a goal or an assist
# (no goals, assists, xG, xAG or goal-creating actions).
FEATURES = [
    "Shots", "Shots on target", "Touches", "Touches in box", "Key passes",
    "Passes into box", "Passes into final third", "Progressive passes",
    "Progressive carries", "Progressive receptions", "Carries into box",
    "Successful take-ons", "Shot-creating actions", "Crosses", "Through balls",
    "Miscontrols", "Dispossessed", "Ball recoveries", "Aerials won",
]
TARGET_COLUMN = "Non-penalty goal contributions"
TARGET = "npG+A per 90"
SEED = 42


def candidate_models() -> dict:
    return {
        "Ridge regression": make_pipeline(StandardScaler(), RidgeCV(alphas=np.logspace(-2, 3, 20))),
        "Random forest": RandomForestRegressor(n_estimators=400, min_samples_leaf=3, random_state=SEED, n_jobs=-1),
    }


def build_xy(df: pd.DataFrame) -> tuple[pd.DataFrame, pd.Series, pd.DataFrame]:
    """Features and target for qualified outfield players."""
    rows = df[df["Qualified"] & (df["Position"] != "GKP")]
    X = per90(rows, FEATURES)
    X["is_FWD"] = rows["Position"].isin(FORWARD_POSITIONS).astype(int)
    X["is_MID"] = (rows["Position"] == "MID").astype(int)
    for league in LEAGUES[1:]:
        X[f"league_{league}"] = (rows["League"] == league).astype(int)
    y = per90(rows, [TARGET_COLUMN])[TARGET_COLUMN].rename(TARGET)
    return X, y, rows


def _importance_shares(model) -> np.ndarray:
    """Share (0-1) of the model's decisions attributable to each input.

    Random forest: impurity-based importance. Ridge: absolute standardised
    coefficients. Both are normalised to sum to 1.
    """
    if hasattr(model, "feature_importances_"):
        raw = model.feature_importances_
    else:
        raw = np.abs(model[-1].coef_)
    return raw / raw.sum()


@dataclass
class ModelReport:
    chosen_model: str
    n_players: int
    n_train: int
    n_test: int
    cv_mae: dict[str, float]
    test_mae: float
    test_r2: float
    baseline_mae: float
    error_reduction_pct: float
    xg_mae: float                    # FBref npxG + xAG per 90 on the same test players
    xg_r2: float
    feature_importance: list[dict]
    test_points: list[dict]          # actual vs predicted on the held-out set
    expected: pd.DataFrame           # out-of-fold expected npG+A per 90 for every player


def train_and_evaluate(df: pd.DataFrame) -> ModelReport:
    X, y, rows = build_xy(df)
    X_tr, X_te, y_tr, y_te, ids_tr, ids_te = train_test_split(
        X, y, rows["id"], test_size=0.2, random_state=SEED
    )
    kf = KFold(n_splits=5, shuffle=True, random_state=SEED)

    # 1. Choose the model with 5-fold cross-validation on the training split only.
    cv_mae = {
        name: round(float(-cross_val_score(m, X_tr, y_tr, cv=kf, scoring="neg_mean_absolute_error").mean()), 4)
        for name, m in candidate_models().items()
    }
    chosen = min(cv_mae, key=cv_mae.get)
    model = clone(candidate_models()[chosen]).fit(X_tr, y_tr)

    # 2. Score it once on the untouched 20% test split.
    pred = np.clip(model.predict(X_te), 0, None)  # output can't be negative
    baseline = DummyRegressor().fit(X_tr, y_tr).predict(X_te)
    test_mae = float(mean_absolute_error(y_te, pred))
    # Reference point: the professional expected-goals model (npxG + xAG from FBref/Opta),
    # non-penalty to match the target.
    xg = per90(rows, ["npxG", "xAG"]).sum(axis=1).loc[X_te.index]
    base_mae = float(mean_absolute_error(y_te, baseline))

    importance = sorted(
        ({"feature": f, "importance": round(float(v), 4)} for f, v in zip(X.columns, _importance_shares(model))),
        key=lambda d: d["importance"], reverse=True,
    )

    # 3. Expected output for every player, each predicted by a model that never saw them.
    oof = np.clip(cross_val_predict(clone(candidate_models()[chosen]), X, y, cv=kf), 0, None)
    expected = pd.DataFrame({"id": rows["id"].to_numpy(), "expected": oof, "actual": y.to_numpy()})

    lookup = df.set_index("id")
    test_points = [
        {"id": int(i), "name": lookup.at[i, "Player Name"], "position": lookup.at[i, "Position"],
         "actual": round(float(a), 3), "predicted": round(float(p), 3)}
        for i, a, p in zip(ids_te, y_te, pred)
    ]

    return ModelReport(
        chosen_model=chosen, n_players=len(X), n_train=len(X_tr), n_test=len(X_te),
        cv_mae=cv_mae, test_mae=round(test_mae, 4), test_r2=round(float(r2_score(y_te, pred)), 3),
        baseline_mae=round(base_mae, 4),
        error_reduction_pct=round(100 * (1 - test_mae / base_mae), 1),
        xg_mae=round(float(mean_absolute_error(y_te, xg)), 4),
        xg_r2=round(float(r2_score(y_te, xg)), 3),
        feature_importance=importance, test_points=test_points, expected=expected,
    )
