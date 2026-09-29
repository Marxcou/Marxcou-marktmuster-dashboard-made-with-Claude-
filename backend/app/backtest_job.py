"""Muster-Backtest als einmaliger Job (nicht im Worker-Zeitplan, weil er je nach Rechner 20 bis 90 Minuten läuft).

Docker:   docker compose run --rm worker python -m app.backtest_job
Lokal:    cd backend && python -m app.backtest_job

Braucht STOOQ_API_KEY in .env. Ohne Kursdaten wird nichts gespeichert (Grundregel 6)."""
import argparse
import logging
import os
import sys
from datetime import UTC, datetime, timedelta
from pathlib import Path

from app.adapters.stooq import StooqAdapter
from app.analysis import fmt
from app.analysis.backtest import BacktestConfig, PatternSummary, share
from app.analysis.catalog import PATTERN_NAMES
from app.backtest_service import run_pattern_backtest
from app.backtest_universe import UNIVERSE_LABEL, default_universe, read_universe_file
from app.db import SessionLocal

log = logging.getLogger("backtest")


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    d = BacktestConfig()
    p = argparse.ArgumentParser(prog="python -m app.backtest_job", description="Muster-Backtest mit Tagesdaten")
    p.add_argument("--start", default="2010-01-01", help="erster Tag der Kursdaten (JJJJ-MM-TT)")
    p.add_argument("--horizon", type=int, default=d.horizon_bars, help="Kerzen nach dem Ausgangspunkt")
    p.add_argument("--min-move", type=float, default=d.min_move_pct, help="Mindestbewegung in %% für einen Treffer")
    p.add_argument("--step", type=int, default=d.step_bars, help="Abstand der Erkennungsläufe in Kerzen")
    p.add_argument("--window", type=int, default=d.window_bars, help="Kerzen je Erkennungslauf")
    p.add_argument("--workers", type=int, default=max(1, (os.cpu_count() or 2) - 1), help="parallele Prozesse")
    p.add_argument("--symbols", help="nur diese Werte, z. B. SAP.XETR,AAPL.XNAS (zum Ausprobieren)")
    p.add_argument("--universe-file", type=Path, help="eigene Liste, je Zeile SYMBOL,BÖRSE")
    p.add_argument("--cache-dir", type=Path, default=Path(os.environ.get("BACKTEST_CACHE_DIR", "backtest-cache")),
                   help="Zwischenspeicher der geladenen Tagesdaten")
    p.add_argument("--max-cache-age-days", type=int, default=7)
    p.add_argument("--dry-run", action="store_true", help="nur ausgeben, nichts in der Datenbank speichern")
    return p.parse_args(argv)


def _line(s: PatternSummary) -> str:
    name = PATTERN_NAMES[s.pattern_type]
    if s.hit_rate is None or s.ci_low is None or s.ci_high is None:
        return f"{name}: keine auswertbaren Fälle"
    base = share(s.base_rate) if s.base_rate is not None else "nicht verfügbar"
    return (f"{name}: {share(s.hit_rate)} von {s.sample_size} Fällen (95 %: {share(s.ci_low)} bis "
            f"{share(s.ci_high)}), Basisrate {base}")


def main(argv: list[str] | None = None) -> int:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(message)s")
    a = parse_args(argv)
    cfg = BacktestConfig(horizon_bars=a.horizon, min_move_pct=a.min_move, window_bars=a.window, step_bars=a.step)
    adapter = StooqAdapter()
    if not adapter.is_configured():
        print("STOOQ_API_KEY fehlt in .env. Ohne echte Kursdaten wird kein Backtest gerechnet.", file=sys.stderr)
        return 2
    universe = read_universe_file(a.universe_file) if a.universe_file else default_universe()
    label = f"eigene Liste ({len(universe)} Werte)" if a.universe_file else UNIVERSE_LABEL
    if a.symbols:
        wanted = {s.strip().upper() for s in a.symbols.split(",") if s.strip()}
        universe = [u for u in universe if f"{u[0]}.{u[1]}" in wanted]
        label = f"Auswahl ({len(universe)} Werte: {', '.join(sorted(wanted))})"
    start = datetime.fromisoformat(a.start).replace(tzinfo=UTC)
    log.info("Muster-Backtest: %d Werte ab %s, %d Prozesse", len(universe), fmt.day(start), a.workers)
    try:
        if a.dry_run:
            summaries, data = run_pattern_backtest(None, adapter, universe, label, start, cfg, a.workers,
                                                   a.cache_dir, timedelta(days=a.max_cache_age_days))
        else:
            with SessionLocal() as db:
                summaries, data = run_pattern_backtest(db, adapter, universe, label, start, cfg, a.workers,
                                                       a.cache_dir, timedelta(days=a.max_cache_age_days))
    except ValueError as exc:
        print(str(exc), file=sys.stderr)
        return 1
    print(f"\nAusgewertet: {len(data.series)} Werte, ohne Daten: {len(data.missing)}")
    for key, reason in sorted(data.missing.items()):
        print(f"  fehlt {key}: {reason}")
    for s in summaries:
        print(_line(s))
    print("\nNichts gespeichert (--dry-run)." if a.dry_run else "\nErgebnisse gespeichert (Tabelle backtest_runs).")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
