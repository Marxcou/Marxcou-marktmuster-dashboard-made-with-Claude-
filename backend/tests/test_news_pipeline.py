from datetime import UTC, datetime, timedelta

import httpx
import pytest
from sqlalchemy import select

from app.adapters import registry
from app.adapters.base import NewsRecord
from app.adapters.finnhub_news import FinnhubNewsAdapter
from app.adapters.gdelt import GdeltAdapter
from app.adapters.http import SourceError
from app.adapters.marketaux import MarketauxAdapter
from app.config import get_settings
from app.db import SessionLocal
from app.models import (
    Event,
    Instrument,
    LlmUsage,
    NewsCluster,
    NewsInstrument,
    NewsItem,
    Sentiment,
    Source,
    User,
    WatchlistItem,
)
from app.news_dedup import normalize_url, similar, title_tokens
from app.news_match import Candidate, Matcher
from app.news_service import ingest, run_adapter
from app.sentiment_claude import ClaudeSentimentSource, verify
from app.sentiment_lexicon import LexiconSentimentSource
from app.sentiment_service import sentiment_pass
from app.sentiment_service import status as sentiment_status
from app.sources_sync import sync_sources
from tests.conftest import login

NOW = datetime.now(UTC)


def rec(source, ext, title, url, minutes=0, symbols=(), excerpt="", language="en", publisher=None):
    return NewsRecord(external_id=ext, url=url, title=title, excerpt=excerpt,
                      published_at=NOW - timedelta(minutes=30) + timedelta(minutes=minutes), fetched_at=NOW,
                      source_key=source, language=language, symbols=tuple(symbols), publisher=publisher)


@pytest.fixture()
def env(monkeypatch, client):
    """Registrierte Quellen, Instrumente (AAPL, SAP) und eine Watchlist des Admins."""
    for k in ("FINNHUB_API_KEY", "MARKETAUX_API_KEY", "ANTHROPIC_API_KEY"):
        monkeypatch.setenv(k, "")
    get_settings.cache_clear()
    registry.clear()
    offline = httpx.MockTransport(lambda r: httpx.Response(200, json={"articles": []}))  # kein echtes Netz in Tests
    fin, mar, gd = FinnhubNewsAdapter(), MarketauxAdapter(), GdeltAdapter(transport=offline, sleep=lambda _s: None)
    for a in (fin, mar, gd, LexiconSentimentSource(), ClaudeSentimentSource()):
        registry.register(a)
    with SessionLocal() as db:
        sync_sources(db)
        sid = db.scalar(select(Source.id).where(Source.key == "finnhub_news"))
        db.add_all([Instrument(symbol="AAPL", name="Apple Inc.", exchange="XNAS", currency="USD", source_id=sid,
                               fetched_at=NOW, isin="US0378331005"),
                    Instrument(symbol="SAP", name="SAP SE", exchange="XETR", currency="EUR", source_id=sid,
                               fetched_at=NOW)])
        db.commit()
        uid = db.scalar(select(User.id))
        for iid in db.scalars(select(Instrument.id)):
            db.add(WatchlistItem(user_id=uid, instrument_id=iid))
        db.commit()
    yield {"finnhub": fin, "marketaux": mar, "gdelt": gd}
    registry.clear()
    get_settings.cache_clear()


def test_normalize_url_drops_tracking_www_and_fragment():
    assert normalize_url("HTTPS://www.Example.com/a/b/?utm_source=x&id=3#frag") == "https://example.com/a/b?id=3"


def test_title_similarity_ignores_publisher_suffix_and_word_order_noise():
    a = title_tokens("Apple beats quarterly estimates as iPhone sales climb - Reuters")
    b = title_tokens("Apple beats quarterly estimates as iPhone sales climb | CNBC")
    c = title_tokens("Apple unveils new headquarters design in Cupertino")
    assert similar(a, b) and not similar(a, c)
    assert not similar(title_tokens("Apple Q3"), title_tokens("Apple Q4"))  # kurze Titel: nur bei Gleichheit


