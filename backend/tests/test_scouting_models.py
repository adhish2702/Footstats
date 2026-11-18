import numpy as np
import pandas as pd
import pytest

from footstats import clustering_engine as ce
from footstats import market_values as mv
from footstats import scouting_models as sm
from footstats.data import LEAGUES


@pytest.fixture(scope="module")
def engine() -> sm.ScoutingEngine:
    """The engine without prices: the efficiency model."""
    return sm.ScoutingEngine.build(mode="efficiency")


@pytest.fixture(scope="module")
def priced(engine) -> sm.ScoutingEngine:
    """The engine as it runs by default, on Transfermarkt market values."""
    if not mv.VALUES_CSV.exists():
        pytest.skip("market values file not built")
    return sm.ScoutingEngine.build(clustering=engine.clustering)


# ---- style vectors and clusters ------------------------------------------------------
def test_vectors_use_the_clustering_scale(engine):
    for group, r in engine.clustering.groups.items():
        v = engine.vectors[group]
        assert np.isfinite(v.to_numpy()).all(), group
        # Players the engine clustered get exactly the engine's z-scores...
        assert np.allclose(v.loc[r.scaled.index], r.scaled), group
        # ...and lower-minute players are added on the same scale.
        assert len(v) > len(r.scaled), group
    assert sum(len(v) for v in engine.vectors.values()) == len(engine.players) == 2707


def test_every_player_has_a_cluster(engine):
    p = engine.players
    for group, r in engine.clustering.groups.items():
        members = p[p["Group"] == group]
        assert set(members["Cluster_ID"]) == set(r.names), group
        assert (members.loc[r.labels.index, "Cluster_ID"] == r.labels).all(), group
        assert set(members["Cluster"]) == set(r.names.values()), group
    assert p["Clustered"].sum() == 1576
    assert (p.loc[p["Clustered"], "Minutes"] >= 900).all()


# ---- 1. similarity ---------------------------------------------------------------------
def test_similarity_matrix_is_cosine(engine):
    for group, sim in engine.similarity.items():
        values = sim.to_numpy()
        assert values.shape == (len(engine.vectors[group]),) * 2, group
        assert np.allclose(values, values.T) and np.allclose(np.diag(values), 1), group
        assert values.min() >= -1 - 1e-9 and values.max() <= 1 + 1e-9, group
    v = engine.vectors["MID"]
    a, b = v.index[0], v.index[1]
    expected = v.loc[a] @ v.loc[b] / (np.linalg.norm(v.loc[a]) * np.linalg.norm(v.loc[b]))
    assert engine.similarity["MID"].at[a, b] == pytest.approx(expected)


def test_find_similar_players_table(engine):
    table = engine.find_similar_players("Vitinha")
    assert len(table) == 10 and table.index.is_unique
    assert {"Player", "Squad", "League", "Pos", "Age", "Minutes", "Similarity_%", "Cluster",
            "Cluster_ID", "Composite_Score", "Value_Gap", "Progressive passes /90",
            "Pass accuracy %"} <= set(table.columns)
    assert table["Similarity_%"].is_monotonic_decreasing
    assert table["Similarity_%"].between(50, 100).all()
    assert "Vitinha" not in set(table["Player"])
    assert (table["Pos"] == "MID").all() and (table["Minutes"] >= 500).all()
    query = table.attrs["query"]
    assert query["Player"] == "Vitinha" and query["Cluster"] == "Tempo-setting playmaker"
    # The module-level function is the same search on a shared engine.
    assert engine.find_similar_players("Vitinha", top_n=3).index.tolist() == table.index[:3].tolist()


def test_similar_players_make_football_sense(engine):
    def matches(name, **kw):
        return engine.find_similar_players(name, **kw)

    assert (matches("Vitinha")["Cluster"] == "Tempo-setting playmaker").mean() >= 0.8
    assert (matches("Virgil van Dijk")["Cluster"] == "Ball-playing centre-back").mean() >= 0.8
    assert (matches("Erling Haaland")["Pos"] == "STR").all()
    assert "Ederson" in set(matches("Alisson", top_n=5)["Player"])
    assert matches("Alisson")["Pos"].eq("GKP").all()


