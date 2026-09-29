// Grundregel 2: Seite "Quellen" mit Beschreibung, Intervall, Verzögerung und Status jeder Quelle.
import { expect, test } from "./helpers/fixtures";

test.beforeEach(async ({ page }) => {
  await page.goto("/quellen");
});

test("jede Quelle zeigt Beschreibung, Intervall, Verzögerung, Status und Nutzungsbedingungen", async ({ page }) => {
  const cards = page.getByTestId("source-card");
  await expect(cards.first()).toBeVisible();
  const n = await cards.count();
  expect(n).toBeGreaterThanOrEqual(5);
  for (let i = 0; i < n; i++) {
    const c = cards.nth(i);
    await expect(c.getByTestId("source-status")).toBeVisible();
    await expect(c).toContainText("Intervall");
    await expect(c).toContainText("Verzögerung");
    await expect(c).toContainText("Letzter Erfolg");
    await expect(c.getByRole("link", { name: "Nutzungsbedingungen" })).toBeVisible();
  }
});

test("Demo-Quellen sind online und ausdrücklich als Beispieldaten benannt", async ({ page }) => {
  const demo = page.getByTestId("source-card").filter({ hasText: "Demo-Kursquelle (Beispieldaten)" });
  await expect(demo.getByTestId("source-status")).toHaveText("online");
  await expect(demo).toContainText("Erfundene Kerzen für Tests");
});

test("Quellen ohne Schlüssel erscheinen als deaktiviert mit Grund statt zu verschwinden", async ({ page }) => {
  const disabled = page.getByTestId("source-card").filter({ has: page.getByTestId("source-status").filter({ hasText: "deaktiviert" }) });
  expect(await disabled.count()).toBeGreaterThanOrEqual(1);
  await expect(disabled.first()).toContainText("Letzter Fehler");
});
