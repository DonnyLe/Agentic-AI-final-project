import pytest

from kangaroo.db.memory import InMemoryRepository


@pytest.fixture
def repo() -> InMemoryRepository:
    """Fake repository; tests never touch a real database unless marked live."""
    return InMemoryRepository()
