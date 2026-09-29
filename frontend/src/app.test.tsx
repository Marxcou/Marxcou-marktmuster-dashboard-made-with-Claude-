import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { App } from "./App";
import { AuthProvider } from "./lib/auth";
import { formatNumber, formatPercent } from "./lib/format";
import { renderApp, mockApi, ME, SOURCE, INSTRUMENT } from "./testUtils";

vi.mock("./components/PriceChart", () => ({ PriceChart: ({ bars }: { bars: unknown[] }) => <div data-testid="price-chart">{bars.length} Balken</div> }));

const ROUTES = ["/", "/login", "/quellen", "/nachrichten", "/instrument/1", "/konto", "/admin/benutzer", "/gibt-es-nicht"];

describe.each(ROUTES)("Route %s", (path) => {
  it("zeigt den Hinweis (Grundregel 5)", async () => {
    mockApi({ "/auth/me": ME, "/watchlist": [], "/instruments/1": { ...INSTRUMENT, quote: null }, "/instruments/1/bars": { instrument: INSTRUMENT, timeframe: "1d", bars: [], empty_reason: "x" } });
    render(
      <QueryClientProvider client={new QueryClient()}>
        <AuthProvider><MemoryRouter initialEntries={[path]}><App /></MemoryRouter></AuthProvider>
      </QueryClientProvider>,
    );
    expect((await screen.findAllByTestId("disclaimer"))[0].textContent).toContain("keine Anlageberatung");
  });
});

it("formatiert deutsch", () => {
  expect(formatNumber(1234.5)).toBe("1.234,50");
  expect(formatPercent(0.0123)).toContain("1,23");
});

describe("Zugriff", () => {
  it("leitet ohne Anmeldung auf /login um", async () => {
    mockApi({ "/auth/me": 401 });
    renderApp("/");
    expect(await screen.findByRole("heading", { name: "Anmelden" })).toBeTruthy();
  });
});

describe("Watchlist", () => {
  it("zeigt leere Watchlist ausdrücklich", async () => {
    mockApi({ "/auth/me": ME, "/watchlist": [] });
    renderApp("/");
    expect(await screen.findByTestId("empty-watchlist")).toBeTruthy();
  });

  it("zeigt Kurs mit Quelle und Abrufzeit", async () => {
    mockApi({
      "/auth/me": ME,
      "/watchlist": [{ ...INSTRUMENT, quote: { price: 190.5, change_abs: 1, change_pct: 0.5, ts_utc: "2026-09-28T14:00:00Z", fetched_at: "2026-09-28T14:00:05Z", delay_seconds: null, is_demo: false, source: SOURCE } }],
    });
    renderApp("/");
    expect(await screen.findByText(/190,50/)).toBeTruthy();
    expect(screen.getByTestId("source-tip").textContent).toContain("Alpaca");
  });

  it("zeigt fehlenden Kurs statt Platzhalter", async () => {
    mockApi({ "/auth/me": ME, "/watchlist": [{ ...INSTRUMENT, quote: null }] });
    renderApp("/");
    expect(await screen.findByTestId("no-quote")).toBeTruthy();
  });
});

describe("Chart-Seite", () => {
  it("zeigt Leerzustand mit Grund, wenn keine Balken vorliegen", async () => {
    mockApi({ "/auth/me": ME, "/instruments/1": { ...INSTRUMENT, quote: null }, "/instruments/1/bars": { instrument: INSTRUMENT, timeframe: "1d", bars: [], empty_reason: "Keine Intraday-Daten für XETRA im kostenlosen Tarif" } });
    renderApp("/instrument/1");
    const box = await screen.findByTestId("no-bars");
    expect(box.textContent).toContain("Keine Intraday-Daten");
  });

  it("zeichnet den Chart und nennt den letzten Datenpunkt", async () => {
    const bar = { ts_utc: "2026-09-28T00:00:00Z", open: 1, high: 2, low: 0.5, close: 1.5, volume: 10, fetched_at: "2026-09-28T20:00:00Z", is_demo: false, source: SOURCE };
    mockApi({ "/auth/me": ME, "/instruments/1": { ...INSTRUMENT, quote: null }, "/instruments/1/bars": { instrument: INSTRUMENT, timeframe: "1d", bars: [bar], empty_reason: null } });
    renderApp("/instrument/1");
    expect(await screen.findByTestId("price-chart")).toBeTruthy();
    expect(screen.getByTestId("last-update").textContent).toContain("Letzter Datenpunkt");
  });
});
