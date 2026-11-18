import pandas as pd
import pytest

from footstats import market_values as mv
from footstats.data import load_players


# ---- names ---------------------------------------------------------------------------
def test_fold_ignores_accents_case_and_punctuation():
    assert mv.fold("Obite N'Dicka") == "obite ndicka"
    assert mv.fold("Pierre-Emile Højbjerg") == "pierre emile hojbjerg"
    assert mv.fold("  Đorđe   PETROVIĆ ") == "dorde petrovic"
    assert mv.fold("Lee Jae-sung") == "lee jae sung"


def test_name_closeness_tiers():
    close = mv._closeness
    assert close("lee jae sung", "jae sung lee") == 1.0             # same words, other order
    assert close("catena", "alejandro catena") == 0.95              # one inside the other
    assert close("max kilman", "maximilian kilman") == 0.9          # same surname
    assert close("alex palmer", "kasey palmer", surname_counts=False) < 0.88
    assert close("yeremi pino", "yeremy pino") > 0.88               # spelling
    assert close("erling haaland", "bukayo saka") < 0.5
    assert close("", "anyone") == 0.0


# ---- matching, on a hand-made example ----------------------------------------------------
def _fbref(rows):
    df = pd.DataFrame(rows, columns=["Player Name", "Born", "Club", "League"])
    df["Clubs"] = df["Club"]
    df.insert(0, "id", range(len(df)))
    return df


def _transfermarkt(rows):
    tm = pd.DataFrame(rows, columns=["player_id", "name", "born", "club", "club_id", "league", "value"])
    tm["key"] = tm["name"].map(mv.fold)
    tm["value_date"] = pd.Timestamp("2025-06-01")
    tm["club_ids"] = tm["club_id"].map(lambda c: frozenset([c]))
    tm["past_club_ids"] = tm["club_ids"]
    tm["leagues"] = tm["league"].map(lambda c: frozenset([c] if c else []))
    return tm


@pytest.fixture(scope="module")
def toy_matches():
    fbref = _fbref([
        ("Ana Alpha", 2000, "Milan", "Serie A"),          # plain exact match
        ("Bo Beta", 2000, "Milan", "Serie A"),            # teaches the club mapping
        ("Emerson", 1999, "Milan", "Serie A"),            # namesake abroad must be refused
        ("Vitinha", 2000, "Milan", "Serie A"),            # two candidates, league decides
        ("Kid Gamma", 2006, "Milan", "Serie A"),          # registered with the reserve side
        ("Max Delta", 1997, "Milan", "Serie A"),          # "Maximilian Delta" at the same club
        ("Alex Palmer", 1996, "Milan", "Serie A"),        # only a different Palmer exists
        ("Zed Omega", 1990, "Milan", "Serie A"),          # not in Transfermarkt at all
    ])
    tm = _transfermarkt([
        (1, "Ana Alpha", 2000, "AC Milan", 5, "IT1", 10_000_000),
        (2, "Bo Beta", 2000, "AC Milan", 5, "IT1", 20_000_000),
        (3, "Emerson", 1999, "V-Varen Nagasaki", 77, None, 800_000),
        (4, "Emerson Royal", 1999, "AC Milan", 5, "IT1", 9_000_000),
        (5, "Vitinha", 2000, "Paris Saint-Germain", 9, "FR1", 80_000_000),
        (6, "Vitinha", 2000, "AC Milan", 5, "IT1", 8_000_000),
        (7, "Kid Gamma", 2006, "Milan Futuro", 55, None, 300_000),
        (8, "Maximilian Delta", 1997, "AC Milan", 5, "IT1", 25_000_000),
        (9, "Kasey Palmer", 1996, "Hull City", 60, "IT1", 1_000_000),
    ])
    return mv.match_players(fbref, tm).set_index("Player")


def test_exact_matches(toy_matches):
    assert toy_matches.at["Ana Alpha", mv.VALUE_COLUMN] == 10_000_000
    assert toy_matches.at["Ana Alpha", "Match"] == "exact"
    assert toy_matches.at["Ana Alpha", "Valuation date"] == "2025-06-01"


