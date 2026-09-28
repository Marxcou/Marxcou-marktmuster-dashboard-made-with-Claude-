import hashlib
import secrets
from datetime import timedelta

from argon2 import PasswordHasher
from argon2.exceptions import VerificationError
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.config import get_settings
from app.models import User, UserSession, utcnow

_hasher = PasswordHasher()


def hash_password(password: str) -> str:
    return _hasher.hash(password)


def verify_password(password_hash: str, password: str) -> bool:
    try:
        return _hasher.verify(password_hash, password)
    except VerificationError:
        return False


def _digest(token: str) -> str:
    return hashlib.sha256(token.encode()).hexdigest()


def create_session(db: Session, user: User) -> tuple[str, UserSession]:
    token = secrets.token_urlsafe(32)
    sess = UserSession(
        token_hash=_digest(token),
        user_id=user.id,
        csrf_token=secrets.token_urlsafe(24),
        expires_at=utcnow() + timedelta(hours=get_settings().session_ttl_hours),
    )
    db.add(sess)
    db.commit()
    return token, sess


def load_session(db: Session, token: str) -> tuple[User, UserSession] | None:
    sess = db.get(UserSession, _digest(token))
    if sess is None:
        return None
    expires = sess.expires_at if sess.expires_at.tzinfo else sess.expires_at.replace(tzinfo=utcnow().tzinfo)
    if expires < utcnow():
        db.delete(sess)
        db.commit()
        return None
    user = db.scalar(select(User).where(User.id == sess.user_id))
    return (user, sess) if user else None


def delete_session(db: Session, token: str) -> None:
    sess = db.get(UserSession, _digest(token))
    if sess:
        db.delete(sess)
        db.commit()
