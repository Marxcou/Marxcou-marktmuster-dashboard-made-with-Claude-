// Einzige Stelle für Anmeldung in den E2E-Tests. Ändert sich der Login (z. B. durch die Benutzerverwaltung),
// wird nur diese Datei angepasst.
import { expect, type APIRequestContext, type Page } from "@playwright/test";
import { E2E_ADMIN } from "./credentials.mjs";

export const CREDENTIALS = E2E_ADMIN;

/** Anmeldung über die Oberfläche (für die Tests des Login-Ablaufs selbst). */
export async function loginViaUi(page: Page, creds = CREDENTIALS): Promise<void> {
  await page.goto("/login");
  await page.getByLabel("E-Mail").fill(creds.email);
  await page.getByLabel("Passwort").fill(creds.password);
  await page.getByRole("button", { name: "Anmelden" }).click();
  await expect(page.getByRole("heading", { name: "Watchlist" })).toBeVisible();
}

/** Anmeldung über die API; die Sitzungs-Cookies gelten danach für Seite und Anfragen desselben Kontexts. Liefert das CSRF-Token. */
export async function loginViaApi(request: APIRequestContext, creds = CREDENTIALS): Promise<string> {
  const res = await request.post("/api/auth/login", { data: creds });
  expect(res.ok(), `API-Login fehlgeschlagen: ${res.status()}`).toBeTruthy();
  return ((await res.json()) as { csrf_token: string }).csrf_token;
}
