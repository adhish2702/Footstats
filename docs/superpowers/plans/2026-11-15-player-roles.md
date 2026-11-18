# Player Roles Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Give every player one of 18 tactical roles within their position and rate them on that role's weights against players in the same role.

**Architecture:** A new `roles.py` computes style features and picks the best-fitting role per player (average of capped z-scores of signed signals, the same method as the striker/winger split). `ratings.py` is keyed by role instead of position. The K-Means module becomes a check on how well unsupervised clusters agree with the roles. The API gains a `role` field and filter and `/api/roles` replaces `/api/clusters`.

**Tech Stack:** Python 3.13, pandas, scikit-learn, FastAPI, pytest; React 18 + Vite.

**Spec:** `docs/superpowers/specs/2026-11-15-player-roles-design.md`

## Global Constraints

- Role signals must not use goals, assists, xG, npxG or xAG.
- No hand-labelled players; assignment is a rule applied to everyone.
- Position codes stay `GKP, DEF, MID, WNG, STR`.
- Rating pool is the same role's qualified players; fall back to the position pool below 15.
- Every role's weights sum to 1 in absolute value.
- Not a git repo: no commit steps.

## Review Focus

- A player with very few minutes (ratios near 0/0) still gets a role and a finite rating.
- A position subset with no qualified players (tests on filtered frames) does not crash assignment.
- `role` filter with a value from another position returns an empty list, not an error; an unknown role returns 422.
- A goalkeeper who played for two clubs gets averages (pass length, sweeper distance) weighted by volume, not summed.
- New frontend against a backend that has not been restarted (no `role` field) must not crash the player panel.

---

### Task 1: Extra stats in `data.py`

**Files:** Modify `backend/footstats/data.py`; Test `backend/tests/test_analysis.py`

**Produces:** new count columns `Switches, Throw-ins, Progressive pass distance, Crosses into box, Tackles in defensive third, Tackles outside own third, Touches in own box, Touches in defensive third, Touches in middle third, Touches in attacking third, Take-ons attempted, Carries into final third, Passes received, Fouls, Fouls drawn, Offsides, Goalkeeper passes`; rates `Pass length` (goalkeepers, yards), `Launch %`, `Sweeper distance` recomputed from volume-weighted sums after merging clubs.

- [ ] Test: `test_touch_thirds_are_consistent` — own-box touches <= defensive-third touches; the three thirds sum to within 2% of `Touches` for players with 500+ touches.
- [ ] Test: `test_goalkeeper_averages_in_range` — qualified keepers have `Pass length` between 15 and 60 and `Launch %` between 0 and 1.
- [ ] Implement, run, pass.

### Task 2: `roles.py` — features and assignment

**Files:** Create `backend/footstats/roles.py`; Modify `backend/footstats/data.py` (call at end of `load_players`); Test `backend/tests/test_roles.py`

**Produces:**
- `ROLES: dict[str, list[str]]` position -> role names (18 in total, as in the spec)
- `ROLE_INFO: dict[str, dict]` role -> `{"position", "plural", "description", "signals": {feature: +1|-1}}`
- `role_features(df) -> pd.DataFrame` named style features
- `role_scores(df) -> pd.DataFrame` one column per role, NaN outside the role's position
- `full_back_score(defenders) -> pd.Series` (> 0 means full-back)
- `assign_roles(df) -> pd.Series` named `Role`
- `load_players()` adds a `Role` column.

- [ ] Tests: every player has a role belonging to their position; each role has at least 20 qualified players; named archetypes land in the expected role (list fixed in the test file after confirming each against the data, at least three per role where clear examples exist); adding 20 goals and assists to everyone changes no role.
- [ ] Implement with the signals from the exploration script as a starting point; tune until tests pass.

### Task 3: Role-keyed ratings

**Files:** Modify `backend/footstats/ratings.py`, `backend/footstats/similar.py`; Test `backend/tests/test_analysis.py`

**Produces:**
- `RATING_WEIGHTS: dict[str, dict[str, float]]` keyed by role name
- `PROFILE_METRICS: dict[str, list[str]]` position -> union of its roles' metrics (used by similarity)
- `metric_values(df, metrics: list[str])`
- `compute_ratings(df)` unchanged signature; pool = same role, qualified, else position pool if < 15.

- [ ] Tests: weights exist for every role and sum to 1; ratings in 0–99; mean qualified rating per role is within 3 of 50; standout checks (Dembélé, Salah, Lewandowski, Haaland, Kane, Pedri in the top 10 of their role); similar players still same position.
- [ ] Implement, run, pass.

### Task 4: Service, API and the K-Means check

**Files:** Modify `backend/footstats/clusters.py`, `service.py`, `backend/app.py`; Test `backend/tests/test_api.py`, `test_analysis.py`

**Produces:**
- `clusters.role_agreement(df) -> dict[position, {"k", "agreement", "chance", "silhouette"}]` — K-Means with k = number of roles on the position's role-score columns, clusters matched one-to-one to roles; `agreement` is the share of qualified players whose cluster maps to their role.
- Player summary: `role` replaces `style`. Player detail: `role_rank {rank, of}` replaces `position_rank`, plus `role_description`; each percentile row carries `per90: bool`.
- `list_players(..., role=None)`; `GET /api/players?role=`; `GET /api/roles` replaces `/api/clusters`.

- [ ] Tests: role filter; unknown role 422; `/api/roles` lists 5 positions and 18 roles with sizes; agreement is above chance for every position.
- [ ] Implement, run, pass.

### Task 5: Frontend

**Files:** Modify `frontend/src/api.js`, `components/PlayersView.jsx`, `PlayerDetail.jsx`, `ScoutingView.jsx`, `ModelView.jsx`

- [ ] Players: role select (options follow the chosen position), role shown in each row.
- [ ] Player panel: role, description, "nth of N <role plural>", percentiles against the role.
- [ ] Scouting cards show role. "How it works" shows roles per position with sizes, signals and the K-Means agreement.
- [ ] `npm run build` succeeds; check in the browser.

### Task 6: README

- [ ] Replace the playing-styles row and results text with roles; update sanity checks, test count, API table, layout and limitations.
