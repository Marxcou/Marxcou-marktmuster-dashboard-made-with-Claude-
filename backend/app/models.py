"""Kerntabellen für Phase 1. Jede Datenzeile trägt source_id und fetched_at (Grundregel 2).
Weitere Tabellen (News, Muster, Prognosen, ...) kommen mit ihren Phasen per eigener Migration."""
from datetime import UTC, date, datetime
from typing import Any

from sqlalchemy import (
    JSON,
    Boolean,
    Date,
    DateTime,
    Float,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column

from app.db import Base


def utcnow() -> datetime:
    return datetime.now(UTC)


class User(Base):
    __tablename__ = "users"
    id: Mapped[int] = mapped_column(primary_key=True)
    email: Mapped[str] = mapped_column(String(320), unique=True)
    password_hash: Mapped[str] = mapped_column(String(255))
    display_name: Mapped[str] = mapped_column(String(100))
    role: Mapped[str] = mapped_column(String(10), default="user")  # admin | user
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class UserSession(Base):
    __tablename__ = "user_sessions"
    token_hash: Mapped[str] = mapped_column(String(64), primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    csrf_token: Mapped[str] = mapped_column(String(64))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))


class Source(Base):
    __tablename__ = "sources"
    id: Mapped[int] = mapped_column(primary_key=True)
    key: Mapped[str] = mapped_column(String(50), unique=True)
    name: Mapped[str] = mapped_column(String(100))
    kind: Mapped[str] = mapped_column(String(20))  # price | news | llm | reference
    description: Mapped[str] = mapped_column(Text, default="")
    homepage: Mapped[str] = mapped_column(String(500), default="")
    terms_url: Mapped[str] = mapped_column(String(500), default="")
    update_interval: Mapped[str] = mapped_column(String(100), default="")
    delay_text: Mapped[str] = mapped_column(String(100), default="")
    requires_key: Mapped[bool] = mapped_column(Boolean, default=False)
    is_official: Mapped[bool] = mapped_column(Boolean, default=True)
    status: Mapped[str] = mapped_column(String(20), default="disabled")  # online|degraded|offline|disabled
    last_success_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    last_error: Mapped[str | None] = mapped_column(Text, nullable=True)


class Instrument(Base):
    __tablename__ = "instruments"
    id: Mapped[int] = mapped_column(primary_key=True)
    symbol: Mapped[str] = mapped_column(String(20))
    name: Mapped[str] = mapped_column(String(200))
    isin: Mapped[str | None] = mapped_column(String(12), nullable=True, index=True)
    figi: Mapped[str | None] = mapped_column(String(12), nullable=True)
    exchange: Mapped[str] = mapped_column(String(4))  # XNYS | XNAS | XETR
    currency: Mapped[str] = mapped_column(String(3))
    provider_symbols: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
    source_id: Mapped[int] = mapped_column(ForeignKey("sources.id"))
    fetched_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    __table_args__ = (UniqueConstraint("symbol", "exchange"),)


class WatchlistItem(Base):
    __tablename__ = "watchlist_items"
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), primary_key=True)
    instrument_id: Mapped[int] = mapped_column(ForeignKey("instruments.id"), primary_key=True)
    position: Mapped[int] = mapped_column(Integer, default=0)
    added_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class PriceBar(Base):
    __tablename__ = "price_bars"
    instrument_id: Mapped[int] = mapped_column(ForeignKey("instruments.id"), primary_key=True)
    timeframe: Mapped[str] = mapped_column(String(3), primary_key=True)  # 1m|5m|1h|1d
    ts_utc: Mapped[datetime] = mapped_column(DateTime(timezone=True), primary_key=True)
    source_id: Mapped[int] = mapped_column(ForeignKey("sources.id"), primary_key=True)
    open: Mapped[float] = mapped_column(Float)
    high: Mapped[float] = mapped_column(Float)
    low: Mapped[float] = mapped_column(Float)
    close: Mapped[float] = mapped_column(Float)
    volume: Mapped[float | None] = mapped_column(Float, nullable=True)
    fetched_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    is_demo: Mapped[bool] = mapped_column(Boolean, default=False)


class Quote(Base):
    __tablename__ = "quotes"
    id: Mapped[int] = mapped_column(primary_key=True)
    instrument_id: Mapped[int] = mapped_column(ForeignKey("instruments.id"), index=True)
    price: Mapped[float] = mapped_column(Float)
    change_abs: Mapped[float | None] = mapped_column(Float, nullable=True)
    change_pct: Mapped[float | None] = mapped_column(Float, nullable=True)
    ts_utc: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    source_id: Mapped[int] = mapped_column(ForeignKey("sources.id"))
    fetched_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    delay_seconds: Mapped[int | None] = mapped_column(Integer, nullable=True)
    is_demo: Mapped[bool] = mapped_column(Boolean, default=False)
    __table_args__ = (Index("ix_quotes_instr_ts", "instrument_id", "ts_utc"),)


