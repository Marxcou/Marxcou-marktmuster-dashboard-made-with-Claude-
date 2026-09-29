import { useState, type FormEvent } from "react";
import { Navigate } from "react-router-dom";
import { ApiError } from "../lib/api";
import { useAuth } from "../lib/auth";

export function Login() {
  const { me, login } = useAuth();
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  if (me) return <Navigate to="/" replace />;

  const submit = async (e: FormEvent) => {
    e.preventDefault();
    setBusy(true);
    setError(null);
    try {
      await login(email, password);
    } catch (err) {
      const msg = err instanceof Error ? err.message : "";
      setError(
        err instanceof ApiError && err.status === 403 && err.detail ? err.detail
          : msg === "unauthorized" ? "E-Mail oder Passwort falsch."
          : msg.startsWith("HTTP ") ? `Anmeldung nicht möglich: Server-Antwort ${msg}.`
          : "Anmeldung nicht möglich. Ist das Backend erreichbar?",
      );
    } finally {
      setBusy(false);
    }
  };

  return (
    <form onSubmit={submit} className="mx-auto max-w-sm space-y-3">
      <h1 className="text-xl font-semibold">Anmelden</h1>
      <p className="text-sm text-slate-400">Konten legt ein Administrator an, eine offene Registrierung gibt es nicht.</p>
      <label className="block text-sm">E-Mail
        <input type="email" required value={email} onChange={(e) => setEmail(e.target.value)} autoComplete="username" className="mt-1 w-full rounded border border-slate-700 bg-slate-900 px-3 py-2" />
      </label>
      <label className="block text-sm">Passwort
        <input type="password" required value={password} onChange={(e) => setPassword(e.target.value)} autoComplete="current-password" className="mt-1 w-full rounded border border-slate-700 bg-slate-900 px-3 py-2" />
      </label>
      {error && <p role="alert" className="text-sm text-rose-300">{error}</p>}
      <button type="submit" disabled={busy} className="rounded bg-sky-700 px-4 py-2 text-sm font-semibold disabled:opacity-50">Anmelden</button>
    </form>
  );
}
