"""Ende-zu-Ende: Kerzen + Meldungen in der DB -> Analyse -> Endpunkte, Ereignisse, Verknüpfung."""
from datetime import UTC, datetime, timedelta

import numpy as np
import pytest
from sqlalchemy import select

from app.analysis_service import analyze_instrument
from app.db import SessionLocal
from app.models import Event, IndicatorEvent, Instrument, NewsCluster, NewsInstrument, NewsItem, PriceBar, Source
from tests.conftest import login

NOW = datetime(2026, 9, 29, 12, 0, tzinfo=UTC)
N = 300


def seed(with_volume=True):
    rng = np.random.default_rng(11)
    ret = rng.normal(0, 0.005, N)
    ret[285] = -0.08  # auffällige Bewegung an Kerze 285
    close = 100 * np.cumprod(1 + ret)
    days = [datetime(2026, 9, 28, tzinfo=UTC) - timedelta(days=N - 1 - i) for i in range(N)]  # letzte = 28.09.
    with SessionLocal() as db:
        src = Source(key="stooq", name="Stooq", kind="price", homepage="https://stooq.com",
                     terms_url="https://stooq.com/t", delay_text="Handelsende")
        news_src = Source(key="finnhub_news", name="Finnhub", kind="news", homepage="https://finnhub.io")
        db.add_all([src, news_src])
        db.flush()
        inst = Instrument(symbol="AAPL", name="Apple Inc.", exchange="XNAS", currency="USD", source_id=src.id)
        db.add(inst)
        db.flush()
        for d, c in zip(days, close, strict=True):
            db.add(PriceBar(instrument_id=inst.id, timeframe="1d", ts_utc=d, source_id=src.id, open=c, high=c * 1.004,
                            low=c * 0.996, close=c, volume=float(rng.integers(900, 1100)) if with_volume else None,
                            fetched_at=NOW))
        # eine laufende (nicht abgeschlossene) Kerze von "heute": darf nie ausgewertet werden
        db.add(PriceBar(instrument_id=inst.id, timeframe="1d", ts_utc=datetime(2026, 9, 29, tzinfo=UTC),
                        source_id=src.id, open=1, high=1000, low=1, close=1, volume=1e9, fetched_at=NOW))
        # Meldung 5 Stunden vor Beginn der Bewegungs-Kerze, eine weit davon entfernt
        move_start = days[285]
        near = NewsCluster(canonical_title="Apple meldet Lieferprobleme",
                           first_published_at=move_start - timedelta(hours=5), last_published_at=move_start,
                           item_count=1)
        far = NewsCluster(canonical_title="Ältere Meldung", first_published_at=move_start - timedelta(days=9),
                          last_published_at=move_start - timedelta(days=9), item_count=1)
        db.add_all([near, far])
        db.flush()
        for cl in (near, far):
            db.add(NewsItem(source_id=news_src.id, external_id=str(cl.id), url=f"https://x/{cl.id}",
                            url_normalized=f"x/{cl.id}", title=cl.canonical_title, published_at=cl.first_published_at,
                            fetched_at=NOW, cluster_id=cl.id))
            db.add(NewsInstrument(cluster_id=cl.id, instrument_id=inst.id, match_method="provider_tag",
                                  source_id=news_src.id))
        db.commit()
        return inst.id


