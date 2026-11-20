"""Live checks against the real services. Run with KANGAROO_LIVE=1."""

import os
from typing import Literal

import pytest
from langchain_openai import ChatOpenAI
from pydantic import BaseModel
from sqlalchemy import text
from sqlalchemy.ext.asyncio import create_async_engine

from kangaroo.config import Role, get_settings

pytestmark = [
    pytest.mark.live,
    pytest.mark.skipif(os.environ.get("KANGAROO_LIVE") != "1", reason="set KANGAROO_LIVE=1"),
]


class Answer(BaseModel):
    answer: str
    confidence: Literal["low", "medium", "high"]


async def test_openrouter_structured_output() -> None:
    settings = get_settings()
    model = ChatOpenAI(
        model=settings.model_for(Role.ADJUDICATOR),
        base_url=settings.llm_base_url,
        api_key=settings.openrouter_api_key,
        temperature=0,
    )
    structured = model.with_structured_output(Answer, method="function_calling")

    result = await structured.ainvoke("What is the capital of France?")

    assert isinstance(result, Answer)
    assert "paris" in result.answer.lower()


async def test_neon_select_one() -> None:
    engine = create_async_engine(get_settings().async_database_url)

    async with engine.connect() as conn:
        value = await conn.scalar(text("select 1"))

    await engine.dispose()

    assert value == 1
