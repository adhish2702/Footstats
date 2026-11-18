import numpy as np
import pandas as pd
import pytest

from footstats import clustering_engine as ce
from footstats.data import load_players


@pytest.fixture(scope="module")
def result() -> ce.ClusteringResult:
    return ce.run()


@pytest.fixture(scope="module")
def frames():
    possession = ce.team_possession()
    metadata, features = ce.build_frames(load_players(), possession)
    return possession, metadata, features


# ---- 1. metadata stays out of the features ------------------------------------
def test_metadata_is_separate_from_features(frames):
    _, metadata, features = frames
    assert {"Player", "Squad", "League", "Pos", "Age", "Minutes"} <= set(metadata.columns)
    banned = {"Age", "Minutes", "Appearances", "Starts", "Born", "Player Name", "Club", "League"}
    for group, specs in ce.GROUP_FEATURES.items():
        used = {spec[1] for spec in specs.values()} | {spec[2] for spec in specs.values() if len(spec) > 2}
        assert not used & banned, group
        assert not set(features[group].columns) & set(metadata.columns), group


def test_features_do_not_measure_output():
    output = {"Goals", "Assists", "Non-penalty goals", "Penalty goals", "xG", "npxG", "xAG",
              "Goal Contributions", "Goals conceded", "Clean sheets", "Goals prevented", "Save %"}
    for group, specs in ce.GROUP_FEATURES.items():
        assert not {spec[1] for spec in specs.values()} & output, group


def test_every_qualified_player_is_in_exactly_one_group(frames):
    _, metadata, features = frames
    assert set(features) == set(ce.GROUPS)
    ids = np.concatenate([f.index.to_numpy() for f in features.values()])
    assert len(ids) == len(set(ids)) == len(metadata) == 1576
    assert (metadata["Minutes"] >= 900).all()
    for group, f in features.items():
        assert np.isfinite(f.to_numpy()).all(), group


# ---- 2. possession adjustment --------------------------------------------------
def test_possession_estimate_is_plausible(frames):
    possession, _, _ = frames
    assert len(possession) == 96 and possession.between(0.3, 0.7).all()
    # Within each league, shares average 50% by construction.
    assert abs(possession.mean() - 0.5) < 0.01
    for club in ("Manchester City", "Bayern Munich", "Paris S-G", "Barcelona"):
        assert possession[club] > 0.55, club
    for club in ("Getafe", "Everton", "Nott'ham Forest"):
        assert possession[club] < 0.47, club


def test_possession_factor():
    factor = ce.possession_factor(pd.Series([0.4, 0.5, 0.6]))
    assert factor.round(3).tolist() == [0.833, 1.0, 1.25]


def test_defensive_counts_are_scaled_by_team_possession(frames):
    _, metadata, features = frames
    df = load_players().set_index("id")
    defenders = features["DEF"]
    raw = df.loc[defenders.index, "Tackles"] / df.loc[defenders.index, "Minutes"] * 90
    ratio = (defenders["Tackles (adj)"] / raw).dropna()
    expected = ce.possession_factor(metadata.loc[ratio.index, "Team possession"])
    assert np.allclose(ratio, expected, atol=1e-9)
    # A high-possession club's defender is marked up, a low-possession club's marked down.
    by_name = metadata["Player"]
    saliba = by_name[by_name == "William Saliba"].index[0]
    tarkowski = by_name[by_name == "James Tarkowski"].index[0]
    assert ratio[saliba] > 1 > ratio[tarkowski]
    # Passing volume is left alone.
    passes = df.loc[defenders.index, "Passes attempted"] / df.loc[defenders.index, "Minutes"] * 90
    assert np.allclose(defenders["Passes attempted"], passes)


# ---- 3. scaling ------------------------------------------------------------------
def test_features_are_standardised_within_each_group(result):
    for group, r in result.groups.items():
        assert np.allclose(r.scaled.mean(), 0, atol=1e-9), group
        assert np.allclose(r.scaled.std(ddof=0), 1, atol=1e-9), group


# ---- 4. choosing K ----------------------------------------------------------------
def test_validation_covers_k_three_to_ten(result):
    for group, r in result.groups.items():
        assert list(r.validation.index) == list(range(3, 11)), group
        assert r.validation["inertia"].is_monotonic_decreasing, group
        assert r.validation["silhouette"].between(-1, 1).all(), group
        assert r.silhouette_k == r.validation["silhouette"].idxmax()
        assert 3 <= r.elbow_k <= 10 and abs(r.k - r.elbow_k) <= 1


def test_elbow_finds_an_obvious_bend():
    validation = pd.DataFrame({"inertia": [100, 60, 30, 27, 25, 23, 22, 21]},
                              index=pd.RangeIndex(3, 11, name="k"))
    assert ce.elbow_k(validation) == 5


def test_k_can_be_forced():
    forced = ce.run(k_override={"GKP": 3})
    assert forced.groups["GKP"].k == 3 and forced.groups["GKP"].k_was_overridden
    assert forced.groups["GKP"].labels.nunique() == 3
    assert not forced.groups["DEF"].k_was_overridden
    # Four goalkeeper names can't fit three clusters: a cluster holding two
    # reference players keeps its number instead of guessing a name.
    names = forced.groups["GKP"].names
    assert len(set(names.values())) == 3
    assert any(name.startswith("GKP ") for name in names.values())
    assert set(names.values()) - {f"GKP {c}" for c in names} <= set(ce.ARCHETYPES["GKP"])


# ---- 5. K-Means and the mixture benchmark --------------------------------------------
def test_kmeans_labels_are_numbered_by_size(result):
    for group, r in result.groups.items():
        sizes = r.labels.value_counts()
        assert sorted(sizes.index) == list(range(1, r.k + 1)), group
        assert sizes.sort_index().is_monotonic_decreasing, group
        assert sizes.min() >= 5, group


