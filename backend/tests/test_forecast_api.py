"""Ende-zu-Ende: Kerzen in der DB -> Prognose-Job -> /forecast. Nur Korridor, Backtest-Werte nur aus einem Lauf."""
from datetime import UTC, datetime, timedelta

import numpy as np
import pytest
from sqlalchemy import select

from app.db import SessionLocal
from app.forecast_service import forecast_instrument
from app.models import BacktestRun, Instrument, PatternDetection, PriceBar, Source
from tests.conftest import login

NOW = datetime(2026, 9, 29, 12, 0, tzinfo=UTC)
LAST_DAY = datetime(2026, 9, 28, tzinfo=UTC)


def seed(n=400, symbol="SAP", demo=False):
    rng = np.random.default_rng(4)
    close = 100 * np.exp(np.cumsum(rng.normal(0, 0.015, n)))
    days = [LAST_DAY - timedelta(days=n - 1 - i) for i in range(n)]
    with SessionLocal() as db:
        src = db.scalar(select(Source).where(Source.key == "stooq"))
        if src is None:
            src = Source(key="stooq", name="Stooq", kind="price", homepage="https://stooq.com",
                         terms_url="https://stooq.com/t", delay_text="Handelsende")
            db.add(src)
            db.flush()
        inst = Instrument(symbol=symbol, name=f"{symbol} AG", exchange="XETR", currency="EUR", source_id=src.id)
        db.add(inst)
        db.flush()
        for d, c in zip(days, close, strict=True):
            db.add(PriceBar(instrument_id=inst.id, timeframe="1d", ts_utc=d, source_id=src.id, open=float(c),
                            high=float(c) * 1.01, low=float(c) * 0.99, close=float(c), volume=1000.0,
                            fetched_at=NOW, is_demo=demo))
        # laufende Kerze von heute: darf nie eingehen
        db.add(PriceBar(instrument_id=inst.id, timeframe="1d", ts_utc=datetime(2026, 9, 29, tzinfo=UTC),
                        source_id=src.id, open=1, high=1000, low=1, close=1, volume=1e9, fetched_at=NOW))
        db.commit()
        return inst.id, float(close[-1])


def run(iid, now=NOW):
    with SessionLocal() as db:
        return forecast_instrument(db, db.get(Instrument, iid), now=now)


def add_detection(iid, upper, lower):
    with SessionLocal() as db:
        src = db.scalar(select(Source).where(Source.key == "stooq"))
        d = PatternDetection(
            instrument_id=iid, timeframe="1d", pattern_type="doppelboden", fingerprint="fp1", name="Doppelboden",
            direction="aufwärts", start_ts=LAST_DAY - timedelta(days=30), end_ts=LAST_DAY - timedelta(days=5),
            formed_ts=LAST_DAY - timedelta(days=3), status="in_bildung", key_points=[], lines=[], criteria=[],
            confidence=0.7, confidence_breakdown=[], confirmation_level=upper, invalidation_level=lower,
            scenarios=[{"kind": "bestaetigung", "title": "Bestätigung", "trigger_level": upper, "trigger_rule": "…",
                        "description": "…"},
                       {"kind": "scheitern", "title": "Scheitern", "trigger_level": lower, "trigger_rule": "…",
                        "description": "…"}],
            explanation="…", params={}, params_hash="x", algo_version="1.0.0", source_id=src.id, source_ids=[src.id],
            fetched_at=NOW)
        db.add(d)
        db.commit()
        return d.id


