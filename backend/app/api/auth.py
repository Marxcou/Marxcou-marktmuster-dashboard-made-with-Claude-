from typing import Annotated

from fastapi import APIRouter, Cookie, HTTPException, Response
from pydantic import BaseModel, EmailStr, Field
from sqlalchemy import select

from app.config import get_settings
from app.deps import DB, SESSION_COOKIE, CurrentUserAllowPwChange
from app.models import User
from app.security import (
    create_session,
    delete_session,
    delete_user_sessions,
    hash_password,
    load_session,
    session_token_hash,
    verify_password,
)

router = APIRouter(prefix="/api/auth", tags=["auth"])


class LoginIn(BaseModel):
    email: EmailStr
    password: str


class UserOut(BaseModel):
    id: int
    email: str
    display_name: str
    role: str
    must_change_password: bool = False


class MeOut(BaseModel):
    user: UserOut
    csrf_token: str


@router.post("/login", response_model=MeOut)
def login(body: LoginIn, response: Response, db: DB) -> MeOut:
    user = db.scalar(select(User).where(User.email == body.email.lower()))
    if user is None or not verify_password(user.password_hash, body.password):
        raise HTTPException(401, "E-Mail oder Passwort falsch")
    if not user.is_active:
        raise HTTPException(403, "Dieses Konto ist gesperrt. Bitte den Administrator fragen.")
    token, sess = create_session(db, user)
    s = get_settings()
    response.set_cookie(
        SESSION_COOKIE, token, httponly=True, samesite="lax", secure=s.cookie_secure,
        max_age=s.session_ttl_hours * 3600, path="/",
    )
    return MeOut(user=UserOut.model_validate(user, from_attributes=True), csrf_token=sess.csrf_token)


@router.get("/me", response_model=MeOut)
def me(
    db: DB, user: CurrentUserAllowPwChange,
    session: Annotated[str | None, Cookie(alias=SESSION_COOKIE)] = None,
) -> MeOut:
    loaded = load_session(db, session or "")
    assert loaded is not None
    return MeOut(user=UserOut.model_validate(user, from_attributes=True), csrf_token=loaded[1].csrf_token)


@router.post("/logout", status_code=204)
def logout(
    response: Response, db: DB, _user: CurrentUserAllowPwChange,
    session: Annotated[str | None, Cookie(alias=SESSION_COOKIE)] = None,
) -> None:
    if session:
        delete_session(db, session)
    response.delete_cookie(SESSION_COOKIE, path="/")


class PasswordChange(BaseModel):
    current_password: str
    new_password: str = Field(min_length=10, max_length=200)


@router.post("/change-password", status_code=204)
def change_password(
    body: PasswordChange, db: DB, user: CurrentUserAllowPwChange,
    session: Annotated[str | None, Cookie(alias=SESSION_COOKIE)] = None,
) -> None:
    """Jeder Nutzer ändert sein eigenes Passwort. Andere Sitzungen des Kontos werden beendet."""
    if not verify_password(user.password_hash, body.current_password):
        raise HTTPException(400, "Das aktuelle Passwort ist falsch")
    if body.new_password == body.current_password:
        raise HTTPException(400, "Das neue Passwort muss sich vom bisherigen unterscheiden")
    user.password_hash = hash_password(body.new_password)
    user.must_change_password = False
    delete_user_sessions(db, user.id, keep_token_hash=session_token_hash(session) if session else None)
    db.commit()