def test_mixture_gives_every_player_probabilities(result):
    for group, r in result.groups.items():
        p = r.probabilities
        assert list(p.columns) == list(range(1, r.k + 1)), group
        assert p.index.equals(r.labels.index), group
        assert np.allclose(p.sum(axis=1), 1), group
        assert ((p >= 0) & (p <= 1)).all().all(), group


def test_mixture_is_lined_up_with_kmeans(result):
    for group, r in result.groups.items():
        b = r.benchmark
        chance = (r.labels.value_counts(normalize=True) ** 2).sum()
        assert b["same_cluster_share"] > chance, group
        assert b["same_cluster_share"] == round(float((r.probabilities.idxmax(axis=1) == r.labels).mean()), 3)
        assert 0.85 <= b["pca_variance_kept"] <= 1 and b["gmm_covariance"] in {"full", "tied", "diag"}
        assert 0 <= b["hybrid_share"] < 0.5


def test_assignments_table(result):
    table = result.assignments()
    assert len(table) == 1576 and table.index.is_unique
    assert {"Player", "Squad", "Group", "cluster", "gmm_cluster", "gmm_confidence",
            "gmm_second_cluster", "gmm_second_probability", "hybrid"} <= set(table.columns)
    assert (table["gmm_confidence"] >= table["gmm_second_probability"]).all()
    assert (table["gmm_cluster"] != table["gmm_second_cluster"]).all()
    assert (table["hybrid"] == (table["gmm_confidence"] < ce.HYBRID_BELOW)).all()


# ---- 6. summary ----------------------------------------------------------------------
def test_summary_has_a_row_per_cluster(result):
    summary = result.summary()
    assert len(summary) == sum(r.k for r in result.groups.values())
    assert summary.groupby("group")["players"].sum().to_dict() == {
        g: len(r.labels) for g, r in result.groups.items()}
    assert (summary["high"].str.len() > 0).all()
    assert (summary["closest_to_centre"].str.count(";") >= 4).all()
    # "More of" lists only above-average features, "less of" only below-average ones.
    assert not summary["high"].str.contains(r" -\d").any()
    assert not summary["low"].str.contains(r" \+\d").any()


def test_clusters_recover_obvious_differences(result):
    table = result.assignments().set_index("Player")
    # Centre-backs and attacking full-backs should not share a cluster...
    assert table.at["Virgil van Dijk", "cluster"] != table.at["Federico Dimarco", "cluster"]
    assert table.at["James Tarkowski", "cluster"] != table.at["Jeremie Frimpong", "cluster"]
    # ...nor target men and wingers, nor holding and attacking midfielders.
    assert table.at["Chris Wood", "cluster"] != table.at["Lamine Yamal", "cluster"]
    assert table.at["Idrissa Gana Gueye", "cluster"] != table.at["Cole Palmer", "cluster"]


# ---- names --------------------------------------------------------------------------------
def test_every_cluster_gets_its_name(result):
    expected = {
        "FWD": {1: "Target striker", 2: "All-round striker", 3: "Direct winger",
                4: "Defensive winger", 5: "Focal-point wide attacker", 6: "Wide playmaker"},
        "MID": {1: "Anchor", 2: "Box-arriving attacking midfielder", 3: "Ball-winner",
                4: "Tempo-setting playmaker", 5: "Advanced creator"},
        "DEF": {1: "Stopper", 2: "Touchline full-back", 3: "Ball-playing centre-back",
                4: "Attacking wing-back"},
        "GKP": {1: "Line keeper", 2: "High-involvement distributor", 3: "Sweeper-keeper",
                4: "Long-ball keeper"},
    }
    assert {g: r.names for g, r in result.groups.items()} == expected
    assert result.summary()["archetype"].tolist() == [n for g in expected.values() for n in g.values()]


def test_names_follow_the_players_not_the_numbers(result):
    r = result.groups["DEF"]
    # Renumber the clusters: the names must move with the players.
    shuffled = r.labels.map({1: 4, 2: 3, 3: 2, 4: 1})
    renamed = ce.name_clusters("DEF", shuffled, result.metadata)
    assert renamed == {4: "Stopper", 3: "Touchline full-back", 2: "Ball-playing centre-back",
                       1: "Attacking wing-back"}
    # A group with no names listed keeps its numbers.
    assert ce.name_clusters("XYZ", r.labels, result.metadata) == {c: f"XYZ {c}" for c in range(1, 5)}


def test_assignments_carry_archetypes(result):
    table = result.assignments().set_index("Player")
    assert table.at["Chris Wood", "archetype"] == "Target striker"
    assert table.at["Vitinha", "archetype"] == "Tempo-setting playmaker"
    assert table.at["Virgil van Dijk", "archetype"] == "Ball-playing centre-back"
    assert table.at["Achraf Hakimi", "archetype"] == "Attacking wing-back"
    assert table.at["Alisson", "archetype"] == "Sweeper-keeper"
    assert table[["archetype", "gmm_archetype", "gmm_second_archetype"]].notna().all().all()


def test_outputs_are_written(result, tmp_path):
    paths = ce.save(result, tmp_path)
    assert set(paths) == {"plot", "validation", "benchmark", "summary", "summary_markdown",
                          "assignments", "possession"}
    for path in paths.values():
        assert path.exists() and path.stat().st_size > 200, path
    assert paths["plot"].read_bytes()[:8] == b"\x89PNG\r\n\x1a\n"
    assignments = pd.read_csv(paths["assignments"])
    assert len(assignments) == 1576
    assert {"p_cluster_1", "p_cluster_2", "p_cluster_3"} <= set(assignments.columns)
