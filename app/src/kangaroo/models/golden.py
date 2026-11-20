"""Golden labels and scoring. Used by the UI and the eval only, never by agents."""

from pydantic import BaseModel

from kangaroo.models.case import SUPPORTED_TIERS, Tier
from kangaroo.models.decision import Decision, Verdict


class GoldenLabel(BaseModel):
    case_id: str
    final: str
    notes: str
    # Tier of the case's candidate action (corpus `target_tier`). A clean T3 case
    # is labeled `none`, so the label alone can't say the case is out of scope.
    action_tier: Tier

    @property
    def in_scope(self) -> bool:
        return self.action_tier in SUPPORTED_TIERS


def normalize_label(label: str) -> str:
    """Same label in a canonical form: tier first, rules sorted."""
    parts = label.split()

    if not parts or parts[0] == "none":
        return "none"

    return " ".join([parts[0], *sorted(parts[1:])])


def matches_golden(decision: Decision, golden: GoldenLabel) -> bool:
    """Whether a decision counts as correct for a golden case.

    Out-of-scope cases (T3/T4 actions) are correct only when the verdict is
    `unsupported`. In-scope cases need an exact label match.
    """
    if not golden.in_scope:
        return decision.verdict is Verdict.UNSUPPORTED

    return normalize_label(decision.label) == normalize_label(golden.final)
