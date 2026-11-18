"""Step 2: find tactical archetypes with unsupervised clustering.

Built on the loader in data.py (one row per player, readable column names).
Unlike roles.py, nothing here is hand-written football knowledge: players are
grouped purely by the shape of their numbers, and the output is a table of
what defines each group so a person can name it.

Pipeline, per positional group (FWD, MID, DEF, GKP):

1. Split recruitment metadata (name, club, league, position, age, minutes)
   from the style features, so age and playing time never enter a distance.
2. Possession-adjust defensive counts, so defenders on teams that have the
   ball a lot are not marked down for having less defending to do.
3. Standardise the features within the group.
4. Score K = 3..10 by inertia (elbow) and silhouette, and plot both.
5. Fit K-Means, then PCA + a Gaussian mixture as a benchmark that also gives
   every player a probability for each cluster.
6. Summarise each cluster by its most distinctive features and typical players.

Run:  python -m footstats.clustering_engine          (from the pipeline folder)
"""
from __future__ import annotations

import argparse
from dataclasses import dataclass, field
from pathlib import Path

import numpy as np
import pandas as pd
from scipy.optimize import linear_sum_assignment
from sklearn.cluster import KMeans
from sklearn.decomposition import PCA
from sklearn.metrics import adjusted_rand_score, silhouette_score
from sklearn.mixture import GaussianMixture
from sklearn.preprocessing import StandardScaler

from .data import DEFAULT_CSV, MIN_MINUTES, load_players

SEED = 42
K_RANGE = range(3, 11)
GROUPS = ["FWD", "MID", "DEF", "GKP"]
# data.py splits FBref's forwards into wingers and strikers; here they are one
# group again, so the clustering has to find that split (and others) by itself.
POSITION_GROUP = {"WNG": "FWD", "STR": "FWD", "MID": "MID", "DEF": "DEF", "GKP": "GKP"}
DEFAULT_OUT = Path(__file__).resolve().parents[1] / "outputs" / "clustering"

# ---- 1. metadata vs style features ----------------------------------------------
# Never used as a clustering feature. The source has no market-value column;
# if one is added, list it here so it stays out of the feature matrix.
METADATA = {"Player": "Player Name", "Squad": "Club", "League": "League", "Pos": "Position",
            "Age": "Age", "Minutes": "Minutes"}

# feature name -> (kind, column[, denominator])
#   "p90":   count per 90 minutes
#   "padj":  count per 90, possession-adjusted (see possession_factor)
#   "share": count divided by another count
#   "rate":  already a rate, used as it is
# No goals, assists or expected goals: those say how good a player is, not how
# they play, and would pull the best players into a cluster of their own.
OUTFIELD_FEATURES: dict[str, tuple] = {
    # attacking the box
    "Shots": ("p90", "Shots"),
    "Touches in opposition box": ("p90", "Touches in box"),
    "Offsides": ("p90", "Offsides"),
    "Fouls won": ("p90", "Fouls drawn"),
    # creating
    "Key passes": ("p90", "Key passes"),
    "Passes into box": ("p90", "Passes into box"),
    "Through balls": ("p90", "Through balls"),
    "Crosses": ("p90", "Crosses"),
    "Shot-creating actions": ("p90", "Shot-creating actions"),
    # build-up
    "Passes attempted": ("p90", "Passes attempted"),
    "Pass accuracy": ("rate", "Pass accuracy"),
    "Progressive passes": ("p90", "Progressive passes"),
    "Passes into final third": ("p90", "Passes into final third"),
    "Switches of play": ("p90", "Switches"),
    "Passes received": ("p90", "Passes received"),
    "Progressive passes received": ("p90", "Progressive receptions"),
    # carrying
    "Progressive carries": ("p90", "Progressive carries"),
    "Carries into final third": ("p90", "Carries into final third"),
    "Carries into box": ("p90", "Carries into box"),
    "Take-ons attempted": ("p90", "Take-ons attempted"),
    # defending (possession-adjusted)
    "Tackles (adj)": ("padj", "Tackles"),
    "Tackles outside own third (adj)": ("padj", "Tackles outside own third"),
    "Interceptions (adj)": ("padj", "Interceptions"),
    "Blocks (adj)": ("padj", "Blocks"),
    "Clearances (adj)": ("padj", "Clearances"),
    "Ball recoveries (adj)": ("padj", "Ball recoveries"),
    "Dribblers challenged (adj)": ("padj", "Dribblers challenged"),
    "Fouls (adj)": ("padj", "Fouls"),
    # in the air
    "Aerial duels": ("p90", "Aerial duels"),
    "Aerial win rate": ("rate", "Aerial win %"),
    # where on the pitch
    "Touches in own third (share)": ("share", "Touches in defensive third", "Touches"),
    "Touches in final third (share)": ("share", "Touches in attacking third", "Touches"),
    "Throw-ins": ("p90", "Throw-ins"),
}
# Goalkeepers: how they play, not how well they stop shots.
GOALKEEPER_FEATURES: dict[str, tuple] = {
    "Actions outside the box": ("p90", "Sweeper actions"),
    "Distance of actions from goal": ("rate", "Sweeper distance"),
    "Crosses claimed (share)": ("rate", "Crosses stopped %"),
    "Passes attempted": ("p90", "Goalkeeper passes"),
    "Pass accuracy": ("rate", "Pass accuracy"),
    "Long passes (share)": ("rate", "Launch %"),
    "Average pass length": ("rate", "Pass length"),
    "Touches": ("p90", "Touches"),
}
GROUP_FEATURES = {"FWD": OUTFIELD_FEATURES, "MID": OUTFIELD_FEATURES,
                  "DEF": OUTFIELD_FEATURES, "GKP": GOALKEEPER_FEATURES}

