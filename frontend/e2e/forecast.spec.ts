// Grundregel 4: Prognose nur als Korridor, mit Methode und Backtest-Fehlermaßen.
import { expect, test } from "./helpers/fixtures";
import { findForbidden } from "./helpers/grundregeln";

test.beforeEach(async ({ page, app }) => {
  await page.goto(`/instrument/${app.demo.id}`);
  await page.getByLabel("Prognosekorridor").first().check({ force: true });
});

test("Prognosekorridor mit Wahrscheinlichkeitsbereichen, Methode und Backtest", async ({ page }) => {
  const panel = page.getByTestId("forecast-panel");
  await expect(panel).toBeVisible();
  await expect(panel.getByTestId("forecast-demo")).toContainText("Beispieldaten (Demo-Modus)");
  await expect(panel.getByTestId("forecast-basis")).toContainText("Berechnet aus Kursdaten bis");
  const legend = panel.getByTestId("forecast-legend");
  for (const level of ["50", "80", "95"]) await expect(legend).toContainText(`${level} %-Bereich`);
  // Tabelle: je Schritt ein Bereich, keine Einzelprognose
  await expect(panel.getByTestId("horizon-table")).toBeVisible();
  // Methode einsehbar
  await panel.getByTestId("forecast-method").locator("summary").click();
  await expect(panel.getByTestId("forecast-method")).toContainText(/Monte|Bootstrap|Verfahren/i);
  // Backtest-Fehlermaße gegen die naive Referenz
  const bt = panel.getByTestId("forecast-backtest").first();
  await expect(bt).toBeVisible();
  await expect(bt).toContainText("Kurs bleibt gleich");
  await expect(bt.getByTestId("coverage-table")).toBeVisible();
  await expect(bt.getByTestId("metrics-table")).toBeVisible();
  expect(findForbidden(await panel.innerText())).toBeNull();
});

test("Horizont umschaltbar", async ({ page }) => {
  const group = page.getByRole("group", { name: "Prognosehorizont" });
  await expect(group.getByRole("button").first()).toBeVisible();
  const buttons = group.getByRole("button");
  const last = buttons.last();
  await last.click();
  await expect(last).toHaveAttribute("aria-pressed", "true");
});

test("Szenario-Niveaus eines gewählten Musters erscheinen im Vergleich zum Korridor", async ({ page }) => {
  await page.getByTestId("pattern-list").getByRole("button", { name: /Doppelboden/ }).click();
  await expect(page.getByTestId("scenario-levels")).toContainText("Szenario-Niveaus");
});

test("Korridor ist nur für Tageskerzen verfügbar und nennt den Grund", async ({ page }) => {
  await page.getByRole("group", { name: "Zeitraum" }).getByRole("button", { name: "1W", exact: true }).click();
  await expect(page.getByTestId("no-forecast")).toContainText("nur für Tageskerzen");
});
