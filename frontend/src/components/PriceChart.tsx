import { ColorType, CrosshairMode, createChart, type IChartApi, type UTCTimestamp } from "lightweight-charts";
import { useEffect, useRef } from "react";
import type { Bar } from "../lib/api";

export type ChartKind = "candles" | "line";

const berlin = (opts: Intl.DateTimeFormatOptions) => new Intl.DateTimeFormat("de-DE", { timeZone: "Europe/Berlin", ...opts });
const toTime = (iso: string) => Math.floor(new Date(iso).getTime() / 1000) as UTCTimestamp;

export function PriceChart({ bars, kind, intraday }: { bars: Bar[]; kind: ChartKind; intraday: boolean }) {
  const ref = useRef<HTMLDivElement>(null);
  const chartRef = useRef<IChartApi | null>(null);

  useEffect(() => {
    if (!ref.current) return;
    const chart = createChart(ref.current, {
      autoSize: true,
      height: 420,
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
    });
    chartRef.current = chart;

    if (kind === "candles") {
      const s = chart.addCandlestickSeries({ upColor: "#34d399", downColor: "#fb7185", wickUpColor: "#34d399", wickDownColor: "#fb7185", borderVisible: false });
      s.setData(bars.map((b) => ({ time: toTime(b.ts_utc), open: b.open, high: b.high, low: b.low, close: b.close })));
    } else {
      const s = chart.addLineSeries({ color: "#38bdf8", lineWidth: 2 });
      s.setData(bars.map((b) => ({ time: toTime(b.ts_utc), value: b.close })));
    }
    // Volumen nur dort, wo die Quelle es liefert; fehlende Werte werden nicht ergänzt.
    const vol = chart.addHistogramSeries({ priceFormat: { type: "volume" }, priceScaleId: "vol", color: "#64748b" });
    chart.priceScale("vol").applyOptions({ scaleMargins: { top: 0.8, bottom: 0 } });
    vol.setData(bars.filter((b) => b.volume != null).map((b) => ({ time: toTime(b.ts_utc), value: b.volume as number, color: b.close >= b.open ? "#065f46" : "#9f1239" })));
    chart.timeScale().fitContent();

    return () => { chart.remove(); chartRef.current = null; };
  }, [bars, kind, intraday]);

  return <div ref={ref} data-testid="price-chart" className="w-full" role="img" aria-label="Kursdiagramm" />;
}
