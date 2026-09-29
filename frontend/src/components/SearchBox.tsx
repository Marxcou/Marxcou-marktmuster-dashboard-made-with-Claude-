import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useEffect, useState } from "react";
import { Link } from "react-router-dom";
import { api, type Instrument } from "../lib/api";

export function SearchBox({ watchedIds }: { watchedIds: Set<number> }) {
  const qc = useQueryClient();
  const [input, setInput] = useState("");
  const [q, setQ] = useState("");
  useEffect(() => {
    const t = setTimeout(() => setQ(input.trim()), 300);
    return () => clearTimeout(t);
  }, [input]);

  const search = useQuery({
    queryKey: ["search", q],
    enabled: q.length >= 1,
    queryFn: () => api<Instrument[]>(`/instruments/search?q=${encodeURIComponent(q)}`),
  });
  const add = useMutation({
    mutationFn: (id: number) => api("/watchlist", { method: "POST", body: JSON.stringify({ instrument_id: id }) }),
    onSuccess: () => {
      void qc.invalidateQueries({ queryKey: ["watchlist"] });
      // Zähler des neuen Instruments (Muster, Meldungen) nachladen, sonst zeigt die Karte bis zum nächsten Abruf 0
      void qc.invalidateQueries({ queryKey: ["pattern-counts"] });
      void qc.invalidateQueries({ queryKey: ["news-counts"] });
    },
  });

  return (
    <section aria-label="Suche" className="mb-6">
      <label htmlFor="search" className="mb-1 block text-sm text-slate-300">Suche nach Ticker, Firmenname oder ISIN</label>
      <input id="search" type="search" value={input} onChange={(e) => setInput(e.target.value)} placeholder="z. B. AAPL, SAP oder US0378331005"
        className="w-full max-w-md rounded border border-slate-700 bg-slate-900 px-3 py-2" />
      {q && search.isLoading && <p className="mt-2 text-sm text-slate-400">Suche läuft …</p>}
      {search.isError && <p className="mt-2 text-sm text-rose-300">Die Suche ist fehlgeschlagen. Bitte später erneut versuchen.</p>}
      {search.data && search.data.length === 0 && (
        <p className="mt-2 text-sm text-slate-400" data-testid="no-results">Keine Treffer in den gespeicherten Instrumenten.</p>
      )}
      {search.data && search.data.length > 0 && (
        <ul className="mt-2 max-w-md divide-y divide-slate-800 rounded border border-slate-800 bg-slate-900" data-testid="search-results">
          {search.data.map((i) => (
            <li key={i.id} className="flex items-center justify-between gap-2 px-3 py-2 text-sm">
              <Link to={`/instrument/${i.id}`} className="min-w-0 truncate">
                <span className="font-semibold">{i.symbol}</span> · {i.name} <span className="text-slate-400">({i.exchange}{i.isin ? `, ${i.isin}` : ""})</span>
              </Link>
              {watchedIds.has(i.id) ? (
                <span className="text-xs text-slate-400">In Watchlist</span>
              ) : (
                <button type="button" className="rounded border border-slate-600 px-2 py-1 text-xs" onClick={() => add.mutate(i.id)} disabled={add.isPending}>
                  Zur Watchlist
                </button>
              )}
            </li>
          ))}
        </ul>
      )}
    </section>
  );
}
