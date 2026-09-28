import { useInfiniteQuery, useQuery } from "@tanstack/react-query";
import { api, type NewsCounts, type NewsResponse, type SentimentStatus, type SentimentLabel } from "./api";

export interface NewsFilter { instrumentId?: number; source?: string; sentiment?: SentimentLabel; since?: string; until?: string }

export const NEWS_MISSING = "Die Nachrichten-Schnittstelle des Backends ist noch nicht verfügbar. Es werden keine Nachrichten angezeigt.";

function qs(f: NewsFilter, cursor?: string) {
  const p = new URLSearchParams();
  if (cursor) p.set("cursor", cursor);
  if (f.instrumentId != null) p.set("instrument_id", String(f.instrumentId));
  if (f.source) p.set("source", f.source);
  if (f.sentiment) p.set("sentiment", f.sentiment);
  if (f.since) p.set("since", f.since);
  if (f.until) p.set("until", f.until);
  return p.toString();
}

// 404 heißt: Endpunkt noch nicht vorhanden. Das ist ein Leerzustand mit Grund, kein Fehler und kein Platzhalter (Grundregel 6).
async function orMissing<T extends { empty_reason: string | null }>(path: string, empty: T): Promise<T> {
  try {
    return await api<T>(path);
  } catch (e) {
    if (e instanceof Error && e.message === "HTTP 404") return { ...empty, empty_reason: NEWS_MISSING };
    throw e;
  }
}

export const useNews = (f: NewsFilter, refetchMs = 60_000) =>
  useInfiniteQuery({
    queryKey: ["news", f],
    initialPageParam: undefined as string | undefined,
    queryFn: ({ pageParam }) => orMissing<NewsResponse>(`/news?${qs(f, pageParam)}`, { items: [], total: 0, empty_reason: null }),
    getNextPageParam: (last) => last.next_cursor ?? undefined,
    refetchInterval: refetchMs,
  });

export const useSentimentStatus = () =>
  useQuery({ queryKey: ["sentiment-status"], queryFn: () => api<SentimentStatus>("/news/sentiment-status"), retry: false, refetchInterval: 300_000 });

export const useInstrumentNews = (id: string | undefined, since?: string) =>
  useQuery({
    queryKey: ["instrument-news", id, since],
    enabled: !!id,
    queryFn: () => orMissing<NewsResponse>(`/instruments/${id}/news${since ? `?since=${encodeURIComponent(since)}` : ""}`, { items: [], total: 0, empty_reason: null }),
    refetchInterval: 60_000,
  });

export const useNewsCounts = (since: string) =>
  useQuery({
    queryKey: ["news-counts", since],
    queryFn: () => orMissing<NewsCounts>(`/news/counts?since=${encodeURIComponent(since)}`, { counts: {}, empty_reason: null }),
    refetchInterval: 60_000,
  });
