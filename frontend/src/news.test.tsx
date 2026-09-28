import { render, screen, fireEvent, waitFor } from "@testing-library/react";
import { renderApp, mockApi, ME, SOURCE, INSTRUMENT } from "./testUtils";
import { NewsClusterCard } from "./components/NewsClusterCard";
import type { NewsCluster } from "./lib/api";

vi.mock("./components/PriceChart", () => ({
  PriceChart: ({ markers, onMarkerClick }: { markers: { clusterId: number }[]; onMarkerClick: (ids: number[]) => void }) => (
    <button data-testid="price-chart" onClick={() => onMarkerClick(markers.map((m) => m.clusterId))}>{markers.length} Marker</button>
  ),
}));

const CLUSTER: NewsCluster = {
  id: 7, canonical_title: "Apple meldet Quartalszahlen", first_published_at: "2026-09-28T13:00:00Z", item_count: 2,
  instruments: [{ id: 1, symbol: "AAPL" }],
  sentiment: { label: "neutral", score: 0.05, method: "lexicon", model_name: "Loughran-McDonald", rationale: "Wenige wertende Begriffe.", evidence: ["Quartalszahlen"] },
  items: [
    { id: 1, title: "Apple reports results", excerpt: "Kurzer Auszug", url: "https://a.example/1", published_at: "2026-09-28T13:00:00Z", fetched_at: "2026-09-28T13:05:00Z", source: SOURCE },
    { id: 2, title: "Apple Zahlen", excerpt: null, url: "https://b.example/2", published_at: "2026-09-28T13:10:00Z", fetched_at: "2026-09-28T13:15:00Z", source: { ...SOURCE, key: "gdelt", name: "GDELT" } },
  ],
};
const SRC = (o: object) => ({ key: "finnhub", name: "Finnhub", kind: "news", description: "Firmennachrichten", homepage: "https://finnhub.io", terms_url: "https://finnhub.io/terms", update_interval: "alle 5 Min.", delay_text: "Minuten", requires_key: true, is_official: false, status: "online", last_success_at: "2026-09-28T13:00:00Z", last_error: null, ...o });

it("zeigt alle Quellen einer zusammengeführten Meldung, Stimmung mit Begründung und Modell", () => {
  render(<NewsClusterCard cluster={CLUSTER} />);
  expect(screen.getAllByTestId("news-item")).toHaveLength(2);
  expect(screen.getAllByText("GDELT", { exact: false }).length).toBeGreaterThan(0);
  expect(screen.getByTestId("sentiment").textContent).toContain("Loughran-McDonald");
  expect(screen.getByTestId("sentiment").textContent).toContain("Wenige wertende Begriffe.");
});

describe("Nachrichtenseite", () => {
  it("zeigt Meldungen", async () => {
    mockApi({ "/auth/me": ME, "/watchlist": [], "/sources": [SRC({})], "/news": { items: [CLUSTER], total: 1, empty_reason: null } });
    renderApp("/nachrichten");
    expect(await screen.findByTestId("news-cluster")).toBeTruthy();
  });
  it("nennt das aktive Stimmungsverfahren und den Ausweichgrund", async () => {
    mockApi({ "/auth/me": ME, "/watchlist": [], "/sources": [], "/news": { items: [CLUSTER], total: 1, next_cursor: null, empty_reason: null },
      "/news/sentiment-status": { active_method: "lexicon", claude_configured: false, budget_usd: 10, spent_usd: 0, month: "2026-09", fallback_reason: "Kein API-Schlüssel gesetzt" } });
    renderApp("/nachrichten");
    expect((await screen.findByTestId("sentiment-status")).textContent).toContain("Kein API-Schlüssel gesetzt");
  });
  it("kennzeichnet KI-Stimmung als KI-generiert", () => {
    render(<NewsClusterCard cluster={{ ...CLUSTER, sentiment: { ...CLUSTER.sentiment!, method: "claude", model_name: "claude-haiku-4-5" } }} />);
    expect(screen.getByTestId("sentiment").textContent).toContain("KI-generiert");
  });
  it("zeigt Leerzustand, wenn das Backend den Endpunkt noch nicht hat (404)", async () => {
    mockApi({ "/auth/me": ME, "/watchlist": [], "/sources": [] });
    renderApp("/nachrichten");
    expect((await screen.findByTestId("no-news")).textContent).toContain("noch nicht verfügbar");
  });
  it("sendet Filter an die API", async () => {
    mockApi({ "/auth/me": ME, "/watchlist": [{ ...INSTRUMENT, quote: null }], "/sources": [SRC({})], "/news": { items: [], total: 0, empty_reason: null } });
    renderApp("/nachrichten");
    fireEvent.change(await screen.findByLabelText("Stimmung"), { target: { value: "negativ" } });
    await waitFor(() => expect((fetch as unknown as ReturnType<typeof vi.fn>).mock.calls.some((c) => String(c[0]).includes("sentiment=negativ"))).toBe(true));
  });
});

