"""Trace events: what each agent did during a run, shown live in the UI."""

from datetime import UTC, datetime
from enum import StrEnum

from pydantic import BaseModel, Field, JsonValue


class TraceKind(StrEnum):
    INTAKE = "intake"
    ROUTE = "route"
    TOOL_CALL = "tool_call"
    TOOL_RESULT = "tool_result"
    FINDINGS = "findings"
    ADJUDICATION = "adjudication"
    GUARD = "guard"
    DECISION = "decision"
    ERROR = "error"


class TraceEvent(BaseModel):
    node: str
    kind: TraceKind
    message: str
    payload: dict[str, JsonValue] = Field(default_factory=dict)
    at: datetime = Field(default_factory=lambda: datetime.now(UTC))
