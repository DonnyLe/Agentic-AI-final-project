"""FastAPI application: JSON API under /api, plus the built React app."""

import logging
from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager
from pathlib import Path

import anyio
from fastapi import Depends, FastAPI, HTTPException, status
from fastapi.responses import FileResponse, HTMLResponse
from fastapi.staticfiles import StaticFiles
from scalar_fastapi import AgentScalarConfig, get_scalar_api_reference

from kangaroo.ai.agents.graph import build_graph
from kangaroo.ai.agents.runner import RunService
from kangaroo.ai.llm import OpenAICompatibleModels
from kangaroo.api.middlewares.auth import require_token
from kangaroo.api.routes import cases, policy, runs
from kangaroo.api.schemas import Health
from kangaroo.api.services import Services
from kangaroo.config import REPO_DIR, Settings, get_settings, setup_logging
from kangaroo.db.postgres import PostgresRepository, make_engine
from kangaroo.policy import load_policy

FRONTEND_DIST = REPO_DIR / "frontend" / "dist"

logger = logging.getLogger(__name__)


def production_services(settings: Settings) -> Services:
    loaded_policy = load_policy()
    models = OpenAICompatibleModels(settings)
    repo = PostgresRepository(make_engine(settings.async_database_url))
    run_service = RunService(
        repo,
        build_graph(models, loaded_policy),
        loaded_policy,
        models.model_names(),
        settings.kangaroo_max_concurrent_runs,
    )

    return Services(repo=repo, runs=run_service, policy=loaded_policy)


def create_app(
    services: Services | None = None,
    settings: Settings | None = None,
    frontend_dist: Path = FRONTEND_DIST,
) -> FastAPI:
    settings = settings or get_settings()

    @asynccontextmanager
    async def lifespan(app: FastAPI) -> AsyncGenerator[None]:
        app.state.services = services or production_services(settings)
        svc = app.state.services
        logger.info(
            "started: policy %s, models %s, %d concurrent runs, access token %s",
            svc.policy.version,
            svc.runs.model_names,
            svc.runs.max_concurrent,
            "on" if app.state.access_token else "off",
        )
        yield
        logger.info("shutting down, waiting for runs in progress")
        await app.state.services.runs.wait_all()
        await app.state.services.repo.close()

    # docs_url=None replaces FastAPI's Swagger UI with Scalar at /docs.
    app = FastAPI(
        title="Kangaroo", version="0.1.0", lifespan=lifespan, docs_url=None, redoc_url=None
    )
    app.state.access_token = settings.kangaroo_access_token.get_secret_value()

    @app.get("/docs", include_in_schema=False)
    async def docs() -> HTMLResponse:
        return get_scalar_api_reference(
            openapi_url=app.openapi_url,
            title="Kangaroo API",
            telemetry=False,
            agent=AgentScalarConfig(disabled=True),
        )

    @app.get("/api/health", tags=["health"])
    async def health() -> Health:
        return Health(ok=True)

    protected = [Depends(require_token)]

    for module in (cases, runs, policy):
        app.include_router(module.router, prefix="/api", dependencies=protected)

    _mount_frontend(app, frontend_dist)

    return app


def _mount_frontend(app: FastAPI, dist: Path) -> None:
    """Serve the built React app, falling back to index.html for client routes."""
    root = dist.resolve()
    index = root / "index.html"

    if not index.is_file():
        logger.warning("no built frontend at %s, serving the API only", root)
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


setup_logging(get_settings().kangaroo_log_level)
app = create_app()
