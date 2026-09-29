import { fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import { renderApp, mockApi, ME, SOURCE, INSTRUMENT } from "./testUtils";
import { ForecastPanel } from "./components/ForecastPanel";
import type { ForecastResponse, PatternDetection } from "./lib/api";
import { coverageNote, levelPosition, metricVsNaive, scenarioLevels, validSteps } from "./lib/forecast";

vi.mock("./components/PriceChart", () => ({
  PriceChart: (p: { forecast: unknown[]; scenarioLevels: unknown[]; patterns: unknown[]; onPatternClick: (id: number) => void }) => (
    <button data-testid="price-chart" onClick={() => p.onPatternClick(42)}>{p.forecast.length} Prognoseschritte, {p.scenarioLevels.length} Szenario-Niveaus, {p.patterns.length} Muster</button>
  ),
}));

const q = (mid: number) => ({ "2.5": mid - 5, "10": mid - 3, "25": mid - 1.5, "50": mid, "75": mid + 1.5, "90": mid + 3, "97.5": mid + 5 });
const BASIS = { bars_from: "2021-09-29T00:00:00Z", bars_to: "2026-09-28T00:00:00Z", bar_count: 1256, last_fetched_at: "2026-09-28T20:05:00Z", sources: [SOURCE] };
const BACKTEST = {
  status: "berechnet" as const, run_id: 17, sample_size: 142, horizon_bars: 20, date_range: "2023-10-02 – 2026-08-31", universe: "SAP (XETR), eigene Historie",
  coverage: [{ nominal: 0.5, observed: 0.47 }, { nominal: 0.8, observed: 0.7 }, { nominal: 0.95, observed: 0.93 }],
  metrics: [{ key: "median_abs_error", name: "Mittlerer absoluter Fehler des Medians", model: 4.1, naive: 4.3, unit: "%" }, { key: "pinball_loss", name: "Pinball-Verlust", model: 1.2, naive: 2.1, unit: "%" }],
  skill: 0.05, dm_p_value: 0.21, better_than_naive: false, verdict_text: "Beim Median nicht nachweisbar besser (p = 0,21).",
  by_horizon: [{ horizon_bars: 5, sample_size: 142, skill: 0.01, dm_p_value: 0.4, better_than_naive: false }],
};
const FORECAST: ForecastResponse = {
  instrument_id: 1, timeframe: "1d", horizon_bars: 20, based_on_until: "2026-09-28T00:00:00Z", last_close: 151.2, currency: "EUR", generated_at: "2026-09-28T20:10:00Z", algo_version: "forecast-1",
  method: { key: "monte_carlo_block_bootstrap", name: "Monte-Carlo-Simulation (Block-Bootstrap)", description: "Simuliert Pfade aus historischen Renditeblöcken.", assumptions: ["Zukünftige Schwankung ähnelt der historischen."], limitations: ["Feiertage nicht berücksichtigt."], params: { block_length: 10 } },
  steps: [{ ts: "2026-09-29T00:00:00Z", quantiles: q(151) }, { ts: "2026-10-26T00:00:00Z", quantiles: q(152) }],
  backtest: BACKTEST, note: "Statistische Szenarien, keine Vorhersage.", data_basis: BASIS, empty_reason: null,
  comparison: [{ method_key: "arima_1_1_0", name: "ARIMA(1,1,0)", steps: [{ ts: "2026-10-26T00:00:00Z", quantiles: q(150) }], backtest: { ...BACKTEST, better_than_naive: null } }],
  pattern_scenarios: [{ detection_id: 42, pattern_type: "doppelboden", name: "Doppelboden", status: "in_bildung", neither_probability: 0.57, note: "Die Simulation kennt das Muster nicht.",
    scenarios: [{ kind: "bestaetigung", title: "Bestätigung", trigger_level: 151.4, model_probability: 0.31, model_probability_text: "In 31 % der simulierten Pfade schließt der Kurs zuerst über 151,40.", historical: null },
      { kind: "scheitern", title: "Scheitern", trigger_level: 139.72, model_probability: 0.12, model_probability_text: null, historical: { share: 0.58, sample_size: 214, text: null } }] }],
};
const PATTERN = {
  id: 42, name: "Doppelboden", status: "in_bildung", status_label: "In Bildung", start_ts: "2026-08-20T00:00:00Z", end_ts: "2026-09-17T00:00:00Z",
  key_points: [], lines: [], criteria: [], confidence: { score: 0.74, method: "", breakdown: [] }, confirmation_level: 151.4, invalidation_level: 139.72, backtest: null, explanation: "", data_basis: BASIS, params: {}, algo_version: "1", params_hash: "x", detected_at: "2026-09-17T20:06:00Z", direction_if_confirmed: "aufwärts", scenarios: [
    { kind: "bestaetigung", title: "Bestätigung", trigger_level: 151.4, trigger_rule: "", description: "", historical: null },
    { kind: "scheitern", title: "Scheitern", trigger_level: 139.72, trigger_rule: "", description: "", historical: null }],
} as unknown as PatternDetection;
const EMPTY: ForecastResponse = { ...FORECAST, steps: [], backtest: null, comparison: [], pattern_scenarios: [], empty_reason: "Zu wenige Kerzen für eine Prognose (mindestens 250, vorhanden 80)." };

describe("Prognose-Panel (Grundregel 4)", () => {
  const ui = (data: ForecastResponse | undefined, pattern: PatternDetection | null = null) =>
    render(<ForecastPanel data={data} loading={false} error={false} horizon={20} onHorizon={() => {}} currency="EUR" pattern={pattern} />);

  it("zeigt drei Wahrscheinlichkeitsbereiche mit Werten, aber keine Einzelprognose", () => {
    ui(FORECAST);
    expect(within(screen.getByTestId("forecast-legend")).getAllByRole("listitem")).toHaveLength(3);
    const t = screen.getByTestId("horizon-table").textContent ?? "";
    expect(t).toContain("95 %"); expect(t).toContain("80 %"); expect(t).toContain("50 %");
    expect(t).toContain("147,00"); expect(t).toContain("157,00"); // 95-%-Bereich am Ende: 152 ± 5
    expect(t).not.toMatch(/Median/);
    expect(screen.getByTestId("forecast-note").textContent).toContain("keine Einzelprognose");
    expect(screen.getByTestId("forecast-basis").textContent).toContain("Block-Bootstrap");
  });
  it("macht Methode, Annahmen und Grenzen einsehbar", () => {
    ui(FORECAST);
    const m = screen.getByTestId("forecast-method").textContent ?? "";
    expect(m).toContain("historischen Renditeblöcken"); expect(m).toContain("Feiertage nicht berücksichtigt"); expect(m).toContain("block_length");
  });
  it("zeigt Abdeckung und Fehlermaße gegen die naive Referenz und sagt offen, wenn sie nicht besser ist", () => {
    ui(FORECAST);
    expect(screen.getAllByTestId("coverage-table")[0].textContent).toContain("zu eng");
    const m = screen.getAllByTestId("metrics-table")[0].textContent ?? "";
    expect(m).toContain("Kurs bleibt gleich"); expect(m).toContain("geringerer Fehler als die Referenz");
    expect(screen.getByTestId("not-better-naive").textContent).toContain("nicht nachweisbar besser");
    expect(screen.getAllByTestId("skill")[0].textContent).toContain("p = 0,21");
    expect(screen.getAllByTestId("forecast-backtest")[0].textContent).toContain("142");
    expect(screen.getAllByTestId("horizon-backtest-table")[0].textContent).toContain("nicht nachweisbar");
  });
  it("nennt fehlenden Backtest ausdrücklich", () => {
    ui({ ...FORECAST, comparison: [], backtest: { ...BACKTEST, status: "nicht_berechnet", sample_size: null, note: "Noch nicht berechnet." } });
    expect(screen.getByTestId("forecast-backtest-missing").textContent).toContain("nicht verfügbar");
    expect(screen.queryByTestId("forecast-backtest")).toBeNull();
  });
  it("zeigt den Grund statt eines Korridors, wenn keine Prognose vorliegt", () => {
    ui(EMPTY);
    expect(screen.getByTestId("no-forecast").textContent).toContain("mindestens 250");
    expect(screen.queryByTestId("horizon-table")).toBeNull();
    expect(screen.queryByTestId("forecast-legend")).toBeNull();
  });
  it("verwirft unvollständige Schritte statt sie zu ergänzen", () => {
    ui({ ...FORECAST, steps: [{ ts: "2026-09-29T00:00:00Z", quantiles: { "2.5": 1 } as never }] });
    expect(screen.getByTestId("no-forecast").textContent).toContain("keine vollständigen");
  });
  it("stellt Szenario-Niveaus, simulierte Pfadanteile und die historische Quote nebeneinander", () => {
    ui(FORECAST, PATTERN);
    const s = screen.getByTestId("scenario-levels").textContent ?? "";
    expect(s).toContain("151,40"); expect(s).toContain("139,72"); expect(s).toContain("außerhalb des 95-%-Bereichs");
    const l = screen.getByTestId("pattern-scenario-link").textContent ?? "";
    expect(l).toContain("31 % der simulierten Pfade"); expect(l).toContain("58 % von 214 Fällen"); expect(l).toContain("nicht verfügbar (kein Muster-Backtest)"); expect(l).toContain("57 %");
  });
  it("kennzeichnet Demodaten", () => {
    ui({ ...FORECAST, is_demo: true });
    expect(screen.getByTestId("forecast-demo").textContent).toContain("Demo-Modus");
  });
});

describe("Prognose-Hilfen", () => {
  it("filtert unvollständige Schritte und sortiert", () => {
    expect(validSteps([{ ts: "b", quantiles: q(1) }, { ts: "a", quantiles: q(1) }, { ts: "c", quantiles: { "50": 1 } as never }]).map((s) => s.ts)).toEqual(["a", "b"]);
  });
  it("beschreibt die Lage eines Niveaus im Korridor", () => {
    const last = { ts: "x", quantiles: q(100) };
    expect(levelPosition(100.5, last).inside).toBe(50);
    expect(levelPosition(104, last).inside).toBe(95);
    expect(levelPosition(120, last).text).toContain("darüber");
    expect(levelPosition(1, undefined).inside).toBeNull();
  });
  it("ordnet Abdeckung und Fehler neutral ein", () => {
    expect(coverageNote(0.8, 0.78)).toBe("nahe am Sollwert");
    expect(coverageNote(0.8, 0.6)).toContain("zu eng");
    expect(coverageNote(0.5, 0.7)).toContain("zu weit");
    expect(metricVsNaive({ key: "k", model: 1, naive: 2 }).text).toContain("geringerer");
    expect(metricVsNaive({ key: "k", model: 3, naive: 2 }).text).toContain("größerer");
    expect(metricVsNaive({ key: "k", model: null, naive: 2 }).ratio).toBeNull();
  });
  it("übernimmt nur Szenarien mit Niveau", () => {
    expect(scenarioLevels(PATTERN)).toHaveLength(2);
    expect(scenarioLevels(null)).toEqual([]);
  });
});

const BARS = { instrument: INSTRUMENT, timeframe: "1d", empty_reason: null, bars: [0, 1, 2].map((i) => ({ ts_utc: `2026-09-2${i + 5}T00:00:00Z`, open: 1, high: 2, low: 1, close: 2, volume: 10, fetched_at: "2026-09-28T20:00:00Z", is_demo: false, source: SOURCE })) };
const base = { "/auth/me": ME, "/instruments/1": { ...INSTRUMENT, quote: null }, "/instruments/1/bars": BARS };

describe("Chart-Seite Phase 4", () => {
  it("zeigt „noch nicht verfügbar“, solange das Backend keine Prognose-Schnittstelle hat", async () => {
    mockApi(base);
    renderApp("/instrument/1");
    expect((await screen.findByTestId("no-forecast")).textContent).toContain("noch nicht verfügbar");
    expect(screen.getByTestId("price-chart").textContent).toContain("0 Prognoseschritte");
  });
  it("übergibt den Korridor und die Szenario-Niveaus des gewählten Musters an den Chart", async () => {
    mockApi({ ...base, "/instruments/1/forecast": FORECAST, "/instruments/1/patterns": { instrument: INSTRUMENT, timeframe: "1d", detections: [PATTERN], zones: [], data_basis: BASIS, algo_version: "1", params_hash: "x", computed_at: null, empty_reason: null } });
    renderApp("/instrument/1");
    await waitFor(() => expect(screen.getByTestId("price-chart").textContent).toContain("2 Prognoseschritte, 0 Szenario-Niveaus"));
    fireEvent.click(screen.getByTestId("price-chart"));
    await waitFor(() => expect(screen.getByTestId("price-chart").textContent).toContain("2 Szenario-Niveaus"));
    expect(screen.getByTestId("pattern-scenario-link")).toBeTruthy();
  });
  it("blendet den Korridor aus, wenn er abgeschaltet wird", async () => {
    mockApi({ ...base, "/instruments/1/forecast": FORECAST });
    renderApp("/instrument/1");
    await waitFor(() => expect(screen.getByTestId("price-chart").textContent).toContain("2 Prognoseschritte"));
    fireEvent.click(screen.getByRole("checkbox", { name: "Prognosekorridor" }));
    await waitFor(() => expect(screen.getByTestId("price-chart").textContent).toContain("0 Prognoseschritte"));
    expect(screen.queryByTestId("forecast-panel")).toBeNull();
  });
  it("erklärt, dass es Korridore nur auf Tageskerzen gibt", async () => {
    mockApi(base);
    renderApp("/instrument/1");
    fireEvent.click(await screen.findByRole("button", { name: "1T" }));
    expect((await screen.findByTestId("no-forecast")).textContent).toContain("nur für Tageskerzen");
  });
});

describe("Erstberechnung nach dem Hinzufügen", () => {
  it("zeigt im Prognose-Panel einen neutralen Wartezustand statt einer Fehlermeldung", () => {
    const pending: ForecastResponse = { ...EMPTY, pending: true, empty_reason: "Die Prognose wird gerade berechnet. Die Ansicht aktualisiert sich automatisch." };
    render(<ForecastPanel data={pending} loading={false} error={false} horizon={20} onHorizon={() => {}} currency="EUR" pattern={null} />);
    expect(screen.getByTestId("forecast-pending").textContent).toContain("wird berechnet");
    expect(screen.queryByTestId("no-forecast")).toBeNull();
  });
});

describe("Chart-Seite: Wartezustand und nicht verfügbare Zeiträume", () => {
  const XETRA = { ...INSTRUMENT, exchange: "XETR", symbol: "NVD", currency: "EUR" };
  const base = { "/auth/me": ME, "/instruments/1": { ...XETRA, quote: null } };

  it("nennt beim frisch hinzugefügten Wert 'Kursdaten werden abgerufen' statt einer leeren Ansicht", async () => {
    mockApi({ ...base, "/instruments/1/bars": { instrument: XETRA, timeframe: "1d", bars: [], pending: true, empty_reason: "Kursdaten werden gerade abgerufen. Die Ansicht aktualisiert sich automatisch." } });
    renderApp("/instrument/1");
    await waitFor(() => expect(screen.getByTestId("bars-pending").textContent).toContain("Kursdaten werden abgerufen"));
    expect(screen.queryByTestId("no-bars")).toBeNull();
  });

  it("nennt für XETRA-Intraday den Grund (kostenloser Tarif) und zeigt keinen Wartezustand", async () => {
    const reason = "Keine Intraday-Daten für XETRA im kostenlosen Tarif. Verfügbar sind Tagesdaten (Handelsende).";
    mockApi({ ...base, "/instruments/1/bars": { instrument: XETRA, timeframe: "1h", bars: [], pending: false, empty_reason: reason } });
    renderApp("/instrument/1");
    fireEvent.click(await screen.findByRole("button", { name: "1W" }));
    await waitFor(() => expect(screen.getByTestId("no-bars").textContent).toContain("kostenlosen Tarif"));
    expect(screen.queryByTestId("bars-pending")).toBeNull();
  });
});
