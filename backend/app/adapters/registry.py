"""Registry aller Adapter. Workstreams 1B/2A/2B registrieren ihre Adapter hier (eine Zeile pro Quelle).
Solange keiner registriert ist, zeigt die Quellen-Seite ehrlich eine leere Liste."""
from app.adapters.base import NewsAdapter, PriceAdapter, SourceAdapter

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


def load_builtin_adapters() -> None:
    """Registriert alle eingebauten Adapter. Adapter ohne API-Schlüssel werden trotzdem registriert und als
    'disabled' auf der Quellen-Seite gezeigt (Grundregel 6: ehrlich statt still)."""
    from app.adapters.alpaca import AlpacaAdapter
    from app.adapters.alphavantage_news import AlphaVantageNewsAdapter
    from app.adapters.finnhub import FinnhubAdapter
    from app.adapters.finnhub_news import FinnhubNewsAdapter
    from app.adapters.gdelt import GdeltAdapter
    from app.adapters.marketaux import MarketauxAdapter
    from app.adapters.openfigi import OpenFigiAdapter
    from app.adapters.rss import build_rss_adapters
    from app.adapters.sec_edgar import SecEdgarAdapter
    from app.adapters.stooq import StooqAdapter
    from app.sentiment_claude import ClaudeSentimentSource
    from app.sentiment_lexicon import LexiconSentimentSource

    for adapter_cls in (
        AlpacaAdapter, FinnhubAdapter, StooqAdapter, OpenFigiAdapter, FinnhubNewsAdapter, SecEdgarAdapter,
        AlphaVantageNewsAdapter, MarketauxAdapter, GdeltAdapter, LexiconSentimentSource, ClaudeSentimentSource,
    ):
        if adapter_cls.key not in _ADAPTERS:
            register(adapter_cls())
    for rss in build_rss_adapters():
        if rss.key not in _ADAPTERS:
            register(rss)
