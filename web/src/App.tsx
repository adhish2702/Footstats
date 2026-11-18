import { Suspense, lazy } from "react";
import { Link, Route, Routes } from "react-router-dom";
import { Panel } from "./components/bits";
import { Layout } from "./components/Layout";
import { EmptyState, LoadingPanel } from "./components/states";
import { ClubGapsPage } from "./pages/ClubGapsPage";
import { ClubsPage } from "./pages/ClubsPage";
import { InsightsPage } from "./pages/InsightsPage";
import { PlayersPage } from "./pages/PlayersPage";

// The profile and compare pages carry the chart library, so they load on demand.
const PlayerPage = lazy(() => import("./pages/PlayerPage").then((m) => ({ default: m.PlayerPage })));
const ComparePage = lazy(() => import("./pages/ComparePage").then((m) => ({ default: m.ComparePage })));

const page = (el: React.ReactNode) => <Suspense fallback={<LoadingPanel height={360} />}>{el}</Suspense>;

function NotFound() {
  return (
    <Panel>
      <EmptyState title="Page not found" action={<Link className="button" to="/">Back to players</Link>}>
        That address doesn't match anything here.
      </EmptyState>
    </Panel>
  );
}

export function App() {
  return (
    <Routes>
      <Route element={<Layout />}>
        <Route index element={<PlayersPage />} />
        <Route path="players/:id" element={page(<PlayerPage />)} />
        <Route path="clubs" element={<ClubsPage />} />
        <Route path="clubs/:id" element={<ClubGapsPage />} />
        <Route path="compare" element={page(<ComparePage />)} />
        <Route path="insights" element={<InsightsPage />} />
        <Route path="*" element={<NotFound />} />
      </Route>
    </Routes>
  );
}
