"""Application settings, read from the environment and an env file.

Local dev reads app/.env. With KANGAROO_ENV=prod, app/.env.prod is read instead,
for running migrations against the deployed (Neon) database.
Real environment variables always win over either file.
"""

import logging
import os
from enum import StrEnum
from functools import lru_cache
from pathlib import Path

from pydantic import SecretStr
from pydantic_settings import BaseSettings, SettingsConfigDict
from rich.console import Console
from rich.logging import RichHandler

APP_DIR = Path(__file__).resolve().parents[2]
REPO_DIR = APP_DIR.parent
DATA_DIR = REPO_DIR / "data"
ENV_FILE = APP_DIR / (".env.prod" if os.environ.get("KANGAROO_ENV") == "prod" else ".env")


class Role(StrEnum):
    """Agent roles that each get their own model setting."""

    INTAKE = "intake"
    SUPERVISOR = "supervisor"
    EVIDENCE = "evidence"
    ADJUDICATOR = "adjudicator"


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=ENV_FILE, extra="ignore")

    llm_base_url: str = "https://openrouter.ai/api/v1"
    openrouter_api_key: SecretStr = SecretStr("")

    kangaroo_model_default: str = "nvidia/nemotron-3.5-lightning:free"
    kangaroo_model_intake: str = ""
    kangaroo_model_supervisor: str = ""
    kangaroo_model_evidence: str = ""
    kangaroo_model_adjudicator: str = ""

    # Shared across roles; OpenRouter's free tier allows about 20 requests a minute.
    llm_requests_per_minute: float = 16

    # Workers AI, for the Clef-flash decision model (kangaroo.ai.decision_model).
    cloudflare_account_id: str = ""
    cloudflare_api_token: SecretStr = SecretStr("")

    database_url: SecretStr = SecretStr("")

    kangaroo_access_token: SecretStr = SecretStr("")
    kangaroo_max_concurrent_runs: int = 2
    kangaroo_log_level: str = "INFO"

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


# Libraries that log every request at INFO.
QUIET_LOGGERS = ("httpx", "httpcore", "openai")


def setup_logging(level: str = "INFO") -> None:
    """Send all logging through Rich. Safe to call more than once."""
    handler = RichHandler(
        console=Console(stderr=True),
        rich_tracebacks=True,
        markup=False,  # log messages carry case text, which may contain [brackets]
        show_path=False,
    )
    handler.setFormatter(logging.Formatter("%(name)s  %(message)s", datefmt="[%X]"))

    root = logging.getLogger()
    root.handlers = [handler]
    root.setLevel(level.upper())

    # uvicorn installs its own handlers; route its loggers through ours instead.
    for name in ("uvicorn", "uvicorn.error", "uvicorn.access"):
        uvicorn_logger = logging.getLogger(name)
        uvicorn_logger.handlers = []
        uvicorn_logger.propagate = True

    for name in QUIET_LOGGERS:
        logging.getLogger(name).setLevel(logging.WARNING)
