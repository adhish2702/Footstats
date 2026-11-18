"""Attach Transfermarkt market values to the FBref players.

The FBref export has no prices. This module reads two files from the
transfermarkt-datasets project (github.com/dcaribou/transfermarkt-datasets,
CC0) and writes one small CSV, data/market_values_2024_25.csv, with a market
value in euros for each player it can identify. scouting_models.py picks that
file up automatically.

Which value: each player's last Transfermarkt valuation on or before 30 June
2025, so the price is the market's view at the end of the season the stats
describe. Nearly all are dated May or June 2025. Valuations older than May
2024 (the end of the season before) are too stale and are not used.

Matching: the two sources share no player id, so players are matched by name
and year of birth, in three passes from strict to loose:

1. "exact":  same name (accents and case ignored) and same birth year, and the
             Transfermarkt player has to fit: valued in the same league, or
             ever valued at the same club, or at its reserve side. Without
             that check Emerson Royal (Milan) is given the price of another
             Emerson born in 1999 who plays in Japan.
2. "club":   same birth year and same club that season, and names that agree
             closely (one name's words contained in the other's, the same
             surname, or a near-identical spelling). This catches "Max Kilman"
             / "Maximilian Kilman" and "Lee Jae-sung" / "Jae-sung Lee".
3. "league": same birth year and league, and almost the same spelling.

A player who cannot be matched confidently is left without a value.

Run:  python -m footstats.market_values              (from the backend folder)
"""
from __future__ import annotations

import argparse
import re
import unicodedata
from difflib import SequenceMatcher
from pathlib import Path

import pandas as pd

from .data import DEFAULT_CSV, load_players

DATA_DIR = DEFAULT_CSV.parent
TM_DIR = DATA_DIR / "transfermarkt"
VALUES_CSV = DATA_DIR / "market_values_2024_25.csv"
VALUE_COLUMN = "Market value (EUR)"
VALUE_FROM, SEASON_END = "2024-05-01", "2025-06-30"
LEAGUE_CODES = {"Premier League": "GB1", "La Liga": "ES1", "Serie A": "IT1",
                "Bundesliga": "L1", "Ligue 1": "FR1"}

_LETTERS = str.maketrans({"ø": "o", "Ø": "O", "đ": "d", "Đ": "D", "ł": "l", "Ł": "L",
                          "ß": "ss", "æ": "ae", "Æ": "AE", "ı": "i"})


def fold(text) -> str:
    """Lower-case, strip accents and punctuation: "N'Dicka" and "Ndicka" become the same."""
    text = unicodedata.normalize("NFKD", str(text).translate(_LETTERS))
    text = "".join(c for c in text if not unicodedata.combining(c)).lower()
    return re.sub(r"\s+", " ", re.sub(r"[^a-z0-9 ]", "", text.replace("-", " "))).strip()


# ---- Transfermarkt side ------------------------------------------------------------------
def season_values(tm_dir: str | Path = TM_DIR) -> pd.DataFrame:
    """One row per Transfermarkt player with a usable valuation.

    Columns: player_id, name, key (folded name), born, value, value_date, club
    and club_id (at that valuation), club_ids and leagues (every club and
    league the player was valued at between VALUE_FROM and SEASON_END), and
    past_club_ids (every club he was ever valued at up to SEASON_END).
    """
    tm_dir = Path(tm_dir)
    players = pd.read_csv(tm_dir / "players.csv.gz",
                          usecols=["player_id", "name", "date_of_birth", "position"])
    valuations = pd.read_csv(tm_dir / "player_valuations.csv.gz", parse_dates=["date"])
    valuations = valuations[valuations["date"] <= SEASON_END].sort_values("date")
    by_player = valuations[valuations["date"] >= VALUE_FROM].groupby("player_id")
    table = pd.DataFrame({
        "value": by_player["market_value_in_eur"].last(),
        "value_date": by_player["date"].last(),
        "club": by_player["current_club_name"].last(),
        "club_id": by_player["current_club_id"].last(),
        "club_ids": by_player["current_club_id"].agg(frozenset),
        "leagues": by_player["player_club_domestic_competition_id"].agg(
            lambda s: frozenset(s.dropna())),
    })
    table["past_club_ids"] = valuations.groupby("player_id")["current_club_id"].agg(frozenset)
    table = table[table["value"] > 0].join(players.set_index("player_id"), how="inner")
    table["key"] = table["name"].map(fold)
    table["born"] = pd.to_datetime(table["date_of_birth"], errors="coerce").dt.year
    return table.reset_index()


