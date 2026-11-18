"""Step 3: turn the clusters into a recruitment tool.

Built on clustering_engine.py (style vectors, clusters, archetype names) and
ratings.py (the position-specific composite score, 0-99).

Two parts:

1. Similarity. Cosine similarity between standardised style vectors, within a
   positional group (FWD, MID, DEF, GKP). find_similar_players() returns the
   closest stylistic matches to a named player across all five leagues.

2. Value. The FBref data has no prices, so market_values.py attaches each
   player's Transfermarkt value at the end of 2024/25. A model predicts (log)
   market value from age, minutes, league, position and the composite score, and

       Value_Gap = predicted market value - actual market value

   in euros. A large positive gap is a player the market prices below what his
   age, playing time and performance would normally fetch.
   get_undervalued_gems() returns young players near the top of their tactical
   cluster with the largest gaps.

   Without prices (mode="efficiency", or if the values file is missing) the
   model instead predicts the composite score from age, minutes, league and
   position, and Value_Gap = actual - expected score in rating points.

Ridge regression, a random forest and XGBoost are compared either way, and
SHAP values explain what drives the chosen model.

Run:  python -m footstats.scouting_models            (from the backend folder)
"""
from __future__ import annotations

import argparse
import re
import unicodedata
from dataclasses import dataclass, field
from functools import lru_cache
from pathlib import Path

import numpy as np
import pandas as pd
from sklearn.base import clone
from sklearn.dummy import DummyRegressor
from sklearn.ensemble import RandomForestRegressor
from sklearn.linear_model import RidgeCV
from sklearn.metrics import mean_absolute_error, r2_score
from sklearn.metrics.pairwise import cosine_similarity
from sklearn.model_selection import KFold, cross_val_predict, cross_val_score, train_test_split
from sklearn.pipeline import Pipeline, make_pipeline
from sklearn.preprocessing import StandardScaler
from xgboost import XGBRegressor

from . import clustering_engine as ce
from .data import DEFAULT_CSV, LEAGUES, NOT_PER90, POSITIONS, load_players, per90
from .market_values import load_market_values
from .ratings import compute_ratings
from .service import ELITE_CLUBS

SEED = 42
DEFAULT_OUT = Path(__file__).resolve().parents[1] / "outputs" / "scouting"
# Below this a composite score is mostly shrinkage toward 50, so the player is
# left out of the value model and has no Value_Gap.
VALUE_MIN_MINUTES = 500
TOP_PERCENTILE = 75.0  # a "gem" is in the top quarter of his cluster by composite score

# Shown next to each match so a result can be judged without opening the data.
# Counts are per 90 minutes; rates are percentages.
KEY_STATS = {
    "FWD": ["Non-penalty goals", "npxG", "xAG", "Shots", "Shot-creating actions",
            "Successful take-ons"],
    "MID": ["Progressive passes", "Key passes", "xAG", "Tackles won", "Interceptions",
            "Pass accuracy"],
    "DEF": ["Tackles won", "Interceptions", "Clearances", "Progressive passes",
            "Aerial win %", "Pass accuracy"],
    "GKP": ["Goals prevented", "Save %", "Crosses stopped %", "Sweeper actions",
            "Pass accuracy", "Launch %"],
}


# ---- names --------------------------------------------------------------------------------
_LETTERS = str.maketrans({"ø": "o", "Ø": "O", "đ": "d", "Đ": "D", "ł": "l", "Ł": "L",
                          "ß": "ss", "æ": "ae", "Æ": "AE", "ı": "i"})


def _fold(text: str) -> str:
    """Lower-case and strip accents, so "Odegaard" finds "Ødegaard"."""
    text = unicodedata.normalize("NFKD", str(text).translate(_LETTERS))
    return "".join(c for c in text if not unicodedata.combining(c)).lower().strip()


def _stat_label(metric: str) -> str:
    if metric in NOT_PER90:
        return metric if metric.endswith("%") else f"{metric} %"
    return f"{metric} /90"


def key_stats(df: pd.DataFrame, group: str) -> pd.DataFrame:
    """The group's key stats for the rows of df (per 90, or % for rates)."""
    metrics = KEY_STATS[group]
    counts = [m for m in metrics if m not in NOT_PER90]
    out = per90(df, counts).round(2)
    for m in metrics:
        if m in NOT_PER90:
            out[m] = (df[m] * 100).round(1)
    return out[metrics].rename(columns=_stat_label)


