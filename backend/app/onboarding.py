"""Sofortige Erstberechnung für ein neu auf eine Watchlist gesetztes Instrument.

Die periodischen Jobs (Muster/Analyse alle 5 Minuten, Prognose alle 15 Minuten) würden ein neues Instrument erst
verzögert erfassen. Dieser Lauf ruft dieselben Dienste einmalig auf: Kursabruf, Mustererkennung, Indikator-Ereignisse,
Prognose. Jeder Schritt ist einzeln abgesichert; schlägt einer fehl, bleibt es bei dem Leerzustand mit Grund und die
periodischen Jobs holen es nach."""
import logging
from collections.abc import Callable
from datetime import UTC, datetime, timedelta
from functools import partial

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.analysis_service import TIMEFRAMES as ANALYSIS_TIMEFRAMES
from app.analysis_service import analyze_instrument
from app.db import SessionLocal
from app.forecast_service import forecast_instrument
from app.models import Instrument, WatchlistItem
from app.pattern_service import TIMEFRAMES as PATTERN_TIMEFRAMES
from app.pattern_service import scan_instrument
from app.price_service import backfill_new_instrument, has_intraday

log = logging.getLogger("onboarding")

# So lange nach dem Hinzufügen gilt ein noch fehlendes Ergebnis als "wird berechnet". Danach zeigt die Oberfläche
# wieder den nüchternen Leerzustand mit Grund, damit ein fehlgeschlagener Lauf nicht ewig als Wartezustand erscheint.
PENDING_WINDOW = timedelta(minutes=15)


def is_pending(db: Session, instrument_id: int, now: datetime | None = None) -> bool:
    """True, wenn das Instrument innerhalb des Zeitfensters auf einer Watchlist landete (Berechnung läuft/steht an)."""
    now = now or datetime.now(UTC)
    added = db.scalar(select(func.max(WatchlistItem.added_at)).where(WatchlistItem.instrument_id == instrument_id))
    if added is None:
        return False
    if added.tzinfo is None:
        added = added.replace(tzinfo=UTC)
    return now - added < PENDING_WINDOW


def _step(db: Session, label: str, fn: Callable[[], object]) -> None:
    try:
        fn()
    except Exception:  # noqa: BLE001 - ein Schritt darf die folgenden nicht verhindern
        db.rollback()
        log.exception("Erstberechnung %s fehlgeschlagen", label)


def process_new_instrument(instrument_id: int) -> None:
    """Hintergrundaufgabe nach dem Hinzufügen zur Watchlist."""
    with SessionLocal() as db:
        inst = db.get(Instrument, instrument_id)
        if inst is None:
            return
        _step(db, f"{inst.symbol} Kursabruf", lambda: backfill_new_instrument(instrument_id))
        for tf in PATTERN_TIMEFRAMES:
            if tf != "1d" and not has_intraday(inst.exchange):
                continue  # ohne Intraday-Kerzen gibt es nichts zu erkennen; die API nennt den Grund
            _step(db, f"{inst.symbol} Muster {tf}", partial(scan_instrument, db, inst, tf))
        for tf in ANALYSIS_TIMEFRAMES:
            if tf != "1d" and not has_intraday(inst.exchange):
                continue
            _step(db, f"{inst.symbol} Analyse {tf}", partial(analyze_instrument, db, inst, tf))
        _step(db, f"{inst.symbol} Prognose", lambda: forecast_instrument(db, inst))
