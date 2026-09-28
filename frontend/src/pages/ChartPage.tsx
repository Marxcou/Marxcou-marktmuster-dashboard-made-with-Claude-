import { useQuery, useQueryClient } from "@tanstack/react-query";
import { useMemo, useState } from "react";
import { Link, useParams } from "react-router-dom";
import { PriceChart, type ChartKind } from "../components/PriceChart";
import { SourceTip } from "../components/SourceTip";
import { useLiveEvents } from "../hooks/useLiveEvents";
import { api, type BarsResponse, type InstrumentWithQuote } from "../lib/api";
import { formatDateTime, formatPercent, formatPrice } from "../lib/format";
import { RANGES, rangeStart, windowBars } from "../lib/timeframes";

export function ChartPage() {
  const { id } = useParams();
  const qc = useQueryClient();
  const [rangeLabel, setRangeLabel] = useState("6M");
  const [kind, setKind] = useState<ChartKind>("candles");
  const range = RANGES.find((r) => r.label === rangeLabel) ?? RANGES[3];
  const intraday = range.timeframe !== "1d";

  const inst = useQuery({ queryKey: ["instrument", id], queryFn: () => api<InstrumentWithQuote>(`/instruments/${id}`), refetchInterval: 15_000 });
  const bars = useQuery({
    queryKey: ["bars", id, range.label],
    queryFn: () => api<BarsResponse>(`/instruments/${id}/bars?timeframe=${range.timeframe}&start=${encodeURIComponent(rangeStart(range))}`),
    refetchInterval: intraday ? 15_000 : 60_000,
  });
  useLiveEvents((e) => {
    if (e.type === "quote" && String(e.payload.instrument_id) === id) {
      qc.invalidateQueries({ queryKey: ["instrument", id] });
      qc.invalidateQueries({ queryKey: ["bars", id] });
    }
  });

  const shown = useMemo(() => windowBars(bars.data?.bars ?? [], range), [bars.data, range]);
  const q = inst.data?.quote;
  const last = shown[shown.length - 1];
  const lastUpdate = bars.dataUpdatedAt ? new Date(bars.dataUpdatedAt).toISOString() : null;

  return (
    <section>
      <Link to="/" className="text-sm text-slate-400 underline">← Watchlist</Link>
      {inst.isError && <p role="alert" className="mt-2 text-rose-300">Instrument konnte nicht geladen werden.</p>}
      {inst.data && (
        <header className="mt-2 mb-4">
          <h1 className="text-xl font-semibold">{inst.data.symbol} <span className="font-normal text-slate-400">{inst.data.name} · {inst.data.exchange}</span></h1>
          {q ? (
            <div>
              <p className="text-2xl font-semibold">{formatPrice(q.price, inst.data.currency)}
                {q.change_pct != null && <span className={`ml-2 text-base ${q.change_pct >= 0 ? "text-emerald-400" : "text-rose-400"}`}>{formatPercent(q.change_pct / 100)}</span>}
              </p>
              <SourceTip source={q.source} ts={q.ts_utc} fetchedAt={q.fetched_at} />
            </div>
          ) : (
            <p className="text-sm text-amber-300">Kein aktueller Kurs verfügbar.</p>
          )}
        </header>
      )}

      <div className="mb-3 flex flex-wrap items-center gap-2">
        <div role="group" aria-label="Zeitraum" className="flex gap-1">
          {RANGES.map((r) => (
            <button key={r.label} type="button" aria-pressed={r.label === rangeLabel} onClick={() => setRangeLabel(r.label)}
              className={`rounded border px-3 py-1 text-sm ${r.label === rangeLabel ? "border-sky-500 bg-sky-900" : "border-slate-700"}`}>{r.label}</button>
          ))}
        </div>
        <div role="group" aria-label="Diagrammtyp" className="ml-auto flex gap-1">
          {(["candles", "line"] as const).map((k) => (
            <button key={k} type="button" aria-pressed={k === kind} onClick={() => setKind(k)}
              className={`rounded border px-3 py-1 text-sm ${k === kind ? "border-sky-500 bg-sky-900" : "border-slate-700"}`}>{k === "candles" ? "Kerzen" : "Linie"}</button>
          ))}
        </div>
      </div>

      {bars.isLoading && <p className="text-slate-400">Lade Kursdaten …</p>}
      {bars.isError && <p role="alert" className="text-rose-300">Kursdaten konnten nicht geladen werden (Backend nicht erreichbar).</p>}
      {bars.data && shown.length === 0 && (
        <div className="rounded border border-amber-700/50 bg-amber-950/30 p-4 text-amber-200" data-testid="no-bars">
          <p className="font-semibold">Keine Kursdaten für diesen Zeitraum.</p>
          <p className="text-sm">{bars.data.empty_reason ?? "Die Quelle hat für diesen Zeitraum keine Daten geliefert."}</p>
        </div>
      )}
      {shown.length > 0 && (
        <>
          <PriceChart bars={shown} kind={kind} intraday={intraday} />
          <p className="mt-2 text-xs text-slate-400" data-testid="last-update">
            Letzter Datenpunkt: {last && formatDateTime(last.ts_utc)}
            {lastUpdate && ` · Zuletzt im Dashboard aktualisiert: ${formatDateTime(lastUpdate)}`}
            {shown.some((b) => b.is_demo) && " · Beispieldaten (Demo-Modus)"}
          </p>
          {last && <SourceTip source={last.source} ts={last.ts_utc} fetchedAt={last.fetched_at} />}
        </>
      )}
    </section>
  );
}