HYBRID_BELOW = 0.70  # a player whose best cluster probability is under this is a hybrid
PCA_VARIANCE = 0.90  # the mixture model is fitted on the components that keep this much


# ---- 2. possession adjustment -----------------------------------------------------
def team_possession(csv_path: str | Path = DEFAULT_CSV) -> pd.Series:
    """Estimated possession share per club (0-1), indexed by FBref club name.

    The source has no possession column and no opponent data, so possession is
    estimated from passes: a club's passes per match against the average passes
    per match of the other clubs in its league. This understates the extremes
    (PSG come out at 61%, against a real figure nearer 68%, because teams
    facing PSG pass less than they usually do) but ranks clubs correctly, so
    the adjustment moves the right players in the right direction, just by a
    little less than it should.
    """
    raw = pd.read_csv(csv_path, encoding="utf-8-sig")
    team = pd.DataFrame({
        "League": raw["Comp"], "Club": raw["Squad"],
        "Passes": pd.to_numeric(raw["Att"], errors="coerce").fillna(0),
        "Minutes": pd.to_numeric(raw["Min"], errors="coerce").fillna(0),
    }).groupby(["League", "Club"]).sum()
    per_match = team["Passes"] / (team["Minutes"] / (11 * 90))
    league_total = per_match.groupby(level="League").transform("sum")
    league_size = per_match.groupby(level="League").transform("size")
    others = (league_total - per_match) / (league_size - 1)
    return (per_match / (per_match + others)).droplevel("League").rename("Possession")


def possession_factor(possession: pd.Series) -> pd.Series:
    """Multiplier that rescales defensive counts to an opponent with 50% of the ball.

    A defender can only tackle or intercept while the other team has the ball.
    At 60% possession the opponent has it 40% of the time, so counts are scaled
    by 0.5 / 0.4 = 1.25; at 40% possession by 0.5 / 0.6 = 0.83.
    """
    return 0.5 / (1 - possession)


