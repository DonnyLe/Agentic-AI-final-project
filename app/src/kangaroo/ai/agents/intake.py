"""Intake agent: classifies the candidate action and finds who proposed it.

T3/T4 actions stop at the scope gate (`unsupported`) without reaching other agents.
"""

from langchain_core.messages import BaseMessage, HumanMessage, SystemMessage

from kangaroo.ai.agents import guards
from kangaroo.ai.agents.prompts import UNTRUSTED, render_case, tiers_text
from kangaroo.ai.agents.state import Node, RunState, Update, add_flag, emit, guarded
from kangaroo.ai.llm import ModelProvider, structured_call
from kangaroo.ai.tools.evidence import find_injection
from kangaroo.config import Role
from kangaroo.models.agent_io import IntakeResult
from kangaroo.models.case import Case
from kangaroo.models.trace import TraceKind
from kangaroo.policy import Policy


def intake_messages(case: Case, policy: Policy) -> list[BaseMessage]:
    # Only the tier table, not the rules: intake classifies, the adjudicator judges.
    return [
        SystemMessage(
            "You are the intake step of Kangaroo, which checks meeting follow-up actions "
            "against a team policy. Classify the candidate action and pull out who proposed it.\n\n"
            f"Tiers (policy v{policy.version}):\n{tiers_text(policy)}\n\n"
            "Classify the candidate action exactly as written, by the kind of action it takes, "
            "even if the policy may end up redirecting or refusing it. " + UNTRUSTED
        ),
        HumanMessage(render_case(case)),
    ]


def make_intake(models: ModelProvider, policy: Policy) -> Node:
    @guarded("intake", policy)
    async def intake(state: RunState) -> Update:
        result = await structured_call(
            models.for_role(Role.INTAKE), IntakeResult, intake_messages(state.case, policy)
        )
        transcript = " ".join(s.text for s in state.case.content.segments)
        injected = find_injection(transcript + " " + state.case.content.candidate_action)
        flags = add_flag(state.flags, guards.FLAG_POSSIBLE_INJECTION) if injected else state.flags

        emit(
            "intake",
            TraceKind.INTAKE,
            f"{result.action_class} action: {result.action_summary}",
            intake=result.model_dump(mode="json"),
            possible_injection=injected,
        )

        return {"intake": result, "flags": flags}

    return intake


def make_unsupported(policy: Policy) -> Node:
    async def unsupported(state: RunState) -> Update:
        assert state.intake is not None
        tier = state.intake.action_class
        decision = guards.unsupported(tier, policy, state.flags)

        emit(
            "scope", TraceKind.ROUTE, f"{tier} is outside the alpha's scope; no further agents run."
        )
        emit("scope", TraceKind.DECISION, decision.rationale, label=decision.label)

        return {"decision": decision}

    return unsupported
