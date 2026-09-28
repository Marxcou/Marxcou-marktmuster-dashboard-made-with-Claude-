import type { Bar } from "./api";

export interface Range { label: string; timeframe: "1m" | "5m" | "1h" | "1d"; days: number }

export const RANGES: Range[] = [
  { label: "1T", timeframe: "5m", days: 1 },
  { label: "1W", timeframe: "1h", days: 7 },
  { label: "1M", timeframe: "1d", days: 31 },
  { label: "6M", timeframe: "1d", days: 183 },
  { label: "1J", timeframe: "1d", days: 366 },
  { label: "5J", timeframe: "1d", days: 1830 },
];

const DAY_MS = 86_400_000;

// Abfragebeginn mit Puffer für Wochenenden/Feiertage.
export const rangeStart = (r: Range, now = Date.now()) => new Date(now - (r.days + 5) * DAY_MS).toISOString();

// Das Fenster hängt am letzten vorhandenen Datenpunkt, nicht an der Uhrzeit: so zeigt "1T" auch am Wochenende den letzten Handelstag.
export function windowBars(bars: Bar[], r: Range): Bar[] {
  if (bars.length === 0) return bars;
  const last = new Date(bars[bars.length - 1].ts_utc).getTime();
  return bars.filter((b) => new Date(b.ts_utc).getTime() >= last - r.days * DAY_MS);
}
