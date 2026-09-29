// Navigation und Layout: Tab-Leiste am Handy, Sprungleiste auf der Instrumentseite, kein seitliches Scrollen.
import { expect, test } from "./helpers/fixtures";

test("Handy: Tab-Leiste führt zu allen Bereichen, Hinweis bleibt sichtbar, kein seitliches Scrollen", async ({ page }) => {
  await page.setViewportSize({ width: 390, height: 844 });
  await page.goto("/");
  const tabs = page.getByRole("navigation", { name: "Hauptnavigation (Handy)" });
  await expect(tabs).toBeVisible();
  await tabs.getByRole("link", { name: "Quellen" }).click();
  await expect(page.getByRole("heading", { name: "Quellen" })).toBeVisible();
  await expect(tabs.getByRole("link", { name: "Quellen" })).toHaveAttribute("aria-current", "page");
  await expect(page.getByTestId("disclaimer").first()).toBeVisible();
  for (const path of ["/", "/nachrichten", "/quellen"]) {
    await page.goto(path);
    await expect(page.getByTestId("disclaimer").first()).toBeVisible();
    const overflow = await page.evaluate(() => document.documentElement.scrollWidth - document.documentElement.clientWidth);
    expect(overflow, path).toBeLessThanOrEqual(0);
  }
});

test("Instrumentseite: Sprungleiste erreicht Muster und Nachrichten", async ({ page, app }) => {
  await page.goto(`/instrument/${app.demo.id}`);
  const nav = page.getByRole("navigation", { name: "Bereiche dieser Seite" });
  await expect(nav).toBeVisible();
  await nav.getByRole("button", { name: /Muster/ }).click();
  await expect(page.getByTestId("chart-patterns")).toBeInViewport();
  await nav.getByRole("button", { name: /Nachrichten/ }).click();
  await expect(page.getByTestId("chart-news")).toBeInViewport();
});
