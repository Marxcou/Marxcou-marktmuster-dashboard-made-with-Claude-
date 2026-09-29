"""Indikator-Serien, Indikator-Ereignisse und auffällige Kursbewegungen mit zeitlich passenden Meldungen.
Der Vertrag steht in docs/api-contract.md (Abschnitt Phase 3A)."""
import base64
import binascii
from datetime import UTC, datetime
from typing import Any

import numpy as np
from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel
from sqlalchemy import and_, or_, select

from app.analysis import events as ev
from app.analysis import indicators as ind
from app.analysis import moves as mv
from app.analysis.moves import NOTE
from app.api.instruments import TIMEFRAMES, SourceRef, _ref
from app.bars import aware, load_bars
from app.deps import DB, CurrentUser
from app.models import (
    IndicatorEvent,
    Instrument,
    MoveNewsLink,
    NewsCluster,
    NewsItem,
    NotableMove,
    Source,
)

router = APIRouter(prefix="/api", tags=["indicators"])

INDICATORS_VERSION = "indicators-1"
WARMUP_BARS = 400
EVENT_TYPES = ("golden_cross", "death_cross", "rsi_divergence", "bb_breakout", "volume_spike")
NO_STATS_REASON = "Für Indikator-Ereignisse wird noch keine historische Trefferquote berechnet."


class IndicatorOut(BaseModel):
    key: str
    type: str
    params: dict[str, Any]
    label: str
    panel: str  # price | own
    formula: str
    range: list[float] | None = None
    reference_lines: list[float] | None = None
    lines: dict[str, list[float | None]]


class IndicatorsOut(BaseModel):
    instrument_id: int
    timeframe: str
    algo_version: str
    timestamps: list[datetime]
    indicators: list[IndicatorOut]
    sources: list[SourceRef]
    bars_fetched_at: datetime | None
    computed_at: datetime
    empty_reason: str | None


class CriterionOut(BaseModel):
    name: str
    rule: str
    required: str
    actual: str
    passed: bool


class IndicatorEventOut(BaseModel):
    id: int
    instrument_id: int
    timeframe: str
    type: str
    direction: str | None
    ts: datetime
    start_ts: datetime
    end_ts: datetime
    confirmed_at: datetime
    title: str
    summary: str
    criteria: list[CriterionOut]
    values: dict[str, Any]
    params: dict[str, Any]
    algo_version: str
    historical_stats: dict[str, Any] | None
    historical_stats_reason: str | None
    sources: list[SourceRef]
    bars_fetched_at: datetime
    detected_at: datetime
    is_demo: bool


class IndicatorEventsOut(BaseModel):
    events: list[IndicatorEventOut]
    next_cursor: str | None
    empty_reason: str | None


class MoveNewsOut(BaseModel):
    cluster_id: int
    canonical_title: str
    first_published_at: datetime
    time_offset_minutes: int
    item_count: int
    sources: list[SourceRef]


class NotableMoveOut(BaseModel):
    id: int
    instrument_id: int
    timeframe: str
    move_start: datetime
    move_end: datetime
    return_pct: float
    return_z: float | None
    volume_z: float | None
    reasons: list[str]
    params: dict[str, Any]
    algo_version: str
    sources: list[SourceRef]
    bars_fetched_at: datetime
    detected_at: datetime
    is_demo: bool
    news: list[MoveNewsOut]


class MoveLinksOut(BaseModel):
    moves: list[NotableMoveOut]
    note: str
    empty_reason: str | None


def _clean(a: np.ndarray) -> list[float | None]:
    return [None if np.isnan(v) else round(float(v), 6) for v in a]


def _periods(raw: str | None, name: str, count: int = 5) -> list[int]:
    if not raw:
        return []
    try:
        vals = [int(x) for x in raw.split(",") if x.strip()]
    except ValueError:
        raise HTTPException(422, f"{name}: ganze Zahlen, durch Komma getrennt") from None
    if len(vals) > count or any(v < 2 or v > 500 for v in vals):
        raise HTTPException(422, f"{name}: höchstens {count} Perioden, je 2 bis 500")
    return list(dict.fromkeys(vals))


