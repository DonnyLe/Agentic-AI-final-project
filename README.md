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
uv run python -m kangaroo.seed   # loads data/corpus.jsonl and data/golden.csv

# Frontend
cd ../frontend
bun install
```

## Run locally

```bash
# Terminal 1: API on :8000
cd app && uv run uvicorn kangaroo.api.app:app --port 8000 --reload

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
KANGAROO_ENV=prod uv run python -m kangaroo.seed   # seed Neon
```

## Tests and checks

```bash
cd app && uv run pytest && uv run ruff check && uv run ruff format --check
cd frontend && bun run check
```

## Alpha evaluation

With the API running, this runs the 11 golden alpha cases and writes a markdown table
(see `docs/alpha_eval.md`):

```bash
cd app && uv run python -m kangaroo.eval
uv run python -m kangaroo.eval --base-url https://<deployed-url> --token <token>
```

## Deploy (Render)

`render.yaml` describes one Docker web service built from `Dockerfile`: Bun builds the
SPA, and FastAPI serves it together with `/api`. Migrations run on container start.
Create the service from the blueprint, then set `OPENROUTER_API_KEY`, `DATABASE_URL`
(the Neon URL) and optionally `KANGAROO_ACCESS_TOKEN` in the Render dashboard. With
an access token set, the UI asks for it once and keeps it in the browser.
