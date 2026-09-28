import { Route, Routes } from "react-router-dom";
import { Layout } from "./components/Layout";
import { Placeholder } from "./pages/Placeholder";

// Routen-Gerüst. Workstream 1C ersetzt die Platzhalter durch Login, Watchlist, Suche und Chart-Seite.
export function App() {
  return (
    <Routes>
      <Route element={<Layout />}>
        <Route index element={<Placeholder title="Watchlist" note="Kommt mit Workstream 1C." />} />
        <Route path="quellen" element={<Placeholder title="Quellen" note="Kommt mit Phase 2D." />} />
        <Route path="*" element={<Placeholder title="Seite nicht gefunden" note="Diese Seite existiert nicht." />} />
      </Route>
    </Routes>
  );
}
