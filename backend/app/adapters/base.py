"""Adapter-Schnittstellen. Pro Datenquelle genau ein Adapter (Phase 1B/2 implementieren sie).

Regeln für jede Implementierung:
- Jeder zurückgegebene Datensatz trägt source_key und fetched_at (Grundregel 2).
- Fehlt der API-Schlüssel oder ist die Quelle nicht erreichbar, wird das über health() gemeldet
  und es werden KEINE Ersatzdaten erfunden (Grundregel 6).
- Rate-Limits, Retry/Backoff und Circuit-Breaker liegen im Adapter, ein Ausfall bleibt lokal.
"""
from abc import ABC, abstractmethod
from dataclasses import dataclass
from datetime import datetime
from typing import Literal

SourceKind = Literal["price", "news", "llm", "reference"]
SourceStatus = Literal["online", "degraded", "offline", "disabled"]
Timeframe = Literal["1m", "5m", "1h", "1d"]


@dataclass(frozen=True)
class AdapterMetadata:
    """Alles, was die Seite 'Quellen' anzeigt. Sie wird ausschließlich hieraus erzeugt."""

    key: str
    name: str
    kind: SourceKind
    description: str
    homepage: str
    terms_url: str
    update_interval: str  # z. B. "Live per WebSocket", "alle 5 Min."
    delay_text: str  # z. B. "15 Min. verzögert", "Handelsende"
    requires_key: bool
    is_official: bool = True


@dataclass(frozen=True)
class Health:
    status: SourceStatus
    checked_at: datetime
    last_success_at: datetime | None = None
    message: str | None = None


@dataclass(frozen=True)
class BarRecord:
    symbol: str
    exchange: str
    timeframe: Timeframe
    ts_utc: datetime
    open: float
    high: float
    low: float
    close: float
    volume: float | None
    source_key: str
    fetched_at: datetime


@dataclass(frozen=True)
class QuoteRecord:
    symbol: str
    exchange: str
    price: float
    ts_utc: datetime
    source_key: str
    fetched_at: datetime
    change_abs: float | None = None
    change_pct: float | None = None
    delay_seconds: int | None = None


@dataclass(frozen=True)
class InstrumentRecord:
    symbol: str
    name: str
    exchange: str
    currency: str
    source_key: str
    fetched_at: datetime
    isin: str | None = None
    figi: str | None = None


@dataclass(frozen=True)
class NewsRecord:
    external_id: str
    url: str
    title: str
    excerpt: str  # max. ~300 Zeichen, nie der Volltext
    published_at: datetime
    fetched_at: datetime
    source_key: str
    language: str | None = None
    symbols: tuple[str, ...] = ()


class SourceAdapter(ABC):
    @abstractmethod
    def metadata(self) -> AdapterMetadata: ...

    @abstractmethod
    def health(self) -> Health: ...

    def is_configured(self) -> bool:
        """False, wenn ein nötiger API-Schlüssel fehlt. Dann Status 'disabled'."""
        return True


class PriceAdapter(SourceAdapter):
    supported_exchanges: tuple[str, ...] = ()

    @abstractmethod
    def fetch_bars(
        self, symbol: str, exchange: str, timeframe: Timeframe, start: datetime, end: datetime
    ) -> list[BarRecord]: ...

    def fetch_quote(self, symbol: str, exchange: str) -> QuoteRecord | None:
        return None

    def search_instruments(self, query: str) -> list[InstrumentRecord]:
        return []


class NewsAdapter(SourceAdapter):
    @abstractmethod
    def fetch_news(self, symbols: list[str], since: datetime) -> list[NewsRecord]: ...
