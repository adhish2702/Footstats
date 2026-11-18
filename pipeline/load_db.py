"""Load FootStats into PostgreSQL.

Reads the FBref CSV, runs the existing expected goal-contributions model
(footstats/model.py, unchanged) and the role ratings, and writes clubs,
players, player_stats, model_versions and predictions to the database in
DATABASE_URL. Predictions are computed here, once; the API only reads them.

Every run rebuilds the tables from db/schema.sql inside one transaction, so
the database either has the complete new load or keeps the previous one.

    python load_db.py                     # uses DATABASE_URL from the repo's .env
    python load_db.py --dry-run           # build everything, print counts, write nothing
    python load_db.py --database-url postgresql://...
"""
from __future__ import annotations

import argparse
import hashlib
import os
import re
import sys
import unicodedata
from pathlib import Path

import numpy as np
import pandas as pd

from footstats.data import DEFAULT_CSV, load_players, per90
from footstats.model import FEATURES, SEED, TARGET, ModelReport, train_and_evaluate
from footstats.ratings import compute_ratings

ROOT = Path(__file__).resolve().parents[1]
SCHEMA = ROOT / "db" / "schema.sql"
SEASON = "2024-25"


def snake(name: str) -> str:
    """"Shot-creating actions" -> "shot_creating_actions"."""
    return re.sub(r"[^a-z0-9]+", "_", name.lower()).strip("_")


# FBref stat -> player_stats column. The model's inputs, then a few extras for the profile.
STYLE_COLUMNS = {f: f"{snake(f)}_p90" for f in FEATURES}
EXTRA_P90 = {"Tackles won": "tackles_won_p90", "Interceptions": "interceptions_p90",
             "Clearances": "clearances_p90"}


# Letters that Unicode does not split into a base letter plus an accent.
_SPECIAL_LETTERS = str.maketrans({"ø": "o", "Ø": "O", "đ": "d", "Đ": "D", "ł": "l", "Ł": "L",
                                  "ß": "ss", "æ": "ae", "Æ": "AE", "ı": "i", "ð": "d", "Ð": "D",
                                  "þ": "th", "Þ": "Th", "’": "'"})


def search_key(name: str) -> str:
    """Lower case with accents removed, for name search: "Martin Ødegaard" -> "martin odegaard".
    The API folds the search text the same way (api/src/text.ts)."""
    text = unicodedata.normalize("NFKD", name.translate(_SPECIAL_LETTERS))
    text = "".join(c for c in text if not unicodedata.combining(c))
    return re.sub(r"\s+", " ", text.lower()).strip()


def file_sha256(path: str | Path) -> str:
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def model_version(report: ModelReport, data_sha256: str) -> str:
    """A label that changes whenever the data, the inputs or the chosen model change,
    e.g. "npga90-ridge-regression-1a2b3c4d"."""
    fingerprint = "|".join([data_sha256, ",".join(FEATURES), str(SEED), report.chosen_model])
    return f"npga90-{snake(report.chosen_model).replace('_', '-')}-" \
           f"{hashlib.sha256(fingerprint.encode()).hexdigest()[:8]}"


