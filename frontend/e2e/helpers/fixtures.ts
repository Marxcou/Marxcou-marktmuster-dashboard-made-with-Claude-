import { test as base, expect } from "@playwright/test";
import { loginViaApi } from "./auth";
import { DEMO_SYMBOL, findInstrument, setWatchlist, type DemoInstrument } from "./demo";

interface Fixtures {
  /** Angemeldete Seite; die Watchlist des Test-Kontos enthält nur DEMOA. */
  app: { csrf: string; demo: DemoInstrument };
}

export const test = base.extend<Fixtures>({
  app: [async ({ page }, use) => {
    const request = page.context().request;
    const csrf = await loginViaApi(request);
    await setWatchlist(request, csrf, [DEMO_SYMBOL]);
    await use({ csrf, demo: await findInstrument(request, DEMO_SYMBOL) });
  }, { auto: true }],
});

export { expect };
