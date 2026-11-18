import { Link, useSearchParams } from "react-router-dom";
import { path } from "../api/client";
import type { ModelInfo, OverUnder, PlayerSummary } from "../api/types";
import { Avatar, CountUp, GapVerdict, Panel } from "../components/bits";
import { DownIcon, UpIcon } from "../components/icons";
import { EmptyState, ErrorState, LoadingRows } from "../components/states";
import { useApi } from "../hooks/useApi";
import { LEAGUES, POSITION_NAMES, fixed } from "../lib/format";

function List({ players, kind, max, typicalError }: {
  players: PlayerSummary[]; kind: "over" | "under"; max: number; typicalError: number;
}) {
  if (players.length === 0) return <EmptyState title="Nobody here">No players match these filters.</EmptyState>;
  return (
    <ol className="ou-list">
      {players.map((p, i) => {
        const gap = Math.abs(p.prediction!.gapP90);
        return (
          <li key={p.id} className="ou-item enter" style={{ "--i": i } as React.CSSProperties}>
            <span className="rank num">{i + 1}</span>
            <Avatar name={p.name} size={36} />
            <div className="who">
              <Link to={`/players/${p.id}`}>{p.name}</Link>
              <small>
                {p.club.name} · {p.position} · actual <span className="num">{fixed(p.prediction!.actualP90)}</span> vs predicted{" "}
                <span className="num">{fixed(p.prediction!.predictedP90)}</span>
              </small>
            </div>
            <GapVerdict prediction={p.prediction} typicalError={typicalError} compact />
            <div className={`gapbar gapbar--${kind}`} aria-hidden="true">
              <span style={{ width: `${(gap / max) * 100}%` }} />
            </div>
          </li>
        );
      })}
    </ol>
  );
}

export function InsightsPage() {
  const [params, setParams] = useSearchParams();
  const position = params.get("position") ?? "";
  const league = params.get("league") ?? "";
  const limit = params.get("limit") ?? "10";
  const set = (k: string, v: string) => {
    const next = new URLSearchParams(params);
    if (v) next.set(k, v);
    else next.delete(k);
    setParams(next, { replace: true });
  };

  const data = useApi<OverUnder>(path("/insights/over-under", { position, league, limit: limit === "10" ? undefined : limit }));
  const model = useApi<ModelInfo>("/model");
  const typicalError = model.data?.metrics.testMae ?? 0.07;
  const all = data.data ? [...data.data.overperformers, ...data.data.underperformers] : [];
  const max = Math.max(0.05, ...all.map((p) => Math.abs(p.prediction!.gapP90)));

  return (
    <>
      <div className="page-head">
        <div>
          <p className="eyebrow">Actual vs expected</p>
          <h1>Over / under-performers</h1>
          <p className="lede">
            Where a player's non-penalty goals + assists per 90 differ most from what the model expects from how they play.
            Every prediction comes from a model trained without that player.
          </p>
        </div>
      </div>

      {model.status === "ready" && (
        <div className="metric-strip">
          <Panel index={0} label="Model error">
            <p className="label">Held-out error</p>
            <div className="kpi__value" style={{ color: "var(--cyan)" }}><CountUp value={model.data.metrics.testMae} digits={3} /></div>
            <p className="kpi__note">Mean absolute error, npG+A per 90</p>
          </Panel>
          <Panel index={1} label="Baseline">
            <p className="label">Baseline error</p>
            <div className="kpi__value"><CountUp value={model.data.metrics.baselineMae} digits={3} /></div>
            <p className="kpi__note">Always predicting the average</p>
          </Panel>
          <Panel index={2} label="R squared">
            <p className="label">R²</p>
            <div className="kpi__value" style={{ color: "var(--green)" }}><CountUp value={model.data.metrics.testR2} digits={2} /></div>
            <p className="kpi__note">On {model.data.testPlayers} held-out players</p>
          </Panel>
          <Panel index={3} label="Model">
            <p className="label">Model</p>
            <div className="kpi__value" style={{ fontSize: "1.6rem" }}>{model.data.modelName}</div>
            <p className="kpi__note">{model.data.players.toLocaleString("en-GB")} players, 900+ minutes</p>
          </Panel>
        </div>
      )}

      <div className="filters" style={{ gridTemplateColumns: "repeat(3, minmax(140px, 1fr))" }}>
        <div className="field">
          <label htmlFor="ou-position">Position</label>
          <select id="ou-position" className="select" value={position} onChange={(e) => set("position", e.target.value)}>
            <option value="">All outfield</option>
            {(["DEF", "MID", "WNG", "STR"] as const).map((p) => <option key={p} value={p}>{POSITION_NAMES[p]}</option>)}
          </select>
        </div>
        <div className="field">
          <label htmlFor="ou-league">League</label>
          <select id="ou-league" className="select" value={league} onChange={(e) => set("league", e.target.value)}>
            <option value="">All leagues</option>
            {LEAGUES.map((l) => <option key={l} value={l}>{l}</option>)}
          </select>
        </div>
        <div className="field">
          <label htmlFor="ou-limit">Show</label>
          <select id="ou-limit" className="select" value={limit} onChange={(e) => set("limit", e.target.value === "10" ? "" : e.target.value)}>
            {[5, 10, 20, 50].map((n) => <option key={n} value={n}>Top {n}</option>)}
          </select>
        </div>
      </div>

      {data.status === "error" && <Panel><ErrorState error={data.error} onRetry={data.retry} /></Panel>}
      {data.status !== "error" && (
        <div className="ou-grid">
          <Panel index={4} label="Over-performers">
            <div className="panel__title">
              <h2 style={{ display: "flex", alignItems: "center", gap: 8 }}><UpIcon style={{ color: "var(--green)" }} /> Over-performing</h2>
              <p>Actual above predicted</p>
            </div>
            {data.status === "loading" ? <LoadingRows rows={6} /> : <List players={data.data.overperformers} kind="over" max={max} typicalError={typicalError} />}
          </Panel>
          <Panel index={5} label="Under-performers">
            <div className="panel__title">
              <h2 style={{ display: "flex", alignItems: "center", gap: 8 }}><DownIcon style={{ color: "var(--magenta)" }} /> Under-performing</h2>
              <p>Actual below predicted</p>
            </div>
            {data.status === "loading" ? <LoadingRows rows={6} /> : <List players={data.data.underperformers} kind="under" max={max} typicalError={typicalError} />}
          </Panel>
        </div>
      )}
      <p className="note">
        A big gap can mean finishing well or badly, but also luck, a small sample of minutes, or something the model can't see
        (such as shot quality). Gaps under {fixed(typicalError, 2)} are within the model's typical error.
      </p>
    </>
  );
}