def test_league_separates_two_players_with_the_same_name(toy_matches):
    assert toy_matches.at["Vitinha", "Transfermarkt id"] == 6


def test_namesake_with_no_link_to_the_club_is_refused(toy_matches):
    # Not the Emerson in Japan; the club pass then finds Emerson Royal at Milan.
    assert toy_matches.at["Emerson", "Transfermarkt name"] == "Emerson Royal"
    assert toy_matches.at["Emerson", "Match"] == "club"


def test_reserve_side_counts_as_the_same_club(toy_matches):
    assert toy_matches.at["Kid Gamma", "Transfermarkt club"] == "Milan Futuro"
    assert toy_matches.at["Kid Gamma", "Match"] == "exact"


def test_name_variant_at_the_same_club(toy_matches):
    assert toy_matches.at["Max Delta", "Transfermarkt name"] == "Maximilian Delta"
    assert toy_matches.at["Max Delta", "Match"] == "club"


def test_doubtful_players_are_left_unmatched(toy_matches):
    assert "Alex Palmer" not in toy_matches.index   # same surname, same league: not enough
    assert "Zed Omega" not in toy_matches.index
    assert toy_matches["Transfermarkt id"].is_unique


# ---- the built file -------------------------------------------------------------------------
@pytest.fixture(scope="module")
def values_file() -> pd.DataFrame:
    if not mv.VALUES_CSV.exists():
        pytest.skip("market values file not built")
    return pd.read_csv(mv.VALUES_CSV, encoding="utf-8-sig")


def test_values_file_covers_most_regular_players(values_file):
    df = load_players()
    values = mv.load_market_values(df)
    assert values.name == mv.VALUE_COLUMN and list(values.index) == list(df["id"])
    regular = (df["Minutes"] >= 500).to_numpy()
    assert values[regular].notna().mean() > 0.95
    assert values.notna().sum() == len(values_file) > 2400
    assert (values_file[mv.VALUE_COLUMN] > 0).all()


def test_values_file_is_one_price_per_player(values_file):
    assert values_file["Transfermarkt id"].is_unique
    assert not values_file.duplicated(["Player", "Born"]).any()
    assert set(values_file["Match"]) <= {"exact", "club", "league"}
    assert (values_file["Match"] == "exact").mean() > 0.9
    assert values_file["Valuation date"].between(mv.VALUE_FROM, mv.SEASON_END).all()
    # Nearly every price is from the end of the season, not the summer before.
    assert (values_file["Valuation date"] >= "2025-05-01").mean() > 0.95


def test_known_prices_and_tricky_names(values_file):
    by_name = values_file.set_index(["Player", "Club"])
    assert by_name.at[("Lamine Yamal", "Barcelona"), mv.VALUE_COLUMN] == 200_000_000
    assert by_name.at[("Erling Haaland", "Manchester City"), mv.VALUE_COLUMN] == 180_000_000
    assert by_name.at[("Vitinha", "Paris S-G"), mv.VALUE_COLUMN] == 80_000_000
    assert by_name.at[("Emerson", "Milan"), "Transfermarkt name"] == "Emerson Royal"
    assert by_name.at[("Liam Henderson", "Empoli"), "Transfermarkt club"] != "Falkirk FC"
    assert by_name.at[("Max Kilman", "West Ham"), "Transfermarkt name"] == "Maximilian Kilman"
    assert by_name.at[("Son Heung-min", "Tottenham"), "Transfermarkt name"] == "Heung-min Son"
    assert ("Alex Palmer", "Ipswich Town") not in by_name.index


def test_missing_file_means_no_values(tmp_path):
    assert mv.load_market_values(load_players(), tmp_path / "nothing.csv") is None


@pytest.mark.skipif(not (mv.TM_DIR / "player_valuations.csv.gz").exists(),
                    reason="Transfermarkt downloads not present")
def test_rebuilding_gives_the_same_file(values_file, tmp_path):
    rebuilt = mv.build(out=tmp_path / "values.csv")
    assert len(rebuilt) == len(values_file)
    again = pd.read_csv(tmp_path / "values.csv", encoding="utf-8-sig")
    pd.testing.assert_frame_equal(again, values_file)