def test_forecast_endpoint(client):
    iid, last = seed()
    login(client)
    body = client.get(f"/api/instruments/{iid}/forecast").json()
    assert body["empty_reason"] == "Die Prognose wurde für dieses Instrument noch nicht berechnet."
    assert body["steps"] == [] and body["backtest"]["status"] == "nicht_berechnet"
    assert body["median_line"] is None and body["example_paths"] == []
    assert body["method"]["key"] == "monte_carlo_block_bootstrap" and body["method"]["description"]

    stats = run(iid)
    assert stats == {"forecasts": 2, "backtests": 2}
    body = client.get(f"/api/instruments/{iid}/forecast").json()
    assert body["empty_reason"] is None and body["currency"] == "EUR"
    assert body["based_on_until"] == LAST_DAY.isoformat() and body["last_close"] == last  # ohne laufende Kerze
    assert body["data_basis"]["bar_count"] == 400 and body["data_basis"]["sources"][0]["key"] == "stooq"
    steps = body["steps"]
    assert len(steps) == 20 and steps[0]["ts"] == "2026-09-29T00:00:00+00:00"
    for s in steps:
        q = s["quantiles"]
        assert list(q) == ["2.5", "10", "25", "50", "75", "90", "97.5"]
        assert q["2.5"] <= q["10"] <= q["25"] <= q["50"] <= q["75"] <= q["90"] <= q["97.5"]
    assert [b["level"] for b in body["bands"]] == [0.5, 0.8, 0.95]
    bt = body["backtest"]
    assert bt["status"] == "berechnet" and bt["sample_size"] > 0 and bt["horizon_bars"] == 20
    assert [c["nominal"] for c in bt["coverage"]] == [0.5, 0.8, 0.95]
    assert {m["key"] for m in bt["metrics"]} == {"median_abs_error", "pinball_loss"}
    assert bt["verdict_text"] and "Kurs bleibt gleich" in bt["verdict_text"]
    assert bt["better_than_naive"] is None  # 400 Kerzen ergeben weniger als 30 Prüfzeitpunkte
    assert [h["horizon_bars"] for h in bt["by_horizon"]] == [5, 10, 20]
    assert bt["universe"] == "SAP (XETR), eigene Historie" and bt["is_demo"] is False
    comp = body["comparison"][0]
    assert comp["method_key"] == "arima_1_1_0" and len(comp["steps"]) == 20
    assert comp["backtest"]["status"] == "berechnet"

    # Mittlerer Verlauf = 50-%-Quantil des Korridors, mit den Median-Fehlern aus dem Backtest je Horizont
    ml = body["median_line"]
    assert ml["quantile"] == "50" and "Median" in ml["description"] and "kein erwarteter Kurs" in ml["description"]
    assert [e["horizon_bars"] for e in ml["errors"]] == [5, 10, 20]
    by_h = {h["horizon_bars"]: h for h in bt["by_horizon"]}
    for e in ml["errors"]:
        mae = next(m for m in by_h[e["horizon_bars"]]["metrics"] if m["key"] == "median_abs_error")
        assert e["model"] == mae["model"] and e["naive"] == mae["naive"] and e["sample_size"] > 0
    # Beispielpfade: fünf echte simulierte Pfade, aufsteigend nach Endwert, innerhalb der Horizont-Schritte
    ex = body["example_paths"]
    assert [p["percentile"] for p in ex] == [10, 30, 50, 70, 90]
    assert all(len(p["steps"]) == 20 and p["steps"][0]["ts"] == steps[0]["ts"] for p in ex)
    ends = [p["steps"][-1]["close"] for p in ex]
    assert ends == sorted(ends) and steps[-1]["quantiles"]["2.5"] <= ends[2] <= steps[-1]["quantiles"]["97.5"]
    assert "nicht wahrscheinlicher" in body["example_paths_note"]

    short = client.get(f"/api/instruments/{iid}/forecast?horizon=5").json()
    assert len(short["steps"]) == 5 and short["horizon_bars"] == 5
    assert all(len(p["steps"]) == 5 for p in short["example_paths"])
    assert client.get(f"/api/instruments/{iid}/forecast?horizon=21").status_code == 422

    with SessionLocal() as db:
        runs = list(db.scalars(select(BacktestRun).where(BacktestRun.kind == "forecast")))
        assert {r.subject for r in runs} == {"monte_carlo_block_bootstrap", "arima_1_1_0"}
        assert all(r.hit_rate is None for r in runs)