def build_frames(df: pd.DataFrame, possession: pd.Series,
                 min_minutes: int = MIN_MINUTES) -> tuple[pd.DataFrame, dict[str, pd.DataFrame]]:
    """Return (metadata, {group: raw style features}), both indexed by player id.

    Only players with at least min_minutes are kept: per-90 numbers from a few
    hundred minutes are too noisy to place someone in a cluster.
    """
    df = df[df["Minutes"] >= min_minutes].set_index("id")
    metadata = df[list(METADATA.values())].rename(columns={v: k for k, v in METADATA.items()})
    metadata["Group"] = metadata["Pos"].map(POSITION_GROUP)
    # A player who changed clubs is adjusted by the club where he played most.
    metadata["Team possession"] = metadata["Squad"].map(possession).fillna(0.5).round(3)

    minutes = df["Minutes"].clip(lower=1)
    factor = possession_factor(metadata["Team possession"])
    features: dict[str, pd.DataFrame] = {}
    for group, specs in GROUP_FEATURES.items():
        members = metadata["Group"] == group
        cols = {}
        for name, (kind, column, *rest) in specs.items():
            if kind == "p90":
                cols[name] = df[column] / minutes * 90
            elif kind == "padj":
                cols[name] = df[column] / minutes * 90 * factor
            elif kind == "share":
                cols[name] = df[column] / df[rest[0]].clip(lower=1)
            else:
                cols[name] = df[column].astype(float)
        features[group] = pd.DataFrame(cols)[members]
    return metadata, features


# ---- 3. scaling ---------------------------------------------------------------------
def scale(features: pd.DataFrame) -> pd.DataFrame:
    """z-scores within one positional group (mean 0, standard deviation 1 per feature)."""
    values = StandardScaler().fit_transform(features)
    return pd.DataFrame(values, index=features.index, columns=features.columns)


# ---- 4. choosing K --------------------------------------------------------------------
def validate_k(X: pd.DataFrame, k_range=K_RANGE, seed: int = SEED) -> pd.DataFrame:
    """Inertia (within-cluster sum of squares) and silhouette for each K."""
    rows = []
    for k in k_range:
        model = KMeans(n_clusters=k, n_init=10, random_state=seed).fit(X)
        rows.append({"k": k, "inertia": float(model.inertia_),
                     "silhouette": float(silhouette_score(X, model.labels_))})
    return pd.DataFrame(rows).set_index("k")


def elbow_k(validation: pd.DataFrame) -> int:
    """The K where the inertia curve bends most.

    Both axes are rescaled to 0-1 and the elbow is the point furthest below the
    straight line joining the first and last K.
    """
    k = validation.index.to_numpy(dtype=float)
    inertia = validation["inertia"].to_numpy()
    x = (k - k.min()) / (k.max() - k.min())
    y = (inertia - inertia.min()) / (inertia.max() - inertia.min())
    return int(validation.index[np.argmax((1 - x) - y)])


def choose_k(validation: pd.DataFrame) -> tuple[int, int, int]:
    """Return (chosen K, elbow K, best-silhouette K).

    The two methods answer different questions and often disagree: silhouette
    tends to favour very few, coarse clusters, while the elbow says where extra
    clusters stop paying for themselves. The chosen K uses both: the best
    silhouette among the elbow and its two neighbours.
    """
    elbow = elbow_k(validation)
    near = validation.loc[[k for k in (elbow - 1, elbow, elbow + 1) if k in validation.index]]
    return int(near["silhouette"].idxmax()), elbow, int(validation["silhouette"].idxmax())


# ---- 5. K-Means and the mixture benchmark -----------------------------------------------
def fit_kmeans(X: pd.DataFrame, k: int, seed: int = SEED) -> pd.Series:
    """Hard cluster labels 1..k, numbered from the largest cluster to the smallest."""
    labels = KMeans(n_clusters=k, n_init=10, random_state=seed).fit_predict(X)
    order = pd.Series(labels).value_counts().index
    renumber = {old: new for new, old in enumerate(order, start=1)}
    return pd.Series([renumber[c] for c in labels], index=X.index, name="cluster")


