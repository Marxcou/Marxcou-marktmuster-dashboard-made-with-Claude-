"""Muster-Backtest mit echten Kursdaten (Workstream 3C): Tagesdaten laden, Backtest je Aktie rechnen,
Ergebnis je Mustertyp in backtest_runs schreiben (kind="pattern", subject=pattern_type).

Grundregel 6: Es werden nur Daten verwendet, die eine echte Kursquelle geliefert hat (Stooq oder Yahoo,
siehe backtest_job).
Fehlen Daten, fehlt der Wert im Lauf und wird als fehlend aufgeführt; es wird nichts ergänzt oder geschätzt.
Grundregel 2: Jeder Lauf nennt Quelle, Abrufzeitraum, verwendete und fehlende Werte."""
import json
import logging
from collections.abc import Callable, Iterable
from concurrent.futures import ProcessPoolExecutor
from dataclasses import asdict, dataclass, field
from datetime import UTC, date, datetime, timedelta
from pathlib import Path
from typing import Any

from sqlalchemy.orm import Session

from app.adapters.base import AdapterMetadata, BarRecord, PriceAdapter, Timeframe
from app.adapters.http import SourceError
from app.analysis import fmt
from app.analysis.backtest import (
    BACKTEST_VERSION,
    SURVIVORSHIP_NOTE,
    BacktestConfig,
    InstrumentResult,
    PatternSummary,
    backtest_instrument,
    summarize,
)
from app.analysis.catalog import PATTERN_NAMES
from app.analysis.params import ALGO_VERSION, Params, default_params, params_hash
from app.analysis.series import Bars
from app.models import BacktestRun

log = logging.getLogger("backtest")

TIMEFRAME: Timeframe = "1d"
METHOD_TEXT = (
    "Walk-forward ohne Blick in die Zukunft: Die Mustererkennung läuft schrittweise nur auf den Kerzen bis zum "
    "jeweiligen Tag. Ein Fall ist ein bestätigtes Muster; Ausgangspunkt ist der Schlusskurs am Tag der "
    "Bestätigung bzw. am ersten Tag, an dem das Muster sichtbar war (der spätere Tag). Treffer: Ein Schlusskurs "
    "innerhalb von {h} Kerzen liegt mindestens {x} in Richtung des Musters. Basisrate: derselbe Test für jeden "
    "Handelstag derselben Aktien im selben Zeitraum, gewichtet wie die Fälle. 95-%-Intervall nach Wilson."
)


@dataclass
class LoadedSeries:
    key: str  # SYMBOL.BÖRSE
    bars: Bars
    fetched_at: datetime


@dataclass
class DataReport:
    series: list[LoadedSeries] = field(default_factory=list)
    missing: dict[str, str] = field(default_factory=dict)  # SYMBOL.BÖRSE -> Grund


# ---------- Laden (mit Dateicache, damit ein zweiter Lauf die Quelle nicht erneut belastet) ----------

def _cache_file(cache_dir: Path, source_key: str, symbol: str, exchange: str) -> Path:
    return cache_dir / source_key / f"{symbol}.{exchange}.json"


def _read_cache(path: Path, max_age: timedelta, now: datetime) -> tuple[list[BarRecord], datetime] | None:
    if not path.exists():
        return None
    blob = json.loads(path.read_text(encoding="utf-8"))
    fetched = datetime.fromisoformat(blob["fetched_at"])
    if now - fetched > max_age:
        return None
    recs = [BarRecord(symbol=blob["symbol"], exchange=blob["exchange"], timeframe="1d",
                      ts_utc=datetime.fromisoformat(r[0]), open=r[1], high=r[2], low=r[3], close=r[4], volume=r[5],
                      source_key=blob["source_key"], fetched_at=fetched) for r in blob["bars"]]
    return recs, fetched


def _write_cache(path: Path, recs: list[BarRecord], source_key: str, symbol: str, exchange: str,
                 fetched: datetime) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    blob = {"symbol": symbol, "exchange": exchange, "source_key": source_key, "fetched_at": fetched.isoformat(),
            "bars": [[r.ts_utc.isoformat(), r.open, r.high, r.low, r.close, r.volume] for r in recs]}
    path.write_text(json.dumps(blob), encoding="utf-8")


def to_bars(recs: list[BarRecord], today: date) -> Bars:
    """Nur abgeschlossene Tage (die Kerze von heute kann noch laufen), sortiert, ohne doppelte Tage."""
    by_day: dict[datetime, BarRecord] = {}
    for r in recs:
        if r.ts_utc.date() < today:
            by_day[r.ts_utc] = r
    rows = [by_day[k] for k in sorted(by_day)]
    return Bars.from_lists([r.ts_utc for r in rows], [r.open for r in rows], [r.high for r in rows],
                           [r.low for r in rows], [r.close for r in rows], [r.volume for r in rows])


