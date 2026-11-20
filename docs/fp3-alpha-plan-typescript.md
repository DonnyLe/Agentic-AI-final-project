# Kangaroo FP3 alpha: TypeScript / Flue v2 plan

A standalone plan for building the Kangaroo alpha on TypeScript, Flue v2, Cloudflare Workers and Durable Objects. A separate Python plan (`docs/fp3-alpha-plan.md`) exists; this one doesn't depend on it.

Read first: `docs/fp3-alpha-brief.md` (FP3 requirements, corpus facts, agent design). Ignore its stack section where it conflicts with this file.

## What to copy from the current filesystem
- `data/`: FP2 corpus, golden set, policy, Python FP2 scripts (already moved and path-fixed; `python3 data/scripts/check_corpus.py` passes).
- `docs/fp3-alpha-brief.md`.
- `frontend/tools/oxlint/anti-slop/` (vendored anti-slop at commit `13909c9`, with `PROVENANCE.md`), `frontend/oxlint.config.ts`, `frontend/.oxfmtrc.json`: reuse for the whole TS project.
- `app/.env` for the secret values. It's written for the Python app, so translate it:
  - `OPENROUTER_API_KEY`: same name, works as-is.
  - `DATABASE_URL`: same value (Neon direct connection string); used for migrations and as the local Hyperdrive connection string.
  - `KANGAROO_MODEL_*`: Flue needs a provider prefix. `nvidia/nemotron-3.5-lightning:free` becomes `openrouter/nvidia/nemotron-3.5-lightning:free`.
  - Never commit `.env`.

