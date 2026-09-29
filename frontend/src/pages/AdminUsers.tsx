import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useState, type FormEvent } from "react";
import { api, ApiError, type AdminUser } from "../lib/api";
import { useAuth } from "../lib/auth";
import { formatDateTime } from "../lib/format";

interface Shown { email: string; password: string }

function errText(err: unknown): string {
  return err instanceof ApiError && err.detail ? err.detail : "Aktion fehlgeschlagen.";
}

export function AdminUsers() {
  const qc = useQueryClient();
  const { me } = useAuth();
  const q = useQuery({ queryKey: ["admin-users"], queryFn: () => api<AdminUser[]>("/users") });
  const [shown, setShown] = useState<Shown | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [form, setForm] = useState({ email: "", display_name: "", role: "user" });
  const refresh = () => qc.invalidateQueries({ queryKey: ["admin-users"] });

  const create = useMutation({
    mutationFn: () => api<AdminUser & { temporary_password: string }>("/users", { method: "POST", body: JSON.stringify(form) }),
    onSuccess: (u) => { setShown({ email: u.email, password: u.temporary_password }); setForm({ email: "", display_name: "", role: "user" }); setError(null); void refresh(); },
    onError: (e) => setError(errText(e)),
  });
  const setActive = useMutation({
    mutationFn: (v: { id: number; is_active: boolean }) => api<AdminUser>(`/users/${v.id}`, { method: "PATCH", body: JSON.stringify({ is_active: v.is_active }) }),
    onSuccess: () => { setError(null); void refresh(); },
    onError: (e) => setError(errText(e)),
  });
  const reset = useMutation({
    mutationFn: (u: AdminUser) => api<{ temporary_password: string }>(`/users/${u.id}/reset-password`, { method: "POST" }).then((r) => ({ u, r })),
    onSuccess: ({ u, r }) => { setShown({ email: u.email, password: r.temporary_password }); setError(null); void refresh(); },
    onError: (e) => setError(errText(e)),
  });

  const submit = (e: FormEvent) => { e.preventDefault(); create.mutate(); };

  return (
    <section className="space-y-6">
      <div>
        <h1 className="mb-2 ">Benutzerverwaltung</h1>
        <p className="text-sm text-slate-400">Nur Administratoren. Es gibt keine offene Registrierung und keinen E-Mail-Versand: Einmalpasswörter werden genau einmal hier angezeigt und müssen von dir weitergegeben werden. Beim ersten Login muss der Nutzer ein eigenes Passwort festlegen. API-Schlüssel sind für keinen Nutzer sichtbar, sie liegen nur in der Server-Konfiguration.</p>
      </div>
      {shown && (
        <div role="status" data-testid="temp-password" className="rounded border border-amber-700/50 bg-amber-950/40 p-3 text-sm text-amber-200">
          Einmalpasswort für {shown.email}: <code className="rounded bg-slate-900 px-2 py-1 text-slate-100">{shown.password}</code>
          <p className="mt-1 text-xs">Wird nur jetzt angezeigt und nicht gespeichert. Der Nutzer muss es beim ersten Login ändern.</p>
          <button type="button" onClick={() => setShown(null)} className="mt-2 underline">Ausblenden</button>
        </div>
      )}
      {error && <p role="alert" className="text-sm text-rose-300">{error}</p>}
      <form onSubmit={submit} className="grid gap-3 rounded-lg border border-slate-800 bg-slate-900 p-4 md:grid-cols-4">
        <label className="text-sm">E-Mail
          <input type="email" required value={form.email} onChange={(e) => setForm({ ...form, email: e.target.value })} className="mt-1 w-full rounded border border-slate-700 bg-slate-950 px-3 py-2" />
        </label>
        <label className="text-sm">Anzeigename
          <input required maxLength={100} value={form.display_name} onChange={(e) => setForm({ ...form, display_name: e.target.value })} className="mt-1 w-full rounded border border-slate-700 bg-slate-950 px-3 py-2" />
        </label>
        <label className="text-sm">Rolle
          <select value={form.role} onChange={(e) => setForm({ ...form, role: e.target.value })} className="mt-1 w-full rounded border border-slate-700 bg-slate-950 px-3 py-2">
            <option value="user">Nutzer</option>
            <option value="admin">Administrator</option>
          </select>
        </label>
        <div className="flex items-end"><button type="submit" disabled={create.isPending} className="rounded bg-sky-700 px-4 py-2 text-sm font-semibold disabled:opacity-50">Konto anlegen</button></div>
      </form>
      {q.isLoading && <p className="text-slate-400">Lade Benutzer …</p>}
      {q.isError && <p role="alert" className="text-rose-300">Die Benutzerliste konnte nicht geladen werden.</p>}
      {q.data && (
        <table className="w-full text-left text-sm" data-testid="user-table">
          <thead className="text-slate-400"><tr><th className="py-1">Name</th><th>E-Mail</th><th>Rolle</th><th>Status</th><th>Angelegt</th><th /></tr></thead>
          <tbody>
            {q.data.map((u) => (
              <tr key={u.id} className="border-t border-slate-800" data-testid="user-row">
                <td className="py-2">{u.display_name}</td>
                <td>{u.email}</td>
                <td>{u.role === "admin" ? "Administrator" : "Nutzer"}</td>
                <td>{u.is_active ? "aktiv" : "gesperrt"}{u.must_change_password && " (Einmalpasswort offen)"}</td>
                <td>{formatDateTime(u.created_at)}</td>
                <td className="space-x-3 text-right">
                  {u.id !== me?.user.id && (
                    <button type="button" className="underline" onClick={() => setActive.mutate({ id: u.id, is_active: !u.is_active })}>
                      {u.is_active ? "Sperren" : "Entsperren"}
                    </button>
                  )}
                  <button type="button" className="underline" onClick={() => { if (window.confirm(`Neues Einmalpasswort für ${u.email} erzeugen? Bestehende Sitzungen werden beendet.`)) reset.mutate(u); }}>
                    Passwort zurücksetzen
                  </button>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      )}
    </section>
  );
}
