"""Neues Watchlist-Instrument: sofortige Erstberechnung und neutraler "wird berechnet"-Zustand."""
from datetime import UTC, datetime, timedelta

from app import onboarding
from app.db import SessionLocal
from app.models import Forecast, Instrument, PatternScan, PriceBar, Source, WatchlistItem
from app.price_service import NO_INTRADAY_REASON
from tests.conftest import login


def _instrument(exchange: str, bars: int = 0) -> int:
    now = datetime.now(UTC).replace(hour=0, minute=0, second=0, microsecond=0)
    with SessionLocal() as db:
        s = Source(key="test", name="Testquelle", kind="price", delay_text="Handelsende", status="online")
        db.add(s)
        db.flush()
        i = Instrument(symbol="NVD", name="Nvidia", exchange=exchange, currency="EUR", source_id=s.id, fetched_at=now)
        db.add(i)
        db.flush()
        for n in range(bars):
            px = 100 + n * 0.1
            db.add(PriceBar(instrument_id=i.id, timeframe="1d", ts_utc=now - timedelta(days=bars - n),
                            source_id=s.id, open=px, high=px + 1, low=px - 1, close=px, volume=1000,
                            fetched_at=now))
        db.commit()
        return i.id


def _watch(instrument_id: int, minutes_ago: int = 0) -> None:
    with SessionLocal() as db:
        db.add(WatchlistItem(user_id=1, instrument_id=instrument_id,
                             added_at=datetime.now(UTC) - timedelta(minutes=minutes_ago)))
        db.commit()


def test_adding_to_watchlist_runs_first_calculation_immediately(client):
    iid = _instrument("XETR", bars=300)
    csrf = login(client)
    # Der Hintergrundlauf des TestClient hat keine Adapter; Kerzen liegen schon in der Datenbank.
    assert client.post("/api/watchlist", json={"instrument_id": iid}, headers={"X-CSRF-Token": csrf}).status_code == 201
    with SessionLocal() as db:
        assert db.get(PatternScan, (iid, "1d")) is not None  # Mustererkennung lief sofort
        fc = db.query(Forecast).filter(Forecast.instrument_id == iid).all()
        assert fc and all(f.empty_reason is None for f in fc)  # Prognose wartet nicht auf den 15-Minuten-Job
    body = client.get(f"/api/instruments/{iid}/forecast").json()
    assert body["empty_reason"] is None and body["steps"] and body["pending"] is False


def test_process_skips_intraday_for_xetra(client):
    iid = _instrument("XETR", bars=300)
    onboarding.process_new_instrument(iid)
    with SessionLocal() as db:
        assert db.get(PatternScan, (iid, "1h")) is None


def test_failing_step_does_not_stop_the_rest(client, monkeypatch):
    iid = _instrument("XETR", bars=300)

    def boom(*_a, **_k):
        raise RuntimeError("Quelle nicht erreichbar")

    monkeypatch.setattr(onboarding, "backfill_new_instrument", boom)
    monkeypatch.setattr(onboarding, "scan_instrument", boom)
    onboarding.process_new_instrument(iid)
    with SessionLocal() as db:
        assert db.query(Forecast).filter(Forecast.instrument_id == iid).count() > 0


def test_pending_state_shown_shortly_after_adding(client):
    iid = _instrument("XETR")
    login(client)
    _watch(iid)
    fc = client.get(f"/api/instruments/{iid}/forecast").json()
    assert fc["pending"] is True and "wird gerade berechnet" in fc["empty_reason"] and fc["steps"] == []
    pat = client.get(f"/api/instruments/{iid}/patterns", params={"timeframe": "1d"}).json()
    assert pat["pending"] is True and "wird gerade berechnet" in pat["empty_reason"]
    bars = client.get(f"/api/instruments/{iid}/bars", params={"timeframe": "1d"}).json()
    assert bars["pending"] is True and bars["bars"] == []


def test_pending_ends_after_window_with_plain_reason(client):
    iid = _instrument("XETR")
    login(client)
    _watch(iid, minutes_ago=30)
    fc = client.get(f"/api/instruments/{iid}/forecast").json()
    assert fc["pending"] is False and "noch nicht berechnet" in fc["empty_reason"]
    bars = client.get(f"/api/instruments/{iid}/bars", params={"timeframe": "1d"}).json()
    assert bars["pending"] is False and "noch keine Quelle" in bars["empty_reason"]


def test_not_watched_instrument_is_not_pending(client):
    iid = _instrument("XETR")
    login(client)
    assert client.get(f"/api/instruments/{iid}/forecast").json()["pending"] is False


def test_xetra_intraday_names_reason_not_pending(client):
    iid = _instrument("XETR", bars=5)
    login(client)
    _watch(iid)
    for tf in ("1h", "5m"):
        b = client.get(f"/api/instruments/{iid}/bars", params={"timeframe": tf}).json()
        assert b["empty_reason"] == NO_INTRADAY_REASON and b["pending"] is False
    p = client.get(f"/api/instruments/{iid}/patterns", params={"timeframe": "1h"}).json()
    assert p["empty_reason"] == NO_INTRADAY_REASON and p["pending"] is False
