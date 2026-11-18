import { useMemo, useState } from "react";
import type { Club } from "../api/types";
import { Panel } from "../components/bits";
import { SearchIcon } from "../components/icons";
import { EmptyState, ErrorState, LoadingPanel } from "../components/states";
import { useApi } from "../hooks/useApi";
import { LEAGUES } from "../lib/format";
import { foldName } from "../lib/text";

export function ClubsPage() {
  const clubs = useApi<{ data: Club[] }>("/clubs");
  const [query, setQuery] = useState("");
  const [league, setLeague] = useState("");

  const groups = useMemo(() => {
    const q = foldName(query);
    const shown = (clubs.data?.data ?? []).filter(
      (c) => (!league || c.league === league) && (!q || foldName(c.name).includes(q)),
    );
    return LEAGUES.map((l) => ({ league: l, clubs: shown.filter((c) => c.league === l) })).filter((g) => g.clubs.length);
  }, [clubs.data, query, league]);

  return (
    <>
      <div className="page-head">
        <div>
          <p className="eyebrow">Squad gaps</p>
          <h1>Clubs</h1>
          <p className="lede">
            Pick a club to see where its squad's expected output is weakest compared with the rest of its league.
          </p>
        </div>
      </div>
      <div className="filters" style={{ gridTemplateColumns: "minmax(200px, 2fr) minmax(160px, 1fr)" }}>
        <div className="field field--search">
          <label htmlFor="club-search">Club</label>
          <div style={{ position: "relative" }}>
            <input id="club-search" className="input" type="search" value={query} placeholder="Search clubs"
              onChange={(e) => setQuery(e.target.value)} style={{ paddingLeft: 34 }} autoComplete="off" />
            <span style={{ position: "absolute", left: 11, top: 12, color: "var(--text-3)" }}><SearchIcon /></span>
          </div>
        </div>
        <div className="field">
          <label htmlFor="club-league">League</label>
          <select id="club-league" className="select" value={league} onChange={(e) => setLeague(e.target.value)}>
            <option value="">All leagues</option>
            {LEAGUES.map((l) => <option key={l} value={l}>{l}</option>)}
          </select>
        </div>
      </div>

      {clubs.status === "loading" && <div className="club-grid">{Array.from({ length: 8 }, (_, i) => <LoadingPanel key={i} height={50} label="Loading clubs" />)}</div>}
      {clubs.status === "error" && <Panel><ErrorState error={clubs.error} onRetry={clubs.retry} /></Panel>}
      {clubs.status === "ready" && groups.length === 0 && (
        <Panel><EmptyState title="No clubs match">Nothing called “{query}”{league && ` in ${league}`}.</EmptyState></Panel>
      )}
      {groups.map((g) => (
        <section key={g.league} className="league-block" aria-labelledby={`league-${g.league}`}>
          <h2 id={`league-${g.league}`}>{g.league}</h2>
          <div className="club-grid">
            {g.clubs.map((c, i) => (
              <Panel key={c.id} index={i} to={`/clubs/${c.id}`} className="club-card" label={`${c.name} squad gaps`}>
                <span className="club-badge">{c.league}</span>
                <h3>{c.name}</h3>
                <p><span className="num">{c.players}</span> players · <span className="num">{c.playersWithPrediction}</span> modelled</p>
              </Panel>
            ))}
          </div>
        </section>
      ))}
    </>
  );
}
