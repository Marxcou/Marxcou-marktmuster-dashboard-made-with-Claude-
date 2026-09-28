from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from sqlalchemy import func, select

from app.api.instruments import InstrumentOut, InstrumentWithQuote, latest_quote
from app.deps import DB, CurrentUser
from app.models import Instrument, WatchlistItem

router = APIRouter(prefix="/api/watchlist", tags=["watchlist"])


class WatchlistAdd(BaseModel):
    instrument_id: int


@router.get("", response_model=list[InstrumentWithQuote])
def list_watchlist(db: DB, user: CurrentUser) -> list[InstrumentWithQuote]:
    rows = db.execute(
        select(Instrument, WatchlistItem).join(WatchlistItem, WatchlistItem.instrument_id == Instrument.id)
        .where(WatchlistItem.user_id == user.id).order_by(WatchlistItem.position)
    ).all()
    out = []
    for inst, _w in rows:
        base = InstrumentOut.model_validate(inst, from_attributes=True)
        out.append(InstrumentWithQuote(**base.model_dump(), quote=latest_quote(db, inst.id)))
    return out


@router.post("", status_code=201)
def add(body: WatchlistAdd, db: DB, user: CurrentUser) -> dict[str, int]:
    if db.get(Instrument, body.instrument_id) is None:
        raise HTTPException(404, "Instrument nicht gefunden")
    if db.get(WatchlistItem, (user.id, body.instrument_id)) is None:
        pos = db.scalar(select(func.coalesce(func.max(WatchlistItem.position), -1) + 1)
                        .where(WatchlistItem.user_id == user.id)) or 0
        db.add(WatchlistItem(user_id=user.id, instrument_id=body.instrument_id, position=pos))
        db.commit()
    return {"instrument_id": body.instrument_id}


@router.delete("/{instrument_id}", status_code=204)
def remove(instrument_id: int, db: DB, user: CurrentUser) -> None:
    item = db.get(WatchlistItem, (user.id, instrument_id))
    if item:
        db.delete(item)
        db.commit()
