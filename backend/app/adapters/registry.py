"""Registry aller Adapter. Workstreams 1B/2A/2B registrieren ihre Adapter hier (eine Zeile pro Quelle).
Solange keiner registriert ist, zeigt die Quellen-Seite ehrlich eine leere Liste."""
from app.adapters.base import PriceAdapter, SourceAdapter

_ADAPTERS: dict[str, SourceAdapter] = {}


def register(adapter: SourceAdapter) -> None:
    _ADAPTERS[adapter.metadata().key] = adapter


def all_adapters() -> list[SourceAdapter]:
    return list(_ADAPTERS.values())


def price_adapters() -> list[PriceAdapter]:
    return [a for a in _ADAPTERS.values() if isinstance(a, PriceAdapter)]


def clear() -> None:  # nur für Tests
    _ADAPTERS.clear()


def load_builtin_adapters() -> None:
    """Registriert alle eingebauten Adapter. Adapter ohne API-Schlüssel werden trotzdem registriert und als
    'disabled' auf der Quellen-Seite gezeigt (Grundregel 6: ehrlich statt still)."""
    from app.adapters.alpaca import AlpacaAdapter
    from app.adapters.finnhub import FinnhubAdapter
    from app.adapters.openfigi import OpenFigiAdapter
    from app.adapters.stooq import StooqAdapter

    for adapter_cls in (AlpacaAdapter, FinnhubAdapter, StooqAdapter, OpenFigiAdapter):
        if adapter_cls.key not in _ADAPTERS:
            register(adapter_cls())