def test_matcher_priorities_and_conservative_matching():
    m = Matcher([Candidate(1, "AAPL", "XNAS", "Apple Inc.", "US0378331005"),
                 Candidate(2, "SAP", "XETR", "SAP SE", None), Candidate(3, "IT", "XNYS", "Gartner Inc.", None)])
    assert m.match(rec("x", "1", "Whatever", "https://a", symbols=["AAPL"])) == {1: "provider_tag"}
    assert m.match(rec("x", "2", "Neu", "https://a", symbols=["SAP.DE"])) == {2: "provider_tag"}
    assert m.match(rec("x", "3", "Wertpapier US0378331005 im Fokus", "https://a")) == {1: "isin"}
    assert m.match(rec("x", "4", "Why $AAPL rallies", "https://a")) == {1: "ticker"}
    assert m.match(rec("x", "5", "Apple hebt Prognose an", "https://a")) == {1: "name"}
    assert m.match(rec("x", "6", "It is what it is", "https://a")) == {}  # zu kurzes Tickersymbol
    assert m.match(rec("x", "7", "Pineapple prices fall", "https://a")) == {}  # nur ganze Wörter
    # ein US-Tag "SAP" ist nicht XETRA-SAP; die Zuordnung kommt hier nur über den Ticker im Titel
    assert m.match(rec("x", "8", "SAP is an ERP giant", "https://a", symbols=["SAP"])) == {2: "ticker"}


def test_ingest_merges_duplicates_across_sources_and_keeps_every_source(env):
    with SessionLocal() as db:
        n1 = ingest(db, [rec("finnhub_news", "f1", "Apple beats quarterly estimates as iPhone sales climb",
                             "https://a.example/x?utm_source=fh", symbols=["AAPL"], publisher="Reuters")],
                    env["finnhub"])
        n2 = ingest(db, [
            rec("marketaux", "m1", "Apple beats quarterly estimates as iPhone sales climb - CNBC",
                "https://cnbc.example/y", minutes=5, symbols=["AAPL"]),
            rec("marketaux", "m2", "Apple beats quarterly estimates as iPhone sales climb",
                "https://a.example/x", minutes=6, symbols=["AAPL"]),
            rec("marketaux", "m3", "SAP wächst im Cloud-Geschäft deutlich", "https://n.example/sap", symbols=["SAP.DE"],
                language="de")], env["marketaux"])
        assert n1["new_clusters"] == 1 and n2["new_clusters"] == 1 and n2["new_items"] == 3
        clusters = db.scalars(select(NewsCluster).order_by(NewsCluster.id)).all()
        assert [c.item_count for c in clusters] == [3, 1]
        items = db.scalars(select(NewsItem).where(NewsItem.cluster_id == clusters[0].id)).all()
        assert {i.source_id for i in items} == {db.scalar(select(Source.id).where(Source.key == k))
                                                 for k in ("finnhub_news", "marketaux")}
        assert all(i.fetched_at and i.url and i.source_id for i in items)  # Grundregel 2
        assert db.scalar(select(NewsInstrument.match_method).where(NewsInstrument.cluster_id == clusters[1].id)) \
            == "provider_tag"
        # erneuter Abruf legt nichts doppelt an
        again = ingest(db, [rec("finnhub_news", "f1", "x", "https://a.example/x", symbols=["AAPL"])], env["finnhub"])
        assert again["already_known"] == 1 and db.scalar(select(NewsItem.id).limit(1)) is not None
        assert len(db.scalars(select(NewsItem)).all()) == 4
        types = [e.type for e in db.scalars(select(Event))]
        assert types.count("news") == 3  # je Ereignis-Cluster das letzte; Cluster 1 zweimal (neu, erweitert)


def test_require_match_discards_unmatched_noise(env):
    with SessionLocal() as db:
        s = ingest(db, [rec("gdelt", "g1", "Something entirely unrelated", "https://a.example/1"),
                        rec("gdelt", "g2", "Apple opens new store", "https://a.example/2")], env["gdelt"])
        assert (s["discarded"], s["new_items"]) == (1, 1)


