import type { ForecastBacktest, ForecastMedianLine, ForecastResponse, ForecastStep, PatternDetection } from "../lib/api";
import { BAND_FILL, BANDS, EXAMPLE_COLOR, HORIZONS, MEDIAN_COLOR, validExamplePaths, coverageNote, levelPosition, metricName, metricVsNaive, scenarioLevels, validSteps } from "../lib/forecast";
import { formatDate, formatDateTime, formatNumber, formatShare } from "../lib/format";
import { AiExplanation } from "./AiExplanation";
import { SourceTip } from "./SourceTip";

const money = (v: number, currency: string) => new Intl.NumberFormat("de-DE", { style: "currency", currency }).format(v);

// Grundregel 4: Prognosegüte im Vergleich zur naiven Referenz "Kurs bleibt gleich"; fehlt der Backtest, wird das ausdrücklich gesagt.
export function ForecastBacktestBlock({ b }: { b: ForecastBacktest | null }) {
  if (!b || b.status !== "berechnet" || b.sample_size == null) {
    return (
      <div className="rounded border border-amber-700/50 bg-amber-950/30 p-3 text-sm text-amber-200" data-testid="forecast-backtest-missing">
        <p className="font-semibold">Prognosegüte (Backtest): nicht verfügbar</p>
        <p>{b?.note ?? "Für diese Methode liegt noch kein Backtest vor. Wie zuverlässig der Korridor historisch war, ist deshalb unbekannt."}</p>
      </div>
    );
  }
  return (
    <div className="rounded border border-slate-700 p-3 text-sm" data-testid="forecast-backtest">
      <p className="font-semibold">Prognosegüte im Backtest (rollierend, nur mit damals bekannten Daten)</p>
      <p className="text-xs text-slate-400">
        Stichprobe: {b.sample_size} Prognosen{b.horizon_bars != null && ` über je ${b.horizon_bars} Kerzen`}{b.universe && ` · ${b.universe}`}{b.date_range && ` · ${b.date_range}`}
      </p>
      {b.coverage && b.coverage.length > 0 && (
        <table className="mt-2 w-full text-xs" data-testid="coverage-table">
          <caption className="pb-1 text-left text-slate-400">Abdeckung: Anteil der tatsächlichen Ergebnisse, die im Band lagen</caption>
          <thead><tr className="text-left text-slate-400"><th className="py-1">Band</th><th>Sollwert</th><th>Tatsächlich</th><th>Einordnung</th></tr></thead>
          <tbody>{b.coverage.map((c) => (
            <tr key={c.nominal} className="border-t border-slate-800"><td className="py-1">{Math.round(c.nominal * 100)} %</td><td>{formatShare(c.nominal)}</td><td>{formatShare(c.observed, 1)}</td><td>{coverageNote(c.nominal, c.observed)}</td></tr>
          ))}</tbody>
        </table>
      )}
      {b.metrics && b.metrics.length > 0 && (
        <table className="mt-3 w-full text-xs" data-testid="metrics-table">
          <caption className="pb-1 text-left text-slate-400">Fehlermaße gegen die naive Referenz „Kurs bleibt gleich“ (in Prozent des Kurses am Prognoseursprung, kleiner ist besser)</caption>
          <thead><tr className="text-left text-slate-400"><th className="py-1">Maß</th><th>Methode</th><th>Referenz</th><th>Vergleich</th></tr></thead>
          <tbody>{b.metrics.map((m) => {
            const v = metricVsNaive(m);
            return (
              <tr key={m.key} className="border-t border-slate-800">
                <td className="py-1">{metricName(m)}</td><td>{m.model != null ? `${formatNumber(m.model, 2)}${m.unit ? ` ${m.unit}` : ""}` : "nicht verfügbar"}</td><td>{m.naive != null ? `${formatNumber(m.naive, 2)}${m.unit ? ` ${m.unit}` : ""}` : "nicht verfügbar"}</td>
                <td>{v.ratio != null && `${formatNumber(v.ratio, 2)}-fach: `}{v.text}</td>
              </tr>
            );
          })}</tbody>
        </table>
      )}
      {b.skill != null && <p className="mt-2 text-xs text-slate-300" data-testid="skill">Verbesserung des Median-Fehlers gegenüber der Referenz: {formatNumber(b.skill * 100, 1)} %{b.dm_p_value != null && `; Signifikanztest (Diebold-Mariano, einseitig): p = ${formatNumber(b.dm_p_value, 2)}`}.</p>}
      {b.by_horizon && b.by_horizon.length > 0 && (
        <table className="mt-3 w-full text-xs" data-testid="horizon-backtest-table">
          <caption className="pb-1 text-left text-slate-400">Ergebnis nach Horizont</caption>
          <thead><tr className="text-left text-slate-400"><th className="py-1">Horizont</th><th>Stichprobe</th><th>Verbesserung</th><th>p-Wert</th><th>Besser als Referenz</th></tr></thead>
          <tbody>{b.by_horizon.map((h) => (
            <tr key={h.horizon_bars} className="border-t border-slate-800">
              <td className="py-1">{h.horizon_bars} Kerzen</td><td>{h.sample_size ?? "?"}</td><td>{h.skill != null ? `${formatNumber(h.skill * 100, 1)} %` : "nicht verfügbar"}</td>
              <td>{h.dm_p_value != null ? formatNumber(h.dm_p_value, 2) : "nicht verfügbar"}</td><td>{h.better_than_naive == null ? "nicht beurteilbar" : h.better_than_naive ? "ja, nachweisbar" : "nicht nachweisbar"}</td>
            </tr>
          ))}</tbody>
        </table>
      )}
      {b.better_than_naive === false && <p className="mt-2 font-semibold text-amber-300" data-testid="not-better-naive">Historisch nicht nachweisbar besser als die naive Referenz „Kurs bleibt gleich“.{b.verdict_text ? ` ${b.verdict_text}` : ""}</p>}
      {b.better_than_naive === true && b.verdict_text && <p className="mt-2 text-xs text-slate-300">{b.verdict_text}</p>}
      {b.better_than_naive == null && <p className="mt-2 text-xs text-amber-300">Ein Vergleich mit der Referenz liegt nicht vor.</p>}
      {b.sample_size < 30 && <p className="mt-1 text-xs text-amber-300">Kleine Stichprobe (weniger als 30 Prognosen): die Aussagekraft ist gering.</p>}
    </div>
  );
}

