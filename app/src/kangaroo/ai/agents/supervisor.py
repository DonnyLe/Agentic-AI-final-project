"""Supervisor agent: picks the next step (gather evidence, adjudicate or escalate)."""

from langchain_core.messages import BaseMessage, HumanMessage, SystemMessage

from kangaroo.ai.agents import guards
from kangaroo.ai.agents.prompts import UNTRUSTED, render_case, rules_text
from kangaroo.ai.agents.state import Node, RunState, Update, add_flag, emit, guarded
from kangaroo.ai.llm import ModelProvider, structured_call
from kangaroo.config import Role
from kangaroo.models.agent_io import EvidenceFinding, IntakeResult, SupervisorDecision
from kangaroo.models.case import Case
from kangaroo.models.trace import TraceKind
from kangaroo.policy import Policy


def supervisor_messages(
    case: Case,
    intake: IntakeResult,
    policy: Policy,
    findings: list[EvidenceFinding],
    rounds: int,
    max_rounds: int,
) -> list[BaseMessage]:
    gathered = "\n".join(f"- {f.task}: {f.status}. {f.summary}" for f in findings) or "none yet"

    return [
        SystemMessage(
            "You are the supervisor of Kangaroo. Decide the next step for this case: gather "
            "only the evidence this case needs, adjudicate once the evidence is enough, or "
            "escalate if it can't be settled. Evidence tasks:\n"
            "- duplicate_search: search open tickets for a matching defect\n"
            "- ticket_details: read a specific ticket\n"
            "- dependency_check: registry and upstream-issue lookups for a blamed library\n"
            "- roster_check: roster, owners and recorded approvals\n"
            "- transcript_check: re-read specific transcript segments\n"
            "T1 records are settled from the transcript alone, so for T1 choose adjudicate "
            "unless a specific segment must be re-read. Ask for dependency_check only when "
            "someone blames a third-party library or service. Escalate only when required "
            "evidence is missing or contradictory or a needed person or ticket can't be "
            "identified. A case that already looks like a policy violation is not a reason to "
            "escalate: that's the adjudicator's decision, so choose adjudicate. " + UNTRUSTED
        ),
        HumanMessage(
            f"{render_case(case)}\n\n"
            f"Intake: {intake.model_dump_json()}\n\n"
            f"Policy rules for {intake.action_class}:\n{rules_text(policy, intake.action_class)}"
            f"\n\nEvidence gathered so far:\n{gathered}\n\n"
            f"Evidence rounds used: {rounds} of {max_rounds}."
        ),
    ]


def make_supervisor(models: ModelProvider, policy: Policy, max_rounds: int) -> Node:
    @guarded("supervisor", policy)
    async def supervisor(state: RunState) -> Update:
        assert state.intake is not None
        decision = await structured_call(
            models.for_role(Role.SUPERVISOR),
            SupervisorDecision,
            supervisor_messages(
                state.case, state.intake, policy, state.findings, state.rounds, max_rounds
            ),
        )
        note = ""
        flags = state.flags

        if decision.next_step == "gather_evidence" and state.rounds >= max_rounds:
            # Evidence still wanted after the last round means it's missing: pause for a human.
            note = f"Evidence round limit ({max_rounds}) reached with evidence still missing."
            wanted = ", ".join(task.value for task in decision.evidence_tasks)
            reason = f"Evidence still missing after {max_rounds} rounds ({wanted}). "
            reason += decision.reason
            decision = decision.model_copy(
                update={"next_step": "escalate", "evidence_tasks": [], "reason": reason}
            )
            flags = add_flag(flags, guards.FLAG_EVIDENCE_INCOMPLETE)
        elif decision.next_step == "gather_evidence" and not decision.evidence_tasks:
            note = "No evidence tasks given; adjudicating."
            decision = decision.model_copy(update={"next_step": "adjudicate"})

        emit(
            "supervisor",
            TraceKind.ROUTE,
            f"{decision.next_step}: {decision.reason}" + (f" ({note})" if note else ""),
            next_step=decision.next_step,
            evidence_tasks=[task.value for task in decision.evidence_tasks],
            round=state.rounds,
        )

        return {"supervisor": decision, "flags": flags}

    return supervisor


def make_escalate(policy: Policy) -> Node:
    async def escalate(state: RunState) -> Update:
        reason = state.supervisor.reason if state.supervisor else "Escalated."
        tier = state.intake.action_class if state.intake else None
        decision = guards.needs_review(reason, policy, tier=tier, flags=state.flags)

        emit("supervisor", TraceKind.DECISION, f"Escalated: {reason}", label=decision.label)

        return {"decision": decision}

    return escalate
