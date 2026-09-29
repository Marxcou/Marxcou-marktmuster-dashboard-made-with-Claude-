import { useState, type FormEvent } from "react";
import { api, ApiError } from "../lib/api";
import { useAuth } from "../lib/auth";

const MIN_LENGTH = 10;

export function Account({ forced = false }: { forced?: boolean }) {
  const { me, refresh } = useAuth();
  const [current, setCurrent] = useState("");
  const [next, setNext] = useState("");
  const [repeat, setRepeat] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [done, setDone] = useState(false);
  const [busy, setBusy] = useState(false);

  const submit = async (e: FormEvent) => {
    e.preventDefault();
    setDone(false);
    if (next.length < MIN_LENGTH) return setError(`Das neue Passwort braucht mindestens ${MIN_LENGTH} Zeichen.`);
    if (next !== repeat) return setError("Die beiden neuen Passwörter stimmen nicht überein.");
    setBusy(true);
    setError(null);
    try {
      await api<void>("/auth/change-password", { method: "POST", body: JSON.stringify({ current_password: current, new_password: next }) });
      setCurrent(""); setNext(""); setRepeat("");
      setDone(true);
      await refresh();
    } catch (err) {
      setError(err instanceof ApiError && err.detail ? err.detail : "Passwort konnte nicht geändert werden.");
    } finally {
      setBusy(false);
    }
  };

  return (
    <form onSubmit={submit} className="mx-auto max-w-sm space-y-3">
      <h1 className="text-xl font-semibold">Passwort ändern</h1>
      {forced && (
        <p role="status" data-testid="forced-change" className="rounded border border-amber-700/50 bg-amber-950/40 p-2 text-sm text-amber-200">
          Dein Konto hat ein Einmalpasswort. Bitte lege jetzt ein eigenes Passwort fest, danach kannst du das Dashboard nutzen.
        </p>
      )}
      <p className="text-sm text-slate-400">Angemeldet als {me?.user.email}. Nach der Änderung werden deine anderen Sitzungen beendet.</p>
      <label className="block text-sm">Aktuelles Passwort
        <input type="password" required value={current} onChange={(e) => setCurrent(e.target.value)} autoComplete="current-password" className="mt-1 w-full rounded border border-slate-700 bg-slate-900 px-3 py-2" />
      </label>
      <label className="block text-sm">Neues Passwort (mindestens {MIN_LENGTH} Zeichen)
        <input type="password" required value={next} onChange={(e) => setNext(e.target.value)} autoComplete="new-password" className="mt-1 w-full rounded border border-slate-700 bg-slate-900 px-3 py-2" />
      </label>
      <label className="block text-sm">Neues Passwort wiederholen
        <input type="password" required value={repeat} onChange={(e) => setRepeat(e.target.value)} autoComplete="new-password" className="mt-1 w-full rounded border border-slate-700 bg-slate-900 px-3 py-2" />
      </label>
      {error && <p role="alert" className="text-sm text-rose-300">{error}</p>}
      {done && <p role="status" data-testid="password-changed" className="text-sm text-emerald-300">Passwort geändert.</p>}
      <button type="submit" disabled={busy} className="rounded bg-sky-700 px-4 py-2 text-sm font-semibold disabled:opacity-50">Passwort ändern</button>
    </form>
  );
}
