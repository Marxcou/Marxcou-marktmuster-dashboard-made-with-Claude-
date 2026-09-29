// Zugriff auf die gekennzeichneten Demo-Daten (backend/app/e2e_seed.py). Alles hier ist erfunden.
import { expect, type APIRequestContext } from "@playwright/test";

export const DEMO_SYMBOL = "DEMOA"; // Doppelboden, Meldungen, Prognose
export const DEMO_SYMBOL_2 = "DEMOB"; // Doppelboden in Bildung, ohne Meldungen, zum Hinzufügen in Tests

export interface DemoInstrument { id: number; symbol: string; name: string }

export async function findInstrument(request: APIRequestContext, symbol: string): Promise<DemoInstrument> {
  const res = await request.get(`/api/instruments/search?q=${symbol}`);
  expect(res.ok()).toBeTruthy();
  const hit = ((await res.json()) as DemoInstrument[]).find((i) => i.symbol === symbol);
  expect(hit, `Demo-Instrument ${symbol} fehlt (wurde e2e_seed ausgeführt?)`).toBeTruthy();
  return hit as DemoInstrument;
}

export async function setWatchlist(request: APIRequestContext, csrf: string, symbols: string[]): Promise<void> {
  const headers = { "X-CSRF-Token": csrf };
  const current = (await (await request.get("/api/watchlist")).json()) as { id: number }[];
  for (const i of current) await request.delete(`/api/watchlist/${i.id}`, { headers });
  for (const s of symbols) {
    const inst = await findInstrument(request, s);
    const r = await request.post("/api/watchlist", { data: { instrument_id: inst.id }, headers });
    expect(r.ok()).toBeTruthy();
  }
}
