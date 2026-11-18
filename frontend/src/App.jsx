import { useState } from "react";
import { useApi } from "./api.js";
import PlayersView from "./components/PlayersView.jsx";
import ScoutingView from "./components/ScoutingView.jsx";
import ModelView from "./components/ModelView.jsx";

const TABS = [
  { id: "players", label: "Players" },
  { id: "scouting", label: "Scouting" },
  { id: "model", label: "How it works" },
];

export default function App() {
  const [tab, setTab] = useState("players");
  const [selected, setSelected] = useState(null);
  const overview = useApi("/overview");

  const openPlayer = (id) => {
    setSelected(id);
    setTab("players");
    window.scrollTo({ top: 0, behavior: "smooth" });
  };

  return (
    <>
      <header className="pitch">
        <div className="pitch-inner">
          <h1 className="wordmark">FootStats</h1>
          <p className="strap">
            {overview.data
              ? `Every player in Europe's top five leagues, ${overview.data.season}: ${overview.data.players.toLocaleString()} players across ${overview.data.clubs} clubs, each rated in their own role.`
              : "Player ratings, tactical roles and scouting for Europe's top five leagues."}
          </p>
          <nav className="tabs" aria-label="Sections">
            {TABS.map((t) => (
              <button
                key={t.id}
                className="tab"
                aria-current={tab === t.id ? "page" : undefined}
                onClick={() => setTab(t.id)}
              >
                {t.label}
              </button>
            ))}
          </nav>
        </div>
      </header>

      <main className="page">
        {overview.error && (
          <p className="notice" role="alert">
            Can't reach the FootStats API. Start it with <code>uvicorn app:app --port 8000</code> in
            the pipeline folder, then reload this page.
          </p>
        )}
        {tab === "players" && <PlayersView selected={selected} onSelect={setSelected} />}
        {tab === "scouting" && <ScoutingView onOpen={openPlayer} />}
        {tab === "model" && <ModelView onOpen={openPlayer} />}
      </main>

      <footer className="foot">
        Data: FBref player statistics for the 2024/25 Premier League, La Liga, Serie A, Bundesliga
        and Ligue 1. Ratings compare each player with others in the same role across all five
        leagues who played 900+ minutes, with no adjustment for league strength.
      </footer>
    </>
  );
}
