import json
from datetime import UTC, datetime

import httpx
import pytest
from defusedxml import EntitiesForbidden

from app.adapters.alphavantage_news import AlphaVantageNewsAdapter
from app.adapters.base import NewsTarget
from app.adapters.finnhub_news import FinnhubNewsAdapter
from app.adapters.gdelt import GdeltAdapter
from app.adapters.http import SourceError
from app.adapters.marketaux import MarketauxAdapter
from app.adapters.news_common import clean_excerpt, company_search_name
from app.adapters.rss import EQS, FEEDS, RssFeedAdapter, build_rss_adapters, parse_feed
from app.adapters.sec_edgar import SecEdgarAdapter
from app.config import get_settings

SINCE = datetime(2026, 9, 27, tzinfo=UTC)
NOSLEEP = {"sleep": lambda _s: None}


@pytest.fixture(autouse=True)
def keys(monkeypatch):
    for k in ("FINNHUB_API_KEY", "MARKETAUX_API_KEY", "ALPHAVANTAGE_API_KEY"):
        monkeypatch.setenv(k, "test-key")
    monkeypatch.setenv("SEC_EDGAR_CONTACT_EMAIL", "kontakt@example.com")
    monkeypatch.setenv("RSS_ENABLED_FEEDS", "")
    get_settings.cache_clear()
    yield
    get_settings.cache_clear()


def mock(handler):
    return httpx.MockTransport(handler)


def test_clean_excerpt_strips_html_and_truncates_to_300():
    assert clean_excerpt("<p>Hallo &amp; <b>Welt</b></p>") == "Hallo & Welt"
    long = clean_excerpt("wort " * 200)
    assert len(long) <= 300 and long.endswith("…")


def test_company_search_name_drops_legal_form():
    assert company_search_name("Apple Inc.") == "Apple"
    assert company_search_name("Siemens AG") == "Siemens"


def test_finnhub_news_maps_fields_and_tags_symbol():
    def handler(req: httpx.Request) -> httpx.Response:
        assert req.url.params["symbol"] == "AAPL" and req.url.params["token"] == "test-key"
        return httpx.Response(200, json=[
            {"id": 7, "datetime": 1790600000, "headline": "Apple <b>beats</b> estimates", "summary": "Kurz",
             "url": "https://example.com/a", "source": "Reuters", "related": "AAPL"},
            {"id": 8, "datetime": 1000, "headline": "Alt", "summary": "", "url": "https://example.com/b"},
        ])

    recs = FinnhubNewsAdapter(transport=mock(handler), **NOSLEEP).fetch_news(["AAPL"], SINCE)
    assert len(recs) == 1  # die alte Meldung liegt vor `since`
    r = recs[0]
    assert (r.title, r.symbols, r.publisher) == ("Apple beats estimates", ("AAPL",), "Reuters")
    assert r.source_key == "finnhub_news"
    assert r.fetched_at.tzinfo and r.published_at == datetime.fromtimestamp(1790600000, UTC)


def test_finnhub_news_error_stays_local():
    a = FinnhubNewsAdapter(transport=mock(lambda r: httpx.Response(401)), **NOSLEEP)
    with pytest.raises(SourceError):
        a.fetch_news(["AAPL"], SINCE)
    assert a.health().status == "offline"


def test_sec_edgar_builds_links_and_requires_contact_email(monkeypatch):
    def handler(req: httpx.Request) -> httpx.Response:
        assert "kontakt@example.com" in req.headers["User-Agent"]
        if req.url.path.endswith("company_tickers.json"):
            return httpx.Response(200, json={"0": {"cik_str": 320193, "ticker": "AAPL", "title": "Apple Inc."}})
        assert req.url.path == "/submissions/CIK0000320193.json"
        return httpx.Response(200, json={"filings": {"recent": {
            "accessionNumber": ["0000320193-26-000010", "0000320193-26-000011"],
            "acceptanceDateTime": ["2026-09-28T16:05:12.000Z", "2026-09-28T17:00:00.000Z"],
            "form": ["8-K", "S-8"], "primaryDocument": ["a8k.htm", "s8.htm"],
            "primaryDocDescription": ["8-K", "S-8"], "items": ["2.02,9.01", ""]}}})

    a = SecEdgarAdapter(transport=mock(handler), **NOSLEEP)
    recs = a.fetch_news(["AAPL", "UNBEKANNT"], SINCE)
    assert len(recs) == 1  # S-8 gehört nicht zu den beobachteten Formularen
    assert recs[0].url == "https://www.sec.gov/Archives/edgar/data/320193/000032019326000010/a8k.htm"
    assert "Form 8-K" in recs[0].title and "2.02,9.01" in recs[0].excerpt and recs[0].symbols == ("AAPL",)
    monkeypatch.setenv("SEC_EDGAR_CONTACT_EMAIL", "")
    get_settings.cache_clear()
    assert not SecEdgarAdapter().is_configured()


def test_alphavantage_limit_message_is_an_error_not_data():
    a = AlphaVantageNewsAdapter(
        transport=mock(lambda r: httpx.Response(200, json={"Information": "rate limit reached"})), **NOSLEEP)
    with pytest.raises(SourceError, match="rate limit"):
        a.fetch_news(["AAPL"], SINCE)


