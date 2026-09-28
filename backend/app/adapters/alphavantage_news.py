"""Alpha Vantage News (optional, kostenlos: 25 Anfragen pro Tag). Nur Überschrift, Auszug und Link werden
übernommen; die Stimmungsangaben von Alpha Vantage werden bewusst nicht verwendet (eigenes, erklärtes Verfahren)."""
from datetime import UTC, datetime
from typing import Any

import httpx

from app.adapters.base import AdapterMetadata, NewsAdapter, NewsRecord
from app.adapters.http import PassiveHealth, ResilientHttp, SourceError
from app.adapters.news_common import clean_excerpt, clean_title
from app.config import get_settings

DAILY_LIMIT = 20  # Reserve unter den 25 Anfragen pro Tag
CHUNK = 5


class AlphaVantageNewsAdapter(PassiveHealth, NewsAdapter):
    key = "alphavantage_news"
    supported_exchanges = ("XNYS", "XNAS")
    poll_seconds = 3600

    def __init__(self, transport: httpx.BaseTransport | None = None, **kw: Any) -> None:
        self._token = get_settings().alphavantage_api_key
        self.http = ResilientHttp(base_url="https://www.alphavantage.co", rate_per_min=5, transport=transport, **kw)
        self._day = datetime.now(UTC).date()
        self._calls = 0  # nur im Arbeitsspeicher: ein Neustart setzt den Zähler zurück
        self._cursor = 0

    def metadata(self) -> AdapterMetadata:
        return AdapterMetadata(
            key=self.key, name="Alpha Vantage News", kind="news",
            description="Optionale zusätzliche US-Nachrichtenquelle. Das kostenlose Kontingent (25 Anfragen pro Tag) "
            "reicht nur für wenige Aktien je Stunde; die Aktien werden reihum abgefragt.",
            homepage="https://www.alphavantage.co", terms_url="https://www.alphavantage.co/terms_of_service/",
            update_interval="stündlich, reihum (max. 20 Anfragen/Tag)", delay_text="Minuten", requires_key=True,
            is_official=True,
        )

    def is_configured(self) -> bool:
        return bool(self._token)


    def _budget_left(self) -> bool:
        today = datetime.now(UTC).date()
        if today != self._day:
            self._day, self._calls = today, 0
        return self._calls < DAILY_LIMIT

    def fetch_news(self, symbols: list[str], since: datetime) -> list[NewsRecord]:
        if not symbols or not self._budget_left():
            return []
        start = self._cursor % len(symbols)
        chunk = (symbols[start:] + symbols[:start])[:CHUNK]
        self._cursor += CHUNK
        self._calls += 1
        resp = self.http.request("GET", "/query", params={
            "function": "NEWS_SENTIMENT", "tickers": ",".join(chunk), "time_from": since.strftime("%Y%m%dT%H%M"),
            "limit": 50, "sort": "LATEST", "apikey": self._token})
        try:
            data = resp.json()
            if "feed" not in data:  # Limit- und Schlüsselfehler kommen als 200 mit Textfeld
                info = str(data.get("Information") or data.get("Note") or "keine Daten")
                raise SourceError("Alpha Vantage: " + info[:120])
            fetched = datetime.now(UTC)
            out = []
            for r in data["feed"]:
                ts = datetime.strptime(r["time_published"], "%Y%m%dT%H%M%S").replace(tzinfo=UTC)
                tags = tuple(t["ticker"] for t in r.get("ticker_sentiment", []) if t.get("ticker") in chunk)
                out.append(NewsRecord(
                    external_id=r["url"], url=r["url"], title=clean_title(r["title"]),
                    excerpt=clean_excerpt(r.get("summary")), published_at=ts, fetched_at=fetched,
                    source_key=self.key, language="en", publisher=r.get("source") or None, symbols=tags))
            return out
        except (ValueError, KeyError, TypeError) as exc:
            raise SourceError("Unerwartetes Antwortformat") from exc
