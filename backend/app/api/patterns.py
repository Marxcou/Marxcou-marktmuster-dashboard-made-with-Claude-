"""Mustererkennung: Erkennungen, Zonen, Katalog, Zähler. Der Vertrag steht in docs/api-contract.md (Phase 3B).

Die historische Trefferquote kommt ausschließlich aus backtest_runs (Workstream 3C). Gibt es keinen Lauf,
steht status "nicht_berechnet" und alle Zahlen sind null; es wird nie ein Wert geschätzt (Grundregel 6)."""
from datetime import datetime
from typing import Any

from fastapi import APIRouter, HTTPException
from sqlalchemy import or_, select

from app.analysis.catalog import catalog
from app.analysis.params import ALGO_VERSION, default_params, params_hash
from app.analysis.patterns.common import CONFIDENCE_METHOD, STATUS_LABELS
from app.analysis.zones import KIND_LABELS
from app.api.instruments import InstrumentOut, _ref
from app.bars import aware
from app.deps import DB, CurrentUser
from app.models import (
    BacktestRun,
    Instrument,
    PatternDetection,
    PatternScan,
    Source,
    SupportResistanceZone,
    WatchlistItem,
)
from app.onboarding import is_pending
from app.price_service import NO_INTRADAY_REASON, has_intraday

router = APIRouter(prefix="/api", tags=["patterns"])

TIMEFRAMES = ("1d", "1h")
NOT_COMPUTED_NOTE = "Die historische Trefferquote für dieses Muster wurde noch nicht berechnet."
PENDING_REASON = "Die Mustererkennung wird gerade berechnet. Die Ansicht aktualisiert sich automatisch."
NOT_RUN_REASON = "Die Mustererkennung wurde für dieses Instrument noch nicht ausgeführt."
NO_MATCH_REASON = "Aktuell erfüllt kein Muster alle Kriterien."


def _iso(dt: datetime | None) -> str | None:
    return aware(dt).isoformat() if dt is not None else None


def _sources(db: DB, ids: list[int]) -> list[dict[str, Any]]:
    if not ids:
        return []
    return [_ref(s).model_dump() for s in db.scalars(select(Source).where(Source.id.in_(ids)).order_by(Source.key))]


def _data_basis(db: DB, scan: PatternScan) -> dict[str, Any] | None:
    if scan.bars_from is None:
        return None
    return {"bars_from": _iso(scan.bars_from), "bars_to": _iso(scan.bars_to), "bar_count": scan.bar_count,
            "last_fetched_at": _iso(scan.last_fetched_at), "sources": _sources(db, scan.source_ids)}


def _latest_run(db: DB, pattern_type: str, timeframe: str, algo_version: str) -> BacktestRun | None:
    return db.scalar(select(BacktestRun).where(
        BacktestRun.kind == "pattern", BacktestRun.subject == pattern_type, BacktestRun.timeframe == timeframe,
        BacktestRun.algo_version == algo_version).order_by(BacktestRun.created_at.desc(), BacktestRun.id.desc())
        .limit(1))


