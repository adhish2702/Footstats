"""The database load: table contents without a database, and a real load when one is set up."""
import os
import re
from pathlib import Path

import numpy as np
import pytest

import load_db
from footstats.model import FEATURES

SCHEMA = Path(load_db.SCHEMA).read_text(encoding="utf-8")


@pytest.fixture(scope="module")
def tables():
    return load_db.build()


def schema_columns(table: str) -> list[str]:
    """Column names of a table in db/schema.sql (generated columns and defaults left out)."""
    body = re.search(rf"CREATE TABLE {table} \((.*?)\n\);", SCHEMA, re.S).group(1)
    names = []
    for line in body.splitlines():
        line = line.strip()
        if not line or line.startswith(("--", "PRIMARY", "UNIQUE", "CHECK", "('")):
            continue
        if "GENERATED" in line or "DEFAULT now()" in line:
            continue
        names.append(line.split()[0])
    return names


def test_tables_match_the_schema(tables):
    for name, table in tables.items():
        assert list(table.columns) == schema_columns(name), name


def test_row_counts(tables):
    assert len(tables["clubs"]) == 96
    assert len(tables["players"]) == len(tables["player_stats"]) == 2707
    assert len(tables["model_versions"]) == 1
    assert len(tables["predictions"]) == 1457


def test_keys_line_up(tables):
    players, clubs = tables["players"], tables["clubs"]
    assert players["id"].is_unique and clubs["id"].is_unique
    assert players["club_id"].isin(clubs["id"]).all()
    assert set(clubs["league"]) == {"Premier League", "La Liga", "Serie A", "Bundesliga", "Ligue 1"}
    assert (tables["player_stats"]["player_id"] == players["id"]).all()
    assert tables["predictions"]["player_id"].isin(players["id"]).all()


def test_required_columns_have_no_gaps(tables):
    nullable = {"players": {"nationality", "age", "birth_year"},
                "player_stats": {"saves_pct", "clean_sheets", "goals_conceded", "goals_prevented"}}
    for name, table in tables.items():
        gaps = set(table.columns[table.isna().any()])
        assert gaps <= nullable.get(name, set()), (name, gaps)


# The API's tests check the same pairs (api/tests/text.test.ts), so both sides fold alike.
SEARCH_KEYS = {
    "Martin Ødegaard": "martin odegaard",
    "Đorđe Petrović": "dorde petrovic",
    "Kylian Mbappé": "kylian mbappe",
    "Son Heung-min": "son heung-min",
    "  Obite  N'Dicka ": "obite n'dicka",
    "Hakan Çalhanoğlu": "hakan calhanoglu",
    "Þórir Jóhann Helgason": "thorir johann helgason",
    "Albert Guðmundsson": "albert gudmundsson",
    "Nico O’Reilly": "nico o'reilly",
}


def test_search_key_folds_accents_and_case():
    for name, key in SEARCH_KEYS.items():
        assert load_db.search_key(name) == key, name


def test_every_player_has_a_search_name(tables):
    players = tables["players"]
    assert players["search_name"].str.len().gt(0).all()
    assert players["search_name"].str.match(r"^[a-z0-9 '\-.]+$").all()


def test_goalkeeping_stats_only_for_goalkeepers(tables):
    keepers = tables["players"]["position"] == "GKP"
    stats = tables["player_stats"]
    assert stats.loc[keepers, "saves_pct"].notna().all()
    assert stats.loc[~keepers, "saves_pct"].isna().all()


def test_style_columns_are_the_model_inputs(tables):
    assert list(load_db.STYLE_COLUMNS) == FEATURES
    assert set(load_db.STYLE_COLUMNS.values()) <= set(tables["player_stats"].columns)


def test_predictions_are_the_models_out_of_fold_output(tables):
    p = tables["predictions"]
    players = tables["players"].set_index("id")
    covered = players.loc[p["player_id"]]
    assert covered["qualified"].all() and (covered["position"] != "GKP").all()
    assert (p["predicted_p90"] >= 0).all()
    assert p["in_test_set"].sum() == 292
    # actual matches the stored non-penalty G+A per 90
    stats = tables["player_stats"].set_index("player_id")
    assert np.allclose(p["actual_p90"], stats.loc[p["player_id"], "npga_p90"], atol=0.001)


def test_model_version_records_the_real_metrics(tables):
    v = tables["model_versions"].iloc[0]
    assert v["model_name"] == "Ridge regression"
    assert (v["n_players"], v["n_train"], v["n_test"]) == (1457, 1165, 292)
    assert v["test_mae"] == pytest.approx(0.0696, abs=1e-4)
    assert v["baseline_mae"] == pytest.approx(0.1674, abs=1e-4)
    assert v["test_r2"] == pytest.approx(0.785, abs=1e-3)
    assert v["cv_mae"] == pytest.approx(0.0759, abs=1e-4)
    assert re.fullmatch(r"npga90-ridge-regression-[0-9a-f]{8}", v["version"])
    assert len(v["data_sha256"]) == 64
    assert {f["feature"] for f in v["features"]} >= set(FEATURES)
    assert (tables["predictions"]["model_version"] == v["version"]).all()


def test_version_is_stable(tables):
    v = tables["model_versions"].iloc[0]
    again = load_db.build()["model_versions"].iloc[0]["version"]
    assert again == v["version"]


def test_dry_run_writes_nothing(capsys):
    assert load_db.main(["--dry-run"]) == 0
    assert "predictions: 1457 rows" in capsys.readouterr().out


@pytest.mark.skipif(not os.getenv("TEST_DATABASE_URL"), reason="TEST_DATABASE_URL not set")
def test_load_into_a_real_database(tables):
    import psycopg

    url = os.environ["TEST_DATABASE_URL"]
    counts = load_db.write(url, tables)
    assert counts == {"clubs": 96, "players": 2707, "player_stats": 2707,
                      "model_versions": 1, "predictions": 1457}
    with psycopg.connect(url) as conn:
        gap = conn.execute("SELECT round(avg(gap_p90), 3) FROM predictions").fetchone()[0]
        assert abs(float(gap)) < 0.01
        mae = conn.execute("SELECT test_mae FROM model_versions").fetchone()[0]
        assert float(mae) == pytest.approx(0.0696, abs=1e-4)
    # A second load replaces the first rather than adding to it.
    assert load_db.write(url, tables) == counts
