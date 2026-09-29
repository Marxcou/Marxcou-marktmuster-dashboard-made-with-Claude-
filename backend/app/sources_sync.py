import logging

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.adapters.registry import all_adapters
from app.models import Source

log = logging.getLogger(__name__)


def sync_sources(db: Session) -> None:
    """Schreibt Adapter-Metadaten und Health in die Tabelle 'sources' (Quelle der Quellen-Seite)."""
    for adapter in all_adapters():
        meta = adapter.metadata()
        row = db.scalar(select(Source).where(Source.key == meta.key)) or Source(key=meta.key)
        row.name, row.kind, row.description = meta.name, meta.kind, meta.description
        row.homepage, row.terms_url = meta.homepage, meta.terms_url
        row.update_interval, row.delay_text = meta.update_interval, meta.delay_text
        row.requires_key, row.is_official = meta.requires_key, meta.is_official
        try:
            if not adapter.is_configured():
                row.status, row.last_error = "disabled", adapter.disabled_reason
            else:
                h = adapter.health()
                row.status, row.last_error = h.status, h.message
                if h.last_success_at:
                    row.last_success_at = h.last_success_at
        except Exception as exc:  # eine defekte Quelle darf den Start und die anderen Quellen nicht stoppen
            log.warning("Status von %s nicht ermittelbar: %s: %s", meta.key, type(exc).__name__, exc)
            row.status, row.last_error = "offline", f"Statusabfrage fehlgeschlagen ({type(exc).__name__})"
        db.add(row)
    db.commit()
