from typing import Literal

import pytest
from fakes import ScriptedChatModel, structured, tool_reply
from langchain_core.messages import AIMessage, HumanMessage
from pydantic import BaseModel

from kangaroo.llm import StructuredOutputError, parse_json_reply, structured_call


class Answer(BaseModel):
    answer: str
    confidence: Literal["low", "medium", "high"]


PROMPT = [HumanMessage("What is the capital of France?")]
PARIS = Answer(answer="Paris", confidence="high")


async def test_uses_the_tool_call_when_present() -> None:
    model = ScriptedChatModel(script=[structured(PARIS)])

    assert await structured_call(model, Answer, PROMPT) == PARIS


async def test_falls_back_to_json_in_text() -> None:
    text = 'Sure!\n```json\n{"answer": "Paris", "confidence": "high"}\n```'
    model = ScriptedChatModel(script=[AIMessage(content=text)])

    assert await structured_call(model, Answer, PROMPT) == PARIS
    assert len(model.calls) == 1


async def test_nudges_once_then_accepts_the_retry() -> None:
    model = ScriptedChatModel(script=[AIMessage(content="Paris, I think."), structured(PARIS)])

    assert await structured_call(model, Answer, PROMPT) == PARIS
    assert "valid `Answer` tool call" in model.calls[1][-1].content


async def test_gives_up_after_the_retry() -> None:
    bad = tool_reply("Answer", {"answer": "Paris", "confidence": "certain"})
    model = ScriptedChatModel(script=[AIMessage(content="no idea"), bad])

    with pytest.raises(StructuredOutputError):
        await structured_call(model, Answer, PROMPT)


def test_parse_json_reply_handles_wrapped_arguments() -> None:
    text = '{"name": "Answer", "arguments": {"answer": "Paris", "confidence": "low"}}'

    assert parse_json_reply(text, Answer) == Answer(answer="Paris", confidence="low")
    assert parse_json_reply("nothing here", Answer) is None
