from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy import select

from app import price_service as ps
from app.adapters import registry
from app.adapters.base import (
    AdapterMetadata,
    BarRecord,
    Health,
    InstrumentRecord,
    PriceAdapter,
    QuoteRecord,
)
from app.adapters.http import SourceError
from app.alpaca_stream import parse_trades
from app.db import SessionLocal
from app.models import Event, Instrument, PriceBar, Quote, Source, WatchlistItem
from app.sources_sync import sync_sources
from tests.conftest import login

NOW = datetime(2026, 9, 28, 12, 0, tzinfo=UTC)


class Fake(PriceAdapter):
    def __init__(self, key: str, exchanges: tuple[str, ...], bars=(), quote=None, fail=False, search=()):
        self.key, self.supported_exchanges = key, exchanges
        self._bars, self._quote, self._fail, self._search = list(bars), quote, fail, list(search)
        self.bar_calls: list[str] = []

    def metadata(self):
        return AdapterMetadata(key=self.key, name=self.key.title(), kind="price", description="", homepage="h",
                               terms_url="t", update_interval="x", delay_text="Handelsende", requires_key=False)

    def health(self):
        return Health("online", NOW)

    def fetch_bars(self, symbol, exchange, timeframe, start, end):
        self.bar_calls.append(timeframe)
        if self._fail:
            raise SourceError("kaputt")
        return [b for b in self._bars if b.timeframe == timeframe]

    def fetch_quote(self, symbol, exchange):
        if self._fail:
            raise SourceError("kaputt")
        return self._quote

    def search_instruments(self, query):
        return self._search


def bar(key, tf, ts, close, symbol="AAPL", exchange="XNAS"):
    return BarRecord(symbol=symbol, exchange=exchange, timeframe=tf, ts_utc=ts, open=close, high=close + 1,
                     low=close - 1, close=close, volume=10, source_key=key, fetched_at=NOW)


@pytest.fixture()
def db(client):
    registry.clear()
    with SessionLocal() as s:
        yield s
    registry.clear()


def add_instrument(db, adapters, symbol="AAPL", exchange="XNAS", watch=True):
    for a in adapters:
        registry.register(a)
    sync_sources(db)
    inst = ps.upsert_instrument(db, InstrumentRecord(symbol=symbol, name=symbol, exchange=exchange,
                                                     currency="USD", source_key=adapters[0].key, fetched_at=NOW))
    if watch:
        from app.models import User
        uid = db.scalars(select(User.id)).first()
        db.add(WatchlistItem(user_id=uid, instrument_id=inst.id))
        db.commit()
    return inst


def test_store_bars_is_idempotent_and_updates(db):
    inst = add_instrument(db, [Fake("alpaca", ("XNAS",))])
    ts = NOW - timedelta(days=1)
    assert ps.store_bars(db, inst.id, [bar("alpaca", "1d", ts, 10)]) == 1
    ps.store_bars(db, inst.id, [bar("alpaca", "1d", ts, 12)])
    rows = db.scalars(select(PriceBar)).all()
    assert len(rows) == 1 and rows[0].close == 12 and rows[0].source_id and rows[0].fetched_at and not rows[0].is_demo


def test_daily_job_uses_stooq_for_xetra_and_derives_quote(db, monkeypatch):
    monkeypatch.setattr(ps, "session_active", lambda exchange, now=None: True)
    days = [NOW - timedelta(days=2), NOW - timedelta(days=1)]
    stooq = Fake("stooq", ("XNAS", "XNYS", "XETR"), bars=[bar("stooq", "1d", d, c, "SAP", "XETR")
                                                       for d, c in zip(days, (100, 110), strict=True)])
    inst = add_instrument(db, [stooq], "SAP", "XETR")
    monkeypatch.setattr(ps, "SessionLocal", SessionLocal)
    ps.daily_job()
    ps.intraday_job()
    assert stooq.bar_calls == ["1d"]  # XETRA: nie Intraday abgefragt
    q = db.scalars(select(Quote).where(Quote.instrument_id == inst.id)).one()
    assert q.price == 110 and q.change_pct == pytest.approx(10.0) and q.delay_seconds is None
    src = db.get(Source, q.source_id)
    assert src and src.key == "stooq" and src.delay_text == "Handelsende"
    ps.daily_job()  # zweiter Lauf erzeugt keine doppelte Quote
    assert len(db.scalars(select(Quote)).all()) == 1
    assert db.scalars(select(Event).where(Event.type == "quote")).first() is not None


def test_daily_quote_follows_updated_close_of_current_day(db, monkeypatch):
    """Die Tageskerze des laufenden Tages ändert ihren Schlusskurs; die abgeleitete Quote muss folgen."""
    today = NOW.replace(hour=0)
    stooq = Fake("stooq", ("XETR",), bars=[bar("stooq", "1d", today - timedelta(days=1), 100, "SAP", "XETR"),
                                          bar("stooq", "1d", today, 101, "SAP", "XETR")])
    add_instrument(db, [stooq], "SAP", "XETR")
    monkeypatch.setattr(ps, "SessionLocal", SessionLocal)
    ps.daily_job()
    stooq._bars[-1] = bar("stooq", "1d", today, 104, "SAP", "XETR")  # späterer Abruf am selben Tag
    ps.daily_job()
    ps.daily_job()  # unverändert: keine weitere Quote
    prices = [q.price for q in db.scalars(select(Quote).order_by(Quote.id))]
    assert prices == [101, 104]


