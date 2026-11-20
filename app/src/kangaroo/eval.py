"""Alpha evaluation: run golden cases through the API and write a markdown table.

Usage:
  uv run python -m kangaroo.eval                       # local server, default 11 cases
  uv run python -m kangaroo.eval --base-url https://... --token ... --fresh
  uv run python -m kangaroo.eval --cases K-002 K-054

Completed runs are reused unless --fresh, so re-running doesn't spend model quota.
Ambiguous/injection tags come from the corpus file and are used for the report only.
"""

import argparse
import asyncio
import json
import sys
from pathlib import Path

import httpx
from pydantic import BaseModel

from kangaroo.config import REPO_DIR
from kangaroo.corpus import CORPUS_PATH

DEFAULT_CASES = [
    "K-002",
    "K-012",
    "K-020",
    "K-113",
    "K-051",
    "K-054",
    "K-059",
    "K-115",
    "K-109",
    "K-063",
    "K-105",
]
DEFAULT_OUT = REPO_DIR / "docs" / "alpha_eval.md"
POLL_SECONDS = 2.0
TIMEOUT_SECONDS = 600


class Row(BaseModel):
    case_id: str
    category: str
    golden: str
    in_scope: bool
    label: str
    match: bool | None
    proposed_action: str
    flags: list[str]
    evaluation_id: str
    error: str | None


def _categories(case_ids: list[str]) -> dict[str, str]:
    wanted = set(case_ids)
    tags: dict[str, str] = {}

    with CORPUS_PATH.open(encoding="utf-8") as f:
        for line in f:
            raw = json.loads(line)

            if raw["id"] not in wanted:
                continue

            kind = "clean" if raw["seeded_tier"] == "none" else "violation"
            extras = [t for t in ("ambiguous", "injection") if raw[t]]
            tags[raw["id"]] = " ".join([raw["target_tier"], kind, *extras])

    return tags


async def _latest_completed(client: httpx.AsyncClient, case_id: str) -> str | None:
    response = await client.get("/api/evaluations", params={"case_id": case_id, "limit": 20})
    response.raise_for_status()

    return next((e["id"] for e in response.json() if e["status"] == "completed"), None)


async def _wait(client: httpx.AsyncClient, evaluation_id: str) -> dict:
    for _ in range(int(TIMEOUT_SECONDS / POLL_SECONDS)):
        response = await client.get(f"/api/runs/{evaluation_id}")
        response.raise_for_status()
        evaluation = response.json()["evaluation"]

        if evaluation["status"] != "running":
            return evaluation

        await asyncio.sleep(POLL_SECONDS)

    raise TimeoutError(f"Run {evaluation_id} didn't finish in {TIMEOUT_SECONDS}s.")


async def evaluate(base_url: str, token: str, case_ids: list[str], fresh: bool) -> list[Row]:
    headers = {"X-Access-Token": token} if token else {}

    async with httpx.AsyncClient(base_url=base_url, headers=headers, timeout=60) as client:
        reuse = {} if fresh else {cid: await _latest_completed(client, cid) for cid in case_ids}
        to_run = [cid for cid in case_ids if not reuse.get(cid)]
        ids = dict(reuse)

        if to_run:
            print(f"running {len(to_run)} case(s): {' '.join(to_run)}", file=sys.stderr)
            response = await client.post("/api/batch-eval", json={"case_ids": to_run})
            response.raise_for_status()
            ids.update(zip(to_run, response.json()["evaluation_ids"], strict=True))

        evaluations = await asyncio.gather(*(_wait(client, ids[cid]) for cid in case_ids))
        cases = await asyncio.gather(*(client.get(f"/api/cases/{cid}") for cid in case_ids))

    categories = _categories(case_ids)
    rows: list[Row] = []

    for case_id, evaluation, case_response in zip(case_ids, evaluations, cases, strict=True):
        golden = case_response.json()["golden"] or {}
        action = evaluation["proposed_action"] or {}
        rows.append(
            Row(
                case_id=case_id,
                category=categories.get(case_id, ""),
                golden=golden.get("final", "?"),
                in_scope=golden.get("action_tier") in {"T1", "T2"},
                label=evaluation["label"] or evaluation["status"],
                match=evaluation["golden_match"],
                proposed_action=action.get("summary", ""),
                flags=evaluation["flags"],
                evaluation_id=evaluation["id"],
                error=evaluation["error"],
            )
        )

    return rows


def to_markdown(rows: list[Row]) -> str:
    in_scope = [r for r in rows if r.in_scope]
    out_scope = [r for r in rows if not r.in_scope]
    matched = sum(1 for r in in_scope if r.match)
    unsupported_ok = sum(1 for r in out_scope if r.match)
    lines = [
        "| Case | Category | Golden | Kangaroo | Match | Proposed action | Flags |",
        "|---|---|---|---|---|---|---|",
        *(
            f"| {r.case_id} | {r.category} | `{r.golden}` | `{r.label}` | "
            f"{'yes' if r.match else 'no'} | {r.proposed_action} | {', '.join(r.flags) or '—'} |"
            for r in rows
        ),
        "",
        f"- In scope (T1/T2): **{matched}/{len(in_scope)}** exact label matches.",
        f"- Out of scope (T3/T4): **{unsupported_ok}/{len(out_scope)}** "
        "correctly marked unsupported.",
    ]
    agent_errors = [r.case_id for r in rows if "agent_error" in r.flags]

    if agent_errors:
        lines.append(
            "- Held because of model/provider errors, not policy judgment: "
            + ", ".join(agent_errors)
        )

    failures = [r for r in rows if r.error]

    if failures:
        lines.append(f"- Failed runs: {', '.join(f'{r.case_id} ({r.error})' for r in failures)}")

    return "\n".join(lines) + "\n"


def main() -> None:
    parser = argparse.ArgumentParser(description="Run the alpha evaluation through the API.")
    parser.add_argument("--base-url", default="http://localhost:8000")
    parser.add_argument("--token", default="")
    parser.add_argument("--cases", nargs="+", default=DEFAULT_CASES)
    parser.add_argument("--fresh", action="store_true", help="ignore earlier completed runs")
    parser.add_argument("--out", type=Path, default=DEFAULT_OUT)
    args = parser.parse_args()

    rows = asyncio.run(evaluate(args.base_url, args.token, args.cases, args.fresh))
    markdown = to_markdown(rows)
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(markdown, encoding="utf-8")
    print(markdown)
    print(f"wrote {args.out}", file=sys.stderr)


if __name__ == "__main__":
    main()
