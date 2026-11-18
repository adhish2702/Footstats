import { useState } from "react";
import { useApi, POSITION_NAMES, fmt, sentence } from "../api.js";
import { METRIC_NAMES } from "./PlayerDetail.jsx";

export default function ModelView({ onOpen }) {
  const model = useApi("/model");
  const roles = useApi("/roles");
  const m = model.data;

  return (
    <div className="model">
      <section className="block">
        <h2 className="h2">Expected goal contributions</h2>
        <p className="lede">
          A model predicts each outfield player's non-penalty goals plus assists per 90 from how
          they play: shots, touches in the box, key passes, carries and take-ons. It never sees
          goals, assists or xG. Penalties are left out because taking them is an assigned job,
          not a style of play. It was trained on 80% of the {m?.n_players?.toLocaleString() ?? "…"}{" "}
          outfield players with 900+ minutes across the five leagues, then scored once on the
          other 20% it had never seen.
        </p>

        {m && (
          <>
            <dl className="metrics">
              <div>
                <dt>Average error on unseen players</dt>
                <dd>{fmt(m.test_mae, 3)}</dd>
                <p>non-penalty goals + assists per 90</p>
              </div>
              <div>
                <dt>Guessing the average instead</dt>
                <dd>{fmt(m.baseline_mae, 3)}</dd>
                <p>the model cuts this error by {m.error_reduction_pct}%</p>
              </div>
              <div>
                <dt>Variance explained (R²)</dt>
                <dd>{fmt(m.test_r2, 2)}</dd>
                <p>on {m.n_test} held-out players</p>
              </div>
              <div className="bench">
                <dt>Professional npxG + xAG, same players</dt>
                <dd>{fmt(m.xg_mae, 3)}</dd>
                <p>R² {fmt(m.xg_r2, 2)}, using shot locations this model doesn't have</p>
              </div>
            </dl>
            <p className="hint">
              {m.chosen_model} was chosen over{" "}
              {Object.keys(m.cv_mae).filter((k) => k !== m.chosen_model).join(", ").toLowerCase()} by
              5-fold cross-validation on the training players (error{" "}
              {Object.entries(m.cv_mae)
                .map(([k, v]) => `${k.toLowerCase()} ${fmt(v, 3)}`)
                .join(" vs ")}
              ).
            </p>

            <div className="model-grid">
              <figure className="fig">
                <figcaption>Predicted vs actual, held-out players</figcaption>
                <Scatter points={m.test_points} onOpen={onOpen} />
              </figure>
              <figure className="fig">
                <figcaption>What the model relies on</figcaption>
                <p className="hint">
                  {m.chosen_model === "Ridge regression"
                    ? "Each input's share of the prediction, measured by the size of its standardised coefficient."
                    : "Each input's share of the forest's split decisions."}{" "}
                  The top inputs are {m.feature_importance.slice(0, 2).map((f) => sentence(f.feature)).join(" and ").toLowerCase()}.
                </p>
                <Importance rows={m.feature_importance.slice(0, 6)} />
              </figure>
            </div>
          </>
        )}
      </section>

      <section className="block">
        <h2 className="h2">Roles</h2>
        <p className="lede">
          Every player is placed in one of 18 tactical roles within their position, then rated on
          what that role is for and ranked against others doing the same job. A poacher is judged
          mostly on goals and chances; a false nine on creating as well as scoring; a stopper on
          clearances, blocks and headers; a ball-playing centre-back on moving the ball forward.
        </p>
        <p className="hint">
          Roles come from how someone plays, never from goals or assists. Each role lists a few
          things it does more or less of than is typical for the position, and a player gets the
          role that fits best. The data has no footedness, pitch positions or pressing counts, so
          these are stand-ins: an inside forward is a winger who shoots and gets into the box
          rather than crossing; a pressing forward is a striker who tackles high up the pitch.
          The source lists strikers and wingers alike as forwards, and full-backs and centre-backs
          alike as defenders, so those are separated the same way first.
        </p>
        {roles.data && (
          <p className="hint">
            As a check, K-Means was asked to group each position by the same signals without being
            told the roles. Its groups match the assigned role for{" "}
            {Math.round(roles.data.agreement * 100)}% of players with 900+ minutes, well above
            chance but far from perfect: roles blend into each other rather than forming hard
            boxes.
          </p>
        )}
        <div className="roles">
          {(roles.data?.positions ?? []).map((pos) => (
            <div key={pos.position} className="role-pos">
              <h3 className="sub">
                {POSITION_NAMES[pos.position]}s{" "}
                {pos.check && (
                  <span className="quiet">
                    K-Means agrees for {Math.round(pos.check.agreement * 100)}% (chance{" "}
                    {Math.round(pos.check.chance * 100)}%)
                  </span>
                )}
              </h3>
              <ul>
                {pos.roles.map((r) => (
                  <li key={r.role}>
                    <p className="role-head">
                      <strong>{r.role}</strong>
                      <span className="quiet">{r.size} players</span>
                    </p>
                    <p className="role-text">{r.description}</p>
                    <p className="role-text quiet">
                      More {listOf(r.more_of)}
                      {r.less_of.length > 0 && `; less ${listOf(r.less_of)}`}.
                    </p>
                    <p className="role-text quiet">
                      Rated mainly on{" "}
                      {listOf(
                        [...r.weights]
                          .sort((a, b) => b.weight - a.weight)
                          .slice(0, 3)
                          .map((w) => METRIC_NAMES[w.metric] ?? w.metric)
                      )}
                      . Top rated: {r.examples.join(", ")}.
                    </p>
                  </li>
                ))}
              </ul>
            </div>
          ))}
        </div>
      </section>
    </div>
  );
}