def _get_instrument(db: DB, instrument_id: int) -> Instrument:
    inst = db.get(Instrument, instrument_id)
    if inst is None:
        raise HTTPException(404, "Instrument nicht gefunden")
    return inst


@router.get("/instruments/{instrument_id}/indicators", response_model=IndicatorsOut)
def get_indicators(  # noqa: PLR0912, PLR0913
    instrument_id: int, db: DB, _u: CurrentUser, timeframe: str = "1d", start: datetime | None = None,
    end: datetime | None = None, limit: int = Query(2000, ge=1, le=10000), sma: str | None = None,
    ema: str | None = None, rsi: int | None = Query(None, ge=2, le=500), macd: str | None = None,
    bb: str | None = None,
) -> IndicatorsOut:
    if timeframe not in TIMEFRAMES:
        raise HTTPException(422, f"timeframe muss einer von {TIMEFRAMES} sein")
    _get_instrument(db, instrument_id)
    sma_p, ema_p = _periods(sma, "sma"), _periods(ema, "ema")
    macd_p = _periods(macd, "macd", 3) if macd else []
    if macd and (len(macd_p) != 3 or not macd_p[0] < macd_p[1]):
        raise HTTPException(422, "macd: schnell,langsam,signal mit schnell < langsam")
    bb_p: tuple[int, float] | None = None
    if bb:
        try:
            raw_per, raw_fac = bb.split(",")
            bb_p = (int(raw_per), float(raw_fac))
        except ValueError:
            raise HTTPException(422, "bb: periode,faktor") from None
        if not 2 <= bb_p[0] <= 500 or not 0.5 <= bb_p[1] <= 5:
            raise HTTPException(422, "bb: Periode 2 bis 500, Faktor 0,5 bis 5")

    rows = load_bars(db, instrument_id, timeframe, end=end, limit=limit + WARMUP_BARS)
    now = datetime.now(UTC)
    if not rows:
        return IndicatorsOut(instrument_id=instrument_id, timeframe=timeframe, algo_version=INDICATORS_VERSION,
                             timestamps=[], indicators=[], sources=[], bars_fetched_at=None, computed_at=now,
                             empty_reason="Keine Kursdaten für diesen Zeitraum gespeichert (noch keine Quelle hat "
                                          "sie geliefert); ohne Kerzen gibt es keine Indikatoren.")
    close = np.array([b.close for b, _ in rows], dtype=float)
    out: list[IndicatorOut] = []
    for n in sma_p:
        out.append(IndicatorOut(
            key=f"sma_{n}", type="sma", params={"period": n}, label=f"SMA ({n})", panel="price",
            formula=f"Arithmetisches Mittel der letzten {n} Schlusskurse",
            lines={"value": _clean(ind.sma(close, n))}))
    for n in ema_p:
        out.append(IndicatorOut(
            key=f"ema_{n}", type="ema", params={"period": n}, label=f"EMA ({n})", panel="price",
            formula=(f"Exponentieller Durchschnitt der Schlusskurse, α = 2/({n}+1); "
                     f"Startwert = SMA der ersten {n} Kerzen"),
            lines={"value": _clean(ind.ema(close, n))}))
    if rsi:
        out.append(IndicatorOut(
            key=f"rsi_{rsi}", type="rsi", params={"period": rsi}, label=f"RSI ({rsi})", panel="own",
            formula=(f"RSI nach Wilder: 100 − 100 / (1 + RS), RS = geglätteter Durchschnittsgewinn / geglätteter "
                     f"Durchschnittsverlust der Schlusskurs-Änderungen ({rsi} Kerzen)"),
            range=[0, 100], reference_lines=[30, 70], lines={"value": _clean(ind.rsi(close, rsi))}))
    if macd_p:
        f, sl, sg = macd_p
        line, sig, hist = ind.macd(close, f, sl, sg)
        out.append(IndicatorOut(
            key=f"macd_{f}_{sl}_{sg}", type="macd", params={"fast": f, "slow": sl, "signal": sg},
            label=f"MACD ({f}, {sl}, {sg})", panel="own",
            formula=(f"MACD = EMA({f}) − EMA({sl}) der Schlusskurse; Signal = EMA({sg}) des MACD; "
                     "Histogramm = MACD − Signal"),
            lines={"macd": _clean(line), "signal": _clean(sig), "histogram": _clean(hist)}))
    if bb_p:
        per, fac = bb_p
        mid, up, lo = ind.bollinger(close, per, fac)
        out.append(IndicatorOut(
            key=f"bb_{per}_{fac:g}".replace(".", "_"), type="bollinger", params={"period": per, "factor": fac},
            label=f"Bollinger-Bänder ({per}, {fac:g} σ)", panel="price",
            formula=(f"Mittelband = SMA({per}); Bänder = Mittelband ± {fac:g} × Standardabweichung "
                     f"(Grundgesamtheit) der letzten {per} Schlusskurse"),
            lines={"middle": _clean(mid), "upper": _clean(up), "lower": _clean(lo)}))

    # Auf das angefragte Fenster kürzen (Vorlauf gehört nicht in die Antwort)
    keep = [i for i, (b, _) in enumerate(rows) if start is None or aware(b.ts_utc) >= aware(start)][-limit:]
    lo_i = keep[0] if keep else len(rows)
    for item in out:
        item.lines = {k: v[lo_i:] for k, v in item.lines.items()}
    shown = rows[lo_i:]
    srcs = {s.id: s for _, s in rows}
    return IndicatorsOut(
        instrument_id=instrument_id, timeframe=timeframe, algo_version=INDICATORS_VERSION,
        timestamps=[b.ts_utc for b, _ in shown], indicators=out, sources=[_ref(s) for s in srcs.values()],
        bars_fetched_at=max((b.fetched_at for b, _ in rows), default=None), computed_at=now,
        empty_reason=None if shown else "Im angefragten Zeitraum liegen keine Kerzen.")


