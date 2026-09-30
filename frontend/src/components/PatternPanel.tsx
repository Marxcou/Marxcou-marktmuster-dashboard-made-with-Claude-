import type { PatternBacktest, PatternDetection } from "../lib/api";
import { formatDate, formatDateTime, formatNumber, formatPercentPoints, formatShare } from "../lib/format";
import { levelLabels, STATUS_TEXT } from "../lib/analysis";
import { AiExplanation } from "./AiExplanation";
import { SourceTip } from "./SourceTip";

const MIN_SAMPLE_HINT = 30;

// Grundregel 3: Was fehlt, wird ausdrücklich genannt statt verschwiegen oder ergänzt.
export function missingParts(p: PatternDetection): string[] {
  const m: string[] = [];
  if (p.criteria.length === 0) m.push("Kriterien mit tatsächlichen Werten");
  if (!p.confidence?.breakdown?.length) m.push("Aufschlüsselung der Konfidenz");
  if (p.scenarios.length < 2) m.push("mindestens zwei Szenarien");
  if (p.confirmation_level == null || p.invalidation_level == null) m.push("Bestätigungs- und Ungültigkeitsniveau");
  return m;
}

export function BacktestBlock({ b }: { b: PatternBacktest | null }) {
  if (!b || b.status !== "berechnet" || b.hit_rate == null || b.sample_size == null) {
    return (
      <div className="rounded border border-amber-700/50 bg-amber-950/30 p-3 text-sm text-amber-200" data-testid="backtest-missing">
        <p className="font-semibold">Historische Trefferquote: nicht verfügbar</p>
        <p>{b?.note ?? "Für dieses Muster liegt noch kein Backtest vor. Es wird keine Trefferquote geschätzt."}</p>
      </div>
    );
  }
  const horizon = b.horizon_bars != null ? `innerhalb von ${b.horizon_bars} Kerzen` : "im Beobachtungszeitraum";
  const move = b.min_move_pct != null ? `um mindestens ${formatNumber(b.min_move_pct, 1)} %` : "";
  return (
    <div className="rounded border border-slate-700 p-3 text-sm" data-testid="backtest">
      <p>
        Historisch folgte auf bestätigte Muster dieser Art in <strong>{formatShare(b.hit_rate)}</strong> der <strong>{b.sample_size}</strong> Fälle eine Bewegung {move} in die Richtung des Musters {horizon}.
      </p>
      <dl className="mt-2 grid grid-cols-2 gap-x-4 gap-y-1 text-xs text-slate-300 sm:grid-cols-4">
        <div><dt className="text-slate-400">Stichprobengröße</dt><dd>{b.sample_size}</dd></div>
        <div><dt className="text-slate-400">95-%-Intervall</dt><dd>{b.ci_low != null && b.ci_high != null ? `${formatShare(b.ci_low)} bis ${formatShare(b.ci_high)}` : "nicht verfügbar"}</dd></div>
        <div><dt className="text-slate-400">Basisrate (alle Handelstage)</dt><dd>{b.base_rate != null ? formatShare(b.base_rate) : "nicht verfügbar"}</dd></div>
        <div><dt className="text-slate-400">Backtest-Lauf</dt><dd>{b.computed_at ? formatDate(b.computed_at) : `Nr. ${b.run_id ?? "?"}`}</dd></div>
      </dl>
      {b.not_better_than_random && <p className="mt-2 font-semibold text-amber-300" data-testid="not-better">Historisch nicht besser als Zufall.{b.verdict_text ? ` ${b.verdict_text}` : ""}</p>}
      {b.not_better_than_random === false && b.verdict_text && <p className="mt-2 text-xs text-slate-300">{b.verdict_text}</p>}
      {b.mean_return_pct != null && b.horizon_bars != null && (
        <p className="mt-2 text-xs text-slate-300" data-testid="backtest-return">
          Mittlere Veränderung {b.horizon_bars} Kerzen nach dem Ausgangspunkt, in Richtung des Musters gerechnet: {formatPercentPoints(b.mean_return_pct)}
          {b.median_return_pct != null && ` (Median ${formatPercentPoints(b.median_return_pct)})`}
          {b.base_mean_return_pct != null && `; alle Handelstage: ${formatPercentPoints(b.base_mean_return_pct)}`}.
        </p>
      )}
      {b.sample_size < MIN_SAMPLE_HINT && <p className="mt-1 text-xs text-amber-300">Kleine Stichprobe (weniger als {MIN_SAMPLE_HINT} Fälle): die Aussagekraft ist gering.</p>}
      <p className="mt-2 text-xs text-slate-400">
        {b.universe && `Datenbasis: ${b.universe}. `}{b.date_range && `Zeitraum: ${b.date_range}. `}{b.survivorship_note}
      </p>
      {b.note && <p className="mt-1 text-xs text-slate-400">{b.note}</p>}
      {(b.method || b.source) && (
        <details className="mt-1 text-xs text-slate-400">
          <summary className="cursor-pointer">Wie wurde das berechnet?</summary>
          {b.method && <p className="mt-1">{b.method}</p>}
          {b.source && <p className="mt-1">Quelle: <a className="underline" href={b.source.homepage} target="_blank" rel="noreferrer">{b.source.name}</a>{b.source.fetched_to && `, abgerufen ${formatDate(b.source.fetched_to)}`}</p>}
        </details>
      )}
    </div>
  );
}

