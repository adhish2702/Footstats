import pandas as pd

from footstats.data import FORWARD_POSITIONS, LEAGUES, POSITIONS, load_players, striker_score
from footstats.ratings import RATING_WEIGHTS


def name_row(fs, name):
    return fs.df[fs.df["Player Name"] == name].iloc[0]


def rank_of(fs, name):
    return fs.player(int(name_row(fs, name)["id"]))["role_rank"]["rank"]


# ---- data -------------------------------------------------------------------
def test_all_five_leagues_loaded():
    df = load_players()
    assert set(df["League"]) == set(LEAGUES)
    assert df["Club"].nunique() == 96  # 20 + 20 + 20 + 18 + 18
    assert len(df) > 2500


def test_one_row_per_player_after_merging_transfers():
    df = load_players()
    assert not df.duplicated(["Player Name", "Born"]).any()
    # Khusanov played for Lens and Manchester City in 2024/25.
    k = df[df["Player Name"] == "Abdukodir Khusanov"].iloc[0]
    assert k["Minutes"] == 975 + 503
    assert {"Lens", "Manchester City"} == set(k["Clubs"].split(" / "))
    assert k["Club"] == "Lens"  # club with the most minutes


def test_rates_recomputed_and_in_range():
    df = load_players()
    for col in ["Pass accuracy", "Challenge success", "Aerial win %", "Save %", "Crosses stopped %"]:
        assert df[col].between(0, 1).all(), col
    passers = df[df["Passes attempted"] > 0]
    pd.testing.assert_series_equal(
        passers["Pass accuracy"], passers["Passes completed"] / passers["Passes attempted"],
        check_names=False,
    )


def test_source_is_internally_consistent():
    df = load_players()
    assert (df["Shots on target"] <= df["Shots"]).all()
    assert (df["Tackles won"] <= df["Tackles"]).all()
    assert (df["Saves"] <= df["Shots on target faced"]).all()
    assert (df["Penalty goals"] <= df["Goals"]).all()


def test_ratings_use_non_penalty_goals():
    df = load_players()
    kane = df[df["Player Name"] == "Harry Kane"].iloc[0]
    assert kane["Non-penalty goals"] == kane["Goals"] - kane["Penalty goals"] == 17
    for role, weights in RATING_WEIGHTS.items():
        assert "Goals" not in weights and "xG" not in weights, role
    for role in ("Poacher", "Inside forward", "Advanced playmaker"):
        assert "Non-penalty goals" in RATING_WEIGHTS[role]


# ---- striker / winger split ---------------------------------------------------
def test_every_position_is_present():
    df = load_players()
    assert set(df["Position"]) == set(POSITIONS)


def test_forwards_split_into_strikers_and_wingers():
    df = load_players().set_index("Player Name")
    strikers = ["Erling Haaland", "Harry Kane", "Robert Lewandowski", "Mateo Retegui",
                "Serhou Guirassy", "Alexander Isak", "Chris Wood", "Ollie Watkins"]
    wingers = ["Lamine Yamal", "Bukayo Saka", "Mohamed Salah", "Vinicius Júnior",
               "Michael Olise", "Raphinha", "Nico Williams", "Rafael Leão"]
    assert (df.loc[strikers, "Position"] == "STR").all()
    assert (df.loc[wingers, "Position"] == "WNG").all()
    # Neither role is a leftover bucket.
    qualified = df[df["Qualified"]]["Position"].value_counts()
    assert min(qualified["STR"], qualified["WNG"]) > 120


def test_role_split_ignores_goals_and_assists():
    # The split should describe how a forward plays, not how productive they are.
    df = load_players()
    forwards = df[df["Position"].isin(FORWARD_POSITIONS)]
    boosted = forwards.assign(Goals=forwards["Goals"] + 20, Assists=forwards["Assists"] + 20)
    pd.testing.assert_series_equal(striker_score(forwards), striker_score(boosted))


# ---- ratings ----------------------------------------------------------------
def test_ratings_in_range(fs):
    assert fs.df["Rating"].between(0, 99).all()


def test_weights_sum_to_one():
    for weights in RATING_WEIGHTS.values():
        assert abs(sum(abs(w) for w in weights.values()) - 1) < 1e-9


def test_ratings_recognise_standout_seasons(fs):
    # Rank among qualified players in the same role.
    assert rank_of(fs, "Kylian Mbappé") <= 3        # inside forwards
    assert rank_of(fs, "Mohamed Salah") <= 3
    assert rank_of(fs, "Ousmane Dembélé") <= 5      # wide playmakers
    assert rank_of(fs, "Michael Olise") <= 5
    assert rank_of(fs, "Robert Lewandowski") <= 5   # poachers
    assert rank_of(fs, "Erling Haaland") <= 10
    assert rank_of(fs, "Harry Kane") <= 5           # false nines
    assert rank_of(fs, "Joshua Kimmich") <= 5       # deep-lying playmakers
    assert rank_of(fs, "Kevin De Bruyne") <= 5      # advanced playmakers


