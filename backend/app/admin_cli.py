"""Übernimmt ADMIN_EMAIL/ADMIN_PASSWORD aus .env in eine bestehende Datenbank, ohne sie zu löschen.

Aufruf: docker compose run --rm api python -m app.admin_cli
"""
import sys

from app.bootstrap import apply_admin_credentials, is_placeholder
from app.config import get_settings
from app.db import SessionLocal


def main() -> int:
    s = get_settings()
    if not s.admin_email or not s.admin_password:
        print("ADMIN_EMAIL und ADMIN_PASSWORD müssen in .env gesetzt sein.", file=sys.stderr)
        return 1
    if is_placeholder(s.admin_email, s.admin_password):
        print("ADMIN_EMAIL/ADMIN_PASSWORD enthalten noch die Platzhalter aus .env.example. "
              "Bitte eigene Werte eintragen.", file=sys.stderr)
        return 1
    with SessionLocal() as db:
        result = apply_admin_credentials(db, s.admin_email, s.admin_password)
    print(f"Admin {s.admin_email.strip().lower()} {'angelegt' if result == 'created' else 'aktualisiert'}.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
