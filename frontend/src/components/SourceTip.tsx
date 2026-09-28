import { formatDateTime } from "../lib/format";
import type { SourceRef } from "../lib/api";

// Grundregel 2: Anbieter, Original-Link, Zeitstempel und Verzögerung an jedem Wert.
export function SourceTip({ source, ts, fetchedAt }: { source: SourceRef; ts?: string; fetchedAt: string }) {
  return (
    <details className="inline-block text-xs text-slate-400" data-testid="source-tip">
      <summary className="cursor-pointer select-none">Quelle: {source.name}</summary>
      <dl className="mt-1 space-y-0.5 rounded border border-slate-700 bg-slate-900 p-2">
        <div><dt className="inline">Anbieter: </dt><dd className="inline"><a className="underline" href={source.homepage} target="_blank" rel="noreferrer">{source.name}</a></dd></div>
        <div><dt className="inline">Verzögerung: </dt><dd className="inline">{source.delay_text}</dd></div>
        {ts && <div><dt className="inline">Zeitpunkt des Werts: </dt><dd className="inline">{formatDateTime(ts)}</dd></div>}
        <div><dt className="inline">Abgerufen: </dt><dd className="inline">{formatDateTime(fetchedAt)}</dd></div>
        <div><a className="underline" href={source.terms_url} target="_blank" rel="noreferrer">Nutzungsbedingungen</a></div>
      </dl>
    </details>
  );
}
