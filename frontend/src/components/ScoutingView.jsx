import { useState } from "react";
import { useApi, POSITION_NAMES, AGE_OPTIONS, fmt, rolesFor } from "../api.js";
import RatingChip from "./RatingChip.jsx";

export default function ScoutingView({ onOpen }) {
  const [position, setPosition] = useState("MID");
  const [role, setRole] = useState("");
  const [league, setLeague] = useState("");
  const [maxAge, setMaxAge] = useState("");
  const leagues = useApi("/leagues");
  const roles = useApi("/roles");
  const targets = useApi(
    "/scouting/targets",
    { position, role, league, max_age: maxAge, limit: 10 },
    [position, role, league, maxAge]
  );
  const perf = useApi("/scouting/performance", { league, limit: 8 }, [league]);

  return (
    <div className="scouting">
      <section className="block">
        <h2 className="h2">Players worth a bid</h2>
        <p className="lede">
          The highest-rated players, each judged in their own role, outside Europe's 17 biggest
          buying clubs (the Premier League's
          Big Six, Real, Barça, Atlético, Bayern, Dortmund, Leverkusen, Inter, Milan, Juventus,
          Napoli and PSG), the usual pool for a step-up transfer.
        </p>
        <div className="filters scout-filters">
          <label className="field">
            <span>League</span>
            <select value={league} onChange={(e) => setLeague(e.target.value)}>
              <option value="">All five leagues</option>
              {(leagues.data ?? []).map((l) => (
                <option key={l}>{l}</option>
              ))}
            </select>
          </label>
          <label className="field">
            <span>Age</span>
            <select value={maxAge} onChange={(e) => setMaxAge(e.target.value)}>
              {AGE_OPTIONS.map((o) => (
                <option key={o.value} value={o.value}>
                  {o.label}
                </option>
              ))}
            </select>
          </label>
          <label className="field">
            <span>Role</span>
            <select value={role} onChange={(e) => setRole(e.target.value)}>
              <option value="">Any {POSITION_NAMES[position].toLowerCase()} role</option>
              {rolesFor(roles.data, position).map((r) => (
                <option key={r}>{r}</option>
              ))}
            </select>
          </label>
        </div>
        <div className="seg" role="radiogroup" aria-label="Position">
          {Object.entries(POSITION_NAMES).map(([k, v]) => (
            <button
              key={k}
              role="radio"
              aria-checked={position === k}
              className="seg-btn"
              onClick={() => {
                setPosition(k);
                setRole("");
              }}
            >
              {v}s
            </button>
          ))}
        </div>
        {targets.data && targets.data.length === 0 && (
          <p className="empty">No qualified players match. Try a wider age range or another league.</p>
        )}
        <ol className="targets">
          {(targets.data ?? []).map((p) => (
            <li key={p.id}>
              <button className="link name" onClick={() => onOpen(p.id)}>
                {p.name}
              </button>
              <span className="club">
                {p.club}, {p.league}. Age {p.age ?? "–"}
              </span>
              <span className="style">{p.role}</span>
              <RatingChip value={p.rating} />
            </li>
          ))}
        </ol>
      </section>

      <section className="block">
        <h2 className="h2">Output vs underlying play</h2>
        <p className="lede">
          Non-penalty goals plus assists per 90 minus what the model expects from shots, touches in the box,
          key passes and carries. A big negative gap can mean bad luck or poor finishing, so a player may be
          cheaper than his underlying numbers. A big positive gap may not last.
        </p>
        <div className="gaps">
          <GapList title="Below expected" rows={perf.data?.underperforming} onOpen={onOpen} />
          <GapList title="Above expected" rows={perf.data?.overperforming} onOpen={onOpen} />
        </div>
      </section>
    </div>
  );
}

function GapList({ title, rows = [], onOpen }) {
  const max = Math.max(0.01, ...rows.map((r) => Math.abs(r.gap)));
  return (
    <div>
      <h3 className="sub">{title}</h3>
      <ul className="gap-list">
        {rows.map((r) => (
          <li key={r.id} title={`Actual ${fmt(r.ga90)} vs expected ${fmt(r.xga90)} per 90`}>
            <button className="link name" onClick={() => onOpen(r.id)}>
              {r.name}
            </button>
            <span className="club">
              {r.club}, {r.league}
            </span>
            <span className="gap-bar" aria-hidden="true">
              <span
                className={`gap-fill ${r.gap < 0 ? "neg" : "pos"}`}
                style={{ width: `${(Math.abs(r.gap) / max) * 100}%` }}
              />
            </span>
            <span className="gap-val">
              {r.gap < 0 ? "−" : "+"}
              {fmt(Math.abs(r.gap))}
            </span>
          </li>
        ))}
      </ul>
    </div>
  );
}
