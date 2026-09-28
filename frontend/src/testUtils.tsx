import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { App } from "./App";
import { AuthProvider } from "./lib/auth";

export const SOURCE = { key: "alpaca", name: "Alpaca", homepage: "https://alpaca.markets", terms_url: "https://alpaca.markets/disclosures", delay_text: "Echtzeit (IEX)" };
export const INSTRUMENT = { id: 1, symbol: "AAPL", name: "Apple Inc.", isin: "US0378331005", exchange: "XNAS", currency: "USD" };
export const ME = { user: { id: 1, email: "a@b.de", display_name: "Luca", role: "admin" }, csrf_token: "t" };

// Stellt fetch auf feste Antworten je Pfad (ohne Query-String) um; eine Zahl steht für einen HTTP-Status.
export function mockApi(routes: Record<string, unknown>) {
  vi.stubGlobal("fetch", vi.fn(async (url: string) => {
    const key = url.replace(/^\/api/, "").split("?")[0];
    const r = key === "/meta" ? { demo_mode: false, timezone: "Europe/Berlin", disclaimer: "" } : routes[key];
    if (typeof r === "number") return new Response("{}", { status: r });
    if (r === undefined) return new Response("{}", { status: 404 });
    return new Response(JSON.stringify(r), { status: 200 });
  }));
}

export function renderApp(path: string) {
  return render(
    <QueryClientProvider client={new QueryClient({ defaultOptions: { queries: { retry: false } } })}>
      <AuthProvider><MemoryRouter initialEntries={[path]}><App /></MemoryRouter></AuthProvider>
    </QueryClientProvider>,
  );
}
