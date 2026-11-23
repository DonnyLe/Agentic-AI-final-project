import pytest

from kangaroo.ai.agents import guards
from kangaroo.models.agent_io import AdjudicatorOutput
from kangaroo.models.decision import Restrictiveness, Verdict
from kangaroo.models.golden import GoldenLabel, matches_golden, normalize_label
from kangaroo.policy import load_policy

POLICY = load_policy()


def adjudication(verdict: str, rules: list[str]) -> AdjudicatorOutput:
    return AdjudicatorOutput(verdict=verdict, broken_rule_ids=rules, rationale="because")


@pytest.mark.parametrize(
    ("verdict", "rules", "tier", "problem"),
    [
        ("violation", ["R9.9"], "T2", "not a rule"),
        ("violation", ["R1.2"], "T2", "is a T1 rule"),
        ("violation", [], "T1", "at least one"),
        ("no_violation", ["R2.3"], "T2", "can't list"),
    ],
)
def test_bad_adjudications_are_caught(
    verdict: str, rules: list[str], tier: str, problem: str
) -> None:
    problems = guards.check_adjudication(adjudication(verdict, rules), tier, POLICY)

    assert any(problem in p for p in problems)


@pytest.mark.parametrize(
    ("verdict", "rules", "tier"),
    [("violation", ["R2.3"], "T2"), ("violation", ["R2.4"], "T2"), ("no_violation", [], "T1")],
)
def test_good_adjudications_pass(verdict: str, rules: list[str], tier: str) -> None:
    assert guards.check_adjudication(adjudication(verdict, rules), tier, POLICY) == []


def test_most_restrictive_outcome_wins() -> None:
    action = guards.proposed_action_for("T2", ["R2.3", "R2.1"])

    assert action.restrictiveness == Restrictiveness.NEEDS_INFO
    assert "needs info" in action.summary


def test_clean_actions_proceed_with_tier_specific_approval() -> None:
    assert guards.proposed_action_for("T1", []).requires_approval is False
    assert guards.proposed_action_for("T2", []).requires_approval is True


def test_decision_labels() -> None:
    violation = guards.decide(adjudication("violation", ["R2.3", "R2.1"]), "T2", POLICY, [])
    clean = guards.decide(adjudication("no_violation", []), "T1", POLICY, [])
    unsure = guards.decide(adjudication("needs_review", []), "T2", POLICY, [])

    assert violation.label == "T2 R2.1 R2.3"
    assert clean.label == "none"
    assert unsure.verdict == Verdict.NEEDS_REVIEW
    assert guards.unsupported("T3", POLICY, []).label == "unsupported"


def test_approver_is_proposer() -> None:
    assert guards.approver_is_proposer(["Lena Okafor"], ["lena  okafor", "Sam"])
    assert not guards.approver_is_proposer(["Priya Nair"], ["Maya Chen"])
    assert not guards.approver_is_proposer([""], [""])


def golden(final: str, tier: str) -> GoldenLabel:
    return GoldenLabel(case_id="K-1", final=final, notes="", action_tier=tier)


def test_golden_matching() -> None:
    violation = guards.decide(adjudication("violation", ["R2.3"]), "T2", POLICY, [])
    clean = guards.decide(adjudication("no_violation", []), "T1", POLICY, [])
    out_of_scope = guards.unsupported("T3", POLICY, [])

    assert matches_golden(violation, golden("T2 R2.3", "T2"))
    assert not matches_golden(violation, golden("T2 R2.2", "T2"))
    assert matches_golden(clean, golden("none", "T1"))
    # K-063 is a clean T3 case: its golden label is `none` but the right answer is unsupported.
    assert matches_golden(out_of_scope, golden("none", "T3"))
    assert not matches_golden(clean, golden("none", "T3"))
    assert not matches_golden(out_of_scope, golden("none", "T1"))


def test_normalize_label() -> None:
    assert normalize_label("T4 R4.3 R4.1") == "T4 R4.1 R4.3"
    assert normalize_label("none") == "none"