def test_each_role_averages_fifty(fs):
    qualified = fs.df[fs.df["Qualified"]]
    means = qualified.groupby("Role")["Rating"].mean()
    assert means.between(48, 52).all(), means.round(1).to_dict()


def test_percentiles_cover_the_roles_metrics(fs):
    for _, row in fs.df.sample(200, random_state=0).iterrows():
        assert set(fs.percentiles[int(row["id"])]) == set(RATING_WEIGHTS[row["Role"]])


def test_low_minute_players_shrunk_toward_average(fs):
    low = fs.df[fs.df["Minutes"] < 200]
    assert (low["Rating"] - 50).abs().max() < 12


def test_lower_is_better_metric_inverted(fs):
    gk = fs.df[(fs.df["Position"] == "GKP") & fs.df["Qualified"]]
    gk = gk.assign(ga90=gk["Goals conceded"] / gk["Minutes"] * 90)
    best, worst = gk.loc[gk["ga90"].idxmin()], gk.loc[gk["ga90"].idxmax()]
    assert fs.percentiles[int(best["id"])]["Goals conceded"] > fs.percentiles[int(worst["id"])]["Goals conceded"]


# ---- roles report ------------------------------------------------------------
def test_roles_report_describes_every_role(fs):
    report = fs.roles_report()
    assert [p["position"] for p in report["positions"]] == POSITIONS
    roles = [r for p in report["positions"] for r in p["roles"]]
    assert len(roles) == 18
    for r in roles:
        assert r["size"] >= 25 and r["more_of"] and len(r["examples"]) == 3
        assert abs(sum(w["weight"] for w in r["weights"]) - 1) < 1e-9
    assert 0.5 < report["agreement"] < 1


# ---- similar players --------------------------------------------------------
def test_similar_players_same_position_any_league(fs):
    pid = int(name_row(fs, "Bruno Guimarães")["id"])
    sims = fs.player(pid)["similar"]
    assert len(sims) == 5
    assert pid not in {s["id"] for s in sims}
    positions = fs.df.set_index("id").loc[[s["id"] for s in sims], "Position"]
    assert (positions == "MID").all()
    assert [s["similarity"] for s in sims] == sorted((s["similarity"] for s in sims), reverse=True)


# ---- model ------------------------------------------------------------------
def test_model_beats_baseline_on_held_out_data(fs):
    r = fs.model_report()
    assert r["n_test"] >= 250
    assert r["test_mae"] < 0.6 * r["baseline_mae"]
    assert r["test_r2"] > 0.6


def test_model_is_benchmarked_against_xg(fs):
    r = fs.model_report()
    # Professional xG uses shot locations we don't, so it should be at least as good;
    # the model should still land in the same range.
    assert r["xg_mae"] <= r["test_mae"] < 1.5 * r["xg_mae"]


def test_model_does_not_use_goals_assists_or_xg():
    from footstats.model import FEATURES

    leaky = {"Goals", "Assists", "xG", "npxG", "xAG", "Penalty goals", "Goal Contributions",
             "Non-penalty goals", "Non-penalty goal contributions"}
    assert not leaky & set(FEATURES)


def test_penalty_takers_are_not_flagged_as_overperformers(fs):
    # The model can't see who takes penalties, so its target must exclude them;
    # otherwise the actual-minus-expected gap just tracks penalty goals.
    d = fs.df[fs.df["Qualified"]].dropna(subset=["xGA90"])
    gap = d["GA90"] - d["xGA90"]
    pens90 = d["Penalty goals"] / d["Minutes"] * 90
    assert abs(gap.corr(pens90)) < 0.15


def test_test_points_are_unseen_players(fs):
    r = fs.model_report()
    assert len(r["test_points"]) == r["n_test"]
    assert r["n_train"] + r["n_test"] == r["n_players"]


# ---- scouting ---------------------------------------------------------------
def test_scouting_targets_exclude_elite_clubs(fs):
    from footstats.service import ELITE_CLUBS

    targets = fs.scouting_targets(limit=50)
    assert targets and not {t["club"] for t in targets} & ELITE_CLUBS
    assert all(t["qualified"] for t in targets)
    assert len({t["league"] for t in targets}) > 1


def test_scouting_filters_by_league_and_age(fs):
    targets = fs.scouting_targets("MID", 20, league="Serie A", max_age=23)
    assert targets
    assert all(t["league"] == "Serie A" and t["age"] <= 23 for t in targets)