def test_similarity_is_symmetric(engine):
    there = engine.find_similar_players("Pedri", top_n=200).set_index("Player")
    back = engine.find_similar_players("Vitinha", top_n=200).set_index("Player")
    assert there.at["Vitinha", "Similarity_%"] == back.at["Pedri", "Similarity_%"]


def test_similar_player_filters(engine):
    young = engine.find_similar_players("Virgil van Dijk", top_n=8, max_age=22)
    assert len(young) == 8 and (young["Age"] <= 22).all()
    regulars = engine.find_similar_players("Vitinha", min_minutes=2500)
    assert (regulars["Minutes"] >= 2500).all()
    abroad = engine.find_similar_players("Lamine Yamal", leagues=["Serie A", "Ligue 1"])
    assert set(abroad["League"]) <= {"Serie A", "Ligue 1"} and len(abroad) == 10
    assert set(engine.find_similar_players("Lamine Yamal", leagues="serie a")["League"]) == {"Serie A"}
    assert len(engine.find_similar_players("Vitinha", top_n=3)) == 3
    with pytest.raises(ValueError, match="unknown league"):
        engine.find_similar_players("Vitinha", leagues=["Eredivisie"])


def test_player_lookup(engine):
    exact = engine.player_id("Martin Ødegaard")
    assert engine.player_id("martin odegaard") == exact == engine.player_id("Ødegaard")
    with pytest.raises(KeyError):
        engine.player_id("Nobody Atall")
    # Two players are called Nicolás González; the club separates them.
    with pytest.raises(ValueError, match="matches 2 players"):
        engine.player_id("Nicolás González")
    juventus = engine.player_id("Nicolás González", squad="Juventus")
    assert engine.players.at[juventus, "Squad"] == "Juventus"
    assert engine.find_similar_players("Nicolás González", squad="Juventus").attrs["query"]["id"] == juventus


# ---- 2. value model ------------------------------------------------------------------------
def test_the_fbref_csv_has_no_market_value_column(engine, tmp_path):
    assert sm.find_value_column() is None
    assert engine.value.mode == "efficiency" and engine.value.value_column is None
    fake = tmp_path / "with_value.csv"
    fake.write_text("Player,Squad,Min,Market Value (EUR)\nA,B,90,1000000\n", encoding="utf-8")
    assert sm.find_value_column(fake) == "Market Value (EUR)"
    plain = tmp_path / "plain.csv"
    plain.write_text("Player,Squad,Min,Valuable Passes\nA,B,90,3\n", encoding="utf-8")
    assert sm.find_value_column(plain) is None


def test_three_models_are_compared(engine):
    c = engine.value.comparison
    assert list(c.index) == ["Baseline (training mean)", "Ridge regression", "Random forest", "XGBoost"]
    assert c["chosen"].sum() == 1 and c.index[c["chosen"]][0] == engine.value.best
    models = c.drop("Baseline (training mean)")
    assert engine.value.best == models["cv_mae"].idxmin()
    # The chosen model beats always predicting the average, on players it never saw...
    assert c.at[engine.value.best, "test_mae"] < c.at["Baseline (training mean)", "test_mae"]
    # ...but only just: age, minutes and league say little about how good a player is.
    assert 0 < c.at[engine.value.best, "test_r2"] < 0.15


def test_model_inputs_are_only_age_minutes_league_and_position(engine):
    X = engine.value.X
    assert set(engine.value.groups) == {"Age", "Minutes", "League", "Position"}
    assert sorted(c for cols in engine.value.groups.values() for c in cols) == sorted(X.columns)
    assert (X[engine.value.groups["League"]].sum(axis=1) == 1).all()
    assert (X[engine.value.groups["Position"]].sum(axis=1) == 1).all()
    assert len(X) == (engine.players["Minutes"] >= sm.VALUE_MIN_MINUTES).sum() == 1909


