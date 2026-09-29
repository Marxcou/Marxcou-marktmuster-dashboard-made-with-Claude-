import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { CardSkeleton } from "../components/Skeleton";
import { InstrumentCard } from "../components/InstrumentCard";
import { SearchBox } from "../components/SearchBox";
import { useLiveEvents } from "../hooks/useLiveEvents";
import { usePatternCounts } from "../lib/analysis";
import { useNewsCounts } from "../lib/news";
import { api, type InstrumentWithQuote } from "../lib/api";

export function Watchlist() {
  const qc = useQueryClient();
  const list = useQuery({ queryKey: ["watchlist"], queryFn: () => api<InstrumentWithQuote[]>("/watchlist"), refetchInterval: 30_000 });
  useLiveEvents((e) => { if (e.type === "quote") qc.invalidateQueries({ queryKey: ["watchlist"] });
    if (e.type === "news") qc.invalidateQueries({ queryKey: ["news-counts"] });
    if (e.type === "detection") qc.invalidateQueries({ queryKey: ["pattern-counts"] }); });
  const remove = useMutation({
    mutationFn: (id: number) => api(`/watchlist/${id}`, { method: "DELETE" }),
    onSuccess: () => qc.invalidateQueries({ queryKey: ["watchlist"] }),
  });
  // Auf Minuten gerundet, damit der Query-Key stabil bleibt.
  const since = new Date(Math.floor((Date.now() - 86_400_000) / 60_000) * 60_000).toISOString();
  const counts = useNewsCounts(since);
  const patternCounts = usePatternCounts();
  const watched = new Set((list.data ?? []).map((i) => i.id));

  return (
    <section>
      <h1 className="mb-1">Watchlist</h1>
      <p className="mb-4 text-sm text-slate-400">Deine beobachteten Instrumente. Karte antippen für Chart, Muster, Prognose und Nachrichten.</p>
      <SearchBox watchedIds={watched} />
      {list.isLoading && <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-3"><CardSkeleton /><CardSkeleton /><CardSkeleton /></div>}
      {list.isError && <p role="alert" className="text-rose-300">Die Watchlist konnte nicht geladen werden (Backend nicht erreichbar).</p>}
      {list.data && list.data.length === 0 && (
        <div className="empty-state" data-testid="empty-watchlist"><p className="font-semibold text-slate-100">Die Watchlist ist leer.</p><p className="mt-1 text-sm">Suche oben nach einem Instrument und füge es hinzu.</p></div>
      )}
      <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-3">
        {list.data?.map((i) => <InstrumentCard key={i.id} item={i} onRemove={() => remove.mutate(i.id)}
          newsCount={counts.data && !counts.data.empty_reason ? (counts.data.counts[String(i.id)] ?? 0) : undefined}
          // Fehlt das Instrument in der Antwort, wurde es noch nicht ausgewertet: "nicht verfügbar" statt einer unwahren 0
          patternCount={patternCounts.data && !patternCounts.data.empty_reason ? patternCounts.data.counts[String(i.id)] : undefined}
          patternReason={patternCounts.isError ? "Backend nicht erreichbar" : patternCounts.data?.empty_reason}
          newsReason={counts.isError ? "Backend nicht erreichbar" : counts.data?.empty_reason} />)}
      </div>
    </section>
  );
}
