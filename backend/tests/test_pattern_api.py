"""Ende-zu-Ende: Kerzen in der DB -> Mustererkennung (Worker) -> Endpunkte, Ereignisse, Backtest-Verweis."""
from datetime import UTC, datetime, timedelta

from sqlalchemy import select

from app.db import SessionLocal
from app.models import BacktestRun, Event, Instrument, PatternDetection, PriceBar, Source, WatchlistItem
from app.pattern_service import scan_instrument
from tests.conftest import login
from tests.synthetic import path

NOW = datetime(2026, 9, 29, 12, 0, tzinfo=UTC)
# Doppelboden 30..60, Nackenlinie bei 110,22, bestätigt an Kerze 72; danach Seitwärtsphase bis Kerze 150
ANCHORS = [(0, 120), (30, 100), (45, 110), (60, 100.3), (80, 118), (100, 125), (150, 124)]


def seed(anchors=ANCHORS, symbol="SAP", exchange="XETR"):
    bars = path(anchors)
    n = len(bars)
    days = [datetime(2026, 9, 28, tzinfo=UTC) - timedelta(days=n - 1 - i) for i in range(n)]
    with SessionLocal() as db:
        src = db.scalar(select(Source).where(Source.key == "stooq"))
        if src is None:
            src = Source(key="stooq", name="Stooq", kind="price", homepage="https://stooq.com",
                         terms_url="https://stooq.com/t", delay_text="Handelsende")
            db.add(src)
            db.flush()
        inst = Instrument(symbol=symbol, name=f"{symbol} AG", exchange=exchange, currency="EUR", source_id=src.id)
        db.add(inst)
        db.flush()
        for i, d in enumerate(days):
            db.add(PriceBar(instrument_id=inst.id, timeframe="1d", ts_utc=d, source_id=src.id,
                            open=float(bars.open[i]), high=float(bars.high[i]), low=float(bars.low[i]),
                            close=float(bars.close[i]), volume=1000.0, fetched_at=NOW))
        # laufende Kerze von heute: darf nie ausgewertet werden
        db.add(PriceBar(instrument_id=inst.id, timeframe="1d", ts_utc=datetime(2026, 9, 29, tzinfo=UTC),
                        source_id=src.id, open=1, high=1000, low=1, close=1, volume=1e9, fetched_at=NOW))
        db.commit()
        return inst.id, days


def run_scan(iid, now=NOW):
    with SessionLocal() as db:
        return scan_instrument(db, db.get(Instrument, iid), "1d", now=now)


def test_scan_and_patterns_endpoint(client):
    iid, days = seed()
    login(client)
    r = client.get(f"/api/instruments/{iid}/patterns")
    assert r.status_code == 200
    assert r.json()["empty_reason"] == "Die Mustererkennung wurde für dieses Instrument noch nicht ausgeführt."

    stats = run_scan(iid)
    assert stats["new"] >= 1
    body = client.get(f"/api/instruments/{iid}/patterns").json()
    assert body["empty_reason"] is None and body["computed_at"]
    assert body["data_basis"]["bar_count"] == len(days)  # ohne die laufende Kerze
    assert body["data_basis"]["sources"][0]["key"] == "stooq"
    det = next(d for d in body["detections"] if d["pattern_type"] == "doppelboden")
    assert det["status"] == "bestaetigt" and det["status_label"] == "Bestätigt"
    assert det["start_ts"] == days[30].isoformat() and det["end_ts"] == days[60].isoformat()
    assert det["confirmed_at"] == days[72].isoformat()
    assert [k["role"] for k in det["key_points"]] == ["tief_1", "zwischenhoch", "tief_2"]
    assert det["lines"][0]["role"] == "nackenlinie" and det["lines"][0]["extend_right"] is True
    assert det["confidence"]["method"] and det["confidence"]["breakdown"]
    assert {s["kind"] for s in det["scenarios"]} == {"bestaetigung", "scheitern"}
    assert all(s["historical"] is None for s in det["scenarios"])
    # Grundregel 3/6: ohne Backtest keine Zahl, sondern ausdrücklich "nicht berechnet"
    bt = det["backtest"]
    assert bt["status"] == "nicht_berechnet" and bt["hit_rate"] is None and bt["sample_size"] is None
    assert "noch nicht berechnet" in bt["note"]
    assert det["data_basis"]["sources"][0]["name"] == "Stooq"
    assert det["params"]["doppel.max_extrem_abweichung_pct"] == 1.5

    single = client.get(f"/api/patterns/{det['id']}").json()
    assert single["id"] == det["id"] and single["explanation"] == det["explanation"]
    assert client.get("/api/patterns/999999").status_code == 404


