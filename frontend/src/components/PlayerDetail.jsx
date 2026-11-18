import { useApi, POSITION_NAMES, fmt, ordinal, sentence } from "../api.js";

export const METRIC_NAMES = {
  npxG: "Non-penalty xG",
  xAG: "Expected assists (xAG)",
  "Aerial win %": "Aerial duels won",
  "Save %": "Save percentage",
  "Crosses stopped %": "Crosses claimed",
  "Challenge success": "Tackle success vs dribblers",
  Switches: "Switches of play",
  "Sweeper actions": "Actions outside the box",
  "Fouls drawn": "Fouls won",
  "Progressive receptions": "Progressive passes received",
};

const rateMetrics = new Set(["Pass accuracy", "Challenge success", "Aerial win %", "Save %", "Crosses stopped %"]);

export default function PlayerDetail({ id, onSelect }) {
  const { data: p, error, loading } = useApi(`/players/${id}`, {}, [id]);

  if (error) return <p className="notice">Couldn't load this player. {error.message}</p>;
  if (!p) return <p className="count">{loading ? "Loading…" : ""}</p>;

  const posName = POSITION_NAMES[p.position] ?? "Player";
  // Fall back to the position if the API is an older build without roles.
  const peers = p.role_plural ?? `${posName.toLowerCase()}s`;
  const rawGap = p.xga90 !== null ? p.ga90 - p.xga90 : null;
  const gap = rawGap !== null && Math.abs(rawGap) < 0.005 ? 0 : rawGap;

  return (
    <article className={`card-detail${loading ? " is-loading" : ""}`}>
      <p className="detail-meta">
        {p.club}, {p.league}. {p.age ? `Age ${p.age}, ` : ""}
        {p.nationality}
      </p>
      <h2 className="detail-name">{p.name}</h2>
      {p.clubs.includes(" / ") && <p className="hint">Also played for {p.clubs.split(" / ").filter((c) => c !== p.club).join(" and ")} this season. Stats are combined.</p>}

      <div className="scoreline">
        <div className="big-rating">
          <span className="big-num">{fmt(p.rating, 1)}</span>
          <span className="big-label">rating</span>
        </div>
        <div className="scoreline-text">
          {p.role_rank ? (
            <p>
              <strong>
                {ordinal(p.role_rank.rank)} of {p.role_rank.of}
              </strong>{" "}
              {peers} with 900+ minutes across the top five leagues.
            </p>
          ) : (
            <p>
              Only {p.minutes} minutes played, so this rating is pulled toward the average of 50.
            </p>
          )}
          {p.role && (
            <p>
              Role: <strong>{p.role}</strong> ({posName.toLowerCase()}). {p.role_description}
            </p>
          )}
        </div>
      </div>

      <dl className="statline">
        <div><dt>Apps</dt><dd>{p.appearances}</dd></div>
        <div><dt>Minutes</dt><dd>{p.minutes.toLocaleString()}</dd></div>
        <div><dt>Goals</dt><dd>{p.goals}</dd></div>
        <div><dt>Assists</dt><dd>{p.assists}</dd></div>
      </dl>

      <h3 className="sub">How the rating is built</h3>
      <p className="hint">
        Percentile against {peers} with 900+ minutes in all five leagues, on the stats this role
        is judged by. Counting stats are per 90 minutes. Bar thickness shows how much each stat
        counts.
      </p>
      <ul className="pct-list">
        {p.percentiles.map((m) => (
          <li key={m.metric} className="pct-row">
            <span className="pct-name">
              {METRIC_NAMES[m.metric] ?? sentence(m.metric)}
              {(m.per90 ?? !rateMetrics.has(m.metric)) ? " per 90" : ""}
              {m.lower_is_better ? ", fewer is better" : ""}
            </span>
            <span className="pct-bar" aria-hidden="true">
              <span className="pct-mid" />
              <span
                className="pct-fill"
                style={{ width: `${m.percentile}%`, height: `${4 + m.weight * 30}px` }}
              />
            </span>
            <span className="pct-val">{Math.round(m.percentile)}</span>
          </li>
        ))}
      </ul>

      {p.xga90 !== null && (
        <>
          <h3 className="sub">Expected vs actual output</h3>
          <p className="hint">
            Non-penalty goals plus assists per 90, against what the model expects from how they
            play (shots, touches in the box, key passes, carries). It doesn't use xG.
          </p>
          <dl className="xga">
            <div><dt>Actual</dt><dd>{fmt(p.ga90)}</dd></div>
            <div><dt>Expected</dt><dd>{fmt(p.xga90)}</dd></div>
            <div>
              <dt>Difference</dt>
              <dd className={gap > 0 ? "pos" : gap < 0 ? "neg" : undefined}>
                {gap > 0 ? "+" : gap < 0 ? "−" : ""}
                {fmt(Math.abs(gap))}
              </dd>
            </div>
          </dl>
        </>
      )}

      <h3 className="sub">Most similar {posName.toLowerCase()}s in Europe</h3>
      <p className="hint">Compared across every role in the position, so a match may carry a different label.</p>
      <ul className="similar">
        {p.similar.map((s) => (
          <li key={s.id}>
            <button className="link" onClick={() => onSelect(s.id)}>
              {s.name}
            </button>
            <span className="club">
              {s.club}, {s.league}
            </span>
            <span className="sim">{Math.round(s.similarity)}% match</span>
          </li>
        ))}
      </ul>
    </article>
  );
}
