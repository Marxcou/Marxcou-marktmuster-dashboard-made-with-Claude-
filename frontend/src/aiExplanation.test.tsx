import { render, screen, waitFor } from "@testing-library/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { AiExplanation, type ExplanationResponse } from "./components/AiExplanation";
import { mockApi } from "./testUtils";

const BUDGET = { month: "2026-09", spent_usd: 0.42, budget_usd: 10 };
const AI: ExplanationResponse = { text: "Der Doppelboden wurde erkannt, weil zwei Tiefs nahe beieinander liegen.", source: "ki", label: "KI-generiert (Claude Sonnet 5.5)", model_name: "Claude Sonnet 5.5", model_version: "claude-sonnet-5-5", generated_at: "2026-09-29T12:00:00Z", cost_usd: 0.0123, fallback_reason: null, budget: BUDGET };
const TEMPLATE: ExplanationResponse = { ...AI, source: "vorlage", label: "Automatisch aus den Werten erstellt (Vorlage, ohne KI)", model_name: null, model_version: null, cost_usd: 0, fallback_reason: "Monatslimit erreicht" };

function show(kind: "pattern" | "forecast" = "pattern") {
  return render(<QueryClientProvider client={new QueryClient()}><AiExplanation kind={kind} id={7} /></QueryClientProvider>);
}

describe("Erklärtext (Punkt 6)", () => {
  it("kennzeichnet KI-Text mit Modell, Zeit, Kosten und Monatsverbrauch", async () => {
    mockApi({ "/patterns/7/explanation": AI });
    show();
    expect(screen.getByTestId("ai-explanation-loading")).toBeTruthy();
    expect((await screen.findByTestId("ai-explanation-text")).textContent).toContain("Doppelboden wurde erkannt");
    const label = screen.getByTestId("ai-explanation-label");
    expect(label.textContent).toContain("KI-generiert");
    expect(label.textContent).toContain("Claude Sonnet 5.5");
    expect(screen.getByTestId("ai-explanation").textContent).toContain("0,012 US-$");
    expect(screen.getByTestId("ai-explanation").textContent).toContain("0,42 US-$ von 10,00 US-$");
    expect(screen.queryByTestId("ai-explanation-reason")).toBeNull();
  });

  it("kennzeichnet die Vorlage und nennt den Grund, ohne sie als KI auszugeben", async () => {
    mockApi({ "/instruments/7/forecast/explanation": TEMPLATE });
    show("forecast");
    await screen.findByTestId("ai-explanation-text");
    expect(screen.getByTestId("ai-explanation-label").textContent).toContain("Vorlage, ohne KI");
    expect(screen.getByTestId("ai-explanation-label").textContent).not.toContain("KI-generiert");
    expect(screen.getByTestId("ai-explanation-reason").textContent).toContain("Monatslimit erreicht");
  });

  it("zeigt bei Fehlern einen Hinweis statt eines erfundenen Textes", async () => {
    mockApi({ "/patterns/7/explanation": 500 });
    show();
    await waitFor(() => expect(screen.getByTestId("ai-explanation-error")).toBeTruthy());
    expect(screen.queryByTestId("ai-explanation-text")).toBeNull();
  });
});
