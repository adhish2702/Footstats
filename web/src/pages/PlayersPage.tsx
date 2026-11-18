import { useEffect, useState } from "react";
import { Link, useSearchParams } from "react-router-dom";
import { path } from "../api/client";
import type { Club, PlayerPage } from "../api/types";
import { Avatar, ClubBadge, Panel, PositionChip, VsExpected } from "../components/bits";
import { PlusIcon, SearchIcon } from "../components/icons";
import { EmptyState, ErrorState, LoadingRows } from "../components/states";
import { useCompare } from "../hooks/compare";
import { useDebounced } from "../hooks/motion";
import { useApi } from "../hooks/useApi";
import { LEAGUES, POSITIONS, POSITION_NAMES, fixed, thousands } from "../lib/format";

const SORTS = [
  { value: "-rating", label: "Rating, high to low" },
  { value: "-npga", label: "G+A per 90, high to low" },
  { value: "-predicted", label: "Predicted, high to low" },
  { value: "-gap", label: "Over-performing most" },
  { value: "gap", label: "Under-performing most" },
  { value: "-prevented", label: "Goals prevented (keepers)" },
  { value: "-minutes", label: "Minutes, most first" },
  { value: "age", label: "Age, youngest first" },
  { value: "name", label: "Name, A to Z" },
];
const PAGE_SIZE = 20;

