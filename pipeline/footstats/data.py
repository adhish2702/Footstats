"""Load and clean 2024/25 player stats for Europe's top five leagues (FBref)."""
from __future__ import annotations

from pathlib import Path

import pandas as pd

from .roles import assign_roles

DEFAULT_CSV = Path(__file__).resolve().parents[2] / "data" / "fbref_top5_2024_25.csv"

POSITIONS = ["GKP", "DEF", "MID", "WNG", "STR"]
# FBref only says "FW"; forwards are split into strikers and wingers by forward_roles().
FORWARD_POSITIONS = ["WNG", "STR"]
POSITION_MAP = {"GK": "GKP", "DF": "DEF", "MF": "MID", "FW": "FWD"}
LEAGUES = ["Premier League", "La Liga", "Serie A", "Bundesliga", "Ligue 1"]

# Minimum minutes for a player's per-90 numbers to be considered reliable.
MIN_MINUTES = 900

# FBref column -> readable name, for counting stats (summed across clubs, rated per 90).
COUNTS = {
    "MP": "Appearances", "Starts": "Starts", "Min": "Minutes",
    "Gls": "Goals", "Ast": "Assists", "PK": "Penalty goals",
    "xG": "xG", "npxG": "npxG", "xAG": "xAG",
    "Sh": "Shots", "SoT": "Shots on target",
    "Cmp": "Passes completed", "Att": "Passes attempted",
    "KP": "Key passes", "1/3": "Passes into final third", "PPA": "Passes into box",
    "PrgP": "Progressive passes", "TB": "Through balls", "Crs": "Crosses",
    "SCA": "Shot-creating actions",
    "Tkl": "Tackles", "TklW": "Tackles won", "Int": "Interceptions",
    "Clr": "Clearances", "Blocks_stats_defense": "Blocks", "Err": "Errors leading to shots",
    "Att_stats_defense": "Dribblers challenged", "Lost": "Challenges lost",
    "Touches": "Touches", "Att Pen": "Touches in box", "Succ": "Successful take-ons",
    "Carries": "Carries", "PrgC": "Progressive carries", "CPA": "Carries into box",
    "PrgR": "Progressive receptions", "Mis": "Miscontrols", "Dis": "Dispossessed",
    "Recov": "Ball recoveries", "Won": "Aerials won", "Lost_stats_misc": "Aerials lost",
    # goalkeeping
    "GA": "Goals conceded", "SoTA": "Shots on target faced", "Saves": "Saves",
    "CS": "Clean sheets", "PSxG+/-": "Goals prevented", "Opp": "Crosses faced",
    "Stp": "Crosses stopped", "#OPA": "Sweeper actions", "Att (GK)": "Goalkeeper passes",
    # where and how a player is involved; used to work out roles (roles.py)
    "Sw": "Switches", "TI": "Throw-ins", "PrgDist": "Progressive pass distance",
    "CrsPA": "Crosses into box",
    "Def 3rd": "Tackles in defensive third", "Mid 3rd": "Tackles in middle third",
    "Att 3rd": "Tackles in attacking third",
    "Def Pen": "Touches in own box", "Def 3rd_stats_possession": "Touches in defensive third",
    "Mid 3rd_stats_possession": "Touches in middle third",
    "Att 3rd_stats_possession": "Touches in attacking third",
    "Att_stats_possession": "Take-ons attempted", "1/3_stats_possession": "Carries into final third",
    "Rec": "Passes received", "Fls": "Fouls", "Fld_stats_misc": "Fouls drawn",
    "Off_stats_misc": "Offsides",
}

# FBref gives these goalkeeper numbers as averages. To combine a keeper's clubs
# they are turned into totals (average x volume), summed, and divided back out.
# total -> (source average, source volume, scale)
WEIGHTED = {
    "Goalkeeper pass distance": ("AvgLen", "Att (GK)", 1),
    "Goalkeeper passes launched": ("Launch%", "Att (GK)", 0.01),
    "Sweeper action distance": ("AvgDist", "#OPA", 1),
}

# Rate stats, recomputed from their counting components after merging clubs.
RATES = ["Pass accuracy", "Challenge success", "Aerial win %", "Save %", "Crosses stopped %",
         "Pass length", "Launch %", "Sweeper distance"]

# Stats used as-is (already a rate) rather than converted to per 90.
NOT_PER90 = set(RATES)


def _safe_div(a, b):
    return (a / b.where(b > 0)).fillna(0)


