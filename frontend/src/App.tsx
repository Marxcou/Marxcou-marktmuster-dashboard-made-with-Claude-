import { Navigate, Route, Routes } from "react-router-dom";
import { Layout } from "./components/Layout";
import { useAuth } from "./lib/auth";
import { ChartPage } from "./pages/ChartPage";
import { News } from "./pages/News";
import { Login } from "./pages/Login";
import { Placeholder } from "./pages/Placeholder";
import { Sources } from "./pages/Sources";
import { Watchlist } from "./pages/Watchlist";

function RequireAuth({ children }: { children: JSX.Element }) {
  const { me, loading } = useAuth();
  if (loading) return <p className="text-slate-400">Lade …</p>;
  return me ? children : <Navigate to="/login" replace />;
}

export function App() {
  return (
    <Routes>
      <Route element={<Layout />}>
        <Route path="login" element={<Login />} />
        <Route index element={<RequireAuth><Watchlist /></RequireAuth>} />
        <Route path="instrument/:id" element={<RequireAuth><ChartPage /></RequireAuth>} />
        <Route path="nachrichten" element={<RequireAuth><News /></RequireAuth>} />
        <Route path="quellen" element={<RequireAuth><Sources /></RequireAuth>} />
        <Route path="*" element={<Placeholder title="Seite nicht gefunden" note="Diese Seite existiert nicht." />} />
      </Route>
    </Routes>
  );
}