def test_value_gap_is_actual_minus_expected(engine):
    p = engine.players
    modelled = p["Value_Gap"].notna()
    assert modelled.sum() == 1909 and (p.loc[modelled, "Minutes"] >= 500).all()
    assert p.loc[~modelled, "Expected_Score"].isna().all()
    gap = p.loc[modelled, "Composite_Score"] - p.loc[modelled, "Expected_Score"]
    assert np.allclose(gap, p.loc[modelled, "Value_Gap"], atol=0.051)
    # Out-of-fold residuals: centred on zero overall and in every league.
    assert abs(p["Value_Gap"].mean()) < 0.3
    assert p.groupby("League")["Value_Gap"].mean().abs().max() < 1.0
    # Expected scores stay near the average: the model has little to go on.
    assert p.loc[modelled, "Expected_Score"].between(40, 60).all()


def test_positive_outliers_are_flagged(engine):
    p = engine.players
    gaps = p["Value_Gap"].dropna()
    fence = sm.upper_fence(gaps)
    assert (p["Gap_Outlier"] == (p["Value_Gap"] > fence)).all()
    assert 5 <= p["Gap_Outlier"].sum() <= 0.05 * len(gaps)
    assert p.loc[p["Gap_Outlier"], "Value_Gap"].min() > gaps.quantile(0.95)
    assert sm.upper_fence(pd.Series([1, 2, 3, 4, 5])) == 7.0


def test_shap_values_add_up_to_the_prediction(engine):
    m = engine.value
    assert m.shap.shape == m.X.shape
    prediction = m.model.predict(m.X)
    assert np.allclose(m.base_value + m.shap.sum(axis=1), prediction, atol=1e-3)
    grouped = m.shap_by_feature()
    assert list(grouped.columns) == ["Age", "Minutes", "League", "Position"]
    assert np.allclose(grouped.sum(axis=1), m.shap.sum(axis=1))
    importance = m.importance()
    features = importance[importance["level"] == "feature"]
    assert features["mean_abs_shap"].is_monotonic_decreasing and len(features) == 4
    assert (importance["mean_abs_shap"] >= 0).all()


# ---- gems ------------------------------------------------------------------------------------
def test_gems_are_young_top_of_cluster_and_over_delivering(engine):
    for group in ce.GROUPS:
        gems = engine.get_undervalued_gems(group)
        assert 0 < len(gems) <= 15, group
        assert (gems["Age"] <= 24).all(), group
        assert (gems["Value_Gap"] > 0).all() and gems["Value_Gap"].is_monotonic_decreasing, group
        assert (gems["Cluster_Percentile"] >= sm.TOP_PERCENTILE).all(), group
        assert (engine.players.loc[gems.index, "Group"] == group).all(), group
    assert "Michael Olise" in set(engine.get_undervalued_gems("FWD")["Player"])


def test_gems_filters(engine):
    by_number = engine.get_undervalued_gems("MID", cluster_id=5)
    by_name = engine.get_undervalued_gems("MID", cluster_id="Advanced creator")
    assert by_number.index.tolist() == by_name.index.tolist() and len(by_number) > 0
    assert (by_number["Cluster"] == "Advanced creator").all()
    assert len(engine.get_undervalued_gems("DEF", top_n=4)) == 4
    assert (engine.get_undervalued_gems("FWD", max_age=20)["Age"] <= 20).all()
    assert (engine.get_undervalued_gems("STR")["Pos"] == "STR").all()
    assert engine.get_undervalued_gems("fwd").index.tolist() == engine.get_undervalued_gems("FWD").index.tolist()
    older = engine.get_undervalued_gems("GKP", max_age=None, top_n=50)
    assert older["Age"].max() > 24
    strict = engine.get_undervalued_gems("FWD", min_cluster_percentile=95)
    assert (strict["Cluster_Percentile"] >= 95).all()
    outside = engine.get_undervalued_gems("FWD", exclude_elite_clubs=True)
    assert not set(outside["Squad"]) & {"Barcelona", "Paris S-G", "Bayern Munich", "Manchester City"}


