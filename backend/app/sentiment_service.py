"""Stimmung je Cluster berechnen: Claude, wenn verfügbar und im Budget, sonst Lexikon. Die Rückfallstufe ist immer
sichtbar (method und model_name der gespeicherten Stimmung, plus /api/news/sentiment-status)."""
import logging
from datetime import timedelta

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.adapters.http import SourceError
from app.adapters.registry import get_adapter
from app.config import get_settings
from app.models import NewsCluster, NewsItem, Sentiment, Source, utcnow
from app.sentiment_claude import ClaudeSentimentSource, current_month, spent_usd
from app.sentiment_lexicon import SentimentResult, analyze

log = logging.getLogger("sentiment")
UPGRADE_WINDOW = timedelta(days=3)  # Lexikon-Einstufungen jüngerer Cluster werden mit Claude nachgeholt


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


def status(db: Session) -> dict[str, object]:
    reason = fallback_reason(db)
    return {
        "active_method": "lexicon" if reason else "claude", "claude_configured": _claude() is not None,
        "budget_usd": get_settings().claude_monthly_budget_usd, "spent_usd": round(spent_usd(db), 4),
        "month": current_month(), "fallback_reason": reason,
    }


def _canonical_item(db: Session, cluster: NewsCluster) -> NewsItem:
    return db.scalars(select(NewsItem).where(NewsItem.cluster_id == cluster.id)
                      .order_by(NewsItem.published_at, NewsItem.id).limit(1)).one()


def compute(db: Session, cluster: NewsCluster) -> SentimentResult:
    item = _canonical_item(db, cluster)
    claude = _claude()
    if claude is not None:
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


def sentiment_pass(db: Session, limit: int = 30) -> int:
    """Berechnet fehlende Stimmungen und holt Lexikon-Einstufungen jüngerer Cluster mit Claude nach."""
    done = 0
    missing = db.scalars(select(NewsCluster).outerjoin(Sentiment, Sentiment.cluster_id == NewsCluster.id)
                         .where(Sentiment.cluster_id.is_(None)).order_by(NewsCluster.first_published_at.desc())
                         .limit(limit)).all()
    for c in missing:
        store(db, c.id, compute(db, c))
        done += 1
    if _claude() is not None and fallback_reason(db) is None and done < limit:
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
