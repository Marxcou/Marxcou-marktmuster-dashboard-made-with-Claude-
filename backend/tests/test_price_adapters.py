import json
from datetime import UTC, datetime

import httpx
import pytest

from app.adapters.alpaca import AlpacaAdapter
from app.adapters.finnhub import FinnhubAdapter
from app.adapters.http import ResilientHttp, SourceError, SourceUnavailable
from app.adapters.openfigi import OpenFigiAdapter
from app.adapters.stooq import StooqAdapter, stooq_symbol
from app.adapters.yahoo import YahooAdapter, yahoo_symbol
from app.config import get_settings

T0 = datetime(2026, 9, 1, tzinfo=UTC)
T1 = datetime(2026, 9, 28, tzinfo=UTC)
NOSLEEP = {"sleep": lambda _s: None}


@pytest.fixture(autouse=True)
def keys(monkeypatch):
    for k in ("ALPACA_API_KEY_ID", "ALPACA_API_SECRET_KEY", "FINNHUB_API_KEY", "STOOQ_API_KEY"):
        monkeypatch.setenv(k, "test-key")
    get_settings.cache_clear()
    yield
    get_settings.cache_clear()


def mock(handler):
    return httpx.MockTransport(handler)


def test_alpaca_bars_paginate_and_carry_source():
    calls = []

    def handler(req: httpx.Request) -> httpx.Response:
        calls.append(dict(req.url.params))
        assert req.headers["APCA-API-KEY-ID"] == "test-key" and req.url.params["feed"] == "iex"
        if "page_token" not in req.url.params:
            return httpx.Response(200, json={"bars": [
                {"t": "2026-09-25T13:30:00Z", "o": 1, "h": 2, "l": 0.5, "c": 1.5, "v": 100}], "next_page_token": "p2"})
        return httpx.Response(200, json={"bars": [
            {"t": "2026-09-25T13:31:00Z", "o": 1.5, "h": 2, "l": 1, "c": 1.8, "v": 50}], "next_page_token": None})

    bars = AlpacaAdapter(transport=mock(handler), **NOSLEEP).fetch_bars("AAPL", "XNAS", "1m", T0, T1)
    assert [b.close for b in bars] == [1.5, 1.8] and len(calls) == 2
    assert all(b.source_key == "alpaca" and b.fetched_at.tzinfo for b in bars)
    assert bars[0].ts_utc == datetime(2026, 9, 25, 13, 30, tzinfo=UTC)


def test_alpaca_quote_from_snapshot():
    body = {"AAPL": {"latestTrade": {"p": 110.0, "t": "2026-09-28T14:00:00Z"}, "prevDailyBar": {"c": 100.0}}}
    q = AlpacaAdapter(transport=mock(lambda r: httpx.Response(200, json=body)), **NOSLEEP).fetch_quote("AAPL", "XNAS")
    assert q and q.price == 110.0 and q.change_pct == pytest.approx(10.0) and q.source_key == "alpaca"


def test_alpaca_quote_none_when_no_trade():
    a = AlpacaAdapter(transport=mock(lambda r: httpx.Response(200, json={"AAPL": {}})), **NOSLEEP)
    assert a.fetch_quote("AAPL", "XNAS") is None


def test_not_configured_without_key(monkeypatch):
    monkeypatch.setenv("ALPACA_API_KEY_ID", "")
    get_settings.cache_clear()
    assert AlpacaAdapter().is_configured() is False


def test_finnhub_quote_and_unknown_symbol_is_none():
    ok = {"c": 190.5, "d": 1.5, "dp": 0.79, "t": 1790000000}
    a = FinnhubAdapter(transport=mock(lambda r: httpx.Response(200, json=ok)), **NOSLEEP)
    q = a.fetch_quote("AAPL", "XNAS")
    assert q and q.price == 190.5 and q.change_abs == 1.5 and q.source_key == "finnhub"
    zero = {"c": 0, "d": None, "dp": None, "t": 0}
    assert FinnhubAdapter(transport=mock(lambda r: httpx.Response(200, json=zero)), **NOSLEEP).fetch_quote(
        "ZZZZ", "XNAS") is None


def test_stooq_symbol_mapping():
    assert stooq_symbol("SAP", "XETR") == "sap.de" and stooq_symbol("BRK.B", "XNYS") == "brk-b.us"


