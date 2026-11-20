"""Alembic environment: async engine, URL from kangaroo settings."""

import asyncio

from alembic import context
from sqlalchemy.engine import Connection

from kangaroo.config import get_settings
from kangaroo.db.postgres import make_engine
from kangaroo.db.tables import Base

target_metadata = Base.metadata


def _run_migrations(connection: Connection) -> None:
    context.configure(connection=connection, target_metadata=target_metadata)

    with context.begin_transaction():
        context.run_migrations()


async def _run_online() -> None:
    engine = make_engine(get_settings().async_database_url)

    async with engine.connect() as connection:
        await connection.run_sync(_run_migrations)

    await engine.dispose()


if context.is_offline_mode():
    raise SystemExit("Offline migrations aren't supported; run against DATABASE_URL.")

asyncio.run(_run_online())
