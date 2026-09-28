import { useQuery } from "@tanstack/react-query";
import { NavLink, Outlet } from "react-router-dom";
import { api, type Meta } from "../lib/api";
import { useAuth } from "../lib/auth";

// Rückfalltext, falls /api/meta nicht erreichbar ist: der Hinweis muss trotzdem sichtbar sein (Grundregel 5).
export const DISCLAIMER_FALLBACK =
  "Dieses Dashboard stellt keine Anlageberatung dar. Alle Analysen sind automatisiert, können fehlerhaft sein und dienen ausschließlich der Information.";

export function Disclaimer({ text }: { text?: string }) {
  return (
    <div role="note" data-testid="disclaimer" className="border-t border-amber-700/40 bg-amber-950/40 px-4 py-2 text-sm text-amber-200">
      {text ?? DISCLAIMER_FALLBACK}
    </div>
  );
}

export function Layout() {
  const { me, logout } = useAuth();
  const { data: meta } = useQuery({ queryKey: ["meta"], queryFn: () => api<Meta>("/meta"), retry: false });
  return (
    <div className="flex min-h-screen flex-col bg-slate-950 text-slate-100">
      {meta?.demo_mode && (
        <div role="alert" data-testid="demo-banner" className="bg-fuchsia-800 px-4 py-2 text-center text-sm font-semibold">
          DEMO-MODUS: Beispieldaten, keine echten Marktdaten
        </div>
      )}
      <header className="flex items-center gap-6 border-b border-slate-800 px-4 py-3">
        <span className="font-semibold">Marktmuster-Dashboard</span>
        <nav className="flex gap-4 text-sm text-slate-300">
          <NavLink to="/">Watchlist</NavLink>
          <NavLink to="/nachrichten">Nachrichten</NavLink>
          <NavLink to="/quellen">Quellen</NavLink>
        </nav>
        {me && (
          <div className="ml-auto flex items-center gap-3 text-sm text-slate-300">
            <span>{me.user.display_name}</span>
            <button type="button" onClick={() => void logout()} className="underline">Abmelden</button>
          </div>
        )}
      </header>
      <Disclaimer text={meta?.disclaimer} />
      <main className="flex-1 p-4"><Outlet /></main>
      <Disclaimer text={meta?.disclaimer} />
    </div>
  );
}