# ---- 1. style vectors and similarity --------------------------------------------------------
def style_vectors(df: pd.DataFrame, clustering: ce.ClusteringResult) -> dict[str, pd.DataFrame]:
    """Standardised style vectors for every player, indexed by player id.

    The clustering engine only scales and clusters players with 900+ minutes.
    Everyone else is put on the same scale here (the 900+ players' mean and
    standard deviation), so a lower-minute player can still be searched for or
    returned as a match without changing what a z-score means.
    """
    _, raw = ce.build_frames(df, clustering.possession, min_minutes=0)
    vectors = {}
    for group, r in clustering.groups.items():
        reference = raw[group].loc[r.scaled.index]
        mean, std = reference.mean(), reference.std(ddof=0).replace(0, 1)
        features = raw[group].replace([np.inf, -np.inf], np.nan).fillna(mean)
        vectors[group] = (features - mean) / std
    return vectors


def assign_clusters(vectors: pd.DataFrame, r: ce.GroupResult) -> pd.Series:
    """Cluster number for every player in the group.

    Players the engine clustered keep their K-Means label; the rest go to the
    nearest cluster centre.
    """
    centres = r.scaled.groupby(r.labels).mean()
    distance = ((vectors.to_numpy()[:, None, :] - centres.to_numpy()[None, :, :]) ** 2).sum(axis=2)
    labels = pd.Series(centres.index.to_numpy()[distance.argmin(axis=1)], index=vectors.index)
    labels.loc[r.labels.index] = r.labels
    return labels.astype(int)


def similarity_matrix(vectors: pd.DataFrame) -> pd.DataFrame:
    """Pairwise cosine similarity (-1 to 1) between every pair of players in a group."""
    return pd.DataFrame(cosine_similarity(vectors.to_numpy()),
                        index=vectors.index, columns=vectors.index)


# ---- 2. the value model -----------------------------------------------------------------------
VALUE_PATTERN = re.compile(
    r"market|valuation|transfer.?(value|fee)|(^|[_ ])value([_ ]|$)|price|wage|salary", re.I)


def find_value_column(csv_path: str | Path = DEFAULT_CSV) -> str | None:
    """Name of a market-value column in the source CSV, or None if there isn't one."""
    columns = pd.read_csv(csv_path, nrows=0, encoding="utf-8-sig").columns
    return next((c for c in columns if VALUE_PATTERN.search(c)), None)


def values_from_column(df: pd.DataFrame, csv_path: str | Path, column: str) -> pd.Series:
    """Market value per player id. A player listed at two clubs takes the higher figure."""
    raw = pd.read_csv(csv_path, encoding="utf-8-sig")
    rows = pd.DataFrame({"Player Name": raw["Player"].str.strip(),
                         "Born": raw["Born"].fillna(-1).astype(int),
                         "value": pd.to_numeric(raw[column], errors="coerce")})
    by_player = rows.groupby(["Player Name", "Born"])["value"].max()
    keys = pd.MultiIndex.from_frame(df[["Player Name", "Born"]])
    return pd.Series(by_player.reindex(keys).to_numpy(), index=df["id"].to_numpy(), name=column)


def value_candidates() -> dict:
    """The three models compared. Age, minutes and league carry little signal,
    so the tree models are kept shallow to stop them fitting noise."""
    return {
        "Ridge regression": make_pipeline(StandardScaler(), RidgeCV(alphas=np.logspace(-2, 4, 25))),
        "Random forest": RandomForestRegressor(n_estimators=300, min_samples_leaf=15,
                                               max_features=0.5, random_state=SEED, n_jobs=-1),
        "XGBoost": XGBRegressor(n_estimators=300, max_depth=3, learning_rate=0.03,
                                subsample=0.8, colsample_bytree=0.8, min_child_weight=10,
                                reg_lambda=5.0, random_state=SEED),
    }


def design_matrix(players: pd.DataFrame, with_composite: bool) -> tuple[pd.DataFrame, dict[str, list[str]]]:
    """Model inputs, and which columns belong to which feature (for grouping SHAP values).

    Age squared lets the linear model bend (players peak, then decline); the
    two age columns are reported together as "Age".
    """
    age = players["Age"].astype(float)
    age = age.fillna(age.median())
    X = pd.DataFrame({"Age": age, "Age squared": age ** 2,
                      "Minutes": players["Minutes"].astype(float)}, index=players.index)
    groups = {"Age": ["Age", "Age squared"], "Minutes": ["Minutes"], "League": [], "Position": []}
    for league in LEAGUES:
        X[f"League: {league}"] = (players["League"] == league).astype(float)
        groups["League"].append(f"League: {league}")
    for position in POSITIONS:
        X[f"Position: {position}"] = (players["Pos"] == position).astype(float)
        groups["Position"].append(f"Position: {position}")
    if with_composite:
        X["Composite score"] = players["Composite_Score"].astype(float)
        groups["Composite score"] = ["Composite score"]
    return X, groups