def fit_mixture(X: pd.DataFrame, k: int, kmeans_labels: pd.Series,
                seed: int = SEED) -> tuple[pd.DataFrame, dict]:
    """PCA + Gaussian mixture with k components, lined up with the K-Means clusters.

    Returns (probabilities, benchmark). probabilities has one column per K-Means
    cluster number; each row sums to 1. The covariance shape (full, tied or
    diagonal) is whichever gives the lowest BIC, so small groups are not
    over-fitted with a full covariance matrix per component.
    """
    pca = PCA(n_components=PCA_VARIANCE, random_state=seed).fit(X)
    Z = pca.transform(X)

    def gmm(n, cov):
        return GaussianMixture(n_components=n, covariance_type=cov, n_init=5,
                               reg_covar=1e-4, random_state=seed).fit(Z)

    candidates = {cov: gmm(k, cov) for cov in ("full", "tied", "diag")}
    covariance = min(candidates, key=lambda c: candidates[c].bic(Z))
    model = candidates[covariance]
    bic_by_k = {n: float(gmm(n, covariance).bic(Z)) for n in K_RANGE}

    # Match each mixture component to the K-Means cluster it overlaps most.
    proba = model.predict_proba(Z)
    hard = proba.argmax(axis=1)
    table = pd.crosstab(hard, kmeans_labels.to_numpy()).reindex(
        index=range(k), columns=range(1, k + 1), fill_value=0)
    comps, clusters = linear_sum_assignment(-table.to_numpy())
    column_of = {int(comp): int(table.columns[c]) for comp, c in zip(comps, clusters)}
    probabilities = pd.DataFrame(proba, index=X.index).rename(columns=column_of)
    probabilities = probabilities[sorted(probabilities.columns)]

    gmm_labels = probabilities.idxmax(axis=1)
    confidence = probabilities.max(axis=1)
    benchmark = {
        "pca_components": int(pca.n_components_),
        "pca_variance_kept": round(float(pca.explained_variance_ratio_.sum()), 3),
        "gmm_covariance": covariance,
        "gmm_best_k_by_bic": int(min(bic_by_k, key=bic_by_k.get)),
        "kmeans_silhouette": round(float(silhouette_score(X, kmeans_labels)), 3),
        "gmm_silhouette": round(float(silhouette_score(X, gmm_labels)), 3)
        if gmm_labels.nunique() > 1 else float("nan"),
        "adjusted_rand_index": round(float(adjusted_rand_score(kmeans_labels, gmm_labels)), 3),
        "same_cluster_share": round(float((gmm_labels == kmeans_labels).mean()), 3),
        "mean_confidence": round(float(confidence.mean()), 3),
        "hybrid_share": round(float((confidence < HYBRID_BELOW).mean()), 3),
    }
    return probabilities, benchmark


# ---- naming the clusters --------------------------------------------------------------------
# Names given to the clusters after reading the summary. Cluster numbers are
# not stable (they follow cluster size, and change with K or new data), so each
# name is tied to a reference player who sits near the centre of the cluster:
# whichever cluster holds that player gets the name. If K changes, clusters
# with no reference player, or with two, simply keep their number.
#
# Four names are weaker than the rest. "All-round striker" has no feature more
# than 0.4 standard deviations from average. "Defensive winger" and
# "Focal-point wide attacker" partly reflect the team (one that defends a lot,
# one that dominates). "Line keeper" is defined by low involvement, not by
# anything measured about shot-stopping.
ARCHETYPES: dict[str, dict[str, str]] = {
    "FWD": {
        "Target striker": "Jean-Philippe Mateta",
        "All-round striker": "Jonathan David",
        "Direct winger": "Jarrod Bowen",
        "Defensive winger": "Jorge de Frutos",
        "Focal-point wide attacker": "Khvicha Kvaratskhelia",
        "Wide playmaker": "Antoine Griezmann",
    },
    "MID": {
        "Anchor": "Jesper Karlström",
        "Box-arriving attacking midfielder": "Lorenzo Pellegrini",
        "Ball-winner": "Carlos Baleba",
        "Tempo-setting playmaker": "Vitinha",
        "Advanced creator": "Cole Palmer",
    },
    "DEF": {
        "Stopper": "Wout Faes",
        "Touchline full-back": "Nélson Semedo",
        "Ball-playing centre-back": "Ibrahima Konaté",
        "Attacking wing-back": "Rayan Aït-Nouri",
    },
    "GKP": {
        "Line keeper": "Michele Di Gregorio",
        "High-involvement distributor": "Kevin Trapp",
        "Sweeper-keeper": "Ederson",
        "Long-ball keeper": "Dean Henderson",
    },
}


def name_clusters(group: str, labels: pd.Series, metadata: pd.DataFrame) -> dict[int, str]:
    """Cluster number -> archetype name, falling back to e.g. "MID 3" when unsure."""
    players = metadata.loc[labels.index, "Player"]
    claims: dict[int, list[str]] = {}
    for name, reference in ARCHETYPES.get(group, {}).items():
        found = labels[players == reference]
        if len(found) == 1:
            claims.setdefault(int(found.iloc[0]), []).append(name)
    return {int(c): claims[c][0] if len(claims.get(c, [])) == 1 else f"{group} {c}"
            for c in sorted(labels.unique())}


