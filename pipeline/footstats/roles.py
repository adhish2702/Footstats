"""Place every player in a tactical role within their position.

A role is decided from how someone plays, never from how productive they are:
no goals, assists or expected-goals numbers are used. Each role lists a few
signals it expects more (+1) or less (-1) of than is typical. A player's score
for a role is the average of those signals as z-scores against players with
900+ minutes in the same group (capped at +/-3 so one extreme number can't
decide it), and the player gets the role with the highest score.

The data has no footedness, pitch coordinates or pressing counts, so the
signals are stand-ins: an inside forward is a winger who shoots and gets into
the box rather than crossing, a pressing forward is a striker who tackles high
up the pitch, and so on.
"""
from __future__ import annotations

import pandas as pd

# ---- style features -----------------------------------------------------------
# name -> (kind, column[, denominator column])
#   "p90":   column per 90 minutes
#   "share": column divided by another count (usually touches)
#   "rate":  column used as it is
FEATURES: dict[str, tuple] = {
    # passing
    "Passes": ("p90", "Passes attempted"),
    "Passes per touch": ("share", "Passes attempted", "Touches"),
    "Pass accuracy": ("rate", "Pass accuracy"),
    "Progressive passes": ("p90", "Progressive passes"),
    "Passes into final third": ("p90", "Passes into final third"),
    "Switches of play": ("p90", "Switches"),
    "Key passes": ("p90", "Key passes"),
    "Through balls": ("p90", "Through balls"),
    "Passes into box": ("p90", "Passes into box"),
    "Passes received": ("p90", "Passes received"),
    "Progressive passes received": ("p90", "Progressive receptions"),
    "Progressive passes received per touch": ("share", "Progressive receptions", "Touches"),
    "Crosses per touch": ("share", "Crosses", "Touches"),
    "Throw-ins": ("p90", "Throw-ins"),
    # where the touches are
    "Touches": ("p90", "Touches"),
    "Touches in own box (share)": ("share", "Touches in own box", "Touches"),
    "Touches in own third (share)": ("share", "Touches in defensive third", "Touches"),
    "Touches in middle third (share)": ("share", "Touches in middle third", "Touches"),
    "Touches in final third (share)": ("share", "Touches in attacking third", "Touches"),
    "Touches in opposition box (share)": ("share", "Touches in box", "Touches"),
    # on the ball
    "Shots per touch": ("share", "Shots", "Touches"),
    "Take-ons per touch": ("share", "Take-ons attempted", "Touches"),
    "Progressive carries": ("p90", "Progressive carries"),
    "Progressive carries per touch": ("share", "Progressive carries", "Touches"),
    "Carries into final third": ("p90", "Carries into final third"),
    "Carries into box": ("p90", "Carries into box"),
    "Offsides": ("p90", "Offsides"),
    "Fouls won": ("p90", "Fouls drawn"),
    # defending
    "Tackles": ("p90", "Tackles"),
    "Tackles outside own third": ("p90", "Tackles outside own third"),
    "Interceptions": ("p90", "Interceptions"),
    "Ball recoveries": ("p90", "Ball recoveries"),
    "Fouls": ("p90", "Fouls"),
    "Clearances": ("p90", "Clearances"),
    "Blocks": ("p90", "Blocks"),
    "Dribblers challenged": ("p90", "Dribblers challenged"),
    "Aerial duels": ("p90", "Aerial duels"),
    "Aerial win rate": ("rate", "Aerial win %"),
    # goalkeeping
    "Actions outside the box": ("p90", "Sweeper actions"),
    "Distance of actions from goal": ("rate", "Sweeper distance"),
    "Goalkeeper passes": ("p90", "Goalkeeper passes"),
    "Long passes (share)": ("rate", "Launch %"),
    "Average pass length": ("rate", "Pass length"),
}


def role_features(df: pd.DataFrame) -> pd.DataFrame:
    """Style features for every player in df (see FEATURES)."""
    minutes = df["Minutes"].clip(lower=1)
    out = {}
    for name, (kind, column, *rest) in FEATURES.items():
        if kind == "p90":
            out[name] = df[column] / minutes * 90
        elif kind == "share":
            out[name] = df[column] / df[rest[0]].clip(lower=1)
        else:
            out[name] = df[column].astype(float)
    return pd.DataFrame(out, index=df.index)


# ---- full-backs vs centre-backs -------------------------------------------------
# FBref lists both as "DF". Full-backs take throw-ins, cross and get forward;
# centre-backs clear the ball, contest headers and touch it in their own box.
# The scores form two humps with a dip between about -0.2 and 0.4. Players in
# the dip are hybrids (the outside centre-backs of a back three, full-backs who
# also play centrally); they are grouped with the centre-backs, where the wide
# centre-back role picks them up.
FULL_BACK_THRESHOLD = 0.4
FULL_BACK_SIGNALS = {
    "Throw-ins": 1, "Crosses per touch": 1, "Touches in final third (share)": 1,
    "Clearances": -1, "Aerial duels": -1, "Touches in own box (share)": -1,
}