def shap_values(model, X: pd.DataFrame) -> tuple[pd.DataFrame, float]:
    """SHAP value of every feature for every player, and the model's average prediction.

    For each player, base value + the row's SHAP values = the model's prediction.
    """
    import shap

    if isinstance(model, Pipeline):  # scaled linear model: explain it on the scaled inputs
        Z = pd.DataFrame(model[:-1].transform(X), index=X.index, columns=X.columns)
        background = shap.maskers.Independent(Z, max_samples=len(Z))  # every player, not a sample
        explanation = shap.LinearExplainer(model[-1], background)(Z)
    else:
        explanation = shap.TreeExplainer(model)(X)
    base = float(np.ravel(explanation.base_values)[0])
    return pd.DataFrame(explanation.values, index=X.index, columns=X.columns), base


@dataclass
class ValueModel:
    mode: str                  # "efficiency" or "market_value"
    target: str                # what the model predicts
    unit: str                  # unit of the SHAP values and errors
    value_column: str | None
    comparison: pd.DataFrame   # one row per model, plus the predict-the-mean baseline
    best: str
    model: object              # the chosen model, fitted on every player
    X: pd.DataFrame
    groups: dict[str, list[str]]
    expected: pd.Series        # out-of-fold prediction per player, in target units
    shap: pd.DataFrame
    base_value: float

    def shap_by_feature(self) -> pd.DataFrame:
        """SHAP values with one-hot columns (and the two age columns) added together."""
        return pd.DataFrame({name: self.shap[cols].sum(axis=1) for name, cols in self.groups.items()})

    def importance(self) -> pd.DataFrame:
        """Mean absolute SHAP value per feature and per column, largest first."""
        grouped = self.shap_by_feature().abs().mean()
        columns = self.shap.abs().mean()
        rows = [{"level": "feature", "name": n, "mean_abs_shap": v} for n, v in grouped.items()]
        rows += [{"level": "column", "name": n, "mean_abs_shap": v} for n, v in columns.items()]
        table = pd.DataFrame(rows).sort_values(["level", "mean_abs_shap"], ascending=[False, False])
        return table.round({"mean_abs_shap": 4}).reset_index(drop=True)


def fit_value_model(players: pd.DataFrame, values: pd.Series | None = None,
                    value_column: str | None = None) -> ValueModel:
    """Compare the three models, keep the best, and predict every player out of fold.

    players: rows to model (already filtered by minutes), with Composite_Score.
    values:  market value per player, if there is one. Without it the model
             predicts the composite score itself (the efficiency model).

    The model is chosen by 5-fold cross-validated error on an 80% training
    split and reported on the held-out 20%. The expected value used for the
    value gap is always an out-of-fold prediction, so no player's gap comes
    from a model that was trained on that player.
    """
    market = values is not None
    if market:
        players = players[values.reindex(players.index).gt(0)]
        y = np.log10(values.reindex(players.index).astype(float))
        target, unit = "log10 market value", "log10 value"
    else:
        y = players["Composite_Score"].astype(float)
        target, unit = "Composite score", "rating points"
    X, groups = design_matrix(players, with_composite=market)

    X_train, X_test, y_train, y_test = train_test_split(X, y, test_size=0.2, random_state=SEED)
    folds = KFold(n_splits=5, shuffle=True, random_state=SEED)
    candidates = {"Baseline (training mean)": DummyRegressor(), **value_candidates()}
    rows = []
    for name, model in candidates.items():
        cv = -cross_val_score(model, X_train, y_train, cv=folds,
                              scoring="neg_mean_absolute_error").mean()
        prediction = clone(model).fit(X_train, y_train).predict(X_test)
        rows.append({"model": name, "cv_mae": cv,
                     "test_mae": mean_absolute_error(y_test, prediction),
                     "test_r2": r2_score(y_test, prediction)})
    comparison = pd.DataFrame(rows).set_index("model").round(4)
    best = comparison["cv_mae"].drop("Baseline (training mean)").idxmin()
    comparison["chosen"] = comparison.index == best

    chosen = value_candidates()[best]
    expected = pd.Series(cross_val_predict(clone(chosen), X, y, cv=folds), index=X.index)
    model = clone(chosen).fit(X, y)
    shap, base = shap_values(model, X)
    return ValueModel(mode="market_value" if market else "efficiency", target=target, unit=unit,
                      value_column=value_column, comparison=comparison, best=best, model=model,
                      X=X, groups=groups, expected=expected, shap=shap, base_value=base)