# ---- 6. summary ---------------------------------------------------------------------------
def _names(metadata: pd.DataFrame, ids) -> str:
    return "; ".join(f"{metadata.at[i, 'Player']} ({metadata.at[i, 'Squad']})" for i in ids)


def summarise(group: str, X: pd.DataFrame, labels: pd.Series, metadata: pd.DataFrame,
              probabilities: pd.DataFrame, names: dict[int, str] | None = None,
              top: int = 5, low: int = 3, players: int = 6) -> pd.DataFrame:
    """One row per cluster: name, size, most distinctive features, typical players.

    Feature values are the cluster's mean z-score, so +1.2 reads as "1.2
    standard deviations above the average player in this positional group".
    """
    rows = []
    confidence = probabilities.max(axis=1)
    for cluster in sorted(labels.unique()):
        members = labels.index[labels == cluster]
        centre = X.loc[members].mean().sort_values(ascending=False)
        distance = ((X.loc[members] - X.loc[members].mean()) ** 2).sum(axis=1)
        rows.append({
            "group": group, "cluster": int(cluster),
            "archetype": (names or {}).get(int(cluster), f"{group} {cluster}"),
            "players": len(members),
            "share": round(len(members) / len(labels), 3),
            "high": ", ".join(f"{f} {v:+.2f}" for f, v in centre[centre > 0].head(top).items()),
            "low": ", ".join(f"{f} {v:+.2f}" for f, v in centre[centre < 0].tail(low)[::-1].items()),
            "closest_to_centre": _names(metadata, distance.nsmallest(players).index),
            "most_minutes": _names(metadata, metadata.loc[members, "Minutes"].nlargest(players).index),
            "mean_confidence": round(float(confidence[members].mean()), 3),
            "hybrids": int((confidence[members] < HYBRID_BELOW).sum()),
        })
    return pd.DataFrame(rows)


# ---- running the whole thing ---------------------------------------------------------------
@dataclass
class GroupResult:
    group: str
    scaled: pd.DataFrame
    validation: pd.DataFrame
    k: int
    elbow_k: int
    silhouette_k: int
    labels: pd.Series
    probabilities: pd.DataFrame
    benchmark: dict
    summary: pd.DataFrame
    names: dict[int, str] = field(default_factory=dict)
    k_was_overridden: bool = False


@dataclass
class ClusteringResult:
    metadata: pd.DataFrame
    possession: pd.Series
    groups: dict[str, GroupResult] = field(default_factory=dict)

    def assignments(self) -> pd.DataFrame:
        """Metadata plus hard label, mixture label, confidence and runner-up, per player."""
        parts = []
        for group, r in self.groups.items():
            p = r.probabilities
            ranked = np.argsort(-p.to_numpy(), axis=1)
            cols = p.columns.to_numpy()
            part = self.metadata.loc[r.labels.index].copy()
            part["cluster"] = r.labels
            part["archetype"] = r.labels.map(r.names)
            part["gmm_cluster"] = cols[ranked[:, 0]]
            part["gmm_archetype"] = part["gmm_cluster"].map(r.names)
            part["gmm_confidence"] = p.max(axis=1).round(3)
            part["gmm_second_cluster"] = cols[ranked[:, 1]]
            part["gmm_second_archetype"] = part["gmm_second_cluster"].map(r.names)
            part["gmm_second_probability"] = np.sort(p.to_numpy(), axis=1)[:, -2].round(3)
            part["hybrid"] = part["gmm_confidence"] < HYBRID_BELOW
            parts.append(part)
        return pd.concat(parts)

    def summary(self) -> pd.DataFrame:
        return pd.concat([r.summary for r in self.groups.values()], ignore_index=True)

    def validation(self) -> pd.DataFrame:
        return pd.concat({g: r.validation for g, r in self.groups.items()}, names=["group"])

    def benchmark(self) -> pd.DataFrame:
        rows = {g: {"players": len(r.labels), "k": r.k, "elbow_k": r.elbow_k,
                    "best_silhouette_k": r.silhouette_k, **r.benchmark}
                for g, r in self.groups.items()}
        return pd.DataFrame.from_dict(rows, orient="index").rename_axis("group")