def test_alphavantage_parses_feed_and_respects_daily_budget():
    calls = []

    def handler(req: httpx.Request) -> httpx.Response:
        calls.append(req)
        return httpx.Response(200, json={"feed": [{
            "title": "T", "url": "https://x.example/1", "time_published": "20260928T120000", "summary": "S",
            "source": "Verlag", "ticker_sentiment": [{"ticker": "AAPL"}, {"ticker": "MSFT"}]}]})

    a = AlphaVantageNewsAdapter(transport=mock(handler), **NOSLEEP)
    recs = a.fetch_news(["AAPL"], SINCE)
    assert recs[0].symbols == ("AAPL",) and recs[0].published_at == datetime(2026, 9, 28, 12, tzinfo=UTC)
    a._calls = 20
    assert a.fetch_news(["AAPL"], SINCE) == [] and len(calls) == 1


def test_marketaux_uses_de_suffix_and_entity_tags():
    seen = {}

    def handler(req: httpx.Request) -> httpx.Response:
        seen.update(req.url.params)
        return httpx.Response(200, json={"data": [{
            "uuid": "u1", "title": "SAP wächst", "snippet": "…", "url": "https://x.example/sap",
            "language": "de", "published_at": "2026-09-28T10:33:00.000000Z", "source": "verlag.de",
            "entities": [{"symbol": "SAP.DE"}, {"symbol": "ANDERE"}]}]})

    a = MarketauxAdapter(transport=mock(handler), **NOSLEEP)
    recs = a.fetch_news_for([NewsTarget("SAP", "XETR", "SAP SE"), NewsTarget("AAPL", "XNAS", "Apple Inc.")], SINCE)
    assert seen["symbols"] == "SAP.DE,AAPL" and seen["limit"] == "3"
    assert recs[0].symbols == ("SAP.DE",) and recs[0].language == "de"


def test_gdelt_searches_by_name_and_requires_match():
    def handler(req: httpx.Request) -> httpx.Response:
        assert req.url.params["query"] == '"Apple"'
        return httpx.Response(200, json={"articles": [{
            "url": "https://x.example/g", "title": "Apple news", "seendate": "20260928T101500Z",
            "domain": "x.example", "language": "English"}]})

    a = GdeltAdapter(transport=mock(handler), **NOSLEEP)
    recs = a.fetch_news_for([NewsTarget("AAPL", "XNAS", "Apple Inc.")], SINCE)
    assert a.require_match and recs[0].symbols == () and recs[0].language == "en" and recs[0].excerpt == ""


RSS = b"""<?xml version="1.0"?><rss version="2.0"><channel>
<item><title>Erste Meldung</title><link>https://x.example/1</link><guid>g1</guid>
<description>&lt;p&gt;Kurztext&lt;/p&gt;</description><pubDate>Mon, 28 Sep 2026 10:00:00 +0200</pubDate></item>
<item><title>Ohne Datum</title><link>https://x.example/2</link></item></channel></rss>"""
ATOM = b"""<feed xmlns="http://www.w3.org/2005/Atom"><entry><title>Atom-Meldung</title>
<link href="https://x.example/a"/><id>a1</id><updated>2026-09-28T09:00:00Z</updated><summary>Text</summary></entry></feed>"""


def test_parse_rss_and_atom_drop_items_without_date():
    now = datetime.now(UTC)
    rss = parse_feed(RSS, "rss_x", "de", now)
    assert [r.title for r in rss] == ["Erste Meldung"] and rss[0].excerpt == "Kurztext"
    assert rss[0].published_at == datetime(2026, 9, 28, 8, 0, tzinfo=UTC)
    assert parse_feed(ATOM, "rss_x", "en", now)[0].url == "https://x.example/a"


def test_parse_feed_rejects_xml_bombs_and_garbage():
    with pytest.raises(SourceError):
        parse_feed(b"<not xml", "rss_x", None, datetime.now(UTC))
    bomb = b'<?xml version="1.0"?><!DOCTYPE l [<!ENTITY a "aaaa"><!ENTITY b "&a;&a;&a;">]><rss><channel/></rss>'
    with pytest.raises(EntitiesForbidden):  # defusedxml lehnt Entity-Deklarationen ab
        parse_feed(bomb, "rss_x", None, datetime.now(UTC))


def test_rss_feeds_disabled_by_default_and_enabled_via_env(monkeypatch):
    adapters = {a.key: a for a in build_rss_adapters()}
    assert set(adapters) == {f"rss_{f.id}" for f in FEEDS} | {"eqs_news"}
    assert not any(a.is_configured() for a in adapters.values())
    assert "RSS_ENABLED_FEEDS" in adapters["rss_cnbc"].disabled_reason
    monkeypatch.setenv("RSS_ENABLED_FEEDS", "cnbc")
    monkeypatch.setenv("EQS_RSS_URL", "https://eqs.example/feed")
    get_settings.cache_clear()
    enabled = {a.key for a in build_rss_adapters() if a.is_configured()}
    assert enabled == {"rss_cnbc", "eqs_news"}


def test_rss_adapter_filters_by_since():
    a = RssFeedAdapter(EQS, enabled=True, url="https://eqs.example/feed",
                       transport=mock(lambda r: httpx.Response(200, content=RSS)), **NOSLEEP)
    assert len(a.fetch_news([], datetime(2026, 9, 28, tzinfo=UTC))) == 1
    assert a.fetch_news([], datetime(2026, 9, 29, tzinfo=UTC)) == []
    assert json.dumps(a.metadata().name)
