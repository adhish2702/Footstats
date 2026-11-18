import pandas as pd
import pytest

from footstats.clusters import role_agreement
from footstats.data import load_players
from footstats.ratings import RATING_WEIGHTS
from footstats.roles import (FEATURES, FULL_BACK_SIGNALS, ROLE_INFO, ROLES, assign_roles,
                             full_back_score, role_features)

# Players whose role is not in doubt. The split is rule-based, so these are a
# check on the rules, not labels the rules were fitted to.
ARCHETYPES = {
    "Sweeper-keeper": ["David Raya", "Wojciech Szczęsny", "Jordan Pickford"],
    "Ball-playing goalkeeper": ["Yann Sommer", "Guglielmo Vicario", "André Onana"],
    "Ball-playing centre-back": ["Virgil van Dijk", "William Saliba", "Pau Cubarsí", "Rúben Dias"],
    "Stopper": ["James Tarkowski", "Nikola Milenković", "Dan Burn"],
    "Wide centre-back": ["Noussair Mazraoui", "Djené", "Piero Hincapié"],
    "Inverted full-back": ["Rico Lewis", "Marc Cucurella", "Myles Lewis-Skelly"],
    "Wing-back": ["Jeremie Frimpong", "Federico Dimarco", "Denzel Dumfries"],
    "Deep-lying playmaker": ["Granit Xhaka", "Joshua Kimmich", "Stanislav Lobotka"],
    "Ball-winning midfielder": ["Idrissa Gana Gueye", "Wilfred Ndidi", "Tyler Adams"],
    "Box-to-box midfielder": ["Scott McTominay", "Adrien Rabiot"],
    "Advanced playmaker": ["Martin Ødegaard", "Kevin De Bruyne", "Cole Palmer", "Florian Wirtz"],
    "Inside forward": ["Kylian Mbappé", "Mohamed Salah", "Jarrod Bowen"],
    "Touchline winger": ["Pedro Neto", "Nico Williams"],
    "Wide playmaker": ["Michael Olise", "Raphinha", "Antoine Griezmann"],
    "Pressing forward": ["Morgan Guilavogui", "Gorka Guruzeta"],
    "False nine": ["Harry Kane", "Jonathan David", "Amine Gouiri"],
    "Poacher": ["Erling Haaland", "Robert Lewandowski", "Jamie Vardy", "Ollie Watkins"],
    "Target forward": ["Serhou Guirassy", "Vedat Muriqi"],
}


@pytest.fixture(scope="module")
def players() -> pd.DataFrame:
    return load_players()


def test_eighteen_roles_across_five_positions():
    assert {p: len(r) for p, r in ROLES.items()} == {"GKP": 2, "DEF": 5, "MID": 4, "WNG": 3, "STR": 4}
    assert set(ROLE_INFO) == set(RATING_WEIGHTS) == set(ARCHETYPES)


def test_every_player_has_a_role_from_their_position(players):
    assert players["Role"].notna().all()
    position_of_role = players["Role"].map(lambda r: ROLE_INFO[r]["position"])
    assert (position_of_role == players["Position"]).all()


def test_no_role_is_a_leftover_bucket(players):
    sizes = players[players["Qualified"]]["Role"].value_counts()
    assert set(sizes.index) == set(ROLE_INFO)
    assert sizes.min() >= 25


@pytest.mark.parametrize("role", list(ARCHETYPES))
def test_well_known_players_land_in_their_role(players, role):
    by_name = players.set_index("Player Name")["Role"]
    assert {name: by_name[name] for name in ARCHETYPES[role]} == dict.fromkeys(ARCHETYPES[role], role)


def test_roles_ignore_goals_and_assists(players):
    # Roles should describe how someone plays, not how productive they are.
    output = ["Goals", "Assists", "Non-penalty goals", "Penalty goals", "xG", "npxG", "xAG",
              "Goal Contributions", "Non-penalty goal contributions"]
    used = {spec[1] for spec in FEATURES.values()} | {spec[2] for spec in FEATURES.values() if len(spec) > 2}
    assert not used & set(output)
    boosted = players.copy()
    boosted[output] = boosted[output] + 20
    pd.testing.assert_series_equal(assign_roles(boosted), players["Role"])


def test_signals_are_known_features():
    for role, info in ROLE_INFO.items():
        assert set(info["signals"]) <= set(FEATURES), role
        assert set(info["signals"].values()) <= {1, -1}, role
    assert set(FULL_BACK_SIGNALS) <= set(FEATURES)


def test_full_backs_and_centre_backs_are_separated(players):
    defenders = players[players["Position"] == "DEF"]
    score = full_back_score(defenders).set_axis(defenders["Player Name"])
    full_backs = ["Achraf Hakimi", "Trent Alexander-Arnold", "Federico Dimarco", "Antonee Robinson"]
    centre_backs = ["Virgil van Dijk", "William Saliba", "Antonio Rüdiger", "James Tarkowski"]
    assert score[full_backs].min() > 0.4 > 0 > score[centre_backs].max()
    full_back_roles = {"Inverted full-back", "Wing-back"}
    by_name = players.set_index("Player Name")["Role"]
    assert set(by_name[full_backs]) <= full_back_roles
    assert not set(by_name[centre_backs]) & full_back_roles


def test_low_minute_players_get_finite_features(players):
    # Ratios with tiny denominators must not produce NaN or inf.
    features = role_features(players)
    assert features.notna().all().all()
    assert (features.abs() < 1e6).all().all()


def test_assignment_works_on_a_subset_without_qualified_players(players):
    subset = players[~players["Qualified"]].head(200)
    roles = assign_roles(subset)
    assert roles.notna().all()
    assert (roles.map(lambda r: ROLE_INFO[r]["position"]) == subset["Position"]).all()


def test_goalkeeper_averages_in_range(players):
    keepers = players[(players["Position"] == "GKP") & players["Qualified"]]
    assert keepers["Pass length"].between(15, 60).all()
    assert keepers["Launch %"].between(0, 1).all()
    assert keepers["Sweeper distance"].between(5, 30).all()


def test_goalkeeper_averages_are_weighted_across_clubs(players):
    # Summing two clubs' averages would roughly double them.
    moved = players[(players["Position"] == "GKP") & players["Clubs"].str.contains(" / ")
                    & (players["Goalkeeper passes"] > 100)]
    assert len(moved) > 0
    assert moved["Pass length"].between(15, 60).all()


def test_touch_zones_are_consistent(players):
    busy = players[players["Touches"] >= 500]
    assert (busy["Touches in own box"] <= busy["Touches in defensive third"]).all()
    thirds = busy[["Touches in defensive third", "Touches in middle third",
                   "Touches in attacking third"]].sum(axis=1)
    # FBref counts a touch that crosses a line in both thirds, so the sum runs
    # slightly over the total, never under it.
    assert ((thirds / busy["Touches"]).between(1.0, 1.06)).all()


def test_unsupervised_clusters_agree_with_roles_above_chance(players):
    report = role_agreement(players)
    assert set(report) == set(ROLES)
    for position, r in report.items():
        assert r["agreement"] > r["chance"] + 0.15, position
