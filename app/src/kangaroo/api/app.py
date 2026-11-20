"""FastAPI application: JSON API under /api, plus the built React app."""

import asyncio
import uuid
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from dataclasses import dataclass
from pathlib import Path
from typing import Annotated

import anyio
from fastapi import Depends, FastAPI, Header, HTTPException, Query, Request, status
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from sse_starlette import EventSourceResponse, ServerSentEvent

from kangaroo.api.schemas import (
    BatchStarted,
    Health,
    NewCase,
    NewReview,
    PolicyView,
    RunDetail,
    RunStarted,
    StartBatch,
    StartRun,
)
from kangaroo.config import REPO_DIR, Settings, get_settings
from kangaroo.db.postgres import PostgresRepository, make_engine
from kangaroo.db.records import CaseSummary, EvaluationRecord, ReviewRecord, StoredCase
from kangaroo.db.repository import Repository
from kangaroo.graph import build_graph
from kangaroo.llm import OpenAICompatibleModels
from kangaroo.models.case import Case
from kangaroo.policy import Policy, load_policy
from kangaroo.runs import CaseNotFoundError, RunService, TooManyRunsError

FRONTEND_DIST = REPO_DIR / "frontend" / "dist"
SSE_POLL_SECONDS = 0.5


@dataclass
class Services:
    repo: Repository
    runs: RunService
    policy: Policy


def get_services(request: Request) -> Services:
    return request.app.state.services


ServicesDep = Annotated[Services, Depends(get_services)]


def production_services(settings: Settings) -> Services:
    policy = load_policy()
    models = OpenAICompatibleModels(settings)
    repo = PostgresRepository(make_engine(settings.async_database_url))
    runs = RunService(
        repo,
        build_graph(models, policy),
        policy,
        models.model_names(),
        settings.kangaroo_max_concurrent_runs,
    )

    return Services(repo=repo, runs=runs, policy=policy)


