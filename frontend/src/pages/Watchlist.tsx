import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { InstrumentCard } from "../components/InstrumentCard";
import { SearchBox } from "../components/SearchBox";
import { useLiveEvents } from "../hooks/useLiveEvents";
import { api, type InstrumentWithQuote } from "../lib/api";

export function Watchlist() {
  const qc = useQueryClient();
  const list = useQuery({ queryKey: ["watchlist"], queryFn: () => api<InstrumentWithQuote[]>("/watchlist"), refetchInterval: 30_000 });
  useLiveEvents((e) => { if (e.type === "quote") qc.invalidateQueries({ queryKey: ["watchlist"] }); });
  const remove = useMutation({
    mutationFn: (id: number) => api(`/watchlist/${id}`, { method: "DELETE" }),
    onSuccess: () => qc.invalidateQueries({ queryKey: ["watchlist"] }),
  });
  const watched = new Set((list.data ?? []).map((i) => i.id));

  return (
    <section>
      <h1 className="mb-4 text-xl font-semibold">Watchlist</h1>
      <SearchBox watchedIds={watched} />
      {list.isLoading && <p className="text-slate-400">Lade Watchlist …</p>}
      {list.isError && <p role="alert" className="text-rose-300">Die Watchlist konnte nicht geladen werden (Backend nicht erreichbar).</p>}
      {list.data && list.data.length === 0 && (
        <p className="text-slate-400" data-testid="empty-watchlist">Die Watchlist ist leer. Suche oben nach einem Instrument und füge es hinzu.</p>
      )}
      <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-3">
        {list.data?.map((i) => <InstrumentCard key={i.id} item={i} onRemove={() => remove.mutate(i.id)} />)}
      </div>
    </section>
  );
}
