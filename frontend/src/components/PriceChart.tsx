import { ColorType, CrosshairMode, createChart, LineStyle, type IChartApi, type ISeriesApi, type SeriesMarker, type Time, type UTCTimestamp } from "lightweight-charts";
import { useEffect, useRef } from "react";
import type { Bar, ForecastExamplePath, ForecastStep, IndicatorEvent, PatternDetection, SRZone } from "../lib/api";
import { BAND_FILL, BANDS, bandSeries, EXAMPLE_COLOR, MEDIAN_COLOR, medianSeries, validExamplePaths, validSteps, type ScenarioLevel } from "../lib/forecast";
import { EVENT_SHORT } from "../lib/analysis";
import { type AlignedPoint, ascendingUnique, priceOnLine, snapTime, toTime } from "../lib/chartData";
import type { ChartGroup } from "../lib/chartSync";

export interface NewsMarker { clusterId: number; ts: string; title: string }
export interface PriceOverlay { id: string; color: string; dashed?: boolean; data: AlignedPoint[] }

export type ChartKind = "candles" | "line";

const berlin = (opts: Intl.DateTimeFormatOptions) => new Intl.DateTimeFormat("de-DE", { timeZone: "Europe/Berlin", ...opts });
const PATTERN_COLOR = "#a78bfa";
const EVENT_COLOR = "#22d3ee";
const BG = "#0f172a";

export function baseChartOptions(intraday: boolean, height: number) {
  return {
    autoSize: true,
    height,
    layout: { background: { type: ColorType.Solid, color: "#0f172a" }, textColor: "#cbd5e1" },
    grid: { vertLines: { color: "#1e293b" }, horzLines: { color: "#1e293b" } },
    crosshair: { mode: CrosshairMode.Normal },
    rightPriceScale: { borderColor: "#334155" },
    timeScale: {
      borderColor: "#334155",
      timeVisible: intraday,
      tickMarkFormatter: (t: number) => (intraday ? berlin({ hour: "2-digit", minute: "2-digit" }) : berlin({ day: "2-digit", month: "2-digit" })).format(new Date(t * 1000)),
    },
    localization: {
      locale: "de-DE",
      timeFormatter: (t: number) => berlin({ dateStyle: "medium", ...(intraday ? { timeStyle: "short" } : {}) }).format(new Date(t * 1000)),
      priceFormatter: (p: number) => new Intl.NumberFormat("de-DE", { minimumFractionDigits: 2, maximumFractionDigits: 2 }).format(p),
    },
  };
}