export function PlayersPage() {
  const [params, setParams] = useSearchParams();
  const search = params.get("search") ?? "";
  const league = params.get("league") ?? "";
  const position = params.get("position") ?? "";
  const club = params.get("club") ?? "";
  const sort = params.get("sort") ?? "-rating";
  const page = Math.max(1, Number(params.get("page") ?? 1) || 1);

  // The search box updates as you type; the request waits for a pause.
  const [text, setText] = useState(search);
  const debounced = useDebounced(text.trim(), 250);
  useEffect(() => setText(search), [search]);

  const update = (changes: Record<string, string>, resetPage = true) => {
    const next = new URLSearchParams(params);
    for (const [k, v] of Object.entries(changes)) {
      if (v) next.set(k, v);
      else next.delete(k);
    }
    if (resetPage) next.delete("page");
    setParams(next, { replace: true });
  };

  useEffect(() => {
    if (debounced !== search) update({ search: debounced });
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [debounced]);

  const clubs = useApi<{ data: Club[] }>(path("/clubs", { league }));
  const players = useApi<PlayerPage>(
    path("/players", { search, league, position, club, sort: sort === "-rating" ? undefined : sort, page: page > 1 ? page : undefined, pageSize: PAGE_SIZE }),
  );
  const compare = useCompare();
  const filtered = Boolean(search || league || position || club);

  return (
    <>
      <div className="page-head">
        <div>
          <p className="eyebrow">2024/25 · Europe's top five leagues</p>
          <h1>Player search</h1>
          <p className="lede">
            Every player's role rating and, for outfield players with 900+ minutes, the non-penalty goals + assists per 90
            the model expects from how they play.
          </p>
        </div>
      </div>

      <form className="filters" role="search" onSubmit={(e) => e.preventDefault()}>
        <div className="field field--search">
          <label htmlFor="search">Name</label>
          <div style={{ position: "relative" }}>
            <input id="search" className="input" type="search" value={text} placeholder="Search players, e.g. Ødegaard"
              onChange={(e) => setText(e.target.value)} maxLength={50} autoComplete="off" style={{ paddingLeft: 34 }} />
            <span style={{ position: "absolute", left: 11, top: 12, color: "var(--text-3)" }}><SearchIcon /></span>
          </div>
        </div>
        <div className="field">
          <label htmlFor="league">League</label>
          <select id="league" className="select" value={league} onChange={(e) => update({ league: e.target.value, club: "" })}>
            <option value="">All leagues</option>
            {LEAGUES.map((l) => <option key={l} value={l}>{l}</option>)}
          </select>
        </div>
        <div className="field">
          <label htmlFor="club">Club</label>
          <select id="club" className="select" value={club} onChange={(e) => update({ club: e.target.value })}
            disabled={clubs.status !== "ready"}>
            <option value="">All clubs</option>
            {clubs.data?.data.map((c) => <option key={c.id} value={c.id}>{c.name}</option>)}
          </select>
        </div>
        <div className="field">
          <label htmlFor="position">Position</label>
          <select id="position" className="select" value={position} onChange={(e) => update({ position: e.target.value })}>
            <option value="">All positions</option>
            {POSITIONS.map((p) => <option key={p} value={p}>{POSITION_NAMES[p]}</option>)}
          </select>
        </div>
        <div className="field">
          <label htmlFor="sort">Sort</label>
          <select id="sort" className="select" value={sort} onChange={(e) => update({ sort: e.target.value })}>
            {SORTS.map((s) => <option key={s.value} value={s.value}>{s.label}</option>)}
          </select>
        </div>
      </form>

      <Panel className="table-wrap" label="Players">
        {players.status === "loading" && <LoadingRows label="Loading players" />}
        {players.status === "error" && <ErrorState error={players.error} onRetry={players.retry} />}
        {players.status === "ready" && players.data.total === 0 && (
          <EmptyState title="No players match" action={filtered && (
            <button type="button" className="button button--ghost" onClick={() => { setText(""); setParams({}, { replace: true }); }}>
              Clear filters
            </button>
          )}>
            {search ? <>Nobody called “{search}” with these filters.</> : "Try a different league, club or position."}
          </EmptyState>
        )}
        {players.status === "ready" && players.data.total > 0 && (
          <div className="scroll-x">
          <table className="player-table">
            <caption className="sr-only">
              Players, page {players.data.page} of {players.data.totalPages}, sorted by {SORTS.find((s) => s.value === sort)?.label}
            </caption>
            <thead>
              <tr>
                <th scope="col">Player</th>
                <th scope="col">Club</th>
                <th scope="col">Pos</th>
                <th scope="col" className="r">Age</th>
                <th scope="col" className="r">Min</th>
                <th scope="col" className="r">Rating</th>
                <th scope="col" className="r" title="Non-penalty goals + assists per 90">G+A/90</th>
                <th scope="col" className="r" title="Predicted non-penalty goals + assists per 90">Pred.</th>
                <th scope="col" title="Outfield: actual minus predicted G+A per 90. Goalkeepers: goals prevented per 90 against post-shot xG.">Vs expected</th>
                <th scope="col"><span className="sr-only">Compare</span></th>
              </tr>
            </thead>
            <tbody>
              {players.data.data.map((p, i) => (
                <tr key={p.id} className="enter" style={{ "--i": i } as React.CSSProperties}>
                  <td className="cell-player">
                    <div className="player-cell">
                      <Avatar name={p.name} size={36} />
                      <div style={{ minWidth: 0 }}>
                        <Link to={`/players/${p.id}`}>{p.name}</Link>
                        <small>{p.role}</small>
                      </div>
                    </div>
                  </td>
                  <td data-label="Club"><ClubBadge club={p.club} /></td>
                  <td data-label="Pos"><PositionChip position={p.position} /></td>
                  <td data-label="Age" className="r num">{p.age ?? "—"}</td>
                  <td data-label="Min" className="r num">{thousands(p.minutes)}</td>
                  <td data-label="Rating" className="r"><span className="big-num">{p.rating.toFixed(0)}</span></td>
                  <td data-label="G+A/90" className="r num">{fixed(p.npgaP90)}</td>
                  <td data-label="Pred." className="r num">{fixed(p.prediction?.predictedP90)}</td>
                  <td data-label="Vs expected"><VsExpected player={p} compact /></td>
                  <td className="cell-hide-sm">
                    <button type="button" className="icon-button" onClick={() => compare.add(p.id)}
                      disabled={compare.has(p.id) || compare.full}
                      aria-label={compare.has(p.id) ? `${p.name} is in the comparison` : `Add ${p.name} to the comparison`}
                      title={compare.has(p.id) ? "In the comparison" : compare.full ? "Comparison is full (3)" : "Add to comparison"}>
                      <PlusIcon />
                    </button>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
          </div>
        )}
      </Panel>

      {players.status === "ready" && players.data.total > 0 && (
        <nav className="pagination" aria-label="Pages">
          <span>
            <span className="num">{thousands(players.data.total)}</span> players · page{" "}
            <span className="num">{players.data.page}</span> of <span className="num">{players.data.totalPages}</span>
          </span>
          <span className="pagination__buttons">
            <button type="button" className="button button--ghost" disabled={page <= 1}
              onClick={() => update({ page: String(page - 1) }, false)}>Previous</button>
            <button type="button" className="button button--ghost" disabled={page >= players.data.totalPages}
              onClick={() => update({ page: String(page + 1) }, false)}>Next</button>
          </span>
        </nav>
      )}
    </>
  );
}