def test_failing_adapter_falls_through_without_invented_data(db, monkeypatch):
    good = Fake("stooq", ("XNAS",), bars=[bar("stooq", "1d", NOW - timedelta(days=1), 5)])
    bad = Fake("alpaca", ("XNAS",), fail=True)
    inst = add_instrument(db, [bad, good])
    monkeypatch.setattr(ps, "SessionLocal", SessionLocal)
    ps.daily_job()
    assert [b.source_id for b in db.scalars(select(PriceBar)).all()] == [db.scalar(
        select(Source.id).where(Source.key == "stooq"))]
    assert ps.refresh_quote(db, inst) is False  # beide ohne Kurs: nichts gespeichert
    assert db.scalars(select(Quote)).all() == []


def test_quote_job_prefers_first_adapter_and_publishes_event(db, monkeypatch):
    monkeypatch.setattr(ps, "session_active", lambda exchange, now=None: True)
    q = QuoteRecord(symbol="AAPL", exchange="XNAS", price=101.0, ts_utc=NOW, source_key="alpaca", fetched_at=NOW,
                    change_abs=1.0, change_pct=1.0, delay_seconds=0)
    inst = add_instrument(db, [Fake("alpaca", ("XNAS",), quote=q), Fake("stooq", ("XNAS",))])
    monkeypatch.setattr(ps, "SessionLocal", SessionLocal)
    ps.quote_job()
    row = db.scalars(select(Quote)).one()
    assert row.price == 101.0 and row.source_id and row.fetched_at
    ev = db.scalars(select(Event).where(Event.type == "quote")).one()
    assert ev.payload["instrument_id"] == inst.id and ev.payload["source_key"] == "alpaca"


def test_bars_endpoint_dedupes_sources_and_explains_xetra_intraday(client):
    with SessionLocal() as db:
        registry.clear()
        inst = add_instrument(db, [Fake("alpaca", ("XNAS",)), Fake("stooq", ("XNAS", "XETR"))])
        xetra = ps.upsert_instrument(db, InstrumentRecord(symbol="SAP", name="SAP", exchange="XETR", currency="EUR",
                                                          source_key="stooq", fetched_at=NOW))
        day = NOW - timedelta(days=1)
        ps.store_bars(db, inst.id, [bar("alpaca", "1d", day, 10), bar("stooq", "1d", day.replace(hour=0), 99)])
        ids = (inst.id, xetra.id)
    login(client)
    r = client.get(f"/api/instruments/{ids[0]}/bars", params={"timeframe": "1d"}).json()
    assert len(r["bars"]) == 1 and r["bars"][0]["source"]["key"] == "alpaca"
    x = client.get(f"/api/instruments/{ids[1]}/bars", params={"timeframe": "5m"}).json()
    assert x["bars"] == [] and "XETRA" in x["empty_reason"] and "Intraday" in x["empty_reason"]
    registry.clear()


def test_search_adds_provider_results_and_survives_failure(client):
    rec = InstrumentRecord(symbol="SAP", name="SAP SE", exchange="XETR", currency="EUR", source_key="openfigi",
                           fetched_at=NOW, isin="DE0007164600")
    registry.clear()
    with SessionLocal() as db:
        registry.register(Fake("openfigi", ("XETR",), search=[rec]))
        sync_sources(db)
    login(client)
    r = client.get("/api/instruments/search", params={"q": "sap"}).json()
    assert [(x["symbol"], x["exchange"]) for x in r] == [("SAP", "XETR")]
    registry.clear()
    registry.register(Fake("openfigi", ("XETR",), fail=True))

    class Boom(Fake):
        def search_instruments(self, query):
            raise SourceError("down")

    registry.clear()
    registry.register(Boom("openfigi", ("XETR",)))
    r2 = client.get("/api/instruments/search", params={"q": "sap"}).json()
    assert [x["symbol"] for x in r2] == ["SAP"]  # lokale Treffer bleiben trotz Ausfall
    registry.clear()


def test_parse_trades_ignores_other_messages():
    raw = ('[{"T":"success","msg":"authenticated"},{"T":"t","S":"AAPL","p":190.25,"t":"2026-09-28T14:00:01.5Z"},'
           '{"T":"q","S":"AAPL"}]')
    out = parse_trades(raw)
    assert out == [("AAPL", 190.25, datetime(2026, 9, 28, 14, 0, 1, 500000, tzinfo=UTC))]
    assert parse_trades("kein json") == []


def test_no_instrument_row_without_source(db):
    with pytest.raises(SourceError):
        ps.upsert_instrument(db, InstrumentRecord(symbol="X", name="X", exchange="XNAS", currency="USD",
                                                  source_key="gibtsnicht", fetched_at=NOW))
    assert db.scalars(select(Instrument)).all() == []
