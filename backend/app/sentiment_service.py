"""Stimmung je Cluster berechnen: Claude, wenn verfügbar und im Budget, sonst Lexikon. Die Rückfallstufe ist immer
sichtbar (method und model_name der gespeicherten Stimmung, plus /api/news/sentiment-status)."""
import logging
from datetime import timedelta

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.adapters.http import SourceError
from app.adapters.registry import get_adapter
from app.config import get_settings
from app.models import NewsCluster, NewsItem, Sentiment, SentimentBatch, SentimentBatchItem, Source, utcnow
from app.sentiment_claude import (
    BATCH_FACTOR,
    ClaudeSentimentSource,
    current_month,
    record_usage,
    spent_usd,
    verify,
    worst_case_usd,
)
from app.sentiment_lexicon import SentimentResult, analyze

log = logging.getLogger("sentiment")
UPGRADE_WINDOW = timedelta(days=3)  # Lexikon-Einstufungen jüngerer Cluster werden mit Claude nachgeholt
BATCH_SIZE = 100
RETRYABLE = ("expired", "canceled")  # nur diese Batch-Ergebnisse werden erneut eingereicht


def _claude() -> ClaudeSentimentSource | None:
    a = get_adapter(ClaudeSentimentSource.key)
    return a if isinstance(a, ClaudeSentimentSource) and a.is_configured() else None


def fallback_reason(db: Session) -> str | None:
    claude = _claude()
    if claude is None:
        return "Kein API-Schlüssel gesetzt"
    if spent_usd(db) >= get_settings().claude_monthly_budget_usd or claude.budget_exhausted:
        return "Monatslimit erreicht"
    return None


def reserved_usd(db: Session) -> float:
    """Höchstbetrag offener Batches, der bis zum Eintreffen der Ergebnisse gegen das Monatslimit zählt."""
    return float(db.scalar(select(func.coalesce(func.sum(SentimentBatch.reserved_usd), 0.0))
                           .where(SentimentBatch.status == "in_progress")) or 0.0)


def status(db: Session) -> dict[str, object]:
    reason = fallback_reason(db)
    return {
        "active_method": "lexicon" if reason else "claude", "claude_configured": _claude() is not None,
        "budget_usd": get_settings().claude_monthly_budget_usd, "spent_usd": round(spent_usd(db), 4),
        "month": current_month(), "fallback_reason": reason,
        "claude_mode": "batch" if get_settings().claude_use_batch else "direct",
        "pending_batches": db.scalar(select(func.count()).select_from(SentimentBatch)
                                     .where(SentimentBatch.status == "in_progress")) or 0,
    }


def _canonical_item(db: Session, cluster: NewsCluster) -> NewsItem:
    return db.scalars(select(NewsItem).where(NewsItem.cluster_id == cluster.id)
                      .order_by(NewsItem.published_at, NewsItem.id).limit(1)).one()


def compute(db: Session, cluster: NewsCluster) -> SentimentResult:
    item = _canonical_item(db, cluster)
    claude = _claude()
    # Batch-Modus: die Meldung erscheint sofort mit Lexikon-Stimmung; Claude liefert nach (submit_batch)
    if claude is not None and not get_settings().claude_use_batch:
        try:
            return claude.classify(db, item.title, item.excerpt, item.language)
        except SourceError as exc:
            log.info("Claude-Stimmung nicht verfügbar (%s), Lexikon-Fallback", exc)
    return analyze(item.title, item.excerpt, item.language)


def store(db: Session, cluster_id: int, res: SentimentResult) -> None:
    sid = db.scalar(select(Source.id).where(Source.key == res.source_key))
    if sid is None:
        raise SourceError(f"Unbekannte Quelle {res.source_key}")
    row = db.get(Sentiment, cluster_id) or Sentiment(cluster_id=cluster_id)
    row.label, row.score, row.evidence, row.rationale = res.label, res.score, res.evidence, res.rationale
    row.method, row.model_name, row.model_version, row.source_id = res.method, res.model_name, res.model_version, sid
    row.created_at = utcnow()
    db.add(row)
    db.commit()


