import { useQuery } from "@tanstack/react-query";
import {
  api, PENDING_POLL_MS, type IndicatorEventsResponse, type IndicatorEventType, type IndicatorsResponse, type MoveLinksResponse, type PatternCounts, type PatternsResponse,
} from "./api";

export const ANALYSIS_MISSING = "Die Analyse-Schnittstelle des Backends ist noch nicht verfügbar. Es werden keine Daten angezeigt.";

// 404 heißt: Endpunkt noch nicht vorhanden. Das ist ein Leerzustand mit Grund, kein Fehler und kein Platzhalter (Grundregel 6).
async function orMissing<T extends { empty_reason: string | null }>(path: string, empty: T): Promise<T> {
  try {
    return await api<T>(path);
  } catch (e) {
    if (e instanceof Error && e.message === "HTTP 404") return { ...empty, empty_reason: ANALYSIS_MISSING };
    throw e;
  }
}

// Die Mustererkennung arbeitet nur auf Tages- und Stundenkerzen (Vertrag 3B).
export const patternTimeframe = (tfm: string) => (tfm === "1d" || tfm === "1h" ? tfm : null);

export interface IndicatorToggle { key: string; label: string; param: string; panel: "price" | "own"; seriesKey: string }
export const INDICATOR_TOGGLES: IndicatorToggle[] = [
  { key: "sma20", label: "SMA 20", param: "sma=20", panel: "price", seriesKey: "sma_20" },
  { key: "sma50", label: "SMA 50", param: "sma=50", panel: "price", seriesKey: "sma_50" },
  { key: "ema20", label: "EMA 20", param: "ema=20", panel: "price", seriesKey: "ema_20" },
  { key: "ema50", label: "EMA 50", param: "ema=50", panel: "price", seriesKey: "ema_50" },
  { key: "bb", label: "Bollinger-Bänder (20, 2)", param: "bb=20,2", panel: "price", seriesKey: "bb_20_2" },
  { key: "rsi", label: "RSI (14)", param: "rsi=14", panel: "own", seriesKey: "rsi_14" },
  { key: "macd", label: "MACD (12, 26, 9)", param: "macd=12,26,9", panel: "own", seriesKey: "macd_12_26_9" },
];

// sma/ema mit mehreren Perioden werden zu einem kommaseparierten Parameter zusammengefasst.
export function indicatorQuery(active: string[]): string {
  const groups = new Map<string, string[]>();
  for (const t of INDICATOR_TOGGLES) {
    if (!active.includes(t.key)) continue;
    const [name, val] = t.param.split("=");
    groups.set(name, [...(groups.get(name) ?? []), val]);
  }
  return [...groups.entries()].map(([n, v]) => `${n}=${n === "sma" || n === "ema" ? v.join(",") : v[0]}`).join("&");
}

export const useIndicators = (id: string | undefined, timeframe: string, start: string | undefined, active: string[]) => {
  const q = indicatorQuery(active);
  return useQuery({
    queryKey: ["indicators", id, timeframe, start, q], enabled: !!id && q !== "",
    queryFn: () => orMissing<IndicatorsResponse>(`/instruments/${id}/indicators?timeframe=${timeframe}${start ? `&start=${encodeURIComponent(start)}` : ""}&${q}`,
      { instrument_id: Number(id), timeframe, algo_version: "", timestamps: [], indicators: [], sources: [], bars_fetched_at: null, empty_reason: null }),
    refetchInterval: 60_000,
  });
};

export const useIndicatorEvents = (id: string | undefined, timeframe: string, since: string | undefined) =>
  useQuery({
    queryKey: ["indicator-events", id, timeframe, since], enabled: !!id,
    queryFn: () => orMissing<IndicatorEventsResponse>(`/instruments/${id}/indicator-events?timeframe=${timeframe}${since ? `&since=${encodeURIComponent(since)}` : ""}&limit=200`,
      { events: [], next_cursor: null, empty_reason: null }),
    refetchInterval: 60_000,
  });

export const useMoveLinks = (id: string | undefined, timeframe: string, since: string | undefined) =>
  useQuery({
    queryKey: ["move-links", id, timeframe, since], enabled: !!id,
    queryFn: () => orMissing<MoveLinksResponse>(`/instruments/${id}/move-links?timeframe=${timeframe}${since ? `&since=${encodeURIComponent(since)}` : ""}`,
      { moves: [], note: "Zeitlich zusammenfallend, keine Aussage über Ursache.", empty_reason: null }),
    refetchInterval: 60_000,
  });

export const usePatterns = (id: string | undefined, timeframe: string | null, start: string | undefined, includeInvalid: boolean) =>
  useQuery({
    queryKey: ["patterns", id, timeframe, start, includeInvalid], enabled: !!id && timeframe != null,
    queryFn: () => orMissing<PatternsResponse>(`/instruments/${id}/patterns?timeframe=${timeframe}${includeInvalid ? "&include_invalid=true" : ""}${start ? `&start=${encodeURIComponent(start)}` : ""}`,
      { instrument: { id: Number(id), symbol: "", name: "", isin: null, exchange: "", currency: "" }, timeframe: timeframe ?? "", detections: [], zones: [], data_basis: null, algo_version: "", params_hash: "", computed_at: null, empty_reason: null }),
    refetchInterval: (q) => (q.state.data?.pending ? PENDING_POLL_MS : 60_000),
  });

export const usePatternCounts = () =>
  useQuery({
    queryKey: ["pattern-counts"],
    queryFn: () => orMissing<PatternCounts>("/patterns/counts", { counts: {}, empty_reason: null }),
    refetchInterval: 60_000,
  });

export const EVENT_SHORT: Record<IndicatorEventType, string> = {
  golden_cross: "GC", death_cross: "DC", rsi_divergence: "RSI", bb_breakout: "BB", volume_spike: "Vol",
};
export const EVENT_NAME: Record<IndicatorEventType, string> = {
  golden_cross: "Golden Cross", death_cross: "Death Cross", rsi_divergence: "RSI-Divergenz", bb_breakout: "Bollinger-Ausbruch", volume_spike: "Volumenspitze",
};
export const DIRECTION_TEXT = { up: "Werte oberhalb bzw. steigend", down: "Werte unterhalb bzw. fallend" } as const;

export const STATUS_TEXT: Record<string, string> = { in_bildung: "In Bildung", bestaetigt: "Bestätigt", ungueltig: "Ungültig" };