def test_lexicon_sentiment_stored_with_method_model_and_evidence(env):
    with SessionLocal() as db:
        ingest(db, [rec("finnhub_news", "f1", "Apple beats estimates and raises guidance", "https://a.example/1",
                        symbols=["AAPL"])], env["finnhub"])
        assert sentiment_pass(db) == 1
        s = db.scalars(select(Sentiment)).one()
        assert (s.label, s.method, s.model_name) == ("positiv", "lexicon", "Finanz-Lexikon (regelbasiert)")
        assert s.evidence == ["beats estimates", "raises guidance"] and "Wortliste" in s.rationale
        assert s.source_id == db.scalar(select(Source.id).where(Source.key == "sentiment_lexicon"))


def test_lexicon_output_has_no_recommendation_language(env):
    from app.grundregeln import find_forbidden
    from app.sentiment_lexicon import analyze
    for title in ("Gewinnwarnung belastet Aktie", "Rekordgewinn und Prognose angehoben", "Sitzung findet statt"):
        assert find_forbidden(analyze(title, "", "de").rationale) == []


GOOD = {"label": "positiv", "score": 0.8, "evidence": ["beats estimates"],
        "rationale": "Die Meldung nennt bessere Zahlen."}


def test_claude_verify_rejects_invented_quotes_and_forbidden_language():
    ok = verify(GOOD, "Apple beats estimates", "")
    assert (ok.method, ok.model_name, ok.evidence) == ("claude", "Claude Haiku 4.5", ["beats estimates"])
    for bad in ({**GOOD, "evidence": ["never said this"]}, {**GOOD, "evidence": []},
                {**GOOD, "rationale": "Ein klares Kursziel von 300."}, {**GOOD, "label": "super"},
                {**GOOD, "score": 3}):
        with pytest.raises(SourceError):
            verify(bad, "Apple beats estimates", "")
    assert verify({**GOOD, "label": "neutral", "evidence": []}, "Apple beats estimates", "").label == "neutral"


def claude_source(monkeypatch, handler, budget="10"):
    monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-test")
    monkeypatch.setenv("CLAUDE_MONTHLY_BUDGET_USD", budget)
    get_settings.cache_clear()
    src = ClaudeSentimentSource(transport=httpx.MockTransport(handler), sleep=lambda _s: None)
    registry.register(src)
    return src


def tool_reply(payload, tin=300, tout=80):
    return httpx.Response(200, json={"content": [{"type": "tool_use", "name": "record_sentiment", "input": payload}],
                                     "usage": {"input_tokens": tin, "output_tokens": tout}})


def test_claude_used_when_configured_and_cost_recorded(env, monkeypatch):
    seen = {}

    def handler(req: httpx.Request) -> httpx.Response:
        seen["key"], seen["body"] = req.headers["x-api-key"], req.read().decode()
        return tool_reply(GOOD, 1000, 100)

    claude_source(monkeypatch, handler)
    with SessionLocal() as db:
        ingest(db, [rec("finnhub_news", "f1", "Apple beats estimates", "https://a.example/1", symbols=["AAPL"])],
               env["finnhub"])
        sentiment_pass(db)
        s = db.scalars(select(Sentiment)).one()
        assert (s.method, s.model_version) == ("claude", "claude-haiku-4-5-20251001")
        assert seen["key"] == "sk-test" and "claude-haiku-4-5-20251001" in seen["body"]
        usage = db.get(LlmUsage, datetime.now(UTC).strftime("%Y-%m"))
        assert usage.cost_usd == pytest.approx(1000 * 1e-6 + 100 * 5e-6)
        assert sentiment_status(db)["active_method"] == "claude"


def test_claude_invalid_answer_falls_back_to_lexicon(env, monkeypatch):
    claude_source(monkeypatch, lambda r: tool_reply({**GOOD, "evidence": ["erfundenes Zitat"]}))
    with SessionLocal() as db:
        ingest(db, [rec("finnhub_news", "f1", "Apple beats estimates", "https://a.example/1", symbols=["AAPL"])],
               env["finnhub"])
        sentiment_pass(db)
        assert db.scalars(select(Sentiment)).one().method == "lexicon"


