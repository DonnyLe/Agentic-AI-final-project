"""Compare how reliably models return structured output (intake role).

Usage: uv run python -m kangaroo.compare_models --models a:free b:free --trials 5

For each model, runs the intake prompt on a few cases and counts:
- tool: valid function call on the first try
- text: no valid call, but valid JSON in the reply text
- fail: neither (structured_call would nudge, then give up)
"""

import argparse
import asyncio
import time
from collections import Counter

from langchain_openai import ChatOpenAI

from kangaroo.agents.prompts import intake_messages
from kangaroo.config import get_settings
from kangaroo.corpus import load_cases
from kangaroo.llm import parse_json_reply
from kangaroo.models.agent_io import IntakeResult

SAMPLE_CASES = ["K-002", "K-054", "K-109", "K-063", "K-115"]


async def trial(model: ChatOpenAI, case_id: str) -> str:
    case = next(c for c in load_cases() if c.id == case_id)
    runnable = model.with_structured_output(
        IntakeResult, method="function_calling", include_raw=True
    )

    try:
        result = await runnable.ainvoke(intake_messages(case))
    except Exception:  # noqa: BLE001 - provider errors count as failures
        return "error"

    if isinstance(result["parsed"], IntakeResult):
        return "tool"

    return "text" if parse_json_reply(str(result["raw"].content), IntakeResult) else "fail"


async def compare(models: list[str], trials: int) -> None:
    settings = get_settings()

    for name in models:
        model = ChatOpenAI(
            model=name,
            base_url=settings.llm_base_url,
            api_key=settings.openrouter_api_key,
            temperature=0,
            timeout=60,
            max_retries=1,
        )
        started = time.perf_counter()
        cases = [SAMPLE_CASES[i % len(SAMPLE_CASES)] for i in range(trials)]
        outcomes = Counter([await trial(model, case_id) for case_id in cases])
        seconds = (time.perf_counter() - started) / trials
        print(
            f"| {name} | {outcomes['tool']}/{trials} | {outcomes['text']} | "
            f"{outcomes['fail']} | {outcomes['error']} | {seconds:.1f}s |"
        )


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--models", nargs="+", required=True)
    parser.add_argument("--trials", type=int, default=5)
    args = parser.parse_args()

    print("| Model | Tool call | Text JSON | Fail | Error | Avg time |")
    print("|---|---|---|---|---|---|")
    asyncio.run(compare(args.models, args.trials))


if __name__ == "__main__":
    main()
