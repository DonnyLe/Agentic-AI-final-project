"""Load the FP2 corpus and golden labels into the database.

Usage: uv run python -m kangaroo.seed
Safe to re-run: rows are upserted by ID.
"""

import asyncio

from kangaroo.config import get_settings
from kangaroo.corpus import load_cases, load_golden_labels
from kangaroo.db.postgres import PostgresRepository, make_engine


async def seed() -> tuple[int, int]:
    cases = load_cases()
    golden = load_golden_labels()
    engine = make_engine(get_settings().async_database_url)

    try:
        repo = PostgresRepository(engine)
        await repo.upsert_cases(cases, source="corpus")
        await repo.upsert_golden_labels(golden)
    finally:
        await engine.dispose()

    return len(cases), len(golden)


def main() -> None:
    case_count, golden_count = asyncio.run(seed())
    print(f"seeded {case_count} cases and {golden_count} golden labels")


if __name__ == "__main__":
    main()
