// Grundregeln 1, 5 und 6 auf jeder Seite der Oberfläche.
import { expect, test } from "./helpers/fixtures";
import { DISCLAIMER, findForbidden } from "./helpers/grundregeln";

const STATIC_PAGES = ["/", "/nachrichten", "/quellen", "/gibt-es-nicht"];

test("Hinweis, Demo-Banner und neutrale Sprache auf jeder Seite", async ({ page, app }) => {
  for (const path of [...STATIC_PAGES, `/instrument/${app.demo.id}`]) {
    await page.goto(path);
    await expect(page.getByTestId("disclaimer").first(), path).toHaveText(DISCLAIMER);
    await expect(page.getByTestId("disclaimer").first(), path).toBeVisible();
    // Grundregel 6: erfundene Daten nur mit sichtbarer Kennzeichnung
    await expect(page.getByTestId("demo-banner"), path).toContainText("DEMO-MODUS");
    if (path.startsWith("/instrument/")) await expect(page.getByTestId("price-chart")).toBeVisible();
    else await page.waitForLoadState("networkidle");
    // Grundregel 1: keine Empfehlungssprache im sichtbaren Text
    const text = await page.locator("body").innerText();
    expect(findForbidden(text), `verbotener Begriff auf ${path}`).toBeNull();
  }
});

test("Disclaimer-Text im Frontend entspricht dem Wortlaut der Grundregel", async () => {
  expect(DISCLAIMER).toBe("Dieses Dashboard stellt keine Anlageberatung dar. Alle Analysen sind automatisiert, können fehlerhaft sein und dienen ausschließlich der Information.");
});