def load_universe(adapter: PriceAdapter, universe: Iterable[tuple[str, str]], start: datetime, now: datetime,
                  cache_dir: Path | None, max_cache_age: timedelta, min_bars: int) -> DataReport:
    meta = adapter.metadata()
    report = DataReport()
    for symbol, exchange in universe:
        key = f"{symbol}.{exchange}"
        cached = _read_cache(_cache_file(cache_dir, meta.key, symbol, exchange), max_cache_age, now) \
            if cache_dir else None
        if cached is not None:
            recs, fetched = cached
        else:
            try:
                recs = adapter.fetch_bars(symbol, exchange, TIMEFRAME, start, now)
            except SourceError as exc:
                report.missing[key] = f"{meta.name}: {exc}"
                log.warning("%s: keine Daten (%s)", key, exc)
                continue
            fetched = now
            if cache_dir and recs:
                _write_cache(_cache_file(cache_dir, meta.key, symbol, exchange), recs, meta.key, symbol, exchange,
                             fetched)
        recs = [r for r in recs if r.ts_utc >= start and r.source_key == meta.key]
        bars = to_bars(recs, now.date())
        if len(bars) < min_bars:
            report.missing[key] = f"{meta.name}: nur {len(bars)} Tageskerzen (mindestens {min_bars} nötig)"
            continue
        report.series.append(LoadedSeries(key, bars, fetched))
        log.info("%s: %d Tageskerzen", key, len(bars))
    return report


# ---------- Rechnen ----------

def _run_one(args: tuple[str, Bars, Params, BacktestConfig]) -> InstrumentResult:
    key, bars, params, cfg = args
    return backtest_instrument(key, bars, TIMEFRAME, params, cfg)


def compute(series: list[LoadedSeries], cfg: BacktestConfig, params: Params, workers: int,
            progress: Callable[[str], None] | None = None) -> list[InstrumentResult]:
    jobs = [(s.key, s.bars, params, cfg) for s in series]
    if workers <= 1:
        results = []
        for j in jobs:
            results.append(_run_one(j))
            if progress:
                progress(j[0])
        return results
    with ProcessPoolExecutor(max_workers=workers) as pool:
        results = []
        for r in pool.map(_run_one, jobs):
            results.append(r)
            if progress:
                progress(r.symbol)
        return results


# ---------- Schreiben ----------

def _summary_metrics(s: PatternSummary) -> dict[str, Any]:
    d = asdict(s)
    for k in ("pattern_type", "sample_size", "hit_rate", "ci_low", "ci_high", "base_rate"):
        d.pop(k)
    return d


def build_runs(summaries: list[PatternSummary], data: DataReport, cfg: BacktestConfig, params: Params,
               source: AdapterMetadata, universe_label: str, now: datetime) -> list[BacktestRun]:
    if not data.series:
        raise ValueError("Keine Kursdaten geladen: es wird kein Backtest-Ergebnis gespeichert.")
    first = min(s.bars.ts[0] for s in data.series)
    last = max(s.bars.ts[-1] for s in data.series)
    fetched = sorted(s.fetched_at for s in data.series)
    date_range = f"{fmt.day(first)} bis {fmt.day(last)}"
    fetched_text = fmt.day(fetched[0]) if fmt.day(fetched[0]) == fmt.day(fetched[-1]) \
        else f"{fmt.day(fetched[0])} bis {fmt.day(fetched[-1])}"
    universe = (f"{universe_label}; ausgewertet {len(data.series)} Werte mit Daten, {len(data.missing)} ohne; "
                f"Tagesdaten von {source.name} ({source.homepage}), abgerufen {fetched_text}")
    run_params: dict[str, Any] = {**cfg.as_params(), "engine_params_hash": params_hash(params),
                                  "backtest_version": BACKTEST_VERSION}
    common: dict[str, Any] = {
        "survivorship_note": SURVIVORSHIP_NOTE,
        "method": METHOD_TEXT.format(h=cfg.horizon_bars, x=fmt.pct(cfg.min_move_pct, 1)),
        "source": {"key": source.key, "name": source.name, "homepage": source.homepage,
                   "terms_url": source.terms_url, "delay_text": source.delay_text,
                   "fetched_from": fetched[0].isoformat(), "fetched_to": fetched[-1].isoformat()},
        "symbols_used": [s.key for s in data.series],
        "symbols_missing": data.missing,
        "bars_total": sum(len(s.bars) for s in data.series),
    }
    return [BacktestRun(kind="pattern", subject=s.pattern_type, timeframe=TIMEFRAME, algo_version=ALGO_VERSION,
                        params=run_params, universe=universe, date_range=date_range, sample_size=s.sample_size,
                        hit_rate=s.hit_rate, ci_low=s.ci_low, ci_high=s.ci_high, base_rate=s.base_rate,
                        metrics={**common, **_summary_metrics(s)}, code_version=BACKTEST_VERSION, created_at=now)
            for s in summaries]


def run_pattern_backtest(db: Session | None, adapter: PriceAdapter, universe: list[tuple[str, str]],
                         universe_label: str, start: datetime, cfg: BacktestConfig, workers: int,
                         cache_dir: Path | None, max_cache_age: timedelta = timedelta(days=7),
                         now: datetime | None = None) -> tuple[list[PatternSummary], DataReport]:
    """Lädt, rechnet und speichert (ohne `db` nur Ausgabe, nichts gespeichert)."""
    now = now or datetime.now(UTC)
    params = default_params()
    data = load_universe(adapter, universe, start, now, cache_dir, max_cache_age, cfg.warmup_bars + cfg.horizon_bars)
    if not data.series:
        raise ValueError("Für keinen Wert liegen Kursdaten vor (API-Schlüssel und Verbindung prüfen). "
                         "Es wird kein Ergebnis gespeichert.")
    done = [0]

    def progress(key: str) -> None:
        done[0] += 1
        log.info("Backtest %d/%d: %s", done[0], len(data.series), key)

    results = compute(data.series, cfg, params, workers, progress)
    summaries = [summarize(pt, results) for pt in PATTERN_NAMES]
    if db is not None:
        db.add_all(build_runs(summaries, data, cfg, params, adapter.metadata(), universe_label, now))
        db.commit()
    return summaries, data
