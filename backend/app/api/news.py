"""Nachrichten-Endpunkte. Der Vertrag steht in docs/api-contract.md (Abschnitt Phase 2)."""
import base64
import binascii
from datetime import UTC, datetime, timedelta
from zoneinfo import ZoneInfo

from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.api.instruments import SourceRef
from app.config import get_settings
from app.deps import DB, CurrentUser
from app.models import (
    Instrument,
    NewsCluster,
    NewsInstrument,
    NewsItem,
    Sentiment,
    Source,
    WatchlistItem,
)
from app.sentiment_service import status as sentiment_status

router = APIRouter(prefix="/api", tags=["news"])
DEFAULT_LIMIT, MAX_LIMIT = 25, 100
SENTIMENTS = ("positiv", "neutral", "negativ")


class InstrumentRef(BaseModel):
    id: int
    symbol: str
    match_method: str


class SentimentOut(BaseModel):
    label: str
    score: float
    method: str
    model_name: str
    model_version: str
    rationale: str
    evidence: list[str]
    created_at: datetime


class NewsItemOut(BaseModel):
    id: int
    title: str
    excerpt: str
    url: str
    published_at: datetime
    fetched_at: datetime
    language: str | None
    publisher: str | None
    source: SourceRef


class NewsClusterOut(BaseModel):
    id: int
    canonical_title: str
    first_published_at: datetime
    last_published_at: datetime
    item_count: int
    instruments: list[InstrumentRef]
    sentiment: SentimentOut | None
    items: list[NewsItemOut]


class NewsListOut(BaseModel):
    items: list[NewsClusterOut]
    total: int
    next_cursor: str | None
    empty_reason: str | None


class CountsOut(BaseModel):
    counts: dict[str, int]
    empty_reason: str | None


class SentimentStatusOut(BaseModel):
    active_method: str
    claude_configured: bool
    budget_usd: float
    spent_usd: float
    month: str
    fallback_reason: str | None
    claude_mode: str = "batch"  # batch (halber Preis, Ergebnis verzögert) | direct
    pending_batches: int = 0


def _source_ref(s: Source) -> SourceRef:
    return SourceRef(key=s.key, name=s.name, homepage=s.homepage, terms_url=s.terms_url, delay_text=s.delay_text)


def _fmt(dt: datetime) -> str:
    tz = ZoneInfo(get_settings().timezone)
    return dt.replace(tzinfo=dt.tzinfo or UTC).astimezone(tz).strftime("%d.%m.%Y %H:%M")


def empty_reason(db: Session, filtered: bool) -> str:
    news_sources = db.scalars(select(Source).where(Source.kind == "news")).all()
    if not any(s.status != "disabled" for s in news_sources):
        return "Keine News-Quelle aktiv. Quellen ohne API-Schlüssel sind deaktiviert, siehe Seite Quellen."
    last = max((s.last_success_at for s in news_sources if s.last_success_at), default=None)
    when = f" Letzter erfolgreicher Abruf einer News-Quelle: {_fmt(last)} Uhr." if last else ""
    if db.scalar(select(func.count(NewsCluster.id))) == 0:
        return "Noch keine Meldungen abgerufen. Neue Meldungen erscheinen nach dem nächsten Abrufzyklus." + when
    return ("Keine Meldungen für diese Auswahl." if filtered else "Keine Meldungen vorhanden.") + when


def _decode_cursor(cursor: str | None) -> int:
    if not cursor:
        return 0
    try:
        offset = int(base64.urlsafe_b64decode(cursor.encode()).decode().removeprefix("o:"))
    except (ValueError, binascii.Error) as exc:
        raise HTTPException(400, "Ungültiger Cursor") from exc
    return max(offset, 0)


def _encode_cursor(offset: int) -> str:
    return base64.urlsafe_b64encode(f"o:{offset}".encode()).decode()


