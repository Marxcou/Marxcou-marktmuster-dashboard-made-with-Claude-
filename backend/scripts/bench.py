"""Messlauf für Phase 5A: füllt eine frische SQLite-Datei mit synthetischen Daten (nur für die Messung, nie für die
App) und misst Worker-Jobs, API-Antwortzeiten und Query-Pläne.

  cd backend && python scripts/bench.py [--instruments 40] [--news 20000]
"""
import argparse
import os
import random
import sys
import tempfile
import time
from datetime import UTC, datetime, timedelta

_tmp = tempfile.mkdtemp()
os.environ["DATABASE_URL"] = f"sqlite:///{_tmp}/bench.db"
os.environ.setdefault("ADMIN_EMAIL", "admin@dashboard-test.org")
os.environ.setdefault("ADMIN_PASSWORD", "bench-password-123")
os.environ["DEMO_MODE"] = "false"
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from fastapi.testclient import TestClient  # noqa: E402
from sqlalchemy import text  # noqa: E402

from app.analysis_service import analysis_job  # noqa: E402
from app.db import Base, SessionLocal, engine  # noqa: E402
from app.forecast_service import forecast_job  # noqa: E402
from app.main import app  # noqa: E402
from app.models import (  # noqa: E402
    Event,
    Instrument,
    NewsCluster,
    NewsInstrument,
    NewsItem,
    PriceBar,
    Quote,
    Source,
    User,
    WatchlistItem,
)
from app.pattern_service import pattern_job  # noqa: E402
from app.security import hash_password  # noqa: E402

NOW = datetime.now(UTC).replace(second=0, microsecond=0)
STEP = {"1d": timedelta(days=1), "1h": timedelta(hours=1), "5m": timedelta(minutes=5), "1m": timedelta(minutes=1)}
COUNT = {"1d": 1500, "1h": 1500, "5m": 3000, "1m": 2730}


def seed(n_inst: int, n_news: int) -> None:
    rnd = random.Random(7)
    Base.metadata.create_all(engine)
    with SessionLocal() as db:
        src = Source(key="bench", name="Bench", kind="price", status="online")
        db.add(src)
        db.flush()
        for i in range(n_inst):
            inst = Instrument(symbol=f"S{i:03d}", name=f"Bench {i}", exchange="XNAS" if i % 2 else "XNYS",
                              currency="USD", source_id=src.id)
            db.add(inst)
            db.flush()
            for tf, n in COUNT.items():
                price, rows = 100.0, []
                for k in range(n):
                    o = price
                    price *= 1 + rnd.gauss(0, 0.01 if tf == "1d" else 0.002)
                    rows.append(PriceBar(instrument_id=inst.id, timeframe=tf, ts_utc=NOW - STEP[tf] * (n - k),
                                         source_id=src.id, open=o, high=max(o, price) * 1.001,
                                         low=min(o, price) * 0.999, close=price, volume=rnd.uniform(1e5, 1e6),
                                         fetched_at=NOW))
                db.add_all(rows)
            for k in range(500):
                db.add(Quote(instrument_id=inst.id, price=100 + k * 0.01, ts_utc=NOW - timedelta(minutes=500 - k),
                             source_id=src.id, fetched_at=NOW))
        pw = hash_password("bench-password-123")
        users = []
        for u in range(5):
            user = User(email=f"u{u}@dashboard-test.org", password_hash=pw, display_name=f"U{u}", role="user")
            db.add(user)
            users.append(user)
        db.flush()
        for user in users:
            for pos, iid in enumerate(rnd.sample(range(1, n_inst + 1), min(15, n_inst))):
                db.add(WatchlistItem(user_id=user.id, instrument_id=iid, position=pos))
        for c in range(n_news):
            ts = NOW - timedelta(minutes=c * 3)
            cl = NewsCluster(canonical_title=f"Meldung {c}", first_published_at=ts, last_published_at=ts, item_count=1)
            db.add(cl)
            db.flush()
            db.add(NewsItem(cluster_id=cl.id, source_id=src.id, external_id=str(c), url=f"https://x.test/{c}",
                            url_normalized=f"https://x.test/{c}", title=f"Meldung {c}", excerpt="", published_at=ts,
                            fetched_at=ts))
            db.add(NewsInstrument(cluster_id=cl.id, instrument_id=rnd.randint(1, n_inst), source_id=src.id,
                                  match_method="provider_tag"))
        for _ in range(200_000):
            db.add(Event(type="quote", payload={"instrument_id": 1, "price": 1.0}))
        db.commit()


