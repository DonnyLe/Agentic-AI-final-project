"""HTTP API tests: real FastAPI app over httpx, in-memory repository, scripted models."""

import asyncio
from collections.abc import AsyncIterator
from pathlib import Path

import httpx
import pytest
from fakes import ScriptedModels, structured
from fastapi import FastAPI
from pydantic import SecretStr

from kangaroo.api.app import Services, create_app
from kangaroo.config import Role, Settings
from kangaroo.corpus import load_cases, load_golden_labels
from kangaroo.db.memory import InMemoryRepository
from kangaroo.graph import build_graph
from kangaroo.models.agent_io import AdjudicatorOutput, IntakeResult, SupervisorDecision
from kangaroo.policy import load_policy
from kangaroo.runs import RunService, TooManyRunsError

POLICY = load_policy()
CASES = {case.id: case for case in load_cases()}
GOLDEN = [label for label in load_golden_labels() if label.case_id in {"K-012", "K-063"}]


def t1_script() -> ScriptedModels:
    return ScriptedModels(
        {
            Role.INTAKE: [
                structured(
                    IntakeResult(
                        action_type_hint="record",
                        action_summary="record a decision",
                        proposers=["Tom Ricci"],
                        cited_segment_ids=[],
                    )
                )
            ],
            Role.SUPERVISOR: [
                structured(
                    SupervisorDecision(
                        tier="T1",
                        tier_reason="saves a note",
                        next_step="adjudicate",
                        reason="transcript only",
                    )
                )
            ],
            Role.EVIDENCE: [],
            Role.ADJUDICATOR: [
                structured(
                    AdjudicatorOutput(
                        verdict="violation", broken_rule_ids=["R1.1"], rationale="objection open"
                    )
                )
            ],
        }
    )


async def make_services(models: ScriptedModels, max_concurrent: int = 2) -> Services:
    repo = InMemoryRepository()
    await repo.upsert_cases([CASES["K-012"], CASES["K-063"]], source="corpus")
    await repo.upsert_golden_labels(GOLDEN)
    graph = build_graph(models, POLICY)
    runs = RunService(repo, graph, POLICY, models.model_names(), max_concurrent)

    return Services(repo=repo, runs=runs, policy=POLICY)


def settings(token: str = "") -> Settings:
    return Settings(_env_file=None, kangaroo_access_token=SecretStr(token))


async def open_client(app: FastAPI) -> AsyncIterator[httpx.AsyncClient]:
    """httpx doesn't run ASGI lifespan events, so run them around the client."""
    transport = httpx.ASGITransport(app)

    async with (
        app.router.lifespan_context(app),
        httpx.AsyncClient(transport=transport, base_url="http://test") as client,
    ):
        yield client


@pytest.fixture
async def client(tmp_path: Path) -> AsyncIterator[httpx.AsyncClient]:
    app = create_app(await make_services(t1_script()), settings(), frontend_dist=tmp_path)

    async for test_client in open_client(app):
        yield test_client


async def wait_for_completion(client: httpx.AsyncClient, evaluation_id: str) -> dict:
    for _ in range(200):
        body = (await client.get(f"/api/runs/{evaluation_id}")).json()

        if body["evaluation"]["status"] != "running":
            return body

        await asyncio.sleep(0.01)

    raise AssertionError("run did not finish")


async def test_health_and_cases(client: httpx.AsyncClient) -> None:
    assert (await client.get("/api/health")).json() == {"ok": True}

    cases = (await client.get("/api/cases")).json()

    assert [c["id"] for c in cases] == ["K-012", "K-063"]
    assert cases[0]["golden_label"] == "T1 R1.1"
    assert (await client.get("/api/cases/K-999")).status_code == 404


async def test_create_custom_case(client: httpx.AsyncClient) -> None:
    content = CASES["K-012"].content.model_dump(mode="json")

    response = await client.post("/api/cases", json={"content": content})

    assert response.status_code == 201
    assert response.json()["case"]["id"] == "C-001"
    assert (await client.get("/api/cases/C-001")).json()["source"] == "custom"


