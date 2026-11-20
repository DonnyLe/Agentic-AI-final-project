"""Plain pydantic records the repository returns (no ORM objects leak out)."""

import uuid
from datetime import datetime
from typing import Literal

from pydantic import BaseModel, JsonValue

from kangaroo.models.case import Case
from kangaroo.models.decision import ProposedAction
from kangaroo.models.golden import GoldenLabel
from kangaroo.models.trace import TraceEvent

type EvaluationStatus = Literal["running", "completed", "failed"]
type ReviewChoice = Literal["approve", "reject"]
type CaseSource = Literal["corpus", "custom"]


class CaseSummary(BaseModel):
    id: str
    source: CaseSource
    meeting_type: str
    meeting_date: str | None
    candidate_action: str
    golden_label: str | None
    last_label: str | None


class StoredCase(BaseModel):
    case: Case
    source: CaseSource
    golden: GoldenLabel | None


class EvaluationRecord(BaseModel):
    id: uuid.UUID
    case_id: str
    status: EvaluationStatus
    verdict: str | None
    tier: str | None
    label: str | None
    rule_ids: list[str]
    rationale: str
    proposed_action: ProposedAction | None
    cited_segment_ids: list[str]
    evidence_refs: list[str]
    flags: list[str]
    models: dict[str, JsonValue]
    policy_version: str
    golden_label: str | None
    golden_match: bool | None
    error: str | None
    created_at: datetime
    finished_at: datetime | None


class TraceRecord(BaseModel):
    seq: int
    event: TraceEvent


class ReviewRecord(BaseModel):
    id: int
    evaluation_id: uuid.UUID
    decision: ReviewChoice
    reviewer: str
    note: str
    created_at: datetime
