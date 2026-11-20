"""The Kangaroo agent graph (LangGraph).

intake ─► supervisor ─┬─ tier T3/T4 ─► unsupported
   ▲ (extracts only)  ├─ gather ─────► evidence ─┐
                      ▲                          │
                      └──────────────────────────┘
                      ├─ adjudicate ─► adjudicator (+ guards)
                      └─ escalate ───► needs_review

Intake extracts facts without the policy. The supervisor reads the whole policy and
assigns the tier on its first turn; the tier is then fixed for the rest of the run.

Each node streams TraceEvents through LangGraph's custom stream. Any node that
fails ends the run with a `needs_review` decision instead of a guess.
"""

import json
from collections.abc import AsyncIterator, Awaitable, Callable
from functools import wraps
from typing import Any, Literal

from langchain_core.messages import BaseMessage, ToolMessage
from langgraph.config import get_stream_writer
from langgraph.graph import END, START, StateGraph
from langgraph.graph.state import CompiledStateGraph
from pydantic import BaseModel, Field, JsonValue

from kangaroo import guards
from kangaroo.agents import prompts
from kangaroo.config import Role
from kangaroo.llm import ModelProvider, structured_call, with_retries
from kangaroo.models.agent_io import (
    AdjudicatorOutput,
    EvidenceFinding,
    EvidenceReport,
    IntakeResult,
    SupervisorDecision,
)
from kangaroo.models.case import Case, Tier
from kangaroo.models.decision import Decision
from kangaroo.models.trace import TraceEvent, TraceKind
from kangaroo.policy import Policy
from kangaroo.tools.evidence import EvidenceView, build_evidence_tools, find_injection

MAX_EVIDENCE_ROUNDS = 2
MAX_TOOL_STEPS = 6
LOG_LIMIT = 1500


class RunState(BaseModel):
    case: Case
    intake: IntakeResult | None = None
    supervisor: SupervisorDecision | None = None
    tier: Tier | None = None
    findings: list[EvidenceFinding] = Field(default_factory=list)
    evidence_log: list[str] = Field(default_factory=list)
    rounds: int = 0
    flags: list[str] = Field(default_factory=list)
    decision: Decision | None = None


type Update = dict[str, Any]
type Node = Callable[[RunState], Awaitable[Update]]


def emit(node: str, kind: TraceKind, message: str, **payload: JsonValue) -> None:
    get_stream_writer()(TraceEvent(node=node, kind=kind, message=message, payload=payload))


def _add_flag(flags: list[str], flag: str) -> list[str]:
    return flags if flag in flags else [*flags, flag]


