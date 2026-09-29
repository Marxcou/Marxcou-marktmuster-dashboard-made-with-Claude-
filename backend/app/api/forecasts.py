"""Prognosen als Quantil-Korridor, Prognose-Backtest und Verknüpfung mit Muster-Szenarien. Vertrag: docs/api-contract.md
(Phase 4A). Es gibt keinen Endpunkt für eine einzelne Linie (Grundregel 4); Fehlermaße stammen nur aus
backtest_runs (kind='forecast'), sonst status "nicht_berechnet" mit null-Werten (Grundregel 6)."""
from datetime import datetime
from typing import Any

from fastapi import APIRouter, HTTPException, Query
from sqlalchemy import select

from app.analysis import fmt
from app.analysis import forecast as fc
from app.api.patterns import _latest_run, _sources
from app.bars import aware
from app.deps import DB, CurrentUser
from app.forecast_service import METHOD_NOTE, NOT_RUN_REASON, TIMEFRAME, params_hash
from app.models import BacktestRun, Forecast, Instrument, PatternDetection

router = APIRouter(prefix="/api", tags=["forecasts"])

NOTE = "Statistische Szenarien aus historischen Schwankungen, keine Vorhersage und keine Anlageberatung."
ONLY_DAILY_REASON = "Prognosen gibt es derzeit nur für Tageskerzen."
BACKTEST_NOT_COMPUTED = "Die Prognosegüte wurde für dieses Instrument noch nicht berechnet."
SCENARIO_NOTE = (
    "Die Simulation kennt das Muster nicht; sie zeigt nur, wie oft die Niveaus bei historischer Schwankung zuerst "
    "erreicht würden. Die historische Quote stammt aus dem Muster-Backtest."
)
LEVELS_STALE = "Noch nicht berechnet: das Muster wurde nach der letzten Prognose aktualisiert."


def _iso(dt: datetime | None) -> str | None:
    return aware(dt).isoformat() if dt is not None else None


def backtest_out(run: BacktestRun | None, reason: str | None = None) -> dict[str, Any]:
    if run is None:
        return {"status": "nicht_berechnet", "run_id": None, "sample_size": None, "horizon_bars": None,
                "date_range": None, "universe": None, "computed_at": None, "is_demo": None, "coverage": [],
                "metrics": [], "skill": None, "dm_p_value": None, "better_than_naive": None, "verdict_text": None,
                "by_horizon": [], "method_note": None, "note": reason or BACKTEST_NOT_COMPUTED}
    m = run.metrics or {}
    horizon = m.get("primary_horizon", fc.HORIZON)
    by_h: list[dict[str, Any]] = m.get("by_horizon", [])
    main = next((h for h in by_h if h["horizon_bars"] == horizon), None) or {}
    return {"status": "berechnet", "run_id": run.id, "sample_size": main.get("sample_size", run.sample_size),
            "horizon_bars": horizon, "date_range": run.date_range or None, "universe": run.universe or None,
            "computed_at": _iso(run.created_at), "is_demo": m.get("is_demo", False),
            "coverage": main.get("coverage", []), "metrics": main.get("metrics", []), "skill": main.get("skill"),
            "dm_p_value": main.get("dm_p_value"), "better_than_naive": main.get("better_than_naive"),
            "verdict_text": m.get("verdict_text"), "by_horizon": by_h, "method_note": m.get("method_note"),
            "note": None}


def _probability_text(p: float, level: float, above: bool, horizon: int) -> str:
    side = "über" if above else "unter"
    return (f"In {fmt.pct(p * 100, 0)} der simulierten Pfade schließt der Kurs innerhalb von {horizon} "
            f"Handelstagen zuerst {side} {fmt.price(level)}.")


def pattern_scenarios(db: DB, row: Forecast) -> list[dict[str, Any]]:
    stored = {e["detection_id"]: e for e in row.pattern_levels or []}
    out: list[dict[str, Any]] = []
    runs: dict[str, BacktestRun | None] = {}
    dets = db.scalars(select(PatternDetection).where(
        PatternDetection.instrument_id == row.instrument_id, PatternDetection.timeframe == TIMEFRAME,
        PatternDetection.status == "in_bildung").order_by(PatternDetection.start_ts))
    for d in dets:
        if d.pattern_type not in runs:
            runs[d.pattern_type] = _latest_run(db, d.pattern_type, d.timeframe, d.algo_version)
        run = runs[d.pattern_type]
        hist = (run.metrics or {}).get("scenarios", {}) if run else {}
        levels = [s["trigger_level"] for s in d.scenarios if s.get("trigger_level") is not None]
        entry = stored.get(d.id)
        fresh = (entry is not None and levels and abs(entry["upper"] - max(levels)) < 1e-9
                 and abs(entry["lower"] - min(levels)) < 1e-9)
        scenarios = []
        for s in d.scenarios:
            level = s.get("trigger_level")
            prob: float | None = None
            text = LEVELS_STALE
            if fresh and entry is not None and level is not None:
                above = abs(level - entry["upper"]) < 1e-9
                prob = entry["p_upper"] if above else entry["p_lower"]
                text = _probability_text(prob, level, above, entry["horizon_bars"])
            scenarios.append({"kind": s["kind"], "title": s["title"], "trigger_level": level,
                              "model_probability": prob, "model_probability_text": text,
                              "historical": hist.get(s["kind"])})
        out.append({"detection_id": d.id, "pattern_type": d.pattern_type, "name": d.name, "status": d.status,
                    "scenarios": scenarios,
                    "neither_probability": entry["p_neither"] if fresh and entry is not None else None,
                    "horizon_bars": entry["horizon_bars"] if fresh and entry is not None else None,
                    "note": SCENARIO_NOTE})
    return out


