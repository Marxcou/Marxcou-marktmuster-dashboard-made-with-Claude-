import { Link } from "react-router-dom";
import type { InstrumentWithQuote } from "../lib/api";
import { formatDateTime, formatPercent, formatPrice } from "../lib/format";
import { SourceTip } from "./SourceTip";

export function InstrumentCard({ item, onRemove, newsCount, newsReason, patternCount, patternReason }: { item: InstrumentWithQuote; onRemove?: () => void; newsCount?: number; newsReason?: string | null; patternCount?: number; patternReason?: string | null }) {
  const q = item.quote;
  const tone = q?.change_pct == null ? "text-slate-400" : q.change_pct > 0 ? "text-emerald-400" : q.change_pct < 0 ? "text-rose-400" : "text-slate-300";
  return (
    <article className="rounded-lg border border-slate-800 bg-slate-900 p-4" data-testid="instrument-card">
      <div className="flex items-start justify-between gap-2">
        <Link to={`/instrument/${item.id}`} className="min-w-0">
          <h2 className="font-semibold">{item.symbol}</h2>
          <p className="truncate text-sm text-slate-400">{item.name} · {item.exchange}</p>
        </Link>
        {onRemove && (
          <button type="button" onClick={onRemove} className="text-xs text-slate-400 underline" aria-label={`${item.symbol} aus Watchlist entfernen`}>
            Entfernen
          </button>
        )}
      </div>
      {q ? (
        <div className="mt-3">
          <p className="text-2xl font-semibold">{formatPrice(q.price, item.currency)}</p>
          <p className={`text-sm ${tone}`}>
            {q.change_abs != null && `${q.change_abs > 0 ? "+" : ""}${formatPrice(q.change_abs, item.currency)} · `}
            {q.change_pct != null ? formatPercent(q.change_pct / 100) : "Tagesveränderung nicht verfügbar"}
          </p>
          <p className="mt-1 text-xs text-slate-400">Stand: {formatDateTime(q.ts_utc)}{q.delay_seconds ? ` (${Math.round(q.delay_seconds / 60)} Min. verzögert)` : ""}</p>
          {q.is_demo && <p className="text-xs font-semibold text-fuchsia-400">Beispieldaten (Demo-Modus)</p>}
          <SourceTip source={q.source} ts={q.ts_utc} fetchedAt={q.fetched_at} />
        </div>
      ) : (
        <p className="mt-3 text-sm text-amber-300" data-testid="no-quote">Kein Kurs verfügbar: Für dieses Instrument wurde bisher kein Kurs von einer Quelle abgerufen.</p>
      )}
      <p className="mt-3 text-xs text-slate-400" data-testid="news-count">
        {newsCount != null
          ? <>Nachrichten (letzte 24 Stunden): <Link to={`/nachrichten?instrument=${item.id}`} className="underline">{newsCount}</Link></>
          : `Nachrichten: nicht verfügbar${newsReason ? ` (${newsReason})` : ""}`}
      </p>
      <p className="text-xs text-slate-400" data-testid="pattern-count">
        {patternCount != null
          ? <>Aktuell erkannte Muster: <Link to={`/instrument/${item.id}`} className="underline">{patternCount}</Link></>
          : `Erkannte Muster: nicht verfügbar${patternReason ? ` (${patternReason})` : ""}`}
      </p>
    </article>
  );
}
