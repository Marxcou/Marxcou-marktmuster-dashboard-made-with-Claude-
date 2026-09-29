import asyncio
from contextlib import asynccontextmanager, suppress

from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from starlette.websockets import WebSocketState

from app.adapters.registry import load_builtin_adapters
from app.api import auth, forecasts, indicators, instruments, meta, news, patterns, users, watchlist
from app.bootstrap import ensure_admin
from app.db import SessionLocal
from app.deps import SESSION_COOKIE
from app.events import poll
from app.log_redaction import install as install_log_redaction
from app.models import Event
from app.security import load_session
from app.sources_sync import sync_sources


@asynccontextmanager
async def lifespan(_app: FastAPI):  # type: ignore[no-untyped-def]
    load_builtin_adapters()
    with SessionLocal() as db:
        ensure_admin(db)
        sync_sources(db)
    yield


install_log_redaction()
app = FastAPI(title="Marktmuster-Dashboard API", lifespan=lifespan)
for r in (meta.router, auth.router, users.router, instruments.router, watchlist.router, news.router,
          indicators.router, patterns.router, forecasts.router):
    app.include_router(r)


@app.websocket("/ws")
async def ws(websocket: WebSocket) -> None:
    """Live-Ereignisse (quote, news, detection, source_status). Nur mit gültiger Sitzung."""
    token = websocket.cookies.get(SESSION_COOKIE)
    with SessionLocal() as db:
        ok = bool(token) and load_session(db, token or "") is not None
        last_id = max((e.id for e in db.query(Event).order_by(Event.id.desc()).limit(1)), default=0)
    if not ok:
        await websocket.close(code=4401)
        return
    await websocket.accept()
    try:
        while websocket.application_state == WebSocketState.CONNECTED:
            with SessionLocal() as db:
                events = poll(db, last_id)
            for e in events:
                last_id = e.id
                await websocket.send_json({"id": e.id, "type": e.type, "payload": e.payload,
                                           "created_at": e.created_at.isoformat()})
            await asyncio.sleep(1.0)
    except WebSocketDisconnect:
        pass
    finally:
        with suppress(Exception):
            await websocket.close()
