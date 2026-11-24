"""Repository contract tests.

They run against the in-memory fake by default and also against Neon Postgres
when KANGAROO_LIVE=1. Live runs use TEST- case IDs and delete their rows.
"""

import os
import uuid
from collections.abc import AsyncIterator

import pytest
from corpus import load_cases
from sqlalchemy import delete

from kangaroo.config import get_settings
from kangaroo.db.memory import InMemoryRepository
from kangaroo.db.postgres import PostgresRepository, make_engine
from kangaroo.db.repository import Repository
from kangaroo.db.tables import (
    CaseRow,
    EvaluationRow,
    GoldenLabelRow,
    ReviewerDecisionRow,
    TraceEventRow,
)
from kangaroo.models.case import Case
from kangaroo.models.decision import Decision, ProposedAction, Restrictiveness, Verdict
from kangaroo.models.golden import GoldenLabel
from kangaroo.models.trace import TraceEvent, TraceKind

LIVE = os.environ.get("KANGAROO_LIVE") == "1"


@pytest.fixture(
    params=[
        "memory",
        pytest.param(
            "postgres",
            marks=[pytest.mark.live, pytest.mark.skipif(not LIVE, reason="set KANGAROO_LIVE=1")],
        ),
    ]
)
async def contract_repo(request: pytest.FixtureRequest) -> AsyncIterator[Repository]:
    if request.param == "memory":
        yield InMemoryRepository()
        return

    engine = make_engine(get_settings().async_database_url)
    yield PostgresRepository(engine)

    async with engine.begin() as conn:
        test_evals = EvaluationRow.case_id.like("TEST-%")
        eval_ids = EvaluationRow.__table__.select().with_only_columns(EvaluationRow.id)
        eval_ids = eval_ids.where(test_evals)
        await conn.execute(delete(TraceEventRow).where(TraceEventRow.evaluation_id.in_(eval_ids)))
        await conn.execute(
            delete(ReviewerDecisionRow).where(ReviewerDecisionRow.evaluation_id.in_(eval_ids))
        )
        await conn.execute(delete(EvaluationRow).where(test_evals))
        await conn.execute(delete(GoldenLabelRow).where(GoldenLabelRow.case_id.like("TEST-%")))
        await conn.execute(delete(CaseRow).where(CaseRow.id.like("TEST-%")))

    await engine.dispose()


def make_case(suffix: str = "") -> Case:
    return load_cases()[0].model_copy(update={"id": f"TEST-{uuid.uuid4().hex[:8]}{suffix}"})


def make_decision() -> Decision:
    return Decision(
        verdict=Verdict.VIOLATION,
        tier="T2",
        rule_ids=["R2.3"],
        rationale="Version exists but no upstream report supports the cause.",
        cited_segment_ids=["M-054-S03"],
        evidence_refs=["package_registry_lookup"],
        proposed_action=ProposedAction(
            restrictiveness=Restrictiveness.FLAG,
            summary="File with the third-party cause marked unverified.",
            requires_approval=True,
            approver="an engineer who is not a proposer",
        ),
        policy_version="1.3",
    )


async def test_cases_round_trip_with_golden_label(contract_repo: Repository) -> None:
    first, second = make_case("a"), make_case("b")
    await contract_repo.upsert_cases([first, second], source="corpus")
    await contract_repo.upsert_golden_labels(
        [GoldenLabel(case_id=second.id, final="none", notes="agreed", action_tier="T1")]
    )

    stored = await contract_repo.get_case(second.id)
    listed = {s.id: s for s in await contract_repo.list_cases()}

    assert stored is not None
    assert stored.case == second
    assert stored.golden is not None
    assert stored.golden.final == "none"
    assert listed[first.id].golden_label is None
    assert listed[second.id].golden_label == "none"
    assert await contract_repo.get_case("TEST-missing") is None


async def test_upsert_replaces_content(contract_repo: Repository) -> None:
    case = make_case()
    changed = case.model_copy(
        update={"content": case.content.model_copy(update={"candidate_action": "changed"})}
    )

    await contract_repo.upsert_cases([case], source="corpus")
    await contract_repo.upsert_cases([changed], source="corpus")

    stored = await contract_repo.get_case(case.id)

    assert stored is not None
    assert stored.case.content.candidate_action == "changed"


async def test_evaluation_lifecycle_and_trace(contract_repo: Repository) -> None:
    case = make_case()
    evaluation_id = uuid.uuid4()
    await contract_repo.upsert_cases([case], source="corpus")
    await contract_repo.create_evaluation(
        evaluation_id, case.id, {"default": "m"}, "1.3", golden_label="T2 R2.3"
    )

    for seq, kind in enumerate([TraceKind.INTAKE, TraceKind.ROUTE, TraceKind.DECISION], start=1):
        await contract_repo.append_trace(
            evaluation_id, seq, TraceEvent(node="n", kind=kind, message=kind.value)
        )

    await contract_repo.complete_evaluation(evaluation_id, make_decision(), golden_match=True)

    evaluation = await contract_repo.get_evaluation(evaluation_id)
    trace_after_one = await contract_repo.list_trace(evaluation_id, after_seq=1)
    listed = {s.id: s for s in await contract_repo.list_cases()}
    history = await contract_repo.list_evaluations(case_id=case.id)

    assert evaluation is not None
    assert evaluation.status == "completed"
    assert evaluation.label == "T2 R2.3"
    assert evaluation.rule_ids == ["R2.3"]
    assert evaluation.golden_match is True
    assert evaluation.proposed_action is not None
    assert evaluation.proposed_action.restrictiveness == Restrictiveness.FLAG
    assert evaluation.finished_at is not None
    assert [r.seq for r in trace_after_one] == [2, 3]
    assert trace_after_one[0].event.kind == TraceKind.ROUTE
    assert listed[case.id].last_label == "T2 R2.3"
    assert [h.id for h in history] == [evaluation_id]


async def test_failed_evaluation_and_reviews(contract_repo: Repository) -> None:
    case = make_case()
    evaluation_id = uuid.uuid4()
    await contract_repo.upsert_cases([case], source="corpus")
    await contract_repo.create_evaluation(evaluation_id, case.id, {}, "1.3", golden_label=None)
    await contract_repo.fail_evaluation(evaluation_id, "model timeout")
    review = await contract_repo.add_review(
        evaluation_id, "reject", "Maya Chen", "not a real commitment"
    )

    evaluation = await contract_repo.get_evaluation(evaluation_id)
    reviews = await contract_repo.list_reviews(evaluation_id)

    assert evaluation is not None
    assert evaluation.status == "failed"
    assert evaluation.error == "model timeout"
    assert [r.id for r in reviews] == [review.id]
    assert reviews[0].decision == "reject"
    assert await contract_repo.get_evaluation(uuid.uuid4()) is None


async def test_custom_case_ids(repo: InMemoryRepository) -> None:
    assert await repo.next_custom_case_id() == "C-001"

    await repo.upsert_cases([make_case().model_copy(update={"id": "C-001"})], source="custom")

    assert await repo.next_custom_case_id() == "C-002"