def backtest_block(run: BacktestRun | None) -> dict[str, Any]:
    if run is None:
        return {"status": "nicht_berechnet", "run_id": None, "hit_rate": None, "sample_size": None, "ci_low": None,
                "ci_high": None, "base_rate": None, "not_better_than_random": None, "horizon_bars": None,
                "min_move_pct": None, "universe": None, "date_range": None, "computed_at": None,
                "survivorship_note": None, "verdict_text": None, "note": NOT_COMPUTED_NOTE,
                "mean_return_pct": None, "median_return_pct": None, "base_mean_return_pct": None, "method": None,
                "source": None}
    # Nicht besser als Zufall: die untere Grenze des 95-%-Intervalls liegt nicht über der Basisrate
    # (Intervall überdeckt die Basisrate oder liegt ganz darunter).
    not_better: bool | None = None
    if run.ci_low is not None and run.ci_high is not None and run.base_rate is not None:
        not_better = run.ci_low <= run.base_rate
    m = run.metrics or {}
    return {"status": "berechnet", "run_id": run.id, "hit_rate": run.hit_rate, "sample_size": run.sample_size,
            "ci_low": run.ci_low, "ci_high": run.ci_high, "base_rate": run.base_rate,
            "not_better_than_random": not_better, "horizon_bars": run.params.get("horizon_bars"),
            "min_move_pct": run.params.get("min_move_pct"), "universe": run.universe or None,
            "date_range": run.date_range or None, "computed_at": _iso(run.created_at),
            "survivorship_note": m.get("survivorship_note"), "verdict_text": m.get("verdict_text"),
            "note": m.get("note"), "mean_return_pct": m.get("mean_return_pct"),
            "median_return_pct": m.get("median_return_pct"), "base_mean_return_pct": m.get("base_mean_return_pct"),
            "method": m.get("method"), "source": m.get("source")}


def detection_out(db: DB, d: PatternDetection, runs: dict[str, BacktestRun | None] | None = None) -> dict[str, Any]:
    runs = runs if runs is not None else {}
    if d.pattern_type not in runs:
        runs[d.pattern_type] = _latest_run(db, d.pattern_type, d.timeframe, d.algo_version)
    run = runs[d.pattern_type]
    hist = (run.metrics or {}).get("scenarios", {}) if run else {}
    scenarios = [{**s, "historical": hist.get(s["kind"])} for s in d.scenarios]
    scan = db.get(PatternScan, (d.instrument_id, d.timeframe))
    return {
        "id": d.id, "instrument_id": d.instrument_id, "timeframe": d.timeframe, "pattern_type": d.pattern_type,
        "name": d.name, "direction_if_confirmed": d.direction, "status": d.status,
        "status_label": STATUS_LABELS[d.status], "status_reason": d.status_reason,
        "status_changed_at": _iso(d.status_changed_at or d.formed_ts), "confirmed_at": _iso(d.confirmed_at),
        "invalidated_at": _iso(d.invalidated_at), "breakout_direction": d.breakout_direction,
        "start_ts": _iso(d.start_ts), "end_ts": _iso(d.end_ts), "formed_at": _iso(d.formed_ts),
        "key_points": d.key_points, "lines": d.lines, "criteria": d.criteria,
        "confidence": {"score": d.confidence, "method": CONFIDENCE_METHOD, "breakdown": d.confidence_breakdown},
        "confirmation_level": d.confirmation_level, "invalidation_level": d.invalidation_level,
        "scenarios": scenarios, "backtest": backtest_block(run), "explanation": d.explanation,
        "data_basis": {**((_data_basis(db, scan) if scan else None) or {}), "sources": _sources(db, d.source_ids),
                       "last_fetched_at": _iso(d.fetched_at)},
        "params": d.params, "algo_version": d.algo_version, "params_hash": d.params_hash,
        "detected_at": _iso(d.detected_at), "is_demo": d.is_demo,
    }


def zone_out(db: DB, z: SupportResistanceZone) -> dict[str, Any]:
    return {"id": z.id, "kind": z.kind, "kind_label": KIND_LABELS[z.kind], "lower": z.lower, "upper": z.upper,
            "center": round((z.lower + z.upper) / 2, 4), "touch_count": len(z.touches), "touches": z.touches,
            "first_touch": _iso(z.first_touch), "last_touch": _iso(z.last_touch), "criteria": z.criteria,
            "confidence": {"score": z.confidence, "method": CONFIDENCE_METHOD, "breakdown": z.confidence_breakdown},
            "explanation": z.explanation, "sources": _sources(db, z.source_ids), "fetched_at": _iso(z.fetched_at),
            "is_demo": z.is_demo}


@router.get("/patterns/catalog")
def get_catalog(_u: CurrentUser) -> dict[str, Any]:
    params = default_params()
    return {"algo_version": ALGO_VERSION, "params_hash": params_hash(params), "confidence_method": CONFIDENCE_METHOD,
            "items": catalog(params)}