def test_budget_cap_blocks_claude_calls_and_reports_fallback(env, monkeypatch):
    calls = []
    claude_source(monkeypatch, lambda r: calls.append(1) or tool_reply(GOOD), budget="0.01")
    with SessionLocal() as db:
        db.add(LlmUsage(month=datetime.now(UTC).strftime("%Y-%m"), input_tokens=0, output_tokens=0, cost_usd=0.0099))
        db.commit()
        ingest(db, [rec("finnhub_news", "f1", "Apple beats estimates", "https://a.example/1", symbols=["AAPL"])],
               env["finnhub"])
        sentiment_pass(db)
        assert calls == [] and db.scalars(select(Sentiment)).one().method == "lexicon"
        st = sentiment_status(db)
        assert st["active_method"] == "lexicon" and st["fallback_reason"] == "Monatslimit erreicht"
        assert sync_sources(db) is None
        assert db.scalar(select(Source.status).where(Source.key == "claude_sentiment")) == "degraded"


def test_lexicon_results_are_upgraded_once_claude_becomes_available(env, monkeypatch):
    with SessionLocal() as db:
        ingest(db, [rec("finnhub_news", "f1", "Apple beats estimates", "https://a.example/1", symbols=["AAPL"])],
               env["finnhub"])
        sentiment_pass(db)
        assert db.scalars(select(Sentiment)).one().method == "lexicon"
        claude_source(monkeypatch, lambda r: tool_reply(GOOD))
        assert sentiment_pass(db) == 1
        assert db.scalars(select(Sentiment)).one().method == "claude"


def test_source_without_key_is_disabled_with_reason_and_never_fetches(env):
    with SessionLocal() as db:
        assert run_adapter(db, env["finnhub"]) is None
        row = db.scalar(select(Source).where(Source.key == "finnhub_news"))
        assert (row.status, row.last_error) == ("disabled", "API-Schlüssel nicht gesetzt")
        assert db.scalar(select(Source.status).where(Source.key == "claude_sentiment")) == "disabled"


def test_run_adapter_end_to_end_and_error_isolation(env, monkeypatch):
    monkeypatch.setenv("FINNHUB_API_KEY", "k")
    get_settings.cache_clear()
    ok = FinnhubNewsAdapter(transport=httpx.MockTransport(lambda r: httpx.Response(200, json=[{
        "id": 1, "datetime": int(NOW.timestamp()) - 600, "headline": "Apple beats estimates", "summary": "",
        "url": "https://a.example/1", "source": "Reuters"}])), sleep=lambda _s: None)
    down = FinnhubNewsAdapter(transport=httpx.MockTransport(lambda r: httpx.Response(500)), sleep=lambda _s: None)
    with SessionLocal() as db:
        assert run_adapter(db, down) is None  # Fehler bleibt lokal, kein Absturz, nichts gespeichert
        assert db.scalar(select(NewsItem.id)) is None
        assert run_adapter(db, ok)["new_items"] == 1
        assert db.scalars(select(Sentiment)).one().label == "positiv"  # Watchlist: nur AAPL wird abgefragt


def _seed_api(env):
    with SessionLocal() as db:
        ingest(db, [rec("finnhub_news", "f1", "Apple beats estimates and raises guidance", "https://a.example/1",
                        symbols=["AAPL"], publisher="Reuters", excerpt="Kurz")], env["finnhub"])
        ingest(db, [rec("marketaux", "m1", "Apple beats estimates and raises guidance", "https://b.example/2",
                        minutes=3, symbols=["AAPL"]),
                    rec("marketaux", "m2", "SAP meldet Gewinnwarnung", "https://n.example/sap", minutes=10,
                        symbols=["SAP.DE"], language="de"),
                    rec("marketaux", "m3", "Sitzung des Aufsichtsrats", "https://n.example/x", minutes=20,
                        language="de")], env["marketaux"])
        sentiment_pass(db)


