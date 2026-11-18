import { Link, useParams } from "react-router-dom";
import type { ClubGaps, KeeperGap, PositionGap } from "../api/types";
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

/** The goalkeeper row: goals prevented per 90, squad against league (either can be negative). */
function KeeperRow({ gap }: { gap: KeeperGap }) {
  const values = [gap.squadPreventedP90 ?? 0, gap.leaguePreventedP90 ?? 0];
  const span = Math.max(0.15, ...values.map(Math.abs));
  // A centred bar: left of the middle is negative, right is positive.
  const bar = (v: number | null, cls: string) => {
    const x = ((v ?? 0) / span) * 50;
    return <span className={cls} style={{ left: `${50 + Math.min(0, x)}%`, width: `${Math.abs(x)}%` }} />;
  };
  const tone = gap.status === "missing" ? "weak" : gap.status;
  return (
    <div className="gap-row">
      <span className="pos-chip">GKP</span>
      <div style={{ display: "grid", gap: 6 }}>
        <StatusTag status={gap.status} />
        <div className="vs-bars" aria-hidden="true">
          <div className="vs-bar">
            <span>Squad</span>
            <span className="bar bar--centred">{bar(gap.squadPreventedP90, `squad--${tone}`)}</span>
            <span className="num">{signed(gap.squadPreventedP90)}</span>
          </div>
          <div className="vs-bar">
            <span>League</span>
            <span className="bar bar--centred">{bar(gap.leaguePreventedP90, "league")}</span>
            <span className="num">{signed(gap.leaguePreventedP90)}</span>
          </div>
        </div>
      </div>
      <span className="big-num" style={{ textAlign: "right" }} title="Goals prevented per 90, squad minus league">
        {gap.differenceP90 === null ? "—" : signed(gap.differenceP90)}
        <span className="sr-only"> goals prevented per 90 against the league average</span>
      </span>
      <div className="gap-row__players">
        <span className="muted">Goals prevented per 90 vs post-shot xG, not the model · </span>
        {gap.players.length
          ? gap.players.map((pl, i) => (
            <span key={pl.id}>{i > 0 && ", "}<Link to={`/players/${pl.id}`}>{pl.name}</Link></span>
          ))
          : "No goalkeeper with 900+ minutes"}
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

  const { club, positions, weakest, goalkeeper } = gaps.data;
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
          <FormationPitch positions={positions} goalkeeper={gaps.data.goalkeeper} club={club.name} />
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
            <p>Outfield: expected npG+A per 90 · GK: goals prevented per 90</p>
          </div>
          <KeeperRow gap={goalkeeper} />
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