def striker_score(forwards: pd.DataFrame) -> pd.Series:
    """How striker-like (positive) or winger-like (negative) each forward plays.

    Strikers take a large share of their touches in the box, shoot often per
    touch and contest aerials. Wingers see more of the ball, cross, dribble and
    carry it forward. Each signal is a z-score against forwards with 900+
    minutes (capped at +/-3 so one extreme number can't decide it), and the
    score is their average. Nothing here measures goals or assists, so the
    split describes where and how someone plays, not how good they are.
    """
    minutes = forwards["Minutes"].clip(lower=1)
    touches = forwards["Touches"].clip(lower=1)
    signals = pd.DataFrame({
        "box share": forwards["Touches in box"] / touches,
        "shots per touch": forwards["Shots"] / touches,
        "aerial duels": (forwards["Aerials won"] + forwards["Aerials lost"]) / minutes * 90,
        "crosses": -forwards["Crosses"] / touches,
        "take-ons": -forwards["Successful take-ons"] / touches,
        "carries": -forwards["Progressive carries"] / touches,
        "touches": -forwards["Touches"] / minutes * 90,
    })
    pool = signals[forwards["Minutes"] >= MIN_MINUTES]
    if len(pool) < 2:
        pool = signals
    z = (signals - pool.mean()) / pool.std(ddof=0).replace(0, 1)
    return z.clip(-3, 3).mean(axis=1)


def forward_roles(df: pd.DataFrame) -> pd.Series:
    """Position column with FBref's broad "FW" split into STR and WNG."""
    position = df["Position"].copy()
    is_fwd = position == "FWD"
    if is_fwd.any():
        score = striker_score(df[is_fwd])
        position[is_fwd] = score.gt(0).map({True: "STR", False: "WNG"})
    return position


def load_players(csv_path: str | Path = DEFAULT_CSV) -> pd.DataFrame:
    """Read the FBref export into one row per player with readable column names.

    Players who changed club mid-season appear once per club in the source.
    Their stats are combined; club and league are taken from the club where
    they played the most minutes.
    """
    raw = pd.read_csv(csv_path, encoding="utf-8-sig")

    df = pd.DataFrame({
        "Player Name": raw["Player"].str.strip(),
        "Born": raw["Born"].fillna(-1).astype(int),
        "Age": raw["Age"],
        "Nationality": raw["Nation"].fillna("").str.split().str[-1].fillna(""),
        "Position": raw["Pos"].fillna("MF").str.split(",").str[0].map(POSITION_MAP),
        "Club": raw["Squad"],
        "League": raw["Comp"].str.split(" ", n=1).str[1],
    })
    for src, name in COUNTS.items():
        df[name] = pd.to_numeric(raw[src], errors="coerce").fillna(0)
    for name, (average, volume, scale) in WEIGHTED.items():
        df[name] = (pd.to_numeric(raw[average], errors="coerce").fillna(0)
                    * pd.to_numeric(raw[volume], errors="coerce").fillna(0) * scale)
    summed = [*COUNTS.values(), *WEIGHTED]

    # Merge multi-club seasons.
    df = df.sort_values("Minutes", ascending=False)
    keys = ["Player Name", "Born"]
    first = df.groupby(keys, sort=False).first()
    sums = df.groupby(keys, sort=False)[summed].sum()
    clubs = df.groupby(keys, sort=False)["Club"].agg(lambda s: " / ".join(s))
    merged = first.drop(columns=summed).join(sums)
    merged["Clubs"] = clubs
    df = merged.reset_index()

    df["Pass accuracy"] = _safe_div(df["Passes completed"], df["Passes attempted"])
    df["Challenge success"] = 1 - _safe_div(df["Challenges lost"], df["Dribblers challenged"])
    df.loc[df["Dribblers challenged"] == 0, "Challenge success"] = 0
    df["Aerial win %"] = _safe_div(df["Aerials won"], df["Aerials won"] + df["Aerials lost"])
    df["Save %"] = _safe_div(df["Saves"], df["Shots on target faced"])
    df["Crosses stopped %"] = _safe_div(df["Crosses stopped"], df["Crosses faced"])
    df["Pass length"] = _safe_div(df["Goalkeeper pass distance"], df["Goalkeeper passes"])
    df["Launch %"] = _safe_div(df["Goalkeeper passes launched"], df["Goalkeeper passes"])
    df["Sweeper distance"] = _safe_div(df["Sweeper action distance"], df["Sweeper actions"])
    df["Tackles outside own third"] = df["Tackles in middle third"] + df["Tackles in attacking third"]
    df["Aerial duels"] = df["Aerials won"] + df["Aerials lost"]

    df["Age"] = df["Age"].fillna(2024 - df["Born"].where(df["Born"] > 0)).astype("Int64")
    df = df[df["Position"].notna()].sort_values(["League", "Club", "Player Name"])
    df = df.reset_index(drop=True)
    df["Position"] = forward_roles(df)
    df["Qualified"] = df["Minutes"] >= MIN_MINUTES
    df["Role"] = assign_roles(df)
    df.insert(0, "id", range(len(df)))
    df["Goal Contributions"] = df["Goals"] + df["Assists"]
    # Penalties say who the designated taker is, not how well someone plays, so
    # ratings and the expected-output model work from non-penalty goals.
    df["Non-penalty goals"] = df["Goals"] - df["Penalty goals"]
    df["Non-penalty goal contributions"] = df["Non-penalty goals"] + df["Assists"]
    return df.copy()  # defragment after adding many columns


def per90(df: pd.DataFrame, cols: list[str]) -> pd.DataFrame:
    """Return the given count columns scaled to per-90-minute rates."""
    minutes = df["Minutes"].clip(lower=1)
    return df[cols].div(minutes, axis=0) * 90
