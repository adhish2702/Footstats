import { Link, useParams } from "react-router-dom";
import type { ModelInfo, PlayerDetail } from "../api/types";
import type { KeeperVsXg } from "../api/types";
import { Avatar, ClubBadge, CountUp, GapVerdict, Panel, PositionChip, VsExpected } from "../components/bits";
import { StyleRadar } from "../components/charts";
import { MiniPitch, PredictionGauge } from "../components/svg";
import { PlusIcon } from "../components/icons";
import { ErrorState, LoadingPanel, Skeleton } from "../components/states";
import { useCompare } from "../hooks/compare";
import { useApi } from "../hooks/useApi";
import { KEEPER_LEVEL, fixed, ordinal, thousands } from "../lib/format";

/** Goals conceded per 90 against what the shots faced were worth. Lower conceded is better. */
function KeeperBars({ keeper }: { keeper: KeeperVsXg }) {
  const max = Math.max(keeper.concededP90, keeper.expectedConcededP90, 0.1) * 1.15;
  const good = keeper.preventedP90 >= 0;
  const row = (label: string, value: number, cls: string) => (
    <div className="vs-bar vs-bar--wide">
      <span>{label}</span>
      <span className="bar"><span className={cls} style={{ width: `${(value / max) * 100}%` }} /></span>
      <span className="num">{fixed(value)}</span>
    </div>
  );
  return (
    <div className="vs-bars" role="img"
      aria-label={`Conceded ${fixed(keeper.concededP90)} per 90 against ${fixed(keeper.expectedConcededP90)} expected.`}>
      {row("Conceded", keeper.concededP90, good ? "squad--above" : "squad--weak")}
      {row("Expected", keeper.expectedConcededP90, "league")}
    </div>
  );
}

