from sqlalchemy import select
from sqlalchemy.orm import Session

from app.config import get_settings
from app.models import User
from app.security import hash_password


def ensure_admin(db: Session) -> None:
    """Legt beim Start den ersten Admin aus ADMIN_EMAIL/ADMIN_PASSWORD an (nur wenn noch keiner existiert)."""
    s = get_settings()
    if not s.admin_email or not s.admin_password:
        return
    if db.scalar(select(User).where(User.role == "admin")):
        return
    db.add(User(email=s.admin_email.lower(), display_name="Administrator", role="admin",
                password_hash=hash_password(s.admin_password)))
    db.commit()
