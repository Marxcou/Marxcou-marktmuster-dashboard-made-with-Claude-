"""Finnhub Company News (kostenlos): US-Unternehmensmeldungen mit Überschrift, kurzer Zusammenfassung und Link."""
import logging
from datetime import UTC, datetime
from typing import Any

import httpx

from app.adapters.base import AdapterMetadata, NewsAdapter, NewsRecord
from app.adapters.http import ProbedHealth, ResilientHttp, SourceError, is_header_safe
from app.adapters.news_common import clean_excerpt, clean_title
from app.config import get_settings

log = logging.getLogger(__name__)


class FinnhubNewsAdapter(ProbedHealth, NewsAdapter):
    key = "finnhub_news"
    supported_exchanges = ("XNYS", "XNAS")
    poll_seconds = 300

    def __init__(self, transport: httpx.BaseTransport | None = None, **kw: Any) -> None:
        self._token = get_settings().finnhub_api_key.strip()
        if self._token and not is_header_safe(self._token):
            log.warning("FINNHUB_API_KEY: unzulässige Zeichen, Finnhub bleibt deaktiviert")
            self._token = ""
        self.http = ResilientHttp(base_url="https://finnhub.io/api/v1", rate_per_min=30, transport=transport,
                                  headers={"X-Finnhub-Token": self._token} if self._token else None, **kw)

    def metadata(self) -> AdapterMetadata:
        return AdapterMetadata(
            key=self.key, name="Finnhub Unternehmensnachrichten", kind="news",
            description="US-Unternehmensmeldungen je Aktie (Überschrift, kurzer Auszug, Link zum Original). "
            "Finnhub reicht Meldungen weiterer Verlage durch; der ursprüngliche Verlag steht je Meldung dabei.",
            homepage="https://finnhub.io", terms_url="https://finnhub.io/terms-of-service",
            update_interval="alle 5 Min. (Watchlist-Aktien)", delay_text="Minuten", requires_key=True,
        )

    def is_configured(self) -> bool:
        return bool(self._token)

    def _probe(self) -> None:
        self.http.request("GET", "/quote", params={"symbol": "AAPL"})

    def fetch_news(self, symbols: list[str], since: datetime) -> list[NewsRecord]:
        out: list[NewsRecord] = []
        today = datetime.now(UTC).date()
        for sym in symbols:
            resp = self.http.request("GET", "/company-news", params={
                "symbol": sym, "from": since.date().isoformat(), "to": today.isoformat()})
            try:
                rows = resp.json()
                fetched = datetime.now(UTC)
                for r in rows:
                    ts = datetime.fromtimestamp(int(r["datetime"]), UTC)
                    if ts < since or not r.get("headline") or not r.get("url"):
                        continue
                    out.append(NewsRecord(
                        external_id=str(r.get("id") or r["url"]), url=r["url"], title=clean_title(r["headline"]),
                        excerpt=clean_excerpt(r.get("summary")), published_at=ts, fetched_at=fetched,
                        source_key=self.key, language="en", publisher=r.get("source") or None, symbols=(sym,),
                    ))
            except (ValueError, KeyError, TypeError) as exc:
                raise SourceError("Unerwartetes Antwortformat") from exc
        return out