def upper_fence(values: pd.Series) -> float:
    """Tukey's rule: anything above Q3 + 1.5 x IQR is an outlier on the high side."""
    q1, q3 = values.quantile([0.25, 0.75])
    return float(q3 + 1.5 * (q3 - q1))


# ---- the engine ---------------------------------------------------------------------------------
@dataclass
class ScoutingEngine:
    players: pd.DataFrame                 # one row per player, indexed by id
    stats: pd.DataFrame                   # the loader's full table, indexed by id
    vectors: dict[str, pd.DataFrame]      # group -> standardised style vectors
    similarity: dict[str, pd.DataFrame]   # group -> pairwise cosine similarity
    value: ValueModel
    clustering: ce.ClusteringResult = field(repr=False)

    @classmethod
    def build(cls, csv_path: str | Path = DEFAULT_CSV, clustering: ce.ClusteringResult | None = None,
              values: pd.Series | None = None, min_minutes: int = VALUE_MIN_MINUTES,
              mode: str = "auto") -> "ScoutingEngine":
        """Build everything once.

        Market values are looked for in this order: the values argument (per
        player id), a value column in the CSV, then the Transfermarkt file
        written by market_values.py. mode="efficiency" ignores all three and
        fits the efficiency model; mode="market_value" insists on prices.
        """
        if mode not in ("auto", "efficiency", "market_value"):
            raise ValueError(f"unknown mode {mode!r}")
        df = load_players(csv_path)
        clustering = clustering or ce.run(csv_path)
        column = None
        if mode == "efficiency":
            values = None
        elif values is not None:
            column = values.name or "value"
        else:
            column = find_value_column(csv_path)
            if column:
                values = values_from_column(df, csv_path, column)
            else:
                values = load_market_values(df)
                column = None if values is None else values.name
        if mode == "market_value" and values is None:
            raise FileNotFoundError("no market values: run python -m footstats.market_values first")

        stats = df.set_index("id")
        players = stats[list(ce.METADATA.values())].rename(
            columns={v: k for k, v in ce.METADATA.items()})
        players["Group"] = players["Pos"].map(ce.POSITION_GROUP)
        players["Role"] = stats["Role"]
        players["Composite_Score"] = compute_ratings(df)[0].to_numpy()

        vectors = style_vectors(df, clustering)
        players["Cluster_ID"] = pd.concat(
            [assign_clusters(vectors[g], r) for g, r in clustering.groups.items()])
        names = {(g, c): n for g, r in clustering.groups.items() for c, n in r.names.items()}
        players["Cluster"] = [names[key] for key in zip(players["Group"], players["Cluster_ID"])]
        # False for players under 900 minutes, whose cluster is the nearest centre.
        players["Clustered"] = players.index.isin(clustering.metadata.index)

        model = fit_value_model(players[players["Minutes"] >= min_minutes], values, column)
        modelled = model.expected.index
        if model.mode == "market_value":
            players["Market_Value"] = values.reindex(players.index).astype(float).round().astype("Int64")
            players["Predicted_Value"] = (10 ** model.expected).round(-4).reindex(
                players.index).astype("Int64")
            players["Value_Gap"] = players["Predicted_Value"] - players["Market_Value"]
            # Predicted / actual: 2.0 means the model would price him at twice his value.
            players["Value_Ratio"] = (players["Predicted_Value"].astype(float)
                                      / players["Market_Value"].astype(float)).round(2)
            # Outliers are judged on the ratio: a gap of 10m euros is huge for a
            # 5m player and nothing for a 150m one.
            players["Gap_Outlier"] = players["Value_Ratio"] > 10 ** upper_fence(
                np.log10(players.loc[modelled, "Value_Ratio"]))
        else:
            players.loc[modelled, "Expected_Score"] = model.expected.round(1)
            players["Value_Gap"] = (players["Composite_Score"] - players["Expected_Score"]).round(1)
            players["Gap_Outlier"] = players["Value_Gap"] > upper_fence(players.loc[modelled, "Value_Gap"])
        # Where a player's composite score ranks inside his own cluster (0-100).
        regulars = players.index[players["Minutes"] >= min_minutes]
        players.loc[regulars, "Cluster_Percentile"] = (
            players.loc[regulars].groupby(["Group", "Cluster_ID"])["Composite_Score"]
            .rank(pct=True).mul(100).round(1))

        return cls(players=players, stats=stats, vectors=vectors,
                   similarity={g: similarity_matrix(v) for g, v in vectors.items()},
                   value=model, clustering=clustering)

    # -- looking a player up ---------------------------------------------------------------------
    def player_id(self, player_name: str, squad: str | None = None) -> int:
        """Id of the named player. Accents and case are ignored; part of a name is enough
        when only one player matches. squad separates two players with the same name."""
        folded = self.players["Player"].map(_fold)
        wanted = _fold(player_name)
        match = folded == wanted
        if not match.any():
            match = folded.str.contains(wanted, regex=False)
        if squad:
            match &= self.players["Squad"].map(_fold).str.contains(_fold(squad), regex=False)
        found = self.players[match]
        if found.empty:
            raise KeyError(f"no player matching {player_name!r}" + (f" at {squad!r}" if squad else ""))
        if len(found) > 1:
            options = ", ".join(f"{r.Player} ({r.Squad})" for r in found.head(8).itertuples())
            raise ValueError(f"{player_name!r} matches {len(found)} players: {options}. "
                             "Give the full name, or pass squad=.")
        return int(found.index[0])

    def _columns(self) -> list[str]:
        if self.value.mode == "market_value":
            value = ["Market_Value", "Predicted_Value", "Value_Gap", "Value_Ratio"]
        else:
            value = ["Expected_Score", "Value_Gap"]
        return ["Player", "Squad", "League", "Pos", "Age", "Minutes", "Cluster", "Cluster_ID",
                "Composite_Score", *value]

    # -- 1. similarity ----------------------------------------------------------------------------
    def find_similar_players(self, player_name: str, top_n: int = 10, max_age: int | None = None,
                             min_minutes: int = 500, leagues: list[str] | str | None = None,
                             *, squad: str | None = None) -> pd.DataFrame:
        """The top_n players whose style is closest to player_name's.

        Candidates come from the same positional group in all five leagues,
        optionally limited by age, minutes and league. Similarity_% is cosine
        similarity x 100 between standardised style vectors: 100 is an identical
        profile, 0 is unrelated. Each row also carries the tactical cluster, the
        composite score, the value gap and the group's key stats. The player
        searched for is described in the result's .attrs["query"].
        """
        pid = self.player_id(player_name, squad)
        group = self.players.at[pid, "Group"]
        scores = self.similarity[group].loc[pid].drop(pid)
        pool = self.players.loc[scores.index]
        keep = pool["Minutes"] >= min_minutes
        if max_age is not None:
            keep &= (pool["Age"] <= max_age).fillna(False).astype(bool)
        if leagues is not None:
            wanted = {_fold(x) for x in ([leagues] if isinstance(leagues, str) else leagues)}
            unknown = wanted - {_fold(x) for x in LEAGUES}
            if unknown:
                raise ValueError(f"unknown league(s): {sorted(unknown)}; use {LEAGUES}")
            keep &= pool["League"].map(_fold).isin(wanted)
        top = scores[keep].nlargest(top_n)

        table = self.players.loc[top.index, self._columns()].copy()
        table.insert(6, "Similarity_%", (top * 100).round(1))
        table = table.join(key_stats(self.stats.loc[top.index], group))
        query = self.players.loc[pid, self._columns()].to_dict()
        query.update(key_stats(self.stats.loc[[pid]], group).iloc[0].to_dict())
        table.attrs["query"] = {"id": pid, "Group": group, **query}
        return table.rename_axis("id")

    # -- 2. gems ------------------------------------------------------------------------------------
    def get_undervalued_gems(self, position: str, cluster_id: int | str | None = None,
                             max_age: int | None = 24, top_n: int = 15, *,
                             min_cluster_percentile: float = TOP_PERCENTILE,
                             exclude_elite_clubs: bool = False) -> pd.DataFrame:
        """Young players near the top of their tactical cluster with the largest value gap.

        position:   FWD, MID, DEF or GKP (WNG or STR narrows FWD to wingers or strikers).
        cluster_id: a cluster number within the group, or its archetype name; None for all.
        Only players with a positive gap and a composite score in the top
        (100 - min_cluster_percentile)% of their cluster are returned, largest gap first.
        exclude_elite_clubs drops players already at Europe's biggest buying clubs.
        """
        position = position.upper()
        pool = self.players[self.players["Value_Gap"].notna()]
        if position in self.vectors:
            pool = pool[pool["Group"] == position]
        elif position in ce.POSITION_GROUP:
            pool = pool[pool["Pos"] == position]
        else:
            raise ValueError(f"unknown position {position!r}; use {', '.join(ce.GROUPS)}, WNG or STR")
        if cluster_id is not None:
            group = ce.POSITION_GROUP.get(position, position)
            names = self.clustering.groups[group].names
            if isinstance(cluster_id, str) and not cluster_id.isdigit():
                by_name = {_fold(n): c for c, n in names.items()}
                if _fold(cluster_id) not in by_name:
                    raise ValueError(f"no {group} cluster called {cluster_id!r}; "
                                     f"use one of {list(names.values())}")
                cluster_id = by_name[_fold(cluster_id)]
            elif int(cluster_id) not in names:
                raise ValueError(f"{group} has clusters {sorted(names)}, not {cluster_id}")
            pool = pool[pool["Cluster_ID"] == int(cluster_id)]
        if max_age is not None:
            pool = pool[(pool["Age"] <= max_age).fillna(False).astype(bool)]
        if exclude_elite_clubs:
            pool = pool[~pool["Squad"].isin(ELITE_CLUBS)]
        pool = pool[(pool["Cluster_Percentile"] >= min_cluster_percentile) & (pool["Value_Gap"] > 0)]
        top = pool.nlargest(top_n, "Value_Gap")
        return top[[*self._columns(), "Cluster_Percentile", "Gap_Outlier"]].rename_axis("id")

    def value_table(self) -> pd.DataFrame:
        """Every modelled player with expected value and value gap, largest gap first."""
        table = self.players[self.players["Value_Gap"].notna()]
        columns = [*self._columns(), "Cluster_Percentile", "Gap_Outlier", "Role", "Clustered"]
        return table[columns].sort_values("Value_Gap", ascending=False).rename_axis("id")


