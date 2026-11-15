import json

import pytest

from kangaroo.corpus import load_cases
from kangaroo.models.case import Case
from kangaroo.tools.evidence import EvidenceView, build_evidence_tools, find_injection

CASES = {case.id: case for case in load_cases()}


def tool_output(case: Case, name: str, **args: object) -> dict:
    tools = {tool.name: tool for tool in build_evidence_tools(case)}

    return json.loads(tools[name].invoke(args))


def test_tool_names() -> None:
    names = [tool.name for tool in build_evidence_tools(CASES["K-054"])]

    assert names == [
        "search_tickets",
        "get_ticket",
        "verify_dependency",
        "get_team_roster",
        "get_transcript_segments",
        "get_other_evidence",
    ]


def test_registry_and_upstream_lookups_normalize_across_key_names() -> None:
    result = tool_output(CASES["K-054"], "verify_dependency", package="jwt-verify-lite")

    assert "4.2.0" in result["content"]["package_registry"]
    assert "0 matching issues" in result["content"]["upstream_issues"]
    assert result["note"].startswith("Evidence from team systems")


def test_single_approval_becomes_a_list() -> None:
    view = EvidenceView(CASES["K-054"])

    assert len(view.approvals()) == 1


@pytest.mark.parametrize("case_id", ["K-109", "K-082"])
def test_reproduction_steps_spellings_are_unified(case_id: str) -> None:
    tickets = EvidenceView(CASES[case_id]).tickets()

    assert tickets
    assert all("reproduction_steps" in t for t in tickets)
    assert not any(k in t for t in tickets for k in ("repro", "repro_steps", "reproduction"))


def test_search_tickets_returns_recorded_search_and_matches() -> None:
    result = tool_output(CASES["K-109"], "search_tickets", query="jobs worker killed running")

    content = result["content"]

    assert "JOB-388" in content["recorded_duplicate_search"]
    assert content["keyword_matches"][0]["id"] == "JOB-388"


def test_injection_in_ticket_body_is_flagged_not_obeyed() -> None:
    result = tool_output(CASES["K-109"], "get_ticket", ticket_id="job-388")

    assert result["content"]["id"] == "JOB-388"
    assert result["possible_injection"]
    assert "Kangaroo" in result["possible_injection"][0]


def test_unknown_ticket() -> None:
    result = tool_output(CASES["K-109"], "get_ticket", ticket_id="NOPE-1")

    assert "not found" in result["content"]["error"]


def test_transcript_segments_and_other_evidence() -> None:
    case = CASES["K-115"]
    first = case.content.segments[0].segment_id

    segments = tool_output(case, "get_transcript_segments", segment_ids=[first])
    other = tool_output(case, "get_other_evidence")

    assert [s["segment_id"] for s in segments["content"]] == [first]
    assert "documentation_lookup" in other["content"]


def test_plain_text_is_not_flagged() -> None:
    assert find_injection("Checkout stays blank on Safari after the SDK update.") == []
