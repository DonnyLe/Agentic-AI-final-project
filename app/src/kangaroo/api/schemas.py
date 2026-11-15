"""Request and response bodies for the HTTP API."""

import uuid

from pydantic import BaseModel, Field

from kangaroo.db.records import EvaluationRecord, ReviewChoice, ReviewRecord, TraceRecord
from kangaroo.models.case import CaseContent
from kangaroo.policy import Rule


class Health(BaseModel):
    ok: bool


class NewCase(BaseModel):
    content: CaseContent


class StartRun(BaseModel):
    case_id: str


class RunStarted(BaseModel):
    evaluation_id: uuid.UUID


class StartBatch(BaseModel):
    case_ids: list[str] = Field(min_length=1, max_length=50)


class BatchStarted(BaseModel):
    evaluation_ids: list[uuid.UUID]


class RunDetail(BaseModel):
    evaluation: EvaluationRecord
    trace: list[TraceRecord]
    reviews: list[ReviewRecord]


class NewReview(BaseModel):
    decision: ReviewChoice
    reviewer: str = Field(min_length=1, max_length=128)
    note: str = Field(default="", max_length=2000)


class PolicyView(BaseModel):
    version: str
    rules: list[Rule]
    markdown: str