export function PatternPanel({ p, onClose }: { p: PatternDetection; onClose?: () => void }) {
  const missing = missingParts(p);
  const labels = levelLabels(p.direction_if_confirmed);
  return (
    <article className="rounded-lg border border-violet-800/60 bg-slate-900 p-4" data-testid="pattern-panel" aria-label={`Erklärung: ${p.name}`}>
      <header className="flex flex-wrap items-start justify-between gap-2">
        <div>
          <h2 className="text-lg font-semibold">{p.name}</h2>
          <p className="text-sm text-slate-300">
            Status: <span data-testid="pattern-status">{STATUS_TEXT[p.status] ?? p.status_label}</span>
            {p.direction_if_confirmed !== "offen" ? ` · Bei Bestätigung beschreibt das Muster eine Bewegung ${p.direction_if_confirmed}` : " · Richtung ergibt sich erst aus dem Ausbruch"}
          </p>
          <p className="text-xs text-slate-400" data-testid="pattern-range">Lage im Chart: {formatDate(p.start_ts)} bis {formatDate(p.end_ts)} · Zeitraster {p.timeframe}</p>
        </div>
        {onClose && <button type="button" onClick={onClose} className="rounded border border-slate-700 px-2 py-1 text-xs">Schließen</button>}
      </header>

      {missing.length > 0 && (
        <p role="alert" className="mt-3 rounded border border-rose-700/60 bg-rose-950/40 p-2 text-sm text-rose-200" data-testid="pattern-incomplete">
          Diese Erkennung ist unvollständig erklärt. Es fehlen: {missing.join(", ")}. Die Angaben sind mit Vorsicht zu lesen.
        </p>
      )}

      {p.explanation && <p className="mt-3 text-sm" data-testid="pattern-explanation">{p.explanation}</p>}
      <AiExplanation kind="pattern" id={p.id} />

      <section className="mt-4" aria-labelledby={`k-${p.id}`}>
        <h3 id={`k-${p.id}`} className="mb-1 font-semibold">Schlüsselpunkte</h3>
        <ul className="text-sm text-slate-300">
          {p.key_points.map((k) => <li key={`${k.role}-${k.ts}`}>{k.label}: {formatNumber(k.price)} am {formatDate(k.ts)}</li>)}
        </ul>
      </section>

      <section className="mt-4" aria-labelledby={`c-${p.id}`}>
        <h3 id={`c-${p.id}`} className="mb-1 font-semibold">Erfüllte Kriterien mit tatsächlichen Werten</h3>
        <div className="overflow-x-auto">
          <table className="w-full min-w-[36rem] text-left text-sm" data-testid="criteria-table">
            <thead className="text-xs text-slate-400"><tr><th className="pr-2">Kriterium</th><th className="pr-2">Regel</th><th className="pr-2">Tatsächlicher Wert</th><th className="pr-2">Ergebnis</th><th className="pr-2 text-right">Teilwert</th><th className="text-right">Gewicht</th></tr></thead>
            <tbody>
              {p.criteria.map((c) => (
                <tr key={c.key} className="border-t border-slate-800 align-top">
                  <td className="py-1 pr-2">{c.name}{!c.required && <span className="block text-xs text-slate-400">Qualitätskriterium</span>}</td>
                  <td className="py-1 pr-2 text-slate-300">{c.rule}</td>
                  <td className="py-1 pr-2">{c.actual_text}</td>
                  <td className="py-1 pr-2">{c.passed ? "erfüllt" : "nicht erfüllt"}</td>
                  <td className="py-1 pr-2 text-right">{formatNumber(c.sub_score)}</td>
                  <td className="py-1 text-right">{formatNumber(c.weight)}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </section>

      <section className="mt-4" aria-labelledby={`f-${p.id}`}>
        <h3 id={`f-${p.id}`} className="mb-1 font-semibold">Konfidenz der Erkennung: <span data-testid="confidence">{formatShare(p.confidence.score)}</span></h3>
        <p className="text-sm text-slate-300">{p.confidence.method}</p>
        <p className="mt-1 text-xs text-slate-400">Die Konfidenz beschreibt nur, wie genau die Kerzen zur Musterdefinition passen. Sie ist keine Wahrscheinlichkeit für den weiteren Verlauf.</p>
        <table className="mt-2 w-full max-w-xl text-left text-sm" data-testid="confidence-table">
          <thead className="text-xs text-slate-400"><tr><th>Kriterium</th><th className="text-right">Gewicht</th><th className="text-right">Teilwert</th><th className="text-right">Beitrag</th></tr></thead>
          <tbody>
            {p.confidence.breakdown.map((b) => (
              <tr key={b.key} className="border-t border-slate-800"><td className="py-0.5">{b.name}</td><td className="text-right">{formatNumber(b.weight)}</td><td className="text-right">{formatNumber(b.sub_score)}</td><td className="text-right">{formatNumber(b.contribution, 3)}</td></tr>
            ))}
            <tr className="border-t border-slate-600 font-semibold"><td>Summe</td><td /><td /><td className="text-right">{formatNumber(p.confidence.breakdown.reduce((s, b) => s + b.contribution, 0), 3)}</td></tr>
          </tbody>
        </table>
      </section>

      <section className="mt-4" aria-labelledby={`s-${p.id}`}>
        <h3 id={`s-${p.id}`} className="mb-1 font-semibold">Mögliche Szenarien</h3>
        <div className="grid gap-3 sm:grid-cols-2">
          {p.scenarios.map((s) => (
            <div key={s.kind} className="rounded border border-slate-700 p-3 text-sm" data-testid="scenario">
              <h4 className="font-semibold">{s.title}</h4>
              <p className="text-slate-300">{s.trigger_rule}</p>
              <p className="mt-1 text-xs text-slate-400">Niveau: {s.trigger_level != null ? formatNumber(s.trigger_level) : "nicht verfügbar"}</p>
              <p className="mt-1">{s.description}</p>
              {s.historical?.text && <p className="mt-1 text-xs text-slate-300">Historisch: {s.historical.text}{s.historical.sample_size != null ? ` (${s.historical.sample_size} Fälle)` : ""}</p>}
            </div>
          ))}
        </div>
        <p className="mt-2 text-sm" data-testid="levels">
          {labels.confirmation}: {p.confirmation_level != null ? formatNumber(p.confirmation_level) : "nicht verfügbar"} · {labels.invalidation}: {p.invalidation_level != null ? formatNumber(p.invalidation_level) : "nicht verfügbar"}
        </p>
        <p className="text-xs text-slate-400">{p.direction_if_confirmed === "offen"
          ? "Beide Niveaus beschreiben nur, ab wann das Muster per Schlusskurs als nach oben bzw. unten aufgelöst gilt. Ungültig wird es, wenn die Spitze der Linien oder das Fristende ohne Ausbruch erreicht wird. Sie sind keine Kursziele."
          : "Beide Niveaus beschreiben nur, ab wann das Muster per Schlusskurs als bestätigt bzw. ungültig gilt. Sie sind keine Kursziele."}</p>
      </section>

      <section className="mt-4" aria-labelledby={`b-${p.id}`}>
        <h3 id={`b-${p.id}`} className="mb-1 font-semibold">Historische Zuverlässigkeit (Backtest)</h3>
        <BacktestBlock b={p.backtest} />
      </section>

      <details className="mt-4 text-xs text-slate-400">
        <summary className="cursor-pointer">Verfahren, Parameter und Datenbasis</summary>
        <p className="mt-1">Regelbasiert und deterministisch. Version {p.algo_version}, Parameter-Kennung {p.params_hash}, erkannt {formatDateTime(p.detected_at)}.</p>
        <pre className="mt-1 overflow-x-auto rounded bg-slate-950 p-2">{JSON.stringify(p.params, null, 2)}</pre>
        <p className="mt-1">Kerzen: {p.data_basis.bar_count} von {formatDate(p.data_basis.bars_from)} bis {formatDate(p.data_basis.bars_to)}, zuletzt abgerufen {formatDateTime(p.data_basis.last_fetched_at)}.</p>
        <div className="mt-1 flex flex-wrap gap-2">{p.data_basis.sources.map((s) => <SourceTip key={s.key} source={s} fetchedAt={p.data_basis.last_fetched_at} />)}</div>
      </details>
    </article>
  );
}
