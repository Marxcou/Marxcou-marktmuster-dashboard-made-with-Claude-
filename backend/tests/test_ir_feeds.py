from datetime import UTC, datetime

import httpx
import pytest

from app.adapters.base import NewsTarget
from app.adapters.http import SourceError
from app.adapters.ir_feeds import IrFeedsAdapter, parse_ir_feeds
from app.config import get_settings

SINCE = datetime(2026, 9, 27, tzinfo=UTC)
NOSLEEP = {"sleep": lambda _s: None}
RSS = b"""<?xml version="1.0"?><rss version="2.0"><channel>
<item><title>Q3-Zahlen</title><link>https://ir.example/q3</link><guid>q3</guid>
<description>&lt;p&gt;Kurztext&lt;/p&gt;</description><pubDate>Mon, 28 Sep 2026 10:00:00 +0200</pubDate></item>
<item><title>Alt</title><link>https://ir.example/old</link><pubDate>Mon, 01 Jun 2026 10:00:00 +0200</pubDate></item>
</channel></rss>"""


@pytest.fixture(autouse=True)
def clear_settings():
    get_settings.cache_clear()
    yield
    get_settings.cache_clear()


def test_parse_ir_feeds_keeps_only_valid_https_entries():
    raw = "aapl|https://ir.example/a.xml, SAP.DE|https://ir.example/s , X|http://insecure.example, |https://y.example,Z"
    assert parse_ir_feeds(raw) == {"AAPL": "https://ir.example/a.xml", "SAP.DE": "https://ir.example/s"}


def test_disabled_by_default_and_enabled_via_env(monkeypatch):
    a = IrFeedsAdapter(**NOSLEEP)
    assert not a.is_configured() and "IR_FEEDS" in a.disabled_reason
    monkeypatch.setenv("IR_FEEDS", "AAPL|https://ir.example/a.xml")
    get_settings.cache_clear()
    assert IrFeedsAdapter(**NOSLEEP).is_configured()


def test_fetch_maps_records_with_source_publisher_and_symbol():
    def handler(req: httpx.Request) -> httpx.Response:
        return httpx.Response(200, content=RSS)

    a = IrFeedsAdapter({"AAPL": "https://ir.example/a.xml", "SAP.DE": "https://ir.example/s"},
                       transport=httpx.MockTransport(handler), **NOSLEEP)
    recs = a.fetch_news_for([NewsTarget("AAPL", "XNAS", "Apple Inc.")], SINCE)
    assert len(recs) == 1  # nur Watchlist-Aktie mit Feed, alter Eintrag fällt weg
    r = recs[0]
    assert (r.title, r.excerpt, r.url, r.source_key) == ("Q3-Zahlen", "Kurztext", "https://ir.example/q3", "ir_feeds")
    assert r.symbols == ("AAPL",) and r.publisher == "Investor Relations Apple Inc."
    assert r.published_at == datetime(2026, 9, 28, 8, 0, tzinfo=UTC) and r.fetched_at.tzinfo is not None


def test_one_broken_feed_does_not_block_others_but_all_broken_is_an_error():
    def handler(req: httpx.Request) -> httpx.Response:
        return httpx.Response(200, content=RSS) if "good" in str(req.url) else httpx.Response(200, content=b"<x")

    feeds = {"AAPL": "https://good.example/a", "SAP.DE": "https://bad.example/s"}
    a = IrFeedsAdapter(feeds, transport=httpx.MockTransport(handler), **NOSLEEP)
    targets = [NewsTarget("AAPL", "XNAS", "Apple"), NewsTarget("SAP.DE", "XETR", "SAP")]
    assert len(a.fetch_news_for(targets, SINCE)) == 1
    with pytest.raises(SourceError):
        a.fetch_news_for(targets[1:], SINCE)
