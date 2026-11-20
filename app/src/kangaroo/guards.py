"""Deterministic checks and decision assembly around the LLM roles.

The LLM proposes; code decides what is allowed to stand:
- rule IDs must exist in the policy and belong to the action's tier;
- the proposed action comes from a fixed ladder, most restrictive outcome wins;
- out-of-scope actions are `unsupported`, failures are `needs_review`;
- an approver who is also a proposer is flagged.
"""

from kangaroo.models.agent_io import AdjudicatorOutput
from kangaroo.models.case import SUPPORTED_TIERS, Tier
from kangaroo.models.decision import Decision, ProposedAction, Restrictiveness, Verdict
from kangaroo.policy import Policy

FLAG_POSSIBLE_INJECTION = "possible_injection"
FLAG_APPROVER_IS_PROPOSER = "approver_is_proposer"
FLAG_AGENT_ERROR = "agent_error"
FLAG_TIER_HINT_MISMATCH = "tier_hint_mismatch"

_HINT_TIERS: dict[str, Tier] = {"record": "T1", "ticket": "T2", "calendar": "T3", "code": "T4"}

_ENGINEER_APPROVER = "an engineer who is not a proposer"

# What each broken rule turns the action into (policy v1.3, T1 and T2).
RULE_OUTCOMES: dict[str, ProposedAction] = {
    "R1.1": ProposedAction(
        restrictiveness=Restrictiveness.FLAG,
        summary="Record it as a proposal or disputed note, not a settled decision.",
        requires_approval=False,
    ),
    "R1.2": ProposedAction(
        restrictiveness=Restrictiveness.FLAG,
        summary="Record the action item as unowned and flag it; don't assign an owner.",
        requires_approval=False,
    ),
    "R1.3": ProposedAction(
        restrictiveness=Restrictiveness.HOLD,
        summary="Keep the original deadline wording and ask for clarification.",
        requires_approval=False,
    ),
    "R2.1": ProposedAction(
        restrictiveness=Restrictiveness.NEEDS_INFO,
        summary="Mark the ticket draft 'needs info'; don't file it as a complete defect.",
        requires_approval=True,
        approver=_ENGINEER_APPROVER,
    ),
    "R2.2": ProposedAction(
        restrictiveness=Restrictiveness.REDIRECT,
        summary="Link the report to the existing ticket instead of filing a new one.",
        requires_approval=True,
        approver=_ENGINEER_APPROVER,
    ),
    "R2.3": ProposedAction(
        restrictiveness=Restrictiveness.FLAG,
        summary="File only with the third-party cause marked unverified and the lookups attached.",
        requires_approval=True,
        approver=_ENGINEER_APPROVER,
    ),
    "R2.4": ProposedAction(
        restrictiveness=Restrictiveness.REDIRECT,
        summary="Record the request as a T1 note; don't file it as a defect.",
        requires_approval=False,
    ),
}

_PROCEED: dict[str, ProposedAction] = {
    "T1": ProposedAction(
        restrictiveness=Restrictiveness.PROCEED,
        summary="Save the internal note as written (T1 records need no approval).",
        requires_approval=False,
    ),
    "T2": ProposedAction(
        restrictiveness=Restrictiveness.PROCEED,
        summary="Draft the ticket as written; file it once approved.",
        requires_approval=True,
        approver=_ENGINEER_APPROVER,
    ),
}

_UNSUPPORTED = ProposedAction(
    restrictiveness=Restrictiveness.HOLD,
    summary="Outside the alpha's scope (T3/T4 actions). Hand to a human reviewer.",
    requires_approval=True,
    approver="a human reviewer",
)

_NEEDS_REVIEW = ProposedAction(
    restrictiveness=Restrictiveness.HOLD,
    summary="Hold for a reviewer: the evidence or the agents couldn't settle this case.",
    requires_approval=True,
    approver="a human reviewer",
)


def is_supported(tier: Tier) -> bool:
    return tier in SUPPORTED_TIERS


def hint_tier(hint: str | None) -> Tier | None:
    """The tier intake's non-binding action-type hint points to, if any."""
    return _HINT_TIERS.get(hint) if hint else None


def check_adjudication(output: AdjudicatorOutput, tier: Tier, policy: Policy) -> list[str]:
    """Problems with an adjudicator answer. Empty means it can stand."""
    problems: list[str] = []
    rules = output.broken_rule_ids

    for rule_id in rules:
        if not policy.has_rule(rule_id):
            problems.append(f"{rule_id} is not a rule in policy v{policy.version}.")
        elif policy.rules[rule_id].tier != tier:
            problems.append(
                f"{rule_id} is a {policy.rules[rule_id].tier} rule; the action is {tier}."
            )

    if output.verdict == "violation" and not rules:
        problems.append("A violation must cite at least one broken rule.")

    if output.verdict == "no_violation" and rules:
        problems.append("no_violation can't list broken rules.")

    return problems


def proposed_action_for(tier: Tier, rule_ids: list[str]) -> ProposedAction:
    """The single outcome to propose: the most restrictive among the broken rules."""
    outcomes = [RULE_OUTCOMES[r] for r in rule_ids if r in RULE_OUTCOMES]

    if not outcomes:
        return _PROCEED[tier]

    return max(outcomes, key=lambda action: action.restrictiveness)


def approver_is_proposer(approvals: list[str], proposers: list[str]) -> bool:
    """True when anyone recorded as approving also proposed the action."""
    proposer_names = {_name_key(p) for p in proposers if p.strip()}

    return any(_name_key(a) in proposer_names for a in approvals if a.strip())


def _name_key(name: str) -> str:
    return " ".join(name.lower().split())


def decide(output: AdjudicatorOutput, tier: Tier, policy: Policy, flags: list[str]) -> Decision:
    """Turn a checked adjudicator answer into the final decision."""
    if output.verdict == "needs_review":
        return needs_review(output.rationale, policy, tier=tier, flags=flags)

    rule_ids = sorted(set(output.broken_rule_ids))
    verdict = Verdict.VIOLATION if output.verdict == "violation" else Verdict.NO_VIOLATION

    return Decision(
        verdict=verdict,
        tier=tier,
        rule_ids=rule_ids,
        rationale=output.rationale,
        cited_segment_ids=output.cited_segment_ids,
        evidence_refs=output.evidence_refs,
        proposed_action=proposed_action_for(tier, rule_ids),
        flags=flags,
        policy_version=policy.version,
    )


def unsupported(tier: Tier, policy: Policy, flags: list[str]) -> Decision:
    return Decision(
        verdict=Verdict.UNSUPPORTED,
        tier=tier,
        rationale=f"The candidate action is a {tier} action. The alpha only handles T1 and T2.",
        proposed_action=_UNSUPPORTED,
        flags=flags,
        policy_version=policy.version,
    )


def needs_review(
    reason: str, policy: Policy, tier: Tier | None = None, flags: list[str] | None = None
) -> Decision:
    return Decision(
        verdict=Verdict.NEEDS_REVIEW,
        tier=tier,
        rationale=reason,
        proposed_action=_NEEDS_REVIEW,
        flags=flags or [],
        policy_version=policy.version,
    )
