// Dünne API-Schicht. Der Vertrag steht in docs/api-contract.md, die Typen hier spiegeln ihn.
export interface SourceRef { key: string; name: string; homepage: string; terms_url: string; delay_text: string }
export interface Instrument { id: number; symbol: string; name: string; isin: string | null; exchange: string; currency: string }
export interface Quote {
  price: number; change_abs: number | null; change_pct: number | null; ts_utc: string; fetched_at: string;
  delay_seconds: number | null; is_demo: boolean; source: SourceRef;
}
export interface InstrumentWithQuote extends Instrument { quote: Quote | null }
export interface Bar {
  ts_utc: string; open: number; high: number; low: number; close: number; volume: number | null;
  fetched_at: string; is_demo: boolean; source: SourceRef;
}
export interface BarsResponse { instrument: Instrument; timeframe: string; bars: Bar[]; empty_reason: string | null }
export interface User { id: number; email: string; display_name: string; role: string }
export interface Me { user: User; csrf_token: string }
export interface Meta { demo_mode: boolean; timezone: string; disclaimer: string }
export interface Source {
  key: string; name: string; kind: string; description: string; homepage: string; terms_url: string;
  update_interval: string; delay_text: string; requires_key: boolean; is_official: boolean;
  status: "online" | "degraded" | "offline" | "disabled"; last_success_at: string | null; last_error: string | null; item_count_24h?: number | null;
}

export type SentimentLabel = "positiv" | "neutral" | "negativ";
export interface NewsSentiment {
  label: SentimentLabel; score: number; method: "lexicon" | "claude"; model_name: string; model_version?: string; rationale: string; evidence: string[];
}
export interface NewsItem {
  id: number; title: string; excerpt: string | null; url: string; published_at: string; fetched_at: string; source: SourceRef;
}
export interface NewsCluster {
  id: number; canonical_title: string; first_published_at: string; item_count: number;
  instruments: { id: number; symbol: string; match_method?: string }[]; sentiment: NewsSentiment | null; items: NewsItem[];
}
export interface NewsResponse { items: NewsCluster[]; total: number; next_cursor?: string | null; empty_reason: string | null }
export interface SentimentStatus {
  active_method: "claude" | "lexicon"; claude_configured: boolean; budget_usd: number; spent_usd: number; month: string; fallback_reason: string | null;
}
export interface NewsCounts { counts: Record<string, number>; empty_reason: string | null }

// Phase 3. Die Typen spiegeln docs/api-contract.md, Abschnitte "Phase 3A" (Indikatoren) und "Phase 3B" (Muster).
export interface IndicatorLines { value?: (number | null)[]; macd?: (number | null)[]; signal?: (number | null)[]; histogram?: (number | null)[]; middle?: (number | null)[]; upper?: (number | null)[]; lower?: (number | null)[] }
export interface IndicatorSeries {
  key: string; type: "sma" | "ema" | "rsi" | "macd" | "bollinger"; params: Record<string, number>; label: string; panel: "price" | "own";
  formula?: string; range?: [number, number]; reference_lines?: number[]; lines: IndicatorLines;
}
export interface IndicatorsResponse {
  instrument_id: number; timeframe: string; algo_version: string; timestamps: string[]; indicators: IndicatorSeries[];
  sources: SourceRef[]; bars_fetched_at: string | null; computed_at?: string | null; empty_reason: string | null;
}

export type IndicatorEventType = "golden_cross" | "death_cross" | "rsi_divergence" | "bb_breakout" | "volume_spike";
export interface EventCriterion { name: string; rule: string; required: string; actual: string; passed: boolean }
export interface IndicatorEvent {
  id: number; instrument_id: number; timeframe: string; type: IndicatorEventType; direction: "up" | "down" | null;
  ts: string; start_ts: string | null; end_ts: string | null; confirmed_at: string | null; title: string; summary: string;
  criteria: EventCriterion[]; values: Record<string, unknown>; params: Record<string, unknown>; algo_version: string;
  historical_stats: Record<string, unknown> | null; historical_stats_reason: string | null;
  sources: SourceRef[]; bars_fetched_at: string; detected_at: string;
}
export interface IndicatorEventsResponse { events: IndicatorEvent[]; next_cursor: string | null; empty_reason: string | null }

export interface MoveNews { cluster_id: number; canonical_title: string; first_published_at: string; time_offset_minutes: number; item_count: number; sources: SourceRef[] }
export interface NotableMove {
  id: number; move_start: string; move_end: string; return_pct: number; return_z: number | null; volume_z: number | null; reasons: string[];
  params: Record<string, unknown>; algo_version: string; sources: SourceRef[]; bars_fetched_at: string; news: MoveNews[];
}
export interface MoveLinksResponse { moves: NotableMove[]; note: string; empty_reason: string | null }