def test_gems_reject_bad_input(engine):
    with pytest.raises(ValueError, match="unknown position"):
        engine.get_undervalued_gems("LB")
    with pytest.raises(ValueError, match="no MID cluster"):
        engine.get_undervalued_gems("MID", cluster_id="Regista")
    with pytest.raises(ValueError, match="has clusters"):
        engine.get_undervalued_gems("GKP", cluster_id=9)


# ---- the market-value model, on Transfermarkt prices ---------------------------------------------
def test_prices_switch_the_engine_to_market_value(priced):
    m = priced.value
    assert m.mode == "market_value" and m.value_column == mv.VALUE_COLUMN
    assert m.target == "log10 market value"
    p = priced.players
    modelled = p["Value_Gap"].notna()
    assert 1800 < modelled.sum() < 1909
    assert (p.loc[modelled, "Minutes"] >= 500).all() and p.loc[modelled, "Market_Value"].gt(0).all()
    assert p.set_index("Player").at["Lamine Yamal", "Market_Value"] == 200_000_000


def test_market_value_model_beats_the_baseline(priced):
    c = priced.value.comparison
    best = priced.value.best
    assert best == c["cv_mae"].drop("Baseline (training mean)").idxmin()
    assert c.at[best, "test_mae"] < 0.7 * c.at["Baseline (training mean)", "test_mae"]
    assert 0.5 < c.at[best, "test_r2"] < 0.8
    # Every candidate, not just the winner, learns something from these inputs.
    assert (c["test_r2"].drop("Baseline (training mean)") > 0.4).all()


def test_market_value_gap_is_predicted_minus_actual(priced):
    p = priced.players[priced.players["Value_Gap"].notna()]
    assert (p["Value_Gap"] == p["Predicted_Value"] - p["Market_Value"]).all()
    ratio = p["Predicted_Value"].astype(float) / p["Market_Value"].astype(float)
    assert np.allclose(p["Value_Ratio"], ratio, atol=0.006)
    assert (p.loc[p["Value_Gap"] > 0, "Value_Ratio"] >= 1).all()
    assert (p.loc[p["Value_Gap"] < 0, "Value_Ratio"] <= 1).all()
    # Out-of-fold predictions: over- and under-pricing roughly balance.
    assert 0.8 < p["Value_Ratio"].median() < 1.25
    assert 0.35 < (p["Value_Gap"] > 0).mean() < 0.65
    # Outliers are judged on the ratio, so they are not just the expensive players.
    flagged = priced.players[priced.players["Gap_Outlier"]]
    assert 0 < len(flagged) < 0.05 * len(p) and flagged["Value_Ratio"].min() > 3


def test_market_value_shap(priced):
    m = priced.value
    assert np.allclose(m.base_value + m.shap.sum(axis=1), m.model.predict(m.X), atol=1e-3)
    features = m.importance()
    features = features[features["level"] == "feature"].set_index("name")["mean_abs_shap"]
    assert set(features.index) == {"Age", "Minutes", "League", "Position", "Composite score"}
    # Age, playing time and performance each matter more than position.
    assert features[["Age", "Minutes", "Composite score"]].min() > features["Position"]
    grouped = m.shap_by_feature()
    # Better players are predicted to be worth more, and older players less.
    assert np.corrcoef(grouped["Composite score"], m.X["Composite score"])[0, 1] > 0.8
    assert grouped.loc[m.X["Age"] >= 31, "Age"].mean() < 0 < grouped.loc[m.X["Age"] <= 22, "Age"].mean()


def test_priced_gems_and_similar_players(priced):
    for group in ce.GROUPS:
        gems = priced.get_undervalued_gems(group)
        assert len(gems) > 0 and (gems["Age"] <= 24).all(), group
        assert (gems["Value_Gap"] > 0).all() and gems["Value_Gap"].is_monotonic_decreasing, group
        assert (gems["Predicted_Value"] > gems["Market_Value"]).all(), group
        assert (gems["Cluster_Percentile"] >= sm.TOP_PERCENTILE).all(), group
    # The most expensive players are never bargains.
    names = set(priced.get_undervalued_gems("FWD", top_n=50)["Player"])
    assert not names & {"Lamine Yamal", "Erling Haaland", "Kylian Mbappé", "Vinicius Júnior"}
    similar = priced.find_similar_players("Vitinha")
    assert {"Market_Value", "Predicted_Value", "Value_Gap", "Value_Ratio"} <= set(similar.columns)
    assert similar.attrs["query"]["Market_Value"] == 80_000_000


