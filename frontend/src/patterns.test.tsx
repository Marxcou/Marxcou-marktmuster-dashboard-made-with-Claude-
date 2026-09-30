import { render, screen, fireEvent, waitFor, within } from "@testing-library/react";
import { renderApp, mockApi, ME, SOURCE, INSTRUMENT } from "./testUtils";
import { PatternPanel } from "./components/PatternPanel";
import { EventList, MoveList } from "./components/AnalysisLists";
import { alignSeries, priceOnLine, snapTime, toTime } from "./lib/chartData";
import { indicatorQuery } from "./lib/analysis";
import type { IndicatorEvent, PatternDetection } from "./lib/api";

vi.mock("./components/AiExplanation", () => ({ AiExplanation: () => <div data-testid="ai-explanation" /> }));
vi.mock("./components/PriceChart", () => ({
  PriceChart: (p: { patterns: unknown[]; overlays: unknown[]; events: unknown[]; zones: unknown[]; onPatternClick: (id: number) => void }) => (
    <button data-testid="price-chart" onClick={() => p.onPatternClick(42)}>{p.patterns.length} Muster, {p.overlays.length} Linien, {p.events.length} Ereignisse, {p.zones.length} Zonen</button>
  ),
}));
vi.mock("./components/SubChart", () => ({ SubChart: ({ series }: { series: { key: string } }) => <div data-testid={`sub-${series.key}`} /> }));

const BASIS = { bars_from: "2021-09-29T00:00:00Z", bars_to: "2026-09-28T00:00:00Z", bar_count: 1256, last_fetched_at: "2026-09-28T20:05:00Z", sources: [SOURCE] };
const BACKTEST_NONE = { status: "nicht_berechnet" as const, run_id: null, hit_rate: null, sample_size: null, ci_low: null, ci_high: null, base_rate: null, not_better_than_random: null, horizon_bars: null, min_move_pct: null, universe: null, date_range: null, computed_at: null, survivorship_note: null, verdict_text: null, note: "Die historische Trefferquote für dieses Muster wurde noch nicht berechnet." };
const PATTERN: PatternDetection = {
  id: 42, instrument_id: 1, timeframe: "1d", pattern_type: "doppelboden", name: "Doppelboden", direction_if_confirmed: "aufwärts",
  status: "in_bildung", status_label: "In Bildung", status_changed_at: null, confirmed_at: null, invalidated_at: null,
  start_ts: "2026-08-20T00:00:00Z", end_ts: "2026-09-17T00:00:00Z",
  key_points: [{ role: "tief_1", label: "Tief 1", ts: "2026-09-03T00:00:00Z", price: 142.1 }, { role: "zwischenhoch", label: "Zwischenhoch", ts: "2026-09-10T00:00:00Z", price: 151.4 }, { role: "tief_2", label: "Tief 2", ts: "2026-09-17T00:00:00Z", price: 141.85 }],
  lines: [], criteria: [{ key: "tief_abweichung", name: "Abweichung der beiden Tiefs", rule: "höchstens 1,5 %", threshold: 1.5, actual: 0.18, unit: "%", actual_text: "Tief 1: 142,10 am 03.09.2026, Tief 2: 141,85 am 17.09.2026, Abweichung 0,18 %", required: true, passed: true, sub_score: 0.88, weight: 0.35 }],
  confidence: { score: 0.74, method: "Gewichteter Mittelwert der Teilwerte.", breakdown: [{ key: "tief_abweichung", name: "Abweichung der beiden Tiefs", weight: 0.35, sub_score: 0.88, contribution: 0.308 }] },
  confirmation_level: 151.4, invalidation_level: 139.72,
  scenarios: [
    { kind: "bestaetigung", title: "Bestätigung", trigger_level: 151.4, trigger_rule: "Schlusskurs über der Nackenlinie bei 151,40", description: "Schließt der Kurs über 151,40, gilt das Muster als bestätigt.", historical: null },
    { kind: "scheitern", title: "Scheitern", trigger_level: 139.72, trigger_rule: "Schlusskurs unter 139,72", description: "Schließt der Kurs darunter, gilt es als ungültig.", historical: null },
  ],
  backtest: BACKTEST_NONE, explanation: "Doppelboden zwischen 20.08.2026 und 17.09.2026.", data_basis: BASIS, params: { max_tief_abweichung_pct: 1.5 },
  algo_version: "1.0.0", params_hash: "3f2a9c1e", detected_at: "2026-09-17T20:06:00Z",
};
const BT = { ...BACKTEST_NONE, status: "berechnet" as const, run_id: 3, hit_rate: 0.62, sample_size: 214, ci_low: 0.55, ci_high: 0.68, base_rate: 0.5, not_better_than_random: false, horizon_bars: 20, min_move_pct: 3, universe: "DAX 40 und 100 US-Werte", date_range: "2016 bis 2026", computed_at: "2026-09-20T00:00:00Z", survivorship_note: "Heutige Indexmitglieder verzerren das Ergebnis.", verdict_text: null, note: null };

