import logging

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.config import get_settings
from app.models import User
from app.security import hash_password

log = logging.getLogger(__name__)

# Platzhalter aus .env.example: damit wird nie ein Admin angelegt.
PLACEHOLDER_EMAILS = {"admin@example.com"}
PLACEHOLDER_PASSWORDS = {"change-me-now"}


def is_placeholder(email: str, password: str) -> bool:
    return email.strip().lower() in PLACEHOLDER_EMAILS or password in PLACEHOLDER_PASSWORDS


def apply_admin_credentials(db: Session, email: str, password: str) -> str:
    """Setzt E-Mail und Passwort des Admins aus den Vorgaben (legt ihn an oder aktualisiert ihn).

    Rückgabe: "created" oder "updated". Wird vom CLI-Befehl `python -m app.admin_cli` genutzt.
    """
    email = email.strip().lower()
    admin = db.scalar(select(User).where(User.email == email)) or db.scalar(
        select(User).where(User.role == "admin").order_by(User.id))
    if admin is None:
        db.add(User(email=email, display_name="Administrator", role="admin",
                    password_hash=hash_password(password)))
        db.commit()
        return "created"
    admin.email = email
    admin.role = "admin"
    admin.password_hash = hash_password(password)
    db.commit()
    return "updated"


def ensure_admin(db: Session) -> None:
    """Legt beim Start den ersten Admin aus ADMIN_EMAIL/ADMIN_PASSWORD an (nur wenn noch keiner existiert).

    Ein vorhandener Admin wird nie überschrieben (ein in der App geändertes Passwort bleibt bestehen).
    Weicht ADMIN_EMAIL vom vorhandenen Admin ab, steht eine Warnung im Log samt Hinweis auf den CLI-Befehl.
    """
    s = get_settings()
    if not s.admin_email or not s.admin_password:
        return
    email = s.admin_email.strip().lower()
    admins = list(db.scalars(select(User).where(User.role == "admin")))
    if admins:
        if email not in {a.email for a in admins}:
            log.warning(
                "ADMIN_EMAIL aus .env (%s) passt zu keinem vorhandenen Admin (%s). Die .env-Zugangsdaten werden "
                "nur beim allerersten Start übernommen. "
                "Zum Übernehmen: docker compose run --rm api python -m app.admin_cli",
                email, ", ".join(a.email for a in admins))
        return
    if is_placeholder(email, s.admin_password):
        log.error(
            "Kein Admin angelegt: ADMIN_EMAIL/ADMIN_PASSWORD in .env enthalten noch die Platzhalter aus .env.example. "
            "Bitte in .env eigene Werte eintragen und neu starten.")
        return
    db.add(User(email=email, display_name="Administrator", role="admin",
                password_hash=hash_password(s.admin_password)))
    db.commit()
