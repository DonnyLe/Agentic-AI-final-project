# Kangaroo

Policy-governed meeting action agent (CS4973 FP3 alpha). A reviewer picks a meeting
case, runs it through a LangGraph multi-agent workflow (intake, supervisor, evidence,
adjudicator, code guards), watches the agent trace live, and gets a decision with the
broken policy rules, evidence, rationale and proposed action. T1 and T2 actions are
supported; T3/T4 actions are marked `unsupported`. Approve/Reject only records the
reviewer's decision; nothing is executed.

- `app/`: Python backend (FastAPI, LangGraph, SQLAlchemy + Alembic, Postgres)
- `frontend/`: React reviewer UI (Vite, Tailwind)
- `data/`: FP2 policy, corpus and golden labels
- `docs/`: plans, alpha eval results, model comparison

## Prerequisites

- Python 3.13 and [uv](https://docs.astral.sh/uv/) 0.12+
- [Bun](https://bun.sh/) 1.4+ and Node 22.18+
- Docker (for the local Postgres)
- An [OpenRouter](https://openrouter.ai/keys) API key (free models work)

## Setup

```bash
# Local Postgres on localhost:5432
docker compose up -d

# Backend
cd app
cp .env.example .env        # fill in OPENROUTER_API_KEY; DATABASE_URL already points at local Postgres
uv sync
uv run alembic upgrade head

# Frontend
cd ../frontend
bun install
```

## Run locally

```bash
# Terminal 1: API on :8000
cd app && uv run uvicorn kangaroo.app:app --port 8000 --reload

# Terminal 2: UI on :5173 (proxies /api to :8000)
cd frontend && bun run dev
```

Open the UI, pick a case, and press **Run case**.

## Environments

Local dev reads `app/.env` (local Postgres). The deployed Neon database lives in
`app/.env.prod`, which is only read when `KANGAROO_ENV=prod` is set. Both files are
gitignored.

```bash
KANGAROO_ENV=prod uv run alembic upgrade head      # migrate Neon
```

## Tests and checks

```bash
cd app && uv run pytest && uv run ruff check && uv run ruff format --check
cd frontend && bun run check
```

## mise tasks

`mise.toml` wraps the commands above. Run `mise tasks` for the full list.

```bash
mise install                  # uv, bun and node at the pinned versions
mise run install              # uv sync + bun install
mise run db:up                # local Postgres
mise run db:dev:migrate:up    # alembic upgrade head
mise run dev                  # API on :8000 and UI on :5173
mise run check                # what CI runs: lint, format check, typecheck, tests
mise run fix                  # lint autofixes + format
```

`db:dev:*` tasks use the local database (`app/.env`). `db:prod:*` tasks use Neon (they
set `KANGAROO_ENV=prod`, so they read `app/.env.prod`):

```bash
mise run db:prod:migrate:status   # current revision, latest revision, model drift check
mise run db:prod:migrate:up       # alembic upgrade head
```

## Deploy (Render)

`render.yaml` is a Render blueprint for one Docker web service built from
`Dockerfile`. Bun builds the SPA, and FastAPI serves it together with `/api`.
Migrations also run on container start, so a deploy never boots against an old schema.

1. Push the branch, then in Render choose **New > Blueprint** and pick this repo.
2. When prompted, enter `OPENROUTER_API_KEY`, `DATABASE_URL` (the Neon URL from
   `app/.env.prod`) and optionally `KANGAROO_ACCESS_TOKEN`. With a token set, the UI
   asks for it once and keeps it in the browser.
3. Before the first deploy, run `mise run db:prod:migrate:status` and, if needed,
   `db:prod:migrate:up`.

The free plan sleeps after 15 minutes idle, so the first request after that is slow.