describe("Erklärpanel (Grundregel 3)", () => {
  it("zeigt Name, Zeitraum, Kriterien mit Werten, Konfidenz mit Aufschlüsselung, zwei Szenarien mit Niveaus", () => {
    render(<PatternPanel p={PATTERN} />);
    expect(screen.getByRole("heading", { name: "Doppelboden" })).toBeTruthy();
    expect(screen.getByTestId("pattern-range").textContent).toContain("2026");
    expect(screen.getByTestId("criteria-table").textContent).toContain("Abweichung 0,18 %");
    expect(screen.getByTestId("confidence").textContent).toBe("74 %");
    expect(screen.getByTestId("confidence-table").textContent).toContain("0,308");
    expect(screen.getAllByTestId("scenario")).toHaveLength(2);
    expect(screen.getByTestId("levels").textContent).toContain("151,40");
    expect(screen.getByTestId("levels").textContent).toContain("139,72");
    expect(screen.queryByTestId("pattern-incomplete")).toBeNull();
  });
  it("nennt beim symmetrischen Dreieck beide Niveaus Ausbruchsniveaus statt eines davon Ungültigkeitsniveau", () => {
    render(<PatternPanel p={{ ...PATTERN, pattern_type: "dreieck_symmetrisch", name: "Symmetrisches Dreieck", direction_if_confirmed: "offen" }} />);
    const t = screen.getByTestId("levels").textContent ?? "";
    expect(t).toContain("Ausbruchsniveau oben: 151,40");
    expect(t).toContain("Ausbruchsniveau unten: 139,72");
    expect(t).not.toContain("Ungültigkeitsniveau");
  });
  it("nennt fehlenden Backtest ausdrücklich und erfindet keine Trefferquote", () => {
    render(<PatternPanel p={PATTERN} />);
    expect(screen.getByTestId("backtest-missing").textContent).toContain("nicht verfügbar");
    expect(screen.queryByTestId("backtest")).toBeNull();
  });
  it("zeigt Trefferquote mit Stichprobe, Intervall und Basisrate", () => {
    render(<PatternPanel p={{ ...PATTERN, backtest: BT }} />);
    const t = screen.getByTestId("backtest").textContent ?? "";
    expect(t).toContain("62 %");
    expect(t).toContain("214");
    expect(t).toContain("55 % bis 68 %");
    expect(t).toContain("50 %");
    expect(screen.queryByTestId("not-better")).toBeNull();
  });
  it("sagt offen, wenn das Muster historisch nicht besser als Zufall ist", () => {
    render(<PatternPanel p={{ ...PATTERN, backtest: { ...BT, hit_rate: 0.51, ci_low: 0.44, ci_high: 0.58, not_better_than_random: true } }} />);
    expect(screen.getByTestId("not-better").textContent).toContain("nicht besser als Zufall");
  });
  it("sagt es auch, wenn die Trefferquote unter der Basisrate liegt, und zeigt Methode, Quelle und mittlere Veränderung", () => {
    render(<PatternPanel p={{ ...PATTERN, backtest: { ...BT, hit_rate: 0.3, ci_low: 0.24, ci_high: 0.37, not_better_than_random: true, verdict_text: "Die Trefferquote liegt unter der Basisrate.", mean_return_pct: -1.25, median_return_pct: -0.5, base_mean_return_pct: 0.8, method: "Walk-forward ohne Blick in die Zukunft.", source: { key: "stooq", name: "Stooq", homepage: "https://stooq.com", fetched_to: "2026-09-29T10:00:00Z" }, note: "Fälle sind nicht unabhängig." } }} />);
    expect(screen.getByTestId("not-better").textContent).toContain("unter der Basisrate");
    const t = screen.getByTestId("backtest").textContent ?? "";
    expect(t).toContain("-1,3 %");
    expect(t).toContain("+0,8 %");
    expect(t).toContain("Walk-forward");
    expect(t).toContain("Stooq");
    expect(t).toContain("nicht unabhängig");
  });
  it("warnt bei kleiner Stichprobe", () => {
    render(<PatternPanel p={{ ...PATTERN, backtest: { ...BT, sample_size: 12 } }} />);
    expect(screen.getByTestId("backtest").textContent).toContain("Kleine Stichprobe");
  });
  it("kennzeichnet eine unvollständige Erklärung", () => {
    render(<PatternPanel p={{ ...PATTERN, scenarios: [PATTERN.scenarios[0]], invalidation_level: null }} />);
    const t = screen.getByTestId("pattern-incomplete").textContent ?? "";
    expect(t).toContain("mindestens zwei Szenarien");
    expect(t).toContain("Ungültigkeitsniveau");
  });
});

