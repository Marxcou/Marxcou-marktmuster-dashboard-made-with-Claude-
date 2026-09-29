import { DEMO_SYMBOL_2, setWatchlist } from "./helpers/demo";
import { expect, test } from "./helpers/fixtures";

test("Watchlist zeigt Karte mit Kurs, Tagesveränderung, Meldungen und Mustern samt Quelle", async ({ page }) => {
  await page.goto("/");
  const card = page.getByTestId("instrument-card").filter({ hasText: "DEMOA" });
  await expect(card).toBeVisible();
  await expect(card.getByText(/\d[\d.]*,\d{2}\s?€/).first()).toBeVisible();
  await expect(card.getByText("Beispieldaten (Demo-Modus)")).toBeVisible();
  await expect(card.getByTestId("news-count")).toContainText("Nachrichten (letzte 24 Stunden): 1");
  await expect(card.getByTestId("pattern-count")).toContainText("Aktuell erkannte Muster: 1");
  await card.getByText("Quelle: Demo-Kursquelle (Beispieldaten)").click();
  await expect(card.getByText("Abgerufen:")).toBeVisible();
});

test("Suche findet per Ticker, Name und ISIN-Feld; Hinzufügen und Entfernen", async ({ page }) => {
  await page.goto("/");
  await page.getByLabel("Suche nach Ticker, Firmenname oder ISIN").fill("Muster Holding");
  const hit = page.getByTestId("search-results").getByRole("listitem").filter({ hasText: DEMO_SYMBOL_2 });
  await expect(hit).toBeVisible();
  await hit.getByRole("button", { name: "Zur Watchlist" }).click();
  await expect(page.getByTestId("instrument-card").filter({ hasText: DEMO_SYMBOL_2 })).toBeVisible();
  await expect(hit.getByText("In Watchlist")).toBeVisible();

  await page.getByRole("button", { name: `${DEMO_SYMBOL_2} aus Watchlist entfernen` }).click();
  await expect(page.getByTestId("instrument-card").filter({ hasText: DEMO_SYMBOL_2 })).toHaveCount(0);
});

test("Suche ohne Treffer nennt den Grund statt Ersatzdaten", async ({ page }) => {
  await page.goto("/");
  await page.getByLabel("Suche nach Ticker, Firmenname oder ISIN").fill("gibtesnicht123");
  await expect(page.getByTestId("no-results")).toContainText("Keine Treffer");
});

test("leere Watchlist zeigt den Leerzustand", async ({ page, app }) => {
  await setWatchlist(page.context().request, app.csrf, []);
  await page.goto("/");
  await expect(page.getByTestId("empty-watchlist")).toBeVisible();
});
