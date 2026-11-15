import json

import pytest

from kangaroo.corpus import CORPUS_PATH, load_cases, load_golden_labels
from kangaroo.policy import load_policy, parse_policy

METADATA_KEYS = {
    "seeded_tier",
    "seeded_rules",
    "ambiguous",
    "injection",
    "generated_by",
    "reviewed_by",
    "target_tier",
    "ambiguity_type",
    "scenario_family",
    "generation_note",
    "review_status",
}
CONTENT_KEYS = {
    "meeting_id",
    "meeting_type",
    "meeting_date",
    "meeting_weekday",
    "meeting_timezone",
    "segments",
    "candidate_action",
    "evidence",
}


def test_loads_every_case_without_metadata() -> None:
    cases = load_cases()

    assert len(cases) == 122

    for case in cases:
        dumped = case.model_dump(mode="json")

        assert dumped.keys() == {"id", "content"}
        assert dumped["content"].keys() == CONTENT_KEYS


def test_source_corpus_really_has_metadata() -> None:
    # Guards the test above: it only means something if the source has these keys.
    first = json.loads(CORPUS_PATH.read_text(encoding="utf-8").splitlines()[0])

    assert first.keys() >= METADATA_KEYS


def test_golden_labels() -> None:
    labels = load_golden_labels()

    assert len(labels) == 39
    assert {label.case_id: label.final for label in labels}["K-054"] == "T2 R2.3"


def test_policy_has_fourteen_rules_across_four_tiers() -> None:
    policy = load_policy()

    assert policy.version == "1.3"
    assert len(policy.rules) == 14
    assert {rule.tier for rule in policy.rules.values()} == {"T1", "T2", "T3", "T4"}
    assert policy.rules["R2.3"].name == "Third-party attribution"
    assert [rule.id for rule in policy.rules_for({"T1"})] == ["R1.1", "R1.2", "R1.3"]


def test_policy_without_rules_is_rejected() -> None:
    with pytest.raises(ValueError, match="missing"):
        parse_policy("# empty")
