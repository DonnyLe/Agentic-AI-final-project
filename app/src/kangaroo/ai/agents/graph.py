"""The Kangaroo agent graph (LangGraph). Each agent lives in its own module.

intake ─┬─ T3/T4 ──────────────────────────────► unsupported
        └─ T1/T2 ─► supervisor ─┬─ gather ─► evidence ─┐
                       ▲        │                      │
                       └────────┼──────────────────────┘
                                ├─ adjudicate ─► adjudicator (+ guards)
                                └─ escalate ───► needs_review

Each node streams TraceEvents through LangGraph's custom stream. Any node that
fails ends the run with a `needs_review` decision instead of a guess.
"""

from collections.abc import AsyncIterator
from typing import Literal

from langgraph.graph import END, START, StateGraph
from langgraph.graph.state import CompiledStateGraph

from kangaroo.ai.agents import guards
from kangaroo.ai.agents.adjudicator import make_adjudicator
from kangaroo.ai.agents.evidence import make_evidence
from kangaroo.ai.agents.intake import make_intake, make_unsupported
from kangaroo.ai.agents.state import RunState
from kangaroo.ai.agents.supervisor import make_escalate, make_supervisor
from kangaroo.ai.llm import ModelProvider
from kangaroo.models.case import Case
from kangaroo.models.decision import Decision
from kangaroo.models.trace import TraceEvent
from kangaroo.policy import Policy

MAX_EVIDENCE_ROUNDS = 2


def after_intake(state: RunState) -> Literal["supervisor", "unsupported", "__end__"]:
    if state.decision is not None or state.intake is None:
        return END

    return "supervisor" if guards.is_supported(state.intake.action_class) else "unsupported"


def after_supervisor(state: RunState) -> Literal["evidence", "adjudicator", "escalate", "__end__"]:
    if state.decision is not None or state.supervisor is None:
        return END

    return {
        "gather_evidence": "evidence",
        "adjudicate": "adjudicator",
        "escalate": "escalate",
    }[state.supervisor.next_step]


def after_evidence(state: RunState) -> Literal["supervisor", "__end__"]:
    return END if state.decision is not None else "supervisor"


def build_graph(
    models: ModelProvider, policy: Policy, max_rounds: int = MAX_EVIDENCE_ROUNDS
) -> CompiledStateGraph:
    graph = StateGraph(RunState)
    graph.add_node("intake", make_intake(models, policy))
    graph.add_node("unsupported", make_unsupported(policy))
    graph.add_node("supervisor", make_supervisor(models, policy, max_rounds))
    graph.add_node("evidence", make_evidence(models, policy))
    graph.add_node("adjudicator", make_adjudicator(models, policy))
    graph.add_node("escalate", make_escalate(policy))

    graph.add_edge(START, "intake")
    graph.add_conditional_edges("intake", after_intake)
    graph.add_conditional_edges("supervisor", after_supervisor)
    graph.add_conditional_edges("evidence", after_evidence)
    graph.add_edge("unsupported", END)
    graph.add_edge("adjudicator", END)
    graph.add_edge("escalate", END)

    return graph.compile()


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
