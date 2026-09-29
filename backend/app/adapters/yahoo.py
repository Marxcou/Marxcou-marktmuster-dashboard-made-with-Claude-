"""Yahoo Finance (inoffiziell): Tagesdaten für US und XETRA über den öffentlichen Chart-Endpunkt.

Nur aktiv mit YAHOO_ENABLED=true in .env. Es gibt keine offizielle API und keine Nutzungsbedingungen, die diese
Nutzung ausdrücklich erlauben; der Endpunkt kann sich ohne Ankündigung ändern. Deshalb standardmäßig aus und auf
der Seite Quellen als inoffiziell gekennzeichnet. Liefert der Endpunkt etwas Unerwartetes, gibt es einen
SourceError, nie geschätzte Werte (Grundregel 6)."""
from datetime import UTC, date, datetime, timedelta
from typing import Any

import httpx

from app.adapters.base import AdapterMetadata, BarRecord, PriceAdapter, Timeframe
from app.adapters.http import ProbedHealth, ResilientHttp, SourceError
from app.config import get_settings

_SUFFIX = {"XNYS": "", "XNAS": "", "XETR": ".DE"}
# Ohne browserähnlichen User-Agent antwortet der Endpunkt meist mit HTTP 429
_HEADERS = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) "
                          "Chrome/128.0 Safari/537.36", "Accept": "application/json"}


def yahoo_symbol(symbol: str, exchange: str) -> str:
    return f"{symbol.upper().replace('.', '-')}{_SUFFIX[exchange]}"


class YahooAdapter(ProbedHealth, PriceAdapter):
    key = "yahoo"
    supported_exchanges = ("XNYS", "XNAS", "XETR")
    disabled_reason = "In .env ausgeschaltet (YAHOO_ENABLED=false)"

    def __init__(self, transport: httpx.BaseTransport | None = None, **kw: Any) -> None:
        self._enabled = get_settings().yahoo_enabled
        self.http = ResilientHttp(base_url="https://query1.finance.yahoo.com", headers=_HEADERS, rate_per_min=30,
                                  transport=transport, **kw)

    def metadata(self) -> AdapterMetadata:
        return AdapterMetadata(
            key=self.key, name="Yahoo Finance (inoffiziell)", kind="price",
            description="Tagesdaten (Handelsende) für US-Aktien und XETRA über den öffentlichen Chart-Endpunkt von "
                        "Yahoo Finance. Inoffiziell: keine dokumentierte API, kann sich ohne Ankündigung ändern. "
                        "Kurse splitbereinigt, nicht dividendenbereinigt. Keine Intraday-Daten in diesem Dashboard.",
            homepage="https://finance.yahoo.com", terms_url="https://legal.yahoo.com/us/en/yahoo/terms/otos/index.html",
            update_interval="täglich", delay_text="Handelsende (Tagesdaten)", requires_key=False, is_official=False,
        )

    def is_configured(self) -> bool:
        return self._enabled

    def _chart(self, ticker: str, params: dict[str, Any]) -> dict[str, Any]:
        resp = self.http.request("GET", f"/v8/finance/chart/{ticker}", params=params)
        try:
            body = resp.json()
        except ValueError as exc:
            raise SourceError("Yahoo lieferte kein JSON") from exc
        chart = body.get("chart") if isinstance(body, dict) else None
        if not isinstance(chart, dict):
            raise SourceError("Unerwartetes Antwortformat von Yahoo")
        if chart.get("error"):
            err = chart["error"]
            code = err.get("code") if isinstance(err, dict) else None
            if code == "Not Found":
                return {}
            raise SourceError(f"Yahoo meldet Fehler: {code or 'unbekannt'}")
        results = chart.get("result") or []
        return results[0] if results and isinstance(results[0], dict) else {}

    def _probe(self) -> None:
        self._chart("AAPL", {"range": "5d", "interval": "1d"})

    def fetch_bars(
        self, symbol: str, exchange: str, timeframe: Timeframe, start: datetime, end: datetime
    ) -> list[BarRecord]:
        if timeframe != "1d" or exchange not in _SUFFIX:
            return []
        result = self._chart(yahoo_symbol(symbol, exchange), {
            "period1": int(start.timestamp()), "period2": int(end.timestamp()), "interval": "1d",
            "events": "div,split", "includePrePost": "false",
        })
        return parse_chart(result, symbol, exchange, datetime.now(UTC))


def _trading_day(ts: int, gmtoffset: int) -> date:
    """Yahoo stempelt Tageskerzen mit dem Handelsbeginn; maßgeblich ist der Kalendertag an der Börse."""
    return (datetime.fromtimestamp(ts, UTC) + timedelta(seconds=gmtoffset)).date()


def parse_chart(result: dict[str, Any], symbol: str, exchange: str, fetched_at: datetime) -> list[BarRecord]:
    """Tageskerzen mit Zeitstempel 00:00 UTC des Handelstags (wie Stooq). Tage mit fehlenden Werten werden
    ausgelassen statt ergänzt."""
    if not result:
        return []
    try:
        stamps = result.get("timestamp") or []
        quote = result["indicators"]["quote"][0] if stamps else {}
        offset = int((result.get("meta") or {}).get("gmtoffset") or 0)
        cols = [quote.get(k) or [] for k in ("open", "high", "low", "close", "volume")]
    except (KeyError, IndexError, TypeError, ValueError) as exc:
        raise SourceError("Unerwartetes Antwortformat von Yahoo") from exc
    if any(len(c) != len(stamps) for c in cols[:4]):
        raise SourceError("Unerwartetes Antwortformat von Yahoo (Spaltenlängen ungleich)")
    out: dict[date, BarRecord] = {}
    for i, ts in enumerate(stamps):
        o, h, lo, c = (cols[k][i] for k in range(4))
        if o is None or h is None or lo is None or c is None:
            continue
        vol = cols[4][i] if i < len(cols[4]) else None
        day = _trading_day(int(ts), offset)
        out[day] = BarRecord(
            symbol=symbol, exchange=exchange, timeframe="1d",
            ts_utc=datetime(day.year, day.month, day.day, tzinfo=UTC), open=float(o), high=float(h), low=float(lo),
            close=float(c), volume=float(vol) if vol is not None else None, source_key="yahoo", fetched_at=fetched_at,
        )
    return [out[d] for d in sorted(out)]
