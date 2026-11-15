"""The final, guarded decision for a case and the proposed enforcement action."""

from enum import IntEnum, StrEnum

from pydantic import BaseModel, Field

from kangaroo.models.case import Tier


class Verdict(StrEnum):
    NO_VIOLATION = "no_violation"
    VIOLATION = "violation"
    UNSUPPORTED = "unsupported"
    NEEDS_REVIEW = "needs_review"


class Restrictiveness(IntEnum):
    """Policy order for picking one outcome when several apply (higher wins)."""

    PROCEED = 0
    FLAG = 1
    REDIRECT = 2
    NEEDS_INFO = 3
    HOLD = 4
    REFUSE = 5


class ProposedAction(BaseModel):
    restrictiveness: Restrictiveness
    summary: str
    requires_approval: bool
    approver: str = ""


class Decision(BaseModel):
    verdict: Verdict
    tier: Tier | None = None
    rule_ids: list[str] = Field(default_factory=list)
    rationale: str
    cited_segment_ids: list[str] = Field(default_factory=list)
    evidence_refs: list[str] = Field(default_factory=list)
    proposed_action: ProposedAction
    flags: list[str] = Field(default_factory=list)
    policy_version: str

    @property
    def label(self) -> str:
        """The decision in golden-label format: `none` or `T<n> R<x.y> ...`."""
        match self.verdict:
            case Verdict.NO_VIOLATION:
                return "none"
            case Verdict.VIOLATION:
                return " ".join([self.tier or "T?", *sorted(self.rule_ids)])
            case _:
                return self.verdict.value