def run(csv_path: str | Path = DEFAULT_CSV, min_minutes: int = MIN_MINUTES,
        k_override: dict[str, int] | None = None) -> ClusteringResult:
    """Run steps 1-6 for every positional group. k_override forces K for a group."""
    possession = team_possession(csv_path)
    metadata, features = build_frames(load_players(csv_path), possession, min_minutes)
    result = ClusteringResult(metadata=metadata, possession=possession)
    for group in GROUPS:
        X = scale(features[group])
        validation = validate_k(X)
        k, elbow, best_silhouette = choose_k(validation)
        forced = (k_override or {}).get(group)
        labels = fit_kmeans(X, forced or k)
        probabilities, benchmark = fit_mixture(X, forced or k, labels)
        names = name_clusters(group, labels, metadata)
        result.groups[group] = GroupResult(
            group=group, scaled=X, validation=validation, k=forced or k, elbow_k=elbow,
            silhouette_k=best_silhouette, labels=labels, probabilities=probabilities,
            benchmark=benchmark, names=names, k_was_overridden=forced is not None,
            summary=summarise(group, X, labels, metadata, probabilities, names),
        )
    return result


GROUP_TITLES = {"FWD": "Forwards", "MID": "Midfielders", "DEF": "Defenders", "GKP": "Goalkeepers"}


def plot_validation(result: ClusteringResult, path: str | Path) -> Path:
    """Elbow curve (top row) and silhouette (bottom row) for each group, sharing the K axis.

    Two rows of small charts rather than one chart with two y-axes: inertia and
    silhouette are on unrelated scales, and a shared plot makes the crossing
    point of the two lines look meaningful when it is not.
    """
    import matplotlib

    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    surface, ink, muted, series = "#fcfcfb", "#0b0b0b", "#52514e", "#2a78d6"
    fig, axes = plt.subplots(2, len(result.groups), figsize=(3.6 * len(result.groups), 6.2),
                             sharex=True, facecolor=surface)
    for col, (group, r) in enumerate(result.groups.items()):
        ks = r.validation.index.to_numpy()
        panels = [
            (axes[0, col], r.validation["inertia"] / r.validation["inertia"].iloc[0] * 100,
             "Inertia, % of K=3", r.elbow_k, f"elbow K={r.elbow_k}"),
            (axes[1, col], r.validation["silhouette"], "Silhouette",
             r.silhouette_k, f"best K={r.silhouette_k}"),
        ]
        for ax, values, ylabel, marked, note in panels:
            ax.set_facecolor(surface)
            ax.axvline(r.k, color=muted, linewidth=1, linestyle=(0, (3, 3)), zorder=1)
            ax.plot(ks, values, color=series, linewidth=2, marker="o", markersize=5, zorder=3)
            ax.plot([marked], [values.loc[marked]], marker="o", markersize=10,
                    markerfacecolor=surface, markeredgecolor=series, markeredgewidth=2, zorder=4)
            ax.annotate(note, (marked, values.loc[marked]), textcoords="offset points",
                        xytext=(10, 12), color=ink, fontsize=9)
            ax.grid(axis="y", color="#e4e3df", linewidth=0.8)
            ax.set_axisbelow(True)
            for side in ("top", "right", "left"):
                ax.spines[side].set_visible(False)
            ax.spines["bottom"].set_color("#c9c8c3")
            ax.tick_params(colors=muted, labelsize=9, length=0)
            ax.set_xticks(ks)
            ax.margins(y=0.18)
            if col == 0:
                ax.set_ylabel(ylabel, color=muted, fontsize=10)
        axes[0, col].set_title(f"{GROUP_TITLES[group]}  (n={len(r.labels)}, chosen K={r.k})",
                               color=ink, fontsize=11, loc="left", fontweight="bold")
        axes[1, col].set_xlabel("Number of clusters K", color=muted, fontsize=10)
    fig.suptitle("Choosing K: elbow (top) and silhouette (bottom) by position group",
                 color=ink, fontsize=13, x=0.01, ha="left", fontweight="bold")
    fig.text(0.01, 0.925, "Dashed line marks the K used. Ring marks the elbow (top) and the "
             "highest silhouette (bottom).", color=muted, fontsize=10, ha="left")
    fig.tight_layout(rect=(0, 0, 1, 0.91))
    path = Path(path)
    fig.savefig(path, dpi=150, facecolor=surface)
    plt.close(fig)
    return path