export function PlayerPage() {
  const { id } = useParams();
  const player = useApi<PlayerDetail>(`/players/${id}`);
  const model = useApi<ModelInfo>("/model");
  const compare = useCompare();
  const typicalError = model.data?.metrics.testMae ?? 0.07;

  if (player.status === "loading") {
    return (
      <div className="stack" role="status" aria-label="Loading player">
        <div style={{ display: "flex", gap: 18, alignItems: "center" }}>
          <Skeleton width={72} height={72} style={{ borderRadius: "50%" }} />
          <div style={{ flex: 1, display: "grid", gap: 10 }}><Skeleton width="45%" height={34} /><Skeleton width="30%" /></div>
        </div>
        <div className="kpis">{[0, 1, 2, 3].map((i) => <LoadingPanel key={i} height={40} />)}</div>
        <div className="grid-2"><LoadingPanel height={320} /><LoadingPanel height={320} /></div>
      </div>
    );
  }
  if (player.status === "error") return <Panel><ErrorState error={player.error} onRetry={player.retry} /></Panel>;

  const p = player.data;
  const out = p.stats.output;
  const gk = p.stats.goalkeeping;

  return (
    <>
      <Panel index={0} className="profile-head" label="Player">
        <Avatar name={p.name} size={72} />
        <div>
          <p className="eyebrow">{p.role}</p>
          <h1>{p.name}</h1>
          <div className="profile-head__meta">
            <ClubBadge club={p.club} />
            <span>{p.club.league}</span>
            <PositionChip position={p.position} />
            {p.age !== null && <span><span className="num">{p.age}</span> years</span>}
            {p.nationality && <span title="Nationality (FBref code)">{p.nationality}</span>}
            {p.clubsPlayed !== p.club.name && <span className="muted">Season: {p.clubsPlayed}</span>}
          </div>
        </div>
        <div className="profile-head__actions">
          {compare.has(p.id) ? (
            <Link className="button button--ghost" to="/compare">In comparison · view</Link>
          ) : (
            <button type="button" className="button" onClick={() => compare.add(p.id)} disabled={compare.full}
              title={compare.full ? "Remove someone from the comparison first (3 maximum)" : undefined}>
              <PlusIcon /> Compare
            </button>
          )}
        </div>
      </Panel>

      <div className="kpis">
        <Panel index={1} label="Rating">
          <p className="label">Role rating</p>
          <div className="kpi__value" style={{ color: "var(--green)" }}><CountUp value={p.rating} digits={0} /></div>
          <p className="kpi__note">0–99 · 50 is an average {p.role.toLowerCase()}</p>
        </Panel>
        <Panel index={2} label="Goals and assists per 90">
          <p className="label">npG+A per 90</p>
          <div className="kpi__value"><CountUp value={out.npgaP90} /></div>
          <p className="kpi__note"><span className="num">{out.nonPenaltyGoals}</span> non-penalty goals, <span className="num">{out.assists}</span> assists</p>
        </Panel>
        {p.keeper ? (
          <Panel index={3} label="Goals prevented">
            <p className="label">Goals prevented per 90</p>
            <div className="kpi__value" style={{ color: "var(--cyan)" }}><CountUp value={p.keeper.preventedP90} signedValue /></div>
            <p className="kpi__note">Post-shot xG faced minus goals conceded</p>
          </Panel>
        ) : (
          <Panel index={3} label="Predicted">
            <p className="label">Predicted per 90</p>
            <div className="kpi__value" style={{ color: "var(--cyan)" }}>
              {p.prediction ? <CountUp value={p.prediction.predictedP90} /> : <span className="num">—</span>}
            </div>
            <p className="kpi__note">{p.prediction ? "From playing style alone" : "Outfield players with 900+ minutes only"}</p>
          </Panel>
        )}
        <Panel index={4} label="Minutes">
          <p className="label">Minutes</p>
          <div className="kpi__value"><span className="num">{thousands(p.minutes)}</span></div>
          <p className="kpi__note"><span className="num">{p.appearances}</span> apps, <span className="num">{p.starts}</span> starts</p>
        </Panel>
      </div>

      <div className="grid-2">
        <Panel index={5} label="Playing style">
          <div className="panel__title">
            <h2>Playing style</h2>
            <p>Percentile vs {p.style.comparedWith}</p>
          </div>
          <StyleRadar series={[{ name: p.name, features: p.style.features }]}
            label={`Radar of ${p.name}'s playing-style percentiles. The full list follows.`} />
          <ul className="feature-list" aria-label="All 19 style features">
            {p.style.features.map((f) => (
              <li key={f.key} className="feature-row">
                <span>{f.label}{f.lowerIsBetter && <span className="muted"> (lower is better)</span>}</span>
                <span className="bar" aria-hidden="true"><span style={{ width: `${f.percentile ?? 0}%` }} /></span>
                <span className="vals">
                  <span className="num">{fixed(f.value)}</span>{" "}
                  <span className="muted">· <span className="num">{ordinal(f.percentile)}</span></span>
                </span>
              </li>
            ))}
          </ul>
          <p className="note">Per 90 minutes. These 19 numbers are the model's inputs: it never sees goals, assists or xG.</p>
        </Panel>

        <div className="stack">
          {p.keeper ? (
            <Panel index={6} label="Goals conceded vs expected">
              <div className="panel__title">
                <h2>Conceded vs expected</h2>
                <VsExpected player={p} />
              </div>
              <KeeperBars keeper={p.keeper} />
              <p className="note">
                Per 90. Expected is the post-shot xG of the shots on target faced (FBref/Opta): how many goals an average
                keeper would concede from them. Goals prevented is expected minus conceded; within{" "}
                <span className="num">{fixed(KEEPER_LEVEL, 2)}</span> either way is called level. This is not the
                goals + assists model, which covers outfield players only.
              </p>
            </Panel>
          ) : (
          <Panel index={6} label="Predicted vs actual">
            <div className="panel__title">
              <h2>Predicted vs actual</h2>
              {p.prediction && <GapVerdict prediction={p.prediction} typicalError={typicalError} />}
            </div>
            {p.prediction ? (
              <>
                <PredictionGauge prediction={p.prediction} typicalError={typicalError} />
                <p className="note">
                  Non-penalty goals + assists per 90. The prediction comes from a model that was trained without this player
                  {p.prediction.inTestSet ? ", who is also one of the 292 held-out test players" : ""}. Gaps under{" "}
                  <span className="num">{fixed(typicalError, 2)}</span> (the model's typical error) are called level.
                </p>
              </>
            ) : (
              <p className="muted">
                {p.position === "GKP"
                  ? `Goals prevented is shown for goalkeepers with 900+ minutes; ${p.name} played ${thousands(p.minutes)}.`
                  : `The model covers players with 900+ minutes; ${p.name} played ${thousands(p.minutes)}.`}
              </p>
            )}
          </Panel>
          )}

          <Panel index={7} label="Position">
            <div className="panel__title"><h2>Position</h2></div>
            <MiniPitch position={p.position} role={p.role} />
          </Panel>

          <Panel index={8} label="Season numbers">
            <div className="panel__title"><h2>Season</h2></div>
            <dl className="stat-grid">
              <div><dt>Goals</dt><dd>{out.goals}</dd></div>
              <div><dt>Assists</dt><dd>{out.assists}</dd></div>
              <div><dt>Penalty goals</dt><dd>{out.penaltyGoals}</dd></div>
              <div><dt>npxG</dt><dd>{fixed(out.npxg, 1)}</dd></div>
              <div><dt>xAG</dt><dd>{fixed(out.xag, 1)}</dd></div>
              <div><dt>Pass accuracy</dt><dd>{fixed(p.stats.defending.passAccuracyPct, 0)}%</dd></div>
              <div><dt>Tackles won /90</dt><dd>{fixed(p.stats.defending.tacklesWonP90)}</dd></div>
              <div><dt>Interceptions /90</dt><dd>{fixed(p.stats.defending.interceptionsP90)}</dd></div>
              {gk && (
                <>
                  <div><dt>Save %</dt><dd>{fixed(gk.savesPct, 1)}</dd></div>
                  <div><dt>Clean sheets</dt><dd>{gk.cleanSheets}</dd></div>
                  <div><dt>Goals conceded</dt><dd>{gk.goalsConceded}</dd></div>
                  <div><dt>Goals prevented</dt><dd>{fixed(gk.goalsPrevented, 1)}</dd></div>
                </>
              )}
            </dl>
          </Panel>
        </div>
      </div>
    </>
  );
}
