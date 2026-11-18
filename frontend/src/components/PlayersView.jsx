import { useEffect, useMemo, useState } from "react";
import { useApi, POSITION_NAMES, AGE_OPTIONS, rolesFor } from "../api.js";
import PlayerDetail from "./PlayerDetail.jsx";
import RatingChip from "./RatingChip.jsx";

export default function PlayersView({ selected, onSelect }) {
  const [q, setQ] = useState("");
  const [position, setPosition] = useState("");
  const [role, setRole] = useState("");
  const [club, setClub] = useState("");
  const [league, setLeague] = useState("");
  const [maxAge, setMaxAge] = useState("");
  const [qualifiedOnly, setQualifiedOnly] = useState(true);
  const [sort, setSort] = useState("rating");

  const leagues = useApi("/leagues");
  const roles = useApi("/roles");
  const clubs = useApi("/clubs", { league }, [league]);
  const players = useApi(
    "/players",
    { position, role, club, league, max_age: maxAge, qualified_only: qualifiedOnly, sort },
    [position, role, club, league, maxAge, qualifiedOnly, sort]
  );

  // Client-side name filter keeps typing instant.
  const rows = useMemo(() => {
    const list = players.data ?? [];
    const needle = q.trim().toLowerCase();
    return needle ? list.filter((p) => p.name.toLowerCase().includes(needle)) : list;
  }, [players.data, q]);

  // Pick the top player on first load so the detail panel is never empty.
  useEffect(() => {
    if (selected === null && rows.length) onSelect(rows[0].id);
  }, [rows, selected, onSelect]);

  // On narrow screens the detail panel sits below the list, so bring it into view.
  const choose = (id) => {
    onSelect(id);
    if (window.matchMedia("(max-width: 900px)").matches) {
      requestAnimationFrame(() =>
        document.querySelector(".detail")?.scrollIntoView({ behavior: "smooth", block: "start" })
      );
    }
  };

  return (
    <div className="players">
      <section className="list" aria-label="Player list">
        <div className="filters">
          <label className="field grow">
            <span>Search</span>
            <input
              type="search"
              value={q}
              placeholder="Player name"
              onChange={(e) => setQ(e.target.value)}
            />
          </label>
          <label className="field">
            <span>Position</span>
            <select
              value={position}
              onChange={(e) => {
                setPosition(e.target.value);
                setRole("");
              }}
            >
              <option value="">All</option>
              {Object.entries(POSITION_NAMES).map(([k, v]) => (
                <option key={k} value={k}>
                  {v}s
                </option>
              ))}
            </select>
          </label>
          <label className="field">
            <span>Role</span>
            <select value={role} onChange={(e) => setRole(e.target.value)}>
              <option value="">All roles</option>
              {rolesFor(roles.data, position).map((r) => (
                <option key={r}>{r}</option>
              ))}
            </select>
          </label>
          <label className="field">
            <span>League</span>
            <select
              value={league}
              onChange={(e) => {
                setLeague(e.target.value);
                setClub("");
              }}
            >
              <option value="">All five leagues</option>
              {(leagues.data ?? []).map((l) => (
                <option key={l}>{l}</option>
              ))}
            </select>
          </label>
          <label className="field">
            <span>Club</span>
            <select value={club} onChange={(e) => setClub(e.target.value)}>
              <option value="">All clubs</option>
              {(clubs.data ?? []).map((c) => (
                <option key={c}>{c}</option>
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
            <span>Sort by</span>
            <select value={sort} onChange={(e) => setSort(e.target.value)}>
              <option value="rating">Rating</option>
              <option value="goals">Goals</option>
              <option value="assists">Assists</option>
              <option value="minutes">Minutes</option>
              <option value="age">Youngest first</option>
              <option value="name">Name</option>
            </select>
          </label>
          <label className="check">
            <input
              type="checkbox"
              checked={qualifiedOnly}
              onChange={(e) => setQualifiedOnly(e.target.checked)}
            />
            900+ minutes only
          </label>
        </div>

        <p className="count" aria-live="polite">
          {players.loading ? "Loading players…" : `${rows.length} ${rows.length === 1 ? "player" : "players"}`}
        </p>

        <div className="table-wrap">
          <table className="ptable">
            <thead>
              <tr>
                <th scope="col">Player</th>
                <th scope="col">Pos</th>
                <th scope="col" className="num col-age">Age</th>
                <th scope="col" className="num col-mins">Mins</th>
                <th scope="col" className="num">G</th>
                <th scope="col" className="num">A</th>
                <th scope="col" className="num">Rating</th>
              </tr>
            </thead>
            <tbody>
              {rows.map((p) => (
                <tr
                  key={p.id}
                  className={p.id === selected ? "is-selected" : undefined}
                  onClick={() => choose(p.id)}
                >
                  <td>
                    <button
                      className="row-link"
                      onClick={(e) => {
                        e.stopPropagation();
                        choose(p.id);
                      }}
                    >
                      {p.name}
                    </button>
                    <span className="club">
                      {p.role ? `${p.role} · ` : ""}
                      {p.club}, {p.league}
                    </span>
                  </td>
                  <td>{p.position}</td>
                  <td className="num col-age">{p.age ?? "–"}</td>
                  <td className="num col-mins">{p.minutes.toLocaleString()}</td>
                  <td className="num">{p.goals}</td>
                  <td className="num">{p.assists}</td>
                  <td className="num">
                    <RatingChip value={p.rating} muted={!p.qualified} />
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
          {!players.loading && rows.length === 0 && (
            <p className="empty">No players match. Clear the search or widen the role, league, club or age filter.</p>
          )}
        </div>
      </section>

      <aside className="detail" aria-label="Player details">
        {selected !== null ? (
          <PlayerDetail id={selected} onSelect={onSelect} />
        ) : (
          <p className="empty">Pick a player to see their rating breakdown.</p>
        )}
      </aside>
    </div>
  );
}