def test_backtest_run_is_attached(client):
    iid, _ = seed()
    run_scan(iid)
    with SessionLocal() as db:
        db.add(BacktestRun(kind="pattern", subject="doppelboden", timeframe="1d", algo_version="1.0.0",
                           params={"horizon_bars": 20, "min_move_pct": 3.0}, universe="DAX 40", sample_size=214,
                           hit_rate=0.62, ci_low=0.55, ci_high=0.68, base_rate=0.51, date_range="2014–2026",
                           metrics={"verdict_text": "Trefferquote über der Basisrate",
                                    "survivorship_note": "Heutige Indexmitglieder",
                                    "scenarios": {"bestaetigung": {"share": 0.62, "sample_size": 214, "text": "…"}}}))
        db.commit()
    login(client)
    det = next(d for d in client.get(f"/api/instruments/{iid}/patterns").json()["detections"]
               if d["pattern_type"] == "doppelboden")
    bt = det["backtest"]
    assert bt["status"] == "berechnet" and bt["sample_size"] == 214 and bt["hit_rate"] == 0.62
    assert bt["not_better_than_random"] is False and bt["horizon_bars"] == 20
    assert det["scenarios"][0]["historical"]["sample_size"] == 214
    assert det["scenarios"][1]["historical"] is None


def test_include_invalid_and_start_filter(client):
    iid, days = seed([(0, 120), (30, 100), (45, 110), (60, 100.3), (70, 104), (85, 90), (100, 88)])
    run_scan(iid)
    login(client)
    default = client.get(f"/api/instruments/{iid}/patterns").json()["detections"]
    assert all(d["status"] != "ungueltig" for d in default)
    everything = client.get(f"/api/instruments/{iid}/patterns?include_invalid=true").json()["detections"]
    assert any(d["pattern_type"] == "doppelboden" and d["status"] == "ungueltig" for d in everything)
    late = client.get(f"/api/instruments/{iid}/patterns", params={"include_invalid": "true",
                                                                   "start": days[90].isoformat()}).json()
    assert all(d["end_ts"] >= days[90].isoformat() for d in late["detections"])


def test_rescan_is_idempotent_and_publishes_only_fresh_changes(client):
    iid, _ = seed()
    run_scan(iid)
    with SessionLocal() as db:
        ids = sorted(db.scalars(select(PatternDetection.id).where(PatternDetection.instrument_id == iid)))
        events = [e for e in db.scalars(select(Event)) if e.payload.get("category") == "pattern"]
    # Doppelboden wurde vor vielen Kerzen bestätigt: kein Live-Ereignis (kein Sturm beim ersten Lauf)
    assert events == []
    stats = run_scan(iid)
    assert stats["new"] == 0 and stats["removed"] == 0
    with SessionLocal() as db:
        assert sorted(db.scalars(select(PatternDetection.id).where(PatternDetection.instrument_id == iid))) == ids


def test_fresh_status_change_publishes_event(client):
    # Serie endet zwei Kerzen nach dem Überschreiten der Nackenlinie
    iid, days = seed([(0, 120), (30, 100), (45, 110), (60, 100.3), (72, 110.9), (73, 111.5)])
    run_scan(iid)
    with SessionLocal() as db:
        events = [e.payload for e in db.scalars(select(Event)) if e.payload.get("category") == "pattern"]
    assert any(e["pattern_type"] == "doppelboden" and e["status"] == "bestaetigt" and e["previous_status"] is None
               for e in events)


def test_counts_and_catalog(client):
    iid, _ = seed([(0, 120), (30, 100), (45, 110), (60, 100.3), (70, 106)])  # Doppelboden in Bildung
    login(client)
    assert client.get("/api/patterns/counts").json()["empty_reason"] == "Die Watchlist ist leer."
    with SessionLocal() as db:
        db.add(WatchlistItem(user_id=1, instrument_id=iid))
        db.commit()
    assert client.get("/api/patterns/counts").json()["counts"] == {}
    run_scan(iid)
    counts = client.get("/api/patterns/counts").json()
    assert counts["counts"][str(iid)] >= 1 and counts["empty_reason"] is None

    cat = client.get("/api/patterns/catalog").json()
    types = {e["pattern_type"] for e in cat["items"]}
    assert len(types) == 13 and {"doppelboden", "kopf_schulter", "wimpel_abwaerts", "keil_fallend"} <= types
    for e in cat["items"]:
        assert abs(sum(c["weight"] for c in e["criteria"]) - 1) < 1e-9
        assert e["params"] and all(p["description"] for p in e["params"])


def test_empty_reasons(client):
    login(client)
    iid, _ = seed([(0, 100), (30, 110)], symbol="TINY")
    run_scan(iid)
    body = client.get(f"/api/instruments/{iid}/patterns").json()
    assert body["detections"] == [] and "Zu wenige Kerzen" in body["empty_reason"]
    r = client.get(f"/api/instruments/{iid}/patterns?timeframe=1h").json()
    assert "Keine Intraday-Daten für XETRA" in r["empty_reason"]
    assert client.get(f"/api/instruments/{iid}/patterns?timeframe=5m").status_code == 422

    flat, _ = seed([(0, 100), (200, 160)], symbol="TREND", exchange="XNAS")
    run_scan(flat)
    body = client.get(f"/api/instruments/{flat}/patterns").json()
    assert body["detections"] == [] and body["empty_reason"] == "Aktuell erfüllt kein Muster alle Kriterien."


def test_requires_login(client):
    assert client.get("/api/patterns/catalog").status_code == 401
