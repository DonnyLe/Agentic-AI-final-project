"""Run routes: start runs and batches, stream traces, list and review evaluations."""

import asyncio
import uuid
from collections.abc import AsyncIterator
from typing import Annotated

from fastapi import APIRouter, Header, HTTPException, Query, status
from sse_starlette import EventSourceResponse, ServerSentEvent

from kangaroo.ai.agents.runner import CaseNotFoundError, TooManyRunsError
from kangaroo.api.schemas import (
    BatchStarted,
    NewReview,
    RunDetail,
    RunStarted,
    StartBatch,
    StartRun,
)
from kangaroo.api.services import Services, ServicesDep
from kangaroo.db.records import EvaluationRecord, ReviewRecord

SSE_POLL_SECONDS = 0.5

router = APIRouter(tags=["runs"])


@router.post("/runs", status_code=status.HTTP_202_ACCEPTED)
async def start_run(body: StartRun, svc: ServicesDep) -> RunStarted:
    try:
        evaluation_id = await svc.runs.start(body.case_id)
    except CaseNotFoundError as error:
        raise HTTPException(status.HTTP_404_NOT_FOUND, f"No case {body.case_id}.") from error
    except TooManyRunsError as error:
        raise HTTPException(status.HTTP_429_TOO_MANY_REQUESTS, str(error)) from error

    return RunStarted(evaluation_id=evaluation_id)


@router.post("/batch-eval", status_code=status.HTTP_202_ACCEPTED)
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


@router.get("/runs/{evaluation_id}")
async def get_run(evaluation_id: uuid.UUID, svc: ServicesDep) -> RunDetail:
    return await _run_detail(svc, evaluation_id)


@router.get("/runs/{evaluation_id}/events")
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


@router.get("/evaluations")
async def list_evaluations(
    svc: ServicesDep, case_id: str | None = None, limit: int = Query(100, le=500)
) -> list[EvaluationRecord]:
    return await svc.repo.list_evaluations(case_id=case_id, limit=limit)


@router.post(
    "/evaluations/{evaluation_id}/reviewer-decision",
    status_code=status.HTTP_201_CREATED,
)
async def add_review(evaluation_id: uuid.UUID, body: NewReview, svc: ServicesDep) -> ReviewRecord:
    """Records the reviewer's decision. Nothing is executed (alpha: propose only)."""
    evaluation = await svc.repo.get_evaluation(evaluation_id)

    if evaluation is None or evaluation.status != "completed":
        raise HTTPException(status.HTTP_409_CONFLICT, "Only completed runs can be reviewed.")

    return await svc.repo.add_review(evaluation_id, body.decision, body.reviewer, body.note)