def test_stooq_parses_csv_and_rejects_non_csv():
    csv_text = "Date,Open,High,Low,Close,Volume\n2026-09-24,10,11,9,10.5,1000\n2026-09-25,10.5,12,10,11,2000\n"
    a = StooqAdapter(transport=mock(lambda r: httpx.Response(200, text=csv_text)), **NOSLEEP)
    bars = a.fetch_bars("SAP", "XETR", "1d", T0, T1)
    assert [b.close for b in bars] == [10.5, 11.0] and bars[0].ts_utc == datetime(2026, 9, 24, tzinfo=UTC)
    assert a.fetch_bars("SAP", "XETR", "1m", T0, T1) == []  # keine Intraday-Daten
    bad = StooqAdapter(transport=mock(lambda r: httpx.Response(200, text="Get your apikey: ...")), **NOSLEEP)
    with pytest.raises(SourceError):  # Hinweistext darf nie als Kursdaten gelesen werden
        bad.fetch_bars("SAP", "XETR", "1d", T0, T1)
    empty = StooqAdapter(transport=mock(lambda r: httpx.Response(200, text="No data")), **NOSLEEP)
    assert empty.fetch_bars("SAP", "XETR", "1d", T0, T1) == []


def test_yahoo_is_off_unless_enabled(monkeypatch):
    assert YahooAdapter().is_configured() is False
    assert YahooAdapter().metadata().is_official is False and "inoffiziell" in YahooAdapter().metadata().name
    monkeypatch.setenv("YAHOO_ENABLED", "true")
    get_settings.cache_clear()
    assert YahooAdapter().is_configured() is True


def test_yahoo_symbol_mapping():
    assert yahoo_symbol("SAP", "XETR") == "SAP.DE" and yahoo_symbol("BRK.B", "XNYS") == "BRK-B"
    assert yahoo_symbol("aapl", "XNAS") == "AAPL"


def _chart(ts: list[int], close: list[float | None], offset: int = 7200) -> dict[str, object]:
    return {"chart": {"error": None, "result": [{"meta": {"gmtoffset": offset}, "timestamp": ts, "indicators": {
        "quote": [{"open": close, "high": close, "low": close, "close": close, "volume": [100] * len(ts)}]}}]}}


def test_yahoo_parses_daily_bars_to_trading_day_and_skips_gaps():
    seen = []
    # 24.09. 07:00 UTC (XETRA-Handelsbeginn), 25.09. ohne Werte, 26.09. 07:00 UTC
    ts = [int(datetime(2026, 9, d, 7, tzinfo=UTC).timestamp()) for d in (24, 25, 26)]

    def handler(req: httpx.Request) -> httpx.Response:
        seen.append(req)
        return httpx.Response(200, json=_chart(ts, [10.5, None, 11.0]))

    a = YahooAdapter(transport=mock(handler), **NOSLEEP)
    bars = a.fetch_bars("SAP", "XETR", "1d", T0, T1)
    assert [b.close for b in bars] == [10.5, 11.0]
    assert [b.ts_utc for b in bars] == [datetime(2026, 9, 24, tzinfo=UTC), datetime(2026, 9, 26, tzinfo=UTC)]
    assert all(b.source_key == "yahoo" and b.fetched_at and b.volume == 100 for b in bars)
    assert seen[0].url.path == "/v8/finance/chart/SAP.DE" and seen[0].url.params["interval"] == "1d"
    assert int(seen[0].url.params["period1"]) == int(T0.timestamp())
    assert "Mozilla" in seen[0].headers["user-agent"]
    assert a.fetch_bars("SAP", "XETR", "1m", T0, T1) == []  # keine Intraday-Daten
    # US: Handelsbeginn 13:30 UTC, gmtoffset -14400 -> derselbe Kalendertag
    us = YahooAdapter(transport=mock(lambda r: httpx.Response(200, json=_chart(
        [int(datetime(2026, 9, 24, 13, 30, tzinfo=UTC).timestamp())], [200.0], offset=-14400))), **NOSLEEP)
    assert us.fetch_bars("AAPL", "XNAS", "1d", T0, T1)[0].ts_utc == datetime(2026, 9, 24, tzinfo=UTC)


