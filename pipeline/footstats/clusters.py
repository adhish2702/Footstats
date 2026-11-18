"""Check the roles against an unsupervised grouping.

Roles are assigned by hand-written rules (roles.py). As a sanity check, K-Means
is run on the same style signals, with no knowledge of the roles, asking for as
many groups as the position has roles. If the roles describe real differences
in how people play, the two should agree well above chance. They never agree
perfectly: playing styles blend into each other rather than forming hard boxes.
"""
from __future__ import annotations

import numpy as np
import pandas as pd
from scipy.optimize import linear_sum_assignment
from sklearn.cluster import KMeans
from sklearn.metrics import silhouette_score

from .roles import FULL_BACK_SIGNALS, ROLE_INFO, ROLES, role_features


def position_signals(position: str) -> list[str]:
    """Every style signal used to tell the position's roles apart."""
    names = [s for role in ROLES[position] for s in ROLE_INFO[role]["signals"]]
    if position == "DEF":
        names += list(FULL_BACK_SIGNALS)
    return list(dict.fromkeys(names))


def role_agreement(df: pd.DataFrame, seed: int = 42) -> dict[str, dict]:
    """Per position: how well K-Means clusters line up with the assigned roles.

    agreement: share of qualified players whose cluster, after matching each
        cluster to one role, is their own role.
    chance: what random groups of the same sizes would score (the sum of
        squared role shares).
    silhouette: how separate the K-Means clusters are (-1 to 1; around 0.1-0.2
        means heavy overlap).
    """
    out: dict[str, dict] = {}
    for position, roles in ROLES.items():
        group = df[(df["Position"] == position) & df["Qualified"]]
        if len(group) < 10 * len(roles):
            continue
        X = role_features(group)[position_signals(position)]
        X = ((X - X.mean()) / X.std(ddof=0).replace(0, 1)).clip(-3, 3).to_numpy()
        labels = KMeans(n_clusters=len(roles), random_state=seed, n_init=10).fit_predict(X)

        table = pd.crosstab(labels, group["Role"].to_numpy()).reindex(columns=roles, fill_value=0)
        rows, cols = linear_sum_assignment(-table.to_numpy())
        matched = table.to_numpy()[rows, cols].sum()
        shares = group["Role"].value_counts(normalize=True)
        out[position] = {
            "k": len(roles),
            "agreement": round(float(matched / len(group)), 3),
            "chance": round(float((shares ** 2).sum()), 3),
            "silhouette": round(float(silhouette_score(X, labels)), 3),
            "players": int(len(group)),
        }
    return out


def overall_agreement(report: dict[str, dict]) -> float:
    """Agreement across all positions, weighted by number of players."""
    total = sum(r["players"] for r in report.values())
    return round(float(np.sum([r["agreement"] * r["players"] for r in report.values()]) / total), 3)
