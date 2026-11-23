"""Runs cases through the graph in the background and records everything."""

import asyncio
import logging
import uuid

from langgraph.graph.state import CompiledStateGraph

from kangaroo.ai.agents.graph import stream_run
from kangaroo.db.records import StoredCase
from kangaroo.db.repository import Repository
from kangaroo.models.decision import Decision
from kangaroo.models.golden import matches_golden
from kangaroo.models.trace import TraceEvent, TraceKind
from kangaroo.policy import Policy

logger = logging.getLogger(__name__)


class CaseNotFoundError(LookupError):
    pass


class TooManyRunsError(RuntimeError):
    pass


class RunService:
    def __init__(
        self,
        repo: Repository,
        graph: CompiledStateGraph,
        policy: Policy,
        model_names: dict[str, str],
        max_concurrent: int,
    ) -> None:
        self.repo = repo
        self.graph = graph
        self.policy = policy
        self.model_names = model_names
        self.max_concurrent = max_concurrent
        self._slots = asyncio.Semaphore(max_concurrent)
        self._waiting_or_running = 0
        self._tasks: set[asyncio.Task[None]] = set()

    async def start(self, case_id: str, queue: bool = False) -> uuid.UUID:
        """Create an evaluation and run it in the background.

        Interactive runs are refused when every slot is busy; batch runs queue.
        """
        if not queue and self._waiting_or_running >= self.max_concurrent:
            raise TooManyRunsError(f"{self.max_concurrent} runs are already in progress.")

        stored = await self.repo.get_case(case_id)

        if stored is None:
            raise CaseNotFoundError(case_id)

        evaluation_id = uuid.uuid4()
        await self.repo.create_evaluation(
            evaluation_id,
            case_id,
            self.model_names,
            self.policy.version,
            golden_label=stored.golden.final if stored.golden else None,
        )

        logger.info("run %s started for case %s", evaluation_id, case_id)
        self._waiting_or_running += 1
        task = asyncio.create_task(self._run(evaluation_id, stored))
        self._tasks.add(task)
        task.add_done_callback(self._tasks.discard)

        return evaluation_id

    async def wait_all(self) -> None:
        """Wait for every background run (used by tests and on shutdown)."""
        while self._tasks:
            await asyncio.gather(*list(self._tasks))

    async def _run(self, evaluation_id: uuid.UUID, stored: StoredCase) -> None:
        seq = 0

        try:
            async with self._slots:
                async for item in stream_run(self.graph, stored.case):
                    if isinstance(item, TraceEvent):
                        seq += 1
                        await self.repo.append_trace(evaluation_id, seq, item)
                    else:
                        await self._finish(evaluation_id, stored, item)
        except Exception as error:
            logger.exception("run %s crashed", evaluation_id)
            message = f"{type(error).__name__}: {error}"
            await self.repo.append_trace(
                evaluation_id,
                seq + 1,
                TraceEvent(node="runner", kind=TraceKind.ERROR, message=message),
            )
            await self.repo.fail_evaluation(evaluation_id, message)
        finally:
            self._waiting_or_running -= 1

    async def _finish(
        self, evaluation_id: uuid.UUID, stored: StoredCase, decision: Decision
    ) -> None:
        golden_match = matches_golden(decision, stored.golden) if stored.golden else None
        await self.repo.complete_evaluation(evaluation_id, decision, golden_match)
        logger.info(
            "run %s finished case %s: %s (golden match: %s)",
            evaluation_id,
            stored.case.id,
            decision.label,
            golden_match,
        )
