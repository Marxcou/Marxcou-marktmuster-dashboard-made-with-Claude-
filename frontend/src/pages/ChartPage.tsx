import { useQuery, useQueryClient } from "@tanstack/react-query";
import { useMemo, useState } from "react";
import { Link, useParams } from "react-router-dom";
import { NewsClusterCard } from "../components/NewsClusterCard";
import { EventList, MoveList, PatternList, ZoneList } from "../components/AnalysisLists";
import { ForecastPanel } from "../components/ForecastPanel";
import { PatternPanel } from "../components/PatternPanel";
import { PriceChart, type ChartKind, type NewsMarker, type PriceOverlay } from "../components/PriceChart";
import { SourceTip } from "../components/SourceTip";
import { SubChart } from "../components/SubChart";
import { useLiveEvents } from "../hooks/useLiveEvents";
import { INDICATOR_TOGGLES, patternTimeframe, useIndicatorEvents, useIndicators, useMoveLinks, usePatterns } from "../lib/analysis";
import { forecastTimeframe, scenarioLevels, useForecast, validSteps } from "../lib/forecast";
import { alignSeries, toTime } from "../lib/chartData";
import { ChartGroup } from "../lib/chartSync";
import { api, type BarsResponse, type InstrumentWithQuote } from "../lib/api";
import { formatDateTime, formatPercent, formatPrice } from "../lib/format";
import { useInstrumentNews } from "../lib/news";
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
    if (e.type === "detection" && String(e.payload.instrument_id) === id) {
      qc.invalidateQueries({ queryKey: e.payload.category === "indicator_event" ? ["indicator-events", id] : ["patterns", id] });
    }
    if (e.type === "quote" && String(e.payload.instrument_id) === id) {
      qc.invalidateQueries({ queryKey: ["instrument", id] });
      qc.invalidateQueries({ queryKey: ["bars", id] });
    }
  });

  const [selected, setSelected] = useState<number[]>([]);
  const firstBar = bars.data?.bars[0]?.ts_utc;
  const news = useInstrumentNews(id, firstBar ? firstBar.slice(0, 13) + ":00:00Z" : undefined);
  const shown = useMemo(() => windowBars(bars.data?.bars ?? [], range), [bars.data, range]);
  const markers = useMemo<NewsMarker[]>(() => {
    if (shown.length === 0) return [];
    const from = new Date(shown[0].ts_utc).getTime();
    return (news.data?.items ?? [])
      .filter((c) => new Date(c.first_published_at).getTime() >= from)
      .map((c) => ({ clusterId: c.id, ts: c.first_published_at, title: c.canonical_title }));
  }, [news.data, shown]);
  const selectedClusters = (news.data?.items ?? []).filter((c) => selected.includes(c.id));

  // Phase 3: Indikatoren, Muster, Ereignisse, Bewegungen mit zeitlich passenden Meldungen.
  const startIso = shown[0]?.ts_utc;
  const [activeInd, setActiveInd] = useState<string[]>([]);
  const [selectedPattern, setSelectedPattern] = useState<number | null>(null);
  const [showInvalid, setShowInvalid] = useState(false);
  const group = useMemo(() => new ChartGroup(), []);
  const ind = useIndicators(id, range.timeframe, startIso, activeInd);
  const events = useIndicatorEvents(id, range.timeframe, startIso);
  const moves = useMoveLinks(id, range.timeframe, startIso);
  const patTf = patternTimeframe(range.timeframe);
  const patterns = usePatterns(id, patTf, startIso, showInvalid);
  const detections = patterns.data?.detections ?? [];
  const selectedDetection = detections.find((d) => d.id === selectedPattern) ?? null;
  const [showForecast, setShowForecast] = useState(true);
  const [horizon, setHorizon] = useState(20);
  const fcTf = forecastTimeframe(range.timeframe);
  const forecast = useForecast(id, fcTf, horizon, showForecast);
  const forecastSteps = useMemo(() => validSteps(forecast.data?.steps ?? []), [forecast.data]);
  const levels = useMemo(() => scenarioLevels(selectedDetection), [selectedDetection]);
  const toggleInd = (key: string) => setActiveInd((a) => (a.includes(key) ? a.filter((k) => k !== key) : [...a, key]));
  const overlays = useMemo<PriceOverlay[]>(() => {
    if (!ind.data || shown.length === 0) return [];
    const barTimes = shown.map((b) => toTime(b.ts_utc));
    const colors: Record<string, string> = { sma: "#facc15", ema: "#fb923c", bollinger: "#94a3b8" };
    const out: PriceOverlay[] = [];
    ind.data.indicators.filter((i) => i.panel === "price" && activeInd.length > 0).forEach((i, n) => {
      const line = (name: keyof typeof i.lines, dashed = false) => out.push({ id: `${i.key}-${name}`, color: colors[i.type] ?? "#e2e8f0", dashed: dashed || i.type === "ema" && n % 2 === 1,
        data: alignSeries(ind.data!.timestamps, i.lines[name], barTimes) });
      if (i.type === "bollinger") { line("upper", true); line("middle"); line("lower", true); } else line("value");
    });
    return out;
  }, [ind.data, shown, activeInd]);
  const ownPanels = (ind.data?.indicators ?? []).filter((i) => i.panel === "own" && activeInd.length > 0);
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

      <div role="group" aria-label="Indikatoren" className="mb-3 flex flex-wrap items-center gap-2" data-testid="indicator-toggles">
        <span className="text-sm text-slate-400">Indikatoren:</span>
        {INDICATOR_TOGGLES.map((t) => (
          <label key={t.key} className={`cursor-pointer rounded border px-3 py-1 text-sm ${activeInd.includes(t.key) ? "border-sky-500 bg-sky-900" : "border-slate-700"}`}>
            <input type="checkbox" className="sr-only" checked={activeInd.includes(t.key)} onChange={() => toggleInd(t.key)} />{t.label}
          </label>
        ))}
      </div>

      <div className="mb-3 flex flex-wrap items-center gap-2">
        <label className={`cursor-pointer rounded border px-3 py-1 text-sm ${showForecast ? "border-sky-500 bg-sky-900" : "border-slate-700"}`}>
          <input type="checkbox" className="sr-only" checked={showForecast} onChange={() => setShowForecast((v) => !v)} />Prognosekorridor
        </label>
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
          <PriceChart bars={shown} kind={kind} intraday={intraday} markers={markers} onMarkerClick={setSelected}
            overlays={overlays} patterns={detections} zones={patterns.data?.zones ?? []} events={events.data?.events ?? []}
            selectedPatternId={selectedPattern} onPatternClick={setSelectedPattern} group={group}
            forecast={showForecast ? forecastSteps : []} scenarioLevels={showForecast ? levels : []} />
          {ownPanels.map((i) => (
            <div key={i.key} className="mt-2">
              <p className="text-xs text-slate-400">{i.label}</p>
              <SubChart series={i} timestamps={ind.data!.timestamps} bars={shown} intraday={intraday} group={group} />
            </div>
          ))}
          {activeInd.length > 0 && (
            <div className="mt-2 text-xs text-slate-400" data-testid="indicator-info">
              {ind.isLoading && <p>Lade Indikatoren …</p>}
              {ind.isError && <p role="alert" className="text-rose-300">Indikatoren konnten nicht geladen werden (Backend nicht erreichbar).</p>}
              {ind.data?.empty_reason && <p className="text-amber-300" data-testid="no-indicators">Keine Indikatoren: {ind.data.empty_reason}</p>}
              {ind.data && !ind.data.empty_reason && (
                <>
                  <p>Berechnet aus den Kursdaten der Quelle{ind.data.sources.length === 1 ? "" : "n"} {ind.data.sources.map((s) => s.name).join(", ")}; Verfahren {ind.data.algo_version}; Kerzen abgerufen {ind.data.bars_fetched_at ? formatDateTime(ind.data.bars_fetched_at) : "(Zeitpunkt nicht angegeben)"}.</p>
                  <ul className="mt-1 list-disc pl-5">{ind.data.indicators.map((i) => <li key={i.key}>{i.label}{i.formula ? `: ${i.formula}` : ""}</li>)}</ul>
                  {activeInd.some((k) => !ind.data!.indicators.some((i) => i.key === INDICATOR_TOGGLES.find((t) => t.key === k)?.seriesKey)) && <p className="text-amber-300">Für einen gewählten Indikator hat das Backend keine Werte geliefert (zu wenige Kerzen oder nicht berechnet).</p>}
                  <div className="mt-1 flex flex-wrap gap-2">{ind.data.sources.map((s) => <SourceTip key={s.key} source={s} fetchedAt={ind.data!.bars_fetched_at ?? ""} />)}</div>
                </>
              )}
            </div>
          )}
          <p className="mt-2 text-xs text-slate-400" data-testid="last-update">
            Letzter Datenpunkt: {last && formatDateTime(last.ts_utc)}
            {lastUpdate && ` · Zuletzt im Dashboard aktualisiert: ${formatDateTime(lastUpdate)}`}
            {shown.some((b) => b.is_demo) && " · Beispieldaten (Demo-Modus)"}
          </p>
          {last && <SourceTip source={last.source} ts={last.ts_utc} fetchedAt={last.fetched_at} />}
        </>
      )}

      {showForecast && (
        <div className="mt-6" data-testid="chart-forecast">
          {fcTf == null
            ? <p className="text-sm text-amber-300" data-testid="no-forecast">Prognosekorridore gibt es nur für Tageskerzen. Für den Zeitraum {range.label} (Kerzen {range.timeframe}) wird keiner berechnet.</p>
            : <ForecastPanel data={forecast.data} loading={forecast.isLoading} error={forecast.isError} horizon={horizon} onHorizon={setHorizon} currency={inst.data?.currency ?? "EUR"} pattern={selectedDetection} />}
        </div>
      )}

      <div className="mt-6" data-testid="chart-patterns">
        <div className="mb-2 flex flex-wrap items-center gap-3">
          <h2 className="font-semibold">Erkannte Chartmuster</h2>
          <label className="text-xs text-slate-300"><input type="checkbox" checked={showInvalid} onChange={(e) => setShowInvalid(e.target.checked)} /> auch ungültige Muster zeigen</label>
        </div>
        {patTf == null && <p className="text-sm text-amber-300" data-testid="no-patterns">Die Mustererkennung arbeitet nur mit Tages- und Stundenkerzen. Für den Zeitraum {range.label} (Kerzen {range.timeframe}) werden keine Muster erkannt.</p>}
        {patterns.isError && <p role="alert" className="text-rose-300">Muster konnten nicht geladen werden (Backend nicht erreichbar).</p>}
        {patterns.data?.empty_reason && <p className="text-sm text-amber-300" data-testid="no-patterns">Keine Muster: {patterns.data.empty_reason}</p>}
        {detections.length > 0 && <PatternList items={detections} selectedId={selectedPattern} onSelect={setSelectedPattern} />}
        {patterns.data && <ZoneList zones={patterns.data.zones} />}
        {selectedDetection && <div className="mt-4"><PatternPanel p={selectedDetection} onClose={() => setSelectedPattern(null)} /></div>}
        {detections.length > 0 && !selectedDetection && <p className="mt-2 text-xs text-slate-400">Ein Muster wählen (Liste oder Klick im Chart), um die vollständige Erklärung zu sehen.</p>}
      </div>

      <div className="mt-6" data-testid="chart-events">
        <h2 className="mb-2 font-semibold">Indikator-Ereignisse</h2>
        {events.isError && <p role="alert" className="text-rose-300">Ereignisse konnten nicht geladen werden (Backend nicht erreichbar).</p>}
        {events.data?.empty_reason && <p className="text-sm text-amber-300" data-testid="no-events">Keine Ereignisse: {events.data.empty_reason}</p>}
        {events.data && events.data.events.length > 0 && <><p className="mb-2 text-xs text-slate-400">Marker im Chart: GC Golden Cross, DC Death Cross, RSI Divergenz, BB Bollinger-Ausbruch, Vol Volumenspitze. Die Ereignisse beschreiben nur die Lage der Werte.</p><EventList events={events.data.events} /></>}
      </div>

      <div className="mt-6" data-testid="chart-moves">
        <h2 className="mb-2 font-semibold">Auffällige Kursbewegungen und zeitlich passende Meldungen</h2>
        {moves.isError && <p role="alert" className="text-rose-300">Kursbewegungen konnten nicht geladen werden (Backend nicht erreichbar).</p>}
        {moves.data?.empty_reason && <p className="text-sm text-amber-300" data-testid="no-moves">Keine Auswertung: {moves.data.empty_reason}</p>}
        {moves.data && moves.data.moves.length > 0 && <MoveList moves={moves.data.moves} note={moves.data.note} onOpenNews={(cid) => setSelected([cid])} />}
      </div>

      <div className="mt-6" data-testid="chart-news">
        <h2 className="mb-2 font-semibold">Nachrichten-Marker</h2>
        {news.isError && <p role="alert" className="text-rose-300">Nachrichten konnten nicht geladen werden (Backend nicht erreichbar).</p>}
        {news.data?.empty_reason && <p className="text-sm text-amber-300" data-testid="no-markers">Keine Nachrichten-Marker: {news.data.empty_reason}</p>}
        {news.data && !news.data.empty_reason && markers.length === 0 && <p className="text-sm text-slate-400">Für den gezeigten Zeitraum liegen keine Meldungen zu diesem Instrument vor.</p>}
        {markers.length > 0 && <p className="text-xs text-slate-400">Marker „N“ = Meldung zeitlich an dieser Kerze (keine Aussage über eine Ursache der Kursbewegung). Klick auf einen Marker zeigt die Meldung mit allen Quellen.</p>}
        <div className="mt-3 space-y-4">{selectedClusters.map((c) => <NewsClusterCard key={c.id} cluster={c} />)}</div>
      </div>
    </section>
  );
}