def create_app(
    services: Services | None = None,
    settings: Settings | None = None,
    frontend_dist: Path = FRONTEND_DIST,
) -> FastAPI:
    settings = settings or get_settings()

    @asynccontextmanager
    async def lifespan(app: FastAPI) -> AsyncIterator[None]:
        app.state.services = services or production_services(settings)
        yield
        await app.state.services.runs.wait_all()
        await app.state.services.repo.close()

    app = FastAPI(title="Kangaroo", version="0.1.0", lifespan=lifespan)
    token = settings.kangaroo_access_token.get_secret_value()

    def require_token(
        x_access_token: Annotated[str | None, Header()] = None,
        access_token: Annotated[str | None, Query()] = None,
    ) -> None:
        # EventSource can't send headers, so the SSE endpoint takes ?access_token=.
        if token and token not in (x_access_token, access_token):
            raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Missing or wrong access token.")

    protected = [Depends(require_token)]

    @app.get("/api/health")
    async def health() -> Health:
        return Health(ok=True)

    @app.get("/api/cases", dependencies=protected)
    async def list_cases(svc: ServicesDep) -> list[CaseSummary]:
        return await svc.repo.list_cases()

    @app.get("/api/cases/{case_id}", dependencies=protected)
    async def get_case(case_id: str, svc: ServicesDep) -> StoredCase:
        stored = await svc.repo.get_case(case_id)

        if stored is None:
            raise HTTPException(status.HTTP_404_NOT_FOUND, f"No case {case_id}.")

        return stored

    @app.post("/api/cases", dependencies=protected, status_code=status.HTTP_201_CREATED)
    async def create_case(body: NewCase, svc: ServicesDep) -> StoredCase:
        case = Case(id=await svc.repo.next_custom_case_id(), content=body.content)
        await svc.repo.upsert_cases([case], source="custom")

        return StoredCase(case=case, source="custom", golden=None)

    @app.post("/api/runs", dependencies=protected, status_code=status.HTTP_202_ACCEPTED)
    async def start_run(body: StartRun, svc: ServicesDep) -> RunStarted:
        try:
            evaluation_id = await svc.runs.start(body.case_id)
        except CaseNotFoundError as error:
            raise HTTPException(status.HTTP_404_NOT_FOUND, f"No case {body.case_id}.") from error
        except TooManyRunsError as error:
            raise HTTPException(status.HTTP_429_TOO_MANY_REQUESTS, str(error)) from error

        return RunStarted(evaluation_id=evaluation_id)

    @app.post("/api/batch-eval", dependencies=protected, status_code=status.HTTP_202_ACCEPTED)
    async def start_batch(body: StartBatch, svc: ServicesDep) -> BatchStarted:
        missing = [cid for cid in body.case_ids if await svc.repo.get_case(cid) is None]

        if missing:
            raise HTTPException(status.HTTP_404_NOT_FOUND, f"Unknown cases: {', '.join(missing)}")

        ids = [await svc.runs.start(cid, queue=True) for cid in body.case_ids]

        return BatchStarted(evaluation_ids=ids)

    async def _run_detail(svc: Services, evaluation_id: uuid.UUID) -> RunDetail:
        evaluation = await svc.repo.get_evaluation(evaluation_id)

        if evaluation is None:
            raise HTTPException(status.HTTP_404_NOT_FOUND, f"No run {evaluation_id}.")

        return RunDetail(
            evaluation=evaluation,
            trace=await svc.repo.list_trace(evaluation_id),
            reviews=await svc.repo.list_reviews(evaluation_id),
        )

    @app.get("/api/runs/{evaluation_id}", dependencies=protected)
    async def get_run(evaluation_id: uuid.UUID, svc: ServicesDep) -> RunDetail:
        return await _run_detail(svc, evaluation_id)

    @app.get("/api/runs/{evaluation_id}/events", dependencies=protected)
    async def run_events(
        evaluation_id: uuid.UUID,
        svc: ServicesDep,
        after: int = 0,
        last_event_id: Annotated[int | None, Header()] = None,
    ) -> EventSourceResponse:
        if await svc.repo.get_evaluation(evaluation_id) is None:
            raise HTTPException(status.HTTP_404_NOT_FOUND, f"No run {evaluation_id}.")

        start_after = last_event_id if last_event_id is not None else after

        async def events() -> AsyncIterator[ServerSentEvent]:
            seen = start_after

            while True:
                for record in await svc.repo.list_trace(evaluation_id, after_seq=seen):
                    seen = record.seq
                    yield ServerSentEvent(
                        id=str(record.seq),
                        event="trace",
                        data=record.model_dump_json(),
                    )

                evaluation = await svc.repo.get_evaluation(evaluation_id)

                if evaluation is not None and evaluation.status != "running":
                    # Drain anything written between the last read and the status change.
                    for record in await svc.repo.list_trace(evaluation_id, after_seq=seen):
                        seen = record.seq
                        yield ServerSentEvent(
                            id=str(record.seq), event="trace", data=record.model_dump_json()
                        )

                    yield ServerSentEvent(event="done", data=evaluation.model_dump_json())
                    return

                await asyncio.sleep(SSE_POLL_SECONDS)

        return EventSourceResponse(events(), ping=15)

    @app.get("/api/evaluations", dependencies=protected)
    async def list_evaluations(
        svc: ServicesDep, case_id: str | None = None, limit: int = Query(100, le=500)
    ) -> list[EvaluationRecord]:
        return await svc.repo.list_evaluations(case_id=case_id, limit=limit)

    @app.post(
        "/api/evaluations/{evaluation_id}/reviewer-decision",
        dependencies=protected,
        status_code=status.HTTP_201_CREATED,
    )
    async def add_review(
        evaluation_id: uuid.UUID, body: NewReview, svc: ServicesDep
    ) -> ReviewRecord:
        """Records the reviewer's decision. Nothing is executed (alpha: propose only)."""
        evaluation = await svc.repo.get_evaluation(evaluation_id)

        if evaluation is None or evaluation.status != "completed":
            raise HTTPException(status.HTTP_409_CONFLICT, "Only completed runs can be reviewed.")

        return await svc.repo.add_review(evaluation_id, body.decision, body.reviewer, body.note)

    @app.get("/api/policy", dependencies=protected)
    async def policy(svc: ServicesDep) -> PolicyView:
        return PolicyView(
            version=svc.policy.version,
            rules=list(svc.policy.rules.values()),
            markdown=svc.policy.text,
        )

    _mount_frontend(app, frontend_dist)

    return app


def _mount_frontend(app: FastAPI, dist: Path) -> None:
    """Serve the built React app, falling back to index.html for client routes."""
    root = dist.resolve()
    index = root / "index.html"

    if not index.is_file():
        return

    if (root / "assets").is_dir():
        app.mount("/assets", StaticFiles(directory=root / "assets"), name="assets")

    @app.get("/{path:path}", include_in_schema=False)
    async def spa(path: str) -> FileResponse:
        if path.startswith("api/"):
            raise HTTPException(status.HTTP_404_NOT_FOUND)

        candidate = await anyio.Path(root / path).resolve()

        if path and await candidate.is_file() and candidate.is_relative_to(root):
            return FileResponse(Path(candidate))

        return FileResponse(index)


app = create_app()
