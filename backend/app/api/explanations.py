"""KI-Erklärtexte zu Erkennungen und Prognosen. Vertrag: docs/api-contract.md (Abschnitt "Erklärtexte").
Der Text entsteht ausschließlich aus den bereits berechneten Werten dieser Endpunkte (siehe explain_facts)."""
from typing import Any

from fastapi import APIRouter, HTTPException

from app.analysis.forecast import HORIZON
from app.api.forecasts import get_forecast
from app.api.patterns import detection_out
from app.deps import DB, CurrentUser
from app.explain_facts import forecast_facts_text, forecast_template, pattern_facts_text, pattern_template
from app.explain_service import get_explanation
from app.models import Instrument, PatternDetection

router = APIRouter(prefix="/api", tags=["explanations"])

NO_FORECAST = "Für diese Prognose liegt kein Korridor vor, deshalb gibt es keinen Erklärtext."


@router.get("/patterns/{detection_id}/explanation")
def pattern_explanation(detection_id: int, db: DB, user: CurrentUser) -> dict[str, Any]:
    d = db.get(PatternDetection, detection_id)
    if d is None:
        raise HTTPException(404, "Erkennung nicht gefunden")
    facts = detection_out(db, d)
    return get_explanation(db, "pattern", d.id, pattern_facts_text(facts), pattern_template(facts),
                           allow_ai=not d.is_demo)


@router.get("/instruments/{instrument_id}/forecast/explanation")
def forecast_explanation(instrument_id: int, db: DB, user: CurrentUser) -> dict[str, Any]:
    inst = db.get(Instrument, instrument_id)
    if inst is None:
        raise HTTPException(404, "Instrument nicht gefunden")
    f = get_forecast(instrument_id, db, user, timeframe="1d", horizon=HORIZON)
    if f["empty_reason"] or not f["steps"]:
        raise HTTPException(404, f["empty_reason"] or NO_FORECAST)
    return get_explanation(db, "forecast", instrument_id, forecast_facts_text(f, inst.symbol),
                           forecast_template(f, inst.symbol),
                           allow_ai=not f["is_demo"])