def _markdown(result: ClusteringResult) -> str:
    """The summary as a readable document: one section per group, one block per cluster."""
    lines = ["# Cluster summary", "",
             "Feature values are mean z-scores within the position group. "
             "`(adj)` means possession-adjusted.", ""]
    for group, r in result.groups.items():
        b = r.benchmark
        lines += [f"## {GROUP_TITLES[group]}: K = {r.k}"
                  + (" (set by hand)" if r.k_was_overridden else ""), "",
                  f"{len(r.labels)} players. Elbow K = {r.elbow_k}, best silhouette K = "
                  f"{r.silhouette_k}. K-Means silhouette {b['kmeans_silhouette']}; the mixture "
                  f"model puts {b['same_cluster_share']:.0%} of players in the same cluster and "
                  f"calls {b['hybrid_share']:.0%} hybrids.", ""]
        for row in r.summary.itertuples():
            number = f"{group} {row.cluster}"
            title = number if row.archetype == number else f"{row.archetype} ({number})"
            lines += [f"### {title}: {row.players} players ({row.share:.0%})", "",
                      f"- **More of:** {row.high}", f"- **Less of:** {row.low}",
                      f"- **Closest to the centre:** {row.closest_to_centre}",
                      f"- **Most minutes:** {row.most_minutes}",
                      f"- **Hybrids:** {row.hybrids} (mean confidence {row.mean_confidence})", ""]
    return "\n".join(lines)


def save(result: ClusteringResult, out_dir: str | Path = DEFAULT_OUT) -> dict[str, Path]:
    """Write the plot and tables; returns the paths written."""
    out = Path(out_dir)
    out.mkdir(parents=True, exist_ok=True)
    paths = {
        "plot": plot_validation(result, out / "k_validation.png"),
        "validation": out / "k_validation.csv",
        "benchmark": out / "benchmark.csv",
        "summary": out / "cluster_summary.csv",
        "summary_markdown": out / "cluster_summary.md",
        "assignments": out / "assignments.csv",
        "possession": out / "team_possession.csv",
    }
    result.validation().round(4).to_csv(paths["validation"])
    result.benchmark().to_csv(paths["benchmark"])
    result.summary().to_csv(paths["summary"], index=False, encoding="utf-8-sig")
    paths["summary_markdown"].write_text(_markdown(result), encoding="utf-8")
    assignments = result.assignments()
    probabilities = pd.concat(
        [r.probabilities.add_prefix("p_cluster_").round(3) for r in result.groups.values()])
    assignments.join(probabilities).to_csv(paths["assignments"], index_label="id", encoding="utf-8-sig")
    result.possession.sort_values(ascending=False).round(3).to_csv(paths["possession"], encoding="utf-8-sig")
    return paths


def main() -> None:
    parser = argparse.ArgumentParser(description="Cluster players into tactical archetypes.")
    parser.add_argument("--out", default=str(DEFAULT_OUT), help="folder for the plot and tables")
    parser.add_argument("--min-minutes", type=int, default=MIN_MINUTES)
    parser.add_argument("--k", nargs="*", default=[], metavar="GROUP=K",
                        help="force K for a group, e.g. --k MID=6 FWD=5")
    args = parser.parse_args()
    override = {g.upper(): int(k) for g, k in (item.split("=") for item in args.k)}
    unknown = set(override) - set(GROUPS)
    if unknown:
        parser.error(f"unknown group(s): {', '.join(sorted(unknown))}; use {', '.join(GROUPS)}")

    result = run(min_minutes=args.min_minutes, k_override=override)
    paths = save(result, args.out)
    pd.set_option("display.width", 200)
    print(result.benchmark().to_string())
    print()
    for name, path in paths.items():
        print(f"{name}: {path}")


if __name__ == "__main__":
    main()