def test_without_the_values_file_the_engine_falls_back(engine, monkeypatch):
    monkeypatch.setattr(sm, "load_market_values", lambda df: None)
    with pytest.raises(FileNotFoundError, match="market_values"):
        sm.ScoutingEngine.build(clustering=engine.clustering, mode="market_value")
    with pytest.raises(ValueError, match="unknown mode"):
        sm.ScoutingEngine.build(clustering=engine.clustering, mode="prices")
    fallback = sm.ScoutingEngine.build(clustering=engine.clustering)
    assert fallback.value.mode == "efficiency"


def test_priced_outputs_are_written(priced, tmp_path):
    paths = sm.save(priced, tmp_path)
    for path in paths.values():
        assert path.exists() and path.stat().st_size > 200, path
    gaps = pd.read_csv(paths["value_gap"])
    assert {"Market_Value", "Predicted_Value", "Value_Gap", "Value_Ratio"} <= set(gaps.columns)
    assert gaps["Value_Gap"].is_monotonic_decreasing
    assert "Transfermarkt" in paths["gems_markdown"].read_text(encoding="utf-8")


# ---- the market-value branch, on made-up prices ----------------------------------------------------
def test_market_value_branch(engine):
    # Invented prices that depend on quality and age, with noise: the engine
    # should switch mode, recover the pattern, and call a half-price player a bargain.
    p = engine.players
    rng = np.random.default_rng(0)
    log_value = (6.0 + 0.04 * (p["Composite_Score"] - 50)
                 - 0.05 * (p["Age"].astype(float).fillna(25) - 25) + rng.normal(0, 0.1, len(p)))
    values = (10 ** log_value).rename("Market Value")
    bargain = engine.player_id("Vitinha")
    values[bargain] /= 4

    priced = sm.ScoutingEngine.build(clustering=engine.clustering, values=values)
    m = priced.value
    assert m.mode == "market_value" and m.value_column == "Market Value"
    assert "Composite score" in m.groups
    assert m.comparison.at[m.best, "test_r2"] > 0.8
    q = priced.players
    modelled = q["Value_Gap"].notna()
    assert np.allclose(q.loc[modelled, "Value_Gap"],
                       q.loc[modelled, "Predicted_Value"] - q.loc[modelled, "Market_Value"], atol=1)
    assert q.at[bargain, "Value_Gap"] > 0 and q.at[bargain, "Gap_Outlier"]
    importance = m.importance()
    features = importance[importance["level"] == "feature"].set_index("name")["mean_abs_shap"]
    assert features.idxmax() == "Composite score"
    assert {"Market_Value", "Predicted_Value"} <= set(priced.get_undervalued_gems("MID").columns)


# ---- outputs ------------------------------------------------------------------------------------------
def test_outputs_are_written(engine, tmp_path):
    paths = sm.save(engine, tmp_path)
    assert set(paths) == {"comparison", "value_gap", "shap_importance", "shap_importance_plot",
                          "shap_effects_plot", "gems", "gems_markdown"}
    for path in paths.values():
        assert path.exists() and path.stat().st_size > 200, path
    for plot in ("shap_importance_plot", "shap_effects_plot"):
        assert paths[plot].read_bytes()[:8] == b"\x89PNG\r\n\x1a\n"
    gaps = pd.read_csv(paths["value_gap"])
    assert len(gaps) == 1909 and gaps["Value_Gap"].is_monotonic_decreasing
    assert set(pd.read_csv(paths["gems"])["group"]) == set(ce.GROUPS)
    assert set(pd.read_csv(paths["gems"])["League"]) <= set(LEAGUES)
