import type { IChartApi } from "lightweight-charts";

// Hält den sichtbaren Zeitbereich mehrerer Diagramme (Kurs, RSI, MACD) synchron. Alle Diagramme bekommen je Kerze einen Zeitpunkt (ggf. leer), damit die logischen Indizes übereinstimmen.
export class ChartGroup {
  private charts = new Set<IChartApi>();
  private busy = false;

  add(chart: IChartApi): () => void {
    this.charts.add(chart);
    const handler = (range: { from: number; to: number } | null) => {
      if (this.busy || !range) return;
      this.busy = true;
      try {
        for (const c of this.charts) if (c !== chart) c.timeScale().setVisibleLogicalRange(range);
      } finally {
        this.busy = false;
      }
    };
    chart.timeScale().subscribeVisibleLogicalRangeChange(handler);
    return () => {
      this.charts.delete(chart);
      try { chart.timeScale().unsubscribeVisibleLogicalRangeChange(handler); } catch { /* Diagramm bereits entfernt */ }
    };
  }
}