def _list(db: Session, *, instrument_id: int | None, source: str | None, sentiment: str | None,
          since: datetime | None, until: datetime | None, limit: int, cursor: str | None) -> NewsListOut:
    if sentiment is not None and sentiment not in SENTIMENTS:
        raise HTTPException(422, "sentiment muss positiv, neutral oder negativ sein")
    q = select(NewsCluster)
    if instrument_id is not None:
        q = q.where(NewsCluster.id.in_(select(NewsInstrument.cluster_id).where(
            NewsInstrument.instrument_id == instrument_id)))
    if source:
        q = q.where(NewsCluster.id.in_(select(NewsItem.cluster_id).join(Source, Source.id == NewsItem.source_id)
                                       .where(Source.key == source)))
    if sentiment:
        q = q.where(NewsCluster.id.in_(select(Sentiment.cluster_id).where(Sentiment.label == sentiment)))
    if since:
        q = q.where(NewsCluster.first_published_at >= since)
    if until:
        q = q.where(NewsCluster.first_published_at <= until)
    total = db.scalar(select(func.count()).select_from(q.subquery())) or 0
    offset = _decode_cursor(cursor)
    clusters = db.scalars(q.order_by(NewsCluster.first_published_at.desc(), NewsCluster.id.desc())
                          .offset(offset).limit(limit)).all()
    ids = [c.id for c in clusters]
    items_by: dict[int, list[NewsItemOut]] = {i: [] for i in ids}
    for item, src in db.execute(select(NewsItem, Source).join(Source, Source.id == NewsItem.source_id)
                                .where(NewsItem.cluster_id.in_(ids)).order_by(NewsItem.published_at, NewsItem.id)):
        items_by[item.cluster_id].append(NewsItemOut(
            id=item.id, title=item.title, excerpt=item.excerpt, url=item.url, published_at=item.published_at,
            fetched_at=item.fetched_at, language=item.language, publisher=item.publisher, source=_source_ref(src)))
    inst_by: dict[int, list[InstrumentRef]] = {i: [] for i in ids}
    for ni, inst in db.execute(select(NewsInstrument, Instrument)
                               .join(Instrument, Instrument.id == NewsInstrument.instrument_id)
                               .where(NewsInstrument.cluster_id.in_(ids)).order_by(Instrument.symbol)):
        inst_by[ni.cluster_id].append(InstrumentRef(id=inst.id, symbol=inst.symbol, match_method=ni.match_method))
    sent_by = {s.cluster_id: s for s in db.scalars(select(Sentiment).where(Sentiment.cluster_id.in_(ids)))}
    out = [NewsClusterOut(
        id=c.id, canonical_title=c.canonical_title, first_published_at=c.first_published_at,
        last_published_at=c.last_published_at, item_count=c.item_count, instruments=inst_by[c.id],
        sentiment=SentimentOut.model_validate(sent_by[c.id], from_attributes=True) if c.id in sent_by else None,
        items=items_by[c.id]) for c in clusters]
    nxt = _encode_cursor(offset + limit) if offset + limit < total else None
    reason = empty_reason(db, filtered=any([instrument_id, source, sentiment, since, until])) if total == 0 else None
    return NewsListOut(items=out, total=total, next_cursor=nxt, empty_reason=reason)


@router.get("/news", response_model=NewsListOut)
def list_news(db: DB, _u: CurrentUser, instrument_id: int | None = None, source: str | None = None,
              sentiment: str | None = None, since: datetime | None = None, until: datetime | None = None,
              limit: int = Query(DEFAULT_LIMIT, ge=1, le=MAX_LIMIT), cursor: str | None = None) -> NewsListOut:
    return _list(db, instrument_id=instrument_id, source=source, sentiment=sentiment, since=since, until=until,
                 limit=limit, cursor=cursor)


@router.get("/news/counts", response_model=CountsOut)
def news_counts(db: DB, user: CurrentUser, since: datetime | None = None) -> CountsOut:
    since = since or datetime.now(UTC) - timedelta(hours=24)
    ids = list(db.scalars(select(WatchlistItem.instrument_id).where(WatchlistItem.user_id == user.id)))
    counts = {str(i): 0 for i in ids}
    if ids:
        rows = db.execute(select(NewsInstrument.instrument_id, func.count(NewsInstrument.cluster_id))
                          .join(NewsCluster, NewsCluster.id == NewsInstrument.cluster_id)
                          .where(NewsInstrument.instrument_id.in_(ids), NewsCluster.first_published_at >= since)
                          .group_by(NewsInstrument.instrument_id))
        counts.update({str(i): n for i, n in rows})
    reason = empty_reason(db, filtered=True) if ids and not any(counts.values()) else None
    return CountsOut(counts=counts, empty_reason=reason)


@router.get("/news/sentiment-status", response_model=SentimentStatusOut)
def news_sentiment_status(db: DB, _u: CurrentUser) -> SentimentStatusOut:
    return SentimentStatusOut(**sentiment_status(db))


@router.get("/instruments/{instrument_id}/news", response_model=NewsListOut)
def instrument_news(instrument_id: int, db: DB, _u: CurrentUser, since: datetime | None = None,
                    until: datetime | None = None, limit: int = Query(DEFAULT_LIMIT, ge=1, le=MAX_LIMIT),
                    cursor: str | None = None) -> NewsListOut:
    if db.get(Instrument, instrument_id) is None:
        raise HTTPException(404, "Instrument nicht gefunden")
    return _list(db, instrument_id=instrument_id, source=None, sentiment=None, since=since, until=until,
                 limit=limit, cursor=cursor)