class Event(Base):
    """Worker -> API Ereignis-Warteschlange (SQLite-basiert; Redis später möglich)."""
    __tablename__ = "events"
    id: Mapped[int] = mapped_column(primary_key=True)
    type: Mapped[str] = mapped_column(String(40))  # quote | news | detection | source_status
    payload: Mapped[dict[str, Any]] = mapped_column(JSON)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class NewsCluster(Base):
    """Zusammengeführte Meldungen zur selben Nachricht. Die UI listet alle Quellen des Clusters."""
    __tablename__ = "news_clusters"
    id: Mapped[int] = mapped_column(primary_key=True)
    canonical_title: Mapped[str] = mapped_column(String(500))
    first_published_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)
    last_published_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    item_count: Mapped[int] = mapped_column(Integer, default=1)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class NewsItem(Base):
    __tablename__ = "news_items"
    id: Mapped[int] = mapped_column(primary_key=True)
    source_id: Mapped[int] = mapped_column(ForeignKey("sources.id"))
    external_id: Mapped[str] = mapped_column(String(300))
    url: Mapped[str] = mapped_column(String(1000))
    url_normalized: Mapped[str] = mapped_column(String(1000), index=True)
    title: Mapped[str] = mapped_column(String(500))
    excerpt: Mapped[str] = mapped_column(String(300), default="")  # nie der Volltext
    published_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)
    fetched_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    language: Mapped[str | None] = mapped_column(String(8), nullable=True)
    publisher: Mapped[str | None] = mapped_column(String(200), nullable=True)
    cluster_id: Mapped[int] = mapped_column(ForeignKey("news_clusters.id"), index=True)
    __table_args__ = (UniqueConstraint("source_id", "external_id"),)


class NewsInstrument(Base):
    __tablename__ = "news_instruments"
    cluster_id: Mapped[int] = mapped_column(ForeignKey("news_clusters.id"), primary_key=True)
    instrument_id: Mapped[int] = mapped_column(ForeignKey("instruments.id"), primary_key=True, index=True)
    match_method: Mapped[str] = mapped_column(String(20))  # provider_tag | isin | ticker | name
    source_id: Mapped[int] = mapped_column(ForeignKey("sources.id"))
    fetched_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class Sentiment(Base):
    """Stimmung je Cluster mit Begründung und Verfahren. source_id verweist auf das Verfahren
    (sentiment_lexicon oder claude_sentiment) und erscheint damit auf der Seite Quellen."""
    __tablename__ = "sentiments"
    cluster_id: Mapped[int] = mapped_column(ForeignKey("news_clusters.id"), primary_key=True)
    label: Mapped[str] = mapped_column(String(10))  # positiv | neutral | negativ
    score: Mapped[float] = mapped_column(Float)  # -1 .. 1
    evidence: Mapped[list[str]] = mapped_column(JSON, default=list)  # wörtliche Zitate
    rationale: Mapped[str] = mapped_column(Text)
    method: Mapped[str] = mapped_column(String(10))  # lexicon | claude
    model_name: Mapped[str] = mapped_column(String(100))
    model_version: Mapped[str] = mapped_column(String(50))
    source_id: Mapped[int] = mapped_column(ForeignKey("sources.id"))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class LlmUsage(Base):
    """Verbrauch der Claude-API je Monat (für die harte Obergrenze CLAUDE_MONTHLY_BUDGET_USD)."""
    __tablename__ = "llm_usage"
    month: Mapped[str] = mapped_column(String(7), primary_key=True)  # YYYY-MM (UTC)
    input_tokens: Mapped[int] = mapped_column(Integer, default=0)
    output_tokens: Mapped[int] = mapped_column(Integer, default=0)
    cost_usd: Mapped[float] = mapped_column(Float, default=0.0)


class ApiUsage(Base):
    """Abrufzähler je Quelle und UTC-Tag für Tageskontingente (übersteht Neustarts des Workers)."""
    __tablename__ = "api_usage"
    source_key: Mapped[str] = mapped_column(String(50), primary_key=True)
    day: Mapped[date] = mapped_column(Date, primary_key=True)
    calls: Mapped[int] = mapped_column(Integer, default=0)


class SentimentBatch(Base):
    """Eine bei Anthropic eingereichte Batch-Anfrage für Stimmungen. reserved_usd ist der Höchstbetrag, der bis zum
    Eintreffen der Ergebnisse gegen das Monatslimit gerechnet wird."""
    __tablename__ = "sentiment_batches"
    id: Mapped[int] = mapped_column(primary_key=True)
    batch_id: Mapped[str] = mapped_column(String(100), unique=True)
    status: Mapped[str] = mapped_column(String(15), default="in_progress")  # in_progress | ended
    reserved_usd: Mapped[float] = mapped_column(Float, default=0.0)
    submitted_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class SentimentBatchItem(Base):
    __tablename__ = "sentiment_batch_items"
    batch_id: Mapped[int] = mapped_column(ForeignKey("sentiment_batches.id"), primary_key=True)
    cluster_id: Mapped[int] = mapped_column(ForeignKey("news_clusters.id"), primary_key=True, index=True)
    # pending | succeeded | rejected (Antwort nicht belegbar) | errored | expired | canceled
    status: Mapped[str] = mapped_column(String(10), default="pending")