# ---- roles ----------------------------------------------------------------------
# group: players are compared within it. It is the position, except that
# defenders are compared within full-backs ("FB") or centre-backs ("CB").
ROLE_INFO: dict[str, dict] = {
    # goalkeepers
    "Sweeper-keeper": {
        "position": "GKP", "group": "GKP", "plural": "sweeper-keepers",
        "description": "Starts high and comes off the line to clear danger behind the defence.",
        "signals": {"Actions outside the box": 1, "Distance of actions from goal": 1},
    },
    "Ball-playing goalkeeper": {
        "position": "GKP", "group": "GKP", "plural": "ball-playing goalkeepers",
        "description": "An extra outfield player in build-up: many short, accurate passes rather than long kicks.",
        "signals": {"Goalkeeper passes": 1, "Pass accuracy": 1, "Long passes (share)": -1,
                    "Average pass length": -1},
    },
    # centre-backs
    "Ball-playing centre-back": {
        "position": "DEF", "group": "CB", "plural": "ball-playing centre-backs",
        "description": "Builds play from the back with a high volume of accurate, line-breaking passes.",
        "signals": {"Passes": 1, "Pass accuracy": 1, "Progressive passes": 1,
                    "Passes into final third": 1, "Switches of play": 1, "Clearances": -1},
    },
    "Stopper": {
        "position": "DEF", "group": "CB", "plural": "stoppers",
        "description": "A defend-first centre-back: clearances, blocks and headers in and around his own box.",
        "signals": {"Clearances": 1, "Blocks": 1, "Aerial duels": 1,
                    "Touches in own box (share)": 1, "Passes": -1, "Progressive carries": -1},
    },
    "Wide centre-back": {
        "position": "DEF", "group": "CB", "plural": "wide centre-backs",
        "description": "Defends the wide channel one-on-one and carries or overlaps into the final third.",
        "signals": {"Throw-ins": 1, "Crosses per touch": 1, "Touches in final third (share)": 1,
                    "Progressive carries": 1, "Dribblers challenged": 1, "Aerial duels": -1},
    },
    # full-backs
    "Inverted full-back": {
        "position": "DEF", "group": "FB", "plural": "inverted full-backs",
        "description": "Tucks into midfield in possession: more passing through the middle, less crossing.",
        "signals": {"Touches in middle third (share)": 1, "Pass accuracy": 1,
                    "Passes per touch": 1, "Crosses per touch": -1},
    },
    "Wing-back": {
        "position": "DEF", "group": "FB", "plural": "wing-backs",
        "description": "Provides the width: overlapping runs, crosses and cutbacks from the final third.",
        "signals": {"Crosses per touch": 1, "Touches in final third (share)": 1,
                    "Touches in opposition box (share)": 1,
                    "Progressive passes received per touch": 1, "Take-ons per touch": 1},
    },
    # midfielders
    "Deep-lying playmaker": {
        "position": "MID", "group": "MID", "plural": "deep-lying playmakers",
        "description": "Sits in front of the defence, sets the tempo and switches play.",
        "signals": {"Passes": 1, "Pass accuracy": 1, "Switches of play": 1,
                    "Touches in own third (share)": 1, "Passes into final third": 1,
                    "Touches in opposition box (share)": -1},
    },
    "Ball-winning midfielder": {
        "position": "MID", "group": "MID", "plural": "ball-winning midfielders",
        "description": "Breaks up play: tackles, interceptions, recoveries and duels, then a simple pass.",
        "signals": {"Tackles": 1, "Interceptions": 1, "Ball recoveries": 1, "Fouls": 1,
                    "Aerial duels": 1, "Passes": -1},
    },
    "Box-to-box midfielder": {
        "position": "MID", "group": "MID", "plural": "box-to-box midfielders",
        "description": "Links both penalty areas: carries the ball forward, runs beyond it and arrives in the box.",
        "signals": {"Progressive carries": 1, "Progressive passes received": 1,
                    "Shots per touch": 1, "Touches in opposition box (share)": 1,
                    "Tackles": 1, "Key passes": -1},
    },
    "Advanced playmaker": {
        "position": "MID", "group": "MID", "plural": "advanced playmakers",
        "description": "Works between the lines in the final third, creating chances with through balls and passes into the box.",
        "signals": {"Key passes": 1, "Through balls": 1, "Passes into box": 1,
                    "Touches in final third (share)": 1, "Fouls won": 1, "Tackles": -1},
    },
    # wingers
    "Inside forward": {
        "position": "WNG", "group": "WNG", "plural": "inside forwards",
        "description": "Cuts in from the flank to shoot and attack the box like a second striker.",
        "signals": {"Shots per touch": 1, "Touches in opposition box (share)": 1,
                    "Offsides": 1, "Crosses per touch": -1, "Passes": -1},
    },
    "Touchline winger": {
        "position": "WNG", "group": "WNG", "plural": "touchline wingers",
        "description": "Stays wide, takes on the full-back one-on-one and crosses or cuts the ball back.",
        "signals": {"Crosses per touch": 1, "Take-ons per touch": 1,
                    "Progressive carries per touch": 1, "Throw-ins": 1, "Shots per touch": -1},
    },
    "Wide playmaker": {
        "position": "WNG", "group": "WNG", "plural": "wide playmakers",
        "description": "Starts wide but drifts inside to pass: close control and vision rather than pace.",
        "signals": {"Passes": 1, "Key passes": 1, "Through balls": 1, "Switches of play": 1,
                    "Touches in middle third (share)": 1, "Take-ons per touch": -1},
    },
    # strikers
    "Pressing forward": {
        "position": "STR", "group": "STR", "plural": "pressing forwards",
        "description": "The first defender: closes down, tackles and recovers the ball high up the pitch.",
        "signals": {"Tackles outside own third": 1, "Interceptions": 1, "Ball recoveries": 1,
                    "Fouls": 1, "Dribblers challenged": 1},
    },
    "False nine": {
        "position": "STR", "group": "STR", "plural": "false nines",
        "description": "Drops into midfield to link play and create, leaving the box for runners.",
        "signals": {"Touches in middle third (share)": 1, "Passes": 1, "Key passes": 1,
                    "Progressive passes": 1, "Through balls": 1,
                    "Touches in opposition box (share)": -1},
    },
    "Poacher": {
        "position": "STR", "group": "STR", "plural": "poachers",
        "description": "Lives on the last defender's shoulder: few touches, most of them in the box, and a shot at the end.",
        "signals": {"Touches in opposition box (share)": 1, "Shots per touch": 1, "Offsides": 1,
                    "Touches": -1, "Aerial duels": -1},
    },
    "Target forward": {
        "position": "STR", "group": "STR", "plural": "target forwards",
        "description": "A physical outlet: wins headers, holds the ball up, draws fouls and brings others into play.",
        "signals": {"Aerial duels": 1, "Aerial win rate": 1, "Fouls won": 1,
                    "Passes received": 1, "Take-ons per touch": -1},
    },
}