const MEDIAN_FALLBACK = "Die Linie verbindet je Handelstag den Median (50-%-Quantil) des Korridors: die Hälfte der simulierten Kurse liegt darüber, die Hälfte darunter. Sie ist die Mitte des Korridors, kein erwarteter Kurs.";

// Mittlerer Verlauf (Grundregel 4): nur als Mitte des Korridors, immer mit dem Backtest-Fehler dieser Linie je Horizont.
function MedianLineBlock({ line, shown }: { line: ForecastMedianLine | null | undefined; shown: boolean }) {
  const errors = line?.errors ?? [];
  return (
    <div data-testid="median-line">
      <h3 className="text-sm font-semibold"><span className="mr-2 inline-block w-5 border-t-2 border-dashed align-middle" style={{ borderColor: MEDIAN_COLOR }} />{line?.name ?? "Mittlerer Verlauf der Modellverteilung"}</h3>
      <p className="mt-1 text-xs text-slate-300">{line?.description ?? MEDIAN_FALLBACK}</p>
      {!shown && <p className="mt-1 text-xs text-slate-400">Im Chart ausgeblendet (Schalter „Mittlerer Verlauf“).</p>}
      {errors.length > 0 ? (
        <table className="mt-2 w-full text-xs" data-testid="median-error-table">
          <caption className="pb-1 text-left text-slate-400">So weit lag der tatsächliche Schlusskurs im Backtest im Mittel von dieser Linie entfernt (in Prozent des Kurses am Prognoseursprung)</caption>
          <thead><tr className="text-left text-slate-400"><th className="py-1">Nach</th><th>Abweichung der Linie</th><th>Referenz „Kurs bleibt gleich“</th><th>Stichprobe</th></tr></thead>
          <tbody>{errors.map((e) => (
            <tr key={e.horizon_bars} className="border-t border-slate-800">
              <td className="py-1">{e.horizon_bars} Handelstagen</td>
              <td>{e.model != null ? `± ${formatNumber(e.model, 2)} %` : "nicht verfügbar"}</td>
              <td>{e.naive != null ? `± ${formatNumber(e.naive, 2)} %` : "nicht verfügbar"}</td>
              <td>{e.sample_size ?? "?"} Prognosen</td>
            </tr>
          ))}</tbody>
        </table>
      ) : (
        <p className="mt-2 text-xs text-amber-300" data-testid="median-error-missing">Abweichung dieser Linie im Backtest: nicht verfügbar, weil noch kein Prognose-Backtest vorliegt.</p>
      )}
    </div>
  );
}

