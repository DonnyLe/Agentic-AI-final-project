"""A scripted chat model for offline tests (no network)."""

import json
import uuid
from collections.abc import Sequence
from typing import Any

from langchain_core.callbacks import AsyncCallbackManagerForLLMRun, CallbackManagerForLLMRun
from langchain_core.language_models import BaseChatModel
from langchain_core.messages import AIMessage, BaseMessage
from langchain_core.outputs import ChatGeneration, ChatResult
from pydantic import BaseModel, PrivateAttr

from kangaroo.config import Role


def tool_reply(name: str, args: dict[str, Any]) -> AIMessage:
    """An AI message that calls one tool."""
    return AIMessage(content="", tool_calls=[{"name": name, "args": args, "id": uuid.uuid4().hex}])


def structured(model: BaseModel) -> AIMessage:
    """An AI message that returns `model` the way with_structured_output expects."""
    return tool_reply(type(model).__name__, json.loads(model.model_dump_json()))


class ScriptedChatModel(BaseChatModel):
    """Replies with the scripted messages in order and records what it was sent."""

    script: list[AIMessage]
    _calls: list[list[BaseMessage]] = PrivateAttr(default_factory=list)

    @property
    def _llm_type(self) -> str:
        return "scripted"

    @property
    def calls(self) -> list[list[BaseMessage]]:
        return self._calls

    def bind_tools(self, tools: Sequence[Any], **kwargs: Any) -> "ScriptedChatModel":
        return self

    def _generate(
        self,
        messages: list[BaseMessage],
        stop: list[str] | None = None,
        run_manager: CallbackManagerForLLMRun | None = None,
        **kwargs: Any,
    ) -> ChatResult:
        self._calls.append(list(messages))

        if not self.script:
            raise AssertionError("ScriptedChatModel ran out of scripted replies")

        return ChatResult(generations=[ChatGeneration(message=self.script.pop(0))])

    async def _agenerate(
        self,
        messages: list[BaseMessage],
        stop: list[str] | None = None,
        run_manager: AsyncCallbackManagerForLLMRun | None = None,
        **kwargs: Any,
    ) -> ChatResult:
        return self._generate(messages, stop)


class ScriptedModels:
    """ModelProvider that hands out one scripted model per role."""

    def __init__(self, scripts: dict[Role, list[AIMessage]]) -> None:
        self.models = {role: ScriptedChatModel(script=list(msgs)) for role, msgs in scripts.items()}

    def for_role(self, role: Role) -> BaseChatModel:
        return self.models[role]

    def model_names(self) -> dict[str, str]:
        return {role.value: "scripted" for role in Role}
