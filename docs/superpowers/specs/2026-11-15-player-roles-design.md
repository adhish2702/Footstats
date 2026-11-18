# Player roles: design

Approved 2026-11-15.

## Intent

One set of rating weights per position treats a poacher and a false nine, or a
ball-winner and a number 10, as if they had the same job. Every player should
be placed in a tactical role within their position and rated on what that role
is for.

## Goals

- Every player gets exactly one role, chosen from their position's roles.
- Each role has its own rating weights.
- A player is rated and ranked against players in the same role.
- The app shows the role, lets you filter by it, and explains how roles are decided.

## Non-goals

- No new data source. Roles come from the FBref columns already in the CSV.
- The goals-plus-assists model and the similar-player search keep working as they do now.

## Anti-goals

- Roles must not be decided by output (goals, assists, xG). They describe how
  someone plays, not how good they are.
- No hand-labelled players. Assignment is a rule applied to everyone.

## Roles (18)

| Position | Roles |
|---|---|
| GKP | Sweeper-keeper, Ball-playing goalkeeper |
| DEF | Ball-playing centre-back, Stopper, Wide centre-back, Inverted full-back, Wing-back |
| MID | Deep-lying playmaker, Ball-winning midfielder, Box-to-box midfielder, Advanced playmaker |
| WNG | Inside forward, Touchline winger, Wide playmaker |
| STR | Pressing forward, False nine, Poacher, Target forward |

Stopper is the one addition to the user's 17. Without it every centre-back who
is not a passer was labelled "wide", which was wrong. The user approved adding it.

## Constraints

- The data has no footedness, pitch coordinates or pressing counts, so roles are
  inferred from proxies (touch shares by third, crosses, throw-ins, switches,
  tackles by third, offsides, fouls, goalkeeper pass length and so on).
- FBref lists full-backs and centre-backs both as "DF", so defenders are split
  into full-backs and centre-backs first, then given a role within that group.
- Project is not a git repo, so nothing is committed.

## Approaches considered

1. **Role scores from signals, best fit wins (chosen).** Each role has a short
   list of signed signals; a player's score for a role is the average of capped
   z-scores against qualified players in the same position; the highest score
   is the role. Same method as the existing striker/winger split, explainable in
   one sentence, and testable against named players.
2. **Use the K-Means clusters as roles.** Fully data-driven, but clusters do not
   line up with named tactical roles and the names would have to be forced on.
3. **Hand-label well-known players and train a classifier.** Needs labels that
   do not exist for 2,700 players and would be subjective.

## Decisions

- Rating pool: same role, qualified players. If a role has fewer than 15
  qualified players the position pool is used instead.
- Rank shown on the player page is within the role.
- Roles replace the K-Means "playing style" label in the API and UI. K-Means is
  kept as a check: per position, how well unsupervised clusters on the same
  signals agree with the assigned roles.
- Position codes (`GKP, DEF, MID, WNG, STR`) are unchanged. `role` is a new
  field and a new optional filter.

## Left to the builder

- Exact signals and weights per role, tuned so that well-known players land in
  the expected role and role sizes are not degenerate.
- How the K-Means agreement is reported.
