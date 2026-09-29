import { expect, test } from "@playwright/test";
import { CREDENTIALS, loginViaUi } from "./helpers/auth";
import { DISCLAIMER } from "./helpers/grundregeln";

test("nicht angemeldet: geschützte Seiten leiten zur Anmeldung", async ({ page }) => {
  for (const path of ["/", "/nachrichten", "/quellen"]) {
    await page.goto(path);
    await expect(page).toHaveURL(/\/login$/);
    await expect(page.getByRole("heading", { name: "Anmelden" })).toBeVisible();
  }
});

test("falsches Passwort zeigt eine Fehlermeldung und meldet nicht an", async ({ page }) => {
  await page.goto("/login");
  await page.getByLabel("E-Mail").fill(CREDENTIALS.email);
  await page.getByLabel("Passwort").fill("falsches-passwort");
  await page.getByRole("button", { name: "Anmelden" }).click();
  await expect(page.getByRole("alert").filter({ hasText: "E-Mail oder Passwort falsch." })).toBeVisible();
  await expect(page).toHaveURL(/\/login$/);
});

test("Anmelden und Abmelden", async ({ page }) => {
  await loginViaUi(page);
  await expect(page).toHaveURL(/\/$/);
  await page.getByRole("button", { name: "Abmelden" }).click();
  await expect(page).toHaveURL(/\/login$/);
  await page.goto("/");
  await expect(page).toHaveURL(/\/login$/);
});

test("Hinweis (Grundregel 5) und Demo-Banner sind auf der Anmeldeseite sichtbar", async ({ page }) => {
  await page.goto("/login");
  await expect(page.getByTestId("disclaimer").first()).toHaveText(DISCLAIMER);
  await expect(page.getByTestId("disclaimer").first()).toBeVisible();
  await expect(page.getByTestId("demo-banner")).toContainText("DEMO-MODUS");
});