describe("Ereignisse und Bewegungen", () => {
  const EV: IndicatorEvent = {
    id: 1, instrument_id: 1, timeframe: "1d", type: "rsi_divergence", direction: "up", ts: "2026-09-17T00:00:00Z", start_ts: null, end_ts: null, confirmed_at: null,
    title: "RSI-Divergenz (Kurs tiefer, RSI höher)", summary: "Der Kurs bildete ein tieferes Tief.", criteria: [{ name: "Tieferes Kurstief", rule: "Tief 2 < Tief 1", required: "< 142,10", actual: "141,85", passed: true }],
    values: {}, params: { rsi_period: 14 }, algo_version: "indicator-events-1", historical_stats: null, historical_stats_reason: "Für Indikator-Ereignisse wird noch keine historische Trefferquote berechnet.",
    sources: [SOURCE], bars_fetched_at: "2026-09-28T20:00:00Z", detected_at: "2026-09-28T20:00:00Z",
  };
  it("zeigt Kriterien und statt einer Trefferquote den Grund", () => {
    render(<EventList events={[EV]} />);
    expect(screen.getByText("141,85")).toBeTruthy();
    expect(screen.getByTestId("event-stats").textContent).toContain("noch keine historische Trefferquote");
  });
  it("formuliert News und Kursbewegung ohne Kausalität", () => {
    render(<MoveList note="Zeitlich zusammenfallend, keine Aussage über Ursache." onOpenNews={() => {}}
      moves={[{ id: 3, move_start: "2026-09-24T00:00:00Z", move_end: "2026-09-25T00:00:00Z", return_pct: -4.1, return_z: -3.6, volume_z: 2.1, reasons: ["return_z"], params: { lookback_bars: 60, z_threshold: 3 }, algo_version: "move-links-1", sources: [SOURCE], bars_fetched_at: "2026-09-28T20:00:00Z",
        news: [{ cluster_id: 7, canonical_title: "Quartalszahlen", first_published_at: "2026-09-23T22:00:00Z", time_offset_minutes: -120, item_count: 2, sources: [SOURCE] }] }]} />);
    const t = screen.getByTestId("move-list").textContent ?? "";
    expect(t).toContain("keine Aussage über Ursache");
    expect(t).toContain("zusammenfallend");
    expect(t).toContain("-4,1 %");
    expect(t).not.toMatch(/wegen|führte zu|löste .* aus|verursacht/);
  });
});

describe("Chart-Hilfen", () => {
  const times = [100, 200, 300].map((t) => t);
  it("hängt Zeitpunkte an die zuletzt begonnene Kerze und ignoriert Zeitpunkte davor", () => {
    expect(snapTime(times, new Date(250 * 1000).toISOString())).toBe(200);
    expect(snapTime(times, new Date(50 * 1000).toISOString())).toBeNull();
  });
  it("lässt fehlende Indikatorwerte leer statt sie zu ergänzen", () => {
    const iso = (t: number) => new Date(t * 1000).toISOString();
    const out = alignSeries([iso(100), iso(200)], [null, 5], times);
    expect(out).toEqual([{ time: 100 }, { time: 200, value: 5 }, { time: 300 }]);
    expect(toTime(iso(100))).toBe(100);
  });
  it("berechnet Werte auf Geraden und baut die Indikator-Abfrage", () => {
    expect(priceOnLine({ t: 0, price: 10 }, { t: 10, price: 20 }, 20)).toBe(30);
    expect(indicatorQuery(["sma20", "sma50", "rsi", "bb"])).toBe("sma=20,50&bb=20,2&rsi=14");
  });
});

