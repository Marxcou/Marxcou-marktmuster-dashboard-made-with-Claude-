import { useQuery } from "@tanstack/react-query";
import { useState } from "react";
import { useSearchParams } from "react-router-dom";
import { NewsClusterCard } from "../components/NewsClusterCard";
import { api, type InstrumentWithQuote, type SentimentLabel, type Source } from "../lib/api";
import { useNews, useSentimentStatus } from "../lib/news";

const PERIODS = [
  { label: "24 Stunden", hours: 24 },
  { label: "7 Tage", hours: 168 },
  { label: "30 Tage", hours: 720 },
  { label: "Alle", hours: 0 },
];

export function News() {
  const [params] = useSearchParams();
  const [instrumentId, setInstrumentId] = useState(params.get("instrument") ?? "");
  const [source, setSource] = useState("");
  const [sentiment, setSentiment] = useState("");
  const [hours, setHours] = useState(168);

  const watch = useQuery({ queryKey: ["watchlist"], queryFn: () => api<InstrumentWithQuote[]>("/watchlist") });
  const sources = useQuery({ queryKey: ["sources"], queryFn: () => api<Source[]>("/sources") });
  const newsSources = (sources.data ?? []).filter((s) => s.kind === "news");

  const since = hours ? new Date(Date.now() - hours * 3_600_000).toISOString() : undefined;
  // Auf Minuten runden, damit der Query-Key nicht bei jedem Render wechselt.
  const stableSince = since ? since.slice(0, 16) + ":00Z" : undefined;
  const news = useNews({
    instrumentId: instrumentId ? Number(instrumentId) : undefined,
    source: source || undefined,
    sentiment: (sentiment || undefined) as SentimentLabel | undefined,
    since: stableSince,
  });

  const pages = news.data?.pages ?? [];
  const items = pages.flatMap((p) => p.items);
  const emptyReason = pages[0]?.empty_reason ?? null;
  const total = pages[0]?.total ?? 0;
  const sstat = useSentimentStatus();

  const sel = "rounded border border-slate-700 bg-slate-900 px-2 py-1 text-sm";
  return (
    <section>
      <h1 className="mb-4 text-xl font-semibold">Nachrichten</h1>
      <form className="mb-4 flex flex-wrap gap-3" aria-label="Filter" onSubmit={(e) => e.preventDefault()}>
        <label className="text-sm">Aktie{" "}
          <select className={sel} value={instrumentId} onChange={(e) => setInstrumentId(e.target.value)}>
            <option value="">Alle</option>
            {watch.data?.map((i) => <option key={i.id} value={i.id}>{i.symbol}</option>)}
          </select></label>
        <label className="text-sm">Quelle{" "}
          <select className={sel} value={source} onChange={(e) => setSource(e.target.value)}>
            <option value="">Alle</option>
            {newsSources.map((s) => <option key={s.key} value={s.key}>{s.name}</option>)}
          </select></label>
        <label className="text-sm">Zeitraum{" "}
          <select className={sel} value={hours} onChange={(e) => setHours(Number(e.target.value))}>
            {PERIODS.map((p) => <option key={p.label} value={p.hours}>{p.label}</option>)}
          </select></label>
        <label className="text-sm">Stimmung{" "}
          <select className={sel} value={sentiment} onChange={(e) => setSentiment(e.target.value)}>
            <option value="">Alle</option>
            <option value="positiv">positiv</option>
            <option value="neutral">neutral</option>
            <option value="negativ">negativ</option>
          </select></label>
      </form>

      {sstat.data && (
        <p className="mb-3 text-xs text-slate-400" data-testid="sentiment-status">
          Stimmungsanalyse: {sstat.data.active_method === "claude" ? "KI-generiert (Claude)" : "regelbasiertes Wörterbuch"}
          {sstat.data.fallback_reason && ` · Ausweichverfahren aktiv: ${sstat.data.fallback_reason}`}
          {sstat.data.claude_configured && ` · KI-Budget ${sstat.data.month}: ${sstat.data.spent_usd.toLocaleString("de-DE", { style: "currency", currency: "USD" })} von ${sstat.data.budget_usd.toLocaleString("de-DE", { style: "currency", currency: "USD" })}`}
        </p>
      )}
      {news.isLoading && <p className="text-slate-400">Lade Nachrichten …</p>}
      {news.isError && <p role="alert" className="text-rose-300">Nachrichten konnten nicht geladen werden (Backend nicht erreichbar).</p>}
      {news.data && items.length === 0 && (
        <div className="rounded border border-amber-700/50 bg-amber-950/30 p-4 text-amber-200" data-testid="no-news">
          <p className="font-semibold">Keine Nachrichten für diese Auswahl.</p>
          <p className="text-sm">{emptyReason ?? "Für die gewählten Filter liegen keine Meldungen vor. Prüfe auf der Seite „Quellen“, ob die Nachrichtenquellen erreichbar sind."}</p>
        </div>
      )}
      {items.length > 0 && (
        <>
          <p className="mb-2 text-xs text-slate-400">{total} Meldungen (Duplikate zusammengeführt, alle Quellen je Meldung aufgeführt)</p>
          <div className="space-y-4">{items.map((c) => <NewsClusterCard key={c.id} cluster={c} />)}</div>
          {news.hasNextPage && (
            <button type="button" onClick={() => void news.fetchNextPage()} disabled={news.isFetchingNextPage} className="mt-4 rounded border border-slate-700 px-3 py-1 text-sm">
              {news.isFetchingNextPage ? "Lade …" : "Weitere Meldungen laden"}
            </button>
          )}
        </>
      )}
    </section>
  );
}