def _encode(ts: datetime, id_: int) -> str:
    return base64.urlsafe_b64encode(f"{aware(ts).isoformat()}|{id_}".encode()).decode()


def _decode(cursor: str) -> tuple[datetime, int]:
    try:
        ts, id_ = base64.urlsafe_b64decode(cursor.encode()).decode().split("|")
        return datetime.fromisoformat(ts), int(id_)
    except (ValueError, binascii.Error, UnicodeDecodeError):
        raise HTTPException(422, "Ungültiger cursor") from None


def _sources(db: DB, ids: list[int]) -> list[SourceRef]:
    return [_ref(s) for s in db.scalars(select(Source).where(Source.id.in_(ids)).order_by(Source.id))]


@router.get("/instruments/{instrument_id}/indicator-events", response_model=IndicatorEventsOut)
def get_indicator_events(  # noqa: PLR0913
    instrument_id: int, db: DB, _u: CurrentUser, timeframe: str = "1d", type: str | None = None,  # noqa: A002
    since: datetime | None = None, until: datetime | None = None, limit: int = Query(50, ge=1, le=200),
    cursor: str | None = None,
) -> IndicatorEventsOut:
    if timeframe not in TIMEFRAMES:
        raise HTTPException(422, f"timeframe muss einer von {TIMEFRAMES} sein")
    if type and type not in EVENT_TYPES:
        raise HTTPException(422, f"type muss einer von {EVENT_TYPES} sein")
    _get_instrument(db, instrument_id)
    stmt = select(IndicatorEvent).where(
        IndicatorEvent.instrument_id == instrument_id, IndicatorEvent.timeframe == timeframe,
        IndicatorEvent.algo_version == ev.ALGO_VERSION)
    if type:
        stmt = stmt.where(IndicatorEvent.type == type)
    if since:
        stmt = stmt.where(IndicatorEvent.ts_utc >= since)
    if until:
        stmt = stmt.where(IndicatorEvent.ts_utc <= until)
    if cursor:
        c_ts, c_id = _decode(cursor)
        stmt = stmt.where(or_(IndicatorEvent.ts_utc < c_ts,
                              and_(IndicatorEvent.ts_utc == c_ts, IndicatorEvent.id < c_id)))
    rows = list(db.scalars(stmt.order_by(IndicatorEvent.ts_utc.desc(), IndicatorEvent.id.desc()).limit(limit + 1)))
    more = len(rows) > limit
    rows = rows[:limit]
    items = [
        IndicatorEventOut(
            id=e.id, instrument_id=e.instrument_id, timeframe=e.timeframe, type=e.type,
            direction=None if e.direction == "none" else e.direction, ts=e.ts_utc, start_ts=e.start_ts,
            end_ts=e.end_ts, confirmed_at=e.confirmed_at, title=e.title, summary=e.summary,
            criteria=[CriterionOut(**c) for c in e.criteria], values=e.values, params=e.params,
            algo_version=e.algo_version, historical_stats=None, historical_stats_reason=NO_STATS_REASON,
            sources=_sources(db, e.source_ids), bars_fetched_at=e.fetched_at, detected_at=e.detected_at,
            is_demo=e.is_demo)
        for e in rows]
    reason = None
    if not items:
        reason = ("Keine Ereignisse mit diesen Filtern gefunden." if (type or since or until or cursor)
                  else "Noch keine Ereignisse erkannt. Die Auswertung braucht gespeicherte Kerzen und läuft im "
                       "Hintergrund; für Kreuzungen des SMA(200) sind mindestens 201 abgeschlossene Kerzen nötig.")
    return IndicatorEventsOut(events=items, next_cursor=_encode(rows[-1].ts_utc, rows[-1].id) if more else None,
                              empty_reason=reason)