def test_api_news_list_filters_and_cluster_shape(client, env):
    csrf = login(client)  # noqa: F841
    _seed_api(env)
    body = client.get("/api/news").json()
    assert body["total"] == 3 and body["empty_reason"] is None and body["next_cursor"] is None
    assert [c["canonical_title"] for c in body["items"]][0] == "Sitzung des Aufsichtsrats"  # neueste zuerst
    apple = next(c for c in body["items"] if c["item_count"] == 2)
    assert {i["source"]["key"] for i in apple["items"]} == {"finnhub_news", "marketaux"}
    assert all(i["url"] and i["fetched_at"] and i["published_at"] and i["source"]["terms_url"] is not None
               for i in apple["items"])
    assert apple["instruments"] == [{"id": apple["instruments"][0]["id"], "symbol": "AAPL",
                                     "match_method": "provider_tag"}]
    s = apple["sentiment"]
    assert (s["label"], s["method"], s["model_name"]) == ("positiv", "lexicon", "Finanz-Lexikon (regelbasiert)")
    assert s["evidence"] and s["rationale"] and s["created_at"]
    assert client.get("/api/news", params={"sentiment": "negativ"}).json()["total"] == 1
    assert client.get("/api/news", params={"source": "finnhub_news"}).json()["total"] == 1
    assert client.get("/api/news", params={"instrument_id": apple["instruments"][0]["id"]}).json()["total"] == 1
    since = (NOW - timedelta(minutes=15)).isoformat()
    assert client.get("/api/news", params={"since": since}).json()["total"] == 1
    assert client.get("/api/news", params={"sentiment": "super"}).status_code == 422


def test_api_pagination_cursor(client, env):
    login(client)
    _seed_api(env)
    p1 = client.get("/api/news", params={"limit": 2}).json()
    assert len(p1["items"]) == 2 and p1["next_cursor"]
    p2 = client.get("/api/news", params={"limit": 2, "cursor": p1["next_cursor"]}).json()
    assert len(p2["items"]) == 1 and p2["next_cursor"] is None
    assert client.get("/api/news", params={"cursor": "kaputt"}).status_code == 400


def test_api_instrument_news_counts_and_status(client, env):
    login(client)
    _seed_api(env)
    aapl = client.get("/api/instruments/search", params={"q": "AAPL"}).json()[0]["id"]
    assert client.get(f"/api/instruments/{aapl}/news").json()["total"] == 1
    assert client.get("/api/instruments/9999/news").status_code == 404
    counts = client.get("/api/news/counts").json()
    assert sorted(counts["counts"].values()) == [1, 1] and counts["empty_reason"] is None
    st = client.get("/api/news/sentiment-status").json()
    assert st["active_method"] == "lexicon" and st["fallback_reason"] == "Kein API-Schlüssel gesetzt"
    assert st["budget_usd"] == 10 and st["claude_configured"] is False


def test_api_requires_login(client):
    for path in ("/api/news", "/api/news/counts", "/api/news/sentiment-status", "/api/instruments/1/news"):
        assert client.get(path).status_code == 401


def test_api_empty_states_explain_why(client, env):
    login(client)
    with SessionLocal() as db:
        db.execute(Source.__table__.update().where(Source.kind == "news").values(status="disabled"))
        db.commit()
    r = client.get("/api/news").json()
    assert r["items"] == [] and "Keine News-Quelle aktiv" in r["empty_reason"]
    with SessionLocal() as db:
        db.execute(Source.__table__.update().where(Source.kind == "news").values(status="online"))
        db.commit()
    assert "Noch keine Meldungen abgerufen" in client.get("/api/news").json()["empty_reason"]
    counts = client.get("/api/news/counts").json()
    assert all(v == 0 for v in counts["counts"].values()) and counts["empty_reason"]


def test_api_sources_lists_news_sources_with_counts_and_reasons(client, env):
    login(client)
    _seed_api(env)
    rows = {r["key"]: r for r in client.get("/api/sources").json()}
    assert rows["marketaux"]["item_count_24h"] == 3 and rows["finnhub_news"]["item_count_24h"] == 1
    assert rows["sentiment_lexicon"]["item_count_24h"] is None and rows["sentiment_lexicon"]["kind"] == "reference"
    assert rows["claude_sentiment"]["kind"] == "llm" and rows["claude_sentiment"]["status"] == "disabled"
    assert rows["claude_sentiment"]["last_error"].startswith("ANTHROPIC_API_KEY")
    assert rows["gdelt"]["terms_url"] and rows["gdelt"]["update_interval"] and rows["gdelt"]["delay_text"]
