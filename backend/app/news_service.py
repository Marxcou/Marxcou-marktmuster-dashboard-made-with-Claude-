"""News-Pipeline: abrufen, Zuordnung zu Instrumenten, Duplikate zu Clustern zusammenführen, speichern,
Stimmung berechnen, Ereignis für die WebSocket-Anzeige veröffentlichen. Jede Zeile trägt source_id und fetched_at
(Grundregel 2); fehlt eine Quelle, wird nichts erfunden."""
import logging
import threading
from collections.abc import Sequence
from datetime import UTC, datetime, timedelta

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.adapters.base import NewsAdapter, NewsRecord, NewsTarget
from app.adapters.http import SourceError
from app.adapters.registry import get_adapter
from app.db import SessionLocal
from app.events import publish
from app.models import Instrument, NewsCluster, NewsInstrument, NewsItem, Source, WatchlistItem, utcnow
from app.news_dedup import CLUSTER_WINDOW_HOURS, normalize_url, similar, title_tokens
from app.news_match import PRIORITY, Candidate, Matcher
from app.sentiment_service import sentiment_pass

log = logging.getLogger("news")
INITIAL_LOOKBACK = timedelta(hours=48)
OVERLAP = timedelta(minutes=15)
EVENT_MAX_AGE = timedelta(hours=6)  # ältere (nachgeholte) Meldungen lösen keine Live-Ereignisse aus
_INGEST_LOCK = threading.Lock()  # ein Schreiber, damit parallele Jobs keine doppelten Cluster anlegen


def _aware(dt: datetime) -> datetime:
    return dt if dt.tzinfo else dt.replace(tzinfo=UTC)


def watchlist_targets(db: Session) -> list[NewsTarget]:
    rows = db.scalars(select(Instrument).join(WatchlistItem, WatchlistItem.instrument_id == Instrument.id)
                      .distinct().order_by(Instrument.id)).all()
    return [NewsTarget(symbol=i.symbol, exchange=i.exchange, name=i.name, isin=i.isin) for i in rows]


def _candidates(db: Session) -> list[Candidate]:
    return [Candidate(i.id, i.symbol, i.exchange, i.name, i.isin) for i in db.scalars(select(Instrument))]