# ---- the two functions, on a shared engine ----------------------------------------------------------
@lru_cache(maxsize=1)
def default_engine() -> ScoutingEngine:
    """The engine for the bundled data, built on first use (takes a few seconds)."""
    return ScoutingEngine.build()


def find_similar_players(player_name: str, top_n: int = 10, max_age: int | None = None,
                         min_minutes: int = 500, leagues: list[str] | str | None = None,
                         *, squad: str | None = None) -> pd.DataFrame:
    """Closest stylistic matches to a player. See ScoutingEngine.find_similar_players."""
    return default_engine().find_similar_players(player_name, top_n, max_age, min_minutes,
                                                 leagues, squad=squad)


def get_undervalued_gems(position: str, cluster_id: int | str | None = None,
                         max_age: int | None = 24, top_n: int = 15, **options) -> pd.DataFrame:
    """Young, top-of-cluster players with the largest value gap. See ScoutingEngine.get_undervalued_gems."""
    return default_engine().get_undervalued_gems(position, cluster_id, max_age, top_n, **options)


# ---- plots ----------------------------------------------------------------------------------------
SURFACE, INK, MUTED, SERIES, GRID, AXIS = "#fcfcfb", "#0b0b0b", "#52514e", "#2a78d6", "#e4e3df", "#c9c8c3"


