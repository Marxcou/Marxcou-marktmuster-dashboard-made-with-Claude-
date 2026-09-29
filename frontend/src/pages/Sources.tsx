import { CardSkeleton } from "../components/Skeleton";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { useLiveEvents } from "../hooks/useLiveEvents";
import { api, type Source } from "../lib/api";
import { formatDateTime } from "../lib/format";

const STATUS: Record<Source["status"], { text: string; cls: string }> = {
  online: { text: "online", cls: "border-emerald-600 text-emerald-300" },
  degraded: { text: "eingeschränkt", cls: "border-amber-600 text-amber-300" },
  offline: { text: "offline", cls: "border-rose-600 text-rose-300" },
  disabled: { text: "deaktiviert", cls: "border-slate-600 text-slate-300" },
};
const KIND: Record<string, string> = { price: "Kursdaten", news: "Nachrichten", llm: "KI", reference: "Referenzdaten" };

export function Sources() {
  const qc = useQueryClient();
  const q = useQuery({ queryKey: ["sources"], queryFn: () => api<Source[]>("/sources"), refetchInterval: 30_000 });
  useLiveEvents((e) => { if (e.type === "source_status") qc.invalidateQueries({ queryKey: ["sources"] }); });

  return (
    <section>
      <h1 className="mb-2">Quellen</h1>
      <p className="mb-4 text-sm text-slate-400">Alle angebundenen Datenquellen mit Aktualisierungsintervall, Verzögerung und aktuellem Status. Die Liste wird aus den Adaptern des Backends erzeugt.</p>
      {q.isLoading && <div className="grid gap-4 md:grid-cols-2"><CardSkeleton /><CardSkeleton /></div>}
      {q.isError && <p role="alert" className="text-rose-300" data-testid="sources-error">Die Quellenliste konnte nicht geladen werden (Backend nicht erreichbar). Der Status der Quellen ist daher unbekannt.</p>}
      {q.data && q.data.length === 0 && <p className="text-amber-300" data-testid="no-sources">Das Backend meldet keine angebundenen Quellen.</p>}
      <div className="grid gap-4 md:grid-cols-2">
        {q.data?.map((s) => {
          const st = STATUS[s.status] ?? STATUS.offline;
          return (
            <article key={s.key} className="card" data-testid="source-card">
              <div className="flex items-start justify-between gap-2">
                <h2 className="font-semibold"><a href={s.homepage} target="_blank" rel="noreferrer" className="underline">{s.name}</a></h2>
                <span className={`rounded border px-2 py-0.5 text-xs ${st.cls}`} data-testid="source-status">{st.text}</span>
              </div>
              <p className="text-xs text-slate-400">{KIND[s.kind] ?? s.kind}{s.is_official ? " · offizielle Quelle" : " · inoffizielle Quelle"}</p>
              <p className="mt-2 text-sm">{s.description}</p>
              <dl className="mt-3 grid grid-cols-[auto,minmax(0,1fr)] [&_dd]:break-words gap-x-3 gap-y-1 text-sm">
                <dt className="text-slate-400">Intervall</dt><dd>{s.update_interval}</dd>
                <dt className="text-slate-400">Verzögerung</dt><dd>{s.delay_text}</dd>
                <dt className="text-slate-400">API-Schlüssel</dt><dd>{s.requires_key ? "erforderlich" : "nicht erforderlich"}</dd>
                <dt className="text-slate-400">Letzter Erfolg</dt><dd>{s.last_success_at ? formatDateTime(s.last_success_at) : "noch kein erfolgreicher Abruf"}</dd>
                {s.kind === "news" && (<><dt className="text-slate-400">Meldungen (24 h)</dt><dd>{s.item_count_24h ?? "nicht verfügbar"}</dd></>)}
                {s.last_error && (<><dt className="text-slate-400">Letzter Fehler</dt><dd className="text-amber-300">{s.last_error}</dd></>)}
              </dl>
              <a href={s.terms_url} target="_blank" rel="noreferrer" className="mt-2 inline-block text-xs underline text-slate-400">Nutzungsbedingungen</a>
            </article>
          );
        })}
      </div>
    </section>
  );
}
