"""Registry aller Adapter. Workstreams 1B/2A/2B registrieren ihre Adapter hier (eine Zeile pro Quelle).
Solange keiner registriert ist, zeigt die Quellen-Seite ehrlich eine leere Liste."""
import logging
from datetime import UTC, datetime

from app.adapters.base import AdapterMetadata, Health, NewsAdapter, PriceAdapter, SourceAdapter

log = logging.getLogger(__name__)

_ADAPTERS: dict[str, SourceAdapter] = {}


def register(adapter: SourceAdapter) -> None:
    _ADAPTERS[adapter.metadata().key] = adapter


def all_adapters() -> list[SourceAdapter]:
    return list(_ADAPTERS.values())


def price_adapters() -> list[PriceAdapter]:
    return [a for a in _ADAPTERS.values() if isinstance(a, PriceAdapter)]


def news_adapters() -> list[NewsAdapter]:
    return [a for a in _ADAPTERS.values() if isinstance(a, NewsAdapter)]


def get_adapter(key: str) -> SourceAdapter | None:
    return _ADAPTERS.get(key)


def clear() -> None:  # nur für Tests
    _ADAPTERS.clear()


class BrokenAdapter(SourceAdapter):
    """Platzhalter für einen Adapter, dessen Aufbau an der Konfiguration scheiterte. Er erscheint auf der Seite
    Quellen als 'disabled' mit Grund (Grundregel 6: nie still verschwinden) und legt nichts anderes lahm."""

    def __init__(self, key: str, name: str, reason: str) -> None:
        self.key, self._name, self.disabled_reason = key, name, reason

    def metadata(self) -> AdapterMetadata:
        return AdapterMetadata(key=self.key, name=self._name, kind="reference",
                               description="Diese Quelle konnte wegen eines Konfigurationsfehlers nicht starten.",
                               homepage="", terms_url="", update_interval="nicht aktiv", delay_text="nicht aktiv",
                               requires_key=False)

    def health(self) -> Health:
        return Health(status="disabled", checked_at=datetime.now(UTC), message=self.disabled_reason)

    def is_configured(self) -> bool:
        return False


def _safe_build(build, key: str, name: str) -> SourceAdapter:  # type: ignore[no-untyped-def]
    try:
        return build()  # type: ignore[no-any-return]
    except Exception as exc:  # ein Konfigurationsfehler darf API und Worker nie am Start hindern
        log.warning("Adapter %s konnte nicht gestartet werden: %s: %s", key, type(exc).__name__, exc)
        return BrokenAdapter(key, name, f"Konfigurationsfehler in .env ({type(exc).__name__}); Quelle deaktiviert")


def load_builtin_adapters() -> None:
    """Registriert alle eingebauten Adapter. Adapter ohne API-Schlüssel werden trotzdem registriert und als
    'disabled' auf der Quellen-Seite gezeigt (Grundregel 6: ehrlich statt still)."""
    from app.adapters.alpaca import AlpacaAdapter
    from app.adapters.alphavantage_news import AlphaVantageNewsAdapter
    from app.adapters.finnhub import FinnhubAdapter
    from app.adapters.finnhub_news import FinnhubNewsAdapter
    from app.adapters.gdelt import GdeltAdapter
    from app.adapters.ir_feeds import IrFeedsAdapter
    from app.adapters.marketaux import MarketauxAdapter
    from app.adapters.openfigi import OpenFigiAdapter
    from app.adapters.rss import build_rss_adapters
    from app.adapters.sec_edgar import SecEdgarAdapter
    from app.adapters.stooq import StooqAdapter
    from app.adapters.yahoo import YahooAdapter
    from app.explain_service import ClaudeExplainSource
    from app.sentiment_claude import ClaudeSentimentSource
    from app.sentiment_lexicon import LexiconSentimentSource

    for adapter_cls in (
        AlpacaAdapter, FinnhubAdapter, StooqAdapter, YahooAdapter, OpenFigiAdapter, FinnhubNewsAdapter, SecEdgarAdapter,
        AlphaVantageNewsAdapter, MarketauxAdapter, GdeltAdapter, IrFeedsAdapter,
        LexiconSentimentSource, ClaudeSentimentSource, ClaudeExplainSource,
    ):
        if adapter_cls.key not in _ADAPTERS:
            register(_safe_build(adapter_cls, adapter_cls.key, adapter_cls.__name__))
    try:
        rss_adapters = build_rss_adapters()
    except Exception as exc:
        log.warning("RSS-Adapter konnten nicht aufgebaut werden: %s: %s", type(exc).__name__, exc)
        reason = f"Konfigurationsfehler in .env ({type(exc).__name__}); Quelle deaktiviert"
        register(BrokenAdapter("rss", "RSS-Feeds", reason))
        rss_adapters = []
    for rss in rss_adapters:
        if rss.key not in _ADAPTERS:
            register(rss)