def _style(ax, grid_axis: str = "y") -> None:
    ax.set_facecolor(SURFACE)
    ax.grid(axis=grid_axis, color=GRID, linewidth=0.8)
    ax.set_axisbelow(True)
    for side in ("top", "right", "left", "bottom"):
        ax.spines[side].set_visible(False)
    ax.tick_params(colors=MUTED, labelsize=9, length=0)


def _what(model: ValueModel) -> str:
    return "market value" if model.mode == "market_value" else "expected composite score"


def _scale_note(model: ValueModel) -> str:
    """Market value is modelled on a log scale; say what a step on it means."""
    return " (+0.30 doubles the value)" if model.mode == "market_value" else ""


def plot_shap_importance(model: ValueModel, path: str | Path) -> Path:
    """Mean absolute SHAP value: by feature (left) and by model column (right)."""
    import matplotlib

    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    importance = model.importance()
    panels = [("By feature", importance[importance["level"] == "feature"]),
              ("By model input", importance[importance["level"] == "column"])]
    fig, axes = plt.subplots(1, 2, figsize=(12.5, 5.2), facecolor=SURFACE,
                             gridspec_kw={"width_ratios": [1, 1.25]})
    for ax, (title, rows) in zip(axes, panels):
        rows = rows.iloc[::-1]
        bars = ax.barh(rows["name"], rows["mean_abs_shap"], color=SERIES, height=0.62)
        ax.bar_label(bars, labels=[f"{v:.2f}" for v in rows["mean_abs_shap"]],
                     padding=4, color=INK, fontsize=9)
        _style(ax, "x")
        ax.margins(x=0.14)
        ax.set_title(title, color=INK, fontsize=11, loc="left", fontweight="bold")
        ax.set_xlabel(f"Mean |SHAP|, {model.unit}", color=MUTED, fontsize=10)
        ax.tick_params(axis="y", labelcolor=INK)
    fig.suptitle(f"What drives {_what(model)}: SHAP feature importance ({model.best})",
                 color=INK, fontsize=13, x=0.01, ha="left", fontweight="bold")
    fig.text(0.01, 0.905, f"How far each input moves a player's prediction on average, in "
             f"{model.unit}{_scale_note(model)}. One-hot columns and the two age terms are "
             "summed on the left.", color=MUTED, fontsize=10, ha="left")
    fig.tight_layout(rect=(0, 0, 1, 0.89))
    path = Path(path)
    fig.savefig(path, dpi=150, facecolor=SURFACE)
    plt.close(fig)
    return path