const lower = (text) => (/^(npxG|xAG)/.test(text) ? text : text.charAt(0).toLowerCase() + text.slice(1));

function listOf(items) {
  const words = items.map(lower);
  return words.length > 1 ? `${words.slice(0, -1).join(", ")} and ${words[words.length - 1]}` : words[0];
}

function Scatter({ points, onOpen }) {
  const [hover, setHover] = useState(null);
  const W = 420, H = 320, P = { l: 44, r: 12, t: 12, b: 40 };
  const max = Math.ceil(Math.max(...points.flatMap((p) => [p.actual, p.predicted])) * 5) / 5;
  const x = (v) => P.l + (v / max) * (W - P.l - P.r);
  const y = (v) => H - P.b - (v / max) * (H - P.t - P.b);
  const ticks = Array.from({ length: Math.round(max / 0.2) + 1 }, (_, i) => +(i * 0.2).toFixed(1));

  return (
    <div className="scatter">
      <svg viewBox={`0 0 ${W} ${H}`} role="img" aria-label="Scatter plot of predicted against actual non-penalty goals plus assists per 90 for held-out players">
        {ticks.map((t) => (
          <g key={t}>
            <line className="grid" x1={x(0)} x2={x(max)} y1={y(t)} y2={y(t)} />
            <text className="tick" x={P.l - 8} y={y(t) + 4} textAnchor="end">{t}</text>
            <text className="tick" x={x(t)} y={H - P.b + 18} textAnchor="middle">{t}</text>
          </g>
        ))}
        <line className="ideal" x1={x(0)} y1={y(0)} x2={x(max)} y2={y(max)} />
        <text className="tick" x={x(max) - 4} y={y(max) + 16} textAnchor="end">perfect prediction</text>
        <text className="axis" x={(W + P.l) / 2} y={H - 4} textAnchor="middle">Actual per 90</text>
        <text className="axis" transform={`translate(12 ${(H - P.b) / 2}) rotate(-90)`} textAnchor="middle">Predicted per 90</text>
        {points.map((p) => (
          <g key={p.id}>
            <circle
              className={`dot${hover?.id === p.id ? " is-hover" : ""}`}
              cx={x(p.actual)} cy={y(p.predicted)} r={3.5}
            />
            <circle
              className="hit" cx={x(p.actual)} cy={y(p.predicted)} r={7}
              tabIndex={0}
              aria-label={`${p.name}: actual ${p.actual}, predicted ${p.predicted}`}
              onMouseEnter={() => setHover(p)} onMouseLeave={() => setHover(null)}
              onFocus={() => setHover(p)} onBlur={() => setHover(null)}
              onClick={() => onOpen(p.id)}
              onKeyDown={(e) => e.key === "Enter" && onOpen(p.id)}
            />
          </g>
        ))}
      </svg>
      {hover && (
        <div
          className="tip"
          style={{ left: `${(x(hover.actual) / W) * 100}%`, top: `${(y(hover.predicted) / H) * 100}%` }}
        >
          <strong>{hover.name}</strong>
          <span>Actual {fmt(hover.actual)}</span>
          <span>Predicted {fmt(hover.predicted)}</span>
        </div>
      )}
    </div>
  );
}

function Importance({ rows }) {
  const max = Math.max(...rows.map((r) => r.importance), 1e-6);
  return (
    <ul className="imp">
      {rows.map((r) => (
        <li key={r.feature}>
          <span className="imp-name">
            {r.feature.startsWith("is_")
              ? `Is a ${{ FWD: "forward", MID: "midfielder" }[r.feature.slice(3)] ?? r.feature.slice(3)}`
              : r.feature.startsWith("league_")
                ? `Plays in ${r.feature.slice(7)}`
                : METRIC_NAMES[r.feature] ?? sentence(r.feature)}
          </span>
          <span className="imp-bar" aria-hidden="true">
            <span style={{ width: `${Math.max((r.importance / max) * 100, 0.5)}%` }} />
          </span>
          <span className="imp-val">{Math.round(r.importance * 100)}%</span>
        </li>
      ))}
    </ul>
  );
}
