// Grundregel 3: jedes erkannte Muster wird vollständig erklärt.
import { expect, test } from "./helpers/fixtures";
import { findForbidden } from "./helpers/grundregeln";

test.beforeEach(async ({ page, app }) => {
  await page.goto(`/instrument/${app.demo.id}`);
});

test("Doppelboden wird gelistet und mit allen Pflichtangaben erklärt", async ({ page }) => {
  const list = page.getByTestId("pattern-list");
  await expect(list.getByRole("button", { name: /Doppelboden/ })).toBeVisible();
  await list.getByRole("button", { name: /Doppelboden/ }).click();

  const panel = page.getByTestId("pattern-panel");
  await expect(panel).toBeVisible();
  // Name, Lage im Chart mit Zeitraum, Status
  await expect(panel.getByRole("heading", { name: "Doppelboden" })).toBeVisible();
  await expect(panel.getByTestId("pattern-range")).toContainText(/Lage im Chart: \d{2}\.\d{2}\.\d{4} bis \d{2}\.\d{2}\.\d{4}/);
  await expect(panel.getByTestId("pattern-status")).toContainText("Bestätigt");
  // erfüllte Kriterien mit tatsächlichen Werten
  const rows = panel.getByTestId("criteria-table").locator("tbody tr");
  expect(await rows.count()).toBeGreaterThanOrEqual(3);
  await expect(panel.getByTestId("criteria-table")).toContainText("erfüllt");
  await expect(panel.getByTestId("criteria-table").locator("tbody tr").first().locator("td").nth(2)).toContainText(/\d/);
  // Konfidenz samt Berechnung
  await expect(panel.getByTestId("confidence")).toHaveText(/\d+\s?%/);
  await expect(panel.getByTestId("confidence-table")).toContainText("Summe");
  await expect(panel.getByText("Gewichteter Mittelwert der Teilwerte")).toBeVisible();
  // mindestens zwei Szenarien und beide Niveaus
  expect(await panel.getByTestId("scenario").count()).toBeGreaterThanOrEqual(2);
  await expect(panel.getByTestId("levels")).toContainText("Bestätigungsniveau:");
  await expect(panel.getByTestId("levels")).toContainText("Ungültigkeitsniveau:");
  // Backtest mit Stichprobengröße (im Demo-Lauf ausdrücklich als Beispielwert gekennzeichnet)
  await expect(panel.getByTestId("backtest")).toContainText(/Stichprobe|Fälle/);
  await expect(panel.getByTestId("backtest")).toContainText(/120/);
  // Verfahren, Parameter, Datenbasis mit Quelle
  await panel.getByText("Verfahren, Parameter und Datenbasis").click();
  await expect(panel.getByText(/Parameter-Kennung/)).toBeVisible();
  await expect(panel.getByText("Quelle: Demo-Kursquelle (Beispieldaten)")).toBeVisible();
  // Grundregel 1
  expect(findForbidden(await panel.innerText())).toBeNull();
});

test("Zeitraum ohne Tageskerzen nennt den Grund für fehlende Muster", async ({ page }) => {
  await page.getByRole("group", { name: "Zeitraum" }).getByRole("button", { name: "1T", exact: true }).click();
  await expect(page.getByTestId("no-patterns")).toContainText("Die Mustererkennung arbeitet nur mit Tages- und Stundenkerzen");
});
