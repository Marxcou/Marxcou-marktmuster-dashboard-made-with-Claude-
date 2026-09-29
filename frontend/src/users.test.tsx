import { fireEvent, screen, waitFor, within } from "@testing-library/react";
import { mockApi, renderApp, ME } from "./testUtils";

const USERS = [
  { id: 1, email: "a@b.de", display_name: "Luca", role: "admin", is_active: true, must_change_password: false, created_at: "2026-09-28T10:00:00Z" },
  { id: 2, email: "f@b.de", display_name: "Freund", role: "user", is_active: true, must_change_password: true, created_at: "2026-09-29T10:00:00Z" },
];

describe("Benutzerverwaltung", () => {
  it("listet Nutzer für Administratoren", async () => {
    mockApi({ "/auth/me": ME, "/users": USERS });
    renderApp("/admin/benutzer");
    const rows = await screen.findAllByTestId("user-row");
    expect(rows).toHaveLength(2);
    expect(within(rows[1]).getByText(/Einmalpasswort offen/)).toBeTruthy();
    expect(within(rows[0]).queryByText("Sperren")).toBeNull(); // eigenes Konto nicht sperrbar
  });

  it("verweigert Nicht-Administratoren die Seite und den Menüpunkt", async () => {
    mockApi({ "/auth/me": { ...ME, user: { ...ME.user, role: "user" } }, "/watchlist": [] });
    renderApp("/admin/benutzer");
    expect(await screen.findByText(/nur für Administratoren/)).toBeTruthy();
    expect(screen.queryByRole("link", { name: "Benutzer" })).toBeNull();
  });

  it("zeigt das Einmalpasswort nach dem Anlegen", async () => {
    vi.stubGlobal("fetch", vi.fn(async (url: string, init?: RequestInit) => {
      const path = url.replace(/^\/api/, "");
      if (path === "/auth/me") return new Response(JSON.stringify(ME), { status: 200 });
      if (path === "/meta") return new Response(JSON.stringify({ demo_mode: false, timezone: "Europe/Berlin", disclaimer: "" }), { status: 200 });
      if (path === "/users" && init?.method === "POST") return new Response(JSON.stringify({ ...USERS[1], id: 3, email: "n@b.de", temporary_password: "Abc-123-xyz-987" }), { status: 201 });
      if (path === "/users") return new Response(JSON.stringify(USERS), { status: 200 });
      return new Response("{}", { status: 404 });
    }));
    renderApp("/admin/benutzer");
    fireEvent.change(await screen.findByLabelText("E-Mail"), { target: { value: "n@b.de" } });
    fireEvent.change(screen.getByLabelText("Anzeigename"), { target: { value: "Neu" } });
    fireEvent.click(screen.getByRole("button", { name: "Konto anlegen" }));
    expect((await screen.findByTestId("temp-password")).textContent).toContain("Abc-123-xyz-987");
  });
});

describe("Passwortwechsel", () => {
  it("erzwingt den Wechsel bei Einmalpasswort", async () => {
    mockApi({ "/auth/me": { ...ME, user: { ...ME.user, must_change_password: true } }, "/watchlist": [] });
    renderApp("/");
    expect(await screen.findByTestId("forced-change")).toBeTruthy();
    expect(screen.queryByTestId("empty-watchlist")).toBeNull();
  });

  it("prüft Länge und Wiederholung im Browser", async () => {
    mockApi({ "/auth/me": ME });
    renderApp("/konto");
    fireEvent.change(await screen.findByLabelText("Aktuelles Passwort"), { target: { value: "alt-alt-alt-1" } });
    fireEvent.change(screen.getByLabelText(/^Neues Passwort \(/), { target: { value: "kurz" } });
    fireEvent.change(screen.getByLabelText("Neues Passwort wiederholen"), { target: { value: "kurz" } });
    fireEvent.click(screen.getByRole("button", { name: "Passwort ändern" }));
    await waitFor(() => expect(screen.getByRole("alert").textContent).toContain("mindestens 10"));
  });

  it("zeigt den Servertext bei falschem aktuellem Passwort", async () => {
    vi.stubGlobal("fetch", vi.fn(async (url: string) => {
      if (url.endsWith("/auth/me")) return new Response(JSON.stringify(ME), { status: 200 });
      if (url.endsWith("/meta")) return new Response(JSON.stringify({ demo_mode: false, timezone: "Europe/Berlin", disclaimer: "" }), { status: 200 });
      return new Response(JSON.stringify({ detail: "Das aktuelle Passwort ist falsch" }), { status: 400 });
    }));
    renderApp("/konto");
    fireEvent.change(await screen.findByLabelText("Aktuelles Passwort"), { target: { value: "falsch-falsch" } });
    fireEvent.change(screen.getByLabelText(/^Neues Passwort \(/), { target: { value: "neues-passwort-1" } });
    fireEvent.change(screen.getByLabelText("Neues Passwort wiederholen"), { target: { value: "neues-passwort-1" } });
    fireEvent.click(screen.getByRole("button", { name: "Passwort ändern" }));
    await waitFor(() => expect(screen.getByRole("alert").textContent).toContain("aktuelle Passwort ist falsch"));
  });
});