def submit_batch(db: Session, limit: int = BATCH_SIZE) -> int:
    """Reicht Lexikon-eingestufte Cluster jüngerer Meldungen als Batch bei Claude ein. Gibt die Anzahl zurück."""
    claude = _claude()
    if claude is None or fallback_reason(db) is not None:
        return 0
    taken = select(SentimentBatchItem.cluster_id).where(SentimentBatchItem.status.notin_(RETRYABLE))
    clusters = db.scalars(select(NewsCluster).join(Sentiment, Sentiment.cluster_id == NewsCluster.id)
                          .where(Sentiment.method == "lexicon", NewsCluster.id.notin_(taken),
                                 NewsCluster.first_published_at > utcnow() - UPGRADE_WINDOW)
                          .order_by(NewsCluster.first_published_at.desc()).limit(limit)).all()
    room = get_settings().claude_monthly_budget_usd - spent_usd(db) - reserved_usd(db)
    requests, reserved = [], 0.0
    for c in clusters:
        item = _canonical_item(db, c)
        cost = worst_case_usd(item.title, item.excerpt, BATCH_FACTOR)
        if reserved + cost > room:
            break
        requests.append((c.id, item.title, item.excerpt))
        reserved += cost
    if not requests:
        return 0
    try:
        batch_id = claude.submit_batch(requests)
    except SourceError as exc:
        log.warning("Claude-Batch nicht eingereicht: %s", exc)
        return 0
    row = SentimentBatch(batch_id=batch_id, reserved_usd=reserved)
    db.add(row)
    db.flush()
    db.add_all(SentimentBatchItem(batch_id=row.id, cluster_id=cid) for cid, _t, _e in requests)
    db.commit()
    return len(requests)


def process_batches(db: Session) -> int:
    """Holt Ergebnisse beendeter Batches ab. Jede Antwort läuft durch dieselbe Prüfung wie bei Einzelaufrufen
    (wörtliche Zitate, keine Empfehlungssprache); was nicht besteht, bleibt bei der Lexikon-Stimmung."""
    claude = _claude()
    if claude is None:
        return 0
    stored = 0
    for batch in db.scalars(select(SentimentBatch).where(SentimentBatch.status == "in_progress")
                            .order_by(SentimentBatch.id)).all():
        try:
            if not claude.batch_ended(batch.batch_id):
                continue
            results = claude.batch_results(batch.batch_id)
        except SourceError as exc:
            log.warning("Claude-Batch %s: %s", batch.batch_id, exc)
            continue
        for it in db.scalars(select(SentimentBatchItem).where(SentimentBatchItem.batch_id == batch.id,
                                                              SentimentBatchItem.status == "pending")).all():
            res = results.get(it.cluster_id, {})
            kind = res.get("type")
            it.status = kind if kind in ("expired", "canceled") else "errored"
            if kind != "succeeded":
                continue
            try:
                msg = res["message"]
                usage = msg["usage"]
                record_usage(db, int(usage["input_tokens"]), int(usage["output_tokens"]), BATCH_FACTOR)
                block = next(b for b in msg["content"] if b.get("type") == "tool_use")
                cluster = db.get(NewsCluster, it.cluster_id)
                item = _canonical_item(db, cluster) if cluster else None
                if item is None:
                    continue
                parsed = verify(block["input"], item.title, item.excerpt)
            except (KeyError, TypeError, ValueError, StopIteration, SourceError) as exc:
                it.status = "rejected"
                log.info("Claude-Batch %s: Antwort für Cluster %s verworfen (%s)", batch.batch_id, it.cluster_id, exc)
                continue
            store(db, it.cluster_id, parsed)
            it.status = "succeeded"
            stored += 1
        batch.status, batch.reserved_usd, batch.completed_at = "ended", 0.0, utcnow()
        db.commit()
    return stored


def sentiment_pass(db: Session, limit: int = 30) -> int:
    """Berechnet fehlende Stimmungen und holt Lexikon-Einstufungen jüngerer Cluster mit Claude nach
    (direkt oder, Standard, als Batch)."""
    done = 0
    missing = db.scalars(select(NewsCluster).outerjoin(Sentiment, Sentiment.cluster_id == NewsCluster.id)
                         .where(Sentiment.cluster_id.is_(None)).order_by(NewsCluster.first_published_at.desc())
                         .limit(limit)).all()
    for c in missing:
        store(db, c.id, compute(db, c))
        done += 1
    if get_settings().claude_use_batch:
        done += process_batches(db)
        submit_batch(db)
    elif _claude() is not None and fallback_reason(db) is None and done < limit:
        upgrades = db.scalars(select(NewsCluster).join(Sentiment, Sentiment.cluster_id == NewsCluster.id)
                              .where(Sentiment.method == "lexicon",
                                     NewsCluster.first_published_at > utcnow() - UPGRADE_WINDOW)
                              .order_by(NewsCluster.first_published_at.desc()).limit(limit - done)).all()
        for c in upgrades:
            res = compute(db, c)
            if res.method == "claude":
                store(db, c.id, res)
                done += 1
    return done
