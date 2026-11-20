# Kangaroo FP3 alpha: implementation plan (v4, Python)

Domain requirements, data facts and FP3 requirements: `docs/fp3-alpha-brief.md`. Its stack section (TypeScript, Flue, Cloudflare) is superseded by this plan.

## Stack
- **Backend (`app/`)**: Python 3.13, uv, `pyproject.toml`, ruff (lint + format), pydantic + pydantic-settings, LangGraph + LangChain (`langchain-openai` `ChatOpenAI` pointed at OpenRouter), FastAPI + uvicorn, SSE for live traces, pytest.
- **Database**: Neon Postgres. SQLAlchemy 2 (async, psycopg 3) + Alembic migrations. All access through repository classes in `kangaroo/db/`; nothing else imports SQLAlchemy, so the database can be swapped.
- **LLMs**: OpenRouter, OpenAI-compatible. Per-role model from `KANGAROO_MODEL_<ROLE>` (fallback `KANGAROO_MODEL_DEFAULT`), shared `LLM_BASE_URL` + key. Default `nvidia/nemotron-3.5-lightning:free` (1,000 free requests/day on this key).
- **Frontend (`frontend/`)**: React + TS + Vite, Bun, Tailwind CSS + Motion. oxlint + vendored anti-slop + oxfmt. `@/*` import alias. Typed API client generated from FastAPI's OpenAPI schema (`openapi-typescript`). Look: clean, artistic, minimal, dithering animations and ASCII art (inspired by instinct.com, Decagon). Design direction shown for approval before building screens.
- **Deploy**: Render, one Docker web service. Multi-stage `Dockerfile` (Bun builds the SPA, uv runtime serves FastAPI + the built SPA). `render.yaml` blueprint describes the service, health check and env vars (secrets marked `sync: false`).
- FP2 data stays in `data/`; its Python scripts are unchanged.

## Layout
```
app/          pyproject.toml, uv.lock, .env(.example), alembic.ini, alembic/
  src/kangaroo/  config.py, models/, policy/, tools/, agents/, graph/, guards/, db/, api/, eval/
  tests/
frontend/     React app
data/  docs/
Dockerfile  render.yaml  README.md
```

## Agent flow (LangGraph StateGraph, one run per case)
1. **Intake** (LLM, structured): action class T1–T4, proposers, cited segments, entities.
2. **T3/T4 → `unsupported`** in code; no further model calls.
3. **Supervisor** (LLM): picks the evidence plan for this case (T1 → adjudicate; T2 with a third-party claim → duplicate search + dependency check + ticket lookup; T2 without → duplicate search only). After each evidence round: adjudicate, one more round (max 2), or escalate to `needs_review`. Each decision and its reason goes to the trace.
4. **Evidence agent** (LLM + tools): `search_tickets`, `get_ticket`, `verify_dependency`, `get_team_roster`, `get_transcript_segments`. Tools read the case's evidence snapshot, normalize key variants (approval/approvals, package_registry(_lookup), upstream_issue(s)(_lookup), repro/repro_steps/reproduction_steps), and mark evidence text as untrusted; a regex flags possible injection text for the UI.
5. **Adjudicator** (LLM, structured): verdict `no_violation | violation | needs_review`, tier, rule IDs, rationale, cited segments, evidence refs.
6. **Guards** (code): rule IDs exist in `data/policy.md`; tier/rule consistency; one repair retry, then `needs_review`; approver-is-proposer flag; fixed outcome ladder picks the proposed action (most restrictive wins); adjudicator can't return `unsupported` for T1/T2; any failure → `needs_review`.

Structured output: `with_structured_output(method="function_calling")`, then pydantic validation; on failure, try parsing the reply text as JSON; then one nudge; then `needs_review`. Actions are proposed only; Approve/Reject records a reviewer decision and nothing executes. Corpus metadata and golden labels never reach a prompt (stripped when the case is loaded).

