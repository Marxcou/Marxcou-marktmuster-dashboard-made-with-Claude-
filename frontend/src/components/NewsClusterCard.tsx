import type { NewsCluster } from "../lib/api";
import { formatDateTime } from "../lib/format";
import { SourceTip } from "./SourceTip";

// Neutrale Darstellung: die Stimmung ist eine Beschreibung des Textes, kein Signal und keine Handlungsaufforderung.
export function SentimentInfo({ s }: { s: NonNullable<NewsCluster["sentiment"]> }) {
  return (
    <details className="text-xs text-slate-300" data-testid="sentiment">
      <summary className="cursor-pointer">Stimmung im Text: {s.label} (Wert {s.score.toLocaleString("de-DE", { maximumFractionDigits: 2 })}) · Methode: {s.method === "claude" ? `KI-generiert, Modell ${s.model_name}` : `Wörterbuch (${s.model_name}${s.model_version ? `, Version ${s.model_version}` : ""})`}</summary>
      <p className="mt-1">{s.rationale}</p>
      {s.evidence.length > 0 && (
        <ul className="mt-1 list-disc pl-5">{s.evidence.map((e) => <li key={e}>„{e}“</li>)}</ul>
      )}
    </details>
  );
}

export function NewsClusterCard({ cluster }: { cluster: NewsCluster }) {
  return (
    <article className="rounded-lg border border-slate-800 bg-slate-900 p-4" data-testid="news-cluster">
      <h2 className="font-semibold">{cluster.canonical_title}</h2>
      <p className="text-xs text-slate-400">
        Erstmals veröffentlicht: {formatDateTime(cluster.first_published_at)}
        {cluster.instruments.length > 0 && ` · ${cluster.instruments.map((i) => i.symbol).join(", ")}`}
        {` · ${cluster.item_count} ${cluster.item_count === 1 ? "Quelle" : "Quellen"}`}
      </p>
      {cluster.sentiment ? <div className="mt-2"><SentimentInfo s={cluster.sentiment} /></div>
        : <p className="mt-2 text-xs text-slate-400">Keine Stimmungsanalyse vorhanden.</p>}
      <ul className="mt-3 space-y-3">
        {cluster.items.map((it) => (
          <li key={it.id} className="border-l-2 border-slate-700 pl-3" data-testid="news-item">
            <a href={it.url} target="_blank" rel="noreferrer" className="text-sm text-sky-300 underline">{it.title}</a>
            {it.excerpt && <p className="text-sm text-slate-300">{it.excerpt}</p>}
            <p className="text-xs text-slate-400">{it.source.name} · veröffentlicht {formatDateTime(it.published_at)}</p>
            <SourceTip source={it.source} ts={it.published_at} fetchedAt={it.fetched_at} />
          </li>
        ))}
      </ul>
    </article>
  );
}
