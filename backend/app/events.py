"""Worker -> API: der Worker schreibt Events in die Tabelle 'events', der API-Prozess liest sie und
leitet sie per WebSocket weiter. Redis kann das später ersetzen (gleiche publish()/poll()-Schnittstelle)."""
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import Event


def publish(db: Session, type_: str, payload: dict[str, Any]) -> None:
    db.add(Event(type=type_, payload=payload))
    db.commit()


def poll(db: Session, after_id: int, limit: int = 200) -> list[Event]:
    return list(db.scalars(select(Event).where(Event.id > after_id).order_by(Event.id).limit(limit)))
