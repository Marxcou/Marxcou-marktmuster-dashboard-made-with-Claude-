"""Instrumente und Kursdaten. Der Vertrag steht in docs/api-contract.md.
Suche: Phase 1A durchsucht nur lokal gespeicherte Instrumente; 1B ergänzt Anbieter-Suche/OpenFIGI."""
from datetime import datetime

from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel
from sqlalchemy import or_, select

from app.deps import DB, CurrentUser
from app.models import Instrument, PriceBar, Quote, Source

router = APIRouter(prefix="/api", tags=["instruments"])

TIMEFRAMES = ("1m", "5m", "1h", "1d")


class SourceRef(BaseModel):
    key: str
    name: str
    homepage: str
    terms_url: str
    delay_text: str


class InstrumentOut(BaseModel):
    id: int
    symbol: str
    name: str
    isin: str | None
    exchange: str
    currency: str


class QuoteOut(BaseModel):
    price: float
    change_abs: float | None
    change_pct: float | None
    ts_utc: datetime
    fetched_at: datetime
    delay_seconds: int | None
    is_demo: bool
    source: SourceRef


class BarOut(BaseModel):
    ts_utc: datetime
    open: float
    high: float
    low: float
    close: float
    volume: float | None
    fetched_at: datetime
    is_demo: bool
    source: SourceRef


class BarsOut(BaseModel):
    instrument: InstrumentOut
    timeframe: str
    bars: list[BarOut]
    # Explizite Leerstands-Aussage statt Ersatzdaten (Grundregel 6):
    empty_reason: str | None = None


class InstrumentWithQuote(InstrumentOut):
    quote: QuoteOut | None = None


def _ref(s: Source) -> SourceRef:
    return SourceRef(key=s.key, name=s.name, homepage=s.homepage, terms_url=s.terms_url, delay_text=s.delay_text)


def latest_quote(db: DB, instrument_id: int) -> QuoteOut | None:
    row = db.execute(
        select(Quote, Source).join(Source, Source.id == Quote.source_id)
        .where(Quote.instrument_id == instrument_id).order_by(Quote.ts_utc.desc()).limit(1)
    ).first()
    if not row:
        return None
    q, s = row
    return QuoteOut(price=q.price, change_abs=q.change_abs, change_pct=q.change_pct, ts_utc=q.ts_utc,
                    fetched_at=q.fetched_at, delay_seconds=q.delay_seconds, is_demo=q.is_demo, source=_ref(s))


@router.get("/instruments/search", response_model=list[InstrumentOut])
def search(db: DB, _u: CurrentUser, q: str = Query(min_length=1, max_length=100)) -> list[Instrument]:
    like = f"%{q.strip()}%"
    stmt = select(Instrument).where(
        or_(Instrument.symbol.ilike(like), Instrument.name.ilike(like), Instrument.isin.ilike(like))
    ).order_by(Instrument.symbol).limit(25)
    return list(db.scalars(stmt))


@router.get("/instruments/{instrument_id}", response_model=InstrumentWithQuote)
def get_instrument(instrument_id: int, db: DB, _u: CurrentUser) -> InstrumentWithQuote:
    inst = db.get(Instrument, instrument_id)
    if inst is None:
        raise HTTPException(404, "Instrument nicht gefunden")
    base = InstrumentOut.model_validate(inst, from_attributes=True)
    return InstrumentWithQuote(**base.model_dump(), quote=latest_quote(db, inst.id))


@router.get("/instruments/{instrument_id}/bars", response_model=BarsOut)
def get_bars(
    instrument_id: int, db: DB, _u: CurrentUser, timeframe: str = "1d",
    start: datetime | None = None, end: datetime | None = None, limit: int = Query(2000, le=10000),
) -> BarsOut:
    if timeframe not in TIMEFRAMES:
        raise HTTPException(422, f"timeframe muss einer von {TIMEFRAMES} sein")
    inst = db.get(Instrument, instrument_id)
    if inst is None:
        raise HTTPException(404, "Instrument nicht gefunden")
    stmt = (select(PriceBar, Source).join(Source, Source.id == PriceBar.source_id)
            .where(PriceBar.instrument_id == instrument_id, PriceBar.timeframe == timeframe))
    if start:
        stmt = stmt.where(PriceBar.ts_utc >= start)
    if end:
        stmt = stmt.where(PriceBar.ts_utc <= end)
    rows = db.execute(stmt.order_by(PriceBar.ts_utc.desc()).limit(limit)).all()
    bars = [
        BarOut(ts_utc=b.ts_utc, open=b.open, high=b.high, low=b.low, close=b.close, volume=b.volume,
               fetched_at=b.fetched_at, is_demo=b.is_demo, source=_ref(s))
        for b, s in reversed(rows)
    ]
    reason = None if bars else "Keine Kursdaten für diesen Zeitraum gespeichert (noch keine Quelle hat sie geliefert)."
    return BarsOut(instrument=InstrumentOut.model_validate(inst, from_attributes=True),
                   timeframe=timeframe, bars=bars, empty_reason=reason)