function HorizonTable({ steps, currency, lastClose }: { steps: ForecastStep[]; currency: string; lastClose: number | null }) {
  const last = steps[steps.length - 1];
  return (
    <table className="mt-2 w-full text-xs" data-testid="horizon-table">
      <caption className="pb-1 text-left text-slate-400">Wahrscheinlichkeitsbereiche am Ende des Horizonts ({formatDate(last.ts)})</caption>
      <thead><tr className="text-left text-slate-400"><th className="py-1">Bereich</th><th>Von</th><th>Bis</th>{lastClose != null && <th>Abstand zum letzten Schlusskurs</th>}</tr></thead>
      <tbody>{[...BANDS].reverse().map((b) => {
        const lo = last.quantiles[b.lower], hi = last.quantiles[b.upper];
        return (
          <tr key={b.level} className="border-t border-slate-800">
            <td className="py-1"><span className="mr-2 inline-block h-2 w-4 align-middle" style={{ background: BAND_FILL[b.level] }} />{b.level} %</td>
            <td>{money(lo, currency)}</td><td>{money(hi, currency)}</td>
            {lastClose != null && <td>{formatNumber(((lo / lastClose) - 1) * 100, 1)} % bis {formatNumber(((hi / lastClose) - 1) * 100, 1)} %</td>}
          </tr>
        );
      })}</tbody>
    </table>
  );
}