def build_tables(df: pd.DataFrame, report: ModelReport, ratings: pd.Series,
                 data_sha256: str) -> dict[str, pd.DataFrame]:
    """The five tables as DataFrames, columns named as in db/schema.sql."""
    # clubs: one row per (club, league), numbered in a stable order.
    clubs = (df[["Club", "League"]].drop_duplicates().sort_values(["League", "Club"])
             .reset_index(drop=True).rename(columns={"Club": "name", "League": "league"}))
    clubs.insert(0, "id", range(1, len(clubs) + 1))
    club_id = {(r.name, r.league): r.id for r in clubs.itertuples()}

    players = pd.DataFrame({
        "id": df["id"].astype(int),
        "name": df["Player Name"],
        "search_name": df["Player Name"].map(search_key),
        "club_id": [club_id[(c, l)] for c, l in zip(df["Club"], df["League"])],
        "clubs_played": df["Clubs"],
        "nationality": df["Nationality"].replace("", None),
        "age": df["Age"].astype("Int64"),
        "birth_year": df["Born"].where(df["Born"] > 0).astype("Int64"),
        "position": df["Position"],
        "role": df["Role"],
        "appearances": df["Appearances"].astype(int),
        "starts": df["Starts"].astype(int),
        "minutes": df["Minutes"].astype(int),
        "qualified": df["Qualified"].astype(bool),
        "rating": df["id"].map(ratings).round(1),
    })

    style = per90(df, FEATURES).rename(columns=STYLE_COLUMNS)
    extra = per90(df, list(EXTRA_P90)).rename(columns=EXTRA_P90)
    output = per90(df, ["Non-penalty goal contributions", "npxG", "xAG"])
    is_gk = df["Position"] == "GKP"
    stats = pd.DataFrame({
        "player_id": df["id"].astype(int),
        "goals": df["Goals"].astype(int),
        "assists": df["Assists"].astype(int),
        "penalty_goals": df["Penalty goals"].astype(int),
        "non_penalty_goals": df["Non-penalty goals"].astype(int),
        "xg": df["xG"].round(1),
        "npxg": df["npxG"].round(1),
        "xag": df["xAG"].round(1),
        "npga_p90": output["Non-penalty goal contributions"].round(3),
        "npxg_p90": output["npxG"].round(3),
        "xag_p90": output["xAG"].round(3),
    })
    stats = pd.concat([stats, style.round(3), extra.round(3)], axis=1)
    stats["pass_accuracy_pct"] = (df["Pass accuracy"] * 100).round(1)
    stats["saves_pct"] = (df["Save %"] * 100).round(1).where(is_gk)
    stats["clean_sheets"] = df["Clean sheets"].where(is_gk).astype("Int64")
    stats["goals_conceded"] = df["Goals conceded"].where(is_gk).astype("Int64")
    stats["goals_prevented"] = df["Goals prevented"].round(1).where(is_gk)

    version = model_version(report, data_sha256)
    versions = pd.DataFrame([{
        "version": version, "model_name": report.chosen_model,
        "target": f"Non-penalty goals + assists per 90 ({TARGET})", "season": SEASON,
        "n_players": report.n_players, "n_train": report.n_train, "n_test": report.n_test,
        "cv_mae": report.cv_mae[report.chosen_model], "test_mae": report.test_mae,
        "baseline_mae": report.baseline_mae, "test_r2": report.test_r2,
        "xg_mae": report.xg_mae, "xg_r2": report.xg_r2,
        "features": report.feature_importance, "data_sha256": data_sha256,
    }])

    held_out = {p["id"] for p in report.test_points}
    expected = report.expected
    predictions = pd.DataFrame({
        "player_id": expected["id"].astype(int),
        "model_version": version,
        "predicted_p90": expected["expected"].round(3),
        "actual_p90": expected["actual"].round(3),
        "in_test_set": expected["id"].isin(held_out),
    })
    return {"clubs": clubs, "players": players, "player_stats": stats,
            "model_versions": versions, "predictions": predictions}


def build(csv_path: str | Path = DEFAULT_CSV) -> dict[str, pd.DataFrame]:
    df = load_players(csv_path)
    ratings, _ = compute_ratings(df)
    report = train_and_evaluate(df)
    return build_tables(df, report, ratings, file_sha256(csv_path))


def _python(value):
    """numpy/pandas scalars -> plain Python values psycopg can send."""
    if value is None or (isinstance(value, float) and np.isnan(value)) or value is pd.NA:
        return None
    if isinstance(value, np.generic):
        return value.item()
    return value


def write(database_url: str, tables: dict[str, pd.DataFrame]) -> dict[str, int]:
    """Recreate the schema and load every table in one transaction. Returns row counts."""
    import psycopg
    from psycopg.types.json import Jsonb

    with psycopg.connect(database_url) as conn:
        with conn.transaction():
            conn.execute(SCHEMA.read_text(encoding="utf-8"))
            for name in ("clubs", "players", "player_stats", "model_versions", "predictions"):
                table = tables[name]
                columns = ", ".join(table.columns)
                with conn.cursor().copy(f"COPY {name} ({columns}) FROM STDIN") as copy:
                    for row in table.itertuples(index=False):
                        copy.write_row([Jsonb(v) if isinstance(v, (list, dict)) else _python(v)
                                        for v in row])
        counts = {name: conn.execute(f"SELECT count(*) FROM {name}").fetchone()[0]
                  for name in tables}
    return counts


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Load FootStats into PostgreSQL.")
    parser.add_argument("--database-url", help="defaults to DATABASE_URL (from .env if present)")
    parser.add_argument("--csv", default=str(DEFAULT_CSV), help="FBref player CSV")
    parser.add_argument("--dry-run", action="store_true", help="build the tables but write nothing")
    args = parser.parse_args(argv)

    try:
        from dotenv import load_dotenv
        load_dotenv(ROOT / ".env")
    except ImportError:
        pass

    print("Loading data and training the model...")
    tables = build(args.csv)
    version = tables["model_versions"].iloc[0]
    print(f"Model {version['version']}: held-out MAE {version['test_mae']} "
          f"(baseline {version['baseline_mae']}), R² {version['test_r2']} "
          f"on {version['n_test']} players")
    if args.dry_run:
        for name, table in tables.items():
            print(f"  {name}: {len(table)} rows")
        return 0

    url = args.database_url or os.getenv("DATABASE_URL")
    if not url:
        print("No database: set DATABASE_URL in .env or pass --database-url.", file=sys.stderr)
        return 1
    counts = write(url, tables)
    for name, n in counts.items():
        print(f"  {name}: {n} rows")
    return 0


if __name__ == "__main__":
    sys.exit(main())
