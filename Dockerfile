# One image for the whole app: Bun builds the React SPA, then FastAPI serves it and /api.

FROM oven/bun:1.4.2 AS frontend
WORKDIR /srv/frontend
COPY frontend/package.json frontend/bun.lock ./
RUN bun install --frozen-lockfile
COPY frontend/ ./
RUN bun run build

FROM python:3.13-slim
COPY --from=ghcr.io/astral-sh/uv:0.12.16 /uv /bin/uv
ENV UV_COMPILE_BYTECODE=1 UV_LINK_MODE=copy PYTHONUNBUFFERED=1

# Keep the repo layout (app/, data/, frontend/dist/): config.py finds data and the
# built SPA relative to app/.
WORKDIR /srv/app
COPY app/pyproject.toml app/uv.lock ./
RUN uv sync --frozen --no-dev --no-install-project
COPY app/ ./
RUN uv sync --frozen --no-dev
COPY data/ /srv/data/
COPY --from=frontend /srv/frontend/dist /srv/frontend/dist

ENV PATH="/srv/app/.venv/bin:$PATH" PORT=8000
EXPOSE 8000

# Migrations are idempotent, so running them on every start is safe.
CMD ["sh", "-c", "alembic upgrade head && uvicorn kangaroo.api.app:app --host 0.0.0.0 --port $PORT"]
