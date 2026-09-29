import { createChart, LineStyle } from "lightweight-charts";
import { useEffect, useRef } from "react";
import type { Bar, IndicatorSeries } from "../lib/api";
import { alignSeries, toTime } from "../lib/chartData";
import type { ChartGroup } from "../lib/chartSync";
import { baseChartOptions } from "./PriceChart";

// Eigenes Teilfenster für RSI bzw. MACD, zeitlich gekoppelt an den Kurschart.
export function SubChart({ series, timestamps, bars, intraday, group }: { series: IndicatorSeries; timestamps: string[]; bars: Bar[]; intraday: boolean; group: ChartGroup }) {
  const ref = useRef<HTMLDivElement>(null);
  useEffect(() => {
    if (!ref.current) return;
    const chart = createChart(ref.current, baseChartOptions(intraday, 140));
    const barTimes = bars.map((b) => toTime(b.ts_utc));
    if (series.type === "macd") {
      const hist = alignSeries(timestamps, series.lines.histogram, barTimes).map((p) => ("value" in p ? { ...p, color: p.value >= 0 ? "#0e7490" : "#9d174d" } : p));
      chart.addHistogramSeries({ priceLineVisible: false, lastValueVisible: false }).setData(hist);
      chart.addLineSeries({ color: "#38bdf8", lineWidth: 1, priceLineVisible: false, lastValueVisible: false }).setData(alignSeries(timestamps, series.lines.macd, barTimes));
      chart.addLineSeries({ color: "#f59e0b", lineWidth: 1, priceLineVisible: false, lastValueVisible: false }).setData(alignSeries(timestamps, series.lines.signal, barTimes));
    } else {
      const s = chart.addLineSeries({ color: "#a3e635", lineWidth: 1, priceLineVisible: false, lastValueVisible: false });
      s.setData(alignSeries(timestamps, series.lines.value, barTimes));
      for (const r of series.reference_lines ?? []) s.createPriceLine({ price: r, color: "#64748b", lineStyle: LineStyle.Dotted, lineWidth: 1, axisLabelVisible: true, title: "" });
    }
    chart.timeScale().fitContent();
    const remove = group.add(chart);
    return () => { remove(); chart.remove(); };
  }, [series, timestamps, bars, intraday, group]);
  return <div ref={ref} data-testid={`subchart-${series.key}`} className="w-full" role="img" aria-label={series.label} />;
}