async def test_run_lifecycle_trace_and_review(client: httpx.AsyncClient) -> None:
    started = await client.post("/api/runs", json={"case_id": "K-012"})

    assert started.status_code == 202

    evaluation_id = started.json()["evaluation_id"]
    detail = await wait_for_completion(client, evaluation_id)
    evaluation = detail["evaluation"]

    assert evaluation["label"] == "T1 R1.1"
    assert evaluation["golden_match"] is True
    assert [t["seq"] for t in detail["trace"]] == list(range(1, len(detail["trace"]) + 1))
    assert {t["event"]["kind"] for t in detail["trace"]} >= {"intake", "route", "decision"}

    review = await client.post(
        f"/api/evaluations/{evaluation_id}/reviewer-decision",
        json={"decision": "approve", "reviewer": "Maya Chen", "note": "agreed"},
    )
    run = (await client.get(f"/api/runs/{evaluation_id}")).json()
    history = (await client.get("/api/evaluations")).json()

    assert review.status_code == 201
    assert run["reviews"][0]["decision"] == "approve"
    assert [e["id"] for e in history] == [evaluation_id]


async def test_review_requires_a_completed_run(client: httpx.AsyncClient) -> None:
    missing = "00000000-0000-0000-0000-000000000000"
    body = {"decision": "reject", "reviewer": "Maya Chen"}

    response = await client.post(f"/api/evaluations/{missing}/reviewer-decision", json=body)

    assert response.status_code == 409


async def test_sse_replays_trace_then_done(client: httpx.AsyncClient) -> None:
    started = await client.post("/api/runs", json={"case_id": "K-012"})
    evaluation_id = started.json()["evaluation_id"]
    await wait_for_completion(client, evaluation_id)

    lines = (await client.get(f"/api/runs/{evaluation_id}/events?after=1")).text.splitlines()
    ids = [line.removeprefix("id:").strip() for line in lines if line.startswith("id:")]
    events = [line.removeprefix("event:").strip() for line in lines if line.startswith("event:")]

    assert ids[0] == "2"
    assert events[:-1] == ["trace"] * (len(events) - 1)
    assert events[-1] == "done"


async def test_unknown_run_and_case(client: httpx.AsyncClient) -> None:
    missing = "00000000-0000-0000-0000-000000000000"

    assert (await client.post("/api/runs", json={"case_id": "K-999"})).status_code == 404
    assert (await client.get(f"/api/runs/{missing}")).status_code == 404
    assert (await client.get(f"/api/runs/{missing}/events")).status_code == 404

    batch = await client.post("/api/batch-eval", json={"case_ids": ["K-999"]})

    assert batch.status_code == 404


async def test_policy(client: httpx.AsyncClient) -> None:
    body = (await client.get("/api/policy")).json()

    assert body["version"] == "1.3"
    assert len(body["rules"]) == 14


async def test_access_token(tmp_path: Path) -> None:
    app = create_app(await make_services(t1_script()), settings("s3cret"), frontend_dist=tmp_path)

    async for client in open_client(app):
        assert (await client.get("/api/health")).status_code == 200
        assert (await client.get("/api/cases")).status_code == 401

        with_header = await client.get("/api/cases", headers={"X-Access-Token": "s3cret"})
        with_query = await client.get("/api/cases?access_token=s3cret")

        assert with_header.status_code == 200
        assert with_query.status_code == 200


async def test_spa_fallback(tmp_path: Path) -> None:
    (tmp_path / "assets").mkdir()
    (tmp_path / "index.html").write_text("<div id=root></div>")
    (tmp_path / "assets" / "app.js").write_text("console.log(1)")
    app = create_app(await make_services(t1_script()), settings(), frontend_dist=tmp_path)

    async for client in open_client(app):
        assert "root" in (await client.get("/runs/abc")).text
        assert (await client.get("/assets/app.js")).text == "console.log(1)"
        assert (await client.get("/api/nope")).status_code == 404


async def test_interactive_runs_are_capped_but_batches_queue() -> None:
    services = await make_services(t1_script(), max_concurrent=1)

    await services.runs.start("K-063")

    with pytest.raises(TooManyRunsError):
        await services.runs.start("K-063")

    await services.runs.start("K-063", queue=True)
    await services.runs.wait_all()