## Persistence (Postgres)
`cases` (id, content JSON, source), `golden_labels` (case_id, final, notes; UI/eval only), `evaluations` (id, case_id, status, verdict, tier, rule_ids, rationale, proposed_action, cited_segment_ids, evidence_refs, models, policy_version, golden_match, timestamps), `trace_events` (evaluation_id, seq, node, type, payload JSON, ts), `reviewer_decisions` (evaluation_id, decision, reviewer, note, ts). Portable column types. Seed script loads `data/corpus.jsonl` + `data/golden.csv`, stripping metadata.

## API (FastAPI, `/api/*`)
`GET/POST /cases`, `GET /cases/{id}`, `POST /runs`, `GET /runs/{id}/events` (SSE, `Last-Event-ID`/`?after=` replay), `GET /runs/{id}`, `GET /evaluations`, `POST /evaluations/{id}/reviewer-decision`, `GET /policy`, `POST /batch-eval`, `GET /health`. Runs execute as background asyncio tasks; trace events are saved as they happen and the SSE stream reads from the database. Optional `X-Access-Token`; `asyncio.Semaphore` caps concurrent runs (429 over the cap). FastAPI serves the built SPA with a fallback to `index.html`.

## Eval
11 golden cases: K-002, K-012, K-020, K-113, K-051, K-054, K-059, K-115, K-109 (in scope) + K-063, K-105 (expect `unsupported`; correct iff verdict is `unsupported`, counted separately, same rule in the UI's compare toggle). `no_violation` → `none`; violation → tier + sorted rules, exact match. Optional extra K-026 (R2.4). The eval CLI caches by (case, model config) and writes a markdown table for the report. A small model-comparison script measures structured-output reliability for a few free tool-capable OpenRouter models.

## Testing
pytest. Unit tests use LangChain fake chat models (no network) for routing, guards, tools, structured-output fallback. Repository tests run on SQLite in memory via the same SQLAlchemy models, plus an optional Postgres test gated by `TEST_DATABASE_URL` (a Neon branch). API tests with FastAPI's test client. One live smoke test gated by an env var. `ruff check` + `ruff format --check`; frontend `bun run check`.

## Steps
1. ~~Move FP2 data into `data/`~~ (done; `check_corpus.py` passes).
2. Python scaffold in `app/`: pyproject, ruff config, pytest, settings, `/api/health`. Live smoke: OpenRouter structured call + Neon `select 1`.
3. Pydantic models + policy registry (14 rules) + case loader that strips metadata.
4. DB layer: SQLAlchemy models, repositories, Alembic migration, seed script; tests.
5. Evidence tools + normalization; tests incl. K-109.
6. Guards + label mapping; table-driven tests.
7. LLM factory (per-role config) + structured-output wrapper with fallbacks.
8. Agents (intake, supervisor, evidence, adjudicator) + LangGraph graph; fake-model tests for every route, including different evidence plans for different T2 cases.
9. Run service (background task, trace persistence, concurrency cap) + FastAPI routes + SSE replay; API tests.
10. Eval CLI + model-comparison script.
11. Frontend design direction (one static page with the dithering/ASCII treatment) for approval.
12. Frontend screens: Cases (+ new case form), Run view (transcript / live trace / decision card with record-only Approve/Reject), History, Policy, Batch eval. Typed client from OpenAPI.
13. Dockerfile + `render.yaml`; local `docker build` + run.
14. Full checks (ruff, pytest, frontend check) and local end-to-end smoke on K-002, K-012, K-109.
15. Deploy to Render (with approval), run the eval on the live URL, fill `docs/FP3_report.md`.
16. Root README: prerequisites (uv, Python 3.13, Bun, Node ≥ 22.18), setup, env vars, migrate, seed, test, run, deploy.

## Risks
- Free OpenRouter models: tool-calling quality varies, availability churns, 1,000 requests/day. Per-role config and the comparison script make swapping cheap; Workers AI or paid models stay available through the same OpenAI-compatible settings.
- Render free web services sleep when idle (slow first request) and have no persistent disk; all state lives in Neon.
- Background runs live in the web process; a restart mid-run leaves that run marked failed (known limitation for the report).
- oxfmt is beta; pinned.