def _run(db: DB, row: Forecast | None) -> BacktestRun | None:
    return db.get(BacktestRun, row.backtest_run_id) if row is not None and row.backtest_run_id else None


def _steps(row: Forecast | None, horizon: int) -> list[dict[str, Any]]:
    return [] if row is None or row.empty_reason else list(row.steps[:horizon])


@router.get("/forecasts/methods")
def get_methods(_u: CurrentUser) -> dict[str, Any]:
    return {"algo_version": fc.ALGO_VERSION, "quantiles": list(fc.QKEYS), "bands": fc.BANDS,
            "backtest_params": fc.BACKTEST_PARAMS, "backtest_method_note": METHOD_NOTE,
            "items": [{**fc.method_info(k), "params_hash": params_hash(k), "is_primary": k == fc.PRIMARY}
                      for k in (fc.PRIMARY, fc.COMPARISON)]}


@router.get("/instruments/{instrument_id}/forecast")
def get_forecast(instrument_id: int, db: DB, _u: CurrentUser, timeframe: str = "1d",
                 horizon: int = Query(fc.HORIZON, ge=1, le=fc.HORIZON)) -> dict[str, Any]:
    inst = db.get(Instrument, instrument_id)
    if inst is None:
        raise HTTPException(404, "Instrument nicht gefunden")
    rows = {r.method: r for r in db.scalars(select(Forecast).where(
        Forecast.instrument_id == instrument_id, Forecast.timeframe == TIMEFRAME))}
    main = rows.get(fc.PRIMARY) if timeframe == TIMEFRAME else None
    comp = rows.get(fc.COMPARISON) if timeframe == TIMEFRAME else None
    if timeframe != TIMEFRAME:
        reason: str | None = ONLY_DAILY_REASON
    elif main is None:
        reason = NOT_RUN_REASON
    else:
        reason = main.empty_reason
    has_data = main is not None and reason is None
    method = fc.method_info(fc.PRIMARY, _clean(main.params) if has_data and main else None)
    data_basis = None
    if has_data and main is not None:
        data_basis = {"bars_from": _iso(main.bars_from), "bars_to": _iso(main.based_on_until),
                      "bar_count": main.bar_count, "last_fetched_at": _iso(main.fetched_at),
                      "sources": _sources(db, main.source_ids)}
    comparison = []
    if has_data and comp is not None and not comp.empty_reason:
        comp_bt = backtest_out(_run(db, comp), comp.backtest_reason)
        comparison.append({"method_key": fc.COMPARISON, "name": fc.METHODS[fc.COMPARISON]["name"],
                           "description": fc.method_info(fc.COMPARISON, _clean(comp.params))["description"],
                           "method": fc.method_info(fc.COMPARISON, _clean(comp.params)),
                           "steps": _steps(comp, horizon), "backtest": comp_bt, "metrics": comp_bt["metrics"]})
    return {
        "instrument_id": instrument_id, "timeframe": timeframe, "method": method,
        "horizon_bars": min(horizon, main.horizon) if has_data and main else 0,
        "based_on_until": _iso(main.based_on_until) if has_data and main else None,
        "last_close": main.last_close if has_data and main else None, "currency": inst.currency,
        "generated_at": _iso(main.created_at) if main else None, "algo_version": fc.ALGO_VERSION,
        "params_hash": params_hash(fc.PRIMARY), "is_demo": bool(main.is_demo) if has_data and main else False,
        "steps": _steps(main, horizon) if has_data else [], "bands": fc.BANDS,
        "backtest": backtest_out(_run(db, main), main.backtest_reason if main else None) if has_data
        else backtest_out(None),
        "comparison": comparison,
        "pattern_scenarios": pattern_scenarios(db, main) if has_data and main else [],
        "data_basis": data_basis, "note": NOTE, "empty_reason": reason,
    }


def _clean(params: dict[str, Any]) -> dict[str, Any]:
    return {k: v for k, v in params.items() if k != "backtest"}
