"""Evidence agent: calls the evidence tools for the supervisor's tasks, then reports findings."""

import json
from typing import Any

from langchain_core.messages import BaseMessage, HumanMessage, SystemMessage, ToolMessage

from kangaroo.ai.agents import guards
from kangaroo.ai.agents.prompts import UNTRUSTED, render_case
from kangaroo.ai.agents.state import Node, RunState, Update, add_flag, emit, guarded
from kangaroo.ai.llm import ModelProvider, structured_call, with_retries
from kangaroo.ai.tools.evidence import build_evidence_tools
from kangaroo.config import Role
from kangaroo.models.agent_io import EvidenceReport, SupervisorDecision
from kangaroo.models.case import Case
from kangaroo.models.trace import TraceKind
from kangaroo.policy import Policy

MAX_TOOL_STEPS = 6
LOG_LIMIT = 1500


def evidence_messages(case: Case, decision: SupervisorDecision) -> list[BaseMessage]:
    tasks = ", ".join(task.value for task in decision.evidence_tasks)

    return [
        SystemMessage(
            "You are Kangaroo's evidence agent. Use the tools to collect facts for the tasks "
            "you're given. Refine a search if the first result falls short. Report what you "
            "found and what you couldn't confirm. " + UNTRUSTED
        ),
        HumanMessage(
            f"{render_case(case)}\n\nTasks: {tasks}\nWhy: {decision.reason}\n\n"
            "Call the tools you need, then stop calling tools."
        ),
    ]


def findings_messages(
    gathered: list[BaseMessage], decision: SupervisorDecision
) -> list[BaseMessage]:
    tasks = ", ".join(task.value for task in decision.evidence_tasks)

    return [
        *gathered,
        HumanMessage(
            f"Summarize the evidence as one finding per task ({tasks}). "
            "Use status confirmed / possible / not_found / unresolved."
        ),
    ]


def make_evidence(models: ModelProvider, policy: Policy) -> Node:
    @guarded("evidence", policy)
    async def evidence(state: RunState) -> Update:
        assert state.supervisor is not None
        model = models.for_role(Role.EVIDENCE)
        tools = {tool.name: tool for tool in build_evidence_tools(state.case)}
        bound = with_retries(model.bind_tools(list(tools.values())))
        messages: list[BaseMessage] = evidence_messages(state.case, state.supervisor)
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
                    flags = add_flag(flags, guards.FLAG_POSSIBLE_INJECTION)

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
            model, EvidenceReport, findings_messages(messages, state.supervisor)
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

    return evidence


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
