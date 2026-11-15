"""Postgres table definitions."""

import uuid
from datetime import datetime
from typing import Any, ClassVar

from sqlalchemy import ForeignKey, String, Text, UniqueConstraint, func
from sqlalchemy.dialects.postgresql import ARRAY, JSONB, TIMESTAMP, UUID
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column


class Base(DeclarativeBase):
    type_annotation_map: ClassVar[dict[Any, Any]] = {
        datetime: TIMESTAMP(timezone=True),
        uuid.UUID: UUID(as_uuid=True),
        dict[str, Any]: JSONB,
        list[str]: ARRAY(Text),
    }


class CaseRow(Base):
    __tablename__ = "cases"

    id: Mapped[str] = mapped_column(String(32), primary_key=True)
    content: Mapped[dict[str, Any]]
    source: Mapped[str] = mapped_column(String(16))
    created_at: Mapped[datetime] = mapped_column(server_default=func.now())


class GoldenLabelRow(Base):
    """Golden labels for UI comparison and eval scoring only. Never read by agents."""

    __tablename__ = "golden_labels"

    case_id: Mapped[str] = mapped_column(ForeignKey("cases.id"), primary_key=True)
    final: Mapped[str] = mapped_column(String(64))
    notes: Mapped[str] = mapped_column(Text, server_default="")
    action_tier: Mapped[str] = mapped_column(String(4))


class EvaluationRow(Base):
    __tablename__ = "evaluations"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True)
    case_id: Mapped[str] = mapped_column(ForeignKey("cases.id"), index=True)
    status: Mapped[str] = mapped_column(String(16))
    verdict: Mapped[str | None] = mapped_column(String(16))
    tier: Mapped[str | None] = mapped_column(String(4))
    label: Mapped[str | None] = mapped_column(String(64))
    rule_ids: Mapped[list[str]] = mapped_column(server_default="{}")
    rationale: Mapped[str] = mapped_column(Text, server_default="")
    proposed_action: Mapped[dict[str, Any] | None]
    cited_segment_ids: Mapped[list[str]] = mapped_column(server_default="{}")
    evidence_refs: Mapped[list[str]] = mapped_column(server_default="{}")
    flags: Mapped[list[str]] = mapped_column(server_default="{}")
    models: Mapped[dict[str, Any]] = mapped_column(server_default="{}")
    policy_version: Mapped[str] = mapped_column(String(16))
    golden_label: Mapped[str | None] = mapped_column(String(64))
    golden_match: Mapped[bool | None]
    error: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(server_default=func.now(), index=True)
    finished_at: Mapped[datetime | None]


class TraceEventRow(Base):
    __tablename__ = "trace_events"
    __table_args__ = (UniqueConstraint("evaluation_id", "seq"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    evaluation_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("evaluations.id"), index=True)
    seq: Mapped[int]
    node: Mapped[str] = mapped_column(String(32))
    kind: Mapped[str] = mapped_column(String(16))
    message: Mapped[str] = mapped_column(Text)
    payload: Mapped[dict[str, Any]] = mapped_column(server_default="{}")
    at: Mapped[datetime]


class ReviewerDecisionRow(Base):
    __tablename__ = "reviewer_decisions"

    id: Mapped[int] = mapped_column(primary_key=True)
    evaluation_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("evaluations.id"), index=True)
    decision: Mapped[str] = mapped_column(String(16))
    reviewer: Mapped[str] = mapped_column(String(128))
    note: Mapped[str] = mapped_column(Text, server_default="")
    created_at: Mapped[datetime] = mapped_column(server_default=func.now())