# ---- matching -------------------------------------------------------------------------------
def _closeness(a: str, b: str, surname_counts: bool = True) -> float:
    """How well two folded names agree, 0-1. Tiers, strongest first:
    1.0 same words in any order; 0.95 one name's words all appear in the other;
    0.9 same surname (only if surname_counts); otherwise the spelling similarity."""
    ta, tb = a.split(), b.split()
    if not ta or not tb:
        return 0.0
    if sorted(ta) == sorted(tb):
        return 1.0
    if set(ta) <= set(tb) or set(tb) <= set(ta):
        return 0.95
    ratio = SequenceMatcher(None, a, b).ratio()
    same_surname = surname_counts and ta[-1] == tb[-1] and len(ta[-1]) > 3
    return max(ratio, 0.9) if same_surname else ratio


# Words that say nothing about which club a name belongs to.
_CLUB_NOISE = {"fc", "cf", "ac", "as", "sc", "ss", "us", "rc", "cd", "ud", "sv", "vfb", "vfl",
               "tsg", "afc", "real", "club", "de", "la", "calcio", "stade", "olympique", "sporting",
               "ii", "b", "u19", "u21", "u23", "primavera", "espoirs", "atletico", "united", "city"}


def _club_words(name) -> set[str]:
    return {w for w in fold(name).split() if w not in _CLUB_NOISE and len(w) > 2 and not w.isdigit()}


def _best(name: str, candidates: pd.DataFrame, at_least: float,
          surname_counts: bool = True) -> int | None:
    """Index of the one candidate whose name is closest, or None if none is close
    enough or two are equally close."""
    if candidates.empty:
        return None
    scores = candidates["key"].map(
        lambda k: _closeness(name, k, surname_counts)).sort_values(ascending=False)
    if scores.iloc[0] < at_least or (len(scores) > 1 and scores.iloc[1] == scores.iloc[0]):
        return None
    return scores.index[0]


