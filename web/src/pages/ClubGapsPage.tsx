import { Link, useParams } from "react-router-dom";
import type { ClubGaps, PositionGap } from "../api/types";
import { Panel, StatusTag } from "../components/bits";
import { FormationPitch } from "../components/FormationPitch";
import { ErrorState, LoadingPanel } from "../components/states";
import { useApi } from "../hooks/useApi";
import { POSITION_NAMES, fixed, signed } from "../lib/format";

function VsLeague({ gap, max }: { gap: PositionGap; max: number }) {
  const pct = (v: number | null) => `${Math.min(100, ((v ?? 0) / max) * 100)}%`;
  const tone = gap.status === "missing" ? "weak" : gap.status;
  return (
    <div className="vs-bars" aria-hidden="true">
      <div className="vs-bar">
        <span>Squad</span>
        <span className="bar"><span className={`squad--${tone}`} style={{ width: pct(gap.squadPredictedP90) }} /></span>
        <span className="num">{fixed(gap.squadPredictedP90)}</span>
      </div>
      <div className="vs-bar">
        <span>League</span>
        <span className="bar"><span className="league" style={{ width: pct(gap.leaguePredictedP90) }} /></span>
        <span className="num">{fixed(gap.leaguePredictedP90)}</span>
      </div>
    </div>
  );
}

export function ClubGapsPage() {
  const { id } = useParams();
  const gaps = useApi<ClubGaps>(`/clubs/${id}/gaps`);

  if (gaps.status === "loading") {
    return <div className="grid-2"><LoadingPanel height={460} label="Loading squad" /><LoadingPanel height={460} label="Loading squad" /></div>;
  }
  if (gaps.status === "error") return <Panel><ErrorState error={gaps.error} onRetry={gaps.retry} /></Panel>;

  const { club, positions, weakest } = gaps.data;
  const max = Math.max(0.1, ...positions.flatMap((p) => [p.squadPredictedP90 ?? 0, p.leaguePredictedP90]));
  const weak = positions.find((p) => p.position === weakest);

  return (
    <>
      <div className="page-head">
        <div>
          <p className="eyebrow"><Link to="/clubs" style={{ color: "inherit" }}>Squad gaps</Link> · {club.league}</p>
          <h1>{club.name}</h1>
          <p className="lede">
            {weak
              ? weak.status === "missing"
                ? <>Weakest: <strong>{POSITION_NAMES[weak.position].toLowerCase()}s</strong>, with no qualified player in that position.</>
                : weak.status === "above"
                  ? <>Every outfield position is at or above the {club.league} average.</>
                  : <>Weakest: <strong>{POSITION_NAMES[weak.position].toLowerCase()}s</strong>, <span className="num">{signed(weak.vsLeaguePct, 1)}%</span> against the {club.league} average.</>
              : "No modelled players."}
          </p>
        </div>
      </div>

      <div className="grid-2">
        <Panel index={0} label="Formation">
          <div className="panel__title">
            <h2>4-3-3</h2>
            <p>Regulars by minutes</p>
          </div>
          <FormationPitch positions={positions} club={club.name} />
          <div className="legend" aria-label="Legend">
            <StatusTag status="above" />
            <StatusTag status="below" />
            <StatusTag status="weak" />
            <StatusTag status="missing" />
          </div>
        </Panel>

        <Panel index={1} label="Positions">
          <div className="panel__title">
            <h2>By position</h2>
            <p>Expected npG+A per 90</p>
          </div>
          {positions.map((g) => (
            <div key={g.position} className="gap-row">
              <span className="pos-chip">{g.position}</span>
              <div style={{ display: "grid", gap: 6 }}>
                <StatusTag status={g.status} />
                <VsLeague gap={g} max={max} />
              </div>
              <span className="big-num" style={{ textAlign: "right" }}>
                {g.vsLeaguePct === null ? "—" : `${signed(g.vsLeaguePct, 1)}%`}
                <span className="sr-only"> against the league average</span>
              </span>
              <div className="gap-row__players">
                {g.players.length
                  ? g.players.map((pl, i) => (
                    <span key={pl.id}>{i > 0 && ", "}<Link to={`/players/${pl.id}`}>{pl.name}</Link></span>
                  ))
                  : `No ${POSITION_NAMES[g.position].toLowerCase()} with 900+ minutes`}
              </div>
            </div>
          ))}
          <p className="note">{gaps.data.method}</p>
        </Panel>
      </div>
    </>
  );
}