def test_yahoo_unknown_symbol_is_empty_and_bad_answers_are_errors():
    gone = {"chart": {"result": None, "error": {"code": "Not Found", "description": "No data found"}}}
    a = YahooAdapter(transport=mock(lambda r: httpx.Response(404, json=gone)), **NOSLEEP)
    with pytest.raises(SourceError):  # HTTP 404 ist ein Fehler der Quelle, nicht "keine Daten"
        a.fetch_bars("NOPE", "XETR", "1d", T0, T1)
    ok_gone = YahooAdapter(transport=mock(lambda r: httpx.Response(200, json=gone)), **NOSLEEP)
    assert ok_gone.fetch_bars("NOPE", "XETR", "1d", T0, T1) == []
    html = YahooAdapter(transport=mock(lambda r: httpx.Response(200, text="<html>consent</html>")), **NOSLEEP)
    with pytest.raises(SourceError):  # z. B. Zustimmungsseite: nie als Kursdaten deuten
        html.fetch_bars("SAP", "XETR", "1d", T0, T1)
    other = {"chart": {"result": None, "error": {"code": "Unauthorized"}}}
    with pytest.raises(SourceError, match="Unauthorized"):
        YahooAdapter(transport=mock(lambda r: httpx.Response(200, json=other)), **NOSLEEP).fetch_bars(
            "SAP", "XETR", "1d", T0, T1)
    ragged = _chart([1, 2], [1.0])
    with pytest.raises(SourceError):
        YahooAdapter(transport=mock(lambda r: httpx.Response(200, json=ragged)), **NOSLEEP).fetch_bars(
            "SAP", "XETR", "1d", T0, T1)


def test_openfigi_search_by_name_and_isin():
    seen = []

    def handler(req: httpx.Request) -> httpx.Response:
        seen.append((req.url.path, json.loads(req.content)))
        if req.url.path == "/v3/search":
            return httpx.Response(200, json={"data": [
                {"figi": "F1", "ticker": "SAP", "name": "SAP SE", "exchCode": "GY", "securityType": "Common Stock"},
                {"figi": "F2", "ticker": "SAP", "name": "SAP SE", "exchCode": "GY", "securityType": "Common Stock"},
                {"figi": "F3", "ticker": "SAPGF", "name": "SAP SE", "exchCode": "US", "securityType": "Common Stock"},
            ]})
        return httpx.Response(200, json=[{"data": [
            {"figi": "F9", "ticker": "AAPL", "name": "APPLE INC", "exchCode": "UW", "securityType": "Common Stock"}]}])

    a = OpenFigiAdapter(transport=mock(handler), **NOSLEEP)
    r = a.search_instruments("SAP")
    # dedupliziert, nur XNYS/XNAS/XETR
    assert [(x.symbol, x.exchange, x.currency) for x in r] == [("SAP", "XETR", "EUR")]
    r = a.search_instruments("us0378331005")
    assert seen[-1][0] == "/v3/mapping" and r[0].isin == "US0378331005" and r[0].exchange == "XNAS"
    assert r[0].name == "Apple Inc"


def test_retry_then_success_and_no_retry_on_auth_error():
    n = {"c": 0}

    def flaky(req: httpx.Request) -> httpx.Response:
        n["c"] += 1
        return httpx.Response(503) if n["c"] < 3 else httpx.Response(200, json={})

    h = ResilientHttp(base_url="https://x", transport=mock(flaky), **NOSLEEP)
    assert h.request("GET", "/").status_code == 200 and n["c"] == 3 and h.last_error is None

    m = {"c": 0}

    def denied(req: httpx.Request) -> httpx.Response:
        m["c"] += 1
        return httpx.Response(401)

    h2 = ResilientHttp(base_url="https://x", transport=mock(denied), **NOSLEEP)
    with pytest.raises(SourceError, match="Schlüssel"):
        h2.request("GET", "/")
    assert m["c"] == 1


def test_circuit_breaker_opens_and_recovers():
    now = {"t": 1000.0}
    h = ResilientHttp(base_url="https://x", transport=mock(lambda r: httpx.Response(500)), retries=0,
                      breaker_threshold=2, breaker_cooldown=30, clock=lambda: now["t"], **NOSLEEP)
    for _ in range(2):
        with pytest.raises(SourceError):
            h.request("GET", "/")
    with pytest.raises(SourceUnavailable):  # offen: kein weiterer Netzwerkzugriff
        h.request("GET", "/")
    assert h.breaker_open
    now["t"] += 31
    assert not h.breaker_open


def test_health_reflects_failure_honestly():
    a = AlpacaAdapter(transport=mock(lambda r: httpx.Response(500)), retries=0, **NOSLEEP)
    h = a.health()
    assert h.status == "offline" and h.message
    ok = AlpacaAdapter(transport=mock(lambda r: httpx.Response(200, json={})), **NOSLEEP)
    assert ok.health().status == "online" and ok.health().last_success_at
