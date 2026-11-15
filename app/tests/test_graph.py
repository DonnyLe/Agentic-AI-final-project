"""Graph routing tests with scripted models (no network)."""

from fakes import ScriptedModels, structured, tool_reply
from langchain_core.messages import AIMessage

from kangaroo.config import Role
from kangaroo.corpus import load_cases
from kangaroo.graph import build_graph, stream_run
from kangaroo.guards import FLAG_POSSIBLE_INJECTION
from kangaroo.models.agent_io import (
    AdjudicatorOutput,
    EvidenceFinding,
    EvidenceReport,
    EvidenceTask,
    IntakeResult,
    SupervisorDecision,
)
from kangaroo.models.case import Case
from kangaroo.models.decision import Decision, Verdict
from kangaroo.models.trace import TraceEvent, TraceKind
from kangaroo.policy import load_policy

CASES = {case.id: case for case in load_cases()}
POLICY = load_policy()


def intake(tier: str, proposers: list[str] | None = None) -> AIMessage:
    return structured(
        IntakeResult(
            action_class=tier,
            action_summary="do the thing",
            proposers=proposers or ["Aisha Rahman"],
            cited_segment_ids=[],
        )
    )


def route(step: str, tasks: list[EvidenceTask] | None = None) -> AIMessage:
    return structured(SupervisorDecision(next_step=step, evidence_tasks=tasks or [], reason="why"))


def verdict(kind: str, rules: list[str] | None = None) -> AIMessage:
    return structured(
        AdjudicatorOutput(verdict=kind, broken_rule_ids=rules or [], rationale="because")
    )


def report(*tasks: EvidenceTask) -> AIMessage:
    findings = [EvidenceFinding(task=t, status="confirmed", summary="found it") for t in tasks]

    return structured(EvidenceReport(findings=findings))


async def run(models: ScriptedModels, case: Case) -> tuple[Decision, list[TraceEvent]]:
    events: list[TraceEvent] = []
    decision: Decision | None = None

    async for item in stream_run(build_graph(models, POLICY), case):
        if isinstance(item, Decision):
            decision = item
        else:
            events.append(item)

    assert decision is not None

    return decision, events


def routes(events: list[TraceEvent]) -> list[str]:
    return [e.payload.get("next_step", "") for e in events if e.kind == TraceKind.ROUTE]


async def test_t1_goes_straight_to_the_adjudicator() -> None:
    models = ScriptedModels(
        {
            Role.INTAKE: [intake("T1")],
            Role.SUPERVISOR: [route("adjudicate")],
            Role.EVIDENCE: [],
            Role.ADJUDICATOR: [verdict("violation", ["R1.1"])],
        }
    )

    decision, events = await run(models, CASES["K-012"])

    assert decision.label == "T1 R1.1"
    assert routes(events) == ["adjudicate"]
    assert not models.models[Role.EVIDENCE].calls
    assert not any(e.kind == TraceKind.TOOL_CALL for e in events)


async def test_t2_with_a_blamed_library_checks_duplicates_and_the_dependency() -> None:
    tasks = [EvidenceTask.DUPLICATE_SEARCH, EvidenceTask.DEPENDENCY_CHECK]
    models = ScriptedModels(
        {
            Role.INTAKE: [intake("T2")],
            Role.SUPERVISOR: [route("gather_evidence", tasks), route("adjudicate")],
            Role.EVIDENCE: [
                tool_reply("search_tickets", {"query": "refresh token invalid_signature"}),
                tool_reply("verify_dependency", {"package": "jwt-verify-lite"}),
                AIMessage(content="done"),
                report(*tasks),
            ],
            Role.ADJUDICATOR: [verdict("violation", ["R2.3"])],
        }
    )

    decision, events = await run(models, CASES["K-054"])

    tool_calls = [e.message for e in events if e.kind == TraceKind.TOOL_CALL]
    adjudicator_prompt = models.models[Role.ADJUDICATOR].calls[0][-1].content

    assert decision.label == "T2 R2.3"
    assert decision.proposed_action.requires_approval
    assert routes(events) == ["gather_evidence", "adjudicate"]
    assert tool_calls == ["search_tickets", "verify_dependency"]
    assert "jwt-verify-lite 4.2.0" in adjudicator_prompt


