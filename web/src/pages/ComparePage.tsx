import { useEffect, useState, type CSSProperties } from "react";
import { Link, useSearchParams } from "react-router-dom";
import { path } from "../api/client";
import type { PlayerDetail, PlayerPage } from "../api/types";
import { Avatar, ClubBadge, GapVerdict, Panel, PositionChip } from "../components/bits";
import { SERIES, SeriesLegend, StyleRadar } from "../components/charts";
import { CloseIcon, SearchIcon, UpIcon } from "../components/icons";
import { EmptyState, ErrorState, LoadingPanel } from "../components/states";
import { MAX_COMPARE, useCompare } from "../hooks/compare";
import { useDebounced } from "../hooks/motion";
import { useApi } from "../hooks/useApi";
import { fixed, ordinal, signed, thousands } from "../lib/format";

function Picker() {
  const compare = useCompare();
  const [text, setText] = useState("");
  const [open, setOpen] = useState(false);
  const q = useDebounced(text.trim(), 200);
  const results = useApi<PlayerPage>(q.length >= 2 ? path("/players", { search: q, pageSize: 8 }) : null);

  const choose = (id: number) => {
    compare.add(id);
    setText("");
    setOpen(false);
  };

  return (
    <div className="picker field">
      <label htmlFor="compare-search">Add a player ({compare.ids.length}/{MAX_COMPARE})</label>
      <div style={{ position: "relative" }}>
        <input id="compare-search" className="input" type="search" value={text} disabled={compare.full}
          placeholder={compare.full ? "Remove a player to add another" : "Type a name, e.g. Pedri"}
          onChange={(e) => { setText(e.target.value); setOpen(true); }} onFocus={() => setOpen(true)}
          onKeyDown={(e) => { if (e.key === "Escape") setOpen(false); }}
          autoComplete="off" role="combobox" aria-expanded={open && q.length >= 2} aria-controls="compare-results"
          style={{ paddingLeft: 34 }} />
        <span style={{ position: "absolute", left: 11, top: 12, color: "var(--text-3)" }}><SearchIcon /></span>
      </div>
      {open && q.length >= 2 && (
        <ul id="compare-results" className="picker__results" role="listbox" aria-label="Matching players">
          {results.status === "loading" && <li className="muted" style={{ padding: 8 }}>Searching…</li>}
          {results.status === "error" && <li style={{ padding: 8, color: "var(--magenta)" }}>{results.error.message}</li>}
          {results.status === "ready" && results.data.data.length === 0 && <li className="muted" style={{ padding: 8 }}>No players called “{q}”.</li>}
          {results.data?.data.map((p) => (
            <li key={p.id} role="option" aria-selected="false">
              <button type="button" onClick={() => choose(p.id)} disabled={compare.has(p.id)}>
                <Avatar name={p.name} size={30} />
                <span>
                  {p.name} {compare.has(p.id) && <small>(added)</small>}
                  <br /><small>{p.club.name} · {p.position} · {p.role}</small>
                </span>
              </button>
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}

type Row = { label: string; values: (number | null)[]; format: (v: number | null) => string; better: "high" | "low" | null };

function bestIndex(row: Row): number | null {
  if (!row.better) return null;
  const vals = row.values.map((v, i) => [v, i] as const).filter(([v]) => v !== null) as [number, number][];
  if (vals.length < 2) return null;
  const sorted = [...vals].sort((a, b) => (row.better === "high" ? b[0] - a[0] : a[0] - b[0]));
  return sorted[0]![0] === sorted[1]![0] ? null : sorted[0]![1];
}

function CompareTable({ players }: { players: PlayerDetail[] }) {
  const pct = (v: number | null) => ordinal(v);
  const sections: { title: string; rows: Row[] }[] = [
    {
      title: "Output",
      rows: [
        { label: "Role rating", values: players.map((p) => p.rating), format: (v) => fixed(v, 0), better: "high" },
        { label: "npG+A per 90", values: players.map((p) => p.npgaP90), format: (v) => fixed(v), better: "high" },
        { label: "Predicted per 90", values: players.map((p) => p.prediction?.predictedP90 ?? null), format: (v) => fixed(v), better: "high" },
        { label: "Actual − predicted", values: players.map((p) => p.prediction?.gapP90 ?? null), format: (v) => signed(v), better: "high" },
        { label: "Minutes", values: players.map((p) => p.minutes), format: (v) => (v === null ? "—" : thousands(v)), better: null },
      ],
    },
    {
      title: "Style per 90 (percentile in position)",
      rows: players[0]!.style.features.map((f, i) => ({
        label: f.label + (f.lowerIsBetter ? " (lower is better)" : ""),
        values: players.map((p) => p.style.features[i]?.value ?? null),
        format: (v) => fixed(v),
        better: f.lowerIsBetter ? "low" : "high",
      })),
    },
  ];
  const styleIndex = (rowIdx: number, playerIdx: number) => players[playerIdx]!.style.features[rowIdx]?.percentile ?? null;

  return (
    <div style={{ overflowX: "auto" }}>
      <table className="compare-table">
        <caption className="sr-only">Side-by-side numbers; the best value in each row is marked “best”.</caption>
        <thead>
          <tr>
            <th scope="col">Stat</th>
            {players.map((p) => <th key={p.id} scope="col">{p.name}</th>)}
          </tr>
        </thead>
        <tbody>
          {sections.map((s) => (
            <FragmentRows key={s.title} title={s.title} cols={players.length + 1}>
              {s.rows.map((row, r) => {
                const best = bestIndex(row);
                return (
                  <tr key={row.label}>
                    <th scope="row" style={{ fontWeight: 400 }}>{row.label}</th>
                    {row.values.map((v, i) => (
                      <td key={i} className={`num ${best === i ? "best" : ""}`}>
                        {best === i && <><UpIcon size={10} /> <span className="sr-only">best: </span></>}
                        {row.format(v)}
                        {s.title.startsWith("Style") && <small className="pct muted">{pct(styleIndex(r, i))}</small>}
                      </td>
                    ))}
                  </tr>
                );
              })}
            </FragmentRows>
          ))}
        </tbody>
      </table>
    </div>
  );
}

function FragmentRows({ title, cols, children }: { title: string; cols: number; children: React.ReactNode }) {
  return (
    <>
      <tr className="section"><td colSpan={cols}>{title}</td></tr>
      {children}
    </>
  );
}

export function ComparePage() {
  const compare = useCompare();
  const [params, setParams] = useSearchParams();

  // A shared link (?ids=1,2,3) replaces the current selection once.
  useEffect(() => {
    const fromUrl = (params.get("ids") ?? "").split(",").map(Number).filter((n) => Number.isInteger(n) && n > 0);
    if (fromUrl.length) compare.set(fromUrl);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);
  useEffect(() => {
    const ids = compare.ids.join(",");
    if ((params.get("ids") ?? "") !== ids) setParams(ids ? { ids } : {}, { replace: true });
  }, [compare.ids, params, setParams]);

  const data = useApi<{ players: PlayerDetail[] }>(compare.ids.length ? `/compare?ids=${compare.ids.join(",")}` : null);
  const players = data.status === "ready" ? data.data.players : [];

  return (
    <>
      <div className="page-head">
        <div>
          <p className="eyebrow">Head to head</p>
          <h1>Compare players</h1>
          <p className="lede">Up to three players, side by side. Style percentiles are within each player's own position.</p>
        </div>
      </div>

      <Picker />

      <div className="chosen">
        {Array.from({ length: MAX_COMPARE }, (_, i) => {
          const id = compare.ids[i];
          const p = players.find((x) => x.id === id);
          if (id === undefined) return <div key={i} className="chosen__empty">Empty slot</div>;
          return (
            <Panel key={id} index={i} className="chosen__card" label={p?.name ?? "Player"}>
              <span className="swatch" style={{ "--c": SERIES[i]!.color } as CSSProperties} aria-hidden="true" />
              {p ? <Avatar name={p.name} size={42} /> : null}
              <div className="who">
                {p ? (
                  <>
                    <Link to={`/players/${p.id}`}>{p.name}</Link>
                    <small><ClubBadge club={p.club} link={false} /> <PositionChip position={p.position} /></small>
                    <small style={{ marginTop: 4 }}><GapVerdict prediction={p.prediction} compact /></small>
                  </>
                ) : <span className="muted">Loading…</span>}
              </div>
              <button type="button" className="icon-button" onClick={() => compare.remove(id)}
                aria-label={`Remove ${p?.name ?? "player"} from the comparison`}>
                <CloseIcon />
              </button>
            </Panel>
          );
        })}
      </div>

      {compare.ids.length === 0 && (
        <Panel>
          <EmptyState title="Nobody picked yet">
            Search above, or use “Compare” on a player's page or in the player list.
          </EmptyState>
        </Panel>
      )}
      {data.status === "loading" && compare.ids.length > 0 && <LoadingPanel height={360} label="Loading comparison" />}
      {data.status === "error" && (
        <Panel>
          <ErrorState error={data.error} onRetry={data.retry} />
          <div style={{ textAlign: "center" }}>
            <button type="button" className="button button--ghost" onClick={() => compare.set([])}>Clear the comparison</button>
          </div>
        </Panel>
      )}
      {data.status === "ready" && players.length > 0 && (
        <div className="grid-2">
          <Panel index={3} label="Style radar">
            <div className="panel__title"><h2>Playing style</h2><p>Percentile in position</p></div>
            <StyleRadar series={players.map((p) => ({ name: p.name, features: p.style.features }))}
              label={`Playing-style radar comparing ${players.map((p) => p.name).join(", ")}. The table gives every value.`} />
            <SeriesLegend names={players.map((p) => p.name)} />
          </Panel>
          <Panel index={4} label="Numbers">
            <div className="panel__title"><h2>Numbers</h2></div>
            <CompareTable players={players} />
          </Panel>
        </div>
      )}
    </>
  );
}
