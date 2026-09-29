import { expect, test } from "./helpers/fixtures";

test.beforeEach(async ({ page, app }) => {
  await page.goto(`/instrument/${app.demo.id}`);
  await expect(page.getByTestId("price-chart")).toBeVisible();
});

test("Chart zeigt Kurs, Kennzeichnung als Beispieldaten, letzten Datenpunkt und Quelle", async ({ page }) => {
  await expect(page.getByRole("heading", { name: /DEMOA/ })).toBeVisible();
  const info = page.getByTestId("last-update");
  await expect(info).toContainText("Letzter Datenpunkt:");
  await expect(info).toContainText("Beispieldaten (Demo-Modus)");
  await page.getByText("Quelle: Demo-Kursquelle (Beispieldaten)").last().click();
  await expect(page.getByText("Verzögerung:").last()).toBeVisible();
  await expect(page.getByText("Nutzungsbedingungen").last()).toBeVisible();
  // Lightweight Charts rendert in ein Canvas
  await expect(page.getByTestId("price-chart").locator("canvas").first()).toBeVisible();
});

test("Zeiträume und Diagrammtyp lassen sich umschalten", async ({ page }) => {
  const range = page.getByRole("group", { name: "Zeitraum" });
  for (const label of ["1M", "6M", "1J", "5J"]) {
    await range.getByRole("button", { name: label, exact: true }).click();
    await expect(range.getByRole("button", { name: label, exact: true })).toHaveAttribute("aria-pressed", "true");
    await expect(page.getByTestId("price-chart").locator("canvas").first()).toBeVisible();
  }
  const kind = page.getByRole("group", { name: "Diagrammtyp" });
  await kind.getByRole("button", { name: "Linie" }).click();
  await expect(kind.getByRole("button", { name: "Linie" })).toHaveAttribute("aria-pressed", "true");
});

test("Intraday-Zeiträume nennen den fehlenden Zeitraster-Grund statt Ersatzdaten", async ({ page }) => {
  await page.getByRole("group", { name: "Zeitraum" }).getByRole("button", { name: "1T", exact: true }).click();
  await expect(page.getByTestId("no-bars")).toBeVisible();
  await expect(page.getByTestId("no-bars")).not.toBeEmpty();
});

test("Indikatoren sind zuschaltbar und nennen Formel und Datenbasis", async ({ page }) => {
  const toggles = page.getByTestId("indicator-toggles");
  for (const name of ["RSI", "MACD"]) await toggles.getByLabel(name).check({ force: true });
  const info = page.getByTestId("indicator-info");
  await expect(info).toContainText("Berechnet aus den Kursdaten");
  await expect(info).toContainText("Demo-Kursquelle (Beispieldaten)");
  await expect(info.getByRole("listitem").first()).toBeVisible();
});

test("Nachrichten-Marker sind mit Quellen aufgeführt", async ({ page }) => {
  const section = page.getByTestId("chart-news");
  await expect(section.getByText("Beispielmeldung").first()).toBeVisible();
});

test("Indikator-Ereignisse und Kursbewegungen erscheinen ohne Kausalitätsbehauptung", async ({ page }) => {
  await expect(page.getByTestId("chart-events").getByTestId("indicator-event").first()).toBeVisible();
  const moves = page.getByTestId("chart-moves");
  await expect(moves).toBeVisible();
  const text = (await moves.innerText()).toLowerCase();
  expect(text).not.toMatch(/\b(weil|verursacht|ausgelöst durch)\b/);
});
