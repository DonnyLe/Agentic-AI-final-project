"""The storage interface the rest of the app depends on.

`PostgresRepository` (kangaroo.db.postgres) is the real implementation.
`InMemoryRepository` (kangaroo.db.memory) is a fake for tests.
"""

import uuid
from typing import Protocol

from kangaroo.db.records import (
    CaseSource,
    CaseSummary,
    EvaluationRecord,
    ReviewChoice,
    ReviewRecord,
    StoredCase,
    TraceRecord,
)
from kangaroo.models.case import Case
from kangaroo.models.decision import Decision
from kangaroo.models.golden import GoldenLabel
from kangaroo.models.trace import TraceEvent


class Repository(Protocol):
    async def upsert_cases(self, cases: list[Case], source: CaseSource) -> None: ...

    async def upsert_golden_labels(self, labels: list[GoldenLabel]) -> None: ...

    async def list_cases(self) -> list[CaseSummary]: ...

    async def get_case(self, case_id: str) -> StoredCase | None: ...

    async def next_custom_case_id(self) -> str: ...

    async def create_evaluation(
        self,
        evaluation_id: uuid.UUID,
        case_id: str,
        models: dict[str, str],
        policy_version: str,
        golden_label: str | None,
    ) -> None: ...

    async def complete_evaluation(
        self, evaluation_id: uuid.UUID, decision: Decision, golden_match: bool | None
    ) -> None: ...

    async def fail_evaluation(self, evaluation_id: uuid.UUID, error: str) -> None: ...

    async def get_evaluation(self, evaluation_id: uuid.UUID) -> EvaluationRecord | None: ...

    async def list_evaluations(
        self, case_id: str | None = None, limit: int = 100
    ) -> list[EvaluationRecord]: ...

    async def append_trace(self, evaluation_id: uuid.UUID, seq: int, event: TraceEvent) -> None: ...

    async def list_trace(
        self, evaluation_id: uuid.UUID, after_seq: int = 0
    ) -> list[TraceRecord]: ...

    async def add_review(
        self, evaluation_id: uuid.UUID, decision: ReviewChoice, reviewer: str, note: str
    ) -> ReviewRecord: ...

    async def list_reviews(self, evaluation_id: uuid.UUID) -> list[ReviewRecord]: ...

    async def close(self) -> None: ...