def test_rerun_is_idempotent_and_deterministic(client):
    iid, _ = seed()
    run(iid)
    login(client)
    first = client.get(f"/api/instruments/{iid}/forecast").json()
    assert run(iid, NOW + timedelta(minutes=15)) == {"forecasts": 0, "backtests": 0}
    again = client.get(f"/api/instruments/{iid}/forecast").json()
    assert again["steps"] == first["steps"] and again["generated_at"] == first["generated_at"]


def test_pattern_scenarios_use_simulated_paths(client):
    iid, last = seed()
    did = add_detection(iid, upper=round(last * 1.05, 4), lower=round(last * 0.95, 4))
    run(iid)
    login(client)
    ps = client.get(f"/api/instruments/{iid}/forecast").json()["pattern_scenarios"]
    assert len(ps) == 1 and ps[0]["detection_id"] == did
    up, dn = ps[0]["scenarios"]
    assert up["kind"] == "bestaetigung" and 0 < up["model_probability"] < 1
    assert 0 < dn["model_probability"] < 1
    assert up["model_probability"] + dn["model_probability"] + ps[0]["neither_probability"] == pytest.approx(1.0)
    assert "simulierten Pfade" in up["model_probability_text"] and " über " in up["model_probability_text"]
    assert up["historical"] is None and "kennt das Muster nicht" in ps[0]["note"]

    # Niveau ändert sich nach der Prognose: keine alte Zahl anzeigen
    with SessionLocal() as db:
        d = db.get(PatternDetection, did)
        d.scenarios = [{**d.scenarios[0], "trigger_level": last * 1.08}, d.scenarios[1]]
        db.commit()
    ps = client.get(f"/api/instruments/{iid}/forecast").json()["pattern_scenarios"]
    assert ps[0]["scenarios"][0]["model_probability"] is None
    assert ps[0]["scenarios"][0]["model_probability_text"].startswith("Noch nicht berechnet")


def test_empty_reasons(client):
    iid, _ = seed(n=100)
    run(iid)
    login(client)
    body = client.get(f"/api/instruments/{iid}/forecast").json()
    assert body["empty_reason"] == "Zu wenige Kerzen für eine Prognose (mindestens 250, vorhanden 100)."
    assert body["steps"] == [] and body["backtest"]["status"] == "nicht_berechnet"
    assert body["backtest"]["metrics"] == [] and body["backtest"]["better_than_naive"] is None
    body = client.get(f"/api/instruments/{iid}/forecast?timeframe=1h").json()
    assert body["empty_reason"] == "Prognosen gibt es derzeit nur für Tageskerzen."
    assert client.get("/api/instruments/99999/forecast").status_code == 404


def test_few_bars_forecast_without_backtest(client):
    iid, _ = seed(n=260)
    run(iid)
    login(client)
    body = client.get(f"/api/instruments/{iid}/forecast").json()
    assert body["empty_reason"] is None and len(body["steps"]) == 20
    assert body["backtest"]["status"] == "nicht_berechnet"
    assert body["backtest"]["note"].startswith("Zu wenige Kerzen für einen Backtest")


def test_demo_bars_are_flagged(client):
    iid, _ = seed(demo=True)
    run(iid)
    login(client)
    body = client.get(f"/api/instruments/{iid}/forecast").json()
    assert body["is_demo"] is True and body["backtest"]["is_demo"] is True


def test_methods_and_login(client):
    assert client.get("/api/forecasts/methods").status_code == 401
    login(client)
    body = client.get("/api/forecasts/methods").json()
    assert [m["key"] for m in body["items"]] == ["monte_carlo_block_bootstrap", "arima_1_1_0"]
    assert all(m["assumptions"] and m["limitations"] for m in body["items"])
    assert body["quantiles"] == ["2.5", "10", "25", "50", "75", "90", "97.5"]
