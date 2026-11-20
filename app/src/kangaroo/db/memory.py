"""In-memory fake of the repository, for tests. Same interface as PostgresRepository."""

import uuid
from datetime import UTC, datetime

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


class InMemoryRepository:
    def __init__(self) -> None:
        self.cases: dict[str, tuple[Case, CaseSource]] = {}
        self.golden: dict[str, GoldenLabel] = {}
        self.evaluations: dict[uuid.UUID, EvaluationRecord] = {}
        self.trace: dict[uuid.UUID, list[TraceRecord]] = {}
        self.reviews: list[ReviewRecord] = []

    async def upsert_cases(self, cases: list[Case], source: CaseSource) -> None:
        for case in cases:
            self.cases[case.id] = (case, source)

    async def upsert_golden_labels(self, labels: list[GoldenLabel]) -> None:
        self.golden.update({label.case_id: label for label in labels})

    async def list_cases(self) -> list[CaseSummary]:
        return [
            CaseSummary(
                id=case_id,
                source=source,
                meeting_type=case.content.meeting_type,
                meeting_date=case.content.meeting_date.isoformat()
                if case.content.meeting_date
                else None,
                candidate_action=case.content.candidate_action,
                golden_label=self.golden[case_id].final if case_id in self.golden else None,
                last_label=self._latest_label(case_id),
            )
            for case_id, (case, source) in sorted(self.cases.items())
        ]

    async def get_case(self, case_id: str) -> StoredCase | None:
        if case_id not in self.cases:
            return None

        case, source = self.cases[case_id]

        return StoredCase(case=case, source=source, golden=self.golden.get(case_id))

    async def next_custom_case_id(self) -> str:
        count = sum(1 for _, source in self.cases.values() if source == "custom")

        return f"C-{count + 1:03d}"

    async def create_evaluation(
        self,
        evaluation_id: uuid.UUID,
        case_id: str,
        models: dict[str, str],
        policy_version: str,
        golden_label: str | None,
    ) -> None:
        self.evaluations[evaluation_id] = EvaluationRecord(
            id=evaluation_id,
            case_id=case_id,
            status="running",
            verdict=None,
            tier=None,
            label=None,
            rule_ids=[],
            rationale="",
            proposed_action=None,
            cited_segment_ids=[],
            evidence_refs=[],
            flags=[],
            models=dict(models),
            policy_version=policy_version,
            golden_label=golden_label,
            golden_match=None,
            error=None,
            created_at=datetime.now(UTC),
            finished_at=None,
        )

    async def complete_evaluation(
        self, evaluation_id: uuid.UUID, decision: Decision, golden_match: bool | None
    ) -> None:
        self.evaluations[evaluation_id] = self.evaluations[evaluation_id].model_copy(
            update={
                "status": "completed",
                "verdict": decision.verdict.value,
                "tier": decision.tier,
                "label": decision.label,
                "rule_ids": decision.rule_ids,
                "rationale": decision.rationale,
                "proposed_action": decision.proposed_action,
                "cited_segment_ids": decision.cited_segment_ids,
                "evidence_refs": decision.evidence_refs,
                "flags": decision.flags,
                "golden_match": golden_match,
                "finished_at": datetime.now(UTC),
            }
        )

    async def fail_evaluation(self, evaluation_id: uuid.UUID, error: str) -> None:
        self.evaluations[evaluation_id] = self.evaluations[evaluation_id].model_copy(
            update={"status": "failed", "error": error, "finished_at": datetime.now(UTC)}
        )

    async def get_evaluation(self, evaluation_id: uuid.UUID) -> EvaluationRecord | None:
        return self.evaluations.get(evaluation_id)

    async def list_evaluations(
        self, case_id: str | None = None, limit: int = 100
    ) -> list[EvaluationRecord]:
        records = sorted(self.evaluations.values(), key=lambda r: r.created_at, reverse=True)

        return [r for r in records if case_id is None or r.case_id == case_id][:limit]

    async def append_trace(self, evaluation_id: uuid.UUID, seq: int, event: TraceEvent) -> None:
        self.trace.setdefault(evaluation_id, []).append(TraceRecord(seq=seq, event=event))

    async def list_trace(self, evaluation_id: uuid.UUID, after_seq: int = 0) -> list[TraceRecord]:
        return [r for r in self.trace.get(evaluation_id, []) if r.seq > after_seq]

    async def add_review(
        self, evaluation_id: uuid.UUID, decision: ReviewChoice, reviewer: str, note: str
    ) -> ReviewRecord:
        record = ReviewRecord(
            id=len(self.reviews) + 1,
            evaluation_id=evaluation_id,
            decision=decision,
            reviewer=reviewer,
            note=note,
            created_at=datetime.now(UTC),
        )
        self.reviews.append(record)

        return record

    async def list_reviews(self, evaluation_id: uuid.UUID) -> list[ReviewRecord]:
        return [r for r in self.reviews if r.evaluation_id == evaluation_id]

    async def close(self) -> None:
        return None

    def _latest_label(self, case_id: str) -> str | None:
        completed = [
            r for r in self.evaluations.values() if r.case_id == case_id and r.status == "completed"
        ]

        return max(completed, key=lambda r: r.created_at).label if completed else None
