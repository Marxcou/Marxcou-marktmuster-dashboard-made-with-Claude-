"""Aufbewahrung: Nachrichten-Cluster, deren letzte Meldung älter als NEWS_RETENTION_DAYS ist, werden samt Meldungen,
Instrumentzuordnung und Stimmung gelöscht. Ganze Cluster, damit nie ein Cluster ohne Leitmeldung übrig bleibt.
Der Mindestwert liegt über dem Abruffenster der Quellen (7 Tage), sonst würden gelöschte Meldungen neu geladen."""
import logging
from datetime import timedelta
from typing import Any, cast

from sqlalchemy import CursorResult, delete, select
from sqlalchemy.orm import Session

from app import events as event_bus
from app.api_usage import prune_usage
from app.config import get_settings
from app.db import SessionLocal
from app.models import (
    NewsCluster,
    NewsInstrument,
    NewsItem,
    Sentiment,
    SentimentBatch,
    SentimentBatchItem,
    utcnow,
)

log = logging.getLogger("retention")
MIN_DAYS = 14
CHUNK = 500


def retention_days() -> int:
    days = get_settings().news_retention_days
    return 0 if days <= 0 else max(days, MIN_DAYS)


def prune_news(db: Session) -> dict[str, int]:
    days = retention_days()
    stats = {"clusters": 0, "items": 0}
    if days == 0:
        return stats
    cutoff = utcnow() - timedelta(days=days)
    while ids := db.scalars(select(NewsCluster.id).where(NewsCluster.last_published_at < cutoff)
                            .order_by(NewsCluster.id).limit(CHUNK)).all():
        res = cast(CursorResult[Any], db.execute(delete(NewsItem).where(NewsItem.cluster_id.in_(ids))))
        stats["items"] += res.rowcount or 0
        db.execute(delete(NewsInstrument).where(NewsInstrument.cluster_id.in_(ids)))
        db.execute(delete(Sentiment).where(Sentiment.cluster_id.in_(ids)))
        db.execute(delete(SentimentBatchItem).where(SentimentBatchItem.cluster_id.in_(ids)))
        db.execute(delete(NewsCluster).where(NewsCluster.id.in_(ids)))
        db.commit()
        stats["clusters"] += len(ids)
    # Batch-Zeilen ohne Einträge (alle Cluster gelöscht, Ergebnisse verarbeitet) räumen
    empty = select(SentimentBatch.id).where(SentimentBatch.status == "ended").outerjoin(
        SentimentBatchItem, SentimentBatchItem.batch_id == SentimentBatch.id).where(
        SentimentBatchItem.batch_id.is_(None))
    db.execute(delete(SentimentBatch).where(SentimentBatch.id.in_(empty)))
    db.commit()
    return stats


def retention_job() -> None:
    with SessionLocal() as db:
        stats = prune_news(db)
        prune_usage(db)
        event_bus.prune(db)
    if stats["clusters"]:
        log.info("Aufbewahrung: %d Cluster mit %d Meldungen gelöscht", stats["clusters"], stats["items"])
