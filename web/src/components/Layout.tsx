import { useEffect, useState } from "react";
import { NavLink, Outlet, useLocation } from "react-router-dom";
import type { ModelInfo } from "../api/types";
import { useCompare } from "../hooks/compare";
import { useApi } from "../hooks/useApi";
import { fixed } from "../lib/format";
import { MoonIcon, SunIcon } from "./icons";
import { PitchBackground } from "./PitchBackground";

type Theme = "dark" | "light";

function ThemeToggle() {
  const [theme, setTheme] = useState<Theme>(() =>
    document.documentElement.dataset.theme === "light" ? "light" : "dark",
  );
  useEffect(() => {
    document.documentElement.dataset.theme = theme;
    document.querySelector('meta[name="theme-color"]')?.setAttribute("content", theme === "light" ? "#EDF2EF" : "#0A0F0D");
    try {
      localStorage.setItem("footstats-theme", theme);
    } catch {
      // storage blocked: the choice lasts for this visit only
    }
  }, [theme]);
  const next = theme === "dark" ? "light" : "dark";
  return (
    <button type="button" className="icon-button" onClick={() => setTheme(next)}
      aria-label={`Switch to ${next} theme`} title={`Switch to ${next} theme`}>
      {theme === "dark" ? <SunIcon /> : <MoonIcon />}
    </button>
  );
}

function Logo() {
  return (
    <svg width="28" height="28" viewBox="0 0 32 32" aria-hidden="true">
      <path d="M3 3h26v26H3zM16 3v26M3 16h26" fill="none" stroke="var(--green)" strokeWidth="1.4" opacity=".6" />
      <circle cx="16" cy="16" r="5.5" fill="none" stroke="var(--green)" strokeWidth="2" />
      <circle cx="16" cy="16" r="1.8" fill="var(--cyan)" />
    </svg>
  );
}

export function Layout() {
  const { ids } = useCompare();
  const model = useApi<ModelInfo>("/model");
  const location = useLocation();

  // New page: start at the top and move focus to the content for keyboard users.
  useEffect(() => {
    window.scrollTo(0, 0);
  }, [location.pathname]);

  // The free API host sleeps when idle; if the first answer is slow, say why.
  const [slow, setSlow] = useState(false);
  useEffect(() => {
    if (model.status !== "loading") {
      setSlow(false);
      return;
    }
    const timer = setTimeout(() => setSlow(true), 3500);
    return () => clearTimeout(timer);
  }, [model.status]);

  return (
    <>
      <a href="#main" className="skip-link">Skip to content</a>
      <PitchBackground />
      <header className="topbar">
        <div className="topbar__inner">
          <NavLink to="/" className="brand" aria-label="FootStats home">
            <Logo />
            <span><b>FOOT</b>STATS</span>
          </NavLink>
          <nav className="nav" aria-label="Main">
            <NavLink to="/" end>Players</NavLink>
            <NavLink to="/clubs">Squad gaps</NavLink>
            <NavLink to="/insights">Over / under</NavLink>
            <NavLink to="/compare">
              Compare
              {ids.length > 0 && <span className="count num" aria-label={`${ids.length} selected`}>{ids.length}</span>}
            </NavLink>
          </nav>
          <div className="theme-slot"><ThemeToggle /></div>
        </div>
      </header>
      {slow && (
        <p className="wake-banner" role="status">
          Waking up the API. Free hosting sleeps when nobody has visited for a while, so the first load can take up to a minute.
        </p>
      )}
      <main id="main" tabIndex={-1}>
        <Outlet />
      </main>
      <footer className="footer">
        <p>
          <strong>Data:</strong> FBref, Europe's top five leagues, 2024/25. Club names are shown as text only; no logos,
          crests, kits or player photos are used.
        </p>
        {model.status === "ready" && (
          <p>
            <strong>Model:</strong> {model.data.modelName}, held-out error {fixed(model.data.metrics.testMae, 3)} vs{" "}
            {fixed(model.data.metrics.baselineMae, 3)} baseline, R² {fixed(model.data.metrics.testR2, 2)} on{" "}
            {model.data.testPlayers} players.
          </p>
        )}
      </footer>
    </>
  );
}
