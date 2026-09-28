"""Stooq: Tagesdaten (Handelsende) für US und XETRA, Hauptquelle für XETRA im kostenlosen Tarif."""
import csv
import io
from datetime import UTC, datetime
from typing import Any

import httpx

from app.adapters.base import AdapterMetadata, BarRecord, PriceAdapter, Timeframe
from app.adapters.http import ProbedHealth, ResilientHttp, SourceError
from app.config import get_settings

_SUFFIX = {"XNYS": "us", "XNAS": "us", "XETR": "de"}


def stooq_symbol(symbol: str, exchange: str) -> str:
    return f"{symbol.lower().replace('.', '-')}.{_SUFFIX[exchange]}"


class StooqAdapter(ProbedHealth, PriceAdapter):
    key = "stooq"
    supported_exchanges = ("XNYS", "XNAS", "XETR")

    def __init__(self, transport: httpx.BaseTransport | None = None, **kw: Any) -> None:
        self._token = get_settings().stooq_api_key
        self.http = ResilientHttp(base_url="https://stooq.com", rate_per_min=20, transport=transport, **kw)

    def metadata(self) -> AdapterMetadata:
        return AdapterMetadata(
            key=self.key, name="Stooq", kind="price",
            description="Tagesdaten (Handelsende) für US-Aktien und XETRA. Keine Intraday-Daten.",
            homepage="https://stooq.com", terms_url="https://stooq.com/", update_interval="täglich",
            delay_text="Handelsende (Tagesdaten)", requires_key=True, is_official=False,
        )

    def is_configured(self) -> bool:
        return bool(self._token)

    def _get(self, symbol: str, d1: str, d2: str) -> str:
        resp = self.http.request("GET", "/q/d/l/", params={
            "s": symbol, "i": "d", "d1": d1, "d2": d2, "apikey": self._token})
        return resp.text

    def _probe(self) -> None:
        today = datetime.now(UTC).strftime("%Y%m%d")
        parse_csv(self._get("aapl.us", today, today), "aapl", "XNAS", datetime.now(UTC), allow_empty=True)

    def fetch_bars(
        self, symbol: str, exchange: str, timeframe: Timeframe, start: datetime, end: datetime
    ) -> list[BarRecord]:
        if timeframe != "1d" or exchange not in _SUFFIX:
            return []
        text = self._get(stooq_symbol(symbol, exchange), start.strftime("%Y%m%d"), end.strftime("%Y%m%d"))
        return parse_csv(text, symbol, exchange, datetime.now(UTC), allow_empty=True)


def parse_csv(
    text: str, symbol: str, exchange: str, fetched_at: datetime, allow_empty: bool = False
) -> list[BarRecord]:
    head = text.lstrip()[:200]
    if head.lower().startswith("date,"):
        pass
    elif not head or head.lower().startswith("no data"):
        if allow_empty:
            return []
        raise SourceError("Keine Daten")
    else:  # z. B. Hinweis zum API-Schlüssel oder Limit: nicht als Kursdaten deuten
        raise SourceError("Stooq lieferte keine CSV-Daten (Schlüssel oder Limit prüfen)")
    out: list[BarRecord] = []
    for row in csv.DictReader(io.StringIO(text)):
        try:
            day = datetime.strptime(row["Date"], "%Y-%m-%d").replace(tzinfo=UTC)
            out.append(BarRecord(
                symbol=symbol, exchange=exchange, timeframe="1d", ts_utc=day, open=float(row["Open"]),
                high=float(row["High"]), low=float(row["Low"]), close=float(row["Close"]),
                volume=float(row["Volume"]) if row.get("Volume") else None, source_key="stooq",
                fetched_at=fetched_at,
            ))
        except (KeyError, ValueError) as exc:
            raise SourceError("Unerwartetes CSV-Format") from exc
    return out
