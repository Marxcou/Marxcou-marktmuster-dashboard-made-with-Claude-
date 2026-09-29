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


def generate_temporary_password() -> str:
    """Zufälliges Einmalpasswort (16 Zeichen, URL-sicher); wird nur einmal angezeigt und nie gespeichert."""
    return secrets.token_urlsafe(12)


def delete_user_sessions(db: Session, user_id: int, keep_token_hash: str | None = None) -> None:
    for sess in db.scalars(select(UserSession).where(UserSession.user_id == user_id)):
        if sess.token_hash != keep_token_hash:
            db.delete(sess)


def session_token_hash(token: str) -> str:
    return _digest(token)


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
    if user is None or not user.is_active:
        return None
    return user, sess


def delete_session(db: Session, token: str) -> None:
    sess = db.get(UserSession, _digest(token))
    if sess:
        db.delete(sess)
        db.commit()
