from pydantic import SecretStr

from kangaroo.config import Role, Settings


def make_settings(**overrides: str) -> Settings:
    return Settings(_env_file=None, **overrides)


def test_role_model_falls_back_to_default() -> None:
    settings = make_settings(kangaroo_model_default="base", kangaroo_model_adjudicator="judge")

    assert settings.model_for(Role.INTAKE) == "base"
    assert settings.model_for(Role.ADJUDICATOR) == "judge"


def test_async_database_url_uses_psycopg_driver() -> None:
    settings = make_settings()
    settings.database_url = SecretStr("postgresql://u:p@host/db?sslmode=require")

    assert settings.async_database_url == "postgresql+psycopg://u:p@host/db?sslmode=require"
