import pytest
from pydantic import ValidationError

from app.config import Settings


def make(**kw: str) -> Settings:
    return Settings(_env_file=None, **kw)  # type: ignore[arg-type]


def test_production_rejects_example_secrets() -> None:
    with pytest.raises(ValidationError):
        make(app_env="production")
    with pytest.raises(ValidationError):
        make(app_env="production", session_secret="x" * 40, admin_password="change-me-now")


def test_production_accepts_real_values() -> None:
    s = make(app_env="production", session_secret="a" * 40, admin_password="ein-starkes-passwort")
    assert s.app_env == "production"


def test_development_keeps_defaults() -> None:
    assert make().app_env == "development"
