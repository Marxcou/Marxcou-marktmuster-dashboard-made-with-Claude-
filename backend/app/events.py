"""Worker -> API: der Worker schreibt Events in die Tabelle 'events', der API-Prozess liest sie und
leitet sie per WebSocket weiter. Redis kann das später ersetzen (gleiche publish()/poll()-Schnittstelle)."""
from datetime import timedelta
from typing import Any, cast

from sqlalchemy import CursorResult, delete, select
from sqlalchemy.orm import Session

from app.models import Event, utcnow


def publish(db: Session, type_: str, payload: dict[str, Any]) -> None:
    db.add(Event(type=type_, payload=payload))
    db.commit()


def poll(db: Session, after_id: int, limit: int = 200) -> list[Event]:
    return list(db.scalars(select(Event).where(Event.id > after_id).order_by(Event.id).limit(limit)))


EVENT_KEEP = timedelta(hours=24)


def prune(db: Session) -> int:
    """Die Tabelle ist nur eine Warteschlange für offene WebSocket-Verbindungen (sie lesen ab ihrer Verbindung).
    Ohne Aufräumen wächst sie um jede Kursaktualisierung jedes Instruments."""
    res = db.execute(delete(Event).where(Event.created_at < utcnow() - EVENT_KEEP))
    db.commit()
    return cast("CursorResult[Any]", res).rowcount or 0
