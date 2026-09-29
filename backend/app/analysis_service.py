"""Indikator-Ereignisse und auffällige Kursbewegungen berechnen und speichern (Worker-Job), inkl. zeitlicher
Verknüpfung mit Meldungen. Alles idempotent: bereits gespeicherte Ereignisse werden nicht doppelt angelegt."""
import logging
from datetime import UTC, datetime, timedelta

import numpy as np
from sqlalchemy import select
from sqlalchemy.orm import Session

from app import events as event_bus
from app.analysis import events as ev
from app.analysis import moves as mv
from app.bars import aware, closed_only, load_bars
from app.db import SessionLocal
from app.models import (
    IndicatorEvent,
    Instrument,
    MoveNewsLink,
    NewsCluster,
    NewsInstrument,
    NotableMove,
    PriceBar,
    Source,
)
from app.price_service import watched_instruments

log = logging.getLogger("analysis")

TIMEFRAMES = ("1d", "1h")
BAR_LIMIT = 1500  # 1d: rund 6 Jahre; 1h: rund 8 Monate Börsenzeit
LINK_MAX_AGE = timedelta(days=30)  # Meldungen können nachgeholt werden; ältere Bewegungen werden nicht neu verknüpft
FRESH_BARS = 2  # nur Ereignisse der letzten Kerzen lösen ein Live-Ereignis (WebSocket) aus, kein Backfill-Sturm


def build_series(rows: list[tuple[PriceBar, Source]], timeframe: str, currency: str) -> ev.Series:
    return ev.Series(
        ts=[aware(b.ts_utc) for b, _ in rows],
        open=np.array([b.open for b, _ in rows], dtype=float), high=np.array([b.high for b, _ in rows], dtype=float),
        low=np.array([b.low for b, _ in rows], dtype=float), close=np.array([b.close for b, _ in rows], dtype=float),
        volume=np.array([np.nan if b.volume is None else b.volume for b, _ in rows], dtype=float),
        timeframe=timeframe, currency=currency,
    )


def _source_info(rows: list[tuple[PriceBar, Source]], indices: list[int]) -> tuple[list[int], datetime]:
    used = [rows[i] for i in range(min(indices), max(indices) + 1)] if indices else rows
    ids = sorted({s.id for _, s in used})
    return ids, max(aware(b.fetched_at) for b, _ in used)


def analyze_instrument(db: Session, inst: Instrument, timeframe: str, now: datetime | None = None) -> dict[str, int]:
    now = now or datetime.now(UTC)
    rows = closed_only(load_bars(db, inst.id, timeframe, limit=BAR_LIMIT), timeframe, now)
    stats = {"events": 0, "moves": 0, "links": 0}
    if len(rows) < 30:
        return stats
    s = build_series(rows, timeframe, inst.currency)
    step = mv.TIMEFRAME_DELTA[timeframe]
    n = len(rows)

    existing = {(e.type, e.direction, aware(e.ts_utc)) for e in db.scalars(
        select(IndicatorEvent).where(IndicatorEvent.instrument_id == inst.id, IndicatorEvent.timeframe == timeframe,
                                     IndicatorEvent.algo_version == ev.ALGO_VERSION))}
    for e in ev.detect_all(s):
        key = (e.type, e.direction or "none", e.ts)
        if key in existing:
            continue
        # Alle geladenen Kerzen bis zur Markierung fließen ein (Indikator-Vorlauf), also zählen ihre Quellen.
        ids, fetched = _source_info(rows, [0, e.index])
        row = IndicatorEvent(
            instrument_id=inst.id, timeframe=timeframe, type=e.type, direction=e.direction or "none", ts_utc=e.ts,
            start_ts=s.ts[e.start_index], end_ts=s.ts[e.index], confirmed_at=s.ts[e.confirmed_index],
            title=e.title, summary=e.summary, criteria=e.criteria, values=e.values, params=e.params,
            algo_version=ev.ALGO_VERSION, source_id=rows[e.index][1].id, source_ids=ids, fetched_at=fetched,
            is_demo=any(b.is_demo for b, _ in rows[e.start_index:e.index + 1]))
        db.add(row)
        db.flush()
        stats["events"] += 1
        if e.confirmed_index >= n - FRESH_BARS:
            event_bus.publish(db, "detection", {
                "category": "indicator_event", "event_id": row.id, "instrument_id": inst.id, "timeframe": timeframe,
                "type": e.type, "direction": e.direction, "ts": e.ts.isoformat()})
    db.commit()

    known = {aware(m.move_start): m for m in db.scalars(select(NotableMove).where(
        NotableMove.instrument_id == inst.id, NotableMove.timeframe == timeframe,
        NotableMove.algo_version == mv.ALGO_VERSION))}
    params = mv.params_for(timeframe)
    for m in mv.detect_moves(s):
        start = s.ts[m.index]
        if start in known:
            continue
        ids, fetched = _source_info(rows, [max(0, m.index - params["lookback_bars"]), m.index])
        move = NotableMove(
            instrument_id=inst.id, timeframe=timeframe, move_start=start, move_end=start + step,
            return_pct=m.return_pct, return_z=m.return_z, volume_z=m.volume_z, reasons=m.reasons, params=params,
            algo_version=mv.ALGO_VERSION, source_id=rows[m.index][1].id, source_ids=ids, fetched_at=fetched,
            is_demo=rows[m.index][0].is_demo)
        db.add(move)
        known[start] = move
        stats["moves"] += 1
    db.commit()
    stats["links"] = link_news(db, inst, timeframe, [m for st, m in known.items() if st >= now - LINK_MAX_AGE])
    return stats


def link_news(db: Session, inst: Instrument, timeframe: str, moves: list[NotableMove]) -> int:
    """Meldungscluster des Instruments, deren erste Veröffentlichung im Zeitfenster liegt. Fügt nur fehlende
    Verknüpfungen hinzu (Meldungen können nach der Bewegung eintreffen)."""
    if not moves:
        return 0
    before, after = mv.WINDOWS[timeframe]
    added = 0
    for move in moves:
        start, end = aware(move.move_start), aware(move.move_end)
        rows = db.execute(
            select(NewsCluster, NewsInstrument.source_id)
            .join(NewsInstrument, NewsInstrument.cluster_id == NewsCluster.id)
            .where(NewsInstrument.instrument_id == inst.id,
                   NewsCluster.first_published_at >= start - timedelta(minutes=before),
                   NewsCluster.first_published_at <= end + timedelta(minutes=after))).all()
        have = set(db.scalars(select(MoveNewsLink.cluster_id).where(MoveNewsLink.move_id == move.id)))
        for cluster, source_id in rows:
            if cluster.id in have:
                continue
            offset = round((aware(cluster.first_published_at) - start).total_seconds() / 60)
            db.add(MoveNewsLink(move_id=move.id, cluster_id=cluster.id, time_offset_minutes=offset,
                                source_id=source_id))
            added += 1
    db.commit()
    return added


def analysis_job() -> None:
    """Für alle Watchlist-Instrumente (alle Nutzer) und je Zeitrahmen; ein Fehler betrifft nur diesen Lauf."""
    with SessionLocal() as db:
        for inst in watched_instruments(db):
            for tf in TIMEFRAMES:
                try:
                    stats = analyze_instrument(db, inst, tf)
                except Exception:  # noqa: BLE001 - ein Instrument darf die anderen nicht stoppen
                    db.rollback()
                    log.exception("Analyse %s/%s fehlgeschlagen", inst.symbol, tf)
                    continue
                if any(stats.values()):
                    log.info("Analyse %s/%s: %s", inst.symbol, tf, stats)
