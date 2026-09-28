from datetime import UTC, datetime, timedelta

from fastapi import APIRouter
from pydantic import BaseModel
from sqlalchemy import func, select

from app.config import get_settings
from app.deps import DB, CurrentUser
from app.grundregeln import DISCLAIMER
from app.models import NewsItem, Source

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
    item_count_24h: int | None = None


@router.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok"}


@router.get("/meta", response_model=MetaOut)
def meta() -> MetaOut:
    s = get_settings()
    return MetaOut(demo_mode=s.demo_mode, timezone=s.timezone, disclaimer=DISCLAIMER)


@router.get("/sources", response_model=list[SourceOut])
def sources(db: DB, _u: CurrentUser) -> list[SourceOut]:
    since = datetime.now(UTC) - timedelta(hours=24)
    counts = dict(db.execute(select(NewsItem.source_id, func.count(NewsItem.id))
                             .where(NewsItem.fetched_at >= since).group_by(NewsItem.source_id)).all())
    out = []
    for s in db.scalars(select(Source).order_by(Source.kind, Source.name)):
        row = SourceOut.model_validate(s, from_attributes=True)
        row.item_count_24h = counts.get(s.id, 0) if s.kind == "news" else None
        out.append(row)
    return out
