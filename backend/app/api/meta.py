from datetime import datetime

from fastapi import APIRouter
from pydantic import BaseModel
from sqlalchemy import select

from app.config import get_settings
from app.deps import DB, CurrentUser
from app.grundregeln import DISCLAIMER
from app.models import Source

router = APIRouter(prefix="/api", tags=["meta"])


class MetaOut(BaseModel):
    demo_mode: bool
    timezone: str
    disclaimer: str


class SourceOut(BaseModel):
    key: str
    name: str
    kind: str
    description: str
    homepage: str
    terms_url: str
    update_interval: str
    delay_text: str
    requires_key: bool
    is_official: bool
    status: str
    last_success_at: datetime | None
    last_error: str | None


@router.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok"}


@router.get("/meta", response_model=MetaOut)
def meta() -> MetaOut:
    s = get_settings()
    return MetaOut(demo_mode=s.demo_mode, timezone=s.timezone, disclaimer=DISCLAIMER)


@router.get("/sources", response_model=list[SourceOut])
def sources(db: DB, _u: CurrentUser) -> list[Source]:
    return list(db.scalars(select(Source).order_by(Source.kind, Source.name)))
