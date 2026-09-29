"""Benutzerverwaltung (nur Administratoren). Es gibt keine offene Registrierung und keinen E-Mail-Versand:
Einmalpasswörter werden genau einmal in der Antwort angezeigt und nie gespeichert (nur der Argon2-Hash)."""
from datetime import datetime

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, EmailStr, Field
from sqlalchemy import func, select

from app.deps import DB, AdminUser
from app.models import User
from app.security import delete_user_sessions, generate_temporary_password, hash_password

router = APIRouter(prefix="/api/users", tags=["users"])


class AdminUserOut(BaseModel):
    id: int
    email: str
    display_name: str
    role: str
    is_active: bool
    must_change_password: bool
    created_at: datetime


class UserCreate(BaseModel):
    email: EmailStr
    display_name: str = Field(min_length=1, max_length=100)
    password: str | None = Field(default=None, min_length=10, max_length=200)  # leer = wird erzeugt
    role: str = Field(default="user", pattern="^(admin|user)$")


class UserCreated(AdminUserOut):
    temporary_password: str  # nur in dieser Antwort


class UserPatch(BaseModel):
    is_active: bool | None = None
    role: str | None = Field(default=None, pattern="^(admin|user)$")
    display_name: str | None = Field(default=None, min_length=1, max_length=100)


class PasswordReset(BaseModel):
    temporary_password: str


def _get(db, user_id: int) -> User:
    user = db.get(User, user_id)
    if user is None:
        raise HTTPException(404, "Benutzer nicht gefunden")
    return user


def _active_admins(db) -> int:
    return db.scalar(select(func.count()).select_from(User).where(User.role == "admin", User.is_active.is_(True))) or 0


@router.get("", response_model=list[AdminUserOut])
def list_users(db: DB, _admin: AdminUser) -> list[User]:
    return list(db.scalars(select(User).order_by(User.id)))


@router.post("", response_model=UserCreated, status_code=201)
def create_user(body: UserCreate, db: DB, _admin: AdminUser) -> dict:
    email = body.email.lower()
    if db.scalar(select(User).where(User.email == email)):
        raise HTTPException(409, "E-Mail ist bereits vergeben")
    password = body.password or generate_temporary_password()
    user = User(email=email, display_name=body.display_name, role=body.role,
                password_hash=hash_password(password), must_change_password=True)
    db.add(user)
    db.commit()
    return {**AdminUserOut.model_validate(user, from_attributes=True).model_dump(), "temporary_password": password}


@router.patch("/{user_id}", response_model=AdminUserOut)
def patch_user(user_id: int, body: UserPatch, db: DB, admin: AdminUser) -> User:
    user = _get(db, user_id)
    demoting = user.role == "admin" and (body.role == "user" or body.is_active is False)
    if demoting and user.is_active and _active_admins(db) <= 1:
        raise HTTPException(409, "Der letzte aktive Administrator kann nicht gesperrt oder herabgestuft werden")
    if user.id == admin.id and (body.is_active is False or body.role == "user"):
        raise HTTPException(409, "Das eigene Konto kann nicht gesperrt oder herabgestuft werden")
    if body.display_name is not None:
        user.display_name = body.display_name
    if body.role is not None:
        user.role = body.role
    if body.is_active is not None:
        user.is_active = body.is_active
        if not body.is_active:
            delete_user_sessions(db, user.id)
    db.commit()
    return user


@router.post("/{user_id}/reset-password", response_model=PasswordReset)
def reset_password(user_id: int, db: DB, _admin: AdminUser) -> PasswordReset:
    user = _get(db, user_id)
    password = generate_temporary_password()
    user.password_hash = hash_password(password)
    user.must_change_password = True
    delete_user_sessions(db, user.id)
    db.commit()
    return PasswordReset(temporary_password=password)
