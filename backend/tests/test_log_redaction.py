"""Kein konfigurierter Schlüssel darf in Logs oder gespeicherten Statustexten erscheinen."""
import logging

import httpx
import pytest

from app.adapters.finnhub import FinnhubAdapter
from app.adapters.http import ResilientHttp, SourceError
from app.adapters.marketaux import MarketauxAdapter
from app.config import get_settings
from app.log_redaction import install, redact

SECRETS = {
    "FINNHUB_API_KEY": "finnhub-SECRET-111", "MARKETAUX_API_KEY": "marketaux-SECRET-222",
    "ALPHAVANTAGE_API_KEY": "alphav-SECRET-333", "STOOQ_API_KEY": "stooq-SECRET-444",
    "ANTHROPIC_API_KEY": "anthropic-SECRET-555", "ALPACA_API_SECRET_KEY": "alpaca-SECRET-666",
}


@pytest.fixture(autouse=True)
def keys(monkeypatch):
    for k, v in SECRETS.items():
        monkeypatch.setenv(k, v)
    get_settings.cache_clear()
    install()
    yield
    get_settings.cache_clear()


def assert_clean(text: str) -> None:
    for v in SECRETS.values():
        assert v not in text


def test_redact_known_values_and_query_params():
    text = f"GET https://x/quote?symbol=AAPL&token=whatever123456&apikey=abc {SECRETS['STOOQ_API_KEY']}"
    out = redact(text)
    assert_clean(out)
    assert "whatever123456" not in out and "symbol=AAPL" in out


def test_httpx_request_logging_and_tracebacks_are_clean(caplog):
    caplog.set_level(logging.DEBUG)

    def handler(req: httpx.Request) -> httpx.Response:
        return httpx.Response(500)

    http = ResilientHttp(base_url="https://api.example.com", transport=httpx.MockTransport(handler),
                         sleep=lambda _s: None)
    with pytest.raises(SourceError):
        http.request("GET", "/q", params={"apikey": SECRETS["STOOQ_API_KEY"]})
    try:
        raise RuntimeError(f"failed https://x/?api_token={SECRETS['MARKETAUX_API_KEY']}")
    except RuntimeError:
        logging.getLogger("app.test").exception("Abruf %s", SECRETS["FINNHUB_API_KEY"])
    text = "\n".join(caplog.text.splitlines()) + (http.last_error or "")
    assert_clean(text)
    assert "Abruf" in text


def test_finnhub_uses_header_not_url():
    seen = []

    def handler(req: httpx.Request) -> httpx.Response:
        seen.append(req)
        return httpx.Response(200, json={"c": 1, "d": 0, "dp": 0, "t": 1})

    a = FinnhubAdapter(transport=httpx.MockTransport(handler), sleep=lambda _s: None)
    a.http.request("GET", "/quote", params={"symbol": "AAPL"})
    assert seen[0].headers["X-Finnhub-Token"] == SECRETS["FINNHUB_API_KEY"]
    assert SECRETS["FINNHUB_API_KEY"] not in str(seen[0].url)


def test_stored_error_text_is_clean():
    a = MarketauxAdapter(transport=httpx.MockTransport(lambda r: httpx.Response(401)), sleep=lambda _s: None)
    with pytest.raises(SourceError):
        a.http.request("GET", "/v1/news/all", params={"api_token": SECRETS["MARKETAUX_API_KEY"]})
    assert_clean(a.http.last_error or "")
