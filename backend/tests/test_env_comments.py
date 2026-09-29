"""Kommentare in .env: Docker Compose übergibt bei "KEY=   # Text" den Kommentar als Wert."""
import logging
from pathlib import Path

import pytest

from app.adapters.ir_feeds import IrFeedsAdapter, parse_ir_feeds_checked
from app.adapters.rss import EQS, RssFeedAdapter
from app.config import Settings, get_settings
from app.sources_sync import sync_sources

ENV_EXAMPLE = Path(__file__).resolve().parents[2] / ".env.example"


@pytest.fixture(autouse=True)
def clear_settings():
    get_settings.cache_clear()
    yield
    get_settings.cache_clear()


def test_env_example_has_no_inline_comments():
    for n, line in enumerate(ENV_EXAMPLE.read_text(encoding="utf-8").splitlines(), 1):
        stripped = line.strip()
        if not stripped or stripped.startswith("#"):
            continue
        value = stripped.partition("=")[2]
        assert "#" not in value, f".env.example Zeile {n}: Kommentar hinter dem Wert"


def test_comment_values_count_as_unset(monkeypatch, caplog):
    monkeypatch.setenv("OPENFIGI_API_KEY", "# optional")
    monkeypatch.setenv("ALPHAVANTAGE_API_KEY", "  # optional")
    monkeypatch.setenv("CLAUDE_USE_BATCH", "# Stimmung per Batch")
    monkeypatch.setenv("FINNHUB_API_KEY", "real-key")
    with caplog.at_level(logging.WARNING, logger="app.config"):
        s = Settings(_env_file=None)
    assert s.openfigi_api_key == "" and s.alphavantage_api_key == ""
    assert s.claude_use_batch is True  # Standardwert statt Validierungsfehler
    assert s.finnhub_api_key == "real-key"
    assert "OPENFIGI_API_KEY" in caplog.text and "optional" not in caplog.text  # nur Name, nie der Wert


def test_ir_feeds_comment_text_is_disabled_with_german_reason(monkeypatch):
    monkeypatch.setenv("IR_FEEDS", "Investor-Relations-Feeds: AAPL|https://.../feed.xml,SAP.DE|https://.../rss")
    a = IrFeedsAdapter()
    assert not a.is_configured()
    assert "ungültig" in a.disabled_reason and "SYMBOL|https://" in a.disabled_reason


def test_ir_feeds_partly_invalid_keeps_valid_entries():
    feeds, invalid = parse_ir_feeds_checked("AAPL|https://ir.example/a.xml,SAP|https://.../x,ÄÖ|https://ü.example/x")
    assert feeds == {"AAPL": "https://ir.example/a.xml"} and invalid == 2


def test_eqs_invalid_url_is_disabled_with_german_reason():
    a = RssFeedAdapter(EQS, enabled=True, url="# Feed-Adresse der EQS-News, Nutzungsbedingungen prüfen")
    assert not a.is_configured() and "EQS_RSS_URL ungültig" in a.disabled_reason
    ok = RssFeedAdapter(EQS, enabled=True, url="https://eqs.example/feed")
    assert ok.is_configured()


def test_sources_page_shows_misconfiguration_not_exception_name(monkeypatch, client):
    from sqlalchemy import select

    from app.adapters import registry
    from app.db import SessionLocal
    from app.models import Source

    monkeypatch.setenv("IR_FEEDS", "AAPL|https://.../feed.xml")
    monkeypatch.setenv("EQS_RSS_URL", "kein-link")
    get_settings.cache_clear()
    registry.clear()
    registry.load_builtin_adapters()
    with SessionLocal() as db:
        sync_sources(db)
        rows = {r.key: r for r in db.scalars(select(Source))}
    registry.clear()
    assert rows["ir_feeds"].status == "disabled" and "IR_FEEDS ungültig" in rows["ir_feeds"].last_error
    assert rows["eqs_news"].status == "disabled" and "EQS_RSS_URL ungültig" in rows["eqs_news"].last_error
    assert "Error" not in rows["ir_feeds"].last_error and "Protocol" not in rows["eqs_news"].last_error
