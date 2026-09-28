from datetime import UTC, datetime

from app.db import SessionLocal
from app.models import Instrument, PriceBar, Quote, Source
from tests.conftest import login


def _seed():
    now = datetime(2026, 9, 28, 12, 0, tzinfo=UTC)
    with SessionLocal() as db:
        s = Source(key="test", name="Testquelle", kind="price", delay_text="Handelsende", status="online")
        db.add(s)
        db.flush()
        i = Instrument(symbol="AAPL", name="Apple Inc.", isin="US0378331005", exchange="XNAS",
                       currency="USD", source_id=s.id, fetched_at=now)
        db.add(i)
        db.flush()
        db.add(PriceBar(instrument_id=i.id, timeframe="1d", ts_utc=now, source_id=s.id, open=1, high=2,
                        low=0.5, close=1.5, volume=10, fetched_at=now))
        db.add(Quote(instrument_id=i.id, price=1.5, ts_utc=now, source_id=s.id, fetched_at=now))
        db.commit()
        return i.id


def test_search_and_watchlist_roundtrip(client):
    iid = _seed()
    csrf = login(client)
    h = {"X-CSRF-Token": csrf}
    assert [x["symbol"] for x in client.get("/api/instruments/search", params={"q": "US0378"}).json()] == ["AAPL"]
    assert client.post("/api/watchlist", json={"instrument_id": iid}, headers=h).status_code == 201
    wl = client.get("/api/watchlist").json()
    assert wl[0]["quote"]["source"]["name"] == "Testquelle"  # Quelle am Kurs (Grundregel 2)
    assert client.delete(f"/api/watchlist/{iid}", headers=h).status_code == 204
    assert client.get("/api/watchlist").json() == []


def test_bars_carry_source_and_empty_state_is_explicit(client):
    iid = _seed()
    login(client)
    r = client.get(f"/api/instruments/{iid}/bars", params={"timeframe": "1d"}).json()
    assert r["bars"][0]["source"]["key"] == "test" and r["bars"][0]["fetched_at"]
    empty = client.get(f"/api/instruments/{iid}/bars", params={"timeframe": "1m"}).json()
    assert empty["bars"] == [] and empty["empty_reason"]  # kein Platzhalter (Grundregel 6)


def test_meta_has_disclaimer(client):
    m = client.get("/api/meta").json()
    assert m["demo_mode"] is False and "keine Anlageberatung" in m["disclaimer"]
