"""Application settings, read from the environment and app/.env."""

from enum import StrEnum
from functools import lru_cache
from pathlib import Path

from pydantic import SecretStr
from pydantic_settings import BaseSettings, SettingsConfigDict

APP_DIR = Path(__file__).resolve().parents[2]
REPO_DIR = APP_DIR.parent
DATA_DIR = REPO_DIR / "data"


class Role(StrEnum):
    """Agent roles that each get their own model setting."""

    INTAKE = "intake"
    SUPERVISOR = "supervisor"
    EVIDENCE = "evidence"
    ADJUDICATOR = "adjudicator"


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=APP_DIR / ".env", extra="ignore")

    llm_base_url: str = "https://openrouter.ai/api/v1"
    openrouter_api_key: SecretStr = SecretStr("")

    kangaroo_model_default: str = "nvidia/nemotron-3.5-lightning:free"
    kangaroo_model_intake: str = ""
    kangaroo_model_supervisor: str = ""
    kangaroo_model_evidence: str = ""
    kangaroo_model_adjudicator: str = ""

    # Shared across roles; OpenRouter's free tier allows about 20 requests a minute.
    llm_requests_per_minute: float = 16

    database_url: SecretStr = SecretStr("")

    kangaroo_access_token: SecretStr = SecretStr("")
    kangaroo_max_concurrent_runs: int = 2

    def model_for(self, role: Role) -> str:
        """The model ID for a role, falling back to the default."""
        per_role = {
            Role.INTAKE: self.kangaroo_model_intake,
            Role.SUPERVISOR: self.kangaroo_model_supervisor,
            Role.EVIDENCE: self.kangaroo_model_evidence,
            Role.ADJUDICATOR: self.kangaroo_model_adjudicator,
        }

        return per_role[role].strip() or self.kangaroo_model_default

    @property
    def async_database_url(self) -> str:
        """DATABASE_URL rewritten for SQLAlchemy's async psycopg driver."""
        url = self.database_url.get_secret_value()

        for prefix in ("postgresql://", "postgres://"):
            if url.startswith(prefix):
                return "postgresql+psycopg://" + url.removeprefix(prefix)

        return url


@lru_cache
def get_settings() -> Settings:
    return Settings()
