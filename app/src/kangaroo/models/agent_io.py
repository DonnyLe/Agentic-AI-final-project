"""Structured outputs the LLM roles must return. Field descriptions are prompt text."""

from enum import StrEnum
from typing import Literal

from pydantic import BaseModel, Field

from kangaroo.models.case import Tier


class IntakeResult(BaseModel):
    """What the candidate action is and who proposed it. Intake extracts; it doesn't decide
    the tier. The supervisor assigns the tier against the policy."""

    action_type_hint: Literal["record", "ticket", "calendar", "code"] | None = Field(
        default=None,
        description=(
            "Rough, non-binding guess at what kind of action this is: record (save a note "
            "or decision), ticket (file or link a defect ticket), calendar (schedule a "
            "meeting), code (change code, open a PR, write a fix plan). Null if unclear."
        ),
    )
    action_summary: str = Field(description="One sentence: what Kangaroo is about to do.")
    proposers: list[str] = Field(
        description="Full names of the people who proposed or asked for this action."
    )
    cited_segment_ids: list[str] = Field(
        description="Segment IDs that contain the request or decision."
    )
    third_party_dependency: str | None = Field(
        default=None,
        description="Third-party library or service blamed for a defect, if anyone blames one.",
    )
    ticket_ids: list[str] = Field(
        default_factory=list, description="Ticket IDs mentioned in the action or transcript."
    )


class EvidenceTask(StrEnum):
    DUPLICATE_SEARCH = "duplicate_search"
    TICKET_DETAILS = "ticket_details"
    DEPENDENCY_CHECK = "dependency_check"
    ROSTER_CHECK = "roster_check"
    TRANSCRIPT_CHECK = "transcript_check"


class SupervisorDecision(BaseModel):
    """The supervisor's tier for the candidate action and its next step for this case."""

    tier: Tier = Field(
        description=(
            "Policy tier of the candidate action itself (T1 Record, T2 Ticket, "
            "T3 Coordination, T4 Code change), per the policy's tier table."
        )
    )
    tier_reason: str = Field(
        description="One sentence: why the candidate action belongs to this tier."
    )
    next_step: Literal["gather_evidence", "adjudicate", "escalate"] = Field(
        description=(
            "gather_evidence: run the listed evidence tasks. adjudicate: the evidence is "
            "enough for a decision. escalate: the case can't be settled; hold for a human."
        )
    )
    evidence_tasks: list[EvidenceTask] = Field(
        default_factory=list,
        description=(
            "Evidence tasks to run now (only with gather_evidence). Pick only what this case needs."
        ),
    )
    reason: str = Field(description="Short reason for this choice, citing the case.")


class EvidenceFinding(BaseModel):
    task: EvidenceTask
    status: Literal["confirmed", "possible", "not_found", "unresolved"] = Field(
        description=(
            "confirmed: evidence settles it; possible: partial match or support only; "
            "not_found: looked and found nothing; unresolved: could not check."
        )
    )
    summary: str = Field(description="What the evidence shows, in one or two sentences.")
    sources: list[str] = Field(
        default_factory=list, description="Evidence keys or ticket IDs the summary relies on."
    )


class EvidenceReport(BaseModel):
    """Findings from one evidence round."""

    findings: list[EvidenceFinding]


class AdjudicatorOutput(BaseModel):
    """The policy decision for the candidate action."""

    verdict: Literal["no_violation", "violation", "needs_review"] = Field(
        description=(
            "violation if carrying out the candidate action exactly as written would break any "
            "rule; no_violation if it complies; needs_review only if the evidence can't settle it."
        )
    )
    broken_rule_ids: list[str] = Field(
        default_factory=list, description="Every broken rule ID, e.g. ['R2.3']. Empty if none."
    )
    rationale: str = Field(description="Two to four sentences tying the evidence to the rules.")
    cited_segment_ids: list[str] = Field(default_factory=list)
    evidence_refs: list[str] = Field(
        default_factory=list, description="Evidence keys or ticket IDs relied on."
    )