def build_graph(
    models: ModelProvider, policy: Policy, max_rounds: int = MAX_EVIDENCE_ROUNDS
) -> CompiledStateGraph:
    def guarded(name: str) -> Callable[[Node], Node]:
        """Turn any failure inside a node into a needs_review decision."""

        def wrap(node: Node) -> Node:
            @wraps(node)
            async def run(state: RunState) -> Update:
                try:
                    return await node(state)
                except Exception as error:  # noqa: BLE001 - every failure must end in needs_review
                    reason = f"{name} failed: {type(error).__name__}: {error}"
                    emit(name, TraceKind.ERROR, reason)
                    tier = state.tier
                    flags = _add_flag(state.flags, guards.FLAG_AGENT_ERROR)
                    decision = guards.needs_review(reason, policy, tier=tier, flags=flags)

                    return {"decision": decision}

            return run

        return wrap

    @guarded("intake")
    async def intake(state: RunState) -> Update:
        result = await structured_call(
            models.for_role(Role.INTAKE), IntakeResult, prompts.intake_messages(state.case)
        )
        transcript = " ".join(s.text for s in state.case.content.segments)
        injected = find_injection(transcript + " " + state.case.content.candidate_action)
        flags = _add_flag(state.flags, guards.FLAG_POSSIBLE_INJECTION) if injected else state.flags

        emit(
            "intake",
            TraceKind.INTAKE,
            result.action_summary,
            intake=result.model_dump(mode="json"),
            possible_injection=injected,
        )

        return {"intake": result, "flags": flags}

    def after_intake(state: RunState) -> Literal["supervisor", "__end__"]:
        if state.decision is not None or state.intake is None:
            return END

        return "supervisor"

    async def unsupported(state: RunState) -> Update:
        assert state.tier is not None
        tier = state.tier
        decision = guards.unsupported(tier, policy, state.flags)

        emit(
            "scope", TraceKind.ROUTE, f"{tier} is outside the alpha's scope; no further agents run."
        )
        emit("scope", TraceKind.DECISION, decision.rationale, label=decision.label)

        return {"decision": decision}

    @guarded("supervisor")
    async def supervisor(state: RunState) -> Update:
        assert state.intake is not None
        decision = await structured_call(
            models.for_role(Role.SUPERVISOR),
            SupervisorDecision,
            prompts.supervisor_messages(
                state.case,
                state.intake,
                policy,
                state.findings,
                state.rounds,
                max_rounds,
                tier=state.tier,
            ),
        )
        flags = state.flags

        if state.tier is None:
            tier = decision.tier
            hint_tier = guards.hint_tier(state.intake.action_type_hint)
            mismatch = hint_tier is not None and hint_tier != tier

            if mismatch:
                flags = _add_flag(flags, guards.FLAG_TIER_HINT_MISMATCH)

            emit(
                "supervisor",
                TraceKind.ROUTE,
                f"Tier {tier}: {decision.tier_reason}"
                + (f" (intake's hint suggested {hint_tier})" if mismatch else ""),
                tier=tier,
                intake_hint=hint_tier,
            )

            if not guards.is_supported(tier):
                return {"supervisor": decision, "tier": tier, "flags": flags}
        else:
            tier = state.tier

            if decision.tier != tier:
                emit(
                    "supervisor",
                    TraceKind.GUARD,
                    f"Supervisor changed the tier to {decision.tier}; keeping {tier}.",
                )
                decision = decision.model_copy(update={"tier": tier})

        note = ""

        if decision.next_step == "gather_evidence" and state.rounds >= max_rounds:
            note = f"Evidence round limit ({max_rounds}) reached; adjudicating with what we have."
        elif decision.next_step == "gather_evidence" and not decision.evidence_tasks:
            note = "No evidence tasks given; adjudicating."

        if note:
            decision = decision.model_copy(update={"next_step": "adjudicate", "evidence_tasks": []})

        emit(
            "supervisor",
            TraceKind.ROUTE,
            f"{decision.next_step}: {decision.reason}" + (f" ({note})" if note else ""),
            next_step=decision.next_step,
            evidence_tasks=[task.value for task in decision.evidence_tasks],
            round=state.rounds,
        )

        return {"supervisor": decision, "tier": tier, "flags": flags}

    def after_supervisor(
        state: RunState,
    ) -> Literal["unsupported", "evidence", "adjudicator", "escalate", "__end__"]:
        if state.decision is not None or state.supervisor is None or state.tier is None:
            return END

        if not guards.is_supported(state.tier):
            return "unsupported"

        return {
            "gather_evidence": "evidence",
            "adjudicate": "adjudicator",
            "escalate": "escalate",
        }[state.supervisor.next_step]

    @guarded("evidence")
    async def evidence(state: RunState) -> Update:
        assert state.supervisor is not None
        model = models.for_role(Role.EVIDENCE)
        tools = {tool.name: tool for tool in build_evidence_tools(state.case)}
        bound = with_retries(model.bind_tools(list(tools.values())))
        messages: list[BaseMessage] = prompts.evidence_messages(state.case, state.supervisor)
        log = list(state.evidence_log)
        flags = state.flags
        seen: dict[str, str] = {}

        for _ in range(MAX_TOOL_STEPS):
            reply = await bound.ainvoke(messages)
            messages.append(reply)

            if not reply.tool_calls:
                break

            for call in reply.tool_calls:
                key = f"{call['name']}:{json.dumps(call['args'], sort_keys=True)}"

                if key in seen:
                    note = "You already made this exact call; the result is unchanged. Move on."
                    emit(
                        "evidence",
                        TraceKind.TOOL_CALL,
                        f"{call['name']} (repeat)",
                        args=call["args"],
                    )
                    messages.append(ToolMessage(content=note, tool_call_id=call["id"]))
                    continue

                output = await _run_tool(tools, call["name"], call["args"])
                seen[key] = output
                injected = _injection_in(output)

                if injected:
                    flags = _add_flag(flags, guards.FLAG_POSSIBLE_INJECTION)

                emit("evidence", TraceKind.TOOL_CALL, call["name"], args=call["args"])
                emit(
                    "evidence",
                    TraceKind.TOOL_RESULT,
                    f"{call['name']} returned {len(output)} chars",
                    tool=call["name"],
                    output=output[:LOG_LIMIT],
                    possible_injection=injected,
                )
                messages.append(ToolMessage(content=output, tool_call_id=call["id"]))
                log.append(f"{call['name']}({json.dumps(call['args'])}) -> {output[:LOG_LIMIT]}")

        report = await structured_call(
            model, EvidenceReport, prompts.findings_messages(messages, state.supervisor)
        )

        emit(
            "evidence",
            TraceKind.FINDINGS,
            f"{len(report.findings)} finding(s)",
            findings=[f.model_dump(mode="json") for f in report.findings],
        )

        return {
            "findings": [*state.findings, *report.findings],
            "evidence_log": log,
            "rounds": state.rounds + 1,
            "flags": flags,
        }

    def after_evidence(state: RunState) -> Literal["supervisor", "__end__"]:
        return END if state.decision is not None else "supervisor"

    @guarded("adjudicator")
    async def adjudicator(state: RunState) -> Update:
        assert state.intake is not None
        assert state.tier is not None
        tier = state.tier
        model = models.for_role(Role.ADJUDICATOR)
        args = (state.case, state.intake, tier, policy, state.findings, state.evidence_log)

        output = await structured_call(
            model, AdjudicatorOutput, prompts.adjudicator_messages(*args)
        )
        problems = guards.check_adjudication(output, tier, policy)

        if problems:
            emit(
                "guards",
                TraceKind.GUARD,
                "Asked the adjudicator to fix its answer.",
                problems=problems,
            )
            output = await structured_call(
                model, AdjudicatorOutput, prompts.adjudicator_messages(*args, problems=problems)
            )
            problems = guards.check_adjudication(output, tier, policy)

        emit(
            "adjudicator",
            TraceKind.ADJUDICATION,
            f"{output.verdict} {' '.join(output.broken_rule_ids)}".strip(),
            output=output.model_dump(mode="json"),
        )

        flags = state.flags

        if guards.approver_is_proposer(
            EvidenceView(state.case).approver_names(), state.intake.proposers
        ):
            flags = _add_flag(flags, guards.FLAG_APPROVER_IS_PROPOSER)
            emit("guards", TraceKind.GUARD, "An approver is also a proposer of this action.")

        if problems:
            reason = "The adjudicator's answer failed policy checks twice: " + "; ".join(problems)
            emit("guards", TraceKind.GUARD, reason, problems=problems)
            decision = guards.needs_review(reason, policy, tier=tier, flags=flags)
        else:
            decision = guards.decide(output, tier, policy, flags)

        emit("guards", TraceKind.DECISION, decision.proposed_action.summary, label=decision.label)

        return {"decision": decision, "flags": flags}

    async def escalate(state: RunState) -> Update:
        reason = state.supervisor.reason if state.supervisor else "Escalated."
        decision = guards.needs_review(reason, policy, tier=state.tier, flags=state.flags)

        emit("supervisor", TraceKind.DECISION, f"Escalated: {reason}", label=decision.label)

        return {"decision": decision}

    graph = StateGraph(RunState)
    graph.add_node("intake", intake)
    graph.add_node("unsupported", unsupported)
    graph.add_node("supervisor", supervisor)
    graph.add_node("evidence", evidence)
    graph.add_node("adjudicator", adjudicator)
    graph.add_node("escalate", escalate)

    graph.add_edge(START, "intake")
    graph.add_conditional_edges("intake", after_intake)
    graph.add_conditional_edges("supervisor", after_supervisor)
    graph.add_conditional_edges("evidence", after_evidence)
    graph.add_edge("unsupported", END)
    graph.add_edge("adjudicator", END)
    graph.add_edge("escalate", END)

    return graph.compile()


async def _run_tool(tools: dict[str, Any], name: str, args: dict[str, Any]) -> str:
    if name not in tools:
        return json.dumps({"error": f"Unknown tool {name}"})

    try:
        return str(await tools[name].ainvoke(args))
    except Exception as error:  # noqa: BLE001 - tool errors go back to the model as text
        return json.dumps({"error": f"{type(error).__name__}: {error}"})


def _injection_in(output: str) -> list[str]:
    try:
        flagged = json.loads(output).get("possible_injection", [])
    except (json.JSONDecodeError, AttributeError):
        return []

    return [str(item) for item in flagged] if isinstance(flagged, list) else []


async def stream_run(graph: CompiledStateGraph, case: Case) -> AsyncIterator[TraceEvent | Decision]:
    """Yield trace events as they happen, then the final decision."""
    final: RunState | None = None

    async for mode, chunk in graph.astream(RunState(case=case), stream_mode=["custom", "values"]):
        if mode == "custom":
            yield chunk
        else:
            final = chunk if isinstance(chunk, RunState) else RunState.model_validate(chunk)

    if final is None or final.decision is None:
        raise RuntimeError("The graph finished without a decision.")

    yield final.decision
