"""Cloudflare's Clef-flash decision model, as a LangChain `BaseDecisionModel`.

Clef-flash takes a state (text or JSON) and up to 64 typed questions and returns
probabilities instead of generated text. It uses the same noul/choice/score shapes as
`langchain_core.decisions`, so this class only adds the Workers AI call:

    model = DecisionModelClient.from_settings(get_settings())
    response = await model.ainvoke({"state": text, "questions": {"t1": Noul(...)}})

Not wired into the graph yet.
"""

from collections.abc import Sequence
from typing import Any

from cloudflare import AsyncCloudflare, Cloudflare
from langchain_core.decisions import BaseDecisionModel, Box, ClassifierResponse, Question, State
from langchain_core.messages import BaseMessage, convert_to_openai_messages
from pydantic import PrivateAttr, SecretStr

from kangaroo.config import Settings

MAX_QUESTIONS = 64


class DecisionModelClient(BaseDecisionModel):
    """Calls a Clef model through the Cloudflare SDK (auth, retries, response unwrapping)."""

    model: str = "clef-flash"
    account_id: str
    api_token: SecretStr

    _client: Cloudflare = PrivateAttr()
    _async_client: AsyncCloudflare = PrivateAttr()

    def model_post_init(self, context: Any) -> None:
        token = self.api_token.get_secret_value()
        self._client = Cloudflare(api_token=token)
        self._async_client = AsyncCloudflare(api_token=token)

    @classmethod
    def from_settings(cls, settings: Settings) -> "DecisionModelClient":
        return cls(
            account_id=settings.cloudflare_account_id,
            api_token=settings.cloudflare_api_token,
        )

    @property
    def _provider(self) -> str:
        return "cloudflare"

    def _classify(self, state: State, questions: dict[str, Question]) -> ClassifierResponse:
        result = self._client.ai.run(
            f"@cf/cloudflare/{self.model}",
            account_id=self.account_id,
            extra_body=self._body(state, questions),
        )
        return ClassifierResponse.model_validate(result)

    async def _aclassify(self, state: State, questions: dict[str, Question]) -> ClassifierResponse:
        result = await self._async_client.ai.run(
            f"@cf/cloudflare/{self.model}",
            account_id=self.account_id,
            extra_body=self._body(state, questions),
        )
        return ClassifierResponse.model_validate(result)

    def _body(self, state: State, questions: dict[str, Question]) -> dict[str, Any]:
        if not 1 <= len(questions) <= MAX_QUESTIONS:
            count = len(questions)
            raise ValueError(f"The model takes 1 to {MAX_QUESTIONS} questions, got {count}.")

        if any(isinstance(q, Box) for q in questions.values()):
            raise ValueError("Clef doesn't support Box questions.")

        return {
            "model": self.model,
            "state": _state_json(state),
            "questions": {
                qid: q.model_dump(mode="json", exclude_none=True) for qid, q in questions.items()
            },
        }


def _state_json(state: State) -> Any:
    """Send LangChain messages as {"role", "content"} dicts; everything else is JSON already."""
    is_messages = isinstance(state, Sequence) and any(isinstance(m, BaseMessage) for m in state)

    if isinstance(state, BaseMessage) or (is_messages and not isinstance(state, str)):
        return convert_to_openai_messages(state)

    return state
