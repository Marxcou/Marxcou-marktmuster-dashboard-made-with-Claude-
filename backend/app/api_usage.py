"""Tageszähler für Quellen mit knappem Kontingent. Der Stand liegt in der Datenbank, damit ein Neustart des Workers
den Zähler nicht zurücksetzt; der Tag wechselt um 00:00 UTC."""
from datetime import UTC, date, datetime, timedelta
from typing import Any, cast

from sqlalchemy import CursorResult, delete
from sqlalchemy.orm import Session

from app.db import SessionLocal
from app.models import ApiUsage

KEEP_DAYS = 35


def today() -> date:
    return datetime.now(UTC).date()


def calls_today(source_key: str, db: Session | None = None) -> int:
    if db is None:
        with SessionLocal() as own:
            return calls_today(source_key, own)
    row = db.get(ApiUsage, (source_key, today()))
    return row.calls if row else 0


def count_call(source_key: str, db: Session | None = None) -> int:
    """Zählt einen Abruf (vor dem Aufruf, wie bisher: ein fehlgeschlagener Abruf verbraucht Kontingent)."""
    if db is None:
        with SessionLocal() as own:
            return count_call(source_key, own)
    row = db.get(ApiUsage, (source_key, today()))
    if row is None:
        row = ApiUsage(source_key=source_key, day=today(), calls=0)
        db.add(row)
    row.calls += 1
    db.commit()
    return row.calls


def prune_usage(db: Session) -> int:
    res = db.execute(delete(ApiUsage).where(ApiUsage.day < today() - timedelta(days=KEEP_DAYS)))
    db.commit()
    return cast(CursorResult[Any], res).rowcount or 0