export function PriceChart({ bars, kind, intraday, markers = [], onMarkerClick, overlays = [], patterns = [], zones = [], events = [], selectedPatternId = null, onPatternClick, group, forecast = [], scenarioLevels = [], medianLine = false, examplePaths = [] }: {
  bars: Bar[]; kind: ChartKind; intraday: boolean; markers?: NewsMarker[]; onMarkerClick?: (clusterIds: number[]) => void;
  overlays?: PriceOverlay[]; patterns?: PatternDetection[]; zones?: SRZone[]; events?: IndicatorEvent[];
  selectedPatternId?: number | null; onPatternClick?: (id: number) => void; group?: ChartGroup;
  forecast?: ForecastStep[]; scenarioLevels?: ScenarioLevel[]; medianLine?: boolean; examplePaths?: ForecastExamplePath[];
}) {
  const clickRef = useRef(onMarkerClick);
  clickRef.current = onMarkerClick;
  const patternClickRef = useRef(onPatternClick);
  patternClickRef.current = onPatternClick;
  const ref = useRef<HTMLDivElement>(null);
  const chartRef = useRef<IChartApi | null>(null);
  const rangeRef = useRef<{ key: string; range: { from: number; to: number } } | null>(null);

  useEffect(() => {
    if (!ref.current) return;
    const chart = createChart(ref.current, baseChartOptions(intraday, 420));
    chartRef.current = chart;
    const barTimes = bars.map((b) => toTime(b.ts_utc));
    // Erscheint oder verschwindet der Korridor, wird neu eingepasst, damit er nicht rechts außerhalb des Sichtbereichs liegt.
    const barsKey = `${bars.length}:${bars[0]?.ts_utc}:${kind}:${validSteps(forecast).length > 0}`;

    let main: ISeriesApi<"Candlestick"> | ISeriesApi<"Line">;
    if (kind === "candles") {
      const s = chart.addCandlestickSeries({ upColor: "#34d399", downColor: "#fb7185", wickUpColor: "#34d399", wickDownColor: "#fb7185", borderVisible: false });
      s.setData(bars.map((b) => ({ time: toTime(b.ts_utc), open: b.open, high: b.high, low: b.low, close: b.close })));
      main = s;
    } else {
      const s = chart.addLineSeries({ color: "#38bdf8", lineWidth: 2 });
      s.setData(bars.map((b) => ({ time: toTime(b.ts_utc), value: b.close })));
      main = s;
    }

    // Indikator-Linien im Kursfenster (Werte aus dem Backend, nichts wird ergänzt).
    for (const o of overlays) {
      const s = chart.addLineSeries({ color: o.color, lineWidth: 1, lineStyle: o.dashed ? LineStyle.Dashed : LineStyle.Solid, lastValueVisible: false, priceLineVisible: false, crosshairMarkerVisible: false });
      s.setData(o.data);
    }

    // Unterstützungs- und Widerstandszonen als gestrichelte Ober- und Untergrenze.
    for (const z of zones) {
      main.createPriceLine({ price: z.upper, color: "#94a3b8", lineStyle: LineStyle.Dashed, lineWidth: 1, axisLabelVisible: false, title: z.kind_label });
      main.createPriceLine({ price: z.lower, color: "#94a3b8", lineStyle: LineStyle.Dashed, lineWidth: 1, axisLabelVisible: false, title: "" });
    }

    // Muster: Linie durch die Schlüsselpunkte, Begrenzungslinien; beim gewählten Muster zusätzlich Bestätigungs- und Ungültigkeitsniveau.
    const lastBarTime = barTimes[barTimes.length - 1];
    for (const p of patterns) {
      const sel = p.id === selectedPatternId;
      const width = sel ? 3 : 1;
      const pts = p.key_points.flatMap((k) => { const t = snapTime(barTimes, k.ts); return t == null ? [] : [{ time: t, value: k.price }]; });
      if (pts.length > 1) {
        const s = chart.addLineSeries({ color: PATTERN_COLOR, lineWidth: width as 1 | 3, lastValueVisible: false, priceLineVisible: false, crosshairMarkerVisible: false });
        s.setData(ascendingUnique(pts));
      }
      for (const l of p.lines) {
        const a = { t: toTime(l.start.ts) as number, price: l.start.price };
        const b = { t: toTime(l.end.ts) as number, price: l.end.price };
        const ta = snapTime(barTimes, l.start.ts), tb = snapTime(barTimes, l.end.ts);
        if (ta == null || tb == null) continue;
        const points = [{ time: ta, value: l.start.price }, { time: tb, value: l.end.price }];
        if (l.extend_right && lastBarTime > tb) points.push({ time: lastBarTime, value: priceOnLine(a, b, lastBarTime) });
        const s = chart.addLineSeries({ color: PATTERN_COLOR, lineWidth: (sel ? 2 : 1), lineStyle: LineStyle.Dashed, lastValueVisible: false, priceLineVisible: false, crosshairMarkerVisible: false });
        s.setData(ascendingUnique(points));
      }
      if (sel) {
        if (p.confirmation_level != null) main.createPriceLine({ price: p.confirmation_level, color: PATTERN_COLOR, lineStyle: LineStyle.Solid, lineWidth: 1, axisLabelVisible: true, title: "Bestätigungsniveau" });
        if (p.invalidation_level != null) main.createPriceLine({ price: p.invalidation_level, color: "#f472b6", lineStyle: LineStyle.Solid, lineWidth: 1, axisLabelVisible: true, title: "Ungültigkeitsniveau" });
      }
    }

    // Prognosekorridor (Grundregel 4): Linien (Median, Beispielpfade) nur innerhalb der Bänder, nie allein. Jedes Band wird als Paar undurchsichtiger Flächen gezeichnet
    // (oben füllen, unten mit der Farbe des äußeren Bereichs überdecken), damit sich die 50/80/95-%-Bereiche sauber verschachteln.
    const fsteps = validSteps(forecast);
    const lastBar = bars[bars.length - 1];
    if (fsteps.length > 0 && lastBar) {
      const start = toTime(lastBar.ts_utc);
      const future = (pts: { ts: string; v: number }[]) => ascendingUnique([{ time: start, value: lastBar.close }, ...pts.map((p) => ({ time: toTime(p.ts), value: p.v })).filter((p) => p.time > start)]);
      const area = (color: string, data: { time: UTCTimestamp; value: number }[]) => {
        const s = chart.addAreaSeries({ topColor: color, bottomColor: color, lineColor: color, lineWidth: 1, lastValueVisible: false, priceLineVisible: false, crosshairMarkerVisible: false });
        s.setData(data);
      };
      const [b95, b80, b50] = BANDS.map((b) => ({ up: future(bandSeries(fsteps, b).map((x) => ({ ts: x.ts, v: x.upper }))), lo: future(bandSeries(fsteps, b).map((x) => ({ ts: x.ts, v: x.lower }))) }));
      area(BAND_FILL[95], b95.up); area(BAND_FILL[80], b80.up); area(BAND_FILL[50], b50.up);
      area(BAND_FILL[80], b50.lo); area(BAND_FILL[95], b80.lo); area(BG, b95.lo);
      // Beispielpfade dünn und blass, der mittlere Verlauf darüber gestrichelt. Keine Beschriftung am Endpunkt, damit er nicht wie ein Zielwert wirkt.
      const line = (color: string, width: 1 | 2, dashed: boolean, data: { time: UTCTimestamp; value: number }[]) => {
        const s = chart.addLineSeries({ color, lineWidth: width, lineStyle: dashed ? LineStyle.Dashed : LineStyle.Solid, lastValueVisible: false, priceLineVisible: false, crosshairMarkerVisible: false });
        s.setData(data);
      };
      for (const p of validExamplePaths(examplePaths)) line(EXAMPLE_COLOR, 1, false, future(p.steps.map((s) => ({ ts: s.ts, v: s.close }))));
      if (medianLine) line(MEDIAN_COLOR, 2, true, future(medianSeries(fsteps)));
      // Szenario-Niveaus des gewählten Musters laufen bis zum Ende des Horizonts, damit sie am Korridor ablesbar sind.
      const end = toTime(fsteps[fsteps.length - 1].ts);
      if (end != null && end > start) {
        for (const l of scenarioLevels) {
          const s = chart.addLineSeries({ color: l.color, lineWidth: 1, lineStyle: LineStyle.Dashed, lastValueVisible: true, priceLineVisible: false, crosshairMarkerVisible: false, title: l.label });
          s.setData([{ time: start, value: l.price }, { time: end, value: l.price }]);
        }
      }
    }

    // Marker: Nachrichten (nur zeitliches Zusammenfallen, keine Aussage über Ursache), Indikator-Ereignisse, Musterbeginn.
    const newsByTime = new Map<number, number[]>();
    for (const m of markers) {
      const t = snapTime(barTimes, m.ts);
      if (t != null) newsByTime.set(t, [...(newsByTime.get(t) ?? []), m.clusterId]);
    }
    const all: SeriesMarker<Time>[] = [...newsByTime.entries()].map(([t, ids]) => ({
      time: t as UTCTimestamp, position: "aboveBar", shape: "circle", color: "#f59e0b", text: ids.length > 1 ? String(ids.length) : "N",
    }));
    for (const e of events) {
      const t = snapTime(barTimes, e.ts);
      if (t != null) all.push({ time: t as UTCTimestamp, position: "belowBar", shape: "square", color: EVENT_COLOR, text: EVENT_SHORT[e.type] ?? "E" });
    }
    for (const p of patterns) {
      const t = snapTime(barTimes, p.start_ts);
      if (t != null) all.push({ time: t as UTCTimestamp, position: "belowBar", shape: "square", color: PATTERN_COLOR, text: p.id === selectedPatternId ? p.name : "M" });
    }
    all.sort((a, b) => (a.time as number) - (b.time as number));
    main.setMarkers(all);

    chart.subscribeClick((param) => {
      if (param.time == null) return;
      const t = param.time as number;
      const ids = newsByTime.get(t);
      if (ids) clickRef.current?.(ids);
      // Klick innerhalb des Zeitraums eines Musters wählt es aus (das zuletzt beginnende gewinnt).
      const hit = patterns.filter((p) => toTime(p.start_ts) <= t && t <= toTime(p.end_ts)).sort((a, b) => toTime(a.start_ts) - toTime(b.start_ts)).pop();
      if (hit) patternClickRef.current?.(hit.id);
    });

    // Volumen nur dort, wo die Quelle es liefert; fehlende Werte werden nicht ergänzt.
    const vol = chart.addHistogramSeries({ priceFormat: { type: "volume" }, priceScaleId: "vol", color: "#64748b" });
    chart.priceScale("vol").applyOptions({ scaleMargins: { top: 0.8, bottom: 0 } });
    vol.setData(bars.filter((b) => b.volume != null).map((b) => ({ time: toTime(b.ts_utc), value: b.volume as number, color: b.close >= b.open ? "#065f46" : "#9f1239" })));

    // Zoom bleibt beim Wechsel von Auswahl oder Indikatoren erhalten, solange es dieselben Kerzen sind.
    const saved = rangeRef.current;
    if (saved && saved.key === barsKey) chart.timeScale().setVisibleLogicalRange(saved.range);
    else chart.timeScale().fitContent();
    const removeFromGroup = group?.add(chart);

    return () => {
      const r = chart.timeScale().getVisibleLogicalRange();
      if (r) rangeRef.current = { key: barsKey, range: r };
      removeFromGroup?.();
      chart.remove();
      chartRef.current = null;
    };
  }, [bars, kind, intraday, markers, overlays, patterns, zones, events, selectedPatternId, group, forecast, scenarioLevels, medianLine, examplePaths]);

  return <div ref={ref} data-testid="price-chart" className="w-full" role="img" aria-label="Kursdiagramm" />;
}
