// Einmalpasswort-Ablauf aus Sicht eines neuen Nutzers (Konto vom Administrator angelegt). Die Verwaltungsoberfläche
// selbst prüft ihr eigener Test; hier zählt, dass der Zugang eines Freundes von der Anmeldung bis zur Watchlist funktioniert.
import { expect, test } from "./helpers/fixtures";
import { loginViaUi } from "./helpers/auth";

test("neues Konto: Einmalpasswort, Pflichtwechsel, eigene leere Watchlist", async ({ page, browser, app }) => {
  const email = `freund-${Date.now()}@dashboard-test.org`;
  const created = await page.context().request.post("/api/users", {
    data: { email, display_name: "Freund E2E" }, headers: { "X-CSRF-Token": app.csrf },
  });
  expect(created.status()).toBe(201);
  const { temporary_password: temp } = (await created.json()) as { temporary_password: string };

  const ctx = await browser.newContext({ baseURL: test.info().project.use.baseURL });
  const friend = await ctx.newPage();
  await loginViaUi(friend, { email, password: temp }, { newPassword: "eigenes-passwort-456" });
  // eigene Watchlist: leer, obwohl die des Administrators gefüllt ist
  await expect(friend.getByTestId("empty-watchlist")).toBeVisible();
  await expect(friend.getByRole("link", { name: "Benutzer" })).toHaveCount(0); // kein Zugriff auf die Verwaltung
  await ctx.close();
});

test("Einmalpasswort: bis zum Wechsel ist nur die Passwortseite erreichbar", async ({ page, browser, app }) => {
  const email = `freund2-${Date.now()}@dashboard-test.org`;
  const res = await page.context().request.post("/api/users", {
    data: { email, display_name: "Freund zwei" }, headers: { "X-CSRF-Token": app.csrf },
  });
  const { temporary_password: temp } = (await res.json()) as { temporary_password: string };
  const ctx = await browser.newContext({ baseURL: test.info().project.use.baseURL });
  const friend = await ctx.newPage();
  await friend.goto("/login");
  await friend.getByLabel("E-Mail").fill(email);
  await friend.getByLabel("Passwort").fill(temp);
  await friend.getByRole("button", { name: "Anmelden" }).click();
  await expect(friend.getByTestId("forced-change")).toBeVisible();
  await friend.goto("/quellen");
  await expect(friend.getByTestId("forced-change")).toBeVisible();
  await ctx.close();
});