@router.get("/patterns/counts")
def get_counts(db: DB, user: CurrentUser) -> dict[str, Any]:
    ids = list(db.scalars(select(WatchlistItem.instrument_id).where(WatchlistItem.user_id == user.id)))
    if not ids:
        return {"counts": {}, "empty_reason": "Die Watchlist ist leer."}
    counts: dict[str, int] = {}
    scans = db.scalars(select(PatternScan).where(PatternScan.instrument_id.in_(ids), PatternScan.timeframe == "1d"))
    for scan in scans:
        stmt = select(PatternDetection).where(PatternDetection.instrument_id == scan.instrument_id,
                                              PatternDetection.timeframe == "1d")
        if scan.recent_from is not None:
            stmt = stmt.where(or_(PatternDetection.status == "in_bildung",
                                  (PatternDetection.status == "bestaetigt")
                                  & (PatternDetection.confirmed_at >= scan.recent_from)))
        else:
            stmt = stmt.where(PatternDetection.status == "in_bildung")
        counts[str(scan.instrument_id)] = len(list(db.scalars(stmt)))
    reason = None if counts else NOT_RUN_REASON
    return {"counts": counts, "empty_reason": reason}


@router.get("/patterns/{detection_id}")
def get_detection(detection_id: int, db: DB, _u: CurrentUser) -> dict[str, Any]:
    d = db.get(PatternDetection, detection_id)
    if d is None:
        raise HTTPException(404, "Erkennung nicht gefunden")
    return detection_out(db, d)


@router.get("/instruments/{instrument_id}/patterns")
def get_patterns(instrument_id: int, db: DB, _u: CurrentUser, timeframe: str = "1d", include_invalid: bool = False,
                 start: datetime | None = None) -> dict[str, Any]:
    if timeframe not in TIMEFRAMES:
        raise HTTPException(422, f"timeframe muss einer von {TIMEFRAMES} sein")
    inst = db.get(Instrument, instrument_id)
    if inst is None:
        raise HTTPException(404, "Instrument nicht gefunden")
    base: dict[str, Any] = {
        "instrument": InstrumentOut.model_validate(inst, from_attributes=True).model_dump(),
        "timeframe": timeframe, "detections": [], "zones": [], "data_basis": None, "algo_version": ALGO_VERSION,
        "params_hash": params_hash(default_params()), "computed_at": None, "empty_reason": None, "pending": False,
    }
    if timeframe != "1d" and not has_intraday(inst.exchange):
        return {**base, "empty_reason": NO_INTRADAY_REASON}
    scan = db.get(PatternScan, (instrument_id, timeframe))
    if scan is None:
        if is_pending(db, instrument_id):
            return {**base, "empty_reason": PENDING_REASON, "pending": True}
        return {**base, "empty_reason": NOT_RUN_REASON}
    stmt = select(PatternDetection).where(PatternDetection.instrument_id == instrument_id,
                                          PatternDetection.timeframe == timeframe)
    if not include_invalid:
        stmt = stmt.where(PatternDetection.status != "ungueltig")
    if start is not None:
        stmt = stmt.where(PatternDetection.end_ts >= start)
    runs: dict[str, BacktestRun | None] = {}
    detections = [detection_out(db, d, runs) for d in db.scalars(stmt.order_by(PatternDetection.start_ts))]
    zones = [zone_out(db, z) for z in db.scalars(select(SupportResistanceZone).where(
        SupportResistanceZone.instrument_id == instrument_id, SupportResistanceZone.timeframe == timeframe)
        .order_by(SupportResistanceZone.lower))]
    reason = scan.empty_reason or (NO_MATCH_REASON if not detections else None)
    return {**base, "detections": detections, "zones": zones, "data_basis": _data_basis(db, scan),
            "algo_version": scan.algo_version, "params_hash": scan.params_hash, "computed_at": _iso(scan.computed_at),
            "empty_reason": reason}
