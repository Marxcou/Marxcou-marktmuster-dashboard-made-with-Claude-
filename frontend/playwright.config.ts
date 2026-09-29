import { defineConfig, devices } from "@playwright/test";

// Ende-zu-Ende-Tests laufen gegen das gebaute Frontend (vite preview) und ein echtes Backend mit frischer SQLite-DB,
// die e2e/start-backend.mjs mit gekennzeichneten Demo-Daten füllt (DEMO_MODE=true). Keine echten Marktdaten,
// keine API-Schlüssel, kein Netzwerkzugriff auf Anbieter.
const PORT = Number(process.env.E2E_WEB_PORT ?? 4173);
const API_PORT = Number(process.env.E2E_API_PORT ?? 8000); // vite.config.ts leitet /api und /ws an Port 8000

export default defineConfig({
  testDir: "./e2e",
  timeout: 30_000,
  expect: { timeout: 10_000 },
  fullyParallel: false,
  workers: 1,
  retries: process.env.CI ? 1 : 0,
  reporter: process.env.CI ? [["list"], ["html", { open: "never" }]] : "list",
  use: { baseURL: `http://localhost:${PORT}`, locale: "de-DE", timezoneId: "Europe/Berlin", trace: "retain-on-failure" },
  projects: [{ name: "chromium", use: { ...devices["Desktop Chrome"] } }],
  webServer: [
    {
      command: "node e2e/start-backend.mjs",
      url: `http://localhost:${API_PORT}/api/health`,
      timeout: 180_000,
      reuseExistingServer: !process.env.CI,
    },
    {
      command: `npm run build && npx vite preview --port ${PORT} --strictPort`,
      url: `http://localhost:${PORT}`,
      timeout: 180_000,
      reuseExistingServer: !process.env.CI,
    },
  ],
});
