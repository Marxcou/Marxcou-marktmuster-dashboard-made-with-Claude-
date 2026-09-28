import json
from datetime import UTC, datetime

import httpx
import pytest

from app.adapters.alpaca import AlpacaAdapter
from app.adapters.finnhub import FinnhubAdapter
from app.adapters.http import ResilientHttp, SourceError, SourceUnavailable
from app.adapters.openfigi import OpenFigiAdapter
from app.adapters.stooq import StooqAdapter, stooq_symbol
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
