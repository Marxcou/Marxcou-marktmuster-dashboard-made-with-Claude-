"""OpenFIGI (Bloomberg-Mapping-Dienst): Suche nach Ticker, Firmenname und ISIN für US und XETRA."""
import re
from datetime import UTC, datetime
from typing import Any

import httpx

from app.adapters.base import AdapterMetadata, BarRecord, InstrumentRecord, PriceAdapter, Timeframe
from app.adapters.http import ProbedHealth, ResilientHttp, SourceError
from app.config import get_settings

# OpenFIGI-Börsencodes -> MIC. Nur diese drei Märkte sind im Umfang (Nasdaq-Segmente UQ/UW/UR).
EXCH_TO_MIC = {"UN": "XNYS", "UQ": "XNAS", "UW": "XNAS", "UR": "XNAS", "GY": "XETR"}
CURRENCY = {"XNYS": "USD", "XNAS": "USD", "XETR": "EUR"}  # Währung folgt dem Handelsplatz
ISIN_RE = re.compile(r"^[A-Z]{2}[A-Z0-9]{9}[0-9]$")


class OpenFigiAdapter(ProbedHealth, PriceAdapter):
    key = "openfigi"
    supported_exchanges = ("XNYS", "XNAS", "XETR")

    def __init__(self, transport: httpx.BaseTransport | None = None, **kw: Any) -> None:
        self._token = get_settings().openfigi_api_key
        headers = {"X-OPENFIGI-APIKEY": self._token} if self._token else {}
        self.http = ResilientHttp(base_url="https://api.openfigi.com", headers=headers,
                                  rate_per_min=20 if not self._token else 200, transport=transport, **kw)

    def metadata(self) -> AdapterMetadata:
        return AdapterMetadata(
            key=self.key, name="OpenFIGI", kind="reference",
            description="Zuordnung von ISIN, Ticker und Firmenname zu Börsenplätzen (NYSE, Nasdaq, XETRA). "
            "Liefert keine Kurse.",
            homepage="https://www.openfigi.com", terms_url="https://www.openfigi.com/about/terms",
            update_interval="bei Suchanfragen", delay_text="nicht zutreffend (Stammdaten)", requires_key=False,
        )

    def _probe(self) -> None:
        self.http.request("POST", "/v3/mapping", json=[{"idType": "TICKER", "idValue": "AAPL", "exchCode": "UW"}])

    def fetch_bars(
        self, symbol: str, exchange: str, timeframe: Timeframe, start: datetime, end: datetime
    ) -> list[BarRecord]:
        return []

    def search_instruments(self, query: str) -> list[InstrumentRecord]:
        q = query.strip()
        if ISIN_RE.match(q.upper()):
            resp = self.http.request("POST", "/v3/mapping", json=[{"idType": "ID_ISIN", "idValue": q.upper()}])
            try:
                data = (resp.json()[0]).get("data") or []
            except (ValueError, IndexError, AttributeError, KeyError) as exc:
                raise SourceError("Unerwartetes Antwortformat") from exc
            return _records(data, isin=q.upper())
        resp = self.http.request("POST", "/v3/search", json={"query": q, "marketSecDes": "Equity"})
        try:
            data = resp.json().get("data") or []
        except (ValueError, AttributeError) as exc:
            raise SourceError("Unerwartetes Antwortformat") from exc
        return _records(data, isin=None)


def _records(data: list[dict[str, Any]], isin: str | None) -> list[InstrumentRecord]:
    now = datetime.now(UTC)
    seen: set[tuple[str, str]] = set()
    out: list[InstrumentRecord] = []
    for d in data:
        mic = EXCH_TO_MIC.get(d.get("exchCode", ""))
        ticker = d.get("ticker")
        if not mic or not ticker or d.get("securityType") not in ("Common Stock", "ADR", None):
            continue
        if (ticker, mic) in seen:
            continue
        seen.add((ticker, mic))
        out.append(InstrumentRecord(
            symbol=ticker, name=str(d.get("name") or ticker).title() if str(d.get("name", "")).isupper()
            else str(d.get("name") or ticker), exchange=mic, currency=CURRENCY[mic], source_key="openfigi",
            fetched_at=now, isin=isin, figi=d.get("figi"),
        ))
    return out
