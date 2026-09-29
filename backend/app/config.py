import logging
from functools import lru_cache
from typing import Any

from pydantic import model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

log = logging.getLogger(__name__)


class Settings(BaseSettings):
    """Alle Konfiguration kommt aus Umgebungsvariablen (.env). Nie Schlüssel im Code."""

    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    app_env: str = "development"
    demo_mode: bool = False
    timezone: str = "Europe/Berlin"
    database_url: str = "sqlite:///./marktmuster.db"

    session_secret: str = "change-me-to-a-long-random-string"
    session_ttl_hours: int = 168
    cookie_secure: bool = False
    admin_email: str = ""
    admin_password: str = ""

    # Schlüssel der Datenquellen (Adapter lesen sie über get_settings(), nie aus dem Code)
    alpaca_api_key_id: str = ""
    alpaca_api_secret_key: str = ""
    finnhub_api_key: str = ""
    stooq_api_key: str = ""
    openfigi_api_key: str = ""
    yahoo_enabled: bool = False
    sec_edgar_contact_email: str = ""
    eqs_rss_url: str = ""  # Feed-Adresse der EQS-News (Nutzungsbedingungen vorher prüfen)
    ir_feeds: str = ""  # "SYMBOL|https://feed,..." Investor-Relations-Feeds (Nutzungsbedingungen vorher prüfen)
    rss_enabled_feeds: str = ""  # Komma-Liste von Feed-IDs (siehe adapters/rss.py) oder "all"
    marketaux_api_key: str = ""
    alphavantage_api_key: str = ""
    anthropic_api_key: str = ""
    claude_monthly_budget_usd: float = 10.0
    claude_use_batch: bool = True  # Stimmung per Batch-API (halber Preis, Ergebnis nach Minuten bis Stunden)
    news_retention_days: int = 90  # ältere Meldungen werden gelöscht; 0 = nie löschen

    @model_validator(mode="after")
    def _production_needs_real_secrets(self) -> "Settings":
        """Im Produktionsbetrieb startet die App nicht mit den Beispielwerten aus .env.example."""
        if self.app_env == "production":
            problems = []
            if self.session_secret.startswith("change-me") or len(self.session_secret) < 32:
                problems.append("SESSION_SECRET (mindestens 32 Zeichen, z. B. openssl rand -hex 32)")
            if self.admin_password.startswith("change-me"):
                problems.append("ADMIN_PASSWORD")
            if problems:
                raise ValueError("APP_ENV=production, aber noch Beispielwerte gesetzt: " + ", ".join(problems))
        return self

    @model_validator(mode="before")
    @classmethod
    def _ignore_comment_values(cls, data: Any) -> Any:
        """Ein Wert, der mit "#" beginnt, ist ein Kommentar, den Docker Compose bei "KEY=   # Text" als Wert übergibt.
        Er zählt als nicht gesetzt (Standardwert). Nur der Name wird protokolliert, nie der Wert."""
        if not isinstance(data, dict):
            return data
        cleaned = {k: v for k, v in data.items() if not (isinstance(v, str) and v.strip().startswith("#"))}
        for k in sorted(set(data) - set(cleaned)):
            log.warning("%s enthält nur einen Kommentar (beginnt mit '#') und gilt als nicht gesetzt. "
                        "In .env keine Kommentare hinter dem Wert schreiben.", k.upper())
        return cleaned


@lru_cache
def get_settings() -> Settings:
    return Settings()