export function ForecastPanel({ data, loading, error, horizon, onHorizon, currency, pattern, showMedian = true, showExamples = false }: {
  data: ForecastResponse | undefined; loading: boolean; error: boolean; horizon: number; onHorizon: (h: number) => void; currency: string; pattern: PatternDetection | null;
  showMedian?: boolean; showExamples?: boolean;
}) {
  const examples = validExamplePaths(data?.example_paths);
  const steps = validSteps(data?.steps ?? []);
  currency = data?.currency ?? currency;
  const last = steps[steps.length - 1];
  const levels = scenarioLevels(pattern);
  const link = pattern ? data?.pattern_scenarios?.find((l) => l.detection_id === pattern.id) ?? null : null;
  return (
    <section className="rounded-lg border border-sky-900/60 bg-slate-900 p-4" data-testid="forecast-panel" aria-label="Prognosekorridor">
      <div className="flex flex-wrap items-center gap-3">
        <h2 className="font-semibold">Prognosekorridor</h2>
        <div role="group" aria-label="Prognosehorizont" className="flex gap-1">
          {HORIZONS.map((h) => (
            <button key={h} type="button" aria-pressed={h === horizon} onClick={() => onHorizon(h)} className={`rounded border px-2 py-0.5 text-xs ${h === horizon ? "border-sky-500 bg-sky-900" : "border-slate-700"}`}>{h} Tage</button>
          ))}
        </div>
      </div>
      <p className="mt-1 text-xs text-slate-400" data-testid="forecast-note">{data?.note ? `${data.note} ` : ""}Der Korridor zeigt, in welchem Bereich Kurse nach dem gewählten Verfahren mit den genannten Wahrscheinlichkeiten liegen könnten. Die gestrichelte Linie ist seine Mitte (Median), keine Einzelprognose und keine Aussage, was geschehen wird.</p>

      {data?.is_demo && <p className="mt-2 text-xs font-semibold text-fuchsia-300" data-testid="forecast-demo">Beispieldaten (Demo-Modus): keine echte Prognose.</p>}
      {loading && <p className="mt-2 text-sm text-slate-400">Lade Prognose …</p>}
      {error && <p role="alert" className="mt-2 text-sm text-rose-300">Prognose konnte nicht geladen werden (Backend nicht erreichbar).</p>}
      {data?.pending && <p className="mt-2 text-sm text-slate-300" role="status" data-testid="forecast-pending">Prognose wird berechnet: {data.empty_reason}</p>}
      {data?.empty_reason && !data.pending && <p className="mt-2 text-sm text-amber-300" data-testid="no-forecast">Kein Prognosekorridor: {data.empty_reason}</p>}
      {data && !data.empty_reason && steps.length === 0 && <p className="mt-2 text-sm text-amber-300" data-testid="no-forecast">Kein Prognosekorridor: Das Backend hat keine vollständigen Wahrscheinlichkeitsbereiche geliefert.</p>}

      {data && steps.length > 0 && (
        <div className="mt-3 space-y-4">
          <AiExplanation kind="forecast" id={data.instrument_id} />
          <p className="text-xs text-slate-300" data-testid="forecast-basis">
            Berechnet aus Kursdaten bis {data.based_on_until ? formatDateTime(data.based_on_until) : "(Zeitpunkt nicht angegeben)"}{data.generated_at && `, erstellt ${formatDateTime(data.generated_at)}`}. Verfahren {data.method?.name ?? "(nicht angegeben)"}, Version {data.algo_version || "?"}.
          </p>
          <ul className="flex flex-wrap gap-3 text-xs" data-testid="forecast-legend" aria-label="Legende der Wahrscheinlichkeitsbereiche">
            {[...BANDS].reverse().map((b) => (<li key={b.level}><span className="mr-1 inline-block h-3 w-5 align-middle" style={{ background: BAND_FILL[b.level] }} />{b.level} %-Bereich</li>))}
          </ul>
          <ul className="flex flex-wrap gap-3 text-xs" data-testid="forecast-line-legend" aria-label="Legende der Linien im Korridor">
            <li><span className="mr-1 inline-block w-5 border-t-2 border-dashed align-middle" style={{ borderColor: MEDIAN_COLOR }} />Mittlerer Verlauf (Median){!showMedian && " (ausgeblendet)"}</li>
            {examples.length > 0 && <li><span className="mr-1 inline-block w-5 border-t align-middle" style={{ borderColor: EXAMPLE_COLOR }} />Beispielpfade ({examples.length}){!showExamples && " (ausgeblendet)"}</li>}
          </ul>
          <HorizonTable steps={steps} currency={currency} lastClose={data.last_close} />
          <MedianLineBlock line={data.median_line} shown={showMedian} />
          {examples.length > 0 && (
            <div data-testid="example-paths">
              <h3 className="text-sm font-semibold"><span className="mr-2 inline-block w-5 border-t align-middle" style={{ borderColor: EXAMPLE_COLOR }} />Beispielpfade aus der Simulation</h3>
              <p className="mt-1 text-xs text-slate-300">{data.example_paths_note ?? "Einzelne simulierte Verläufe als Beispiele; keiner ist wahrscheinlicher als die übrigen."}</p>
              {!showExamples && <p className="mt-1 text-xs text-slate-400">Im Chart einblenden mit dem Schalter „Beispielpfade“.</p>}
            </div>
          )}

          {pattern && levels.length > 0 && (
            <div data-testid="scenario-levels">
              <h3 className="text-sm font-semibold">Szenario-Niveaus von „{pattern.name}“ im Vergleich zum Korridor</h3>
              <ul className="mt-1 space-y-1 text-xs">
                {levels.map((l) => (
                  <li key={l.key}><span className="text-slate-100">{l.label}: {money(l.price, currency)}</span>
                    {data.last_close != null && ` (${formatNumber((l.price / data.last_close - 1) * 100, 1)} % zum letzten Schlusskurs)`} – {levelPosition(l.price, last).text}.</li>
                ))}
              </ul>
              <p className="mt-1 text-xs text-slate-400">Die Angabe beschreibt nur die Lage des Niveaus im Korridor.</p>
            </div>
          )}
          {link && (
            <div data-testid="pattern-scenario-link">
              <h3 className="text-sm font-semibold">Simulation und Muster-Backtest für „{link.name}“</h3>
              <table className="mt-1 w-full text-xs">
                <thead><tr className="text-left text-slate-400"><th className="py-1">Szenario</th><th>Niveau</th><th>Simulierte Pfade</th><th>Historisch (Muster-Backtest)</th></tr></thead>
                <tbody>{link.scenarios.map((sc) => (
                  <tr key={sc.kind} className="border-t border-slate-800 align-top">
                    <td className="py-1">{sc.title}</td><td>{sc.trigger_level != null ? money(sc.trigger_level, currency) : "?"}</td>
                    <td>{sc.model_probability_text ?? (sc.model_probability != null ? formatShare(sc.model_probability) : "nicht verfügbar")}</td>
                    <td>{sc.historical?.share != null ? `${formatShare(sc.historical.share)} von ${sc.historical.sample_size ?? "?"} Fällen` : "nicht verfügbar (kein Muster-Backtest)"}</td>
                  </tr>
                ))}</tbody>
              </table>
              {link.neither_probability != null && <p className="mt-1 text-xs text-slate-300">In {formatShare(link.neither_probability)} der simulierten Pfade wird keines der beiden Niveaus innerhalb des Horizonts erreicht.</p>}
              <p className="mt-1 text-xs text-slate-400">{link.note}</p>
            </div>
          )}

          <details className="text-xs" data-testid="forecast-method">
            <summary className="cursor-pointer font-semibold text-slate-200">Wie wird das berechnet?</summary>
            <p className="mt-1 text-slate-300">{data.method?.description ?? "Für dieses Verfahren liegt keine Beschreibung vor."}</p>
            {data.method?.assumptions && data.method.assumptions.length > 0 && <><p className="mt-2 font-semibold text-slate-300">Annahmen</p><ul className="list-disc pl-5 text-slate-300">{data.method.assumptions.map((a) => <li key={a}>{a}</li>)}</ul></>}
            {data.method?.limitations && data.method.limitations.length > 0 && <><p className="mt-2 font-semibold text-slate-300">Grenzen des Verfahrens</p><ul className="list-disc pl-5 text-slate-300">{data.method.limitations.map((a) => <li key={a}>{a}</li>)}</ul></>}
            {data.method?.params && Object.keys(data.method.params).length > 0 && (
              <dl className="mt-1 grid grid-cols-2 gap-x-4 gap-y-0.5 sm:grid-cols-3">{Object.entries(data.method.params).map(([k, v]) => (<div key={k}><dt className="inline text-slate-400">{k}: </dt><dd className="inline">{String(v)}</dd></div>))}</dl>
            )}
          </details>

          <ForecastBacktestBlock b={data.backtest} />

          {data.comparison && data.comparison.length > 0 && (
            <div data-testid="forecast-comparison">
              <h3 className="text-sm font-semibold">Vergleichsverfahren</h3>
              <ul className="mt-1 space-y-1 text-xs text-slate-300">
                {data.comparison.map((c) => {
                  const l = validSteps(c.steps).slice(-1)[0];
                  const b80 = BANDS.find((b) => b.level === 80)!;
                  return (
                    <li key={c.method_key}>{c.name}: 80-%-Bereich am Ende {l ? `${money(l.quantiles[b80.lower], currency)} bis ${money(l.quantiles[b80.upper], currency)}` : "nicht verfügbar"}
                      <details className="mt-1"><summary className="cursor-pointer text-slate-400">Backtest dieses Verfahrens</summary><div className="mt-1"><ForecastBacktestBlock b={c.backtest ?? null} /></div></details>
                    </li>
                  );
                })}
              </ul>
            </div>
          )}
          {data.data_basis && <div className="flex flex-wrap gap-2">{data.data_basis.sources.map((s) => <SourceTip key={s.key} source={s} fetchedAt={data.data_basis!.last_fetched_at} />)}</div>}
        </div>
      )}
    </section>
  );
}