def match_players(df: pd.DataFrame, tm: pd.DataFrame) -> pd.DataFrame:
    """Match FBref players (the loader's table) to Transfermarkt rows.

    Returns one row per matched player, indexed by FBref id, with the value,
    its date, the Transfermarkt id and name, and which pass made the match.
    """
    fb = df.set_index("id")
    fb_key = fb["Player Name"].map(fold)
    fb_league = fb["League"].map(LEAGUE_CODES)
    matched: dict[int, tuple[int, str]] = {}   # FBref id -> (row in tm, pass)
    used: set[int] = set()

    def take(pid: int, row: int, how: str) -> None:
        matched[pid] = (row, how)
        used.add(row)

    # Pass 1a: same name and birth year, valued in the same league. Two
    # Transfermarkt players can share both (there are two Vitinhas born in 2000).
    by_key = {key: list(rows) for key, rows in tm.groupby(["key", "born"]).groups.items()}
    same_name = {pid: by_key.get((fb_key[pid], fb.at[pid, "Born"]), []) for pid in fb.index}
    for pid, rows in same_name.items():
        rows = [r for r in rows if fb_league[pid] in tm.at[r, "leagues"]]
        if len(rows) == 1:
            take(pid, rows[0], "exact")

    # Learn which Transfermarkt club each FBref club is, from those matches.
    votes = pd.DataFrame([(fb.at[pid, "Club"], tm.at[row, "club_id"], tm.at[row, "club"])
                          for pid, (row, _) in matched.items()], columns=["club", "id", "name"])
    club_id_of = votes.groupby("club")["id"].agg(lambda s: s.mode().iloc[0]).to_dict()
    club_name_of = votes.groupby("club")["name"].agg(lambda s: s.mode().iloc[0]).to_dict()

    def clubs_of(pid: int) -> list[str]:
        return [c.strip() for c in fb.at[pid, "Clubs"].split("/")]

    def fits(pid: int, row: int) -> bool:
        """Has this Transfermarkt player been at the FBref player's club, or its reserves?"""
        ids = {club_id_of.get(c) for c in clubs_of(pid)}
        words = set().union(*(_club_words(club_name_of.get(c, "")) for c in clubs_of(pid)))
        return bool(tm.at[row, "past_club_ids"] & ids) or bool(_club_words(tm.at[row, "club"]) & words)

    # Pass 1b: same name and birth year, valued elsewhere (sold in August, or
    # registered with the reserves) but with the right club in his history.
    for pid, rows in same_name.items():
        rows = [r for r in rows if r not in used and fits(pid, r)]
        if pid not in matched and len(rows) == 1:
            take(pid, rows[0], "exact")

    # Pass 2: same birth year and club, names that agree closely.
    # Pass 3: same birth year and league, names that are almost identical
    # (a shared surname is not enough here: it paired two different Palmers).
    for how, threshold in (("club", 0.75), ("league", 0.88)):
        for pid in fb.index:
            if pid in matched:
                continue
            pool = tm[~tm.index.isin(used)]
            if fb.at[pid, "Born"] > 0:
                pool = pool[pool["born"] == fb.at[pid, "Born"]]
            if how == "club":
                clubs = {club_id_of.get(c) for c in clubs_of(pid)}
                pool = pool[pool["club_ids"].map(lambda ids: bool(ids & clubs))]
            else:
                pool = pool[pool["leagues"].map(lambda codes: fb_league[pid] in codes)]
            row = _best(fb_key[pid], pool, threshold, surname_counts=how == "club")
            if row is not None:
                take(pid, row, how)

    rows = [{"id": pid, "Player": fb.at[pid, "Player Name"], "Born": fb.at[pid, "Born"],
             "Club": fb.at[pid, "Club"], "League": fb.at[pid, "League"],
             VALUE_COLUMN: int(tm.at[row, "value"]),
             "Valuation date": tm.at[row, "value_date"].date().isoformat(),
             "Transfermarkt id": int(tm.at[row, "player_id"]),
             "Transfermarkt name": tm.at[row, "name"],
             "Transfermarkt club": tm.at[row, "club"], "Match": how}
            for pid, (row, how) in sorted(matched.items())]
    return pd.DataFrame(rows).set_index("id")


# ---- building and loading the values file ---------------------------------------------------------
def build(csv_path: str | Path = DEFAULT_CSV, tm_dir: str | Path = TM_DIR,
          out: str | Path = VALUES_CSV) -> pd.DataFrame:
    """Match every player and write the values file. Returns the matches."""
    matches = match_players(load_players(csv_path), season_values(tm_dir))
    matches.to_csv(out, index=False, encoding="utf-8-sig")
    return matches


def load_market_values(df: pd.DataFrame, path: str | Path = VALUES_CSV) -> pd.Series | None:
    """Market value in euros per player id (NaN where unmatched), or None if the
    values file has not been built. Players are identified by name and birth year,
    the same key the loader uses to merge a player's clubs."""
    path = Path(path)
    if not path.exists():
        return None
    values = pd.read_csv(path, encoding="utf-8-sig").set_index(["Player", "Born"])[VALUE_COLUMN]
    keys = pd.MultiIndex.from_frame(df[["Player Name", "Born"]])
    return pd.Series(values.reindex(keys).to_numpy(), index=df["id"].to_numpy(), name=VALUE_COLUMN)


def main() -> None:
    parser = argparse.ArgumentParser(description="Match Transfermarkt market values to FBref players.")
    parser.add_argument("--tm-dir", default=str(TM_DIR), help="folder with the two .csv.gz files")
    parser.add_argument("--out", default=str(VALUES_CSV))
    args = parser.parse_args()

    df = load_players()
    matches = build(tm_dir=args.tm_dir, out=args.out)
    regular = df["Minutes"] >= 500
    print(f"Matched {len(matches)} of {len(df)} players "
          f"({df.loc[regular, 'id'].isin(matches.index).sum()} of {regular.sum()} with 500+ minutes).")
    print(matches["Match"].value_counts().to_string())
    print(f"Written to {args.out}")


if __name__ == "__main__":
    main()