def plot_shap_effects(model: ValueModel, players: pd.DataFrame, path: str | Path) -> Path:
    """How each feature moves the prediction: one panel per feature, one shared y-axis.

    Numeric features (age, minutes, composite score) are dots, one per player;
    league and position are the average SHAP value of their members.
    """
    import matplotlib

    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    grouped = model.shap_by_feature()
    rows = players.loc[grouped.index]
    numeric = {"Age": model.X["Age"], "Minutes": model.X["Minutes"]}
    if "Composite score" in grouped:
        numeric["Composite score"] = model.X["Composite score"]
    categories = {"League": rows["League"], "Position": rows["Pos"]}
    order = {"League": LEAGUES, "Position": POSITIONS}

    names = [*numeric, *categories]
    fig, axes = plt.subplots(1, len(names), figsize=(4.1 * len(names), 4.9), sharey=True,
                             facecolor=SURFACE)
    for ax, name in zip(axes, names):
        _style(ax)
        ax.axhline(0, color=AXIS, linewidth=1, zorder=1)
        if name in numeric:
            ax.scatter(numeric[name], grouped[name], s=9, color=SERIES, alpha=0.35,
                       linewidths=0, zorder=3)
            ax.set_xlabel(name, color=MUTED, fontsize=10)
        else:
            means = grouped[name].groupby(categories[name]).mean().reindex(order[name])
            bars = ax.bar(range(len(means)), means, color=SERIES, width=0.62, zorder=3)
            ax.bar_label(bars, labels=[f"{v:+.2f}" for v in means], padding=3, color=INK, fontsize=9)
            ax.set_xticks(range(len(means)))
            ax.set_xticklabels([x.replace(" ", "\n") if len(x) > 10 else x for x in means.index],
                               fontsize=8.5)
            ax.set_xlabel(f"{name} (average)", color=MUTED, fontsize=10)
        ax.set_title(name, color=INK, fontsize=11, loc="left", fontweight="bold")
        ax.margins(y=0.14)  # room for the bar labels above and below
    axes[0].set_ylabel(f"SHAP value, {model.unit}", color=MUTED, fontsize=10)
    fig.suptitle(f"How each feature moves {_what(model)} ({model.best})",
                 color=INK, fontsize=13, x=0.01, ha="left", fontweight="bold")
    fig.text(0.01, 0.9, f"Above zero raises the prediction, below zero lowers it"
             f"{_scale_note(model)}. Dots are players; bars are group averages.",
             color=MUTED, fontsize=10, ha="left")
    fig.tight_layout(rect=(0, 0, 1, 0.88))
    path = Path(path)
    fig.savefig(path, dpi=150, facecolor=SURFACE)
    plt.close(fig)
    return path


# ---- outputs --------------------------------------------------------------------------------------
def _markdown_table(table: pd.DataFrame) -> list[str]:
    head = "| " + " | ".join(map(str, table.columns)) + " |"
    rule = "|" + "|".join("---" for _ in table.columns) + "|"
    body = ["| " + " | ".join("" if pd.isna(v) else str(v) for v in row) + " |"
            for row in table.itertuples(index=False)]
    return [head, rule, *body]


