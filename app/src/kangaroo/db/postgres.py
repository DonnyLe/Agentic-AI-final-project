"""Postgres implementation of the repository (async SQLAlchemy + psycopg)."""

import uuid

from sqlalchemy import func, select, update
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncEngine, async_sessionmaker, create_async_engine

from kangaroo.db.records import (
    CaseSource,
    CaseSummary,
    EvaluationRecord,
    ReviewChoice,
    ReviewRecord,
    StoredCase,
    TraceRecord,
)
from kangaroo.db.tables import (
    CaseRow,
    EvaluationRow,
    GoldenLabelRow,
    ReviewerDecisionRow,
    TraceEventRow,
)
from kangaroo.models.case import Case
from kangaroo.models.decision import Decision
from kangaroo.models.golden import GoldenLabel
from kangaroo.models.trace import TraceEvent


def make_engine(url: str) -> AsyncEngine:
    # Neon closes idle connections; pre-ping avoids handing out dead ones.
    return create_async_engine(url, pool_pre_ping=True)


class PostgresRepository:
    def __init__(self, engine: AsyncEngine) -> None:
        self.engine = engine
        self._session = async_sessionmaker(engine, expire_on_commit=False)

    # --- cases -------------------------------------------------------------

    async def upsert_cases(self, cases: list[Case], source: CaseSource) -> None:
        if not cases:
            return

        rows = [
            {"id": case.id, "content": case.content.model_dump(mode="json"), "source": source}
            for case in cases
        ]
        statement = insert(CaseRow).values(rows)
        statement = statement.on_conflict_do_update(
            index_elements=[CaseRow.id],
            set_={"content": statement.excluded.content, "source": statement.excluded.source},
        )

        async with self._session.begin() as session:
            await session.execute(statement)

    async def upsert_golden_labels(self, labels: list[GoldenLabel]) -> None:
        if not labels:
            return

        statement = insert(GoldenLabelRow).values([label.model_dump() for label in labels])
        statement = statement.on_conflict_do_update(
            index_elements=[GoldenLabelRow.case_id],
            set_={
                "final": statement.excluded.final,
                "notes": statement.excluded.notes,
                "action_tier": statement.excluded.action_tier,
            },
        )

        async with self._session.begin() as session:
            await session.execute(statement)

    async def list_cases(self) -> list[CaseSummary]:
        latest_label = (
            select(EvaluationRow.label)
            .where(EvaluationRow.case_id == CaseRow.id, EvaluationRow.status == "completed")
            .order_by(EvaluationRow.created_at.desc())
            .limit(1)
            .correlate(CaseRow)
            .scalar_subquery()
        )
        query = (
            select(CaseRow, GoldenLabelRow.final, latest_label)
            .outerjoin(GoldenLabelRow, GoldenLabelRow.case_id == CaseRow.id)
            .order_by(CaseRow.id)
        )

        async with self._session() as session:
            rows = (await session.execute(query)).all()

        return [
            CaseSummary(
                id=row.id,
                source=row.source,
                meeting_type=row.content["meeting_type"],
                meeting_date=row.content["meeting_date"],
                candidate_action=row.content["candidate_action"],
                golden_label=golden,
                last_label=last_label,
            )
            for row, golden, last_label in rows
        ]

    async def get_case(self, case_id: str) -> StoredCase | None:
        query = (
            select(CaseRow, GoldenLabelRow)
            .outerjoin(GoldenLabelRow, GoldenLabelRow.case_id == CaseRow.id)
            .where(CaseRow.id == case_id)
        )

        async with self._session() as session:
            found = (await session.execute(query)).first()

        if found is None:
            return None

        row, golden = found

        return StoredCase(
            case=Case.model_validate({"id": row.id, "content": row.content}),
            source=row.source,
            golden=GoldenLabel.model_validate(golden, from_attributes=True) if golden else None,
        )

    async def next_custom_case_id(self) -> str:
        query = select(func.count()).select_from(CaseRow).where(CaseRow.source == "custom")

        async with self._session() as session:
            count = await session.scalar(query)

        return f"C-{(count or 0) + 1:03d}"

    # --- evaluations -------------------------------------------------------

    async def create_evaluation(
        self,
        evaluation_id: uuid.UUID,
        case_id: str,
        models: dict[str, str],
        policy_version: str,
        golden_label: str | None,
    ) -> None:
        async with self._session.begin() as session:
            session.add(
                EvaluationRow(
                    id=evaluation_id,
                    case_id=case_id,
                    status="running",
                    models=models,
                    policy_version=policy_version,
                    golden_label=golden_label,
                )
            )

    async def complete_evaluation(
        self, evaluation_id: uuid.UUID, decision: Decision, golden_match: bool | None
    ) -> None:
        statement = (
            update(EvaluationRow)
            .where(EvaluationRow.id == evaluation_id)
            .values(
                status="completed",
                verdict=decision.verdict.value,
                tier=decision.tier,
                label=decision.label,
                rule_ids=decision.rule_ids,
                rationale=decision.rationale,
                proposed_action=decision.proposed_action.model_dump(mode="json"),
                cited_segment_ids=decision.cited_segment_ids,
                evidence_refs=decision.evidence_refs,
                flags=decision.flags,
                golden_match=golden_match,
                finished_at=func.now(),
            )
        )

        async with self._session.begin() as session:
            await session.execute(statement)

    async def fail_evaluation(self, evaluation_id: uuid.UUID, error: str) -> None:
        statement = (
            update(EvaluationRow)
            .where(EvaluationRow.id == evaluation_id)
            .values(status="failed", error=error, finished_at=func.now())
        )

        async with self._session.begin() as session:
            await session.execute(statement)

    async def get_evaluation(self, evaluation_id: uuid.UUID) -> EvaluationRecord | None:
        async with self._session() as session:
            row = await session.get(EvaluationRow, evaluation_id)

        return EvaluationRecord.model_validate(row, from_attributes=True) if row else None

    async def list_evaluations(
        self, case_id: str | None = None, limit: int = 100
    ) -> list[EvaluationRecord]:
        query = select(EvaluationRow).order_by(EvaluationRow.created_at.desc()).limit(limit)

        if case_id is not None:
            query = query.where(EvaluationRow.case_id == case_id)

        async with self._session() as session:
            rows = (await session.scalars(query)).all()

        return [EvaluationRecord.model_validate(row, from_attributes=True) for row in rows]

    # --- trace -------------------------------------------------------------

    async def append_trace(self, evaluation_id: uuid.UUID, seq: int, event: TraceEvent) -> None:
        async with self._session.begin() as session:
            session.add(
                TraceEventRow(
                    evaluation_id=evaluation_id,
                    seq=seq,
                    node=event.node,
                    kind=event.kind.value,
                    message=event.message,
                    payload=event.payload,
                    at=event.at,
                )
            )

    async def list_trace(self, evaluation_id: uuid.UUID, after_seq: int = 0) -> list[TraceRecord]:
        query = (
            select(TraceEventRow)
            .where(TraceEventRow.evaluation_id == evaluation_id, TraceEventRow.seq > after_seq)
            .order_by(TraceEventRow.seq)
        )

        async with self._session() as session:
            rows = (await session.scalars(query)).all()

        return [
            TraceRecord(
                seq=row.seq,
                event=TraceEvent(
                    node=row.node,
                    kind=row.kind,
                    message=row.message,
                    payload=row.payload,
                    at=row.at,
                ),
            )
            for row in rows
        ]

    # --- reviewer decisions ------------------------------------------------

    async def add_review(
        self, evaluation_id: uuid.UUID, decision: ReviewChoice, reviewer: str, note: str
    ) -> ReviewRecord:
        statement = (
            insert(ReviewerDecisionRow)
            .values(evaluation_id=evaluation_id, decision=decision, reviewer=reviewer, note=note)
            .returning(ReviewerDecisionRow)
        )

        async with self._session.begin() as session:
            row = (await session.scalars(statement)).one()

        return ReviewRecord.model_validate(row, from_attributes=True)

    async def list_reviews(self, evaluation_id: uuid.UUID) -> list[ReviewRecord]:
        query = (
            select(ReviewerDecisionRow)
            .where(ReviewerDecisionRow.evaluation_id == evaluation_id)
            .order_by(ReviewerDecisionRow.created_at)
        )

        async with self._session() as session:
            rows = (await session.scalars(query)).all()

        return [ReviewRecord.model_validate(row, from_attributes=True) for row in rows]

    async def close(self) -> None:
        await self.engine.dispose()