def test_pipeline_and_endpoints(client):
    iid = seed()
    with SessionLocal() as db:
        inst = db.get(Instrument, iid)
        stats = analyze_instrument(db, inst, "1d", now=NOW)
        assert stats["moves"] >= 1 and stats["links"] == 1
        again = analyze_instrument(db, inst, "1d", now=NOW)
        assert again == {"events": 0, "moves": 0, "links": 0}  # idempotent
        # laufende Kerze wurde nicht ausgewertet
        today = datetime(2026, 9, 29, tzinfo=UTC)
        assert not db.scalars(select(IndicatorEvent).where(IndicatorEvent.ts_utc >= today)).all()
        published = db.scalars(select(Event).where(Event.type == "detection")).all()
        assert all(e.payload["category"] == "indicator_event" for e in published)
    login(client)

    r = client.get(f"/api/instruments/{iid}/move-links?timeframe=1d")
    assert r.status_code == 200
    body = r.json()
    assert body["note"] == "Zeitlich zusammenfallend, keine Aussage über Ursache."
    big = next(m for m in body["moves"] if m["return_pct"] < -7)
    assert big["return_z"] < -3 and "return_z" in big["reasons"]
    assert [n["canonical_title"] for n in big["news"]] == ["Apple meldet Lieferprobleme"]  # die ferne Meldung nicht
    assert big["news"][0]["time_offset_minutes"] == -300
    assert big["news"][0]["sources"][0]["key"] == "finnhub_news"
    assert big["sources"][0]["key"] == "stooq" and big["bars_fetched_at"]

    r = client.get(f"/api/instruments/{iid}/indicator-events?timeframe=1d&limit=200")
    assert r.status_code == 200
    events = r.json()["events"]
    assert events and r.json()["empty_reason"] is None
    for e in events:
        assert e["criteria"] and e["params"] and e["algo_version"] and e["sources"][0]["key"] == "stooq"
        assert e["historical_stats"] is None and e["historical_stats_reason"]
        assert e["direction"] in ("up", "down", None)
    assert [e["ts"] for e in events] == sorted((e["ts"] for e in events), reverse=True)
    # Paging über cursor
    first = client.get(f"/api/instruments/{iid}/indicator-events?timeframe=1d&limit=1").json()
    assert first["next_cursor"] and len(first["events"]) == 1
    cur = first["next_cursor"]
    second = client.get(f"/api/instruments/{iid}/indicator-events?timeframe=1d&limit=1&cursor={cur}").json()
    assert second["events"][0]["id"] != first["events"][0]["id"]
    only = client.get(f"/api/instruments/{iid}/indicator-events?timeframe=1d&type=volume_spike").json()
    assert {e["type"] for e in only["events"]} <= {"volume_spike"}
    assert client.get(f"/api/instruments/{iid}/indicator-events?type=kaufen").status_code == 422


def test_indicator_series_aligned_with_bars(client):
    iid = seed()
    login(client)
    r = client.get(f"/api/instruments/{iid}/indicators?timeframe=1d&limit=100&sma=20,50&ema=12&rsi=14"
                   "&macd=12,26,9&bb=20,2")
    assert r.status_code == 200, r.text
    b = r.json()
    bars = client.get(f"/api/instruments/{iid}/bars?timeframe=1d&limit=100").json()["bars"]
    assert b["timestamps"] == [x["ts_utc"] for x in bars] and len(b["timestamps"]) == 100
    keys = {i["key"]: i for i in b["indicators"]}
    assert list(keys) == ["sma_20", "sma_50", "ema_12", "rsi_14", "macd_12_26_9", "bb_20_2"]
    assert all(len(v) == 100 for i in b["indicators"] for v in i["lines"].values())
    # Vorlauf: trotz limit=100 sind alle Werte bereits gültig (nicht null)
    assert None not in keys["sma_50"]["lines"]["value"] and None not in keys["rsi_14"]["lines"]["value"]
    assert set(keys["macd_12_26_9"]["lines"]) == {"macd", "signal", "histogram"}
    assert keys["rsi_14"]["panel"] == "own" and keys["sma_20"]["panel"] == "price" and keys["sma_20"]["formula"]
    sma20 = keys["sma_20"]["lines"]["value"][-1]
    assert sma20 == pytest.approx(np.mean([x["close"] for x in bars[-20:]]), abs=1e-4)
    assert b["sources"][0]["key"] == "stooq" and b["bars_fetched_at"] and b["algo_version"]
    assert client.get(f"/api/instruments/{iid}/indicators?sma=1").status_code == 422
    assert client.get(f"/api/instruments/{iid}/indicators?macd=26,12,9").status_code == 422
    only = client.get(f"/api/instruments/{iid}/indicators?rsi=14&limit=5").json()
    assert [i["key"] for i in only["indicators"]] == ["rsi_14"]


def test_empty_states_explain_reason(client):
    with SessionLocal() as db:
        s = Source(key="stooq", name="Stooq", kind="price")
        db.add(s)
        db.flush()
        inst = Instrument(symbol="SAP", name="SAP SE", exchange="XETR", currency="EUR", source_id=s.id)
        db.add(inst)
        db.commit()
        iid = inst.id
    login(client)
    for path in ("indicators?rsi=14", "indicator-events", "move-links"):
        body = client.get(f"/api/instruments/{iid}/{path}").json()
        assert body["empty_reason"], path
    assert client.get("/api/instruments/999/indicators").status_code == 404


def test_no_volume_from_source_means_no_volume_events(client):
    iid = seed(with_volume=False)
    with SessionLocal() as db:
        analyze_instrument(db, db.get(Instrument, iid), "1d", now=NOW)
        assert not db.scalars(select(IndicatorEvent).where(IndicatorEvent.type == "volume_spike")).all()
