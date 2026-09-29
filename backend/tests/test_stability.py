"""Phase 5A: Handelszeiten, Aufräumen der Ereignis-Warteschlange, Überspringen unveränderter Berechnungen,
Fehlerisolation der Worker-Jobs."""
from datetime import UTC, datetime, timedelta

from sqlalchemy import select

from app import events as event_bus
from app import price_service as ps
from app.analysis_service import analyze_instrument
from app.db import SessionLocal
from app.market_hours import session_active
from app.models import Event, Instrument, PatternScan, Source
from app.pattern_service import scan_instrument
from tests.test_pattern_api import NOW, seed


def utc(y, m, d, h, mi=0):
    return datetime(y, m, d, h, mi, tzinfo=UTC)


def test_session_windows_per_exchange_and_time_zone():
    assert session_active("XNAS", utc(2026, 9, 29, 14, 0))  # Di 10:00 New York
    assert session_active("XNAS", utc(2026, 9, 29, 8, 30))  # Pre-Market 04:30
    assert not session_active("XNAS", utc(2026, 9, 29, 7, 30))  # 03:30
    assert session_active("XNAS", utc(2026, 9, 30, 0, 20))  # 20:20 = Nachlauf
    assert not session_active("XNAS", utc(2026, 9, 30, 0, 40))
    assert not session_active("XNAS", utc(2026, 9, 26, 15, 0))  # Samstag
    assert session_active("XNYS", utc(2026, 1, 13, 14, 30))  # Winterzeit 09:30
    # XETRA in Berlin-Zeit: 09:00 MESZ = 07:00 UTC, 17:30 MESZ = 15:30 UTC
    assert session_active("XETR", utc(2026, 9, 29, 7, 0))
    assert session_active("XETR", utc(2026, 9, 29, 15, 45))
    assert not session_active("XETR", utc(2026, 9, 29, 5, 30))  # 07:30 MESZ, vor der Vorhandelsphase
    assert not session_active("XETR", utc(2026, 9, 29, 16, 40))
    assert session_active("XETR", utc(2026, 1, 13, 8, 0))  # Winter: 09:00 MEZ
    assert not session_active("XETR", utc(2026, 9, 26, 10, 0))
    assert session_active("XXXX", utc(2026, 9, 26, 10, 0))  # unbekannte Börse: nie stillschweigend pausieren


def test_price_jobs_do_nothing_outside_the_session(client, monkeypatch):
    with SessionLocal() as db:
        src = Source(key="t2", name="T", kind="price")
        db.add(src)
        db.flush()
        db.add(Instrument(symbol="CCC", name="C", exchange="XNAS", currency="USD", source_id=src.id))
        db.commit()
    monkeypatch.setattr(ps, "session_active", lambda exchange, now=None: False)
    monkeypatch.setattr(ps, "SessionLocal", SessionLocal)
    monkeypatch.setattr(ps, "watched_instruments", lambda db: list(db.scalars(select(Instrument))))
    calls = []
    monkeypatch.setattr(ps, "refresh_quote", lambda db, inst: calls.append(inst.symbol))
    monkeypatch.setattr(ps, "backfill_instrument", lambda *a, **k: calls.append("backfill"))
    ps.quote_job()
    ps.intraday_job()
    assert calls == []


def test_jobs_isolate_failing_instrument(client, monkeypatch):
    with SessionLocal() as db:
        src = Source(key="t", name="T", kind="price")
        db.add(src)
        db.flush()
        db.add_all([Instrument(symbol=s, name=s, exchange="XNAS", currency="USD", source_id=src.id)
                    for s in ("AAA", "BBB")])
        db.commit()
    monkeypatch.setattr(ps, "session_active", lambda exchange, now=None: True)
    monkeypatch.setattr(ps, "SessionLocal", SessionLocal)
    seen = []
    def fake(db, inst):
        seen.append(inst.symbol)
        if inst.symbol == "AAA":
            raise RuntimeError("kaputt")
        return True
    monkeypatch.setattr(ps, "refresh_quote", fake)
    monkeypatch.setattr(ps, "watched_instruments", lambda db: list(db.scalars(select(Instrument))))
    ps.quote_job()
    assert seen == ["AAA", "BBB"]


def test_event_queue_is_pruned_but_keeps_recent_events(client):
    with SessionLocal() as db:
        db.add(Event(type="quote", payload={}, created_at=datetime.now(UTC) - timedelta(hours=30)))
        db.add(Event(type="quote", payload={}, created_at=datetime.now(UTC) - timedelta(hours=1)))
        db.commit()
        assert event_bus.prune(db) == 1
        assert len(db.scalars(select(Event)).all()) == 1


def test_pattern_scan_skips_unchanged_bars_but_not_new_ones(client):
    iid, _ = seed()
    with SessionLocal() as db:
        inst = db.get(Instrument, iid)
        first = scan_instrument(db, inst, "1d", now=NOW, skip_unchanged=True)
        assert first["new"] >= 1
        stamp = db.get(PatternScan, (iid, "1d")).computed_at
        again = scan_instrument(db, inst, "1d", now=NOW + timedelta(minutes=5), skip_unchanged=True)
        assert again == {"new": 0, "updated": 0, "removed": 0, "zones": 0}
        assert db.get(PatternScan, (iid, "1d")).computed_at == stamp  # nichts neu berechnet
        # ohne Flag wird immer gerechnet (Tests und manuelle Läufe)
        scan_instrument(db, inst, "1d", now=NOW + timedelta(minutes=5))
        assert db.get(PatternScan, (iid, "1d")).computed_at != stamp
        # neue Kerze: wieder rechnen
        later = NOW + timedelta(days=2)
        scan_instrument(db, inst, "1d", now=later, skip_unchanged=True)
        assert db.get(PatternScan, (iid, "1d")).bar_count > 0


def test_analysis_skips_events_when_unchanged_but_still_links_news(client):
    iid, _ = seed()
    with SessionLocal() as db:
        inst = db.get(Instrument, iid)
        analyze_instrument(db, inst, "1d", now=NOW, skip_unchanged=True)
        again = analyze_instrument(db, inst, "1d", now=NOW, skip_unchanged=True)
        assert again["events"] == 0 and again["moves"] == 0
