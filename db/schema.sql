-- FootStats database schema (PostgreSQL 14+).
--
-- The pipeline (pipeline/load_db.py) runs this file and then reloads every
-- table inside one transaction, so a failed run leaves the old data in place.
-- The API only reads.
--
-- One season (2024/25), Europe's top five leagues, from FBref. Each player has
-- one row: players who changed club mid-season are merged, and shown under the
-- club where they played the most minutes (all clubs are listed in clubs_played).

DROP TABLE IF EXISTS predictions, model_versions, player_stats, players, clubs CASCADE;

CREATE TABLE clubs (
    id      integer PRIMARY KEY,
    name    text NOT NULL,                       -- FBref's short name, e.g. "Manchester Utd"
    league  text NOT NULL CHECK (league IN
              ('Premier League', 'La Liga', 'Serie A', 'Bundesliga', 'Ligue 1')),
    UNIQUE (name, league)
);

CREATE TABLE players (
    id            integer PRIMARY KEY,            -- the pipeline's player id (stable for a given CSV)
    name          text NOT NULL,
    search_name   text NOT NULL,                  -- lower case, accents removed: "Ødegaard" -> "odegaard"
    club_id       integer NOT NULL REFERENCES clubs (id),
    clubs_played  text NOT NULL,                  -- e.g. "St. Pauli / Freiburg"
    nationality   text,                           -- FBref three-letter code, e.g. "ENG"
    age           smallint,                       -- age at the start of the season
    birth_year    smallint,
    position      text NOT NULL CHECK (position IN ('GKP', 'DEF', 'MID', 'WNG', 'STR')),
    role          text NOT NULL,                  -- one of 18 tactical roles, e.g. "Poacher"
    appearances   smallint NOT NULL,
    starts        smallint NOT NULL,
    minutes       integer NOT NULL,
    qualified     boolean NOT NULL,               -- 900+ minutes: per-90 numbers are reliable
    rating        numeric(4, 1) NOT NULL          -- role rating, 0-99, 50 = average in the role
);
CREATE INDEX players_club_idx ON players (club_id);
CREATE INDEX players_position_idx ON players (position);
CREATE INDEX players_search_idx ON players (search_name);

-- Season totals and per-90 rates. Per-90 columns end in _p90; rates in _pct are 0-100.
-- The 19 *_p90 columns from shots_p90 to aerials_won_p90 are the playing-style
-- inputs of the expected goal-contributions model.
CREATE TABLE player_stats (
    player_id                    integer PRIMARY KEY REFERENCES players (id) ON DELETE CASCADE,
    -- output (totals)
    goals                        smallint NOT NULL,
    assists                      smallint NOT NULL,
    penalty_goals                smallint NOT NULL,
    non_penalty_goals            smallint NOT NULL,
    xg                           numeric(5, 1) NOT NULL,
    npxg                         numeric(5, 1) NOT NULL,
    xag                          numeric(5, 1) NOT NULL,
    -- output (per 90)
    npga_p90                     numeric(6, 3) NOT NULL,   -- non-penalty goals + assists
    npxg_p90                     numeric(6, 3) NOT NULL,
    xag_p90                      numeric(6, 3) NOT NULL,
    -- playing style (per 90): the model's inputs
    shots_p90                    numeric(6, 3) NOT NULL,
    shots_on_target_p90          numeric(6, 3) NOT NULL,
    touches_p90                  numeric(7, 2) NOT NULL,
    touches_in_box_p90           numeric(6, 3) NOT NULL,
    key_passes_p90               numeric(6, 3) NOT NULL,
    passes_into_box_p90          numeric(6, 3) NOT NULL,
    passes_into_final_third_p90  numeric(6, 3) NOT NULL,
    progressive_passes_p90       numeric(6, 3) NOT NULL,
    progressive_carries_p90      numeric(6, 3) NOT NULL,
    progressive_receptions_p90   numeric(6, 3) NOT NULL,
    carries_into_box_p90         numeric(6, 3) NOT NULL,
    successful_take_ons_p90      numeric(6, 3) NOT NULL,
    shot_creating_actions_p90    numeric(6, 3) NOT NULL,
    crosses_p90                  numeric(6, 3) NOT NULL,
    through_balls_p90            numeric(6, 3) NOT NULL,
    miscontrols_p90              numeric(6, 3) NOT NULL,
    dispossessed_p90             numeric(6, 3) NOT NULL,
    ball_recoveries_p90          numeric(6, 3) NOT NULL,
    aerials_won_p90              numeric(6, 3) NOT NULL,
    -- defending (per 90) and passing
    tackles_won_p90              numeric(6, 3) NOT NULL,
    interceptions_p90            numeric(6, 3) NOT NULL,
    clearances_p90               numeric(6, 3) NOT NULL,
    pass_accuracy_pct            numeric(4, 1) NOT NULL,
    -- goalkeeping (NULL for outfield players)
    saves_pct                    numeric(4, 1),
    clean_sheets                 smallint,
    goals_conceded               smallint,
    goals_prevented              numeric(5, 1)            -- post-shot xG faced minus goals conceded
);

-- One row per trained model, with the metrics it scored when it was trained.
CREATE TABLE model_versions (
    version        text PRIMARY KEY,                       -- e.g. "npga90-ridge-1a2b3c4d"
    model_name     text NOT NULL,                          -- e.g. "Ridge regression"
    target         text NOT NULL,
    season         text NOT NULL,
    trained_at     timestamptz NOT NULL DEFAULT now(),
    n_players      integer NOT NULL,                       -- qualified outfield players modelled
    n_train        integer NOT NULL,
    n_test         integer NOT NULL,                       -- held-out players
    cv_mae         numeric(6, 4) NOT NULL,                 -- 5-fold CV on the training split
    test_mae       numeric(6, 4) NOT NULL,                 -- on the held-out players
    baseline_mae   numeric(6, 4) NOT NULL,                 -- always predicting the training mean
    test_r2        numeric(5, 3) NOT NULL,
    xg_mae         numeric(6, 4) NOT NULL,                 -- FBref npxG + xAG on the same players
    xg_r2          numeric(5, 3) NOT NULL,
    features       jsonb NOT NULL,                         -- [{"feature", "importance"}, ...]
    data_sha256    text NOT NULL                           -- hash of the source CSV
);

-- Expected vs actual non-penalty goals + assists per 90. Only outfield players
-- with 900+ minutes have a prediction. Each player's prediction comes from a
-- model trained without that player (5-fold out-of-fold), so the gap is fair.
CREATE TABLE predictions (
    player_id      integer NOT NULL REFERENCES players (id) ON DELETE CASCADE,
    model_version  text NOT NULL REFERENCES model_versions (version) ON DELETE CASCADE,
    predicted_p90  numeric(6, 3) NOT NULL,
    actual_p90     numeric(6, 3) NOT NULL,
    gap_p90        numeric(6, 3) GENERATED ALWAYS AS (actual_p90 - predicted_p90) STORED,
    in_test_set    boolean NOT NULL,                       -- one of the held-out players
    PRIMARY KEY (player_id, model_version)
);
CREATE INDEX predictions_gap_idx ON predictions (model_version, gap_p90);
