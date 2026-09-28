from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, EmailStr, Field
from sqlalchemy import select

from app.api.auth import UserOut
from app.deps import DB, AdminUser
from app.models import User
from app.security import hash_password

router = APIRouter(prefix="/api/users", tags=["users"])


class UserCreate(BaseModel):
    email: EmailStr
    display_name: str = Field(min_length=1, max_length=100)
    password: str = Field(min_length=10)
    role: str = Field(default="user", pattern="^(admin|user)$")


@router.get("", response_model=list[UserOut])
def list_users(db: DB, _admin: AdminUser) -> list[User]:
    return list(db.scalars(select(User).order_by(User.id)))


@router.post("", response_model=UserOut, status_code=201)
def create_user(body: UserCreate, db: DB, _admin: AdminUser) -> User:
    email = body.email.lower()
    if db.scalar(select(User).where(User.email == email)):
        raise HTTPException(409, "E-Mail ist bereits vergeben")
    user = User(email=email, display_name=body.display_name, role=body.role,
                password_hash=hash_password(body.password))
    db.add(user)
    db.commit()
    return user
