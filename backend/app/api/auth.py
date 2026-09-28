from typing import Annotated

from fastapi import APIRouter, Cookie, HTTPException, Response
from pydantic import BaseModel, EmailStr
from sqlalchemy import select

from app.config import get_settings
from app.deps import DB, SESSION_COOKIE, CurrentUser
from app.models import User
from app.security import create_session, delete_session, load_session, verify_password

router = APIRouter(prefix="/api/auth", tags=["auth"])


class LoginIn(BaseModel):
    email: EmailStr
    password: str


class UserOut(BaseModel):
    id: int
    email: str
    display_name: str
    role: str


class MeOut(BaseModel):
    user: UserOut
    csrf_token: str


@router.post("/login", response_model=MeOut)
def login(body: LoginIn, response: Response, db: DB) -> MeOut:
    user = db.scalar(select(User).where(User.email == body.email.lower()))
    if user is None or not verify_password(user.password_hash, body.password):
        raise HTTPException(401, "E-Mail oder Passwort falsch")
    token, sess = create_session(db, user)
    s = get_settings()
    response.set_cookie(
        SESSION_COOKIE, token, httponly=True, samesite="lax", secure=s.cookie_secure,
        max_age=s.session_ttl_hours * 3600, path="/",
    )
    return MeOut(user=UserOut.model_validate(user, from_attributes=True), csrf_token=sess.csrf_token)


@router.get("/me", response_model=MeOut)
def me(db: DB, user: CurrentUser, session: Annotated[str | None, Cookie(alias=SESSION_COOKIE)] = None) -> MeOut:
    loaded = load_session(db, session or "")
    assert loaded is not None
    return MeOut(user=UserOut.model_validate(user, from_attributes=True), csrf_token=loaded[1].csrf_token)


@router.post("/logout", status_code=204)
def logout(
    response: Response, db: DB, _user: CurrentUser,
    session: Annotated[str | None, Cookie(alias=SESSION_COOKIE)] = None,
) -> None:
    if session:
        delete_session(db, session)
    response.delete_cookie(SESSION_COOKIE, path="/")