async def test_t2_without_a_library_skips_the_dependency_check_and_flags_injection() -> None:
    models = ScriptedModels(
        {
            Role.INTAKE: [intake("T2")],
            Role.SUPERVISOR: [
                route("gather_evidence", [EvidenceTask.DUPLICATE_SEARCH]),
                route("adjudicate"),
            ],
            Role.EVIDENCE: [
                tool_reply("get_ticket", {"ticket_id": "JOB-388"}),
                AIMessage(content="done"),
                report(EvidenceTask.DUPLICATE_SEARCH),
            ],
            Role.ADJUDICATOR: [verdict("violation", ["R2.2"])],
        }
    )

    decision, events = await run(models, CASES["K-109"])

    route_events = [e for e in events if e.kind == TraceKind.ROUTE]

    assert route_events[0].payload["evidence_tasks"] == ["duplicate_search"]
    assert decision.label == "T2 R2.2"
    assert FLAG_POSSIBLE_INJECTION in decision.flags
    assert "Link the report" in decision.proposed_action.summary


async def test_t3_is_unsupported_without_calling_the_supervisor() -> None:
    models = ScriptedModels(
        {Role.INTAKE: [intake("T3")], Role.SUPERVISOR: [], Role.EVIDENCE: [], Role.ADJUDICATOR: []}
    )

    decision, _ = await run(models, CASES["K-063"])

    assert decision.verdict == Verdict.UNSUPPORTED
    assert not models.models[Role.SUPERVISOR].calls


async def test_bad_rules_get_one_repair_then_needs_review() -> None:
    models = ScriptedModels(
        {
            Role.INTAKE: [intake("T1")],
            Role.SUPERVISOR: [route("adjudicate")],
            Role.EVIDENCE: [],
            Role.ADJUDICATOR: [verdict("violation", ["R2.3"]), verdict("violation", ["R9.9"])],
        }
    )

    decision, events = await run(models, CASES["K-012"])

    assert decision.verdict == Verdict.NEEDS_REVIEW
    assert sum(e.kind == TraceKind.GUARD for e in events) == 2
    assert "fix them" in models.models[Role.ADJUDICATOR].calls[1][-1].content


async def test_repair_that_works_is_accepted() -> None:
    models = ScriptedModels(
        {
            Role.INTAKE: [intake("T1")],
            Role.SUPERVISOR: [route("adjudicate")],
            Role.EVIDENCE: [],
            Role.ADJUDICATOR: [verdict("violation", ["R2.3"]), verdict("violation", ["R1.2"])],
        }
    )

    decision, _ = await run(models, CASES["K-020"])

    assert decision.label == "T1 R1.2"


async def test_model_failure_ends_in_needs_review() -> None:
    models = ScriptedModels(
        {
            Role.INTAKE: [AIMessage(content="I can't"), AIMessage(content="still no")],
            Role.SUPERVISOR: [],
            Role.EVIDENCE: [],
            Role.ADJUDICATOR: [],
        }
    )

    decision, events = await run(models, CASES["K-002"])

    assert decision.verdict == Verdict.NEEDS_REVIEW
    assert events[-1].kind == TraceKind.ERROR


async def test_evidence_rounds_are_capped() -> None:
    task = [EvidenceTask.DUPLICATE_SEARCH]
    one_round = [AIMessage(content="nothing to call"), report(*task)]
    models = ScriptedModels(
        {
            Role.INTAKE: [intake("T2")],
            Role.SUPERVISOR: [route("gather_evidence", task)] * 3,
            Role.EVIDENCE: one_round * 2,
            Role.ADJUDICATOR: [verdict("no_violation")],
        }
    )

    decision, events = await run(models, CASES["K-051"])

    assert decision.label == "none"
    assert routes(events) == ["gather_evidence", "gather_evidence", "adjudicate"]


async def test_escalation() -> None:
    models = ScriptedModels(
        {
            Role.INTAKE: [intake("T2")],
            Role.SUPERVISOR: [route("escalate")],
            Role.EVIDENCE: [],
            Role.ADJUDICATOR: [],
        }
    )

    decision, _ = await run(models, CASES["K-051"])

    assert decision.verdict == Verdict.NEEDS_REVIEW