def timed(label: str, fn, repeat: int = 1) -> float:
    t = time.perf_counter()
    for _ in range(repeat):
        fn()
    dt = (time.perf_counter() - t) / repeat
    print(f"{label:<44}{dt * 1000:10.1f} ms")
    return dt


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--instruments", type=int, default=40)
    ap.add_argument("--news", type=int, default=20000)
    a = ap.parse_args()
    t = time.perf_counter()
    seed(a.instruments, a.news)
    print(f"seed: {time.perf_counter() - t:.1f}s, db {os.path.getsize(f'{_tmp}/bench.db') / 1e6:.0f} MB\n")

    print("== Worker-Jobs (Watchlist-Instrumente: alle Nutzer zusammen) ==")
    with SessionLocal() as db:
        print("watched:", db.execute(text("select count(distinct instrument_id) from watchlist_items")).scalar())
    timed("pattern_job (1. Lauf)", pattern_job)
    timed("pattern_job (2. Lauf, keine neuen Kerzen)", pattern_job)
    timed("analysis_job (1. Lauf)", analysis_job)
    timed("analysis_job (2. Lauf, keine neuen Kerzen)", analysis_job)
    timed("forecast_job (1. Lauf)", forecast_job)
    timed("forecast_job (2. Lauf)", forecast_job)

    print("\n== API ==")
    with TestClient(app) as c:
        r = c.post("/api/auth/login", json={"email": "u0@dashboard-test.org", "password": "bench-password-123"})
        assert r.status_code == 200, r.text
        get = lambda p: (lambda: c.get(p).raise_for_status())  # noqa: E731
        for path in ["/api/watchlist", "/api/news/counts", "/api/patterns/counts", "/api/sources",
                     "/api/instruments/1", "/api/instruments/1/bars?timeframe=1d&limit=2000",
                     "/api/instruments/1/bars?timeframe=1m&limit=2000",
                     "/api/instruments/1/indicators?timeframe=1d&sma=20,50,200&ema=12&rsi=14&macd=12,26,9&bb=20,2",
                     "/api/instruments/1/indicator-events", "/api/instruments/1/move-links",
                     "/api/instruments/1/patterns", "/api/instruments/1/forecast", "/api/news?limit=30",
                     "/api/news?limit=30&sentiment=positiv", "/api/news?limit=30&source=bench",
                     "/api/instruments/1/news"]:
            timed(path[:44], get(path), repeat=5)

    print("\n== Query-Pläne ==")
    with engine.connect() as conn:
        for q in [
            "select * from news_clusters order by first_published_at desc, id desc limit 30",
            "select * from news_clusters where id in (select cluster_id from news_instruments where instrument_id=3)"
            " order by first_published_at desc limit 30",
            "select count(*) from (select * from news_clusters where id in (select cluster_id from news_items"
            " join sources on sources.id=news_items.source_id where sources.key='bench'))",
            "select instrument_id, count(cluster_id) from news_instruments join news_clusters on"
            " news_clusters.id=news_instruments.cluster_id where instrument_id in (1,2,3) and"
            " first_published_at >= '2026-01-01' group by instrument_id",
            "select * from price_bars where instrument_id=1 and timeframe='1d' order by ts_utc desc limit 4000",
            "select * from events where id > 199990 order by id limit 200",
        ]:
            print("\n", q[:110])
            for row in conn.execute(text("explain query plan " + q)):
                print("   ", row[-1])


if __name__ == "__main__":
    main()