ROLES: dict[str, list[str]] = {}
for _role, _info in ROLE_INFO.items():
    ROLES.setdefault(_info["position"], []).append(_role)


def _signal_score(features: pd.DataFrame, qualified: pd.Series, signals: dict[str, int]) -> pd.Series:
    """Average capped z-score of the signed signals, against the qualified rows."""
    values = features[list(signals)]
    pool = values[qualified.to_numpy()]
    if len(pool) < 2:
        pool = values
    z = (values - pool.mean()) / pool.std(ddof=0).replace(0, 1)
    signs = pd.Series(signals)
    return (z.clip(-3, 3) * signs).mean(axis=1)


def full_back_score(defenders: pd.DataFrame) -> pd.Series:
    """High for full-backs, low for centre-backs (full-back above FULL_BACK_THRESHOLD)."""
    return _signal_score(role_features(defenders), defenders["Qualified"], FULL_BACK_SIGNALS)


def role_groups(df: pd.DataFrame) -> pd.Series:
    """The comparison group for each player: their position, or FB / CB for defenders."""
    group = df["Position"].astype(object).copy()
    is_def = df["Position"] == "DEF"
    if is_def.any():
        group[is_def] = full_back_score(df[is_def]).gt(FULL_BACK_THRESHOLD).map({True: "FB", False: "CB"})
    return group


def role_scores(df: pd.DataFrame) -> pd.DataFrame:
    """One column per role; NaN for roles outside the player's group."""
    features = role_features(df)
    group = role_groups(df)
    scores = pd.DataFrame(float("nan"), index=df.index, columns=list(ROLE_INFO))
    for role, info in ROLE_INFO.items():
        members = group == info["group"]
        if members.any():
            scores.loc[members, role] = _signal_score(
                features[members], df.loc[members, "Qualified"], info["signals"])
    return scores


def assign_roles(df: pd.DataFrame) -> pd.Series:
    """Best-fitting role for every player. Needs Position, Qualified and the count columns."""
    return role_scores(df).idxmax(axis=1).rename("Role")