## Stack (settled)
- TypeScript everywhere in the app. Bun as package manager; Vite and `cf` run on Node >= 22.18 (never `bun --bun`).
- Flue `@flue/*` 2.3.0 on Cloudflare Workers + Durable Objects. Hono for HTTP. Valibot schemas (Flue requires Valibot).
- Infra in `cloudflare.config.ts` with `@cloudflare/vite-plugin` 2.0 beta and the `cf` CLI (Wrangler only where needed, e.g. commands that don't read `cloudflare.config.ts`).
- Neon Postgres through Hyperdrive. Drizzle `pg-core` + `postgres` (postgres.js). All DB access behind repository interfaces in `src/db/`.
- LLMs: OpenRouter free models through Flue's built-in `openrouter` provider (the key has 1,000 free-model requests/day). Workers AI (`cloudflare/...`) as fallback.
- React + Vite + TS frontend served from the same Worker (Workers Static Assets). Tailwind CSS + Motion. Look: clean, artistic, minimal, dithering animations and ASCII art (inspired by instinct.com, Decagon). Show a design direction before building screens.
- oxlint + vendored anti-slop (all generic rules at error, Effect group skipped) + oxfmt (beta, pinned). `tsc --noEmit`. `@/*` import alias via tsconfig `paths` + Vite `resolve.tsconfigPaths: true`.
- Tests: Vitest. No `vi.mock` (anti-slop `no-module-mocking`): model calls sit behind a `RoleRunner` interface with a stub for tests. Repository tests against PGlite.
- Scope: T1 + T2 fully supported; T3/T4 → `unsupported`. Approve/Reject only records a decision. No MCP server, precedent RAG, write tools or code sandbox.

## Verified versions (2026-11-15)
`@flue/runtime` `@flue/vite` 2.3.0 · `@cloudflare/vite-plugin` 2.0.0-beta.v.17 · `cf` 1.0.0-beta.32 · `vite` 8.3.8 · `@vitejs/plugin-react` 6.3.0 · `react`/`react-dom` 19.3.1 · `typescript` 7.0.2 · `hono` 4.13.18 · `valibot` 1.5.0 · `drizzle-orm` 0.45.4 · `drizzle-kit` 0.31.11 · `postgres` 4.1.1 · `@electric-sql/pglite` 0.5.16 · `vitest` 5.1.0 · `oxlint` + `@oxlint/plugins` 1.93.0 · `oxfmt` 0.78.0 · `tailwindcss` + `@tailwindcss/vite` 4.3.5 · `@tanstack/react-query` 5.107.1 · `react-router` 8.5.1.

## Spike findings (already proven on this machine; reuse, don't rediscover)

1. **Flue + `cloudflare.config.ts` needs an adapter.** Flue 2.3.0's `flueWorkerConfig()` mutates a Wrangler-format config in place; plugin 2.0 calls its customizer with the parsed `cloudflare.config.ts` object and expects a new object back. This adapter worked (built config contained `FLUE_PING_AGENT` and its SQLite export):

   ```ts
   // infra/flue-adapter.ts
   import type { CloudflareConfig } from "@cloudflare/vite-plugin";
   import { bindings, exports } from "cf/config";

   interface WranglerDoBinding { name: string; class_name: string }
   interface WranglerDraft {
     main?: string;
     compatibility_date?: string;
     compatibility_flags?: string[];
     durable_objects?: { bindings?: WranglerDoBinding[] };
   }
   type FlueCustomizer = (draft: WranglerDraft) => void;

   export function withFlueAgents(flueCustomizer: FlueCustomizer) {
     return (loaded: CloudflareConfig): CloudflareConfig => {
       const worker = loaded.worker;
       if (worker === undefined) throw new Error("cloudflare.config.ts must define a worker for Flue.");

       const draft: WranglerDraft = {
         compatibility_date: worker.compatibilityDate,
         compatibility_flags: [...(worker.compatibilityFlags ?? [])],
         durable_objects: { bindings: [] },
       };
       flueCustomizer(draft);

       const env = { ...worker.env };
       const workerExports = { ...worker.exports };
       for (const binding of draft.durable_objects?.bindings ?? []) {
         env[binding.name] = bindings.durableObject({ worker: worker.name, exportName: binding.class_name });
         workerExports[binding.class_name] = exports.durableObject({ storage: "sqlite" });
       }

       return {
         ...loaded,
         worker: {
           ...worker,
           entrypoint: worker.entrypoint ?? draft.main,
           compatibilityFlags: draft.compatibility_flags,
           env,
           exports: workerExports,
         },
       };
     };
   }
   ```

   ```ts
   // vite.config.ts
   export default defineConfig({
     resolve: { tsconfigPaths: true },
     plugins: [
       flue({ providers: ["cloudflare", "openrouter"] }),   // flue() before cloudflare()
       cloudflare({ config: withFlueAgents(flueWorkerConfig()) }),
       react(),
     ],
   });
   ```

2. **Pin Flue's model libraries.** `@earendil-works/pi-ai` 1.5.0 removed the `Type` export that `@flue/runtime` 2.3.0 imports, so the build fails. In `package.json`:
   ```json
   "overrides": { "@earendil-works/pi-ai": "1.4.0", "@earendil-works/pi-agent-core": "1.4.0" }
   ```
   Remove when Flue ships a release compatible with pi-ai >= 1.5.

3. **`cloudflare.config.ts` shape that worked.** Non-secret settings (models) are read from `.env` at config time via `process.loadEnvFile(".env")`; secrets declared with `bindings.secret()`. `nodejs_compat` populates `process.env`, which Flue's providers read keys from.
   ```ts
   env: {
     AI: bindings.ai({ dev: { remote: true } }),   // Workers AI has no local emulator
     OPENROUTER_API_KEY: bindings.secret(),
     KANGAROO_MODEL_DEFAULT: bindings.text(defaultModel),
     KANGAROO_MODEL_INTAKE: bindings.text(setting("KANGAROO_MODEL_INTAKE", defaultModel)),
     // ...SUPERVISOR, EVIDENCE, ADJUDICATOR
     CASE_RUN: bindings.durableObject({ worker: WORKER_NAME, exportName: "CaseRun" }),
   },
   exports: { CaseRun: exports.durableObject({ storage: "sqlite" }) },
   assets: { notFoundHandling: "single-page-application", runWorkerFirst: ["/api/*"] },
   compatibilityDate: "2026-11-01", compatibilityFlags: ["nodejs_compat"],
   ```
   Hyperdrive: `bindings.hyperdrive({ id: HYPERDRIVE_ID, dev: { connectionString: DATABASE_URL } })`. Create the config with `cf hyperdrive create` (`--origin-host/--origin-user/--origin-password/--origin-database/--origin-scheme postgresql`), parsing `DATABASE_URL` without printing the password.

4. **Calling agents from our own code works.** `init(Agent, { id })` → `handle.dispatch(message)` → `handle.read(receipt)` works from a Hono route and from our own Durable Object. Don't mount Flue's `createAgentRouter` (it has no auth).

5. **Typed output pattern.** One submit tool per role whose `run` writes through a `useDataWriter("result", { schema })` writer and returns `{ output: "recorded", terminate: true }`. The caller reads `reply.data.result[0]`. Verified with Workers AI (`gpt-oss-120b`) and OpenRouter (`nvidia/nemotron-3.5-lightning:free`, 3/3 calls used the tool, 0.5–1.5 s each).

6. **Models sometimes skip the submit tool** and answer in plain JSON text (seen once with `gpt-oss-120b`). `RoleRunner` fallback order: submit-tool data → Valibot-parse the reply text → one nudge to the same instance ("call submit_* now") → `needs_review`.

7. **Other facts.** `AgentProps` gives an agent its instance `id`. `initialData` (Valibot schema static) can carry the case into an agent once at creation, so tools can read it without a DB lookup. Bindings that name the Worker by string generate untyped DO stubs; use one `// SAFETY:`-commented cast (`c.env.CASE_RUN as DurableObjectNamespace<CaseRun>`). anti-slop needed no overrides for Flue `run({ data })` or Hono handlers. Bun blocks three harmless postinstalls (protobufjs, core-js-pure, @google/genai); workerd isn't blocked. `cf whoami` shows the account is logged in.

## Layout
Single Vite project (the Worker, DOs and React SPA build together):
```
cloudflare.config.ts  vite.config.ts  oxlint.config.ts  .oxfmtrc.json  tsconfig.json  package.json  bun.lock
.env.example  .gitignore
infra/flue-adapter.ts
tools/oxlint/anti-slop/           (copied)
drizzle/                          schema + migrations
scripts/  seed.ts  eval.ts  compare-models.ts
src/
  app.ts                          Hono app (Flue's HTTP entry)
  cloudflare.ts                   DO exports (CaseRun, Limiter)
  agents/                         intake, supervisor, evidence, adjudicator
  tools/                          evidence tools + key normalization
  orchestration/                  CaseRun flow, RoleRunner (+ stub)
  guards/                         policy registry, ladder, checks
  schemas/                        Valibot (shared with client)
  db/                             Drizzle schema, repository interfaces, Postgres impl, in-memory fake
  client/                         React app
data/  docs/
```

## Agent flow (inside `CaseRun`, one DO per run)
1. **Intake** (Flue agent): action class T1–T4, proposers, cited segments, entities.
2. **T3/T4 → `unsupported`** in code.
3. **Supervisor** (Flue agent): evidence plan per case (T1 → adjudicate; T2 with third-party claim → duplicate search + dependency check + ticket; T2 without → duplicate search), then after each round: adjudicate / one more round (max 2) / escalate to `needs_review`. Reasons go to the trace.
4. **Evidence** (Flue agent + tools): `search_tickets`, `get_ticket`, `verify_dependency`, `get_team_roster`, `get_transcript_segments`. Read the case evidence snapshot, normalize key variants (approval/approvals, package_registry(_lookup), upstream_issue(s)(_lookup), repro/repro_steps/reproduction_steps), mark evidence text untrusted, regex-flag possible injection for the UI.
5. **Adjudicator** (Flue agent): verdict `no_violation | violation | needs_review`, tier, rule IDs, rationale, cited segments, evidence refs.
6. **Guards** (code): rule IDs exist in `data/policy.md` (14 rules, parsed from `**R1.1 · Name.** text` lines); tier/rule consistency; one repair retry then `needs_review`; approver-is-proposer flag; fixed outcome ladder (refuse > hold > needs-info > redirect/link > flag > proceed) picks the proposed action; adjudicator can't return `unsupported` for T1/T2; any failure → `needs_review`.

Corpus metadata and golden labels never reach a prompt: strip them in the seed script (keep only `id` + `content`; note that `review_status` legitimately appears inside K-123's evidence). Some cases have `null` meeting date/weekday/timezone on purpose.

## Data (Neon via Hyperdrive)
`cases`, `golden_labels` (UI/eval only), `evaluations`, `trace_events` (saved as they happen), `reviewer_decisions`. Portable column types; JSON parsed with Valibot on read.

## API (Hono, `/api/*`)
`GET/POST /cases`, `GET /cases/:id`, `POST /runs`, `GET /runs/:id/events` (SSE via `streamSSE`, `?after=` replay from the trace table), `GET /runs/:id`, `GET /evaluations`, `POST /evaluations/:id/reviewer-decision`, `GET /policy`, `POST /batch-eval`, `GET /health`. Optional access token; `Limiter` DO (plain counter, single-threaded) caps concurrent runs → 429. Export `AppType` for the `hc` client.

## Eval
11 golden cases: K-002, K-012, K-020, K-113, K-051, K-054, K-059, K-115, K-109 (in scope) + K-063, K-105 (expect `unsupported`; correct iff verdict is `unsupported`, counted separately, same rule in the UI compare toggle). `no_violation` → `none`; violation → tier + sorted rules, exact match. Optional K-026 (R2.4). Eval CLI caches by (case, model config). `compare-models.ts` runs ~10 trials per free tool-capable OpenRouter model and reports submit-tool reliability.

## Steps
1. Copy files listed above; scaffold the single Vite project; adapter; pi-ai overrides; `bun install`; `bun run build`; `vite dev`.
2. Spike again quickly: one agent + submit tool on the OpenRouter model, called from a Hono route and from `CaseRun`; Hyperdrive `select 1` against Neon; lint with anti-slop.
3. Valibot schemas (recursive JSON type for evidence; case, intake, routing, tool result, finding, verdict, trace event).
4. `src/db`: Drizzle schema, repository interfaces + Postgres impl + in-memory fake, migrations, PGlite tests.
5. Seed script (`bun scripts/seed.ts`) to Neon via `DATABASE_URL`.
6. `RoleRunner` interface + Flue implementation (with the fallback order above) + stub.
7. Four agents + per-role model config.
8. Evidence tools + normalization; tests incl. K-109.
9. Guards + label mapping; table-driven tests.
10. `CaseRun` orchestration; tests for T1 direct, T2 with and without a library claim (different evidence plans), guard `needs_review`, forced `unsupported`.
11. Hono API + SSE replay + access token + `Limiter`; route tests with fake repos.
12. Eval CLI + model comparison.
13. Frontend design direction for approval, then screens: Cases (+ new case form), Run view (transcript / live trace / decision card with record-only Approve/Reject), History, Policy, Batch eval.
14. Full checks (typecheck, oxlint, oxfmt, vitest); local smoke on K-002, K-012, K-109.
15. Deploy with `cf deploy` (ask the user first; it creates a public workers.dev URL). Set secrets in production. Run the eval on the live URL; fill `docs/FP3_report.md`.
16. README: prerequisites (Bun, Node >= 22.18), setup, env, migrate, seed, test, dev, deploy; note the pi-ai pin.

## Risks
- Flue + plugin 2.0 beta + `cf` beta: our adapter is glue Flue doesn't document; pin versions.
- pi-ai pin may block newer model metadata.
- Free OpenRouter models: tool-calling quality varies, availability churns, 1,000 requests/day.
- Workers AI fallback uses daily free neurons (10,000/day).
- No mid-run resume if a DO is evicted (known limitation for the report).
- oxfmt beta.

## Rules for whoever implements this
- Never commit `.env` or credentials; don't print secrets in logs.
- No AI attribution in commits, PRs or files.
- Commit or push only when the user asks.
