from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


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
    marketaux_api_key: str = ""
    alphavantage_api_key: str = ""
    anthropic_api_key: str = ""
    claude_monthly_budget_usd: float = 10.0


@lru_cache
def get_settings() -> Settings:
    return Settings()