describe("Quellen-Seite", () => {
  it("zeigt Beschreibung, Intervall, Verzögerung und Status je Quelle", async () => {
    mockApi({ "/auth/me": ME, "/sources": [SRC({}), SRC({ key: "edgar", name: "SEC EDGAR", status: "offline", last_success_at: null, last_error: "Zeitüberschreitung" })] });
    renderApp("/quellen");
    const cards = await screen.findAllByTestId("source-card");
    expect(cards).toHaveLength(2);
    expect(cards[0].textContent).toContain("alle 5 Min.");
    expect(cards[0].textContent).toContain("Minuten");
    expect(screen.getAllByTestId("source-status").map((e) => e.textContent)).toEqual(["online", "offline"]);
    expect(cards[1].textContent).toContain("noch kein erfolgreicher Abruf");
    expect(cards[1].textContent).toContain("Zeitüberschreitung");
  });
  it("sagt ausdrücklich, wenn die Liste nicht geladen werden kann", async () => {
    mockApi({ "/auth/me": ME, "/sources": 500 });
    renderApp("/quellen");
    expect(await screen.findByTestId("sources-error")).toBeTruthy();
  });
});

describe("Watchlist-Zähler", () => {
  const card = { ...INSTRUMENT, quote: null };
  it("zeigt die Anzahl neuer Nachrichten", async () => {
    mockApi({ "/auth/me": ME, "/watchlist": [card], "/news/counts": { counts: { "1": 3 }, empty_reason: null } });
    renderApp("/");
    await waitFor(() => expect(screen.getByTestId("news-count").textContent).toContain(": 3"));
  });
  it("zeigt 'nicht verfügbar' statt einer erfundenen 0, wenn der Endpunkt fehlt", async () => {
    mockApi({ "/auth/me": ME, "/watchlist": [card] });
    renderApp("/");
    await waitFor(() => expect(screen.getByTestId("news-count").textContent).toContain("nicht verfügbar"));
  });
});

describe("Chart-Marker", () => {
  const bar = { ts_utc: "2026-09-28T00:00:00Z", open: 1, high: 2, low: 0.5, close: 1.5, volume: 10, fetched_at: "2026-09-28T20:00:00Z", is_demo: false, source: SOURCE };
  const bars = { instrument: INSTRUMENT, timeframe: "1d", bars: [bar], empty_reason: null };
  it("öffnet die Meldung mit Quellen beim Klick auf den Marker", async () => {
    mockApi({ "/auth/me": ME, "/instruments/1": { ...INSTRUMENT, quote: null }, "/instruments/1/bars": bars, "/instruments/1/news": { items: [CLUSTER], total: 1, empty_reason: null } });
    renderApp("/instrument/1");
    const chart = await screen.findByText("1 Marker");
    fireEvent.click(chart);
    expect(await screen.findByTestId("news-cluster")).toBeTruthy();
    expect(screen.getAllByTestId("news-item")).toHaveLength(2);
  });
  it("erklärt fehlende Marker, wenn der Endpunkt fehlt", async () => {
    mockApi({ "/auth/me": ME, "/instruments/1": { ...INSTRUMENT, quote: null }, "/instruments/1/bars": bars });
    renderApp("/instrument/1");
    expect((await screen.findByTestId("no-markers")).textContent).toContain("noch nicht verfügbar");
  });
});