const BARS = { instrument: INSTRUMENT, timeframe: "1d", empty_reason: null, bars: [0, 1, 2].map((i) => ({ ts_utc: `2026-09-2${i + 5}T00:00:00Z`, open: 1, high: 2, low: 1, close: 2, volume: 10, fetched_at: "2026-09-28T20:00:00Z", is_demo: false, source: SOURCE })) };
const IND = { instrument_id: 1, timeframe: "1d", algo_version: "indicators-1", timestamps: BARS.bars.map((b) => b.ts_utc), sources: [SOURCE], bars_fetched_at: "2026-09-28T20:00:00Z", empty_reason: null,
  indicators: [{ key: "sma_20", type: "sma", params: { period: 20 }, label: "SMA (20)", panel: "price", formula: "Mittel der letzten 20 Schlusskurse", lines: { value: [null, 1, 2] } },
    { key: "rsi_14", type: "rsi", params: { period: 14 }, label: "RSI (14)", panel: "own", lines: { value: [null, 40, 50] } }] };
const base = { "/auth/me": ME, "/instruments/1": { ...INSTRUMENT, quote: null }, "/instruments/1/bars": BARS };

describe("Chart-Seite Phase 3", () => {
  it("zeigt Leerzustände mit Grund, wenn das Backend die Endpunkte noch nicht hat", async () => {
    mockApi(base);
    renderApp("/instrument/1");
    expect((await screen.findByTestId("no-patterns")).textContent).toContain("noch nicht verfügbar");
    expect((await screen.findByTestId("no-events")).textContent).toContain("noch nicht verfügbar");
    expect((await screen.findByTestId("no-moves")).textContent).toContain("noch nicht verfügbar");
  });
  it("lädt Indikatoren erst nach dem Zuschalten und übergibt Linien und Teilfenster", async () => {
    mockApi({ ...base, "/instruments/1/indicators": IND });
    renderApp("/instrument/1");
    fireEvent.click(await screen.findByLabelText("SMA 20"));
    fireEvent.click(screen.getByLabelText("RSI (14)"));
    expect(await screen.findByTestId("sub-rsi_14")).toBeTruthy();
    await waitFor(() => expect(screen.getByTestId("price-chart").textContent).toContain("1 Linien"));
    const calls = (fetch as unknown as ReturnType<typeof vi.fn>).mock.calls.map((c) => String(c[0]));
    expect(calls.some((u) => u.includes("/indicators?") && u.includes("sma=20") && u.includes("rsi=14"))).toBe(true);
    expect(screen.getByTestId("indicator-info").textContent).toContain("Mittel der letzten 20 Schlusskurse");
  });
  it("zeigt Muster, öffnet die Erklärung per Klick im Chart und zeigt Zonen", async () => {
    mockApi({ ...base, "/instruments/1/patterns": { instrument: INSTRUMENT, timeframe: "1d", detections: [PATTERN], zones: [{ id: 7, kind: "unterstuetzung", kind_label: "Unterstützungszone", lower: 139.8, upper: 142.3, center: 141.05, touch_count: 4, first_touch: "2026-03-12T00:00:00Z", last_touch: "2026-09-17T00:00:00Z", explanation: "4 Wendepunkte." }], data_basis: BASIS, algo_version: "1.0.0", params_hash: "x", computed_at: null, empty_reason: null } });
    renderApp("/instrument/1");
    await waitFor(() => expect(screen.getByTestId("price-chart").textContent).toContain("1 Muster"));
    expect(screen.getByTestId("price-chart").textContent).toContain("1 Zonen");
    expect(screen.queryByTestId("pattern-panel")).toBeNull();
    fireEvent.click(screen.getByTestId("price-chart"));
    const panel = await screen.findByTestId("pattern-panel");
    expect(within(panel).getByTestId("backtest-missing")).toBeTruthy();
    expect(screen.getByTestId("zone-list").textContent).toContain("139,80");
  });
  it("erklärt, dass Muster auf Minutenkerzen nicht erkannt werden", async () => {
    mockApi(base);
    renderApp("/instrument/1");
    fireEvent.click(await screen.findByRole("button", { name: "1T" }));
    expect((await screen.findAllByTestId("no-patterns"))[0].textContent).toContain("nur mit Tages- und Stundenkerzen");
  });
});

describe("Watchlist Mustersumme", () => {
  it("zeigt die Anzahl erkannter Muster", async () => {
    mockApi({ "/auth/me": ME, "/watchlist": [{ ...INSTRUMENT, quote: null }], "/patterns/counts": { counts: { "1": 2 }, empty_reason: null } });
    renderApp("/");
    expect((await screen.findByTestId("pattern-count")).textContent).toContain("Aktuell erkannte Muster: 2");
  });
  it("nennt den Grund, wenn die Zahl nicht verfügbar ist", async () => {
    mockApi({ "/auth/me": ME, "/watchlist": [{ ...INSTRUMENT, quote: null }] });
    renderApp("/");
    await waitFor(() => expect(screen.getByTestId("pattern-count").textContent).toContain("nicht verfügbar"));
  });
});
