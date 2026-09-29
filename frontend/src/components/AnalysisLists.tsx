import { useState } from "react";
import type { IndicatorEvent, NotableMove, PatternDetection, SRZone } from "../lib/api";
import { EVENT_NAME, STATUS_TEXT } from "../lib/analysis";
import { formatDate, formatDateTime, formatNumber, formatPercentPoints, formatShare } from "../lib/format";
import { SourceTip } from "./SourceTip";

export function PatternList({ items, selectedId, onSelect }: { items: PatternDetection[]; selectedId: number | null; onSelect: (id: number) => void }) {
  return (
    <ul className="space-y-2" data-testid="pattern-list">
      {items.map((p) => (
        <li key={p.id}>
          <button type="button" onClick={() => onSelect(p.id)} aria-pressed={p.id === selectedId}
            className={`w-full rounded border p-3 text-left text-sm ${p.id === selectedId ? "border-violet-500 bg-violet-950/40" : "border-slate-700"}`}>
            <span className="font-semibold">{p.name}</span>
            <span className="ml-2 text-slate-300">{STATUS_TEXT[p.status] ?? p.status_label}</span>
            <span className="block text-xs text-slate-400">
              {formatDate(p.start_ts)} bis {formatDate(p.end_ts)} · Konfidenz der Erkennung {formatShare(p.confidence.score)} · Backtest: {p.backtest?.status === "berechnet" && p.backtest.hit_rate != null ? `${formatShare(p.backtest.hit_rate)} bei ${p.backtest.sample_size} Fällen` : "nicht verfügbar"}
            </span>
          </button>
        </li>
      ))}
    </ul>
  );
}

export function ZoneList({ zones }: { zones: SRZone[] }) {
  if (zones.length === 0) return null;
  return (
    <div className="mt-4" data-testid="zone-list">
      <h3 className="mb-1 font-semibold">Unterstützungs- und Widerstandszonen</h3>
      <ul className="space-y-1 text-sm">
        {zones.map((z) => (
          <li key={z.id}>
            <details>
              <summary className="cursor-pointer">{z.kind_label}: {formatNumber(z.lower)} bis {formatNumber(z.upper)} · {z.touch_count} Berührungen{z.confidence ? ` · Konfidenz ${formatShare(z.confidence.score)}` : ""}</summary>
              <p className="mt-1 text-xs text-slate-300">{z.explanation}</p>
              <p className="text-xs text-slate-400">Erste Berührung {formatDate(z.first_touch)}, letzte {formatDate(z.last_touch)}. Die Zonen sind aus Wendepunkten berechnet und beschreiben nur, wo der Kurs bisher gedreht hat.</p>
            </details>
          </li>
        ))}
      </ul>
    </div>
  );
}

export function EventList({ events }: { events: IndicatorEvent[] }) {
  return (
    <ul className="space-y-2" data-testid="event-list">
      {events.map((e) => (
        <li key={e.id} className="rounded border border-slate-800 p-3 text-sm" data-testid="indicator-event">
          <p className="font-semibold">{e.title || EVENT_NAME[e.type]} <span className="font-normal text-slate-400">· {formatDate(e.ts)}</span></p>
          <p className="text-slate-300">{e.summary}</p>
          <details className="mt-1 text-xs text-slate-300">
            <summary className="cursor-pointer text-slate-400">Kriterien, Parameter und Quelle</summary>
            <table className="mt-1 w-full text-left">
              <thead className="text-slate-400"><tr><th>Kriterium</th><th>Regel</th><th>Soll</th><th>Ist</th><th>Ergebnis</th></tr></thead>
              <tbody>{e.criteria.map((c) => <tr key={c.name} className="border-t border-slate-800"><td>{c.name}</td><td>{c.rule}</td><td>{c.required}</td><td>{c.actual}</td><td>{c.passed ? "erfüllt" : "nicht erfüllt"}</td></tr>)}</tbody>
            </table>
            <p className="mt-1">Parameter: {Object.entries(e.params).map(([k, v]) => `${k} = ${String(v)}`).join(", ") || "keine"} · Version {e.algo_version}</p>
            <p className="mt-1" data-testid="event-stats">{e.historical_stats ? "Historische Statistik liegt vor." : (e.historical_stats_reason ?? "Historische Trefferquote: nicht verfügbar.")}</p>
            <div className="mt-1 flex flex-wrap gap-2">{e.sources.map((s) => <SourceTip key={s.key} source={s} fetchedAt={e.bars_fetched_at} />)}</div>
          </details>
        </li>
      ))}
    </ul>
  );
}

export function MoveList({ moves, note, onOpenNews }: { moves: NotableMove[]; note: string; onOpenNews: (clusterId: number) => void }) {
  const [open, setOpen] = useState<number | null>(null);
  return (
    <div data-testid="move-list">
      <p className="mb-2 text-xs text-slate-400">{note} Die Zuordnung beruht nur auf dem Zeitfenster; ob eine Meldung die Bewegung beeinflusst hat, lässt sich daraus nicht ableiten.</p>
      <ul className="space-y-2">
        {moves.map((m) => (
          <li key={m.id} className="rounded border border-slate-800 p-3 text-sm" data-testid="move">
            <p>
              Auffällige Kursbewegung {formatDate(m.move_start)} bis {formatDate(m.move_end)}: {formatPercentPoints(m.return_pct)}
              <span className="text-xs text-slate-400"> (Abweichung {m.return_z != null ? `${formatNumber(m.return_z, 1)} Standardabweichungen` : "nicht berechnet"}{m.volume_z != null ? `, Volumen ${formatNumber(m.volume_z, 1)}` : ""})</span>
            </p>
            {m.news.length === 0 ? (
              <p className="text-xs text-slate-400">Im Zeitfenster wurde keine Meldung zu diesem Instrument veröffentlicht.</p>
            ) : (
              <>
                <p className="text-xs text-slate-300">Zeitlich zusammenfallend veröffentlicht ({m.news.length}):</p>
                <ul className="mt-1 space-y-1">
                  {m.news.map((n) => (
                    <li key={n.cluster_id}>
                      <button type="button" className="text-left underline" onClick={() => { setOpen(n.cluster_id); onOpenNews(n.cluster_id); }}>{n.canonical_title}</button>
                      <span className="block text-xs text-slate-400">
                        {formatDateTime(n.first_published_at)} ({Math.abs(n.time_offset_minutes)} Min. {n.time_offset_minutes < 0 ? "vor" : "nach"} Beginn der Kerze) · {n.item_count} {n.item_count === 1 ? "Quelle" : "Quellen"}: {n.sources.map((s) => s.name).join(", ")}
                        {open === n.cluster_id && " · unten geöffnet"}
                      </span>
                    </li>
                  ))}
                </ul>
              </>
            )}
            <details className="mt-1 text-xs text-slate-400"><summary className="cursor-pointer">Verfahren und Quelle</summary>
              <p>Auffällig = Rendite oder Volumen weicht um mehr als {String(m.params.z_threshold ?? "?")} Standardabweichungen der letzten {String(m.params.lookback_bars ?? "?")} Kerzen ab. Version {m.algo_version}.</p>
              <div className="flex flex-wrap gap-2">{m.sources.map((s) => <SourceTip key={s.key} source={s} fetchedAt={m.bars_fetched_at} />)}</div>
            </details>
          </li>
        ))}
      </ul>
    </div>
  );
}
