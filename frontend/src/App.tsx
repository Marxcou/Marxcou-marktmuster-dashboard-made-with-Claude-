import { Navigate, Route, Routes } from "react-router-dom";
import { Layout } from "./components/Layout";
import { useAuth } from "./lib/auth";
import { ChartPage } from "./pages/ChartPage";
import { News } from "./pages/News";
import { Account } from "./pages/Account";
import { AdminUsers } from "./pages/AdminUsers";
import { Login } from "./pages/Login";
import { Placeholder } from "./pages/Placeholder";
import { Sources } from "./pages/Sources";
import { Watchlist } from "./pages/Watchlist";

function RequireAuth({ children }: { children: JSX.Element }) {
  const { me, loading } = useAuth();
  if (loading) return <p className="text-slate-400">Lade …</p>;
  if (!me) return <Navigate to="/login" replace />;
  // Einmalpasswort: bis zum Passwortwechsel ist nur die Kontoseite erreichbar.
  if (me.user.must_change_password) return <Account forced />;
  return children;
}

function RequireAdmin({ children }: { children: JSX.Element }) {
  const { me } = useAuth();
  if (me && me.user.role !== "admin") return <Placeholder title="Kein Zugriff" note="Diese Seite ist nur für Administratoren." />;
  return children;
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
        <Route path="konto" element={<RequireAuth><Account /></RequireAuth>} />
        <Route path="admin/benutzer" element={<RequireAuth><RequireAdmin><AdminUsers /></RequireAdmin></RequireAuth>} />
        <Route path="*" element={<Placeholder title="Seite nicht gefunden" note="Diese Seite existiert nicht." />} />
      </Route>
    </Routes>
  );
}
