import pytest
from pydantic import ValidationError

from tests.conftest import make_settings


def test_plain_postgres_urls_get_the_psycopg_driver() -> None:
    supabase_style = "postgres://user:pw@db.example.supabase.co:5432/postgres"

    settings = make_settings(DATABASE_URL=supabase_style)

    assert (
        settings.database_url == "postgresql+psycopg://user:pw@db.example.supabase.co:5432/postgres"
    )


def test_non_postgres_database_url_is_rejected() -> None:
    with pytest.raises(ValidationError, match="PostgreSQL"):
        make_settings(DATABASE_URL="mysql://user@localhost/db")


def test_cors_origins_parse_from_comma_separated_string() -> None:
    settings = make_settings(CORS_ALLOWED_ORIGINS="http://a.test, http://b.test/")

    assert settings.cors_allowed_origins == ["http://a.test", "http://b.test"]


def test_wildcard_cors_is_refused_in_production() -> None:
    with pytest.raises(ValidationError, match="production"):
        make_settings(FINPULSE_ENV="production", CORS_ALLOWED_ORIGINS="*")


def test_log_level_is_case_insensitive() -> None:
    assert make_settings(LOG_LEVEL="debug").log_level == "DEBUG"


def test_unknown_environment_is_rejected() -> None:
    with pytest.raises(ValidationError):
        make_settings(FINPULSE_ENV="prod")
