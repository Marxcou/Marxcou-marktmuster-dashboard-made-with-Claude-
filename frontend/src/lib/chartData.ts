import type { UTCTimestamp } from "lightweight-charts";

export type AlignedPoint = { time: UTCTimestamp; value: number } | { time: UTCTimestamp };

export const toTime = (iso: string) => Math.floor(new Date(iso).getTime() / 1000) as UTCTimestamp;

// Hängt einen Zeitpunkt an die letzte Kerze, die nicht nach ihm beginnt. Liegt er vor der ersten Kerze, gibt es keine Position (kein Raten).
export function snapTime(barTimes: number[], iso: string): number | null {
  const t = toTime(iso);
  if (barTimes.length === 0 || t < barTimes[0]) return null;
  let lo = 0, hi = barTimes.length - 1;
  while (lo < hi) {
    const mid = (lo + hi + 1) >> 1;
    if (barTimes[mid] <= t) lo = mid; else hi = mid - 1;
  }
  return barTimes[lo];
}

// Eine Indikatorlinie auf die Kerzenzeiten legen: Werte, die es nicht gibt (Einschwingphase), bleiben leer statt ergänzt zu werden.
export function alignSeries(timestamps: string[], values: (number | null)[] | undefined, barTimes: number[]): AlignedPoint[] {
  const byTime = new Map<number, number>();
  if (values) timestamps.forEach((ts, i) => { const v = values[i]; if (v != null) byTime.set(toTime(ts), v); });
  return barTimes.map((t) => {
    const v = byTime.get(t);
    return v == null ? { time: t as UTCTimestamp } : { time: t as UTCTimestamp, value: v };
  });
}

// Wert einer Geraden durch zwei Punkte zum Zeitpunkt t (Sekunden).
export const priceOnLine = (a: { t: number; price: number }, b: { t: number; price: number }, t: number) =>
  b.t === a.t ? b.price : a.price + ((b.price - a.price) * (t - a.t)) / (b.t - a.t);

// Punkte für eine Linienserie: aufsteigend und ohne doppelte Zeiten (letzter Wert gewinnt).
export function ascendingUnique(points: { time: number; value: number }[]): { time: UTCTimestamp; value: number }[] {
  const m = new Map<number, number>();
  for (const p of points) m.set(p.time, p.value);
  return [...m.entries()].sort((x, y) => x[0] - y[0]).map(([time, value]) => ({ time: time as UTCTimestamp, value }));
}