export type PatternStatus = "in_bildung" | "bestaetigt" | "ungueltig";
export interface KeyPoint { role: string; label: string; ts: string; price: number }
export interface PatternLine { role: string; label: string; start: { ts: string; price: number }; end: { ts: string; price: number }; extend_right?: boolean }
export interface Criterion {
  key: string; name: string; rule: string; threshold: number | null; actual: number | null; unit: string | null; actual_text: string;
  required: boolean; passed: boolean; sub_score: number; weight: number;
}
export interface ConfidenceBreakdownItem { key: string; name: string; weight: number; sub_score: number; contribution: number }
export interface Confidence { score: number; method: string; breakdown: ConfidenceBreakdownItem[] }
export interface ScenarioHistorical { share: number | null; sample_size: number | null; text: string | null }
export interface Scenario { kind: string; title: string; trigger_level: number | null; trigger_rule: string; description: string; historical: ScenarioHistorical | null }
export interface PatternBacktest {
  status: "berechnet" | "nicht_berechnet"; run_id: number | null; hit_rate: number | null; sample_size: number | null; ci_low: number | null; ci_high: number | null;
  base_rate: number | null; not_better_than_random: boolean | null; horizon_bars: number | null; min_move_pct: number | null;
  universe: string | null; date_range: string | null; computed_at: string | null; survivorship_note: string | null; verdict_text: string | null; note?: string | null;
}
export interface DataBasis { bars_from: string; bars_to: string; bar_count: number; last_fetched_at: string; sources: SourceRef[] }
export interface PatternDetection {
  id: number; instrument_id: number; timeframe: string; pattern_type: string; name: string; direction_if_confirmed: "aufwärts" | "abwärts" | "offen";
  status: PatternStatus; status_label: string; status_changed_at: string | null; confirmed_at: string | null; invalidated_at: string | null;
  start_ts: string; end_ts: string; key_points: KeyPoint[]; lines: PatternLine[]; criteria: Criterion[]; confidence: Confidence;
  confirmation_level: number | null; invalidation_level: number | null; scenarios: Scenario[]; backtest: PatternBacktest | null;
  explanation: string; data_basis: DataBasis; params: Record<string, unknown>; algo_version: string; params_hash: string; detected_at: string;
}
export interface SRZone {
  id: number; kind: "unterstuetzung" | "widerstand" | "im_bereich"; kind_label: string; lower: number; upper: number; center: number;
  touch_count: number; first_touch: string; last_touch: string; explanation: string; confidence?: Confidence;
}
export interface PatternsResponse {
  instrument: Instrument; timeframe: string; detections: PatternDetection[]; zones: SRZone[]; data_basis: DataBasis | null;
  algo_version: string; params_hash: string; computed_at: string | null; empty_reason: string | null;
}
export interface PatternCounts { counts: Record<string, number>; empty_reason: string | null }

// Phase 4. Die Typen spiegeln docs/api-contract.md, Abschnitt "Phase 4A".
// Prognosen gibt es ausschließlich als Quantile je Schritt (Grundregel 4), keine Einzellinie.
export type QuantileKey = "2.5" | "10" | "25" | "50" | "75" | "90" | "97.5";
export interface ForecastStep { step?: number; ts: string; quantiles: Record<QuantileKey, number> }
export interface ForecastMethod { key: string; name: string; description: string; assumptions?: string[]; limitations?: string[]; params?: Record<string, unknown> }
export interface ForecastCoverage { nominal: number; observed: number }
export interface ForecastMetric { key: string; name?: string; model: number | null; naive: number | null; unit?: string | null }
export interface ForecastHorizonResult { horizon_bars: number; sample_size: number | null; coverage?: ForecastCoverage[]; metrics?: ForecastMetric[]; skill: number | null; dm_p_value: number | null; better_than_naive: boolean | null }
export interface ForecastBacktest {
  status: "berechnet" | "nicht_berechnet"; run_id: number | null; sample_size: number | null; date_range: string | null; universe: string | null;
  horizon_bars: number | null; computed_at?: string | null; is_demo?: boolean; note?: string | null; coverage?: ForecastCoverage[]; metrics?: ForecastMetric[];
  skill?: number | null; dm_p_value?: number | null; better_than_naive: boolean | null; verdict_text: string | null; by_horizon?: ForecastHorizonResult[]; method_note?: string | null;
}
export interface ForecastComparison { method_key: string; name: string; description?: string; steps: ForecastStep[]; backtest?: ForecastBacktest | null; metrics?: ForecastMetric[] }
export interface PatternScenarioItem {
  kind: string; title: string; trigger_level: number | null; model_probability: number | null; model_probability_text: string | null; historical: ScenarioHistorical | null;
}
export interface PatternScenarioLink { detection_id: number; pattern_type: string; name: string; status: PatternStatus; scenarios: PatternScenarioItem[]; neither_probability: number | null; note: string }
export interface ForecastResponse {
  instrument_id: number; timeframe: string; method: ForecastMethod | null; horizon_bars: number; based_on_until: string | null;
  last_close: number | null; currency?: string; generated_at: string | null; algo_version: string; params_hash?: string; is_demo?: boolean; steps: ForecastStep[];
  bands?: { level: number; lower: QuantileKey; upper: QuantileKey }[]; backtest: ForecastBacktest | null; comparison?: ForecastComparison[];
  pattern_scenarios?: PatternScenarioLink[]; data_basis: DataBasis | null; note?: string | null; empty_reason: string | null;
}

let csrfToken = "";
export const setCsrfToken = (t: string) => { csrfToken = t; };

export async function api<T>(path: string, init: RequestInit = {}): Promise<T> {
  const headers = new Headers(init.headers);
  if (init.body) headers.set("Content-Type", "application/json");
  if (init.method && init.method !== "GET") headers.set("X-CSRF-Token", csrfToken);
  const res = await fetch(`/api${path}`, { ...init, headers, credentials: "same-origin" });
  if (!res.ok) throw new Error(res.status === 401 ? "unauthorized" : `HTTP ${res.status}`);
  return res.status === 204 ? (undefined as T) : ((await res.json()) as T);
}