@router.get("/instruments/{instrument_id}/move-links", response_model=MoveLinksOut)
def get_move_links(
    instrument_id: int, db: DB, _u: CurrentUser, timeframe: str = "1d", since: datetime | None = None,
    until: datetime | None = None, limit: int = Query(50, ge=1, le=200),
) -> MoveLinksOut:
    if timeframe not in TIMEFRAMES:
        raise HTTPException(422, f"timeframe muss einer von {TIMEFRAMES} sein")
    _get_instrument(db, instrument_id)
    stmt = select(NotableMove).where(
        NotableMove.instrument_id == instrument_id, NotableMove.timeframe == timeframe,
        NotableMove.algo_version == mv.ALGO_VERSION)
    if since:
        stmt = stmt.where(NotableMove.move_start >= since)
    if until:
        stmt = stmt.where(NotableMove.move_start <= until)
    moves = list(db.scalars(stmt.order_by(NotableMove.move_start.desc()).limit(limit)))
    out: list[NotableMoveOut] = []
    for m in moves:
        news: list[MoveNewsOut] = []
        links = db.execute(select(MoveNewsLink, NewsCluster)
                           .join(NewsCluster, NewsCluster.id == MoveNewsLink.cluster_id)
                           .where(MoveNewsLink.move_id == m.id).order_by(NewsCluster.first_published_at)).all()
        for link, cluster in links:
            srcs = db.scalars(select(Source).join(NewsItem, NewsItem.source_id == Source.id)
                              .where(NewsItem.cluster_id == cluster.id).distinct().order_by(Source.id))
            news.append(MoveNewsOut(cluster_id=cluster.id, canonical_title=cluster.canonical_title,
                                    first_published_at=cluster.first_published_at,
                                    time_offset_minutes=link.time_offset_minutes, item_count=cluster.item_count,
                                    sources=[_ref(s) for s in srcs]))
        out.append(NotableMoveOut(
            id=m.id, instrument_id=m.instrument_id, timeframe=m.timeframe, move_start=m.move_start,
            move_end=m.move_end, return_pct=m.return_pct, return_z=m.return_z, volume_z=m.volume_z,
            reasons=m.reasons, params=m.params, algo_version=m.algo_version, sources=_sources(db, m.source_ids),
            bars_fetched_at=m.fetched_at, detected_at=m.detected_at, is_demo=m.is_demo, news=news))
    reason = None if out else (
        "Keine auffälligen Kursbewegungen im Zeitraum gefunden." if (since or until) else
        "Noch keine auffälligen Kursbewegungen erkannt (nötig sind mindestens 61 abgeschlossene Kerzen).")
    return MoveLinksOut(moves=out, note=NOTE, empty_reason=reason)