def _gems_markdown(engine: ScoutingEngine, gems: dict[str, pd.DataFrame]) -> str:
    m = engine.value
    chosen = m.comparison.loc[m.best]
    lines = ["# Undervalued gems", ""]
    if m.mode == "efficiency":
        lines += ["There is no market-value column in the data, so the value gap is an efficiency "
                  "score: the player's composite score minus the score expected from his age, "
                  "minutes, league and position, in rating points.", ""]
    else:
        lines += ["Value gap = the market value the model predicts from age, minutes, league, "
                  "position and composite score, minus the Transfermarkt value at the end of "
                  "2024/25, in euros. Value ratio = predicted / actual.", ""]
    lines += [f"Model: {m.best} (held-out MAE {chosen['test_mae']:.2f} {m.unit}, "
              f"R² {chosen['test_r2']:.2f}). Players aged 24 or under, in the top quarter of "
              "their tactical cluster, largest gap first.", ""]
    for group, table in gems.items():
        lines += [f"## {ce.GROUP_TITLES[group]}", ""]
        lines += _markdown_table(table.drop(columns=["Cluster_ID", "Gap_Outlier"])) + [""]
    return "\n".join(lines)


def save(engine: ScoutingEngine, out_dir: str | Path = DEFAULT_OUT) -> dict[str, Path]:
    """Write the model comparison, value gaps, SHAP tables and plots, and the gems lists."""
    out = Path(out_dir)
    out.mkdir(parents=True, exist_ok=True)
    paths = {
        "comparison": out / "model_comparison.csv",
        "value_gap": out / "value_gap.csv",
        "shap_importance": out / "shap_importance.csv",
        "shap_importance_plot": plot_shap_importance(engine.value, out / "shap_importance.png"),
        "shap_effects_plot": plot_shap_effects(engine.value, engine.players, out / "shap_effects.png"),
        "gems": out / "undervalued_gems.csv",
        "gems_markdown": out / "undervalued_gems.md",
    }
    engine.value.comparison.to_csv(paths["comparison"])
    engine.value_table().to_csv(paths["value_gap"], encoding="utf-8-sig")
    engine.value.importance().to_csv(paths["shap_importance"], index=False)
    gems = {g: engine.get_undervalued_gems(g) for g in ce.GROUPS}
    pd.concat(gems, names=["group"]).to_csv(paths["gems"], encoding="utf-8-sig")
    paths["gems_markdown"].write_text(_gems_markdown(engine, gems), encoding="utf-8")
    return paths


def main() -> None:
    parser = argparse.ArgumentParser(description="Similar players and undervalued gems.")
    parser.add_argument("--out", default=str(DEFAULT_OUT), help="folder for the tables and plots")
    parser.add_argument("--similar", metavar="PLAYER", help="print the closest matches to a player")
    parser.add_argument("--squad", help="club, to separate two players with the same name")
    parser.add_argument("--gems", metavar="POSITION", help="print gems for FWD, MID, DEF or GKP")
    parser.add_argument("--cluster", help="cluster number or archetype name, with --gems")
    parser.add_argument("--top", type=int, help="how many rows to print")
    parser.add_argument("--max-age", type=int)
    parser.add_argument("--min-minutes", type=int, default=500)
    parser.add_argument("--leagues", nargs="*")
    parser.add_argument("--mode", choices=["auto", "efficiency", "market_value"], default="auto",
                        help="auto uses market values when they are available")
    args = parser.parse_args()

    engine = default_engine() if args.mode == "auto" else ScoutingEngine.build(mode=args.mode)
    pd.set_option("display.width", 250, "display.max_columns", 40)
    if args.similar:
        table = engine.find_similar_players(args.similar, args.top or 10, args.max_age,
                                            args.min_minutes, args.leagues, squad=args.squad)
        q = table.attrs["query"]
        print(f"Closest to {q['Player']} ({q['Squad']}, {q['Pos']}, {q['Cluster']}, "
              f"composite {q['Composite_Score']}):\n")
        print(table.to_string(index=False))
    if args.gems:
        table = engine.get_undervalued_gems(args.gems, args.cluster,
                                            args.max_age if args.max_age is not None else 24,
                                            args.top or 15)
        print(table.to_string(index=False))
    if not (args.similar or args.gems):
        priced = engine.players["Value_Gap"].notna().sum()
        print(f"Mode: {engine.value.mode} (market values: {engine.value.value_column}); "
              f"{priced} players modelled\n")
        print(engine.value.comparison.to_string(), "\n")
        for name, path in save(engine, args.out).items():
            print(f"{name}: {path}")


if __name__ == "__main__":
    main()
