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
