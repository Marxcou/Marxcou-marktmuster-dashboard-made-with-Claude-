// Einzige Stelle für Anmeldung in den E2E-Tests. Ändert sich der Login, wird nur diese Datei angepasst.
// Konten mit Einmalpasswort (must_change_password) müssen vor der Nutzung ein eigenes Passwort setzen;
// beide Helfer erledigen das, wenn `newPassword` angegeben ist, und schlagen sonst mit klarer Meldung fehl.
import { expect, type APIRequestContext, type Page } from "@playwright/test";
import { E2E_ADMIN } from "./credentials.mjs";

export interface Credentials { email: string; password: string }
export const CREDENTIALS: Credentials = E2E_ADMIN;

/** Anmeldung über die Oberfläche (für die Tests des Login-Ablaufs selbst). */
export async function loginViaUi(page: Page, creds: Credentials = CREDENTIALS, opts: { newPassword?: string } = {}): Promise<void> {
  await page.goto("/login");
  await page.getByLabel("E-Mail").fill(creds.email);
  await page.getByLabel("Passwort").fill(creds.password);
  await page.getByRole("button", { name: "Anmelden" }).click();
  if (opts.newPassword) await changeForcedPasswordViaUi(page, creds.password, opts.newPassword);
  await expect(page.getByRole("heading", { name: "Watchlist" })).toBeVisible();
}

/** Pflicht-Passwortwechsel nach Einmalpasswort (Seite "Passwort ändern"). */
export async function changeForcedPasswordViaUi(page: Page, current: string, next: string): Promise<void> {
  await expect(page.getByTestId("forced-change")).toBeVisible();
  await page.getByLabel("Aktuelles Passwort").fill(current);
  await page.getByLabel("Neues Passwort (mindestens 10 Zeichen)").fill(next);
  await page.getByLabel("Neues Passwort wiederholen").fill(next);
  await page.getByRole("button", { name: "Passwort ändern" }).click();
  // Nach dem Wechsel gibt die Oberfläche die Seiten frei (kein Umweg über die Kontoseite nötig)
}

/** Anmeldung über die API; die Sitzungs-Cookies gelten danach für Seite und Anfragen desselben Kontexts. Liefert das CSRF-Token. */
export async function loginViaApi(request: APIRequestContext, creds: Credentials = CREDENTIALS, opts: { newPassword?: string } = {}): Promise<string> {
  const res = await request.post("/api/auth/login", { data: creds });
  expect(res.ok(), `API-Login fehlgeschlagen: ${res.status()}`).toBeTruthy();
  const me = (await res.json()) as { csrf_token: string; user: { must_change_password?: boolean } };
  if (me.user.must_change_password) {
    expect(opts.newPassword, `${creds.email} hat ein Einmalpasswort: newPassword angeben`).toBeTruthy();
    const r = await request.post("/api/auth/change-password", {
      data: { current_password: creds.password, new_password: opts.newPassword },
      headers: { "X-CSRF-Token": me.csrf_token },
    });
    expect(r.ok(), `Passwortwechsel fehlgeschlagen: ${r.status()}`).toBeTruthy();
  }
  return me.csrf_token;
}
