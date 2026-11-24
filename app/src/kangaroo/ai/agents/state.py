"""State and helpers shared by every node in the agent graph."""

import logging
from collections.abc import Awaitable, Callable
from functools import wraps
from typing import Any

from langgraph.config import get_stream_writer
from pydantic import BaseModel, Field, JsonValue

from kangaroo.ai.agents import guards
from kangaroo.models.agent_io import EvidenceFinding, IntakeResult, SupervisorDecision
from kangaroo.models.case import Case
from kangaroo.models.decision import Decision
from kangaroo.models.trace import TraceEvent, TraceKind
from kangaroo.policy import Policy

logger = logging.getLogger(__name__)

MAX_ATTEMPTS = 3


class RunState(BaseModel):
    case: Case
    intake: IntakeResult | None = None
    supervisor: SupervisorDecision | None = None
    findings: list[EvidenceFinding] = Field(default_factory=list)
    rounds: int = 0
    flags: list[str] = Field(default_factory=list)
    decision: Decision | None = None


type Update = dict[str, Any]
type Node = Callable[[RunState], Awaitable[Update]]


def emit(node: str, kind: TraceKind, message: str, **payload: JsonValue) -> None:
    get_stream_writer()(TraceEvent(node=node, kind=kind, message=message, payload=payload))


def add_flag(flags: list[str], flag: str) -> list[str]:
    return flags if flag in flags else [*flags, flag]


def guarded(name: str, policy: Policy) -> Callable[[Node], Node]:
    """Retry a failing node, then turn the last failure into a needs_review decision.

    The retry lives here rather than in a LangGraph RetryPolicy: a node error that
    escapes the graph fails the whole evaluation instead of ending in needs_review.
    """

    def wrap(node: Node) -> Node:
        @wraps(node)
        async def run(state: RunState) -> Update:
            reason = ""

            for attempt in range(1, MAX_ATTEMPTS + 1):
                try:
                    return await node(state)
                except Exception as error:
                    logger.warning(
                        "%s failed on case %s (attempt %d of %d)",
                        name,
                        state.case.id,
                        attempt,
                        MAX_ATTEMPTS,
                        exc_info=True,
                    )
                    reason = f"{name} failed: {type(error).__name__}: {error}"
                    emit(name, TraceKind.ERROR, f"{reason} (attempt {attempt} of {MAX_ATTEMPTS})")

            tier = state.intake.action_class if state.intake else None
            flags = add_flag(state.flags, guards.FLAG_AGENT_ERROR)
            reason = f"{reason} ({MAX_ATTEMPTS} attempts)"
            decision = guards.needs_review(reason, policy, tier=tier, flags=flags)

            return {"decision": decision}

        return run

    return wrap