def ingest(db: Session, records: Sequence[NewsRecord], adapter: NewsAdapter) -> dict[str, int]:
    """Speichert Meldungen einer Quelle. Gibt Zähler zurück (neu, Cluster neu, verworfen, doppelt)."""
    stats = {"new_items": 0, "new_clusters": 0, "discarded": 0, "already_known": 0}
    if not records:
        return stats
    with _INGEST_LOCK:
        source_id = db.scalar(select(Source.id).where(Source.key == adapter.metadata().key))
        if source_id is None:
            raise SourceError(f"Unbekannte Quelle {adapter.metadata().key}")
        matcher = Matcher(_candidates(db))
        window_start = min(r.published_at for r in records) - timedelta(hours=CLUSTER_WINDOW_HOURS)
        index: list[tuple[int, str, frozenset[str]]] = [
            (cid, url_n, title_tokens(title)) for cid, url_n, title in db.execute(
                select(NewsItem.cluster_id, NewsItem.url_normalized, NewsItem.title)
                .where(NewsItem.published_at >= window_start))]
        known = set(db.scalars(select(NewsItem.external_id).where(NewsItem.source_id == source_id)))
        events: list[dict[str, object]] = []
        for rec in sorted(records, key=lambda r: r.published_at):
            if rec.external_id in known:
                stats["already_known"] += 1
                continue
            matches = matcher.match(rec)
            if adapter.require_match and not matches:
                stats["discarded"] += 1
                continue
            url_n, tokens = normalize_url(rec.url), title_tokens(rec.title)
            cluster_id = next((cid for cid, u, t in index if u == url_n), None)
            if cluster_id is None:
                cluster_id = next((cid for cid, _u, t in index if similar(t, tokens)), None)
            cluster = db.get(NewsCluster, cluster_id) if cluster_id else None
            is_new = cluster is None
            if cluster is None:
                cluster = NewsCluster(canonical_title=rec.title, first_published_at=rec.published_at,
                                      last_published_at=rec.published_at, item_count=0)
                db.add(cluster)
                db.flush()
                stats["new_clusters"] += 1
            db.add(NewsItem(source_id=source_id, external_id=rec.external_id, url=rec.url, url_normalized=url_n,
                            title=rec.title, excerpt=rec.excerpt[:300], published_at=rec.published_at,
                            fetched_at=rec.fetched_at, language=rec.language, publisher=rec.publisher,
                            cluster_id=cluster.id))
            cluster.item_count += 1
            # SQLite liefert naive Zeitstempel (UTC); für den Vergleich wieder mit Zeitzone versehen
            cluster.last_published_at = max(_aware(cluster.last_published_at), rec.published_at)
            if rec.published_at < _aware(cluster.first_published_at):  # ältere Meldung wird zur Leitmeldung
                cluster.first_published_at, cluster.canonical_title = rec.published_at, rec.title
            existing = {ni.instrument_id: ni for ni in db.scalars(
                select(NewsInstrument).where(NewsInstrument.cluster_id == cluster.id))}
            for iid, method in matches.items():
                ni = existing.get(iid)
                if ni is None:
                    db.add(NewsInstrument(cluster_id=cluster.id, instrument_id=iid, match_method=method,
                                          source_id=source_id, fetched_at=rec.fetched_at))
                elif PRIORITY[method] < PRIORITY[ni.match_method]:
                    ni.match_method = method
            db.flush()
            index.append((cluster.id, url_n, tokens))
            known.add(rec.external_id)
            stats["new_items"] += 1
            if utcnow() - _aware(rec.published_at) < EVENT_MAX_AGE:
                events.append({"cluster_id": cluster.id, "canonical_title": cluster.canonical_title,
                               "first_published_at": cluster.first_published_at.isoformat(),
                               "item_count": cluster.item_count, "is_new": is_new,
                               "instrument_ids": sorted(set(existing) | set(matches))})
        db.commit()
    # je Cluster nur das letzte Ereignis veröffentlichen
    for payload in {e["cluster_id"]: e for e in events}.values():
        publish(db, "news", payload)
    return stats


def since_for(db: Session, adapter: NewsAdapter) -> datetime:
    last = db.scalar(select(func.max(NewsItem.fetched_at)).join(Source, Source.id == NewsItem.source_id)
                     .where(Source.key == adapter.metadata().key))
    if last is None:
        return datetime.now(UTC) - INITIAL_LOOKBACK
    return max(_aware(last) - OVERLAP, datetime.now(UTC) - timedelta(days=7))


def run_adapter(db: Session, adapter: NewsAdapter) -> dict[str, int] | None:
    """Ein Abrufzyklus für eine Quelle. Fehler bleiben lokal (Grundregel 6: Ausfall legt nichts anderes lahm)."""
    key = adapter.metadata().key
    if not adapter.is_configured():
        return None
    try:
        records = adapter.fetch_news_for(watchlist_targets(db), since_for(db, adapter))
        stats = ingest(db, records, adapter)
    except SourceError as exc:
        log.warning("News-Quelle %s: %s", key, exc)
        return None
    log.info("News-Quelle %s: %s", key, stats)
    if stats["new_items"]:
        sentiment_pass(db)
    return stats


def make_job(key: str):  # type: ignore[no-untyped-def]
    def job() -> None:
        adapter = get_adapter(key)
        if isinstance(adapter, NewsAdapter):
            with SessionLocal() as db:
                run_adapter(db, adapter)

    job.__name__ = f"news_{key}"
    return job


def sentiment_job() -> None:
    """Holt fehlende Stimmungen nach und stuft Lexikon-Ergebnisse mit Claude neu ein, sobald möglich."""
    with SessionLocal() as db:
        try:
            sentiment_pass(db)
        except SourceError as exc:
            log.warning("Stimmung: %s", exc)
