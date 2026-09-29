import { useQuery } from "@tanstack/react-query";
import { api } from "../lib/api";
import { formatDateTime, formatNumber } from "../lib/format";

// Erklärtext zu einer Erkennung oder Prognose (Vertrag: docs/api-contract.md, "Erklärtexte"). Der Text entsteht im
// Backend nur aus den berechneten Werten und ist je nach Herkunft als KI-Text oder als Vorlage gekennzeichnet.
export interface ExplanationResponse {
  text: string; source: "ki" | "vorlage"; label: string; model_name: string | null; model_version: string | null;
  generated_at: string; cost_usd: number; fallback_reason: string | null;
  budget: { month: string; spent_usd: number; budget_usd: number };
}

const usd = (v: number) => `${formatNumber(v, v < 0.1 ? 3 : 2)} US-$`;

export const useExplanation = (kind: "pattern" | "forecast", id: number | undefined) =>
  useQuery({
    queryKey: ["explanation", kind, id], enabled: id != null, staleTime: 5 * 60_000, retry: false,
    queryFn: () => api<ExplanationResponse>(kind === "pattern" ? `/patterns/${id}/explanation` : `/instruments/${id}/forecast/explanation`),
  });

export function AiExplanation({ kind, id }: { kind: "pattern" | "forecast"; id: number | undefined }) {
  const q = useExplanation(kind, id);
  const e = q.data;
  const ai = e?.source === "ki";
  return (
    <section className={`mt-3 rounded border p-3 ${ai ? "border-indigo-700/60 bg-indigo-950/30" : "border-slate-700 bg-slate-950/40"}`} data-testid="ai-explanation" aria-label="Erklärtext in einfachen Worten" aria-busy={q.isLoading}>
      <h3 className="text-sm font-semibold">In einfachen Worten</h3>
      {q.isLoading && <p className="mt-1 text-sm text-slate-400" role="status" data-testid="ai-explanation-loading">Erklärtext wird erstellt …</p>}
      {q.isError && <p className="mt-1 text-sm text-slate-400" role="status" data-testid="ai-explanation-error">Der Erklärtext ist gerade nicht verfügbar. Alle berechneten Werte stehen unverändert darunter.</p>}
      {e && (
        <>
          <p className="mt-1 text-xs" data-testid="ai-explanation-label">
            <span className={`mr-2 rounded px-1.5 py-0.5 font-semibold ${ai ? "bg-indigo-900 text-indigo-100" : "bg-slate-800 text-slate-200"}`}>{ai ? "KI-generiert" : "Vorlage, ohne KI"}</span>
            <span className="text-slate-400">
              {ai ? `${e.model_name ?? "Claude"} · erstellt ${formatDateTime(e.generated_at)}` : e.label}
            </span>
          </p>
          <p className="mt-2 whitespace-pre-line text-sm leading-relaxed" data-testid="ai-explanation-text">{e.text}</p>
          {e.fallback_reason && <p className="mt-2 text-xs text-amber-300" data-testid="ai-explanation-reason">Kein KI-Text: {e.fallback_reason}.</p>}
          <p className="mt-2 text-xs text-slate-400">
            {ai ? "Der Text wurde automatisch aus den unten stehenden berechneten Werten formuliert und maschinell auf erfundene Zahlen und Empfehlungssprache geprüft. Er kann trotzdem Fehler enthalten; maßgeblich sind die Werte darunter. "
              : "Dieser Text wird ohne KI aus den unten stehenden Werten zusammengesetzt. "}
            {ai && e.cost_usd > 0 && `Kosten dieses Textes: ${usd(e.cost_usd)}. `}
            Monatsverbrauch der KI-Funktionen: {usd(e.budget.spent_usd)} von {usd(e.budget.budget_usd)}.
          </p>
        </>
      )}
    </section>
  );
}
