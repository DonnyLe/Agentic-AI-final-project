"""Decision model client tests against a mocked Workers AI endpoint."""

import json

import cloudflare
import pytest
import respx
from langchain_core.decisions import Box, Choice, Noul, Score
from langchain_core.messages import HumanMessage
from pydantic import SecretStr

from kangaroo.ai.decision_model import DecisionModelClient

RESULT = {
    "model": "clef-flash",
    "answers": {
        "urgent": {"type": "noul", "noul": 0.82},
        "team": {
            "type": "choice",
            "choice": "billing",
            "probabilities": {"billing": 0.7, "technical": 0.3},
            "confidence": 0.7,
        },
        "severity": {
            "type": "score",
            "score": 1.4,
            "legend": {"0": "low", "1": "medium", "2": "high"},
            "probabilities": {"0": 0.1, "1": 0.4, "2": 0.5},
            "confidence": 0.5,
        },
    },
    "usage": {"input_tokens": 120, "output_tokens": 0},
}

QUESTIONS = {
    "urgent": Noul(instructions="Is this urgent?"),
    "team": Choice(instructions="Which team?", criteria={"billing": "money", "technical": "bugs"}),
    "severity": Score(instructions="How severe?", criteria=["low", "medium", "high"]),
}


RUN_URL = "https://api.cloudflare.com/client/v4/accounts/acct/ai/run/"


def client() -> DecisionModelClient:
    return DecisionModelClient(account_id="acct", api_token=SecretStr("tok"))


@respx.mock
async def test_ainvoke_sends_request_and_parses_answers() -> None:
    envelope = {"result": RESULT, "success": True, "errors": [], "messages": []}
    route = respx.post(url__startswith=RUN_URL).respond(json=envelope)

    state = [HumanMessage("I was charged twice")]
    response = await client().ainvoke({"state": state, "questions": QUESTIONS})

    request = route.calls.last.request
    body = json.loads(request.content)

    assert request.url.path.endswith("/accounts/acct/ai/run/@cf/cloudflare/clef-flash")
    assert request.headers["authorization"] == "Bearer tok"
    assert body["model"] == "clef-flash"
    assert body["state"] == [{"role": "user", "content": "I was charged twice"}]
    assert body["questions"]["urgent"] == {"type": "noul", "instructions": "Is this urgent?"}
    assert body["questions"]["severity"]["criteria"] == ["low", "medium", "high"]
    assert response.nouls["urgent"].noul == 0.82
    assert response.choices["team"].choice == "billing"
    assert response.scores["severity"].probabilities == {0: 0.1, 1: 0.4, 2: 0.5}
    assert response.usage is not None
    assert response.usage["total_tokens"] == 120


@respx.mock
async def test_ainvoke_raises_on_auth_error() -> None:
    respx.post(url__startswith=RUN_URL).respond(401, json={"success": False, "errors": []})

    with pytest.raises(cloudflare.AuthenticationError):
        await client().ainvoke({"state": "state", "questions": QUESTIONS})


@pytest.mark.parametrize(
    ("questions", "message"),
    [({}, "1 to 64"), ({"where": Box(instructions="Find the logo")}, "Box")],
)
async def test_ainvoke_rejects_unsupported_questions(questions: dict, message: str) -> None:
    with pytest.raises(ValueError, match=message):
        await client().ainvoke({"state": "state", "questions": questions})
