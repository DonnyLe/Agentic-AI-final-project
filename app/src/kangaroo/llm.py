"""Chat models per role, and structured output that tolerates sloppy models.

Free models don't always call the output tool. `structured_call` tries, in order:
1. the function call LangChain asked for;
2. JSON found in the reply text;
3. one nudge asking for the tool call again.
If all fail it raises `StructuredOutputError`, which the graph turns into
`needs_review` rather than a guess.
"""

import json
import re
from typing import Protocol

import openai
from langchain_core.language_models import BaseChatModel
from langchain_core.messages import AIMessage, BaseMessage, HumanMessage
from langchain_core.rate_limiters import InMemoryRateLimiter
from langchain_core.runnables import Runnable
from langchain_google_genai import ChatGoogleGenerativeAI
from langchain_openai import ChatOpenAI
from pydantic import BaseModel, ValidationError

from kangaroo.config import Role, Settings


class StructuredOutputError(RuntimeError):
    """A role couldn't produce valid structured output."""


class ModelProvider(Protocol):
    def for_role(self, role: Role) -> BaseChatModel: ...

    def model_names(self) -> dict[str, str]: ...


class OpenAICompatibleModels:
    """ChatOpenAI clients for any OpenAI-compatible endpoint (OpenRouter by default).

    All roles share one rate limiter, because free tiers limit requests per key.
    The OpenAI client itself retries 429s and 5xx with backoff.
    """

    def __init__(self, settings: Settings) -> None:
        self.settings = settings
        limiter = InMemoryRateLimiter(
            requests_per_second=settings.llm_requests_per_minute / 60,
            check_every_n_seconds=0.1,
            max_bucket_size=2,
        )
        self._clients = {role: _client(settings, role, limiter) for role in Role}

    def model_names(self) -> dict[str, str]:
        return {role.value: self.settings.model_for(role) for role in Role}

    def for_role(self, role: Role) -> BaseChatModel:
        return self._clients[role]


def _client(settings: Settings, role: Role, limiter: InMemoryRateLimiter) -> BaseChatModel:
    if settings.llm_provider == "google":
        return ChatGoogleGenerativeAI(
            model=settings.model_for(role),
            google_api_key=settings.google_api_key,
            temperature=0,
            timeout=90,
            max_retries=6,
            rate_limiter=limiter,
        )

    return ChatOpenAI(
        model=settings.model_for(role),
        base_url=settings.llm_base_url,
        api_key=settings.openrouter_api_key,
        temperature=0,
        timeout=90,
        max_retries=6,
        rate_limiter=limiter,
    )


def with_retries[I, O](runnable: Runnable[I, O]) -> Runnable[I, O]:
    """Retry provider errors the OpenAI client doesn't (e.g. OpenRouter's upstream 400s)."""
    return runnable.with_retry(
        retry_if_exception_type=(openai.APIStatusError, openai.APIConnectionError),
        wait_exponential_jitter=True,
        stop_after_attempt=3,
    )


_FENCE_RE = re.compile(r"```(?:json)?\s*(.*?)```", re.S)


def parse_json_reply[T: BaseModel](text: str, schema: type[T]) -> T | None:
    """Pull a JSON object out of free text and validate it, or return None."""
    candidates = [m.group(1) for m in _FENCE_RE.finditer(text)]
    start, end = text.find("{"), text.rfind("}")

    if start != -1 and end > start:
        candidates.append(text[start : end + 1])

    for candidate in candidates:
        try:
            data = json.loads(candidate)
        except json.JSONDecodeError:
            continue

        # Some models wrap the arguments, e.g. {"name": ..., "arguments": {...}}.
        for payload in (data, data.get("arguments"), data.get("parameters")):
            if not isinstance(payload, dict):
                continue

            try:
                return schema.model_validate(payload)
            except ValidationError:
                continue

    return None


async def structured_call[T: BaseModel](
    model: BaseChatModel, schema: type[T], messages: list[BaseMessage]
) -> T:
    runnable = with_retries(
        model.with_structured_output(schema, method="function_calling", include_raw=True)
    )
    result = await runnable.ainvoke(messages)

    if isinstance(result["parsed"], schema):
        return result["parsed"]

    raw: AIMessage = result["raw"]
    text = raw.text if isinstance(raw.text, str) else str(raw.content)

    if parsed := parse_json_reply(text, schema):
        return parsed

    nudge = HumanMessage(
        f"Your last reply was not a valid `{schema.__name__}` tool call "
        f"({result['parsing_error'] or 'no tool call'}). "
        f"Reply only by calling `{schema.__name__}` with valid arguments."
    )
    retry = await runnable.ainvoke([*messages, raw, nudge])

    if isinstance(retry["parsed"], schema):
        return retry["parsed"]

    retry_raw: AIMessage = retry["raw"]

    if parsed := parse_json_reply(str(retry_raw.content), schema):
        return parsed

    raise StructuredOutputError(f"No valid {schema.__name__} after a retry.")
